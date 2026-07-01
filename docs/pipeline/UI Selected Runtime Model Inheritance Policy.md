# UI Selected Runtime Model Inheritance Policy

## Source Of Truth

- The active model selected in Kilo UI is the source of truth for the current session.
- `bet-orchestrator` must use the active Kilo session model.
- Required betting subagents must inherit the active parent/orchestrator model unless the user explicitly approves a dedicated override for that task.

## Approved Runtime Outcomes

- OpenAI/GPT-5.4 is valid when it is the active UI-selected model and launch smoke passes.
- Gemini is valid when it is the active UI-selected model and launch smoke passes.
- Local models are valid when they are the active UI-selected model and launch smoke passes.
- Any selected provider/model is valid when the user has access, the runtime is known, and launch smoke passes.

## Smoke PASS Requirements

- The subagent launched.
- The active runtime model was recorded.
- `ProviderModelNotFoundError=false`.
- `inherited_parent_model=true`, or the subagent used an explicitly user-approved override.
- No silent fallback occurred.
- No conflicting explicit provider/model override occurred.

## Hard Failures

- Unknown active runtime model.
- `ProviderModelNotFoundError=true`.
- Silent fallback to another model without user visibility.
- Explicit stale or conflicting provider/model override.
- Claiming PASS without runtime proof.

## Forbidden Policy Shapes

- Hardcoded Gemini-only policy.
- Hardcoded OpenAI-only policy.
- Required betting subagent provider/model pins.
- Silent fallback to another model.
- False PASS without recorded runtime evidence.
