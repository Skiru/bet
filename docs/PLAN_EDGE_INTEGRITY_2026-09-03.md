# Handoff prompt: pipeline edge integrity (fix, test, polish)

Written 2026-09-03 after pricing `runs/2026-09-03/2026-09-03_kupony.md` by hand.
Paste everything below the line into a fresh session. It is self-contained.

---

You are working in `/Users/mkoziol/projects/bet`, on the `simple_stats` pipeline
(`scripts/simple/run_pipeline.py`: DISCOVER → SUPERBET → ENRICH → MARKET_CONTEXT →
TIPSTERS → ANALYZE → coupons). Read `CLAUDE.md`, `docs/SIMPLE_STATS_RUNBOOK.md` and the
memory index before touching code. Work on a new branch off `main`. Do not commit or
push until every phase's tests are green and you have re-run the 2026-09-03 day from
ENRICH (never from DISCOVER on a rerun; see memory `rerunning-a-day-resume-at-enrich`).

## Why this work exists

A manual audit of the 2026-09-03 coupon found that the pipeline prints edges that are
artefacts of its own estimators, and that it prices a tiny fraction of what Superbet
offers. Three examples, each verified against artifacts in `runs/2026-09-03/`:

- `cards_total` 8.5 UNDER on Grêmio–Internacional looked +20% EV. Our `cards_total` is
  **yellow cards only** (`src/bet/simple_stats/providers.py` aliases every provider's
  `yellow_cards` to `cards_total`/`cards_for`). Superbet's "Liczba kartek" settles a
  straight red as 2 and a second-yellow dismissal as 3. In settled points the last three
  Grenals read ~11–13, 8–9, 4 (two of three OVER 8.5), not 7, 7, 4.
- Potapova `aces_for` 3.5 UNDER printed p_central 0.962 and a minimum price of 1.14 on a
  5/5 sample averaging 1.4 aces. Her 2026 season average is 3.25 and she hit 10 aces in
  round one. The market pivot sat exactly on her season rate.
- Superbet's offer that day carried 3,691 events; we matched 108. DISCOVER dropped 109
  fixtures as `no_primary_identity`. The universe is not small; our entry to it is.

The operator's standard is explicit: **a pick below its minimum price is not a pick, and
a pick priced against the wrong quantity is not a pick either.** Every change below is
about making the printed probability describe the thing Superbet settles, and about
pricing more of what Superbet offers.

## Ground rules

1. Never change `TIER_MARGIN` or loosen `p_low`. The bar's *input* may change; the margin
   pays for p_central's known 4.4pp overstatement on price-selected rows (memory
   `p-low-understates-by-23pp`). Do not "fix" thinness by lowering margins.
2. Tests must not spend provider quota (memory `tests-could-spend-the-quota`). Every new
   test uses fixtures under `tests/fixtures/simple_stats/`. Run the suite with the
   existing conftest guard active.
3. OddsPapi has a **250-request lifetime** budget (memory `oddspapi-serves-identity-not-price`).
   Do not add calls to it. bzzoiro football is uncapped on PRO; bzzoiro-tennis answers
   402 and is withdrawn. highlightly is 100/day and drives discovery breadth.
4. Every behavioural change ships with (a) a regression test named after the day and the
   defect, e.g. `tests/simple_stats/test_regression_2026_09_03_cards_points.py`, (b) a
   before/after diff on the 2026-09-03 sheet via `scripts/simple/diff_stats_sheet.py`,
   and (c) a line in `docs/SIMPLE_STATS_RUNBOOK.md` if operator behaviour changes.
5. Keep `p_low` as the ranking column. It is the honest statement of evidence; it is
   just the wrong thing to divide into 1.
6. The test suite baseline is 69 failures plus collection errors in 23 files (memory
   `test-suite-blocked-at-collection`). Diff failure *sets*, not counts. Do not
   "fix" unrelated tests to make a number go down; do fix collection errors you cause.
7. Do not restrict samples by competition (killed hypothesis, `p-low-understates-by-23pp`).

## Phase 1 — Price the quantity that settles (cards)

**Problem.** `cards_total`, `cards_for`, `cards_1h_*`, `cards_2h_*` are yellows.
`red_cards_total` exists but is sparse (2–4 observations per team on the Grenal dossier)
and never feeds a priced line. Superbet: yellow = 1, straight red = 2, second yellow → 3
in total. The backtest (`scripts/simple/backtest_slate.py`, `src/bet/simple_stats/settle.py`)
settles cards against provider yellow counts, so the calibration that certified
`p_central` on card rows was measured against the wrong quantity too.

