# Betting Pipeline and Engineering — Consolidated Power Agent Contract

## Model routing

- The active model selected in Kilo UI is the source of truth for the current session.
- All production betting agents inherit the active Kilo UI model from the parent session. Explicit per-agent model pins are strictly forbidden in production agents.
- Passing smoke proof requires a launched agent, a recorded active runtime model, `ProviderModelNotFoundError=false`, and no silent fallback.
- Do not define provider API keys in project files. Authentication is OAuth-managed by Kilo.

## Active Power Agent Architecture

Only seven high-performing production power agents exist in the active betting architecture:

1. **`bet-executor` (Primary Mode):** Bounded betting pipeline executor. Runs canonical pipeline scripts (e.g., `scripts/pipeline_steps/run_daily_pipeline.py`), captures logs and fish `$pipestatus` codes, checks git tree cleanliness, and enforces gates. Business agents cannot run shell.
2. **`bet-researcher` (Subagent Mode):** Shell-less domain specialist for discovery, tipsters aggregation, gap detection, enrichment, and fact reconciliation. Handles facts and factual conflicts.
3. **`bet-modeler` (Subagent Mode):** Shell-less domain specialist for S3 probabilities and S4 fair pricing, minimum acceptable quotes, and EV only after real operator odds exist.
4. **`bet-risk-gatekeeper` (Subagent Mode):** Shell-less domain specialist for S5 context, S6 portfolio risk, and S7 hard approval gates. Handles risk conflicts but never impersonates the human S9 operator.
5. **`bet-builder` (Subagent Mode):** Shell-less domain specialist for S8 quote packs, Bet Builder idea groups, and correlation warnings. It does not create an executable coupon.
6. **`bet-auditor` (Subagent Mode):** Verification-only specialist for independent checks, database integrity audits, and S7b validation. May use bash for running target verification tests only. Never mutates or repairs. Performs final verification.
7. **`bet-settler-postevent` (Subagent Mode):** Consolidated historical settlement and learning specialist for S10 (post-event accounting).

All old legacy micro-agents and orchestrators have been removed. `bet-executor` is the normal full-day betting primary. Technical engineering repairs and emergency fallback use built-in Code or General in a fresh worktree and are not handled by any betting agent.

## Execution rules

1. Never run more than one request against the local Rapid-MLX server at once.
2. The active primary coding model may group independent read-only operations, but mutations and delegated tasks remain sequential.
3. A primary agent delegates matching specialist work instead of imitating a specialist. Subagents never delegate recursively.
4. Maximum two attempts for the same failing operation; then change strategy.
5. Never claim success without a concrete diff, artifact, query result, test result, or current cited source.
6. Inspect the current diff before and after edits. Do not overwrite unrelated user changes.

## Engineering workflow

For non-trivial coding, use this sequence:

1. inspect the exact task and repository state;
2. delegate bounded discovery to `repo-explorer-local` when useful;
3. write an acceptance checklist and smallest reversible implementation plan;
4. implement through the active coding agent selected in Kilo UI;
5. run focused tests through `test-runner-local`;
6. request adversarial review from `code-reviewer-local`;
7. repair only verified findings and rerun focused tests;
8. summarize changed files, commands, evidence, remaining risks, and rollback.

Do not use Playwright from local agents. Browser automation requires approval. Context7 is for library/framework documentation. Brave is for current public information.

## Session and context discipline

- Start a new session after switching profile, provider, model, or primary agent. A betting run may continue across bounded phases in the same session, worktree, and `RUN_ID`.
- Read only the files required by the current task; do not recursively ingest the whole repository.
- Keep every displayed tool result below **8 KiB** and save verbose output under `.kilo/artifacts/`.
- Local subagent output must stay below **900 tokens**. Betting handoffs must stay below **1,000 tokens**.
- Local automatic compaction is disabled. Save a checkpoint before manual `/compact`; after one compaction failure, continue in a fresh session.
- Before an unavoidable UI/context limit, finish the current atomic operation and persist a safe checkpoint with branch, HEAD, changed files, completed phases, passed and pending tests, risks, handoff path, `RUN_ID`, and exact continuation prompt. A checkpoint never claims PASS or uses generic step-limit prose.

## Evidence and data

- Direct database reads use only `bet_sqlite_query`; never open SQLite through shell, Python, editor, or another MCP tool.
- Database mutations use reviewed repository scripts and focused tests.
- Every factual betting claim traces to a DB row, generated artifact, or current external source with `as_of`.
- Never invent odds, fixtures, teams, markets, injuries, statistics, lineups, consensus, or model outputs.
- Material external facts should use two independent current sources when available; factual conflicts are handled by `bet-researcher` while risk conflicts are handled by `bet-risk-gatekeeper`.
- `bet-auditor` performs final verification and must return `PASS` before S8 completes.
- All picks remain conditional until the user verifies the exact market and a manual human Superbet quote.
- Tipster absence must be labeled and cannot silently remove an event or block core analysis. Every discovered event requires an explicit terminal status or reason.
- Missing odds do not block analytical coverage, but they block EV, bettable status, Kelly/stake recommendations, and an executable final coupon.
- S9 is human-only. Synthetic or agent-generated approval cannot satisfy it, and zero S7 approvals is valid `NO_ACTION_TERMINAL`.

## Repository and command safety

- Never read, echo, log, commit, or copy credentials, `.env` values, tokens, cookies, private keys, or OAuth state.
- Never use `sudo`, destructive recursive deletion, `git reset --hard`, `git clean`, force push, or unreviewed database mutation.
- A repair is the smallest reversible change and includes a focused regression test.
- Bash scripts with a Bash shebang may be launched from Fish.

## Betting Run Primary Executor & Control-Plane Hardening

- For live/full-day betting sessions, select `bet-executor` as the canonical primary executor. Built-in Code or General with Bash is an emergency fallback and engineering repair path, not the normal betting orchestrator.
- Never select legacy orchestrators as the primary shell executor.
- If the selected primary agent has no Bash, stop immediately with `WRONG_KILO_AGENT_MODE_NO_BASH`.
- Use the same session and same worktree for bounded continuation of a betting run.
- Use a new session in the same worktree only when the UI/session step limit is hit.
- Use a new worktree ONLY for code reviews, patches, and repairs, NOT for continuing an active betting run.
- When executing piped shell commands in Fish shell, use fish `$pipestatus` (e.g. `(pipestatus)`) instead of `$status` to catch failures. For example: `python script.py | tee log.txt; and set pipe_status $pipestatus` to properly handle and verify command success or failure.
