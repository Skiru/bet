---
name: tennis-analysis
description: How to analyse one tennis match's length and serve markets in the sofa pipeline (total games, a player's games won, total sets, aces, double faults, serve points, per-set variants, and the derived most_/handicap_ markets) - surface first, format second, opponent quality of the sample, serve/return decomposition, hold vs break, scoreline arithmetic for every rung, schedule and fatigue; on a leg pewność (confidence), próbka k/n and model (forecast_p), the price only as the betting filter. Use when reading a sofa tennis sheet or the coupon's tennis legs, judging a tennis Bet Builder leg, or writing vetoes and reads. Preloaded into sofa-analyst-tennis.
---

# Tennis analysis — the method, mapped to what `sofa` actually holds

`sofa-pipeline` and `sofa-analysis-core` are preloaded with you. Tennis differs
from football in four ways that change everything below.

1. **There is no source of record.** `sofa` reads Sofascore and Superbet only;
   no other provider is a source, and bzzoiro in particular must never be
   called. No MCP, no model, no consensus. Verification is web, two domains,
   tagged — and **game-level ITF statistics are not available free**, so
   "unverified" is often the honest answer and you must say it rather than
   manufacture a source.
2. **The sample is two individuals**, each with their own surface, format and
   schedule history.
3. **Every market is a function of match length.** A short match settles every
   UNDER at once, so a two-leg tennis slip is usually one bet with two prices.
4. **`K_CENTRE` for tennis is 5**, against football's 15
   (`config/sofa_engine_constants.json`, `by_sport`). A row the sample prices
   is mostly its own sample — at n=10 the sample owns **67%** of the centre.
   There is far less prior propping it up, in both directions. (Since
   2026-10-07 14:05Z `games_won_for` / `handicap_games` / `most_games` and
   half of `games_total` are not such rows: the rating's neighbours price
   them - see below.)

Tennis is usually about two thirds of the board.

| reference | open it when |
|---|---|
| `references/data-inventory.md` | what is measured, which rungs exist, how the sample is scoped, what is *not* carried |
| `references/methodology.md` | the model behind a claim — point-based hierarchy, serve/return, surface and format effects, H2H decay, fatigue, retirements |
| `references/market-playbook.md` | grading a specific market: drivers, scoreline arithmetic, kill cases |
| `references/event-protocol.md` | writing a match section |

The operator's method: `docs/sofa/SUPERBET_BET_BUILDER_METHOD_v3.md` — a
pre-`sofa` document. The method outlived the pipeline it was written for; its
claims about *code* did not. Cite sections, take no behaviour from it.

## What the code already does

`samples.py` scopes each side's observations to tonight's **surface**
(`surfaces_comparable(event.groundType, fixture.ground_type)`: equal, or a
generic "Hard" / "Clay" against any member of its family) and **format**
(`infer_best_of(event) == fixture.default_period_count`). Both come off the
fixture, so both are real rather than inferred from a competition-name pin.
A fixture with a null `ground_type` gets an empty sample (gap
`SURFACE_UNKNOWN`); a null `default_period_count` skips the format scope.
`infer_best_of` reads the format of a past match from the winner's sets (3
sets won = best-of-five, 2 = best-of-three, anything else - a retirement -
`None`).

**What prices a row (stats-only epoch, builds from 2026-10-05 07:15Z; no
price in any `p_central`).** Two estimators exist side by side:

- **The rating** (`src/bet/sofa/tennis_rating.py`): a surface-blended Elo,
  calibrated per tier (ITF / CH / TOUR; `config/tennis_rating.json`, fitted
  2026-09-30 on 239,315 history matches, cut 2026-10-01), gives the match-win
  probability; the 600 historical **best-of-three** matches with the nearest
  probability (`NEIGHBOURS`) are the score distribution, read empirically -
  so games, sets, set games and tiebreaks of one match cannot contradict each
  other. **Best-of-five is not modelled** (no neighbour is a five-setter), and
  a player with fewer than `MIN_RATED = 10` rated matches gets no forecast.
  A null `default_period_count` is read as best-of-three.
- **The sample's estimator**: the player's own scoped last ten, around the
  shrunk centre (`K_CENTRE = 5`); the empirical frequency for the bounded /
  bimodal `sets_total` and `games_won_for`, a count model otherwise.

