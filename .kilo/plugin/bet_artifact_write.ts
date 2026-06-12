import { tool } from "@kilocode/plugin/tool"
import {
  appendFileSync,
  closeSync,
  existsSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  realpathSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs"
import { createHash, randomUUID } from "node:crypto"
import { dirname, extname, join, normalize, relative, resolve } from "node:path"

const AUDIT_DIR = "reports/agent-config/artifact-writer-audit"
const MAX_CONTENT_BYTES = 256 * 1024
const PHASE_HANDOFFS = new Set([
  ".kilo/state/phase-A-handoff.md",
  ".kilo/state/phase-B-handoff.md",
  ".kilo/state/phase-C-handoff.md",
  ".kilo/state/phase-D-handoff.md",
  ".kilo/state/phase-E-handoff.md",
])
const REPORT_ROOTS = ["reports/betting-demo", "reports/betting"]
const CONTENT_TYPE_EXTENSION: Record<"markdown" | "json", ".md" | ".json"> = {
  markdown: ".md",
  json: ".json",
}
const SECRET_PATTERNS = [
  /(?:api[_-]?key|apikey|token|secret|password|passwd|pwd|credential|auth)[\s:=]+['"]?[^\s'"<>]+['"]?/gi,
  /Bearer\s+[A-Za-z0-9._-]+/gi,
  /sk-[A-Za-z0-9]{20,}/gi,
]

type ContentType = "markdown" | "json"
type ResultStatus = "success" | "failed" | "blocked" | "invalid_request" | "cancelled"
type ErrorCode =
  | "NONE"
  | "CAPABILITY_CANCELLED"
  | "PATH_ABSOLUTE"
  | "PATH_TRAVERSAL"
  | "PATH_NOT_ALLOWED"
  | "PATH_SYMLINK_ESCAPE"
  | "PATH_ENCODED_TRAVERSAL"
  | "PATH_INVALID"
  | "EXTENSION_MISMATCH"
  | "CONTENT_BINARY"
  | "CONTENT_TOO_LARGE"
  | "CONTENT_INVALID_JSON"
  | "CONTENT_SECRET_DETECTED"
  | "EXISTS_CREATE_ONLY"
  | "EXPECTED_HASH_REQUIRED"
  | "EXPECTED_HASH_MISMATCH"
  | "LOCK_CONFLICT"
  | "WRITE_FAILED"

interface WriteResult {
  schema_version: number
  status: ResultStatus
  error_code: ErrorCode
  request_id: string
  path: string | null
  bytes_written: number
  sha256: string | null
  created: boolean
  overwritten: boolean
  error: string | null
}

interface AuditEntry {
  timestamp: string
  request_id: string
  session_id: string | null
  message_id: string | null
  path: string
  status: ResultStatus
  error_code: ErrorCode
  created: boolean
  overwritten: boolean
  bytes_written: number
  sha256: string | null
  expected_sha256: string | null
  previous_sha256: string | null
  content_type: ContentType
  create_only: boolean
  reason: string | null
}

function makeResult(input: Omit<WriteResult, "schema_version">): WriteResult {
  return { schema_version: 1, ...input }
}

function computeSha256(content: string): string {
  return createHash("sha256").update(content, "utf8").digest("hex")
}

function isBinaryLike(content: string): boolean {
  return /\u0000/.test(content) || /[\u0001-\u0008\u000B\u000C\u000E-\u001F]/.test(content)
}

function containsSecrets(content: string): boolean {
  return SECRET_PATTERNS.some((pattern) => {
    pattern.lastIndex = 0
    return pattern.test(content)
  })
}

function lstatIfExists(path: string) {
  try {
    return lstatSync(path)
  } catch {
    return null
  }
}

function decodePath(rawPath: string): string {
  try {
    return decodeURIComponent(rawPath)
  } catch {
    return rawPath
  }
}

function normalizeRelativePath(rawPath: string): string {
  return normalize(rawPath.replace(/\\/g, "/")).replace(/^\.\//, "")
}

function isAllowedPath(path: string): boolean {
  if (PHASE_HANDOFFS.has(path)) return true
  return REPORT_ROOTS.some((root) => path.startsWith(`${root}/`))
}

function validatePath(path: string, repoRoot: string, contentType: ContentType): { ok: true; normalized: string; absolute: string } | { ok: false; code: ErrorCode; message: string } {
  if (path.startsWith("/")) {
    return { ok: false, code: "PATH_ABSOLUTE", message: "Absolute paths are not allowed" }
  }

  const decoded = decodePath(path)
  const normalized = normalizeRelativePath(decoded)

  if (decoded.includes("..") || normalized.includes("../") || normalized === "..") {
    return { ok: false, code: decoded !== path ? "PATH_ENCODED_TRAVERSAL" : "PATH_TRAVERSAL", message: "Path traversal is not allowed" }
  }

  if (!isAllowedPath(normalized)) {
    return { ok: false, code: "PATH_NOT_ALLOWED", message: "Path is outside approved artifact roots" }
  }

  const expectedExt = CONTENT_TYPE_EXTENSION[contentType]
  if (extname(normalized) !== expectedExt) {
    return { ok: false, code: "EXTENSION_MISMATCH", message: `Expected ${expectedExt} for ${contentType}` }
  }

  const repoReal = realpathSync(repoRoot)
  const absolute = resolve(repoReal, normalized)
  const parentDir = dirname(absolute)

  try {
    const parentReal = realpathSync(existsSync(parentDir) ? parentDir : dirname(parentDir))
    if (!parentReal.startsWith(repoReal)) {
      return { ok: false, code: "PATH_SYMLINK_ESCAPE", message: "Resolved parent escapes repository" }
    }
  } catch {
    return { ok: false, code: "PATH_INVALID", message: "Parent path cannot be resolved safely" }
  }

  const relativeToRepo = relative(repoReal, absolute)
  if (relativeToRepo.startsWith("..") || relativeToRepo.includes("../")) {
    return { ok: false, code: "PATH_TRAVERSAL", message: "Resolved path escapes repository" }
  }

  let current = repoReal
  for (const part of normalized.split("/")) {
    current = resolve(current, part)
    const stat = lstatIfExists(current)
    if (!stat) continue
    if (stat.isSymbolicLink()) {
      let target: string
      try {
        target = realpathSync(current)
      } catch {
        return { ok: false, code: "PATH_SYMLINK_ESCAPE", message: "Broken symlink detected" }
      }
      if (!target.startsWith(repoReal)) {
        return { ok: false, code: "PATH_SYMLINK_ESCAPE", message: "Symlink escape detected" }
      }
    }
  }

  return { ok: true, normalized, absolute }
}

function appendAudit(entry: AuditEntry, repoRoot: string): void {
  const dir = join(repoRoot, AUDIT_DIR)
  mkdirSync(dir, { recursive: true })
  const file = join(dir, `audit-${new Date().toISOString().slice(0, 10)}.jsonl`)
  appendFileSync(file, `${JSON.stringify(entry)}\n`, "utf8")
}

function finalize(result: WriteResult, repoRoot: string, meta: Omit<AuditEntry, "status" | "error_code" | "created" | "overwritten" | "bytes_written" | "sha256" | "reason"> & { reason?: string | null; previous_sha256?: string | null; expected_sha256?: string | null }): string {
  appendAudit({
    timestamp: new Date().toISOString(),
    request_id: result.request_id,
    session_id: meta.session_id,
    message_id: meta.message_id,
    path: meta.path,
    status: result.status,
    error_code: result.error_code,
    created: result.created,
    overwritten: result.overwritten,
    bytes_written: result.bytes_written,
    sha256: result.sha256,
    expected_sha256: meta.expected_sha256 ?? null,
    previous_sha256: meta.previous_sha256 ?? null,
    content_type: meta.content_type,
    create_only: meta.create_only,
    reason: meta.reason ?? result.error,
  }, repoRoot)
  return JSON.stringify(result, null, 2)
}

async function throwIfAborted(signal: AbortSignal): Promise<void> {
  if (signal.aborted) {
    throw new Error("CAPABILITY_CANCELLED")
  }
  await new Promise((resolve) => setImmediate(resolve))
  if (signal.aborted) {
    throw new Error("CAPABILITY_CANCELLED")
  }
}

export default tool({
  description: [
    "Persist betting artifacts to approved paths only.",
    "Supports phase handoffs and report artifacts via atomic writes.",
    "Enforces path constraints, content validation, CAS overwrite protection, and audit logging.",
    "Returns relative path, bytes written, and SHA-256 hash.",
  ].join(" "),
  args: {
    path: tool.schema.string().min(1).max(256).describe("Approved relative artifact path"),
    content: tool.schema.string().min(1).max(MAX_CONTENT_BYTES).describe("UTF-8 markdown or JSON payload"),
    content_type: tool.schema.enum(["markdown", "json"]).default("markdown").describe("Artifact content type"),
    expected_sha256: tool.schema.string().length(64).optional().describe("Required existing SHA-256 for any overwrite"),
    create_only: tool.schema.boolean().default(true).describe("If true, creation fails when the path already exists"),
  },
  async execute(args, context) {
    const requestId = `art-${randomUUID()}`
    const sessionId = process.env.KILO_SESSION_ID ?? context.sessionID ?? null
    const messageId = process.env.KILO_MESSAGE_ID ?? context.messageID ?? null
    const repoRoot = context.directory
    const contentType = args.content_type as ContentType
    const metaBase = {
      session_id: sessionId,
      message_id: messageId,
      path: args.path,
      content_type: contentType,
      create_only: args.create_only,
    }

    try {
      await throwIfAborted(context.abort)
    } catch {
      return finalize(makeResult({
        status: "cancelled",
        error_code: "CAPABILITY_CANCELLED",
        request_id: requestId,
        path: null,
        bytes_written: 0,
        sha256: null,
        created: false,
        overwritten: false,
        error: "Request cancelled before execution",
      }), repoRoot, metaBase)
    }

    const bytes = Buffer.byteLength(args.content, "utf8")
    if (bytes > MAX_CONTENT_BYTES) {
      return finalize(makeResult({
        status: "invalid_request",
        error_code: "CONTENT_TOO_LARGE",
        request_id: requestId,
        path: null,
        bytes_written: 0,
        sha256: null,
        created: false,
        overwritten: false,
        error: `Content exceeds ${MAX_CONTENT_BYTES} bytes`,
      }), repoRoot, metaBase)
    }

    if (isBinaryLike(args.content)) {
      return finalize(makeResult({
        status: "invalid_request",
        error_code: "CONTENT_BINARY",
        request_id: requestId,
        path: null,
        bytes_written: 0,
        sha256: null,
        created: false,
        overwritten: false,
        error: "Binary or control-character content is not allowed",
      }), repoRoot, metaBase)
    }

    if (containsSecrets(args.content)) {
      return finalize(makeResult({
        status: "blocked",
        error_code: "CONTENT_SECRET_DETECTED",
        request_id: requestId,
        path: null,
        bytes_written: 0,
        sha256: null,
        created: false,
        overwritten: false,
        error: "Secret-like content detected",
      }), repoRoot, metaBase)
    }

    if (contentType === "json") {
      try {
        JSON.parse(args.content)
      } catch {
        return finalize(makeResult({
          status: "invalid_request",
          error_code: "CONTENT_INVALID_JSON",
          request_id: requestId,
          path: null,
          bytes_written: 0,
          sha256: null,
          created: false,
          overwritten: false,
          error: "Invalid JSON content",
        }), repoRoot, metaBase)
      }
    }

    const validated = validatePath(args.path, repoRoot, contentType)
    if (!validated.ok) {
      return finalize(makeResult({
        status: "blocked",
        error_code: validated.code,
        request_id: requestId,
        path: null,
        bytes_written: 0,
        sha256: null,
        created: false,
        overwritten: false,
        error: validated.message,
      }), repoRoot, metaBase)
    }

    const sha256 = computeSha256(args.content)
    const parentDir = dirname(validated.absolute)
    mkdirSync(parentDir, { recursive: true })

    const repoReal = realpathSync(repoRoot)
    const parentReal = realpathSync(parentDir)
    if (!parentReal.startsWith(repoReal)) {
      return finalize(makeResult({
        status: "blocked",
        error_code: "PATH_SYMLINK_ESCAPE",
        request_id: requestId,
        path: null,
        bytes_written: 0,
        sha256: null,
        created: false,
        overwritten: false,
        error: "Parent directory escapes repository",
      }), repoRoot, metaBase)
    }

    const lockPath = `${validated.absolute}.lock`
    const tempPath = `${validated.absolute}.tmp-${requestId}`
    let lockFd: number | null = null

    try {
      await throwIfAborted(context.abort)
      lockFd = openSync(lockPath, "wx")
    } catch (error) {
      const code = error instanceof Error && error.message === "CAPABILITY_CANCELLED" ? "CAPABILITY_CANCELLED" : "LOCK_CONFLICT"
      const status: ResultStatus = code === "CAPABILITY_CANCELLED" ? "cancelled" : "failed"
      const message = code === "CAPABILITY_CANCELLED" ? "Request cancelled before lock acquisition" : "Another write is already in progress for this path"
      return finalize(makeResult({
        status,
        error_code: code,
        request_id: requestId,
        path: null,
        bytes_written: 0,
        sha256: code === "LOCK_CONFLICT" ? sha256 : null,
        created: false,
        overwritten: false,
        error: message,
      }), repoRoot, metaBase)
    }

    let previousSha256: string | null = null
    let existed = false

    try {
      await throwIfAborted(context.abort)
      const targetStat = lstatIfExists(validated.absolute)
      existed = Boolean(targetStat)
      if (targetStat) {
        if (targetStat.isSymbolicLink()) {
          return finalize(makeResult({
            status: "blocked",
            error_code: "PATH_SYMLINK_ESCAPE",
            request_id: requestId,
            path: null,
            bytes_written: 0,
            sha256: null,
            created: false,
            overwritten: false,
            error: "Target path resolves through a symlink",
          }), repoRoot, { ...metaBase, previous_sha256: null })
        }
        previousSha256 = computeSha256(readFileSync(validated.absolute, "utf8"))
      }

      if (args.create_only && existed) {
        return finalize(makeResult({
          status: "failed",
          error_code: "EXISTS_CREATE_ONLY",
          request_id: requestId,
          path: null,
          bytes_written: 0,
          sha256,
          created: false,
          overwritten: false,
          error: "File already exists and create_only is true",
        }), repoRoot, { ...metaBase, previous_sha256: previousSha256, expected_sha256: args.expected_sha256 ?? null })
      }

      if (!args.create_only && existed && !args.expected_sha256) {
        return finalize(makeResult({
          status: "failed",
          error_code: "EXPECTED_HASH_REQUIRED",
          request_id: requestId,
          path: null,
          bytes_written: 0,
          sha256,
          created: false,
          overwritten: false,
          error: "expected_sha256 is required for overwrite",
        }), repoRoot, { ...metaBase, previous_sha256: previousSha256 })
      }

      if (existed && args.expected_sha256 && args.expected_sha256 !== previousSha256) {
        return finalize(makeResult({
          status: "failed",
          error_code: "EXPECTED_HASH_MISMATCH",
          request_id: requestId,
          path: null,
          bytes_written: 0,
          sha256,
          created: false,
          overwritten: false,
          error: "expected_sha256 does not match existing content",
        }), repoRoot, { ...metaBase, previous_sha256: previousSha256, expected_sha256: args.expected_sha256 })
      }

      await throwIfAborted(context.abort)
      writeFileSync(tempPath, args.content, { encoding: "utf8", flag: "wx" })
      await throwIfAborted(context.abort)
      renameSync(tempPath, validated.absolute)

      const result = makeResult({
        status: "success",
        error_code: "NONE",
        request_id: requestId,
        path: validated.normalized,
        bytes_written: bytes,
        sha256,
        created: !existed,
        overwritten: existed,
        error: null,
      })
      return finalize(result, repoRoot, { ...metaBase, path: validated.normalized, previous_sha256: previousSha256, expected_sha256: args.expected_sha256 ?? null })
    } catch (error) {
      if (existsSync(tempPath)) rmSync(tempPath, { force: true })
      const cancelled = error instanceof Error && error.message === "CAPABILITY_CANCELLED"
      return finalize(makeResult({
        status: cancelled ? "cancelled" : "failed",
        error_code: cancelled ? "CAPABILITY_CANCELLED" : "WRITE_FAILED",
        request_id: requestId,
        path: null,
        bytes_written: 0,
        sha256: cancelled ? null : sha256,
        created: false,
        overwritten: false,
        error: cancelled ? "Request cancelled during write" : "Artifact write failed",
      }), repoRoot, { ...metaBase, previous_sha256: previousSha256, expected_sha256: args.expected_sha256 ?? null })
    } finally {
      if (lockFd !== null) {
        try {
          closeSync(lockFd)
        } catch {}
        try {
          rmSync(lockPath, { force: true })
        } catch {}
      }
      if (existsSync(tempPath)) {
        try {
          rmSync(tempPath, { force: true })
        } catch {}
      }
    }
  },
})
