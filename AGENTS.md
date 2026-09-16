# Betting Pipeline and Engineering — Agent Contract

## Model routing

- No agent pins a model. `bet-simple` and every subagent it delegates to
  (`bet-analyst-football`, `bet-analyst-tennis`, `bet-analyst-baseball`,
  `superbet-market-matcher`, `tipster-reader`) inherit whatever model is active
  in the Kilo session that launched them. Explicit per-agent model pins are
  forbidden — pick the model in the Kilo UI (or pass `--model`) before running
  a day.
- Vertex project `project-1b366b53-dab2-429b-80e`, region `europe-west1`.
  `location: "eu"` is not a valid Vertex region and silently breaks every
  call; `global` works but is 10-20x slower. The configured catalog
  (`gemini-2.5-flash-lite` / `gemini-2.5-flash` / `gemini-2.5-pro`, standard
  tier — flex is not enabled for this project) is what's actually available
  regionally; the newer 3.x Gemini family is global-only on this project and
  is not configured here.
- Passing smoke proof requires a launched agent, a recorded active runtime
  model, `ProviderModelNotFoundError=false`, and no silent fallback.
- Do not define provider API keys in project files. Authentication is
  OAuth-managed by Kilo; the `bzzoiro` MCP token is the one project-specific
  exception (`.bzzoiro_token`, referenced from `kilo.json`, never committed).

## Default betting day: `bet-simple`

**`bet-simple` (primary) is the canonical executor for a betting day.** It
drives `scripts/simple/run_pipeline.py`:

```bash
python3 scripts/simple/run_pipeline.py --date <YYYY-MM-DD> -v
```

Real stage order: `DISCOVER -> SUPERBET -> ENRICH -> {MARKET_CONTEXT,
TIPSTERS} -> ANALYZE`, then two ANALYZE tails (the Superbet comparison and
FORECAST) — one `run_id` across all of it, provider preflight before any
spend, one `AGENT_SUMMARY:` line, artifacts and a run receipt under
`runs/<date>/`.

`bet-simple` delegates sport analysis via the `task` tool to
`bet-analyst-football` / `bet-analyst-tennis` / `bet-analyst-baseball`,
reads tipster picks through `tipster-reader`, and gets market-matching and
pricing detail from `superbet-market-matcher`. It merges their vetoes and
**builds a priced coupon** (singles + Bet Builder slips) — this pipeline
does produce EV/price/stake-relevant output, not just a stats sheet.

Deliverables, in order of importance:
1. `runs/<date>/<date>_kupony.md` — the coupon file.
2. `runs/<date>/<date>_analiza.md` — the per-match reasoning behind it.

The human checkpoint is real but comes *after* the coupon, not instead of
one: every row is conditional until the operator verifies the exact market
and price live at Superbet before staking. A generated coupon row is not an
executed bet.

Morning procedure: `docs/MORNING.md`.
Contract: `.kilo/skills/simple-stats-runtime/SKILL.md`.
Operations: `docs/SIMPLE_STATS_RUNBOOK.md`.
Day-to-day commands: `/run-day` (full unattended run), `/rebuild-coupon`
(rebuild the coupon from artifacts already on disk, no new DISCOVER/ENRICH).

## Execution rules

1. The active primary coding model may group independent read-only operations, but mutations and delegated tasks remain sequential.
2. A primary agent delegates matching specialist work instead of imitating a specialist. Subagents never delegate recursively.
3. Maximum two attempts for the same failing operation; then change strategy.
4. Never claim success without a concrete diff, artifact, query result, test result, or current cited source.
5. Inspect the current diff before and after edits. Do not overwrite unrelated user changes.

## Engineering workflow

For non-trivial coding, use this sequence:

1. inspect the exact task and repository state;
2. delegate bounded discovery to the built-in `explore` agent when useful;
3. write an acceptance checklist and smallest reversible implementation plan;
4. implement through the active coding agent selected in Kilo UI;
5. run focused tests directly (no dedicated test-runner subagent is configured);
6. request adversarial review directly, or via `/code-review` (no dedicated reviewer subagent is configured);
7. repair only verified findings and rerun focused tests;
8. summarize changed files, commands, evidence, remaining risks, and rollback.

