# Football methodology — the models behind each claim, and how they map to our data

This is the literature the analyst reasons *with*. None of it produces a
number in the artifacts; all of it decides whether a sample is evidence about
tonight.

Each section ends with what `sofa` holds for it and what it does not - the
latter is where your contribution is.

## 1. Counts are Poisson-like, and most of ours are over-dispersed

- **Goals.** Maher (1982) — independent Poisson per side with attack/defence
  strengths and home advantage. Dixon & Coles (1997, *JRSS-C*) — the same with
  a low-score dependence correction (τ on 0-0/1-0/0-1/1-1) and **exponential
  time-decay** of past matches, motivated by betting-market inefficiency.
  Karlis & Ntzoufras (2003) — bivariate Poisson. Boshnakov et al. (2017) —
  Weibull count models for goals. *Implication for us:* `sofa` has **no
  external model and no consensus**; its own model is the opponent-adjusted
  attack / defence rating (`football_rating`, Maher's multiplicative form with
  exponential smoothing and a league home / away rate), mixed into the centre
  at a per-market weight (`config/sofa_rating_weight.json`). The only reference price is Superbet's own other side,
  power-devigged into `market_p`. On the coupon that price
  is only the betting condition; "past frequency ≠ edge" is answered by the
  calibrated pewność, not by the price, and when the rung is one-sided
  (`NO_MARKET_MARGINAL`, or no `under_odds`) there is no devigged price at all.
  Half splits: first halves carry ~45% of goals, not 50%, and the half-match
  baselines are fitted on far fewer matches than the full-match ones.
- **Corners, shots, fouls, cards.** Variance exceeds the mean (team-level
  heterogeneity, game-state feedback), so a negative-binomial or Conway–
  Maxwell–Poisson fit is the standard; Dawson, Dobson, Goddard & Wilson (2007,
  *JRSS-A*) modelled disciplinary points with a bivariate negative binomial;
  the 2026 *JRSS-A* "Yellow fever" paper uses a bivariate mean-parameterised
  CMP copula across the Big 5 and **rejects referee consistency**. *Implication:*
  `sofa` prices football counts with a **negative binomial whose dispersion is
  fitted on the history per competition** (`config/sofa_count_dispersion.json`;
  `shots_total` a normal with the pooled variance), so the overdispersion is
  in the model, not in the sample's SD. A small `sample_sd` is under-measured,
  never precision - six corner observations of {6,6,6,6,7,7} preceded a 16.
- **Small samples and shrinkage.** Empirical-Bayes shrinkage toward a
  population mean (James–Stein; Efron & Morris 1975) is applied in layers in
  `sofa`, and conflating them is a common error. First the *centre* is shrunk
  toward the league baseline at `w_c = n/(n + K)` - football K = 15, per
  market in `K_CENTRE.by_market.football` (`config/sofa_engine_constants.json`).
  Then, where the rating prices the market, the rating's expected count takes
  a per-market weight `w` of the centre (`config/sofa_rating_weight.json`, the
  `W=` in the row note). The coupon's pewność is the calibrated `p_central`,
  with no price in it; the price can only lower it (line evidence). The old
  VALUE selector's `p_bar` (shrunk toward the price) is not the coupon.
  Wilson (1927) is the lower bound line evidence reads for a key with no
  curve, and the `p_low_cap` / `laplace_cap` of the VALUE selector's
  `bar_reason`. A 4/4 is four matches; 16/20 beats 3/3.

## 2. Home advantage and referee bias are real, and they are in the cards

- Home advantage in football is the largest of the major team sports and has
  been shrinking; it is partly crowd-on-referee. Reade & Singleton (closed
  doors, 2020–21): removing crowds reduced the home bias in cards. Dawson et
  al. (2007): home teams accumulate fewer yellows/reds, attributable to
  referee behaviour rather than team behaviour. Buraimo, Forrest & Simmons
  (2010, *JRSS-A*): bivariate probit on EPL and Bundesliga, controlling for
  derby, stadium type and bookmaker odds as strength — bias toward home teams
  in both. *Implication:* the effect is real,
  and `sofa` encodes it only through the rating's league home / away rate on
  the markets the rating prices; `cards_points_for` and the corners rows are
  unrated, so there the sample's own `venue` field, which you must read, is
  all there is. The referee is the single largest unmodelled input on any
  card row (two officials of one league can differ by a third of a line).
- **Referee heterogeneity** means a card row without a named official is
  missing its biggest driver. **`sofa` does nothing about this** — there is no
  tier to cap and no `k` to double, and the referee is present on ~9% of
  fixtures. So the absence is the normal case and the judgement is entirely
  yours. With an official named, `games` is the sample size: 5.75 over 4
  matches is four numbers.

