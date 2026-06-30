# Unpriced Bet Builder E2E Gap Review

This document summarizes the gap analysis of the unpriced Bet Builder candidate flow across the end-to-end analytical pipeline.

## E2E Gap Analysis Answers

### 1. Where do unpriced candidates originate?
Unpriced candidates originate from upstream data discovery and stats-compilation phases (S1, S2, and S3). They represent highly attractive fixtures/selections where no initial odds are available from standard providers, or are intended for custom same-match Bet Builder placement at bookmakers like Superbet.

### 2. Whether S4 emits them?
Yes, S4 (`s4_valuator.py` via `odds_evaluator.py`) does not fail or halt when encountering candidates without provider odds. Instead, it classifies them as having `NO_ODDS` / `INSUFFICIENT_DATA`, bypasses EV and drift calculation, and successfully writes them out to the S4 candidate JSON.

### 3. Whether S5/pre-S7 drops them?
Yes, historically `s5_gate.py` (which runs `build_pre_s7_universe` from `live_session_universe.py`) would mark any candidate with `odds_decimal <= 1.0` as `REJECTED_MISSING_ODDS`. When valid candidate count fell below 8, the entire step halted with `BLOCKED_INSUFFICIENT_CANDIDATE_UNIVERSE`. While a previous change bypassed setting `is_valid = False` for missing odds, it incorrectly mixed them into the main valid candidates pool, which is semantically dangerous.

### 4. Whether they enter a separate analytical queue?
Currently, no. Unpriced candidates do not enter a distinct, first-class analytical review queue. They are either rejected/dropped entirely, or mixed into the main priced valid candidate list, affecting the `READY_FOR_S7` count.

### 5. Whether analytical-only packages are separated from placement-ready packages?
No. There is no clear segregation. An analytical-only package is not cleanly separated from a placement-ready package, and the pipeline can treat an analytical-only package as a coupon package ready for execution, which violates core safety principles.

### 6. Whether `ready_for_manual_session` is ambiguous?
Yes, `ready_for_manual_session` is highly ambiguous and dangerous. It is marked `True` when either `bettable_count > 0` OR `analytical_count > 0` (and no global config blockers are active). This means a session is marked "ready" for manual placement execution even when only unpriced analytical suggestions exist, posing an accidental placement risk.

### 7. Whether manual quote above min acceptable can bypass evidence/correlation readiness?
Yes, currently any entered manual quote above the `min_acceptable_operator_odds` threshold immediately promotes the candidate to `BETTABLE_MANUAL_ONLY`. It bypasses separate evidence completeness checks and correlation/same-match risk evaluations.
