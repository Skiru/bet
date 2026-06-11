# Routing Matrix — Orchestrator Mode Delegation

## Mode → Responsibility → When to Use

| Mode Slug | Specialist For | Delegate When |
|-----------|---------------|---------------|
| bet-settler | Settlement + learning | S0 output needs PnL validation, bankroll impact, learning extraction |
| bet-scanner | Scan + shortlist | S1 (STEP 3) discovery output + S1e (STEP 7) shortlist needs coverage assessment, fixture verification |
| bet-scout | Tipster intelligence | S2 output (tipster_xref.py STEP 8) needs argument quality assessment, consensus evaluation |
| bet-enricher | Data quality | S2.3-S2.9 output needs readiness assessment for S3 |
| bet-statistician | Deep stats | S3/S3B output needs market ranking validation, safety scores |
| bet-valuator | Odds + EV | S4 output needs fair-odds evaluation, drift detection |
| bet-challenger | Gate + context | S5-S7 output needs upset risk, bear cases, final judgment |
| bet-builder | Coupons + artifacts | S8 output needs portfolio review, correlation check |
| bet-db-analyst | DB readiness | Pre-flight DB audit, table freshness, coverage gaps |
| bet-engineer | Script repair + infra | Any script failure after 2 retries — diagnose, fix, re-run |

## Handoff Contract (what to include in task message)
1. **Script output path** — so specialist can read the full output
2. **Key metrics extracted** — top 3-5 numbers from the run
3. **Specific questions** — what the orchestrator needs answered
4. **Context payload** — date, shortlist count, sport breakdown
5. **Expected verdict format** — APPROVED/FLAGGED/REJECTED + metrics

## Quality Gate for Verdicts (3 questions)
1. Does the verdict contain ≥3 specific metrics with real numbers?
2. Does it contain ORIGINAL ANALYSIS (not just restated script output)?
3. Is the recommended next action clearly justified?

If ANY = NO → request re-analysis with more specific questions.
