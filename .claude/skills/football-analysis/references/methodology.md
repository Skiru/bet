# Football methodology — the models behind each claim, and how they map to our data

This is the literature the analyst reasons *with*. None of it produces a
`p_low`; all of it decides whether a sample is evidence about tonight.

## 1. Counts are Poisson-like, and most of ours are over-dispersed

- **Goals.** Maher (1982) — independent Poisson per side with attack/defence
  strengths and home advantage. Dixon & Coles (1997, *JRSS-C*) — the same with
  a low-score dependence correction (τ on 0-0/1-0/0-1/1-1) and **exponential
  time-decay** of past matches, motivated by betting-market inefficiency.
  Karlis & Ntzoufras (2003) — bivariate Poisson. Boshnakov et al. (2017) —
  Weibull count models for goals. *Implication for us:* the bzzoiro model
  `dc-blend-v1` is in this family; `goals_total`/`goals_for` are the one place
  a **devigged consensus** exists and must be compared (past frequency ≠ edge).
  Half splits: first halves carry ~45% of goals (7,516 matches in-repo), not
  50%.
- **Corners, shots, fouls, cards.** Variance exceeds the mean (team-level
  heterogeneity, game-state feedback), so a negative-binomial or Conway–
  Maxwell–Poisson fit is the standard; Dawson, Dobson, Goddard & Wilson (2007,
  *JRSS-A*) modelled disciplinary points with a bivariate negative binomial;
  the 2026 *JRSS-A* "Yellow fever" paper uses a bivariate mean-parameterised
  CMP copula across the Big 5 and **rejects referee consistency**. *Implication:*
  the sheet's `dispersion` is floored at `sqrt(mean)` because a short sample
  routinely looks tighter than Poisson and is not (Torino–Monza's six corner
  observations {6,6,6,6,7,7} preceded a 16). Treat a sample SD below the
  Poisson floor as under-measured, never as precision.
- **Small samples and shrinkage.** Empirical-Bayes shrinkage toward a
  population mean (James–Stein; Efron & Morris 1975) is what `shrunk_mean`
  does with `n/(n+10)`. Wilson (1927) score interval is `p_low`'s first half;
  the count model at the line is the second. A 4/4 is four matches; 16/20
  beats 3/3 (method §14, §87).

## 2. Home advantage and referee bias are real, and they are in the cards

- Home advantage in football is the largest of the major team sports and has
  been shrinking; it is partly crowd-on-referee. Reade & Singleton (closed
  doors, 2020–21): removing crowds reduced the home bias in cards. Dawson et
  al. (2007): home teams accumulate fewer yellows/reds, attributable to
  referee behaviour rather than team behaviour. Buraimo, Forrest & Simmons
  (2010, *JRSS-A*): bivariate probit on EPL and Bundesliga, controlling for
  derby, stadium type and bookmaker odds as strength — bias toward home teams
  in both. *Implication:* the venue split in `market_priors.json`
  (`cards_for` home 1.60 vs away 2.11) is this effect measured on our data;
  a `cards_for` UNDER on the away side needs a bigger margin than the pooled
  sample suggests, and the referee is the single largest unmodelled input on
  any card row (Bankes 4.15 vs Oliver 3.10 yellows/match — a third of a line).
- **Referee heterogeneity** means a card row without a named official is
  missing its biggest driver; code caps it at `LEAN` and doubles `k`. With an
  official named, `matches` is the sample: 5.75 over 4 matches is four numbers.

## 3. Game state drives counts, and the direction is not symmetric

