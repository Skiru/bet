# Orchestrated Session Continuation Protocol

## J2 Resume Gate

- Resume J2 only after `ProviderModelNotFoundError` is repaired.
- Require `bet-enricher` smoke PASS and `bet-statistician` smoke PASS.
- Require `main` to be clean and synced before the follow-up orchestrated J2 session starts.
- The continuation prompt must explicitly say: do not repeat model repair.
- The continuation prompt must explicitly say: run J2 only.
