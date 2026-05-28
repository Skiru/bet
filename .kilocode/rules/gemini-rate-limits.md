# Google Gemini 3.5 Flash — Rate Limits & Model Info

## Active Model (May 2026)

| Setting | Value |
|---------|-------|
| Model | `google/gemini-3.5-flash` |
| Context | 1M tokens |
| Provider | Google Gemini (direct API key) |
| Free tier | 1,500 RPD, 15 RPM |
| Pricing (if free exhausted) | ~$0.15/M input, $0.60/M output |

## All 10 Agents Use Same Model

No model switching needed. Single API key, single provider.

## Rate Limit Strategy

1. **Full pipeline** (S0→S8) uses ~80-120 calls. Well within 1,500 RPD.
2. **If RPM throttled** (15 RPM): pipeline naturally spaces calls — not an issue.
3. **S3 intensive step**: ~30 candidates × analysis calls. Fits comfortably.
4. **Context budget**: 1M tokens = ~750K words. Agent prompt + instructions ≈ 35K tokens (3.5%).

## Why Gemini 3.5 Flash

- Highest coding index of free models
- Designed for agentic workflows (tool calling, multi-step reasoning)
- 1M context window handles full pipeline state
- Free tier sufficient for daily betting pipeline

## Optimization

- Batch related candidates (5 per call max) to reduce call count
- Cache verdicts in `.kilocode/memory/session-state.md`
- Use `sequentialthinking_sequentialthinking` tool for multi-factor decisions (not simple lookups)
- Skip redundant re-analysis if DB already has fresh results
