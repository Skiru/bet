# Handoff Checkpoint: Pipeline Improvements from 2026-09-12 Settlement

- **Date:** 2026-09-13
- **Branch:** `main`
- **HEAD:** `c33eef70`
- **RUN_ID:** `simple_stats-2026-09-12-T040901Z-b75383cd`
- **Status:** READY FOR IMPLEMENTATION

---

## 1. Context & Completed Discovery

All 2026-09-12 fixtures (1,472 total, 196 fully covered by bzzoiro match stats and player box scores) were settled across all 203,017 candidate rows:
- **`p_low` Calibration Confirmed:** Across 25,147 decided bets with `p_low >= 0.50`, hit rate was **92.09%** (`p_low` 0.50–0.60 hit 90.47%, `p_low` >= 0.70 hit 95.27%).
- **Recorded Coupon Settle:** 29 settled singles: **23 WON, 6 LOST (79.31% hit rate, +9.59% ROI)**.
- **Bet Builder:** Columbus Crew v New York Red Bulls (shots on target under 6.5 + 2H goals under 2.5) **WON 100%**.
- **Root Cause of Losses & Noise:**
  1. 11 unmapped minor league singles leaked onto the coupon due to `_enrich_fallback_metrics` hardcoding synthetic numbers (8–12 corners).
  2. `red_cards_total 0.5 UNDER` is a negative EV fat-tail trap (-8.56% ROI).
  3. OVER lines on totals (`goals_total`, `corners_total`) hit 82.2% vs 93.3% on UNDERs; small samples (n=8 on Auxerre) failed.
  4. Lower odds bands (1.20–1.35) were negative ROI due to bookmaker margin, whereas 1.35–1.50 printed +19.31% ROI.
  5. Bet Builder leg settle in `backtest_slate.py` used `subject` instead of `team_name`.

---

## 2. Two-Iteration Engineering Architecture

### Iteration 1 (Naive Implementation & Vulnerability Audit)
- **Point 1 (Fallback removal):** Naive check `if "fallback" in row.sources: continue` in `coupons.py` leaves empty/corrupted rows in `event_dossiers.json` and `stats_sheet.json`.
  * *Audit Finding:* Must eliminate fallback injection in `enrich.py` entirely, keep `readiness="BLOCKED"`, and keep defensive gates in `coupons.py` (`synthetic_fallback_rejected`).
- **Point 2 (Red cards exclusion):** Naive filter only on `red_cards_total` misses `red_cards_1h_total`, `red_cards_2h_total`, and `red_cards_for`.
  * *Audit Finding:* Define `UNPRICEABLE_MARKET_FAMILIES = frozenset({"red_cards_total", "red_cards_1h_total", "red_cards_2h_total", "red_cards_for"})` and exclude via `unpriceable_market_family`.
- **Point 3 (OVER vs UNDER thresholds):** Naive `min_p_low = 0.58 if OVER else 0.50` alone does not stop small sample variance ($n=8$).
  * *Audit Finding:* Couple `min_p_low = 0.58` with minimum sample size $n \ge 12$ for OVER totals (`goals_total`, `corners_total`, `fouls_total`).
- **Point 4 (Price band & floor):** Naive increase of `--min-odds-floor` to 1.25 in CLI does not update default in `build_coupons.py` and `coupons.py`.
  * *Audit Finding:* Set `min_odds_floor = 1.25` default in `build_coupons.py`, and increase rung score weight for `price_band == "1.35-1.60"`.
- **Point 5 (Bet Builder leg team mapping):** In `backtest_slate.py`, `settle_slips`: `team_name = getattr(leg, "team_name", None) or getattr(leg, "subject", None)`.

### Iteration 2 (Production Refinement)
Full specification ready to execute in code across:
1. `src/bet/simple_stats/enrich.py`
2. `src/bet/simple_stats/coupons.py`
3. `scripts/simple/build_coupons.py`
4. `scripts/simple/backtest_slate.py`
5. Unit and regression tests in `tests/simple_stats/`.
