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

Dated board sizes: Monday 2026-09-21, 3,026 tennis rows, `games_won_for`
alone 1,084; the 2026-10-07 sheet (`05_sheet.json`), 17,744 tennis rows -
`games_won_for` 3,014, `games_won_set1_for` 2,672, `games_won_set2_for` 2,626,
`games_set2_total` 2,346, `games_set1_total` 2,326, `games_total` 1,556,
`handicap_games` 1,545, `sets_total` 220, `most_games` 129 (rows, both
directions; the row count grew with the per-set markets and the full ladder).

## Which estimator each market uses — this decides how to read `p_central`

Stats-only rows (`epoch: "stats_only"`, builds from 2026-10-05 07:15Z) hold
**no price**: no rating blended with it, no shrink to the rung's price, no
ladder centre. Two things can price a row, and since 2026-10-07 14:05Z
(`epochs.tennis_rating_prices`, `TENNIS_RATING_PRICES_FROM_UTC`) the split is:

| market | `p_central` (stats-only, from 2026-10-07 14:05Z) | `forecast_p` |
|---|---|---|
| `games_won_for` | the rating's 600 neighbours alone (`MatchForecast.read`, `tennis_rating.RATING_PRICED_MARKETS`) when the rating reads the fixture; else the sample's empirical frequency around the shrunk centre | the rating, **equal to `p_central`** when it reads the fixture |
| `handicap_games`, `most_games` (not the draw) | the neighbours alone, through `derived.py`'s `rating_p`; else the joint of the two samples | **null** (derived rows carry none) |
| `games_total` | `W_GAMES_TOTAL_RATING` = 0.5 x rating + 0.5 x the NB count model (the NB alone where the rating does not read the fixture) | the rating alone |
| `sets_total` | the sample's empirical frequency, no price | the rating |
| `games_set{1,2}_total`, `games_won_set{1,2}_for` | the sample's estimator (`games_won_set*` empirical frequency) | null |
| `aces_*`, `double_faults_*`, `serve_points_*`, `most_aces` etc. | count model (the centre may carry `CENTRE_SHRUNK_TO_LADDER` on a derived row) | null |
| `tiebreaks_total` | normal CDF, no Poisson floor (`NORMAL_NON_COUNT_METRICS`) | null |

"The rating reads the fixture" means a best-of-three (`default_period_count`
3 **or null**), both players with at least `MIN_RATED = 10` rated matches and
a fitted tier (`run_sheet.tennis_forecast`). Verified on the 2026-10-07 sheet:
all 2,960 `games_won_for` rows with a `forecast_p` have `p_central ==
forecast_p`; `forecast_p` exists only on `games_won_for`, `games_total` and
`sets_total`; handicap / most rows on rated fixtures have none, and their
`p_central` is a multiple of 1/600 (to rounding) on 1,613 of the 1,653 handicap / most rows of rated fixtures (the rest are not explained here - a suspicion: draw or push lines).

Consequence: **the old advice "`p_central` is the sample, `forecast_p` is the
rating, compare them" is void for `games_won_for` and half-void for
`games_total`.** The sample's k/n is the independent number. On `sets_total`
and where the rating does not read the fixture the two estimators are still
separate.

Rows of an older SHEET (before the 2026-10-05 epoch, or before 14:05Z on
2026-10-07) priced it differently, and a leg printed from one keeps its
number:

- `games_total`, `games_won_for`, `sets_total`, `handicap_games` with a
  `TENNIS_RATING` note: rating blended with the price,
  **0.25 x rating + 0.75 x `market_p`** (`W_TENNIS_RATING = 0.25`, unfitted;
  `blend_with_price`; the rating alone on a rung with no price). Pre-epoch
  rows only - a stats-only row never blends.
- `sets_total`, `games_won_for`, per-set games without the rating:
  empirical frequency **shrunk to the rung's price**
  (`P_SHRUNK_TO_PRICE`, w x hits/n + (1 - w) x `market_p`, w = n/(n+30),
  `K_TENNIS_LADDER_CENTRE`).
- The `TENNIS_RATING` note (`rating p ..., no price on this rung, rating
  alone`) still appears on stats-only rows the rating prices; do not read
  "blended" into it - there is no price in the number.

`sets_total` is bounded — on a best-of-three it is 2 or 3 and nothing else.
Integrating a bell curve over two bars took its error from +16.0 pp to +4.0 pp
when removed.

`games_won_for` is **bimodal**, and this is the single most important
distributional fact in tennis here. A straight-sets winner has won at least
twelve games, so the distribution is a loser mode spread over 0–11 and a
winner mode stacked on 12+. One day's 570 observations: 10:17, 11:10,
**12:159**, 13:84 — a trough at eleven and a wall at twelve. **Superbet's line
is 11.5, in the trough.**

## The calibration curve and its ceiling — read this before trusting a confident tennis row

History. The **old** sample-frequency estimator was overconfident at the top:
on 9,286 settled `games_won_for` rows a claimed 0.95 realised 0.728 and the
market had no measured bucket above 0.825 (2026-09-21 measurement).
`Calibration.realised` therefore refuses to let a market with its own curve
borrow the pooled curve above the top of its own measured range - silence
above a market's range is evidence, not a gap (`confidence.py`). That rule is
still in the code.

