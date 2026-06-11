# Kilo Code Setup: Qwen3.6-35B-A3B-OptiQ-4bit (Local via oMLX)

## One-Time Setup (5 minutes + download)

### 1. Install oMLX

```fish
curl -fsSL https://omlx.ai/install.sh | sh
```

### 2. Download the Model

```fish
~/.omlx/bin/omlx download mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit
```

Downloads `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit` (OptiQ mixed-precision quant).

### 3. Start the Server

```fish
./scripts/start_local_model.sh
```

Or foreground mode:
```fish
./scripts/start_local_model.sh --foreground
```

Or directly:
```fish
~/.omlx/bin/omlx serve
```

Wait for `✅ omlx is online: http://127.0.0.1:8000/v1`.

### 4. Configure Kilo Code Extension

1. Open Kilo Code panel → click gear icon (⚙️)
2. **API Provider:** select **"OpenAI Compatible"**
3. **Base URL:** `http://127.0.0.1:8000/v1`
4. **API Key:** leave empty (no auth for localhost)
5. **Model:** auto-reads from `kilo.jsonc` → `openai-compatible/Qwen3.6-35B-A3B-OptiQ-4bit`
6. Done!

### 5. Verify

```fish
curl http://127.0.0.1:8000/v1/models
```

Expected: `{"data":[{"id":"Qwen3.6-35B-A3B-OptiQ-4bit",...}]}`

---

## Model Details

| Property | Value |
|----------|-------|
| Model | Qwen3.6-35B-A3B-OptiQ-4bit (MLX OptiQ mixed-precision quant via oMLX) |
| Architecture | MoE 35B total, 3B active per token, 256 experts, 8 active |
| Hybrid | 40 layers: 75% Mamba2 linear attention + 25% full attention |
| VRAM | ~19-20GB (4-bit OptiQ quantization) |
| Context | 262,144 tokens advertised by the model; active oMLX runtime cap is controlled separately in `~/.omlx/settings.json` |
| Speed | ~30-45 tok/s on M4 Pro 48GB |
| KV Cache | TurboQuant 3-bit (~75% reduction) |
| Tool calling | qwen3_coder_xml parser (native) |
| Reasoning | Enabled in model settings; production reliability still depends on checkpoints and prompt discipline |
| Cost | $0 (fully local) |
| Rate limits | None |
| Server | oMLX v0.4.0+ (`~/.omlx/bin/omlx`) |
| Config | `~/.omlx/settings.json` + `~/.omlx/model_settings.json` |

## Why Qwen3.6-35B-A3B MoE + oMLX

- **oMLX**: production-ready LLM server for Apple Silicon with LRU memory management, SSD-paged KV cache, hot cache, multi-model support
- **MoE 35B**: 35B total knowledge, only 3B params active per token → fast generation
- **OptiQ 4-bit**: mixed-precision quant preserves reasoning and tool-calling subspaces
- **Hybrid Mamba2**: 75% linear attention layers use no KV cache → more context fits
- **Thinking mode**: `<think>` blocks before every answer (critical for betting analysis)
- **Long context support**: the model advertises 262K, but the production runtime may use a lower safety cap to stay within RAM/Metal limits
- **TurboQuant V-cache**: 3-bit KV cache → ~75% prefix cache savings
- No API costs, no rate limits, full privacy, deterministic
- Automatic memory management with hot/SSD cache tiers

## Auto-Start (Optional)

```fish
cp config/com.omlx.server.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.omlx.server.plist
```

## Context Budget

- Agent system prompt: ~3-5K tokens
- Instructions (loaded per agent): ~2-8K tokens
- External prompt files: ~1-3K tokens each
- Working context for analysis: bounded by the active `sampling.max_context_window` in `~/.omlx/settings.json`
- Total usable per request: treat `session-state.md` and file artifacts as the persistence layer, not the raw prompt window

## CRITICAL: Thinking Mode

- NEVER disable thinking — this destroys pipeline value
- The model is configured for reasoning, but you should not assume infinite hidden-thought budget or raw-context persistence
- Betting decisions require: weighing stats, considering context, challenging assumptions
- Without thinking: model produces surface-level script-like output = WORTHLESS
