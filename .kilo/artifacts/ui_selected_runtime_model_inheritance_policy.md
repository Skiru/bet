# UI Selected Runtime Model Inheritance Policy Artifact

- Policy: `USER_SELECTED_KILO_UI_RUNTIME_INHERITANCE`
- Source of truth: active Kilo UI model for the current session.
- Orchestrator: inherits the active Kilo session model.
- Required betting subagents: inherit parent/orchestrator model unless a dedicated override was explicitly user-approved.
- PASS requires launched subagent, known active runtime model, `ProviderModelNotFoundError=false`, no silent fallback, and inherited parent model or approved override.
- Forbidden: hardcoded Gemini-only gate, hardcoded OpenAI-only gate, stale explicit override, silent fallback, unknown runtime PASS.
