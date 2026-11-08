# R1 - schedule / fatigue residuals: data and replay machinery (2026-11-08)

Read-only. Live `data/sofa.db` opened `mode=ro` only, every query a rowid / PK / index range; no network, no refit, no repo edit.
Scratch scripts: `.../scratchpad/cov.py`, `cal2.py`, `cross.py` (same directory as this file). Sampled numbers are estimates and say how they were sampled.

## 0. Prior work you must not redo blind

| what | where | result |
|---|---|---|
| Schedule context vs **raw sample mean** (makeup / rest bins / >=21 d / congested) | `scripts/sofa/measure_schedule_context.py` (188 l.), result `docs/sofa/history/RAPORT_2026-10-04_POROWNYWALNOSC_HISTORII.md:114-139`, table `data/analysis_2026-10-04_history/schedule_context.md` | 293k league matches: makeup no bias; **both sides >= 21 d idle: goals -0.122 [-0.155; -0.092], corners -0.280 [-0.452; -0.108]** vs the sample. Never measured vs the model centre or the price. Became display flags only (`MAKEUP_FIXTURE`, `LONG_LAYOFF`, `CONGESTED`). |
| Live as-of schedule module | `src/bet/sofa/schedule.py` (`side_schedule`, `fixture_schedule`, `LONG_LAYOFF_DAYS=21`, `CONGESTED_7D=3`), called by SAMPLES `src/bet/sofa/samples.py:2331`, written to `03_samples.json` `schedule` | rest days, matches 7d/14d, makeup, other_division - already computed live per fixture (the live feature path exists). |
| Feature battery vs **Superbet price** (p-level, settled lines 09-28..11-04, dev / one hold-out, BH q=0.10) | `scripts/sofa/measure_feature_battery.py` (features C01-C11 at `:223-240`, computed `:850-890`), `docs/sofa/evidence/bateria_statystyk_2026-11-05.md` | C01 rest home: 17 BH passes of 126 cells (football shots/SOT totals, e.g. shots_total -0.70e-3 Brier [-1.03; -0.36]), C02 13, C03 7, C04 back-to-back 0/67, C05 congestion 4, C06 2, **travel C07/C08 0/80** (venue city absent for football), C11 knockout 5. No cell closed a large gap to the price. Tennis was out of scope. |
| Template for a centre term fitted as-of | `src/bet/sofa/season_phase.py`, `scripts/sofa/measure_season_phase.py`, `scripts/sofa/fit_season_phase.py`, evidence `docs/sofa/evidence/season_phase_2026-10-13.md` | exactly the design you want: as-of index, centre from `centre_replay`, Poisson-MLE log(Σy/Σcentre) per bucket, monthly walk-forward, NB log-loss with installed dispersion, match bootstrap, replay flag `--season-phase`, switch `epochs.SEASON_PHASE`, live hook in `run_sheet.py:31,200`. |

## A. Data for as-of schedule features

### A1. Calendar tables

| table | one row = | key columns | size (this session) |
|---|---|---|---|
| `sofa_entity_events` | one cached listing PAGE of one entity (`/team/{id}/events/last|next/{page}`), JSON of ~30 events | PK (entity, kind, page); `events_json` | 155,541 rows (last 141,854 / next 13,687); page 0 = newest, overwritten on refetch |
| `sofa_listing_event` | (entity whose `last` page showed the event, event id, start_ts) - the never-forget index (`src/bet/sofa/listing_index.py:1-50`) | PK (entity_id, kind, event_id); index (entity_id, kind, start_ts) | 3,332,488 |
| `sofa_listed_event` | one event payload per id (newest fetch wins), `sport`, `start_ts`, full listing `event_json` (teams, tournament, uniqueTournament, season, roundInfo, status, scores, periods, tennis `time`, `groundType`) | PK event_id; index (sport, fetched_at, event_id) | football 1,185,873; tennis 371,855; others ~293k |
| `sofa_event_detail` | `/event/{id}` payload (`{"event": ...}`) | PK id | max id 17.52M; for **finished football only ~2.5%** have one (1,289 of 51,706 sampled), ~4.5% of football events with stats |
| `sofa_event_stats` | statistics / incidents / post-match lineups per event | PK id | see A6 |
| `sofa_event_extra` | kind `point_by_point` 97,409 (tennis), `shotmap` 24,770, `incidents` 9,830 | PK (id, kind) | 132k |
| `data/cache/football_history.pkl` | parsed `FootballResult` list SHEET keeps (`football_rating.load_history`, fingerprinted; rewritten by SHEET - copy it) | ts, competition_id, home/away id, values, season_id, stage_id, `knockout`, `awarded`, `women`, reserve flags | 1,085,675 non-friendly matches after `without_awarded`; 2024 255k, 2025 380k, 2026 326k. **Friendlies excluded** (`football_rating.py:365`). |

