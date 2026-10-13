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
| `KUPON_<d>.html` | the same legs as a filterable page (time window in Europe/Warsaw, confidence, sport, competition, market, odds, sortable; a start the FIXTURE_CHECK read differently is flagged). A **view**, not a coupon - `bet.sofa.coupon_html`, written by `build_coupon_pdf.py` after every PDF render, so a rebuilt PDF always brings its HTML (HTML failure: PDF kept, exit 1); alone: `build_coupon_html.py --date <d>` |
| `reads.json`, `vetoes.json`, `read_requests.json` | analysts' per-leg verdicts, vetoes, the operator's extra positions |
| `fixture_status.json`, `sport_fixtures.json` | FIXTURE_CHECK's fresh starts / statuses; the pinned Sofascore ids of sport games |
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
  **not** the estimator SHEET prices with in two places (audit 2026-10-13, A6,
  `calibrate_from_cache.py:1064-1072`): football rating (`W_FOOTBALL_RATING`
  0.5 in the live centre) is replayed in no football centre, and the tennis
  tier / ladder priors are not replayed; tennis neighbours are
  `tennis_rating.AsOfRating` (best-of-five skipped). Football goals joints are
  not replayed and `DERIVED_CURVES_FROM_UTC` is off. Curves refitted
  that way were installed 2026-10-07 17:51Z: a new comparability epoch.
  Hockey / volleyball curves are the installed file's (the `.next.json` of
  2026-10-07, promoted 2026-10-13); CS2's from 2026-10-14 the staged one.
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
- **Player names** (`PLAYER_NAME_TOKENS_FROM_UTC`, 2026-10-12 00:00Z): a
  footballer `players.match_player` finds in no squad is looked for by whole
  name tokens (`match_player_by_tokens`: >= 2 shared, one candidate, one
  side) - Superbet writes full registered names ("Andrade, Matheus Araujo"
  vs "Matheus Araujo"; 346 of 680 `NO_ENTITY_FOUND` players of 10-08..10-10).
  The sample says `match_rule: "tokens"`, the sheet row `PLAYER_NAME_TOKENS`.
  Evidence: `docs/sofa/evidence/player_name_tokens_2026-10-11.md`.
- **Player starts** (operator, 2026-10-11): Superbet voids a footballer's
  market unless he STARTS. SETTLE says `PLAYER_NOT_STARTED`; from
  `PLAYER_STARTS_ONLY_FROM_UTC` (2026-10-12 00:00Z) the sample is his starts
  (`appearances: "starts"`, note `PLAYER_STARTS_ONLY`; bucket-calibrated out
  of sample -0.0027 log-loss [-0.0030, -0.0024] against all appearances) and
  the player curves are refitted on starters' outcomes from their starts,
  staged in `config/sofa_confidence_calibration.next.json` (`effective_from`
  2026-10-12 00:00Z, `confidence.calibration_path_for`; every non-player
  curve identical). Promote it over the installed file once no day <= 10-11
  is rebuilt. Evidence: `docs/sofa/evidence/player_starts_2026-10-11.md`.
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
  (`scripts/sofa/measure_price_gap.py`); check on new data: `T-PRICE-GAP-flag`.
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
  (`settled_shadow_rows`) applies the day's rule; the history curves take it
  with the basketball refit. Football's half
  (`FOOTBALL_LEAGUE_RATE_RULE_FROM_UTC`) is measured worse and stays `None`.
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
  (2026-10-14 00:00Z, audit B10) a team's rounds on a map come from the round
  race (`cs2_engine.team_rounds_from_race`, the map's score distribution the
  round handicap uses), live, at CS2_SETTLE and in the replay; walk-forward
  log-loss -0.0213 [-0.0237, -0.0188]; the CS2 curve refitted on it is staged
  in the `.next.json` from 2026-10-14 (the previous `.next` was promoted over
  the installed file on 2026-10-13). Still unpriced: CS2 series rounds (rounds_*,
  team_rounds) and round parity.
