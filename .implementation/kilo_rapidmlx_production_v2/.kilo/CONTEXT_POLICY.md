# Context-Safety Policy

This policy is mandatory for every agent using the local 28K/4K model profile.

## Hard budgets

- Kilo input budget: 24,576 tokens.
- Kilo output cap: 4,096 tokens.
- Automatic compaction target: 65%.
- Reserved safety buffer: 6,144 tokens.
- One active model generation at a time.
- One subagent at a time.

## Tool-output discipline

The `production-context-guard` plugin stores any result above 12 KiB in `.kilo/artifacts/tool-output/` and replaces it with a head/tail preview. Agents must not bypass this behavior by reopening the entire artifact unless a bounded range is necessary.

Prefer:

1. SQL aggregation instead of raw rows.
2. `rg`, `jq`, `sed`, `head`, `tail` or a script-generated summary instead of full logs.
3. File path + line range instead of complete file contents.
4. Per-phase JSON/Markdown artifacts instead of conversational memory.

## Session lifecycle

1. Read `AGENTS.md`, this policy and the current phase handoff.
2. Work only on the declared phase and exit criteria.
3. Persist detailed results to files as they are created.
4. Write a handoff before compaction and before ending the phase.
5. Start the next phase in a fresh Kilo session.

## Overflow recovery

On `ContextOverflowError` or `Compaction exhausted`:

1. Stop the current session; do not retry the same oversized turn.
2. Export or preserve the session log for diagnosis.
3. Write/reconstruct `.kilo/state/CURRENT_HANDOFF.md` from existing artifacts.
4. Identify the largest tool result in `.kilo/artifacts/tool-output/` or logs.
5. Start a fresh session and load only the handoff and required files.
