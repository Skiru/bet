# Local LLM Server - Rapid-MLX Production

## Server Configuration

**Model:** `mlx-community/Qwen3.6-35B-A3B-4bit`
**Runtime:** Rapid-MLX v0.6.82
**Endpoint:** `http://127.0.0.1:8000/v1`

## Architecture

- **Type:** MoE (Mixture of Experts)
- **Experts:** 256 total, 8 active per token
- **Active params:** ~3B per forward pass
- **Context:** 32768 tokens
- **Output:** 8192 tokens max

## Performance Profile

| Metric | Value | Test Date |
|--------|-------|-----------|
| Decode tok/s | 71.94 | 2026-06-09 |
| E2E tok/s | 67.67 | 2026-06-09 |
| Warm TTFT | 277ms | 2026-06-09 |
| Tool reliability | 100% | 2026-06-09 |
| Cache speedup | 12.4x | 2026-06-09 |

## Usage Rules

1. **Always use `stream: false`** - Non-streaming mode for stability
2. **Temperature 0.2** for deterministic operations
3. **Temperature 0.7** for reasoning tasks
4. **Max tokens 2048** for typical responses
5. **Max tokens 8192** for long-form or complex reasoning

## Cache Behavior

- First request with Kilo prefix (~5K tokens): ~10s
- Subsequent requests (same prefix): ~275ms
- Cache persists across requests in same session
- Cache cleared on server restart

## Known Limitations

- Photo/multimodal input: NOT SUPPORTED (text-only)
- MTP acceleration: NOT COMPATIBLE with this model
- Concurrency: Max 2-3 simultaneous for low latency
- Cold start: ~10s for first request after restart

## Server Management

```fish
# Start
scripts/start-local-model.fish

# Stop
scripts/stop-local-model.fish

# Health check
scripts/healthcheck-local-model.fish

# View logs
tail -f /tmp/rapid-mlx.log
```
