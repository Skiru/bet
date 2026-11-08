# R1 - Tennis inventory for a schedule / fatigue correction (read-only, 2026-11-08)

Scope: tennis only. Everything below is read from code / config / run artifacts in
`/Users/mkoziol/projects/bet`; nothing was run against the network, no refit, no edit.
Inference is marked **SUSPICION**.

---

## 0. One-paragraph answer

Tennis p_central comes from **three estimators**: (A) the **rating** (`tennis_rating.py`:
surface-blended Elo + per-tier logistic calibration with the rest features
`dmin78 / drest / dn7 / dform`), read either directly (`match_won_for`) or through its
**600 neighbours selected by p_home alone**; (B) the **bottom-up point model**
(`tennis_point_model.py` via `tennis_point_sheet.py`) for per-set games totals, every
serve-count key and (from 11-06 17:30Z) per-set games handicap - it reads **no rest /
fatigue at all** (only `drift_per_day`, which widens a belief's variance with time since
the last observation); (C) the **old sample estimator** (players' last 10 matches, tier
prior) for `tiebreaks_total`, the `most_*` / `handicap_aces` serve joints and half of
`games_total`. Fatigue therefore reaches today only through the rating's p_home, and the
neighbour read means it can shift the *level* (who is favoured) but never the *shape*
of a score distribution beyond what p explains. `dmin78` is close to blind at ITF:
`time.periodN` (set durations) is present on ~18% of recent finished ITF listings vs ~98%
CH / TOUR, and a missing duration counts as 0 minutes.

---

## 1. Every tennis market family mapped and priced

Authoritative lists:

| list | file:line | contents |
|---|---|---|
| `TENNIS_METRICS` (sample / settle metrics) | `src/bet/sofa/metrics.py:569-700` | games_total, games_won_for, sets_total, match_won_for, aces_total/_for, double_faults_total/_for, tiebreaks_total, serve_points_total/_for (= aces + DF), aces/double_faults/serve_points _set1/_set2 _total/_for, games_won_set1/2/3_for, games_set1/2_total |
| derived prefixes `most_` / `handicap_` | `src/bet/sofa/market_mapper.py:777,787,808,962,1067`; priced `src/bet/sofa/derived.py:450+` | handicap_games, most_games, handicap_games_won_set1/2, handicap_aces, most_aces(_set1/2), most_double_faults_set1/2, most_serve_points(_set1/2) |
| set markets | `src/bet/sofa/tennis_sets.py:52-69` (`SET_MARKETS`) | set1_won_for, set2_won_for, set_score ("2:0".."0:2", OVER only), set_score_not (complement, "wygra seta", "bez straty seta", set handicap +-1.5) |
| match winner | `src/bet/sofa/tennis_winner.py` (`MATCH_WON_FOR`) | match_won_for, line 0.5 two-sided |
| rating-readable / priced | `src/bet/sofa/tennis_rating.py:128-155` | `RATED_MARKETS` {games_total, games_won_for, sets_total, handicap_games}; `_READABLE_MARKETS` + tiebreaks_total, games_set1/2_total, games_won_set1/2/3_for, most_games; `RATING_PRICED_MARKETS` {games_won_for, handicap_games, most_games}; `SET_RATING_PRICED_MARKETS` {games_set1/2_total, games_won_set1/2/3_for, sets_total}; `W_GAMES_TOTAL_RATING` 0.5 |
| point model scope | `src/bet/sofa/epochs.py:3753-3758` (`TENNIS_POINT_MODEL_MARKETS`, 20 keys) and `:3920-3925` (`TENNIS_HANDICAP_POINT_MODEL_MARKETS`) | games_set1/2_total; {aces, double_faults, serve_points} x {match, set1, set2} x {_for, _total}; handicap_games_won_set1/2 |
| totals floor | `src/bet/sofa/epochs.py:3692-3713` | games_total, sets_total pass at 0.60 (`leg_floor`) |

