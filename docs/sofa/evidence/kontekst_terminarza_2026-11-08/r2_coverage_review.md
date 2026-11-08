# R2 - Coverage review of draft_plan_v1 (schedule / fatigue into football + tennis forecasts)

Read-only, 2026-11-08, HEAD e4fb587d + working tree. Independent of round 1: the market list was rebuilt from
`05_sheet.json` of 4 days (10-25, 11-04, 11-07, 11-08; every football / tennis row, its notes and estimator markers;
script `r2_sheet_inv.py`, outputs `r2_sheet_inv_*.txt` in this folder), the code lists (`metrics.FOOTBALL_METRICS` 58,
`TENNIS_METRICS` 28, `CARD_INCIDENT_SCOPES` 11, module `MARKETS` constants) and the curve keys of
`config/sofa_confidence_calibration.next.2026-11-07.json`. One read-only DB peek (latest 20k rowids of
`sofa_listed_event`). "SUSPICION" = inferred, not measured.

Verdict on round 1: its family table is right (sheets give exactly 133 football / 44 tennis keys on each of the 4 days,
the 9 sim keys only from 11-06) and its estimator attribution matches the row notes. What it and the plan miss is
listed below. Severity: BLOCKER = the plan as written cannot deliver its own goal or produces a wrong result;
MAJOR = a family / effect silently left out or a downstream break; MINOR = completeness.

---

## A. Market coverage (task 1)

1. **P3 "Tier 1 for all 58 team metrics" is impossible as written.** `centre_replay.walk` raises
   `ValueError("not a rated base metric's market")` for any market whose `base_metric` is None
   (`src/bet/sofa/centre_replay.py:90-94`; `football_rating.base_metric` `football_rating.py:254-262` accepts only the
   14 `BASE_METRICS`, `:68-83`), and the history pickle stores values only for those 14 (`_stats_values` loops
   `BASE_METRICS`, `football_rating.py:323-341`). Out of reach of Tier 1: `saves_*` (4), `throw_ins_*` (6),
   `goal_kicks_*` (6), `tackles_*` (2), `shots_2h_*`, `shots_on_target_2h_*`, `fouls_2h_*`, `offsides_1h/2h_*` (10),
   `xg_*` - 28 of 58 keys, plus every player prop, shot detail, card-half, red / penalty event and tennis key.
   Severity **BLOCKER** (P6 promises a row for every family). Fix: P3 gets a second extractor - per-match values of
   every `FOOTBALL_METRICS` key through `metrics.extract_metric` from `sofa_event_stats` (as SAMPLES / SETTLE read them),
   and a sample-only centre (last-10 shrunk to league rate, the SHEET K per market) for the 28 non-base keys; say
   explicitly which centre each key is judged against.

2. **The family list must come from code + curves, not from observed rows.** Keys with installed curves (or mapped by
   OFFER) that no sheet of the 4 days held: `goal_kicks_1h/2h_for/_total`, `red_cards_1h_for`, `both_red_cards`,
   `games_won_set3_for`, `both_over_corners_1h/2h`, `both_over_fouls_1h/2h`, `both_over_shots_1h/2h`,
   `handicap_fouls[_1h/_2h]`, `handicap_offsides`, `handicap_saves[_1h]`, `handicap_throw_ins`, `handicap_goal_kicks`,
   `handicap_tackles`, `handicap_goals[_1h/_2h]`, `most_goals` (curve keys of `.next.2026-11-07.json` minus
   `r2_sheet_inv_1107.txt`); `classify_derived_market` generates `most_/handicap_/both_over_` over any base metric and
   half (`market_mapper.py:715-835`). Severity **MAJOR** (operator: not one market missed). Fix: P0's market list =
   union of `FOOTBALL_METRICS`, `CARD_INCIDENT_SCOPES`, `football_result/1x2_dnb/score_markets/incidents/card_halves
   .MARKETS`, `epochs.FOOTBALL_SIM_MARKETS`, player + shot-detail names, derived prefixes x base metrics,
   `TENNIS_METRICS`, `tennis_sets.SET_MARKETS`, `tennis_rating.RATING_PRICED/SET_RATING_PRICED_MARKETS`,
   `epochs.TENNIS_POINT_MODEL_MARKETS` / `TENNIS_HANDICAP_POINT_MODEL_MARKETS`, the derived tennis joints and every
   calibration key; each latent key gets a row "reach = same as <sibling>" so it is not dropped when it first appears.

