# R1 - Football inventory for a schedule / fatigue centre correction

Read-only research, 2026-11-08. Repo `/Users/mkoziol/projects/bet`. Nothing run except
reading code / config and aggregating `runs/sofa/<d>/08_confidence.json` and
`08_refusals.json` (no DB, no network). Line numbers are as of HEAD `e4fb587d` plus the
uncommitted working tree. "SUSPICION" marks anything inferred rather than read.

---

## 0. Executive summary

* **Families.** 133 distinct football market keys were priced against a Superbet price on
  10-21..11-08 (17 days with `08_refusals.json`). In code: 58 `FOOTBALL_METRICS`
  (`metrics.py:173`; `xg_total` / `xg_for` included, no Superbet name maps to them), 11
  incident scopes (`metrics.py:1160`), 8 player props, 8 shot-detail props, 12 result /
  score / incident keys, 9 simulator keys, and the open-ended derived families `both_over_*`,
  `most_*`, `handicap_*` over any base metric and half (`market_mapper.py:715`, `:874`,
  `:1014`).
* **The single most important fact for the design.** About 51% of the football legs at
  confidence >= 0.70 in `08_confidence.json` (40,319 of 77,987) are **result / score markets
  priced only from the PURE rating goals centres** (`FootballForecast.centre("goals_for",
  side)`): double chance, DNB, 1X2, `result_or_*`, `btts_or_over`, `dc_and_*`,
  `result_handicap`, `first_goal`. Another 20% are goals marginals. The **9 simulator
  families** read the same pure centres. A correction put **only into the SHEET centre chain**
  (`centre_chain.apply_team_terms`, where referee and closeness live) **never reaches these
  families**, and it does not reach the supremacy that drives GAME_STATE, the count, goals,
  closeness and player stretches, or the side red / penalty events. A correction put **into
  the rating** (`RatingBook.expected` / `FootballForecast.centre`) reaches all of them, but it
  reaches only the rating half of a blended marginal, and nothing that is priced from the
  sample alone.
* **Unreachable by any team-centre correction:** league-rate events (`red_cards_total`,
  `penalties_total`, `red_cards_1h_total`, `penalties_1h_total`, `both_red_cards`); footballer
  shot-detail props (own starts shrunk to the position pool); footballer assists /
  interceptions / offsides / fouls drawn / tackles (raw own sample: the share config has no
  tackles cell); and every derived joint whose side metric is not one of the 4
  `DERIVED_MARGINAL_CENTRES_METRICS`. That last group includes **all half-scoped joints**:
  `both_over_goals_1h` / `_2h` alone produce 3,051 legs >= 0.70.
* **Schedule data today:** `bet.sofa.schedule` is computed in SAMPLES (`samples.py:2331`) and
  read only for display: `context_flags` in CONFIDENCE (`run_confidence.py:292-296, 1020-1027`),
  the make-up note in `build_coupon.py:101-103`, the PDF tags in `build_coupon_pdf.py:344` and
  the dossier `dossier.py:701`. Nothing in SHEET, the rating, `centre_chain` or the simulator
  reads it (grep: no `schedule` in `run_sheet.py`, `football_rating.py`, `centre_chain.py`,
  `football_sim*.py`, `calibrate_from_cache.py`).
* **Measured before:** `scripts/sofa/measure_schedule_context.py` (10-04, 293k league
  matches; residual against the raw sample mean). Both sides on >= 21 days of rest:
  goals_total -0.122 [-0.155, -0.092], corners -0.280 [-0.452, -0.108]
  (`docs/sofa/history/RAPORT_2026-10-04_POROWNYWALNOSC_HISTORII.md:127-134`). As a log-loss
  feature: goals_total -0.00015 [-0.00023, -0.00008], others crossing 0
  (`docs/sofa/evidence/model_defects_2026-10-05.md:234-241`). Audit C14 (2026-10-13) said:
  repeat the measurement after the opponent correction (`AUDYT_RYNKOW_KONTEKST_2026-10-13.md:118`).
  The make-up fixture showed no effect.

---

## 1. Every football market family the pipeline maps and prices

### 1a. Where the lists are (authoritative sources)

| list | what it holds | file:line |
|---|---|---|
| `FOOTBALL_METRICS` | 58 team metrics, full match + `1ST` / `2ND` period, `_for` / `_total` | `src/bet/sofa/metrics.py:173-438` |
| `CARD_INCIDENT_SCOPES` | 11 incident-scoped metrics (card points by half, reds, penalties, both red) | `metrics.py:1160-1172` |
| `extract_metric` | the one reader (SETTLE, SAMPLES, dossier) | `metrics.py:1485` |
| `MATCH_MARKET_NAMES` | Superbet total names -> metric | `src/bet/sofa/market_mapper.py:37-104` |
| `TEAM_MARKET_PATTERNS` | Superbet per-team names -> `_for` metric | `market_mapper.py:126-280` |
| `PLAYER_MARKET_NAMES`, `PLAYER_PROPS_V2_NAMES` | 7 + 1 footballer props | `market_mapper.py:283-303`; metrics `players.py:62` |
| `shot_detail.MARKET_NAMES` / `METRICS` | 8 shot-detail props | `src/bet/sofa/shot_detail.py:32-43` |
| `classify_derived_market` | `both_over_<m>`, `most_<m>[_<scope>]`, `handicap_<m>` | `market_mapper.py:715-835` |
| `classify_mappable_family` | "<team> strzeli gola" -> `goals[_1h/_2h]_for` 0.5; BTTS by half -> `both_over_goals_1h/2h`; `both_over_saves[_1h]`; `handicap_corners_1h/2h` | `market_mapper.py:874-987` |
| `classify_stat_variant` / `STAT_VARIANT_MARKETS` | `both_over_throw_ins/goal_kicks/tackles`, `handicap_shots[_1h/_2h]` | `market_mapper.py:1008-1072` |
| `DERIVED_BASE_TO_SIDE_METRIC`, `derived_side_metric` | base of a derived market -> side metric | `market_mapper.py:1075-1106` |
| `football_result.DOUBLE_CHANCE` | `double_chance` | `src/bet/sofa/football_result.py:70` |
| `football_1x2_dnb.MARKETS` | `result_1x2`, `draw_no_bet` | `src/bet/sofa/football_1x2_dnb.py:60` |
| `football_score_markets.MARKETS` | `result_or_over/under`, `btts_or_over`, `result_or_btts`, `result_or_clean_sheet`, `result_handicap`, `dc_and_over/under` | `src/bet/sofa/football_score_markets.py:83-85` |
| `football_incidents.INCIDENT_MARKETS` | `first_goal`, `red_cards_total`, `penalties_total` | `src/bet/sofa/football_incidents.py:253` |
| `football_card_halves.MARKETS` | card halves, most / handicap halves, red / penalty side and 1H, `both_red_cards` | `src/bet/sofa/football_card_halves.py:79-87` |
| `epochs.FOOTBALL_SIM_MARKETS` | 9 path markets | `src/bet/sofa/epochs.py:3801-3804` |
| `tennis_winner.RATING_ONLY_MARKETS` | every no-sample, own-curve-only market (football: DC, 1X2/DNB, score, incident, card halves, sim) | `src/bet/sofa/tennis_winner.py:66-69` |
| OFFER order of classifiers | total/team names -> derived -> player -> mappable -> result -> incident -> stat variant -> card half -> sim | `src/bet/sofa/offer.py:160-246` |
| `epochs.FOOTBALL_FORM_TABLE_FAMILIES` | 35 `market|DIR` that read the season-table book | `epochs.py:1461-1497` |

### 1b. The family table

Column "seen" = priced with a Superbet price in `08_refusals.json` on 10-21..11-08 (Section 5).

