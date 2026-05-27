# Gemini 2.5 Flash — Rate Limits & Best Practices

## Free Tier Limits (Google AI Studio, no credit card)

| Limit | Value | Implication |
|-------|-------|-------------|
| Requests per day (RPD) | 1,500 | ~62/hour. Full pipeline run uses 50-80 requests. |
| Requests per minute (RPM) | 15 | Space agent calls ≥4s apart |
| Tokens per minute (TPM) | 250,000 | ~15K words/min input. Keep prompts focused. |
| Context window | 1,000,000 tokens | Massive — can load entire S3 reports |

## Implications for Pipeline

1. **One full pipeline run** (S0→S8) uses ~50-80 agent calls. At 1,500 RPD you get ~18 full runs/day.
2. **Rate limit during S3** (most intensive step): ~30 candidates × 1 call each = 30 calls. At 15 RPM = 2 minutes minimum between bursts.
3. **If rate-limited (429):** Wait 60s and retry. Don't panic. The limit resets per minute.
4. **Thinking budget:** Gemini 2.5 Flash supports `thinking_budget` parameter. For complex analysis (S3, S7), request more thinking tokens.

## Optimization Strategies

1. **Batch context:** Instead of 30 individual candidate calls, batch 5 candidates per call with full context.
2. **Cache agent outputs:** After S3, write verdicts to `.kilocode/memory/session-state.md`. If interrupted, resume from last completed candidate.
3. **Prioritize thinking:** Use `sequentialthinking` MCP for multi-factor decisions (not simple lookups).
4. **Skip redundant calls:** If DB already has today's analysis_results, don't re-run S3.

## Fallback: DeepSeek V3

If Gemini quota exhausted:
- Cost: ~$0.27/1M input tokens ($1.10/1M output)
- Monthly estimate: ~$3-5 for typical betting pipeline usage
- Context: 128K tokens (smaller but sufficient for individual candidates)
- Configure in Kilo Code settings as secondary provider

## Thinking Budget Hints

| Step | Complexity | Suggested Budget |
|------|-----------|-----------------|
| S0 Settlement | Low | Default |
| S1 Discovery | Low | Default |
| S2 Tipster | Medium | Extended |
| S3 Deep Stats | HIGH | Maximum |
| S4 Odds | Medium | Extended |
| S5 Context | HIGH | Maximum |
| S6 Upset Risk | HIGH | Maximum |
| S7 Gate | HIGH | Maximum |
| S8 Coupons | Medium | Extended |
