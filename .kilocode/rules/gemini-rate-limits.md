# Kilo Gateway — Free Models & Rate Limits

## Active Models (May 2026)

| Agent | Model | Type | Notes |
|-------|-------|------|-------|
| bet-orchestrator | `poolside/laguna-m.1:free` | Flagship coding | #1 most used in Kilo |
| bet-statistician | `poolside/laguna-m.1:free` | Flagship coding | Deep analysis |
| bet-builder | `poolside/laguna-m.1:free` | Flagship coding | Portfolio construction |
| bet-challenger | `inclusionai/ring-2-6-1t:free` | 1T thinking | Gate reasoning |
| bet-settler | `nvidia/nemotron-3-super-120b-a12b:free` | 120B MoE | Settlement review |
| bet-enricher | `nvidia/nemotron-3-super-120b-a12b:free` | 120B MoE | Data quality |
| bet-valuator | `nvidia/nemotron-3-super-120b-a12b:free` | 120B MoE | Odds/EV |
| bet-scanner | `x-ai/grok-code-fast-1:optimized:free` | Fast optimized | Discovery |
| bet-scout | `x-ai/grok-code-fast-1:optimized:free` | Fast optimized | Tipster intel |
| bet-db-analyst | `google/gemma-4-26b-a4b-it:free` | Lightweight MoE | DB queries |

## Rate Limits (Free Models via Kilo Gateway)

- **No daily request limit** (unlike Google AI Studio's 1,500 RPD)
- **Per-minute throttling** may apply during peak hours
- **If throttled:** Switch to different free model (Nemotron ↔ Laguna ↔ Grok)
- **Context windows:** Laguna ~128K, Nemotron ~128K, Ring ~128K, Gemma ~32K

## Implications for Pipeline

1. **One full pipeline run** (S0→S8) uses ~50-100 agent calls. No daily cap issue.
2. **S3 intensive step:** ~30 candidates × delegation. Space calls if throttled.
3. **Fallback strategy:** If one model throttled → switch model ID in kilo.jsonc.
4. **Context budget:** Keep per-delegation prompts focused. Don't dump entire S3 report into one call.

## Optimization

- Batch related candidates (5 per call max) to reduce call count
- Cache verdicts in `.kilocode/memory/session-state.md`
- Use `sequentialthinking` MCP for multi-factor decisions (not simple lookups)
- Skip redundant re-analysis if DB already has fresh results
