# D12 - downstream gates, schedule term `football_result` (path ii), settled days 2026-10-13..2026-11-07

Pre-registered: `docs/sofa/evidence/kontekst_terminarza_2026-11-08/r3_final_review.md` 248-262. Read-only measurement; scripts and outputs in `data/refit_2026-11-08_schedule/d12/` (`extract.py`, `features.py`, `pricing.py`, `conf.py`, `d12.py`, `make_report.py`). Every number below is printed by those scripts (`d12_main.json`, `d12_sim_delta.json`, logs).

Variants: **base** = the artifacts as built (08_confidence legs, 11_coupon singles, 08_refusals rows). **corrected** = the term exp(t) on the noted pure-rating goals centres of path (ii) rows (frozen `fr_frozen.json` coef), the four simulator floor keys untouched. Two runs: **main** (simulator keys NOT recomputed - base p not reproducible within 1e-6) and **sim_delta** (sensitivity: simulator keys also corrected by the delta method below).

## 1. Method and reproduction

- Features: events needed 11918; calendar 1185873 85; fixtures not in sofa_listed_event 2068 added from sofa_event_detail 2068; computed 11918 missing from calendar 0 in pkl 8212 differ from pkl 16. Calendar = `sofa_listed_event` (as `football_features.py`) plus the 2068 day fixtures absent from it, taken from their cached `/event` payload (`sofa_event_detail`); the 16 'differ from pkl' are events whose history gained those fixtures.
- Base p from the noted centres (centres printed to 3 dp) vs `p_central`, all in-scope sheet rows of the 26 days:

```
btts_or_over              n=  12062 mismatch(>1e-6 after 4dp)=  6705 maxdiff=0.000300 unparsed=0
dc_and_over               n=  24240 mismatch(>1e-6 after 4dp)= 11384 maxdiff=0.000300 unparsed=0
dc_and_under              n=  25833 mismatch(>1e-6 after 4dp)= 14378 maxdiff=0.000300 unparsed=0
double_chance             n=  29522 mismatch(>1e-6 after 4dp)= 13543 maxdiff=0.000300 unparsed=0
draw_no_bet               n=  19286 mismatch(>1e-6 after 4dp)= 12502 maxdiff=0.000500 unparsed=0
first_goal                n=  15110 mismatch(>1e-6 after 4dp)=  6878 maxdiff=0.000300 unparsed=0
result_1x2                n=  19830 mismatch(>1e-6 after 4dp)= 11427 maxdiff=0.000300 unparsed=0
result_handicap           n=  10637 mismatch(>1e-6 after 4dp)=  5091 maxdiff=0.000200 unparsed=0
result_or_btts            n=   5152 mismatch(>1e-6 after 4dp)=  2626 maxdiff=0.000300 unparsed=0
result_or_clean_sheet     n=   5164 mismatch(>1e-6 after 4dp)=  2538 maxdiff=0.000300 unparsed=0
result_or_over            n= 132103 mismatch(>1e-6 after 4dp)= 58759 maxdiff=0.000300 unparsed=0
result_or_under           n= 130839 mismatch(>1e-6 after 4dp)= 65684 maxdiff=0.000300 unparsed=0
sim                       n=  25104 mismatch(>1e-6 after 4dp)=  7024 maxdiff=0.001300 unparsed=0
```
  The base is therefore NOT reproduced exactly (rounding of the noted centres). Corrected p = p_central + [price(centres x exp(t)) - price(centres)]; non-sim rows checked 1484 max |delta(true centre) - delta(noted centre)| over +-0.0005 corners 1.89e-05 (non-sim). For the simulator (max diff 0.0013, 7024 of 25104 rows > 1e-6) the main run does not recompute; sim_delta applies the same delta with the event-seeded simulator (common random numbers).
