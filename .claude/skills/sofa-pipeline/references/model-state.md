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
| `READ_SCOPE_FROM_UTC` | 10-27 00:00 | the read set narrows to the 20 best-value matches (`READ_SCOPE_EVENTS`, artifact `read_events`; 30 before); same moment, `report_check` binds a read removal to a dated fact or `DEFEKT:` (operator's go 10-26, analyst audit: removed minus KEEP ROI -0.9 pp [-5.9, +4.2], 1,104 vs 9,198 legs, 10-13..10-25; ledger group "od 10-27") |

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

### Basketball: the league rate restarts after an off-season (2026-10-23 00:00Z; operator's go 2026-10-22 ~10:21Z; ledger group "od 10-23")

| constant | what | evidence |
|---|---|---|
| `LEAGUE_SEASON_RESTART_FROM_UTC` (2026-10-23 00:00Z), `LEAGUE_SEASON_RESTART_SPORTS` {basketball}; `football_rating.SEASON_GAP_S` 45 d, `SEASON_PRIOR_MATCHES` 10, `SEASON_RESTART_LEVEL_ONLY` True | The score model's league rate (`_League`, `ALPHA_LEAGUE` 0.02, ~ the last 50 games) carried a season's end into the next: the NBA (132) read 218.1 points on 10-21 (its May / June 2026 playoffs 215 / 206) against 228.6 for October's first 14 games; the model sat 13.2 points under Superbet's main total on 13 games and a replay printed 42 NBA legs on 10-21 / 10-22, 36 UNDERs on halves / quarters. On (`RatingBook.season_restart`, set only by `score_model.build_model(season_restart=...)`; football never): a league whose next game comes >= 45 days after its last reads the plain mean of the ended season (playoffs included; `_League.season_mean`, needs >= `MIN_LEAGUE_MATCHES` of it), and from its first new game its LEVEL (home + away) restarts from that mean worth 10 games (step 1/(w+1) down to `ALPHA_LEAGUE`), the home share at `ALPHA_LEAGUE`. The match count `n` (the 30-game gate) is never reset. Read by SPORT_CONFIDENCE (`DbForecaster`), `settled_shadow_rows` (day's rule), `walk_forward_rows(season_restart=)`, `fit_sport_confidence` (`--league-season-restart`, else the `--before` day's rule; `fitted_from.league_season_restart`), `fit_sport_derived` (`estimator_switches`). The installed basketball curve (`.next.json`, fitted 2026-10-14 on the old rule) is NOT refitted: a refit on the rule was measured worse on settled Superbet lines and not installed (2026-10-22, section (d), `REFIT_KOSZ_SEZON_2026-10-22.md`) | Walk-forward A/B on copies of the DB (`data/refit_2026-10-22/league_season/`, `measure_restart.py`; as `walk_forward_rows`: rebuild every 30 days, book updated game by game, live switches; both arms scored on the union of their synthetic lines of every coupon game-line family; 1,000 sims; game bootstrap), 2024-09..2026-10-22, log loss per line new - old: **NBA** 2,644 games -0.0006 [-0.0010, -0.0001], first 30 days of a season (448 games) -0.0030 [-0.0050, -0.0012] (totals -0.0125, team totals -0.0079, halves -0.0034, quarters -0.0014; winner / handicap ~0); level actual - model at season starts 2024 +2.3 -> +1.4, 2025 +1.1 -> +0.6, 2026 (14 games) +10.3 -> +0.6; squared total error -2.84 [-4.60, -1.08] per game. **Other basketball** (1 in 20, 2026-09.. 1 in 4) 4,243 games -0.0001 [-0.0005, +0.0003], no family's interval above 0. Pooled (NBA + thinned other, 6,887 games) -0.0003 [-0.0006, +0.00004] - touches 0; pooled season starts -0.0009 [-0.0018, -0.0001]. Printable rows (curve >= 0.70) realised - confidence unchanged (NBA -2.0 pp both arms; other +1.3 / +1.2). The level-only form was chosen AFTER the pre-registered both-sides form (K 10) measured winner +0.0018 [+0.0003, +0.0031] / handicap +0.0013 [+0.0001, +0.0025] worse outside the NBA (NBA -0.0005 [-0.0010, -0.0001]) - on the same windows, so its margin over that form is in-sample. Replay of 10-21 / 10-22 (`replay_1021.py`, model cut 20 min before each kick-off): 42 NBA legs (36 UNDER, 3 handicap T2, 3 winner / 1X2 T1) -> 14 (6 UNDER, 1 OVER, 3 handicap T2, 4 winner / 1X2 T1); model minus Superbet's main total -13.2 -> -3.8 points. Report `docs/sofa/history/NBA_SEZON_STAWKA_LIGI_2026-10-22.md`; `tests/sofa/test_league_season_restart.py`; registered `T-BB-SEASON-RESTART-superbet` |

### No curve from our settled days alone (2026-10-24 00:00Z; operator's go for fixes 2026-10-23; ledger group "od 10-24")

| constant | what | evidence |
|---|---|---|
| `LIVE_ONLY_CURVE_REFUSED_FROM_UTC` (2026-10-24 00:00Z) | `fit_confidence` read every `sofa_settled_row`, replayed (`run_date` `cache-calibration`) and live alike, so markets the history replay does not price got curves from our settled days alone (found 10-22, `REFIT_PILKA_2026-10-22.md` "Znalezisko"). Tool fix (live at once, no effect on what prints): the fit tracks per key whether a replayed row reached it; a key reached only by live rows gets no curve (by_market, direction, thin, class sections, per-line curves, pools) and is listed under `live_only_refused` (fit output JSON and file; `--classes-only` / `--line-curves-only` in their `*_fitted_from`); a separately fitted curve carried in (`fit_meta.carry_separately_fitted_curves`) is not listed. A table without `run_date` (hand-built fixtures) counts every row as history. Switch (installed curves): the 50 keys of `config/sofa_live_only_curves.json` are stripped by `live_only_curves.for_day` in `run_confidence` and in `fit_line_evidence` (base of the `--before` day); such a key has no curve and no pool stands in (`Calibration.no_pool_keys`), so it reads its own Superbet lines or `NO_LINE_EVIDENCE`; the unproven-market ceiling stays the full file's. By the day and the build clock | Fixed fit re-run on `data/refit_2026-10-17/sofa_replay.db` (the installed curves' DB): 50 keys refused, all installed, none separately fitted; the 283 other top-level curves byte-identical to the installed ones. All tennis: `serve_points_*` (match / set 1 / set 2, for / total), `aces_set1/2_*`, `double_faults_set1/2_*`, `tiebreaks_total`; men 36 (8 `by_market`, 2 direction, 26 thin), `tennis_women` 14 thin; 100-1,167 rows a key, 15,029 in all; **no bucket >= 0.70 in any of them**. Legs 10-13..10-22: 0 printed or gated legs read one of these curves (6 printed `tiebreaks_total` UNDER legs of 10-15 / 10-16 read `sb:` already). Replay of 10-21 / 10-22's refusal rows of these markets (installed line evidence): ~500 rows a day change their read (pool capped by a thin bucket or a sub-0.70 curve -> own lines / NO_LINE_EVIDENCE), 0 change printability. Report `docs/sofa/history/KRZYWE_TYLKO_Z_NASZYCH_DNI_2026-10-23.md`; `tests/sofa/test_live_only_curves.py` |

