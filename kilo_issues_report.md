# Kilo Code Issues Report
Generated: 2026-05-31T15:34 (live check)

---

## Summary of Active Issues

| # | Issue | Severity | Affected Tasks | Root Cause |
|---|-------|----------|----------------|------------|
| 1 | "Only 'text' content type is supported" (404) | **CRITICAL** | 2/5 recent tasks | Kilo sends image_url content to Rapid-MLX which runs `--no-mllm` |
| 2 | "You did not use a tool in your previous response" | MEDIUM | 2/5 recent tasks | Model sometimes outputs text-only when Kilo expects tool_call format |
| 3 | Python import error `bet.discovery` | RESOLVED | 1 task (May 27) | Import works now — was likely a venv/path issue at that time |
| 4 | Gemini 503/429 errors | OBSOLETE | 3 tasks (May 12) | Old Gemini provider, no longer used since switch to local Rapid-MLX |
| 5 | Connection error to Rapid-MLX | LOW | 1 task (May 27) | Transient — server was likely restarting |

---

## Issue #1: Image Content Rejected (CRITICAL — blocks screenshot workflows)

**Error:** `OpenAI completion error: 404 "Only 'text' content type is supported."`

**Root Cause:** 
- Rapid-MLX is started with `--no-mllm` (disables vision/multimodal encoder)
- Kilo Code sends user screenshots as `{"type": "image_url", ...}` in the messages array
- Server rejects non-text content blocks with a 404/400

**Reproduction:**
```bash
curl http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"qwen3.6-35b","messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}]}]}'
# Returns: {"detail":"Model does not support image, video, or audio inputs."}
```

**Fix options:**
1. **In kilo.jsonc** — Add `"supportsImages": false` to the model config (if Kilo respects it) to prevent Kilo from sending images to this model
2. **In Kilo UI** — Don't paste screenshots into chat when using the local model; use OCR/text extraction first
3. **Server-side** — Remove `--no-mllm` flag from Rapid-MLX start command (costs ~2GB extra VRAM, may not work with Qwen3.6-35B-A3B which has no vision encoder)
4. **Kilo config** — Check if there's a model capability flag like `"vision": false` in newer Kilo schema to suppress image sends

**Recommended fix:** Option 1 or check Kilo docs for model capability flags. The model (Qwen3.6-35B-A3B) genuinely has no vision — it's text-only MoE.

---

## Issue #2: Tool Use Format Mismatch (MEDIUM)

**Error:** `[ERROR] You did not use a tool in your previous response! Please retry with a tool use.`

**Root Cause:**
- Kilo expects the model to emit a tool_call in certain situations
- Qwen3.6-35B sometimes outputs plain text (especially after long `<think>` blocks that consume the output budget)
- The model may also produce malformed tool call XML that the `qwen3_coder_xml` parser can't parse

**Contributing factors from AGENTS.md:**
- `<think>` blocks limited to 200 tokens per AGENTS.md rule
- If model exceeds think budget → less room for structured tool output → truncation → no tool call parsed

**Fix options:**
1. Increase `--max-tokens` beyond 32768 (if memory allows)
2. Add system prompt reinforcement: "Always use a tool. Never respond with plain text."
3. Check if Rapid-MLX `--tool-call-parser qwen3_coder_xml` is dropping valid tool calls (log the raw stream)
4. Verify the 200-token thinking limit in AGENTS.md isn't causing issues — model may need more reasoning space before tool selection

---

## Issue #3: Import Error (RESOLVED)

**Error:** `from bet.discovery import discover_events` — ImportError

**Status:** Works now. Was likely caused by running `python3` instead of `.venv/bin/python3` or a missing module at that time.

---

## Issue #4: Gemini Errors (OBSOLETE)

**Errors:** 503 "high demand" / 429 "exceeded quota"

**Status:** These are from May 12 when the project used Gemini as the provider. Since switching to local Rapid-MLX (~May 24+), these are irrelevant.

---

## Current Server Status (live check 2026-05-31 15:34)

- **Rapid-MLX process:** RUNNING (PID 23567, 40.8% memory = ~20GB, uptime since 1:05PM today)
- **HTTP endpoint:** http://localhost:8000/v1 — responds HTTP 200
- **Model loaded:** `mlx-community/Qwen3.6-35B-A3B-4bit` (alias: `qwen3.6-35b`)
- **MCP servers configured:** 3 (sequentialthinking, sqlite, brave-search) — all enabled
- **Text completions:** Working (verified via curl)
- **Image/vision:** Not supported (expected — `--no-mllm` flag)
- **Monitor process:** Running (PID 42998, fish script at `/tmp/rapid-mlx-monitor.fish`)

---

## Recommended Actions (priority order)

1. **[HIGH]** Fix image content handling — either add `"supportsImages": false` to kilo.jsonc model config, or find Kilo's model capability flag to disable vision sends
2. **[MEDIUM]** Investigate tool-call parsing failures — check Rapid-MLX logs for raw model output when "did not use a tool" error fires
3. **[LOW]** Clean up old task history (May 12 Gemini tasks are obsolete noise)

---

## Fixes Applied (2026-05-31)

**Protocol v12 rewrite** to prevent "dumb script runner" behavior:
- `agent-execution-protocol.instructions.md` — Full rewrite. Added: SELF-CHECK 3-question gate, mandatory `/tmp/` redirect, BAD vs GOOD examples table, anti-drift detection, forbidden actions list. Cut from scattered bullet lists to structured tables.
- `AGENTS.md` — Trimmed from 100 to 63 lines. Removed duplication with protocol. Added OUTPUT RULE. Tightened delegation protocol to table format.
- `anti-drift-protocol.md` — Rewrote from 60 to 32 lines. Rules as table, drift as checklist, recovery as 3-step.
- `bet-orchestrator.md` — All commands now redirect to `/tmp/sN.txt 2>&1`. AFTER EACH SCRIPT section adds exit code check. S2 circuit breaker is now HARD STOP. Removed duplicated TOOL BUDGET (already in protocol).

**Total system prompt payload: 2,852 words (~3,700 tokens) — lean enough for 3B active params to retain.**