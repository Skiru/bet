# DEEP CODE REVIEW — Production Pipeline 2026-05-05

**Scope:** 16 scripts reviewed: `pipeline_orchestrator.py`, `gate_checker.py`, `coupon_builder.py`, `deep_stats_report.py`, `build_shortlist.py`, `validate_coupons.py`, `settle_on_finish.py`, `run_full_scan_and_prepare.sh`, `aggregate_and_select.py`, `normalize_stats.py`, `compute_safety_scores.py`, `validate_s3_output.py`, `discover_fixtures.py`, `tipster_aggregator.py`, `fetch_weather.py`

**Excludes:** 22 bugs already fixed per prior review.

---

## CRITICAL BUGS (must fix before today's run)

### C1. `bankroll_after` excludes combo spend — understates real exposure
**[coupon_builder.py:953]**

```python
"bankroll_after": round(bankroll - core_spend - singles_spend, 2),
```

`combo_spend` is computed on line 934 and included in `total_spend` (line 952), but omitted from `bankroll_after`. If the user places combos, their actual remaining bankroll is lower than displayed. The PODSUMOWANIE table shows a misleadingly high bankroll.

**Fix:** `round(bankroll - core_spend - combo_spend - singles_spend, 2)`

---

### C2. Tennis red flag checks raw odds, not odds ratio — flags virtually every pick
**[gate_checker.py:314]**

```python
if market_best and market_best > 1.50 and "game" in market_name:
    flags.append(f"FLAG: Tennis odds ratio {market_best} > 1.50 for game totals")
```

`market_best` is the bookmaker's decimal odds for the pick (e.g., 1.85), NOT the ratio between favorite/underdog odds. Nearly all game total bets have odds > 1.50, so this flags every tennis game total pick. The message says "odds ratio" but the value is just odds.

**Fix:** Either compute actual odds ratio (fav_odds / dog_odds) from odds data, or remove this check until the ratio can be properly computed.

---

### C3. `--skip-scan` also skips settlement — semantically wrong
**[pipeline_orchestrator.py:246]**

```python
SCAN_STEP_IDS = {"s0_settle", "s1_scan", "s1a_discover", "s1b_parallel", "s1c_aggregate", "s1d_matrix", "s1e_shortlist"}
```

Line 1718: `if skip_scan and step_id in SCAN_STEP_IDS: skip...`. Because `s0_settle` is in `SCAN_STEP_IDS`, `--skip-scan` also skips settlement of the previous day. Settlement is logically independent of scanning.

**Fix:** Remove `"s0_settle"` from `SCAN_STEP_IDS`.

---

## SIGNIFICANT BUGS (should fix)

### S1. Double EV injection — S4 and S7 both call `_inject_ev_from_odds()`
**[pipeline_orchestrator.py:882, 1375]**

`_inject_ev_from_odds()` is called in `_run_odds_eval()` (S4, line 882) and again in `_run_s7()` (line 1375). Both calls operate on candidate dicts. If odds change between S4 and S7, the second call silently overwrites. If they don't change, it's wasted work. Creates confusion about which step owns EV computation.

**Fix:** Remove the S7 call (S4 is the designated odds evaluation step), or remove S4 and keep only S7.

---

### S2. `settle_coupons()` treats any `half_loss` leg as full coupon loss
**[settle_on_finish.py:534-539]**

```python
if "half_loss" in statuses:
    coupon["status"] = "loss"
    coupon["pnl_pln"] = str(round(-stake / 2, 2))
    continue
```

In accumulator betting, a half_loss leg means that leg's effective multiplier is 0.5 (half stake returned). A 3-leg coupon with 2 wins + 1 half_loss is a partial win, not a loss. Current code short-circuits and treats it as a flat loss.

**Fix:** Don't short-circuit. In the effective_odds loop, handle half_loss with `leg_odds = 0.5`.

---

### S3. `settle_pick()` never produces `half_win` / `half_loss` — dead code paths
**[settle_on_finish.py]**