**Do.**
- Add canonical metrics `cards_points_total` and `cards_points_for` = yellows +
  2 × straight reds + 1 per second-yellow dismissal (its first yellow is already
  counted). Source the red breakdown from bzzoiro match incidents (`get_match_incidents`
  distinguishes yellow / red / yellow-red) when enriching, and from
  `red_cards_total` when incidents are unavailable (then assume straight reds and flag
  the observation `RED_TYPE_UNKNOWN`). Where no red information exists at all, mark the
  observation `REDS_UNKNOWN` and **exclude it from card-points samples** rather than
  treating it as zero (memory `a-zero-that-means-unknown`).
- Map Superbet "Liczba kartek" and "<Team> - liczba kartek" to the points metrics in
  `src/bet/simple_stats/offered_lines.py` / `superbet_offer.py`. Map "Liczba czerwonych
  kartek" to `red_cards_total`. Keep the yellow metrics for providers that only have
  yellows and for any future yellow-only market, but they must not be priced against
  "Liczba kartek".
- Settlement: `settle.py` and the backtest actuals reader must compute points the same
  way. Delete cached actuals that were built on yellows before re-running the backtest.
- Re-run the estimator bake-off / backtest on card rows only and record the calibration
  table for `cards_points_*` in the memory note `cards-total-is-yellow-only-superbet-counts-reds`.

**Accept when.** On the 2026-09-03 dossier, Grêmio–Internacional `cards_points_total`
h2h reads 11 or 13 for 2025-09-21 (7Y+2R), 8 or 9 for 2026-04-11 (7Y+1R), 4 for
2026-08-27; the coupon no longer prints `cards_total` against "Liczba kartek"; the
regression test asserts the alias table has no `yellow_cards → cards_points_*` entry
without red handling.

## Phase 2 — Stop zero-miss small samples from printing certainty

**Problem.** `analyze.py:1458-1464`: `p_central` falls back to `count_model_central`,
which fits a distribution to the sample and reads the tail. On 5/5 it returns 0.99;
`required_odds` (`bet_builder_draft.py:261`) then demands 1.11. Every 5/5 tennis row on
2026-09-03 passed its bar this way. `p_low` was identical across three rungs on
Tagger 7.5/8.5/9.5 because the count model, not the sample, separated them.

**Do.**
- Cap the bar input: `p_bar = min(p_central, (hits + 1) / (n + 2))` for any sample with
  zero misses, and additionally `p_bar = p_low` when `n < 8`. Expose the cap reason in
  the row (`bar_basis_reason`) and in the coupon caveats so the operator sees why the
  minimum moved.
- When the count model separates rungs with no observation between them, mark those
  rows `RUNG_SEPARATED_BY_MODEL` and cap their tier at LEAN.
- Keep `p_central` itself unchanged for calibration reporting; only the bar input moves.

**Accept when.** Potapova `aces_for` 3.5 UNDER and Bu–Zheng `double_faults_total` 8.5
UNDER show a minimum price ≥ 1.75 (they were 1.14 and 1.11) and fall out of "Warte swojej
ceny". Grenal `cards_for` Internacional 3.5 UNDER (8/9) keeps a bar near 1.29.

## Phase 3 — Use Superbet's two-sided ladder as a prior on every row

**Problem.** For every audited row the de-vigged Superbet pivot was available and
disagreed with us by 20–50 points (cards 7.5 pivot vs sample median 5.5; fouls 36.5 vs
27.4; aces 3.5 vs 1.4). `MAX_MARKET_DISAGREEMENT` (`coupons.py:231`) only annotates;
`MAX_LADDER_SIGMA` (`coupons.py:270`) needs two de-vigged rungs and is blind on
single-rung markets (`ladder_sigma: null` on 9 of 15 singles). Genuine value *is* a
disagreement, so the gate cannot simply demote — but a 5-observation sample should not
be allowed to overrule a two-sided price unchallenged.

**Do.**
- In the SUPERBET step, compute for each offered line the de-vigged probability
  `p_mkt = (1/u) / (1/u + 1/o)` when both sides are active. Store it on the comparison
  row as `superbet_implied_probability` and, for ladders, the implied centre.
- In coupon building, compute a **market-shrunk probability**
  `p_shrunk = w·p_bar + (1−w)·p_mkt` with `w = n / (n + k)`, `k` a per-market constant
  starting at 10 for football totals and 20 for tennis length-dependent markets (aces,
  double faults, games, sets). Use `p_shrunk` as the bar input. Keep `p_low` as the
  ranking column. Print `p_mkt`, `w`, and `p_shrunk` in the coupon row.