### Coverage audit 2026-10-23 "ALL IN" (2026-10-24 00:00Z; operator's go 2026-10-23 ~13:50Z; ledger group "od 10-24")

Plan P1-P14 of `docs/sofa/history/AUDYT_POKRYCIA_2026-10-23.md` (section 7);
implementation report `docs/sofa/history/AUDYT_POKRYCIA_WDROZENIE_2026-10-23.md`.
Operator's rule: items without a measurement (P2, P8, P9, P12, P14) on once code
+ tests pass; measured items (P1, P3, P4, P5, P6, P7) on only if better out of
sample (or, for a coverage fix, the added rows calibrated and nothing worse on
the old rows). Every switch is read by the day and the build clock
(`epochs._audit_1023_on`); off = the old call exactly (no new argument passed).
`SAMPLE_CONFLICT_CUT_FROM_UTC` (P1) ON: an ENTITY_CONFLICT side keeps its
newest 10 matches after the newest clash (only when it has 10); football
2025-10-01..10-20, installed curves, match bootstrap: 8,339 sides / 7,709
matches recovered, printable recovered rows 93,631 realised - confidence
+0.51 pp [+0.15, +0.85], minus clean +0.35 [-0.05, +0.75]; shots_for -4.6 pp
[-6.6, -2.6] on 2,144 rows (1 of 23 markets); 2 friendly tournaments in a
switch-only key (`excluded_from_sample_conflict_cut`, categories unverified;
`find_friendly_competitions.py` counts it as reviewed).
Refits: `prepare_refit.py` install warns (`replay_switch_warnings`, never
refuses) while P1 / P3 (football) / P5 / P14 is on - `calibrate_from_cache`
replays none of them; `fit_sport_confidence.py` warns for P7 (CS2) and P13
(volleyball) and records `fitted_from.unreplayed_switches`. `rebuild_plan` has
no marker for P1 / P3 / P5 / P14: a SAMPLES / SHEET built for 10-24 before
00:00Z would stay on the old rules.
Football
(main session, from agent A's measurements 2026-10-23):
- `PLAYER_HISTORY_ANY_TEAM_SPORTS` += football (P3): a thin sample is topped up
  by player id from cached lineups of the peers = the opponents of the side's
  sample proper; each peer's newest 20 matches (`FOREIGN_PEER_GAMES`, listing
  read to `PEER_LISTING_LIMIT` 40) go through the sample proper's acceptance
  (`samples.peer_history`: finished, before kick-off, no friendly, one listing
  per match, RESERVE_SQUAD, one squad per id, P1's cut and
  `excluded_from_sample_conflict_cut` under P1), one row per (match, peer),
  statistics read with the kick-off (a provisional row proves no zero).
  Re-measured 2026-10-23 on this live rule (review R2 #1-#3, #8; target matches
  2026-08-01..10-20, 3,371, installed curves, histories under P1, match
  bootstrap): added printable rows 5,497 (562 matches) realised - confidence
  +0.25 pp [-0.82, +1.28], added minus base +0.07 pp [-1.03, +1.10]; no
  market's added interval excludes zero (shots UNDER -0.94 [-3.24, +1.19],
  1,316 rows); peers reach ~5.3% of thin player cases; old rows unchanged by
  construction -> ON (`scripts/sofa/measure_audit1023_p3_any_team_football.py`).
  Caveat: window = season start; shots / SOT / fouls / tackles centres from
  `player_share` do not see foreign games.
- `PLAYER_SLUG_NAME_FROM_UTC` (P5) ON: slug fallback; false-match test on the
  15,423 newest lineups (600,124 entries): same person 24,321, another 0; live
  10-21..10-23 4 / 4 / 6 names recovered, each one id
  (`scripts/sofa/measure_audit1023_p5_slug.py`); `contracts` + SETTLE
  (`run_settle.player_token_names`) admit "slug".
- `PLAYER_OMITTED_ZERO_FROM_UTC` (P6) stays None, refit not installed: new
  reader + refit curve vs old, out of sample, log loss +0.00030 [-0.00025,
  +0.00086]; on rows the old reader graded +0.00080 [+0.00025, +0.00141]
  (`scripts/sofa/measure_audit1023_p6_offsides.py`).