Context7 is for library/framework documentation. `webfetch` (fetch a known
URL) works for every agent, including subagents. **`websearch` does not** —
confirmed 2026-09-16: it only works for Kilo's built-in agents (`ask`,
`code`, ...); any custom agent defined under `.kilo/agent/*.md` gets
`Invalid Tool` regardless of its permission grant. `bet-analyst-football`
verifies through bzzoiro MCP by id; `bet-analyst-tennis` fetches known
domains directly (`atptour.com` / `wtatennis.com` / `tennisabstract.com` —
see the `tennis-analysis` skill); `bet-analyst-baseball` has no such
fixed-domain fallback documented and is the most exposed to this limit.
Don't grant `websearch` to a custom agent expecting it to work.

## Session and context discipline

- Start a new session after switching profile, provider, model, or primary agent. A betting run may continue across bounded phases in the same session, worktree, and `RUN_ID`.
- Read only the files required by the current task; do not recursively ingest the whole repository.
- Keep every displayed tool result below **8 KiB** and save verbose output under `.kilo/artifacts/`.
- Local subagent output must stay below **900 tokens**. Betting handoffs must stay below **1,000 tokens**.
- Local automatic compaction is disabled. Save a checkpoint before manual `/compact`; after one compaction failure, continue in a fresh session.
- Before an unavoidable UI/context limit, finish the current atomic operation and persist a safe checkpoint with branch, HEAD, changed files, completed phases, passed and pending tests, risks, handoff path, `RUN_ID`, and exact continuation prompt. A checkpoint never claims PASS or uses generic step-limit prose.

## Evidence and data

- Raw SQLite files under `betting/data/*.db*` are excluded from Kilo's own
  read/edit permissions — that block is enforced by Kilo itself, not by a
  project config file. Don't route around it (shelling into the file,
  copying it out, etc.). Database mutations use reviewed repository scripts
  and focused tests.
- Every factual betting claim traces to a DB row, generated artifact, or current external source with `as_of`.
- Never invent odds, fixtures, teams, markets, injuries, statistics, lineups, consensus, or model outputs.
- Material external facts should use two independent current sources when available. There is no dedicated researcher/auditor agent in the current design — `bet-analyst-football`/`-tennis`/`-baseball` and `superbet-market-matcher` carry this responsibility directly, through the veto list `bet-simple` merges before building the coupon.
- All picks remain conditional until the user verifies the exact market and a manual human Superbet quote. A generated coupon row is a candidate, not a placed bet.
- Tipster absence must be labeled and cannot silently remove an event or block core analysis. Every discovered event requires an explicit terminal status or reason.
- Missing odds do not block analytical coverage, but they block EV, bettable status, Kelly/stake recommendations, and an executable final coupon.

## Repository and command safety

- Never read, echo, log, commit, or copy credentials, `.env` values, tokens, cookies, private keys, or OAuth state.
- Never use `sudo`, destructive recursive deletion, `git reset --hard`, `git clean`, force push, or unreviewed database mutation.
- A repair is the smallest reversible change and includes a focused regression test.
- Bash scripts with a Bash shebang may be launched from Fish.

## Betting run primary executor

- For live/full-day betting sessions, select `bet-simple` as the canonical primary executor. Built-in Code or General with Bash is an emergency fallback and engineering repair path, not the normal betting orchestrator.
- If the selected primary agent has no Bash, stop immediately with `WRONG_KILO_AGENT_MODE_NO_BASH`.
- Use the same session and same worktree for bounded continuation of a betting run.
- Use a new session in the same worktree only when the UI/session step limit is hit.
- Use a new worktree ONLY for code reviews, patches, and repairs, NOT for continuing an active betting run.
- When executing piped shell commands in Fish shell, use fish `$pipestatus` (e.g. `(pipestatus)`) instead of `$status` to catch failures. For example: `python script.py | tee log.txt; and set pipe_status $pipestatus` to properly handle and verify command success or failure.