- Calibrate `k` with `backtest_slate.py` on the slates that have a `superbet_offer.json`
  (2026-09-01 onwards; keep every offer file, it is the scarce input). Report the ROI of
  `p_bar`, `p_shrunk(k=5)`, `p_shrunk(k=10)`, `p_shrunk(k=20)` arms with intervals. Do
  not pick `k` by eye.
- Single-rung markets: when only one rung exists, `ladder_sigma` must still be computed
  from the de-vigged single pivot versus the sample median normalised by the sample's own
  spread (memory `ladder-check-must-be-scale-free`). Two rungs are not required to know
  where the market puts its centre.

**Accept when.** On 2026-09-03 with `k=10`: Grenal `cards_for` Internacional 3.5 UNDER
still clears at 2.07; Potapova aces, Dart games, Bu–Zheng double faults do not; the
comparison artifact carries `superbet_implied_probability` on every two-sided line; the
backtest report for the `k` arms is committed under `docs/`.

## Phase 4 — Make analyst downgrades bite

**Problem.** `AnalystVeto` (`bet_builder_draft.py:101`) `DOWNGRADE` lowers tier one step,
which raises the margin from 1.05 to 1.10. Under the p_central bar that is a 5% move.
`fouls_total` and `fouls_for` on the Grenal were downgraded with a reason that said
"conditional on this match the record is 1/3, not 19/21" and still printed as value.

**Do.**
- Add `reason_class` to `AnalystVeto`: `SAMPLE_NOT_REPRESENTATIVE`, `LINE_ON_MODE`,
  `MISSING_REFEREE`, `ESTIMAND_WRONG`, `DATA_CONFLICT`, `OTHER`.
- `SAMPLE_NOT_REPRESENTATIVE` and `ESTIMAND_WRONG` set `w = 0` in Phase 3 (fully
  market-priced) for the affected rows — the sample is declared uninformative, so the
  row survives only if the operator's price beats the market's own de-vigged price plus
  margin, which is almost never. `LINE_ON_MODE` applies only to the named rung.
  `MISSING_REFEREE` caps card-market rows at LEAN and requires `p_shrunk` with `k` doubled.
- The coupon header must print the class next to each downgrade.

**Accept when.** A regression test feeds the 2026-09-03 vetoes file with classes added
and asserts `fouls_total` 36.5 UNDER and both `fouls_for` rows drop below the value line
while `cards_for` Internacional 3.5 UNDER does not.

## Phase 5 — Context that exists but never arrives

**Problem.** `fixture_context.round_name`, `group_name`, `previous_leg_event_id` are null
in 165/165 dossiers although `get_match_detail` returns them (`discover.py:621` comment
acknowledges the fields). `is_local_derby` is false for the Grenal at 11 km; the flag is
bzzoiro's and is wrong, so no code path ever degraded the biggest derby of the day.
Referee is null on 8 of 22 football fixtures and card rows stayed CALL. `_confidence`
(`analyze.py:1353`) returns HIGH at n ≥ 8 without a per-side minimum, so 3+11 and 4+4
samples read as settled. `STALE_SEASON` (`analyze.py:786`) cannot fire on h2h because the
h2h route has no competition/season id, so a 15-month-old meeting sits in a current
sample. `possession` is 100.0 on every observation.

**Do.**
- Populate the three round fields from the discovery payload; add a `KNOCKOUT_SECOND_LEG`
  context flag when `previous_leg_event_id` is set and the aggregate is level or within
  one goal (fetch the first-leg score once). The flag caps UNDER rows on cards and fouls
  at LEAN.
- Derive `derby_by_distance = travel_distance_km is not None and travel_distance_km < 25`
  and treat `is_local_derby or derby_by_distance` as derby. Pin (154, 161) as a known
  derby regardless. Derby caps card and foul UNDER rows at LEAN and adds the flag text.
- Referee: when `referee_id` is null, card-market rows cannot be CALL. When a referee is
  present with ≥ 15 matches, blend the referee's per-match yellow rate into the card mean
  with weight `m_ref / (m_ref + 20)` and print it.
- `_confidence`: require `min(n_side_a, n_side_b) >= 3` for HIGH and `>= 2` for MEDIUM;
  otherwise LOW with reason `ONE_SIDED_SAMPLE`.
- h2h staleness: apply a date cutoff of 15 months on h2h observations only (they carry
  dates), flag `STALE_H2H`.
- Drop `possession` from every priced path and from dossier metrics until the provider
  mapping is fixed; a constant is not data.

**Accept when.** The Grenal dossier shows `round_name="Quarterfinals"`,
`previous_leg_event_id="587786"`, derby true, `KNOCKOUT_SECOND_LEG` set; Neom and
Al-Fayha card rows read confidence LOW with `ONE_SIDED_SAMPLE`; no row has `possession`.

