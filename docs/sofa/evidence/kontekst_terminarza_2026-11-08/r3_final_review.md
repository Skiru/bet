# R3 - final adversarial review of PLAN_KONTEKST_TERMINARZA_PILKA_TENIS_2026-11-08

Read-only, 2026-11-08, HEAD e4fb587d + working tree. No repo file edited, no network, no pipeline run.
Volumes counted offline from the scratch pickle copy `F/fh.pkl` (football) and `data/cache/tennis_played_serve_sets.pkl`
(tennis Played list as of 10-19; scripts `F/r3_quarters2.py`, `F/r3_tq2.py`). Code facts cite file:line read in this session.

Verdict: the plan has the right shape (one recording replay, offset GLM, calendar split, Holm, sealed exam) but it is
**not yet executable by another session without judgement calls**: the split is wrong for count statistics and tennis
serve markets (data starts late), the pass rule has no numbers, the recording mechanism and the dev-only curve refit
are not specified, and the deployment step is a one-line list. 4 BLOCKERs, 13 MAJORs, 8 MINORs below.

---

## (a) Finding-status table

Status: **inc** = incorporated adequately; **part** = named but under-specified (change in column 3); **miss** = absent;
**rej** = explicitly rejected with a reason (acceptable unless noted); **wrong** = incorporated in a way that is wrong.

### Coverage review (r2_coverage_review.md, C1-C32)

