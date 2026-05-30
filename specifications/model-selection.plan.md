# Implementation Plan: Switch to Qwen3.5-35B-A3B-4bit (MoE)

**Date:** 2026-05-29  
**Research:** [model-selection.research.md](model-selection.research.md)  
**Status:** Ready for execution

---

## Summary

Switch local inference from Qwen3.6-27B Dense 8-bit (30GB, 1 tok/s) to Qwen3.5-35B-A3B 4-bit MoE (18GB, 45-70 tok/s). Key format change: tool parser `qwen3_coder_xml` → `hermes`. Reasoning parser unchanged (`qwen3`).

---

## Phase 1: Validate New Model (test port, zero risk)

> Goal: Confirm the model works before touching production config.

### Task 1.1 — [REUSE] Verify model is downloaded

```fish
~/.local/bin/rapid-mlx info qwen3.5-35b-4bit
```

- **Definition of done:** Command shows model path, size ~18GB, no download needed. If not present, run `rapid-mlx pull qwen3.5-35b-4bit`.

### Task 1.2 — [CREATE] Start test server on port 8001

```fish
~/.local/bin/rapid-mlx serve qwen3.5-35b-4bit --port 8001 \
  --no-mllm --max-num-seqs 1 \
  --reasoning-parser qwen3 \
  --default-temperature 0.6 --default-top-p 0.95 --default-top-k 20 \
  --max-tokens 32768 \
  --pin-system-prompt --enable-prefix-cache \
  --kv-cache-quantization --kv-cache-quantization-bits 4 \
  --cache-memory-mb 10000 \
  --gpu-memory-utilization 0.85 \
  --prefill-step-size 8192 \
  --gc-control \
  --enable-auto-tool-choice --tool-call-parser hermes
```

- **Dependency:** Task 1.1
- **Definition of done:** Server responds to `curl http://localhost:8001/v1/models` with model ID `qwen3.5-35b-4bit`.

### Task 1.3 — [REUSE] Validate tool calling (hermes format)

Send a representative tool-call prompt via curl:

```fish
curl -s http://localhost:8001/v1/chat/completions -H "Content-Type: application/json" -d '{
  "model": "qwen3.5-35b-4bit",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant with access to tools."},
    {"role": "user", "content": "What is the current time in Warsaw?"}
  ],
  "tools": [
    {"type": "function", "function": {"name": "get_current_time", "description": "Get current time in a timezone", "parameters": {"type": "object", "properties": {"timezone": {"type": "string"}}, "required": ["timezone"]}}}
  ]
}' | python3 -m json.tool
```

- **Dependency:** Task 1.2
- **Definition of done:** Response contains `tool_calls` array with `function.name = "get_current_time"` and `function.arguments` containing `"timezone": "Europe/Warsaw"` (or similar). Hermes format parses correctly.

### Task 1.4 — [REUSE] Validate reasoning (`<think>` blocks)

```fish
curl -s http://localhost:8001/v1/chat/completions -H "Content-Type: application/json" -d '{
  "model": "qwen3.5-35b-4bit",
  "messages": [
    {"role": "user", "content": "Analyze whether a team with L10 goals scored average of 2.1 is likely to hit Over 1.5 goals. Think step by step."}
  ]
}' | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['choices'][0]['message'].get('reasoning_content','NO REASONING')[:500])"
```

- **Dependency:** Task 1.2
- **Definition of done:** `reasoning_content` field is populated with multi-line thinking. NOT empty, NOT "NO REASONING".

### Task 1.5 — [REUSE] Measure generation speed

```fish
curl -s -w "\n---\nTotal time: %{time_total}s\n" http://localhost:8001/v1/chat/completions -H "Content-Type: application/json" -d '{
  "model": "qwen3.5-35b-4bit",
  "messages": [
    {"role": "user", "content": "Write a detailed 500-word analysis of why Mixture of Experts models are efficient on Apple Silicon."}
  ],
  "max_tokens": 1024
}' | tail -5
```

- **Dependency:** Task 1.2
- **Definition of done:** Total time < 30s for ~500 tokens output (implies >15 tok/s). Target: <15s (>35 tok/s).

### Task 1.6 — [REUSE] Stop test server

```fish
lsof -ti :8001 | xargs kill
```

- **Dependency:** Tasks 1.3–1.5 all pass
- **Definition of done:** Port 8001 is free.

