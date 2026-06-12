import { tool } from "@kilocode/plugin/tool"
import { spawn } from "node:child_process"
import { join, resolve, dirname, basename } from "node:path"
import { readFileSync, existsSync, realpathSync, statSync, mkdirSync, writeFileSync, appendFileSync } from "node:fs"
import { createHash, randomUUID } from "node:crypto"

// =============================================================================
// CONFIGURATION
// =============================================================================

const MANIFEST_PATH = "config/bet-script-operations.json"
const LOG_PATH = "reports/bet-script-executor/runs"
const ARTIFACT_PATH = "reports/bet-script-executor/artifacts"
const DEDUP_STATE_PATH = "reports/bet-script-executor/dedup-state"

// Deduplication configuration
const DEDUP_TTL_MS = 60000 // 60 seconds TTL for completed results
const STALE_LOCK_TTL_MS = 30000 // 30 seconds TTL for stale lock recovery

// Secret patterns for redaction
const SECRET_PATTERNS = [
  /(?:api[_-]?key|apikey|token|secret|password|passwd|pwd|credential|auth)[\s:=]+['"]?[^\s'"<>]+['"]?/gi,
  /['"]?[A-Za-z0-9_-]{20,}['"]?/g,  // Long strings that could be tokens
  /Bearer\s+[A-Za-z0-9_-]+/gi,
  /sk-[A-Za-z0-9]{20,}/gi,  // OpenAI-style keys
  /[a-f0-9]{32,}/gi,  // Hex strings (could be hashes/tokens)
]

// =============================================================================
// DEDUPLICATION STATE
// =============================================================================

interface ExecutionState {
  key: string
  status: "in_flight" | "completed"
  startedAt: number
  requestId: string
  result?: ExecutionResult
  pid?: number
}

// In-memory map for same-process coordination
const executionState = new Map<string, ExecutionState>()

// Bounded completed-result cache with TTL
const completedCache = new Map<string, { result: ExecutionResult; completedAt: number }>()

function buildDedupKey(
  sessionId: string | null,
  messageId: string | null,
  operation: string,
  args: Record<string, unknown>,
): string {
  // Canonical key: sessionID:messageID:operation:argsHash
  // Use stable key ordering for argument serialization
  const sortedArgs = Object.keys(args)
    .sort()
    .reduce((acc, key) => {
      acc[key] = args[key]
      return acc
    }, {} as Record<string, unknown>)

  const argsHash = createHash("sha256")
    .update(JSON.stringify(sortedArgs))
    .digest("hex")
    .slice(0, 16)

  // Include session and message ID for proper deduplication
  const sessionPart = sessionId || "no-session"
  const messagePart = messageId || "no-message"

  return `${sessionPart}:${messagePart}:${operation}:${argsHash}`
}

function checkDuplicate(key: string): { isDuplicate: boolean; state?: ExecutionState; cachedResult?: ExecutionResult } {
  const now = Date.now()

  // Check in-flight executions
  const inFlight = executionState.get(key)
  if (inFlight) {
    // Check for stale lock
    if (inFlight.status === "in_flight" && now - inFlight.startedAt > STALE_LOCK_TTL_MS) {
      // Stale lock - allow recovery
      executionState.delete(key)
    } else {
      return { isDuplicate: true, state: inFlight }
    }
  }

  // Check completed cache
  const cached = completedCache.get(key)
  if (cached) {
    if (now - cached.completedAt < DEDUP_TTL_MS) {
      return { isDuplicate: true, cachedResult: cached.result }
    } else {
      // Expired - remove from cache
      completedCache.delete(key)
    }
  }

  return { isDuplicate: false }
}

function markInFlight(key: string, requestId: string): void {
  executionState.set(key, {
    key,
    status: "in_flight",
    startedAt: Date.now(),
    requestId,
  })
}

function markCompleted(key: string, result: ExecutionResult): void {
  // Remove from in-flight
  executionState.delete(key)

  // Add to completed cache
  completedCache.set(key, {
    result,
    completedAt: Date.now(),
  })

  // Bounded cache - remove oldest entries if too large
  if (completedCache.size > 100) {
    const entries = Array.from(completedCache.entries())
      .sort((a, b) => a[1].completedAt - b[1].completedAt)
    // Remove oldest 50 entries
    for (let i = 0; i < 50; i++) {
      completedCache.delete(entries[i][0])
    }
  }
}

// =============================================================================
// TYPES
// =============================================================================

interface OperationManifest {
  schema_version: number
  description?: string
  operations: Record<string, Operation>
}

interface Operation {
  description: string
  executable: string
  script: string
  working_directory: string
  timeout_seconds: number
  max_stdout_bytes: number
  max_stderr_bytes: number
  allowed_arguments: Record<string, ArgumentSpec>
  environment_allowlist: string[]
  read_only: boolean
  idempotent: boolean
}

interface ArgumentSpec {
  type: "string" | "integer" | "boolean"
  pattern?: string
  minimum?: number
  maximum?: number
  required?: boolean
  default?: unknown
  description?: string
}

interface ExecutionResult {
  schema_version: number
  status: "success" | "failed" | "timeout" | "cancelled" | "output_limit_exceeded" | "invalid_request" | "executor_error" | "duplicate_in_flight" | "duplicate_completed"
  request_id: string
  operation: string
  started_at: string
  duration_ms: number
  exit_code: number | null
  timed_out: boolean
  cancelled: boolean
  subprocesses_started: number
  stdout: OutputCapture
  stderr: OutputCapture
  parsed_result: Record<string, unknown>
  warnings: string[]
  error: string | null
}

interface OutputCapture {
  summary: string
  bytes_captured: number
  truncated: boolean
  artifact_path: string | null
}

interface LogEntry {
  timestamp: string
  request_id: string
  session_id: string | null
  message_id: string | null
  dedup_key: string
  operation: string
  arguments_hash: string
  script_identity: string
  start_time: string
  duration_ms: number
  exit_code: number | null
  status: string
  subprocesses_started: number
  bytes_captured: number
  truncation: boolean
  timeout: boolean
  cancellation: boolean
  artifact_paths: string[]
  error_category: string | null
}

// =============================================================================
// VALIDATION
// =============================================================================

function validatePath(path: string, repoRoot: string): boolean {
  // Reject absolute paths
  if (path.startsWith("/")) return false
  
  // Reject path traversal
  if (path.includes("..")) return false
  
  // Reject shell metacharacters
  const dangerous = /[|;&$`\\(){}<>!*?[\]]/
  if (dangerous.test(path)) return false
  
  // Resolve and verify it stays within repo
  try {
    const resolved = resolve(repoRoot, path)
    const realRepoRoot = realpathSync(repoRoot)
    const realPath = realpathSync(resolved)
    return realPath.startsWith(realRepoRoot)
  } catch {
    return false
  }
}

function validateArgument(value: unknown, spec: ArgumentSpec): { valid: boolean; error?: string; coerced?: unknown } {
  if (value === undefined || value === null) {
    if (spec.required) {
      return { valid: false, error: "Required argument missing" }
    }
    return { valid: true, coerced: spec.default }
  }
  
  switch (spec.type) {
    case "string": {
      if (typeof value !== "string") {
        return { valid: false, error: `Expected string, got ${typeof value}` }
      }
      if (spec.pattern) {
        const regex = new RegExp(spec.pattern)
        if (!regex.test(value)) {
          return { valid: false, error: `Value does not match pattern ${spec.pattern}` }
        }
      }
      // Reject shell metacharacters
      const dangerous = /[|;&$`\\(){}<>!*?\[\]]/
      if (dangerous.test(value)) {
        return { valid: false, error: "Value contains forbidden characters" }
      }
      return { valid: true, coerced: value }
    }
    
    case "integer": {
      const num = Number(value)
      if (!Number.isInteger(num)) {
        return { valid: false, error: `Expected integer, got ${typeof value}` }
      }
      if (spec.minimum !== undefined && num < spec.minimum) {
        return { valid: false, error: `Value ${num} below minimum ${spec.minimum}` }
      }
      if (spec.maximum !== undefined && num > spec.maximum) {
        return { valid: false, error: `Value ${num} above maximum ${spec.maximum}` }
      }
      return { valid: true, coerced: num }
    }
    
    case "boolean": {
      if (typeof value === "boolean") {
        return { valid: true, coerced: value }
      }
      if (value === "true" || value === "1") {
        return { valid: true, coerced: true }
      }
      if (value === "false" || value === "0") {
        return { valid: true, coerced: false }
      }
      return { valid: false, error: `Expected boolean, got ${typeof value}` }
    }
    
    default:
      return { valid: false, error: `Unknown type: ${spec.type}` }
  }
}