| # | family group | market keys | seen |
|---|---|---|---|
| 1 | goals totals / side, full + halves | `goals_total`, `goals_for`, `goals_1h_total`, `goals_1h_for`, `goals_2h_total`, `goals_2h_for` (incl. "<team> strzeli gola" = `goals_*_for` 0.5) | all 6 |
| 2 | corners | `corners_total/_for`, `corners_1h_total/_for`, `corners_2h_total/_for` | all 6 |
| 3 | card points (full match) | `cards_points_total`, `cards_points_for` | both |
| 4 | card points by half | `cards_points_1h_total/_for`, `cards_points_2h_total/_for` | all 4 |
| 5 | shots | `shots_total/_for`, `shots_1h_total/_for`, `shots_2h_total/_for` | all 6 |
| 6 | shots on target | `shots_on_target_total/_for`, `_1h_total/_for`, `_2h_total/_for` | all 6 |
| 7 | fouls | `fouls_total/_for`, `fouls_1h_total/_for`, `fouls_2h_total/_for` | all 6 |
| 8 | offsides | `offsides_total/_for`, `_1h_total/_for`, `_2h_total/_for` | all 6 |
| 9 | goalkeeper saves | `saves_total/_for`, `saves_1h_total/_for` | all 4 |
| 10 | throw-ins | `throw_ins_total/_for`, `_1h_total/_for`, `_2h_total/_for` | all 6 |
| 11 | goal kicks | `goal_kicks_total/_for`, `_1h_*`, `_2h_*` | only `goal_kicks_total/_for` priced (halves mapped, no priced row seen; they appear in the form-table list, `epochs.py:1469-1476`) |
| 12 | tackles | `tackles_total`, `tackles_for` | both |
| 13 | xG | `xg_total`, `xg_for` | not mapped to any Superbet name (`MATCH_MARKET_NAMES` has none) |
| 14 | red cards | `red_cards_total` (incident), `red_cards_for`, `red_cards_1h_total`, `red_cards_1h_for`, `both_red_cards` | 3 of 5 (no priced `red_cards_1h_for` / `both_red_cards` row seen) |
| 15 | penalties | `penalties_total`, `penalties_for`, `penalties_1h_total`, `penalties_1h_for` | all 4 |
| 16 | result | `double_chance`, `result_1x2`, `draw_no_bet` | all 3 |
| 17 | score "or" / combos | `result_or_over`, `result_or_under`, `btts_or_over`, `result_or_btts`, `result_or_clean_sheet`, `result_handicap`, `dc_and_over`, `dc_and_under` | all 8 |
| 18 | first goal | `first_goal` (incident), `first_goal_1h` (sim) | both |
| 19 | simulator path markets | `htft`, `result_1h`, `result_2h`, `higher_scoring_half`, `team_scores_both_halves`, `btts_halves`, `btts_any_half`, `first_goal_1h`, `half_goals_combo` | all 9 |
| 20 | joints "each team over" | `both_over_goals` (= BTTS at 0.5), `both_over_goals_1h/_2h`, `both_over_corners[_1h/_2h]`, `both_over_cards_points`, `both_over_shots[_1h/_2h]`, `both_over_shots_on_target`, `both_over_fouls[_1h/_2h]`, `both_over_offsides`, `both_over_saves[_1h]`, `both_over_throw_ins`, `both_over_goal_kicks`, `both_over_tackles` | 13 seen |
| 21 | joints "most" | `most_corners[_1h/_2h]`, `most_cards_points[_1h/_2h]`, `most_shots[_1h/_2h]`, `most_shots_on_target`, `most_goals` | 10 seen |
| 22 | joints handicap | `handicap_corners[_1h/_2h]`, `handicap_cards_points[_1h/_2h]`, `handicap_shots[_1h/_2h]`, `handicap_shots_on_target`, `handicap_goals`, (curves exist for `handicap_fouls*`, `handicap_offsides`, `handicap_saves*`, `handicap_throw_ins`, `handicap_goal_kicks`, `handicap_tackles`) | 9 seen |
| 23 | footballer props | `player_shots_for`, `player_shots_on_target_for`, `player_assists_for`, `player_fouls_for`, `player_tackles_for`, `player_interceptions_for`, `player_offsides_for`, `player_fouls_drawn_for` | 7 seen (no interceptions row) |
| 24 | footballer shot detail | `player_shots_outside_box_for`, `player_headed_shots_for`, `player_left_foot_shots_for`, `player_right_foot_shots_for`, `player_sot_outside_box_for`, `player_sot_headed_for`, `player_sot_left_foot_for`, `player_sot_right_foot_for` | all 8 |

Not mapped at all (for completeness; `runs/sofa/2026-11-07/market_coverage.md`): Superbet
combos (57,940 occurrences on one day), result combos, exact score, goal-count distributions /
parity, player goals / cards, goal timing / sequence, own goals and similar. A schedule term
cannot touch these.

---

## 2. Metric, estimator chain and existing corrections per family

### 2a. The shared marginal chain (team count / goals rows)

`run_sheet.process_fixture` (`scripts/sofa/run_sheet.py:2544`) does the following, in order,
for a non-derived, non-rating-only, non-player rung:

| step | what | file:line |
|---|---|---|
| sample | side sample (`_for`) or the pooled deduplicated sample of both sides + h2h (`_total`; refused THIN if either side < min_sample) | `run_sheet.py:2872-2934` |
| opponent correction (B15) | each past observation rescaled by its opponent's defence ratio and the domain gap (`CORRECTED_METRICS`: corners, corners halves, shots, shots_1h, SOT, SOT_1h, fouls, fouls_1h, cards_points_for, offsides_for; goals stay raw); a total = corrected for + against | `run_sheet.py:2895-2932`; `src/bet/sofa/opponent_correction.py:1-60` (`CORRECTED_METRICS` :52); switch `epochs.py:1566` (10-14) |
| prior + K shrink | prior (day league / teams' leagues / women / global / men's friendly), `w = n/(n+K)` (`PER_MARKET_K`) | `run_sheet.py:1030-1130` (`sample_centre`) |
| rating blend | `FootballForecast.centre(market, side)` for the 14 `BASE_METRICS` (`football_rating.py:68-83`): `W_FOOTBALL_RATING` 0.5 or `sofa_rating_weight.json` per market; `_total` = home + away rating; excluded: `UNRATED_MARKETS` (corners totals and halves, `offsides_total`, `cards_points_for`) except `RATED_SCOPE_MARKETS` (`cards_points_for`, `corners_1h_for`, `corners_2h_for`, `offsides_total`) | `run_sheet.py:1132-1160`; `football_rating.py:128-152, 1267-1326` |
| inside the rating | Maher-style attack / defence per metric, league rate + home ratio, cross-league strength / LINK, **cup strength** (`cup_strength.py`, `epochs.py:2365`), **season table** on `goals_for` / `goals_1h_for` only in the table book (`FORM_TABLE_METRICS` `football_rating.py:785`, `table_adjust` `:1318`), awarded results excluded | `football_rating.py:1056` (`expected`), `:1198` (`replay`); `run_sheet.py:3822-3843` (two books) |
| venue prior | sample-only side rows `corners_1h_for` / `corners_2h_for` x league home/away rate | `centre_chain.py:81-95`; `football_rating.py:152` |
| GAME_STATE | `exp(beta * supremacy)` for `cards_points_for`, `corners_for`, `fouls_for`, `shots_for` | `centre_chain.py:96-111`; `config/sofa_game_state.json` |
| count stretch | side `exp(b s [+ b2 s^2])`, total `exp(g1|s|+g2 s^2)`: `corners_1h/2h_for`, `goal_kicks_for`, `offsides_for`, `saves[_1h]_for/_total`, `shots_1h/2h_for`, `shots_on_target[_1h/_2h]_for`, `shots_on_target_total`, `throw_ins_for/_total` | `centre_chain.py:112-129`; `config/sofa_count_stretch.json` |
| **referee** | cards / fouls centre x referee as-of shrunk ratio^beta: `cards_points_for/_total`, `fouls_for/_total`, `fouls_1h_*`, `fouls_2h_*` | `centre_chain.py:130-152`; `referees.py:469` (`family_of`); `config/sofa_referee_effect.json` |
| **closeness** | `exp(g1|s|+g2 s^2)`, s = home supremacy: `cards_points_for`, `cards_points_total`, `shots_total`, `shots_1h_total` | `centre_chain.py:153-169`; `config/sofa_closeness_stretch.json` |
| goals stretch | goals centres x supremacy stretch, per season phase: the 6 goals markets | `centre_chain.py:170-189`; `config/sofa_goals_stretch.json` |
| player share / stretch | footballer rows only (see 2d) | `run_sheet.py:3035-3060` |
| season phase | goals centres x `exp(c[market][phase])`: the 6 goals markets | `centre_chain.py:193-208`; `config/sofa_season_phase.json` |
| dispersion | `sd^2 = centre + alpha centre^2`, alpha per (market, competition) from `config/sofa_count_dispersion.json` (51 football markets, NB or floored normal); else the sample variance scaled by centre/mean | `run_sheet.py:3123-3130`; `engine.py:298-345`; switch `epochs.py:282` (10-09) |
| p_central | NB or normal tail at the line from (centre, pred_sd) | `run_sheet.py:3247`; `engine.py:364-388` |
| form table per family | the fixture is priced on both books; a row of the 35 `FOOTBALL_FORM_TABLE_FAMILIES` takes the table book's p | `run_sheet.py:2468` (`merge_form_table_rows`); `epochs.py:1451-1497` |

