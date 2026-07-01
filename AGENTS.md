# Betting Pipeline and Engineering — Hybrid Production Agent Contract

## Model routing

- The active model selected in Kilo UI is the source of truth for the current session.
- `code-gpt54` is a historical compatibility label. Do not treat it as a permanent Gemini-only policy anchor in repository contracts.
- `code-local` remains the local Rapid-MLX Qwen route (`openai-compatible/qwen36-local-35b`) when the user explicitly selects it.
- `bet-orchestrator` must inherit the active Kilo session model selected in the UI.
- Every required `bet-*` subagent must inherit the active parent/orchestrator model unless the user explicitly approves a dedicated override for that task.
- Passing smoke proof requires a launched subagent, a recorded active runtime model, `ProviderModelNotFoundError=false`, no silent fallback, and either `inherited_parent_model=true` or an explicitly user-approved override.
- Do not define provider API keys in project files. Authentication is OAuth-managed by Kilo.

## Execution rules

1. Never run more than one request against the local Rapid-MLX server at once.
2. Local Qwen agents (when used) issue exactly one tool call per assistant turn and wait for the result.
3. The active primary coding model may group independent read-only operations, but mutations and delegated tasks remain sequential.
4. A primary agent delegates matching specialist work instead of imitating a specialist. Subagents never delegate recursively.
5. Maximum two attempts for the same failing operation; then change strategy or delegate.
6. Never claim success without a concrete diff, artifact, query result, test result, or current cited source.
7. Inspect the current diff before and after edits. Do not overwrite unrelated user changes.

## Engineering workflow

For non-trivial coding, use this sequence:

1. inspect the exact task and repository state;
2. delegate bounded discovery to `repo-explorer-local` when useful;
3. write an acceptance checklist and smallest reversible implementation plan;
4. implement through the active coding agent selected in Kilo UI, typically `code-gpt54` for heavier work or `code-local` for bounded/private work;
5. run focused tests through `test-runner-local`;
6. request adversarial review from `code-reviewer-local`;
7. repair only verified findings and rerun focused tests;
8. summarize changed files, commands, evidence, remaining risks, and rollback.

Do not use Playwright from local Qwen agents. Browser automation requires approval. Context7 is for library/framework documentation. Brave is for current public information.

## Session and context discipline

- Start a new session after switching profile, provider, model, primary agent, or betting phase.
- Read only the files required by the current task; do not recursively ingest the whole repository.
- Keep every displayed tool result below **8 KiB** and save verbose output under `.kilo/artifacts/`.
- Local subagent output must stay below **900 tokens**. Betting handoffs must stay below **1,000 tokens**.
- Local automatic compaction is disabled. Save a checkpoint before manual `/compact`; after one compaction failure, continue in a fresh session.

## Evidence and data

- Direct database reads use only `bet_sqlite_query`; never open SQLite through shell, Python, editor, or another MCP tool.
- Database mutations use reviewed repository scripts and focused tests.
- Every factual betting claim traces to a DB row, generated artifact, or current external source with `as_of`.
- Never invent odds, fixtures, teams, markets, injuries, statistics, lineups, consensus, or model outputs.
- Material external facts should use two independent current sources when available; unresolved conflicts invoke `bet-reconciler`.
- `bet-test-engineer` must return `PASS` before a phase completes.
- All picks remain conditional until the user verifies the exact market and a manual human Superbet quote.

## Repository and command safety

- Never read, echo, log, commit, or copy credentials, `.env` values, tokens, cookies, private keys, or OAuth state.
- Never use `sudo`, destructive recursive deletion, `git reset --hard`, `git clean`, force push, or unreviewed database mutation.
- A repair is the smallest reversible change and includes a focused regression test.
- Bash scripts with a Bash shebang may be launched from Fish.
