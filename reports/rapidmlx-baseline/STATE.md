# Phase 1 — Rapid-MLX Raw Baseline State

## Metadata

- **Phase:** P1 — Production-Oriented Rapid-MLX Raw Baseline
- **Repository:** /Users/mkoziol/projects/bet/.kilo/worktrees/cherry-juice
- **Branch:** cherry-juice
- **Initial HEAD:** 515927c9e966dd886b171b70b1651d83c880f473
- **UTC Start:** 2026-06-11T19:28:54Z
- **Controller:** GPT-5.4 (reasoning: medium)

## Current Stage

COMPLETE — RAPID_BASELINE_PASS

## Selected Environment

- **Status:** ESTABLISHED
- **Python Path:** /Users/mkoziol/.venvs/rapid-mlx-0.7.1/bin/python3
- **Rapid-MLX Binary:** /Users/mkoziol/.venvs/rapid-mlx-0.7.1/bin/rapid-mlx
- **Rapid-MLX Version:** 0.7.1
- **Model Alias:** qwen3.6-35b-4bit
- **Model Canonical:** mlx-community/Qwen3.6-35B-A3B-4bit
- **Tool Parser:** qwen3_coder_xml (auto-detected)
- **Reasoning Parser:** qwen3 (auto-detected)
- **Server PID:** 54776 (launcher-managed, corrected 2026-06-12)

## Configuration Fingerprint

- **Status:** FINALIZED
- **Fingerprint ID:** run-20260611T195541Z-330294b8
- **Repository HEAD:** 515927c9e966dd886b171b70b1651d83c880f473
- **Suite Version:** 1.0.0

## Completed Gates

- [x] P1.0 — Clean workspace confirmed
- [x] P1.1 — Rapid-MLX 0.7.1 environment established
- [x] P1.2 — Model candidate verified (qwen3.6-35b-4bit)
- [x] P1.3 — Pre-start system state captured
- [x] P1.4 — Launcher script created
- [x] P1.5 — Server started and qualified
- [x] P1.6 — Test harness created
- [x] P1.8 — Smoke suite passed
- [x] P1.9 — Chat qualification passed (10/10)
- [x] P1.10 — Single-tool qualification passed (35/35)
- [x] P1.11 — Sequential workflow passed (15/15)
- [x] P1.12 — Streaming chat passed (6/6)
- [x] P1.13 — Cancellation recovery passed (3/3)
- [x] P1.14 — Truncation safety verified
- [x] P1.15 — Cache diagnostic completed
- [x] P1.16 — Multi-turn stability passed (20/20)
- [x] P1.17 — Resource observations captured
- [x] Final report generated

## Invalidated Gates

- NONE

## Blockers

- NONE

## Final Status

**RAPID_BASELINE_PASS**

All mandatory gates passed under one unchanged configuration fingerprint.

---

## Runtime Correction Record (2026-06-12T06:43:00Z)

### Detected Drift

A direct Rapid-MLX background process was started outside the certified launcher:

- **Kilo background handle:** `bgp_eba6b08ec0010F2wcz0AaHMwQv`
- **Reported OS PID:** 29827
- **Issue:** Process was launched directly with full Hugging Face repository ID and `--text-only` flag instead of through `scripts/rapidmlx-baseline.sh start`
- **Detection time:** 2026-06-12T06:43:17Z

### Correction Actions

1. Verified PID 29827 was not running (process had already terminated)
2. Verified port 8000 was free
3. Started Rapid-MLX through certified launcher: `scripts/rapidmlx-baseline.sh start`
4. Verified launcher-managed runtime matches Phase 1 fingerprint

### Discarded Test Results

- Any Phase 2 results produced against PID 29827 are discarded
- No Phase 2 results were recorded before correction was applied

### Corrected Launcher-Managed Runtime

| Property | Value |
|----------|-------|
| PID | 54776 |
| Start Time | Fri Jun 12 08:43:53 2026 |
| Binary | `/Users/mkoziol/.venvs/rapid-mlx-0.7.1/bin/rapid-mlx` |
| Version | 0.7.1 |
| Model Alias | `qwen3.6-35b-4bit` |
| Model Canonical | `mlx-community/Qwen3.6-35B-A3B-4bit` |
| Tool Parser | `qwen3_coder_xml` |
| Reasoning Parser | `qwen3` |
| Host | 127.0.0.1 |
| Port | 8000 |
| Max Tokens | 4096 |
| GPU Memory Utilization | 0.70 |

### Phase 1 Fingerprint Comparison

| Property | Phase 1 Final | Current | Match |
|----------|---------------|---------|-------|
| Binary | `/Users/mkoziol/.venvs/rapid-mlx-0.7.1/bin/rapid-mlx` | Same | YES |
| Version | 0.7.1 | 0.7.1 | YES |
| Model Alias | `qwen3.6-35b-4bit` | Same | YES |
| Model Canonical | `mlx-community/Qwen3.6-35B-A3B-4bit` | Same | YES |
| Tool Parser | `qwen3_coder_xml` | Same | YES |
| Reasoning Parser | `qwen3` | Same | YES |
| Host | 127.0.0.1 | Same | YES |
| Port | 8000 | Same | YES |
| Max Tokens | 4096 | Same | YES |
| GPU Memory Utilization | 0.70 | Same | YES |
| MLLM | Disabled (`--no-mllm`) | Same | YES |

**Fingerprint match: EXACT**

### Smoke Subset Results (2026-06-12T06:45:59Z)

Run ID: `run-20260612T064559Z-a0b588ab`

| Test | Result |
|------|--------|
| Health check | PASS (HTTP 200) |
| Models endpoint | PASS (HTTP 200) |
| Non-thinking chat | PASS |
| Thinking chat | PASS |
| Forced tool call (non-streaming) | PASS (tool_calls=1) |
| Automatic tool selection (streaming) | PASS (tool_calls=1) |
| No-tool negative control | PASS (tool_calls=0) |

**Smoke subset: 7/7 PASS**

### Evidence Paths

- Smoke results: `reports/rapidmlx-baseline/runs/run-20260612T064559Z-a0b588ab.json`
- Manifest: `reports/rapidmlx-baseline/runtime/manifest.json`
- PID file: `reports/rapidmlx-baseline/runtime/rapid-mlx.pid`
- Startup log: `reports/rapidmlx-baseline/logs/startup.log`

---

## Next Atomic Action

Continue Phase 2 from P2.2: Kilo integration testing with launcher-managed runtime.