- Hockey / basketball player lines: p = player_model's pre-game number in
  SHADOW's `player_model.jsonl` (reads SPORT_IDENTITY's pinned teams before
  names, `teams_source`); no history curve, so `NO_LINE_EVIDENCE` until a
  family's p bucket holds 50 settled pre-game lines; graded from
  SHADOW_SETTLE's own player row.
- Basketball second half / Q4 grade on the regulation periods - overtime does
  not count (operator, 2026-10-07); full-game basketball markets include it.
- A hockey / basketball game Sofascore publishes with no periods (only
  `current` and `winnerCode`) is graded from its final score
  (`shadow.build_result(..., allow_final_only=True)`, SHADOW_SETTLE only;
  `score_source: "final_only"`): full-game markets, regulation where
  `normaltime` (or no sign of overtime) tells it, never a period / half /
  quarter. Until 2026-10-12 such a game stayed DATA_MISMATCH for good
  (10-22 basketball games a day from 10-07). History readers keep the
  default and never see it.

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
  and ratings still skip both (changing that changes what prints). Player props grade only from the player's own squad
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
- **Ledger** (`record_results.py` -> `runs/sofa/ledger/results.jsonl`, read
  with `audit_ledger.py`): the coupon's result, the legs removed by reads and
  each sport kept side by side, never pooled. It reads `sofa_settled_row`, so
  re-run it after any `regrade_settled.py`. Exit 0 with legs pending, 1 on a
  `MISMATCH` (two graders disagree - a defect), 2 on a crash.
