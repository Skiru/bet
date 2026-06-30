# Downstream Odds Assumptions & Blockers Code Review

This document reviews how candidates without odds are handled by the pipeline downstream, identifying critical assumptions and blocker points that prevent unpriced Bet Builder candidates from being analyzed.

## Reviewed Components
- `scripts/odds_evaluator.py`
- `scripts/pipeline_steps/s4_valuator.py`
- `scripts/pipeline_steps/s5_gate.py`
- `scripts/pipeline_steps/s7_validate.py`
- `src/bet/pipeline/live_session_universe.py`
- `src/bet/pipeline/daily_manual_session.py`
- `src/bet/pipeline/rich_coupon_package.py`
- `scripts/pipeline_daily_manual_session.py`
- `scripts/pipeline_rich_coupon_package.py`
- `scripts/generate_market_matrix.py`
- `.kilo/artifacts/bet_builder_odds_architecture_guard.md`

---

## Downstream Gap & Blockers Analysis

### 1. Rejected Too Early / Missing Odds Blocker in `live_session_universe.py`
- **Location**: `src/bet/pipeline/live_session_universe.py`, lines 235-238 (in `classify_candidate_quality`).
- **Mechanism**: The quality gate checks if `candidate.odds_decimal <= Decimal("1.0")`. If true, the candidate is marked as invalid (`is_valid = False`) with a verdict of `CandidateQualityVerdict.REJECTED_MISSING_ODDS`.
- **Impact**: Any candidate without provider odds is rejected prior to S7 gate evaluation. If the number of valid candidates falls below `min_candidates` (default 8), the entire S7 pipeline run terminates with `BLOCKED_INSUFFICIENT_CANDIDATE_UNIVERSE`.

### 2. Converted to NO_BET / Missing Odds Blocker in `daily_manual_session.py`
- **Location**: `src/bet/pipeline/daily_manual_session.py`, lines 262-263 (in `review_s8_candidate_for_manual_session`).
- **Mechanism**: If `odds_decimal == ZERO`, it adds a blocker `"missing odds decimal"`. Under lines 314-316, if any blocker exists, the candidate's status is forced to `NO_BET`.
- **Impact**: Candidates without pre-existing provider odds are instantly degraded to `NO_BET` even if they have excellent model probabilities, preventing any human-in-the-loop operator from checking or quoting them in Superbet.

### 3. Lost Between S4/S5/S7/S8/S9
- **S4 Valuator (`s4_valuator.py` / `odds_evaluator.py`)**: S4 does not fail on unpriced candidates, but labels them as `NO_ODDS` / `INSUFFICIENT_DATA` and skips EV computation.
- **S5 Gate (`s5_gate.py` / `gate_checker.py`)**: The 20-point approval gate is resilient to stats-first (unpriced) mode (it allows `STATS-FIRST: EV not calculable` for Gate #8 and skips odds drift/gap checks). However, because S5/S7 gate runs validation wrapper `live_session_universe.py`, any unpriced candidate is dropped from the universe before the gate actually runs.
- **S8 (`daily_manual_session.py`)**: Any candidate with missing odds gets assigned `NO_BET` instead of `PRICE_PENDING_OPERATOR_CHECK`.
- **S9 (`rich_coupon_package.py`)**: Only packages candidates in status `BETTABLE_MANUAL_ONLY`. Since candidates without odds are forced to `NO_BET`, they are completely dropped and never packaged as analytical suggestions.

### 4. Incorrectly Allowed as BETTABLE
- Currently, a candidate can only become `BETTABLE` if it has odds. However, there is no guard preventing fake/invented odds or synthetic odds (such as 1.87 balanced total lines) from being treated as actual/factual bookmaker odds and flagged as `BETTABLE_MANUAL_ONLY` without verified operator quoting.

### 5. Blocked from Analytical Review Even Though Enrichment Exists
- Standard market enrichment (supporting stats, counter stats, trend summaries) is fully resolved during S3/S4, but because of the missing odds block in `live_session_universe.py` and `daily_manual_session.py`, these highly enriched matches never reach the human operator. They are silently lost in the `NO_BET` or rejected pools.