---

## Phase 2: Backup Current Configuration

> Goal: Preserve ability to roll back in one command.

### Task 2.1 — [CREATE] Backup kilo.jsonc

```fish
cp kilo.jsonc kilo.jsonc.bak-qwen36-27b
```

- **Definition of done:** File `kilo.jsonc.bak-qwen36-27b` exists with current content.

### Task 2.2 — [CREATE] Backup plist

```fish
cp config/com.rapid-mlx.server.plist config/com.rapid-mlx.server.plist.bak-qwen36-27b
```

- **Definition of done:** Backup file exists.

### Task 2.3 — [CREATE] Backup start script

```fish
cp scripts/start_local_model.sh scripts/start_local_model.sh.bak-qwen36-27b
```

- **Definition of done:** Backup file exists.

---

## Phase 3: Stop Current Server

> Goal: Free port 8000 and GPU memory for new model.

### Task 3.1 — [REUSE] Stop LaunchDaemon (if running)

```fish
launchctl bootout gui/(id -u) ~/Library/LaunchAgents/com.rapid-mlx.server.plist 2>/dev/null; or true
```

- **Definition of done:** `lsof -i :8000 -sTCP:LISTEN` returns nothing.

### Task 3.2 — [REUSE] Kill any remaining process on port 8000

```fish
lsof -ti :8000 | xargs kill 2>/dev/null; or true
```

- **Dependency:** Task 3.1
- **Definition of done:** Port 8000 is free.

---

## Phase 4: Apply Configuration Changes

> Goal: Update all config files to reference new model.

### Task 4.1 — [MODIFY] `scripts/start_local_model.sh`

Changes:
1. Header comment: update model description to Qwen3.5-35B-A3B MoE 4-bit
2. `set -l MODEL` → `"qwen3.5-35b-4bit"`
3. Default FLAGS:
   - `--cache-memory-mb 500` → `--cache-memory-mb 10000`
   - `--gpu-memory-utilization 0.88` → `--gpu-memory-utilization 0.85`
   - `--prefill-step-size 2048` → `--prefill-step-size 8192`
   - `--tool-call-parser qwen3_coder_xml` → `--tool-call-parser hermes`
4. Safe mode FLAGS: same parser changes + `--cache-memory-mb 3000` → `8000`, `--gpu-memory-utilization 0.80` stays
5. Minimal mode FLAGS: `--tool-call-parser qwen3_coder_xml` → `--tool-call-parser hermes`
6. Echo block: Context `262K` → `131K`, VRAM `~30GB (8-bit)` → `~18GB (4-bit MoE)`

- **Dependency:** Phase 2 complete
- **Definition of done:** Script references `qwen3.5-35b-4bit`, hermes parser, updated memory/prefill values. Runs without syntax errors (`fish -n scripts/start_local_model.sh`).

### Task 4.2 — [MODIFY] `kilo.jsonc`

Changes:
1. Header comments: update model description
2. Model definition: rename key to `qwen3.5-35b-a3b`, set `"id": "qwen3.5-35b-4bit"`, context limit `131072`
3. All 11 agent `"model"` references: `"openai-compatible/qwen3.6-27b"` → `"openai-compatible/qwen3.5-35b-a3b"`
4. Global default model (line 360): same change

- **Dependency:** Phase 2 complete
- **Definition of done:** `grep -c "qwen3.6" kilo.jsonc` returns 0. `grep -c "qwen3.5-35b-a3b" kilo.jsonc` returns ≥12. JSON parses cleanly (`python3 -c "import json; json.loads(open('kilo.jsonc').read().split('*/')[0] if '/*' in open('kilo.jsonc').read() else '')"` — or use jsonc parser).

### Task 4.3 — [MODIFY] `config/com.rapid-mlx.server.plist`

Changes:
1. `qwen3.6-27b-8bit` → `qwen3.5-35b-4bit`
2. `4000` (cache-memory-mb) → `10000`
3. `0.92` (gpu-memory-utilization) → `0.85`
4. `4096` (prefill-step-size) → `8192`
5. `qwen3_coder_xml` (tool-call-parser) → `hermes`

- **Dependency:** Phase 2 complete
- **Definition of done:** `plutil -lint config/com.rapid-mlx.server.plist` passes. `grep qwen3.6 config/com.rapid-mlx.server.plist` returns nothing.

