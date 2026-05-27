# Session State

> Updated by orchestrator after EVERY major step. Read by ALL agents before analysis.
> On first run (when empty): agents proceed with full context load — no resumption needed.
> Format: orchestrator writes date, phase, last_step, key_metrics, blockers after each delegation.

## Current Session
- **Date:** (not started)
- **Phase:** (not started)
- **Last Step:** (none)
- **Key Metrics:** (none)
- **Blockers:** (none)

## Previous Step Summary
(empty — populated during pipeline run)

## Active Flags
(none)

## Recovery Instructions
If resuming after interruption:
1. Read this file to determine last completed step
2. Verify DB state: `SELECT COUNT(*) FROM analysis_results WHERE betting_date = date('now')`
3. Skip already-completed steps (check for output files/DB entries)
4. Resume from next uncompleted step
