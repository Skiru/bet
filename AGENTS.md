# Betting Pipeline and Engineering — Hybrid Production Agent Contract

## Model routing

- `code-gpt54`: **OpenAI – ChatGPT Plus/Pro**, model `openai-codex/gpt-5.4`, reasoning effort `medium`. Use for difficult architecture, large refactors, complex debugging, migrations, security-sensitive implementation, and final review.
- `code-local`: Rapid-MLX local Qwen (`openai-compatible/qwen36-local-35b`). Use for routine/private coding, repository exploration, bounded fixes, summaries, and low-cost iterations.
- `bet-orchestrator` and all `bet-*` specialists always use the local Qwen profile unless the user explicitly approves a model-routing change.
- Never use `gpt-5.4-codex`; the ChatGPT subscription provider model ID is `gpt-5.4`.
- Do not define OpenAI API keys in project files. ChatGPT Plus/Pro authentication is OAuth-managed by Kilo.

## Execution rules

1. Never run more than one request against the local Rapid-MLX server at once.
2. Local Qwen agents issue exactly one tool call per assistant turn and wait for the result.
3. `code-gpt54` may group independent read-only operations, but mutations and delegated tasks remain sequential.
4. A primary agent delegates matching specialist work instead of imitating a specialist. Subagents never delegate recursively.
5. Maximum two attempts for the same failing operation; then change strategy or delegate.
6. Never claim success without a concrete diff, artifact, query result, test result, or current cited source.
7. Inspect the current diff before and after edits. Do not overwrite unrelated user changes.

## Engineering workflow

For non-trivial coding, use this sequence:

1. inspect the exact task and repository state;
2. delegate bounded discovery to `repo-explorer-local` when useful;
3. write an acceptance checklist and smallest reversible implementation plan;
4. implement through `code-gpt54` for heavy work or `code-local` for bounded work;
5. run focused tests through `test-runner-local`;
6. request adversarial review from `code-reviewer-local`;
7. repair only verified findings and rerun focused tests;
8. summarize changed files, commands, evidence, remaining risks, and rollback.

Do not use Playwright from local Qwen agents. Browser automation is available only in the GPT profile and requires approval. Context7 is for library/framework documentation. Brave is for current public information.

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
- All picks remain conditional until the user verifies the exact market and odds in Betclic.

## Repository and command safety

- Never read, echo, log, commit, or copy credentials, `.env` values, tokens, cookies, private keys, or OAuth state.
- Never use `sudo`, destructive recursive deletion, `git reset --hard`, `git clean`, force push, or unreviewed database mutation.
- A repair is the smallest reversible change and includes a focused regression test.
- Bash scripts with a Bash shebang may be launched from Fish.