"Supremacy" s = the rating's goals_for home minus away (`football_rating.py:1328-1340`), read
from the pure goals rating. It is the covariate of GAME_STATE, the count / goals / closeness /
player stretches and the side-event beta.

### 2b. Per-family estimator and corrections

Abbreviations: **R** = rating blend; **pR** = pure rating centre (no sample); **S** = sample +
prior shrink; **OC** = opponent correction; **GS** = game state; **CS** = count stretch;
**REF** = referee; **CL** = closeness; **GST** = goals stretch; **SP** = season phase;
**VP** = venue prior; **TBL** = season-table book family; **CUP** = cup strength inside the
rating.

| family (metric via `extract_metric`) | estimator -> p_central | corrections on the centre today | dispersion | evidence |
|---|---|---|---|---|
| `goals_total/_for` (goals_from_listing) | S (same competition for goals) + R (rating_weight) -> NB | R(CUP, TBL book for `goals_for`/`goals_1h_for`), GST, SP; no OC (goals raw) | count_dispersion | `football_rating.py:68-83`; `opponent_correction.py:52`; `centre_chain.py:170-208` |
| `goals_1h_*`, `goals_2h_*` | as above (halves are BASE_METRICS) | R, GST, SP; `goals_2h_for` both directions in TBL | count_dispersion | `epochs.py:1478-1479` |
| `corners_for` | S+OC + R -> NB | GS; line curves | dispersion | game_state config |
| `corners_total` | pooled S+OC only (UNRATED), NB | none of GS/CS/REF/CL | dispersion | `football_rating.py:129-137` |
| `corners_1h_for/_2h_for` | S+OC + R (RATED_SCOPE); VP only when the rating does not rate the row | CS | dispersion | `football_rating.py:150-153` |
| `corners_1h/2h_total` | pooled S (UNRATED) | none | dispersion | |
| `cards_points_for` (cards_points_from_incidents) | S+OC + R (RATED_SCOPE) -> NB | GS, REF, CL | dispersion | |
| `cards_points_total` | S+OC + R (sum) | REF, CL | dispersion | |
| `cards_points_1h/2h_*` | **rating-only**: side NB on the **live** `cards_points_for` centre (after its chain) x the competition's half share; for a side without a live row, rating centre x GS x REF x CL (`card_half_term_mults`) | inherits the cards_points_for chain | `HALF_NB_R` | `run_sheet.py:1934-1969, 1970`; `football_card_halves.py:1-40`; `epochs.py:2810` |
| `most_/handicap_cards_points_1h/2h` | joint of the two half NBs (independent) | as above | | `football_card_halves.py:81` |
| `shots_for` / `shots_1h_for` | S+OC + R | GS (`shots_for`), CS (`shots_1h_for`) | dispersion | |
| `shots_total` / `shots_1h_total` | S+OC + R (sum) | CL | dispersion | |
| `shots_2h_*` | S only (not a BASE_METRIC) | CS (`shots_2h_for`); `shots_2h_total` OVER in TBL | dispersion | |
| `shots_on_target_for/_total/_1h_*` | S+OC + R | CS (`_for`, `_1h_for`, `_total`) | dispersion | |
| `shots_on_target_2h_*` | S only | CS (`_2h_for`) | dispersion | |
| `fouls_for/_total`, `fouls_1h_*` | S+OC + R | GS (`fouls_for`), REF | dispersion | |
| `fouls_2h_*` | S only | REF | dispersion | |
| `offsides_for` / `offsides_total` | S+OC + R (`offsides_total` via RATED_SCOPE) | CS (`offsides_for`) | dispersion | |
| `offsides_1h/2h_*` | S only | none | dispersion | |
| `saves_*` (goalkeeperSaves) | S only | CS (`saves_for`, `saves_total`, `saves_1h_*`) | dispersion | |
| `throw_ins_*` (throwIns) | S only | CS (`throw_ins_for/_total`) | dispersion | |
| `goal_kicks_*` (goalKicks) | S only | CS (`goal_kicks_for`) | dispersion | |
| `tackles_*` (totalTackle) | S only | none | dispersion | |
| `double_chance` | **pR**: independent NB goals on the pure goals centres, r from `config/sofa_football_result.json`; OVER only | R internals only (CUP, TBL book? see note) | `nb_r` | `run_sheet.py:1540-1580`; `football_result.py:1-45` |
| `result_1x2`, `draw_no_bet` | pR, same NB; class curve `season_early` | as above | `nb_r` | `run_sheet.py:1628`; `football_1x2_dnb.py` |
| score markets (8 keys) | pR, same NB; a curve per slice `market@subject@line` | as above | `nb_r` | `football_score_markets.py:1-60`; `run_sheet.py:1692` |
| `first_goal` | pR: P(none) = NB P(0,0); a side's share of the expected goals | as above | `nb_r` | `football_incidents.py:237-241`; `run_sheet.py:1807` |
| `red_cards_total`, `penalties_total`, `red_cards_1h_total`, `penalties_1h_total`, `both_red_cards` | **competition's as-of rate**, shrunk to the gender's (`BASE_M` 30); no team input | none | - | `football_incidents.py:237-245`; `football_card_halves.py:33-37` |
| `red_cards_for`, `penalties_for`, `penalties_1h_for` (and `red_cards_1h_for`) | league intensity x `exp(beta * side supremacy)` (`SIDE_EVENT_SUP_BETA`) | supremacy only | - | `football_card_halves.py:535-545`; `epochs.py:2795-2808` |
| 9 simulator keys | pR goals centres (+ pR cards_points centres for the red process) -> 4,000 seeded minute-by-minute paths with a fitted state-dependent profile | none beyond the rating | sim params | `football_sim_sheet.py:69-82`; `run_sheet.py:1882-1933`; `config/sofa_football_sim_params.json` |
| joints on `goals_for`, `corners_for`, `shots_on_target_for`, `cards_points_for` | Gaussian / count joint (`build_joint`) of the two sides, centred on the **marginal rows' centres** (whole chain), or on a filled side's chain when Superbet quoted no ladder; rho from `sofa_side_correlations.json` | whatever the marginal row carries | marginal sd (dispersion) | `run_sheet.py:3604-3626, 1223-1331`; `derived.py:450-560`; `epochs.py:224-226` (the 4 metrics), `:3488` (JOINT_FILLED_SIDE_CHAIN) |
| joints on any other side metric (`goals_1h/2h_for`, `corners_1h/2h_for`, `shots[_1h/_2h]_for`, `fouls*`, `offsides`, `saves*`, `throw_ins`, `goal_kicks`, `tackles`) | joint of the **raw side samples** (mean / variance of the observations) | **none** | raw sample variance | `run_sheet.py:3608` (filter), `:1277`; `derived.py:536-545` |
| `player_shots_for`, `player_shots_on_target_for`, `player_fouls_for` | **share** of his side's team centre T (shots_for / fouls_for row centre after the team chain); SOT x accuracy shrunk to position | inherits the team chain via T; player stretch only where the share did not apply | NB | `run_sheet.py:3035-3046`, `:2397`; `player_share.py:1-50`; `config/sofa_player_share.json` (3 markets) |
| `player_shots_for`, `player_shots_on_target_for` (no share) | own starts mean (+ prior where any) x player stretch `exp(beta s)` | supremacy | NB | `run_sheet.py:3047-3060`; `config/sofa_player_stretch.json` |
| `player_assists_for`, `player_tackles_for`, `player_interceptions_for`, `player_offsides_for`, `player_fouls_drawn_for` | own starts sample (`sample_centre` with no rating, `run_sheet.py:1132-1140` skips player metrics), NB for assists / fouls drawn, normal otherwise | none (`player_share.TEAM_METRIC` lists tackles, `player_share.py:36-41`, but the installed config has no tackles cell) | sample | `engine.py:148-180`; `players.py:62` |
| 8 shot-detail props | `shot_detail.forecast`: his starts shrunk to his position's pool, Poisson | none | - | `run_sheet.py:2760-2771, 2191`; `shot_detail.py:150` |

