---
name: bet-orchestrating-workflows
description: Reusable workflow mechanics for bet customizations — delegation flow, routing rules, resume/stop gates, and shared handoff contracts.
user-invocable: false
---

# Bet Orchestrating Workflows

Shared execution mechanics for multi-step betting pipeline workflows.

## Execution Spine

```
LOOP per step in STEP_ORDER:
  1. RUN script → capture exit code + AGENT_SUMMARY
  2. DELEGATE to specialist (routing table below)
  3. RECEIVE verdict (APPROVED/FLAGGED/REJECTED)
  4. IF REJECTED and retries < 2: fix → re-run → re-delegate
  5. UPDATE state.advance(step, summary)
  6. PRESENT verdict to user (3-5 lines)
  7. ADVANCE to next step
```

## Routing Matrix

| Step | Specialist | Focus |
|------|-----------|-------|
| S0 | bet-settler | PnL, learning signals |
| S1/S1e | bet-scanner | Coverage, shortlist quality |
| S2 | bet-scout | Tipster arguments, consensus |
| S2.3-S2.9 | bet-enricher | Data quality, S3 readiness |
| S3 | bet-statistician | Edge validation, safety scores |
| S4 | bet-valuator | EV, drift, Kelly |
| S5/S6/S7 | bet-challenger | Bear cases, gate verdicts |
| S8 | bet-builder | Coupon validation, correlation |
| DB error | bet-db-analyst | Diagnosis + repair |

## Resume Protocol

1. Load `PipelineState.load(today)` → read `current_step`
2. If step output exists from today → skip to next
3. If no state file → fresh start from S0/S1

## Stop Gates

| Condition | Action |
|-----------|--------|
| Drawdown ≥ 20% | STOP, consult user |
| S2 returns 0 tips | Web search fallback, then continue |
| S3 < 20 analyses | Verify shortlist file, re-run |
| S7 < 5 approved | Re-run without --strict |
| 2 consecutive failures same step | Skip, log, continue |

## Delegation Payload

```json
{
  "step": "S3",
  "date": "2026-05-30",
  "exit_code": 0,
  "summary": {"total": 45, "with_data": 32},
  "request": "Assess output quality and return verdict."
}
```

## State Persistence

Pipeline state lives in `betting/data/{date}_state.json` via `bet.pipeline.PipelineState`.
- `state.advance(step, summary)` after each successful script
- `state.can_proceed(next_step)` before running next script
- Orchestrator reads state on activation to know position

## Rules

- Skipping delegation = FAILED SESSION
- Never skip S2 (tipster = core value)
- Statistical markets before outcome markets
- All commands use `.venv/bin/python3`
- Fish shell only (no bash syntax)
