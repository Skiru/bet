# Working agreement — `bet`

This file describes the system **as it is now**: one pipeline, `sofa`, and one
coupon a day. It is not a changelog. A change to the rules edits the section
it belongs to; the story of how it got here lives in `docs/sofa/history/` and
in git.

## The pipeline: `sofa`

Sofascore statistics, Superbet prices, one coupon a day for every sport —
football, tennis, hockey, basketball, volleyball, CS2. The product of a day is
**`runs/sofa/<date>/KUPON_<date>.pdf`**, rendered from **`11_coupon.json`**.

```
BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON
                                          ↘ CONFIDENCE ─────────────┐
   SHADOW / CS2 → SPORT_IDENTITY → SPORT_CONFIDENCE ────────────────┤
                                   COUPON_ASSEMBLY (11_coupon.json) → PDF   ★ the product
   in a rebuild, before CONFIDENCE: FIXTURE_CHECK
   deliberately separate:           SETTLE → FIT
```

Source of truth for the order: `DEFAULT_SEQUENCE` in `scripts/sofa/run_pipeline.py`.
There is no other pipeline and no other coupon. Stage names like `DISCOVER`,
`ENRICH`, `ANALYZE`, `MARKET_CONTEXT`, `TIPSTERS` do not exist here; discovery
is BOARD, and it asks the bookmaker.

Reference (Polish): `docs/sofa/PIPELINE.md` every stage, field and gate;
`docs/sofa/RUNBOOK.md` the day's order and "what if"; `docs/sofa/AGENTIC_FLOW.md`
agents and hand-offs; `docs/sofa/CONFIG.md` config files and the refit loop.

### Artifacts of a day (`runs/sofa/<d>/`)

| file | what it is |
|---|---|
| `08_confidence.json` | football / tennis legs with confidence and gates; SETTLE's and the refit's input |
| `08_confidence_sports.json` | hockey / basketball / volleyball / CS2 legs (SPORT_CONFIDENCE) |
| `11_coupon.json` | **the coupon**; read it through `confidence.coupon_artifact()` |
| `KUPON_<d>.pdf`, `printed/<ts>.json`, `12_printed.json` | the product and its append-only print record (a rebuild locks from the first print) |
| `KUPON_<d>.html` | the same legs as a filterable page (time window in Europe/Warsaw, confidence, minimum x, sport, competition, market, odds, sortable; a start the FIXTURE_CHECK read differently is flagged; "rodzina na plusie" filter / tag and a button setting x >= 1 and a family on the plus, from `family_record.json`). A **view**, not a coupon - `bet.sofa.coupon_html`, written by `build_coupon_pdf.py` after every PDF render, so a rebuilt PDF always brings its HTML (HTML failure: PDF kept, exit 1); alone: `build_coupon_html.py --date <d>` |
| `family_record.json` | every family's (sport, market, direction) record on the official coupon's printed legs of the 14 days before (from 10-09), graded as the ledger grades; "on the plus" = >= 50 legs and units > 0 (`bet.sofa.family_record`, `build_family_record.py`, recomputed before each HTML when the ledger moved; a failure only hides the filter). The view's selection aid, never a gate: walk-forward 10-12..10-17 (windows of 3-8 days) x >= 1 and a family on the plus -0.6% [-4.8, +3.9] on 1,254 legs vs -4.5% for the rest, better on 6 of 6 days but pooled +4.0 pp [-0.3, +8.1] with 81% of its legs on 10-17 - advantage not yet shown, no proven profit (`docs/sofa/evidence/selection_walk_forward_2026-10-18.md`, `T-FAMILY-SELECTION`) |
| `13_results.json` | the settled result of every printed position (`bet.sofa.coupon_results`, the ledger's own grades - `record_results.graded_confidence`): outcome, won / lost / refund / unknown, the value the market counted, the match score. Written by `mark_coupon_results.py` (which `record_results.py` calls for every date it records); the day's PDF and HTML are then re-rendered from it (below, "Settlement") |
| `reads.json`, `vetoes.json`, `read_requests.json` | analysts' per-leg verdicts, vetoes, the operator's extra positions |
| `fixture_status.json`, `sport_fixtures.json` | FIXTURE_CHECK's fresh starts / statuses; the pinned Sofascore ids of sport games |
| `unmapped_prices/<ts>.jsonl.gz` | every OFFER run's prices of the markets it does not read (`bet.sofa.unmapped_prices`, from 2026-10-14) - a record for a later model's line evidence, read by nothing |
| `06_coupon.json` | the priced VALUE selector - **not the coupon** (2026-09-20: -20.4% vs the PDF's +8.2%) |

## How the coupon is built

**Confidence comes from the statistics; the price is only the condition for
the bet and may only lower a confidence** (from 2026-10-07 10:55Z). The
yardstick (operator): the statistics must tell a good 1.20 from a bad 1.20, in
every sport alike, and nothing that could win is cut by name.

### Confidence

- **Curves are fitted on the history** of events and statistics, replayed as of
  each match with the estimator SHEET prices with today (operator, 2026-10-07).
  Our own settled days are an audit of a curve, never its source.
  `config/sofa_confidence_calibration.json` (football / tennis) and
  `config/sofa_sport_confidence_calibration.json` (the four measured sports;
  a staged `.next.json` is read from its `effective_from`,
  `sport_confidence.calibration_path_for`) are the curves.
- SHEET keeps the price out of `p_central`. The rating is published beside it
  as `forecast_p` ("model", uncalibrated, never a gate). CONFIDENCE maps the
  statistics to a calibrated confidence through the curves.
- **Line evidence** (`bet.sofa.line_evidence`,
  `config/sofa_superbet_line_evidence.json`; from `LINE_EVIDENCE_FROM_UTC`
  2026-10-07 10:55Z): every key - football, tennis and the four measured
  sports - is also read through its own settled Superbet lines. The confidence
  is the lowest of
  - the history curve lowered by the key's **offset** (its measured
    realised-minus-confidence on printable lines; needs `MIN_OFFSET_ROWS` 50
    lines and `MIN_OFFSET_GAMES` 30 games, else the sport's pooled offset with
    `MIN_SPORT_OFFSET_GAMES` 20; never above 0), and
  - the **price-band cap**: what lines of the key at this `p` realised in this
    band of Superbet's price (`PRICE_BANDS`: 1.30 / 1.60 / 2.20; cell of
    `MIN_CAP_CELL` 20), applied only where measured below the confidence
    (operator, "krzywa per pasmo kursu"). A band cell without enough lines
    widens downward inside its band; with none, the key's own lines over every
    band from its `p` down (to 0.70) bound it.

  A key without a curve reads the Wilson bound of its own lines divided by the
  sport's measured design effect (`design_effect` in the evidence file; lines
  of one game are not independent) - from `BUCKET_DESIGN_EFFECT_FROM_UTC`
  (2026-10-14 00:00Z, audit A4) by its p bucket's own (`deff` the fit writes
  per bucket; 1 where every game gives one line; an older file reads the
  sport's; walk-forward log-loss -0.0351 [-0.0409, -0.0292],
  `docs/sofa/evidence/bucket_design_effect_2026-10-13.md`) - needs `MIN_EVIDENCE_BUCKET` 50 settled
  lines and `MIN_EVIDENCE_GAMES` 15 games in the bucket, else
  `NO_LINE_EVIDENCE`. The sport's pooled offset is measured without a key
  holding more than `CONCENTRATION_MAX` (50%) of its printable lines; this can
  **raise** another CS2 key's confidence (operator's choice). A CS2 fixture
  with no `best_of` is not guessed as best-of-3. Rules after
  `LINE_EVIDENCE_V2_FROM_UTC` (2026-10-07 13:42Z) are `LineEvidence.v2`.
  Legs carry `line_offset` / `price_band_cap` when lowered. The evidence is
  refitted every morning by `refresh_line_evidence.py` (it never touches a
  curve); the v2 rules need its `games` field - an older file reads nothing for a key without a curve.
  Evidence: `docs/sofa/evidence/discrimination_within_price_2026-10-07.md`.
- **Curves per line** (`LINE_CURVES_FROM_UTC` 2026-10-18 12:48Z - planned for
  10-19 00:00Z, moved by the operator into the built day: 10-18 is mixed,
  ledger group "10-18 mieszany", its legs printed before stay locked;
  `bet.sofa.line_curves`): a football curve is fitted per market
  x direction over the replay's whole line ladder, while Superbet quotes a
  few lines near the centre, and the model's p is not calibrated alike across
  lines (replay: goals_for UNDER 1.5 -2.4 pp on 305k rows, the far UNDER lines
  +1..+3 pp). For the 33 men's football keys of `config/sofa_line_curves.json`
  (chosen where the per-line curve beat the pooled one out of sample at
  Superbet's quoted lines with the interval below zero; 6 keys measured worse
  and stay pooled - the shots totals, goal_kicks_total OVER)
  `fit_confidence` writes `by_market_direction_line` and CONFIDENCE reads a
  leg's own line bucket first (`Calibration.realised(..., line=)`; source
  `line:<market>|<DIR>@<line>`), a line bucket under 400 rows the pooled curve
  as before; a class leg (women, season_early) is unchanged. Measured
  (`scripts/sofa/measure_line_curves.py`, train 2025-07..2026-03, test
  2026-04..10-12): log-loss at p >= 0.70 -6.4e-4 [-7.0, -5.8], mean |line gap|
  1.21 -> 0.92 pp; live offered rows 10-09..10-17 gap -1.09 -> -0.57 pp, ROI
  unchanged (-4.54% / -4.53%); E2E 10-18 +57 / -300 legs (player singles
  52 -> 41: shots OVER 1.5, which the pooled curve overstates -1.5 pp; a
  one-sided single reads `market:` or `line:`, `confidence.OWN_CURVE_SOURCES`),
  settled 10-15..10-17
  -599.0 -> -582.9 u. (dropped 167 legs -9.2%). A calibration fix, not an
  edge. The line evidence's base follows the --before day's latest build
  (`line_curves.day_reads_per_line`; refitted for --before 2026-10-18 at the
  switch: the football pooled printable gap -0.68 -> -0.45 pp, other sports'
  offsets unchanged). Installed 2026-10-18 12:04Z by
  `install_line_curves.py` (inert before the switch: 320,733 / 320,733 rows
  read alike without a line); backup `config/backup_2026-10-18_line_curves/`.
  Evidence `docs/sofa/evidence/line_curves_2026-10-18.md`, check `T-LINE-CURVES`.
- **Model packages** (switches in `bet.sofa.epochs`, all from 2026-10-07
  14:05Z, measured out of sample on the history,
  `docs/sofa/history/AUDYT_MODELI_2026-10-07.md`):
  `TENNIS_RATING_PRICES_FROM_UTC` (`games_won_for`, `handicap_games`,
  `most_games` - not its draw - priced by the rating alone, no price;
  `games_total` is the 50/50 mix of the NB and the rating);
  `DERIVED_MARGINAL_CENTRES_FROM_UTC` (football goals / corners /
  shots-on-target / cards joints built from the marginal rows' centres);
  `BB_FRESHNESS_FROM_UTC` (basketball simulation noise x1.085 when the thinner
  side has <= 2 games in 120 days, x1.026 for 3..9 - live forecaster and
  history replay alike). The history replay (`calibrate_from_cache.py`) is
  the estimator SHEET prices with, since the refit of 2026-10-13 (audit A6)
  including the football rating in the football marginal rows' centres
  (`--football-rating` with `--rated-scope --venue-prior --game-state
  --rating-weight --season-phase`) and the tennis set ratings
  (`--tennis-set-ratings`), and since the refit of 2026-10-14 the B15
  opponent correction (`--opponent-correction`), player markets on starts
  only (`--player-starts-only`) and the joints of cards_points / goals /
  corners / shots_on_target (`--derived`; their curves are fitted but not
  read - `DERIVED_CURVES_FROM_UTC` is off); still not replayed: the tennis
  tier / ladder priors, and men's friendlies (851; see "Switched on
  2026-10-14"). Tennis neighbours are
  `tennis_rating.AsOfRating` (best-of-five skipped); the set bases
  (`sets_total`, per-set games) are replayed for best-of-three matches only
  (`calibrate_from_cache.set_values`, `metrics.infer_best_of == 3`; fix
  2026-10-14: the night replay had written 6,688 `sets_total` 2.5 rows of
  Grand Slam best-of-fives, UNDER realised ~0), and SHEET refuses
  `sets_total` on a fixture not known to be best of three
  (`BEST_OF_FIVE_NOT_MODELLED`, `run_sheet.format_bound_refusal`); the
  best-of-five `games_total` / `games_won_for` samples of the replay are not
  format-scoped (open, measure before a fix). Hockey / volleyball / CS2
  curves are the installed sport file's (CS2's B10 curve promoted over it
  2026-10-14, bc69b56e); basketball's from 2026-10-14 the staged `.next.json`
  (A7, "Measured sports").
- **Installed model packages (refit installed 2026-10-08 23:42Z, commits
  5330f357 / fdbe0aae; switches ON from 2026-10-09 00:00Z, judged on the day
  built AND the build clock - a day < 10-09 is the old estimator and is never
  rebuilt under the new one):** `COUNT_DISPERSION_FROM_UTC` (football count
  spread from an alpha fitted on the history, NB per competition,
  `config/sofa_count_dispersion.json`, `fit_count_dispersion.py`; the normal
  with the pooled variance for `shots_total`; log-loss better on 52/52 markets
  out of sample; rows carry `dispersion_rule`; replay `--count-dispersion`);
  `TENNIS_SCOPED_TABLE_FROM_UTC` (rating neighbours from the tier x gender
  cell, tier, then pooled when a cell holds < 1200 outcomes, plus the tier
  start `lp_t`; games_total -81e-4 log-loss; `tennis_table_rule`; replay
  `--tennis-scoped-table`, fit `fit_tennis_rating.py --tier-start`);
  `PER_MARKET_K_FROM_UTC` (`K_CENTRE.by_market.football` in
  `sofa_engine_constants.json`: cards_points_for 25, fouls_total 2,
  shots_for 8, shots_total 5; goals stay at 15; `k_rule`; `--per-market-k`).
  `CARDS_CORRELATION_FROM_UTC` stays `None` (cards joints with side
  correlation +0.126, held in `epochs`; no `cards_rule`; the cards joints'
  curves are not read while `DERIVED_CURVES_FROM_UTC` is `None`): waiting for
  the operator. `COUNT_DISPERSION` and `PER_MARKET_K` are a pair (SHEET refuses,
  `epochs.require_k_with_dispersion`, exit 2, with only one on). A rebuild of
  a day >= 10-09 re-runs SHEET itself on a sheet without the markers
  (`rebuild_plan.py`). Measured preview on 2026-10-07 data: printing legs
  572 -> 634 (football 251 -> 269, tennis 321 -> 365; 47 of the 113 new legs
  tennis `games_won_for` UNDER), builders 11 -> 8. The line evidence was
  fitted on the OLD curves and is applied against the new ones until
  `refresh_line_evidence.py` refits it: the first mornings' offsets are noisy
  for the repriced families (`games_won_for` UNDER likely over-lowered;
  `goals_total` / `corners_total` possibly double-counted, conservative).
  Evidence: `docs/sofa/evidence/{count_families,tennis_calibration,
  dependence_goals,pooling,k_under_dispersion}_2026-10-08.md`; reports
  `docs/sofa/history/RAPORT_STAGED_REFIT_2026-10-08.md` and
  `RUNBOOK_INSTALL_2026-10-08.md`. The tennis `tier_start` offsets look ahead
  inside the replay (Elo at the cut), like the coefficients. A refit carrying
  these is `prepare_refit.py rebuild-cache-rows --confirm --without-db-backup
  --count-dispersion --per-market-k --cards-correlation --tennis-scoped-table`
  on the copy, with `fit_tennis_rating.py --tier-start`.