3. **Round-1 attribution checks (no misclassification found, two wording traps).** (a) Tennis `handicap_games` /
   `most_games` rows carry only `DERIVED: joint ... rho=+0.000 (UNMEASURED, independent)` in their notes, yet p comes
   from the rating neighbours via `derived_rating_p = _stats_only_rating_p(rating)` (`run_sheet.py:1355-1369,
   3628-3633`). (b) `games_set1/2_total` rows say `forecast_source: tennis_rating` while p_central is the point model
   (`run_sheet.py:3259-3270`). A replay that classifies rows by notes / `forecast_source` will misfile both. MINOR.
   Fix: P3 classifies by market key against the code dispatch, never by notes.

## B. How a correction reaches each family (task 2)

4. **Blended rows: E1-only reaches 30-95% of the centre, and E1 + E2 together double-counts.** Centre =
   w x rating + (1-w) x shrunk sample with per-market w (`config/sofa_rating_weight.json`: goals_for 0.95,
   goals_1h_for / 2h_for 0.8, **goals_1h_total / goals_2h_total 0.3**, fouls_for 0.65, others 0.75-0.9; `goals_total`
   and other unlisted rated keys `W_FOOTBALL_RATING` 0.5). The plan's P5 "factor on the centre, both entry points"
   leaves undefined whether E2 multiplies a centre whose rating half already carries E1. Severity **BLOCKER** (the
   effect size measured in P4 on the final centre is not the one installed). Fix: one rule written in P5: E1 (inside
   `FootballForecast.centre`) is the term for the pure-rating consumers and supremacy; for blended marginal rows the
   term is applied once to the final centre (E2) with the rating half read uncorrected - or E1 + E4 (rescale the
   sample half), never E1 + E2. P4's residual is computed against exactly the centre the chosen rule produces.

5. **Season phase / layoff confound is built into the live chain.** `season_phase` is an E2 term on the 6 goals
   markets (`centre_chain.py:193-208`) and the `season_early` curve class reads rounds 1..3 for 1X2 / DNB / score
   markets (`football_1x2_dnb.py:162-170`, `season_phase.py:51-87`); the plan's strongest prior signal (both sides
   >= 21 d idle) is mostly a season start (10-05 note "confounded with season start"). Tier 1's centre has no season
   phase (`centre_replay.py` docstring :5-27). Severity **MAJOR**. Fix: P4 residuals against a centre that already
   carries the live season-phase term; layoff buckets reported separately for round <= 3 and > 3; a correction on a
   `season_early`-classed leg must be shown not to double-count that class curve.

6. **Congestion is correlated with team strength; Tier 1 lacks every supremacy term.** Clubs playing midweek in Europe
   are favourites; Tier 1 omits GAME_STATE, count / goals / closeness / player stretch and referee
   (`centre_replay.py:22-27`), all functions of supremacy. A congestion bucket's residual will absorb the missing
   supremacy stretch. Severity **MAJOR** (answers open question 1: Tier 1 is not valid as is). Fix: Tier 1 centre must
   include the live supremacy terms (`centre_chain.apply_team_terms` can be called on the replay centre with the
   installed tables) or P4 must stratify by supremacy bucket; referee only for cards / fouls.