Observed in 08_refusals.json of 17 days (10-21..10-29, 11-01..11-08) - 44 families, no
others (`games_won_set3_for` is mapped/readable but no row appeared). Not read at all
(display only / unmapped): game-order / "after N games" markets (point_by_point backfill
exists for them, `scripts/sofa/backfill_event_extra.py:9-10`), parity of games
(SUSPICION: in `unmapped_prices`, not checked).

## 2. Estimator per family (what produces p_central, from 2026-11-07)

Dispatch in SHEET: `scripts/sofa/run_sheet.py:3086-3100` (point model covers the row),
`:3157-3200` (rating p, `set_rated`, `rating_prices`), `:3252-3258` (games_total mix),
`:3260-3270` (point model replaces p_raw). Note: `forecast_source: tennis_rating` on a
sheet row is the published *second number*, not necessarily the p_central estimator
(e.g. games_set1_total rows carry `tennis_rating` while p_central is the point model's).

| family | p_central estimator | where |
|---|---|---|
| match_won_for | rating `p_side_wins` (= calibrated p_home), no sample, no price | `tennis_winner.py`; `tennis_rating.py:650` |
| games_won_for | rating neighbours (subject's own pool) | `RATING_PRICED_MARKETS`, `MatchForecast.read` `tennis_rating.py:661-720` |
| handicap_games | rating neighbours (subject's margin > -line) | same; via `derived.price_derived_rungs` rating_p |
| most_games | rating neighbours (margin > 0) | same |
| sets_total | rating neighbours (sets count) | `SET_RATING_PRICED_MARKETS`, epochs `TENNIS_SET_RATING_PRICES` 10-13 18:10Z |
| games_won_set1/2(/3)_for | rating neighbours (set3 conditional on a full third set) | same |
| set1/2_won_for, set_score, set_score_not | rating neighbours of the HOME player (`set_win_p`, `score_probs`) | `tennis_sets.py:215-240`; run_sheet `:2108-2165` |
| games_total | 0.5 x rating neighbours + 0.5 x NB of the two players' last-10 sample (tier x gender x surface prior) | `run_sheet.py:3192-3196, 3252-3258` |
| games_set1/2_total | **point model** (4,000 sims, seeded by event id) | `tennis_point_sheet.py`; `TENNIS_POINT_MODEL_FROM_UTC` 11-06 00:00Z |
| aces / double_faults / serve_points, match + set1/2, _for/_total (18 keys) | **point model** (simulated serve points x ace/DF rate, NB shapes) | `tennis_point_sheet.mean_sd` |
| handicap_games_won_set1/2 | **point model** (set margin), before 11-06 17:30Z rating neighbours' own set margins (R2, 10-28) | `tennis_handicap_point.py:57-80`; `derived.py:795-815` |
| tiebreaks_total | sample (two players' last 10, normal / empirical) | old path; curves live-only-stripped |
| most_aces(_set1/2), most_double_faults_set1/2, most_serve_points(_set1/2), handicap_aces | derived joint of the two players' samples (rho), **not** the point model | `derived.py:329-450` |

### 2a. The rating (`src/bet/sofa/tennis_rating.py`)

- History: `load_history` (`:356`) reads `sofa_entity_events` kind=last + the listed-event
  index; `parse_event` (`:285-353`) keeps finished singles "Ended"/"Retired" (walkovers out,
  exhibitions out). `minutes` = sum of `event.time.period1..N` seconds / 60, **None unless
  every set has a duration** (`:330-333`). Retired matches are logged (minutes, played
  count) but never update Elo nor enter the neighbour table (`completed`).
- Elo: overall + per surface family (hard/clay/grass, `surface_family` `:193`; indoor folded
  into hard), K = 250/(n+5)^0.4 (`:404`), `update` `:500-529`.
- Features (`RatingBook.features` `:473-498`, all home minus away):

| feature | exact meaning in code |
|---|---|
| `lp` | logit of overall-Elo win probability (clamped 1e-3) |
| `lp_t` | V5: overall Elo with newcomers started at 1500 + tier offset (`tier_start`), gap x ln10/400, unclamped; **the installed config uses `lp_t` in place of `lp`** |
| `lps` | logit of the surface-blended Elo p (0.5 overall + 0.5 surface family) |
| `dmin78` | (minutes on court in the previous 78 h, home - away) / 60 -> **hours**; only matches whose `minutes` is known count (`_context` `:452-471`) |
| `drest` | 1 if the player's last logged match is > `REST_DAYS` 21 days before the start, else 0; difference in {-1,0,1}; no history = 0 |
| `dn7` | difference in matches (any logged, retirements included) in the previous 7 days |
| `dform` | (current overall Elo - overall Elo before the 5th-last match) home minus away, / 100; 0 if < 5 past matches |
| `dhigh` | difference in career share of matches above ITF (CH or TOUR) |
| `dtour` | difference in career share of TOUR-level matches |

- Logit: `calibrated_p` (`:532-541`): z = b0 + sum b_k f_k, per tier group ITF / CH / TOUR
  (`tier_group` `:183`), p_home = sigmoid(z). `MIN_RATED` 10 rated matches per side else no
  forecast (`:88`).
- **`config/tennis_rating.json`** (installed, no staged `tennis_rating.next.*.json`):
  features `[lp_t, lps, dmin78, drest, dn7, dform, dhigh, dtour]`, `fitted_from.cut_utc`
  2026-10-01, `fitted_at_utc` 2026-10-08T14:19Z, 241,699 history / 151,849 rated matches,
  `tier_start` ITF -22.0 / CH +168.2 / TOUR +239.1. Coefficients:

| tier (n) | b0 | lp_t | lps | dmin78 | drest | dn7 | dform | dhigh | dtour |
|---|---|---|---|---|---|---|---|---|---|
| ITF (109,126) | 0.023 | 0.947 | 0.157 | **-0.0158** | **-0.225** | **+0.0088** | -0.024 | 1.669 | -0.198 |
| CH (25,826) | 0.029 | 0.533 | 0.294 | **-0.0355** | **-0.265** | **+0.0197** | -0.023 | 0.838 | 0.899 |
| TOUR (16,269) | 0.009 | 0.366 | 0.466 | **-0.0465** | **-0.422** | **+0.0364** | -0.074 | 0.384 | 1.244 |

  Fitted by `scripts/sofa/fit_tennis_rating.py --cut ... --tier-start` (logistic Newton,
  `fit_coefficients` `:969`). The fit predates the 2026-10-27 best-of-5 filter fix
  (T-BO5, `fit_coefficients` docstring) - **SUSPICION: installed coefficients were fitted
  with the legacy `len(sets) <= 3` population** (fitted_at 10-08 < 10-27).
- Reading the signs: one hour more on court in 78 h costs 0.016-0.047 logit; a > 21-day
  layoff costs 0.22-0.42 logit (~5-10 pp near 50%); `dn7` is **positive** (more matches
  this week = slightly better) - **SUSPICION: a selection effect** (a player still in the
  draw is winning), so `dn7` is not a fatigue term as fitted. ITF's small `dmin78` is
  consistent with its missing durations (section 5) - SUSPICION.
- Neighbours: `_window` (`:775-791`) takes the `NEIGHBOURS` 600 table outcomes whose
  calibrated p is nearest the fixture's p_home (and 1-p_home for the away pool); the
  table is cut by (tier, gender) -> tier -> pooled with >= 1,200 outcomes
  (`TENNIS_SCOPED_TABLE`, on since 10-09; `_scoped_cell` `:855`); CH/TOUR use a table
  without match-tiebreak deciders. **Similarity is p alone** - no surface, rest or
  length key. Outcomes are completed best-of-three only (`_outcomes`).
- `W_TENNIS_RATING` 0.25 price blend (`:118`) is dormant in the stats-only epoch.

### 2b. Point model (`src/bet/sofa/tennis_point_model.py`, `tennis_point_sheet.py`)

- Serve point logit = cell[gender, tier, surface] + S_server - R_returner (+ no tournament
  term for serve), Gaussian beliefs updated online (EKF) on serve points won/played from
  `/statistics` (`parse_serve_stats` `:154`), else from the score as pseudo-points
  (`SCORE_WEIGHT` 0.7); aces: cell + server + returner("aces conceded") + tournament; DFs:
  cell + server + tournament (`:339-445`). Constants chosen on history before 2026-01-01.
- Forecast as of the start (`forecast_fixtures` walk-forward); `PointModel.forecast`
  (`:519-532`): inputs = serve/return/ace/DF beliefs, cell, tournament id, decider
  tiebreak book. Simulation `simulate` (`:659`) with form noise (`FORM_VAR` 0.04,
  `FORM_COV` -0.0225).
- **No rest / fatigue / previous-match length input.** The only time term is
  `drift_per_day` (`_belief` `:356-363`): variance grows with days since the player's last
  observation (a layoff widens uncertainty, does not move the mean). Best of five or no
  `defaultPeriodCount == 3` -> NOT_RATED (`tennis_point_sheet.py:95-103`).

### 2c. Set-handicap neighbours (R2) and old estimator

- R2 `read_set_handicap` (`tennis_rating.py:726-748`), live 10-28..11-06 17:30Z, now
  superseded by the point model for those two keys.
- Old sample estimator: last 10 matches per player, same surface family / best-of
  (`samples.py`), centre shrunk to `tennis_prior.tier_prior` (gender x tier x surface,
  `src/bet/sofa/tennis_prior.py`); NB / empirical / normal; derived joints rho. No
  schedule term.

## 3. Where a fatigue correction would enter, and what it reaches

| entry point | mechanism | reaches automatically | does NOT reach |
|---|---|---|---|
| **A. new rating feature(s)** (e.g. previous-match minutes/sets/points, minutes in 48 h, back-to-back tournaments, surface switch, retirement flag) in `RatingBook._context/features` (`tennis_rating.py:452-498`) + `FEATURES` (`:94`), refit `config/tennis_rating.json` | shifts p_home; config is applied by name, so a new feature is inert until refitted | match_won_for (directly); via the neighbour window: games_won_for, handicap_games, most_games, sets_total, games_won_set1/2/3_for, set1/2_won_for, set_score, set_score_not; games_total (50% weight) | games_set1/2_total, all 18 serve keys, handicap_games_won_set1/2 (point model); tiebreaks_total, most_/handicap_aces joints (sample) |
| A-limit | neighbours are chosen by p only | - | a fatigue effect on **shape** (fewer games given p, set-3 collapse, more lopsided sets) is invisible; needs a second neighbour key or a conditional table (SUSPICION) |
| **B. point model**: per-side shift of serve / return logit (and/or ace/DF rate) in `PointModel.forecast` (`tennis_point_model.py:519-532`), ideally also in `update` so ratings learn net of fatigue | moves simulated serve point probabilities -> games, sets, serve counts | games_set1/2_total, aces/DF/serve_points (match, sets, _for/_total), handicap_games_won_set1/2 | every rating-read family (A) |
| **C. sample-estimator centre multiplier** (pattern: `tennis_aces_correction`, `run_sheet.py:1169`) | scales a centre | tiebreaks_total, most_/handicap_aces joints | - (low volume: ~0-6 printed legs in 18 days) |
| D. retirement risk | a retirement is a refund (`settle.REFUND_REASONS`) and retired matches are out of the neighbour table | - | a fatigue -> retirement effect costs nothing graded; only the conditional-on-completion distribution matters |

To reach both groups one would need A **and** B (two estimators, two refit chains).

## 4. Curves / files to refit after a change

| change | refit | script(s) |
|---|---|---|
| rating features / coefficients | `config/tennis_rating.json` (or staged `tennis_rating.next.<D>.json`, `params_path_for` `:1000`) | `scripts/sofa/fit_tennis_rating.py --cut <D> --tier-start [--score-winner]` |
| -> every rating-fed curve in `config/sofa_confidence_calibration.json` (installed, fitted 10-17 on replay `data/refit_2026-10-17`, flags incl. `tennis_rating, tennis_scoped_table, tennis_set_ratings, tennis_sample_scope`) and staged `.next.json` (11-06 17:30Z) / `.next.2026-11-07.json`: tennis by_market (23 keys), by_market_direction (34), thin (32); classes `tennis_women`, `tennis_team_cup`; `handicap_games|OVER` refitted in `.next*` (11-05 replay) | replay + fit | `scripts/sofa/prepare_refit.py` -> `calibrate_from_cache.py --tennis-rating --tennis-scoped-table --tennis-set-ratings --tennis-sample-scope [--tennis-score-winner]` -> `fit_confidence.py` (never `--tennis-serve-markets` / `--tennis-aces-opponent`) |
| -> `match_won_for` curve (+ tennis_women) | fitted 10-13 on `AsOfRating` | `scripts/sofa/fit_tennis_winner_curve.py` |
| -> set1/2_won_for, set_score (+ women) | fitted 10-14 | `scripts/sofa/fit_incident_set_curves.py` (tennis_sets group) |
| -> set_score_not | fitted 10-16 from the same rows.csv | `scripts/sofa/fit_score_market_curves.py --tennis-rows` |
| point model inputs | `config/sofa_tennis_point_curves.json` (fitted 11-05, window 01-01..10-20, 53,216 matches) + backfill `data/line_evidence/tennis_point_model_p.json.gz` | `scripts/sofa/fit_tennis_point_curves.py [--backfill-out]` |
| -> per-set handicap | `config/sofa_tennis_handicap_point_curves.json` + `data/line_evidence/tennis_handicap_point_model_p.json.gz` | `scripts/sofa/measure_tennis_handicap_point_model.py` (writes the curves), `fit_tennis_point_curves.py --handicap --backfill-out` |
| live-only curves | `config/sofa_live_only_curves.json` lists 50 tennis keys (serve per-set _for, serve_points, tiebreaks_total, women thin) stripped since 10-24 - not refitted, they stay refused; under the point model its own curves overlay the serve keys | `bet.sofa.live_only_curves` |
| after any of the above | line evidence offsets / band caps are realised minus confidence per key - stale after a p change | `scripts/sofa/refresh_line_evidence.py --before <D>` (morning loop) |
| also re-measure | the 0.60 totals floor (games_total, sets_total) was measured on today's chain | `scripts/sofa/measure_tennis_totals_floor.py` |
| SHEET | `tennis_rating.json` is hashed in `config_sha` (`src/bet/sofa/sheet_config.py:32`): a built sheet gets `CONFIG_CHANGED`, not re-run; a rating switch needs a SHEET marker for `rebuild_plan` | `bet.sofa.epochs` switch + marker |

## 5. Data available for fatigue features (tennis)

Checked on the 3,000 newest `sofa_listed_event` tennis rows (2,441 finished; read-only, LIMITed):

| feature | source in cache | coverage / notes | code that reads it today |
|---|---|---|---|
| start time, rest days, matches in 7/14 d | listing `startTimestamp` (player `last` pages + index) | complete | `tennis_rating._context` (dn7, drest), `schedule.py:45-83` (`LONG_LAYOFF` >= 21 d, `CONGESTED` >= 3 in 7 d - **display only** `context_flags`), `dossier.side_summary` `rest_days / games_7d / games_14d` (`dossier.py:347-349`) |
| previous-match duration | listing `time.period1..5` (seconds per set) | ITF **375 / 2,031 (18%)**, CH 284 / 289, TOUR 119 / 121 | `tennis_rating.parse_event` `:330-333` (all-or-none) -> `dmin78` |
| sets / games of previous match | `homeScore/awayScore.periodN` (+ `periodNTieBreak`) | complete | `tennis_score.set_games`; neighbour outcomes |
| points played | `/statistics` `pointsTotal`, `servicePointsScored`, `receiverPointsScored`, `serviceGamesTotal`, per ALL/1ST/2ND/3RD (`sofa_event_stats.statistics_json`) | non-empty ITF 1,129 / 2,031, CH 216 / 289, TOUR 103 / 121 in the window (CH/TOUR gaps = rows not yet fetched, SUSPICION) | `tennis_point_model.parse_serve_stats` (serve points), `metrics` |
| point-by-point | `sofa_event_extra` kind `point_by_point` (`backfill_event_extra.py`) | **0 of 2,441** recent events | `point_by_point.py`, measure scripts only |
| retirement / walkover | `status.description` Retired / Walkover | complete | `dossier.recent_retirement` (`dossier.py:215`, 14 d, KRECZ WATCH); rating logs retired minutes, walkovers dropped |
| surface | `groundType` (listing, uniqueTournament, `/event` detail) | 175 / 175 | `surface_family` -> rating (lps), point-model cell, tier prior, sample filter; indoor not separated |
| tournament / round | `tournament.uniqueTournament.id/name`, `roundInfo` (round, name e.g. "Qualification", "Semifinals") | complete | tier via `category.name`; point model tournament term; round **not read** anywhere |
| venue / city / country (travel, time zone) | `/event` detail `venue.city/country` | CH/TOUR detail rows: 305 / 308 carry a venue; ITF detail: none seen; `uniqueTournament.city/country` empty in all 308; detail exists only for fetched fixtures, not history (SUSPICION) | `dossier.py:1725-1768` (display), `settle.venue_timezone` |
| player country | `homeTeam.country` | complete | not read for tennis |
| ranking | `homeTeam.ranking` | value at fetch time, not as-of (SUSPICION: look-ahead if used historically) | dossier display |

## 6. Volume (runs/sofa)

Days with `08_refusals.json`: 10-21..10-29, 11-01..11-08 (17; 10-20 has no refusals file,
10-30/31 no run dirs); 2,742 tennis events. Caveat: `08_refusals.json` is the **last**
rebuild, so rows already started are `KICKED_OFF` without a confidence - the
confidence columns undercount. The printed counts (`11_coupon.json` `singles`, 18 days
incl. 10-20) are the robust number: **7,221 printed tennis legs**.

| family | priced rows | conf computed | conf >= 0.70 | conf >= 0.60 | printed (11_coupon) | estimator |
|---|---|---|---|---|---|---|
| games_won_for | 32,412 | 9,047 | 1,163 | 2,232 | 1,043 | rating nbrs |
| games_won_set1_for | 31,884 | 8,247 | 1,263 | 2,169 | 880 | rating nbrs |
| games_won_set2_for | 31,906 | 8,209 | 1,154 | 2,108 | 774 | rating nbrs |
| games_set1_total | 23,116 | 5,686 | 1,438 | 1,915 | 1,291 | point model (from 11-06), before rating nbrs |
| games_set2_total | 23,762 | 5,700 | 1,293 | 1,820 | 1,098 | point model / rating nbrs |
| set_score_not | 4,717 | 1,159 | 336 | 585 | 751 | rating nbrs |
| set1_won_for | 5,264 | 1,413 | 149 | 309 | 386 | rating nbrs |
| set2_won_for | 5,248 | 1,401 | 141 | 293 | 327 | rating nbrs |
| match_won_for | 5,202 | 1,348 | 153 | 312 | 336 | rating p |
| sets_total | 4,486 | 1,243 | 108 (all UNDER) | 597 | 161 (68 via 0.60 floor) | rating nbrs |
| games_total | 16,474 | 4,722 | 26 | 426 | 61 (42 via 0.60 floor) | 0.5 rating + 0.5 NB |
| tiebreaks_total | 1,758 | 535 | 22 | 77 | 30 | sample |
| set_score | 9,138 | 2,547 | 23 | 90 | 23 | rating nbrs |
| handicap_games | 16,357 | 4,590 | 66 | 305 | 0 | rating nbrs |
| handicap_games_won_set1/2 | 9,288 | 3,000 | 42 | 257 | 0 | point model / R2 nbrs |
| most_games | 2,033 | 681 | 30 | 99 | 0 | rating nbrs |
| serve keys (aces / DF / serve_points, match + sets, _for/_total; 18) | ~15,600 | ~3,800 | ~60 | ~240 | 60 | point model (from 11-06) / sample |
| most_aces*, most_double_faults*, most_serve_points*, handicap_aces | ~5,400 | ~1,200 | 0 | 0 | 0 | sample joints |

Printed by direction (top): games_won_for UNDER 829, games_set2_total UNDER 767,
games_set1_total UNDER 752, set_score_not OVER 751, games_won_set1_for OVER 574,
games_set1_total OVER 539, games_won_set2_for OVER 535. **~98% of printed tennis legs
come from rating-neighbour families or per-set games totals**; the serve families are
~1%. Full per-direction table: `/private/tmp/claude-501/-Users-mkoziol-projects-bet/9d6e1d47-eb57-4159-af91-cfd455891846/scratchpad/vol.txt`
(script `vol.py` beside it).

## 7. Earlier measurements of rest / fatigue in tennis

| where | what | result |
|---|---|---|
| `src/bet/sofa/tennis_rating.py:21-27` (docstring, rating built ~09-17/09-23, commit 01be2f2a 2026-09-23) | each context term on 30,421 matches with both rated, z vs zero | hours in 78 h z -6.7; > 21 d layoff -4.1; matches in 7 d -2.6; form -2.0. No separate report file found (grep docs) |
| `docs/sofa/evidence/tennis_calibration_2026-10-08.md` (+ `scripts/sofa/measure_tennis_calibration.py:1475` `CONTEXT`) | surface / tier / V5 variants with the context block held fixed | no ablation of rest features; V5 -10.4e-4 log loss installed |
| `docs/sofa/history/AUDYT_RYNKOW_KONTEKST_2026-10-13.md:118, :912, :1985, :2152` | C14 context flags; "fatigue only in p, not in the games distribution" | rest gain minimal (football goals_total -0.00015); tennis fatigue only via `dmin78 / drest / dn7`; no tennis measurement |
| `docs/sofa/evidence/kupon_od_nowa_2026-10-31/batches/C_evidence_other/cells.csv` rows 40-41 | pooled non-count legs (all sports incl. tennis) with `CONGESTED` / `LONG_LAYOFF` flags vs the split | CONGESTED dev n 2,590 excess +0.69 pp [-1.40, +2.73], val n 629 +1.68 [-2.33, +5.60]; LONG_LAYOFF dev 585 -0.05 [-4.13, +3.85] - noise; no tennis-only cell |
| `docs/sofa/evidence/tennis_krecz_2026-11-01.md` | retirement <= 14 d before (A) and model - own sample gap (B) | no gate (CIs span zero); operator rule KRECZ WATCH from 11-02, ledger tag RETIREMENT (`T-KRECZ-WATCH`) |
| `.claude/skills/tennis-analysis/SKILL.md:128-137, 182` | analyst contract | rest / long previous match / travel = note only, never a removal |
| `.claude/skills/sofa-pipeline/references/model-state.md` | grep tennis + rest/fatigue | nothing beyond P14 / refit rows; no fatigue switch, no declined fatigue measurement |

Not measured anywhere (gaps): previous-match length in sets / games / points as a
predictor; fatigue on games / sets **distribution** given p; back-to-back tournaments;
surface switch; travel / time zone; qualifying-round load; per-tier `dmin78` with
missing durations handled (imputed from games); `dn7` as selection vs fatigue.
