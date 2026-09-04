# Tennis methodology — the models behind each claim, and how they map to our data

## 1. Tennis is a hierarchy of nearly-independent points

- **Klaassen & Magnus (2001, *JASA*)**, ~90,000 Wimbledon points: points are
  *not* exactly i.i.d. — winning the previous point helps slightly, and servers
  do worse on important points — but the deviations are small enough that an
  i.i.d. point model is a workable approximation for match-level quantities.
- **Barnett & Clarke (2005, *IMA J. Management Math.*)**: combine each
  player's serve-points-won and return-points-won with tour averages to get
  the two serve probabilities for *this* pairing
  (`p_A = f_A − g_B + g_tour`, where `f` is A's serve % won, `g` is B's return
  % won), then propagate point → game → set → match to predict winner **and
  match length**, updatable live. **O'Malley (2008)** and **Newton & Keller
  (2005)** give the closed-form game/set/match probabilities.
- *Implication for us:* every length market (games, sets, a player's games)
  is a function of two **hold probabilities**. We do not hold serve/return
  percentages per player (only aces, DFs, first-serve %, break points faced),
  so the analyst reconstructs them from the web for the two players on this
  surface and reasons: high hold both sides ⇒ long sets, tie-breaks, few
  breaks; asymmetric hold ⇒ short sets; both fragile ⇒ many breaks, possibly
  three sets. Method §84's "two paths to an over" is exactly this.

## 2. Surface changes the hold rate, and the hold rate changes everything

- Hold rates are highest on grass, lowest on clay, hard in between. The
  returner's break chance is ~1.5 points higher on clay than hard and ~7
  points higher than on grass (Smarkets trading note); the probability a set
  reaches 6-6 is highest on grass. A best-of-three between two strong servers
  on grass typically finishes in 19–23 games; the same pairing on clay runs
  3–5 games longer on average (Tennisbettingforum surface data).
- Aces and "free points" fall on clay; double faults are not surface-neutral
  either (players take more second-serve risk when the return is punishing).
- *Implication:* a sample from another surface describes another regime.
  `SURFACE_MISMATCH` removes it when the competition is pinned; when it is
  not, you must read `surface` on each observation and say what fraction
  matches tonight (Boulter–Muchová: grass medians 9.0/11.0 aces vs hard
  6.0/5.0 — the row was an artefact of a surface neither would play on).
  Method §66's order — current surface → current tournament → recent form →
  opponent quality → season → H2H → ranking — is the analyst's order here.

## 3. Format: best-of-five is a different sport for every length market

- Men's Grand Slam main draw is best-of-five; everything else (all WTA, ATP
  tour, slam qualifying) is best-of-three. A BO5 match runs 18–65 games and 3–5
  sets; a BO3 runs 12–39 games and 2–3 sets. `total_sets UNDER 3.5` is a
  tautology in BO3 and a real bet in BO5; a book pricing a BO5 event posts
  2.40 for the same words.
- *Implication:* the format gate (`config/tennis_match_format.json`) needs the
  competition name; if it did not run, men's slam rows appear at the top of the
  sheet with `p_low` 0.78–0.84 and are worthless. Slam qualifying is BO3 and
  tennis-abstract files it under the same level "G" — the code separates by
  round; you should confirm the round on the web.

## 4. Ratings, form and opponent quality

- **Kovalchik (2016, *JQAS*)** compared eleven prediction approaches: Elo
  (the FiveThirtyEight variant) and ranking-based regression were best, ~75%
  for top players — competitive with bookmakers; career-to-date data helped
  for lower-ranked players. **Angelini, Candila & De Angelis (2022)**:
  surface-specific Elo improves men's forecasts; standard Elo is enough for
  women. Sackmann publishes surface Elo on tennisabstract.com.
- *Implication:* we hold no rating. Use the book's own match odds
  (`result_market_lines`) as the favourite-strength input to the scenario
  weights, labelled as the book's opinion; use web rankings/Elo to classify
  the **opposition of the sample** (method §67: a 6-1 6-2 against a qualifier
  is not the same evidence as 7-6 6-4 against a top-20 server) and tonight's
  opponent. A `games_won` distribution is conditional on who the player faced;
  the row conditions on nothing (Tagger: mode 12 against WTA-125 fields).
- Quality of win (method §68): read the scorelines behind the sample, not W/L.
  Recency over momentum (§72): W-W-W against low quality is not momentum.

## 5. H2H decays and is a supporting prior (method §65, §107)

Weights 1.0 (0–90 d), 0.75 (91–180), 0.50 (181–365), 0.25 (>365), and
surface-matched or not. An old H2H that contradicts current surface form is a
**conflict → downgrade**, never a tiebreaker toward the H2H side. The pipeline
already drops >12-month meetings (`STALE_H2H`) from totals samples.