| id | status | what to change in the plan |
|---|---|---|
| C1 | inc | 3.4 covers non-base keys by the sample chain; add a table "key -> centre it is judged against" (live_centre output = sample centre for the 28 non-base keys, `calibrate_from_cache.py:1311-1313` returns the sample centre when `forecast.centre` is None). |
| C2 | part | F0 list must be generated from code (`FOOTBALL_METRICS`, `CARD_INCIDENT_SCOPES`, module `MARKETS`, derived prefixes x base metrics `market_mapper.py:715-835`, tennis lists, every calibration key), each latent key with "reach = as <sibling>". "~25 keys" is not a rule. |
| C3 | miss | Add to F2/F3: rows are classified by market key against the code dispatch, never by notes / `forecast_source` (tennis `handicap_games`, `games_set1/2_total` traps). |
| C4 | part | F4 says "one path per row" but no rule. Replace with D3 below (exact rule). |
| C5 | part | Season phase is in the recorded centre (good). Missing: layoff buckets reported for round <= 3 vs > 3, and the `season_early` class-curve interaction (D12). |
| C6 | inc | Full replay carries every supremacy term; strata by favourite strength in 3.5. |
| C7 | part | "średnia i rozrzut" only. Add the pre-registered dispersion test (Pearson chi2/df of NB residual by bucket; result-model draw / upset rate vs NB p) and the allowed lever (alpha / `nb_r` multiplier per bucket only if the test passes on dev). |
| C8 | part | "1. i 2. połowa osobno" only. Add: term fitted per (metric, half) with 1H = 2H as null; card halves need a context-dependent 2H share; simulator a 2H-vs-1H goal-profile tilt - each only if measured; otherwise those families are "reached through the 90' total only" in the family table. |
| C9 | part | Section 6 rejects half `both_over_*` (raw sample) but is silent on the other raw joints (`most_corners_1h/2h`, `handicap_shots*`, `both_over_saves*`). Either add the joint path (scale each side's raw values by its side term before `build_joint`, `derived.py:536-545`) or list every raw joint by name as "not reached". |
| C10 | rej | Section 6 excludes league-rate reds / penalties. Accept, but the reason must cite power (method M14: reds unresolvable at these n), not only "no model". |
| C11 | part | Lineup minutes are a feature (section 5), but no player-level term. State: share props (shots / SOT / fouls, `config/sofa_player_share.json`) inherit the team term automatically; non-share props "not reached" in this plan; props scored on starters only (M18). |
| C12 | part | F3/F4 name sum/max for tennis and "cechy obu graczy", but the neighbour selection (`tennis_rating._window` :775-791, by p only) is untouched, so totals still cannot move. Add: joint-load as a second neighbour key, or move those families to the point model - pick one in F0. |
| C13 | part | "ewentualnie zależne od seta" - make it a pre-registered alternative (shift(prior load) vs shift + slope x points played), and the same term in `PointModel.update` tested vs forecast-only. |
| C14 | part | Tiebreaks / raw serve joints rejected in section 6 (ok). Missing: the sample half of `games_total` (`W_GAMES_TOTAL_RATING` mix, `run_sheet.py:3252-3256`) - say whether it gets the term or is left (then `games_total` is only partly reached; it is on the 0.60 floor). |
| C15 | inc | F4 tests the term in the rating update and the table book. Add explicitly: both books under `FOOTBALL_FORM_TABLE` (D3). |
| C16 | inc | "każda strona i rywal". |
| C17 | inc | ET / penalties previous match. |
| C18 | part | Add the citation of the 10-23 lineup measurement ("real XI no gain on team counts") and the rule that only PREVIOUS matches' lineups are read (never the current one - a leak). |
| C19 | part | Next-match feature present; add the as-of rule (start known at kickoff; rescheduled next fixtures excluded) - see M5. |
| C20 | inc | Hour / weekday as control. |
| C21 | part | Hours rest, tie-breaks, qualifying, doubles are listed. Missing: previous-match finish time (night session), and how live gets doubles (rating log is singles only, `tennis_rating.parse_event`). |
| C22 | part | Weather, coach listed. Add travel distance / altitude as "not computable (venue on ~4.5% of football detail rows)". |
| C23 | part | One function (3.3, F1). Missing: (i) a test that a replayed fixture's features equal what SAMPLES wrote for it on a settled day; (ii) the existing display flags (`CONGESTED`, `LONG_LAYOFF`, `MAKEUP_FIXTURE`) byte-identical; (iii) the live-vs-replay exposure distribution check (M6). |
| C24 | part | "przefitowanie krzywych i tabel" - replace with the file list in checklist (d) step 22-27. |
| C25 | inc | F8 names the p backfill; spell it out (checklist step 28). |
| C26 | part | Floors named; no rule. Add D13. |
| C27 | part | Named; add "report printed / removed counts and the removed legs' realised rate with and without the term, before the switch". |
| C28 | inc | Parser named; add a test that the note wording is unchanged or the regex extended (`rating_market_gap.py:103-111`). |
| C29 | inc | Named; add the twin-pair disagreement report from `bet.sofa.leg_identity`. |
| C30 | part | Missing: `SHEET_OPTIONAL_FILES` (not `SHEET_CONFIG_FILES`), row marker + `rebuild_plan.AUDIT_MARKERS`, `UNFITTED_CONSTANTS`, analysts' skills (`football-analysis`, `tennis-analysis` must say the model now carries fatigue), dossier display. See checklist. |
| C31 | miss | Score the completed-match population as SETTLE grades it (retired / walkover / awarded refunded or excluded) and report the retirement rate by exposure bucket as its own outcome. |
| C32 | inc | Offset GLM, not log ratio (3.5). |

### Method review (r2_method_review.md, M1-M18)

| id | status | what to change |
|---|---|---|
| M1 | part | 3.4 has the recording run but not how to record without touching live code. Add D4 (hook list). Also "if the 6 h run is refused" fallback is not needed - make the run mandatory. |
| M2 | part | Day-gated for football (3.4) and tennis (F2). Missing: the shuffle-within-day unit test, and the fact that the pure-rating walk-forwards (`football_sim.walk_forward_centres`, `football_sim.py:448-484`, groups by identical ts only) leak - see D5. |
| M3 | part | Prediction-only vs +update is in F4. Missing: "first match after a congested spell" bucket reported separately; adopt (a) unless (b) is materially better (define: (b) better by > 1 SE on dev). |
| M4 | part | Offset + team-vs-itself + home-away contrast + favourite strata present. Missing: sign/symmetry rule (a significant coefficient with a sign against the mechanism is rejected) and continental vs domestic strata. |
| M5 | part | "permutation + two negative controls" - name them: permutation within team-season (200), lagged exposure rest_{t-1}, mechanism-free outcome (opponent offsides). Gate: dev permutation p < 0.05 and |beta_lag| < 0.5 |beta|. |
| M6 | part | Coverage flag present; add "coverage=false -> dropped from fit, x1 live" and the exposure-distribution check (last 30 days of 03_samples vs replay, each bucket within 3 pp). |
| M7 | part | Layoff split named loosely ("razem z fazą sezonu i przerwą reprezentacyjną"). Make the four layoff kinds explicit (season start, winter break, FIFA window, individual gap); postponed matches excluded from load. |
| M8 | part | Dev refit of tennis coefficients covers the in-sample leak. Missing: the written list of earlier looks (10-04 schedule measurement on 2025-08..2026-10, 10-05, 11-05 battery) and which feature choices came from them (>= 21 d bucket). |
| M9 | part | Calendar split adopted - but **wrong for counts / tennis serve** (D1). National teams (World Cup 2026 in the exam) not excluded (D11). Prospective shadow kept (see section 6 / D16). |
| M10 | inc | "w obu wariantach"; add "point-model hyperparameters as installed in both arms - accepted symmetric contamination". |
| M11 | part | Metrics named. Missing: >= 0.70 calibration on rows selected by the **baseline** p; curves refit **on dev only** in both arms (fit_confidence cannot - D6). |
| M12 | part | ~40 tests Holm present. Missing: parametric form (piecewise-linear rest capped at 10 d), partial pooling within group, numeric delta. Replaced by the rule in (c): exam unit = group, Holm across groups. |
| M13 | part | "Bootstrap po drużynie" -> two-way cluster bootstrap (home team x away team), tennis player x tournament-week, 2,000 reps; match bootstrap reported beside. |
| M14 | part | Power in 3.7, but "minimalny efekt" has no value. Fix |c| >= 0.03 / 1 pp winner p (rule (c)). |
| M15 | part | "egzamin raz" only. Missing: explore / validate (<= 3 logged looks) / exam tiers, the seal, spec hash, one spec per (mechanism, group). See (c) guards. |
| M16 | part | F4 has games-based load and dn7 vs rounds won. Missing: features **replace** dmin78 / dn7 (not added beside), previous-match dominance control, qualifier quasi-experiment as supporting evidence, cross-market consistency (point-model implied winner p vs rating by bucket). |
| M17 | miss | Best-of-five as exposure only, descriptive (few hundred matches); no five-setter feature collinear with games load. Section 5 lists "pięciosetówka" as a feature - **wrong** per M17; replace with games load. |
| M18 | part | Hours rest only for tennis; football rest must be hours/24 too (section 5 says "<= 3 dni"). Missing: short rest x continental as an interaction, time zone from team country exploratory only (multi-zone countries), row coverage per bucket (`MIN_VALUES`), price_gap / rating_market_gap interaction report, null result is a valid deliverable (present in 7 - ok). |

Totals: coverage 10 inc, 1 rej (acceptable), 19 part, 2 miss; method 1 inc, 16 part, 1 miss (M17 partly wrong).
Three findings are missing (C3, C31, M17), and 35 of 50 are only named - an implementing session would have to invent
the missing rules, which is exactly the forking-path risk M15 warns about.

---

## (b) Defects

### D1 BLOCKER - the dev period is empty for count statistics and tennis serve markets

Evidence (football pickle, matches with the statistic per quarter; tennis Played list):

| quarter | football all | goals_1h | corners | shots | cards_points | tennis all | tennis aces/serve pts |
|---|---|---|---|---|---|---|---|
| 2024Q3 | 68,843 | 46,651 | 354 | 354 | 587 | 27,088 | 189 |
| 2024Q4 | 93,658 | 56,905 | 5,524 | 5,521 | 7,027 | 23,475 | 324 |
| 2025Q1 | 78,092 | 50,875 | 6,654 | 4,791 | 6,152 | 21,891 | 429 |
| 2025Q2 | 95,004 | 60,490 | 9,567 | 5,230 | 6,896 | 27,918 | 17,964 |
| 2025Q3 | 92,891 | 62,981 | 13,789 | 8,013 | 10,961 | 30,268 | 28,394 |
| 2025Q4 | 114,310 | 71,224 | 17,732 | 11,741 | 15,834 | 22,904 | 15,643 |
| 2026Q1 | 92,146 | 60,744 | 17,096 | 11,095 | 13,274 | 25,599 | 17,447 |
| 2026Q2 | 109,464 | 65,641 | 14,009 | 11,906 | 14,458 | 38,199 | 31,117 |
| 2026Q3 | 94,591 | 65,075 | 20,392 | 12,574 | 18,417 | 37,570 | 31,226 |

(2026Q4 football to 11-08: 29,390 / corners 11,767; tennis cache ends 10-19.)

So "próby 07.2024-12.2025" holds ~48k corner matches (2024Q3 ~0, 2024Q4 5.5k, and the first months have no
sample of >= 5 prior values per side, `MIN_SAMPLE`), and tennis serve statistics essentially start 2025-04. A rule
"dev = 07.2024-12.2025" invites a session to report a 2024 dev that is goals-only without noticing.

Replacement text for plan 3.2:
> **Okresy (per grupa).** Egzamin: 2026-01-01..2026-10-31 dla wszystkich grup. Rozwój = wszystko przed 2026-01-01,
> z rozgrzewką (rating i próbki budowane od początku historii, wiersze liczone od):
> gole, wynik, tenis zwycięzca / gemy / sety: od 2024-07-01; liczniki piłki (rożne, strzały, kartki, faule, spalone,
> połowy): od 2025-01-01 (pierwszy kwartał, w którym obie strony mają >= 5 wartości); tenis serwis (asy, podwójne
> błędy, punkty serwisowe, gemy w secie z modelu punktowego): od 2025-05-01 (model punktowy potrzebuje rozgrzewki).
> Podział rozwoju: **eksploracja** = do 2025-08-31, **walidacja** = 2025-09-01..2025-12-31 (<= 3 zapisane spojrzenia).
> Przed analizą raport liczebności wierszy (bez wyników) per grupa x kwartał x kubeł ekspozycji; grupa, której
> eksploracja ma < 50% wymaganej liczby wierszy narażonych z tabeli mocy, idzie na egzamin tylko łącznie z
> pokrewną grupą (pooling) albo wcale - decyzja zapisana przed walidacją.

### D2 BLOCKER - the pass rule has no numbers

Section 3 says "margines nie-gorszości ustalony w F0", "minimalny efekt warty działania" - no values, no unit, no
definition of "helped". Replace with rule (c) below verbatim.

### D3 BLOCKER - the single-path rule is not written

F4 "jedna droga na wiersz" leaves the session to decide where the term sits, and the measured coefficient must be
estimated against exactly that centre (C4, M1). Replacement text for F4 (football):
> **Droga poprawki (zamrożona w F0):** (i) wiersze brzegowe liczników / goli (team `_for` / `_total`, połowy, wiersze
> łączone "na środkach brzegowych" `DERIVED_MARGINAL_CENTRES_METRICS`, propsy przez udział): mnożnik exp(t) na
> **końcowym** środku `live_centre` / `centre_chain.apply_centre_chain` - po fazie sezonu (`centre_chain.py:227`),
> z połową ratingową i z `supremacy` dla stretchy czytanymi **bez** poprawki; (ii) odbiorcy czystego ratingu (1X2,
> DC, DNB, wynik dokładny i jego krzywe-plastry, symulator): poprawione środki goli w `FootballForecast.centre`
> (obie książki, także tabela sezonu dla 35 rodzin `FOOTBALL_FORM_TABLE_FAMILIES`), nigdy jednocześnie z (i) na tym
> samym wierszu; (iii) aktualizacja ratingu (`RatingBook.update`) bez terminu w wariancie podstawowym (a);
> wariant (b) z terminem w oczekiwaniu aktualizacji tylko gdy na rozwoju lepszy o > 1 SE. Współczynnik dla (i) jest
> dopasowany względem zapisanego końcowego środka; dla (ii) względem zapisanych środków ratingu.

### D4 BLOCKER - the recording run is not specified; feasibility answer

It is feasible without touching live code, by the `data/refit_2026-11-05_replay/verify/run_window.py` pattern
(import `calibrate_from_cache as cfc`, monkeypatch module globals, set `sys.argv`, call `cfc.main()`):
- `cfc._settle_centred` (`calibrate_from_cache.py:1919`) is called by global name from `settle_rows`
  (:1665, :1673, :1688): wrap it to record, per call, `match.event_id, match.timestamp, competition_id, market,
  subject, actual, n, mean, variance, sample` (sample only where `uses_empirical_frequency(market)`), the shrunk
  centre, the hooked centre (wrap the `centre_hook` argument), `COUNT_DISPERSION.read(...)` (:1944-1947) and the
  spread (`sheet_predictive_sd`, :1948). With these, any arm's p is recomputed offline with the same pure functions
  (`sheet_predictive_sd`, `sheet_count_p_raw`, `p_empirical_centred_raw`) at the **baseline** arm's
  `lines_for(baseline centre)` - lines fixed independently of the treatment arm (M11).
- `cfc.live_centre` (:1271) is also called by global name for joint side centres (:1795): wrap it to record
  `forecast.centre(market, side)`, `forecast.supremacy(side)`, the phase and the centre **before** the season-phase
  step (recompute it by calling the wrapped function with `rules` lacking `season_phase`, or record
  `apply_season_phase`'s multiplier) - needed because the dev-only season-phase refit (plan 3.2) must be applied
  offline without a second 6 h run.
- `FootballRatingReplay.forecast` (:1248; book advanced to the match's UTC day start, :1221-1234 - day-gated, no
  same-day leak) and `RatingReplay.forecast` (:940, tennis): wrap to record every event's rating centres of the 14
  base metrics (home/away) and the tennis MatchForecast p, **for every event, not only those that reach
  `_settle_centred`** (which skips n < `MIN_SAMPLE`, :1932). These are the baseline for the pure-rating consumers (D5).
- `--form-table-per-family` (not `--form-table`): record which book each row took (:1564).
- Stream records to disk per month (npz / parquet); the 11-05 run produced 139.8M rows - a Python list like
  `run_window.py`'s `captured` will not fit. Write exam-period rows (kickoff >= 2026-01-01) to separate files, outcome
  columns (`actual`) in a third file (seal, rule (c) G2).
- Flags: take them from `data/refit_2026-11-05_replay/ftA/replay_rules.json` (the 11-05 replay: adds
  `--closeness-stretch --player-coverage --awarded-excluded --referee --player-share --tennis-score-winner
  --sample-conflict-cut`) with `--form-table-per-family` replacing `--form-table`, `--no-write`, `--from 2024-07-01`,
  `--db-path <VACUUM copy>`. **Do not** take them from `fitted_from.replay_rules` of the calibration files: the
  installed, `.next.json` and `.next.2026-11-07.json` all carry the 10-17 stamp (no referee / closeness / player
  share / awarded / form table) - a stale stamp (see D9).
- Runtime: full replay 5.2-6.5 h (`chainA_replay.log` `rows_seconds` 18,870-23,244 s); a 5-day window still costs
  ~1.4 h because history and books are always built in full (`run_window.log`, 5,065 s). Mandatory smoke first: a
  5-day window (2025-10-01..05) with the recorder, asserting recorded hooked centre == the row's `sample_mean`-free
  recomputation of p_central to 1e-9 on every row; then the full run once. VACUUM copy ~12 min, 55 GB; 222 GiB free.

Tennis: `fit_tennis_rating.py --cut 2026-01-01 --tier-start --score-winner --db-path <copy> --out <scratch>`
(features are the code tuple `FEATURES`/`V5_FEATURES`, `tennis_rating.py:94-104`; the config's `features` list is
what SHEET reads, :1040; `fitted_from` records source, cut, history / rated counts, score_winner, fit population -
`fit_tennis_rating.py:80-92`). The installed `config/tennis_rating.json` was fitted 10-08 with cut 10-01 and has no
`score_winner` / `fit_population` keys, i.e. before P14 and the 10-27 best-of-five fix - the dev refit of the
baseline arm is therefore a real change, not a formality; report the baseline-arm dev refit vs installed on dev as
its own row. Runtime unmeasured (history load from `sofa_entity_events`; expect minutes - measure and log).
Neighbour families need the neighbour machinery (`run_sheet._stats_only_rating_p`), so evaluate them through the
recording replay with `SOFA_CONFIG_DIR` pointing at a scratch config dir holding each arm's `tennis_rating.json` -
two tennis-only replays are acceptable cost only if `calibrate_from_cache` can skip football; otherwise record the
neighbour table inputs and recompute offline. Point model: `fit_tennis_point_curves.py --history-cache ... --from
2025-05-01 --before 2026-11-01 --workers 8 --rows-out` over `tennis_point_model.walk_forward` (:885; groups identical
start seconds only - make the measurement copy day-gated, D5); history load 155 s, 4,000 sims per match - expect
tens of minutes with 8 workers (measure).

### D5 MAJOR - the pure-rating and point-model walk-forwards leak same-day results

`football_sim.walk_forward_centres` (`football_sim.py:448-484`) and `tennis_point_model.walk_forward` (:885) group
only identical kick-off seconds; `centre_replay.walk` and `tennis_rating.replay` update per match. Rule: every
baseline for 1X2 / DC / DNB / score markets / simulator is the **recorded day-gated rating centres** from D4, run
offline through the result model / simulator; tennis replays used for the exam are day-gated (forecast every match of
day D from the state at D 00:00Z) in **both** arms; a shuffle-within-day test (forecasts of a day invariant to the
order of that day's matches) is part of F1's tests.

### D6 MAJOR - "curves refit in both arms on dev" has no tool

`fit_confidence.py` has no date cut (reads every `sofa_settled_row`, `main` :165-). Plan F5/F6 must say: dev-only
curves for the evaluation are fitted offline from the recorded rows with the same bucket logic (`bucket_of`,
`wilson_lo`, K13 thin-bucket caps, class curves, per-line curves for the 33 keys, score slices) - a measurement script,
never written to `config/`. The install refit later is the normal full-history one on the copy (checklist).

### D7 MAJOR - live feature path

The live term must read features through the same function as the replay. Today `schedule.side_schedule`
(`schedule.py:221-243`) excludes friendlies and reads the side's own cached `last` pages; SHEET already holds the DB.
Rule for F1: one module `bet.sofa.schedule_features` (pure, as-of, from `sofa_listing_event` + `sofa_listed_event`
union, friendlies rule decided once, `coverage` flag) called by the replay and by SHEET; `schedule.py`'s display
output byte-identical (test). If SAMPLES must change, `rebuild_plan` needs a SAMPLES re-run marker for open fixtures
(the "sample switch" path 1c); computing in SHEET avoids it - prefer SHEET. Live coverage is higher than history
(SAMPLES fetches the sides' pages fresh): the exposure-distribution check (M6) is a gate before the switch.

### D8 MAJOR - pre-registration cannot go into the test registry as written

`check_test_registry.py` refuses a test whose `data_window.from` is not strictly after `registered_on`. The historical
exam (2026-01..10) is therefore a frozen evidence document (git SHA), not a registry test. The registry gets one
forward test, e.g. `T-SCHEDULE-TERM-FORWARD`, registered before its window starts (window from the switch day). Plan
F0 must say both.

### D9 MAJOR - replay flag stamp is stale; the new flag must be stamped where it is read

`fitted_from.replay_rules.flags` of all three calibration files is the 10-17 stamp (checked), although the 11-05
replay used more flags. A future refit that reads the stamp would drop the schedule flag. Checklist: add the
`CentreRules` field + `--schedule-term` flag to `calibrate_from_cache` (and `describe()` :1093-), to
`prepare_refit.write_replay_rules` / `replay_switch_warnings` (`prepare_refit.py:895-935`), make install refuse a
replay without the flag while the switch is on (as `--awarded-excluded`), and re-stamp the files the install writes.

### D10 MAJOR - collinear constants refit on dev: which, and how without a second replay

3.2 names season phase, tennis rating, form table. State: (i) season phase - refit with `fit_season_phase.py`
restricted to dev, applied offline on the recorded pre-phase centre (D4) in both arms; (ii) tennis rating - D4;
(iii) form-table families were selected on live rows 10-18..11-04 (outside the exam) - keep as installed, say so;
(iv) game state, stretches, rating weights, referee, count dispersion, cup strength were fitted on history including
the exam period - identical in both arms, declared as accepted symmetric contamination (the comparison is
treatment - baseline, so it biases only the level, not the difference, except where a term competes with the exposure:
goals stretch by phase - report the coefficient with the goals-stretch phase split on and off on dev).

### D11 MAJOR - national teams, women, season_early, classes

World Cup 2026 (competition 16) and qualifiers sit in the exam. Rule: national-team matches excluded from fit and
exam (reported descriptively); women's football fitted and scored as its own stratum (class curves `NO_CLASS_CURVE`
read only `by_class`), installed only if its own stratum passes, else the term is x1 for women; tennis women's /
men's / team cups likewise. `season_early` legs (rounds 1..3, `football_1x2_dnb.py:162-170`) take no layoff term
unless the class-curve refit shows no double counting on dev.

### D12 MAJOR - downstream gates must be measured before the switch, with rules

Replacement text for F8 items (C26-C29):
> Przed przełącznikiem, na okresie egzaminu i na rozliczonych dniach 10-13..11-07 (audyt), dla obu wariantów:
> liczba nóg drukowanych / usuniętych przez `MODEL_ABOVE_OWN_SAMPLE` i ich trafność; liczba nóg z `price_gap` i
> `rating_market_gap` (D przeliczone na poprawionym ratingu); pary bliźniaków `SAME_EVENT_DEDUP` z różną pewnością
> i zmiana wyboru. Nic z tego nie blokuje wdrożenia, ale każda liczba trafia do raportu.

### D13 MAJOR - 0.60 floors

The tennis totals floor (`games_total`, `sets_total`) and the four simulator floor keys were frozen on today's p
(`epochs.py:3692-3716, 3835`). Rule: a floor key gets the corrected p only after its floor is re-measured with the
same frozen procedure (`docs/sofa/evidence/football_sim_floor_2026-11-06.md`, tennis 11-05 floor) on the corrected
p of the exam period; until then the switch excludes those keys (they stay on the uncorrected p, row marker says so).

### D14 MAJOR - tennis design details

Section 5 lists "pięciosetówka" and minutes; per M16/M17 replace with: workload = games (full coverage) in 78 h / 7 d,
points where present with a coverage indicator, minutes only as sensitivity; rounds won in the current tournament
separate from matches in previous tournaments within 7 d; previous-match dominance as control; these **replace**
dmin78 / dn7 / drest in the arm (not added beside); best-of-five previous match enters only through games load. The
neighbour choice for totals (C12) decided in F0. Live: the new features must exist in `tennis_rating.features()` with
the old keys kept (days before the switch read the old config); the staged `config/tennis_rating.next.<D>.json` with
`effective_from` (`fit_tennis_rating.py --effective-from`, `params_path_for` :1000-1025) is the per-day switch.

### D15 MAJOR - parallel sessions and commits

The working tree already holds another session's uncommitted files (`config/sofa_superbet_line_evidence.json`,
`scripts/sofa/build_slip.py`, `src/bet/sofa/slip_builder.py`, `tests/sofa/test_slip_builder.py`,
`config/sofa_settleability.2026-11-08.json`). Add to the plan: commit only own paths (`git add <paths>`, never
`-A` / `.`), never `git stash`, commit straight to main, run the gates on the tree as it is, push only the SHA that
passed the gates (`git push origin <sha>:main`), and re-check `git log origin/main` before pushing.

### D16 MAJOR - F7 (6-week shadow before any switch) contradicts the standing install rule

See section 6 recommendation below; replacement text there.

### D17 MAJOR - the switch date is not fixed by the plan

The epochs switch must be "the next day 00:00Z after the install commit", not a date written into the plan (the
work spans days). Install never into a built day (operator 10-15 standing go: measured better + tests + report).

### D18 MINOR - smoke and restart

A crash of the 6 h recording means a restart; require the 5-day smoke (D4) and a `nohup`/background run with a log
under `data/refit_<d>_schedule/`, with the loops up (copy, never live DB).

### D19 MINOR - classification by key, not notes (C3).

### D20 MINOR - retirement / refund population (C31).

### D21 MINOR - the 7-10 pp over-promise at odds >= 1.40 (section 7) must stay a separate study; never mixed into these
arms (attribution).

### D22 MINOR - football rest in hours/24 (M18); short rest x continental as interaction; time zone exploratory.

### D23 MINOR - the plan file itself is untracked; F0 must commit the plan + pre-registration together and record the SHA.

### D24 MINOR - list "not computable" features (travel distance, altitude, weather, coach) by name (C22).

### D25 MINOR - "Cień na żywo >= 6 tygodni" volume: ~15k count matches is an estimate; compute from the live board.

---

## (c) Concrete numeric pass rule (replacement for plan sections 3.6-3.9 and F5-F6)

**Units.** Exam unit = metric group g in G = {goals (full, 1H, 2H; sides and totals), corners, shots+SOT,
cards+fouls, offsides, football result (1X2/DC/DNB/score via rating, sim keys), tennis winner, tennis games/sets
(rating + neighbours), tennis serve (point model)}. Each group's correction = all its frozen mechanism coefficients
together (shrunk, fitted on explore + validate). Mechanism-level tests are dev-only gates. K = number of groups
submitted to the exam (<= 9).

**Submission gates (dev, before the exam; all must hold for g to be submitted):**
S1 permutation null (fatigue feature permuted within team-season / player-season, 200 reps): p < 0.05;
S2 lagged negative control: |beta(rest_{t-1})| < 0.5 |beta(rest_t)|; mechanism-free outcome coefficient CI covers 0;
S3 sign matches the pre-registered direction (own short rest lowers own attack counts, etc.);
S4 validate-tier Delta (definition below) < 0 point estimate;
S5 power: exam exposed rows (counted from the outcome-free X file) >= n required for |c| = 0.03 at 80% power with
DEFF 1.75 (plan 3.7 table), else g is submitted only pooled with a sibling or not at all.

**Primary metric.** Delta_g = mean over exam **matches** of [S_treat - S_base], S = the match's summed per-row
proper score over g's rows: NB log score of the observed count with each arm's centre and the recorded dispersion
(counts, goals); Bernoulli log loss (tennis winner, result markets at their own outcomes); the point model's line log
loss at baseline-fixed lines (tennis serve). Negative = better.

**PASS(g) iff all of:**
P1 one-sided upper 95% bound of Delta_g < 0, from a two-way cluster bootstrap (football: home team x away team;
tennis: player x tournament-week; 2,000 reps), **Holm-adjusted across the K submitted groups** (alpha 0.05 family-wise);
P2 materiality: frozen |c| >= 0.03 (3% of the centre) in at least one pre-registered exposure bucket holding >= 2% of
g's exam rows (tennis winner: mean |Delta p| >= 0.01 in that bucket); a significant but immaterial g = NOT_PASSED;
P3 calibrated line level (dev-refit curves in each arm, baseline-fixed lines): Delta_line point estimate <= 0 and its
upper 95% bound < +2e-4 nats per row;
P4 calibration at >= 0.70, rows selected by the **baseline** calibrated p: |realised - mean p|_treat <=
|realised - mean p|_base + 0.005; the same on rows selected by treatment p reported (no gate);
P5 non-inferiority on every other group and on every pre-registered stratum (women, favourite |s| terciles,
continental vs domestic, round <= 3, tennis tiers): upper 95% bound of Delta < +1e-4 nats per row (groups) and
< +5e-4 (strata, each n >= 2,000 rows; smaller strata descriptive);
P6 exam-refit coefficient (descriptive, never installed) has the dev sign.

**"Helped"** = at least one group PASSes. Only PASSing groups' terms are installed; a mechanism shared with a failing
group is x1 there. Zero passing groups = the deliverable is the null report; nothing is committed except the
measurement scripts / evidence (no switch, no config).

**Guards against iterating on the exam:**
G1 F0 commit (plan + pre-registration + feature module + power table + this rule) before the recording run; its SHA
and the sha256 of the feature module and of the frozen coefficient JSON are written into the exam output;
G2 the recorder writes exam rows to `exam_X.*` (predictors, centres) and `exam_y.*` (outcomes) separately; before the
exam only `exam_X` may be opened (row counts, exposure distributions); `exam_y` is read only by
`measure_schedule_exam.py --spec-sha <sha>` which appends one line (UTC time, SHA, hashes, verdicts) to
`docs/sofa/evidence/schedule_context_exam_log.md` and refuses to run if a line already exists for this study;
G3 validate tier at most 3 looks, each logged with its spec hash; a change of bucket edge, window, friendly rule,
control set or path rule after any validate look = a new look;
G4 one specification per group goes to the exam; after the exam no re-specification is evaluated on 2026-01..10 -
the next attempt waits for forward data;
G5 the report lists every look, every failed group, and the earlier looks at 2025-08..2026-10 (10-04/10-05
schedule measurement, 11-05 battery) and the choices they influenced.

---

## 6. F7 shadow vs the operator's install rule - recommendation

The operator's rule (memory `install-if-better-than-current-2026-11-06`): hold-out better than the installed estimator
-> install, switch next day 00:00Z, tests, E2E, docs, ledger group. A mandatory 6-week pre-switch shadow is a stricter
bar he did not ask for and would be overridden. But the risk M9 named (a historical exam everyone partly looked at) is
real. Reconcile by **inverting the shadow**: install on the exam pass (rule (c) is already stricter than his point-
estimate rule, so it satisfies it a fortiori), and keep the uncorrected number on every live row as the shadow.
Replacement text for F7:
> **F7 - wdrożenie po egzaminie + odwrócony cień.** Po zaliczeniu (c) przełącznik od następnego dnia 00:00Z
> (reguła operatora 2026-11-06). Każdy wiersz objęty poprawką niesie obok `p_central` także `p_central_bez_terminarza`
> i współczynnik; test w rejestrze `T-SCHEDULE-TERM-FORWARD` (zarejestrowany przed dniem przełącznika) porównuje oba
> na rozliczonych wierszach SETTLE (te same miary co egzamin). Reguła wycofania zapisana z góry: po 6 tygodniach lub
> po liczbie wierszy narażonych z tabeli mocy (co później) - jeśli Delta na nowych danych ma znak przeciwny i górna
> granica 95% < 0 dla "bez poprawki lepsze", przełącznik wyłączony od następnego dnia 00:00Z (nowa epoka), raport.
> Brak sygnału = zostaje (zgodnie z "lepsze od obecnego").

---

## (d) Ordered deployment checklist (implementing session)

Preparation (nothing that prints changes)
1. Read CLAUDE.md, `model-state.md`, this review; `git status` - note foreign uncommitted paths (D15).
2. F0: write `docs/sofa/evidence/schedule_context_prereg_2026-11-xx.md` (mechanisms, exact features, parametric forms,
   groups, path rule D3, periods D1, power table, rule (c), guards, earlier looks, not-computable features, family
   table generated from code C2). Commit with the plan (own paths only). Record SHA. No registry entry yet (D8).
3. F1: `src/bet/sofa/schedule_features.py` (pure, as-of, coverage flag, hours rest, union calendar) + tests in
   `tests/sofa/` (as-of no-leak, shuffle-within-day, replay == SAMPLES on a settled day, display flags
   byte-identical). Gates (pytest, ruff, mypy --strict --no-incremental, check_test_registry). Commit. Hash the module.
4. `VACUUM INTO data/refit_<d>_schedule/sofa_copy.db` from `file:data/sofa.db?mode=ro` (~12 min, 55 GB).
5. Recorder script under `data/refit_<d>_schedule/` (D4). 5-day smoke (~1.4 h); assert recomputed p == replay p.
6. Full recording run on the copy (~5-6.5 h, background, log); exam rows split X / y (G2).
7. Tennis: dev-cut rating refits for both arms (D4, D14) on the copy; day-gated point-model walk-forward both arms.
8. Outcome-free exam X report: exposure distributions, row counts per group x bucket, live-vs-replay exposure check
   (last 30 days of `03_samples.json`, within 3 pp per bucket).
Measurement
9. F3 on explore: offset GLMs (team-season FE primary, within-match contrast, strata), dispersion test, halves,
   prediction-only vs +update; S1-S3.
10. F4: freeze coefficients (shrunk), path rule; validate looks (<= 3, logged); S4-S5. Commit the frozen
    coefficient JSON (scratch evidence path, not `config/`) + the exam script; record hashes.
11. F5/F6: one exam (`measure_schedule_exam.py --spec-sha`), rule (c). Write `docs/sofa/evidence/schedule_context_2026-11-xx.md`
    (Polish), every group / family row: reached / not reached / changed.
12. If no group PASSes: commit the evidence and the measurement scripts only; model-state.md "measured and declined";
    stop.
Install (only PASSing groups; operator standing go 10-15 + 11-06, never into a built day)
13. Downstream report on exam + 10-13..11-07 (D12); floors re-measured or floor keys excluded (D13).
14. `bet.sofa.epochs`: `SCHEDULE_TERM = "schedule_term_v1"`, `SCHEDULE_TERM_FROM_UTC` = next day 00:00Z after the
    install commit, `schedule_term_enabled(date, at)`, `SCHEDULE_TERM_MARKER`; tennis via staged
    `config/tennis_rating.next.<D>.json` (`--effective-from`) plus its own marker.
15. Live hook after `apply_season_phase_term` in `centre_chain.apply_centre_chain` (`centre_chain.py:213-227`) for
    path (i); `FootballForecast.centre` in both books for path (ii); identical code in
    `calibrate_from_cache.live_centre` behind `CentreRules.schedule_term` + `--schedule-term` (D9); parity test
    live == replay.
16. Config `config/sofa_schedule_terms.json` (fitted on full history at install - or the frozen dev coefficients;
    decide in F0 and say so) added to `sheet_config.SHEET_OPTIONAL_FILES` (not `SHEET_CONFIG_FILES`, so past
    `config_sha` is unchanged); any chosen-not-fitted constant listed in `UNFITTED_CONSTANTS` on the rows.
17. Row field: the term, its features, `p_central` without it (F7 shadow); contracts / schema updated.
18. `rebuild_plan`: marker into `AUDIT_MARKERS` + `sheet_*` state (pattern `sheet_season_phase`, `rebuild_plan.py:128,
    317-353, 611`) so a built day re-runs SHEET when the switch is on and rows lack the marker.
19. `rating_market_gap` parser test (note wording) ; `SAME_EVENT_DEDUP` twin test with one twin corrected.
20. Display: dossier / PDF / HTML note "kontekst terminarza w modelu"; `football-analysis`, `tennis-analysis`,
    `sofa-analysis-core` skills: fatigue is now in the model (a WATCH on rest alone double-counts).
21. Tests in `tests/sofa/` for each of 14-20; gates.
Refits on a copy (`prepare_refit.py`, `--db-path <copy> --without-db-backup`, install runs `tests/sofa`)
22. `rebuild-cache-rows` with the 11-05 flags + `--form-table-per-family --schedule-term` (~6 h).
23. Football curves: `by_market_direction`, thin, `by_class` (women, season_early), score-market slices
    (`fit_score_market_curves.py`), 1X2/DC/DNB (`fit_result_1x2_dnb_curve.py`, `fit_double_chance_curve.py`), incident
    / card-half (`fit_incident_set_curves.py`), joints + `sofa_side_correlations.json` (`fit_joint_curves.py`), per-line
    33 keys (`fit_confidence.py --line-curves-only` + `install_line_curves.py`), simulator
    (`fit_football_sim_curves.py`).
24. Tennis: `fit_tennis_winner_curve.py`, set curves, `set_score_not`, `fit_tennis_point_curves.py` (+ `--handicap`).
25. Re-check (not refit unless measured worse) the centre tables fitted on the old centres: rating weight, game state,
    stretches, season phase, referee, count dispersion; result in the report.
26. Stage every refit as a dated `.next.<D>.json` with `effective_from` = the switch day (never over the installed
    file, never a file a built day reads); stamp `fitted_from.replay_rules` with the full flag set incl.
    `schedule_term`.
27. `prepare_refit` install (tests/sofa, restore on failure).
28. Line evidence: backfill corrected p for settled Superbet lines from 10-13 (pattern
    `data/line_evidence/tennis_point_model_p.json.gz`, `fit_line_evidence.py:354-421`), wire into
    `refresh_line_evidence.py`; refit for the switch day.
29. `audit_ledger.EPOCH_GROUPS`: new group "od <D>" (`audit_ledger.py:148`).
30. Registry: `T-SCHEDULE-TERM-FORWARD` (registered before D, window from D, rule F7); `check_test_registry.py`.
31. Docs: `model-state.md` (switch, date, measurement, evidence, ledger group); CLAUDE.md "Confidence" section;
    Polish `docs/sofa/PIPELINE.md`, `CONFIG.md`, `RUNBOOK.md`; report `docs/sofa/history/`.
32. Gates: `pytest tests/sofa -q`, `ruff check src/bet/sofa scripts/sofa`, `mypy --strict --no-incremental src/bet/sofa
    scripts/sofa`, `check_test_registry.py`.
33. E2E: rebuild a scratch copy of a settled day (never the real runs dir; md5 the real files) with the clock at D;
    `day_status.py`; verify markers and floors.
34. Commit own paths only; push only the verified SHA; confirm `origin/main` did not move under it.
35. Day D: first build checked (`rebuild_plan` re-run, `config_sha`, `WARN rating_market_gap` absent).
