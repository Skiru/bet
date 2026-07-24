# Unified Orchestrated Analyst Session Contract

## Model Resolution

- The active Kilo UI runtime model is the source of truth for the orchestrated session.
- `bet-orchestrator` must inherit the active Kilo session model.
- Every required subagent must inherit the active parent/orchestrator model unless the user explicitly approved a dedicated override for that task.
- A launch smoke PASS is valid only when the subagent launched, the active runtime model was recorded, `ProviderModelNotFoundError=false`, no silent fallback occurred, and inheritance held or the override was explicitly user-approved.
- Broken or stale explicit subagent overrides are a contract failure.
- If the active runtime model is unknown, block.

## Runtime Proof

- `bet-researcher` and `bet-modeler` require live launch smoke evidence before J2 resumes.
- `bet-modeler` should be smoke-tested with them for runtime-inheritance proof.
- The recorded active runtime may be OpenAI, Gemini, local, or another user-accessible subscribed model if launch smoke passes under the active UI selection.
- A stale or precheck-blocked handoff does not satisfy runtime proof.
