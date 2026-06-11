---
name: betting-pipeline-runtime
description: Use for running, resuming, validating or repairing any S0-S10 phase of the agent-driven sports betting pipeline.
---

# Betting Pipeline Runtime

## Session partition

- Phase A: S0.
- Phase B: S1-S1e.
- Phase C: S2.
- Phase D: S2.3-S7.
- Phase E: S8-S10.

Do not cross a phase boundary in the same Kilo session. At the boundary, write `.kilo/state/phase-<LETTER>-handoff.md`, update `.kilo/state/CURRENT_HANDOFF.md`, then end the session.

## Per-phase loop

1. Verify prerequisite artifact paths and DB readiness.
2. Run one bounded script/action.
3. Validate exit criteria mechanically.
4. Delegate only the analysis required by that phase.
5. Persist full evidence under `betting/` or `.kilo/artifacts/`.
6. Return only a compact decision record.

## Failure handling

- Retry the same operation at most twice.
- On a third failure, change strategy or delegate to `bet-engineer`.
- Never repeat a large web/browser/tool response in chat.
- S2 with zero valid tips is a hard stop requiring user input.