## 6. Fatigue, schedule, retirements (method §73)

Sets and games played, minutes on court, hours of rest, back-to-back days,
travel, qualifiers' extra matches — all web-sourced here. Do not assume "three
sets yesterday = bad": a three-set win over a strong opponent can be better
evidence of level than two easy wins. A recent retirement or medical time-out
is a **void risk** for length markets (Superbet's rules on retirement differ by
market — say the risk, do not price it), and a fitness asymmetry is a
kill-case for any OVER built on competitiveness.

## 7. Tie-breaks and breaks are not aces (method §85–§86)

About one in five ATP sets and one in eight WTA sets go to a tie-break
(Tennis Abstract). Tie-break probability is a function of *both* hold rates
on this surface, not of ace counts; a big server against an elite returner
holds less than his ace count suggests. High hold + high return pressure can
produce break-break-short-set, not a long set. Test `HOLD SUPPORT vs BREAK
RISK` separately for every OVER.

## 8. Distribution over mean, and scoreline arithmetic (method §15, §37, §40, §88)

Games in a set: 6 (6-0) to 13 (7-6). Two-set match: 12–26 games; three-set:
18–39. A player's games in a straight-sets loss: 0–12; in a straight-sets
win: 12–14. So for every rung write the scorelines that settle it and ask
which are natural for the modal scenario (`7-5 6-4 = 22` fails O23.5; `7-6
7-5 = 25` passes). A rung the modal scoreline lands *on* is the fragile one.
`total_games` mean ≫ median (22.5 vs 19.5) means a few three-setters carry
the mean; the median is the two-set world.

## 9. Small samples and identity (method §87, §98)

Per-player form is ten matches; on-surface it is often 3–7. Wilson and the
count model already shrink, but identical `p_low` across neighbouring rungs
means the sample has no observation between them. And a wrong human is worse
than a small sample: before 2026-08-28 one provider served Benoît Paire's page
under 72 WTA names. `MISIDENTIFIED` gaps are the guard; never reconcile with
older tennis numbers.

## 10. Price, with no consensus to lean on (method §26, §89–§90, §104)

There is no odds feed, no model and no MCP for tennis here, so `p_low`/
`p_central` are the only probabilities and are weaker than a football row's
(nothing corroborates them; the sport is not settled by the backtest, so no
calibration exists). Decide the rung blind, then look at the price. Superbet
is a soft book; its tennis totals ladders are wide (12.5–36.5) so the rung the
sheet chose is one of many — read the whole ladder and say why that rung.

## Sources

- Klaassen, F. J. G. M. & Magnus, J. R. (2001). Are points in tennis independent and identically distributed? *JASA* 96(454), 500–509. https://www.tandfonline.com/doi/abs/10.1198/016214501753168217
- Barnett, T. & Clarke, S. R. (2005). Combining player statistics to predict outcomes of tennis matches. *IMA Journal of Management Mathematics* 16(2), 113–120. https://academic.oup.com/imaman/article-abstract/16/2/113/704903
- O'Malley, A. J. (2008). Probability formulas and statistical analysis in tennis. *JQAS* 4(2).
- Newton, P. K. & Keller, J. B. (2005). Probability of winning at tennis I. Theory and data. *Studies in Applied Mathematics*.
- Kovalchik, S. A. (2016). Searching for the GOAT of tennis win prediction. *JQAS* 12(3), 127–138. https://vuir.vu.edu.au/34652/
- Angelini, G., Candila, V. & De Angelis, L. (2022). Weighted Elo rating for tennis match predictions / surface-specific Elo. *European Journal of Operational Research*; see also https://www.degruyterbrill.com/document/doi/10.1515/jqas-2019-0110/html
- Sackmann, J. Tennis Abstract — surface Elo, tie-break frequency (ATP ~1/5 sets, WTA ~1/8). http://www.tennisabstract.com/blog/category/tiebreaks/
- Smarkets. French Open tennis trading strategy (returner break chance by surface). https://help.smarkets.com/hc/en-gb/articles/115003425649
- Tennisbettingforum. Tennis surface betting strategy (games per BO3 by surface). https://tennisbettingforum.com/tennis-surface-betting-strategy/
- In-repo: memory notes `pooled-estimator-targets-wrong-quantity`, `tennis-total-measured-the-wrong-quantity`, `surface-contamination-and-friendly-leak`, `bo5-gate-suppressed-the-market-not-the-sample`, `tennis-sources-consolidated`, `jsmatches-fallback-is-2018-vintage`; `config/tennis_surface_map.json` `_why`.
