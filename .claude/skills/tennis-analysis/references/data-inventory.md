# Tennis data inventory - what `sofa` measures, and what it does not

One statistics provider, **Sofascore**; Superbet supplies the prices. No
second feed, no consensus. Doubles are filtered out at BOARD (a name with `/`).

## Metrics (`TENNIS_METRICS` in `src/bet/sofa/metrics.py`)

Whole match: `games_total`, `games_won_for`, `sets_total`, `tiebreaks_total`,
`aces_*`, `double_faults_*`, `serve_points_*` (`_total` the match, `_for` one
player named by `subject`). Per set: `games_set1/2_total`,
`games_won_set1/2/3_for` (from the set score in the listing, so a row exists
wherever the match history does), `aces_set1/2_*`, `double_faults_set1/2_*`,
`serve_points_set1/2_*`. Rating-only: `match_won_for` ("Zwycięzca"),
`set1_won_for` / `set2_won_for`, `set_score`, `set_score_not`. Derived (not
sampled, `src/bet/sofa/derived.py`): `most_games`, `most_aces`,
`most_serve_points` (and per set), `most_double_faults_set1/2`,
`handicap_games`, `handicap_games_won_set1/2`, `handicap_aces`.

## Which estimator prices which market

| market | `p_central` | `forecast_p` |
|---|---|---|
| `games_won_for`; `games_set1/2_total`, `games_won_set1/2/3_for`, `sets_total` (`tennis_rating.SET_RATING_PRICED_MARKETS`, row marker `tennis_set_rule`); `match_won_for`, `set1/2_won_for`, `set_score`, `set_score_not` | the rating's neighbours alone | equal to `p_central` |
| `handicap_games`, `most_games` (not the draw) | the neighbours, through `derived.py` | none |
| `handicap_games_won_set1/2` | from 2026-10-28 the neighbours' own set-N margin (`tennis_rating.SET_HANDICAP_MARKETS`, note `SET_HANDICAP_NEIGHBOURS`); earlier the rho-0 joint of the two players' set games | none |
| `games_total` | `W_GAMES_TOTAL_RATING` 0.5 x neighbours + 0.5 x the NB count model | the rating alone |
| aces, double faults, serve points, `most_aces`, `most_serve_points`, `handicap_aces` | count model on the sample (derived: joint of the two samples) | none |
| `tiebreaks_total` | normal CDF without a Poisson floor (`NORMAL_NON_COUNT_METRICS`) | none |

"The rating reads the match" = best of three (`default_period_count` 3 or
null), both players with >= `MIN_RATED` (10) rated matches, a fitted tier
(`tennis_forecast` in `scripts/sofa/run_sheet.py`). The neighbours come from the tier x gender
cell (tier, then the pooled table, when a cell holds < 1200 outcomes; row
marker `tennis_table_rule`). Where the rating does not read the match, a
rating-priced family falls back to the sample's estimator and has no
`forecast_p` - and the rating-only markets have no row at all.

Verified on `runs/sofa/2026-10-19/05_sheet.json`: every tennis row with a
`forecast_p` on the families of the first row has `p_central == forecast_p`;
`games_total` differs (half the NB).

`games_won_for` is bimodal: a straight-sets winner has >= 12 games, a loser
is spread over 0-11 (one day's 570 observations: 10:17, 11:10, 12:159,
13:84). Superbet's line is usually 11.5, in the trough. `sets_total` is
bounded (2 or 3 on a best of three).

## The calibration curve

The curves are fitted on the history of Sofascore events replayed as of each
match with the estimator SHEET prices with (the rating as of that day,
best-of-five skipped, each side's sample scoped as SAMPLES scopes it) - not on
our settled days. `calibration_n` counts replayed rows, heavily correlated,
not independent matches. Tennis has its own sport pool and class curves
(`tennis_women`, `tennis_team_cup`; a class key without a curve is
`NO_CLASS_CURVE`). A market with its own curve never borrows a pool above
the top of its measured range (`Calibration.realised`); per-set serve and
serve-points keys never borrow one at all (`confidence.TENNIS_PER_SET_SERVE`,
`TENNIS_SERVE_POINTS`). Line evidence then lowers the confidence by what the
key's settled Superbet lines realised (`line_offset`, `price_band_cap`).

## Sample scoping - and where a null defeats it

A past match is kept only when the surface is comparable
(`settle.surfaces_comparable`: equal labels, or a generic "Hard" / "Clay"
against any member of its family - so an indoor fixture can sample
outdoor-unknown matches) and the format matches
(`metrics.infer_best_of(event) == fixture.default_period_count`;
`infer_best_of` is `None` for a retirement, so those never enter). A fixture
with a null `ground_type` gets an empty sample (`SURFACE_UNKNOWN`), a past
event with none is dropped; a null `default_period_count` skips the format
scope without a gap. Retired and walkover matches stay out of samples
(`settle.is_completed_event`); the rating counts a retirement as time on
court, not as a result.

`sample_n = 10` per side, `min_sample = 5`, pages read descending. Three
buckets per metric: `side_a`, `side_b`, `h2h`; `h2h` is built from the
`side_a` / `side_b` observations against each other, so it inherits their
scope and window, and never reaches a `*_for` row. Each observation carries
`opponent` and `opponent_id`.

**Match tiebreaks.** Sofascore stores a 10-point match tiebreak as `periodN`
points; every sample, neighbour and settlement counts it as one game to its
winner (`tennis_score.set_games`; Sofascore's `gamesWon` counts none).
Superbet's rule is unverified. Tour and Challenger neighbours exclude
match-tiebreak matches, ITF ones include them.

## Per-fixture context (`02_fixtures.json`)

| field | tennis meaning |
|---|---|
| `default_period_count` | the real best-of, 3 or 5; null = the format scope did not run |
| `ground_type` | the surface; null at the thin end of the calendar |
| `competition_name`, `category_name` | ATP / WTA / Challenger / ITF, the event |
| `kickoff_utc` vs `superbet_kickoff_utc` | disagree by up to 11 h on ITF; take the earlier |
| `identity` | `FUZZY` on a tennis name is a real risk |
| `round_number` / `round_name` | often null |

## What is NOT in the artifacts

- rankings, of either player or of any sample opponent;
- the round when null, and whether it is qualifying (best of three even at a
  slam);
- the previous match's length or duration (its start, the rest in days and
  the matches in 7 / 14 days **are** on disk: `03_samples.json` `schedule` ->
  `side_a` / `side_b` -> `last_match_utc`, `rest_days`, `matches_7d`,
  `matches_14d`);
- retirement risk, walkovers, withdrawals (a retirement or walkover is a
  refund);
- indoor vs outdoor, altitude, ball, wind.

The favourite's strength without a price is the rating's `forecast_p` on the
`match_won_for` sheet row; a price is never evidence.

## Where the centre comes from (sample-priced rows)

```
w_c    = n / (n + 8)              K_CENTRE tennis (config/sofa_engine_constants.json, by_sport)
centre = w_c * sample_mean + (1 - w_c) * prior
```

At n=10 the sample owns 56% of the centre: a clean sample is respected, a bad
one is barely corrected.

## Builder families

`games_*`, `sets_*`, `tiebreaks_*` and `handicap_games` are one quantity
family in `confidence.QUANTITY_FAMILIES` ("games"), so a builder takes at most
one of them; aces and double faults are separate families and will combine
although they share the match-length mechanism.
