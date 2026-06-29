# Bet Builder Lane Routing Audit

**Date:** 2026-06-29  
**Branch:** `feat/live-session-discovery-root-cause-repair-b`  
**HEAD SHA:** `ebc76be5936d80ad53870098a6712648fba8b59b`  
**Verdict:** `LANE_ROUTING_PASS_WITH_REPAIRED_BUGS`

---

## Detailed Audit Questions & Answers

### 1. When `READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW` is returned?
It is returned by `build_pre_s7_universe` in `src/bet/pipeline/live_session_universe.py` when there are fewer than `config.min_candidates` priced valid candidates, but there is at least one unpriced analytical candidate that satisfies `classify_unpriced_analytical_candidate`. This classification requires the candidate to have sport, competition, event, market, pick, line (for O/U), valid model probability ($0 < p < 1$), and non-empty supporting stats.

### 2. Whether S5 proceeds to S7 for analytical-only runs?
**Yes.** Currently, `s5_gate.py` has a checklist:
```python
if report.status not in ("READY_FOR_S7", "READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW"):
```
When S5 runs an analytical-only candidate universe, it does not block here. It continues to run `run_wrapper_scripts_with_evidence`, which invokes `gate_checker.py` (the S7 priced approval gate).

### 3. Whether analytical-only candidates can appear in S7 priced candidate inputs?
**Yes.** S7's priced candidate inputs are resolved from S4 valuation artifacts. Since unpriced candidates are processed by S4 as potential analytical options, they are passed as inputs to S7.

### 4. Whether analytical-only candidates can be counted as S7 approved?
**No.** In `gate_checker.py` (line 1972), candidates without verified real odds are caught by the check:
```python
if not has_real_odds:
    extended_reasons.append("NO_VERIFIED_ODDS: active approval requires a real market price")
```
Thus, they are always routed to the `extended_pool` rather than the `approved` pool. Consequently, `approved_count` for an analytical-only run is always `0`.

### 5. Whether analytical-only packages can be confused with coupon packages?
**No.** `rich_coupon_package.py` differentiates them explicitly. If `bettable_count == 0` and `analytical_count > 0`, it assigns `package_type = "ANALYTICAL_ONLY"`. However, a major confusion exists at the CLI script level: `pipeline_rich_coupon_package.py` checks `package_type != "NO_BET_PACKAGE"` and erroneously prints `STATUS=READY_FOR_HUMAN_REVIEW` for analytical packages instead of routing them to operator quote review.

### 6. Whether `ready_for_manual_placement` can ever be true without a quote/evidence/correlation pass?
**Yes (Critical Bug).** In `daily_manual_session.py`, priced candidates (where `is_unpriced` is False) are directly assigned `review_status = "BETTABLE_MANUAL_ONLY"` without running `evidence_correlation_gate` or checking correlation risk. This allows priced candidates to bypass safety and same-match correlation checks.

---

## Verification and Classification

* **`ANALYTICAL_TO_S7_ROUTING_BUG`**: **VERIFIED BUG.** S5 routes analytical-only candidate runs to the priced `gate_checker.py`, which is designed for priced validation.
* **`ANALYTICAL_APPROVAL_COUNT_BUG`**: **VERIFIED BUG.** Because `gate_checker.py` routes unpriced candidates to `extended_pool`, the approved count is `0`, which causes the S7 step to fail and block downstream S8 from generating the ledger coupon drafts.
* **`PACKAGE_TYPE_CONFUSION_BUG`**: **VERIFIED BUG.** `pipeline_rich_coupon_package.py` prints `STATUS=READY_FOR_HUMAN_REVIEW` for analytical-only packages because they are not "NO_BET_PACKAGE".
* **`READYNESS_FLAG_BUG`**: **VERIFIED BUG.** Priced candidates bypass the evidence/correlation gate in `daily_manual_session.py`.
