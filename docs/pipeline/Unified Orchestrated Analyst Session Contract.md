# Unified Orchestrated Analyst Session Contract

## Model Resolution

- `bet-orchestrator` must resolve to `google-vertex/gemini-3.5-flash-flex-high`.
- Every required subagent must either:
1. inherit a verified Gemini 3.5 Flash Flex model from bet-orchestrator, or
2. have an explicit model override that passes a live subagent launch smoke test.
- Broken explicit subagent overrides are a contract failure even when the same alias exists globally.
- OpenAI, Claude, and Qwen routing remain forbidden for required betting subagents.

## Runtime Proof

- `bet-enricher` and `bet-statistician` require live launch smoke evidence before J2 resumes.
- `bet-valuator`, `bet-challenger`, `bet-builder`, and `bet-test-engineer` should be smoke-tested when practical after model-resolution repair.
- A stale or precheck-blocked handoff does not satisfy runtime proof.
