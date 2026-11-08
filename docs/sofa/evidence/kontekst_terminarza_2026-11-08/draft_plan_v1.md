# DRAFT v1 - schedule / fatigue context into the forecast (football + tennis)

Inputs: r1_football_inventory.md, r1_tennis_inventory.md, r1_data_replay.md, r1_evidence_literature.md (same folder).

## Goal (operator, 2026-11-08)
Not an edge over the price. The pipeline's own forecast of every football and tennis market should be as accurate as
possible: the centre closer to what happens, the confidence equal to the hit rate ("we say 75% -> 75% happens").
Judged on history with known results, without Superbet's price (price only reported beside, never the criterion).
Football and tennis first; other sports only after a pass.

## What exists (round 1)
- Football: schedule computed in SAMPLES (`samples.py:2331`, `schedule.py`) -> context_flags, display only. Measured
  10-04/05 vs raw sample (both sides >= 21 d idle: goals -0.12, corners -0.28; logloss gain -0.00015, declined; confounded
  with season start) and 11-05 vs price (rest days pass only shots / SOT totals; back-to-back 0/67, travel 0/80).
  Never measured vs the MODEL centre. Template: season_phase.py / measure_season_phase.py / fit_season_phase.py.
- Football reach: two entry points. (a) SHEET centre chain (referee / closeness live here) -> team counts, goals rows,
  player props via share; NOT result/score markets. (b) inside the rating (`FootballForecast.centre`) -> result/score
  markets (51% of >= 0.70 legs), simulator, stretches; only the rating half of blended rows.
  Unreachable: league-rate (reds, penalties, both reds), shot-detail props, assists/tackles/interceptions/offsides/
  fouls-drawn props, half-scoped both_over joints (raw samples, 3,051 legs >= 0.70). corners_total has no correction path
  at all today (needs a total-level term).
- Tennis: fatigue only in the rating (dmin78, drest, dn7 + dform/dhigh/dtour; fitted 10-08, cut 10-01, maybe before the
  10-27 best-of-five fix). dmin78 reads missing durations as 0 (ITF ~18% coverage) -> tired ITF player looks rested.
  dn7 positive = probably selection (still winning). Point model (games per set, aces, DF, serve points, per-set handicap)
  and old sample estimator read no fatigue. Points played (pointsTotal) has near-full coverage -> a better workload measure.
  No travel data (tournament city/country empty).
- Data: calendars from the union of listings (93.8% football / 83.2% tennis sides covered; real misses 1.5% / 2.2%);
  competition kind available; venue coords ~4.5% only; coach needs a 93k-190k request backfill (endpoint unverified).
- Machinery: Tier 1 `centre_replay.walk` (centre + actual per match/side/metric, ~50 s, approximates SHEET without
  stretches/referee/form table); tennis `tennis_point_model.walk_forward` (155 s load) and the rating fit. Tier 2
  patched `calibrate_from_cache` on a VACUUM copy (~1.4 h per 5-day window, 5-6.5 h full).

## Plan
P0 Pre-registration (written BEFORE any residual is looked at): features and buckets, periods, scoring, decision rule,
   the complete market list with reach status. Periods: development 2025-01-01..2026-05-31, hold-out 2026-06-01..
   2026-10-31 (touched once), our settled days 10-13..11-07 = audit only.
P1 As-of calendar index: strictly before kickoff, union of listings, friendlies and cups and doubles counted for load
   (even though excluded from samples), only matches actually played (postponed excluded), a coverage flag - unknown
   calendar = missing, never 0 (the ITF dmin78 lesson).
P2 Feature list (frozen):
   Football per side: rest days (buckets <=2, 3, 4-5, 6-8, 9-20, >=21), matches in 7/14/21 d, rest difference between
   sides, continental match in the previous 4 days, international-break return, season round (control, season_phase),
   knockout/cup context, cross-border trip proxy (team countries differ), time-zone difference (team countries).
   Tennis per player: points played in last match / last 3 / 7 days, minutes on court (coverage-flagged), sets played
   last match, five-setter, matches in 7 d, rest days, layoff >= 21, recent retirement, surface switch vs previous
   tournament, consecutive tournament weeks, indoor/outdoor switch.
P3 Baseline replay on dev+hold-out: football Tier 1 for all 58 team metrics (full/1H/2H, _for/_total) + the rating's goal
   centres per match (result markets); tennis rating p per match + point-model per-match means (games/set, aces, DF,
   serve points) + neighbours families.
P4 Residual analysis on dev only: residual = actual / centre (log ratio) by feature bucket, per metric, per sport;
   match bootstrap; BH across cells; placebo test (rest AFTER the match must show nothing); control season phase and
   competition; team quality controlled by measuring against the model centre (team's own level already in it).
P5 Correction design: shrunk multiplicative factor per metric group on the centre (football both entry points + a
   total-level term for corners_total); tennis: refit rating features (points-based workload, coverage flag, dn7
   reconsidered) + a serve/return rate shift in the point model. Fitted walk-forward month by month on dev.
P6 Scoring on dev: NB / point-model log-loss per line at market-like lines, Brier, calibration of rows >= 0.70; a row in
   the result table for EVERY market family (133 football, 44 tennis): reached / not reached / changed / effect.
P7 Hold-out exam once with the frozen correction. Pass = log-loss better with CI excluding 0 per family group, no group
   worse beyond a pre-set tolerance, >= 0.70 calibration not worse.
P8 Only for a pass: Tier 2 full SHEET replay on a DB copy, curve refits (operator's go), epochs switch next day 00:00Z,
   tests, docs, line evidence backfill of p, check MODEL_ABOVE_OWN_SAMPLE interaction.
P9 Polish report; then hockey / basketball / volleyball / CS2 with the same harness.

Out of scope now: weather (needs a non-Sofascore source - operator's rule), coach change (backfill first, phase 2),
conflicts / morale (not measurable on history; analyst only).

## Open questions for review
- Is Tier 1 (approximate SHEET) a valid place to judge a correction, given stretches/referee/form table are missing?
- Are the periods right (season boundaries, 2024 thin)?
- Is log ratio the right residual for low counts (reds, offsides, goals 1H)?
- Anything missing from the market list or feature list?