Now. The curves were **refitted on 2026-10-07** (installed that evening; a new
comparability epoch) on the **history of Sofascore events replayed as of each
match with the estimator SHEET prices with** - the tennis rating as of that
day, best-of-five matches skipped - not on our own settled days
(`config/sofa_confidence_calibration.json`, `fitted_from.db_path`
`data/refit_2026-10-08/sofa_replay.db`). `by_market.games_won_for` now reaches the `0.950-1.010`
bucket (realised 0.942 on 1,396 replayed rows; `games_total` tops at
0.875-0.900, `sets_total` at 0.600-0.700). The rows are replayed, heavily
correlated, and **not** independent matches: read `calibration_n` as a count
of rows. Tennis also has its own sport pool (`pooled_by_sport.tennis`), used
before the global one, and class curves (`by_class`: `tennis_women`,
`tennis_team_cup`).

Then line evidence (`bet.sofa.line_evidence`, from 2026-10-07 10:55Z) lowers
the confidence by the key's measured realised-minus-confidence on
Superbet's settled lines (`line_offset`) and by the price-band cap
(`price_band_cap`). Dated figures from `config/sofa_superbet_line_evidence.json`
(fitted 2026-10-07 19:11Z on the 2026-10-05/06 lines): tennis pooled offset
-0.054 over 210 games; printable `games_won_for` OVER -0.17, UNDER -0.12.
Those lines were priced by the older estimator - **no settled line yet
belongs to the rating-priced `games_won_for`**. A market without a curve of
its own, or a derived joint, reads its own lines or is `NO_LINE_EVIDENCE`.

## Sample scoping — and where a null defeats it

`samples.py` keeps a past match only when:

- `event.groundType == fixture.ground_type` — **tonight's surface**
- `infer_best_of(event) == fixture.default_period_count` — **tonight's format**

Both come off the fixture rather than from a competition-name pin, which is
what made the retired pipeline's surface scoping inert.

**The failure mode is a null.** At Challenger and ITF level `ground_type` is
the thinnest part of Sofascore's data. A fixture with no surface gets an
**empty** sample (gap `SURFACE_UNKNOWN`) and a past event with no surface is
dropped; a null `default_period_count` skips the format scope without a gap
(and the rating reads such a match as best-of-three). The surface test is
`settle.surfaces_comparable`: equal labels, or a generic "Hard" / "Clay" label
against any member of its family, so an indoor fixture can sample matches
whose indoor / outdoor is unknown. Check the fields before trusting a
surface or format claim, and say "unknown" when they are.
`infer_best_of` returns `None` for a match whose winner did not win 2 or 3
sets (a retirement), so those never enter a format-scoped sample.

`sample_n = 10` per side, `min_sample = 5`. Pages read **descending**.

Three buckets per metric: `side_a`, `side_b`, `h2h`. **`h2h` never reaches a
`*_for` row** — a head-to-head is a fact about a pairing.

**Match tiebreaks (open operator question).** Sofascore stores a 10-point
match tiebreak (ITF, UTR, team cups) as `periodN` points. Every sample,
neighbour and settlement counts it as **one game** to its winner
(`tennis_score.set_games`; `metrics.py` prefers the set score over
`gamesWon`, which counts none). Superbet's rule for games markets is
unverified; bet365's is one game.

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
- retirement risk, walkovers, withdrawals (a retirement - Sofascore status
  "Retired" - and a walkover are **refunds**, `settle.RETIRED` /
  `settle.WALKOVER`, since 2026-10-07)
- indoor vs outdoor, altitude, ball type, wind
- **any match-odds price** — there is no favourite strength in the sheet or
  the coupon (`Zwycięzca` sits in `unmapped_markets`); the rating's
  match-win probability is in the `TENNIS_RATING` note of a priced row, the
  book's view only through the `handicap_games` ladder in `04_offer.json`
- doubles: BOARD filters out any tennis match name containing `/`

## Where the centre comes from

```
w_c    = n / (n + 5)              K_CENTRE for tennis (by_sport)
centre = w_c·sample_mean + (1 − w_c)·prior
```

At n=10 the sample owns **67%** of the centre against football's 40%. There is
very little prior holding a tennis row up — which cuts both ways: a clean
sample is respected, and a bad one is not corrected. This is the centre of a
**sample-priced** row; `games_won_for` / `handicap_games` / `most_games` (and
half of `games_total`) on a fixture the rating reads no longer use it.

## Measured, and worth carrying

- Tennis length markets were measured overconfident by ~25 pp on 2026-09-06
  under the old estimator and then left uncorrected; the 2026-10-07 refit and
  line evidence replace that situation (above), they do not erase the
  dated finding that settled lines realised below confidence.
- `sets_total` and `aces_*` ladders were 0% checkable on the 2026-09
  measurement; overall only 52.4% of ladders could be checked at all.
- `games_*`, `sets_*`, `tiebreaks_*` and `handicap_games` are **one quantity
  family** in `confidence.py` (`QUANTITY_FAMILIES`, "games"), so a builder
  takes at most one of them; `aces_*` and `double_faults_*` are separate
  families.
- Serve points and per-set serve markets were refused in September for
  want of a curve of their own (149/253 = 0.589 realised against 0.777
  claimed; `serve_points_for` 15/31). That list still sits in
  `confidence.py` (`TENNIS_SERVE_POINTS`, `TENNIS_PER_SET_SERVE`) and still
  stops them borrowing a pool, but a market with its own curve in the
  2026-10-07 file (`serve_points_for`, `aces_set2_for`,
  `double_faults_set{1,2}_for`, `serve_points_set2_for`) is read from it, and
  all of them go through line evidence.
