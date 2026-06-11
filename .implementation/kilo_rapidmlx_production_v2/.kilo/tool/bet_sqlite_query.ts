import { tool } from "@kilocode/plugin/tool"
import { spawn } from "node:child_process"
import { join } from "node:path"

const MAX_CAPTURE_BYTES = 64 * 1024
const TIMEOUT_MS = 20_000

async function runReadOnlyQuery(
  script: string,
  cwd: string,
  payload: Record<string, unknown>,
): Promise<string> {
  return await new Promise((resolve, reject) => {
    const child = spawn("python3", [script], {
      cwd,
      env: process.env,
      stdio: ["pipe", "pipe", "pipe"],
    })
    let stdout = ""
    let stderr = ""
    let overflow = false

    const append = (current: string, chunk: Buffer): string => {
      const merged = current + chunk.toString("utf8")
      if (Buffer.byteLength(merged, "utf8") > MAX_CAPTURE_BYTES) {
        overflow = true
        child.kill("SIGKILL")
        return merged.slice(0, MAX_CAPTURE_BYTES)
      }
      return merged
    }

    child.stdout.on("data", (chunk: Buffer) => { stdout = append(stdout, chunk) })
    child.stderr.on("data", (chunk: Buffer) => { stderr = append(stderr, chunk) })
    child.on("error", reject)

    const timer = setTimeout(() => child.kill("SIGKILL"), TIMEOUT_MS)
    child.on("close", (code, signal) => {
      clearTimeout(timer)
      if (overflow) return reject(new Error("SQLite helper exceeded its capture limit"))
      if (signal === "SIGKILL") return reject(new Error(`SQLite helper exceeded ${TIMEOUT_MS} ms`))
      const output = stdout.trim()
      if (code !== 0) {
        const detail = output || stderr.trim() || `exit ${code}`
        return reject(new Error(detail))
      }
      resolve(output)
    })

    child.stdin.end(JSON.stringify(payload))
  })
}

export default tool({
  description: [
    "Run one bounded read-only SELECT/WITH query against betting/data/betting.db.",
    "The database is opened in SQLite mode=ro, write opcodes and PRAGMA are denied,",
    "the VM work budget is bounded, and at most 200 rows / ~10 KiB are returned.",
    "Inspect schema by querying sqlite_master. Always select only required columns.",
  ].join(" "),
  args: {
    sql: tool.schema.string().min(1).max(12000).describe("One SELECT or WITH query; no PRAGMA or mutations"),
    limit: tool.schema.number().int().min(1).max(200).optional().describe("Maximum rows, default 100"),
  },
  async execute(args, context) {
    const script = join(context.directory, "scripts", "sqlite_readonly.py")
    return await runReadOnlyQuery(script, context.directory, {
      sql: args.sql,
      limit: args.limit ?? 100,
      project_root: context.directory,
      db_path: process.env.KILO_SQLITE_DB ?? "betting/data/betting.db",
    })
  },
})
