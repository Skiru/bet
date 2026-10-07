---
name: football-analysis
description: How to analyse one football fixture's counting markets in the sofa pipeline (goals, corners, cards as booking points, fouls, shots, shots on target, offsides, per-team and per-half lines, and the derived both_over/handicap/most markets) - round and stakes, second legs, derbies, referee, absences, venue, opponent class, game script, distribution over mean, which rung; on a leg pewność (confidence), próbka k/n and model (forecast_p), the price only as the betting filter. Use when reading a sofa football sheet or the coupon's football legs, judging a Bet Builder leg, or writing vetoes and reads. Preloaded into sofa-analyst-football.
---

# Football analysis — the method, mapped to what `sofa` actually holds

`sofa-pipeline` (the contract) and `sofa-analysis-core` (the analyst's rules)
are preloaded with you. This skill answers the one question neither does:
*given these rows, how does a competent football analyst decide whether the
sample describes tonight's match?*

| reference | open it when |
|---|---|
| `references/data-inventory.md` | you need to know exactly what is measured, from which Sofascore field, and what is simply absent |
| `references/methodology.md` | you need the model behind a claim — Poisson/Dixon–Coles, overdispersion, referee bias, game state, congestion, two-legged ties, shrinkage |
| `references/market-playbook.md` | you are grading a specific market: drivers, kill cases, what settles it |
| `references/event-protocol.md` | you are writing a fixture section |

The operator's method is `docs/sofa/SUPERBET_BET_BUILDER_METHOD_v3.md` — a
pre-`sofa` document, kept because the *method* (what to look at in a fixture)
outlived the pipeline it was written for. Cite the sections you used; do not
restate them, and never take pipeline behaviour from it.

## What is different about `sofa`, and you must not forget it

`sofa` carries **far less context than the pipeline this method was written
for**. There is no season-form table, no xG summary per team, no squad
availability list, no standings, no bookmaker consensus, no referee blend into
the centre, no derby flag, no tier system, and no cross-provider agreement.
What exists is: the fixture's identity and round, a referee on ~9% of fixtures
(2026-10-07: 14 of 153), a venue name on few (20 of 153), **the raw
observations**, and the opponent-adjusted team rating that the centre is
blended with (below).

Two consequences, both load-bearing:

1. **The context half of this method has to come from outside the artifacts** —
   and the only source available is the open web, read as two independent
   domains and tagged. **bzzoiro is not a `sofa` source and must never be
   called.** `sofa` is Sofascore statistics and Superbet prices; reaching for
   another provider launders a number the pipeline never sampled into a read
   that is supposed to rest on those two. Where the web cannot answer either,
   write `UNVERIFIED` — that is a real answer, not a gap to be filled.
2. **Your leverage is higher, not lower.** Every context fact the old pipeline
   encoded as a flag is now a fact only you can supply.

## What the code already does — do not re-derive or veto for it

- **Centre.** Shrinks the sample toward a fitted league baseline,
  `w_c = n/(n+K_CENTRE)`, `K_CENTRE = 15` for football
  (`config/sofa_engine_constants.json`, `by_sport`), then blends the result 50/50
  with the opponent-adjusted rating (`football_rating`, Maher-style attack x
  defence x home ratios per metric, `W_FOOTBALL_RATING = 0.5`, a `FOOTBALL_RATING`
  row note) wherever the rating prices the market. `UNRATED_MARKETS` keep the
  sample's centre alone: `corners_total`, `corners_1h_*`, `corners_2h_*`,
  `cards_points_for`, `offsides_total`; saves, tackles, throw-ins, goal kicks and
  xG are not rated at all (the rated metrics are `football_rating.BASE_METRICS`:
  goals, corners, cards points, fouls, offsides, shots, shots on target, with
  their halves). The rating needs >= 5 matches of the metric for both sides and a
  league (or global) rate of >= 30 matches.
- **Distribution.** The spread is the sample's dispersion, scaled with the
  centre and inflated by `1 + 1/n` (`sheet_predictive_sd`). Goals (all periods),
  `corners_for`, `corners_1h_*`, full-match `offsides_*`, `cards_points_*` and the player
  shots / shots on target / assists are priced through a negative binomial;
  `corners_total`, `corners_2h_*`, `shots_*`, `shots_on_target_*`, `fouls_*` and
  `saves_*` still use the normal CDF with a support floor (`engine.
  NEGATIVE_BINOMIAL_METRICS`). Do not say "overdispersion is in the model" of
  those.
- **Confidence.** Calibrates `model_p` (the sheet's `p_central`) into the leg's
  **pewność** (`confidence`) through `config/sofa_confidence_calibration.json`
  (refit 2026-10-07 on the history of statistics replayed with the sheet's
  estimator), then reads it through its own settled Superbet lines
  (`bet.sofa.line_evidence`: the curve lowered by a measured offset, the
  price-band cap; a key with no curve reads the Wilson bound of its own lines,
  else `NO_LINE_EVIDENCE`). Publishes the rating's own probability beside it as
  **model** (`forecast_p`, uncalibrated, never a gate).
- **Price.** Power-devigs the offered price (`market_p`); the old VALUE selector
  only blends toward it at `w = n/(n+10)` (`p_bar`, priced, `06_coupon.json`).
  On the coupon the price is only the betting condition: x = confidence x odds
  >= 0.90, ladder margin <= 15% (a one-sided rung has no margin, so it never
  prints as a single), price age <= 45 min, odds >= 1.0867, the start on the
  earliest of three clocks (a leg within 15 min of it is refused).
- **Sample gates, every leg (not only builder legs).** >= 10 observations
  (`THIN_SAMPLE_FOR_BUILDER`), newest match <= 60 d (`STALE_SAMPLE`), oldest
  <= 180 d (`SAMPLE_CROSSES_SEASON`, national teams judged by count),
  line-inside-sample, mode-must-not-lose, and the automatic
  `MODEL_ABOVE_OWN_SAMPLE` WATCH (`model_p` - own hit rate > 0.15, football
  only, props excluded, needs >= 5 observations). Builders add one leg per
  quantity family, tempo coherence and an internal 12% correlation haircut
  that is never printed.
- **Refusals by name** that remain: `CROSS_LEAGUE_UNLINKED`, `NO_CLASS_CURVE`
  (women's football reads only its class curves), `NOT_SETTLEABLE`,
  `CATCH_ALL_BUCKET`, the floors. Those by name that are gone since 2026-10-07
  10:55Z: `refused_markets`, `admitted_player_markets`,
  `DERIVED_NOT_CALIBRATABLE` - a market with no measurement is
  `NO_LINE_EVIDENCE`.

## The protocol

For every fixture with a football leg in your read set (the first 30
positions of `11_coupon.json`, every printed builder leg, `read_requests.json`
- see `sofa-analysis-core`), and any fixture you intend to veto. Full template:
`references/event-protocol.md`.

1. **Identity & both clocks.** From `02_fixtures.json`: `identity`
   (`FUZZY` is never "confirmed"), `kickoff_utc`, `superbet_kickoff_utc`,
   `kickoff_disagreement_h` — all of it from Sofascore and Superbet, which is
   the whole of what `sofa` reads. A fixture that has already started at the
   artifact's time is a veto on all lines.
2. **Stakes.** `round_name`, `cup_round_type`, `previous_leg_event_id` are in
   the fixture. The *aggregate* is not — read the first leg. League position,
   dead rubber, promotion play-off and derby status are **not** in the
   artifacts: take them from the web, tag each one, and mark `UNVERIFIED`
   where you cannot. Derby: name it and say how you know.
   **Schedule is, since 2026-10-04:** the fixture's `schedule` block in
   `03_samples.json` (`makeup_of`, `makeup_postponed_utc`, per side
   `rest_days`, `matches_7d`, `matches_14d`) and the legs' `context_flags`
   (`MAKEUP_FIXTURE(...)`, `LONG_LAYOFF(...)` at >= 21 days, `CONGESTED(...)`
   at >= 3 matches in 7 days). Quote them; the web is still needed for *why*.
   A make-up fixture (a postponed meeting of the same two sides in the same
   competition) means find out why it was postponed - illness in a squad,
   weather, a pitch - and whether that cause still holds; 2026-10-04
   Farense - Chaves (UNDER 3.5 lost 4-0) was a round-5 make-up after a viral
   outbreak and nobody asked. Congestion is an availability and rotation
   argument (methodology.md section 5), not a fatigue one.
3. **Sample integrity.** Open `03_samples.json` for this fixture and metric.
   Count `side_a` / `side_b` / `h2h` separately. Read every observation's
   `match_date_utc`, `opponent`, `venue`, `competition_id`. Then ask:
   - does the sample span a manager change, a promotion, a transfer window?
   - are the h2h observations *the misses*? (a pooled 19/21 that goes 1/3
     conditional on this fixture)
   - is one side thin while the other carries the mean?
   - do `X_for(A) + X_for(B)` land near `X_total`'s mean? If not, the two rows
     are not measuring the same match.
   - does `subject` resolve to the side you think? This is the most fragile
     join in the pipeline.
   - goal markets (`goals_total`, `goals_for`, `goals_1h_for`,
     `goals_2h_for`) of a LEAGUE fixture sample only REGULAR matches of the
     fixture's own competition when the side has five or more, and friendlies
     / pre-season tournaments are out of every sample. A cup or friendly
     observation in such a goal sample is a defect to report; a knockout
     fixture keeps the usual newest-ten sample, cups included (not a defect).
   - `sample_hit_rate` on the leg against `model_p`: above 0.15 the code
     already refused it from the official coupon (`MODEL_ABOVE_OWN_SAMPLE`);
     a smaller gap is still yours to weigh.
4. **Shrinkage share.** `w_c = n/(n+15)`. State it. At n=10 the league prior
   owns **60%** of the sample-side centre; where the row carries a
   `FOOTBALL_RATING` note the rating then owns half of the final centre
   (`centre` on the sheet row), so the sample's own share is half of `w_c` (20%
   at n=10). For any `*_1h_*` / `*_2h_*` row state it twice — half-match
   baselines are fitted on a smaller, different population (the
   `corners_2h_total` global baseline rests on n=102, config fit 2026-10-07),
   and a stale baselines file once shipped corners priors 24–32% too high
   (September 2026, two days).
5. **Distribution.** From the observations: min, max, median, mode, and where
   the line sits inside that range. A line beyond the sample's extreme is an
   extrapolation into a region with zero observations, whatever the hit rate
   says. A line on the mode is a coin flip dressed as a lean.
6. **Opponent & venue.** Tonight's venue against the sample's home/away mix;
   the opponent's own `*_for` profile. **We hold no `*_against` observation** —
   say so rather than inventing an "allowed" number; the only opponent
   adjustment is the rating's defence ratio, printed in the `FOOTBALL_RATING`
   note (and absent on unrated markets). Style clash: a low block
   generates corners for the attacker and shots-against for itself.
7. **Referee** (cards, fouls only). `RefereeRecord` gives `games`,
   `yellow_cards`, `red_cards`, `yellow_red_cards` — a rate, not an
   observation of tonight. It is present on ~9% of fixtures and **is not
   blended into the centre in `sofa`**. Absence is the default; say what the
   league's spread makes of that.
8. **Absences & lineups.** Not in the artifacts at all — the web, two
   independent domains, tagged; within ~1 h of kickoff the club's or the
   league's own lineup page. Four starters out is a
   `CONTEXT` veto candidate (`context: ABSENCES`); a rested XI in a cup tie
   likewise (`ROTATION`). Where to look: `sofa-analysis-core`
   `references/context-sources.md`.
9. **Game script A–D** (the method's GAME SCRIPT block): favourite ahead,
   underdog ahead, 0-0 to 60', level. Say which is modal and whether the
   market survives it. There is no 1X2 price in the artifacts and no other
   source for one: read the
   favourite from Superbet's own ladders in `04_offer.json` (each side's
   `goals_for` rungs, `handicap_corners` and `most_*` rungs where offered;
   `unmapped_markets` lists the names of the 1X2 / handicap / double-chance
   markets without prices), or say the scenarios are unweighted.
10. **The ladder.** All rungs in `04_offer.json` for this market, with
    `p_central` and `offered_odds` per rung (and the leg's pewność, próbka
    k/n and model where it is one). Note
    `NO_LADDER_CHECK` and `LADDER_DISAGREES` / `LADDER_SPREAD_DISAGREES`
    where they appear: they are the old VALUE selector's verdict notes ("VALUE
    withheld") and CONFIDENCE does not gate on them, so an unmeasurable or
    disagreeing ladder is yours to weigh, not something the coupon already
    refused.
11. **Correlation**, for anything that may become a builder leg: the mechanism,
    the direction, and the one scenario that kills every leg at once. Never
    multiply. `confidence.py` owns the combined number.
12. **Price — only the filter.** `offered_odds`, x = confidence x odds
    against 0.90, the price's own `fetched_at_utc`. The code has applied it;
    it is never a reason for or against the leg.
13. **Buy case / kill case.** The strongest fact for, the strongest fact
    against, which wins. `BUY ≈ KILL` → WATCH at most.
14. **Verdict** `KEEP / WATCH / NO_BET` — a read entry for every leg of
    your read set (WATCH and NO_BET both remove it from the coupon into
    `removed_by_reads`, graded apart in audit_settlement 7i) — and the veto
    entry if any.

## Kill cases this repo has already paid for

Check every read against these.

- **Team-corner OVER plus total-corner UNDER without a tail test.**
  Porto–Arouca went 12–2: one side can destroy the total alone.
- **The misses are the h2h.** A fouls line at 19/21 pooled, 1/3 conditional on
  this fixture. `SAMPLE_UNINFORMATIVE`, `line: null`.
- **Line on the mode.** Cards at 7.5 with five 7s and two 8s in twenty
  observations. Veto that line; 8.5 may still be fine.
- **A single conflicting observation deciding the bar.** 6 vs 8 on one match
  moved a row from 19/21 to 20/21 and across the bar.
- **No referee on a card row in a high-spread league.** In `sofa` this is the
  *normal* state (~9% coverage), so it is not automatically a veto — but on a
  card row where the league's spread is wide, say what the absence costs.
- **A mean pulled by four outliers against a different class of opponent.**
  Shots mean 29.6 against median 26, the four highest all against continental
  opposition.
- **Sample centre far from the book's ladder centre.** Corners mean 2.80
  against a ladder median of 5.76 — the sample described a different
  team-state. Look for `LADDER_DISAGREES` / `LADDER_SPREAD_DISAGREES` on the sheet row
  (the code does not refuse the coupon leg for them).
- **Past frequency read as an edge.** A team scoring in twelve straight is not
  a 92% claim; the calibrated pewność is the claim, and próbka 12/12 is only
  the sample it came from.
- **Certainty for free.** A 0.5 UNDER or 5.5 goals UNDER at 1.01–1.05 tops a
  sheet by hit rate and is not a bet. Never lead with one. CONFIDENCE refuses
  any price under 1.0867 (`1 / CONFIDENCE_CEILING`, ceiling 0.9202) for exactly
  this reason.
- **`both_over_*` / `most_*` / `handicap_*` have no sample of their own.** A
  joint of the two sides' marginals plus a measured side correlation
  (`config/sofa_side_correlations.json`); the sheet notes say how far the
  market checked it (`NO_MARKET_MARGINAL`, `ONE_SIDED_LADDER`,
  `MARGINAL_DISAGREEMENT`). For the goals, corners, shots-on-target and cards
  joints the marginals are the two `*_for` rows' own centres (since
  2026-10-07 14:05Z); fouls, shots and offsides joints still read the raw
  sample mean and variance. They have no history curve (`DERIVED_CURVES_FROM_UTC`
  is off), so confidence is the Wilson bound of the key's own settled Superbet
  lines in the p bucket, else `NO_LINE_EVIDENCE`. As coded, such a row has no
  observations to run the sample gates on, and neither the 2026-10-06 nor the
  2026-10-07 coupon holds one. If one is in your read set, report the two
  `*_for` rows and refuse the multiplication.
- **Extra time and penalties in a cup second leg.** Check the competition's
  rule before trusting any counting UNDER: some go straight to penalties, some
  play 30 minutes, and "90 minutes" means different things.
- **Half-match rows on a thin sample.** The `corners_2h_total` global baseline
  rests on n=102 observations (`config/sofa_league_baselines.json`, fit
  2026-10-07), `corners_1h_total` on 721. At n=8 the row is 65% league prior
  before the rating blend.
- **A high surplus** (`06_coupon.json`, the old VALUE selector - not the
  coupon). Above +0.40 is suspect *by definition*; that selector sorts on
  exactly the quantity that grows when `p` is wrong.

## Football-specific output requirements

Per fixture, always state — even when the answer is "none": round and stakes
and where you read them; the referee with `games`, or explicitly that there is
none; absences per side with how you checked; the venue; the modal game-script
scenario; the shrinkage share `n/(n+15)`; and which gates the code already
applied, so a veto of yours does not silently duplicate one.
