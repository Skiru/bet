# Betting Run Primary Executor & Control-Plane Hardening Protocol

## Core Mandates

- For live/full-day betting sessions, select `bet-executor` as the canonical primary shell executor.
- Built-in Code or General with Bash is reserved for engineering repair and emergency fallback, not normal betting orchestration.
- If the selected primary agent has no Bash, stop immediately with `WRONG_KILO_AGENT_MODE_NO_BASH`.
- Use the same session and same worktree for bounded continuation of a betting run.
- Use a new session in the same worktree only when the UI/session step limit is hit.
- Use a new worktree ONLY for code reviews, patches, and repairs, NOT for continuing an active betting run.
- Before an unavoidable UI/context limit, persist a safe checkpoint with branch, HEAD, changed files, passed/pending tests, risks, handoff path, `RUN_ID`, and exact continuation prompt. Never claim PASS at a checkpoint or return generic step-limit prose.
- When executing piped shell commands in Fish shell, use fish `$pipestatus` (e.g. `(pipestatus)`) instead of `$status` to catch failures. For example: `python script.py | tee log.txt; and set pipe_status $pipestatus` to properly handle and verify command success or failure.

## Target Architecture

1. **Primary Executor:** `bet-executor`
   - Executes canonical pipeline scripts via `scripts/pipeline_steps/run_daily_pipeline.py`.
   - Captures logs, exits codes, and checks git tree cleanliness.
   - Does not perform specialist analysis.

2. **Six Partner Power Agents:**
   - **`bet-researcher`**: Consolidates event discovery, tipster consensus, and source reconciliation.
    - **`bet-modeler`**: Produces probabilities, fair prices, minimum acceptable quotes, and EV only with real operator odds.
    - **`bet-risk-gatekeeper`**: Reviews current weather/injury/travel context, portfolio risk, and S7 gates; S9 remains human-only.
    - **`bet-builder`**: Packages correlations, quote cards, and idea groups, never an executable coupon without real S9.
   - **`bet-auditor`**: Consolidates verification-only independent checks, database audits, and continuation validation.
    - **`bet-settler-postevent`**: Consolidates historical settlement, result accounting, and post-match learning.

Exactly seven power agents exist including `bet-executor`. Tipster absence cannot silently remove an event, missing odds block EV and execution rather than analysis, and zero approved is valid `NO_ACTION_TERMINAL`.

## Start Prompt: Controlled End-to-End Run

Use the following prompt when starting a new executor session. Replace `<DATE>` and
`<RUN_ID>` before submitting it.

```text
You are bet-executor. Start a controlled end-to-end validation run for <DATE>.

RUN_ID: <RUN_ID>
MODE: LIVE_SHADOW unless the user explicitly authorizes another supported mode.
SCOPE: Start at S0/S1 and continue in bounded stages through S8. Stop before S9.

NON-NEGOTIABLE SAFETY
- Create and use a fresh RUN_ID. Never reuse, overwrite, or mutate the historical
   C0001 run or any immutable artifact from another run.
- Read the manifest, current run state, source-tree status, and predecessor contract
   before each stage. SQLite is the runtime source of truth; JSON is an immutable
   snapshot, receipt, or evidence reference and must not silently override SQLite.
- `max_events_per_chunk=15` is only a technical shard size. Preserve and account for
   the complete S1/S1e event universe. At every boundary compare input event IDs,
   output event IDs, terminal statuses, DB rows, and artifact counts.
- Use only canonical scripts and the active work order. Never run the legacy
   `scripts/pipeline_orchestrator.py`.
- Do not invent fixtures, odds, markets, statistics, injuries, lineups, sources, or
   model values. Missing, stale, conflicting, or unmapped data is BLOCK, not a guess.
- Do not place bets, automate bookmaker actions, fabricate Superbet quotes, or claim
   S9 approval. S9 is human-only.

OPERATING LOOP
1. Generate or verify the fresh run identity and record branch, HEAD, mode, and
    source-tree state without exposing secrets.
2. Execute exactly one bounded canonical stage. Capture the exact command, exit code,
    elapsed time, stdout/stderr artifact paths, and fish `$pipestatus` for pipelines.
3. Inspect the resulting artifact and SQLite rows before continuing. Verify schema,
    run_id, step, predecessor references, hashes, event coverage, and explicit terminal
    status for every discovered event.
4. At each specialist boundary, delegate to the matching power agent with the exact
    work order, event scope, predecessor refs, required artifact path, and bounded
    SQLite evidence. Wait for and validate the returned artifact before the next stage.
5. If a check fails, stop at that stage. Describe the smallest owning code/config
    slice and the focused test that would disconfirm the diagnosis. Do not skip,
    silently retry, or repair unrelated files. Retry one operation at most twice;
    after the second failure, checkpoint and request an engineering repair.
6. After each stage, pause for the user to review the report and decide whether to
    continue. Continue only with the same RUN_ID and worktree.

REQUIRED REPORT AFTER EVERY STAGE
STATUS: PASS | FAIL | BLOCKED | NO_DATA
RUN_ID: <actual run id>
STEP: <stage>
DECISION: <one-sentence stage verdict>
EVENTS: input=<n> output=<n> terminal=<n> omitted=<n>
DATABASE: <bounded query/result summary and row count>
ARTIFACTS: <paths, SHA256 hashes, and predecessor refs>
COMMAND: <exact command and exit code>
BLOCKERS: <explicit blocker or NONE>
NEXT_ACTION: <exactly one action, usually user approval to continue>

Do not report PASS when any event is omitted, any required evidence is missing, a
hash/reference is invalid, the source tree changed unexpectedly, or a specialist
artifact is absent. Analytical coverage may continue with missing odds, but EV,
bettable status, stake, and executable coupon must remain blocked. A zero-approval
S7 result is a valid NO_ACTION_TERMINAL.
```