`compute_pnl()` handles `half_win`/`half_loss` (lines 392-395), and `settle_coupons()` checks for them. But `settle_pick()` never sets these statuses — it only sets `"win"`, `"loss"`, or `"push"`. Asian handicap bets (which produce half results) are not handled.

**Impact:** Any Asian handicap bet stays `pending` forever. The half_win/half_loss handling in `settle_coupons` is unreachable dead code.

---

### S4. Volleyball/tennis score validation thresholds too loose
**[settle_on_finish.py:181-183]**

```python
"volleyball": (25, 15),   # max_total, max_single
"tennis": (15, 8),
```

Volleyball set scores: max 3-2 (total=5, max_single=3). Current (25, 15) allows scores like 10-8 to pass validation — these could be point scores from a random page section. Tennis: max 3-2 or 3-0 in best-of-5. Current (15, 8) allows 7-6 (a single set score) to be treated as match result.

**Fix:** `"volleyball": (5, 3)`, `"tennis": (7, 5)`.

---

## GAPS

### G1. No Asian handicap or handicap settlement
**[settle_on_finish.py]**

`settle_pick()` handles ML/1X2, totals, BTTS, double chance. Asian handicaps (AH ±0.25, ±0.75) and European handicaps are not auto-settled. These are common Betclic markets. Handicap bets stay `pending` until manual resolution.

---

### G2. No match date verification in settlement
**[settle_on_finish.py:632-644]**

When polling for results, the script finds scores by team name matching but never checks if the score is from TODAY's match vs. a previous meeting. If Team A plays Team B twice in 48h (baseball doubleheader, tennis rematch), the wrong score could be used.

---

### G3. Generic tipster parser produces noisy false-positive picks
**[tipster_aggregator.py:370-430]**

`parse_generic_tipster_html()` splits HTML by regex looking for "Team A vs Team B" patterns, caps at 200 blocks, but has no confidence threshold. The regex matches navigation elements, article titles, and non-prediction text. Only ZawodTyper has a site-specific parser; the other 10 sites fall through to this generic parser.

---

### G4. No DB rollback on partial coupon persistence failure
**[coupon_builder.py:1407-1460]**

`persist_coupons_to_db()` iterates coupons in a single transaction. If coupon 5/10 fails, the `continue` on line 1453 skips it, but the loop continues. The `conn.commit()` at line 1458 commits the partial set, leaving DB in an inconsistent state.

---

### G5. Validator can't extract leg odds from rich description format
**[validate_coupons.py:38-117 vs coupon_builder.py:1070-1115]**

`parse_coupon_tables()` reads pipe-delimited table rows. But the `_coupon_section()` function writes coupons both as a table AND as a rich multi-line format below (`### Analiza szczegółowa`). The validator only reads the table. If the table row's description field doesn't contain per-leg odds in `@1.85` or `(1.85)` format, the arithmetic check is silently skipped (`legs_odds` is empty → line 134 returns `True, 0.0, 0.0`).

---

### G6. No weather staleness check
**[fetch_weather.py]**

When `--date` is >16 days in the future, Open-Meteo returns unreliable forecast data. No warning is emitted. Also, existing weather JSON is silently overwritten.

---

## IMPROVEMENTS

### I1. `datetime.utcnow()` deprecated in Python 3.12+
**[tipster_aggregator.py:371, 456, 808]**

Use `datetime.now(timezone.utc)` instead (PEP 587).

---

### I2. `stress_test_coupon()` uses `safety_score` as probability
**[coupon_builder.py:339]**

```python
p = _safe_float(bm.get("probability") or bm.get("safety_score", 0.5), 0.5)
```

When `probability_engine` isn't available, `safety_score` (= `min(hit_rate_L10, hit_rate_H2H)`) is used as probability. Safety score ≠ true probability — a safety of 0.80 means 80% historical hit rate, not 80% future probability. The P(coupon) display may be misleading.