## 3. Game state drives counts, and the direction is not symmetric

Score effects (StatsBomb 2013; later replications): the trailing side takes
more shots of lower quality, holds more possession, wins more corners; the
leading side shoots less and better. Corners split almost evenly between
winner and loser over a match (4.70 vs 4.78 in an earlier sample), which is why
goals ↔ corners is ~0 while goals ↔ SOT is clearly positive (earlier
measurements: +0.04 and +0.55). *Implication:* the method's GAME SCRIPT
A-D scenarios (favourite ahead / underdog ahead / 0-0 to 60' / level) are the
practical form of this; weight them from Superbet's own ladders in
`04_offer.json` (`result_1x2`, `double_chance`, each side's `goals_for`,
`handicap_corners`, `most_*` where offered) or say they are unweighted,
and ask for each market which scenario kills it. A strong favourite at home scoring early flattens SOT-against and corners-for the
underdog; a 0-0 to 60' inflates fouls and cards in a knockout.

## 4. Stakes and match importance

- **Two-legged ties.** The second leg is played with knowledge of the
  aggregate; a side trailing must attack (shots, corners, goals-for up on
  their side; cards up as the clock runs), a side comfortably through rotates
  and manages. Second-leg home advantage is documented (Page & Page 2007).
  Extra time exists in some competitions and not others (UEFA yes; Copa do
  Brasil from the R16 straight to penalties) — settlement rules for counting
  markets follow the competition. *Implication:* `previous_leg_event_id`,
  `round_name` and `cup_round_type` are the highest-value context fields in
  `sofa` and all three are on `Fixture` directly. What is **not** there is the
  first leg's *score* — follow `previous_leg_event_id` yourself. Nor is the
  competition's extra-time rule, which decides what "90 minutes" means for
  every counting UNDER.
- **Derbies** raise fouls and cards materially (Buraimo et al. controlled for
  it because it matters). **`sofa` has no derby flag at all.** Name the derby
  yourself and say how you know.
- **Dead rubbers, relegation six-pointers, cup rotation** change the XI and
  the tempo. The table is on disk only as the leg's `stakes` flag
  (six-pointer / top-4 race, measured small: +0.2 cards, +0.9 fouls, -0.15
  goals per match); read the rest on the web (two domains, tagged) before
  believing "last ten" describes tonight, or write `UNVERIFIED`.

## 5. Fixture congestion and fatigue

Julian, Page & Harper (2020, *Sports Medicine*, meta-analysis): players
largely **maintain total distance and physical output** under congestion
(<96h between matches); injury incidence rises (systematic reviews 2022).
*Implication:* congestion is an **availability and rotation** argument, not a
"tired legs → fewer shots" argument. Say which. `sofa` holds the load
(`schedule`, `CONGESTED`) but no availability data: who plays is an external
check.

## 6. Underlying quality vs results

Expected goals regress: a side scoring well above its xGF is finishing hot;
the finishing will regress before the shot volume does. `sofa` collects `xg_for` / `xg_total` as
per-match observations where Sofascore publishes them — absent for most
competitions — and there is **no season aggregate and no code flag**.
*Implication:* a shots/SOT lean built on results (goals) is weaker than one
built on the shots sample itself; a `goals_for` OVER on an over-performing side
is the classic regression trap, and you have to notice it yourself. Do not read
an absent xG as zero.

## 7. Opponent adjustment and the `against` value

The standard model conditions on opponent defence (Maher/Dixon–Coles attack ×
defence). Every `_for` observation carries `against` - the opponent's value
in that match - so what tonight's opponent concedes is its own observations'
`against` values. Built-in adjustments: the rating's defence ratio (the
`FOOTBALL_RATING` note, absent on unrated markets such as `corners_total`)
and the opponent correction (`opponent_rule`, `corrected_sample`: a side's
sample rescaled to a neutral opponent; goals and players excluded). You also
have is each observation's `opponent` field: the sample's opponents are visible, so "these
four highest values were all against continental sides" is checkable.

## 8. Recency and weighting

Dixon–Coles decay half-lives in the literature run ~1–2 seasons for goals;
for counting stats with tactical drivers (manager change, new full-backs) a
shorter window is defensible. The method's convergence / disagreement
step: compare season-heavy vs
recent-heavy vs venue-heavy vs opponent-adjusted reads; convergence raises
confidence, divergence lowers it. `sofa`'s sample is the last ten matches by
construction (`sample_n = 10`, `min_sample = 5`), read **descending**, and for
a league fixture's goal markets the last ten REGULAR matches of the same
competition when there are five or more — there is no season view and no
decay weighting in the sample, so every observation counts equally. The
rating is the exception: it is an exponentially smoothed history (a per-metric
`ALPHA`, 0.01-0.08 per match).
`sample_newest_days` is on the row; the observations' own `match_date_utc`
gives you the span.

