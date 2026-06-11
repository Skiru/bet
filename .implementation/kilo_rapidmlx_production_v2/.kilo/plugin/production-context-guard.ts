import type { Plugin } from "@kilocode/plugin"
import { appendFile, mkdir, writeFile } from "node:fs/promises"
import { basename, join } from "node:path"

const DEFAULT_MAX_BYTES = 12 * 1024
const DEFAULT_HEAD_BYTES = 7 * 1024
const DEFAULT_TAIL_BYTES = 3 * 1024

function positiveInt(value: string | undefined, fallback: number): number {
  const parsed = Number.parseInt(value ?? "", 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

function safeName(value: unknown): string {
  return String(value ?? "tool")
    .replace(/[^a-zA-Z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80) || "tool"
}

function utf8Preview(buffer: Buffer, headBytes: number, tailBytes: number): { head: string; tail: string } {
  return {
    head: buffer.subarray(0, Math.min(headBytes, buffer.length)).toString("utf8"),
    tail: buffer.subarray(Math.max(0, buffer.length - tailBytes)).toString("utf8"),
  }
}

const server: Plugin = async ({ directory }) => {
  const maxBytes = positiveInt(process.env.KILO_TOOL_OUTPUT_MAX_BYTES, DEFAULT_MAX_BYTES)
  const headBytes = Math.min(positiveInt(process.env.KILO_TOOL_OUTPUT_HEAD_BYTES, DEFAULT_HEAD_BYTES), maxBytes)
  const tailBytes = Math.min(positiveInt(process.env.KILO_TOOL_OUTPUT_TAIL_BYTES, DEFAULT_TAIL_BYTES), maxBytes)
  const artifactDir = join(directory, ".kilo", "artifacts", "tool-output")
  const runtimeDir = join(directory, ".kilo", "runtime")
  const auditLog = join(runtimeDir, "context-guard.jsonl")

  async function audit(entry: Record<string, unknown>): Promise<void> {
    try {
      await mkdir(runtimeDir, { recursive: true })
      await appendFile(auditLog, JSON.stringify({ at: new Date().toISOString(), ...entry }) + "\n", "utf8")
    } catch {
      // Observability is fail-open; never break a tool result because logging failed.
    }
  }

  return {
    "chat.params": async (_input, output) => {
      const requested = Number(output.maxOutputTokens ?? 4096)
      output.maxOutputTokens = Math.min(Number.isFinite(requested) ? requested : 4096, 4096)
    },

    "tool.execute.after": async (input, output) => {
      if (typeof output.output !== "string") return
      const body = Buffer.from(output.output, "utf8")
      if (body.byteLength <= maxBytes) return

      const tool = safeName(input.tool)
      const stamp = new Date().toISOString().replace(/[:.]/g, "-")
      const filename = `${stamp}-${tool}.txt`
      const artifactPath = join(artifactDir, filename)
      const relativePath = join(".kilo", "artifacts", "tool-output", filename)
      const preview = utf8Preview(body, headBytes, tailBytes)

      try {
        await mkdir(artifactDir, { recursive: true })
        await writeFile(artifactPath, body)
        output.output = [
          `[CONTEXT-GUARD] Tool output truncated from ${body.byteLength} bytes.`,
          `Full result: ${relativePath}`,
          `Read only a bounded range if more detail is required.`,
          "",
          "--- HEAD ---",
          preview.head,
          "",
          "--- OMITTED ---",
          "",
          "--- TAIL ---",
          preview.tail,
        ].join("\n")
        output.title = `${output.title ?? tool} [truncated → ${basename(relativePath)}]`
        output.metadata = {
          ...(output.metadata ?? {}),
          contextGuard: {
            truncated: true,
            originalBytes: body.byteLength,
            artifact: relativePath,
          },
        }
        await audit({ event: "tool-output-truncated", tool, originalBytes: body.byteLength, artifact: relativePath })
      } catch (error) {
        // Fail safely: preserve a bounded preview even when artifact persistence fails.
        output.output = [
          `[CONTEXT-GUARD] Output exceeded ${maxBytes} bytes and artifact persistence failed.`,
          `Error: ${String(error)}`,
          "",
          "--- BOUNDED HEAD ---",
          preview.head,
          "",
          "--- BOUNDED TAIL ---",
          preview.tail,
        ].join("\n")
        await audit({ event: "tool-output-truncate-write-failed", tool, originalBytes: body.byteLength, error: String(error) })
      }
    },

    "experimental.session.compacting": async (_input, output) => {
      output.context.push(
        [
          "## Production handoff requirements",
          "Preserve the current phase, exit criteria, completed work, exact artifact paths, decisions, unresolved risks, and next action.",
          "Prefer .kilo/state/CURRENT_HANDOFF.md and the current phase handoff over reconstructing state from old tool output.",
          "Do not preserve private chain-of-thought or verbose tool transcripts.",
        ].join("\n"),
      )
    },

    "experimental.compaction.autocontinue": async (input, output) => {
      if (input.overflow) {
        output.enabled = false
        await audit({ event: "overflow-autocontinue-disabled" })
      }
    },

    event: async ({ event }) => {
      if (event.type === "session.error") {
        await audit({ event: "session-error", payload: event })
      }
    },
  }
}

export default { id: "production-context-guard", server }
