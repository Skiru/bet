# Football data inventory - what `sofa` measures, and what it does not

Everything comes from **Sofascore only**: no second statistics provider, no
consensus, no agreement flag. Say so once in the header.

## Metrics (`FOOTBALL_METRICS` in `src/bet/sofa/metrics.py`)

Full match, `_total` (the match) and `_for` (one side, named by `subject`):
goals, corners, cards points, fouls, offsides, shots, shots on target, xG,
saves (`goalkeeperSaves`), throw-ins, goal kicks, tackles (`totalTackle`, no
halves). Per half (`_1h_` / `_2h_`): goals, corners, fouls, shots, shots on
target, offsides, throw-ins, goal kicks, and saves first half. A second half
may be derived as full minus first where Sofascore reports one half only;
`check_halves_identity` flags halves that do not sum (`INTERNAL_INCONSISTENT`
in `gaps[]`).

Footballer markets live on their own axis, `players` in `03_samples.json`
(see the market playbook). Score and rating-only markets (double chance,
1X2, DNB, first goal, reds, penalties, the score markets) have no sample.

**Untracked zeros.** A 0 on throw-ins, tackles, goal kicks - and on corners,
fouls, shots, shots on target in a partial feed (no `passes` field) - is the
provider not counting: the match is a gap for that metric, not an observation
of 0 (`metrics.ZERO_MEANS_UNTRACKED`, `NEED_FULL_FEED`; a partial feed's
corner total of exactly 1 is refused too).

**Conceded values.** Every `_for` observation carries `against` - the
opponent's value of the same metric in that match - and `opponent_id`. Tonight's opponent's `against` values are what it
concedes; compare them with this side's `value`s, raw (not opponent-adjusted).

## How each metric is produced

| metric | source | trap |
|---|---|---|
| `goals_*` | score / incidents | settled at 90 minutes (`normaltime`); when SETTLING, after extra time the other counts stay `EVENT_NOT_FINISHED` and a match decided on penalties with no extra time is graded on its whole-match counts; samples and ratings skip both kinds of match. Superbet's "(z dogrywką)" markets are a different question |
| `corners_*` | `/statistics`, per period | |
| `cards_points_*` | `/incidents/` | **booking points, not cards**: yellow 1, straight red 2, second yellow 3 (how Superbet settles "Liczba kartek"). Rescinded cards handled; staff cards and cards to a player on the bench are dropped when settling (`metrics.drop_bench_cards`) - samples keep every card |
| `fouls_*`, `offsides_*` | `/statistics` | |
| `shots_*` | `/statistics` | the raw field `totalShotsOnGoal` is **all shots** |
| `shots_on_target_*` | `/statistics` | |
| `xg_*` | `/statistics` | absent for most competitions - never read absent as 0; Superbet does not price it |
| `saves_*`, `throw_ins_*`, `goal_kicks_*`, `tackles_*` | `/statistics` | zeros often untracked (above) |

## Per-fixture context (`02_fixtures.json`)

| field | coverage | what it buys you |
|---|---|---|
| `competition_name`, `category_name`, `competition_id`, `season_id` | full | tier, country |
| `round_number`, `round_name`, `cup_round_type` | good | league round vs knockout |
| `previous_leg_event_id` | when Sofascore linked it | it *is* a second leg - not the aggregate |
| `venue_name` | few | |
| `referee` (`RefereeRecord`: `name`, `games`, `yellow_cards`, `red_cards`, `yellow_red_cards`) | small minority, announced late | a rate, not in the centre |
| `default_period_count` | full | the number of halves - says nothing |
| `identity` | full | `CONFIRMED` or `FUZZY` - never call `FUZZY` confirmed |
| `national_teams`, `sofascore_status`, `kickoff_disagreement_h`, `superbet_kickoff_utc` | full | two national sides are judged on count, not age; the clocks |

## Not in the artifacts at all

Each is a CONTEXT opening - source it and tag it:

- league table, points, dead rubber, relegation or promotion stakes (beyond
  the `stakes` flag);
- the first leg's score;
- availability, suspensions, injuries, a rested XI;
- *why* a make-up fixture was postponed (that it is one, and each side's rest
  and load, **are** on disk: `schedule`, `context_flags`);
- the manager, or a change inside the sample window;
- weather, pitch;
- whether a match is a derby;
- whether a player starts tonight (his row carries only past minutes).

## Sample construction

`sample_n = 10`, `min_sample = 5`, pages read **descending** (newest first).
Three buckets per metric: `side_a`, `side_b`, `h2h`; each observation carries
`sofascore_event_id`, `match_date_utc`, `opponent`, `opponent_id`, `value`,
`competition_id`, `season_id`, `venue`, `minutes`.

- Friendlies and pre-season tournaments are excluded everywhere
  (`bet.sofa.comparability`; `config/sofa_friendly_competitions.json`
  `excluded`, 852 women's friendlies allowed); an 851 men's friendly fixture
  admits the sides' 851 matches.
- A LEAGUE fixture's goal markets read the side's newest REGULAR matches of
  the same competition when there are five or more; a knockout fixture keeps
  the newest ten.
- **`h2h` never reaches a `*_for` row** - a pairing fact is not a claim about
  one side. A `*_total` pools `side_a + side_b + h2h`, deduplicated, with no
  age rule of its own.
- A sheet row carrying `opponent_rule` was centred on the side's sample
  rescaled to a neutral opponent and today's league (`corrected_sample` on
  the row; goals and players excluded); the shape gates read those values,
  not the raw observations.

## Where the centre comes from

```
w_c    = n / (n + K)                         K = 15; per market by_market.football (k_rule)
centre = w_c * sample_mean + (1 - w_c) * prior
centre = w * rating + (1 - w) * centre       rated markets; w from config/sofa_rating_weight.json
```

`prior` is the competition's baseline (`config/sofa_league_baselines.json`);
the row's `PRIOR_*` note says when it came from the day's samples, the sides'
leagues or nothing (`NO_PRIOR`). The rating (`FOOTBALL_RATING` note) is league
rate x home / away ratio x own attack x opponent defence. Unrated:
`corners_total`, `corners_1h_total`, `corners_2h_total`, saves, tackles,
throw-ins, goal kicks, xG. The count is then priced through a negative
binomial with a fitted dispersion (`shots_total` a normal), so `p_central`
does not equal the sample hit rate and should not.

## Measured, and worth carrying

- First halves carry ~45% of goals, not 50%; the half baselines rest on far
  smaller populations than the full-match ones.
- A team's goals and the match total are one quantity counted twice
  (measured lambda 2.165 over 84 rung pairs); across different quantities
  lambda sits at 0.95-1.02 and the product is about right.