7. **Dispersion is not in the plan at all.** Variance sources: `count_dispersion` alpha per (market, competition)
   (`run_sheet.py:3123-3130`, `engine.py:298-345`), the result-model NB `nb_r` 7.586 global
   (`config/sofa_football_result.json`, MEASURED, not fitted), the sim's `goal_frailty` / `count_alpha`
   (`football_sim.py:527-545`), tennis `FORM_VAR` / `FORM_COV` and `drift_per_day` (point model). Fatigue / rotation
   may raise variance (upsets, lopsided scores) without moving the mean; a mean-only factor cannot express it and
   P4's log-ratio residual cannot see it. Severity **MAJOR**. Fix: P4 adds a pre-registered dispersion test per bucket
   (Pearson chi2 / df of the NB residual, and the result model's draw / upset rate vs its NB p); P5 allows an alpha
   (or nb_r) multiplier per bucket only if that test passes.

8. **Halves: a 2H-only effect cannot be expressed on several paths.** (a) 2H non-goal counts (`shots_2h`,
   `sot_2h`, `fouls_2h`, `offsides_2h`, `throw_ins_2h`, `goal_kicks_2h`) and `corners_2h_total` are sample-only - E1
   never reaches them. (b) Card halves are the full-match `cards_points_for` centre x a fixed competition half share
   (`run_sheet.py:1934-1970`, note "half 2, share 0.681"): a fatigue term moves 1H and 2H alike; a 2H tilt needs a
   context-dependent share. (c) The simulator draws goals on a global `goal_profile` per minute bin
   (`football_sim.py:530`) from the 90-minute centre only (`football_sim_sheet.centres_of`, `halves={}`,
   `football_sim_sheet.py:66-80`): `htft`, `result_1h/2h`, `higher_scoring_half`, `team_scores_both_halves`,
   `btts_halves`, `half_goals_combo` can only move through the total. Severity **MAJOR**. Fix: P2/P5 fit the term per
   (metric, half) with "1H = 2H" as the null; where 2H differs, a 2H-share term for card halves and a goal-profile tilt
   (2H vs 1H log multiplier by bucket) for the sim, both measured in P4.

9. **Joints: raw-sample joints are unreachable by any listed entry point.** Only goals / corners / SOT / cards_points
   full-match joints are centred on marginal rows (`epochs.DERIVED_MARGINAL_CENTRES_METRICS`, `epochs.py:224-226`);
   every half joint (`both_over_goals_1h/2h` - the biggest raw group, `most_corners_1h/2h`, `handicap_shots*`,
   `both_over_saves*` ...) is a joint of raw side samples (sheet note `DERIVED: joint of both sides, rho=+0.000`,
   no FOOTBALL_RATING / chain note). Rho from `sofa_side_correlations.json` is context-free. Severity **MAJOR**. Fix:
   P5 includes a joint path - scale each side's raw-sample values by its side term before `build_joint`
   (`derived.py:536-545`) - and P6 scores joints on their own rows; or the plan names them "not reached" with the
   reason, visibly.

10. **Pure-rating / league-rate events.** `red_cards_total`, `penalties_total`, `red_cards_1h_total`,
    `penalties_1h_total`, `both_red_cards` read the competition rate only (sheet `src: league_rate`); side reds /
    penalties read league rate x exp(beta x supremacy) (`football_card_halves.py:535-545`). "Tired defenders concede
    penalties / see reds late" is a plausible fatigue effect the plan cannot even test. Severity **MAJOR** (operator's
    no-gap rule). Fix: P4 tests a fixture-level multiplier on the league rate by both sides' buckets (Poisson on
    incidents, history from `sofa_event_stats.incidents`); P5 an E5-style rate term if it passes.

