import { mkdirSync, readFileSync, rmSync, symlinkSync, existsSync, writeFileSync } from "node:fs"
import { createHash } from "node:crypto"
import { join, dirname } from "node:path"
import os from "node:os"
import { pathToFileURL } from "node:url"
import { spawnSync } from "node:child_process"

const [, , projectRoot, reportPath] = process.argv
if (!projectRoot || !reportPath) {
  console.error("usage: node test-bet-artifact-write-runner.mjs <projectRoot> <reportPath>")
  process.exit(2)
}

async function ensureTsx() {
  const result = spawnSync("npx", ["-y", "tsx", "--version"], { encoding: "utf8" })
  if (result.status !== 0) {
    throw new Error(result.stderr || result.stdout || "tsx unavailable")
  }
}

function sha256(content) {
  return createHash("sha256").update(content, "utf8").digest("hex")
}

function makeContext(directory, signal) {
  return {
    sessionID: "phase4a-test-session",
    messageID: `msg-${Math.random().toString(16).slice(2)}`,
    agent: "code-gpt54",
    directory,
    worktree: directory,
    abort: signal,
    metadata() {},
    ask() {
      throw new Error("ask must not be called")
    },
  }
}

function parseResult(raw) {
  return typeof raw === "string" ? JSON.parse(raw) : JSON.parse(raw.output)
}

function makeContent(bytes) {
  return "A".repeat(bytes)
}

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

async function invoke(toolDef, directory, args, opts = {}) {
  const controller = opts.controller ?? new AbortController()
  const result = await toolDef.execute(args, makeContext(directory, controller.signal))
  return parseResult(result)
}

