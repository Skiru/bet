# UI Selected Runtime Model Inheritance Policy

## Source Of Truth

- `ACTIVE_KILO_UI_RUNTIME_MODEL` is the source of truth for the current session.
- `bet-orchestrator` inherits the active Kilo UI runtime model.
- Required betting subagents inherit the active parent or orchestrator runtime model by default.
- No required betting agent may pin a provider or model in frontmatter or profile by default.

## Approved Runtime Outcomes

- OpenAI and `gpt-5.4` are valid when selected in the Kilo UI and launch smoke passes.
- Gemini models are valid when selected in the Kilo UI and launch smoke passes.
- Local models are valid when selected in the Kilo UI and launch smoke passes.
- Another user-accessible provider or model is valid when selected in the Kilo UI, the runtime is known, and launch smoke passes.

## Smoke PASS Requirements

- The subagent launched.
- The active runtime model was recorded.
- `ProviderModelNotFoundError=false`.
- `inherited_parent_model=true`, or the subagent used an explicitly user-approved override.
- No silent fallback occurred.
- No conflicting explicit provider or model override occurred.
- A tiny artifact was written for the smoke run.

## Hard Failures

- Unknown active runtime model.
- `ProviderModelNotFoundError=true`.
- Silent fallback to another model without user visibility.
- Explicit stale or conflicting provider or model override.
- Claiming PASS without runtime proof.

## Forbidden Policy Shapes

- Hardcoded Gemini-only policy.
- Hardcoded OpenAI-only policy.
- Hardcoded local-only policy.
- Required betting subagent provider or model pins.
- Silent fallback to another model.
- False PASS without recorded runtime evidence.