11. **Player props: fatigue acts through minutes and rotation, not only through T.** Samples are his starts
    (`PLAYER_STARTS_ONLY`), a non-starter voids (refund) - so rotation risk costs nothing, but a congested starter is
    subbed earlier: his count scales with minutes. Only shots / SOT / fouls follow the team centre via share
    (`config/sofa_player_share.json`, 3 markets; `player_share.TEAM_METRIC` lists tackles but the config has no cell);
    tackles / interceptions / offsides / fouls drawn / assists and the 8 shot-detail props read his own sample only.
    `minutesPlayed` per player is in cached post-match lineups (`players.py:262-263, 351`; sheet note
    `PLAYER_MINUTES: median 90'`). Severity **MAJOR**. Fix: P2 adds per-player features (his minutes in the last 7 /
    14 d, starts in a row, team congestion); P4 measures his count residual per start by them; P5 a player-level
    multiplier applied to every prop family (share and non-share, shot detail through his centre).

12. **Tennis: symmetric fatigue is invisible to the rating and to the neighbours.** Rating features are home-minus-away
    differences only (`tennis_rating.features`, `tennis_rating.py:473-498`), neighbours are chosen by calibrated p
    alone (`_window`, `:775-791`). Two tired players -> same p -> same games / sets / set-score distribution. That
    covers `games_won_for`, `handicap_games`, `most_games`, `sets_total` (0.60 floor), `games_won_set1/2/3_for`,
    `set1/2_won_for`, `set_score`, `set_score_not` and half of `games_total`. Severity **BLOCKER** for the totals goal.
    Fix: P5 tennis adds a sum-of-load feature to the neighbour selection (second key, or a conditional neighbour table
    by joint load bucket) or moves these families to the point model where a per-player serve / return shift acts on
    both; P4 measures residuals of games / sets totals given p by joint-load bucket.

13. **Tennis point model: a constant serve shift cannot express within-match fatigue.** `simulate` draws one
    serve-point probability per player per simulated match and uses it for every point of every set
    (`tennis_point_model.py:659-720`, `p_serve` fixed). "Set 2 / set 3 after a long build-up" (per-set games totals,
    per-set aces / DF / serve points, per-set handicaps, the third set) needs a decay with points played. Also: the
    ratings learn from fatigued matches (`PointModel.update`), so a forecast-only shift is partly double-counted.
    Severity **MAJOR**. Fix: P5 point model term = shift(prior load) + slope x points played in this match (fitted on
    set-level serve stats, ALL / 1ST / 2ND / 3RD groups exist in `statistics_json`); the same term applied in
    `update` (learn net of fatigue), tested against forecast-only.

14. **Tennis sample-estimator families are not reached.** `tiebreaks_total` (sample, curves live-only-stripped),
    `most_aces[_set1/2]`, `most_double_faults_set1/2`, `most_serve_points[_set1/2]`, `handicap_aces` (raw-sample
    joints; sheet notes `DERIVED ... rho=+0.000`) and the sample half of `games_total`
    (`W_GAMES_TOTAL_RATING` mix, `run_sheet.py:3252-3256`; also on the 0.60 floor). The plan's tennis P5 (rating
    refit + point-model shift) touches none of them. Severity **MAJOR**. Fix: either price tiebreaks and the serve
    joints from the point model's simulation (it already simulates tie-breaks and serve counts) or a centre
    multiplier on the sample (pattern `tennis_aces_correction`, `run_sheet.py:1169`); games_total's sample half gets
    the same term or the mix weight is refitted.

15. **E1 must also go into the table book, and the rating update must be consistent.** SHEET prices each fixture on
    two rating books (`run_sheet.py:3822-3843`), 35 families take the table book's row. The rating learns attack /
    defence from matches played tired (`RatingBook.update`): adding a term to `expected` without the same term in the
    surprise of `update` shrinks the learnt effect toward zero over time. Severity **MAJOR**. Fix: P5 E1 applied in
    both books and in `update`'s expectation; P7 compares forecast-only vs forecast + update.

## C. Features missing from P2 (task 3) - all computable from the cache, Sofascore only

16. **Opponent's fatigue in a side's `_for` model.** P2 lists per-side features and the rest difference, but P4/P5
    describe a factor "per metric" without saying the side model reads both its own and the opponent's buckets (a
    tired opponent concedes). MAJOR. Fix: side term = f(own bucket) x g(opponent bucket), totals f(both); pre-register.

