---
name: tennis-analysis
description: How to analyse one tennis match's length and serve markets in the sofa pipeline (total games, a player's games won, total sets, aces, double faults, serve points, per-set variants, and the derived most_/handicap_ markets) - surface first, format second, opponent quality of the sample, serve/return decomposition, hold vs break, scoreline arithmetic for every rung, schedule and fatigue, price last. Use when reading a sofa tennis sheet, grading VALUE rows, judging a tennis Bet Builder leg, or writing vetoes. Preloaded into sofa-analyst-tennis.
---

# Tennis analysis — the method, mapped to what `sofa` actually holds

`sofa-pipeline` and `sofa-analysis-core` are preloaded with you. Tennis differs
from football in four ways that change everything below.

1. **There is no source of record.** `bzzoiro-tennis` answers
   `402 addon_required`. No MCP, no model, no consensus. Verification is web,
   two domains, tagged — and **game-level ITF statistics are not available
   free**, so "unverified" is often the honest answer and you must say it
   rather than manufacture a source.
2. **The sample is two individuals**, each with their own surface, format and
   schedule history.
3. **Every market is a function of match length.** A short match settles every
   UNDER at once, so a two-leg tennis slip is usually one bet with two prices.
4. **`K_CENTRE` for tennis is 2**, against football's 25. A tennis row is
   almost entirely its own sample — at n=10 the sample owns **83%** of the
   centre. There is far less league prior propping it up, in both directions.

Tennis is usually about two thirds of the board.

| reference | open it when |
|---|---|
| `references/data-inventory.md` | what is measured, which rungs exist, how the sample is scoped, what is *not* carried |
| `references/methodology.md` | the model behind a claim — point-based hierarchy, serve/return, surface and format effects, H2H decay, fatigue, retirements |
| `references/market-playbook.md` | grading a specific market: drivers, scoreline arithmetic, kill cases |
| `references/event-protocol.md` | writing a match section |

The operator's method: `docs/legacy/SUPERBET_BET_BUILDER_METHOD_v3.md` — a
pre-`sofa` document. The method outlived the pipeline it was written for; its
claims about *code* did not. Cite sections, take no behaviour from it.

## What the code already does

`samples.py` scopes each side's observations to tonight's **surface**
(`event.groundType == fixture.ground_type`) and **format**
(`infer_best_of(event) == fixture.default_period_count`). Both come off the
fixture, so both are real rather than inferred from a competition-name pin —
which is a genuine improvement over the retired pipeline, where surface never
reached the scoping at all.

`sets_total` and `games_won_for` are priced by the **sample's own frequency**,
not by a bell curve. `sets_total` is bounded (2 or 3 on a best-of-three) and
`games_won_for` is violently bimodal — a straight-sets winner has at least
twelve games, so the distribution has a loser mode spread over 0–11 and a
winner mode stacked on 12+. Across 570 observations in one day: 10:17, 11:10,
**12:159**, 13:84. Superbet's line sits at **11.5, in the trough.** A normal
CDF puts smooth density exactly where the real distribution has almost none.

For every other tennis metric `p_central` comes from a count model, so it will
**not** equal the sample hit rate.

## What the code cannot see

- the round (R1/QF/final), and that **qualifying is best-of-three even at a slam**
- either player's ranking, or the ranking of any opponent in the sample — the
  `opponent` field is a name and nothing more
- the previous match: its length, its date, hours of rest, a three-match
  qualifying route
- retirement risk, a walkover, a late withdrawal
- indoor versus outdoor, altitude, ball type, wind
- whether the competition's surface pin is right at Challenger/ITF level, where
  coverage is thinnest

## The protocol — surface first, format second, price last

For every tennis fixture with a `VALUE` row, every fixture appearing in
`08_confidence.json`, and any fixture you intend to veto.

1. **Identity, both clocks, format, surface.** From `02_fixtures.json`:
   `competition_name`, `ground_type`, `default_period_count` (for tennis this
   **is** the real best-of), `identity`, `kickoff_utc`,
   `superbet_kickoff_utc`, `kickoff_disagreement_h`.
   **The clock disagreement is structural and reaches 11 h on ITF** — Superbet
   posts a nominal "not before", Sofascore appears to publish the tournament's
   local time as UTC, and the error runs the wrong way: a finished match looks
   upcoming. Take the **earlier** clock. Then verify against the tournament's
   order of play, tagged, before spending anything else.
2. **Sample integrity, per side.** `03_samples.json`: how many observations
   survived the surface and format scope, their dates, their opponents. **A
   side with 0–3 scoped observations is not a sample.** If a total's split
   shows one side at zero, the "total" is one player's history wearing a
   match's name — veto it `SAMPLE_UNINFORMATIVE`.