async function main() {
  await ensureTsx()
  const tempRoot = join(os.tmpdir(), `bet-artifact-write-${Date.now()}`)
  mkdirSync(tempRoot, { recursive: true })
  mkdirSync(join(tempRoot, ".kilo", "state"), { recursive: true })
  mkdirSync(join(tempRoot, "reports", "betting-demo"), { recursive: true })
  mkdirSync(join(tempRoot, "reports", "betting"), { recursive: true })
  mkdirSync(join(tempRoot, "outside"), { recursive: true })

  const outsideTarget = join(tempRoot, "outside", "escape.md")
  const symlinkPath = join(tempRoot, "reports", "betting-demo", "symlink.md")
  symlinkSync(outsideTarget, symlinkPath)

  const sourcePath = join(projectRoot, ".kilo", "tool", "bet_artifact_write.ts")
  const pluginToolUrl = pathToFileURL(join(projectRoot, ".kilo", "node_modules", "@kilocode", "plugin", "dist", "tool.js")).href
  const harnessToolPath = join(tempRoot, "bet_artifact_write.harness.ts")
  const source = readFileSync(sourcePath, "utf8").replace(
    'from "@kilocode/plugin/tool"',
    `from ${JSON.stringify(pluginToolUrl)}`,
  )
  writeFileSync(harnessToolPath, source, "utf8")

  const toolModule = await import(pathToFileURL(harnessToolPath).href)
  const toolDef = toolModule.default

  const auditFile = () => join(tempRoot, "reports", "agent-config", "artifact-writer-audit", `audit-${new Date().toISOString().slice(0, 10)}.jsonl`)
  const results = []

  const run = async (name, fn) => {
    try {
      const detail = await fn()
      results.push({ name, status: "PASS", detail })
    } catch (error) {
      results.push({ name, status: "FAIL", detail: String(error?.message ?? error) })
    }
  }

  await run("schema_stable", async () => {
    assert(toolDef?.args?.content_type, "content_type schema missing")
    const parsed = toolDef.args.content_type.safeParse("markdown")
    assert(parsed.success, "content_type schema parse failed")
    return "content_type enum parsed"
  })

  await run("valid_phase_a_markdown_handoff", async () => {
    const res = await invoke(toolDef, tempRoot, {
      path: ".kilo/state/phase-A-handoff.md",
      content: "# Phase A\n\nSTATUS: PASS\n",
      content_type: "markdown",
      create_only: true,
    })
    assert(res.status === "success" && res.path === ".kilo/state/phase-A-handoff.md", JSON.stringify(res))
    return res
  })

  await run("valid_phase_e_markdown_handoff", async () => {
    const res = await invoke(toolDef, tempRoot, {
      path: ".kilo/state/phase-E-handoff.md",
      content: "# Phase E\n\nSTATUS: PASS\n",
      content_type: "markdown",
      create_only: true,
    })
    assert(res.status === "success", JSON.stringify(res))
    return res
  })

  await run("valid_markdown_report", async () => {
    const res = await invoke(toolDef, tempRoot, {
      path: "reports/betting-demo/report.md",
      content: "# Synthetic Report\n",
      content_type: "markdown",
      create_only: true,
    })
    assert(res.status === "success" && res.sha256, JSON.stringify(res))
    return res
  })

  await run("valid_json_report", async () => {
    const body = JSON.stringify({ status: "ok", synthetic: true }, null, 2)
    const res = await invoke(toolDef, tempRoot, {
      path: "reports/betting-demo/report.json",
      content: body,
      content_type: "json",
      create_only: true,
    })
    assert(res.status === "success" && res.bytes_written === Buffer.byteLength(body, "utf8"), JSON.stringify(res))
    return res
  })

  await run("invalid_phase", async () => {
    const res = await invoke(toolDef, tempRoot, {
      path: ".kilo/state/phase-Z-handoff.md",
      content: "# bad\n",
      content_type: "markdown",
      create_only: true,
    })
    assert(res.error_code === "PATH_NOT_ALLOWED", JSON.stringify(res))
    return res
  })

  await run("absolute_path", async () => {
    const res = await invoke(toolDef, tempRoot, {
      path: "/tmp/escape.md",
      content: "x",
      content_type: "markdown",
      create_only: true,
    })
    assert(res.error_code === "PATH_ABSOLUTE", JSON.stringify(res))
    return res
  })

  await run("traversal", async () => {
    const res = await invoke(toolDef, tempRoot, {
      path: "reports/betting-demo/../escape.md",
      content: "x",
      content_type: "markdown",
      create_only: true,
    })
    assert(res.error_code === "PATH_TRAVERSAL", JSON.stringify(res))
    return res
  })

  await run("normalized_or_encoded_traversal", async () => {
    const res = await invoke(toolDef, tempRoot, {
      path: "reports/betting-demo/%2e%2e/escape.md",
      content: "x",
      content_type: "markdown",
      create_only: true,
    })
    assert(res.error_code === "PATH_ENCODED_TRAVERSAL", JSON.stringify(res))
    return res
  })

  await run("symlink_escape", async () => {
    const res = await invoke(toolDef, tempRoot, {
      path: "reports/betting-demo/symlink.md",
      content: "x",
      content_type: "markdown",
      create_only: false,
      expected_sha256: sha256("")
    })
    assert(res.error_code === "PATH_SYMLINK_ESCAPE", JSON.stringify(res))
    return res
  })

  await run("unsupported_extension", async () => {
    const res = await invoke(toolDef, tempRoot, {
      path: "reports/betting-demo/report.txt",
      content: "x",
      content_type: "markdown",
      create_only: true,
    })
    assert(res.error_code === "EXTENSION_MISMATCH", JSON.stringify(res))
    return res
  })

  await run("invalid_or_binary_content", async () => {
    const res = await invoke(toolDef, tempRoot, {
      path: "reports/betting-demo/binary.md",
      content: "bad\u0000data",
      content_type: "markdown",
      create_only: true,
    })
    assert(res.error_code === "CONTENT_BINARY", JSON.stringify(res))
    return res
  })

  await run("oversized_content", async () => {
    const res = await invoke(toolDef, tempRoot, {
      path: "reports/betting-demo/large.md",
      content: makeContent(256 * 1024 + 1),
      content_type: "markdown",
      create_only: true,
    })
    assert(res.error_code === "CONTENT_TOO_LARGE", JSON.stringify(res))
    return res
  })

  await run("synthetic_secret_content", async () => {
    const res = await invoke(toolDef, tempRoot, {
      path: "reports/betting-demo/secret.md",
      content: "api_key=super-secret-token",
      content_type: "markdown",
      create_only: true,
    })
    assert(res.error_code === "CONTENT_SECRET_DETECTED" && !String(res.error).includes("super-secret-token"), JSON.stringify(res))
    return res
  })

  await run("create_over_existing_without_expected_hash", async () => {
    const res = await invoke(toolDef, tempRoot, {
      path: "reports/betting-demo/report.md",
      content: "# overwrite\n",
      content_type: "markdown",
      create_only: true,
    })
    assert(res.error_code === "EXISTS_CREATE_ONLY", JSON.stringify(res))
    return res
  })

  await run("overwrite_missing_hash", async () => {
    const res = await invoke(toolDef, tempRoot, {
      path: "reports/betting-demo/report.md",
      content: "# overwrite\n",
      content_type: "markdown",
      create_only: false,
    })
    assert(res.error_code === "EXPECTED_HASH_REQUIRED", JSON.stringify(res))
    return res
  })

  await run("overwrite_wrong_hash", async () => {
    const res = await invoke(toolDef, tempRoot, {
      path: "reports/betting-demo/report.md",
      content: "# overwrite\n",
      content_type: "markdown",
      create_only: false,
      expected_sha256: "0".repeat(64),
    })
    assert(res.error_code === "EXPECTED_HASH_MISMATCH", JSON.stringify(res))
    return res
  })

  await run("overwrite_correct_hash", async () => {
    const prior = readFileSync(join(tempRoot, "reports", "betting-demo", "report.md"), "utf8")
    const next = "# overwrite\n"
    const res = await invoke(toolDef, tempRoot, {
      path: "reports/betting-demo/report.md",
      content: next,
      content_type: "markdown",
      create_only: false,
      expected_sha256: sha256(prior),
    })
    assert(res.status === "success" && res.overwritten === true && res.sha256 === sha256(next), JSON.stringify(res))
    return res
  })

  await run("cancellation", async () => {
    const controller = new AbortController()
    controller.abort()
    const res = await invoke(toolDef, tempRoot, {
      path: "reports/betting-demo/cancelled.md",
      content: "cancel me",
      content_type: "markdown",
      create_only: true,
    }, { controller })
    assert(res.status === "cancelled" && res.error_code === "CAPABILITY_CANCELLED", JSON.stringify(res))
    assert(!existsSync(join(tempRoot, "reports", "betting-demo", "cancelled.md")), "cancelled file should not exist")
    return res
  })

  await run("concurrent_creation_same_path", async () => {
    const target = "reports/betting-demo/concurrent.md"
    const [a, b] = await Promise.all([
      invoke(toolDef, tempRoot, { path: target, content: "one", content_type: "markdown", create_only: true }),
      invoke(toolDef, tempRoot, { path: target, content: "two", content_type: "markdown", create_only: true }),
    ])
    const successes = [a, b].filter((r) => r.status === "success")
    const failures = [a, b].filter((r) => r.status !== "success")
    assert(successes.length === 1, JSON.stringify([a, b]))
    assert(failures.length === 1, JSON.stringify([a, b]))
    assert(["LOCK_CONFLICT", "EXISTS_CREATE_ONLY"].includes(failures[0].error_code), JSON.stringify([a, b]))
    return { a, b }
  })

  await run("audit_log_completeness", async () => {
    const file = auditFile()
    const lines = readFileSync(file, "utf8").trim().split("\n").filter(Boolean)
    assert(lines.length >= 20, `expected >=20 audit lines, got ${lines.length}`)
    const parsed = lines.map((line) => JSON.parse(line))
    assert(parsed.every((entry) => entry.request_id && entry.error_code), "missing audit fields")
    return { lines: lines.length, file }
  })

  const failed = results.filter((r) => r.status === "FAIL")
  const report = {
    timestamp: new Date().toISOString(),
    status: failed.length === 0 ? "PASS" : "FAIL",
    total: results.length,
    passed: results.length - failed.length,
    failed: failed.length,
    results,
    synthetic_repo: tempRoot,
    audit_file: auditFile(),
  }

  mkdirSync(dirname(reportPath), { recursive: true })
  writeFileSync(reportPath, JSON.stringify(report, null, 2), "utf8")
  console.log(JSON.stringify({ status: report.status, reportPath, passed: report.passed, failed: report.failed }))

  if (failed.length) process.exit(1)
}

main().catch(async (error) => {
  mkdirSync(dirname(reportPath), { recursive: true })
  writeFileSync(reportPath, JSON.stringify({ status: "FAIL", error: String(error?.stack ?? error) }, null, 2), "utf8")
  console.error(String(error?.stack ?? error))
  process.exit(1)
})