Since **2026-10-07 14:05Z** (`epochs.tennis_rating_prices`, judged on the day
and the build clock; operator's decision, curves refit the same evening):

| family | `p_central` |
|---|---|
| `games_won_for`, `handicap_games`, `most_games` (not the draw) | the neighbours alone (`RATING_PRICED_MARKETS`) - no price, no sample |
| `games_total` | 0.5 x rating + 0.5 x the NB count model (`W_GAMES_TOTAL_RATING`) |
| `sets_total`, per-set games, `tiebreaks_total`, aces, double faults, serve points | the sample's estimator |

`forecast_p` (`forecast_source` `tennis_rating`, uncalibrated, never a gate)
is written on `games_won_for`, `games_total` and `sets_total` only - **not**
on `handicap_games` / `most_games` (checked on the 2026-10-07 sheet). On a
rated `games_won_for` row `forecast_p == p_central`; for `games_total` the
rating is half of `p_central`. **So the old reading "`p_central` is the sample, `forecast_p` is
the rating, compare them" no longer holds for those families: the rating is
both numbers, and the independent evidence on the leg is the sample's k/n.**
`sets_total` still has two separate estimators. The `K_CENTRE` shrinkage
still decides every sample-priced row, and any rated family on a fixture the
rating does not read.

A SHEET built before that moment priced these families the old way (the
sample; before 2026-10-05 the rating blended with the price,
`TENNIS_RATING`, or the empirical frequency pulled onto the price,
`P_SHRUNK_TO_PRICE` - see `references/data-inventory.md`).

`games_won_for` is **violently bimodal** — a straight-sets winner has at
least twelve games, so the distribution has a loser mode spread over 0–11
and a winner mode stacked on 12+ (one day's 570 observations: 10:17, 11:10,
**12:159**, 13:84 - a dated measurement). Superbet's line sits at **11.5, in
the trough.** The sample's empirical frequency (the old estimator) and the
rating's neighbours both carry that shape; a normal CDF does not. On a leg,
three numbers stand side by side: **pewność** (`confidence`, the calibrated
curve lowered by line evidence), **próbka** k/n (`sample_hit_rate` x
`sample_size`) and **model**; the price is only the betting condition
(x = confidence x odds >= 0.90, ladder margin <= 15%).

**Match tiebreaks (open operator question).** A 10-point match tiebreak
(ITF, UTR, team cups) sits in Sofascore's `periodN` as points. The pipeline
counts it as **one game** to its winner in every sample, neighbour and
settlement (`tennis_score.set_games`); Sofascore's `gamesWon` counts none;
bet365 counts one. **Superbet's rule for games markets is unverified** (its
regulamin does not say) - a leg a match tiebreak decides may grade
differently from the code. Name it, do not decide it. Tour and Challenger
neighbours exclude match-tiebreak matches, ITF ones include them.

**Retirement and walkover are refunds** (`settle.RETIRED`,
`settle.WALKOVER`, in `settle.REFUND_REASONS`; operator, 2026-10-07): 0 u.,
never a loss. Retired and walkover matches stay out of samples
(`is_completed_event`); the rating counts a retirement as time on court but
not as a result.

## What the code cannot see

- the round (R1/QF/final), and that **qualifying is best-of-three even at a slam**
- either player's ranking, or the ranking of any opponent in the sample — the
  `opponent` field is a name and nothing more
- the previous match: its length, its date, hours of rest, a three-match
  qualifying route
- retirement risk, a walkover, a late withdrawal (a retirement or walkover
  refunds a single leg - it is a void risk, not a loss risk)
- indoor versus outdoor, altitude, ball type, wind
- whether the competition's surface pin is right at Challenger/ITF level, where
  coverage is thinnest

## The protocol — surface first, format second, the price only as the filter