- **Comparability:** the current rules apply from 2026-10-06; a refit install
  or an epoch switch starts a new epoch (the latest: the audit switches of
  2026-10-14 00:00Z - LEAGUE_RATE_RULE, BUCKET_DESIGN_EFFECT,
  CS2_TEAM_ROUNDS_RACE with its CS2 curve - ledger group
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
**Measured, registered threshold met, `None` until the football refit (stage 4: the curves must be fitted on the same centre)**
(one step ahead on the history 2025-08-01..2026-10-12, NB log-loss of the
centre at the count - not Superbet lines, the replay has no rating, A6):
`GAME_STATE_FROM_UTC` (B1: side centre x exp(beta x expected goal
difference), betas in `config/sofa_game_state.json`, `fit_game_state.py`;
corners_for -0.0149 [-0.0160, -0.0138], shots_for -0.0150, cards_points_for
-0.0043, fouls_for -0.0002 [-0.0004, -0.00003] per side, walk-forward betas;
`docs/sofa/evidence/game_state_2026-10-13.md`),
`FOOTBALL_RATED_SCOPE_FROM_UTC` (B2: the rating on
`football_rating.RATED_SCOPE_MARKETS` = cards_points_for, corners_1h/2h_for,
offsides_total; the corners totals stay unrated, corners_total worse
+0.0009 [+0.0003, +0.0015]) and `FOOTBALL_VENUE_PRIOR_FROM_UTC` (B2: league
home / away multiplier on a sample-only corners_1h/2h_for centre;
`docs/sofa/evidence/unrated_markets_2026-10-13.md`). B1's cards beta was
fitted on the unrated centre: refit it if both go on.

**Waiting for the operator** (switches off, `None` in `bet.sofa.epochs`):
`CURVE_STATUS_FROM_UTC` (a curve failing `measure_calibration.py` stops
printing), `MODEL_FIXES_FROM_UTC` (tennis NB dispersion; with the next refit),
`BUILDER_SCREEN_PRICE_FROM_UTC` (switched off 2026-10-05: sofa does not price
builders), `CARDS_CORRELATION_FROM_UTC` (the one staged package left; needs
`DERIVED_CURVES_FROM_UTC` to be read at all), `DERIVED_CURVES_FROM_UTC` (derived joints read a history curve;
needs a refit carrying the replayed joints), `MAPPABLE_FAMILIES_FROM_UTC`
(OFFER reads the MAPPABLE families of `bet.sofa.market_coverage`: "<club>
strzeli gola" and halves as goals_*_for 0.5, "Zostanie rozegrany N. set" as
sets_total N-0.5, half BTTS, both-over saves, half corner / set games
handicaps - `market_mapper.classify_mappable_family`; a yes/no answer never
adds a second rung where the ladder quotes one; off = OFFER byte-identical,
`docs/sofa/PIPELINE.md` section 5), the coupon form dials. Open
questions: Superbet's game count of a tennis match tiebreak. Measured
2026-10-12 night: the line-evidence offsets of the repriced families moved
<= 1.3 pp a day over 10-09..10-12 (stable, reproduced from the legs); the
tennis `games_won_for` OVER offsets (-8.5 men, -12.1 women) were measured on
old-estimator rows, while the new estimator's rows are calibrated there
(-0.2 pp, n 117) - over-lowered, a candidate (evidence on rows >= 10-09 for
the repriced families) once a walk-forward has the days.
**Before the next refit:** measure the admitted football props separately;
measure the tennis games population of replay matches without `/statistics`;
queued: CS2 `map_team_rounds` from the round race, football joints with the
football rating in their centre.
Current backups: `config/backup_2026-10-05`,
`config/backup_2026-10-06_sport_calibration/`, `config/backup_2026-10-08`,
`config/backup_2026-10-09`,
`data/backup_2026-10-05/sofa.db`; `data/refit_2026-10-08/sofa_replay.db` is
the DB the installed curves were fitted from (`fitted_from.db_path`) - keep it.

**Measured for the next refit (2026-10-12 night, out of sample on the history,
`docs/sofa/history/RAPORT_NOC_2026-10-12.md`):** tennis match winner from the
as-of rating -0.1232 log-loss vs base, calibrated +-1.3 pp, 45.7% of matches
>= 0.70 (`measure_tennis_outcome_model.py`; then set-1 winner, set score);
football DNB / double chance / 1X2 from the pure rating centre with NB r ~7
(skill 11.7 / 6.2 / 6.4%; a history curve over-states the season start by
2.4-4 pp - it needs a season-phase term; UNLINKED stays refused); football
BTTS has no skill vs the league base rate, parity and exact score never reach
0.70 (`measure_football_result_model.py`).
**Not modelled yet** (operator 10-07: every market that could win; the next
work, each through a curve and its own Superbet lines): football / tennis
outcome markets - 1X2, double chance, draw-no-bet, both teams to score, goals
parity, half-time/full-time, exact score; tennis match / set winner, set
score, games parity (OFFER's `unmapped_markets`, ~27,800 lines on 10-07,
part of them Superbet's own combinations); CS2 series rounds and round
parity; derived football / tennis joints and women's tennis per-set markets
above their measured range wait for 50 settled lines a bucket
(`NO_LINE_EVIDENCE`).

**Measured and declined - do not re-propose without new evidence:**
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
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/capture_closing.py --date <d> --loop &   # closing price of every printed leg -> closing.jsonl; stops after 12 failed passes
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
PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --from <D-8> --to <D-1>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py --from <d> --to <d> [--variant official]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/regrade_settled.py --moved-void --dry-run   # then --apply; --players regrades props from the own squad
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_shadow.py --from <d> --to <d> [--sport hockey]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_cs2.py --from <d> --to <d> [--history]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_clv.py --from <d> --to <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_boosts.py --from <d> --to <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_niches.py --from <d> --to <d> [--min-matches N]   # evidence, never a bet list
PYTHONPATH=src:. .venv/bin/python scripts/sofa/purge_entity_alias.py --dry-run   # a wrongly verified team alias; --list-suspects
```

**Refit - on a copy of the DB, installed only with the operator's go** ("Changing the pipeline" 4; `docs/sofa/CONFIG.md` section 7)
```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date <d> [--db-path <copy>] {backup [--db <path>]|rebuild-cache-rows [--dry-run|--confirm] [--without-db-backup] [--derived ...] [--no-tennis-rating]|fit|compare [--days <d> <d2>] [--with-sheet]|install --confirm|restore --confirm --backup <dir>}
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_confidence.py --classes-only   # only the by_class curves
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
