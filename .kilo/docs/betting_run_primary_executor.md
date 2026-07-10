# Betting Run Primary Executor & Control-Plane Hardening Protocol

## Core Mandates

- For live/full-day betting sessions, select `bet-executor` or the built-in `Code` or `General` agent with Bash.
- Never select legacy orchestrators as the primary shell executor for script phases.
- If the selected primary agent has no Bash, stop immediately with `WRONG_KILO_AGENT_MODE_NO_BASH`.
- Use the same session and same worktree for bounded continuation of a betting run.
- Use a new session in the same worktree only when the UI/session step limit is hit.
- Use a new worktree ONLY for code reviews, patches, and repairs, NOT for continuing an active betting run.
- When executing piped shell commands in Fish shell, use fish `$pipestatus` (e.g. `(pipestatus)`) instead of `$status` to catch failures. For example: `python script.py | tee log.txt; and set pipe_status $pipestatus` to properly handle and verify command success or failure.

## Target Architecture

1. **Primary Executor:** `bet-executor` (or Code/General with Bash)
   - Executes canonical pipeline scripts via `scripts/pipeline_steps/run_daily_pipeline.py`.
   - Captures logs, exits codes, and checks git tree cleanliness.
   - Does not perform specialist analysis.

2. **Consolidated Power Agent Set:**
   - **`bet-researcher`**: Consolidates event discovery, tipster consensus, and source reconciliation.
   - **`bet-modeler`**: Consolidates statistical probabilities, fair odds valuations, EV, and Kelly stake sizing.
   - **`bet-risk-gatekeeper`**: Consolidates weather/injury/travel context, repeats portfolio guarding, and human gates.
   - **`bet-builder`**: Consolidates same-game and same-day correlations, coupon building, and quote cards.
   - **`bet-auditor`**: Consolidates verification-only independent checks, database audits, and continuation validation.
   - **`bet-settler-postevent`**: Consolidates historical settlement, result accounting, and post-match learning.
