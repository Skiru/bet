# Orchestrated Session Continuation Protocol

## J2 Resume Gate

- Resume J2 only after `ProviderModelNotFoundError` is repaired.
- Require runtime proof that the active Kilo UI model is known and recorded.
- Require `bet-researcher` smoke PASS and `bet-modeler` smoke PASS.
- Require required betting subagents to inherit the active parent runtime model with no silent fallback and no conflicting explicit override.
- Require `main` to be clean and synced before the follow-up orchestrated J2 session starts.
- The continuation prompt must explicitly say: do not repeat model repair.
- The continuation prompt must explicitly say: run J2 only.