- Confidence: the day's CONFIDENCE chain (`Calibration.realised` with the day's staged calibration and overlays -> `LineEvidence.read` -> `leg_floor` / catch-all / x >= 0.90 / prints_as_single), called on today's config files. The line evidence of each past day is not kept on disk (refitted every morning, overwritten), so the chain at the base p differs from the recorded confidence on most legs: TOTAL {'n': 58575, 'exact': 9106, 'le0.005': 39899, 'le0.02': 53339, 'src_same': 57502} (all in-scope + floor-sim 08 legs; `src_same` = same curve). Therefore corrected confidence = recorded confidence + [chain(p_corr) - chain(p_base)] where the chain does not reproduce the leg exactly, and chain(p_corr) where it does. Per run: main: {'differs': 48615, 'exact': 9187}; sim_delta: {'differs': 48615, 'exact': 9187}.
- Simulator keys in scope (htft, result_1h, result_2h, higher_scoring_half, first_goal_1h): 0 legs in 08_confidence and 0 printed singles on all 26 days; of their 12,315 sheet rows the 08_refusals rows (10-21..11-07) were 10,468 BELOW_CONFIDENCE_FLOOR, 1,799 KICKED_OFF, 33 CROSS_LEAGUE_UNLINKED, 12 NO_LINE_EVIDENCE, 2 NO_FETCHED_AT, 1 ODDS_TOO_LOW; sim_delta produced no simulator entrant, so the two runs are identical. 21 in-scope legs had no sheet row (not recomputed); 752 legs are the four floor keys (excluded, uncorrected).
- Printability = confidence >= the leg's floor, x >= 0.90, not catch-all, prints_as_single (margin <= 15% or the one-sided rule). Gates that do not read p (start, fresh price, reads, settleability, unlinked...) are taken as built.

## 2. Run `main`

### t distribution (in-scope 08 legs recomputed)

- leg status: {'ok': 57748, 't_nonzero': 30923, 'no_coverage': 50, 'national': 4}; printed legs: {'ok': 56649, 't_nonzero': 30188, 'no_coverage': 34, 'national': 4}
- sides with coverage: 115496; share of those sides with t != 0: 0.5355; mean |t| per side 0.00698; max |t| 0.13215

### Printed / printable legs (in scope)

