---
agent: "bet-statistician"
description: "S3B autonomous prompt for late-breaking verification before placement."
---

# S3B — Time-Sensitive Recheck

This prompt is intentionally more than a thin router because it owns the late-breaking recheck flow close to placement time. Reusable routing and stop gates still live in `bet-orchestrating-workflows`.

## Orchestrator Must Provide
- the affected candidate set and current preferred markets
- latest injury, lineup, weather, drift, or start-time changes
- the prior S3/S4/S5 verdicts that may need to be updated
- the betting day and cutoff window

## Recheck Sequence
1. Re-verify whether the original edge mechanism still holds.
2. Refresh only the time-sensitive facts that changed the thesis.
3. Decide keep, downgrade, move to extended pool, or escalate.
4. Return only the minimal changes needed for the final build.

## Output Contract
Return the structured verdict required by `agent-execution-protocol.instructions.md` plus:
- changed picks and the reason they changed
- any hard stop conditions for placement
- next-step readiness for the builder or final validation

## Guardrails
- analysis-only; do not run pipeline scripts
- write only short time-sensitive observations to `/memories/session/` when they are reusable

<!-- BET:internal-prompt:bet-time-sensitive:v2 -->