| constant | what | evidence |
|---|---|---|
| `IDENTITY_FRESH_RECHECK_ALL_FROM_UTC` (P2 / B2) | `sport_identity.identify_event(fresh_all)`: the K5 fresh re-ask fires on ANY refusal read from a cached team page within `FRESH_RECHECK_WITHIN` (3 h) of the start (not only `NO_GAME_WITHIN_1H`), every sport, once per team per run; then the second team's page (its resolved id, else its query id; cache first, fresh in the window). Record fields `second_team_id`, `second_listing_from_cache`, `second_fresh_recheck`, `identified_by_second_team` / `second_team_reason`; `NOT_ON_SOFASCORE` reads the first team's page and needs the second's to agree: a second page that shows the game but refuses it (AMBIGUOUS, START_GAP...) leaves `NO_GAME_WITHIN_1H` with `absence_contradicted_by_second_team: <reason>` (review R1 F4); breaker / `BRIDGE_ABORTED` unchanged. No measurement (operator) | cost upper bound 179 / 123 / 156 extra listing requests on 10-21 / 10-22 / 10-23 (partial), ~15 s of bridge a day (`scripts/sofa/measure_audit1023_p2_recheck_cost.py`); `tests/sofa/test_audit1023_p2_fresh_recheck.py` (5 of 8 fail on HEAD) |
| `SPORT_QUERY_ANCHOR_FROM_UTC` (P4 / B3), `sport_identity.QUERY_ANCHOR_SPORTS` {volleyball} | `sport_identity.match_query_anchor`, after `match_shadow` refuses and no side has a resolved id: the query team's ONE game at Superbet's exact start (`QUERY_ANCHOR_MAX_GAP` 0), gender, not postponed, own name >= 90 (`QUERY_ANCHOR_OWN_SCORE`) and same squad; opponent VETO first (its `TeamResolver.query_ids` non-empty and the game's opponent not among them; `run_sport_identity` passes `anchor_opponents=resolver.query_ids`), then MUTUAL / NAME >= 65 / SHARED_WORD; two games = AMBIGUOUS. `match_method` QUERY_ANCHOR + `query_anchor_rule`; a refusal writes `query_anchor_reason`. Not in `NAME_METHODS` / `OPPONENT_METHODS`: the entity map learns no name from it | backtest 10-05..10-23 on the DB copy, last SPORT_IDENTITY record per event, ids hidden (`scripts/sofa/measure_audit1023_p4_query_anchor.py`): volleyball 1,308 true-team-as-query + 1,172 today's-query-id picks, **0 wrong** (3 impostor ids, all refused); decoy opponent accepted 18 of 15,280; recall 11 of 96 query-only refusals (8 = the settle's event, 0 contradicted, 3 unsettled; OK Maribor - ACH Lublana 10-23). Hockey 0 wrong / 4,985, recall 4; basketball 0 / 5,760, recall 15 - clean but out of scope (adding them is the operator's call). Calibration of added legs not measured (11 events in 19 days). `tests/sofa/test_audit1023_p4_query_anchor.py` |
| `PLAYER_HISTORY_ANY_TEAM_FROM_UTC` (P3 / K7 / B1), `PLAYER_HISTORY_ANY_TEAM_SPORTS` {hockey, football} | `player_model.load_appearances(any_team=True)` (needs `PLAYER_TEAM_FROM_SIDE`): the player's own sample also reads the peers' `last` lists (the two teams' opponents in their loaded games), read by side, marked `Appearance.foreign` - own sample only, never the pool (`line_probability`); `find_player` asks the peers only on NOT_IN_HISTORY, strict rule, two agreeing = NAME_UNCERTAIN; rows `player_history_rule: "any_team_peers"`. Per sport; a call without `sport` is football's (`samples.py`; football in the set from the P3 football measurement, bullet above). SHADOW_SETTLE's settle-time number reads it too by the game's day. Constants resolve per day (`player_model.params_path_for`: a staged `config/sofa_player_model.next.<YYYY-MM-DD>.json` from its day and clock) - none staged | settled Superbet pre-game player lines 09-29..10-22, DB copy, box's player, side rule in both readers, 1,000 game bootstraps (`scripts/sofa/measure_audit1023_p3_player_any_team.py`): **hockey** 24,838 sides / 155 games, p on 22,418 -> 24,294; common sides log loss -0.0018 [-0.0034, -0.0003], Brier -0.0007 [-0.0012, -0.0002] (still worse than the price: +0.0070 [+0.0027, +0.0111] vs +0.0088); 2,240 sides whose p moved -0.0181 [-0.0354, -0.0030]; 938 added favoured sides claim 0.667 hit 0.647, -0.020 [-0.055, +0.013] (calibrated); pre-game name path 6,085 -> 6,205 as the box, 1 new wrong player (0.016%) -> ON. **Basketball** 27,864 sides / 245 games: common -0.0013 [-0.0045, +0.0019]; 2,015 added favoured sides claim 0.627 hit 0.544, -0.083 [-0.115, -0.052] -> OFF (section b). Hockey refit on the new reader (`fit_player_model.py --sport hockey --any-team`: prior_games 2.0, calibration_b 0.930) vs installed constants on it: -0.0003 [-0.0008, +0.0001] -> not installed (`data/refit_2026-10-23_allin/p3/fit_hockey_any.json`). Line evidence of hockey `player_*` keys was built on the old p (~9% of sides move). `tests/sofa/test_audit1023_p3_player_any_team.py` |
| `CS2_LINEUP_ELO_UNRATED_FROM_UTC` (P7 / B8) | `cs2_engine.RatingModel.home_logit`: a pair whose team ids are not both `MIN_MAPS_RATED` reads the lineup gap through its own calibration (`cs2_engine.fit_unrated`: the rated lineup intercept, slope fitted on the unrated pairs' walk-forward points; `u_fit >= MIN_FIT`); rated pairs unchanged. Read by SPORT_CONFIDENCE (`build_ratings(..., lineup_unrated)`) and `settle_cs2.attach_model` (offer day + kickoff). Numbered-map lines of an unrated pair read `p_map_nr` with the rated pairs' order / pool terms. A leg whose side has no number, or another one, without the rule carries `lineup_unrated_rule: "cs2_lineup_unrated_1023"` (`cs2_engine.LINEUP_UNRATED_RULE`, `run_sport_confidence.DbForecaster.unrated_rule`; legs only - the settled CS2 rows carry no marker). No curve refit | walk-forward on the DB copy 2025-10-23..2026-10-22, 7-day refits, evaluated from 02-20, series bootstrap 2,000 (`scripts/sofa/measure_audit1023_p7_cs2_lineup_unrated.py`): 567 series / 1,221 maps gain a number (111 series in the last 30 days), 8,575 rated series 0 rows changed; maps log loss 0.628 vs home share 0.690 (-0.062 [-0.078, -0.046]); realised - claimed home -0.8 pp [-3.6, +2.0], favourite +1.7 pp [-0.9, +4.3], slope 1.12 [0.95, 1.33]; series favourite +2.7 pp [-1.0, +6.3]; from 06-20 only favourite -1.1 pp [-4.4, +2.3]. Variant chosen among three on these data (rated calibration alone: slope 1.83 [1.54, 2.15]; free intercept: home -3.2 pp [-5.9, -0.3]). `p_map_nr` on the unrated group (same walk-forward with `fit_map_terms` per refit, review R1 F2): log loss -0.0017 [-0.0037, +0.0002] vs without the terms, favourite +0.4 pp [-2.2, +2.8], slope 1.08 - calibrated, kept. Not measured on Superbet lines. `tests/sofa/test_audit1023_p7_cs2_lineup_unrated.py`, `test_audit1023_p7_unrated_marker.py` |
| `NAME_RULES_1023_FROM_UTC` (P8) | CS2: `cs2.ROSTER_MARKER_FOLD` ("prospect" = the roster marker "prospects"; Sofascore "Inner Circle Prospect" / Superbet "Inner Circle Prospects") in `esports_score` / `pick_event` / `series_orientation`, read by SPORT_IDENTITY (`match_cs2`, `match_cs2_anchored`, `_cs2_same_roster`) and `settle_cs2`; `cs2_engine.player_id(prefix)`: a nickname found by prefix as settlement does (one roster nick >= `NICK_PREFIX_MIN` 5 letters; two = nobody), via `model_probability(name_rules)`, tried only when neither roster has the exact nickname (settlement's order, `cs2.MapResult.player`; review R1 F1). Hockey: `player_model.names_agree(translit)` folds ue/oe/ae, leading "ye", x -> ks, final -iy/-ij/-y, EQUAL folded tokens only (no prefix / initial), pre-game name finding only, rows `name_rule: "translit_1023"`; basketball never folds. No measurement | hockey 7,271 stored names: 0 new agreements between two ids (basketball 20, e.g. Braeden / Braden Smith - not applied); hockey settled lines name path 6,220 vs 6,205 as the box, 0 more wrong players. `tests/sofa/test_audit1023_p8_cs2_names.py`, `test_audit1023_p8_hockey_translit.py`, `test_audit1023_wiring_cs2_identity.py` (Privateer - Inner Circle Prospects pinned only under the rule) |
| `PLAYER_BOTH_SIDES_LISTED_FROM_UTC` (P9) | A hockey / basketball game seen on one team's `last` page only is written for the other team from its stored payload under its own list kind `last_side` (`sport_history.OPPONENT_KIND`, `list_both_sides`; offline, idempotent; `refresh_sport_history.py` after every refresh, `--both-sides-only` alone). Nothing reading `last` sees it; the player model (SHADOW's pregame number by the game's day and snapshot clock, SHADOW_SETTLE's settle number by the game's day) reads `sport_history.listing_kinds` -> `("last", "last_side")`, one row a game (`listed_rows`); rows `player_lists_rule: "both_sides"`. `fit_player_model.py` still reads `last` only. No measurement (operator) | live repair 2026-10-23 ~15:20Z (main session, `refresh_sport_history.py --both-sides-only`): 42,892 `last_side` rows; games of the last 400 days hockey 1,241 / basketball 7,273; Vancouver @ Florida 16546356 now in 3692's list (`scripts/sofa/measure_audit1023_p9_both_sides.py`). Effect on p / prints not measured. `tests/sofa/test_audit1023_p9_both_sides.py`, `test_audit1023_wiring_both_sides.py`, `test_audit1023_wiring_p9_players.py` |
| `CS2_SERIES_ONLY_MODEL_P_FROM_UTC` (P12 / B12) | `settle_cs2.settle_one`'s series-only path calls `attach_model` (error -> `model_error`, grade kept), read by the SETTLE run's own day and clock (model_p feeds only the next morning's line evidence, never a built coupon); earlier series once through `settle_cs2.py --attach-series-only-model --sweep-from 2026-09-28 --sweep-to <D-1>` (offline, DB read-only, SETTLED `series_only` records, rows without `model_p` only, idempotent, refuses `SWITCH_OFF`) - run on the 10-24 morning before `refresh_line_evidence.py`. A settle writing meanwhile keeps the attached `model_p` (`settle_cs2.keep_attached_models`, re-read under the file lock; review R1 F3). No measurement | dry run on copies (clock 10-24 06:00Z): 116 series, 392 W/L lines, 346 get `model_p` (match_winner 194, team_maps 48, maps_handicap 40, exact_maps 36, maps_total 28), 46 without (unrated pairs; days <= 10-23 read the old estimator), 0 errors. `tests/sofa/test_audit1023_p12_cs2_series_only_model.py` |
| `VB_GOLDEN_SET_FROM_UTC` (P13, model side) | `score_model.parse_event(golden_set=True)`: a volleyball match followed by a golden set (Sofascore AET / AGS) enters the score-model history and sample games on its own sets (complete match to 3, sets equal `current`), via `sport_confidence.parse_history` / `TeamGames.build(golden_set)` from `run_sport_confidence._shadow_model`; fits and `settled_shadow_rows` stay off until a refit. The settlement side is a correctness fix live 2026-10-23 without a switch (`shadow.GOLDEN_SET_DESCRIPTIONS`: FINISHED, winner from the sets, never `winnerCode`; the golden set in `overtime` counts in nothing - Regulamin 5.D.3.a) | cache 90 AET / AGS games: 89 parse (15670573 refused, sets 3-0 vs `current` 3-1); `winnerCode` names the tie's winner on 28 of 90 (12193496: sets 3-1, winnerCode 2); 0 settled records on such a match, nothing to re-settle (`scripts/sofa/measure_audit1023_p13_golden_set.py`); history +89 games, the latest 2026-05-01 (no effect on 10-23's p). `tests/sofa/test_audit1023_p13_golden_set.py`, `test_audit1023_wiring_score_history.py` |
| `TENNIS_RATING_SCORE_WINNER_FROM_UTC` (P14 / B14) | `tennis_rating.parse_event(score_winner=True)` / `load_history(score_winner=)`: an "Ended" match with no `winnerCode` takes its winner from a complete set score (`winner_from_sets`; Retired / Walkover / Defaulted never, winnerCode 3 never), and a type-0 side that is not a team (not national, no "/", no subTeams) is a player; a match is a women's when either side says "F" (review R2 #5). No measurement required; the offline count (`scripts/sofa/measure_audit1023_p14_tennis_rating.py`) and SHEET's wiring (`load_tennis_rating` by the built day and clock) are done: SHEET `run_sheet.load_tennis_rating` reads it by the built day and clock (rating rebuilt per run, no cross-day cache); history 261,184 -> 261,357 matches (+173, 0 lost); 10-23: the same 184 of 187 fixtures rated, largest home-win move 0.018 (one > 0.01). Tennis SHEET rows carry no marker for it. Installed tennis curves fitted on a replay without it; a later refit replays it | 17362029 (ITF M15 Ithaca, 6-0 6-1, winnerCode null) enters the rating only under the switch; `tests/sofa/test_audit1023_p14_tennis_rating.py` |

Wiring smoke (offline, 10-23 inputs copied, DB copy, P7 / P8 / P13 flipped on
10-23 at clocks 08:51Z and 14:00Z): 0 legs and 0 p changed in every sport
(hockey 513 / basketball 58 / volleyball 0 / CS2 6 legs at 08:51Z) - no unrated
CS2 pair among that day's open identified series.

### Confidence review 2026-10-27 (2026-10-28 00:00Z; operator 2026-10-27: fix every defect, refit what is needed, standing go of 10-15; ledger group "od 10-28")

Literature review of every sport's confidence path, three passes each; report
`docs/sofa/history/PRZEGLAD_PEWNOSCI_2026-10-27.md`. On from 10-28 00:00Z:
- `JOINT_FILLED_SIDE_CHAIN` (R1, `bet.sofa.centre_chain`): a football joint's side with no quoted ladder gets the centre chain its marginal row gets (opponent correction, venue prior, GAME_STATE, stretches, referee, season phase) - the chain the joint curves' replay already applied. Our settled days 10-21..10-26, 4,102 filled-side rows / 1,370 matches: log loss -0.0000 [-0.0025, +0.0025] - neutral, a consistency fix; rows carry `JOINT_SIDE_CHAIN`.
- `TENNIS_SET_HANDICAP_NEIGHBOURS` (R2, `tennis_rating.read_set_handicap`): per-set games handicap from the rating neighbours' own set scores, not an independent (rho 0) joint (which put 0.256 on a level set margin, real 0.0002). History 442,470 rows / 14,792 matches log loss 0.5509 -> 0.4863 (+0.0646 [+0.0613, +0.0680]); settled Superbet lines 10-14..10-26 5,260 / 399 matches 0.6657 -> 0.6215 (+0.0442 [+0.0215, +0.0668]). No curve key exists; line evidence reads them. Rows carry `SET_HANDICAP_NEIGHBOURS`.
- Basketball and CS2 curves with a pool-adjacent-violators pass only (no refit; `sport_confidence.monotone_curve`), `config/sofa_sport_confidence_calibration.next.2026-10-28.json`: Superbet lines log loss basketball -0.00012 [-0.00017, -0.00007], CS2 -0.00005 [-0.00009, -0.00001]; hockey / volleyball byte for byte the 10-24 curves.
E2E: SHEET / CONFIDENCE / SPORT_CONFIDENCE / COUPON_ASSEMBLY of a scratch copy of 10-27 with the switches moved to 10-27 - all OK; vs a switches-off control only rows marked R1 (326, mean dp +0.0003) and R2 (1,012, mean dp +0.0008, p5..p95 -0.35..+0.35) move.

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

Confidence review 2026-10-27 (code in, switch `None` / fit option default off;
`docs/sofa/history/PRZEGLAD_PEWNOSCI_2026-10-27.md`):
- `HK_LATE_GOAL_IN_MEAN` (R3): the empty-net late goal was added on top of a P3 mean that holds it (P3 2.189 vs 2.05 simulated). Raw p: P3 better on the 30-day holdout (-0.00169 [-0.00318, -0.00040]), not over 12 months; full winner / handicap +0.0013 / +0.0006 worse on the holdout. The hockey refit with it on was worse than the 10-24 curve (holdout +0.00060 [+0.00030, +0.00092], Superbet +0.00139). Off.
- `CS2_DECIDER_MAP_POSTERIOR` (R4): Bo3 map 3 at p is (pK+1)/(K+2) under the series Beta. Raw p calibrated (map 3 p>=0.65 gap -4.8 -> +0.15 pp; log loss -0.00243 [-0.00449, -0.00040] on 7,174 rows), but the CS2 refit with it on was not better than the 10-24 curve (holdout +0.00019 [-0.00004, +0.00041]); live p is read through a curve fitted on the old p, so off until a CS2 refit carries it and measures better.
- `FIRST_GOAL_NB_EXACT` (R5): the first-goal split exact under NB goals (Poisson ratio overstated the favourite 0.7-0.9 pp). Raw p +1.7e-5 [-9.3e-5, +1.3e-4]; the refitted first_goal curve worse (+1.2e-3 [+0.7e-3, +1.7e-3]). Off.
- Tennis rating fit on best-of-three only (`tennis_rating.fit_coefficients`; the old filter kept bo5 3-0 wins: selection on the outcome): winner log loss -0.9e-5 [-4.5e-5, +2.6e-5] - neutral, nothing staged; applies to the next tennis rating fit. Dated loader `tennis_rating.params_path_for` (`tennis_rating.next.<d>.json`) exists, none staged.
- Sport curves with Kish effective n and PAV (`fit_sport_confidence.py` defaults on) refitted before 2026-10-28: none better than the 10-24 curves (basketball holdout -0.00028 but Superbet +0.00254; volleyball Superbet +0.00158) - not staged. CS2 Elo burn-in 30..150 days: holdout worse (90 d +0.00019 [+0.00006, +0.00031]), default 0.
- Football / tennis curve PAV: -2e-8 [-1.6e-7, +1.3e-7] on 15.86M rows (10 keys non-monotone, 0.001-0.017) - not installed.

| constant | measurement | evidence |
|---|---|---|
| `FOOTBALL_LEAGUE_RATE_RULE_FROM_UTC` | A2's football half: rating at the all-league rate beat the sample alone in thin competitions, squared error -0.58 [-0.62, -0.54] per side in its favour | `docs/sofa/history/RAPORT_IMPLEMENTACJI_AUDYTU_2026-10-13.md` |
| `UNIT_STRENGTH_FROM_PARENT_FROM_UTC` | A1: regional unit's strength from its competition's; goals log-loss -0.0010 [-0.0029, +0.0008] on 7,724 cross-unit matches | `scripts/sofa/measure_unit_strength.py` |
| `CS2_MAP_IDENTITY_FROM_UTC` | B11 map order / pool terms; walk-forward 24,995 maps / 11,217 series, +0.00021 [-0.00022, +0.00064] | `docs/sofa/evidence/cs2_map_identity_2026-10-13.md` |
| `HK_SHOTS_FROM_UTC`, `HK_EMPTY_NET_FROM_UTC` | B8 hockey shots x save%: centre replaced total +0.00126 [+0.00010, +0.00241] worse, blend +0.00025 [-0.00033, +0.00084]; fitted empty net handicap -0.00037 [-0.00074, +0.000006], total +0.00111 worse; shots exist for 6,755 of 29,516 games, none in October 2026 | `docs/sofa/evidence/hockey_goalie_empty_net_2026-10-13.md`, `docs/sofa/history/RAPORT_B8_HOKEJ_2026-10-13.md` |
| `VB_SET_LENGTH_FROM_UTC`, `VB_SET_HISTORY_FROM_UTC` | B9 / C10 volleyball set length, 5,050 matches walk-forward: points_total +0.0025 [-0.0005, +0.0054], points_handicap -0.0011 [-0.0036, +0.0013], set_extra_points -0.0004 [-0.0014, +0.0007]; C9 not measured (depends on B9) | `docs/sofa/evidence/volleyball_set_length_2026-10-13.md`, `docs/sofa/history/RAPORT_B9_C10_C9_2026-10-13.md` |
| `BB_OVERTIME_FROM_UTC` | A3 overtime in the basketball replay: regulation 1X2 -0.00354 [-0.00719, -0.00015], totals / winner no better; as a curve variant +0.00113 [-0.00123, +0.00353] | `docs/sofa/evidence/basketball_refit_2026-10-13.md` |
| `BB_PACE_FROM_UTC`, `BB_PACE_LEVEL_FROM_UTC` | B7 / B7b basketball pace x efficiency (`score_model.PACE_METRICS`; `fit_sport_confidence --bb-pace` / `--bb-pace-level`); live only with a basketball curve refitted on it | `docs/sofa/evidence/basketball_pace_2026-10-13.md`, `docs/sofa/evidence/basketball_pace_level_2026-10-13.md` |
| `PLAYER_HISTORY_ANY_TEAM_SPORTS` without basketball (audit 2026-10-23 P3) | basketball any-team reader on settled Superbet player lines 09-29..10-22: common sides log loss -0.0013 [-0.0045, +0.0019]; 2,015 added favoured sides claim 0.627 hit 0.544, -0.083 [-0.115, -0.052] (over-claim). A basketball refit on the any-team reader not run (one objective > 12 min, ~60 evaluations) - open | `docs/sofa/history/AUDYT_POKRYCIA_WDROZENIE_2026-10-23.md`, `scripts/sofa/measure_audit1023_p3_player_any_team.py` |
| `BB_HALVES_LEAGUES_FROM_UTC` (audit P11) | NCAA basketball in halves (`score_model.BB_HALVES_COMPETITIONS`: 33651 NCAA Men's D-I 5,940 of 5,943 Ended games in 2 periods, 648, 33653, 13434, 33654, 33652, 18640; `basketball_halves`), parsed as the regulation sum only; wired into SPORT_CONFIDENCE. Off: no NCAA basketball in Superbet's offer (SHADOW 09-29..10-24 none; by-date offer to 11-12 on 10-23 none; struct "USA - NCAA" 36 / 2108 / 33447, "(K)" 2175 / 33361, sport unknown), halves not settleable (`shadow.build_result` wants four quarters, `_pair` h1 / h2 read quarters), the installed curve fitted without NCAA and NCAA games move `RatingBook.global_league` (other leagues' expectations; synthetic `period_sd` 0 -> 0.13). Before on: halves settlement, NCAA replay of the curve, the global-rate effect | `tests/sofa/test_audit1023_p11_halves.py` |
| `sport_identity.QUERY_ANCHOR_SPORTS` without hockey / basketball (audit P4) | measured clean (hockey 0 wrong / 4,985, recall 4; basketball 0 / 5,760, recall 15, every known settle agrees) but outside the plan's scope; adding them is the operator's call, from a next day | `scripts/sofa/measure_audit1023_p4_query_anchor.py` |
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
NOT_IN_HISTORY names; `docs/sofa/history/RAPORT_K7_K8_POMIAR_2026-10-14.md`):
audit P3 - hockey and football on from 2026-10-24, basketball measured worse and off
(section a / b).

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

Re-measured 2026-10-26 on 20,367 settled Superbet lines (312 matches, 09-18..10-25,
match bootstrap; `docs/sofa/evidence/tennis_serve_markets_2026-10-26.md`, plan
`tennis_serve_markets_plan_2026-10-26.md`): shipping p >= 0.70 -> 2,778 legs at
0.781 claimed, 0.548 realised, ROI -10.1%; Brier worse than the price
(+0.0302 [+0.0205, +0.0401]); a curve fitted on market-like lines never reaches
0.70. Superbet's aces / serve-points lines realise at their price against our
grades; the model's centre is biased for serve points (+5 pp OVER) and double
faults (+7 / +18 pp). Double faults: line 5.79 vs realised 4.97 (OVER 32.5%),
gap narrowing; UNDER +6.8% [+0.9, +13.5] found post hoc among 36 cells - a
lead, forward test `T-TENNIS-DF-UNDER-FORWARD` (from 10-27). Still off; a
bottom-up model (points -> games -> sets) awaits the operator's go.

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
| hockey refit 2026-10-23 | staged 2026-10-23, read from 2026-10-24 00:00Z (`config/sofa_sport_confidence_calibration.next.2026-10-24.json`, the dated staged chain of `sport_confidence.calibration_path_for`; 10-14..10-23 keep reading `.next.json`) | hockey section only: `fit_sport_confidence.py --sport hockey --before 2026-10-23 --league-rate-rule` (fit 2025-09-23..2026-09-23, 785,934 rows; holdout 09-23..10-23, 647,144 rows / 3,375 games; no season restart, no A7); new-market DC curves carried; basketball / volleyball / CS2 sections byte-identical to `.next.json`. Settled Superbet lines 09-29..10-21 (out of sample for both): log loss -0.00048 [-0.00062, -0.00033] (71,948 lines / 1,788 games; `handicap` alone +0.00224 [+0.00187, +0.00262] worse); confidence >= 0.70 -0.5 pp [-1.5, +0.5] -> -0.2 pp [-1.2, +0.8], difference +0.30 pp [+0.13, +0.49]; history holdout +0.00003 [-0.00002, +0.00008], >= 0.70 +0.8 -> +0.9 pp. Pre-registered `T-HOCKEY-REFIT-1024` (PROPOSED) | DB copy `data/refit_2026-10-23/sp.db` deleted; rows / comparisons kept in `data/refit_2026-10-23/`; `docs/sofa/history/REFIT_HOKEJ_SIATKOWKA_2026-10-23.md` |

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

Sport curves: volleyball / CS2 = the installed sport file's (CS2's
B10 curve promoted 2026-10-14, bc69b56e); basketball = the staged `.next.json`
(A7 + hybrid); hockey = the 10-07 curve through 10-23, from 10-24 the
2026-10-23 refit (`.next.2026-10-24.json`).

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

- football team-side legs against the opponent's concede profile (2026-10-29,
  after the operator's slips of 10-28: Panathinaikos corners over 3.5 - own
  9/10, Aris conceded it 3/10 - lost with 2; read-only,
  scratchpad `opp_concede.py`): printed football `corners_for` /
  `corners_1h_for` / `shots_for` / `shots_on_target_for` / `both_over_corners`
  singles 10-13..10-27 with WIN / LOSS, 2,314 legs / 615 matches; opp_rate =
  share of the opponent's last 10 competitive games with stats in which ITS
  opponent reached the leg's line. Flag opp_rate < confidence - 0.15: 411 legs
  (18%, ~27 a day) realised -4.8 pp vs confidence [-10.2, +0.3], -6.1 pp vs
  1/odds [-11.3, -1.2]; flagged minus unflagged -6.5 pp [-12.0, -1.0] vs
  confidence; own-sample control +0.2 [-8.5, +8.3]. **Not robust**: tertiles
  of opp_rate do not rise, the logistic term (logit(conf) + rate - conf) is
  +0.46 [-0.49, +1.31], the pooled effect is carried by `corners_1h_for` (71
  legs, -13.2 pp [-23.9, -2.5], one cell of ~30), `corners_for` -3.3 pp
  [-9.6, +2.8]. A suspicion: no gate, no removal; shown as the dossier's
  `style.matchup` and the KUPON html "zestawienie" tag. Re-measure out of
  sample (from 10-28) before any gate, `corners_1h_for` first. Operator
  2026-10-29: such a signal is never skipped - from reports of 2026-10-29 (moved from 10-30 by the operator) an
  analyst / verifier WATCH may rest on it (`RYNEK: ... k/n`, `context:
  "MARKET"`, share >= 0.25 below confidence or the < 50% possession bucket on
  >= 4 games; never NO_BET; `report_check`). No gate, no confidence change; the
  MARKET-tagged `removed_by_reads` legs graded in the ledger are the
  out-of-sample measurement (a removal of a leg that would have won costs its
  price) - audit them by tag before widening it.
- basketball player model, three corrections measured offline 2026-10-26 (operator: "wazne jest aby rozliczac rynki nba wszystkie"; `docs/sofa/evidence/nba_player_model_2026-10-26.md`): a **form term** (mean model residual of the last 5 games, slope +0.13 [+0.11, +0.14] on 255k test player-games, log-loss -0.0017, but NBA 2026-27 -0.06 [-0.15, +0.04], 41 games, and p >= 0.70 lines 372 -> 337), a **directional calibration** per market and side (test log-loss -0.0010, NBA 2026-27 +0.0026 with the CI off zero, Superbet lines no gain, UNDER >= 0.7 still overconfident) and a **top-up for movers** (own sample < 5 -> up to 20 appearances of the same player id for other teams: 59% of thin player-games priced, 94% in NBA 2026-27, beats the pool mean by -0.132 log-loss, but 0.663 vs 0.645 for normal p, and on settled Superbet lines log-loss 0.719 > 0.693). None installed. Re-measure with the same scripts when NBA 2026-27 has ~200 games (late November 2026), NBA and other basketball apart.
- the football / tennis curves refitted on the fuller history (2026-10-22/23,
  operator's go ~21:30Z "install where measurement shows improvement"; replay
  on the copy `data/refit_2026-10-22c/fb.db` with the installed flags plus
  `--closeness-stretch --player-coverage`: 1,302,366 matches / 127.0M rows vs
  1,282,317 / 121.9M of 10-17 - the backfill added +1.6% matches; no
  football-only fit exists, both sports fitted, tennis history incomplete):
  candidate fitted without matches / live rows from 10-18 vs the installed
  curve, history holdout 10-18..10-22 (1,712 matches, 302 football) log loss
  -0.4e-4 [-1.2, +0.4] (football -0.8 [-2.0, +0.5], tennis +0.3 [+0.0, +0.7],
  tennis_women +1.2 [+0.5, +1.9] worse); >= 0.70 realised - confidence +0.26
  -> +0.31 pp; settled Superbet lines from 10-18 by group: gated gap moves
  <= 0.17 pp, log loss intervals across zero for football. Not installed, no
  staged file, no epoch (`docs/sofa/history/REFIT_PILKA_2026-10-22.md`). The
  per-line curves are refitted by the same fit (43 / 76 keys unchanged) and
  were measured with it - no separate refit. A football / tennis refit is
  worth repeating only when the replay grows materially (the stats backfill
  reaching matches the replay lacks), or with referee / player share
  replayable;
- a goals_for dispersion fix and a refitted double-chance r (2026-10-22,
  pre-registered, history replay with today's centre - rating weight, goals
  stretch v2, season phase, cup strength - TRAIN 2025-07..2026-03, TEST
  2026-04-01..10-21, 164,251 matches): SHEET's goals_for NB is too WIDE, not
  too narrow (variance ratio 0.888 [0.880, 0.897], PIT tail mass 0.191);
  alpha + d (d -0.065) ladder log loss -1.39e-4 [-1.93, -0.86] raw but
  +0.38e-4 [+0.16, +0.64] after a calibration map, second test half +1.39,
  1X2 +1.53e-4 worse; DC r 21.4 -0.76e-4 [-1.69, +0.18], btts +25.7e-4
  worse. DC p on history realises ABOVE p at >= 0.70 (+0.5..+1.2 pp);
  goals_for after a map within ~1 pp (UNDER -0.81 pp). The live
  goals_for / double_chance gaps (DIAGNOZA 2026-10-22) are not the
  distribution's shape. Open suspicion: the goals_for centre under-shrinks
  (low centre sides +0.11 goals, high -0.05). Not installed, no switch
  (`docs/sofa/history/POMIAR_GOLE_DRUZYNY_2026-10-22.md`);

- the basketball curve refitted on the season-restart rule (2026-10-22,
  operator's go ~19:40Z with "install only if not worse"; `fit_sport_confidence.py
  --sport basketball --before 2026-10-23 --bb-freshness on --league-rate-rule
  --league-season-restart --market-lines data/a7_odds/basketball.jsonl` on the
  copy `data/refit_2026-10-22b/bb_refit.db`; fit 2025-09-23..2026-09-23): on
  settled Superbet lines 09-29..10-21 (152,276 / 2,229 games, p with the
  restart for both curves, both out of sample) log loss new - installed
  +0.00078 [+0.00065, +0.00093] (NBA, 8 games, +0.00075 [+0.00019, +0.00132];
  other +0.00078 [+0.00064, +0.00092]; h1_total +0.0068, h1_team_total
  +0.0043 worse, quarter_handicap -0.0012, h2_handicap -0.0010, total -0.0003
  better); confidence >= 0.70 -11.8 pp [-15.2, -8.2] -> -11.9 pp [-15.3, -8.4]
  (NBA +2.4 -> +2.0 pp, 139 lines); history holdout 09-23..10-23 -0.00008
  [-0.00011, -0.00005] (NBA 14 games -0.00001 [-0.0005, +0.0006]). Same
  picture as the 10-16 full-cache refit: a newer window worsens the half /
  team-total families. Not installed, no epoch; a key-subset hybrid would be
  chosen after the result (`docs/sofa/history/REFIT_KOSZ_SEZON_2026-10-22.md`).
  (Since 2026-10-23 a dated staged file `.next.<YYYY-MM-DD>.json` carries a
  later day's sport curves without promoting `.next.json`.);
- the volleyball refit on the fuller history (2026-10-23, `--before
  2026-10-23 --league-rate-rule`): settled Superbet lines 09-29..10-21 log
  loss -0.00080 [-0.00137, -0.00023] (18,210 lines / 922 games), >= 0.70
  -6.9 -> -6.4 pp (+0.56 pp [+0.50, +0.63]), holdout -0.00013 [-0.00028,
  +0.00002] - but the whole gain is `set_winner` (-0.0063), a settled-only
  family (`settled_only_families`) refitted from our settled lines
  09-29..10-09; with the history-fitted families alone -0.00003 [-0.00046,
  +0.00041], and the refit would add three curves from our days alone
  (`set_points_total` OVER, `set_points_odd_even`). Not staged (hard rule:
  our settled days are an audit, never a curve's source). Both curves
  overstate `points_handicap` (-26 pp, 251 lines) and `points_total` (-22 pp,
  53 lines) at >= 0.70 - `measure_sport_curve_swap.py`'s own verdict
  `install: false` (`docs/sofa/history/REFIT_HOKEJ_SIATKOWKA_2026-10-23.md`);
- the league-rate season restart for hockey and volleyball (2026-10-22, both
  sides at the fast step, K 10, the basketball walk-forward's method): hockey
  +0.0005 [+0.0002, +0.0009] log loss per line on 6,169 games (2026-09.. start
  +0.0022 [+0.0013, +0.0032]), volleyball +0.0012 [+0.0005, +0.0020] on 5,373 -
  their league levels do not drift between seasons; the level-only form was
  not measured for them
  (`docs/sofa/history/NBA_SEZON_STAWKA_LIGI_2026-10-22.md`);
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

- **NBA player lines (2026-10-26)**: why no leg prints (p sits at the median by the book's construction, new markets have ~25 games of lines, p overconfident in the top buckets) is in `docs/sofa/evidence/nba_player_model_2026-10-26.md`; open: re-measure at ~200 NBA 2026-27 games; NBA-specific calibration term; a box that sums to the score +-1 point (Milwaukee - Chicago 10-23, 494 lines ungraded; today refused by design); `NOT_IN_HISTORY` outside the NBA.
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
- Basketball period spread by league (2026-10-22, not switched): NBA
  quarters / halves read 2.5 / 1.4 pp overconfident out of sample at curve
  >= 0.70 while other leagues read +0.9 / +1.2 (NBA quarter-side residual SD
  5.98 vs the pooled 5.20, `bb_sd_level_power` 0); the season restart leaves
  it (NBA printable rows -2.0 pp both arms). A level-scaled spread was
  declined 2026-10-03 on pooled windows; a per-level or per-pace spread
  needs its own measurement and switch
  (`data/refit_2026-10-22/nba_measure/nba_measure.md` section 2).
- A basketball refit on the season-restart rule: done with the operator's go
  2026-10-22 and NOT installed (section (d)); the installed curve (10-14 A7 +
  10-15 hybrid) stays, p moves by the rule from 10-23.
- `fit_confidence` reads every `sofa_settled_row`, live rows included: a market
  the replay never prices (tennis serve points, per-set aces / double faults,
  tiebreaks) gets its curve from our settled days alone - against "curves
  from the history". The installed file carries such keys from earlier
  refits; the 2026-10-22c candidate froze them to the installed values
  (`data/refit_2026-10-22c/freeze_live_only.py`). Hardening item: exclude
  live rows from the fit, or freeze those keys in the tool.
- Football staging exists: `confidence.calibration_path_for` reads
  `config/sofa_confidence_calibration.next.json` from its `effective_from`
  (CONFIDENCE, `fit_line_evidence`); `run_coupon.py` (06) reads the installed
  file; `install_line_curves.py` refuses beside a `.next.json`.
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
- **Data-coverage audit 2026-10-23** (`docs/sofa/history/AUDYT_POKRYCIA_2026-10-23.md`;
  implemented `AUDYT_POKRYCIA_WDROZENIE_2026-10-23.md`, section (a) "Coverage audit
  2026-10-23"): on from 2026-10-24 00:00Z P1, P2, P3 (hockey, football), P4 (volleyball),
  P5, P7, P8, P9, P12, P13, P14. Still open: P3 basketball (measured worse; a refit on the
  any-team reader not run), P4 hockey / basketball (clean, out of scope - operator's
  call), P6 (measured worse), P11 (no NCAA basketball on Superbet; halves settlement
  missing), the football referee record (~half its matches; incidents backfill run).
  Volleyball QVL 2345 -> 39366: not a defect (no 25/26 season at the source).

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
| "od 10-24" | 10-24 .. | current; LIVE_ONLY_CURVE_REFUSED 00:00Z - 50 installed tennis curve keys fitted from live rows alone are not read (serve points, per-set aces / double faults, tiebreaks); the hockey refit of 2026-10-23 read from 00:00Z (`.next.2026-10-24.json`); the coverage audit's switches 00:00Z (P2 identity re-ask, P3 hockey + football any-team players, P5 football player slug, P1 ENTITY_CONFLICT sample cut, P4 volleyball query anchor, P7 CS2 unrated lineup rating, P8 name rules, P9 both-sides lists, P12 CS2 series-only `model_p` (evidence only), P13 volleyball golden set in the history, P14 tennis rating score winner) |
| "od 10-23" | 10-23 | SPORT_LATE_WINDOW 00:00Z - a day's measured-sport legs run to D+1 05:00Z (the evening rebuild's), a scope change of the coupon; LEAGUE_SEASON_RESTART 00:00Z - basketball's league rate restarts after an off-season (basketball p moves) |

| "od 10-27" | 10-27 | the analyst audit's read scope (20 matches) and sourced removals |
| "od 10-28" | 10-28 .. | current; confidence review: JOINT_FILLED_SIDE_CHAIN (R1), TENNIS_SET_HANDICAP_NEIGHBOURS (R2) 00:00Z, monotone basketball / CS2 curves (`.next.2026-10-28.json`) |

There is no group "od 10-17": PLAYER_SAMPLE_GATES 00:00Z falls in "10-17 mieszany".

Boundaries are constants in `scripts/sofa/audit_ledger.py` (`*_MIXED_DATE`,
`*_EPOCH_FROM_DATE`); moving a switch must move its boundary.