For every tennis fixture with a leg in your read set (the first 30 positions
of `11_coupon.json`, every printed builder leg, `read_requests.json` - see
`sofa-analysis-core`), and any fixture you intend to veto.

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
   in the last month. Since 2026-10-04 the start of each player's last
   finished match, the rest in days and the matches in 7 / 14 days are on
   disk (the fixture's `schedule` block in `03_samples.json`; `LONG_LAYOFF` /
   `CONGESTED` in the legs' `context_flags`) - quote them; the length and
   duration of that match are still web, tagged. A veto on it is `CONTEXT` with
   `context: SCHEDULE`; ranking points to defend are `MOTIVATION`. Where to
   look: `sofa-analysis-core` `references/context-sources.md`.
7. **H2H with decay.** A supporting prior, never the primary signal.
   **`h2h` observations never reach a `*_for` row** by design.
8. **Scenario matrix.** Favourite pulls away / underdog holds serve / both
   first serves work / tie-break or deciding set. Which is modal, which kills
   the market. **`sofa` carries no match-odds price**, so the favourite's
   strength is not in the artifacts — say so or source it and label it.
9. **Ladder and tail.** Every rung Superbet posts for this market with
   `p_central` and `offered` (and the leg's pewność, próbka k/n and model
   where it is one). A third set adds 12–15 games to a two-set match — the
   tail is huge and one-sided.
10. **Price — only the filter.** `offered_odds`, x = confidence x odds
    against 0.90, the price's `fetched_at_utc`. The code applied it; it is
    never a reason for or against the leg. A one-sided rung has `market_p`
    null (`NO_MARKET_MARGINAL`) - say so.
11. **Buy case / kill case → verdict** `KEEP / WATCH / NO_BET` + the read
    entry for every leg of your read set (WATCH and NO_BET remove it into
    `removed_by_reads`, graded apart in audit_settlement 7i) + the veto entry.

## Kill cases this repo has already paid for

- **One side scoped to zero.** A `double_faults_total` with n=9, all of it one
  player, because the surface scope removed every one of the other's matches.
  Check the `side_a` / `side_b` split on **every** total.
- **A sample from the wrong surface.** Aces 5.5 OVER built on grass
  observations for a hard-court match; the hard-court medians were 6.0/5.0
  against grass 9.0/11.0. `sofa` scopes on `ground_type` — but at Challenger
  and ITF level that field is the thinnest part of the data. A fixture with
  no surface gets an empty sample (`SURFACE_UNKNOWN`); a past event with none
  is dropped; generic "Hard" / "Clay" labels match any member of their
  family, so an indoor fixture can sample outdoor-unknown matches. **Check
  it.**
- **Opponent class not conditioned.** A `games_won_for` 9.5 OVER with a mode of
  12 against much weaker fields, against a far stronger opponent tonight. The
  rating's neighbours condition on the match-win probability but not on
  surface, serve or the sample's fields - a rating-priced row still needs your
  opposition check.
- **A format the rating does not read.** A best-of-five is not modelled - no
  `forecast_p`, the sample prices the row. A null `default_period_count` is
  read as best-of-three by the rating and skips the format scope of the
  sample: on a men's slam a null is the failure to look for.
- **Best-of-three tautologies priced as best-of-five.** `sets_total UNDER 3.5`
  at 15/15 from a BO3 sample on a BO5 event. `default_period_count` is the
  guard; if it is null, the scope did not run.
- **The line in the trough.** `games_won_for` 11.5 sits between the loser mode
  and the wall at twelve. The empirical frequency (the old estimator) and the
  neighbours handle it; a normal CDF did not, and it ran predicted 0.404
  against realised 0.320 on 862 settled rows (a September measurement).
- **Identical `p_central` across rungs.** On a sample-priced row no
  observation falls between them, so the model and not the sample separates
  the prices. On a rating-priced row (`games_won_for`) `p_central` moves in
  steps of 1/600 and the neighbours, not the player's record, set the steps:
  check the próbka k/n against it.
- **A match tiebreak decides the leg.** ITF / UTR / team-cup matches that
  reach a 10-point deciding tiebreak: the code counts one game; Superbet's
  count is unverified (open operator question).
- **Certainty for free.** A `sets_total UNDER 3.5` on a best-of-three is a
  tautology. CONFIDENCE refuses anything under 1.0867 and `outside_model_resolution`
  refuses a `p_raw` outside [0.05, 0.95] — but check the rung yourself.
- **A high `p_central` on `games_won_for` is the number to trust least.** The
  old sample-frequency estimator was measured overconfident at the top (on
  9,286 settled rows a claimed 0.95 realised 0.728, no bucket above 0.825 -
  a September measurement, since superseded). The curve fitted on the history
  replay of the rating now has buckets to 0.95+ (`config/sofa_confidence_calibration.json`,
  `by_market.games_won_for`; replayed rows, not independent matches), and the
  2026-10-05/06 Superbet lines still realised below confidence for printable
  `games_won_for` legs (`config/sofa_superbet_line_evidence.json`,
  `keys.tennis`: OVER -0.17, UNDER -0.12, dated, measured under the older
  estimator). There are no settled lines of the rating-priced estimator yet.
- **A short match settles every UNDER at once.** Sets, games, aces and double
  faults are one mechanism. A tennis Bet Builder of two UNDERs is one bet
  charged twice — and `confidence.py`'s quantity families put `games_*`,
  `sets_*` and `handicap_games` in the **same** family for exactly that reason.

- **Tier gap: refit done, the veto rule is retired.** `config/tennis_rating.json`
  was refit with `dhigh`/`dtour` on 2026-09-30 (cut 2026-10-01, 239,315
  history matches). Do not veto on a tier-share gap any more. Tour and
  Challenger forecasts read no neighbour decided by a match tiebreak
  (`Outcome.match_tiebreak`). Davis/BJK Cup and exhibitions
  (`tennis_team_cup`) and women's events (`tennis_women`) read only their own
  class curves and class line evidence; such a leg missing from
  `08_confidence` was refused (`NO_CLASS_CURVE` / `NO_LINE_EVIDENCE`), not
  lost.
- **What the curves are fitted on.** Since the 2026-10-07 refit (installed
  that evening, a new comparability epoch) the curves are fitted on the
  history of Sofascore events replayed as of each match with the estimator
  SHEET prices with - the tennis rating as of that day
  (`calibrate_from_cache`, `tennis_rating.AsOfRating`), best-of-five matches
  skipped (`infer_best_of`) - not on our own settled days, which are an
  audit. Superbet's settled lines correct the curve (`bet.sofa.line_evidence`).

## Tennis-specific output requirements

Per match, always state: tour and format from `default_period_count` (a
best-of-five is outside the rating); surface
from `ground_type`, **or explicitly that it is unknown**; round and start time
as verified, on both clocks, with the disagreement in hours; each side's
scoped `n` and the class of the opposition behind it; the previous match where
you found it; and once, in the header, that tennis has **no source of record**
— not once per row.
