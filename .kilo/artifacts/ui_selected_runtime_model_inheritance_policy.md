# UI Selected Runtime Model Inheritance Policy Artifact

- Policy: `USER_SELECTED_KILO_UI_RUNTIME_INHERITANCE`
- Source of truth: `ACTIVE_KILO_UI_RUNTIME_MODEL`
- Orchestrator: inherits the active Kilo session model.
- Required betting subagents: inherit parent or orchestrator model unless a dedicated override was explicitly user-approved.
- PASS requires launched subagent, known active runtime model, `ProviderModelNotFoundError=false`, no silent fallback, inherited parent model or approved override, and a smoke artifact.
- Forbidden: hardcoded Gemini-only gate, hardcoded OpenAI-only gate, hardcoded local-only gate, stale explicit override, silent fallback, unknown runtime PASS.
