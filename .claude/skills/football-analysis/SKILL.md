---
name: football-analysis
description: How to analyse one football fixture's counting markets in the sofa pipeline (goals, corners, cards as booking points, fouls, shots, shots on target, offsides, per-team and per-half lines, and the derived both_over/handicap/most markets) - round and stakes, second legs, derbies, referee, absences, venue, opponent class, game script, distribution over mean, which rung, price last. Use when reading a sofa football sheet, grading VALUE rows, judging a Bet Builder leg, or writing vetoes. Preloaded into sofa-analyst-football.
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

The operator's method is `docs/legacy/SUPERBET_BET_BUILDER_METHOD_v3.md` — a
pre-`sofa` document, kept because the *method* (what to look at in a fixture)
outlived the pipeline it was written for. Cite the sections you used; do not
restate them, and never take pipeline behaviour from it.

## What is different about `sofa`, and you must not forget it

`sofa` carries **far less context than the pipeline this method was written
for**. There is no season-form table, no xG summary per team, no squad
availability list, no standings, no bookmaker consensus, no referee blend into
the centre, no derby flag, no tier system, and no cross-provider agreement.
What exists is: the fixture's identity and round, a referee on ~9% of fixtures,
a venue name, and **the raw observations**.

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

Shrinks the sample toward a fitted league baseline at `K_CENTRE = 25`; prices
football counts through a negative binomial (overdispersion is in the model);
power-devigs the offered price; blends toward it at `w = n/(n+10)`; checks the
book's whole ladder where it can (only 52.4% of ladders are checkable);
enforces price age 45 min, sample age 60 days, kickoff 15 min on the earlier
clock, odds floors, one mechanism family per fixture; and for builder legs
enforces sample ≥ 10 observations, ≤ 180 days, mode-must-not-lose,
line-inside-sample, tempo coherence and the 12% correlation haircut.

## The protocol

For every fixture carrying a `VALUE` row, every fixture with a leg in
`08_confidence.json`, and any fixture you intend to veto. Full template:
`references/event-protocol.md`.

1. **Identity & both clocks.** From `02_fixtures.json`: `identity`
   (`FUZZY` is never "confirmed"), `kickoff_utc`, `superbet_kickoff_utc`,
   `kickoff_disagreement_h` — all of it from Sofascore and Superbet, which is
   the whole of what `sofa` reads. A fixture that has already started at the
   artifact's time is a veto on all lines.
2. **Stakes.** `round_name`, `cup_round_type`, `previous_leg_event_id` are in
   the fixture. The *aggregate* is not — read the first leg. League position,
   dead rubber, promotion play-off, congestion (third match in seven days, a
   midweek continental tie) and derby status are **not** in the artifacts: take
   them from the web, tag each one, and mark `UNVERIFIED` where you cannot.
   Derby: name it and say how you know.
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
4. **Shrinkage share.** `w_c = n/(n+25)`. State it. At n=10 the league prior
   owns **71%** of the centre. For any `*_1h_*` / `*_2h_*` row state it twice
   — half-match baselines are fitted on a smaller, different population, and a
   stale baselines file has already shipped corners priors 24–32% too high.
5. **Distribution.** From the observations: min, max, median, mode, and where
   the line sits inside that range. A line beyond the sample's extreme is an
   extrapolation into a region with zero observations, whatever the hit rate
   says. A line on the mode is a coin flip dressed as a lean.
6. **Opponent & venue.** Tonight's venue against the sample's home/away mix;
   the opponent's own `*_for` profile. **We hold no `*_against` metric** — say
   so rather than inventing an "allowed" number. Style clash: a low block
   generates corners for the attacker and shots-against for itself.
7. **Referee** (cards, fouls only). `RefereeRecord` gives `games`,
   `yellow_cards`, `red_cards`, `yellow_red_cards` — a rate, not an
   observation of tonight. It is present on ~9% of fixtures and **is not
   blended into the centre in `sofa`**. Absence is the default; say what the
   league's spread makes of that.
8. **Absences & lineups.** Not in the artifacts at all — the web, two
   independent domains, tagged; within ~1 h of kickoff the club's or the
   league's own lineup page. Four starters out is a
   `CONTEXT` veto candidate; a rested XI in a cup tie likewise.
9. **Game script A–D** (method §24): favourite ahead, underdog ahead, 0-0 to
   60', level. Say which is modal and whether the market survives it. There is
   no 1X2 price in the artifacts and no other source for one: read the
   favourite from Superbet's own ladders in `04_offer.json` (goals, handicap
   and `most_*` rungs where offered), or say the scenarios are unweighted.
10. **The ladder.** All rungs in `04_offer.json` for this market, with
    `p_central` / `p_bar` / `offered_odds` / `surplus` per rung. Note
    `NO_LADDER_CHECK` where it appears: that row passed *without* the ladder
    test, which is not the same as passing it.
11. **Correlation**, for anything that may become a builder leg: the mechanism,
    the direction, and the one scenario that kills every leg at once. Never
    multiply. `confidence.py` owns the combined number.
12. **Price — last.** `required_odds` against `offered_odds`; `surplus` and its
    suspicion threshold (+0.40); the price's own `fetched_at_utc`.
13. **Buy case / kill case.** The strongest fact for, the strongest fact
    against, which wins. `BUY ≈ KILL` → WATCH at most.
14. **Verdict** `KEEP / WATCH / NO BET`, and the veto entry if any.

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
  team-state. Look for `LADDER_DISAGREES` / `LADDER_SPREAD_DISAGREES`.
- **Past frequency read as an edge.** A team scoring in twelve straight is not
  a 92% claim; devig the price and compare before speaking.
- **Certainty for free.** A 0.5 UNDER or 5.5 goals UNDER at 1.01–1.05 tops a
  sheet by hit rate and is not a bet. Never lead with one. CONFIDENCE refuses
  anything under 1.0867 for exactly this reason.
- **`both_over_*` has no sample.** It is a function of two sides, carries
  2–252 settled rows in total, and *every* such row also carries
  `ONE_SIDED_LADDER` and `NO_MARKET_MARGINAL`. Report the two `*_for` rows and
  refuse the multiplication. CONFIDENCE will not build a leg from one.
- **Extra time and penalties in a cup second leg.** Check the competition's
  rule before trusting any counting UNDER: some go straight to penalties, some
  play 30 minutes, and "90 minutes" means different things.
- **Half-match rows on a thin sample.** `corners_2h_*` has 62 matches in the
  entire settled history. At n=8 the row is 76% league prior.
- **A high surplus.** Above +0.40 is suspect *by definition*; the selector sorts
  on exactly the quantity that grows when `p` is wrong.

## Football-specific output requirements

Per fixture, always state — even when the answer is "none": round and stakes
and where you read them; the referee with `games`, or explicitly that there is
none; absences per side with how you checked; the venue; the modal game-script
scenario; the shrinkage share `n/(n+25)`; and which gates the code already
applied, so a veto of yours does not silently duplicate one.