## 9. Price, edge, and market efficiency

- Implied probability = 1/odds; remove the overround before comparing.
  `sofa` uses a **power devig**, not a proportional one: proportional
  overstated long shots by ~7 pp and understated favourites by ~7 pp.
  Superbet is a soft book, and it is the only price `sofa` has or may quote;
  no other bookmaker or aggregator is a reference here.
- Edge exists only when `fair probability > implied`, with a fair estimate of
  adequate quality (the method's edge definition). Per-team "to score" and 0.5 lines are house
  markets that sit at or under consensus (ledger 2026-08-30/31: −0.1 to −5.6pp
  on five such legs).
- On the coupon none of this is evidence for a leg: the price is only the
  betting condition (x = confidence x odds >= 0.90, ladder margin <= 15%).
- Kelly / stake sizing is deliberately out of scope for every agent.

## 10. Correlation and slips

Positive dependence among same-match legs makes the product of leg
probabilities too **low** for shots-and-goals and about right for corners
(r ≈ 0); fouls run mildly *against* goals. Independence holds **across** quantities
(λ 0.95–1.02) and fails **within** one: a team's goals against the match total
is λ 2.165, up to 8.37. That is why `confidence.py` takes at most one leg per
quantity family and refuses builders whose legs disagree about tempo. A Bet
Builder cannot rescue a below-bar leg, and the real cost is the join:
Superbet's correlation markup measured **8.8–19.6%** on the three builder
prices this repo has ever seen, against which the flat 12% haircut is the
estimate. The contradiction test as a *scenario* test and the tail-risk read are
yours; the builder's price is not - sofa does not price a builder, the
operator reads it off Superbet's screen, and the 12% haircut is internal and
never quoted.

## 11. Post-mortem discipline

Attribute every settled row to `MODEL-CONSISTENT / MODEL-SURPRISING /
PURE VARIANCE` (the method's post-mortem list) and to one error category. A category that
wins 84% produces losses; three of them in a row is not evidence the category
is broken. In `sofa` the post-mortem
tools are `audit_settlement.py` (how much came in, and which of it was a bet —
**section 7c is the PDF coupon's real result**) and `audit_day_deep.py` (was
the miss systematic or dispersion, and would today's gates still have made
yesterday's bet). Use them on a class of read, never on one row.

## Sources

- Maher, M. J. (1982). Modelling association football scores. *Statistica Neerlandica*.
- Dixon, M. J. & Coles, S. G. (1997). Modelling association football scores and inefficiencies in the football betting market. *JRSS-C* 46(2). https://rss.onlinelibrary.wiley.com/doi/abs/10.1111/1467-9876.00065
- Karlis, D. & Ntzoufras, I. (2003). Analysis of sports data by using bivariate Poisson models. *The Statistician*.
- Dawson, P., Dobson, S., Goddard, J. & Wilson, J. (2007). Are football referees really biased and inconsistent? *JRSS-A* 170(1).
- Buraimo, B., Forrest, D. & Simmons, R. (2010). The 12th man? Refereeing bias in English and German soccer. *JRSS-A* 173(2).
- Reade, J. & Singleton, C. (2021). Eliminating supportive crowds reduces referee bias. https://centaur.reading.ac.uk/101715/
- "Yellow fever: an investigation into referee consistency in the Big 5 leagues" (2026). *JRSS-A*. https://academic.oup.com/jrsssa/advance-article/doi/10.1093/jrsssa/qnag014/8488960
- StatsBomb (2013). Score Effects. https://statsbomb.com/2013/12/score-effects
- Julian, R., Page, R. M. & Harper, L. D. (2020). The effect of fixture congestion on performance during professional male soccer match-play: a systematic critical review with meta-analysis. *Sports Medicine*. https://pubmed.ncbi.nlm.nih.gov/33068272/
- Page, L. & Page, K. (2007). The second leg home advantage. *Journal of Sports Sciences*.
- Efron, B. & Morris, C. (1975). Data analysis using Stein's estimator. *JASA*.
- Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. *JASA*.
- In-repo measurements (the base-rates file is from an earlier provider's
  2026 sample, an order of magnitude only): `.claude/skills/bet-slip-audit/reference/base-rates.md`; `src/bet/sofa/confidence.py` (the disagreement table, the quantity-family lambdas, the correlation markup); `config/sofa_engine_constants.json` (K_CENTRE); `docs/sofa/RUNBOOK.md`.
