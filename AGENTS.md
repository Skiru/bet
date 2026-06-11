# Betting Pipeline and Engineering — Hybrid Production Agent Contract

## Model routing

- `code-gpt54`: **OpenAI – ChatGPT Plus/Pro**, model `openai-codex/gpt-5.4`, reasoning effort `medium`. Use for difficult architecture, large refactors, complex debugging, migrations, security-sensitive implementation, and final review.
- `code-local`: Rapid-MLX local Qwen (`openai-compatible/qwen36-local-35b`). Use for routine/private coding, repository exploration, bounded fixes, summaries, and low-cost iterations.
- `bet-orchestrator` and all `bet-*` specialists always use the local Qwen profile unless the user explicitly approves a model-routing change.
- Never use `gpt-5.4-codex`; the ChatGPT subscription provider model ID is `gpt-5.4`.
- Do not define OpenAI API keys in project files. ChatGPT Plus/Pro authentication is OAuth-managed by Kilo.

## Runtime

- Kilo Code baseline: **7.3.41 stable or newer stable**. Do not deploy a pre-release as the production default.
- Local inference: Rapid-MLX 0.7.0, API model ID `default`, endpoint `http://127.0.0.1:8000/v1`.
- Local Kilo budget: **28,672 context / 24,576 input / 4,096 output** on Apple M4 Pro with 48 GB unified memory.
- Local profile is text-only: no vision, DFlash, MTP, speculative decoding, or concurrent local generations.
- Never print or request private chain-of-thought, `<think>` blocks, hidden scratchpads, or sequential-thinking traces.

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

## Betting phase contract

| Phase | Scope | Mandatory specialists | Exit artifact |
|---|---|---|---|
| A | S0 settlement and historical learning | `bet-settler`, `bet-db-analyst`, `bet-test-engineer` | `.kilo/state/phase-A-handoff.md` |
| B | S1–S1e discovery and shortlist | `bet-scanner`, `bet-test-engineer` | `.kilo/state/phase-B-handoff.md` |
| C | S2 tipster aggregation | `bet-scout`, `bet-test-engineer` | `.kilo/state/phase-C-handoff.md` |
| D | S2.3–S7 enrichment, modelling and gates | `bet-enricher`, `bet-statistician`, `bet-valuator`, `bet-challenger`, `bet-test-engineer` | `.kilo/state/phase-D-handoff.md` |
| E | S8–S10 construction and final validation | `bet-builder`, `bet-test-engineer` | `.kilo/state/phase-E-handoff.md` |

Conflicting evidence goes to `bet-reconciler`. Script/runtime failure after two bounded attempts goes to `bet-engineer`. Zero valid tips in Phase C is a hard stop. Run one phase per session.

## Specialist result schema

Every betting specialist returns only: `STATUS`, `DECISION`, `EVIDENCE`, `CALCULATIONS`, `UNCERTAINTY`, `RISKS`, `NEXT_ACTION`.

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
