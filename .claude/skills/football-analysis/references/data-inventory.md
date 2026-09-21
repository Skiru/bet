# Football data inventory — exactly what `sofa` measures, and what it does not

Everything here comes from **Sofascore only**. There is no second statistics
provider, no consensus, no agreement flag. Say that once in your header and
never present a row as corroborated.

## Metrics collected (`FOOTBALL_METRICS` in `src/bet/sofa/metrics.py`)

Full match:

```
goals_total          goals_for
corners_total        corners_for
cards_points_total   cards_points_for
fouls_total          fouls_for
offsides_total       offsides_for
shots_total          shots_for
shots_on_target_total shots_on_target_for
xg_total             xg_for
```

Per half (`/statistics` has always been keyed by period; these were unmapped
until 2026-09-18):

```
goals_1h_*  goals_2h_*
corners_1h_* corners_2h_*
fouls_1h_*
shots_1h_*  shots_on_target_1h_*
```

`_total` is the match; `_for` is one side, and `subject` names which. A
`period_complement` exists so a second half can be derived as full minus
first where Sofascore reports only one.

**There is no `*_against` metric.** If you want "what the opponent concedes",
you must read the opponent's own `*_for` and say you are using a proxy.

## Derived markets (`src/bet/sofa/derived.py`) — priced, not sampled

```
both_over_<metric>    "Każda z drużyn powyżej 3.5 rz. rożnych"
most_<metric>         "Najwięcej kartek", "Liczba rzutów rożnych - H2H"
handicap_<metric>     "Rzuty rożne handicap"
```

These are **functions of two sides**, not counts of one thing. Consequences you
must state whenever you touch one:

- No per-side sample reaches them, so every such row also carries
  `ONE_SIDED_LADDER` and `NO_MARKET_MARGINAL` on the sheet.
- They carry 2–252 settled rows each across the whole history
  (`both_over_shots` 26, `both_over_fouls` 18), so no market-specific
  calibration curve can be fitted.
- CONFIDENCE refuses them outright (`DERIVED_NOT_CALIBRATABLE`), so they can
  never become a Bet Builder leg.
- They are computed from the two sides' correlation
  (`config/sofa_side_correlations.json`), and the measured correlation between
  the two teams' corners is **r = −0.279** — a negative number, which is not
  what "both over" intuition assumes.

## How each metric is actually produced

| metric | source | trap |
|---|---|---|
| `goals_*` | the score / incidents | includes extra time only if the event's status says so (`EXTRA_TIME_STATUS_CODES = {110, 120}`). Superbet's "(z dogrywką)" markets and the 90-minute ones are different questions. |
| `corners_*` | `/statistics`, per period | |
| `cards_points_*` | `/incidents/`, **not** `/statistics` | **Booking points, not cards.** Yellow 1, straight red 2, second yellow 3 — the way Superbet settles *Liczba kartek*. A yellow-only count reads 7/7/4 where the real figure is 10/9/4. Rescinded cards appear in incidents and are handled. |
| `fouls_*`, `offsides_*` | `/statistics` | |
| `shots_*` | `/statistics` | the raw field `totalShotsOnGoal` is **all shots**, not shots on target, despite its name. |
| `shots_on_target_*` | `/statistics` | |
| `xg_*` | `/statistics` | absent for most competitions. Do not read an absent xG as zero. |

`check_halves_identity` verifies that the halves sum to the full match where
both are present; a failure is `INTERNAL_INCONSISTENT` in `gaps[]`.

## Per-fixture context (`02_fixtures.json`)

| field | coverage | what it buys you |
|---|---|---|
| `competition_name`, `category_name`, `competition_id`, `season_id` | full | tier, country. The **first** place a competition is named at all — Superbet's board sends only ids. |
| `round_number`, `round_name`, `cup_round_type` | good | league round vs knockout round |
| `previous_leg_event_id` | when Sofascore linked it | tells you it *is* a second leg. **Not the aggregate** — read the first leg. |
| `venue_name` | mostly | |
| `referee` (`RefereeRecord`: `name`, `games`, `yellow_cards`, `red_cards`, `yellow_red_cards`) | **~9%** — announced late | a per-match rate, nothing more, and **not blended into the centre in `sofa`** |
| `ground_type` | tennis only in practice | |
| `default_period_count` | full | for football it is the number of halves and says nothing useful. Its old name `best_of` said something untrue about every football fixture. |
| `identity` | full | `CONFIRMED` or `FUZZY`. A `FUZZY` fixture may be the wrong match. |

## What is NOT in the artifacts, at all

You cannot read these anywhere in `runs/sofa/<date>/`. Every one of them is a
`CONTEXT` veto opening and must be sourced and tagged:

- league table, points, position, dead rubber, relegation or promotion stakes
- the aggregate score of a first leg
- squad availability, suspensions, injuries, a rested XI
- manager identity or a manager change inside the sample window
- weather, pitch condition
- a 1X2 price or any bookmaker consensus
- whether a fixture is a derby
- expected minutes for anything player-level (and `sofa` prices no player props
  for football at all)

## Sample construction

`sample_n = 10`, `min_sample = 5`. Pages are read **descending** — they were
read ascending once, which made "the last ten matches" mean the ten oldest and
put median sample freshness at 154 days instead of 5.

Per metric you get three buckets: `side_a`, `side_b`, `h2h`. Each observation
carries `sofascore_event_id`, `match_date_utc`, `opponent`, `value`,
`competition_id`, `season_id`, `venue`.

**`h2h` never reaches a per-team market.** `*_for` gets zero h2h observations
by design — a head-to-head is a fact about a pairing, and a `_for` row is a
claim about one side.

## Where the centre comes from

```
w_c    = n / (n + 25)                     K_CENTRE for football, FITTED
centre = w_c·sample_mean + (1 − w_c)·prior
```

`prior` is the competition's own baseline from
`config/sofa_league_baselines.json`, else the global one. Football counts then
go through a **negative binomial** around that centre — overdispersion is in
the model, which is why `p_central` does not equal the sample hit rate for
football and should not.

At n=10 the league prior owns **71%** of the centre. On half-match markets say
so explicitly: those baselines are fitted on a smaller and different population
than the full-match ones (the goals halves are internally inconsistent by −13%
and −17%, reported by `half_match_coherence` and not yet equalised), and a
stale baselines file shipped corners priors 24–32% too high for two days.

## Measured, and worth carrying

- `corners_2h_*` has **62 matches** in the entire settled history.
- Only **52.4%** of ladders can be checked at all.
- First halves carry ~45% of goals, not 50%.
- A team's goals and the match total are one quantity counted twice: measured
  lambda **2.165** over 84 rung pairs, up to 8.37. Across different quantities
  lambda sits in 0.95–1.02 and the product is right.
