# Football market playbook — drivers, what settles it, how it fails

For each market: what it measures here, what moves it, the base rate, the
kill cases, and what a good read says. Base rates are in-repo (700 matches,
ten leagues; 7,516 for goals) unless stated.

## Corners (`corners_total`, `corners_for`)

- **Measures:** corners awarded, both sides / one side. Sample last ten,
  season-scoped, venue prior applied to `_for` rows (home > away, z≈5).
- **Drivers:** attacking volume and *width* (crosses, full-back involvement),
  the opponent's block depth (deep block ⇒ blocked shots ⇒ corners), game
  state (trailing side wins corners without winning), pitch and weather (wind
  argues down). **Goals ↔ corners ≈ 0**: a goal-heavy match is not a
  corner-heavy one.
- **Base:** 9.5/match; >8.5 in 61%, >9.5 in 49%; per team 4.77, >4.5 in 48%.
- **Market signal:** the one totals market with a bzzoiro price and model
  (8.5/9.5/10.5). `CONFIRMS` with both numbers is the only promotion.
- **Kill cases:** team-corner OVER + total UNDER (Porto–Arouca 12–2); sample
  mean far from the ladder centre (Sheffield 2.80 vs 5.76); one side's ten
  matches in a different competition class; a 1.40 price on a per-team 4.5
  (asks 70% of a coin-flip market).
- **Good read:** "typowo 8–11, ogon do 14; obie strony szerokie; rywal broni
  nisko; scenariusz C podnosi; 10.5 UNDER siedzi na modzie — 11.5 to szczebel."

## Cards (`cards_points_total`, `cards_points_for`) — booking points

- **Measures:** Superbet's *Liczba kartek* settles yellow 1, straight red 2,
  second yellow 3 (`cards_points_*`, off `/incidents/`). The yellow-only
  `cards_total` is collected but no longer priced. Priors one slate old.
- **Drivers, in order:** the **referee** (a third of a line between officials
  in one league; home bias in cards is referee behaviour), fouls volume,
  stakes (derby, knockout, relegation), game state (0-0 late in a knockout),
  discipline profile of each side (`cards_for`), red-card propensity
  (`avg_red_per_match`) which adds 2–3 points at once.
- **Base:** `cards_points_total` 4.38 (one slate); yellow-only 3.72 over
  1,326 observations. Per team yellow 1.86, home 1.60 / away 2.11.
- **Code already:** blends the referee into the centre at `matches ≥ 15`
  (`centre_note`), caps and doubles `k` when no referee, flags derby and
  second leg. Do not double-count these in a DOWNGRADE; add what code cannot
  see (league spread, this official's reds, cup extra time, a hot rivalry the
  flag missed).
- **Kill cases:** no referee in a high-spread league; line on the mode (7.5
  with five 7s); a red in a derby second leg (+2/+3 points at once); the
  official has 3–4 matches; `RED_TYPE_UNKNOWN` flags in the sample; UNDER in
  a tie that can go to extra time (30 more minutes settle into the market).
- **Good read:** referee with `matches`, yellows *and* reds per match,
  `centre_note` quoted, both sides' `cards_points_for` distributions, stakes,
  the modal scenario, and the rung beyond the sample's max.

## Fouls (`fouls_total`, `fouls_for`)

- **Measures:** fouls committed. Rarely offered by Superbet (30 lines on a
  106-fixture board) — check `availability` before spending analysis.
- **Drivers:** referee's foul tolerance (`avg_fouls_per_match`), league
  (Süper Lig 27.9 vs Bundesliga 20.7), pressing and duel intensity,
  derby/knockout, game state (a side protecting a lead fouls to stop
  transitions). Fouls run **against** goals (r −0.13).
- **Base:** 24.3/match, >20.5 in 75%; per team 12.17, >12.5 in 45%.
- **Estimand check:** `fouls_for A mean + fouls_for B mean ≈ fouls_total
  mean`; a large gap means the pooled sample and the per-team samples describe
  different match sets.
- **Kill cases:** the misses are the h2h (Grenal 43/39/33 vs pooled 27);
  a per-team line inside the sample's mode with two values exactly one below
  (18/18 at 18.5).

## Shots and shots on target (`shots_total/_for`, `shots_on_target_total/_for`)

- **Measures:** total shots / on target. Superbet ladders start high
  (SOT 7.5+, shots 24.5+), so many sheet rungs are `LINE_NOT_OFFERED`.