## Phase 6 — Dedup and corroboration honesty

**Problem.** The `(bucket, day)` collapse on DISAGREE keeps the lower value (Náutico
6 vs 8, América 8 vs 4), which favours every UNDER. `AGREE` on the Grenal meant 3 of 20
matches corroborated (`corroborated_matches` exists but the label ignores it). With
highlightly at 101/100, 20,961 of 21,925 rows were SINGLE_SOURCE and the file still said
"AGREE" where it could.

**Do.**
- On a per-observation provider conflict, keep the value **adverse to the priced
  direction** (max for UNDER, min for OVER) and record `CONFLICT_RESOLVED_ADVERSE`; when
  the conflict spans the line itself, exclude the observation and record
  `CONFLICT_ON_LINE`.
- `cross_provider_agreement`: `AGREE` only when `corroborated_matches / sample_size >= 0.5`;
  otherwise `PARTIAL_AGREE` with the share printed. The coupon's "Zgodność" column shows
  the share, not the label alone.
- DISCOVER must fail loudly (verdict `DEGRADED`) when highlightly is exhausted before the
  slate is complete, and the runbook must say to wait for the quota or accept
  `espn-football` as the only corroborator for the day.

**Accept when.** Náutico `cards_total` 6.5 UNDER reads 19/21 or excludes the 6-vs-8
match; the Grenal card rows read `PARTIAL_AGREE 3/20`.

## Phase 7 — Discovery from the offer, not toward it

**Problem.** Discovery starts from odds-api/highlightly and then tries to match Superbet.
On 2026-09-03: 165 discovered, 52 enriched, 109 dropped `no_primary_identity`
(`enrich.py:618`), 57 of ours absent from the offer, and Superbet's 3,691 events matched
108. Tennis has no bzzoiro id at all (bzzoiro-tennis is 402). Player props: 3,373 rows
`MARKET_NOT_OFFERED`, 27 `OFFERED`, none priced above bar.

**Do.**
- Add an **offer-driven discovery mode** (`run_discover.py --from-offer PATH`): read the
  Superbet offer, keep events in our sports and window, resolve each to a bzzoiro fixture
  by `search_matches` on normalised names and kickoff (±10 min), and only then enrich.
  Preserve today's discovery as a second source of identities; union the two, dedupe by
  the existing `(club, instant)` rule (memory `dedup-one-club-one-instant`) with its two
  guards intact.
- Report the funnel every run: offered → in window → resolved to bzzoiro → enriched →
  priced → above bar. Print it in `AGENT_SUMMARY` and in the analysis header.
- Tennis: without a paid bzzoiro-tennis addon there is no reference source. Cap every
  tennis row at LEAN and print "no reference source" in the caveat until one exists. Do
  not spend OddsPapi on it.
- Do not chase Brazilian nickname joins for props (memory
  `coupon-value-is-the-binding-constraint`): a wrong join names the wrong human.

**Accept when.** A dry run on the 2026-09-03 offer file resolves at least 60% of offered
football events in window to a bzzoiro id without a single live request in tests
(fixtures only), and the funnel prints in the summary.

## Phase 8 — Coupon construction

