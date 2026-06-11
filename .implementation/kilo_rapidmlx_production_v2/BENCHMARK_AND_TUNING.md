# Benchmark and Tuning — M4 Pro 48 GB

## Objective

Select the most reliable Qwen3.6-35B-A3B configuration for long-running Kilo agent work. Do not optimize for decode tokens/second alone. A faster configuration that loses a tool call, grows swap, or fails compaction is disqualified.

## Candidate matrix

### A — certified baseline

```fish
set -gx RAPID_MLX_MODEL qwen3.6-35b-4bit
set -gx RAPID_MLX_PROFILE safe
./scripts/local-llm.sh restart
```

This uses Rapid-MLX's maintained alias and is the first configuration that must pass every gate.

### B — production profile

```fish
set -gx RAPID_MLX_MODEL qwen3.6-35b-4bit
set -gx RAPID_MLX_PROFILE production
./scripts/local-llm.sh restart
```

Promote only after candidate A passes.

### C — OptiQ quality candidate

```fish
set -gx RAPID_MLX_MODEL mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit
set -gx RAPID_MLX_PROFILE safe
./scripts/local-llm.sh restart
```

OptiQ is an A/B candidate, not the initial baseline. It must prove parser compatibility, stable tool calling, bounded memory and better task quality on the same suite. Do not enable Native MTP merely because the checkpoint contains an MTP head.

### D — benchmark-only prefill

```fish
set -gx RAPID_MLX_MODEL qwen3.6-35b-4bit
set -gx RAPID_MLX_PROFILE benchmark
./scripts/local-llm.sh restart
```

This is an isolated experiment. Any sustained swap growth, UI stalls or worse p95 latency disqualifies it.

## Fixed controls

Keep these unchanged across candidates:

- Kilo 7.3.41;
- Rapid-MLX 0.7.0;
- Kilo model ID `default` at the API boundary;
- context/input/output = 28,672 / 24,576 / 4,096;
- one LLM generation and one subagent at a time;
- identical prompts, tools, repository revision and MCP state;
- no DFlash, MTP, suffix decoding or tool-logits bias during baseline qualification;
- close memory-heavy applications or record them in the report.

## Test sequence per candidate

```fish
./scripts/local-llm.sh manifest
./scripts/local-llm.sh model-info
./scripts/prod-check.sh

./scripts/rapid_mlx_soak.py \
  --rounds 60 \
  --pause 2 \
  --pid-file .kilo/runtime/rapid-mlx-8000.pid \
  --report reports/rapid-soak-CANDIDATE.json

./scripts/kilo_compaction_soak.py \
  --turns 12 \
  --payload-chars 7000 \
  --report reports/kilo-compaction-CANDIDATE.json
```

In a second terminal during the soak:

```fish
./scripts/mac_resource_monitor.py \
  --pid-file .kilo/runtime/rapid-mlx-8000.pid \
  --duration 7200 \
  --output reports/mac-resources-CANDIDATE.csv
```

Then execute one real phase-sized workload with a new Kilo session and verify that it writes a bounded handoff.

## Hard disqualifiers

A candidate fails immediately on any of the following:

- crash, OOM or unrecoverable request timeout;
- malformed, missing or duplicated required tool call;
- `Compaction exhausted` or `ContextOverflowError`;
- failed continuation after a cancelled stream or compaction;
- monotonically increasing swap after warm-up;
- an output artifact that cannot be traced to the source tool result;
- a context-guard or read-only SQLite security test failure;
- a materially worse result on the fixed domain validation set.

## Score after hard gates pass

| Area | Weight | Measurement |
|---|---:|---|
| Tool and agent reliability | 40% | required tool calls, multi-tool order, continued sessions, phase completion |
| Context stability | 25% | no overflow, compaction recovery, handoff correctness |
| Memory stability | 15% | RSS plateau, swap trend, memory pressure |
| Latency | 15% | TTFT and end-to-end p50/p95, not only decode rate |
| Decode throughput | 5% | output tokens per wall-clock second |

The 5% throughput weight is deliberate: this is an agentic production system, not a chat benchmark.

## Promotion rule

- `safe` becomes the recovery profile after all hard gates pass.
- `production` becomes default only if it passes the same suite and improves end-to-end p95 without increasing errors or swap trend.
- OptiQ replaces the stock 4-bit model only if it passes all hard gates and wins a blind domain-quality comparison on a fixed set of repository tasks.
- `benchmark` never becomes default based on tokens/second alone.

## Regression cadence

Run the short `prod-check.sh` after changes to Kilo, Rapid-MLX, the model, plugins, MCP packages, prompts or context limits. Run the 60-round and compaction soaks before promoting a new baseline. Keep reports named with model, profile, Kilo version, Rapid-MLX version and date.