### Task 4.4 — [MODIFY] `.github/copilot-instructions.md`

Update the "Active Model Standard" section:
1. Model name: `Qwen3.5-35B-A3B 4-bit MoE local via Rapid-MLX + Kilo Code`
2. Model reference: `openai-compatible/qwen3.5-35b-a3b`
3. Context: `131K tokens`
4. Architecture: `MoE 35B total, 3B active per token, 4-bit quantization (~18GB VRAM)`
5. Server command: updated with new flags
6. Tool calling: `hermes parser`
7. Stale model literals: add `qwen3.6-27b` to the stale list

- **Dependency:** Phase 2 complete
- **Definition of done:** No references to `qwen3.6-27b-8bit` or `qwen3_coder_xml` remain in active model standard. `qwen3.6-27b` is listed as stale.

### Task 4.5 — [MODIFY] `AGENTS.md`

Update the model line in the Architecture section:
- `Model: Qwen3.5-35B-A3B MoE 4-bit (local via Rapid-MLX, 131K context, MoE 35B/3B active, thinking mode ALWAYS ON).`

- **Dependency:** Phase 2 complete
- **Definition of done:** AGENTS.md references the new model. No mentions of `qwen3.6-27b-8bit` in the Architecture section.

---

## Phase 5: Start New Server and Validate

> Goal: Confirm production config works end-to-end.

### Task 5.1 — [REUSE] Start new server on port 8000

```fish
./scripts/start_local_model.sh
```

- **Dependency:** Phase 3 + Task 4.1 complete
- **Definition of done:** `curl http://localhost:8000/v1/models` returns `qwen3.5-35b-4bit`.

### Task 5.2 — [REUSE] Repeat validation (tool call + reasoning + speed)

Run same tests as Tasks 1.3–1.5 against port 8000.

- **Dependency:** Task 5.1
- **Definition of done:** All three checks pass on production port.

### Task 5.3 — [REUSE] Install LaunchDaemon for auto-start

```fish
cp config/com.rapid-mlx.server.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/(id -u) ~/Library/LaunchAgents/com.rapid-mlx.server.plist
```

- **Dependency:** Task 5.2
- **Definition of done:** `launchctl print gui/(id -u)/com.rapid-mlx.server` shows service running.

### Task 5.4 — [REUSE] Start new Kilo Code session

Open Kilo Code, verify it connects to the new model and can execute tool calls.

- **Dependency:** Task 5.2
- **Definition of done:** Kilo Code session starts, model responds, tool calls work (test with a simple MCP tool like `sequentialthinking`).

---

## Rollback Procedure

If any Phase 5 validation fails:

```fish
# 1. Stop new server
lsof -ti :8000 | xargs kill

# 2. Restore configs
cp kilo.jsonc.bak-qwen36-27b kilo.jsonc
cp config/com.rapid-mlx.server.plist.bak-qwen36-27b config/com.rapid-mlx.server.plist
cp scripts/start_local_model.sh.bak-qwen36-27b scripts/start_local_model.sh

# 3. Restart old server
./scripts/start_local_model.sh

# 4. Restore LaunchDaemon
cp config/com.rapid-mlx.server.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/(id -u) ~/Library/LaunchAgents/com.rapid-mlx.server.plist
```

If hermes tool calling is unreliable but speed improvement is needed, use **Qwen3.6-35B-DWQ** as documented in research §6.4 (keeps `qwen3_coder_xml` parser, ~17 tok/s).

---

## Success Criteria

| Metric | Threshold | Target |
|--------|-----------|--------|
| Server starts on port 8000 | Required | — |
| Tool calls parse correctly (hermes) | 100% of test cases | — |
| Reasoning (`<think>`) populated | Required | — |
| Generation speed | >15 tok/s | >40 tok/s |
| Prefill 23K tokens | <60s | <25s |
| Kilo Code session functional | Required | — |
| Memory usage (Metal) | <35 GB | <28 GB |
| No references to old model in active config | Required | — |

---

## Dependencies Graph

```
Phase 1 (validate) ──→ Phase 2 (backup) ──→ Phase 3 (stop old) ──→ Phase 4 (apply) ──→ Phase 5 (start new)
                                                                                              │
                                                                                              ▼
                                                                                      [ROLLBACK if fail]
```

Phase 1 can run concurrently with production (uses port 8001). Phases 2–5 are sequential and require ~10 minutes total downtime.