**Problem.** `coupons.py:1183` keeps one row per `(event, market, subject)` and picks by
surplus, so cards 8.5 UNDER (20/20, sample max below the line) was dropped as
`duplicate_market_for_event` in favour of 7.5 (line on the sample's mode). Bet Builders
kept 6 of 25 legs below their own bar "as context"; legs were nested (Inter ≤3 and
Grêmio ≤5 nearly imply total ≤8); `bet_builder_draft.py`'s CLI never receives the offer,
so its availability gate is inert; the §40 contradiction test and §44 builder score from
`docs/SUPERBET_BET_BUILDER_METHOD_v3.md` are not computed in code.

**Do.**
- Rung choice: score each rung by `p_shrunk × price − 1` minus a penalty when the line
  lies within one unit of the sample mode or when the sample maximum exceeds the line;
  print the runner-up rung beneath the single as "alternatywny szczebel".
- Bet Builder: every leg must pass its own bar; at most one leg per mechanism family
  (cards/fouls together count as one; corners another; goals another; tennis length
  markets one); refuse nested legs where one implies another; compute the §44 score and
  refuse below 0.60; add `--offer` to the CLI and fail if absent.
- Add a final `SUPERBET_COMPARE` pass at coupon time (the step exists via `--offer`) and
  a `--refresh-offer` flag on `build_coupons.py` that re-fetches the public offer (about
  110 requests, no quota) so the coupon prints prices from minutes, not hours, ago.
- The coupon header must state the bar basis, the `k` used, and the number of rows
  removed by each new gate.

**Accept when.** On the 2026-09-03 rerun the Grenal single is `cards_points_total` at the
rung the scorer picks, with the alternative rung printed; no BB leg sits below its bar;
the header shows the funnel and gate counts.

## Order, verification, and what to report back

Work in the order above; Phases 1–3 carry most of the value and Phases 4–8 depend on
their outputs. After each phase:

1. Run the unit tests you added plus `tests/simple_stats/` in isolation.
2. Re-run 2026-09-03 from ENRICH into a scratch output directory (never overwrite
   `runs/2026-09-03/` until the end), then `diff_stats_sheet.py` old vs new and read
   the diff yourself. Name every row that changed direction or crossed the bar.
3. Run `backtest_slate.py` on every slate with a `superbet_offer.json`, both bar bases,
   and paste the table into the phase's section of `docs/PLAN_EDGE_INTEGRITY_2026-09-03.md`
   under a "Results" heading.

Finish with a report that a reader who did not watch you work can act on: what changed,
which rows on 2026-09-03 the changes removed or added and why each is correct, the
backtest tables, what you did not do and why, and which memory notes you updated
(at minimum `cards-total-is-yellow-only-superbet-counts-reds`, `bar-basis-is-now-p-central`,
`coupon-value-is-the-binding-constraint`). Then stop. Do not stake anything and do not
print a combined price for any slip.

---

# Results (2026-09-03, branch `edge-integrity-2026-09-03`)

Re-run resumed at ENRICH against the recorded `2026-09-03_event_list.json`, with
the clock pinned to 09:00 UTC (`run_enrich.py --now`) so the diff is about the
code and not about which fixtures had kicked off in the meantime. Slate gate
identical to the recorded run: 109 `no_primary_identity`, 1 `not_priced`, 3
`kickoff_passed`, 52 fixtures enriched.

**Headline.**

| | recorded 2026-09-03 | after |
|---|---:|---:|
| singles printed | 15 | 15 |
| singles **worth their price** | 15 | **7** |
| Bet Builder slips | 8 | 3 |
| slip legs | 25 | 6 |
| legs below their own bar | 6 | **0** |

All thirteen UNDER rows the audit was written about are gone. The two rows that
survived — Grenal `shots_total` 24.5 OVER and `offsides_for` 0.5 OVER — kept
their VALUE verdict at a higher bar (1.65 → 1.86 and 1.25 → 1.46).

## Phase 1 — Results

`cards_points_total` / `cards_points_for` = yellows + 2 × straight reds + 1 per
second-yellow dismissal, with the red type read from
`/events/{id}/incidents/` (new: `BzzoiroClient.get_incidents_result`).

The Grenal head-to-head, in the quantity Superbet settles:

| meeting | yellows (`cards_total`) | booking points |
|---|---:|---:|
| 2025-09-21 | 7 | **10** |
| 2026-04-11 | 7 | **9** |
| 2026-08-27 | 4 | **4** |

**10, not the 11-or-13 the note predicted**, and the arithmetic is card by card:
Internacional had four plain yellows plus A. Bernabei's second-yellow dismissal
(3 points, not 4 — both his yellows are already in `yellow_cards`), Grêmio two
yellows plus Arthur's straight red, and Mano Menezes' yellow is a manager's and
worth nothing. 4 + 3 + 2 + 2 = 10. `/stats/` reports 7 yellows and 2 reds for
that match, and 7 + 2×2 = 11 double-counts the second yellow by one.

The line the audit was about, `cards_total` 8.5 UNDER, was 20/20 in yellows and
is **16/20** in booking points. The Grenal single is now `cards_points_total`
8.5 UNDER at 1.48 against a 1.42 bar, with 9.5 UNDER printed as the alternative
rung.

Measured over the 468 paired observations on the re-run's own dossiers:

| | value |
|---|---:|
| observations where points ≠ yellows | 88 / 468 = **18.8%** |
| mean yellows / mean points | 3.609 / 3.983 (**+0.374** a match) |
| observations changing side at UNDER 3.5 … 9.5 | 2.1% – 6.2% |

Provider behaviour, measured over 80 historical fixtures on 2026-09-03 and the
reason the code is shaped as it is:

- `red_cards` absent from `/stats/` means zero reds — confirmed by incidents on
  **51 of 51** such fixtures. It is still not read as zero: incidents are the
  authority, and where they cannot be read the observation leaves the sample.
- The incidents feed **undercounts**: fewer player cards than `/stats/` on 4 of
  80. `/stats/` reported 0 reds against an incident red on 1 of 80. Neither was
  ever seen to invent a card, so the larger count is taken in both directions.
- Manager cards are excluded by `/stats/` already; the incidents parser agrees.
- Second-yellow dismissals: 4 in 80 fixtures. Straight reds: 14.

**Calibration table: not produced, and cannot be yet.** `cards_points_*` did
not exist before 2026-09-03, so no earlier dossier carries it and no rebuilt
sheet for a finished slate has a card row to settle. The only slate that has
the metric is today's, and its fixtures had not been played when this was
written. The measurement to run tomorrow is
`backtest_slate.py --date 2026-09-03 --rebuilt --calibrate`.

Priors pinned in `config/market_priors.json` from the re-run's own dossiers,
following that file's `_how_to_extend` recipe: `cards_points_total` mean 4.3754
over 293 observations, `cards_points_for` mean 2.0723 over 249. **No venue pair
for `cards_points_for`:** the split is real and the right sign (home 1.8409 over
132, away 2.3333 over 117, z = −2.55 — the referee home bias `cards_for` shows
at −0.52 a game over 1,110 observations) but 117 is under this repo's own
120-per-side floor, so it is recorded in the file's note and not pinned.

## Phase 2 — Results

`bar_input` caps the bar's *input*: Laplace `(hits+1)/(n+2)` on a zero-miss
sample, and `p_low` at `n < 8`. `p_central` itself is untouched.

| row | before | after |
|---|---:|---:|
| Potapova `aces_for` 3.5 UNDER (5/5) | min 1.14, Superbet 1.63 → VALUE | min **1.95** → not value |
| Bu–Zheng `double_faults_total` 8.5 UNDER (5/5) | min 1.11, Superbet 1.95 → VALUE | min **1.9452** → clears by 0.005 |
| Grenal `cards_for` Int. 3.5 UNDER (8/9) | min 1.29 | unchanged at 1.2885 |
| Grêmio `cards_for` 4.5 UNDER (10/10) | min 1.1366 | 1.1454 (Laplace binds) |
| Neom `cards_total` 4.5 UNDER (10/10) | min 1.3177 | unchanged (already below Laplace) |

**The Bu–Zheng row is the one the note's acceptance criterion overstated.** At
1.95 against a 1.9452 bar it clears by half a percent; what removes it is the
market prior (Phase 3), which puts its bar past 2.2. Written into
`test_regression_2026_09_03_zero_miss_bar.py` rather than papered over.

`RUNG_SEPARATED_BY_MODEL` fires on 8,840 of the re-run's rows — every rung whose
neighbour has the same hit count and a different `p_low`. It caps at LEAN, worth
5% on the margin.

## Phase 3 — Results

`p_shrunk = w·p_bar + (1−w)·p_mkt`, `w = n/(n+k)`. All four rows the note names
land where it asked:

| row | n | p_bar | p_mkt | w | bar | Superbet | verdict |
|---|--:|--:|--:|--:|--:|--:|---|
| Grenal `cards_points_for` Int. 3.5 UNDER | 9 | 0.604 | 0.438 | 0.47 | 1.82 | 2.07 | **clears** |
| Potapova `aces_for` 3.5 UNDER | 5 | 0.566 | 0.565 | 0.20 | 1.95 | 1.63 | out |
| Dart `games_won` 5.5 OVER | 5 | 0.566 | 0.659 | 0.20 | 1.72 | 1.41 | out |
| Bu–Zheng `double_faults_total` 8.5 UNDER | 5 | 0.566 | 0.472 | 0.20 | 2.24 | 1.95 | out |

Restated as a rule the operator can hold: the bar now asks you to beat the
devigged price by `(margin − 1) / w` — 50% relative at n=5, k=20; 15% at n=20,
k=10.

`superbet_implied_probability` is on **332 of the 354 priced comparison rows**
(the other 22 are one-sided). Single-rung `ladder_sigma` is no longer null: the
centre is read from the pivot and the sample's own spread, and where both paths
exist they agree — the Grenal's card ladder gives −0.878 interpolated and −0.868
from its 7.5 pivot alone.

### The `k` arms

`backtest_slate.py --rebuilt --max-singles 400 --bar-basis p_central --shrink-k K`
over 2026-09-01 and 2026-09-02, the two finished slates that have a
`superbet_offer.json`. Bootstrap 3,000 resamples, **clustered by fixture**
(`event_id` is now carried on every settled record for exactly this).

| arm | fixtures | settled | hit | staked | ROI | 95% CI | P(ROI<0) |
|---|--:|--:|--:|--:|--:|---|--:|
| k=0 (no prior) | 48 | 99 | 82.8% | 99 | −5.2% | [−16.3%, +4.4%] | 85% |
| k=5 | 49 | 95 | 86.3% | 95 | −3.6% | [−13.3%, +5.2%] | 78% |
| **k=10** | 48 | 90 | 88.9% | 90 | −3.2% | [−10.7%, +3.6%] | 82% |
| k=20 | 47 | 91 | 91.2% | 91 | −1.9% | [−9.5%, +5.0%] | 68% |
| k=40 | 47 | 94 | 92.6% | 94 | −1.4% | [−8.3%, +5.4%] | 67% |

**This does not pick `k`, and it is reported rather than squinted at.** Every
interval straddles zero and every pair of intervals overlaps almost entirely:
90 staked units over 48 fixtures on two slates cannot separate the arms. What
the table does say, monotonically and in every column, is that more market
weight never hurt — hit rate climbs 82.8% → 92.6% and ROI improves at every
step, with no turning point inside the range tested. The shipped values (10
football, 20 tennis length markets) therefore sit on the *conservative* side of
where the weak evidence points, which is the right side to be on while the
evidence is this weak. Re-run this with `--shrink-k 40` and `--shrink-k 80`
once four or five slates carry an offer.

## Phase 4 — Results

`AnalystVeto.reason_class` added, defaulting to `OTHER` so every vetoes file
already written still validates and still behaves exactly as it did.

- `SAMPLE_NOT_REPRESENTATIVE` / `ESTIMAND_WRONG` → `w = 0`. The row is priced on
  the book's own devigged number plus the tier margin, which a book does not
  sell. On the Grenal's `fouls_total` 36.5 UNDER that is the difference between
  VALUE at 1.82 and `PRICED_BELOW_THRESHOLD`.
- `MISSING_REFEREE` → `k` doubled (21 observations keep 51% instead of 68%).
- `LINE_ON_MODE` without a `line` names no rung and is **refused**, and the
  refusal is printed in the header rather than swallowed.
- The header prints the class and what it did to the arithmetic:
  `DOWNGRADE analityka [SAMPLE_NOT_REPRESENTATIVE]: … , waga próby = 0 …`.

The 2026-09-03 vetoes file predates the field, so every entry in the re-run
reads `[OTHER]` and behaves as a tier step, exactly as it did. Classifying that
file is the analyst's call, not this change's.

## Phase 5 — Results

The Grenal's dossier now reads:

```
round_name           "Quarterfinals"
previous_leg_event_id "587786"        (0-0, mapped onto tonight's sides)
travel_distance_km    11.0            is_local_derby: false  ->  derby: true
home_team_id/away     "154" / "161"
```

The three round fields were on every `/events/` row all along; the discovery
adapter's `raw_data` dict was where they stopped. `scripts/simple/backfill_fixture_context.py`
rewrites them into an event list without re-running DISCOVER, which is what
makes them reachable on a re-run at all.

Ceilings on the re-run: `RUNG_SEPARATED_BY_MODEL` 8,840 rows,
`NO_REFERENCE_SOURCE` 1,156 (all tennis), `MISSING_REFEREE` 76, `DERBY` 48,
`KNOCKOUT_SECOND_LEG` 14.

Referee blend, card match totals only: the Grenal's centre moves from the
sample's own 6.25 to **5.81**, and the row says why —
`"Bruno Arleu de Araujo averages 5.89/match over 49 matches, blended at w=0.71"`.
The weight `m/(m+20)` is the handoff note's and is **not measured**; it is one
named constant so the measurement has one number to move.

`possession` is gone from every alias table. It was 100.0 on 522 of 530
observations and 0.0 on the other 8 — a per-side percentage put through the
combiner that sums both sides of a *count*. No market read it.

**`_confidence` does not do what the note asked, and the note's own examples are
why.** Neom–Al-Khaleej and Al-Fayha–Al-Kholood both carry **4 observations a
side** on `cards_points_total`, so `min(n_a, n_b) >= 3` reads HIGH and the rule
as written catches neither. The floor is therefore **5**, which is not a number
chosen to catch them: it is what `enrich._compute_readiness` already means by a
complete sample ("at least five matches a side"), and that is the condition
`tier_for_row` hands CALL out on. Both fixtures now read **MEDIUM with
`ONE_SIDED_SAMPLE`**, not LOW — LOW is for a side down to a single trial, and
putting a 4+4 sample beside a 1+19 one would make the word useless. 139 rows
carry the reason.

`STALE_H2H` (15 months, measured against the sample's own newest observation
because the h2h route carries no season id for `STALE_SEASON` to read) removed
126 observations.

## Phase 6 — Results

- `CONFLICT_ON_LINE` excluded 38 observations; `CONFLICT_RESOLVED_ADVERSE`
  flagged 168 rows. Where a conflict does *not* straddle the line the two rules
  coincide on the hit count by construction — what the adverse value changes
  there is the centre the count model prices from, which is what `p_central`,
  and therefore the bar, is read off.
- `PARTIAL_AGREE` added. **The Grenal's card rows read `PARTIAL_AGREE 3/20`**,
  which is the acceptance criterion exactly. 348 rows across the slate moved
  from `AGREE`; the coupon's Zgodność column now prints the share, not the word.
- DISCOVER reports `SLATE_DEGRADED` and a PARTIAL verdict when a slate-critical
  source (`highlightly`) runs out of quota mid-slate. **Not the verdict word
  "DEGRADED" the note asked for**: the repo's agent contract accepts
  OK/PARTIAL/FAILED/NO_BET/PRECONDITION_FAILED and nothing else, so the cause
  travels in `issues` and `metrics` exactly as `BLOCK_NO_EVENTS` already does.

## Phase 7 — Results

**The 60% acceptance criterion is unreachable, and the reason is not the
matcher.** Measured live on 2026-09-03:

| | count |
|---|---:|
| Superbet board in window | 4,041 events |
| — football | **150** |
| — tennis | 489 |
| — sports this pipeline does not read (esports, simulated football, …) | 3,402 |
| bzzoiro football fixtures in the same window | **29** |
| resolved by `resolve_board_to_reference` | **24** |
| = of the 29 available | 83% |
| = of the 150 offered | **16.0%** |

bzzoiro carries 28 football fixtures on Wednesday 2026-09-03 and 153 on Saturday
2026-08-30. The ceiling is the provider of record's midweek league coverage, not
our entry to the offer, and no amount of matching reaches a fixture the
reference provider has never heard of. Offer-driven discovery cannot widen this
slate; what it can do is **say so**, which is what shipped:

- `SuperbetOfferV1.unmatched_events` now records every board fixture in our
  sports that did not join, identity only, no extra request. Without it the
  question is unanswerable from the artifact — the 2026-09-03 offer file counts
  512 unmatched events and names none of them.
- `resolve_board_to_reference` is the join, pure and fixture-testable.
- The funnel prints in the coupon header.

Tennis is capped at LEAN with `NO_REFERENCE_SOURCE` on all 1,156 of its rows.
No OddsPapi requests were added. No nickname joins were attempted.

## Phase 8 — Results

- **Rung choice.** `p_shrunk × price − 1`, minus 0.05 for a line within one unit
  of the sample's mode and 0.05 for a sample that has already crossed the line
  (maximum above it for an UNDER, minimum below it for an OVER). It changed 53
  rungs on the re-run, and it picks the Grenal's `cards_points_total` **8.5**
  UNDER over 7.5 — the reversal the note asked for. The runner-up is printed as
  `alternative_line`.
- **Bet Builder.** Every leg must clear its own bar (was opt-in, now always when
  an offer is present): 6 legs below their bar → **0**. One leg per *mechanism*
  (discipline = cards + fouls, attacking, scoring, tennis length) rather than
  per market. Nested legs — a part inside its whole in the same direction —
  refused. §44 computed and refused below 0.60. 8 slips / 25 legs → 3 slips /
  6 legs, scoring 0.690, 0.696 and 0.729.
- `bet_builder_draft.py --offer` is now **required**; its availability gate had
  never run from that CLI.
- `build_coupons.py --refresh-offer` re-fetches the board and overwrites the
  artifact, keeping the old one on any failure.
- The header states the bar basis, the `k`s, which caps bound, every gate's row
  count, and the funnel.

## What was not done, and why

- **The card-points calibration table.** The metric is one day old and its only
  slate has not finished. See Phase 1.
- **`k` is not calibrated.** The measurement was run and reported; it cannot
  separate the arms on two slates. See Phase 3.
- **The referee blend weight `m/(m+20)` is unmeasured.** It is the note's
  number, isolated behind one named constant.
- **§44's tail-risk penalty.** It needs a scenario model this pipeline does not
  have. Inventing one to fill a term would be worse than a term short, so the
  score is capped by what is missing rather than inflated by it.
- **TIPSTERS was not re-run**, so the re-run's card rows carry no tipster
  column: the claim vocabulary moved to `cards_points_total` and the recorded
  signal artifact is filed under `cards_total`. Rerun-only; a live run
  classifies with the current code and joins.
