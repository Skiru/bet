# Model state - switches, fits, measurements (reference)

Read this before proposing or changing a model, a curve, a switch or a refit.
The archive of record for developers: every switch with its date, measurement
and evidence path; the installed fits and their source DBs; what was measured
and declined; what is open. The code is the authority for dates:
`src/bet/sofa/epochs.py` (every `*_FROM_UTC`; `None` = off). Evidence lives in
`docs/sofa/evidence/`, reports in `docs/sofa/history/`. Intervals are 95%
match-bootstrap unless said otherwise; log-loss deltas are new minus old
(negative = better).

## (a) Switches ON

A day built before a switch's moment, or rebuilt later, keeps the rule it was
printed by (switches are judged on the day built AND the build clock). Where a
switch went into an already built day the day is mixed (section f).

### Foundations (10-05 .. 10-08)

| constant | from (UTC) | what | evidence |
|---|---|---|---|
| `STATS_ONLY_FROM_UTC` | 10-05 07:15 | confidence from the statistics alone; the price only the betting condition | `docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md` |
| `SPORTS_ON_COUPON_FROM_UTC` | 10-05 08:30 | hockey / basketball / volleyball / CS2 print on the one coupon (the separate sport coupons retired 2026-10-05) | same |
| `COUPON_STRUCTURE_FROM_UTC` | 10-06 00:00 | coupon-form dials (ladder `one_rung`, per-match cap - both OFF unless `config/sofa_coupon_form.json` sets them) and the builder screen-price gate (itself off: `BUILDER_SCREEN_PRICE_FROM_UTC` None) | same, F4 |
| `SETTLEABILITY_FROM_UTC` | 10-06 00:00 | `NOT_SETTLEABLE` for (competition, family) cells of `config/sofa_settleability.json` | F0.6 |
| `AMPERSAND_SUBJECTS_FROM_UTC` | 10-06 00:00 | a club with "&" in its name is a subject of its own markets when it equals a listing participant (`market_mapper.subject_is_combination`); 37 occurrences 09-18..10-05 | F1.1 |
| `POOL_NEIGHBOUR_CAP_FROM_UTC` | 10-06 00:00 | K13b: a pooled read capped by the market's nearest own bucket below (goals_1h_total O0.5 printed 0.815 vs own 0.709 / 0.731; 57 rows / 48 matches -12.6 pp [-24.1, -1.2], capped +3.1 [-8.4, +14.4]; a market with no own bucket read off the pool -14.1 pp [-21.0, -7.2], 290 rows, not touched) | `scripts/sofa/measure_pool_holes.py` |
| `NATIONAL_SAMPLE_AGE_FROM_UTC` | 10-06 00:00 | national-team fixtures judged by sample count, not the 180-day `SAMPLE_CROSSES_SEASON` age | - |
| `LINK_SHARED_LEAGUE_FROM_UTC` | 10-07 06:45 | a football pair is LINKED only when both sides' leagues are the competition they share (else `CROSS_LEAGUE_UNLINKED`); the hockey / basketball / volleyball score model reads the same book; rows carry `link_rule`; a promoted side is cross-league until its new league is its modal one | - |
| `LINE_EVIDENCE_FROM_UTC` | 10-07 10:55 | line evidence: offset + price-band cap + Wilson bound for keys without a curve (rules: arithmetic.md, Chain 2) | `docs/sofa/evidence/discrimination_within_price_2026-10-07.md` |
| `LINE_EVIDENCE_V2_FROM_UTC` | 10-07 13:42 | `LineEvidence.v2` rules (need the evidence file's `games` field; an older file reads nothing for a key without a curve) | - |
| `TENNIS_RATING_PRICES_FROM_UTC` | 10-07 14:05 | `games_won_for`, `handicap_games`, `most_games` (not its draw) priced by the rating alone, no price; `games_total` = 50/50 mix of NB and rating | `docs/sofa/history/AUDYT_MODELI_2026-10-07.md` |
| `DERIVED_MARGINAL_CENTRES_FROM_UTC` | 10-07 14:05 | football goals / corners / shots-on-target / cards joints built from the marginal rows' centres | same |
| `BB_FRESHNESS_FROM_UTC` | 10-07 14:05 | basketball simulation noise x1.085 when the thinner side has <= 2 games in 120 days, x1.026 for 3..9 (live and history replay) | same |
| `PEER_CHOICE_FROM_UTC` | 10-08 08:10 | peer annotation (★ the surer of two legs of one match within `PEER_BAND` 0.06); annotation only; 10-08 mixed | `docs/sofa/evidence/peer_choice_2026-10-08.md` |

Peer choice measurement: of 57,791 decided pairs (football / tennis, 20 days)
the more confident leg won 53.4% [52.2, 54.7]; no sample statistic (hit rate,
size, near misses, margin, venue, last 5), tournament metadata (popularity,
reserve / women / cup / national) or combination improved the confidence out of
sample; hockey / basketball / volleyball show no measurable edge
(`scripts/sofa/measure_peer_choice.py`; check `T-PEER-CHOICE-edge`). Stakes
flags (`bet.sofa.stakes`, `STAKES_SIX_POINTER`, `STAKES_TOP4`, from the football
history's league table as of kickoff): six-pointer +0.2 cards, +0.9 fouls,
-0.15 goals, -1.0 shots per match (0.08-0.16 sd); top-4 +0.2 cards, -0.2
goals; not corrected for relegation-zone weakness; shown, never gated.

### Refit installed 2026-10-08 23:42Z (commits 5330f357 / fdbe0aae), switches from 10-09 00:00Z

| constant | from | what |
|---|---|---|
| `COUNT_DISPERSION_FROM_UTC` | 10-09 00:00 | football count spread from an alpha fitted on the history, NB per competition (`config/sofa_count_dispersion.json`, `fit_count_dispersion.py`); normal with pooled variance for `shots_total`; log-loss better on 52/52 markets out of sample; rows `dispersion_rule`; replay `--count-dispersion` |
| `TENNIS_SCOPED_TABLE_FROM_UTC` | 10-09 00:00 | rating neighbours from the tier x gender cell, then tier, then pooled when a cell holds < 1200 outcomes, plus tier start `lp_t`; games_total -81e-4 log-loss; `tennis_table_rule`; replay `--tennis-scoped-table`, fit `fit_tennis_rating.py --tier-start` (tier_start offsets look ahead inside the replay - Elo at the cut - like the coefficients) |
| `PER_MARKET_K_FROM_UTC` | 10-09 00:00 | `K_CENTRE.by_market.football` in `config/sofa_engine_constants.json`: cards_points_for 25, fouls_total 2, shots_for 8, shots_total 5; goals stay 15; `k_rule`; `--per-market-k`. Paired with COUNT_DISPERSION: SHEET exits 2 with only one on (`epochs.require_k_with_dispersion`) |
| `READ_EVENTS_FROM_UTC` | 10-09 00:00 | reads by match: every unlocked leg of the first 30 matches (`read_unit: "event"`; operator "30 wydarzeń, nie 30 rynków") |

A day < 10-09 is the old estimator and is never rebuilt under the new one; a
rebuild of a day >= 10-09 re-runs SHEET on a sheet without the markers
(`rebuild_plan.py`). Preview on 10-07 data: printing legs 572 -> 634 (football
251 -> 269, tennis 321 -> 365; 47 of the 113 new legs tennis `games_won_for`
UNDER), builders 11 -> 8. Line evidence was fitted on the old curves and
applied to the new until refitted (first mornings' offsets noisy:
`games_won_for` UNDER likely over-lowered; `goals_total` / `corners_total`
possibly double-counted). Evidence:
`docs/sofa/evidence/{count_families,tennis_calibration,dependence_goals,pooling,k_under_dispersion}_2026-10-08.md`;
`docs/sofa/history/RAPORT_STAGED_REFIT_2026-10-08.md`,
`docs/sofa/history/RUNBOOK_INSTALL_2026-10-08.md`. A refit carrying these:
`prepare_refit.py rebuild-cache-rows --confirm --without-db-backup
--count-dispersion --per-market-k --cards-correlation --tennis-scoped-table`
on the copy, with `fit_tennis_rating.py --tier-start`.

### Player switches 10-12 (ledger group "od 10-12")

| constant | from | what | evidence |
|---|---|---|---|
| `PLAYER_NAME_TOKENS_FROM_UTC` | 10-12 00:00 | a footballer `players.match_player` misses is looked for by whole name tokens (`match_player_by_tokens`: >= 2 shared, one candidate, one side); 346 of 680 `NO_ENTITY_FOUND` players of 10-08..10-10; sample `match_rule: "tokens"`, row `PLAYER_NAME_TOKENS` | `docs/sofa/evidence/player_name_tokens_2026-10-11.md` |
| `PLAYER_STARTS_ONLY_FROM_UTC` | 10-12 00:00 | player sample = his starts (`appearances: "starts"`, note `PLAYER_STARTS_ONLY`); bucket-calibrated -0.0027 log-loss [-0.0030, -0.0024] vs all appearances; player curves fitted on starters (in the installed calibration since the 10-14 refit, replay `--player-starts-only`) | `docs/sofa/evidence/player_starts_2026-10-11.md` |
| `ONE_SIDED_SINGLES_FROM_UTC` | 10-12 00:00 | a one-sided (OVER-only) player leg prints as a single when its confidence is its own market's history curve with n >= 300 (`confidence.one_sided_single`); measured before: 49 would-print legs 10-05..10-10, ROI -10.3% [-27, +4] vs -3.0% team legs - open check | same |
| `PRICE_GAP_FLAG_FROM_UTC` | 10-12 11:51 | `price_gap` annotation (`CONFIDENCE_ABOVE_PRICE`, `GAP` 0.03), football / tennis; 10-12 mixed | `docs/sofa/evidence/price_gap_2026-10-12.md` |

`regrade_settled.py --player-not-started` deleted 5,215 bench rows of
09-24..10-10 on 2026-10-11 (none printed). Price-gap measurement: printed legs
10-09..10-11, football 458 legs / 269 matches -6.8 pp [-12.0, -2.1], tennis
52 / 35 -18.6 pp [-31.0, -5.9], rest +0.3 pp; same sign every day
10-07..10-11; ROI not measurably worse. Measured sports carry no flag:
hockey's 32 over-price legs -1.2 pp [-15.1, +11.9]; basketball overstated on
both sides of the price alike (-15 / -18 pp on 52 / 50 legs - a curve
question); volleyball / CS2 too few (`scripts/sofa/measure_price_gap.py`;
CS2 measured on settled lines instead and flagged from 10-21, below).
`T-PRICE-GAP-flag` PASSED 2026-10-19: 10-13..10-18 football 2,111 flagged legs
/ 932 matches -10.0 pp [-12.8, -7.4] (hit 0.696 at mean 1/odds 0.734), rest
-0.9 pp; ROI alike (-5.1% / -5.5%). Four other red flags measured the same
week add nothing (`scripts/sofa/measure_red_flags.py`,
`docs/sofa/evidence/red_flags_2026-10-19.md`): a long price at confidence just
above 0.70 is `price_gap` itself; confidence above own k/n and builders
nothing; a leading favourite's shots / corners OVER too few legs
(`T-RED-FLAG-SCRIPT`, from 10-20).

### Audit 2026-10-13: refit 10-13 18:06Z and switches 18:10Z (10-13 mixed)

| constant | from | what | evidence |
|---|---|---|---|
| `GAME_STATE_FROM_UTC` | 10-13 18:10 | B1: side centre x exp(beta x expected goal difference), `config/sofa_game_state.json`; betas refitted on the live centre, installed 10-13 20:57Z (df5323ea): corners_for 0.129 -> 0.0986, shots_for 0.0974 -> 0.0506, cards_points_for -0.0845 -> -0.0664, fouls_for kept (refit +0.000031 worse); marker `game_state_rule` | `docs/sofa/evidence/game_state_2026-10-13.md` |
| `FOOTBALL_RATED_SCOPE_FROM_UTC` | 10-13 18:10 | B2: rating also on `football_rating.RATED_SCOPE_MARKETS` = cards_points_for, corners_1h/2h_for, offsides_total; corners totals unrated (corners_total worse +0.0009 [+0.0003, +0.0015]); `rated_scope_rule` | `docs/sofa/evidence/unrated_markets_2026-10-13.md` |
| `FOOTBALL_VENUE_PRIOR_FROM_UTC` | 10-13 18:10 | B2: league home / away multiplier on a sample-only corners_1h/2h_for centre; `venue_prior_rule` | same |
| `FOOTBALL_RATING_WEIGHT_FROM_UTC` | 10-13 18:10 | B14: rating weight per market from `config/sofa_rating_weight.json`, else `W_FOOTBALL_RATING`; `rating_weight_rule` | `docs/sofa/evidence/rating_weight_2026-10-13.md` |
| `SEASON_PHASE_FROM_UTC` | 10-13 18:10 | C1: goals centre x exp(c[market][phase]), `config/sofa_season_phase.json`; `season_phase_rule` | `docs/sofa/evidence/season_phase_2026-10-13.md` |
| `TENNIS_SET_RATING_PRICES_FROM_UTC` | 10-13 18:10 | B5: per-set games and sets_total from the rating's neighbours; `tennis_set_rule` | `docs/sofa/evidence/tennis_set_markets_2026-10-13.md` |
| `CS2_TEAM_ROUNDS_RACE_FROM_UTC` | 10-13 18:10 | B10: a team's rounds on a map from the round race (`cs2_engine.team_rounds_from_race`), live, at CS2_SETTLE and in the replay; walk-forward log-loss -0.0213 [-0.0237, -0.0188]; CS2 curve refitted on it staged 10-13, promoted 10-14 (bc69b56e). Moved by the operator from 10-14 00:00Z | - |
| `CS2_COUNT_EXPOSURE_FROM_UTC` | 10-13 18:10 | B12: kills / deaths / assists / team kills from the round race's (W, L) x per-round rates (`cs2_engine.ExposureBook`); log-loss -0.0135 / -0.0258 / -0.0099 / -0.0380, every interval below zero; headshots measured worse (+0.188), stay on the sample (outside `EXPOSURE_FAMILIES`) - the +0.188 was 239 impossible rows; headshots join with `CS2_PLAYER_SHARE_FROM_UTC` 10-21; line evidence of these families fitted on the old p, no check on Superbet lines 10-05..10-12 | `docs/sofa/evidence/cs2_kills_exposure_2026-10-13.md`, `docs/sofa/history/RAPORT_B11_B12_2026-10-13.md` |

Refit 10-13: `docs/sofa/history/RAPORT_REFIT_2026-10-13.md`; superseded by the
10-14 refit.

### Switches of 2026-10-14 00:00Z (before 10-14's build; operator 10-13, all markets on; `docs/sofa/history/PLAN_NOC_2026-10-13.md`)

| constant | what | evidence |
|---|---|---|
| `LEAGUE_RATE_RULE_FROM_UTC` | A2 (operator O1, correctness rule): a hockey / basketball / volleyball friendly / pre-season (`comparability.is_friendly_event`) is `FRIENDLY_FIXTURE`; a competition below `MIN_LEAGUE_MATCHES` (30) has no model p (`NO_LEAGUE_RATE`), never the all-league mean (NBA Preseason read 82.8 points a side); no fallback to the home league; line-evidence replay (`settled_shadow_rows`) applies the day's rule; measurement too small (17 would-print lines / 16 games) | `scripts/sofa/measure_league_rate_rule.py` (`T-A2-league-rate-refusals`) |
| `BUCKET_DESIGN_EFFECT_FROM_UTC` | A4: a key without a curve divides its Wilson bound by its p bucket's own `deff` (1 where every game gives one line; an older file reads the sport's); walk-forward log-loss -0.0351 [-0.0409, -0.0292] | `docs/sofa/evidence/bucket_design_effect_2026-10-13.md` (`T-A4-bucket-deff`) |
| `READ_BY_VALUE_FROM_UTC` | the 30 read matches are those of best value: best unlocked leg's confidence x odds, football / tennis confidence capped at 1/odds + `price_gap.GAP` (`confidence.read_value`, `read_order: "value"`) | - |
| `TENNIS_MATCH_WINNER_FROM_UTC` | D2: "Zwycięzca" as one two-sided rung `match_won_for`, priced from the as-of rating alone, own curve only (`bet.sofa.tennis_winner`); skill -0.1263 [-0.1303, -0.1228] log-loss vs class base rate; calibration threshold not met, every miss cautious; >= 0.70 printed 0.802 vs realised 0.828 holdout | `docs/sofa/evidence/tennis_match_winner_2026-10-13.md` |
| `MAPPABLE_FAMILIES_FROM_UTC` | OFFER reads the MAPPABLE families of `bet.sofa.market_coverage` ("<club> strzeli gola" and halves as goals_*_for 0.5, "Zostanie rozegrany N. set" as sets_total N-0.5, half BTTS, both-over saves, half corner / set games handicaps - `market_mapper.classify_mappable_family`); a yes/no answer never adds a second rung where the ladder quotes one; E2E on 10-13 samples clean on / off, the bridge leg untested (Sofascore 403) | `docs/sofa/evidence/mappable_e2e_2026-10-14.md` |
| `MEN_FRIENDLY_SAMPLE_WINDOW_FROM_UTC`, `MEN_FRIENDLY_BASELINE_FROM_UTC` | `bet.sofa.men_friendly`: an 851 fixture's pool also admits the sides' 851 matches; goals_total / goals_for read variant C (every pool match since the oldest of the newest ten 851 matches); SHEET goals prior = as-of mean of 851 matches (2.54 over 2,365; goals_for half; >= 30 matches; note `PRIOR_MEN_FRIENDLY`, no row marker - mid-day re-run SHEET by hand); C-D with as-of prior goals_total -0.0071 [-0.0127, -0.0015], goals_for -0.0140 [-0.0196, -0.0086]; women's 852 unchanged. Curves fitted without 851 (`fit_meta.friendly_exclusion_sql`): an 851 fixture reads competitive curves as an approximation | `docs/sofa/evidence/national_friendly_samples_2026-10-13.md` |
| `PLAYER_TEAM_FROM_SIDE_FROM_UTC` | hockey / basketball player props: a past game's squad is the lineup side the team held in that game (`player_model.appearances_from_lineups(..., side)`, `event_side`), by SHADOW's day key and the computing clock; before it the entry's `teamId` (Carlson model_n 5 of 85, McTavish 6 of 88 on 10-13); SHADOW, SHADOW_SETTLE and `measure_player_props.py` follow the day's rule; `fit_player_model.py --player-team-from-side`; rows `player_team_rule`; off = byte-identical | `docs/sofa/evidence/sport_player_props_2026-10-13.md` |
| `MARKET_POSITIONED_LINES_FROM_UTC` | A7: basketball curve fitted on lines placed where the Sofascore market stood (`data/a7_odds/basketball.jsonl`), staged `config/sofa_sport_confidence_calibration.next.json` (`effective_from` 10-14, bc69b56e); log-loss -0.0622 [-0.0702, -0.0546] on 41,414 Superbet lines / 651 games 10-05..10-12; at the market's line model p up to 0.70 realises 0.47-0.53, so totals / handicaps / team totals (old curve ~0.77, realised 0.618) stop printing (dry run 0 legs) | `docs/sofa/evidence/market_positioned_lines_2026-10-13.md`, `docs/sofa/evidence/basketball_refit_2026-10-13.md` |

Refit of 2026-10-14 (football / tennis) installed 05:31Z: section (c).

| constant | from | what | evidence |
|---|---|---|---|
| `SAMPLE_OPPONENT_CORRECTION_FROM_UTC` | 10-14 05:45 | B15 with A5 (`bet.sofa.opponent_correction`): a football side's sample rescaled to a neutral opponent (x / def(opponent)) and to today's league domain before SHEET's centre (goals and players excluded); CONFIDENCE's shape gates / MODEL_ABOVE_OWN_SAMPLE read the corrected values (`corrected_sample`, `opponent_rule`); calibrated log-loss better on 12 of 18 corners / shots / fouls markets with interval below zero, none worse (shots_for -1.96e-3 [-2.38, -1.56], cross-league pairs 3-4x that). SAMPLES writes `opponent_id` only from 10-13 evening, so B15 acts from 10-14's SAMPLES on | `docs/sofa/evidence/sample_opponent_correction_2026-10-13.md` |

### Identity plan K1-K8, 2026-10-14 11:30Z (10-14 mixed)

| constant | what |
|---|---|
| `ENTITY_MAP_FROM_UTC` | K1 / K4 (`bet.sofa.entity_map`): SPORT_IDENTITY teaches `sofa_entity` once per event (`sofa_entity_taught`); name-confirmed side (`entity_map.NAME_METHODS`, score > 82) = `verified`, `source = identity_names`, `evidence_event_id`; opponent-rule only = candidate (`sofa_entity_candidate`); a held name offered another id is queued (`sofa_entity_conflict`), never overwritten - `SofaCache.save_entity` (`src/bet/sofa/cache.py`; RESOLVE, SHADOW_SETTLE) follows the same rule; tournaments to `sofa_tournament_map` (football / tennis from RESOLVE, key `id:<superbet tournament id>`; read by nothing yet). Learned rows read by `TeamResolver`, `player_model.resolve_team` (`entity_map_rule`) and `SofaCache.get_entity` from the switch; CS2 reads learned rows only (backfill_cs2's "Ninjas in Pyjamas" = NIP Impact 448738 queued). Manual decisions `config/sofa_entity_aliases.json` applied by every SPORT_IDENTITY run (`entity_map.sync_manual`); queue `report_entity_queue.py` (10-14: 55 candidates; conflicts decided NIP = 366560, Golden Horde = 1272785). Backfill `backfill_entity_map.py` 10-14 09:39Z: 477 new names, 0 contradictions, 2 CS2 conflicts, 71 candidates (backup `data/backup_entity_map_20261014T093901Z/`). Direct gain: 32 not-identified events in 10 days. `docs/sofa/history/RAPORT_K1_MAPA_ENCJI_2026-10-14.md` |
| `DAY_ANCHOR_FROM_UTC` | K2 (hockey / basketball / volleyball; not CS2, not tennis): with no listed game on both names, the anchor team's only game within the hour (sport, gender, not postponed) is the event (`match_method: "DAY_ANCHOR"`); two such = AMBIGUOUS; the other side's own id missing = RESOLVED_ID_DISAGREES; opponent's name only a candidate. Backtest (`measure_day_anchor.py`): 1,578 / 1,578 right, 79 settle finds agreed, 0 contradicted; live gain NO_MATCH_IN_LISTING events (12 in 10 days; replay 10-13/14: 8); window 1 h. Open: BC Barcelos (K) - Francisco Franco (K) is Sofascore's BC Barcelos - CAB Madeira. `docs/sofa/history/RAPORT_K2_DAY_ANCHOR_2026-10-14.md` |
| `TOURNAMENT_DAY_FROM_UTC` | K3: an event neither side of which has an id matched by both names inside its tournament's day (`bet.sofa.day_listing`, `unique-tournament/<ut>/scheduled-events/<d>`, cached in `sofa_day_listing`; weaker side >= 60, lead >= 20); 95 tournament-days: 284 / 284 right with ids hidden, 24 of 42 targets, 15 settle-confirmed, 0 contradicted |
| `NOT_ON_SOFASCORE_FROM_UTC` | K5: a `NO_GAME_WITHIN_1H` from a cached page (6 h TTL) within 3 h of start is asked once fresh; only a fresh page of an id-resolved team with no game within 12 h is `reason: "NOT_ON_SOFASCORE"` (still NOT_IDENTIFIED, still re-asked, `absence_evidence`); a game 1-12 h away keeps NO_GAME_WITHIN_1H with `nearest_game_h`. BRIDGE_ABORTED = refusal periods (10-09 504 tab, 10-13/14 night 403), re-asked every 30 min, no code change (K6). `docs/sofa/history/RAPORT_K3_K7_TOZSAMOSC_2026-10-14.md` |
| `PLAYER_NAME_SURNAME_FROM_UTC` | K7: whole surname + first-name prefix >= 3 letters (`players.match_player_by_surname`), one candidate on one side; 10-12..10-14: 1,827 / 1,827 picked the same person (a shared initial only: 6 wrong), 22 new players; `match_rule: "surname"`, note `PLAYER_NAME_SURNAME`; SETTLE grades `matched_name` like a token match |
| `FOOTBALL_DAY_ANCHOR_FROM_UTC` | K8 (operator "Tylko 1. wlacz"): RESOLVE takes a verified side's only football game within 1 h of Superbet's start, in Superbet's order (F25), board's gender, not postponed, the opponent's verified id (if any) in it (`resolve.football_day_anchor_event`); 3,458 / 3,459 bridged fixtures 10-05..10-14 with the opponent hidden, ~11 more fixtures a day; the one miss (Hapoel / Maccabi Petah Tikva U19 10-11) accepted. Tennis never (replaced opponents) |

### New markets 10-14 .. 10-16

| constant | from | what | evidence |
|---|---|---|---|
| `FOOTBALL_RESULT_MARKETS_FROM_UTC` | 10-14 14:20 (operator "WŁĄCZ OD TERAZ", 10-14 mixed) | D1 double chance: "Podwójna szansa" as `double_chance`, the left-out "Mecz" outcome its UNDER; NB goals on pure rating centres, r 7.586 in `config/sofa_football_result.json` (unfitted), OVER only, `result_rule`; 90-minute score (`bet.sofa.football_result`) | `docs/sofa/evidence/football_result_phase_2026-10-13.md` |
| `SHOT_DETAIL_MARKETS_FROM_UTC` | 10-14 14:20 | footballer shots outside the box / headed / left / right foot, all and on target: SAMPLES / SETTLE count from `/shotmap` only where it gives the player his lineups `totalShots`; SHEET `shot_detail.forecast` from `config/sofa_shot_detail.json` (absent: `NO_SHOT_DETAIL_FIT`; fit `data/refit_shot_detail_2026-10-14/`); `shot_detail_rule`; left / right foot curves installed 10-15, other six keys failed the gate | `docs/sofa/evidence/shot_detail_2026-10-14.md`, `docs/sofa/history/RAPORT_LUKI_RYNKOW_2026-10-14.md` |
| `SPORT_DERIVED_MARKETS_FROM_UTC` | 10-14 14:50 (operator "1. 2. tak") | hockey / basketball double chance (regulation) and volleyball team sets / sets count from the score model (`shadow.DERIVED_MARKETS`); log-loss vs base better on every 1X / X2 and volleyball key, none on "12" | `docs/sofa/evidence/sport_derived_2026-10-14.md` |
| `FOOTBALL_INCIDENT_MARKETS_FROM_UTC` | 10-14 14:50 | `bet.sofa.football_incidents`: "1. gol" one-sided `first_goal` (NB goals, pure rating); `red_cards_total` / `penalties_total` O/U 0.5 / 1.5 from the competition's as-of full-feed rate; graded from regular-time incidents; at p >= 0.70 walk-forward 06-09..10-14 first goal +1.0 pp n 1,376, reds +0.7 n 10,152, penalties +1.0 n 9,518; minute bands never reach 0.70, not read | `docs/sofa/evidence/football_incidents_tennis_sets_2026-10-14.md` |
| `TENNIS_SET_MARKETS_FROM_UTC` | 10-14 14:50 | `bet.sofa.tennis_sets`: `set1_won_for` / `set2_won_for`, one-sided `set_score`, from the rating's neighbours; set 1 +1.0 pp n 12,174, set 2 +0.4 n 12,502, exact sets +1.5 n 4,107 | same |
| `FOOTBALL_RESULT_1X2_DNB_FROM_UTC` | 10-15 00:00 | "Mecz" 1 / 2 as `result_1x2`, "Zakład bez remisu" as one `draw_no_bet` rung (OVER home, UNDER away, draw = refund `DNB_DRAW_REFUND`); early-phase men's leg reads class `season_early` (`bet.sofa.football_1x2_dnb`); DNB keys passed the one-sided gate and are installed, every 1X2 key failed (no curve, NO_LINE_EVIDENCE) | `docs/sofa/evidence/football_1x2_dnb_phase_2026-10-15.md` |
| `CS2_SERIES_ROUNDS_FROM_UTC` | 10-15 00:00 | CS2 rounds_total / rounds_handicap / team_rounds over a series (`cs2_engine.series_rounds_side_p`: maps won from the mixed series distribution, rounds per map from the race); curves installed 10-15 00:17Z despite the warning (three keys pass on the history ladder; at Superbet's lines 21 sides / 19 series realised 0.33 at 0.74); round parity unpriced | `docs/sofa/evidence/cs2_series_rounds_2026-10-15.md` (`T-CS2-SERIES-ROUNDS-superbet`) |
| `BASKETBALL_DC_PAIR_FROM_UTC` | 10-16 00:00 (correctness fix) | Superbet quotes basketball DC as 1X / X2 only and `shadow.parse_event` took a group only whole (`cs2.DOUBLE_CHANCE_SET`), so it was never read; now a non-whole basketball group is read as two-way pairs against the regulation 1X2 outcome left out (same scope), fair p and margin of that partition, ids `dc_id x 100 - 1/2/3`, complement a price only (`partner_odds`); `dc_pair_rule`; hockey, volleyball, whole groups unchanged | `tests/sofa/test_basketball_dc_pair.py` |
| `FOOTBALL_CUP_STRENGTH_FROM_UTC` | 10-16 00:00 | `RatingBook.cup_delta` per (domestic competition, metric), learnt from cross-league matches of the nine cups in `config/sofa_cup_strength.json` (UCL / UEL / UECL, AFC Elite / Two, Libertadores, Sudamericana, CAF, CONCACAF), read on top of the domains' sigma (`RatingBook.cup_extra`, `bet.sofa.cup_strength`); steps goals_for 0.05 (1X2 log-loss -0.0285 [-0.0381, -0.0188], 2,194 matches), goals_1h_for 0.05, goals_2h_for 0.02, shots_for 0.02 (1,748 backfilled cup stats, both cuts below zero); corners, SOT, fouls, cards, offsides, halves of corners / shots no step; non-cup 302,635 moved matches goals -0.00003 [-0.00006, -0.000003] (`--spill`); before: 3,740 cross-league cup matches from 2024-07 under-rated the stronger league's side by +5.2 pp P(win) [+3.6, +7.0]; `cup_strength_rule`; the file is an operator list outside `config_sha`; replay `--cup-strength` | `docs/sofa/history/RAPORT_SILA_PUCHAROW_2026-10-16.md` (`measure_cross_league_cups.py --in-book`, TRAIN 2024-07..2025-06, TEST from 2025-07 and from 2026-01) |
| `SAMPLE_CUP_STRENGTH_FROM_UTC` | 10-16 04:10 | B15's gaps read the cup correction with the past match's and the fixture's competition (`SampleCorrector(cup_aware=True)`, `sample_cup_rule`, replay `--sample-cup-strength`); shots_for -0.00006 [-0.00012, -0.000003], -0.00044 on rows with a cup, shots_total zero; 35 cup fixtures on 10-15 | `docs/sofa/evidence/tennis_replay_sample_scope_2026-10-16.md` (refit 10-16b) |
| `FOOTBALL_SCORE_MARKETS_FROM_UTC` | 10-16 07:46 (operator "Włącz od teraz", 10-16 mixed) | `bet.sofa.football_score_markets`: `result_or_over` / `result_or_under` (subject 1 / X / 2), `btts_or_over`, `result_or_btts`, `result_or_clean_sheet`, `result_handicap` (+1.5 / +2.5 / +3.5; +0.5 is the DC; never a `handicap_` prefix - `is_derived` would kill it), `dc_and_over` / `dc_and_under` (12 & over / 1X & under); duplicates merged at the lower price; SHEET prices the OVER from the DC's NB grid (`score_market_rule`, `result_phase`); graded on the 90-minute score at 0.5, never at the goals line; curves per slice `<market>@<subject>@<line>|OVER` (`confidence.curve_market`, also `fit_line_evidence.py`; no pool read); OVER-only rungs print as one-sided singles (slice n >= 300); until own lines settle, line evidence uses football's pooled offset and price band (`cap:*@...`; 1.30-1.60 cell realised ~0.69 at p 0.83, so most legs above 1.30 do not print); PDF / HTML in Superbet's words (`football_score_markets.display_market`) | `docs/sofa/evidence/football_score_markets_2026-10-16.md`, `docs/sofa/history/RAPORT_NOWE_RYNKI_2026-10-16.md` |
| `TENNIS_SET_COMPLEMENTS_FROM_UTC` | 10-16 07:46 | `set_score_not` "<player> 0:2" OVER = he wins a set (one rung for "wygra seta" Tak, "Handicap setowy" (1.5), "liczba setów" over 0.5, the other's "wygra bez straty seta" Nie); 1 - the 0:2 share of the neighbours; `set_complement_rule` | same |

Score markets E2E (10-14 / 10-15 / 10-16, off vs on): SHEET off = on minus the
new rows byte for byte, 0 legs lost or changed, +484 / +536 / +1,068 legs;
settled 10-14..15: 1,018 legs / 233 matches +1.2 pp [-1.8, +4.2] over
confidence, ROI -2.4% [-6.1, +1.2]; `set_score_not` 27 legs -9.8 pp [-27, +7]
(`T-SCORE-MARKETS-superbet`). Rungs of one match are not grouped as a ladder.
A rebuild from 07:46Z re-reads OFFER / re-runs SHEET itself when the rungs /
rows are missing (`rebuild_plan`). Every OFFER reader builds its fetcher from
`offer.day_flags(date)`.

### Player sample gates, stretches, per-line curves (10-17 .. 10-18)

| constant | from | what | evidence |
|---|---|---|---|
| `PLAYER_SAMPLE_GATES_FROM_UTC` | 10-17 00:00 (operator 10-16) | a row on `confidence.PLAYER_SHAPE_GATE_MARKETS` (shots, SOT, fouls, tackles, assists, offsides; not /shotmap shot-detail, not interceptions) needs only `PLAYER_MIN_SAMPLE` (5) values; a leg a shape gate would have refused carries `player_sample_rule` and never joins a builder | `docs/sofa/evidence/player_sample_gates_2026-10-16.md`, `docs/sofa/evidence/player_line_evidence_2026-10-16.md`, `docs/sofa/history/RAPORT_BRAMKI_ZAWODNIKOW_2026-10-16.md` (`T-PLAYER-SAMPLE-GATES`) |
| `FOOTBALL_GOALS_STRETCH_FROM_UTC` | 10-17 13:37 | `goals_stretch_v2`: goals centre x exp(beta s) / exp(g1 abs(s) + g2 s^2); one set per season phase allowed (goals_for early / mid / late / final 0.018 .. 0.064, halves early only; a missing phase or no phase reads the single set); `config/sofa_goals_stretch.json`, `fit_goals_stretch.py --per-phase goals_for:early,mid,late,final goals_1h_for:early goals_2h_for:early`; replay `--goals-stretch` | `docs/sofa/evidence/goals_stretch_2026-10-17.md` |
| `FOOTBALL_COUNT_STRETCH_FROM_UTC` | 10-17 13:37 | `count_stretch_v1`: the 16 markets of `count_stretch.COUNT_STRETCH_MARKETS` outside GAME_STATE (half corners, shots by half, SOT, offsides, saves, throw-ins, goal kicks, SOT / saves / throw-ins totals), after GAME_STATE and venue prior; walk-forward NB and both after-curve checks below zero on all 16; raw NB of a fixed fit not significant for shots_1h_for (pre-2026) and offsides_for (2026-H1); offsides_1h_for left out; `config/sofa_count_stretch.json`, `fit_count_stretch.py` (from 2026-01-01); `--count-stretch` | `docs/sofa/evidence/count_stretch_2026-10-17.md` |
| `FOOTBALL_PLAYER_STRETCH_FROM_UTC` | 10-17 13:37 | `player_stretch_v1`: player_shots_for / player_shots_on_target_for centre x exp(beta s) of his own side, 0.126 / 0.117; `config/sofa_player_stretch.json`, `fit_player_stretch.py`; `--player-stretch` | `docs/sofa/evidence/player_stretch_2026-10-17.md` |
| `LINE_CURVES_FROM_UTC` | 10-18 12:48 (planned 10-19 00:00Z, moved by the operator; 10-18 mixed) | per-line football curves for the 33 keys of `config/sofa_line_curves.json` (`bet.sofa.line_curves`; source `line:<market>|<DIR>@<line>`; < 400 rows reads pooled) | `docs/sofa/evidence/line_curves_2026-10-18.md` (`T-LINE-CURVES`) |

Supremacy stretches (arithmetic `bet.sofa.supremacy_stretch`; s = the rating's
expected goal difference clamped at `MAX_SUPREMACY`, a total the home side's;
each fit on the cup-strength book): switched on (operator "włączaj już teraz")
BEFORE their refitted curves; measured for that combination first (stretched p
through the curve fitted on unstretched p, test 2026): goals_for, goals totals,
all 16 count markets and both player markets better, every CI below zero
except shots_on_target_total pre-2026 (neutral); goals_1h_for / goals_2h_for
better in log-loss but their favourite OVER legs at >= 0.70 overstated with the
old curve (-5.7 / -3.0 pp) - held back until the refit was installed (restored
to `config/sofa_goals_stretch.json` at the install, SHEET re-run by hand). To
watch on live legs: goal_kicks_for UNDER s -1..-0.5, throw_ins_total UNDER
abs(s) >= 1.5 (thin cells), shots_on_target_for / shots_1h_for ~0.5 pp lower at
>= 0.70. MODEL_ABOVE_OWN_SAMPLE removes more legs (E2E 10-17: +27) - the
stretch moves the model away from the opponent-blind sample by design.
Report `docs/sofa/history/RAPORT_DZIEN_2026-10-17.md`.

Player sample gates measurement: a footballer's sample is his starts in the
team's last 10 matches (5-10 values), so THIN_SAMPLE_FOR_BUILDER (< 10)
admitted only 10/10 starters and LINE_BEYOND_SAMPLE refused OVER 0.5 for one
who never blanked (10-15: of 57 player legs clearing curve, line evidence and x
at the sheet's price, 54 refused - 45 on the six markets; 5 printed, 2 clearing
x only at a fresh price). History OVER: refused groups realise on their curve
(+0.5..+1.5 pp; together ~0.4 pp below passing; LINE_BEYOND -0.9 [-1.8,
+0.1], 5 starts -1.9 [-2.9, -0.8] vs PASS). Superbet lines 10-12..10-15 with
line evidence: 55 legs / 37 matches -5.9 pp [-15.9, +4.5], ROI -11.7% [-23.8,
+1.2] (no edge at the price). E2E 10-15 (clock 12:59Z): +40 player singles (22
LINE_BEYOND, 18 THIN), 0 legs lost or changed, builders identical. ~14 player
singles a day expected.

Per-line curves measurement (`scripts/sofa/measure_line_curves.py`, train
2025-07..2026-03, test 2026-04..10-12): replay goals_for UNDER 1.5 -2.4 pp on
305k rows, far UNDER lines +1..+3 pp; keys chosen where the per-line curve
beat the pooled one at Superbet's quoted lines with interval below zero; 6 keys
measured worse and stay pooled (shots totals, goal_kicks_total OVER);
log-loss at p >= 0.70 -6.4e-4 [-7.0, -5.8], mean abs line gap 1.21 -> 0.92 pp;
live offered rows 10-09..10-17 gap -1.09 -> -0.57 pp, ROI unchanged (-4.54% /
-4.53%); E2E 10-18 +57 / -300 legs (player singles 52 -> 41: shots OVER 1.5,
which the pooled curve overstated -1.5 pp; a one-sided single reads `market:` or
`line:`, `confidence.OWN_CURVE_SOURCES`); settled 10-15..10-17 -599.0 ->
-582.9 u. (dropped 167 legs -9.2%). A calibration fix, not an edge. The line
evidence's base follows the --before day's latest build
(`line_curves.day_reads_per_line`), refitted for --before 2026-10-18 at the
switch: football pooled printable gap -0.68 -> -0.45 pp, other sports
unchanged. Installed 10-18 12:04Z by `install_line_curves.py` (inert before the
switch: 320,733 / 320,733 rows read alike without a line); backup
`config/backup_2026-10-18_line_curves/`. A class leg (women, season_early)
unchanged.

### CS2 player share (2026-10-21 00:00Z; operator's go 2026-10-20)

| constant | from | what | evidence |
|---|---|---|---|
| `CS2_PLAYER_SHARE_FROM_UTC` | 10-21 00:00 | the exposure's player share over `cs2_engine.SHARE_WINDOW` 40 maps shrunk with `K_SHARE_BY_STAT` (kills 8, deaths 8, assists 16, headshots 4; walk-forward on history), headshots join the exposure (`ExposureBook.families`); live, at CS2_SETTLE (`model_p`); log-loss at the emulated Superbet line 2026-04..09-27 (100,525 player-maps, 4,477 matches): kills -0.00305 [-0.00357, -0.00253], deaths -0.00111, assists -0.00402, headshots -0.01018; kills slope 0.71 -> 0.87. Calibration fix, not an edge: Superbet 09-28..10-19 blend over the devigged price includes zero in every family (kills +0.00037 [-0.0020, +0.0030]) | `docs/sofa/history/POMIAR_CS2_PLAYER_KILLS_2026-10-20.md` |

Live from 2026-10-20 (correctness, no switch): `cs2_engine.load_history` drops
a row's headshots when headshots > kills (239 rows of 2025-10-27, up to 2030;
they made B12's headshots +0.188). The CS2 player families never had a
history curve: `cs2_walk_forward_rows` carries no player rows, so their
`not_calibrated` reason is `NO_HISTORY_ROWS` from the next fit (the installed
files still say `NO_FIT_BUCKET_WITH_N>=200`); their confidence is line evidence
only. Measured on Superbet's lines 09-28..10-19 (127 series, 9,414 lines):
today's model AUC kills 0.484 vs price 0.516, adds nothing over the price; do
not build player curves on synthetic lines (at our own mean line kills is
calibrated, at Superbet-placed lines overconfident). Line evidence of the
player keys mixes the old and the new p until enough days of the new one.

### CS2 price_gap flag (2026-10-21 00:00Z; operator's go 2026-10-20)

| constant | from | what | evidence |
|---|---|---|---|
| `CS2_PRICE_GAP_FROM_UTC` | 10-21 00:00 | `price_gap` (`CONFIDENCE_ABOVE_PRICE`, `GAP` 0.03) on CS2 legs too (`price_gap.LATER_SPORTS`, `epochs.price_gap_sports`); annotation only, but a flagged CS2 leg is capped at 1/odds + `GAP` in `confidence.read_value` (read order). Measured on settled Superbet CS2 lines 09-28..10-19 whose `model_p` the installed curve puts on the coupon's floor and x, line evidence not applied: flagged 238 lines / 77 series -18.6 pp [-27.1, -10.1] vs confidence, -2.1 pp vs de-margined price; rest 234 +2.2 pp; ROI -8.8% [-23.1, +4.9] vs -0.6%. Series families alone (38 flagged) and "model favourite, market underdog" (55) show nothing. `T-CS2-PRICE-GAP-flag` registered | `docs/sofa/history/POMIAR_CS2_PRICE_GAP_2026-10-20.md` |

### Football statistics night (2026-10-21 00:00Z; standing go of 10-15; ledger group "od 10-21")

Operator 2026-10-20 evening: every Superbet football statistic, cards / fouls /
players / shots in every combination. Report
`docs/sofa/history/RAPORT_NOC_STATYSTYKI_2026-10-21.md`. Log-loss x1e-4 unless
marked, new minus old.

| constant | what | evidence |
|---|---|---|
| `FOOTBALL_REFEREE_FROM_UTC` | `referee_v1` (`bet.sofa.referees`, `config/sofa_referee_effect.json`, fit 2026-01-01..10-16): cards_points_* and fouls_* (incl. halves) centre x the referee's as-of shrunk ratio ** beta (cards 0.59, K 10; fouls 0.70-0.72), after GAME_STATE / count stretch; referee from `sofa_event_referee` (`backfill_referees.py`: 83,872 matches, 2,540 referees, 20-10) or the cached `/event`; none named = x1 (`referee_read.status` NO_REFEREE / NO_REFEREE_RECORD). Test 2026: cards_points_total -28.6 [-35.8, -22.0], cards_points_for -16.1, fouls_total -54.3, fouls_for -27.6, fouls halves -21..-67, every CI below zero, again on the 2026-H1 -> 07.. split; after the curve fouls_1h_total (<2026) / fouls_2h_total (H1) touch zero; calibration at >= 0.70 unchanged (the gain is discrimination). Live: referee named ~48 h before kick-off (0% beyond); 85.9% of cards / fouls events labelled. Not replayable yet (no labels in the replay): the next refit cannot carry it | `docs/sofa/evidence/referee_effect_2026-10-21.md` |
| `FOOTBALL_CLOSENESS_STRETCH_FROM_UTC` | `closeness_stretch_v1` (`bet.sofa.closeness_stretch`, `config/sofa_closeness_stretch.json`): x exp(g1 abs(s) + g2 s^2) after GAME_STATE / count stretch / referee on cards_points_for / _total (x0.84 at abs(s) 2) and shots_total / shots_1h_total (x1.03); walk-forward NB cards_points_total -34.6 [-43.0, -24.7], shots_total -11.2 [-15.5, -6.8]; after the curve significant on one split each, never worse; on top of the referee cards_points_total -33.4 [-47.8, -17.6], together <= 0.2 pp overclaim at >= 0.70. Declined: fouls (H1 fit +33.8 worse), corners, side counts, dispersion(abs(s)) (worse at >= 0.70 through the curves). Replay `--closeness-stretch` | `docs/sofa/evidence/football_closeness_stretch_2026-10-21.md` |
| `FOOTBALL_PLAYER_SHARE_FROM_UTC` | `player_share_v1` (`bet.sofa.player_share`, `config/sofa_player_share.json`): player_shots_for / _shots_on_target_for / _fouls_for centre = his shrunk share of his side's count over his starts (m 40 / 40 / 80, position prior) x the side's team centre today, SOT x shrunk accuracy (m_acc 40); a side without a team row keeps the old centre. Before: the centre was the raw mean of his starts (no prior); our p was right on level, 1/odds of the one-sided OVER ladders carries the margin (shots 0.5: hit 0.537, p 0.505, 1/odds 0.750). History test 2026-04..10-12: shots -235 / -197 / -124 / -76 at 0.5 / 1.5 / 2.5 / 3.5, SOT -228 / -154 / -66, all CIs below zero; Superbet settled lines 10-12..10-19: shots -178 [-240, -104], SOT -168, fouls -239 [-305, -170] (0.5 neutral). Curves fitted on the old p under-claim it by 2-6 pp at >= 0.70 - needs a refit. Fouls legs nearly stop printing (old: 57 legs hit 0.632 at ~0.73). Tackles declined (0.5 +51 worse). Not replayable yet | `docs/sofa/evidence/football_player_share_2026-10-21.md` |
| `FOOTBALL_PLAYER_COVERAGE_FROM_UTC` | SAMPLES: (a) a missing `onTargetScoringAttempt` proven zero by on + off target + blocked (213,047 / 213,047; woodwork is inside them); (b) a player with < 5 starts in the last 10 sampled from his newest <= 10 starts of the last 20 (`PLAYER_WIDE_SAMPLE_N`; history at >= 0.70 recovered rows -0.1 pp [-0.6, +0.5] vs base; vs 3-4 starts -339 [-387, -293]); (c) transliteration and inner-surname name rules (0 wrong of 23,666). SHEET +17-20% player rows, 0-2 legs a day. Replay `--player-coverage` | `docs/sofa/evidence/football_player_coverage_2026-10-21.md` |
| `FOOTBALL_PLAYER_PROPS_V2_FROM_UTC` | "Zawodnik - liczba fauli na zawodniku" as `player_fouls_drawn_for` (OVER only): `wasFouled` from /lineups, a missing key 0 only when the squad sum lies in [opponent fouls - 4, opponent fouls] (99.6%); NB on his starts (-211 [-221, -202] vs normal); curve `player_fouls_drawn_for|OVER` installed (holdout +1.79 pp [+0.32, +3.33], n 3,008). Declined: "otrzyma kartkę" (p never >= 0.70, max 0.536), "Którykolwiek z zawodników ..." (loses to a base rate in 8 of 9), player pairs | `docs/sofa/evidence/football_player_props_v2_2026-10-21.md` |
| `FOOTBALL_STAT_VARIANTS_FROM_UTC` | OFFER reads "Każda drużyna powyżej X rzutów z autu / wybić od bramki", "Każda z drużyn powyżej X odbiorów", "Strzały - Handicap", "1. / 2. połowa - liczba strzałów - handicap" (`market_mapper.classify_stat_variant`) as both_over_* / handicap_shots*; joint of the sides' samples, no curve: NO_LINE_EVIDENCE, one-sided, never a single. Declined (never 0.70 except copies of read rungs): corner parity / ranges, exact cards | `docs/sofa/evidence/football_stat_variants_2026-10-21.md` |
| `FOOTBALL_CARD_HALVES_FROM_UTC` | `bet.sofa.football_card_halves`: card points by half ("1. / 2. połowa - [<TEAM>] liczba kartek", most, handicap), side / half red cards and penalties, both teams red; a card counts in the half it was shown (komunikat 06/2022: shown at the break = 2nd half; a two-yellow dismissal split 1 + 2 is an assumption, 3.1% of matches); half centre = league as-of half share x the full-match centre (beats own half sample by 144 / 138); 20 curves installed, 18 kept (one-sided gate; every OVER of reds / pens, most_*, 2nd-half handicap, 1st-half side OVER failed). Graded 10-14..10-19: would-print 579 rows won 0.810 at 0.827 | `docs/sofa/evidence/football_card_halves_2026-10-21.md` |
| `FOOTBALL_CARD_HALVES_TERMS_FROM_UTC` | `card_halves_terms_v1` (audit 2026-10-21): half card centre = league half share x the side's live `cards_points_for` centre (rating, game state, referee, closeness; no row: rating x the same terms) - 1H side -53 [-65, -39], 2H side -87 [-105, -67], totals -26 / -52; side penalties / reds p = 1 - exp(-lambda_L exp(beta s)), s the side's expected goal difference: penalties_for -36.7 [-43.4, -30.6] (beta 0.276), penalties_1h_for -17.6, red_cards_for -6.7 (beta -0.172); red_cards_1h_for and the 1st-half totals unchanged. On the new p `cards_points_2h_for|UNDER` (-2.12 pp, n 1,261) and women's `handicap_cards_points_1h|OVER` (n 298) failed the gate and were removed 10-20 ~23:10Z (18 card-halves curves stay) | `docs/sofa/evidence/football_card_halves_terms_2026-10-21.md` |
| `DERIVED_CURVES_FROM_UTC`, `CARDS_CORRELATION_FROM_UTC`, `DERIVED_SHEET_MARGINS_FROM_UTC`, `DERIVED_SAMPLE_GATES_FROM_UTC` | operator 2026-10-21 ~04:50Z ("wszystkie rynki to wszystkie"): football joints (both_over / most / handicap of goals, cards, corners, SOT, goals halves) read their 10-17 history curves (a one-sided joint leg prints as a single: source `market:`, n >= 300), cards joints with side correlation +0.126, a joint side without a quoted ladder priced by `run_sheet.sample_centre`; `THIN_SAMPLE_FOR_BUILDER` on a joint reads each side's marginal sample (>= 10 values each; LINE_BEYOND / MODE_LOSES / MODEL_ABOVE_OWN_SAMPLE not applied), the leg carries `derived_side_samples` and never joins a builder. E2E 10-20: +49 legs (both_over_goals U 18, _1h U 12, corners O 10, SOT O 4...), 0 lost / changed, builders identical; with the per-line goals-halves curves and the joints' own line offsets (main code, 10-20 copy): 114 joint legs, every one named in Superbet's words. The joints' offsets are fitted against their curve from the switch on (`fit_line_evidence.reads_derived_curves`; until 7b41d17f the morning refresh never passed `--derived-curves`, so a joint got only the pooled -0.6 pp): both_over_goals U printable 0.836 realised 0.765 on 1,393 lines 10-05..10-19 (-7.1 pp [-9.3, -4.9]), corners O +0.2, goals_1h U -1.1. Measured 10-14: lines admitted realised below price (ROI -1.8% [-4.4, +0.7]) - accepted (operator accepts below price). Installed 2026-10-21 before the day was built (`fit_joint_curves.py`, one-sided gate, per line only - a men's leg reads its own line's curve, a failed line none): stage1 29 line curves (goals halves, saves) + 10 women; stage2 130 line curves (fouls and halves, shots and halves, offsides, throw-ins, goal kicks, tackles, corner halves; handicaps of these) + 12 women. Failed (overstate > 2 pp): both_over_shots U 10.5-14.5, _1h U 6.5, _2h U 6.5 / 7.5, handicap_shots_1h 2.5; never 0.70 on holdout: both_over offsides / throw-ins O, handicap_shots, most_ of every non-goal metric except most_shots@0. E2E 10-20 with stage2: +1 leg (handicap_corners_2h), 0 lost / changed - Superbet priced only the 'tak' side of fouls / shots / offsides 'każda z drużyn' that day | `docs/sofa/evidence/derived_curves_2026-10-14.md`, `docs/sofa/history/RAPORT_NOC_STATYSTYKI_2026-10-21.md` |

Not replayable in a refit yet: referee (labels absent from the replay), player
share (its measurement replays it; calibrate_from_cache does not). The curves of
the moved markets were fitted without them; the next refit must decide
(`prepare_refit.py install` warns for both, and refuses a replay without
`--closeness-stretch` / `--player-coverage` while those switches are on; the
gated card-halves / fouls-drawn / shot-detail curves win over a fit's own).
Morning routine (sofa-day 1a): `backfill_referees.py --days 14 --max-minutes 8` after D-1 is settled
(labels the referees of new matches; the fixture's referee comes from RESOLVE /
FIXTURE_CHECK's `/event`).

### RESOLVE reserve / youth retry and per-day misses (2026-10-21 09:20Z into the built day; operator "rob wszystko zeby zaczelo dzialac od dzisiaj"; ledger group "10-21 mieszany")

| constant | what | evidence |
|---|---|---|
| `SQUAD_SEARCH_RETRY_FROM_UTC` | `resolve.search_query` strips our "(r)", so "Atlas U21" was searched as "atlas" and Atlas FC U21 (1111909) never reached the candidates. On: a side below the senior squad whose marker-free search matched nothing and held no candidate of its level is searched again with Superbet's name (`resolve.squad_retry_queries`: bracketed markers dropped, a name marked only "(R)" + " Reserve") and only candidates of its own level are tried (`resolve.squad_level_candidate`; the senior club never again); opponent / kickoff / orientation gates unchanged. A miss recorded before the switch does not block such a name (`SofaCache.get_entity_miss(recorded_after=)`). SHADOW_SETTLE (`record_miss=False`) reads it at once (grades only the pinned id). Measured live 2026-10-21 on the 168 distinct squad sides of the 138 football board entries RESOLVE lost 10-07..10-21 (of 1,100 with a squad side): plain search held a candidate of the side's level for 71, the retry for 25 more; RESOLVE replayed on a slim DB copy, retry off vs on: +6 fixtures, all right by eye (Reserves / U21 competitions), 0 changed, 0 lost. Not this fix: "U19" sides with no U19 result (29, 23 Italian), MLS "2" sides, "B" in the middle ("Žalgiris B Vilnius") | `scripts/sofa/measure_squad_search.py`, `docs/sofa/history/RAPORT_RESOLVE_REZERWY_2026-10-21.md` |
| `ENTITY_MISS_PER_DAY_FROM_UTC` | an entity miss counts only when recorded on the fixture's kickoff day (UTC), not 7 days (`entity_miss_ttl_min`); the late RESOLVE pass also re-asks a miss older than `late_resolve.LATE_LISTING_TTL_MIN` (`SofaResolver.miss_fresh_min`). Measured 10-21 on the 127 football gaps of 10-13..10-20 with neither side known: 11 blocked by an older miss while Sofascore had the game; the late pass of 10-21 08:48Z could not re-ask Ravasio - Bouchelaghem / Sharma - Aggarwal (misses of 10-20 05:40Z). Cost: one search per unbridged name per day | `docs/sofa/history/RAPORT_RESOLVE_PUDLA_2026-10-21.md` |

### RESOLVE late pass (2026-10-21 08:48Z into the built day; operator "Włączaj od razu!"; ledger group "10-21 mieszany")

| constant | what | evidence |
|---|---|---|
| `LATE_RESOLVE_FROM_UTC` | a rebuild while the day is live (`rebuild_plan` step 0, after ensure_bridge, soft) re-asks RESOLVE for the board entries no fixture bridges whose board start is > 20 min ahead (`bet.sofa.late_resolve.candidates`; 00:00Z placeholders skipped) with `run_resolve._resolve_one`, listings read fresh (`LATE_LISTING_TTL_MIN` 30), entity misses honoured as in RESOLVE; an event the day already holds is never touched; a new open fixture is appended to 02 and only it goes through `run_offer` / `run_samples` / `run_sheet --event-ids` (merged, every other row kept, `late_resolve.merge_by_event`); `late_resolve.json` records passes and carries a half-done event on. Measured 2026-10-21 (read-only): 65 tennis entries never bridged 10-07..10-20 while their game later sat in a known player's listing, 39 with an id above every id their day's RESOLVE bridged (football 4); live replay 08:40Z: 2 of the day's open unbridged tennis entries resolve with today's code and no alias; a lost event ~1.2 printed legs (tennis), ~8.6 (football). Adds fixtures, changes no p | `docs/sofa/history/RAPORT_POZNY_RESOLVE_2026-10-21.md` |

### RESOLVE squad-level alias (2026-10-21 10:30Z, operator "Włączaj od razu!"; 10-21 mixed, ledger group "10-21 mieszany")

| constant | what | evidence |
|---|---|---|
| `FOOTBALL_SQUAD_LEVEL_ALIAS_FROM_UTC` | the last football fallback, after the exact match and the searched anchor (it never changes a fixture they bridge): the searched candidates' listings plus up to 3 search results of an alias level (`resolve.squad_alias_candidate`: same club by level-free name, gender, not simulated) are read for the ONE game within 60 min of Superbet's start whose sides are the board's by name with the level words removed (`resolve.level_free_name`; searched side `part_score` >= 90 `SQUAD_ALIAS_OWN_SCORE`, opponent > 82) and by ONE pair-consistent level shift (`resolve.squad_level_shift` / `squad_level_alias`: same non-senior level, U-bands one year apart, reserve <-> U19..U23 `SQUAD_ALIAS_RESERVE_AGES`; Sofascore's trailing "2" read as reserve by `resolve.football_squad_levels` only - `names.normalize_name` / `team_levels` / cache keys unchanged; never senior <-> anything; both non-senior board sides must share the shift, a senior board side must be senior on Sofascore), F25 order, board gender, not postponed; two such games refuse; vetoed when a team the opponent's own search names (or its verified entity) plays ANOTHER game within 60 min (`resolve.squad_alias_veto`, one search + <= 3 listings, only once a game is found). Fixture FUZZY, `match_rule` "SQUAD_LEVEL_ALIAS:<board>-><Sofascore>", never cached as verified; a miss recorded before the switch does not block. Backtest 10-05..10-20, 6,534 bridged fixtures, each side searched, candidates = true team + every alias namesake of the database's listings: real opponent 0 wrong (as is 1,698 right; board level shifted on both sides 3,429 right, 257 refused, 110 vetoed; one-sided 2,509 right; half-shifted 0 accepted); decoy opponent (another bridged side of the same tournament / day) 10 of 9,022 accepted - 3 fixtures, opponent a token subset of another club (Zurich / Grasshopper Club Zürich, Cavigal Nice / Nice, B36 / HB Tórshavn) - vs the ordinary name gate's 20 of 2,848 on the same decoys. F2 recall (10-21 live search replay): 18 of 23 (12 Primavera 2 U19->U20, 4 Central America / India reserve->U19/U20, 2 MLS Next Pro "2"); refused Pisa - Ascoli and Modena - Cremonese (one side's level differs - pair consistency; the measured loose variant gets both, 0 wrong too, not installed), Mechelen B (Sofascore names the side as the first team), Union SG B (no candidate), Leuven B - KRC Harelbeke (opponent 81.8). Not measured: live search ranking for the bridged set (search not cached); the alias candidates' listing cost on a full day | `scripts/sofa/measure_squad_level_alias.py`, `tests/sofa/test_resolve_squad_level_alias.py`, `docs/sofa/history/RAPORT_RESOLVE_POZIOM_2026-10-21.md` |
| `FOOTBALL_SQUAD_LEVEL_ALIAS_LOOSE_FROM_UTC` (2026-10-21 11:30Z, operator "Włącz!"; 10-21 mixed) | the alias without pair consistency: two non-senior board sides may each shift on their own (`squad_level_shift(..., loose=True)`; Pisa U19 - Ascoli U19 as Sofascore's Pisa U19 - Ascoli U20); never the senior squad. `--loose` on the same backtest: real opponent 0 wrong, the same 10 of 9,022 decoys; F2 recall 20 of 23 | `scripts/sofa/measure_squad_level_alias.py --loose`, `tests/sofa/test_resolve_squad_level_alias.py`, `docs/sofa/history/RAPORT_RESOLVE_POZIOM_2026-10-21.md` |

### RESOLVE short-name search (2026-10-21 11:00Z, operator "Włączaj od razu!"; 10-21 mixed, ledger group "10-21 mieszany")

| constant | what | evidence |
|---|---|---|
| `FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC` | RESOLVE's short-name search (`bet.sofa.short_name_search`, called by `run_resolve._resolve_one` after both sides failed - normal search, reserve retry, searched anchor): each side searched by its 2 longest words of >= 4 letters (resolve stopwords + club words out, a "...spor" word also without "spor"; `short_name_queries`), up to 5 fitting results per query, a result counting only when it holds the query as a whole word, has the side's gender / level / unmarked squad words and the query is not a word of the other side (`short_candidate_fits`); a game is accepted only when side A's candidates (verified entity alone, else normal search + short) hold its HOME team and side B's its AWAY team, within 60 min, gender, levels, squad words, not postponed, neither name contradicted (each name carrying a word of 4+ letters the other lacks: Cheltenham / Swindon Town, Real / Atletico Madrid B, `name_contradicts`), no candidate of the side's own name (`part_score` > 82) playing another game in the window (`named_elsewhere`), the ONE such game, at least one side through a short query (`short_name_pair_event`). FUZZY, `match_rule` "SHORT_NAME:<BOTH\|A\|B>", never cached as verified; a pair that found nothing is a miss for its day (`(short) <a> v <b>`). Backtest 10-05..10-20, 6,534 bridged fixtures, short results stood in by every listed team the rule admits: true pair 5,193 right / 0 wrong (531 none, 810 no short side); short only 3,339 / 0; true team of one or both sides hidden 0 accepted of 6,534 x 3; decoy opponent (another bridged side of the same tournament / day) 17 of 17,504 accepted (Dundee FC / Dundee United, HB / B36 Torshavn, Kuwait SC / Al Arabi Kuwait...); before the contradiction check and the veto 266 decoys, 21 hidden-team accepts (Bedford Town, Plymouth Parkway, Unia Swarzedz) and 1 true-pair wrong (Maccabi for Hapoel Petah Tikva U19). F3 live replay (22 gaps of 10-13..10-18, `_resolve_one` on a DB copy): 8 right, 0 wrong; Modica - Athletic Club Palermo refused only by its hindsight status "interrupted"; lost: 11 one-sided (by design), Avellino / Catanzaro U19 vs Sofascore U20 (F2), MEG & Centre (two Sofascore events of the game), Taipei Xiongzan / Taipei Bravo! (contradiction). Cost: 2.5 extra searches per lost pair (F3 mean), ~31 lost football pairs a day 10-05..10-20 (2-123), so ~80 searches a day + up to 5 listings a query (most cached) | `scripts/sofa/measure_short_name_search.py`, `tests/sofa/test_resolve_short_name.py`, `docs/sofa/history/RAPORT_RESOLVE_KROTKA_NAZWA_2026-10-21.md` |

### RESOLVE searched anchor (2026-10-21 10:00Z, operator "Włączaj od razu!"; 10-21 mixed, ledger group "10-21 mieszany")

| constant | what | evidence |
|---|---|---|
| `FOOTBALL_SEARCHED_ANCHOR_FROM_UTC` | K8's day anchor for a SEARCHED (unverified) football side, tried only when nothing matched by name: a fitting search candidate named as the side (`part_score` >= 90 `SEARCHED_ANCHOR_OWN_SCORE`, same squad level, same unmarked "2 / C" word) has the ONLY game within 60 min of Superbet's start (two games of two candidates refuse), Superbet's order (F25), board gender, not postponed, opponent's squad level (`resolve.searched_anchor_event`); the opponent agrees weakly (`resolve.searched_anchor_agreement`): VETO first - its own search (3 fitting results) or verified entity names ANOTHER team strongly (> 82) - then MUTUAL (one of them is the other side), NAME (`part_score` >= 65 `SEARCHED_ANCHOR_OPPONENT_SCORE`), SHARED_WORD (`shadow_opponent_agrees`, 15 min). Fixture `identity` FUZZY, `match_rule` "SEARCHED_ANCHOR:<how>"; never cached as verified; a miss recorded before the switch does not block. Backtest 10-05..10-20, 6,534 bridged fixtures, each side as the searched one with impostor candidates (every listed team named as the side): true opponent 0 wrong (8,674 right; anchor alone with the name hidden 5 wrong of 11,650, every one refused by the opponent check); decoy opponent (another bridged side of the same tournament / day) 16 of 29,109 accepted with the veto stand-in, 639 without it (16 of the 885 decoys no strong name vetoes = 1.8%); opponent >= 50 measured and rejected (3,237 decoys without veto; Hannoverscher / Karlsruher 62, Chertsey / Yate 64 were real wrong games); own name > 82 rejected (Worcester City for Gloucester City 82.8, Los Angeles FC for LA Galaxy 88.0). F1 (28 entries, live search replay 10-21): 20 identified, Sutton / Kelantan / Karvan / Odysseas refused; lost Gabala (normalize_name folds "Qəbələ" to "qbl"), Jonava - BFA (27), WKS, Pemba, UST, Videoton, Astra (vetoes / names), Levante (postponed). Not measured: the live search ranking on the bridged set (search is not cached) | `scripts/sofa/measure_searched_anchor.py`, `tests/sofa/test_resolve_searched_anchor.py`, `docs/sofa/history/RAPORT_RESOLVE_KOTWICA_WYSZUKANA_2026-10-21.md` |

### SAMPLES identity gate per family (2026-10-21 10:50Z into the built day, operator; 10-21 mixed, ledger group "10-21 mieszany")

| constant | what | evidence |
|---|---|---|
| `IDENTITY_GATE_PER_FAMILY_FROM_UTC` (2026-10-21 10:50Z) | `metrics.check_identities` was one verdict for the whole match and SAMPLES applied it to every metric (Roma - Real 16938872: Real's shots 16 vs 8 + 8 + 1, no woodwork, all 52 of Real's metrics dropped). On (`metrics.identity_failures` + `identity_gap_for_metric`): shots identity -> only `shots_*` / `shots_on_target_*` (halves; shot handicaps / both-over through `shots_for`); goal incidents != score -> only incident metrics (card points incl. halves, reds, penalties); home period sum -> goals and reds / penalties (a subset of `goal_score_inconsistent`); tennis `gamesWon` -> whole match as before; a metric not in `FOOTBALL_METRICS` / `CARD_INCIDENT_SCOPES` -> any failure. Same rule in `settle.historical_sample` / `run_backfill.py` (SETTLE grading never used this gate). `03_samples.json` entries carry `identity_gate: "per_family"`; `rebuild_plan` step 1c re-runs `run_samples.py --event-ids` (bridge, soft) and `run_sheet.py --event-ids` for open football fixtures without the marker and with an `INTERNAL_INCONSISTENT` gap (`identity_unsampled`). Curves: the replay (`calibrate_from_cache` / `prepare_refit`) never called `check_identities` - fitted with no identity gate at all, so this brings SAMPLES closer to the curves' replay, not away; no refit needed for this | `scripts/sofa/measure_identity_gate.py` on 03_samples 10-17..10-21: (fixture, metric, event) gaps INTERNAL_INCONSISTENT 2,708 / 2,091 / 757 / 1,336 / 859, restored 1,677 / 1,090 / 311 / 417 / 335 (goals, corners, cards, saves, offsides, fouls); bias (cache football 07-01..10-21, match bootstrap): shots-only matches (n 253) vs kept (~29k) goals -0.07 [-0.30, +0.17], corners +0.30 [-0.13, +0.72], card points +0.14 [-0.31, +0.60], fouls -0.65 [-1.49, +0.10]; goal-incident matches (n 57) goals +0.83 [+0.34, +1.37] by construction (a placeholder list fails only off 0-0, the old gate kept those feeds' 0-0s); `docs/sofa/history/RAPORT_BRAMKA_TOZSAMOSCI_2026-10-21.md` |

### Basketball player lines v2 (2026-10-23 00:00Z; standing rule: no leg prints before its own lines)

| constant | what | evidence |
|---|---|---|
| `BASKETBALL_PLAYER_V2_FROM_UTC` | SHADOW reads nine more NBA player lines (`shadow.PLAYER_V2_MARKETS`: 231804 FT made, 231805 FT attempts, 231806 / 231807 field goals made / attempted, 231808 / 231809 twos made / attempted, 231810 threes attempted, 231811 personal fouls, 200985 turnovers; one `/lineups` key each), by the record's day and clock; snapshots carry `player_v2_rule`, sport legs too. p = `player_model` (player_rate_v3, installed constants, not fitted on these families); SHADOW_SETTLE grades from the player's own row; no curve, `line_evidence.read` without a base reads only the key's own bucket (no pooled offset), so `NO_LINE_EVIDENCE` until 50 lines / 15 games a bucket - nothing prints on day one, no ledger epoch group. `leg_relations`: shots of one kind linked (`_PLAYER_COMPONENTS`; points vs threes now DEPENDENT too), made shots feed the score. Not read: first-quarter player lines (no per-quarter box), "N+" milestones (one-sided), most / first, double / triple double. A refit of `fit_player_model.py` now includes these nine families in its objective | live probe 2026-10-22 (2 NBA games, ~14 players a game per family, both sides quoted; none on EuroLeague / EuroCup / ABA / ACB); keys on 2,048 stored boxes / 39,088 appearances 99.96% present, points / field-goal identities exact. History replay of the installed model, test split (kickoff >= 2026-07-01, ~47k player-games a family, line = sample median half-integer, not Superbet's): band 0.7-0.8 claimed / hit FT made 0.742 / 0.753, FT att 0.739 / 0.763, FG made 0.735 / 0.723, FG att 0.732 / 0.709, twos made 0.738 / 0.747, twos att 0.735 / 0.730, threes att 0.739 / 0.751, fouls 0.738 / 0.747, turnovers 0.742 / 0.743 (old families: points 0.740 / 0.705, threes 0.743 / 0.759); above 0.8 the FG families over-claim (FG made 0.838 / 0.682, n 768). Registry `T-BB-PLAYER-V2-calibration`; `tests/sofa/test_basketball_player_v2.py` |

### Measured sports: the rolling day window (2026-10-23 00:00Z; operator's decision 2026-10-22; ledger group "od 10-23")

| constant | what | evidence |
|---|---|---|
| `SPORT_LATE_WINDOW_FROM_UTC` (2026-10-23 00:00Z), `LATE_WINDOW_END_H` 5 | A hockey / basketball / volleyball / CS2 game belonged to the UTC day of its start, so NBA / NHL games after 00:00Z fell to the next day's coupon, whose morning build found them under way. On, `sport_identity.day_window(D)` = [end(D-1), end(D)), end(D) = D+1 05:00Z (`epochs.sport_late_window(D)`, read by the DAY alone so the windows partition the timeline: 10-22 = [10-22 00:00Z, 10-23 00:00Z), 10-23 = [10-23 00:00Z, 10-24 05:00Z)). Read by SPORT_IDENTITY, SPORT_CONFIDENCE, `rebuild_plan.observe_sport`, COUPON_ASSEMBLY (`build_coupon.in_day_window`; football / tennis keep the UTC day, builders too) and `day_status` (day over at end(D), D+1's snapshot file read too). SHADOW / CS2 of D fetch a D+1 game starting before end(D) once even beyond the horizon, into D+1's file (`run_shadow.snapshot`, `run_cs2.snapshot`). A leg starting on D+1 carries `window: "late"`; an event on D-1's printed 11_coupon.json (singles + builders) is `ALREADY_PRINTED_PREV_DAY`. The loops' mornings settle D+1's file up to end(D) (`settle_shadow.py` / `settle_cs2.py --date D+1 --kickoff-before`; SETTLE_AFTER 4 h, so only games started by ~01:15Z grade that morning, the rest a day later with D+1's own settle); grading reads each leg's `source_date` file as before. The late games are priced only by the operator's manual evening rebuild (`rebuild_day.py --date D`, ~20:00-21:00Z; morning legs stay locked) - not automated. A scope change, no curve or estimator changes | operator 2026-10-22; 10-22's last SPORT_CONFIDENCE refused 276 hockey and 4,927 basketball sides KICKED_OFF (`runs/sofa/2026-10-22/08_confidence_sports.json`; 3,893 basketball / hockey rows in the planning pass's build); 10-21's files held 38 games starting 10-22 00:00-05:00Z (8 hockey, 18 basketball, 10 volleyball, 2 CS2), none on file by 20:00Z under the old 3 h horizon (read-only replay of `sport_identity.snapshot_events`); `tests/sofa/test_sport_late_window.py`; registered `T-SPORT-LATE-WINDOW` |

### Measured sports - other live facts

- Basketball A7 hybrid (2026-10-15 11:29:38Z, operator "WŁĄCZ JUŻ DZISIAJ",
  not a mixed day: printable lines and 10-15 E2E unchanged): the A7 cache
  (`data/a7_odds/`) covers every target since 10-15 (basketball 26,536 asked:
  5,910 with line markets, 5,943 not on Sofascore; the 10-14 curve was fitted
  on the 40% asked by 10-13). The whole section refitted on the full cache was
  worse (+0.00034 [+0.00001, +0.00068] on 56,740 lines 10-05..10-14, printable
  gap -12.9 -> -16.4 pp) and not installed; its five A7 keys alone (total,
  handicap, team total - 50,360 market-line rows, buckets >= 0.70 realise
  0.56-0.65, never printable) replaced the staged section's
  (`fitted_from.a7_families_refit`): -0.00123 [-0.00151, -0.00096]. Backup
  `config/backup_2026-10-15_bb_a7_hybrid/`;
  `docs/sofa/evidence/basketball_a7_full_2026-10-16.md`.
- Sport history refresh (`refresh_sport_history.py`, `bet.sofa.sport_history`):
  until 10-12 a game's result never entered the hockey / basketball /
  volleyball history (10-07..10-11: 0-30% of settled games; model and line
  evidence stopped on 10-04). A week's ~500 games moved log-loss by nothing
  measurable (hockey -0.45e-3 [-1.86, +0.98], basketball +1.11e-3 [-1.63,
  +3.83]); gain is evidence coverage (volleyball 5,318 -> 8,474 settled lines)
  (`measure_sport_history_ab.py`).
- `final_only` grading (2026-10-12): until then a period-less hockey /
  basketball game stayed DATA_MISMATCH for good (10-22 basketball games a day
  from 10-07). Missing `winnerCode` named from a decided score from 2026-10-17
  (Shumen - Botev 87-84).
- Hockey / basketball player names: football's token and surname rules, then
  tokens without Jr / Sr / II suffixes (`shadow.player_value`, 2026-10-17).

## (b) Switches OFF (`None`)

### Waiting for the operator

| constant | what | state |
|---|---|---|
| `CURVE_STATUS_FROM_UTC` | a curve failing `measure_calibration.py` stops printing | waiting |
| `MODEL_FIXES_FROM_UTC` | tennis NB dispersion | with the next refit |
| `BUILDER_SCREEN_PRICE_FROM_UTC` | a builder prints only with a recorded screen price | switched off 2026-10-05: sofa does not price builders |
| coupon form dials | `ladder_form` / `max_positions_per_match` in `config/sofa_coupon_form.json` | operator's call |

Derived joints: the 10-14 refit replayed them; on Superbet lines 10-09..10-12
(in sample for the curve) the joint curves beat the line-evidence stand-in at
p >= 0.60 by -0.0154 [-0.0309, +0.0004] (touches zero); clearly only where both
sides had a marginal centre (-0.0357 [-0.0585, -0.0135]); on raw samples (B3's
population) the curve alone overstates by 11 pp at >= 0.70; lines it would
admit realised below their price (ROI -1.8% [-4.4, +0.7], `both_over_goals`
-6.2% [-10.6, -2.1]). Re-measure on rows from 10-13 on
(`docs/sofa/evidence/derived_curves_2026-10-14.md`). Switched on 2026-10-21
00:00Z with `DERIVED_SAMPLE_GATES` (section a, "Football statistics night"):
until then `THIN_SAMPLE_FOR_BUILDER` refused every derived football row.

### Measured and not switched on

| constant | measurement | evidence |
|---|---|---|
| `FOOTBALL_LEAGUE_RATE_RULE_FROM_UTC` | A2's football half: rating at the all-league rate beat the sample alone in thin competitions, squared error -0.58 [-0.62, -0.54] per side in its favour | `docs/sofa/history/RAPORT_IMPLEMENTACJI_AUDYTU_2026-10-13.md` |
| `UNIT_STRENGTH_FROM_PARENT_FROM_UTC` | A1: regional unit's strength from its competition's; goals log-loss -0.0010 [-0.0029, +0.0008] on 7,724 cross-unit matches | `scripts/sofa/measure_unit_strength.py` |
| `CS2_MAP_IDENTITY_FROM_UTC` | B11 map order / pool terms; walk-forward 24,995 maps / 11,217 series, +0.00021 [-0.00022, +0.00064] | `docs/sofa/evidence/cs2_map_identity_2026-10-13.md` |
| `HK_SHOTS_FROM_UTC`, `HK_EMPTY_NET_FROM_UTC` | B8 hockey shots x save%: centre replaced total +0.00126 [+0.00010, +0.00241] worse, blend +0.00025 [-0.00033, +0.00084]; fitted empty net handicap -0.00037 [-0.00074, +0.000006], total +0.00111 worse; shots exist for 6,755 of 29,516 games, none in October 2026 | `docs/sofa/evidence/hockey_goalie_empty_net_2026-10-13.md`, `docs/sofa/history/RAPORT_B8_HOKEJ_2026-10-13.md` |
| `VB_SET_LENGTH_FROM_UTC`, `VB_SET_HISTORY_FROM_UTC` | B9 / C10 volleyball set length, 5,050 matches walk-forward: points_total +0.0025 [-0.0005, +0.0054], points_handicap -0.0011 [-0.0036, +0.0013], set_extra_points -0.0004 [-0.0014, +0.0007]; C9 not measured (depends on B9) | `docs/sofa/evidence/volleyball_set_length_2026-10-13.md`, `docs/sofa/history/RAPORT_B9_C10_C9_2026-10-13.md` |
| `BB_OVERTIME_FROM_UTC` | A3 overtime in the basketball replay: regulation 1X2 -0.00354 [-0.00719, -0.00015], totals / winner no better; as a curve variant +0.00113 [-0.00123, +0.00353] | `docs/sofa/evidence/basketball_refit_2026-10-13.md` |
| `BB_PACE_FROM_UTC`, `BB_PACE_LEVEL_FROM_UTC` | B7 / B7b basketball pace x efficiency (`score_model.PACE_METRICS`; `fit_sport_confidence --bb-pace` / `--bb-pace-level`); live only with a basketball curve refitted on it | `docs/sofa/evidence/basketball_pace_2026-10-13.md`, `docs/sofa/evidence/basketball_pace_level_2026-10-13.md` |
| `TENNIS_ACES_OPPONENT_FROM_UTC` | aces centre x the returner's conceded aces shrunk to the tier prior (`bet.sofa.tennis_aces_opponent`, marker `tennis_aces_rule`, replay `--tennis-aces-opponent`; double faults worse, never corrected): history test 2026 aces_for +0.0003 [-0.0006, +0.0011], aces_total +0.0124 worse, per-set aces -0.003; Superbet lines with the real SHEET (64 matches, 1,364 lines, 10-06..10-16) +0.0060 [-0.0251, +0.0348] | `docs/sofa/evidence/tennis_aces_opponent_2026-10-17.md`, `docs/sofa/history/RAPORT_TENIS_SERWIS_2026-10-17.md` |

Other measured-and-kept-out curve refits: basketball plain refit with the
league-rate rule (confidence log-loss -0.00042 [-0.00145, +0.00063], printable
gap -16 pp unchanged; `docs/sofa/evidence/basketball_refit_2026-10-13.md`);
2026-10-14 sport refits on Superbet lines 10-05..10-12
(`docs/sofa/evidence/sport_refit_2026-10-13.md`): CS2 -0.00008 [-0.00030,
+0.00015], hockey +0.00151 [+0.00105, +0.00200] worse, volleyball -0.00032
[-0.00175, +0.00120]. Hockey A7 (operator 2026-10-15, not on): `parse_lines`
reads "Match goals" (settles with overtime; only its position read, graded as
regulation total 623); replay puts hockey's total alone on it, handicap / team
totals synthetic; a fit reads the hockey cache only with explicit
`--market-lines` (`sport_confidence.MARKET_LINE_DEFAULT_SPORTS`); log-loss
-0.0055 [-0.0072, -0.0039] vs a synthetic refit (all on totals), but the model
never reaches 0.70 at the market's line: the 382 printable total lines of
10-05..10-14 (calibrated today -0.4 pp [-5.0, +4.0]) would read nothing
(`docs/sofa/evidence/hockey_a7_2026-10-16.md`); hockey's 16,484 games asked
(6,950 with the "Match goals" total, no spread). Identity K7 (players found
only under another team: hockey 25 of 30 / basketball 20 of 48
NOT_IN_HISTORY names) is a model change, to be measured first
(`docs/sofa/history/RAPORT_K7_K8_POMIAR_2026-10-14.md`).

### Tennis serve markets (kept off)

Aces / double faults are priced from the server's own scoped sample shrunk to
the tier prior; the returner never enters. Serve markets the replay never read
(per-set aces / double faults, aces + double faults match and per set; replay
`--tennis-serve-markets`) got history curves
(`scripts/sofa/fit_tennis_serve_curves.py`, staged in
`data/refit_tennis_serve_2026-10-17/`, install group `tennis_serve` REPLACES
its markets' curves) that pass the one-sided gate on the history but at
Superbet's lines print far below confidence: per-set double faults / serve
points 12 legs / 4 matches -20.7 pp [-50.8, +5.8]; aces with the correction 20
/ 13 -30.6 pp [-52.2, -4.6] (`scripts/sofa/measure_tennis_serve_market_line.py`)
- not installed (`T-TENNIS-SERVE-MARKET-LINE`). Mechanism: the replay's curve
is fitted on the whole synthetic ladder (`lines_for`), Superbet quotes one line
near the median where p >= 0.70 is a disagreement with the market; on the
history alone a curve fitted on all lines read on market-like lines claims
0.761 and realises 0.668 (aces_for). Installed tennis serve curves: aces /
double faults match only (history curve at >= 0.70 on Superbet's lines -22.6
pp [-33.4, -14.3], 140 lines / 43 matches; line evidence holds back all but
short prices: 14 printed legs settled 0.714 vs 0.759). **Never pass
`--tennis-serve-markets` or `--tennis-aces-opponent` to a refit** before
`T-TENNIS-SERVE-MARKET-LINE` passes; `prepare_refit.py install` refuses a refit
whose replay lacks a flag an installed separately fitted curve requires
(`requires_replay_flags`, `dropped_replay_rules`). Tennis printed legs
10-09..10-16 as a whole -1.0 pp [-3.5, +1.5] (1,473 legs, ROI -5.5%); per-player
set games OVER -7.1 / -6.6 pp, intervals touching zero
(`T-TENNIS-SET-GAMES-OVER`).

Exposure / tournament / returner centres (2026-10-19, pre-registered,
`scripts/sofa/measure_tennis_serve_exposure.py`, main tour only, tier prior as
SHEET, curves on market-like lines): true match length is the largest missing
factor (oracle aces log-loss -0.014) but the rating's expected games recover
little; on the history only per-set aces pass (x tournament factor -0.0011, +
returner -0.0038), double faults nothing; at the market line no aces-match arm
reaches 0.70. At Superbet's lines 10-06..10-18 the per-set aces arm is no
better (-0.0006 [-0.0078, +0.0069]) and its legs overstate (35 / 15 matches,
-11.3 pp [-26.0, +4.4]) - not in SHEET (`T-TENNIS-ACES-SETS-EXPOSURE`,
`docs/sofa/evidence/tennis_serve_exposure_2026-10-19.md`).

## (c) Installed fits, source DBs, backups

| fit | installed | content | source / backup |
|---|---|---|---|
| refit 2026-10-08 | 10-08 23:42Z (5330f357 / fdbe0aae) | dispersion, scoped tennis table, per-market K (section a) | `data/refit_2026-10-08/` (logs and `replay/` dirs; no `sofa_replay.db` on disk) |
| refit 2026-10-13 | 10-13 18:06Z | football / tennis curves etc.; superseded | `config/backup_2026-10-14` (before it) |
| refit 2026-10-14 | 10-14 05:31Z (`prepare_refit.py install`) | curves, engine constants, league baselines, reliability on 121.9M rows (max settled run date 10-12; 6,688 best-of-five `sets_total` rows deleted from the copy); `K_CENTRE` tennis 8, football 15; replay incl. `--football-rating --rated-scope --venue-prior --game-state --rating-weight --season-phase --tennis-set-ratings --opponent-correction --player-starts-only --derived`; starts-only player curves promoted (`.next.json` removed, copy in backup). Dry run (10-13 artifacts): printed singles 1323 -> 1296; common legs +0.04 pp mean, 0.3 pp abs; basketball totals / handicaps / team totals 0 (A7); hockey, CS2 unchanged; B15 corrected no row | replay DB deleted 10-16 (logs kept); `config/backup_2026-10-15`; `docs/sofa/history/RAPORT_NOC_2026-10-13_14.md` |
| new-market curves | 10-15 00:17Z (`install_new_market_curves.py --dir data/refit_new_markets_2026-10-15 --confirm`) | 29 curves admitted by the one-sided gate (below) | `config/backup_2026-10-15_new_markets/`; `docs/sofa/evidence/new_market_curves_2026-10-15.md`, `docs/sofa/history/RAPORT_KRZYWE_NOWE_RYNKI_2026-10-15.md` |
| basketball A7 hybrid | 10-15 11:29:38Z | five A7 keys (section a) | `config/backup_2026-10-15_bb_a7_hybrid/` |
| cup-strength refit 2026-10-16 | 10-15 23:02Z | football / tennis curves on `data/refit_2026-10-16/sofa_replay.db` (125.4M rows, `--cup-strength`); DC / DNB / first goal refitted on the same book (verdicts unchanged); `fit_constants` K fits skip rating-only markets' sample-less rows (3f77701e); E2E 10-15: 1,238 common legs, none moved > 0.006, cups move 60 legs (59 cup), +65 / -37 (Lech - Leverkusen, Celje - Omonia, CSKA - Monaco, Egnatia - Midtjylland move the way the analysts' vetoes said) | replay DB deleted 10-16; `config/backup_2026-10-16` |
| refit 2026-10-16b | 10-16 04:02Z (standing go of 10-15 evening) | `data/refit_2026-10-16b/sofa_replay.db` (120.3M rows, after `backfill_event_stats.py --competitions` gave 1,748 cup matches statistics), plus `--tennis-sample-scope` (before: 13% of best-of-three rows, 57% ATP, held a Grand Slam five-setter, centre +1.97 games, log-loss +0.0445) and `--sample-cup-strength`; E2E 10-15 vs 10-16: +22 / -6 legs (11 tennis games_won_for), common +0.0001 mean, max 0.050; 13 `tennis_team_cup` class keys (aces, double faults, games_total, set 3, sets_total) lost their curve - NO_CLASS_CURVE until measured | replay DB deleted 2026-10-19; `config/backup_2026-10-16b`; `docs/sofa/evidence/tennis_replay_sample_scope_2026-10-16.md` |
| score-market slice curves | 10-16 (`install_new_market_curves.py --dir data/refit_new_markets_2026-10-17`) | 133 football slice curves (men 50, season_early 40, women 43) + `set_score_not` men and `tennis_women:`; `scripts/sofa/fit_score_market_curves.py` on the 1X2/DNB and tennis set fit rows - no replay; one-sided gate + no slice overstating (one curve per market had hidden -3..-9 pp slices in a -0.5 pp pooled gap) | - |
| refit 2026-10-17 | 10-17 19:13Z (into the mixed day) | football / tennis curves, engine constants, league baselines, reliability on `data/refit_2026-10-17/sofa_replay.db` (1,282,317 matches, 121.9M rows; 10-16b flags + `--goals-stretch --count-stretch --player-stretch`); tests/sofa 5102 passed; line evidence refitted; `fit_confidence` keeps footballer shot-detail rows out (`shot_detail.METRICS`; the first fit had replaced the left / right foot curves). E2E: 10-16 +83 / -44 legs, settled -89.94 -> -90.95 u. (dropped 41 graded -0.51, added 81 -1.52); 10-17 +71 / -28, common abs move 0.002 mean, 0.060 max | **keep this DB** (`fitted_from.db_path`); `config/backup_2026-10-18` |
| per-line curves | 10-18 12:04Z (`install_line_curves.py`) | `by_market_direction_line` only | `config/backup_2026-10-18_line_curves/` |

New-market curves of 10-15 (operator go 10-14 "zbudować krzywe dla tych
wszystkich rynków"; one-sided holdout gate, operator 10-14 18:55Z,
`scripts/sofa/new_market_gate.py`: fit before 2026-09-01, judged on
09-01..10-13; a key fails only if its curve overstates - n >= 300 holdout
forecasts at curve >= 0.70 and realised - curve >= -2 pp; understatement passes;
every "12" key refused by policy; sports' admission rule unchanged). Football /
tennis: `player_left_foot_shots_for` / `player_right_foot_shots_for` OVER,
`double_chance` OVER (+ `women:`), `first_goal` OVER, `penalties_total` /
`red_cards_total` UNDER, `set1_won_for` / `set2_won_for` OVER and UNDER,
`set_score` OVER (each + `tennis_women:`), `draw_no_bet` OVER / UNDER (+
`season_early:` and `women:` OVER). Sports: hockey `double_chance` /
`period_double_chance` TEAM, basketball `double_chance` TEAM, volleyball
`team_sets_exact` NO / `team_wins_set` YES, CS2 `rounds_handicap` TEAM,
`rounds_total` OVER, `team_rounds` OVER. Every other new key (1X2, "12", shots
outside the box / headed / on target, reds / pens OVER, basketball halves /
quarters, volleyball sets_count) has no curve. E2E copy of 10-14: +110 legs (DC
78, reds UNDER 12, pens UNDER 6, hockey DC 9, set winners 4, first goal 1), 0
lost, no common leg moved; 102 of the 110 at confidence below 1/odds (they pass
x >= 0.90); whether they beat the price is unmeasured.

Carrying separately fitted curves: `match_won_for` and every new-market key are
carried by a refit itself since 2026-10-16 (`fit_meta.carry_separately_fitted_curves`
in `fit_confidence`, `carry_sport_new_market_curves` in `fit_sport_confidence`;
listed in `new_market_curves_fitted_from`); before, a refit dropped them unless
carried by hand.

Sport curves: hockey / volleyball / CS2 = the installed sport file's (CS2's
B10 curve promoted 2026-10-14, bc69b56e); basketball = the staged `.next.json`
(A7 + hybrid).

Replay contents (`calibrate_from_cache.py`): football rating in the marginal
rows' centres (`--football-rating` with `--rated-scope --venue-prior
--game-state --rating-weight --season-phase`), tennis set ratings
(`--tennis-set-ratings`), B15 (`--opponent-correction`), starts-only players
(`--player-starts-only`), joints of cards_points / goals / corners /
shots_on_target (`--derived`; fitted, not read), cup strength, sample cup
strength, tennis sample scope, the three stretches. Tennis neighbours are
`tennis_rating.AsOfRating` (best-of-five skipped); set bases replayed for
best-of-three only (`calibrate_from_cache.set_values`, `metrics.infer_best_of
== 3`; fix 2026-10-14 after 6,688 Grand Slam `sets_total` 2.5 rows with UNDER
realised ~0); SHEET refuses `sets_total` not known to be best of three
(`BEST_OF_FIVE_NOT_MODELLED`, `run_sheet.format_bound_refusal`). Not replayed:
tennis tier / ladder priors, men's friendlies (851).

Backups: `config/backup_2026-10-05`, `config/backup_2026-10-06_sport_calibration/`,
`config/backup_2026-10-08`, `config/backup_2026-10-09`, `config/backup_2026-10-14`
(before the 10-13 refit), `config/backup_2026-10-15` (before the 10-14 refit,
with the removed `.next.json`), `config/backup_2026-10-15_new_markets/`,
`config/backup_2026-10-15_bb_a7_hybrid/`, `config/backup_2026-10-16` (before the
cup-strength refit), `config/backup_2026-10-16b`, `config/backup_2026-10-18`
(before refit 2026-10-17), `config/backup_2026-10-18_line_curves/`.
`data/refit_2026-10-17/sofa_replay.db` is the DB the installed football /
tennis curves were fitted from (`fitted_from.db_path`) - keep it. There is no
full copy of `data/sofa.db` on disk: the operator deleted
`data/backup_2026-10-05/sofa.db` and the replay DB of `data/refit_2026-10-16b/`
on 2026-10-19 (disk cleanup); the replay DBs of `data/refit_2026-10-16/` and
`data/refit_2026-10-14/` went 2026-10-16 (logs / manifests of all kept). The
day-by-day rows of the fits (`*_history_fit` / `_holdout.jsonl`) are kept only
in the newest two `data/line_evidence/rows_before_<d>` (older ones keep
`*_superbet_settled.jsonl`).

## (d) Measured and declined - do not re-propose without new evidence

- a footballer's line-evidence offset measured only on lines with curve x odds
  >= 0.90 (2026-10-16, walk-forward 10-12..10-15): dropped legs not measurably
  worse (-7.3 pp [-22.2, +7.3] vs -4.1 kept), acted on player_shots_for alone
  and raised tackles - the shape of the 10-12 per-bin offset
  (`docs/sofa/evidence/player_line_evidence_2026-10-16.md`);
- football "&" result markets (result & goals, result & BTTS, goals & BTTS, DC
  & goals other than 12 & over / 1X & under) - overstate or never reach 0.70;
  the favourite's European handicap (-5.2 pp); goals parity, exact goals, a
  side's goal intervals (never 0.70); total goals interval (passes, 0 legs clear
  at Superbet's prices); copies of read markets ("Każdy wygra seta", "Dokładna
  liczba setów", "liczba setów 1.5": same event, 1-3% better price in ~8% of
  pairs, no new leg) (`docs/sofa/evidence/football_score_markets_2026-10-16.md`);
- a second coupon or a variant (operator: one coupon, many sports);
- a 0.80 confidence floor (operator: "many options");
- current-season-only samples (worse on every metric); same-competition
  samples for corners / fouls / shots / cards (no gain) or for knockouts (worse);
- trimming national-team samples to 180 days (worse log-loss);
- blending the price into confidence or gating on disagreement with it
  (disagreement is an anti-signal; every weight moved to the price only copies
  the price) - the price-band cap is not a blend: it only lowers, only where a
  band's settled lines measured below the curve (operator 2026-10-07);
- league selection / gate tuning (anti-selects out of sample);
- (2026-10-08, out of sample on the history) hierarchical / empirical-Bayes
  pooling of team and league effects (+3.1e-4 log-loss vs fixed K); a t copula
  or per-league-class correlation for joints; Dixon-Coles and bivariate Poisson
  for goals (rho -0.013, kappa ~ 0); zero-inflated NB, empirical and mixture
  families and per-team dispersion for counts; beta / isotonic / spline
  calibration instead of buckets (-7e-4, ECE no better); a lower credible bound
  on p; a surface-hierarchy or serve/return tennis model; exponential-decay
  memory (half-life 180 d);
- re-ranking peer legs by own-sample size, hit rate, near misses, venue, recent
  form, tournament popularity / reserve / women / cup flags (2026-10-08: no
  out-of-sample gain on 62k legs);
- (2026-10-12, walk-forward on printed legs 10-09..10-11) a stricter price-band
  cap (to the cell's realised rate whenever lower): dropped 15% of legs which
  had not done worse (ROI -0.6% vs -4.4% kept), barely moved the over-price gap;
  an offset per confidence-minus-price bin: half the correction, dropped legs
  not worse either - flagged instead (`price_gap`);
- (2026-10-12 night, `measure_sport_guard.py`, walk-forward on the measured
  sports' settled lines 10-07..10-11; 1,885 would-print lines / 536 games) a
  per-key p-bucket cap for hockey / basketball / volleyball / CS2: point cap
  dropped 135 lines not worse (ROI -4.7% vs -5.4% kept); Wilson cap dropped 8
  that all won. The sports' overstatement is a curve question (basketball's
  history curve read 0.762 on lines realising 0.615, -14.6 pp [-19.6, -9.6]
  before the offset; hockey calibrated);
- `FOOTBALL_LEAGUE_RATE_RULE`, hockey / volleyball / CS2 / plain-basketball
  refits, full-cache basketball A7, hockey A7, tennis serve curves and aces
  correction, the tennis serve exposure arms - section (b);
- CS2 map total from the round race vs base rate: zero on the history; operator:
  do nothing (2026-10-19, `scripts/sofa/measure_cs2_map_total_race.py`).

## (e) Open questions, not modelled yet, before the next refit

- **Open checks on new data**: `T-PEER-CHOICE-edge`, `T-FAMILY-SELECTION`,
  `T-LINE-CURVES`, `T-PLAYER-SAMPLE-GATES`, `T-SCORE-MARKETS-superbet`,
  `T-CS2-SERIES-ROUNDS-superbet`, `T-TENNIS-SERVE-MARKET-LINE`,
  `T-TENNIS-SET-GAMES-OVER`, `T-TENNIS-ACES-SETS-EXPOSURE`, `T-RED-FLAG-SCRIPT`,
  `T-A2-league-rate-refusals`, `T-A4-bucket-deff`, `T-IDENTITY-unexplained`.
- Family selection (view only): walk-forward 10-12..10-17 (windows 3-8 days)
  x >= 1 and a family on the plus -0.6% [-4.8, +3.9] on 1,254 legs vs -4.5%
  rest, better on 6 of 6 days but pooled +4.0 pp [-0.3, +8.1] with 81% of its
  legs on 10-17 (`docs/sofa/evidence/selection_walk_forward_2026-10-18.md`).
- Volleyball overstates ~16 pp at confidence >= 0.70 with either curve (-15.4 pp
  [-24.4, -6.8] new); basketball printable gap -16 pp - curve / line-evidence
  questions.
- Superbet's game count of a tennis match tiebreak.
- Line-evidence offsets of repriced families moved <= 1.3 pp a day over
  10-09..10-12 (stable); tennis `games_won_for` OVER offsets (-8.5 men, -12.1
  women) were measured on old-estimator rows while the new rows are calibrated
  (-0.2 pp, n 117) - over-lowered, a candidate once a walk-forward has the days.
- Best-of-five `games_total` / `games_won_for` replay samples are not
  format-scoped (measure before a fix).
- Abandoned match (Regulamin 5.D.5: a market decided at the interruption
  stands, the rest void) not graded yet.
- Football props (2026-10-15, 10-12..10-14): curve calibrated (-2.1 pp [-6.9,
  +2.7], 319 lines / 51 games), ROI -16.5% at Superbet's short prices
  (`docs/sofa/evidence/football_props_2026-10-15.md`).
- **Before the next refit**: measure the tennis games population of replay
  matches without `/statistics`; carry the men's friendlies (851 rows in the
  goals fit, variant C, the as-of 851 prior); every refit replays every rule
  the installed curves carry (`fitted_from.replay_rules.flags` of
  `config/sofa_confidence_calibration.json`: the 10-16b flags `--cup-strength
  --sample-cup-strength --tennis-sample-scope` plus `--goals-stretch
  --count-stretch --player-stretch`); never the serve flags (section b).
- **Measured for the next refit** (2026-10-12 night,
  `docs/sofa/history/RAPORT_NOC_2026-10-12.md`): football DNB / DC / 1X2 from
  the pure rating centre with NB r ~7 (skill 11.7 / 6.2 / 6.4%; a history curve
  over-states the season start by 2.4-4 pp - needs a season-phase term; UNLINKED
  stays refused); football BTTS has no skill vs the league base rate, parity and
  exact score never reach 0.70 (`measure_football_result_model.py`,
  `measure_tennis_outcome_model.py`).
- **Not modelled yet** (operator 10-07: every market that could win, each
  through a curve and its own Superbet lines): BTTS alone, half-time /
  full-time and half-result markets, Superbet's `;` combinations, tennis game
  order / points in a game / games parity (measured: never 0.70), CS2 round
  parity (OFFER's `unmapped_markets`, `market_coverage.md` labels each);
  derived football / tennis joints and women's tennis per-set markets above
  their measured range wait for 50 settled lines a bucket (`NO_LINE_EVIDENCE`).
- Unread markets' prices are recorded (`unmapped_prices/`, from 2026-10-14) for
  a later model's line evidence.

## (f) Ledger epoch groups

Source: `audit_ledger.EPOCH_GROUPS`. The current rules apply from 2026-10-06; a
refit install or an epoch switch starts a new epoch; a switch moved into a
built day makes that day mixed - its own group, summed with neither neighbour.
Groups are never pooled.

| group (code) | days | why |
|---|---|---|
| "do 10-04" | < 10-05 | earlier rules; rows of variants retired 2026-10-05 whose code is gone (`wariant`, `multi`, `sport:<sport>`, `rule:<sport>`), kept as recorded, never rebuilt |
| "10-05 rano" | 10-05 rows not of epoch `stats_only` | the morning build before STATS_ONLY 07:15Z |
| "stats_only" | 10-05 (rebuild) .. 10-08 | stats-only coupon; current rules apply from 10-06; 10-08 built under the old estimator, never rebuilt, re-PDF'd or re-read after the 10-08 23:42Z install (PEER_CHOICE 08:10Z is annotation only) |
| "od 10-09" | 10-09 .. 10-11 | refit of 10-08 23:42Z effective 10-09 |
| "od 10-12" | 10-12 | player switches 00:00Z (ONE_SIDED_SINGLES, PLAYER_STARTS_ONLY, PLAYER_NAME_TOKENS, staged player curves); PRICE_GAP_FLAG 11:51Z annotation only |
| "10-13 mieszany" | 10-13 | refit 10-13 18:06Z, its switches and CS2 B10 / B12 from 18:10Z into the built day |
| "10-14 mieszany" | 10-14 | 00:00Z switches, refit 05:31Z and B15 05:45Z before the build; identity switches 11:30Z and new markets 14:20Z / 14:50Z into it |
| "od 10-15" | 10-15 | new-market curves 00:17Z, 1X2 / DNB and CS2 series rounds 00:00Z |
| "10-16 mieszany" | 10-16 | cup-strength refit 10-15 23:02Z, FOOTBALL_CUP_STRENGTH and BASKETBALL_DC_PAIR 00:00Z, refit 10-16b 04:02Z, SAMPLE_CUP_STRENGTH 04:10Z before the build; score markets / set complements 07:46Z into it |
| "10-17 mieszany" | 10-17 | stretches 13:37Z and refit 2026-10-17 19:13Z into it |
| "od 10-18" | none | holds no day |
| "10-18 mieszany" | 10-18 | LINE_CURVES 12:48Z into it |
| "od 10-19" | 10-19 .. 10-20 | LINE_CURVES from 00:00Z |
| "od 10-21" | none | holds no day (CS2_PLAYER_SHARE 00:00Z; CS2_PRICE_GAP 00:00Z annotation (+ read order); the seven football statistics switches 00:00Z and their curves (installed 10-20 ~22Z) - all in "10-21 mieszany") |
| "10-21 mieszany" | 10-21 | the "od 10-21" switches 00:00Z, then LATE_RESOLVE 08:48Z, SQUAD_SEARCH_RETRY (moved from 10-22 00:00Z) and ENTITY_MISS_PER_DAY 09:20Z into the built day (late fixtures reach the coupon after the first print); IDENTITY_GATE_PER_FAMILY 10:50Z (wider football samples, re-sampled open fixtures) |
| "od 10-22" | 10-22 | SQUAD_SEARCH_RETRY 00:00Z (more reserve / youth fixtures) |
| "od 10-23" | 10-23 .. | current; SPORT_LATE_WINDOW 00:00Z - a day's measured-sport legs run to D+1 05:00Z (the evening rebuild's), a scope change of the coupon |

There is no group "od 10-17": PLAYER_SAMPLE_GATES 00:00Z falls in "10-17 mieszany".

Boundaries are constants in `scripts/sofa/audit_ledger.py` (`*_MIXED_DATE`,
`*_EPOCH_FROM_DATE`); moving a switch must move its boundary.