function redactSecrets(text: string): string {
  let result = text
  for (const pattern of SECRET_PATTERNS) {
    result = result.replace(pattern, "[REDACTED]")
  }
  return result
}

// =============================================================================
// LOGGING
// =============================================================================

function appendLog(entry: LogEntry, repoRoot: string): void {
  try {
    const logDir = join(repoRoot, LOG_PATH)
    const logFile = join(logDir, `executor-${new Date().toISOString().slice(0, 10)}.jsonl`)
    
    // Ensure directory exists
    if (!existsSync(logDir)) {
      mkdirSync(logDir, { recursive: true })
    }
    
    const line = JSON.stringify(entry) + "\n"
    appendFileSync(logFile, line, "utf8")
  } catch {
    // Silently fail logging
  }
}

// =============================================================================
// EXECUTION
// =============================================================================

async function executeOperation(
  operation: Operation,
  operationId: string,
  args: Record<string, unknown>,
  repoRoot: string,
  requestId: string,
  dedupKey: string,
  abortSignal?: AbortSignal,
): Promise<ExecutionResult> {
  const startedAt = new Date().toISOString()
  const startTime = Date.now()
  
  // Build argv
  const argv: string[] = [operation.script]
  
  for (const [key, value] of Object.entries(args)) {
    if (value !== undefined && value !== null) {
      // Convert to kebab-case argument
      const argName = "--" + key.replace(/_/g, "-")
      argv.push(argName, String(value))
    }
  }
  
  // Minimal environment
  const env: Record<string, string> = {
    PATH: process.env.PATH || "/usr/bin:/bin",
    HOME: process.env.HOME || "/tmp",
    PYTHONUNBUFFERED: "1",
    PYTHONIOENCODING: "utf-8",
  }
  
  // Add allowlisted environment variables
  for (const name of operation.environment_allowlist) {
    if (process.env[name]) {
      env[name] = process.env[name]
    }
  }
  
  // Working directory
  const cwd = operation.working_directory === "." 
    ? repoRoot 
    : resolve(repoRoot, operation.working_directory)
  
  return await new Promise((resolve) => {
    let stdout = ""
    let stderr = ""
    let stdoutBytes = 0
    let stderrBytes = 0
    let stdoutTruncated = false
    let stderrTruncated = false
    let killed = false
    let childPid: number | undefined
    
    const child = spawn(operation.executable, argv, {
      cwd,
      env,
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    })
    
    childPid = child.pid
    
    // Update in-flight state with PID
    const state = executionState.get(dedupKey)
    if (state) {
      state.pid = childPid
    }
    
    const timer = setTimeout(() => {
      killed = true
      child.kill("SIGKILL")
    }, operation.timeout_seconds * 1000)
    
    // Handle abort signal
    const abortHandler = () => {
      killed = true
      child.kill("SIGKILL")
    }
    abortSignal?.addEventListener("abort", abortHandler)
    
    const captureOutput = (
      stream: "stdout" | "stderr",
      chunk: Buffer,
      maxBytes: number,
    ): { text: string; bytes: number; truncated: boolean } => {
      const currentBytes = stream === "stdout" ? stdoutBytes : stderrBytes
      const currentText = stream === "stdout" ? stdout : stderr
      
      const newBytes = currentBytes + chunk.length
      
      if (newBytes > maxBytes) {
        // Truncate and kill
        const remaining = maxBytes - currentBytes
        const text = chunk.toString("utf8", 0, Math.max(0, remaining))
        child.kill("SIGKILL")
        return { text, bytes: maxBytes, truncated: true }
      }
      
      return { text: chunk.toString("utf8"), bytes: newBytes, truncated: false }
    }
    
    child.stdout?.on("data", (chunk: Buffer) => {
      const result = captureOutput("stdout", chunk, operation.max_stdout_bytes)
      stdout += result.text
      stdoutBytes = result.bytes
      if (result.truncated) stdoutTruncated = true
    })
    
    child.stderr?.on("data", (chunk: Buffer) => {
      const result = captureOutput("stderr", chunk, operation.max_stderr_bytes)
      stderr += result.text
      stderrBytes = result.bytes
      if (result.truncated) stderrTruncated = true
    })
    
    child.on("error", (err) => {
      clearTimeout(timer)
      abortSignal?.removeEventListener("abort", abortHandler)
      
      const durationMs = Date.now() - startTime
      
      resolve({
        schema_version: 1,
        status: "executor_error",
        request_id: requestId,
        operation: operationId,
        started_at: startedAt,
        duration_ms: durationMs,
        exit_code: null,
        timed_out: false,
        cancelled: false,
        subprocesses_started: 1,
        stdout: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
        stderr: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
        parsed_result: {},
        warnings: [],
        error: err.message,
      })
    })
    
    child.on("close", (code, signal) => {
      clearTimeout(timer)
      abortSignal?.removeEventListener("abort", abortHandler)
      
      const durationMs = Date.now() - startTime
      
      // Redact secrets
      const safeStdout = redactSecrets(stdout)
      const safeStderr = redactSecrets(stderr)
      
      // Determine status
      let status: ExecutionResult["status"]
      if (killed && signal === "SIGKILL") {
        status = abortSignal?.aborted ? "cancelled" : "timeout"
      } else if (stdoutTruncated || stderrTruncated) {
        status = "output_limit_exceeded"
      } else if (code !== 0) {
        status = "failed"
      } else {
        status = "success"
      }
      
      // Try to parse JSON from stdout
      let parsedResult: Record<string, unknown> = {}
      try {
        if (safeStdout.trim()) {
          parsedResult = JSON.parse(safeStdout.trim())
        }
      } catch {
        // Not valid JSON, leave empty
      }
      
      // Create summary (first 500 chars)
      const stdoutSummary = safeStdout.slice(0, 500)
      const stderrSummary = safeStderr.slice(0, 500)
      
      // Save artifacts if needed
      let stdoutArtifactPath: string | null = null
      let stderrArtifactPath: string | null = null
      
      if (stdoutBytes > 1024) {
        try {
          const artifactDir = join(repoRoot, ARTIFACT_PATH)
          if (!existsSync(artifactDir)) {
            mkdirSync(artifactDir, { recursive: true })
          }
          stdoutArtifactPath = join(artifactDir, `${requestId}-stdout.json`)
          writeFileSync(stdoutArtifactPath, safeStdout, "utf8")
        } catch {
          // Silently fail
        }
      }
      
      const result: ExecutionResult = {
        schema_version: 1,
        status,
        request_id: requestId,
        operation: operationId,
        started_at: startedAt,
        duration_ms: durationMs,
        exit_code: code,
        timed_out: status === "timeout",
        cancelled: status === "cancelled",
        subprocesses_started: 1,
        stdout: {
          summary: stdoutSummary,
          bytes_captured: stdoutBytes,
          truncated: stdoutTruncated,
          artifact_path: stdoutArtifactPath,
        },
        stderr: {
          summary: stderrSummary,
          bytes_captured: stderrBytes,
          truncated: stderrTruncated,
          artifact_path: stderrArtifactPath,
        },
        parsed_result: parsedResult,
        warnings: stdoutTruncated || stderrTruncated 
          ? ["Output was truncated due to size limits"] 
          : [],
        error: status === "failed" 
          ? safeStderr.slice(0, 500) || `Exit code ${code}`
          : null,
      }
      
      // Mark as completed in dedup state
      markCompleted(dedupKey, result)
      
      // Log execution
      const logEntry: LogEntry = {
        timestamp: startedAt,
        request_id: requestId,
        session_id: process.env.KILO_SESSION_ID || null,
        message_id: process.env.KILO_MESSAGE_ID || null,
        dedup_key: dedupKey,
        operation: operationId,
        arguments_hash: createHash("sha256").update(JSON.stringify(args)).digest("hex").slice(0, 16),
        script_identity: operation.script,
        start_time: startedAt,
        duration_ms: durationMs,
        exit_code: code,
        status,
        subprocesses_started: 1,
        bytes_captured: stdoutBytes + stderrBytes,
        truncation: stdoutTruncated || stderrTruncated,
        timeout: status === "timeout",
        cancellation: status === "cancelled",
        artifact_paths: [stdoutArtifactPath, stderrArtifactPath].filter(Boolean) as string[],
        error_category: status !== "success" ? status : null,
      }
      appendLog(logEntry, repoRoot)
      
      resolve(result)
    })
  })
}