17. **Previous match went to extra time / penalties.** Listing `status.code` 110 / 120 and
    `metrics.played_extra_time` (`metrics.py:21-45`) - on every listing payload. Note history values drop extra-time
    events (`football_rating.py:328-329`) but the calendar must keep them as load. MAJOR (cheapest strong fatigue
    signal). Fix: P2 adds "120 minutes in the previous match" and minutes-weighted load (90 / 120 + added time from
    listing `time`).

18. **Red card / suspensions and starters' load from lineups.** Listing payloads carry `homeRedCards` / `awayRedCards`
    when non-zero (4 of 10 finished rows sampled); post-match lineups give each starter's `minutesPlayed`. Features:
    reds in the previous match (suspension), share of the last XI's minutes played in the last 7 d, number of XI
    changes vs the previous match (rotation). MINOR-MAJOR (lineup coverage = matches with stats only; 10-23 measured
    "real XI no gain on team counts" - cite it). Fix: P2 lists them, flagged by coverage.

19. **Next match proximity (rotation before a big game).** The calendar index holds the side's next scheduled match;
    "continental / cup match within 3 days after" is a known rotation driver. As-of caveat: the start it had at
    kickoff, not after a later postponement. MINOR. Fix: P2 adds it with the as-of rule stated; placebo applies.

20. **Kickoff local hour / weekday.** `startTimestamp` + `config/sofa_country_timezones.json` (as `settle.void_deadline`).
    MINOR. Fix: P2 control feature (not fatigue, but interacts with midweek congestion).

21. **Tennis gaps.** (a) Rest measured in **hours**, not days (the rating already uses 78 h; same-day and next-morning
    matches after rain delays); (b) tie-breaks played in the previous match (`periodNTieBreak` / 7-6 sets);
    (c) qualifying -> main draw (`roundInfo.name` "Qualification", listed today but read nowhere for tennis);
    (d) doubles the same / previous day - plan says "counted for load" but the rating log is singles only
    (`tennis_rating.parse_event`) and live `schedule` reads the player's own listing; (e) previous-match finish time
    (start + duration) vs next start (night session); (f) previous opponent's serve dominance (aces faced) - weak,
    measure only. MAJOR for (a)/(d), MINOR otherwise. Fix: add to P2 with coverage flags.

22. **Explicitly out, say why.** Altitude / travel distance (venue coordinates on ~4.5% of football detail rows, none
    on listings - r1_data_replay A3), weather, coach (backfill). MINOR. Fix: P0 lists them as "not computable", not
    silently absent.

## D. Downstream breaks (task 4)

23. **Live feature path != history feature path.** Live `schedule.side_schedule` excludes friendlies
    (`schedule.py:221-243`) and reads only the side's own `last` pages + index (`samples.cached_listing`,
    `samples.py:1246-1263`); P1 builds history from the union of listings with friendlies and doubles counted. A term
    fitted on one and served on the other is mis-specified. Also `context_flags` / dossier `schedule` /
    PDF tags read the same object (`run_confidence.py:292-296`, `dossier.py:701`). Severity **BLOCKER**. Fix: one
    feature function used by both the history replay and SAMPLES (new fields, old display flags kept byte-identical),
    with a test that a replayed fixture gives the same features as SAMPLES wrote for it on a settled day.