Score effects (StatsBomb 2013; later replications): the trailing side takes
more shots of lower quality, holds more possession, wins more corners; the
leading side shoots less and better. Corners split almost evenly between
winner and loser over a match (4.70 vs 4.78 in-repo), which is why
goals ↔ corners is ~0 while goals ↔ SOT is +0.55. *Implication:* method §24's
four scenarios (favourite ahead / underdog ahead / 0-0 to 60' / level) are the
practical form of this; weight them by the 1X2 probabilities from
`market_context`, and ask for each market which scenario kills it. A strong
favourite at home scoring early flattens SOT-against and corners-for the
underdog; a 0-0 to 60' inflates fouls and cards in a knockout.

## 4. Stakes and match importance

- **Two-legged ties.** The second leg is played with knowledge of the
  aggregate; a side trailing must attack (shots, corners, goals-for up on
  their side; cards up as the clock runs), a side comfortably through rotates
  and manages. Second-leg home advantage is documented (Page & Page 2007).
  Extra time exists in some competitions and not others (UEFA yes; Copa do
  Brasil from the R16 straight to penalties) — settlement rules for counting
  markets follow the competition. *Implication:* `previous_leg_event_id` and
  `round_name` are the highest-value context fields in the system and are null
  in the dossiers; read them via `get_match_detail`.
- **Derbies** raise fouls and cards materially (Buraimo et al. controlled for
  it because it matters); `is_local_derby` is a provider flag that has been
  wrong — use distance too.
- **Dead rubbers, relegation six-pointers, cup rotation** change the XI and
  the tempo. Read the table (`get_standings`) and the fixture list
  (`get_team_fixtures`) before believing "last ten" describes tonight.

## 5. Fixture congestion and fatigue

Julian, Page & Harper (2020, *Sports Medicine*, meta-analysis): players
largely **maintain total distance and physical output** under congestion
(<96h between matches); injury incidence rises (systematic reviews 2022).
*Implication:* congestion is an **availability and rotation** argument (props,
`squad_availability`, predicted XI), not a "tired legs → fewer shots"
argument. Say which.

## 6. Underlying quality vs results

Expected goals regress: a side scoring well above its xGF is finishing hot;
the finishing will regress before the shot volume does. The only season xG in
the system is `season_form` (from standings); code flags an actual-minus-xGF
gap ≥0.75/game over ≥5 games. *Implication:* a shots/SOT lean built on
results (goals) is weaker than one built on the shots sample itself; a
goals-for OVER on an over-performing side is the classic regression trap.

## 7. Opponent adjustment without an "against" metric

The standard model conditions on opponent defence (Maher/Dixon–Coles attack ×
defence). We hold `goals_against` only; for corners, shots, fouls we hold each
side's own `*_for`. Use the opponent's own `*_for` and style as a proxy
(a side that shoots 18 times concedes possession and fouls; a side that
defends deep concedes corners) and say it is a proxy. The bzzoiro model's xG
per side in `market_context` is the one opponent-adjusted number available.

## 8. Recency and weighting

Dixon–Coles decay half-lives in the literature run ~1–2 seasons for goals;
for counting stats with tactical drivers (manager change, new full-backs) a
shorter window is defensible. Method §12–§13: compare season-heavy vs
recent-heavy vs venue-heavy vs opponent-adjusted reads; convergence raises
confidence, divergence lowers it. Our sample is last-ten by construction
(`team_a_l10`), scoped to this season — so "recent" is all we have, and
`season_form` is the season view.

## 9. Price, edge, and market efficiency

- Implied probability = 1/odds; remove the overround before comparing
  (multiplicative devig is the default here; Shin's method was tested and
  rejected for our purpose). Pinnacle's closing line is the sharp reference
  (closing-line-value literature); Superbet is a soft book and is **not** in
  the 88-book grid.
- Edge exists only when `fair probability > implied`, with a fair estimate of
  adequate quality (method §104). Per-team "to score" and 0.5 lines are house
  markets that sit at or under consensus (ledger 2026-08-30/31: −0.1 to −5.6pp
  on five such legs).
- Kelly / stake sizing is deliberately out of scope for every agent.

## 10. Correlation and slips

Positive dependence among same-match legs makes the product of leg
probabilities too **low** for shots-and-goals and about right for corners
(r ≈ 0); fouls run mildly *against* goals. Same-match legs measured over
12,555 pairs in-repo give λ = 1.009, i.e. a Bet Builder cannot rescue a
below-bar leg. The builder score (method §44) is implemented in
`bet_builder_draft.py`; the contradiction test as a *scenario* test (§40),
the tail-risk penalty and the source-conflict penalty are yours.

## 11. Post-mortem discipline

Attribute every settled row to `MODEL-CONSISTENT / MODEL-SURPRISING /
PURE VARIANCE` (method §117) and to one error category (§47). A category that
wins 84% produces losses; three of them in a row is not evidence the category
is broken (`tier_for_row` docstring records the experiment). Use
`backtest_slate.py` for a class of read, never for one row.

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
- In-repo measurements: `.claude/skills/bet-slip-audit/reference/base-rates.md`, memory notes `same-match-legs-are-independent`, `venue-is-a-prior-not-a-split`, `p-low-understates-by-23pp`, `estimator-bakeoff-ladder-yardstick`.
