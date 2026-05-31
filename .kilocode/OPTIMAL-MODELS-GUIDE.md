# Kilo Code — Model Configuration (May 2026)

## Active Model: Qwen3.6-35B-A3B MoE 4-bit (Local via Rapid-MLX)

All 10 agents use: `openai-compatible/qwen3.6-35b-a3b`

| Property | Value |
|----------|-------|
| Provider | OpenAI-compatible (local Rapid-MLX server) |
| Base URL | `http://localhost:8000/v1` |
| Context | 131K tokens (model max), 64K recommended active |
| Speed | 45-70 tok/s generation on M4 Pro 48GB |
| Prefill | 15-25s for 23K token prompts |
| VRAM model | ~19-20GB (4-bit MoE on disk/Metal) |
| VRAM KV | ~12GB available (4-bit quantized + TurboQuant V-cache) |
| Rate limits | None (fully local) |
| Tool calling | qwen3_coder_xml parser (native Qwen3.6 format) |
| Reasoning | qwen3 parser (`<think>` blocks — ALWAYS ON) |
| Architecture | MoE 35B total, 3B active per token, hybrid attention/Mamba |
| HuggingFace | `mlx-community/Qwen3.6-35B-A3B-4bit` |

## Why Qwen3.6-35B-A3B MoE 4-bit

| Benefit | Detail |
|---------|--------|
| Deep reasoning | `<think>` blocks + `preserve_thinking` — model retains reasoning across multi-turn |
| MoE efficiency | 35B knowledge but only 3B params read per token → 45-70 tok/s |
| Memory headroom | 19GB model leaves 21GB for KV cache + OS (vs 32GB for old 27B Dense 8-bit) |
| No OOM risk | Old model saturated 40GB Metal → 1 tok/s, kernel panic risk. New model: abundant headroom |
| No rate limits | Pipeline runs at full speed without pauses |
| No API costs | $0 forever |
| Privacy | All data stays on-device |
| 131K context | Pipeline state fits: shortlists + stats + tipster arguments |
| Hybrid arch | Mamba layers DON'T use KV cache → more context fits in RAM |
| TurboQuant | V-cache compressed to 3-bit → 86% prefix cache savings |

## Setup

1. Install: `pipx install rapid-mlx`
2. Pull: `~/.local/bin/rapid-mlx pull qwen3.6-35b`
3. Start: `./scripts/start_local_model.sh`
4. Kilo Settings → API Provider → **OpenAI Compatible**
5. Base URL: `http://localhost:8000/v1`, API Key: `not-needed`
6. Model auto-reads from `kilo.jsonc` → `openai-compatible/qwen3.6-35b-a3b`

## Server Command (Full Optimized — State of Art)

```fish
~/.local/bin/rapid-mlx serve qwen3.6-35b --port 8000 \
  --no-mllm --max-num-seqs 1 --reasoning-parser qwen3 \
  --default-temperature 0.6 --default-top-p 0.95 --default-top-k 20 \
  --default-repetition-penalty 1.05 \
  --max-tokens 16384 --pin-system-prompt --enable-prefix-cache \
  --kv-cache-turboquant --kv-cache-turboquant-bits 3 \
  --cache-memory-mb 2000 --gpu-memory-utilization 0.9 \
  --prefill-step-size 4096 --gc-control \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder_xml
```

## Server Modes

| Mode | Command | GPU % | Cache | Use Case |
|------|---------|-------|-------|----------|
| Default | `./scripts/start_local_model.sh` | 88% | 12GB | Normal pipeline |
| Safe | `./scripts/start_local_model.sh --safe` | 75% | 8GB | Heavy multitasking |
| Minimal | `./scripts/start_local_model.sh --minimal` | default | default | Debugging |

## Parameter Rationale (Optimized for Betting Pipeline)