Note on the pure-rating families and the season table. `FootballForecast.centre` applies
`table_adjust` when the book carries a season table (`football_rating.py:1312-1318`). The
pure-rating families therefore read the table only when they are priced on the table book.
Their keys are not in `FOOTBALL_FORM_TABLE_FAMILIES`, so they take the no-table run's row.
SUSPICION: not checked row by row.

### 2c. Rating base metrics (the reach of an in-rating correction)

`football_rating.BASE_METRICS` (`football_rating.py:68-83`): `goals_for`, `goals_1h_for`,
`goals_2h_for`, `corners_for`, `corners_1h_for`, `corners_2h_for`, `cards_points_for`,
`fouls_for`, `fouls_1h_for`, `offsides_for`, `shots_for`, `shots_1h_for`, `shots_on_target_for`,
`shots_on_target_1h_for`. Everything else is sample-only.

---

## 3. Where a schedule / fatigue correction would enter, and what it would reach

### 3a. Candidate entry points

| entry | where in code | reaches automatically | does NOT reach |
|---|---|---|---|
| **E1 - inside the rating** (a per-side multiplier on `RatingBook.expected` / `FootballForecast.centre`, by metric, from each side's rest / congestion) | `football_rating.py:1056` (`expected`) or `:1267` (`centre`); the rating is replayed in `replay` `:1198`, so a learnt version needs the as-of schedule of every history match | the rating half of every rated marginal (14 base metrics, their totals); **supremacy**, and through it GS, CS, CL, GST, player stretch, side reds / penalties; **all pure-rating families**: DC, 1X2, DNB, 8 score markets, `first_goal`, 9 sim keys (goals and the red process), card halves on a side without a live row, the joints of the 4 marginal-centre metrics via their rows | sample-only marginals (saves, throw-ins, goal kicks, tackles, offsides halves, `fouls_2h`, `shots_2h`, `sot_2h`, corners totals); the sample half of a blend (W = 0.5 or `sofa_rating_weight.json`); raw-sample joints; league-rate events; shot detail; non-share player props |
| **E2 - a new term in the SHEET centre chain** (next to the referee / closeness: `apply_team_terms`) | `src/bet/sofa/centre_chain.py:67-190`; table loaded like `RefereeEffectTable`, passed through `CentreTerms` (`centre_chain.py:42-55`) | every marginal team row incl. sample-only; the 4 marginal-centre joints (`run_sheet.py:3604-3611`) and their filled sides (`JOINT_FILLED_SIDE_CHAIN`, `run_sheet.py:1325-1331`); footballer share rows (T = the team row's centre after the chain, `run_sheet.py:3104-3107`); card halves on a side with a live `cards_points_for` row (`run_sheet.py:3108-3112`) | **pure-rating families** (DC, 1X2, DNB, score, `first_goal`, sim: about 51% of the >= 0.70 legs); supremacy-driven terms; side reds / penalties; raw-sample joints; league-rate events; shot detail; non-share props. The `card_half_term_mults` fallback (`run_sheet.py:1934-1969`) repeats GS x REF x CL by hand and would need the term added too |
| **E3 - dispersion** (alpha a function of congestion / rotation) | `count_dispersion.Dispersion.variance`, `engine.sheet_predictive_sd` (`engine.py:298-345`); `nb_r` of `sofa_football_result.json` for the pure-rating families; the sim's NB | all count marginals (the variance follows the centre already); joints of the 4 metrics through the marginal sd | as for E2 unless `nb_r` / the sim are touched |
| **E4 - normalise the past sample** (each observation rescaled for the schedule context it was played in, as `opponent_correction` rescales for the opponent) | `opponent_correction.SampleCorrector.correct` (`opponent_correction.py:121`), `correct_total` (`:176`) | the sample half of every marginal and of the filled joint sides | everything priced from the rating only |
| **E5 - a total-level multiplier** | as CL (`closeness_stretch.py:74`): `side_key` None, both sides' context | `_total` rows | - |

Points that apply to any entry:

* **Totals.** `_total` rows pool both sides' match totals (`run_sheet.py:2872-2901`), and a
  rated total is home + away rating (`football_rating.py:1319-1320`). A per-side schedule
  effect on a total needs either E1 (per side inside the rating) or a total-level function of
  both sides' contexts (E5). A side-level term in E2 with `side_key` None would not apply.
* **Halves.** Halves are their own metrics, not derived from the full match. The 1H / 2H
  goals, corners, fouls 1H, shots 1H and SOT 1H are base metrics of their own; the 2H count
  metrics are sample-only. A fatigue effect concentrated late in a match would need a 2H-
  specific coefficient. SUSPICION: "fatigue shows in the 2H" is the literature's claim, not
  measured here.
* **Ladders.** All rungs of one (market, subject) share one centre and sd, so every line of a
  ladder moves at once. Nothing per line is needed. Per-line curves
  (`config/sofa_line_curves.json`) read the moved p.
* **Player props via share** move with T under E2, and under E1 only through the rating half
  of T.
* **The simulator** reads only `FootballForecast.centre("goals_for"/"cards_points_for")`
  (`football_sim_sheet.py:69-82`). Only E1 reaches it.
* **`MODEL_ABOVE_OWN_SAMPLE`.** CONFIDENCE automatically removes a football leg (props
  excluded) whose p exceeds its own-sample hit rate by more than 0.15 (`confidence.py:705-737`;
  `run_confidence.py:957-969`). A correction that moves p up, away from the raw sample, can be
  stripped by this gate. Audit 2026-10-13 point 8 (`AUDYT_RYNKOW_KONTEKST_2026-10-13.md:1984`)
  says to measure any context correction together with the gate.
* **SHEET markers / rebuild_plan.** Every football correction stamps a row marker (`referee_rule`,
  `game_state_rule`, ...; see `epochs.py:1682-1690, 2506`), so `rebuild_plan` re-runs SHEET when
  the switch is on. A schedule term needs its own marker.
* **Data dependency.** The schedule is computed in SAMPLES from cached listings
  (`samples.py:2331-2342`, `schedule.side_schedule` `schedule.py:221-243`) and stored in
  `03_samples.json`. SHEET would have to read it from there. A history replay needs the same
  as-of reading for every past match. `measure_schedule_context.py` already has that reader.
  The schedule also lacks some of what the task asks about: travel distance, midweek European
  games as a kind (only counts; `match_kind` is used to drop friendlies), and coach change.

### 3b. Families a centre correction CANNOT reach (without new machinery)

| family | why | file:line |
|---|---|---|
| `red_cards_total`, `penalties_total`, `red_cards_1h_total`, `penalties_1h_total`, `both_red_cards` | competition base rate, no team input | `football_incidents.py:237-245`; `football_card_halves.py:33-37` |
| `red_cards_for`, `penalties_for`, `penalties_1h_for`, `red_cards_1h_for` | league rate x supremacy only (E1 reaches them via supremacy, E2 does not) | `football_card_halves.py:535-545` |
| 8 shot-detail props | own starts shrunk to the position pool | `shot_detail.py:150-170` |
| `player_assists_for`, `player_tackles_for`, `player_interceptions_for`, `player_offsides_for`, `player_fouls_drawn_for` | own sample, no team centre | `run_sheet.py:2807-2866, 1132-1140` |
| raw-sample joints: `both_over_goals_1h/2h`, `both_over_corners_1h/2h`, `both_over_shots*`, `both_over_fouls*`, `both_over_offsides`, `both_over_saves*`, `both_over_throw_ins/goal_kicks/tackles`, `most_corners_1h/2h`, `most_shots*`, `handicap_corners_1h/2h`, `handicap_shots*` | `DERIVED_MARGINAL_CENTRES_METRICS` = only goals_for / corners_for / SOT_for / cards_points_for | `epochs.py:224-226`; `run_sheet.py:3608`, `:1277` |
| pure-rating families (A + sim) | only through E1 | as above |

---

## 4. Curves and files that a centre change invalidates, and what replays them

The rule (CLAUDE.md, "Curves are fitted on the history... replayed as of each match with the
estimator SHEET prices with today"): a new centre term is first a replay flag of the cache
replay, then a refit on a DB copy. It needs the operator's go to install.

| curve / file | keys affected | fitted by | replay needed |
|---|---|---|---|
| `config/sofa_confidence_calibration.json` + the staged `.next.json` (11-06 17:30Z) and `.next.2026-11-07.json` (live for 11-08) | `by_market_direction` (246 keys, football count / goals / joint / player / score / incident / card-half), `by_market` (97), `thin_by_market_direction` (54), `by_class` (`women` 184 / `season_early` 41 football keys), `pooled_by_sport` | `scripts/sofa/fit_confidence.py` on the rows of `scripts/sofa/calibrate_from_cache.py`, orchestrated by `scripts/sofa/prepare_refit.py` (replay -> fit -> install, `tests/sofa` gate) | `calibrate_from_cache.py` would need a new flag (as `--referee` `:3356`, `--closeness-stretch` `:3250`, `--form-table-per-family` `:3372`, `--awarded-excluded` `:3122`); `prepare_refit` checks the installed file's `fitted_from.replay_rules.flags` (the live files still carry the 10-17 list of 21 flags; the 11-05 replay added `--closeness-stretch --player-coverage --awarded-excluded --referee --player-share --tennis-score-winner`, `docs/sofa/evidence/refit_replay_2026-11-05.md:7, 42`) |
| per-line curves | `by_market_direction_line` (76 keys, incl. joints at their line); the key list `config/sofa_line_curves.json` (33 football keys) | `fit_confidence` (line buckets); `scripts/sofa/install_line_curves.py` | same replay |
| score-market slice curves (`result_or_*@S@L`, `result_handicap@...`, `dc_and_*@...`, `btts_or_over@...`) | in the calibration file | `scripts/sofa/fit_score_market_curves.py` ("history curves on the replay's pure rating centres", `football_score_markets.py:5-8`) | E1 only |
| `double_chance`, `result_1x2`, `draw_no_bet` (+ `season_early`, `women`) | in the calibration file | `fit_double_chance_curve.py`, `fit_result_1x2_dnb_curve.py` | E1 only |
| `first_goal`, `red_cards_*`, `penalties_*`, card halves | in the calibration file (`new_market_curves_fitted_from`) | `fit_incident_set_curves.py` | E1 (first goal, side events); E2 (card halves) |
| joint curves + `config/sofa_side_correlations.json` | `both_over_*`, `most_*`, `handicap_*` | `fit_joint_curves.py` | for the 4 marginal-centre metrics |
| `config/sofa_football_sim_curves.json` | 11 `market|DIR` + `women` | `fit_football_sim_curves.py` (walk-forward 06-01..10-20) | E1 only; the sim walk-forward must read the corrected centres |
| shot-detail curve / `config/sofa_shot_detail.json` | 8 props | `fit_shot_detail.py` | unaffected |
| **centre-term tables fitted on the rating's centres** | `sofa_game_state.json`, `sofa_count_stretch.json`, `sofa_closeness_stretch.json`, `sofa_goals_stretch.json`, `sofa_player_stretch.json`, `sofa_season_phase.json`, `sofa_rating_weight.json`, `sofa_referee_effect.json`, `sofa_player_share.json`, `sofa_count_dispersion.json` | `calibrate_from_cache.py` / `fit_*` scripts (outputs listed in `prepare_refit.py`) | E1 moves the supremacy and the rating centres these were fitted against. SUSPICION: their coefficients would need re-fitting or at least re-checking |
| `sofa_football_result.json` (`nb_r`) | pure-rating NB dispersion | measured, no fit script writes it (`football_result.py:30-33`) | E1 or E3 |
| **line evidence** `config/sofa_superbet_line_evidence.json` | every key's offset / price-band cap | `refresh_line_evidence.py` -> `fit_line_evidence.py` every morning; it reads each settled row's **stored** `p_central` from `07_settled.json` through the installed curve (`fit_line_evidence.py:1-14`) | After a centre change, the past rows carry the old estimator's p. The tennis point model, the sim and the volleyball rally model each needed a p backfill (`data/line_evidence/*_p.json.gz`; CLAUDE.md). SUSPICION: a schedule term would need one too, or a period of mixed-estimator evidence |
| settleability, live-only curves | unaffected (not centre-based) | | |

Ledger: an install is a new epoch group (`audit_ledger.EPOCH_GROUPS`).

---

## 5. Volume (football legs by family)

Sources: `runs/sofa/<d>/08_confidence.json` `legs` (field names: `sport`, `market`,
`confidence`, `direction`, `line`, `subject`, ...). 18 days: 10-20..10-29 and 11-01..11-08
(10-30 / 10-31 have no file). And `08_refusals.json` (columns `event, market, market_id,
period, subject, line, direction, odds, p, confidence, reason`; `reason` null = passed every
gate). 17 days: 10-21..10-29 and 11-01..11-08.

Caveats:
* `08_confidence.json` `legs` holds only legs that reached a print floor (min confidence 0.607
  on 11-05; the 0.60 floors). They are not all priced rows. "Priced" is the refusals file.
* Both files are the **last CONFIDENCE run of the day** (often an evening rebuild), so
  `KICKED_OFF` dominates the refusal reasons. Each day's file counts its own rows; a leg
  printed on several days' rebuilds counts once per day file. Days are summed, not deduplicated
  across days.
* Volumes are counts of legs, not of matches. The 11-06 / 11-07 days use the new
  sim / table models.

### 5a. By estimator group

| group | keys | priced rows | conf >= 0.70 (refusals) | passed every gate | 08_confidence legs | 08_confidence legs >= 0.70 |
|---|---|---|---|---|---|---|
| A. result / score markets (pure rating goals, NB) | 12 | 296,536 | 24,633 | 17,331 | 40,319 | 40,319 |
| B. minute simulator path markets | 9 | 42,718 | 531 | 756 | 1,252 | 606 |
| C. league-rate events (no team input) | 4 | 5,778 | 1,069 | 975 | 1,797 | 1,797 |
| D. side events (league rate x exp(beta*supremacy)) | 3 | 4,613 | 404 | 365 | 541 | 541 |
| E. card halves (cards_points_for live centre x half share) | 8 | 11,232 | 336 | 273 | 384 | 384 |
| F. player shot detail (own starts, position pool) | 8 | 95,291 | 406 | 12 | 20 | 20 |
| G. player props (sample, share/stretch) | 7 | 162,512 | 1,566 | 212 | 348 | 348 |
| H. joints both_over_/most_/handicap_ (team metrics) | 30 | 69,156 | 3,961 | 2,604 | 4,822 | 4,822 |
| I. goals marginal (rating + sample) | 6 | 184,702 | 14,178 | 7,641 | 15,236 | 15,236 |
| J. team count marginals (corners/cards/shots/SOT/fouls/offsides/saves/throw-ins/goal kicks/tackles) | 46 | 192,558 | 15,250 | 7,817 | 13,914 | 13,914 |
| **total** | 133 | 1,065,096 | 62,334 | 37,986 | 78,633 | 77,987 |

Within H, the joints of the 4 marginal-centre metrics (`both_over_goals`, `both_over_corners`,
`both_over_cards_points`, `both_over_shots_on_target`, `handicap_cards_points`,
`most_shots_on_target`, `most_corners`) give 1,678 legs >= 0.70. The raw-sample joints
give 3,144, led by `both_over_goals_1h` 1,842 and `both_over_goals_2h` 1,209.

### 5b. By market key (sorted by 08_confidence legs >= 0.70)

| market (family key) | priced rows (08_refusals, odds present) | with confidence | conf >= 0.70 | passed every gate | 08_confidence legs | of which conf >= 0.70 | days present (08_confidence) | top refusal reasons |
|---|---|---|---|---|---|---|---|---|
| `result_or_over` | 91,135 | 31,455 | 8,408 | 6,309 | 15,285 | 15,285 | 18 | KICKED_OFF 41311; BELOW_CONFIDENCE_FLOOR 23047 |
| `result_or_under` | 90,137 | 31,193 | 9,028 | 5,801 | 13,516 | 13,516 | 18 | KICKED_OFF 41268; BELOW_CONFIDENCE_FLOOR 22165 |
| `double_chance` | 20,306 | 8,083 | 3,401 | 2,528 | 5,902 | 5,902 | 18 | KICKED_OFF 10460; BELOW_CONFIDENCE_FLOOR 4682 |
| `corners_total` | 32,302 | 15,226 | 2,859 | 2,330 | 4,409 | 4,409 | 18 | KICKED_OFF 14547; BELOW_CONFIDENCE_FLOOR 12367 |
| `goals_total` | 56,118 | 22,594 | 4,161 | 2,095 | 4,345 | 4,345 | 18 | KICKED_OFF 27926; BELOW_CONFIDENCE_FLOOR 18433 |
| `goals_2h_total` | 23,926 | 11,028 | 2,913 | 1,983 | 3,935 | 3,935 | 18 | KICKED_OFF 11085; BELOW_CONFIDENCE_FLOOR 8115 |
| `goals_1h_total` | 22,288 | 9,949 | 2,079 | 1,428 | 2,766 | 2,766 | 18 | KICKED_OFF 10103; BELOW_CONFIDENCE_FLOOR 7870 |
| `goals_for` | 42,924 | 18,915 | 3,360 | 1,397 | 2,743 | 2,743 | 18 | KICKED_OFF 19028; BELOW_CONFIDENCE_FLOOR 15555 |
| `result_handicap` | 7,467 | 2,691 | 1,491 | 1,138 | 2,318 | 2,318 | 18 | KICKED_OFF 2721; ODDS_TOO_LOW 1900 |
| `corners_1h_total` | 13,612 | 7,058 | 1,258 | 1,010 | 1,898 | 1,898 | 18 | KICKED_OFF 5929; BELOW_CONFIDENCE_FLOOR 5800 |
| `both_over_goals_1h` | 6,621 | 3,061 | 1,407 | 953 | 1,842 | 1,842 | 17 | KICKED_OFF 3288; BELOW_CONFIDENCE_FLOOR 1654 |
| `corners_for` | 29,726 | 14,571 | 2,777 | 942 | 1,704 | 1,704 | 18 | KICKED_OFF 12305; BELOW_CONFIDENCE_FLOOR 11794 |
| `both_over_goals_2h` | 6,973 | 3,282 | 978 | 645 | 1,209 | 1,209 | 17 | KICKED_OFF 3460; BELOW_CONFIDENCE_FLOOR 2304 |
| `btts_or_over` | 8,490 | 3,712 | 550 | 447 | 1,069 | 1,069 | 18 | KICKED_OFF 4574; BELOW_CONFIDENCE_FLOOR 3162 |
| `cards_points_total` | 8,508 | 4,825 | 836 | 524 | 886 | 886 | 18 | BELOW_CONFIDENCE_FLOOR 3989; KICKED_OFF 3092 |
| `draw_no_bet` | 13,275 | 5,336 | 489 | 358 | 883 | 883 | 18 | KICKED_OFF 7057; BELOW_CONFIDENCE_FLOOR 4847 |
| `goals_2h_for` | 20,775 | 9,619 | 940 | 417 | 815 | 815 | 18 | KICKED_OFF 9408; BELOW_CONFIDENCE_FLOOR 8679 |
| `penalties_total` | 2,582 | 1,325 | 409 | 387 | 805 | 805 | 18 | KICKED_OFF 1158; BELOW_CONFIDENCE_FLOOR 916 |
| `red_cards_total` | 2,151 | 1,171 | 511 | 439 | 775 | 775 | 18 | KICKED_OFF 904; BELOW_CONFIDENCE_FLOOR 660 |
| `shots_on_target_total` | 9,179 | 5,028 | 862 | 484 | 774 | 774 | 18 | BELOW_CONFIDENCE_FLOOR 4166; KICKED_OFF 3214 |
| `corners_2h_total` | 3,842 | 2,251 | 562 | 466 | 749 | 749 | 18 | BELOW_CONFIDENCE_FLOOR 1689; KICKED_OFF 1247 |
| `both_over_goals` | 17,035 | 7,282 | 579 | 378 | 713 | 713 | 17 | KICKED_OFF 9136; BELOW_CONFIDENCE_FLOOR 6703 |
| `result_or_btts` | 3,668 | 1,784 | 558 | 388 | 712 | 712 | 18 | KICKED_OFF 1566; BELOW_CONFIDENCE_FLOOR 1226 |
| `corners_1h_for` | 11,534 | 6,210 | 1,220 | 376 | 635 | 635 | 18 | BELOW_CONFIDENCE_FLOOR 4990; KICKED_OFF 4595 |
| `goals_1h_for` | 18,671 | 8,576 | 725 | 321 | 632 | 632 | 18 | KICKED_OFF 8364; BELOW_CONFIDENCE_FLOOR 7851 |
| `team_scores_both_halves` | 3,874 | 2,194 | 488 | 494 | 818 | 550 | 3 | KICKED_OFF 1512; BELOW_CONFIDENCE_FLOOR 1366 |
| `shots_total` | 9,066 | 5,274 | 512 | 308 | 511 | 511 | 18 | BELOW_CONFIDENCE_FLOOR 4762; KICKED_OFF 3584 |
| `cards_points_for` | 7,930 | 4,486 | 641 | 256 | 443 | 443 | 18 | BELOW_CONFIDENCE_FLOOR 3845; KICKED_OFF 3053 |
| `both_over_corners` | 6,257 | 2,859 | 352 | 249 | 432 | 432 | 17 | KICKED_OFF 2738; BELOW_CONFIDENCE_FLOOR 2507 |
| `shots_on_target_for` | 11,814 | 6,441 | 1,061 | 219 | 394 | 394 | 18 | BELOW_CONFIDENCE_FLOOR 5380; KICKED_OFF 4152 |
| `corners_2h_for` | 4,808 | 2,795 | 552 | 173 | 325 | 325 | 18 | BELOW_CONFIDENCE_FLOOR 2243; KICKED_OFF 1500 |
| `penalties_for` | 848 | 417 | 204 | 204 | 315 | 315 | 17 | KICKED_OFF 258; BELOW_CONFIDENCE_FLOOR 213 |
| `saves_total` | 4,476 | 2,838 | 399 | 196 | 295 | 295 | 18 | BELOW_CONFIDENCE_FLOOR 2439; KICKED_OFF 1539 |
| `both_over_cards_points` | 3,483 | 1,971 | 248 | 149 | 255 | 255 | 17 | BELOW_CONFIDENCE_FLOOR 1723; KICKED_OFF 1356 |
| `cards_points_1h_total` | 3,110 | 1,831 | 215 | 175 | 238 | 238 | 17 | BELOW_CONFIDENCE_FLOOR 1616; KICKED_OFF 1228 |
| `shots_for` | 12,454 | 7,312 | 587 | 137 | 234 | 234 | 17 | BELOW_CONFIDENCE_FLOOR 6725; KICKED_OFF 4863 |
| `saves_for` | 6,769 | 4,250 | 512 | 143 | 230 | 230 | 18 | BELOW_CONFIDENCE_FLOOR 3738; KICKED_OFF 2247 |
| `penalties_1h_total` | 470 | 253 | 149 | 149 | 217 | 217 | 17 | KICKED_OFF 147; BELOW_CONFIDENCE_FLOOR 104 |
| `dc_and_over` | 16,740 | 8,107 | 147 | 114 | 200 | 200 | 17 | KICKED_OFF 8158; BELOW_CONFIDENCE_FLOOR 7960 |
| `red_cards_for` | 3,157 | 1,035 | 175 | 138 | 195 | 195 | 17 | ODDS_TOO_LOW 1276; BELOW_CONFIDENCE_FLOOR 860 |
| `offsides_total` | 3,152 | 1,827 | 234 | 111 | 189 | 189 | 16 | BELOW_CONFIDENCE_FLOOR 1593; KICKED_OFF 1179 |
| `dc_and_under` | 17,768 | 8,605 | 337 | 100 | 181 | 181 | 17 | KICKED_OFF 8631; BELOW_CONFIDENCE_FLOOR 8268 |
| `result_or_clean_sheet` | 3,679 | 1,923 | 153 | 101 | 165 | 165 | 18 | BELOW_CONFIDENCE_FLOOR 1770; KICKED_OFF 1692 |
| `player_tackles_for` | 20,376 | 10,847 | 482 | 99 | 164 | 164 | 18 | BELOW_CONFIDENCE_FLOOR 10365; KICKED_OFF 6982 |
| `player_shots_for` | 49,316 | 28,263 | 499 | 81 | 144 | 144 | 18 | BELOW_CONFIDENCE_FLOOR 27764; KICKED_OFF 16279 |
| `cards_points_2h_total` | 1,544 | 1,017 | 116 | 93 | 139 | 139 | 17 | BELOW_CONFIDENCE_FLOOR 901; KICKED_OFF 514 |
| `both_over_shots_on_target` | 2,076 | 1,203 | 148 | 83 | 135 | 135 | 16 | BELOW_CONFIDENCE_FLOOR 1055; KICKED_OFF 821 |
| `handicap_cards_points` | 1,210 | 793 | 76 | 65 | 96 | 96 | 16 | BELOW_CONFIDENCE_FLOOR 717; KICKED_OFF 417 |
| `offsides_for` | 3,056 | 1,851 | 192 | 56 | 95 | 95 | 14 | BELOW_CONFIDENCE_FLOOR 1659; KICKED_OFF 1121 |
| `first_goal` | 10,064 | 4,861 | 65 | 43 | 82 | 82 | 15 | KICKED_OFF 4917; BELOW_CONFIDENCE_FLOOR 4796 |
| `saves_1h_total` | 1,234 | 758 | 131 | 53 | 77 | 77 | 16 | BELOW_CONFIDENCE_FLOOR 627; KICKED_OFF 472 |
| `half_goals_combo` | 15,273 | 8,437 | 43 | 217 | 377 | 56 | 3 | BELOW_CONFIDENCE_FLOOR 7941; KICKED_OFF 6768 |
| `shots_on_target_1h_total` | 1,692 | 956 | 41 | 27 | 53 | 53 | 13 | BELOW_CONFIDENCE_FLOOR 915; KICKED_OFF 714 |
| `both_over_fouls` | 985 | 556 | 57 | 30 | 52 | 52 | 10 | BELOW_CONFIDENCE_FLOOR 499; KICKED_OFF 388 |
| `both_over_saves` | 2,131 | 1,068 | 23 | 16 | 31 | 31 | 11 | BELOW_CONFIDENCE_FLOOR 1045; KICKED_OFF 646 |
| `penalties_1h_for` | 608 | 173 | 25 | 23 | 31 | 31 | 12 | ODDS_TOO_LOW 267; BELOW_CONFIDENCE_FLOOR 148 |
| `most_shots_on_target` | 1,620 | 977 | 35 | 20 | 30 | 30 | 9 | BELOW_CONFIDENCE_FLOOR 942; KICKED_OFF 605 |
| `player_fouls_for` | 29,127 | 18,862 | 223 | 16 | 23 | 23 | 11 | BELOW_CONFIDENCE_FLOOR 18639; KICKED_OFF 8483 |
| `player_fouls_drawn_for` | 26,758 | 16,607 | 362 | 16 | 17 | 17 | 6 | BELOW_CONFIDENCE_FLOOR 16245; KICKED_OFF 8376 |
| `most_corners` | 3,928 | 1,934 | 32 | 9 | 17 | 17 | 8 | BELOW_CONFIDENCE_FLOOR 1902; KICKED_OFF 1804 |
| `player_right_foot_shots_for` | 19,769 | 11,685 | 314 | 7 | 15 | 15 | 11 | BELOW_CONFIDENCE_FLOOR 11371; KICKED_OFF 6968 |
| `both_over_goal_kicks` | 408 | 201 | 18 | 5 | 8 | 8 | 6 | BELOW_CONFIDENCE_FLOOR 183; KICKED_OFF 130 |
| `cards_points_1h_for` | 3,248 | 1,712 | 5 | 5 | 7 | 7 | 4 | BELOW_CONFIDENCE_FLOOR 1707; KICKED_OFF 1370 |
| `result_1x2` | 13,807 | 5,701 | 6 | 4 | 6 | 6 | 2 | KICKED_OFF 7546; BELOW_CONFIDENCE_FLOOR 5695 |
| `saves_1h_for` | 794 | 496 | 0 | 0 | 6 | 6 | 4 | BELOW_CONFIDENCE_FLOOR 496; KICKED_OFF 288 |
| `player_left_foot_shots_for` | 14,006 | 8,401 | 92 | 5 | 5 | 5 | 3 | BELOW_CONFIDENCE_FLOOR 8309; KICKED_OFF 4962 |
| `both_over_shots` | 2,219 | 1,284 | 3 | 2 | 2 | 2 | 2 | BELOW_CONFIDENCE_FLOOR 1281; KICKED_OFF 850 |
| `offsides_2h_for` | 434 | 346 | 2 | 1 | 2 | 2 | 1 | BELOW_CONFIDENCE_FLOOR 344; KICKED_OFF 88 |
| `fouls_for` | 1,524 | 970 | 1 | 1 | 1 | 1 | 1 | BELOW_CONFIDENCE_FLOOR 969; KICKED_OFF 464 |
| `shots_on_target_1h_for` | 1,118 | 658 | 1 | 1 | 1 | 1 | 1 | BELOW_CONFIDENCE_FLOOR 657; KICKED_OFF 402 |
| `goal_kicks_for` | 906 | 518 | 5 | 1 | 1 | 1 | 1 | BELOW_CONFIDENCE_FLOOR 513; KICKED_OFF 346 |
| `shots_2h_for` | 496 | 344 | 3 | 1 | 1 | 1 | 1 | BELOW_CONFIDENCE_FLOOR 341; KICKED_OFF 116 |
| `offsides_1h_for` | 438 | 350 | 2 | 1 | 1 | 1 | 1 | BELOW_CONFIDENCE_FLOOR 348; KICKED_OFF 88 |
| `player_shots_on_target_for` | 24,561 | 15,293 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 15293; KICKED_OFF 8436 |
| `player_shots_outside_box_for` | 18,840 | 11,468 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 11468; KICKED_OFF 6694 |
| `player_headed_shots_for` | 11,089 | 6,799 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 6799; KICKED_OFF 3942 |
| `htft` | 10,609 | 5,649 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 5649; KICKED_OFF 4879 |
| `player_sot_right_foot_for` | 10,013 | 6,238 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 6238; KICKED_OFF 3509 |
| `player_sot_outside_box_for` | 8,680 | 5,463 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 5463; KICKED_OFF 2981 |
| `player_sot_left_foot_for` | 8,165 | 5,056 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 5056; KICKED_OFF 2868 |
| `player_assists_for` | 7,939 | 4,716 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 4716; KICKED_OFF 2991 |
| `player_sot_headed_for` | 4,729 | 2,948 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 2948; KICKED_OFF 1644 |
| `player_offsides_for` | 4,435 | 2,717 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 2717; KICKED_OFF 1525 |
| `result_1h` | 3,027 | 1,817 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 1817; KICKED_OFF 1201 |
| `result_2h` | 3,026 | 1,814 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 1814; KICKED_OFF 1201 |
| `most_cards_points` | 2,967 | 1,749 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 1749; KICKED_OFF 1170 |
| `higher_scoring_half` | 2,919 | 1,728 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 1728; KICKED_OFF 1185 |
| `handicap_corners` | 2,794 | 1,570 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 1570; KICKED_OFF 1157 |
| `most_corners_1h` | 2,534 | 1,402 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 1402; KICKED_OFF 1071 |
| `btts_halves` | 1,690 | 930 | 0 | 23 | 25 | 0 | 3 | BELOW_CONFIDENCE_FLOOR 887; KICKED_OFF 752 |
| `shots_1h_total` | 1,636 | 910 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 910; KICKED_OFF 686 |
| `fouls_total` | 1,452 | 852 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 852; KICKED_OFF 546 |
| `first_goal_1h` | 1,380 | 762 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 762; KICKED_OFF 612 |
| `most_shots` | 1,243 | 733 | 5 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 728; KICKED_OFF 450 |
| `cards_points_2h_for` | 1,086 | 590 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 590; KICKED_OFF 360 |
| `shots_1h_for` | 1,024 | 592 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 592; KICKED_OFF 358 |
| `btts_any_half` | 920 | 508 | 0 | 22 | 32 | 0 | 3 | BELOW_CONFIDENCE_FLOOR 466; KICKED_OFF 408 |
| `throw_ins_for` | 906 | 508 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 508; KICKED_OFF 346 |
| `tackles_for` | 898 | 532 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 532; KICKED_OFF 344 |
| `most_corners_2h` | 814 | 487 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 487; KICKED_OFF 297 |
| `both_over_offsides` | 792 | 458 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 458; KICKED_OFF 297 |
| `most_cards_points_1h` | 705 | 330 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 330; KICKED_OFF 237 |
| `most_cards_points_2h` | 705 | 330 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 330; KICKED_OFF 237 |
| `throw_ins_total` | 684 | 379 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 379; KICKED_OFF 270 |
| `goal_kicks_total` | 682 | 398 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 398; KICKED_OFF 268 |
| `shots_on_target_2h_for` | 590 | 418 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 418; KICKED_OFF 160 |
| `red_cards_1h_total` | 575 | 295 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 295; KICKED_OFF 160 |
| `tackles_total` | 486 | 274 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 274; KICKED_OFF 190 |
| `fouls_1h_for` | 442 | 320 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 320; KICKED_OFF 88 |
| `fouls_2h_for` | 438 | 332 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 332; KICKED_OFF 88 |
| `handicap_cards_points_2h` | 425 | 194 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 194; KICKED_OFF 144 |
| `handicap_cards_points_1h` | 409 | 260 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 260; KICKED_OFF 144 |
| `both_over_saves_1h` | 397 | 217 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 217; KICKED_OFF 153 |
| `both_over_throw_ins` | 395 | 138 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 138; NO_LINE_EVIDENCE 125 |
| `handicap_corners_1h` | 360 | 189 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 189; KICKED_OFF 139 |
| `handicap_corners_2h` | 358 | 185 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 185; KICKED_OFF 139 |
| `both_over_tackles` | 346 | 109 | 0 | 0 | 0 | 0 | 0 | NO_LINE_EVIDENCE 122; KICKED_OFF 112 |
| `shots_on_target_2h_total` | 316 | 216 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 216; KICKED_OFF 90 |
| `throw_ins_1h_for` | 308 | 204 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 204; KICKED_OFF 88 |
| `throw_ins_2h_for` | 308 | 206 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 206; KICKED_OFF 88 |
| `most_shots_1h` | 273 | 164 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 164; KICKED_OFF 74 |
| `most_shots_2h` | 272 | 163 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 163; KICKED_OFF 73 |
| `shots_2h_total` | 264 | 186 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 186; KICKED_OFF 66 |
| `fouls_1h_total` | 232 | 160 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 160; KICKED_OFF 50 |
| `fouls_2h_total` | 230 | 164 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 164; KICKED_OFF 50 |
| `offsides_1h_total` | 230 | 178 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 178; KICKED_OFF 50 |
| `offsides_2h_total` | 228 | 176 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 176; KICKED_OFF 50 |
| `handicap_shots_on_target` | 184 | 121 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 121; KICKED_OFF 44 |
| `handicap_shots` | 174 | 30 | 0 | 0 | 0 | 0 | 0 | NO_LINE_EVIDENCE 65; KICKED_OFF 42 |
| `throw_ins_1h_total` | 170 | 106 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 106; KICKED_OFF 50 |
| `throw_ins_2h_total` | 170 | 102 | 0 | 0 | 0 | 0 | 0 | BELOW_CONFIDENCE_FLOOR 102; KICKED_OFF 50 |
| `handicap_shots_1h` | 154 | 44 | 0 | 0 | 0 | 0 | 0 | NO_LINE_EVIDENCE 55; BELOW_CONFIDENCE_FLOOR 44 |
| `handicap_shots_2h` | 153 | 43 | 0 | 0 | 0 | 0 | 0 | NO_LINE_EVIDENCE 55; BELOW_CONFIDENCE_FLOOR 43 |

(The aggregation script and its raw JSON are next to this file: `vol.py`, `vol.json`.)

---

## 6. Today's schedule metadata and who reads it

| item | what | file:line |
|---|---|---|
| `SideSchedule` | `last_match_utc`, `rest_days`, `matches_7d`, `matches_14d`, `other_division` | `src/bet/sofa/schedule.py:50-60` |
| `FixtureSchedule` | `makeup_of`, `makeup_postponed_utc`, `side_a`, `side_b`; `.flags()` -> `MAKEUP_FIXTURE`, `LONG_LAYOFF` (>= 21 d, `:45`), `CONGESTED` (>= 3 in 7 d, `:47`), `OTHER_DIVISION_SAMPLE` | `schedule.py:63-89` |
| computation | finished, non-friendly events before kick-off from the cached `last` listings (no request); a match without statistics counts | `schedule.py:221-243` (`side_schedule`), `:246-284` (`fixture_schedule`) |
| written by | SAMPLES -> `03_samples.json` `schedule` | `src/bet/sofa/samples.py:2330-2349`; field `contracts.py:282-284` |
| read by CONFIDENCE | `context_flags` on the leg, display only | `scripts/sofa/run_confidence.py:292-296, 1020-1027` |
| read by COUPON / PDF / dossier | make-up note; PDF tags; dossier `schedule` block | `scripts/sofa/build_coupon.py:101-103`; `build_coupon_pdf.py:344`; `src/bet/sofa/dossier.py:701` |
| read by SAMPLES / SHEET / rating / centre chain / sim / replay | **no** (no `schedule` reference in `run_sheet.py`, `football_rating.py`, `centre_chain.py`, `football_sim.py`, `football_sim_sheet.py`, `calibrate_from_cache.py`); CLAUDE.md: "`context_flags` ... are shown, never gated" | grep |
| prior measurement | `scripts/sofa/measure_schedule_context.py` (residual vs raw sample mean, by makeup / rest band / congested) and `measure_sample_composition.py --context` | results above (Section 0) |
| not present | travel distance (venue city exists only in the dossier); European-cup midweek as its own kind (`comparability.match_kind` exists; the schedule counts every competitive match alike); coach change (no source in the pipeline; SUSPICION: Sofascore `/team/{id}` manager data are not cached) | - |

---

## 7. Surprising / worth knowing

1. **Pure-rating dominance.** Result / score markets account for 51% of the football legs at
   >= 0.70, and none of them goes through `centre_chain`. A referee-style E2 term would leave
   them untouched. Only an in-rating term (E1) moves them, and E1 also moves supremacy, so every
   stretch table fitted against it.
2. **Half-scoped joints read raw samples.** `both_over_goals_1h/2h` (3,051 legs >= 0.70) and
   every other half joint are built on the raw side samples. They read no rating, no chain
   and no opponent correction, because `DERIVED_MARGINAL_CENTRES_METRICS` holds only 4
   full-match metrics (`epochs.py:224-226`). No centre correction reaches them unless that list
   grows. Audit C16 already flagged this for fouls / shots / offsides
   (`AUDYT_RYNKOW_KONTEKST_2026-10-13.md:120`).
3. **`corners_total` is the top count family** (4,409 legs >= 0.70). It is unrated: pooled
   sample + opponent correction, and no GS / CS / referee / closeness term at all. A schedule
   effect on corners (the 10-04 table: -0.280 at >= 21 d) would need a total-level term.
4. **`MODEL_ABOVE_OWN_SAMPLE`** can strip upward-moved legs (`confidence.py:705`).
5. **Line evidence uses stored p.** `fit_line_evidence.py` keys its offsets on the settled
   rows' stored `p_central`. A centre change makes past rows a different estimator's p
   (SUSPICION: a backfill would be needed, as for the tennis point / sim / volleyball models).
6. **The referee and closeness tables are not in the live calibration's `replay_rules`.** The
   live calibration files still list the 10-17 flags (21). The 11-05 refit replayed
   `--referee --player-share --closeness-stretch`, but only its refitted keys were staged
   (`staged_change.refitted_keys`); every other key is the 10-17 curve. A new term's refit
   would refit on top of this mixed state.
7. **Stale docstrings.** `football_sim.py:1-6` still says "MEASUREMENT ONLY ... nothing in the
   pipeline imports this module". `football_sim_sheet.py` imports it and it has been live
   since 11-06 17:30Z. `player_share.TEAM_METRIC` lists `player_tackles_for`
   (`player_share.py:36-41`), but `config/sofa_player_share.json` has only shots / SOT / fouls,
   so tackles props get no share.
8. **Effect sizes from the earlier measurement are small.** Rest as a log-loss feature gave
   -0.00015 on goals_total (10-05), against the referee / closeness gains on cards (-2..-5 pp
   per the 11-05 report). Weigh the work against this before E1.