24. **Every curve fitted on the old p.** Football: `by_market_direction` / thin / `by_class` (women,
    season_early), per-line curves (33 keys, `config/sofa_line_curves.json`), score-market slices
    (`fit_score_market_curves.py`), DC / 1X2 / DNB, incident / card-half curves, joint curves +
    `sofa_side_correlations.json`, `sofa_football_sim_curves.json`. Tennis: `match_won_for`
    (`fit_tennis_winner_curve.py`), set curves, `set_score_not`, `sofa_tennis_point_curves.json`,
    `sofa_tennis_handicap_point_curves.json`, `tennis_rating.json` itself (neighbour table p changes for every
    history row). Plus the centre-term tables fitted on supremacy / rating centres (`sofa_rating_weight.json`,
    `sofa_game_state.json`, count / closeness / goals / player stretch, season phase, referee). P8 says "curve refits"
    only. MAJOR. Fix: P8 lists each file with its fit script and replay flag (`calibrate_from_cache` new
    `CentreRules` field, `prepare_refit` `replay_rules`), and states which tables are re-fitted vs re-checked.

25. **Line evidence reads stored p.** `fit_line_evidence.py:1-30` reads `07_settled.json` p_central through the
    installed curve; the point model, sim and vb rally each needed a p backfill (`fit_line_evidence.py:354-421`).
    MAJOR. Fix: P8 adds a backfill of the corrected p for every reached key's settled Superbet lines (10-13..), or
    a stated mixed-evidence period.

26. **Frozen floors measured on today's chain.** Tennis 0.60 for `games_total` / `sets_total` and football sim 0.60
    for 4 keys (`epochs.py:3692-3716, 3835`) were "each measured on its own band, frozen rule". MAJOR. Fix: P8
    re-measures each floor on the corrected p before the switch; until then the floor reads the uncorrected p or
    the switch excludes those keys.

27. **MODEL_ABOVE_OWN_SAMPLE.** Removes a football leg (props excluded) whose p exceeds its own-sample hit rate by
    > 0.15 (`confidence.py:705-737`, `run_confidence.py:957-969`). A term that moves p away from the raw sample by
    design (the sample does not know today's fatigue) increases removals. MAJOR. Fix: P7 reports printed / removed
    counts with and without the term, and the removed legs' realised rate, before any switch.

28. **rating_market_gap parses SHEET's notes.** It regex-reads "pure rating centres home X / away Y" and the
    FOOTBALL_RATING note wording (`rating_market_gap.py:103-111, 238-280`); a reworded note gives
    `WARN rating_market_gap` on >= 20 football matches, and D >= 1.0 was measured on the old rating margin. MINOR.
    Fix: keep note wording or extend the parser with a test; re-check D on the corrected rating.

29. **SAME_EVENT_DEDUP twins on different estimators.** E.g. a side's `goals_for` over 0.5 (blended marginal) =
    `result_or_btts` of that side (pure rating); `btts_any_half` UNDER = `btts_halves` (both sim). If the term
    reaches one twin and not the other, confidences of one event diverge and the dedup's "higher price, then lower
    confidence" pick can flip. MINOR. Fix: P6 reports twin-pair disagreement before / after
    (`bet.sofa.leg_identity` pairs).

30. **Plumbing a switch needs.** New config in `sheet_config.SHEET_CONFIG_FILES` (config_sha), row marker field in
    `contracts` + `rebuild_plan` re-run, `UNFITTED_CONSTANTS` names, `audit_ledger.EPOCH_GROUPS`, model-state.md,
    analysts' contracts (`tennis-analysis` / `football-analysis` treat fatigue as a note - they must be told the model
    now carries it, or WATCHes double-count), dossier display of the term. MINOR. Fix: P8 checklist.

31. **Scoring population.** Retired / walkover tennis and awarded football are refunds / excluded
    (`settle.REFUND_REASONS`, `AWARDED_EXCLUDED`); fatigue raises retirements, so P6/P7 must score the
    completed-match population as SETTLE grades it and report the retirement rate by bucket separately. MINOR.

32. **Residual form for low counts (open question 3).** log(y / centre) is undefined at y = 0 (reds, penalties,
    offsides, 1H goals). Use the season-phase template's Poisson-MLE log(sum y / sum centre) per bucket and NB
    log-loss (`measure_season_phase.py`), not a per-match log ratio. MINOR.