| Parameter | Value | Why |
|-----------|-------|-----|
| `--no-mllm` | skip vision | Pipeline never uses images, frees ~2GB |
| `--max-num-seqs 1` | single request | Sequential pipeline, dedicate ALL resources |
| `--reasoning-parser qwen3` | `<think>` blocks | CORE VALUE — model reasons through evidence first |
| `--temperature 0.6` | MINIMUM | **CRITICAL** — below 0.6, model skips `<think>` blocks entirely. All agents must use ≥ 0.6 |
| `--top-p 0.95 + top-k 20` | Qwen optimal | Diverse but controlled token selection |
| `--default-repetition-penalty 1.05` | anti-loop | Penalizes repeated tokens 5% — breaks degenerate enumeration loops |
| `--max-tokens 16384` | controlled | Server-side safety cap. Client (kilo.jsonc) further limits to 8192. |
| `--pin-system-prompt` | cached | Agent instructions stay in Metal — sub-100ms TTFT on repeat |
| `--enable-prefix-cache` | reuse KV | Multi-step orchestrator reuses common prompt prefix = instant |
| `--kv-cache-turboquant` | 3-bit V-cache | 86% savings on prefix cache. K stays FP16 for accuracy |
| `--cache-memory-mb 2000` | 2GB | Conservative — prevents Metal OOM with 4096 prefill chunks |
| `--gpu-memory-utilization 0.9` | 90% Metal | 19GB model + 2GB cache + overhead = safe within 40GB Metal |
| `--prefill-step-size 4096` | small chunks | **CRITICAL** — larger values (8K/16K) cause OOM at 17K+ token prompts with tools |
| `--gc-control` | no GC during gen | No latency spikes during reasoning chains |
| `--tool-call-parser qwen3_coder_xml` | native | Qwen3.6's built-in XML tool format — highest accuracy |

## Memory Budget (M4 Pro 48GB)

```
Total System RAM:      48 GB
Metal GPU allocation:  40.2 GB (83.75% — Apple reserves the rest)

Model weights:         ~19 GB (4-bit MoE, 35B params)
KV cache allocation:   ~12 GB (for active + prefix cache)
TurboQuant savings:    ~86% on V-cache → effectively 4x more context
OS + Metal overhead:    ~9 GB
───────────────────────────────────────
Total projected:       ~40 GB (99% Metal utilization, NO swap)

Compare to OLD model (Qwen3.6-27B Dense 8-bit):
  Model: 32 GB + KV: 8 GB = 40 GB → OOM, 1 tok/s, kernel panic risk
```

## Per-Request Temperature Strategy

⚠️ **CRITICAL: Qwen3.6 requires temperature ≥ 0.6 for `<think>` blocks to function.**
At temperatures below 0.6, the model immediately closes `</think>` and outputs reasoning as plain text
(not captured by the reasoning parser). This was verified empirically on 2026-05-29.

The server `--default-temperature 0.6` applies when Kilo doesn't override. ALL Kilo agents use 0.6.

| Pipeline Step | Temperature | Why |
|---------------|-------------|-----|
| ALL steps | 0.6 | MINIMUM required for `<think>` block generation |

**Why 0.6 is safe for structured/deterministic work:**
- `--default-top-k 20` constrains sampling to top 20 tokens → prevents hallucination
- `--default-top-p 0.95` adds further constraint
- The model intelligently decides WHEN to think deeply vs. answer directly
- For simple prompts: skips thinking, produces deterministic structured output
- For complex analysis: engages 8-13K chars of reasoning, then structured output
- Verified: even without thinking, output quality is high (correct answers, proper structure)
- With thinking: output gains self-correction, exhaustive bear cases, and deeper calculation verification

**NEVER set agent temperature below 0.6** — doing so silently destroys analytical value.

**top_k=20 is verified optimal** — higher values (40, 60) produce identical results. Lower keeps reasoning focused.

## Thinking Mode (Qwen3.6 Native) — Verified 2026-05-29

- **`<think>` blocks are ALWAYS ON** (server: `--reasoning-parser qwen3`)
- **MINIMUM temperature 0.6 is MANDATORY** — below this, thinking is silently disabled
- Model generates internal reasoning before complex responses (8-13K chars for complex analysis)
- For simple/direct questions, model intelligently skips thinking (0 reasoning chars, fast answer)
- `preserve_thinking: true` — model retains reasoning context across multi-turn orchestrator loops
- NEVER use `--no-thinking` — this destroys analytical value
- NEVER set temperature < 0.6 — this has the SAME effect as `--no-thinking`
- In streaming mode: `reasoning_content` field carries thinking chunks separately from `content`

