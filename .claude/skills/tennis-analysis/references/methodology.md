# Tennis methodology — the models behind each claim, and how they map to our data

Each section ends with what `sofa` holds for it and what it does not - the
latter is where your contribution is.

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
  `sofa` scopes on the fixture's own `ground_type`
  (`event.groundType == fixture.ground_type` in `samples.py`), which is a real
  improvement on a competition-name pin. **The failure mode is a null:** at
  Challenger and ITF level `ground_type` is often absent: a fixture with
  none gets an empty sample (`SURFACE_UNKNOWN`), a past event with none is
  dropped, and a generic "Hard" / "Clay" label matches any member of its
  family (`settle.surfaces_comparable`). Check the field and say "surface
  unknown" when it is. Grass medians of 9.0/11.0 aces against hard
  6.0/5.0 is what an unscoped sample costs. The analyst's order remains:
  current surface → current tournament → recent form → opponent quality →
  season → H2H → ranking.

## 3. Format: best-of-five is a different sport for every length market

- Men's Grand Slam main draw is best-of-five; everything else (all WTA, ATP
  tour, ATP Challenger, slam qualifying) is best-of-three. A BO5 match runs 18–65 games and 3–5
  sets; a BO3 runs 12–39 games and 2–3 sets. `total_sets UNDER 3.5` is a
  tautology in BO3 and a real bet in BO5; a book pricing a BO5 event posts
  2.40 for the same words.
- *Implication:* `sofa` scopes on `default_period_count`, which for tennis is
  Sofascore's real best-of, taken from the fixture rather than inferred from a
  competition name (past matches: `infer_best_of`, from the winner's sets).
  A **null** there means the format scope did not run, and men's slam rows
  then reach the top of the sheet as tautologies worth nothing. The rating
  (`tennis_rating.py`) is built from best-of-three matches only: a best-of-five
  fixture gets no rating forecast (no `forecast_p`, the sample prices the
  row), and a null format is read as best-of-three.
  **Slam qualifying is best-of-three** even though it carries the slam's name —
  confirm the round on the web, because `round_name` is frequently null for
  tennis.

## 4. Ratings, form and opponent quality

- **Kovalchik (2016, *JQAS*)** compared eleven prediction approaches: Elo
  (the FiveThirtyEight variant) and ranking-based regression were best, ~75%
  for top players — competitive with bookmakers; career-to-date data helped
  for lower-ranked players. **Angelini, Candila & De Angelis (2022)**:
  surface-specific Elo improves men's forecasts; standard Elo is enough for
  women. Sackmann publishes surface Elo on tennisabstract.com.
- *Implication:* sofa holds one rating (`src/bet/sofa/tennis_rating.py`): a
  surface-blended Elo, calibrated per tier (ITF / CH / TOUR), whose
  match-win probability picks the 600 nearest historical best-of-three
  matches; games, sets and tiebreaks are read off them. A row priced through
  it carries a `TENNIS_RATING` note with "<side> wins the match p" - the
  model's opinion, not the book's. It **is** the price of the families in
  SKILL.md's table (`games_won_for`, per-set games, `sets_total`, the winner
  and set markets, `handicap_games`, `most_games`) and half of
  `games_total`'s; on those `p_central` and `forecast_p` are the same number
  and the player's own sample enters only as próbka k/n. The neighbours are
  scoped by tier x gender, not by surface or opposition, so the surface and
  the opposition remain the analyst's. The favourite's strength without a
  price is the rating's `forecast_p` on the `match_won_for` sheet row (a
  price is never evidence); use web rankings/Elo to classify
  the **opposition of the sample** (method §67: a 6-1 6-2 against a qualifier
  is not the same evidence as 7-6 6-4 against a top-20 server) and tonight's
  opponent. A `games_won` distribution is conditional on who the player faced;
  the row conditions on nothing (Tagger: mode 12 against WTA-125 fields).
- Quality of win (method §68): read the scorelines behind the sample, not W/L.
  Recency over momentum (§72): W-W-W against low quality is not momentum.

## 5. H2H decays and is a supporting prior (method §65, §107)