---

### I3. `compute_stake()` returns 1.0 PLN for negative-EV
**[coupon_builder.py:309-315]**

When Kelly fraction `f ≤ 0` (negative edge), the function returns 1.0 PLN anyway. Kelly says don't bet. In stats-first mode (no odds) this is acceptable, but when odds ARE available and EV is clearly negative, stakes are still allocated.

---

### I4. `COMBO_THEMES` hard-coded with lambdas
**[coupon_builder.py]**

Combo themes (SAFE-2, STAT-3, EV-TOP, DIVERSIFIER, etc.) are hard-coded with lambda filters. Users can't adjust theme parameters without editing source code. The rest of the pipeline is config-driven via `betting_config.json`.

---

### I5. `run_full_scan_and_prepare.sh` hard-codes 200+ URLs
**[run_full_scan_and_prepare.sh]**

All scan URLs are embedded in the shell script. Adding/removing a source requires editing the script. `config/scan_urls.json` exists but may not be the actual source.

---

### I6. `_pick_description_pl()` displays `(0.00)` for missing odds
**[coupon_builder.py:158]**

In stats-first mode, picks without odds show `(0.00)` in coupon descriptions. The validator extracts `0.00` as leg odds → combined odds = 0 → ARITHMETIC error. The display also looks broken to the user.

**Fix:** Show `(kurs TBD)` or omit the odds parenthetical when odds = 0.

---

## CONSISTENCY ISSUES

### X1. Night classification timezone handling differs
**[gate_checker.py:403-408] vs [coupon_builder.py:371-384]**

`gate_checker` parses night by naive string splitting (`kickoff.split("T")[1][:2]`) without timezone conversion — returns `"N"` string tier. `coupon_builder._classify_night()` uses `datetime.fromisoformat()` with proper UTC→Warsaw timezone conversion — returns `bool`. A kickoff at 19:30 UTC = 21:30 Warsaw would be classified as NOT night by gate_checker but IS night by coupon_builder. This causes picks to have mismatched tiers.

---

### X2. Date format inconsistency across pipeline
**[build_shortlist.py:283,563,657,665,713] vs [pipeline_orchestrator.py:830-833]**

Shortlist uses compact dates (`20260505`) for filenames. The orchestrator handles this with fallback logic that tries both formats:
```python
shortlist_path = DATA_DIR / f"{date_compact}_s2_shortlist.json"
if not shortlist_path.exists():
    shortlist_path = DATA_DIR / f"{date}_s2_shortlist.json"
```
This works but is fragile. Any new consumer must know to try both formats. Should standardize on one format.

---

### X3. `search_flashscore_playwright()` doesn't accept `sport` parameter
**[settle_on_finish.py:267]**

```python
def search_flashscore_playwright(home, away):
    return _flashscore_batch_cache.get(home, away)
```

The batch fetcher validates scores per-sport during `_parse_scores()`, but the lookup `get()` doesn't re-validate. When called from the settlement loop (line 654), it has no sport context. Basketball scores may have been rejected during parsing (default max_total=30), so `get()` returns None even if the game was actually fetched.

---

### X4. Coupon validator only checks table rows, misses analysis sections
**[validate_coupons.py:38-117]**

`parse_coupon_tables()` reads pipe-delimited rows only. Coupon markdown has stress test data, correlation warnings, and analysis sections outside tables. None of this content is validated for consistency.

---

### X5. Team name regex safety inconsistency in settlement
**[settle_on_finish.py:155, 273 vs 227-260]**

`search_cached_html()` and `search_sofascore()` use `re.escape(home)` in regex (safe). But `_FlashscoreBatchFetcher._fuzzy_match()` uses substring `in` checks. Not a security issue, but teams with regex-special characters (e.g., "1. FC Köln") could cause `re.error` in the non-Playwright paths.

---

**Total: 3 critical, 4 significant, 6 gaps, 6 improvements, 5 consistency issues.**