- **Refit of 2026-10-14 (football / tennis; installed 05:31Z by
  `prepare_refit.py install`, tests passed, backup `config/backup_2026-10-15`;
  10-14 was not yet built, so not a mixed day):** curves, engine constants,
  league baselines and reliability fitted on `data/refit_2026-10-14/sofa_replay.db`
  (121.9M rows, max settled run date 2026-10-12; 6,688 best-of-five
  `sets_total` rows deleted from the copy before the fit; `K_CENTRE` tennis 8,
  football 15). It supersedes the refit of 2026-10-13 18:06Z (10-13 mixed;
  `docs/sofa/history/RAPORT_REFIT_2026-10-13.md`). The centre the curves
  describe is on (audit standing go):
  - since 2026-10-13 18:10Z: `GAME_STATE_FROM_UTC` (B1: side centre x
    exp(beta x expected goal difference), `config/sofa_game_state.json`;
    betas refitted on the live centre and installed 2026-10-13 20:57Z,
    df5323ea: corners_for 0.129 -> 0.0986, shots_for 0.0974 -> 0.0506,
    cards_points_for -0.0845 -> -0.0664, fouls_for kept - its refit was
    +0.000031 worse; `docs/sofa/evidence/game_state_2026-10-13.md`),
    `FOOTBALL_RATED_SCOPE_FROM_UTC` (B2: the rating also on
    `football_rating.RATED_SCOPE_MARKETS` = cards_points_for, corners_1h/2h_for,
    offsides_total; corners totals stay unrated, corners_total worse +0.0009
    [+0.0003, +0.0015]), `FOOTBALL_VENUE_PRIOR_FROM_UTC` (B2: league home / away
    multiplier on a sample-only corners_1h/2h_for centre;
    `unrated_markets_2026-10-13.md`), `FOOTBALL_RATING_WEIGHT_FROM_UTC` (B14:
    the rating's weight per market from `config/sofa_rating_weight.json`, else
    `W_FOOTBALL_RATING`; `rating_weight_2026-10-13.md`),
    `SEASON_PHASE_FROM_UTC` (C1: goals centre x exp(c[market][phase]),
    `config/sofa_season_phase.json`; `season_phase_2026-10-13.md`),
    `TENNIS_SET_RATING_PRICES_FROM_UTC` (B5: per-set games and sets_total from
    the rating's neighbours; `tennis_set_markets_2026-10-13.md`);
  - from 2026-10-14 05:45Z: `SAMPLE_OPPONENT_CORRECTION_FROM_UTC` (B15 with
    A5, `bet.sofa.opponent_correction`: a football side's sample rescaled to a
    neutral opponent, x / def(opponent), and to today's league domain before
    SHEET's centre - goals and players excluded - and CONFIDENCE's shape gates
    / MODEL_ABOVE_OWN_SAMPLE reading the corrected values, `corrected_sample`
    and `opponent_rule` on the row; calibrated log-loss better on 12 of 18
    corners / shots / fouls markets with the interval below zero, none worse,
    e.g. shots_for -1.96e-3 [-2.38, -1.56], cross-league pairs 3-4x that;
    `docs/sofa/evidence/sample_opponent_correction_2026-10-13.md`). SAMPLES
    writes `opponent_id` only from 2026-10-13 evening: an older sample is not
    corrected, so B15 acts from 10-14's SAMPLES on (not yet observed live).

  The starts-only player curves are in the installed file
  (`config/sofa_confidence_calibration.next.json` removed at the install -
  promoted; its copy in the backup); `match_won_for` (tennis winner) is
  re-merged after the fit (from 2026-10-16 `fit_confidence` carries it itself, `fit_meta.carry_separately_fitted_curves`). Dry run (10-13 morning
  artifacts, 10-14 switch set, new curves): printed singles 1323 -> 1296;
  football / tennis stable (common legs' confidence +0.04 pp mean, 0.3 pp
  absolute); basketball totals / handicaps / team totals 0 (A7); hockey and
  CS2 unchanged; B15 corrected no row (old samples). SHEET stamps the
  centre switches on the rows they apply to (`epochs.*_MARKER`:
  `game_state_rule`, `rated_scope_rule`, `venue_prior_rule`,
  `season_phase_rule`, `rating_weight_rule`, `opponent_rule` on football
  rows, `tennis_set_rule` on tennis rows; absent when off), and
  `rebuild_plan.py` re-runs SHEET when one is on for the day and clock and a
  row of its sport lacks it (a sheet without that sport never re-runs).
  Every row also carries `config_sha` (`bet.sofa.sheet_config`: the fitted
  files SHEET reads); a sheet priced on other constants gets a
  `CONFIG_CHANGED` note but is **not** re-run (an install is undated and
  never goes into a built day without a go - then `run_pipeline.py --only
  SHEET` by hand); curves need nothing, CONFIDENCE reads them on every
  rebuild. Report: `docs/sofa/history/RAPORT_NOC_2026-10-13_14.md`.
- **Switched on 2026-10-14 00:00Z** (operator 2026-10-13, "Wszystkie rynki
  włączone"; plan `docs/sofa/history/PLAN_NOC_2026-10-13.md`):
  `TENNIS_MATCH_WINNER_FROM_UTC` (D2: OFFER reads "Zwycięzca" as one two-sided
  rung `match_won_for`, SHEET prices it from the as-of rating alone,
  CONFIDENCE reads only its own curve, `bet.sofa.tennis_winner`; skill
  -0.1263 [-0.1303, -0.1228] log-loss vs the class base rate; the curve's
  calibration threshold was not met, every miss on the cautious side,
  >= 0.70 printed 0.802 vs realised 0.828 on the holdout;
  `docs/sofa/evidence/tennis_match_winner_2026-10-13.md`),
  `MAPPABLE_FAMILIES_FROM_UTC` (OFFER also reads the MAPPABLE families of
  `bet.sofa.market_coverage`: "<club> strzeli gola" and halves as
  goals_*_for 0.5, "Zostanie rozegrany N. set" as sets_total N-0.5, half
  BTTS, both-over saves, half corner / set games handicaps -
  `market_mapper.classify_mappable_family`; a yes/no answer never adds a
  second rung where the ladder quotes one; E2E on 10-13's samples clean
  on / off, the bridge leg untested - Sofascore 403;
  `docs/sofa/evidence/mappable_e2e_2026-10-14.md`),
  `MEN_FRIENDLY_SAMPLE_WINDOW_FROM_UTC` and `MEN_FRIENDLY_BASELINE_FROM_UTC`
  (`bet.sofa.men_friendly`; SAMPLES: an 851 fixture's pool also admits the
  sides' 851 matches and goals_total / goals_for read variant C - every pool
  match since the oldest of the newest ten 851 matches; SHEET: its goals
  prior is the as-of mean of 851 matches, 2.54 over 2,365, goals_for half,
  >= 30 matches, note `PRIOR_MEN_FRIENDLY`, no row marker - on mid-day,
  re-run SHEET by hand; C - D with the as-of prior goals_total -0.0071
  [-0.0127, -0.0015], goals_for -0.0140 [-0.0196, -0.0086]; women's 852
  unchanged; `docs/sofa/evidence/national_friendly_samples_2026-10-13.md`).
  The curves were fitted without 851 (the replay never puts an 851 match in
  a side's history, `fit_meta.friendly_exclusion_sql`): an 851 fixture reads
  the competitive matches' curves as an approximation.
  `PLAYER_TEAM_FROM_SIDE_FROM_UTC` and `MARKET_POSITIONED_LINES_FROM_UTC`:
  "Measured sports".
- **Wait for a measurement, not a name:** a market with no curve and no
  evidence is `NO_LINE_EVIDENCE`. Before `LINE_EVIDENCE_FROM_UTC` (rebuilds of
  older days only) the by-name refusals still apply: `refused_markets`,
  `admitted_player_markets`, `admitted_tennis_set_markets` in the football /
  tennis calibration (carried over by every refit),
  `DERIVED_NOT_CALIBRATABLE`, and the sports' `admitted` keys.

### What prints

- **A leg prints** when confidence >= 0.70, confidence x odds >= 0.90, ladder
  (group) margin <= 15% (`COUPON_PROFILE`), not ODDS_TOO_LOW, not started,
  fresh price (STALE_PRICE otherwise; a moved price re-prices the leg). Every
  passing single prints - no page limit.
- **Refusals worth knowing** (each named on the row):
  - `CROSS_LEAGUE_UNLINKED`: football ratings compare leagues only through a
    measured league strength; a pair is LINKED only when both sides' leagues
    are the competition they share (`LINK_SHARED_LEAGUE_FROM_UTC`, 2026-10-07
    06:45Z; the hockey / basketball / volleyball score model reads the same
    book; sheet rows carry `link_rule`, a rebuild re-runs SHEET on an
    old-rule sheet). A promoted side is cross-league until its new league is
    its modal one;
  - women's football, women's tennis and tennis team cups read only their
    class's curves (`NO_CLASS_CURVE`);
  - `NOT_SETTLEABLE`: (competition, family) cells in `config/sofa_settleability.json`;
  - K13 / K13b: a thin direction bucket caps the curve; a pooled read is capped
    by the market's nearest own bucket below;
  - `SAMPLE_CROSSES_SEASON` (180 days; `MAX_BUILDER_SAMPLE_AGE_DAYS`) - except
    national-team fixtures, judged by count (`NATIONAL_SAMPLE_AGE`);
  - CS2 team-rounds line outside 9.5-12.5: `LINE_OUTSIDE_FIT`;
  - a football player leg: Superbet quotes player props on the OVER side
    only, so the ladder has no overround and the 15% margin rule cannot
    judge it. From `ONE_SIDED_SINGLES_FROM_UTC` (2026-10-12 00:00Z, operator)
    such a leg (`one_sided_market`) prints as a single when its confidence is
    its own market's history curve with n >= 300 (`confidence.one_sided_single`;
    PDF margin column "1-str."); every other gate applies. Measured before:
    49 would-print legs of 10-05..10-10, ROI -10.3% [-27, +4] vs -3.0% for
    team legs (`docs/sofa/evidence/player_starts_2026-10-11.md`) - an open
    check on new data, not a proven edge.
  - a football player row and the sample-shape gates
    (`PLAYER_SAMPLE_GATES_FROM_UTC`, 2026-10-17 00:00Z, operator 2026-10-16):
    a footballer's sample is his starts in his team's last 10 matches (5-10
    values), so THIN_SAMPLE_FOR_BUILDER (< 10) admitted only a player with
    10/10 starts and LINE_BEYOND_SAMPLE refused OVER 0.5 for one who never
    blanked (10-15: of 57 player legs clearing curve, line evidence and x at
    the sheet's price 54 were refused - 45 on the six markets below; 5
    printed, 2 of them clearing x only at a fresh price). From the switch a
    row on one of `confidence.PLAYER_SHAPE_GATE_MARKETS` (shots, shots on
    target, fouls, tackles, assists, offsides - not the /shotmap shot-detail
    markets, their own estimator, nor interceptions, no curve; unmeasured)
    needs only
    `PLAYER_MIN_SAMPLE` (5) values - the replay's floor its curve was fitted
    on; age, curve, line evidence, floor and x unchanged; a leg a shape gate
    would have refused carries `player_sample_rule` = the first such gate in
    CONFIDENCE's order and never joins a builder. Measured: history OVER, the
    refused groups realise on their curve (+0.5..+1.5 pp; all together ~0.4
    pp below the passing ones, LINE_BEYOND -0.9 [-1.8, +0.1], 5 starts -1.9
    [-2.9, -0.8] vs PASS) - the gates select slightly, they do not protect
    the printed number; Superbet's lines 10-12..10-15 with line
    evidence 55 legs / 37 matches -5.9 pp [-15.9, +4.5], ROI -11.7% [-23.8,
    +1.2] (curve in sample; at the price, no edge); a player offset on
    x >= 0.90 lines only was measured and declined. E2E 10-15 (clean copy,
    clock 12:59Z, so started matches out): +40 player singles (22
    LINE_BEYOND, 18 THIN), 0 legs lost or changed, builders identical;
    report `docs/sofa/history/RAPORT_BRAMKI_ZAWODNIKOW_2026-10-16.md`
    (`docs/sofa/evidence/player_sample_gates_2026-10-16.md`,
    `player_line_evidence_2026-10-16.md`; check on new data
    `T-PLAYER-SAMPLE-GATES`).
- **Player names** (`PLAYER_NAME_TOKENS_FROM_UTC`, 2026-10-12 00:00Z): a
  footballer `players.match_player` finds in no squad is looked for by whole
  name tokens (`match_player_by_tokens`: >= 2 shared, one candidate, one
  side) - Superbet writes full registered names ("Andrade, Matheus Araujo"
  vs "Matheus Araujo"; 346 of 680 `NO_ENTITY_FOUND` players of 10-08..10-10).
  The sample says `match_rule: "tokens"`, the sheet row `PLAYER_NAME_TOKENS`.
  Evidence: `docs/sofa/evidence/player_name_tokens_2026-10-11.md`.
- **Player surnames** (`PLAYER_NAME_SURNAME_FROM_UTC`, 2026-10-14 11:30Z,
  identity plan K7): a footballer neither `match_player` nor the token rule
  finds is looked for by whole surname + a first-name prefix of >= 3 letters
  (`players.match_player_by_surname`: Benjamin Joshua Chrisene / Ben
  Chrisene, Treymaurice Nyoni / Trey Nyoni), one candidate on one side. On
  10-12..10-14: 1,827 / 1,827 matched players picked the same person (a
  shared initial only: 6 wrong), 22 new players. `match_rule: "surname"`,
  sheet note `PLAYER_NAME_SURNAME`; SETTLE grades its `matched_name` like a
  token match.
- **Player starts** (operator, 2026-10-11): Superbet voids a footballer's
  market unless he STARTS. SETTLE says `PLAYER_NOT_STARTED`; from
  `PLAYER_STARTS_ONLY_FROM_UTC` (2026-10-12 00:00Z) the sample is his starts
  (`appearances: "starts"`, note `PLAYER_STARTS_ONLY`; bucket-calibrated out
  of sample -0.0027 log-loss [-0.0030, -0.0024] against all appearances) and
  the player curves are fitted on starters' outcomes from their starts -
  since the refit of 2026-10-14 in the installed
  `config/sofa_confidence_calibration.json` itself (the replay ran with
  `--player-starts-only`; the staged `.next.json` that carried them since
  2026-10-12 was removed at the install, its copy in `config/backup_2026-10-15`).
  Evidence: `docs/sofa/evidence/player_starts_2026-10-11.md`.
- **Start clock** = the earliest of RESOLVE's clock, Superbet's start signal
  (`superbet_started_utc`, `superbet_kickoff_seen_utc`; in-play odds are
  dropped for every reader) and FIXTURE_CHECK's fresh `/event` start. A
  postponed / cancelled printed match is FIXTURE_NOT_AS_SCHEDULED; no bridge =
  UNVERIFIED, nothing refused. A transient error on one fixture (bridge
  504 / timeout, 5xx) is retried once, then that fixture alone is
  UNVERIFIED and the check goes on; a refusal (403 / 429, breaker open or
  tripped) or two fixtures in a row given up on stops it. Blind spot: a suspended pre-match offer with no
  metadata says nothing; only the clocks see it.
- **Peer choice and stakes** (from `PEER_CHOICE_FROM_UTC` 2026-10-08
  08:10Z, operator: "jak masz dwie nogi po 1.2 to zaproponuj tę z większą
  pewnością"; 10-08 is a mixed day; **annotation only** - no leg is added,
  removed or re-ranked, no confidence moves): two legs of one match on
  different variables priced within `PEER_BAND` 0.06 are peers
  (`bet.sofa.peer_choice`); the surer by confidence is starred (★ on the PDF,
  `peer.preferred`), a weaker one names it. The edge is measured and small:
  of 57,791 decided pairs (football / tennis, 20 days) the more confident leg
  won 53.4% [52.2, 54.7]; **no** sample statistic (hit rate, size, near
  misses, margin, venue, last 5), tournament metadata (popularity, reserve /
  women / cup / national) or its combination improved the confidence out of
  sample; hockey / basketball / volleyball show no measurable edge. Tournament
  rank and sample depth therefore do not re-rank peers. Match **stakes**
  (`bet.sofa.stakes`: `STAKES_SIX_POINTER`, `STAKES_TOP4`, from the football
  history's league table as of the kickoff) are a context flag on the leg with
  the direction of the measured effect (six-pointer: +0.2 cards, +0.9 fouls,
  -0.15 goals, -1.0 shots per match, 0.08-0.16 sd; top-4: +0.2 cards, -0.2 goals; not corrected
  for the weakness of relegation-zone clubs): shown, never gated, never a
  correction. Evidence: `docs/sofa/evidence/peer_choice_2026-10-08.md`
  (`scripts/sofa/measure_peer_choice.py`); pre-registered check on new data:
  `T-PEER-CHOICE-edge`.
- **Confidence above the price** (`PRICE_GAP_FLAG_FROM_UTC` 2026-10-12
  11:51Z, moved by the operator to the day's rebuild - 10-12 is a mixed day;
  **annotation only**): a football / tennis leg
  whose confidence exceeds 1/odds by more than `GAP` 0.03 carries `price_gap`
  (`CONFIDENCE_ABOVE_PRICE`, `bet.sofa.price_gap`) and a sentence on the PDF /
  HTML / md. Measured on the printed legs of 10-09..10-11: such legs realised
  below their confidence, about at their price - football 458 legs / 269
  matches -6.8 pp [-12.0, -2.1], tennis 52 / 35 -18.6 pp [-31.0, -5.9]; the
  rest calibrated (+0.3 pp); same sign every day 10-07..10-11. Their ROI was
  not measurably worse, so it is the printed number that over-promises (what
  a slip of several legs multiplies), not the singles' money. The measured
  sports carry no flag (measured the same way: hockey's 32 over-price legs
  -1.2 pp [-15.1, +11.9], i.e. none; basketball overstated on both sides of
  the price alike, -15 / -18 pp on 52 / 50 legs - a curve question, not a
  price one; volleyball / CS2 too few). Evidence:
  `docs/sofa/evidence/price_gap_2026-10-12.md`
  (`scripts/sofa/measure_price_gap.py`); check on new data `T-PRICE-GAP-flag`
  PASSED 2026-10-19: 10-13..10-18 football 2,111 flagged legs / 932 matches
  -10.0 pp [-12.8, -7.4] (hit 0.696 at mean 1/odds 0.734), the rest -0.9 pp;
  ROI alike (-5.1% / -5.5%). Of four other red flags measured the same week
  (`scripts/sofa/measure_red_flags.py`,
  `docs/sofa/evidence/red_flags_2026-10-19.md`) none adds to it: a long
  price at a confidence just above 0.70 is `price_gap` itself, confidence
  above the own sample's k/n and builders nothing, a leading favourite's
  shots / corners OVER too few legs (`T-RED-FLAG-SCRIPT`, from 10-20).
- **Bet Builders:** one per fixture, by best `combined_probability`; an
  internal haircut x >= 0.90 decides stakeable and is never printed. **sofa
  does not price a builder**: the PDF shows its legs with Superbet's single
  prices, the combined p and "kurs buildera: sprawdź na ekranie Superbetu". A
  screen price the operator records in `09_screen_prices.json` is shown back
  as his note.
- **Assembly** (`build_coupon.py`): order by confidence, then earlier start,
  one match's legs together; legs locked from an earlier print come first,
  unnumbered; builders B1.. on their own pages; ladders under "ta sama
  zmienna"; an exposure-per-match section. A leg printed before its start
  stays (locked); a leg removed before its start stays removed.
  `ladder_form` / `max_positions_per_match` are OFF unless
  `config/sofa_coupon_form.json` sets them (operator's call).
- **Superbet's words** (`bet.sofa.superbet_names`, display only, no leg
  changes): every leg of `11_coupon.json` carries `superbet_market` /
  `superbet_selection` as the screen writes them ("3. tercja - Seattle
  Kraken - liczba goli" / "poniżej 1.5"; a handicap as "Seattle Kraken
  (1.5)", the side's own number), names read from Superbet's live offer
  2026-10-16, a football / tennis side in the board's spelling
  (`board_sides`); a market it does not know keeps its old label, nothing
  guessed. The PDF's "rynek" column prints it with the selection in bold
  (the "linia" column says pow. / pon.), the peer notes and the "ta sama
  zmienna" headers name legs the same way, and the HTML's market column is
  it. COUPON_ASSEMBLY stamps it; the PDF / HTML stamp an older artifact at
  render. Why: 2026-10-15 a chat slip wrote "Seattle +1.5 w 3. tercji"
  (a period handicap) and the bet placed was the market beside it, Seattle's
  period goals under 1.5 @1.21.
- **Reads:** analysts read the first 30 unlocked positions (from 2026-10-09 00:00Z the unit is the match: every unlocked leg of the first 30 matches of the coupon, `read_unit: "event"` in the artifact; operator, "30 wydarzeń, nie 30 rynków"; from `READ_BY_VALUE_FROM_UTC` 2026-10-14 00:00Z the 30 matches are those of the best value - the best unlocked leg's confidence x odds, a football / tennis confidence capped at 1/odds + `price_gap.GAP`, `confidence.read_value`, `read_order: "value"`; operator 2026-10-13), every printed
  builder leg and whatever is in `read_requests.json`
  (`confidence.legs_requiring_read`, `READ_REQUIRED_SINGLES`; audit C3 checks
  it; a rebuild moves positions, so re-read until C3 is clean); the rest
  prints unread. WATCH or NO_BET in `reads.json` - or the automatic football
  `MODEL_ABOVE_OWN_SAMPLE` (model - own sample hit rate >
  `MAX_OWN_SAMPLE_GAP` 0.15, props excluded) - moves a leg to
  `removed_by_reads`, graded on its own, never in the coupon's result.
  `context_flags` (`MAKEUP_FIXTURE`, `LONG_LAYOFF`, `CONGESTED`) are shown,
  never gated.

### Measured sports (hockey, basketball, volleyball, CS2)

SHADOW / CS2 snapshot Superbet -> SPORT_IDENTITY pins the Sofascore id before
the start (an event not identified by its start keeps its last pre-start
record, `frozen_at_start`, and is not asked again) -> SPORT_CONFIDENCE reads the sport calibration (fitted without
prices) and corrects it with line evidence. SHADOW / CS2 themselves stay a
measurement of Superbet's price and feed nothing else.

- **Entity map** (identity plan K1, `bet.sofa.entity_map`; reads from
  `ENTITY_MAP_FROM_UTC` 2026-10-14 11:30Z, day and clock): after writing
  `sport_fixtures.json` SPORT_IDENTITY teaches `sofa_entity`, once per
  Sofascore event (`sofa_entity_taught`). A side its own name confirmed
  (`entity_map.NAME_METHODS`, score > 82) is a `verified` row with
  `source = identity_names` and `evidence_event_id`; a side only the
  opponent rule confirmed is a NEEDS_ALIAS candidate
  (`sofa_entity_candidate`), never an identity; a held name offered another
  id is queued (`sofa_entity_conflict`) and from the switch never
  overwritten - `cache.save_entity` (RESOLVE, SHADOW_SETTLE) follows the
  same rule. Tournaments go to `sofa_tournament_map` (football / tennis from
  RESOLVE, keyed `id:<superbet tournament id>`; read by nothing yet). Learned
  rows are read by `TeamResolver`, `player_model.resolve_team` (rows by name
  carry `entity_map_rule`) and `cache.get_entity` only from the switch; CS2
  reads learned rows only, never backfill_cs2's own (one holds "Ninjas in
  Pyjamas" as NIP Impact 448738 - queued). Backfill of the days on disk:
  `backfill_entity_map.py` (2026-10-14 09:39Z: 477 new names, 0
  contradictions, 2 CS2 conflicts, 71 candidates; backup
  `data/backup_entity_map_20261014T093901Z/`). Measured direct gain: 32
  not-identified events in 10 days had a side learned from an earlier game;
  the rest of the plan (K2 day anchor) needs these ids.
  `docs/sofa/history/RAPORT_K1_MAPA_ENCJI_2026-10-14.md`.
- **Manual decisions** (identity plan K4): `config/sofa_entity_aliases.json`
  (`aliases`: the Superbet name IS this id; `rejected`: NOT this candidate;
  sport, superbet_name, sofascore_id, decided_by, decided_at, evidence) is
  applied by every SPORT_IDENTITY run (`entity_map.sync_manual`, from
  `ENTITY_MAP_FROM_UTC`): an alias is held with `source = manual`, replacing
  a held id, and closes that name's conflicts / candidates. The queue to
  decide from: `report_entity_queue.py --date <d>` ->
  `runs/sofa/<d>/entity_queue.md` (2026-10-14: 55 candidates; the 2
  conflicts decided - NIP = 366560, Golden Horde = 1272785 "The Golden
  Horde"). Fuzzy matching never writes the file. Polish
  country names were already in `sofa_name_aliases.json`; the national teams
  still unresolved (Jordania, Kuwejt...) play tournaments Sofascore does not
  list (K5).
- **Day anchor** (identity plan K2, `DAY_ANCHOR_FROM_UTC` 2026-10-15
  00:00Z; hockey / basketball / volleyball, not CS2, not tennis): with no
  listed game on both names, the anchor team's (a side's resolved id) ONLY
  game within the hour (sport, gender, not postponed) is the event, whatever
  the other name says (`match_method: "DAY_ANCHOR"`); two such games
  AMBIGUOUS, the other side's own id missing RESOLVED_ID_DISAGREES; the
  opponent's name is only a candidate, never learned. Backtest with the
  opponent hidden (`measure_day_anchor.py`, ids as at identification, newest
  fetched version of each game): 1,578 / 1,578 IDENTIFIED picked right, 79
  settle finds agreed, 0 contradicted; live gain the NO_MATCH_IN_LISTING
  events (12 in 10 days; replay on 10-13/14 caches: 8). Window stays 1 h.
  Open: BC Barcelos (K) - Francisco Franco (K) is Sofascore's BC Barcelos -
  CAB Madeira. `docs/sofa/history/RAPORT_K2_DAY_ANCHOR_2026-10-14.md`.
- **Tournament day, proven absence** (identity plan K3 / K5, both from
  2026-10-14 11:30Z): an event NEITHER side of which has an id is matched by
  both names inside its tournament's games of the day
  (`TOURNAMENT_DAY_FROM_UTC`; `bet.sofa.day_listing`,
  `unique-tournament/<ut>/scheduled-events/<d>` through the entity map's
  tournament map, cached in `sofa_day_listing`; weaker side >= 60, lead >= 20;
  95 tournament-days: 284 / 284 IDENTIFIED right with ids hidden, 24 of 42
  targets, 15 settle-confirmed, 0 contradicted). A `NO_GAME_WITHIN_1H` read
  from a cached page (6 h TTL) within 3 h of the start is asked once fresh
  (`NOT_ON_SOFASCORE_FROM_UTC`), and only a fresh page of an id-resolved team
  with no game within 12 h is `reason: "NOT_ON_SOFASCORE"` (still
  NOT_IDENTIFIED, still re-asked, `absence_evidence`); a game 1-12 h away
  keeps NO_GAME_WITHIN_1H with `nearest_game_h`. Until 10-12 most
  NO_GAME_WITHIN_1H were games asked after their start (fixed 10-12,
  `frozen_at_start`). BRIDGE_ABORTED is refusal periods (10-09 504 tab, 10-13/14
  night 403), re-asked every 30 min: no code change (K6).
  `docs/sofa/history/RAPORT_K3_K7_TOZSAMOSC_2026-10-14.md`.
- **History is kept current by `refresh_sport_history.py`** (bridge;
  `bet.sofa.sport_history`, run first by `refresh_line_evidence.py` every
  morning): SPORT_IDENTITY asks listings before the game, so until 2026-10-12
  a game's result never entered the hockey / basketball / volleyball history
  (10-07..10-11: 0-30% of the settled games; the live model and the line
  evidence stopped on 10-04). It asks `/event/{id}` once for every game that
  should have ended and indexes it. `day_status.py` `sport_history` WARNs
  below 80% of D-1's pinned games. Measured 2026-10-12
  (`measure_sport_history_ab.py`, lines of 10-05..10-11): a week's ~500 games
  moved the model's log-loss by nothing measurable (hockey -0.45e-3
  [-1.86, +0.98], basketball +1.11e-3 [-1.63, +3.83]); its gain is the
  evidence's coverage (volleyball 5,318 -> 8,474 settled lines).
- **League rate** (`LEAGUE_RATE_RULE_FROM_UTC` 2026-10-14 00:00Z, audit A2,
  operator O1 - a correctness rule, switched on by that decision; the
  measurement was too small to tell, 17 would-print lines in 16 games): a
  hockey / basketball / volleyball game that `comparability.is_friendly_event`
  calls a friendly / pre-season is `FRIENDLY_FIXTURE` (football's rule), and a
  game in a competition below `MIN_LEAGUE_MATCHES` (30) has no model p
  (`NO_LEAGUE_RATE`) - never the all-league mean (NBA Preseason read 82.8
  points a side). No fallback to the home league. The line-evidence replay
  (`settled_shadow_rows`) applies the day's rule. A plain basketball curve
  refitted with it was not installed (on Superbet's lines of 10-05..10-12
  confidence log-loss -0.00042 [-0.00145, +0.00063], the printable gap
  -16 pp unchanged; `docs/sofa/evidence/basketball_refit_2026-10-13.md`);
  the A7 curve below was. Football's half
  (`FOOTBALL_LEAGUE_RATE_RULE_FROM_UTC`) is measured worse and stays `None`.
- **Basketball curve on market-positioned lines** (`MARKET_POSITIONED_LINES_FROM_UTC`
  2026-10-14 00:00Z, audit A7, standing go; the curve staged in
  `config/sofa_sport_confidence_calibration.next.json`, `effective_from`
  2026-10-14, bc69b56e): the history curve is fitted on lines placed where
  the Sofascore market stood (`data/a7_odds/basketball.jsonl`), p still the
  score model's. Log-loss -0.0622 [-0.0702, -0.0546] on 41,414 Superbet lines /
  651 games of 10-05..10-12. At the market's line the model's p up to 0.70
  realises 0.47-0.53, so totals / handicaps / team totals (old curve ~0.77,
  realised 0.618) land in buckets with n < 200 and stop printing (dry run:
  0 such legs). The A7 cache (`data/a7_odds/`) covers every target since
  2026-10-15 (basketball 26,536 asked: 5,910 with line markets, 5,943 not on
  Sofascore; the 10-14 curve was fitted on the 40% asked by 10-13; the
  whole section refitted on the full cache is worse, +0.00034 [+0.00001,
  +0.00068] on 56,740 Superbet lines of 10-05..10-14, printable gap -12.9 ->
  -16.4 pp, and was not installed; its five A7 keys alone (total, handicap,
  team total - 50,360 market-line rows, buckets >= 0.70 realise 0.56-0.65,
  never a printable confidence) replaced those of the staged section at
  2026-10-15 11:29:38Z (operator, "WŁĄCZ JUŻ DZISIAJ"; every other key the
  10-14 fit's, `fitted_from.a7_families_refit`): -0.00123 [-0.00151,
  -0.00096], printable lines and the 10-15 E2E unchanged, so no mixed day;
  backup `config/backup_2026-10-15_bb_a7_hybrid/`;
  `basketball_a7_full_2026-10-16.md`); hockey's 16,484 games
  were asked the same day (6,950 with the "Match goals" total, no spread
  published). Hockey A7 is measured and **not switched on** (operator
  2026-10-15): `parse_lines` reads "Match goals" (it settles with overtime;
  only its position is read, graded as the regulation total 623), the replay
  puts hockey's total alone on it, handicap / team totals stay synthetic, and
  a fit reads the hockey cache only with an explicit `--market-lines`
  (`sport_confidence.MARKET_LINE_DEFAULT_SPORTS`). Log-loss -0.0055
  [-0.0072, -0.0039] vs a synthetic refit, all of it on totals, but the
  model never reaches 0.70 at the market's line: the 382 printable total
  lines of 10-05..10-14 (Superbet's ladder, calibrated today: -0.4 pp
  [-5.0, +4.0]) would read nothing (`hockey_a7_2026-10-16.md`). Overtime (A3,
  `BB_OVERTIME_FROM_UTC`) stays `None`: +0.00113 [-0.00123, +0.00353].
  `docs/sofa/evidence/basketball_refit_2026-10-13.md`,
  `market_positioned_lines_2026-10-13.md`.
- **Hockey / volleyball / CS2 curve refits** for 2026-10-14 were measured and
  kept out (`docs/sofa/evidence/sport_refit_2026-10-13.md`; Superbet lines
  10-05..10-12): CS2 -0.00008 [-0.00030, +0.00015], hockey +0.00151
  [+0.00105, +0.00200] worse, volleyball -0.00032 [-0.00175, +0.00120].
  Volleyball overstates ~16 pp at confidence >= 0.70 with either curve
  (-15.4 pp [-24.4, -6.8] new) - like basketball, a curve / line-evidence
  question, open.
- Every fitted key of all four prints on the same rules as football and
  tennis. Volleyball still needs a tournament with a settled event in the
  last 14 days. A sport without a usable calibration is `NOT_CALIBRATED`
  (exit 1, the rest still builds).
- `sport_confidence.EXTENDED_MARKETS`: basketball quarters, second half, dnb,
  odd/even; hockey period dnb (score model, from the history). Volleyball adds
  exact set score, points / set parity, "set on extra points". CS2 adds
  `CS2_EXTENDED_FAMILIES` (map round handicap / total, team kills, player
  kills / deaths / assists / headshots; box-score families graded from
  CS2_SETTLE's own row) and the series families (maps_total, maps_handicap,
  team_maps, exact_maps) from a Beta-mixed series distribution
  (`cs2_engine.SERIES_KAPPA`). From `CS2_TEAM_ROUNDS_RACE_FROM_UTC`
  (2026-10-13 18:10Z, audit B10; moved by the operator from 10-14 00:00Z to
  the refit's rebuild of 10-13) a team's rounds on a map come from the round
  race (`cs2_engine.team_rounds_from_race`, the map's score distribution the
  round handicap uses), live, at CS2_SETTLE and in the replay; walk-forward
  log-loss -0.0213 [-0.0237, -0.0188]; the CS2 curve refitted on it is staged
  in the `.next.json` from 2026-10-13 and promoted over the installed file
  on 2026-10-14 (bc69b56e). CS2 series rounds (rounds_total,
  rounds_handicap, team_rounds) are priced from `CS2_SERIES_ROUNDS_FROM_UTC`
  (2026-10-15 00:00Z; `cs2_engine.series_rounds_side_p`: maps won from the
  mixed series distribution, each map's rounds from the race) with their
  history curves installed 2026-10-15 00:17Z ("New-market curves" below;
  the operator installed them despite the warning: three keys pass the gate
  on the history ladder, but at Superbet's own lines 21 sides / 19 series
  realised 0.33 at 0.74; `docs/sofa/evidence/cs2_series_rounds_2026-10-15.md`,
  `T-CS2-SERIES-ROUNDS-superbet`); round parity is still unpriced.
- Hockey / basketball player lines: p = player_model's pre-game number in
  SHADOW's `player_model.jsonl` (reads SPORT_IDENTITY's pinned teams before
  names, `teams_source`); no history curve, so `NO_LINE_EVIDENCE` until a
  family's p bucket holds 50 settled pre-game lines; graded from
  SHADOW_SETTLE's own player row (a name `match_player` misses is looked for
  by football's token and surname rules, then by tokens without Jr / Sr / II
  suffixes - `shadow.player_value`, 2026-10-17; a nickname is never
  guessed). A past game's squad (the player's sample
  and the position pool) is, from `PLAYER_TEAM_FROM_SIDE_FROM_UTC`
  (2026-10-14 00:00Z; the game's day - SHADOW's day key, the kickoff's UTC
  date - and the computing clock), the lineup side the team held in that
  game (`player_model.appearances_from_lineups(..., side)`, `event_side`;
  a game whose payload names the team on neither side is left out). Before
  it, each entry's `teamId` - the player's team when the box was
  downloaded - so a traded player's old-team games against his new team
  were in the new team's sample (Carlson model_n 5 of 85 appearances,
  McTavish 6 of 88 on 10-13; `docs/sofa/evidence/sport_player_props_2026-10-13.md`).
  A mapping fix behind a switch because it moves p: SHADOW's pre-game
  number, SHADOW_SETTLE's settle-time number and `measure_player_props.py`
  follow the day's rule; `fit_player_model.py --player-team-from-side`
  replays it; rows carry `player_team_rule`; off = byte-identical. The line
  evidence reads the p written before the game, so it follows the day's
  rule by construction.
- Basketball second half / Q4 grade on the regulation periods - overtime does
  not count (operator, 2026-10-07); full-game basketball markets include it.
- A hockey / basketball game Sofascore publishes with no periods (only
  `current` and `winnerCode`) is graded from its final score
  (`shadow.build_result(..., allow_final_only=True)`, SHADOW_SETTLE only;
  `score_source: "final_only"`): full-game markets, regulation where
  `normaltime` (or no sign of overtime) tells it, never a period / half /
  quarter. Until 2026-10-12 such a game stayed DATA_MISMATCH for good
  (10-22 basketball games a day from 10-07). History readers keep the
  default and never see it. With the same flag a decided score with no
  `winnerCode` names its winner (2026-10-17, Shumen - Botev 87-84, every
  other check still applies). A CS2 player line whose nickname Superbet
  extends ("MartinezSa") reads the one roster nickname of >= 5 letters that
  prefixes it (`cs2.MapResult.player`).

- **CS2 count exposure** (`CS2_COUNT_EXPOSURE_FROM_UTC` 2026-10-13 18:10Z, audit B12, standing go; moved by the operator from 10-14 00:00Z to the refit's rebuild of 10-13): kills / deaths / assists / team kills are priced from the round race's (W, L) x per-round rates (`cs2_engine.ExposureBook`; log-loss new - old -0.0135 / -0.0258 / -0.0099 / -0.0380, every interval below zero); headshots measured worse (+0.188) and stay on the sample (outside `EXPOSURE_FAMILIES`). The line evidence of these families was fitted on the old p; no check on Superbet lines of 10-05..10-12 was made. Evidence: `docs/sofa/evidence/cs2_kills_exposure_2026-10-13.md`, `docs/sofa/history/RAPORT_B11_B12_2026-10-13.md`.

## Settlement and the ledger

- **SETTLE:** a refund (0 u.), never a loss, when the match was put back
  past Superbet's deadline - **23:59 of the day after the offered start,
  local time at the venue** (`settle.void_deadline`, zone from the venue /
  competition / home side's country, `config/sofa_country_timezones.json`,
  UTC when unknown; Regulamin Zakładów Online 5.E.1.a of 2026-02-10, read
  2026-10-13; until then 48 h) - or brought forward > 48 h (`VOID_AFTER`),
  was awarded, retired (Sofascore code 92, `RETIRED`), a walkover
  (`WALKOVER`), cancelled (`CANCELED`) or is still postponed / delayed past
  that deadline (`POSTPONED_BEYOND_VOID`; before it `POSTPONED`, pending) -
  `settle.REFUND_REASONS`; SHADOW_SETTLE / CS2_SETTLE read the same
  deadline. An abandoned match is not yet graded by 5.D.5 (a market already
  decided at the interruption stands, the rest is void): open. A
  football match decided on penalties (code 120) with no extra time (no
  `extra1` / `extra2` / `overtime`, current = normaltime + penalties) is
  graded on its whole-match statistics (`metrics.played_extra_time`,
  `extract_metric(..., settling=True)`); after extra time the non-goal
  counts stay `EVENT_NOT_FINISHED`; goals are always `normaltime`. Samples
  and ratings still skip both (changing that changes what prints). A card
  shown to a player on the bench is not counted (Superbet komunikat 06/2022,
  like a staff card): SETTLE and regrade read card rows without the cards of
  a player the lineups put off the pitch at that moment
  (`metrics.drop_bench_cards`; unused substitute only when the incident feed
  lists substitutions; samples keep every card; `regrade_settled.py
  --cards-bench`, from 2026-10-17). A half's goals whose `period1`
  contradicts the incidents' HT marker are refused when settling
  (`metrics.half_time_disagrees`; a graded row stays as it is). Player props grade only from the player's own squad
  (PLAYER_AMBIGUOUS); a sample matched by tokens grades its own
  `matched_name` there (a candidate in the other squad is PLAYER_AMBIGUOUS).
  A player who did not play, did not start or was not in the matchday squad
  (`PLAYER_DID_NOT_PLAY`, `PLAYER_NOT_STARTED`, `PLAYER_NOT_IN_SQUAD`) is listed per leg in `07_settle_skips.json`
  `void_legs`, and a printed such leg is a refund in 7c and the ledger
  (`regrade_settled.py --player-not-started` deleted 5,215 bench rows of
  09-24..10-10 on 2026-10-11, none printed); a printed leg without a sheet row goes to
  `07_settled_printed.json`. Sport legs grade at the printed price against the
  pinned id (`NOT_GRADED:ID_CHANGED` otherwise; a volleyball set line on a
  set never played - a 3-0 has no set 4 - is VOID, a refund, like a CS2 map
  never played: Regulamin 5.E.1.h-i, `shadow.set_not_played`, audit C21),
  in their own 7c table, never
  in `sofa_settled_row` or `fit_confidence`. Statistic gaps close days later:
  `resettle_sweep.py` every morning.
- **Results on the coupon** (operator, 2026-10-18): once a day is graded,
  `record_results.py` marks it (`mark_coupon_results.py`, `--no-mark` skips):
  `13_results.json`, then `build_coupon_pdf.py --with-results` re-renders
  KUPON_<d>.pdf and .html - every row green (won), red (lost) or yellow (not
  known, or a refund at 0 u.), the leg's claim (Superbet's selection, its
  confidence) beside what the market counted ("było: 11"; a yes / no market:
  the match score; a measured sport's handicap: team1 minus team2), the match
  score under the match, builders and their legs alike, and a closing percent
  summary per sport and in all (won / lost / other, hit rate of the decided
  legs against their mean confidence, flat units / ROI at the printed price;
  the HTML adds a result filter and the summary of the current filter). The
  grades are the ledger's, never a second grader; a printed leg the results
  do not hold is yellow, never green. Only days from
  `coupon_results.RESULTS_FROM_DATE` (2026-10-13; 10-08 and older are never
  redrawn) that are over (before today, UTC) are marked; the files as printed
  are kept as `KUPON_<d>.przed_wynikami.pdf` / `.html`. A results render is a
  view of a finished day, not a print: no `printed/<ts>.json`, no freshness
  guards, and the marked files keep the printed files' mtime (CONFIDENCE and
  audit C1 read the PDF's mtime as "printed"). Only `--with-results` reads
  `13_results.json` - a normal render or rebuild never shows results; the next
  mark draws them again (`13_results_rendered.json` holds the hashes of the
  last results render). Football scores are Superbet's 90 minutes (extra time
  and penalties said apart, only when the payload has them; the half time
  from the incidents' HT marker over a contradicting period1, as SETTLE). A
  refunded builder's legs are yellow ("zwrot buildera", the leg's own result
  named). A measured sport's result key is `sport_key` plus market id and CS2
  map (sport_key alone would let two markets / maps share a result). On a
  phone the HTML's table scrolls in its own box. Display only -
  nothing it shows enters a confidence or a gate.
- **Ledger** (`record_results.py` -> `runs/sofa/ledger/results.jsonl`, read
  with `audit_ledger.py`): the coupon's result, the legs removed by reads and
  each sport kept side by side, never pooled. It reads `sofa_settled_row`, so
  re-run it after any `regrade_settled.py`. Exit 0 with legs pending, 1 on a
  `MISMATCH` (two graders disagree - a defect), 2 on a crash.
- **Comparability:** the current rules apply from 2026-10-06; a refit install
  or an epoch switch starts a new epoch (the latest: the identity plan's
  switches - ENTITY_MAP, DAY_ANCHOR, TOURNAMENT_DAY, NOT_ON_SOFASCORE,
  PLAYER_NAME_SURNAME, FOOTBALL_DAY_ANCHOR - moved by the operator into
  10-14 at 11:30Z: 10-14 is mixed, ledger group "10-14 mieszany", the days
  after it "od 10-15", which also starts the new-market curves installed
  2026-10-15 00:17Z and the 1X2 / DNB and CS2 series-rounds switches; from
  10-16 the cup-strength football refit installed 2026-10-15 23:02Z and
  refit 2026-10-16b with SAMPLE_CUP_STRENGTH from 04:10Z, both before
  10-16's build, FOOTBALL_CUP_STRENGTH and BASKETBALL_DC_PAIR from 00:00Z,
  and the football score markets / tennis set complements moved by the
  operator into the built day at 07:46Z - 10-16 is mixed, ledger group
  "10-16 mieszany"; 10-17 itself is mixed too - the supremacy stretches from
  13:37Z and refit 2026-10-17 from 19:13Z moved into the built day by the
  operator: ledger group "10-17 mieszany" (PLAYER_SAMPLE_GATES from 00:00Z),
  the days after "od 10-18" ("od 10-17" holds no day); 10-18 is mixed too -
  LINE_CURVES moved into the built day at 12:48Z: ledger group "10-18
  mieszany" ("od 10-18" holds no day), the days after "od 10-19"; before them ledger group
  "od 10-14"
  - the switches of 2026-10-14 00:00Z (LEAGUE_RATE_RULE, BUCKET_DESIGN_EFFECT,
  READ_BY_VALUE, TENNIS_MATCH_WINNER, MAPPABLE_FAMILIES, MEN_FRIENDLY_*,
  PLAYER_TEAM_FROM_SIDE, MARKET_POSITIONED_LINES with the A7 basketball
  curve), the football / tennis refit installed 05:31Z and
  SAMPLE_OPPONENT_CORRECTION from 05:45Z, all before 10-14's build, so 10-14
  is not mixed; before it the football / tennis refit installed 2026-10-13
  18:06Z with its switches and the CS2 B10 / B12 switches from 18:10Z, into
  a built day - 10-13 is mixed, ledger group "10-13 mieszany"
  (`audit_ledger.EPOCH_GROUPS`), summed with neither "od 10-12" nor
  "od 10-14"; before it the player switches of
  2026-10-12 00:00Z - ONE_SIDED_SINGLES, PLAYER_STARTS_ONLY, PLAYER_NAME_TOKENS
  and the staged player curves - ledger group "od 10-12"; before it the refit installed
  2026-10-08 23:42Z, effective 2026-10-09; days from 10-09 are not summed with
  earlier ones; 10-08 was built under the old rules and is never rebuilt,
  re-PDF'd or re-read after the install). Earlier days ran under other rules
  and are other experiments - the ledger keeps them in their own groups and
  they are never summed with the current ones. Days up to the morning of
  2026-10-05 also hold rows of variants whose code is gone (`wariant`,
  `multi`, `sport:<sport>`, `rule:<sport>`): kept as recorded, never rebuilt.

## Changing the pipeline

The shape above stays; it is improved, not rebuilt.

1. **Measure first.** A change comes with a measurement on settled rows or
   history (match bootstrap, out of sample) or it is a suspicion. `measure_*.py`
   scripts are read-only evidence.
2. **Correctness fixes** (a misgrade, a wrong mapping, a crash) go live at once,
   with a test.
3. **Anything that changes what prints** gets a switch in `bet.sofa.epochs`,
   by default effective from the next day's 00:00Z. Only the operator moves it
   earlier, to an exact time (the day is then mixed and says so); never on
   your own mid-day.
4. **Refits and calibration fits** (`prepare_refit.py`, `fit_*`) run on a
   **copy** of the database (SQLite `VACUUM INTO`, then `--db-path <copy>`
   with `--without-db-backup`; scratch in `data/refit_<date>/`), never
   against live rows, so the daily loops stay up. `install` runs
   `tests/sofa` and restores on failure. Installing changes what prints, so
   it needs the operator's go - and no refit without it, mid-day included.
   **Standing go for the 2026-10-13 audit** (operator, 2026-10-13;
   `docs/sofa/history/AUDYT_RYNKOW_KONTEKST_2026-10-13.md`, "Decyzje
   operatora"): while implementing that audit a switch may be turned on by
   the implementing session when the out-of-sample measurement is better with
   an interval excluding zero, `tests/sofa` pass and a report is written; a
   refit carrying the audit's fixes may be installed without a further go,
   also into a day already built - then at an exact UTC time, the day is
   mixed and says so, printed legs stay locked, and the ledger opens a new
   epoch. Nothing else is covered by this go.
5. **Every fix ships a test** in `tests/sofa/` (offline, fast); run the gates.
6. **Update this file's section** and the Polish doc in `docs/sofa/`; a run or
   a night gets a report in `docs/sofa/history/`.

Daily loops spawn each step through `run_pipeline.py` (fresh code per step);
only the loop's own orchestration is old code until it ends.

**Measured and not switched on** (audit 2026-10-13 implementation, `None`;
`docs/sofa/history/RAPORT_IMPLEMENTACJI_AUDYTU_2026-10-13.md`):
`FOOTBALL_LEAGUE_RATE_RULE_FROM_UTC` (A2's football half: the rating at the
all-league rate beat the sample alone in thin competitions, squared error
-0.58 [-0.62, -0.54] per side in its favour), `UNIT_STRENGTH_FROM_PARENT_FROM_UTC`
(A1: a regional unit's strength from its competition's; goals log-loss
-0.0010 [-0.0029, +0.0008] on 7,724 cross-unit matches).
**Football day anchor** (identity plan K8, `FOOTBALL_DAY_ANCHOR_FROM_UTC`
2026-10-14 11:30Z, switched on by the operator, "Tylko 1. wlacz"):
RESOLVE takes a verified side's ONLY football game within 1 h of
Superbet's start, read in Superbet's order (F25), gender as the board's,
not postponed, the opponent's own verified id (if any) in it
(`resolve.football_day_anchor_event`). 3,458 / 3,459 bridged fixtures of
10-05..10-14 with the opponent hidden, ~11 more fixtures a day; the one
unsettled (Hapoel / Maccabi Petah Tikva U19 10-11) accepted by the operator.
Tennis never (replaced opponents).
**Football league strength in international club cups**
(`FOOTBALL_CUP_STRENGTH_FROM_UTC` 2026-10-16 00:00Z, operator go 2026-10-15;
refit installed 2026-10-15 23:02Z, before 10-16's build - not a mixed day;
`docs/sofa/history/RAPORT_SILA_PUCHAROW_2026-10-16.md`): the
league-strength book links leagues mostly through their own lower
divisions and ordered top flights wrongly - on 3,740 cross-league cup
matches from 2024-07 the rating under-rated the side from the stronger
league by +5.2 pp P(win) [+3.6, +7.0]. `football_rating.RatingBook` now
carries a per-(domestic competition, metric) correction `cup_delta`, learnt
only from cross-league matches of the nine cups of
`config/sofa_cup_strength.json` (UCL / UEL / UECL, AFC Elite / Two,
Libertadores, Sudamericana, CAF, CONCACAF) inside `update`, read on such a
cup's fixture on top of the domains' sigma (`RatingBook.cup_extra`,
`bet.sofa.cup_strength`). Steps per metric, only where better out of sample
with the interval below zero (`measure_cross_league_cups.py --in-book`,
TRAIN 2024-07..2025-06, TEST from 2025-07 and from 2026-01): goals_for 0.05
(1X2 log-loss -0.0285 [-0.0381, -0.0188], 2,194 matches; better than the
post-hoc D), goals_1h_for 0.05, goals_2h_for 0.02, shots_for 0.02 (re-measured
on 1,748 backfilled cup statistics, both cuts below zero); corners, shots on
target, fouls, cards, offsides, halves of corners / shots measured no better
(some worse) - no step. Non-cup matches feel the changed ratios: on 302,635
moved matches goals -0.00003 [-0.00006, -0.000003], nothing worse
(`--spill`). Rows carry `cup_strength_rule`; a rebuild of a day >= 10-16
re-runs SHEET on a sheet without it. The file is an operator list with
chosen steps, outside `config_sha`. Replay `--cup-strength`. The football /
tennis curves were refitted on that replay (`data/refit_2026-10-16/
sofa_replay.db`, 125.4M rows, installed 2026-10-15 23:02Z; `fit_constants` K
fits skip the rating-only markets' sample-less rows since 3f77701e) and the
double chance / DNB / first goal curves refitted on the same book (gate
verdicts unchanged), then refitted again before 10-16's build (refit
2026-10-16b, installed 2026-10-16 04:02Z, below); E2E
on 10-15: 1,238 common legs, the new curves move none by > 0.006, the cups
move 60 legs (59 cup), +65 / -37 legs, all but a few cup legs - Lech -
Leverkusen, Celje - Omonia, CSKA - Monaco, Egnatia - Midtjylland move the
way the analysts' vetoes said.
**Refit 2026-10-16b (installed 2026-10-16 04:02Z, before 10-16's build - not
mixed; operator's standing go of 2026-10-15 evening, "instaluj zawsze, sam
decyduj"):** the football / tennis curves on `data/refit_2026-10-16b/
sofa_replay.db` (120.3M rows; the DB copied after 1,748 cup matches got their
statistics, `backfill_event_stats.py --competitions`) with two more replay
rules: `--tennis-sample-scope` (a tennis side's sample scoped as SAMPLES
scopes it - the fixture's format and a comparable surface; before, 13% of
best-of-three rows, 57% ATP, held a Grand Slam five-setter, centre +1.97
games, log-loss +0.0445; `tennis_replay_sample_scope_2026-10-16.md`) and
`SAMPLE_CUP_STRENGTH_FROM_UTC` 2026-10-16 04:10Z (B15's gaps read the cup
correction with the past match's and the fixture's competition,
`SampleCorrector(cup_aware=True)`, marker `sample_cup_rule`, replay
`--sample-cup-strength`; shots_for calibrated log-loss -0.00006 [-0.00012,
-0.000003], -0.00044 on rows with a cup, shots_total zero; only shots move,
35 cup fixtures on 10-15). E2E on 10-15 vs refit 2026-10-16: +22 / -6 legs
(11 tennis games_won_for), common legs +0.0001 mean, max 0.050. 13
`tennis_team_cup` class keys (aces, double faults, games_total, set 3,
sets_total) have no curve any more - fewer replayed rows after the scoping:
NO_CLASS_CURVE until measured. Backup `config/backup_2026-10-16b`.
**Measured and not switched on, identity plan** (2026-10-14,
`docs/sofa/history/RAPORT_K7_K8_POMIAR_2026-10-14.md`): hockey / basketball players found only
under another team (K7: 25 of 30 / 20 of 48 NOT_IN_HISTORY names - pricing
them from another team's games is a model change, to be measured first).
**Measured and not switched on, measured sports** (audit 2026-10-13, all `None`, code behind the switch):
`CS2_MAP_IDENTITY_FROM_UTC` (B11: map order / pool terms, walk-forward on 24,995 maps / 11,217 series, A vs base +0.00021 [-0.00022, +0.00064], no effect; `cs2_map_identity_2026-10-13.md`),
`HK_SHOTS_FROM_UTC` and `HK_EMPTY_NET_FROM_UTC` (B8: hockey shots x save%, centre replaced: total +0.00126 [+0.00010, +0.00241] worse, blend +0.00025 [-0.00033, +0.00084]; fitted empty net: handicap -0.00037 [-0.00074, +0.000006], total +0.00111 worse; shots exist for 6,755 of 29,516 games, none in October 2026; `hockey_goalie_empty_net_2026-10-13.md`, `RAPORT_B8_HOKEJ_2026-10-13.md`),
`VB_SET_LENGTH_FROM_UTC` and `VB_SET_HISTORY_FROM_UTC` (B9 / C10: volleyball set length table, 5,050 matches walk-forward: points_total +0.0025 [-0.0005, +0.0054], points_handicap -0.0011 [-0.0036, +0.0013], set_extra_points -0.0004 [-0.0014, +0.0007]; threshold not met; C9 not measured, it depends on B9; `volleyball_set_length_2026-10-13.md`, `RAPORT_B9_C10_C9_2026-10-13.md`),
`BB_OVERTIME_FROM_UTC` (A3: overtime in the basketball replay; regulation 1X2 -0.00354 [-0.00719, -0.00015], totals and winner no better; as a curve variant +0.00113 [-0.00123, +0.00353]; `basketball_refit_2026-10-13.md`),
curve refits of 2026-10-14 for basketball (plain, league-rate rule: -0.00042 [-0.00145, +0.00063]), hockey (+0.00151 worse), volleyball and CS2 (zero) - "Measured sports".

B1 / B2 / B14 / C1 / B5 are on since 2026-10-13 18:10Z and B15 since
2026-10-14 05:45Z ("Refit of 2026-10-14" under Confidence); B1's betas were
refitted on the live centre (2026-10-13 20:57Z) before that replay.

**Switched on 2026-10-14 14:20Z** (operator, "WŁĄCZ OD TERAZ"; into the built
day - 10-14 is mixed; on 10-14 neither had a curve and nothing printed; the
curves that passed the gate are installed from 2026-10-15 00:17Z, "New-market
curves" below):
`FOOTBALL_RESULT_MARKETS_FROM_UTC` (audit D1, double chance only:
OFFER reads "Podwójna szansa" as `double_chance` with the left-out "Mecz"
outcome as its UNDER, SHEET prices the selection from NB goals on the pure
rating centres, r 7.586 in `config/sofa_football_result.json`, unfitted, OVER
only, `result_rule`; graded on the 90-minute score; `bet.sofa.football_result`,
`docs/sofa/evidence/football_result_phase_2026-10-13.md`; from
`FOOTBALL_RESULT_1X2_DNB_FROM_UTC` 2026-10-15 00:00Z also "Mecz" 1 / 2 as
`result_1x2` and "Zakład bez remisu" as one `draw_no_bet` rung - OVER home,
UNDER away, a draw a refund `DNB_DRAW_REFUND` - with an early-phase men's
leg reading the curve class `season_early`, `bet.sofa.football_1x2_dnb`;
DNB keys passed the one-sided holdout gate and are installed, every 1X2 key
failed (no curve, NO_LINE_EVIDENCE); `docs/sofa/evidence/football_1x2_dnb_phase_2026-10-15.md`),
`SHOT_DETAIL_MARKETS_FROM_UTC` (footballer shots outside the box / headed /
left / right foot, all and on target: OFFER reads the eight names as player
markets, SAMPLES and SETTLE count them from `/shotmap` only where it gives the
player his lineups `totalShots`, SHEET prices `shot_detail.forecast` from
`config/sofa_shot_detail.json` (absent file: `NO_SHOT_DETAIL_FIT`) -
rows `shot_detail_rule`;
`docs/sofa/evidence/shot_detail_2026-10-14.md`). The shot-detail estimator file
`config/sofa_shot_detail.json` is installed (fit `data/refit_shot_detail_2026-10-14/`);
its left / right foot shots curves are installed (2026-10-15), the other six
keys failed the gate. Every OFFER also records the unread markets' prices
(`unmapped_prices/`). Report: `docs/sofa/history/RAPORT_LUKI_RYNKOW_2026-10-14.md`.

**Switched on 2026-10-14 14:50Z** (operator, "1. 2. tak"; into the built day,
10-14 mixed; curves of the keys that passed installed 2026-10-15 00:17Z): `SPORT_DERIVED_MARKETS_FROM_UTC` (SHADOW reads, SHADOW_SETTLE
grades and SPORT_CONFIDENCE prices from the score model the hockey /
basketball double chance - regulation, as the 1X2 - and volleyball's team
sets and sets count, `shadow.DERIVED_MARKETS`; history log-loss vs base
better on every 1X / X2 and volleyball key, none on "12";
`docs/sofa/evidence/sport_derived_2026-10-14.md`); `FOOTBALL_INCIDENT_MARKETS_FROM_UTC` (`bet.sofa.football_incidents`: "1. gol"
as one-sided `first_goal` from the double chance's NB goals on the pure
rating, "Liczba czerwonych kartek" / "Liczba przyznanych rzutów karnych" O/U
0.5 / 1.5 as `red_cards_total` / `penalties_total` from the competition's
as-of full-feed rate, graded from regular-time incidents; at p >= 0.70
calibrated walk-forward 06-09..10-14: first goal +1.0 pp n 1,376, reds +0.7
pp n 10,152, penalties +1.0 pp n 9,518; the minute bands never reach 0.70 and
are not read) and `TENNIS_SET_MARKETS_FROM_UTC` (`bet.sofa.tennis_sets`: "X.
set - zwycięzca" as `set1_won_for` / `set2_won_for`, the tennis "Dokładny
wynik" as one-sided `set_score`, from the rating's neighbours; set 1 +1.0 pp
n 12,174, set 2 +0.4 pp n 12,502, exact sets +1.5 pp n 4,107) - rating-only
markets; `docs/sofa/evidence/football_incidents_tennis_sets_2026-10-14.md`.

**New-market curves installed 2026-10-15 00:17Z** (operator go 2026-10-14,
"zbudować krzywe dla tych wszystkich rynków"; before 10-15's build, so not a
mixed day; `scripts/sofa/install_new_market_curves.py --dir
data/refit_new_markets_2026-10-15 --confirm`, backup
`config/backup_2026-10-15_new_markets/`, `tests/sofa` passed; each key's
`new_market_curves_fitted_from` in the file): 29 history curves of the
markets switched on 10-14 / 10-15, fitted before 2026-10-15 and admitted by
the **one-sided holdout gate** (operator 2026-10-14 18:55Z;
`scripts/sofa/new_market_gate.py`: fit before 2026-09-01, judged on
09-01..10-13, a key fails only if its curve **overstates** - n >= 300
holdout forecasts at curve >= 0.70 and realised - curve >= -2 pp;
under-statement passes; every "12" key refused by policy; the sports'
admission rule unchanged). Football / tennis
(`config/sofa_confidence_calibration.json`): `player_left_foot_shots_for` /
`player_right_foot_shots_for` OVER, `double_chance` OVER (+ `women:`),
`first_goal` OVER, `penalties_total` / `red_cards_total` UNDER,
`set1_won_for` / `set2_won_for` OVER and UNDER, `set_score` OVER (each
+ `tennis_women:`), `draw_no_bet` OVER / UNDER (+ `season_early:` and
`women:` OVER). Sports (`config/sofa_sport_confidence_calibration.json` and
its `.next.json`): hockey `double_chance` / `period_double_chance` TEAM,
basketball `double_chance` TEAM, volleyball `team_sets_exact` NO /
`team_wins_set` YES, CS2 `rounds_handicap` TEAM, `rounds_total` OVER,
`team_rounds` OVER. Every other new key (1X2, "12", shots outside the box /
headed / on target, reds / pens OVER, basketball halves / quarters,
volleyball sets_count) has no curve: `NO_LINE_EVIDENCE` until its own lines
settle. Line evidence reads the installed keys like any other (offset /
band cap only lower). E2E on a copy of 10-14 (build clock, before vs after):
+110 legs (double chance 78, reds UNDER 12, pens UNDER 6, hockey DC 9, set
winners 4, first goal 1 - a one-sided single), 0 legs lost, no common leg's
confidence moved; **102 of the 110 at a confidence below 1/odds** (they pass
x >= 0.90); whether these markets beat Superbet's price is unmeasured.
Basketball double chance: Superbet quotes it as 1X / X2 only, and
`shadow.parse_event` takes a double-chance group only whole
(`cs2.DOUBLE_CHANCE_SET`), so until 10-16 it was never read; from
`BASKETBALL_DC_PAIR_FROM_UTC` (2026-10-16 00:00Z, a correctness fix of a
switched-on market, next-day default) a basketball group that is not whole
is read as two-way pairs - each selection against the regulation 1X2
outcome it leaves out, same scope (game / halves / quarter), fair p and
margin of that partition, synthetic ids `dc_id x 100 - 1/2/3`, the
complement a price only (`partner_odds`), never a leg or a row; records /
legs carry `dc_pair_rule`; hockey, volleyball and a whole group unchanged
(`tests/sofa/test_basketball_dc_pair.py`). A read can name a sport
double-chance side (`contracts.READ_SIDES` has 1X / X2 / 12 from
2026-10-15).
`docs/sofa/evidence/new_market_curves_2026-10-15.md`,
`docs/sofa/history/RAPORT_KRZYWE_NOWE_RYNKI_2026-10-15.md`.

**Switched on 2026-10-16 07:46Z: football score markets and tennis
exact-score complements** (operator 2026-10-16, "wdroż oba", then "Włącz od
teraz" - moved from 10-17 00:00Z into the built day: 10-16 is mixed, ledger
group "10-16 mieszany", its legs printed before stay locked; the days after
"od 10-17"; a rebuild from 07:46Z re-reads OFFER when 04_offer.json holds no
such rung and re-runs SHEET when 05_sheet.json holds no such row,
`rebuild_plan` - no step by hand): `FOOTBALL_SCORE_MARKETS_FROM_UTC` (`bet.sofa.football_score_markets`:
OFFER reads "Mecz lub liczba goli (L)" / "<team> / Remis lub powyżej /
poniżej X goli w meczu" as `result_or_over` / `result_or_under` (subject 1 /
X / 2), "Obie drużyny strzelą gola lub powyżej L gola" as `btts_or_over`,
"... lub obie drużyny strzelą gola" / "... lub którakolwiek drużyna zachowa
czyste konto" as `result_or_btts` / `result_or_clean_sheet`, "Handicap"
+1.5 / +2.5 / +3.5 as `result_handicap` (+0.5 is the double chance, not
read; never a `handicap_` prefix - `is_derived` would kill it), "Podwójna
szansa & liczba goli" 12 & powyżej / 1X & poniżej as `dc_and_over` /
`dc_and_under`; two markets quoting one bet are merged at the lower price,
no collision recorded; SHEET prices the OVER from the double chance's NB
grid on the pure rating centres (`score_market_rule`, `result_phase`);
SETTLE grades the event on the 90-minute score **at 0.5, never at the
goals line**) and `TENNIS_SET_COMPLEMENTS_FROM_UTC` (rides on
TENNIS_SET_MARKETS: `set_score_not` "<player> 0:2" OVER = he wins a set -
"wygra seta" Tak, "Handicap setowy" (1.5), "liczba setów" powyżej 0.5, the
other's "wygra bez straty seta" Nie, one canonical rung; 1 - the 0:2 share
of the rating's neighbours; `set_complement_rule`). **Curves per slice**:
a score market's curve key is `<market>@<subject>@<line>|OVER`
(`confidence.curve_market`, also in `fit_line_evidence.py`; a slice without
a curve never reads a pool) - one curve per market hid -3..-9 pp slices
(NB tail at high "or over" lines, the draw's "or" markets) in a -0.5 pp
pooled gap; an early-phase men's leg reads `season_early:` (`leg_class`),
women `women:`. Fitted by `scripts/sofa/fit_score_market_curves.py` on the
rows the installed 1X2/DNB (cup book) and tennis set fits already wrote - no
replay - one-sided gate plus no slice overstating; installed by
`install_new_market_curves.py --dir data/refit_new_markets_2026-10-17`
(133 football slice curves: men 50, season_early 40, women 43; set_score_not
men + `tennis_women:`; listed in `new_market_curves_fitted_from`, which a
refit now carries itself - `fit_meta.carry_separately_fitted_curves` in
`fit_confidence`, `carry_sport_new_market_curves` in `fit_sport_confidence`,
for every new-market key and `match_won_for`; until 2026-10-16 a refit
dropped them unless carried by hand). E2E in a scratch replay (10-14 / 10-15 / 10-16, off vs on on the same
input): SHEET off = on minus the new rows byte for byte, 0 legs lost or
changed, +484 / +536 / +1,068 legs; settled 10-14..15: 1,018 legs / 233
matches realised +1.2 pp [-1.8, +4.2] over confidence, ROI -2.4% [-6.1,
+1.2] (at the price, no measured edge); set_score_not 27 legs -9.8 pp
[-27, +7] (open, `T-SCORE-MARKETS-superbet`). Several rungs of one match are
one script but not grouped as a ladder (two-dimensional, like DC / 1X2). A
rung Superbet quotes OVER only ("Mecz lub liczba goli" without its "wygra lub"
pair, `dc_and_*`) prints as a one-sided single (its slice curve n >= 300);
until a key has its own settled lines, line evidence lowers it by football's
pooled offset and caps it by football's pooled price band (`cap:*@...` -
at 1.30-1.60 that cell realised ~0.69 at p 0.83, so most such legs above
1.30 do not print). The PDF / HTML name these legs in Superbet's words
(`football_score_markets.display_market`, "Mecz lub liczba goli: <team> lub
powyżej 2.5 (Tak)", "<player> wygra seta (Tak)"). Every OFFER reader builds
its fetcher from `offer.day_flags(date)` (run_offer, capture_closing, the
verifier's and the scout's re-asks), so no reader misses a switch.
`docs/sofa/evidence/football_score_markets_2026-10-16.md`,
`docs/sofa/history/RAPORT_NOWE_RYNKI_2026-10-16.md`.

**Switched on 2026-10-17 13:37Z (operator, "włączaj już teraz") - 10-17 is
mixed, ledger group "10-17 mieszany", the days after "od 10-18"; legs printed
before stay locked:** the three supremacy stretches below, BEFORE their
refitted curves (the replay carrying them runs from 12:31Z). Measured for that
combination first (stretched p through the curve fitted on unstretched p,
test 2026): goals_for / goals totals / all 16 count markets / both player
markets better, every CI below zero except shots_on_target_total pre-2026
(neutral); goals_1h_for and goals_2h_for better in log-loss but their
favourite OVER legs at >= 0.70 overstate with the old curve (-5.7 / -3.0 pp)
- held back until the refitted curves were installed. **Refit 2026-10-17
installed 19:13Z** (same go, into the mixed day; backup
`config/backup_2026-10-18`, tests/sofa 5102 passed): football / tennis
curves, engine constants, league baselines and reliability fitted on
`data/refit_2026-10-17/sofa_replay.db` (1,282,317 matches, 121.9M rows; the
10-16b flags plus `--goals-stretch --count-stretch --player-stretch`; keep
this DB - `fitted_from.db_path`); goals_1h_for / goals_2h_for restored to
`config/sofa_goals_stretch.json` at the install, SHEET re-run by hand,
line evidence refitted on the new curves. E2E at the build clocks: 10-16
+83 / -44 legs, settled -89.94 -> -90.95 u. (dropped 41 graded -0.51,
added 81 -1.52 - no lost leg of the day turned); 10-17 +71 / -28, common
legs |move| 0.002 mean, 0.060 max. `fit_confidence` keeps the footballer
shot-detail rows out of the replay fit (`shot_detail.METRICS`; the first
fit had replaced the left / right foot curves). Report
`docs/sofa/history/RAPORT_DZIEN_2026-10-17.md`. To watch on live legs: goal_kicks_for UNDER
s -1..-0.5, throw_ins_total UNDER |s| >= 1.5 (thin cells),
shots_on_target_for / shots_1h_for ~0.5 pp lower at >= 0.70. The
MODEL_ABOVE_OWN_SAMPLE gate removes more legs (E2E 10-17: +27): the stretch
moves the model away from the opponent-blind sample by design.

**Supremacy stretches (measured 2026-10-17, each its own switch, file,
fit script, replay flag and every-football-row marker; arithmetic shared in
`bet.sofa.supremacy_stretch`; s = the rating's expected goal difference,
clamped at `MAX_SUPREMACY`, a total the home side's):**
`FOOTBALL_GOALS_STRETCH_FROM_UTC` (`goals_stretch_v2`: goals centre x
exp(beta s) / exp(g1 |s| + g2 s^2), a market may carry one set per season
phase - goals_for early / mid / late / final 0.018 .. 0.064, halves early
only; a phase the file lacks, and a match with no phase, read the single
set; `config/sofa_goals_stretch.json`, `fit_goals_stretch.py --per-phase
goals_for:early,mid,late,final goals_1h_for:early goals_2h_for:early`
(offset with the installed season phase, cup-strength book), `--goals-stretch`;
`docs/sofa/evidence/goals_stretch_2026-10-17.md`),
`FOOTBALL_COUNT_STRETCH_FROM_UTC` (`count_stretch_v1`: the 16 count markets
of `count_stretch.COUNT_STRETCH_MARKETS` outside GAME_STATE - half corners,
shots by half, shots on target, offsides, saves, throw-ins, goal kicks, the
shots-on-target / saves / throw-ins totals - after GAME_STATE and the venue
prior; walk-forward NB and both after-curve out-of-sample checks below zero
on all 16, the raw NB of a fixed fit not significant for shots_1h_for
(pre-2026 fit) and offsides_for (2026-H1 fit), offsides_1h_for left out;
`config/sofa_count_stretch.json`, `fit_count_stretch.py` (from 2026-01-01,
cup-strength book),
`--count-stretch`; `count_stretch_2026-10-17.md`) and
`FOOTBALL_PLAYER_STRETCH_FROM_UTC` (`player_stretch_v1`: player_shots_for /
player_shots_on_target_for centre x exp(beta s) of his own side, 0.126 /
0.117; `config/sofa_player_stretch.json`, `fit_player_stretch.py` (cup-strength
book, epochs as of `--before`),
`--player-stretch`; `player_stretch_2026-10-17.md`). Each changes p: the
curves are refitted on a replay carrying it before its switch is set.

**Measured and not switched on, tennis serve markets** (2026-10-17,
`docs/sofa/evidence/tennis_aces_opponent_2026-10-17.md`, report
`docs/sofa/history/RAPORT_TENIS_SERWIS_2026-10-17.md`): aces / double faults
are priced from the server's own scoped sample shrunk to the tier prior; the
returner never enters. `TENNIS_ACES_OPPONENT_FROM_UTC` (`None`;
`bet.sofa.tennis_aces_opponent`: aces centre x the returner's conceded aces
shrunk to the tier prior over it, totals by the weighted pair; double faults
measured worse and never corrected; SHEET marker `tennis_aces_rule`, replay
`--tennis-aces-opponent`): history replay test 2026 aces_for +0.0003
[-0.0006, +0.0011] on all lines, aces_total +0.0124 worse, per-set aces
-0.003; on Superbet's settled lines with the real SHEET (64 matches, 1,364
lines, 10-06..10-16) +0.0060 [-0.0251, +0.0348] - nothing. The serve markets
the replay never read (per-set aces / double faults, aces + double faults
match and per set; replay `--tennis-serve-markets`) got history curves
(`scripts/sofa/fit_tennis_serve_curves.py`, staged in
`data/refit_tennis_serve_2026-10-17/`, install group `tennis_serve` REPLACES
its markets' curves) that pass the one-sided holdout gate on the history but
at Superbet's lines would print legs far below their confidence (per-set
double faults / serve points 12 legs / 4 matches -20.7 pp [-50.8, +5.8];
aces with the correction 20 / 13 -30.6 pp [-52.2, -4.6];
`scripts/sofa/measure_tennis_serve_market_line.py`) - not installed; check on
new data `T-TENNIS-SERVE-MARKET-LINE`. The mechanism: the replay's curve is
fitted on the whole synthetic ladder (`lines_for`), Superbet quotes one line
near the median, where a model p >= 0.70 is a disagreement with the market;
on the history alone a curve fitted on all lines read on market-like lines
claims 0.761 and realises 0.668 (aces_for). Installed tennis serve curves
today: aces / double faults match only (history curve at >= 0.70 on
Superbet's lines -22.6 pp [-33.4, -14.3], 140 lines / 43 matches; the line
evidence holds back all but short prices: 14 printed legs settled 0.714 vs
0.759). **Never pass `--tennis-serve-markets` or `--tennis-aces-opponent` to
a refit** before `T-TENNIS-SERVE-MARKET-LINE` passes: `fit_confidence` would
write those curves itself. `prepare_refit.py install` refuses a refit whose
replay lacks a flag an installed separately fitted curve requires
(`requires_replay_flags`, `dropped_replay_rules`). Tennis printed legs
10-09..10-16 as a whole: -1.0 pp [-3.5, +1.5] (1,473 legs, ROI -5.5%);
per-player set games OVER -7.1 / -6.6 pp, intervals touching zero:
`T-TENNIS-SET-GAMES-OVER`.

**Waiting for the operator** (switches off, `None` in `bet.sofa.epochs`):
`CURVE_STATUS_FROM_UTC` (a curve failing `measure_calibration.py` stops
printing), `MODEL_FIXES_FROM_UTC` (tennis NB dispersion; with the next refit),
`BUILDER_SCREEN_PRICE_FROM_UTC` (switched off 2026-10-05: sofa does not price
builders), the coupon form
dials, and the derived football joints -
`DERIVED_CURVES_FROM_UTC` (joints read a history curve),
`CARDS_CORRELATION_FROM_UTC` (cards joints with side correlation +0.126;
the 10-14 cards joint curves were fitted with it, so it must go on with
DERIVED_CURVES) and `DERIVED_SHEET_MARGINS_FROM_UTC` (audit B3: a football
joint's side with no quoted ladder priced by SHEET's formula,
`run_sheet.sample_centre`, and an UNLINKED fixture's joints refused; history
one step ahead -0.0254 [-0.0264, -0.0245] on 60,000 matches,
`derived_margins_2026-10-13.md`). The refit of 2026-10-14 replayed the
joints; on Superbet lines of 10-09..10-12 (in sample for the curve) its
joint curves beat the line-evidence stand-in at p >= 0.60 by -0.0154
[-0.0309, +0.0004] - the interval touches zero; clearly only where both
sides had a marginal centre (-0.0357 [-0.0585, -0.0135]), while on raw
samples (B3's population) the curve alone overstates by 11 pp at >= 0.70;
the lines it would admit realised below their price (ROI -1.8%
[-4.4, +0.7], `both_over_goals` -6.2% [-10.6, -2.1]). Verdict: the three go
on together or not at all, re-measured on rows from 10-13 on
(`docs/sofa/evidence/derived_curves_2026-10-14.md`). None of them changes
the coupon while `THIN_SAMPLE_FOR_BUILDER` refuses every derived football
row (it reads the derived row's own market as its sample; 0 derived legs in
`08_confidence.json` 10-09..10-13) - the operator's decision first.
Open questions: Superbet's game count of a tennis match tiebreak. Measured
2026-10-12 night: the line-evidence offsets of the repriced families moved
<= 1.3 pp a day over 10-09..10-12 (stable, reproduced from the legs); the
tennis `games_won_for` OVER offsets (-8.5 men, -12.1 women) were measured on
old-estimator rows, while the new estimator's rows are calibrated there
(-0.2 pp, n 117) - over-lowered, a candidate (evidence on rows >= 10-09 for
the repriced families) once a walk-forward has the days.
**Before the next refit:** measure the tennis games population of replay
matches without `/statistics`; a refit carrying the men's friendlies (851
rows in the goals fit, variant C, the as-of 851 prior); every refit passes
`--cup-strength --sample-cup-strength --tennis-sample-scope` (on since
2026-10-16). Football
props measured separately (2026-10-15, 10-12..10-14): the curve is
calibrated (-2.1 pp [-6.9, +2.7], 319 lines / 51 games), ROI -16.5% at
Superbet's short prices, ~nothing printed (`football_props_2026-10-15.md`);
from PLAYER_SAMPLE_GATES (2026-10-17) ~14 player singles a day are expected
(`player_line_evidence_2026-10-16.md`).
Current backups: `config/backup_2026-10-05`,
`config/backup_2026-10-06_sport_calibration/`, `config/backup_2026-10-08`,
`config/backup_2026-10-09`, `config/backup_2026-10-14` (before the 10-13
refit), `config/backup_2026-10-15` (before the 10-14 refit, with the removed
`.next.json`), `config/backup_2026-10-15_new_markets/` (before the
new-market curves), `config/backup_2026-10-15_bb_a7_hybrid/` (before the
basketball A7 keys from the full cache), `config/backup_2026-10-16` (before
the cup-strength refit), `config/backup_2026-10-16b` (before refit
2026-10-16b), `config/backup_2026-10-18` (before refit 2026-10-17),
`config/backup_2026-10-18_line_curves/` (before the per-line curves),
`data/backup_2026-10-05/sofa.db`;
`data/refit_2026-10-17/sofa_replay.db` is the DB the installed football /
tennis curves were fitted from (`fitted_from.db_path`) - keep it, and
`data/refit_2026-10-16b/sofa_replay.db` (the previous install's) and
`data/refit_2026-10-08/sofa_replay.db`; the replay DBs of
`data/refit_2026-10-16/` and `data/refit_2026-10-14/` were deleted 2026-10-16
(their logs / manifests kept).

**Measured for the next refit (2026-10-12 night, out of sample on the history,
`docs/sofa/history/RAPORT_NOC_2026-10-12.md`):** tennis set-1 winner and set
score after the match winner (on since 2026-10-14, `measure_tennis_outcome_model.py`);
football DNB / double chance / 1X2 from the pure rating centre with NB r ~7
(skill 11.7 / 6.2 / 6.4%; a history curve over-states the season start by
2.4-4 pp - it needs a season-phase term; UNLINKED stays refused); football
BTTS has no skill vs the league base rate, parity and exact score never reach
0.70 (`measure_football_result_model.py`).
**Not modelled yet** (operator 10-07: every market that could win; the next
work, each through a curve and its own Superbet lines). Modelled since: the
double chance, 1X2 (no curve passed), DNB, first goal, reds / penalties,
tennis match / set winner and exact sets score (10-14 / 10-15), the football
score markets and `set_score_not` (10-16 07:46Z). Still not: BTTS alone, half-time /
full-time and the half-result markets, Superbet's `;` combinations, tennis
game order / points in a game / games parity (measured: never 0.70), CS2
round parity (OFFER's `unmapped_markets`, `market_coverage.md` labels each);
derived football / tennis joints and women's tennis per-set markets above
their measured range wait for 50 settled lines a bucket (`NO_LINE_EVIDENCE`).

**Measured and declined - do not re-propose without new evidence:**
- (2026-10-16, walk-forward 10-12..10-15,
  `docs/sofa/evidence/player_line_evidence_2026-10-16.md`) a footballer's
  line-evidence offset measured only on lines with curve x odds >= 0.90:
  the legs it dropped were not measurably worse (-7.3 pp [-22.2, +7.3] vs
  -4.1 kept), it acted on player_shots_for alone and raised tackles (its lines
  fell back to the football pool) - the shape of the 10-12 per-bin offset;
- (2026-10-16, history holdout + Superbet's lines,
  `docs/sofa/evidence/football_score_markets_2026-10-16.md`) the football
  "&" result markets (result & goals, result & BTTS, goals & BTTS, DC & goals
  other than 12 & over / 1X & under) - overstate or never reach 0.70; the
  favourite's European handicap (-5.2 pp); goals parity, exact goals and a
  side's goal intervals (never 0.70); the total goals interval (passes, but 0
  legs clear the coupon at Superbet's prices); copies of read markets ("Każdy
  wygra seta", "Dokładna liczba setów", "liczba setów 1.5": the same event,
  1-3% better price in ~8% of pairs, no new leg);
- a second coupon or a variant (operator: one coupon, many sports);
- a 0.80 confidence floor (operator: "many options");
- current-season-only samples (worse on every metric); same-competition
  samples for corners / fouls / shots / cards (no gain) or for knockouts (worse);
- trimming national-team samples to 180 days (worse log-loss);
- blending the price into confidence or gating on disagreement with it
  (disagreement is an anti-signal; every weight moved to the price only
  copies the price) - the price-band cap is not a blend: it only lowers, and
  only where a band's settled lines measured below the curve (operator,
  2026-10-07);
- league selection / gate tuning (anti-selects out of sample);
- (2026-10-08, out of sample on the history, `docs/sofa/evidence/`):
  hierarchical / empirical-Bayes pooling of team and league effects (worse
  than the fixed K for own counts, +3.1e-4 log-loss); a t copula or a
  per-league-class correlation for joints; Dixon-Coles and bivariate Poisson
  for goals (rho -0.013, kappa ~ 0); zero-inflated NB, empirical and mixture
  families and per-team dispersion for counts; beta / isotonic / spline
  calibration instead of the buckets (-7e-4, ECE no better); a lower
  credible bound on p; a surface-hierarchy or serve/return tennis model;
  exponential-decay memory (half-life 180 d);
- re-ranking peer legs by own-sample size, hit rate, near misses, venue or
  recent form, or by tournament popularity / reserve / women / cup flags
  (2026-10-08: no out-of-sample gain on 62k legs; the pipeline's confidence
  is already the best-measured order).
- (2026-10-12, walk-forward on the printed legs of 10-09..10-11, evidence
  fitted on the days before each) a stricter price-band cap (to the cell's
  realised rate whenever lower): dropped 15% of the legs, which had not done
  worse (ROI -0.6% vs -4.4% kept), and barely moved the over-price gap; an
  offset per confidence-minus-price bin: half the correction, and dropped legs
  that had not done worse either. The over-price gap is flagged instead
  (`price_gap`).
- (2026-10-12 night, `measure_sport_guard.py`, walk-forward on the measured
  sports' settled Superbet lines of 10-07..10-11, evidence fitted on the days
  before each; 1,885 would-print lines / 536 games) a per-key p-bucket cap
  for hockey / basketball / volleyball / CS2: the point cap dropped 135 lines
  that had not done worse (ROI -4.7% vs -5.4% kept); the Wilson cap dropped 8
  that all won. The sports' overstatement is a curve question (basketball's
  history curve reads 0.762 on Superbet lines that realised 0.615, -14.6 pp
  [-19.6, -9.6] before the offset; hockey calibrated), for the next refit.

## Entry points

| you want | use |
|---|---|
| a full betting day - D-1 settled and recorded, the coupon + PDF, reads, verification | `/sofa-day [dzisiaj\|wczoraj\|YYYY-MM-DD]` |
| the analysts' read of an existing coupon ("dodatkowo: <pozycje>" adds to `read_requests.json`) | `/sofa-analyze` |
| coupon + PDF from artifacts on disk (`rebuild_day.py`) | `/sofa-rebuild` |
| adversarial verification of a built day | `/sofa-verify` |
| settle D-1 and decide about constants | `/sofa-settle` |
| price a slip the operator screenshotted | the `bet-slip-audit` skill |

Agents: `sofa-runner`, `sofa-analyst-football`, `sofa-analyst-tennis`,
`sofa-analyst-sport` (one instance per measured sport, read-only),
`sofa-verifier`, `sofa-settler`, `sofa-market-scout`. Skills preloaded into
them: `sofa-pipeline`, `sofa-analysis-core`, `football-analysis`,
`tennis-analysis`. Agent definitions and skills load at session start: an
edited one is live only in the next session.

## Commands

Python runs as `PYTHONPATH=src:. .venv/bin/python ...`. `.venv/bin/python` is
3.12; `.venv/bin/pip` belongs to 3.14 - install with `.venv/bin/python -m pip`.
Exit codes: **0 OK, 1 PARTIAL, 2 FAILED**; PARTIAL on RESOLVE / OFFER /
SAMPLES is the normal shape of a healthy run.

**The day**
```bash
.venv/bin/python scripts/sofa/ensure_bridge.py                                   # always first: brings the bridge up if down, then check_bridge
.venv/bin/python scripts/sofa/check_bridge.py                                    # the grade alone
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --from-stage RESOLVE --run-id <id>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only SHEET --run-id <id>   # after a change of the SHEET estimator: a rebuild re-runs SHEET only on an old-rule sheet (p_central lives in 05_sheet.json)
# SHEET parses the whole football history: ~10 min when the day's listings changed, ~30 s on a rebuild (pickle in data/cache/). A SHEET quiet for 10 min is parsing - do not kill it.
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <d> [--dry-run] [--skip-audits]   # THE rebuild, never the stage scripts by hand: stale prices first (OFFER near 45 min, SHADOW / CS2 near 3 h), SPORT_IDENTITY, SHEET only if refused, FIXTURE_CHECK, CONFIDENCE, SPORT_CONFIDENCE, COUPON_ASSEMBLY, PDF, audits; a finished day refreshes nothing
PYTHONPATH=src:. .venv/bin/python scripts/sofa/day_status.py --date <d>        # one status report: snapshot ages, loops alive, ledger MISMATCH, CLV coverage, UNVERIFIED; no network; exit 0 / 1 WARN / 2 broken
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/shadow_daily.py --date <d> --chain >> runs/sofa/shadow/daily_<d>.log 2>&1 &   # hockey/basketball/volleyball day, unattended: snapshots + SPORT_IDENTITY for D and D+1, morning settles D, D-1, D-2
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/cs2_daily.py --date <d> --chain >> runs/sofa/cs2/daily_<d>.log 2>&1 &         # the CS2 day, unattended; a second loop for the date refuses
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/capture_closing.py --date <d> --loop >> runs/sofa/<d>/capture_closing.log 2>&1 &   # closing price of every printed leg -> closing.jsonl; stops after 12 failed passes. Normally NOT by hand: cs2_daily.py (chained, 23:30Z D-1) and shadow_daily.py (04:30Z D) start it for their date as they start (`capture_closing.ensure_loop`; a live loop for the date is left alone, a second one exits 2); started before the build it waits for 11_coupon.json until the day is over. day_status WARNs `loop:capture_closing` when it is not running and legs are still to close or the coupon is not built yet
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_boosts.py --date <d>        # Superbet boosts snapshot (not the coupon), several times a day; one event's error is skipped (exit 1), an open breaker stops (exit 2)
```
A loop step that runs past `cs2_daily.STEP_TIMEOUT_S` (6 h, >= 3x the longest step measured 09-28..10-12) is killed with its process group and logged `STEP_FAILED TIMEOUT`, like any failed step. `day_status.py` also WARNs on sport identity (`identity`: any BRIDGE_ABORTED, or below hockey 85% / basketball 75% / CS2 45% / volleyball 25% with >= 10 events, CS2 1x1 duplicates excluded). A daily loop reads its plan when it starts: one started before a code change
runs its old steps until it ends.

**Single stages** (`rebuild_day.py` runs them in order; by hand only to debug)
```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_fixture_check.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only SHADOW
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only CS2
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_identity.py --date <d> [--sport hockey] [--if-snapshot]   # --if-snapshot: no snapshot = NOTHING_TO_DO, exit 0 (the loops' D+1 run)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_confidence.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon.py --date <d>        # exit 1 while 08_confidence_sports.json is absent
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <d>
```

**Settle and record**
```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only SHADOW_SETTLE
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only CS2_SETTLE
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_cs2.py --sweep-from <D-7> --sweep-to <D-2>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/refresh_sport_history.py [--days 14] [--dry-run]   # bridge; run first by refresh_line_evidence.py: the sports' games that should have ended enter the history
PYTHONPATH=src:. .venv/bin/python scripts/sofa/refresh_line_evidence.py --before <D> [--dry-run] [--skip-sport-rows] [--skip-history]   # EVERY morning (bridge up first: step 0 refreshes the sports' history) after D-1 is settled and recorded, before D's build: four sport row fits (--dry-run inside, no curve touched, ~15-20 min) + fit_line_evidence; rows in data/line_evidence/rows_before_<D>; exit 1 = a sport's row fit failed, its earlier rows reused
PYTHONPATH=src:. .venv/bin/python scripts/sofa/resettle_sweep.py --from <D-14> --to <D-2> --include-day <D-5>   # every morning; bridge (none: exit 1, nothing done)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settle_identity.py --from <d> --to <d> [--sport all]   # after D-1's settle; exit 1 on a finding
PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --from <D-8> --to <D-1>   # also marks each day's KUPON pdf / html with its results (--no-mark: not)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/mark_coupon_results.py --from <d> --to <d> [--force] [--no-render]   # 13_results.json + KUPON pdf / html coloured by result; offline
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py --from <d> --to <d> [--variant official]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/regrade_settled.py --moved-void --dry-run   # then --apply; --players regrades props from the own squad
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_shadow.py --from <d> --to <d> [--sport hockey]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_cs2.py --from <d> --to <d> [--history]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_clv.py --from <d> --to <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_boosts.py --from <d> --to <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_niches.py --from <d> --to <d> [--min-matches N]   # evidence, never a bet list
PYTHONPATH=src:. .venv/bin/python scripts/sofa/purge_entity_alias.py --dry-run   # a wrongly verified team alias; --list-suspects
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_entity_map.py [--dry-run] [--reteach]   # identity plan K1, once: the entity map learns from every sport_fixtures.json / RESOLVE day on disk; --dry-run rolls back; --apply backs up sofa_entity first
PYTHONPATH=src:. .venv/bin/python scripts/sofa/report_entity_queue.py --date <d>   # identity plan K4: the NEEDS_ALIAS queue (OPEN conflicts and candidates, ready JSON entries for config/sofa_entity_aliases.json) -> runs/sofa/<d>/entity_queue.md; no network
```

**Refit - on a copy of the DB, installed only with the operator's go** ("Changing the pipeline" 4; `docs/sofa/CONFIG.md` section 7)
```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date <d> [--db-path <copy>] {backup [--db <path>]|rebuild-cache-rows [--dry-run|--confirm] [--without-db-backup] [--derived ...] [--no-tennis-rating]|fit|compare [--days <d> <d2>] [--with-sheet]|install --confirm|restore --confirm --backup <dir>}
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_confidence.py --classes-only   # only the by_class curves
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_confidence.py --db-path <replay copy> --out <staged copy of the installed calibration> --line-curves-only   # only the per-line curves (bet.sofa.line_curves); every other key byte-for-byte
PYTHONPATH=src:. .venv/bin/python scripts/sofa/install_line_curves.py --staged <staged file> (--dry-run | --confirm) [--backup-dir config/backup_<d>_line_curves]   # takes only by_market_direction_line; refuses a staged file differing elsewhere; backup, tests/sofa, restore on failure
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_tennis_serve_curves.py --before <d> --out-dir data/refit_tennis_serve_<d> [--played-cache f.pkl]   # tennis serve curves (aces under the correction, per-set serve, serve points) on a tennis-only replay, read-only on the DB; staged for install_new_market_curves.py (group tennis_serve REPLACES its markets); NOT installed - see "Measured and not switched on, tennis serve markets"
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_score_market_curves.py --out-dir data/refit_new_markets_<d> --football-rows <1x2/dnb fit rows.csv.gz> --tennis-rows <tennis_sets rows.csv>   # score-market slice curves + set_score_not, staged; install with install_new_market_curves.py --dir
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_sport_confidence.py --sport {hockey|basketball|volleyball|cs2|all} --before <d> [--dry-run] [--rows-out <dir>] [--bb-freshness auto|on|off]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_settleability.py --before <d> [--dry-run]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_sport_confidence.py --sport all --before <d> --dry-run --rows-out <dir> --out <dir>/cal.json   # ~15 min a sport: the Superbet rows line evidence reads
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_line_evidence.py --before <d> --sport-rows-dir <dir> [--dry-run]   # after every curve refit (refresh_line_evidence.py does it daily); without the dir: no price-band cap for the sports
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_calibration.py --from <d> --to <d> [--epoch stats_only] [--write-config --before <d>]   # PASS n>=300 and |gap|<=2 pp
PYTHONPATH=src:. .venv/bin/python scripts/sofa/find_women_competitions.py
PYTHONPATH=src:. .venv/bin/python scripts/sofa/find_friendly_competitions.py --out docs/sofa/evidence/friendly_candidates_<d>.json   # candidates; a person decides
```

**History backfill** (bridge; short chunks, resumable)
```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_listings.py --sport {football|tennis|hockey|basketball|volleyball} --days 730 --max-minutes 7
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_event_stats.py --sport {football|tennis} --days 365 [--board-days 7] --max-minutes 7
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_football_lineups.py --days 365 --max-minutes 7
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_cs2.py --days 180
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_event_extra.py --kind {shotmap|point_by_point|incidents} --sport {football|tennis|hockey|basketball|volleyball} --days 120 --max-minutes 7   # sofa_event_extra; incidents: the measured sports' finished games (football's are in sofa_event_stats)
```

**Measurement** (read-only evidence for a decision, never a gate)
```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_count_families.py [flags: see the evidence doc]  # distribution family per count market (2026-10-08)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_pooling.py [flags: see the evidence doc]  # pooling / per-market K / league effect
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_k_under_dispersion.py   # per-market K under the fitted dispersion; flags: see the evidence doc
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_dependence_goals.py [flags: see the evidence doc]  # copulas, side correlations, goals model
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_calibration.py [flags: see the evidence doc]  # tennis rating scopes, calibration method, intervals
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_count_dispersion.py --before <d> --cases <dir> [--write]   # without --write a dry run; --write writes config/sofa_count_dispersion.json atomically (a dry run reads nothing; the installed file is read from 2026-10-09 00:00Z)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/report_market_coverage.py --date <d> [--sports|--sports-only] [--sports-raw-dir <dir>] [--sports-out-dir <dir>]   # --sports: hockey/basketball/volleyball/CS2 unread names (SHADOW/CS2 record none, so a live Superbet probe of the day's pre-match events, or saved payloads) -> market_coverage_sports.*
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_settleability.py --from <d> --to <d> [--with-fit] [--json-out f] [--md-out f]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_blocked_families.py [--from <d>] [--to <d>]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sport_identity.py --from <d> --to <d> [--sport hockey]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_defects.py [--start <d>] [--end <d>]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_own_sample_gap.py --from <d> --to <d> [--sport football|tennis]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sample_composition.py [--start <d>] [--end <d>] --metrics goals_for corners_total
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_schedule_context.py [--start <d>] [--end <d>]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_score_model.py --sport {hockey|basketball|volleyball} --date <d> [--date <d2>] [--rows-out f]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_score_history.py --sport <s> --start <d> --end <d> [--params '{...}']
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_information.py --rows <rows.jsonl>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_player_props.py --sport {basketball|hockey} [--date <d>] [--rows-out f]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_devig.py --from <d> --to <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/probe_lineup_availability.py --date <d> [--dry-run] [--summary]   # not yet run
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_league_rate_rule.py [--from <d>] [--to <d>] [--skip-football]   # audit A2 (T-A2-league-rate-refusals)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_bucket_design_effect.py --rows-dir <dir> --days <d>...   # audit A4 walk-forward (T-A4-bucket-deff)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_unit_strength.py [--from <d>] [--to <d>]   # audit A1
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sport_derived.py --sport all --start <d> --end <d> [--max-games 4000] [--json-out f] [--md-out f]   # SPORT_DERIVED_MARKETS: double chance / volleyball sets keys on the history walk-forward, log-loss vs base, calibration, share >= 0.70
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_settled_by_market.py --from <d> --to <d> [--p-min 0.70] [--min-n 20] [--md-out f] [--json-out f]   # every sport, every market x direction: n, hit, raw model p, 1/odds, ROI + game bootstrap; sports never pooled
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_team_identity.py [--from <d>] [--to <d>] [--sport all|football|...] [--md-out f] [--json-out f]   # identity plan K0: UNEXPLAINED events / players per kickoff day, sport and entity (IDENTIFIED / EXCLUDED / EXPLAINED / UNEXPLAINED); names judged on today's DB; T-IDENTITY-unexplained
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_day_anchor.py [--from <d>] [--to <d>] [--md-out f] [--json-out f]   # identity plan K2: DAY_ANCHOR precision with the opponent hidden, picks on NOT_IDENTIFIED vs the settle, start gaps
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tournament_day.py --from <d> --to <d> [--precision-days 60] [--offline]   # identity plan K3: ASKS THE BRIDGE once per (tournament, day) not cached; tournament-day match precision with ids hidden and recovery; stops at a refusal
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sport_incidents.py --sport {hockey|basketball} [--json-out f] [--md-out f]   # "1. gol" / race to X from the score model, walk-forward on cached incidents
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_aces_opponent.py --cut 2026-01-01 [--played-cache f.pkl] [--md-out f]   # TENNIS_ACES_OPPONENT on the tennis cache replay (both arms, curve on train, log-loss on test, all and market-like lines); ~25 min, tennis only
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_line_curves.py --db data/refit_2026-10-17/sofa_replay.db [--md-out f] [--json-out f]   # per-line vs pooled curve, football, out of sample on the replay at Superbet's quoted lines (~3 min); chose config/sofa_line_curves.json
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_selection_walk_forward.py --from <d> --to <d> [--md-out f]   # T-FAMILY-SELECTION: the view's family / x selections walk-forward on the printed legs, plus the calibration gap and ROI by confidence - 1/odds per sport
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_red_flags.py --from <d> --to <d> [--md-out f]   # red flags on the printed legs (scenario s >= +0.5, confidence above own k/n, builders, long price): flagged gap minus control, 98.75%; offline, ~20 s; T-RED-FLAG-SCRIPT
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_serve_market_line.py --from <d> --to <d> --staged data/refit_tennis_serve_2026-10-17 [--md-out f]   # T-TENNIS-SERVE-MARKET-LINE: staged vs installed serve curves through the line evidence on Superbet's settled lines; aces re-priced by SHEET with / without the correction
```

**Gates before a commit**
```bash
.venv/bin/python -m pytest tests/sofa -q
.venv/bin/python -m ruff check src/bet/sofa scripts/sofa
.venv/bin/python -m mypy --strict --no-incremental src/bet/sofa scripts/sofa   # a stale mypy cache gives false errors
PYTHONPATH=src:. .venv/bin/python scripts/sofa/check_test_registry.py
```

## Hard rules

- **The PDF rendered from `11_coupon.json` is the coupon.** Reporting
  `06_coupon.json`, `p_bar` or `08_confidence.json` as the coupon inverts the day.
- **Never invent** a number, a fixture, a price or an availability.
- **Never print a combined / Bet Builder / parlay price**, and never present
  `odds_if_product` as one - Superbet does not price a slip as the product of
  its legs (measured markup 8.8–19.6%).
- **No stake sizing, no automated placement.** The stake is the operator's.
- **A slip assembled in chat is not a coupon and has no gates - so say no
  first.** When the operator asks for N slips, a target price or disjoint
  slips and the day only supports fewer, say so plainly in the first line
  ("dzień cienki - masz jeden kupon" / "dziś żadnego") instead of filling
  the request with weaker legs. "Supports" is measured, not felt: first scan
  the whole window for legs of the market families whose printed legs
  realised at or above their price on the latest settled days (name the
  days and N; match bootstrap; one family in twenty clearing zero is what
  chance gives - say so), and inside a match prefer such a leg. Every table
  the operator may stake from carries that measured chance (a `price_gap`
  leg at its price, never its confidence) and says "na minusie" when it is
  below the price - in **every** re-summary, not only an earlier message.
  The product of confidences is never the headline. (2026-10-12: three
  slips, two of them -EV by our own numbers, the caveat dropped from the
  table the operator staked from.)
- **A leg proposed in chat is named in Superbet's words** - its
  `superbet_market: superbet_selection` from `11_coupon.json`
  (`bet.sofa.superbet_names.names` for a leg of another artifact), never a
  paraphrase like "Seattle +1.5 w 3. tercji": the operator finds it on the
  screen by that name, and "+1.5" beside "Poniżej 1.5" is a misclick
  (2026-10-15, Tampa - Seattle).
- **Never read, echo or log `.env` values.**
- **Curves are fitted on the history of events and statistics** (operator,
  2026-10-07: "nasze źródło to historia statystyk"), replayed as of each match
  with the estimator the sheet uses today (rating included). Our own settled
  days are an audit of a curve, never its source; line evidence (offsets, price
  bands) is a guard that only lowers, and any number it holds is reported as
  measured on N days.
- **Never re-fit or install constants or calibrations without the operator's
  go**, and never into a day already built (except the 2026-10-13 audit's
  standing go, "Changing the pipeline" 4): a refit runs on a copy of the DB,
  installs only after `tests/sofa` pass.
- **A pooled number must say what it pooled across.** Friendlies are out of
  samples and ratings (`bet.sofa.comparability` is the one "does this past
  match count" rule). "History is thin" is not an argument before
  `backfill_listings.py` has run.
- **Never strip `UNFITTED_CONSTANTS`** from a row or a report.
- **Sofascore and Superbet only** - no other data provider in the pipeline.
  Superbet `190` (virtual football), `75` (e-football), `157` (e-hockey) and
  `70` (e-basketball) are simulations - never add them.
- A settled result is a fact about the day, **not about the decision that made
  it**. "It won" never enters the reasoning for the next one.

## The bridge (Sofascore through a real browser)

- **`MIN_INTERVAL_MS = 350` in the userscript is the safety mechanism and is
  never lowered.** It paces each connection; capacity comes from more tabs,
  never a faster tab. (2026-09-17: one `curl_cffi` client, 100 workers,
  550 req/s, no browser - the shape the bridge exists to prevent.)
- **Open the windows with `launch_bridge_browser.py`;** they may be minimised.
  Its launch flags stop Chrome clamping a hidden page's timers to >= 1000 ms
  (which silently cut a tab to ~1 req/s). They are process-creation flags, so
  Chrome must be fully quit first; the script refuses otherwise.
- **`SOFA_MAX_CONCURRENCY` is the window count — never below it.** Measured
  2026-09-22, five windows:

  | `SOFA_MAX_CONCURRENCY` | achieved | p50 | p90 |
  |---|---|---|---|
  | 3 | 0.15 req/s | 20,138 ms | 20,162 ms |
  | **5** | **11.67 req/s** | **354 ms** | **620 ms** |
  | 8 | 11.72 req/s | 668 ms | 704 ms |
  | 12 | 11.66 req/s | 1,010 ms | 1,056 ms |

  Above the window count only latency grows (queue depth → `STALE_PRICE`);
  below it the bridge collapses. Change it together with `--windows` and
  re-run `measure_bridge_capacity.py`.
- **`SOFA_TARGET_RPS` sits above what the tabs serve** (5 x 2.86 = 14.3 req/s,
  so 20). A starved bucket idles the tabs.
- **Measure the round trip, not the wall clock around the client** - the token
  bucket is inside the client; use `p50 net` from `measure_bridge_capacity.py`.
- **Refusals happen.** Sofascore has answered 403 bursts (5 x 403 in one
  instant) during long runs at full width (2026-09-28, -29, -30; once only a
  hand-solved challenge helped). Unmeasured suspicion: a token lasts ~25 min
  under sustained load. Backfills run short and resume; a refusal means slow
  down - never refresh tokens pre-emptively to outrun it.
- **Superbet has a breaker too:** 3 failures (403 / 429 / 5xx / timeout; a 404
  is an answer) open it (`SOFA_BREAKER_*`). OFFER keeps the unasked fixtures'
  old entries (CONFIDENCE refuses them STALE_PRICE); an all-refused SHADOW /
  CS2 snapshot is FAILED.
- `SOFA_NOW` freezes `timeutil.now()` for as-of replays only; `run_pipeline.py`
  refuses it.

## Working style

- **Evidence or it did not happen.** A claim about the pipeline names the file
  and line, or the artifact and field. An unmeasured statement is marked as a
  suspicion.
- **A skipped check is named.** If a run went clean, a guard was *not tested* -
  never "it works".
- **Check a subagent's numbers** when you can check them locally.
- Live runs are deliberate: hours of bridge time, visible to a third party's
  production API.

## Language and repository

Operator-facing documentation in `docs/sofa/` is **Polish** (so are the
analysts' reports). Code, tests, this file and the `.claude/` contracts are
**English**. `data/sofa.db` is the only working database. The slip calculator
is `scripts/sofa/audit_slip.py` (`bet.sofa.slip_audit`); the operator's builder
method is `docs/sofa/SUPERBET_BET_BUILDER_METHOD_v3.md`.