Weights 1.0 (0–90 d), 0.75 (91–180), 0.50 (181–365), 0.25 (>365), and
surface-matched or not. An old H2H that contradicts current surface form is a
**conflict → downgrade**, never a tiebreaker toward the H2H side.

**`sofa` does not filter H2H by age.** `STALE_H2H` was the retired pipeline's
gate and has no equivalent here: `samples.py` builds the `h2h` bucket from
the `side_a` / `side_b` observations (so it inherits their scope and newest-ten
window, with no age rule of its own), and a `*_total` rung pools
`side_a + side_b + h2h`, deduplicated by event id - an old meeting inside the
window counts as much as last month's.
Only the coupon-level age gates apply afterwards (`MAX_SAMPLE_AGE_DAYS = 60` on
the freshest observation, 180 days on the oldest, `SAMPLE_CROSSES_SEASON`), and they
judge the *bucket*, not the meeting. A `*_for` rung never sees h2h at all —
it reads only the side it names. Check the observation dates yourself.

## 6. Fatigue, schedule, retirements (method §73)

Sets and games played, minutes on court, hours of rest, back-to-back days,
travel, qualifiers' extra matches — all web-sourced here. Do not assume "three
sets yesterday = bad": a three-set win over a strong opponent can be better
evidence of level than two easy wins. A recent retirement or medical time-out
is a **void risk** for length markets: a retirement (Sofascore
status "Retired") and a walkover are refunds (0 u., `settle.RETIRED` /
`settle.WALKOVER`; operator's rule) - say the risk, do not price it - and a
fitness asymmetry is a kill-case for any OVER built on competitiveness. A
retired match does not enter a sample, and the rating counts it as time on
court only.

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

Per-player form is ten matches; after the surface and format scope it is often
3–7, and **a side with 0–3 is not a sample**. Identical `p_central` across
neighbouring rungs means the sample has no observation between them — the model
separates the prices, not the evidence.

`K_CENTRE` is 8 for tennis: at n=10 the sample owns 56% of the centre of a
sample-priced row against football's 40% (the rating-priced families do not
read it - see §4). A clean sample is respected and a bad one is barely
corrected.

A wrong human is worse than a small sample. `identity: FUZZY` on a tennis name
is a real risk — names collide — and it must never be reported as confirmed.

## 10. Price, with no consensus to lean on (method §26, §89–§90, §104)

There is no odds feed, no consensus and no MCP for tennis here. The only
reference price is Superbet's own other side, power-devigged into `market_p`,
and when the rung is one-sided there is none (`market_p` null).
Decide the rung blind. On the coupon the price is only the betting condition
(x = confidence x odds >= 0.90, ladder margin <= 15%) - never evidence.

Tennis is calibrated from the history, not from our settled days: the
curves are fitted on Sofascore events replayed as of each match with the
estimator SHEET prices with (`data-inventory.md`, "The calibration curve");
`calibration_n` counts replayed rows, not independent matches. Line evidence
then lowers the confidence by what the key's Superbet lines realised below it
(`line_offset`, `price_band_cap`). Per-set serve and serve-points keys never
borrow a pool (`confidence.TENNIS_PER_SET_SERVE`, `TENNIS_SERVE_POINTS`).
A 10-point match tiebreak counts as one game in the code; Superbet's rule is
unverified (open operator question).

Superbet's tennis ladders are wide, so the
rung the sheet ranked is one of many — read the whole ladder and say why that
rung.

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
- In-repo: `src/bet/sofa/tennis_rating.py` (the rating, `RATING_PRICED_MARKETS`, `W_GAMES_TOTAL_RATING`), `src/bet/sofa/epochs.py` (`tennis_rating_prices`), `src/bet/sofa/tennis_score.py` (the match tiebreak), `src/bet/sofa/engine.py` (`EMPIRICAL_FREQUENCY_METRICS`, and the measured bimodality of `games_won_for`); `src/bet/sofa/confidence.py` (`Calibration.realised`, the measured-ceiling rule, the sport pool); `src/bet/sofa/samples.py` (the surface and format scope); `docs/sofa/RUNBOOK.md`.