3. **Opponent quality of the sample.** Look the `opponent` names up and
   classify the sample's opposition. A `games_won_for` mode of 12 built
   against ITF fields says nothing about tonight's seed.
4. **Serve / return decomposition.** From `aces_for`, `double_faults_for`,
   `serve_points_for`, plus the web for hold %, return points won, tie-break
   record on this surface. Is this a high-hold competitive OVER, a
   breaks-and-three-sets OVER, or a one-sided UNDER? **Aces ≠ tie-breaks. A big
   serve does not mean over games** — it often means the opposite, because
   holds are quick.
5. **Distribution and scoreline arithmetic.** The sample's min, max, median,
   mode; then the concrete scorelines that settle each rung. `6-3 6-4` is 19
   games. `7-6 6-7 7-6` is 39. A player's games in `6-2 6-3` is 5. Which rung
   does the **modal** scoreline land on?
6. **Schedule and fatigue.** Previous match: sets, games, duration, date;
   back-to-back days; a qualifier carrying three extra matches; a retirement
   in the last month. Web, tagged.
7. **H2H with decay.** A supporting prior, never the primary signal.
   **`h2h` observations never reach a `*_for` row** by design.
8. **Scenario matrix.** Favourite pulls away / underdog holds serve / both
   first serves work / tie-break or deciding set. Which is modal, which kills
   the market. **`sofa` carries no match-odds price**, so the favourite's
   strength is not in the artifacts — say so or source it and label it.
9. **Ladder and tail.** Every rung Superbet posts for this market with
   `p_central` / `p_bar` / `offered` / `required` / `surplus`. A third set adds
   12–15 games to a two-set match — the tail is huge and one-sided.
10. **Price — last, and there is often nothing to check it against.** When the
    rung is one-sided, `market_p` is null, the bar is unanchored
    (`NO_MARKET_MARGINAL`), and `p_bar` is just `p`. Say so.
11. **Buy case / kill case → verdict** `KEEP / WATCH / NO BET` + the veto entry.

## Kill cases this repo has already paid for

- **One side scoped to zero.** A `double_faults_total` with n=9, all of it one
  player, because the surface scope removed every one of the other's matches.
  Check the `side_a` / `side_b` split on **every** total.
- **A sample from the wrong surface.** Aces 5.5 OVER built on grass
  observations for a hard-court match; the hard-court medians were 6.0/5.0
  against grass 9.0/11.0. `sofa` scopes on `ground_type` — but at Challenger
  and ITF level that field is the thinnest part of the data. When it is
  missing, the scope silently does nothing. **Check it.**
- **Opponent class not conditioned.** A `games_won_for` 9.5 OVER with a mode of
  12 against much weaker fields, against a far stronger opponent tonight.
- **Best-of-three tautologies priced as best-of-five.** `sets_total UNDER 3.5`
  at 15/15 from a BO3 sample on a BO5 event. `default_period_count` is the
  guard; if it is null, the scope did not run.
- **The line in the trough.** `games_won_for` 11.5 sits between the loser mode
  and the wall at twelve. The empirical estimator handles it; a normal one did
  not, and it ran predicted 0.404 against realised 0.320 on 862 settled rows.
- **Identical `p_central` across three rungs.** No observation falls between
  them, so the model and not the sample separates the prices.
- **Certainty for free.** A `sets_total UNDER 3.5` on a best-of-three is a
  tautology. CONFIDENCE refuses anything under 1.0867 and `outside_model_resolution`
  refuses a `p_raw` outside [0.05, 0.95] — but check the rung yourself.
- **The empirical frequency is overconfident at the top.** On 9,286 settled
  `games_won_for` rows a claimed 0.95 realises **0.728**, and that market has
  no measured bucket above 0.825. A high `p_central` on this market is the one
  number you should trust least.
- **A short match settles every UNDER at once.** Sets, games, aces and double
  faults are one mechanism. A tennis Bet Builder of two UNDERs is one bet
  charged twice — and `confidence.py`'s quantity families put `games_*`,
  `sets_*` and `handicap_games` in the **same** family for exactly that reason.

## Tennis-specific output requirements

Per match, always state: tour and format from `default_period_count`; surface
from `ground_type`, **or explicitly that it is unknown**; round and start time
as verified, on both clocks, with the disagreement in hours; each side's
scoped `n` and the class of the opposition behind it; the previous match where
you found it; and once, in the header, that tennis has **no source of record**
— not once per row.