// =============================================================================
// TOOL EXPORT
// =============================================================================

export default tool({
  description: [
    "Execute an approved betting-pipeline script with validated arguments.",
    "Only operations defined in the manifest are allowed.",
    "Returns structured JSON with status, output, and metadata.",
  ].join(" "),
  args: {
    operation: tool.schema
      .string()
      .min(1)
      .max(64)
      .describe("Operation ID from the approved manifest"),
    arguments: tool.schema
      .record(tool.schema.string(), tool.schema.unknown())
      .optional()
      .describe("Validated arguments for the operation"),
    request_id: tool.schema
      .string()
      .min(1)
      .max(64)
      .optional()
      .describe("Optional request identifier for idempotency"),
  },
  async execute(args, context) {
    const requestId = args.request_id || `req-${randomUUID()}`
    const repoRoot = context.directory
    const sessionId = process.env.KILO_SESSION_ID || null
    const messageId = process.env.KILO_MESSAGE_ID || null
    
    // Load manifest
    const manifestPath = join(repoRoot, MANIFEST_PATH)
    let manifest: OperationManifest
    
    try {
      if (!existsSync(manifestPath)) {
        return JSON.stringify({
          schema_version: 1,
          status: "executor_error",
          request_id: requestId,
          operation: args.operation,
          started_at: new Date().toISOString(),
          duration_ms: 0,
          exit_code: null,
          timed_out: false,
          cancelled: false,
          subprocesses_started: 0,
          stdout: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
          stderr: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
          parsed_result: {},
          warnings: [],
          error: "Manifest not found",
        })
      }
      
      manifest = JSON.parse(readFileSync(manifestPath, "utf8"))
    } catch (err) {
      return JSON.stringify({
        schema_version: 1,
        status: "executor_error",
        request_id: requestId,
        operation: args.operation,
        started_at: new Date().toISOString(),
        duration_ms: 0,
        exit_code: null,
        timed_out: false,
        cancelled: false,
        subprocesses_started: 0,
        stdout: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
        stderr: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
        parsed_result: {},
        warnings: [],
        error: `Failed to load manifest: ${err}`,
      })
    }
    
    // Validate schema version
    if (manifest.schema_version !== 1) {
      return JSON.stringify({
        schema_version: 1,
        status: "executor_error",
        request_id: requestId,
        operation: args.operation,
        started_at: new Date().toISOString(),
        duration_ms: 0,
        exit_code: null,
        timed_out: false,
        cancelled: false,
        subprocesses_started: 0,
        stdout: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
        stderr: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
        parsed_result: {},
        warnings: [],
        error: `Unsupported manifest schema version: ${manifest.schema_version}`,
      })
    }
    
    // Validate operation exists
    const operation = manifest.operations[args.operation]
    if (!operation) {
      return JSON.stringify({
        schema_version: 1,
        status: "invalid_request",
        request_id: requestId,
        operation: args.operation,
        started_at: new Date().toISOString(),
        duration_ms: 0,
        exit_code: null,
        timed_out: false,
        cancelled: false,
        subprocesses_started: 0,
        stdout: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
        stderr: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
        parsed_result: {},
        warnings: [],
        error: `Unknown operation: ${args.operation}`,
      })
    }
    
    // Validate script path
    if (!validatePath(operation.script, repoRoot)) {
      return JSON.stringify({
        schema_version: 1,
        status: "invalid_request",
        request_id: requestId,
        operation: args.operation,
        started_at: new Date().toISOString(),
        duration_ms: 0,
        exit_code: null,
        timed_out: false,
        cancelled: false,
        subprocesses_started: 0,
        stdout: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
        stderr: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
        parsed_result: {},
        warnings: [],
        error: "Invalid script path",
      })
    }
    
    // Validate arguments
    const validatedArgs: Record<string, unknown> = {}
    const inputArgs = args.arguments || {}
    
    // Check for unknown arguments
    for (const key of Object.keys(inputArgs)) {
      if (!operation.allowed_arguments[key]) {
        return JSON.stringify({
          schema_version: 1,
          status: "invalid_request",
          request_id: requestId,
          operation: args.operation,
          started_at: new Date().toISOString(),
          duration_ms: 0,
          exit_code: null,
          timed_out: false,
          cancelled: false,
          subprocesses_started: 0,
          stdout: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
          stderr: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
          parsed_result: {},
          warnings: [],
          error: `Unknown argument: ${key}`,
        })
      }
    }
    
    // Validate each argument
    for (const [argName, argSpec] of Object.entries(operation.allowed_arguments)) {
      const value = inputArgs[argName]
      const validation = validateArgument(value, argSpec)
      
      if (!validation.valid) {
        return JSON.stringify({
          schema_version: 1,
          status: "invalid_request",
          request_id: requestId,
          operation: args.operation,
          started_at: new Date().toISOString(),
          duration_ms: 0,
          exit_code: null,
          timed_out: false,
          cancelled: false,
          subprocesses_started: 0,
          stdout: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
          stderr: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
          parsed_result: {},
          warnings: [],
          error: `Invalid argument '${argName}': ${validation.error}`,
        })
      }
      
      if (validation.coerced !== undefined) {
        validatedArgs[argName] = validation.coerced
      }
    }
    
    // Build deduplication key
    const dedupKey = buildDedupKey(sessionId, messageId, args.operation, validatedArgs)
    
    // Check for duplicate execution
    const dupCheck = checkDuplicate(dedupKey)
    if (dupCheck.isDuplicate) {
      if (dupCheck.cachedResult) {
        // Return cached result
        return JSON.stringify({
          ...dupCheck.cachedResult,
          status: "duplicate_completed",
          subprocesses_started: 0,
        })
      } else if (dupCheck.state) {
        // In-flight execution
        return JSON.stringify({
          schema_version: 1,
          status: "duplicate_in_flight",
          request_id: requestId,
          operation: args.operation,
          started_at: new Date().toISOString(),
          duration_ms: 0,
          exit_code: null,
          timed_out: false,
          cancelled: false,
          subprocesses_started: 0,
          stdout: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
          stderr: { summary: "", bytes_captured: 0, truncated: false, artifact_path: null },
          parsed_result: {},
          warnings: ["Duplicate request - execution already in progress"],
          error: null,
        })
      }
    }
    
    // Mark as in-flight
    markInFlight(dedupKey, requestId)
    
    // Execute
    const result = await executeOperation(
      operation,
      args.operation,
      validatedArgs,
      repoRoot,
      requestId,
      dedupKey,
      context.abort,
    )
    
    return JSON.stringify(result, null, 2)
  },
})