| quantity | base | corrected |
|---|---|---|
| in-scope 08 legs (passed every gate) | 57823 | - |
| ... sim legs not recomputed | 0 | |
| ... legs whose p changed / confidence changed | | 30923 / 3367 |
| printed in-scope singles (11_coupon) | 56708 (won 43735 / lost 12198 / other 775; hit 0.7819) | 56159 (won 43326 / lost 12066 / other 767; hit 0.7822) |
| printed -> not printable (flip out) | - | 747 (won 556 / lost 180 / other 11; hit 0.7554) |
| refused at a p gate -> printable (entrants; 08_refusals days 10-21..11-07 only) | - | 198 (won 147 / lost 48 / other 3; hit 0.7538) |
| refused rows the base chain (today's config) already calls printable (skipped) | 97 | |
| football singles printed, all markets | 109053 | 108504 |

### MODEL_ABOVE_OWN_SAMPLE

- removed legs (11_coupon removed_by_reads, refusal MODEL_ABOVE_OWN_SAMPLE): in scope 0 (won 0 / lost 0 / other 0; hit None); out of scope 958 (won 740 / lost 217 / other 1; hit 0.7732) - identical in both variants (the term moves no row with a sample; path (ii) rows carry sample_size 0, `model_above_own_sample` needs >= 5 values). In-scope 08_refusals rows with that reason (10-21..11-07): 0.

### price_gap (confidence - 1/odds > 0.03), printed in-scope legs

- base (recomputed on the leg): 2705 (won 1844 / lost 797 / other 64; hit 0.6982); recorded `price_gap` field: 2705
- corrected: 2698 (won 1844 / lost 791 / other 63; hit 0.6998)

### rating_market_gap (D >= 1.0), printed football singles (all markets; live only from 11-04)

- rating view sources: {'05_sheet goals_total FOOTBALL_RATING note': 9136, '05_sheet result note (pure rating centres)': 51}
- matches with D >= 1: base 484, corrected 480
- flagged legs: base 1099 (won 802 / lost 297 / other 0; hit 0.7298) (in scope 985, out 114); corrected, D on the corrected rating whatever its source 1088 (won 795 / lost 293 / other 0; hit 0.7307) (in 975, out 113); corrected as wired today (only a SOURCE_PURE view moves) 1098 (won 801 / lost 297 / other 0; hit 0.7295)
- base recompute vs the recorded field, 11-04..11-07 (recorded flags, singles agreeing, singles): {'2026-11-04': (24, 1266, 1266), '2026-11-05': (15, 1835, 1835), '2026-11-06': (18, 3498, 3498), '2026-11-07': (106, 11628, 11628)}

### SAME_EVENT_DEDUP twins (hypothetical: the rule is live from 11-08; groups with >= 2 printed legs of one event, one in scope)

- twin groups: 545; with a confidence or membership change: 37; chosen leg changed: 9
- legs dedup would remove: base 658, corrected 640

### Per day (printed in scope / flip out / entrants / conf changed)

| day | printed in scope | flip out | entrants | legs conf changed |
|---|---|---|---|---|
| 2026-10-13 | 0 | 0 | n/a | 0 |
| 2026-10-14 | 0 | 0 | n/a | 0 |
| 2026-10-15 | 106 | 2 | n/a | 9 |
| 2026-10-16 | 1308 | 18 | n/a | 74 |
| 2026-10-17 | 6811 | 59 | n/a | 288 |
| 2026-10-18 | 5288 | 45 | n/a | 263 |
| 2026-10-19 | 950 | 34 | n/a | 112 |
| 2026-10-20 | 1089 | 11 | n/a | 69 |
| 2026-10-21 | 922 | 22 | 9 | 92 |
| 2026-10-22 | 657 | 9 | 11 | 68 |
| 2026-10-23 | 2021 | 26 | 15 | 134 |
| 2026-10-24 | 6665 | 62 | 7 | 230 |
| 2026-10-25 | 4203 | 44 | 4 | 223 |
| 2026-10-26 | 715 | 18 | 1 | 82 |
| 2026-10-27 | 1496 | 26 | 0 | 102 |
| 2026-10-28 | 1825 | 42 | 4 | 157 |
| 2026-10-29 | 804 | 34 | 6 | 104 |
| 2026-10-30 | 1687 | 35 | 17 | 130 |
| 2026-10-31 | 5814 | 75 | 8 | 329 |
| 2026-11-01 | 4101 | 70 | 50 | 283 |
| 2026-11-02 | 1049 | 22 | 6 | 134 |
| 2026-11-03 | 1002 | 12 | 12 | 71 |
| 2026-11-04 | 589 | 12 | 5 | 59 |
| 2026-11-05 | 580 | 11 | 10 | 66 |
| 2026-11-06 | 1649 | 13 | 1 | 71 |
| 2026-11-07 | 5377 | 45 | 32 | 217 |

## 2. Run `sim_delta`

### t distribution (in-scope 08 legs recomputed)

- leg status: {'ok': 57748, 't_nonzero': 30923, 'no_coverage': 50, 'national': 4}; printed legs: {'ok': 56649, 't_nonzero': 30188, 'no_coverage': 34, 'national': 4}
- sides with coverage: 115496; share of those sides with t != 0: 0.5355; mean |t| per side 0.00698; max |t| 0.13215

### Printed / printable legs (in scope)

| quantity | base | corrected |
|---|---|---|
| in-scope 08 legs (passed every gate) | 57823 | - |
| ... sim legs not recomputed | 0 | |
| ... legs whose p changed / confidence changed | | 30923 / 3367 |
| printed in-scope singles (11_coupon) | 56708 (won 43735 / lost 12198 / other 775; hit 0.7819) | 56159 (won 43326 / lost 12066 / other 767; hit 0.7822) |
| printed -> not printable (flip out) | - | 747 (won 556 / lost 180 / other 11; hit 0.7554) |
| refused at a p gate -> printable (entrants; 08_refusals days 10-21..11-07 only) | - | 198 (won 147 / lost 48 / other 3; hit 0.7538) |
| refused rows the base chain (today's config) already calls printable (skipped) | 97 | |
| football singles printed, all markets | 109053 | 108504 |

### MODEL_ABOVE_OWN_SAMPLE

- removed legs (11_coupon removed_by_reads, refusal MODEL_ABOVE_OWN_SAMPLE): in scope 0 (won 0 / lost 0 / other 0; hit None); out of scope 958 (won 740 / lost 217 / other 1; hit 0.7732) - identical in both variants (the term moves no row with a sample; path (ii) rows carry sample_size 0, `model_above_own_sample` needs >= 5 values). In-scope 08_refusals rows with that reason (10-21..11-07): 0.

### price_gap (confidence - 1/odds > 0.03), printed in-scope legs

- base (recomputed on the leg): 2705 (won 1844 / lost 797 / other 64; hit 0.6982); recorded `price_gap` field: 2705
- corrected: 2698 (won 1844 / lost 791 / other 63; hit 0.6998)

### rating_market_gap (D >= 1.0), printed football singles (all markets; live only from 11-04)

- rating view sources: {'05_sheet goals_total FOOTBALL_RATING note': 9136, '05_sheet result note (pure rating centres)': 51}
- matches with D >= 1: base 484, corrected 480
- flagged legs: base 1099 (won 802 / lost 297 / other 0; hit 0.7298) (in scope 985, out 114); corrected, D on the corrected rating whatever its source 1088 (won 795 / lost 293 / other 0; hit 0.7307) (in 975, out 113); corrected as wired today (only a SOURCE_PURE view moves) 1098 (won 801 / lost 297 / other 0; hit 0.7295)
- base recompute vs the recorded field, 11-04..11-07 (recorded flags, singles agreeing, singles): {'2026-11-04': (24, 1266, 1266), '2026-11-05': (15, 1835, 1835), '2026-11-06': (18, 3498, 3498), '2026-11-07': (106, 11628, 11628)}

### SAME_EVENT_DEDUP twins (hypothetical: the rule is live from 11-08; groups with >= 2 printed legs of one event, one in scope)

- twin groups: 545; with a confidence or membership change: 37; chosen leg changed: 9
- legs dedup would remove: base 658, corrected 640

### Per day (printed in scope / flip out / entrants / conf changed)

| day | printed in scope | flip out | entrants | legs conf changed |
|---|---|---|---|---|
| 2026-10-13 | 0 | 0 | n/a | 0 |
| 2026-10-14 | 0 | 0 | n/a | 0 |
| 2026-10-15 | 106 | 2 | n/a | 9 |
| 2026-10-16 | 1308 | 18 | n/a | 74 |
| 2026-10-17 | 6811 | 59 | n/a | 288 |
| 2026-10-18 | 5288 | 45 | n/a | 263 |
| 2026-10-19 | 950 | 34 | n/a | 112 |
| 2026-10-20 | 1089 | 11 | n/a | 69 |
| 2026-10-21 | 922 | 22 | 9 | 92 |
| 2026-10-22 | 657 | 9 | 11 | 68 |
| 2026-10-23 | 2021 | 26 | 15 | 134 |
| 2026-10-24 | 6665 | 62 | 7 | 230 |
| 2026-10-25 | 4203 | 44 | 4 | 223 |
| 2026-10-26 | 715 | 18 | 1 | 82 |
| 2026-10-27 | 1496 | 26 | 0 | 102 |
| 2026-10-28 | 1825 | 42 | 4 | 157 |
| 2026-10-29 | 804 | 34 | 6 | 104 |
| 2026-10-30 | 1687 | 35 | 17 | 130 |
| 2026-10-31 | 5814 | 75 | 8 | 329 |
| 2026-11-01 | 4101 | 70 | 50 | 283 |
| 2026-11-02 | 1049 | 22 | 6 | 134 |
| 2026-11-03 | 1002 | 12 | 12 | 71 |
| 2026-11-04 | 589 | 12 | 5 | 59 |
| 2026-11-05 | 580 | 11 | 10 | 66 |
| 2026-11-06 | 1649 | 13 | 1 | 71 |
| 2026-11-07 | 5377 | 45 | 32 | 217 |

## 3. Limitations

- The base p is not re-priced exactly (centres noted to 3 dp); the term enters as a delta (error bound above). Simulator keys: not recomputed in `main`; `sim_delta` is a sensitivity only.
- Confidence on today's config files: the per-day line-evidence fit is not on disk; the corrected confidence is anchored on the recorded one plus the chain's delta. Curves are step functions in p buckets, so most small p moves change no confidence.
- Features as of the DB copy (2026-11-08): `cont_next4` sees fixtures listed later than the build; 2068 fixtures were added from `/event` payloads. Not a live replay of the build-time calendar.
- Entrants only from `08_refusals.json` (10-21..11-07), the LAST build of each day: rows refused KICKED_OFF there were judged by earlier builds whose refusals are not kept -> entrants are a lower bound; days 10-13..10-20 have none counted.
- 08 legs are the last build's (locked legs keep their print-time confidence and odds). Twins / dedup and rating_market_gap were not live on most of these days: their numbers are what the rule would have done.
- No curve refit with the term (r3 steps 22-27): the corrected p is read through today's curves.