- **Drivers:** attacking volume, opponent block, game state (trailing side
  shoots more, worse), **finishing regression** (xG gap flags), a 90-minute
  tempo. SOT ↔ goals +0.55: a SOT OVER and a goals OVER are one thesis.
- **Base:** SOT 8.7/match (>6.5 in 73%); per team 4.35 (>2.5 in 77%).
- **Kill cases:** mean pulled by outliers against weak opposition (Grêmio 41–50
  ×4 — the median still describes the fixture, so this is a one-step `OTHER`
  DOWNGRADE, not a zero-weight one); `ARGUES_AGAINST` xG flag on the shooting side; seven unavailable in
  the attacking side; a favourite that scores early and manages (scenario A
  kills SOT-for the favourite in the second half).

## Goals (`goals_total`, `goals_for`, `goals_1h_total`, `goals_2h_total`)

- **Measures:** read off the score, so `n` runs ahead of every other market
  (every finished match has a score, ~2 of 10 have `/stats/`). Halves from
  the half-time score. `goals_for` is the exception per-team market that can
  be corroborated (ESPN/highlightly know the side).
- **This is a priced market with a consensus.** Devig it
  (`audit_slip.py --market team_to_score …`, or the 1X2 + O/U 2.5 block in
  `market_context`) and compare; the sample's 12-straight is not an edge.
  Superbet's per-team "to score" lines sat 0.1–5.6pp **under** fair on all
  five ledger legs.
- **Halves:** first half 44.7% of goals; `1-3 each half` peaks at 52% at 3.6
  goals (`range_market_ceiling`); price floor 1.92, in practice 2.10.
- **Kill cases:** 0.5 OVER / 5.5 UNDER at 1.01–1.05 leading the sheet
  (certainty, not a bet); a Dixon–Coles-shaped model already pricing the same
  information; second leg with an aggregate that changes who must score.

## Offsides, red cards (`offsides_total/_for`, `red_cards_total`)

- **Offsides:** driven by the high line of *one* side and the runners of the
  other; Superbet's ladder starts at 2.5. Thin samples, high variance; treat
  as WATCH unless the matchup argument is specific (a high-line side vs a
  fast striker).
- **Red cards 0.5:** a rare event (0.18–0.5 per match by referee); a Wilson
  bound on 10 matches says nothing at 0.5; price only with the referee's
  `avg_red_per_match` and career reds, and never HIGH.

## Player props (`player_*`)

- **Measures:** box-score counts for appearances **with minutes**; unused
  subs dropped. Superbet prices ~10k player lines a day under free-text names;
  `PLAYER_NOT_MATCHED` is a refusal, never a price.
- **Gates (method §20–§21):** XI confirmed or the prop stays `LEAN`; expected
  minutes < 70 forbids HIGH; a player on `unavailable` is void (already
  filtered) but can go stale after ANALYZE — re-check `get_match_lineups`
  within the hour.
- **Drivers:** role and expected minutes, opponent (a full-back against a
  dribbler for `player_fouls`/`player_was_fouled`), set-piece duties for
  shots, game state (a striker on a side chasing gets shots), rotation.
- **Kill cases:** a veto that cannot name the player (widens to 20 rows —
  do not emit); `player_cards UNDER 0.5` at 10/10 near the top of the sheet
  (priced ~1.05); a rotation player with `n = 4` reading as a tight
  distribution.

## Per-team markets in general (`*_for`)

- Single-source by construction (only bzzoiro keeps the side); `LEAN`
  ceiling except `goals_for`. Tonight's `venue` selects the prior; check the
  sample's own venue mix (eight away matches for a home fixture is a thinner
  sample than `n=8` suggests).
- `both_teams_over` ("każda z drużyn") has **no** row and never will:
  `min(p_A, p_B)` is a ceiling. Report the two rows and forbid the product.

## Bet Builder (any of the above combined)

- Run `scripts/simple/bet_builder_draft.py --stats-sheet … --event-id …` and
  report verbatim (legs, each bar, `correlation_note`, `builder_score` and
  its parts). The CLI has no `--offer` flag: **confront every leg with
  `row.superbet.price` yourself** — on 2026-09-03 three of four drafted legs
  were priced below their own bar.
- Then by hand (method §40–§43, §76, §91–§93): a concrete scoreline/stat line
  satisfying every leg; whether the common region is broad or needs an edge
  case; the shared mechanism and the scenario that kills all legs; tail-risk
  and source-conflict penalties on top of the code's score. Prefer mechanism
  1 + mechanism 2 over the same market three times. Never a combined price.
