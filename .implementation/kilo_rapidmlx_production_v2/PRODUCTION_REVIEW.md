# Production Review — Kilo Code + Rapid-MLX on M4 Pro 48 GB

## Executive decision

Use one direct, observable path:

```text
Kilo VS Code / Kilo CLI
        ↓ OpenAI-compatible API
Rapid-MLX 0.7.0 on 127.0.0.1:8000
        ↓
Qwen3.6-35B-A3B 4-bit
```

Do not put LM Studio, LiteLLM, Open WebUI or another proxy in the critical path until the direct baseline passes. They may be added later for UI or metrics, but each adds another streaming, timeout and schema-translation failure surface.

## Critical corrections to the existing repository documentation

1. The project README names oMLX in its introduction and Rapid-MLX later. Rapid-MLX is the single production backend.
2. `131K` is a model capability claim, not a safe operational budget for a 48 GB multi-agent workload. The production Kilo contract is 28,672 total / 24,576 input / 4,096 output.
3. Mandatory public `<think>` blocks plus a sequential-thinking MCP duplicate reasoning and rapidly inflate context. They are removed.
4. A single A→E conversation is replaced by one Kilo session per phase group with compact, versioned handoffs.
5. `.kilocode/memory/session-state.md` is replaced by `.kilo/state/CURRENT_HANDOFF.md`; `AGENTS.md` remains the durable policy source.
6. Rapid-MLX 0.6.82 references are replaced by exact version 0.7.0.
7. `./scripts/start-local-model.fish` is replaced by the sole launcher `./scripts/local-llm.sh`.
8. The archived reference SQLite MCP server is removed. A project-local read-only Kilo tool opens SQLite in `mode=ro`, denies write opcodes and PRAGMA, limits VM work, rows and output bytes.

## Why the context-guard plugin is mandatory

Kilo's built-in prune pass clears completed tool outputs only after they leave a fixed 40,000-token recency window. That window is larger than the entire 28K model budget used here, so built-in pruning cannot be the first line of defense.

The project plugin therefore:

- truncates each tool result above 12 KiB before it becomes durable conversation history;
- stores the complete result under `.kilo/artifacts/tool-output/`;
- keeps only a bounded head/tail preview in the transcript;
- caps requested model output at 4,096 tokens;
- injects phase/handoff requirements into compaction;
- disables the synthetic auto-continue turn when compaction was caused by overflow;
- records truncations and session errors in `.kilo/runtime/context-guard.jsonl`.

The plugin can be isolated with `KILO_PURE=1` to distinguish provider/config failures from plugin failures.

## Why Kilo CLI is part of the production design

Kilo CLI is not a second orchestrator. It is the deterministic QA and operations interface for the same configuration used by VS Code:

- `kilo config check` and `kilo debug config` verify the resolved configuration;
- `kilo debug agent` verifies effective agent permissions;
- `kilo debug skill` verifies on-demand skill discovery;
- `kilo mcp list` verifies only the enabled external MCP servers;
- `kilo roll-call` checks provider/model transport and latency;
- `kilo run --format json --session ...` drives repeatable continued-session tests;
- `kilo export --sanitize` captures failed sessions without leaking file contents;
- `kilo stats` provides a second view of token/tool usage.

Never use `kilo run --auto` as the normal production launcher: it approves every permission. The tests use narrowly scoped agents whose permissions are explicit in `kilo.jsonc`.

## Context architecture

```text
Long-lived truth                  Short-lived model context
-----------------------------     ----------------------------
SQLite + generated artifacts  →   only required rows/ranges
phase handoff files           →   current phase state
AGENTS.md + on-demand skills  →   compact durable rules
full tool output artifacts    →   12 KiB bounded preview
```

Rules:

- one local LLM generation at a time;
- one subagent at a time;
- phase A/B/C/D/E in separate sessions;
- no raw terminal dumps, full database exports or browser snapshots in chat;
- handoff under 1,200 tokens;
- manual `/compact` before a major in-phase transition, never after overflow.

## Runtime profiles

| Profile | Prefill step | GPU memory utilization | Purpose |
|---|---:|---:|---|
| `safe` | 1024 | 0.66 | First validation and recovery baseline |
| `production` | 2048 | 0.70 | Default after all safe gates pass |
| `benchmark` | 4096 | 0.74 | Isolated experiment only |

All profiles use 4,096 max output, KV-cache quantization, text-only mode, telemetry disabled, localhost binding and a single model process.

## Production acceptance gates

1. Exact Kilo and Rapid-MLX versions are recorded.
2. Raw chat, single-tool, multi-tool, streaming and bounded-context tests pass.
3. Kilo resolves the expected provider/model, limits and agent permissions.
4. The custom read-only SQLite tool passes a deterministic direct invocation.
5. The context-guard test creates a full artifact, returns a bounded transcript and successfully continues the session.
6. Twelve continued Kilo CLI turns pass without overflow.
7. A compaction-pressure session continues without `Compaction exhausted`.
8. A 60-round raw Rapid-MLX soak passes with no crash/OOM/tool-parser failure.
9. A real phase-sized Kilo session completes and writes its handoff.
10. RSS reaches a plateau and swap does not rise monotonically.

Production-ready means these gates pass on the target Mac. Static validation elsewhere is not a substitute for the Mac soak.

## Deferred experiments

Test one change per report and never mix experimental flags into the baseline:

- `benchmark` prefill profile;
- tool-logits bias;
- suffix decoding;
- LiteLLM + Prometheus/Grafana after direct-path qualification;
- Playwright MCP 0.0.76 only in phases that need browser automation; prefer the repository's bounded Playwright scripts when they already cover the task;
- an OptiQ 4-bit A/B candidate after the stock Rapid-MLX alias is certified;
- a separate dense reviewer model only after the 35B baseline is stable.

Do not enable DFlash for this 35B agentic path. Do not enable MTP unless the checkpoint contains compatible MTP tensors and passes the same tool/context suite.

## Community evidence and limitations

Reports from M4 Pro 48 GB users indicate that Qwen3.6-35B-A3B can be practical for tool-oriented work and may be more attractive than the slower dense 27B on this memory class. Other reports show that long-context prefill, cache growth and tool reliability vary substantially by runtime, quant and workload. These reports are useful for selecting experiments, not for certifying this Mac. The package therefore records local p50/p95 latency, RSS, swap, tool success and exact versions.
