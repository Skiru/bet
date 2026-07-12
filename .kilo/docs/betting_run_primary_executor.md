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