**Does a team's calendar include all competitions?** Sofascore's team `last` listing is the team's whole calendar (league, cups, continental, friendlies). Verified on 28 football teams (`cal2.py`, 22 random verified board teams + 6 big clubs, 2025-08-01..2026-11-08): Real Madrid 77 events (LaLiga 49, UCL 18, friendlies 6, Copa 2, Supercopa 2), Bayern 80 (BL 42, UCL 18, Pokal 8, friendlies 8, supercups 4), Legia 77 (incl. UECL 8, UEL 2, Puchar 2, friendlies 17), Celtic 87, Inter 80, Barcelona 80; lower teams show their league + cups + friendlies too. Big clubs' longest gaps are real breaks (2026-05-23 -> summer; 2026-09-20 -> 10-10 = the merged FIFA Sep/Oct 2026 window - checked event by event for Real / Bayern, no hole).
Holes come from **fetch history, not from Sofascore**: a side whose listing was never fetched, or a page that slid out before being indexed.

Coverage test (`cross.py`; events with statistics sampled across id windows 11M..17.5M; for each side: is the event in that side's own `sofa_listing_event`?):

| sport | sides | on own listing | own listing has rows within ±30 d but not this event | side has no listing near the date |
|---|---|---|---|---|
| football | 660 | 619 (93.8%) | 10 (1.5%) | 31 (4.7%) |
| tennis | 730 | 607 (83.2%) | 16 (2.2%) | 107 (14.7%; 2023: 35/78) |

Implication: build the calendar from the **union** over all listings (scan `sofa_listed_event` by team ids in the JSON), not from a side's own listing. That union is cheap: 99k football rows with 6 `json_extract`s in 7.0 s -> **~85 s for all football, ~30 s tennis** (measured). It still misses a match no listing of either side ever showed (the 4.7% / 14.7% "no listing near" sides are mostly obscure opponents; SUSPICION: for sides we price the hole rate is near the 1.5-2.2% row). Tennis players with few pages (`pages=(2,1)`) show 100-180 d gaps (Rocha 108 d, Mititelu 178 d) - injury or hole, not separable without a fetch; SUSPICION holes.
Tennis listings include the player's **doubles** (pair entity ids, players in `subTeams`) - needed for workload, and absent from `tennis_point_model.load_point_history` (singles only).

### A2. Competition type
- `bet.sofa.comparability.match_kind` -> `REGULAR / KNOCKOUT / FRIENDLY` (`src/bet/sofa/comparability.py:44-47, 137 is_friendly_event, 174 is_knockout, 188 match_kind`); friendlies from `config/sofa_friendly_competitions.json` (`excluded` 79 ids, `excluded_other_sports` 5, `allowed` 1) plus name regex `_NON_COMPETITIVE` (`:86`).
- `FootballResult.knockout` already in the history pickle (40,192 knockout of the post-2025-08 matches).
- Continental club cups: `config/sofa_cup_strength.json` `competitions` = [7, 679, 17015, 463, 668, 384, 480, 1054, 498] (UCL, UEL, UECL, Libertadores, Sudamericana, AFC ...), loader `src/bet/sofa/cup_strength.py:34`.
- National teams: `homeTeam.national` in every event JSON. Tennis tier: `tennis_rating.tier_group` (ITF / CH / TOUR, in `PointMatch.tier`); `uniqueTournament.tennisPoints` only on ~15% of rows (sample 2026: 1,251/7,428).

### A3. Venue / travel / time zone
- `sofa_listed_event` has **no venue** (key census of 1,914 finished football and 1,922 tennis listing payloads: `venue` 0). The battery hit the same wall (`bateria_statystyk_2026-11-05.md:850`).
- `sofa_event_detail.event.venue` (city, country, `venueCoordinates` lat/lon, capacity) exists only where `/event/{id}` was fetched: among football events with stats ~4.5% (128/2,854 sampled; coordinates on 126). Tennis venue city on ~9% (194/2,115 of 2026), never coordinates.
- Always available: `homeTeam.country.alpha2`, `tournament.category.country` -> crude cross-border / time-zone shift. `config/sofa_country_timezones.json` (247 single-zone countries, 31 multi_zone; used by `settle.void_deadline`).
- Backfill options (network; NOT done): per team `/team/{id}` (SUSPICION: carries home venue with coordinates) - ~10.6k football teams with count statistics since 2025-08 (pickle count) -> ~15 min at the measured 11.67 req/s; per event `/event/{id}` ~93k-190k events -> 2.2-4.5 h bridge time.

### A4. Tennis workload
- Set durations: `event_json.time.period1..5` (seconds) in the listing payload, coverage by start year (sample of id windows >= 9M): 2024 69% (2,261/3,292), 2025 30% (1,449/4,774), 2026 39% (2,877/7,428). Match duration = sum of periods.
- Points played (duration proxy): statistics group `Points` item `Total` in `statistics_json` (items list checked: Aces, DF, serve/return points, `Total`, `Total won`, service games...) - wherever stats exist (~73% of tennis events with a stats row).
- Sets / games played: `homeScore.period1..` on every listing payload (also `PointMatch.sets`).
- Retirement / walkover: `status.description` `Retired` / `Walkover` / `Defaulted` (2026 sample: 240 / 118 / 0 of 7,428); `dossier.recent_retirement` already uses it.
- Surface: `groundType` on 98-99% (Hardcourt outdoor / indoor, Clay, Red clay, Grass...); `PointMatch.surface`.
- Point-by-point (`sofa_event_extra` kind `point_by_point`): 97,409 finished tennis events; no timestamps inside (sets/games/points only) - not a duration source.

### A5. Coach / manager
- `detail_json.event.homeTeam.manager` / `awayTeam.manager` (and `parentTeam.manager`): {name, id, country}. In the last 3,000 detail rows: 188/191 sides. It is the team's manager **at fetch time**, not at the match (SUSPICION from the payload shape; a detail fetched pre-match by FIXTURE_CHECK is close to as-of, a later backfill is not). Coverage tiny (detail exists for ~2.5% of finished football).
- `lineups_json` has `supportStaff` - empty on 300/300 sampled; no manager.
- Backfill: per event `/event/{id}/managers` (SUSPICION: endpoint exists on Sofascore; not used anywhere in `src/bet/sofa` or `scripts/sofa`). One request per event: ~93k events with count stats since 2025-08 (~2.2 h at 11.67 req/s) or ~190k with any stats row (~4.5 h); new code + cache table needed. Manager-change date = first event whose manager id differs.

### A6. Volume and date range (estimates)
- Events with a non-empty `statistics_json` (1-in-20 id-window sample, x20): football ~10k (2024), ~85k (2025), ~95k (2026); tennis ~0.4k (2024), ~38k (2025), ~101k (2026). Stats essentially start 2024-H2 (football) / 2025 (tennis).
- Football history pickle: matches with count statistics (corners or shots) since 2025-08: **93,320** (monthly 1.5k (06-2026) .. 10.6k (10-2026)); goals for all 1.09M.
- `calibrate_from_cache` loads 1,457,004 played football+tennis matches (`data/refit_2026-11-05_replay/chainA_replay.log` SOFA_SUMMARY `matches_replayed`).
- Referee: `sofa_event_referee` football 80,297 (referee_page) + 5,471 (detail) + 17,522 (event, 52 with id).

## B. Replay machinery

| tool | what it replays | output per (match, side, metric) centre + actual? | runtime (evidence) |
|---|---|---|---|
| `src/bet/sofa/centre_replay.py` `walk()` (`:71-147`) | rating book read strictly before each match (`RatingBook`, updated after), sample = last 10 values shrunk to the book's league rate with per-market K; `FootballForecast.centre`, `supremacy`, `venue_multiplier` | **yes**: `CentreRow(event_id, ts, competition_id, market, side, y, sample, rating, supremacy, venue_mult)`; live centre = 0.5 rating + 0.5 sample (`measure_season_phase.live_centre:162`) | **measured now**: pickle load 1.9 s; whole-history walk with 5 markets, rows for 2026-09..10: 50.5 s, 283,360 rows (283,100 rated). Approximation, not SHEET byte for byte (prior from book, not config; no stretches / referee / form table / cup strength unless passed) - stated in its docstring `:22-27`. |
| `football_sim.walk_forward_centres` (`src/bet/sofa/football_sim.py:448`) | pure rating centres of `CENTRE_METRICS` (goals_for, goals_1h/2h, corners halves, fouls, shots, SOT, cards_points) | yes (rating only, no sample half); cached `data/football_sim_2026-11-06/forecasts.pkl` (206,183 events) | 112 s for 206k wanted (`data/football_sim_2026-11-06/forecast.log`) |
| `scripts/sofa/calibrate_from_cache.py` (3,755 l.) via `prepare_refit.py rebuild-cache-rows` | the full SHEET chain: `live_centre` hook `:1271-1355` (rating blend, venue prior, game state, count/closeness/goals/player stretch, referee, season phase, opponent correction, form table) + SHEET estimator; tennis rating `RatingReplay` | **no**: `SettledRow` (`:779`) = line, direction, sample_size, **sample_mean**, sample_sd, **p_central**, **actual**, outcome - the centre is computed and dropped (`_settle_centred:1937-1940`). Rows go to `sofa_settled_row` run_date `cache-calibration` (or nowhere with `--no-write`). | full replay `rows_seconds` 18,870-23,244 s (5.2-6.5 h), 139.5M rows (`chainA_replay.log`); 5-day window `--from/--to --no-write` with every flag: 5,065 s (`data/refit_2026-11-05_replay/verify/run_window.py` log) - the history and books are always built in full. |
| `scripts/sofa/fit_confidence.py` | fits curves from `sofa_settled_row` | (p, outcome) only | - |
| `scripts/sofa/fit_tennis_point_curves.py` + `tennis_point_model.walk_forward` (`src/bet/sofa/tennis_point_model.py:885`) | point model as of each singles match; `tennis_point_sheet.mean_sd(ms, market, side)` (`:157`) gives the simulated mean per market | forecast per match (`MatchForecast`) -> mean via `market_sim` + `mean_sd`; actual from `PointMatch` / stats; `--rows-out` jsonl.gz is (line, p, outcome) | history load 155 s (`tennis_point_model_2026-11-05.md:297`); 4,000 sims/match 0.18 s per 20k |
| `fit_football_sim_curves.py` | sim keys on walk-forward centres | p rows | uses the pickles |
| `measure_schedule_context.py`, `measure_sample_composition.py` | sample-mean forecast | residual = actual - sample mean (not model) | - |
| `measure_feature_battery.py` | features vs settled Superbet lines | p-level logistic | - |

**Adding an experimental term without touching live code** - existing patterns:
1. A pure measurement script (season-phase style): `centre_replay.walk` rows + feature columns -> fit c[bucket] = log(Σy/Σcentre) on dev, apply exp(c) to the centre, compare NB log-loss (`measure_season_phase.nb_logloss_vec`, alpha from `config/sofa_count_dispersion.json`) with match bootstrap. No flag needed; nothing live imports it.
2. Line-level confirmation through the real chain: import `calibrate_from_cache` as a module and monkeypatch, exactly as `data/refit_2026-11-05_replay/verify/run_window.py` does (it wraps `ReliabilityAccumulator.add` and `build_player_rows`). Wrap `live_centre` (record (event, market, side, centre) and/or multiply by the term) and `ReliabilityAccumulator.add` (capture rows) - live code untouched.
3. Only after a pass: a `CentreRules` field + `--<flag>` in `calibrate_from_cache` (`:1031-1127`, applied in `live_centre`), recorded in `replay_rules` -> `fitted_from.replay_rules.flags` (`prepare_refit.py:895-935`), switch in `bet.sofa.epochs` like `SEASON_PHASE` (`epochs.py:1622-1685`, row marker), live hook in `run_sheet.py` beside `apply_season_phase_term`.

**DB copy procedure** (`docs/sofa/CONFIG.md:358-366`, CLAUDE.md "Changing the pipeline" 4): `sqlite3.connect("file:data/sofa.db?mode=ro", uri=True)` then `VACUUM INTO 'data/refit_<d>/sofa_replay.db'`; 11-05 took 12 min for 54.7 GB (`refit_replay_2026-11-05.md:42`); then `--db-path <copy>` and `prepare_refit ... --without-db-backup`. A full `rebuild-cache-rows` writes ~140M rows into the copy (grows it); `--no-write` does not. Disk now: 222 GiB free (`df`), so one copy fits (11-05 coverage work could not: 27 GB free then). `load_cache(read_only=True)` exists (`calibrate_from_cache.py:569, 606`) but the CLI never passes it - `run_window.py` ran on the copy. Long reads on the live WAL DB block checkpoints - use the copy for anything hours long; the pickle harness needs no DB at all.

## C. Recommended harness (cheapest correct)

Two tiers; tier 1 decides, tier 2 confirms on lines only for terms that pass.

**Tier 1 - centre residuals, football (minutes):**
- Reuse: copy `data/cache/football_history.pkl` (frozen fingerprint), `football_rating.without_awarded`, `centre_replay.walk` (already yields y, sample, rating, supremacy; live centre = `measure_season_phase.live_centre`), `count_dispersion.load_table`, `measure_season_phase.nb_logloss_vec` / `boot_by_match`, the season-phase walk-forward fit `coefficients_before` shape.
- New (one script, `scripts/sofa/measure_schedule_residuals.py` or scratch under `data/refit_<d>_schedule/`): (a) a calendar index from one read-only scan of `sofa_listed_event` (football + tennis, all statuses, friendlies kept, doubles mapped through `subTeams`; ~2 min), queried strictly `< kickoff` (copy the battery's `as_of` rule `measure_feature_battery.py:576` and its leakage test pattern `tests/sofa/test_measure_feature_battery.py`); (b) features per side: rest days, matches 7/14/21 d, minutes-weighted load (extra time from `is_extra_time_event`), previous match knockout / continental (cup_strength ids) / away / other country, makeup (`schedule.find_makeup`), back-to-back; (c) residual log(y/centre) per bucket, Poisson/NB term fitted monthly walk-forward on dev, frozen; (d) one hold-out.
- Runtime: calendar ~2 min, walk ~1-3 min per market set, bootstrap minutes. Output `data/refit_<date>_schedule/` (rows parquet/pkl, report md), evidence in `docs/sofa/evidence/`.
- Limits: centre approximates SHEET (no stretches / referee / form table); markets limited to `football_rating.base_metric` ones; stats only from 2024-H2.

**Tier 1 - tennis (minutes):** `tennis_point_model.load_point_history` (155 s, read-only) + `walk_forward` -> `market_sim` -> `tennis_point_sheet.mean_sd` for games_total, games_won_for, aces, DF, set games; actual from `PointMatch.sets` / serve stats; workload features from the listed-event calendar (time.periodN where present, else points `Total`, else games played; doubles included; surface change; retirement). Games total / games_won_for are priced live by the tennis rating, not the point model - residuals vs the point-model mean are a proxy there (SUSPICION that conclusions transfer).

**Tier 2 - line confirmation (hours, only for a passing term):** VACUUM INTO copy (~12 min, ~55 GB), then a `run_window.py`-style wrapper around `calibrate_from_cache.main()` with the installed fit's flags, monkeypatched `live_centre` multiplying by the frozen term, `--no-write`, capturing rows; ~1.4 h per window (history always built in full), ~5-6.5 h for a full write-replay if curves must be refitted. Compare log-loss / calibration >= 0.70 per family, then line evidence on settled Superbet rows (the battery says the price bar is hard: no schedule cell closed a gap).

**Do not expect much (from prior evidence):** vs the raw sample only the >=21 d layoff showed a bias; vs the price rest features passed BH mainly on shots / SOT totals with small Brier gains, back-to-back and travel nothing. Venue-based travel and manager change need new backfills (A3, A5) - those are the only genuinely new features here.
