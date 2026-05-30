# Kilo Code Setup: Qwen3.6-35B-A3B MoE 4-bit (Local via Rapid-MLX)

## One-Time Setup (5 minutes + download)

### 1. Install Rapid-MLX

```fish
pipx install rapid-mlx
```

### 2. Pull the Model

```fish
~/.local/bin/rapid-mlx pull qwen3.6-35b
```

Downloads `mlx-community/Qwen3.6-35B-A3B-4bit` (~18 GiB).

### 3. Start the Server

```fish
./scripts/start_local_model.sh
```

Or manually:
```fish
~/.local/bin/rapid-mlx serve qwen3.6-35b --port 8000 \
  --no-mllm --max-num-seqs 1 --reasoning-parser qwen3 \
  --default-temperature 0.6 --default-top-p 0.95 --default-top-k 20 \
  --max-tokens 32768 --pin-system-prompt --enable-prefix-cache \
  --kv-cache-turboquant --kv-cache-turboquant-bits 3 \
  --cache-memory-mb 12000 --gpu-memory-utilization 0.88 \
  --prefill-step-size 8192 --gc-control \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder_xml
```

Wait for `Ready: http://localhost:8000/v1`.

### 4. Configure Kilo Code Extension

1. Open Kilo Code panel → click gear icon (⚙️)
2. **API Provider:** select **"OpenAI Compatible"**
3. **Base URL:** `http://localhost:8000/v1`
4. **API Key:** `not-needed` (any value works)
5. **Model:** auto-reads from `kilo.jsonc` → `openai-compatible/qwen3.6-35b-a3b`
6. Done!

### 5. Verify

Switch to `bet-orchestrator` agent and test tool calling:
```fish
curl http://localhost:8000/v1/models
```

---

## Model Details

| Property | Value |
|----------|-------|
| Model | Qwen3.6-35B-A3B MoE 4-bit (hybrid attention/Mamba) |
| Architecture | MoE 35B total, 3B active per token |
| VRAM | ~19-20GB (4-bit quantization) |
| Context | 131K tokens (model maximum) |
| Speed | ~45-70 tok/s on M4 Pro 48GB |
| Tool calling | qwen3_coder_xml parser |
| Reasoning | qwen3 parser (`<think>` blocks — ALWAYS ON) |
| Cost | $0 (fully local) |
| Rate limits | None |
| HuggingFace | `mlx-community/Qwen3.6-35B-A3B-4bit` |

## Why Qwen3.6-35B-A3B MoE 4-bit

- MoE 35B → 35B total knowledge, only 3B params active per token → fast generation
- 4-bit precision → fits comfortably in 48GB unified memory with 21GB headroom
- Thinking mode → `<think>` blocks before every answer (critical for betting analysis)
- 131K context → entire pipeline state fits in one call
- Hybrid attention/Mamba → Mamba layers don't use KV cache → more context capacity
- TurboQuant V-cache → 86% prefix cache savings
- No API costs, no rate limits, full privacy, deterministic
- No OOM risk — old 27B Dense 8-bit saturated Metal → 1 tok/s, kernel panic risk

## Auto-Start (Optional)

```fish
cp config/com.rapid-mlx.server.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.rapid-mlx.server.plist
```

## Context Budget

- Agent system prompt: ~3-5K tokens
- Instructions (loaded per agent): ~2-8K tokens
- External prompt files: ~1-3K tokens each
- Working context for analysis: ~100-120K tokens available
- Total usable per request: ~125K tokens (sufficient for full pipeline state)

## CRITICAL: Thinking Mode

- NEVER use `--no-thinking` — this destroys pipeline value
- The `<think>` blocks are where the model reasons through evidence
- Betting decisions require: weighing stats, considering context, challenging assumptions
- Without thinking: model produces surface-level script-like output = WORTHLESS