### Verified Benchmark Results (2026-05-29, Round 2)

| Prompt Type | Reasoning | Content | Time | Quality |
|-------------|-----------|---------|------|---------|
| Corners analysis (single pick, full stats) | 12,606 chars | 3,101 chars | 97.3s | Self-corrects calculations, identifies all bear cases |
| Gate checker (3 picks, devil's advocate) | 8,954 chars | 3,276 chars | 63.3s | Correct implied prob, catches recency bias, survivorship bias |
| Simple questions | 0 chars | direct answer | <5s | Intelligently skips thinking |

### Parameter Sensitivity (Empirically Verified)

| Parameter | Tested Values | Winner | Finding |
|-----------|---------------|--------|---------|
| temperature | 0.6 / 0.7 / 0.8 | **0.6** | ONLY 0.6 triggers `<think>` consistently. 0.7+ skips thinking entirely |
| top_k | 20 / 40 / 60 | **No difference** | All three produce identical behavior — top_k doesn't affect thinking engagement |
| max_tokens | 4096 / 8192 / 32768 | **≥8192** | At 4096, all tokens consumed by reasoning (0 content). 8192+ gives both |

### Thinking Engagement Note

Thinking activation is **probabilistic**, not deterministic. On repeated identical prompts with prefix
caching enabled, the model may skip thinking on subsequent calls (KV cache shortcutting). This does NOT
affect production pipeline behavior because:
1. Pipeline prompts always contain unique game data → no prefix cache hits on the analysis portion
2. Only affects exact-duplicate prompts in testing scenarios
3. When thinking activates, quality is excellent (self-correction, exhaustive analysis, bear cases)

## Auto-Start (launchd)

```fish
cp config/com.rapid-mlx.server.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/(id -u) ~/Library/LaunchAgents/com.rapid-mlx.server.plist
```

## Architecture Notes

- **MoE (Mixture of Experts)**: 128 expert networks per layer, top-2 routing per token. Only 3B parameters are read from memory per token — the rest sit idle. This gives 35B-class knowledge at 3B-class speed.
- **Speed formula**: Apple Silicon speed ≈ bandwidth / bytes-read-per-token. At 273 GB/s and ~1.5 GB read (3B × 0.5 bytes at 4-bit), theoretical max ≈ 182 tok/s. Realistic with overhead + thinking: 45-70 tok/s.
- **Hybrid attention/Mamba**: Some layers use Mamba (linear attention) which processes tokens without KV cache. Reduces memory pressure for long contexts.
- **4-bit MoE quantization**: On MoE models, 4-bit has LESS quality impact than on dense models (expert redundancy absorbs quantization noise).
- **TurboQuant V-cache**: Compresses Value cache to 3-bit while keeping Keys in FP16. This is safe because V vectors have lower entropy than K vectors.

## Important Notes

- Tool calling uses `qwen3_coder_xml` format (Qwen3.6 native — NOT hermes)
- Reasoning uses `qwen3` parser (parses `<think>...</think>` blocks)
- **NEVER use `--no-thinking`** — this destroys pipeline value
- **NEVER set temperature below 0.6** — this silently disables `<think>` blocks (same effect as --no-thinking)
- Context window is 131K (model max), practical budget ~64K per active request
- The model alias in rapid-mlx is `qwen3.6-35b` → resolves to `mlx-community/Qwen3.6-35B-A3B-4bit`
- Previous model (Qwen3.6-27B Dense 8-bit at 32GB) caused OOM at 1 tok/s — NEVER go back
- In streaming mode, reasoning_content is properly separated into its own field (verified 2026-05-29)
- Non-streaming API may NOT aggregate reasoning_content correctly (possible Rapid-MLX bug) — always use streaming

## Rollback

If issues arise, backups are at:
- `scripts/start_local_model.sh.bak-qwen36-27b`
- `kilo.jsonc.bak-qwen36-27b`
- `config/com.rapid-mlx.server.plist.bak-qwen36-27b`
