# Tennis data inventory — exactly what `sofa` measures, and what it does not

One statistics provider: **Sofascore**. No second feed, no agreement field, no
model, no consensus. Superbet supplies the prices and nothing else.

## Metrics collected (`TENNIS_METRICS` in `src/bet/sofa/metrics.py`)

Whole match:

```
games_total          games_won_for
sets_total           tiebreaks_total
aces_total           aces_for
double_faults_total  double_faults_for
serve_points_total   serve_points_for
```

Per set (set 1 and set 2 only):

```
aces_set1_*  aces_set2_*
double_faults_set1_*  double_faults_set2_*
serve_points_set1_*   serve_points_set2_*
```

Derived, priced but not sampled (`src/bet/sofa/derived.py`):

```
most_aces  most_games  most_serve_points  handicap_games
```

`_total` is the match, `_for` is one player, and `subject` names which.

On a Monday board (2026-09-21) tennis produced 25 markets and 3,026 rows;
`games_won_for` alone was **1,084** of them, `games_total` 688,
`handicap_games` 581, `sets_total` 168.

## Which estimator each market uses — this decides how to read `p_central`

| market | estimator | so `p_central` … |
|---|---|---|
| stats-only row (`epoch: "stats_only"`), any market | the sample's estimator alone (`run_sheet.process_fixture`, `stats_only`) - no rating blended with the price, no shrink to the rung's price, no ladder centre | holds **no price**; the rating is `forecast_p` (`tennis_rating`) beside it, never a gate |
| older row: `games_total`, `games_won_for`, `sets_total`, `handicap_games` with a `TENNIS_RATING` note (`tennis_rating.RATED_MARKETS`) | rating blended with the price (`blend_with_price`) | **0.25·rating p + 0.75·`market_p`** (`W_TENNIS_RATING = 0.25`, unfitted); the rating alone only on a rung with no price |
| older row: `sets_total`, `games_won_for`, `games_set{1,2}_total`, `games_won_set{1,2,3}_for` without the rating (`EMPIRICAL_FREQUENCY_METRICS`) | empirical frequency **shrunk to the rung's price** (`p_empirical_shrunk_to_price`, note `P_SHRUNK_TO_PRICE`) | **w·hits/n + (1−w)·`market_p`**, w = n/(n+30) (`K_TENNIS_LADDER_CENTRE`; 0.25 at n=10); the raw hit rate only on a rung with no price |
| `games_total` (unrated), `aces_*`, `double_faults_*`, `serve_points_*`, `most_*` | count model (centre may carry `CENTRE_SHRUNK_TO_LADDER`) | will **not** equal the hit rate, and should not |
| `tiebreaks_total` | non-count | refused by CONFIDENCE (`NOT_IN_CALIBRATION_FIT`) |

So on an older row a `p_central` near `market_p` and far from `hits/n` was
the code working (`scripts/sofa/run_sheet.py`, `process_fixture`); on a
stats-only row it is a coincidence worth a look.

`sets_total` is bounded — on a best-of-three it is 2 or 3 and nothing else.
Integrating a bell curve over two bars took its error from +16.0 pp to +4.0 pp
when removed.

`games_won_for` is **bimodal**, and this is the single most important
distributional fact in tennis here. A straight-sets winner has won at least
twelve games, so the distribution is a loser mode spread over 0–11 and a
winner mode stacked on 12+. One day's 570 observations: 10:17, 11:10,
**12:159**, 13:84 — a trough at eleven and a wall at twelve. **Superbet's line
is 11.5, in the trough.**

Replayed over 1,293 rungs the two estimators scored: normal CDF OVER 1.07 /
UNDER 0.93; empirical OVER 1.01 / UNDER 0.98.

## The calibration ceiling — read this before trusting a confident tennis row

The empirical frequency is honest in the middle and **overconfident at the
top**. On 9,286 settled `games_won_for` rows a claimed 0.95 realises **0.728**,
and the market has **no measured bucket above 0.825** (its best realises
0.756).

`Calibration.realised` therefore refuses to let a market with its own curve
borrow the pooled curve above the top of its own measured range: silence above
a market's measured range is evidence, not a gap — it says the model never
produces a confident prediction there that verifies. Letting it fall through
produced 12 tennis legs at a claimed 0.905 that the market has never once been
observed to deliver.

Tennis also has its own pooled curve (`pooled:<sport>`), used before the global
one, because tennis has 56,581 settled rows of its own and the global pool is
almost entirely football counts.

## Sample scoping — and where it silently does nothing

`samples.py` keeps a past match only when:

- `event.groundType == fixture.ground_type` — **tonight's surface**
- `infer_best_of(event) == fixture.default_period_count` — **tonight's format**

Both come off the fixture rather than from a competition-name pin, which is
what made the retired pipeline's surface scoping inert.

**The failure mode is a null.** At Challenger and ITF level `ground_type` is
the thinnest part of Sofascore's data; when it is absent the comparison cannot
match and the scope does not protect you. Check the field before trusting a
surface claim, and say "surface unknown" when it is.

`sample_n = 10` per side, `min_sample = 5`. Pages read **descending**.

Three buckets per metric: `side_a`, `side_b`, `h2h`. **`h2h` never reaches a
`*_for` row** — a head-to-head is a fact about a pairing.

## Per-fixture context (`02_fixtures.json`)

| field | tennis meaning |
|---|---|
| `default_period_count` | **the real best-of, 3 or 5.** Load-bearing at a slam. Null means the format scope did not run. |
| `ground_type` | the surface. Null at the thin end of the calendar. |
| `competition_name`, `category_name` | ATP / WTA / Challenger / ITF, and the event |
| `kickoff_utc` vs `superbet_kickoff_utc` | **disagree by up to 11 h on ITF**, and the error makes a finished match look upcoming. Take the earlier. |
| `identity` | `FUZZY` on a tennis name is a real risk — take it seriously |
| `round_number` / `round_name` | often null for tennis |
| `referee`, `venue_name` | not meaningful here |

## What is NOT in the artifacts

- **rankings**, either player's or any sample opponent's
- the round, and whether it is qualifying (**qualifying is best-of-three even
  at a slam**)
- the previous match's length or duration (its start and the rest in days
  **are** on disk since 2026-10-04: `schedule.side_a/side_b` in
  `03_samples.json` - `last_match_utc`, `rest_days`, `matches_7d`,
  `matches_14d`)
- retirement risk, walkovers, withdrawals
- indoor vs outdoor, altitude, ball type, wind
- **any match-odds price** — there is no favourite strength anywhere in the
  artifacts, and no consensus to devig against
- doubles: BOARD filters out any tennis match name containing `/`

## Where the centre comes from

```
w_c    = n / (n + 5)              K_CENTRE for tennis (by_sport)
centre = w_c·sample_mean + (1 − w_c)·prior
```

At n=10 the sample owns **67%** of the centre against football's 40%. There is
very little prior holding a tennis row up — which cuts both ways: a clean
sample is respected, and a bad one is not corrected.

## Measured, and worth carrying

- `sets_total` has **202** settled rows — too few for its own market curve,
  which is why the sport pool exists.
- `sets_total` and `aces_*` ladders were **0%** checkable; overall only 52.4%
  of ladders can be checked at all.
- Tennis length markets were measured overconfident by ~25 pp on 2026-09-06 and
  **deliberately not corrected** — the fix risked overfitting.
- `games_*`, `sets_*` and `handicap_games` are **one quantity family** in
  `confidence.py`, so a builder takes at most one of them.
