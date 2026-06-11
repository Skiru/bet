# Hybrid context policy

- Select exactly one primary agent for the session: `code-local`, `code-gpt54`, or `bet-orchestrator`.
- Start a new session whenever switching provider, primary agent, project phase, or profile.
- A manual model choice in the UI overrides the agent model. Reset the session override before relying on agent defaults.
- Local Qwen sessions: one tool call at a time, one subagent at a time, tool output below 8 KiB, and manual checkpoint before `/compact`.
- GPT-5.4 sessions: independent read-only tools may be grouped, but file mutations, shell mutations, commits, and subagent delegation stay sequential.
- Never request or expose hidden chain-of-thought. Return evidence, decisions, calculations, uncertainty, and next actions.
- Persist verbose logs and reports under `.kilo/artifacts/`; keep only summaries and paths in chat.
- Maximum two attempts for the same failing operation. Then change strategy or delegate.
