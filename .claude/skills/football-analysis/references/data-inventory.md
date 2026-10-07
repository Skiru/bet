# Football data inventory — exactly what `sofa` measures, and what it does not

> **Since 2026-10-07 10:55Z (`epochs.LINE_EVIDENCE_FROM_UTC`)** the refusals BY NAME below (`DERIVED_NOT_CALIBRATABLE`, `OPERATOR_REFUSED` / `refused_markets`, `PLAYER_PROP_NOT_ADMITTED`, `TENNIS_SET_MARKET_NOT_ADMITTED`, a sport key outside `admitted`) describe the old epoch only: every market is now read through its own settled Superbet lines (`bet.sofa.line_evidence`), and one with no measurement is `NO_LINE_EVIDENCE`. See `.claude/skills/sofa-pipeline/SKILL.md`, "Line evidence and the 2026-10-07 changes".

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
saves_total          saves_for          (goalkeeperSaves)
throw_ins_total      throw_ins_for
goal_kicks_total     goal_kicks_for
tackles_total        tackles_for        (totalTackle; no halves)
```

Per half (`/statistics` has always been keyed by period; these were unmapped
until 2026-09-18):

```
goals_1h_*  goals_2h_*
corners_1h_* corners_2h_*
fouls_1h_*  fouls_2h_*
shots_1h_*  shots_2h_*
shots_on_target_1h_*  shots_on_target_2h_*
offsides_1h_*  offsides_2h_*
saves_1h_*
throw_ins_1h_*  throw_ins_2h_*
goal_kicks_1h_*  goal_kicks_2h_*
```

`_total` is the match; `_for` is one side, and `subject` names which. A
`period_complement` exists so a second half can be derived as full minus
first where Sofascore reports only one. Football player props (shots, shots on
target, assists, fouls, tackles, interceptions, offsides) live on their own
axis, `players` in `03_samples.json`, see the market playbook.

**Untracked zeros.** A 0-0 on throw-ins, tackles, goal kicks, and on corners,
fouls, shots and shots on target in a partial Sofascore feed (no `passes`
field) is the provider not counting, not a fact; such a match is a gap for the
metric, not an observation of 0 (`metrics.ZERO_MEANS_UNTRACKED`,
`NEED_FULL_FEED`; a partial feed's corner total of exactly 1 is refused too).
An absent observation in a sample is therefore not "the team had none".

**There is no `*_against` metric.** If you want "what the opponent concedes",
you must read the opponent's own `*_for` and say you are using a proxy.

## Derived markets (`src/bet/sofa/derived.py`) — priced, not sampled

```
both_over_<metric>    "Każda z drużyn powyżej 3.5 rz. rożnych"; both_over_goals at 0.5 = "Obie drużyny strzelą"
most_<metric>         "Najwięcej kartek", "Liczba rzutów rożnych - H2H"
handicap_<metric>     "Rzuty rożne handicap"
```
Football rungs on the 2026-10-07 offer: `both_over_` goals, corners, cards points,
fouls, offsides, shots, shots on target; `most_` corners (full match and halves),
cards points, shots, shots on target; `handicap_corners`.

These are **functions of two sides**, not counts of one thing. Consequences you
must state whenever you touch one:

- No observation of the joint exists in `03_samples.json` (its `metrics` hold
  only the `*_total` / `*_for` keys), so the sample gates have nothing to read.
- The sheet notes say how far the market checked the row: `DERIVED` (with the
  `rho` used), `NO_MARKET_MARGINAL` where Superbet's per-side ladders are not
  quoted at that line (292 of 702 derived football rows on 2026-10-07),
  `ONE_SIDED_LADDER` (168), `MARKET_MARGINAL_JOINT` (248), `MARGINAL_DISAGREEMENT`
  (3), `NO_MARKET_MARGINAL_CHECK` (13).
- They have no history curve: `epochs.DERIVED_CURVES_FROM_UTC` is `None` (the
  replayed football goals joints are not in the 2026-10-07 refit), and
  `DERIVED_NOT_CALIBRATABLE` is gone since 2026-10-07 10:55Z. Confidence reads
  only the key's own settled Superbet lines (`sofa_superbet_line_evidence.json`
  holds 20 football derived keys of 9 to 254 settled lines each in all, and a p
  bucket needs >= 50 lines from >= 15 games) or is `NO_LINE_EVIDENCE`.
- They are computed from the two sides' marginals and their correlation
  (`config/sofa_side_correlations.json`, residual correlation, `_min_pairs`
  200): corners **r = −0.145** (raw −0.198), goals −0.012, shots −0.093,
  fouls +0.044; cards points has none (`rho` UNMEASURED, independent). A
  negative number for corners is not what "both over" intuition assumes.
- From 2026-10-07 14:05Z the goals, corners, shots-on-target and cards joints
  are built from the marginal rows' centres (`epochs.
  DERIVED_MARGINAL_CENTRES_FROM_UTC`, `derived.marginal_centred_stats`: the
  K_CENTRE shrink plus the rating, variance scaled with the centre and
  inflated by `1 + 1/n`); fouls, shots and offsides joints keep the raw sample
  mean and variance. The derived sheet row's `centre` field is the raw sample mean (2026-10-07
  both_over_goals row: `centre` = `sample_mean`), so it does not show which
  centre the joint used.

## How each metric is actually produced

| metric | source | trap |
|---|---|---|
| `goals_*` | the score / incidents | includes extra time only if the event's status says so (`EXTRA_TIME_STATUS_CODES = {110, 120}`). Superbet's "(z dogrywką)" markets and the 90-minute ones are different questions. |
| `corners_*` | `/statistics`, per period | |
| `cards_points_*` | `/incidents/`, **not** `/statistics` | **Booking points, not cards.** Yellow 1, straight red 2, second yellow 3 — the way Superbet settles *Liczba kartek*. A yellow-only count reads 7/7/4 where the real figure is 10/9/4. Rescinded cards appear in incidents and are handled; cards shown to the bench / coaching staff (`manager`, no `player`) are dropped, as Superbet's rules say. |
| `fouls_*`, `offsides_*` | `/statistics` | |
| `shots_*` | `/statistics` | the raw field `totalShotsOnGoal` is **all shots**, not shots on target, despite its name. |
| `shots_on_target_*` | `/statistics` | |
| `xg_*` | `/statistics` | absent for most competitions. Do not read an absent xG as zero. |
| `saves_*`, `throw_ins_*`, `goal_kicks_*`, `tackles_*` | `/statistics` (`goalkeeperSaves`, `throwIns`, `goalKicks`, `totalTackle`) | a 0 on throw-ins / goal kicks / tackles is often the provider not counting (`ZERO_MEANS_UNTRACKED`); the match is then a gap, not a 0. |

`check_halves_identity` verifies that the halves sum to the full match where
both are present; a failure is `INTERNAL_INCONSISTENT` in `gaps[]`.

## Per-fixture context (`02_fixtures.json`)

| field | coverage | what it buys you |
|---|---|---|
| `competition_name`, `category_name`, `competition_id`, `season_id` | full | tier, country. The **first** place a competition is named at all — Superbet's board sends only ids. |
| `round_number`, `round_name`, `cup_round_type` | good | league round vs knockout round |
| `previous_leg_event_id` | when Sofascore linked it | tells you it *is* a second leg. **Not the aggregate** — read the first leg. |
| `venue_name` | few (2026-10-07: 20 of 153) | |
| `referee` (`RefereeRecord`: `name`, `games`, `yellow_cards`, `red_cards`, `yellow_red_cards`) | **~9%** (2026-10-07: 14 of 153) — announced late | a per-match rate, nothing more, and **not blended into the centre in `sofa`** |
| `ground_type` | tennis only in practice | |
| `default_period_count` | full | for football it is the number of halves and says nothing useful. Its old name `best_of` said something untrue about every football fixture. |
| `identity` | full | `CONFIRMED` (team names equal after folding, `fuzz.ratio` >= 99) or `FUZZY` (matched by a looser name score and the kickoff window; 79 of 153 football fixtures on 2026-10-07). Never call a `FUZZY` fixture confirmed; compare the two sources' names. |
| `national_teams`, `sofascore_status`, `kickoff_disagreement_h`, `superbet_kickoff_utc` | full | two national sides are judged on sample count, not age; the two clocks |

## What is NOT in the artifacts, at all

You cannot read these anywhere in `runs/sofa/<date>/`. Every one of them is a
`CONTEXT` veto opening and must be sourced and tagged:

- league table, points, position, dead rubber, relegation or promotion stakes
- the aggregate score of a first leg
- squad availability, suspensions, injuries, a rested XI
- *why* a make-up fixture was postponed (the fact that it is one, and each
  side's rest and matches in 7 / 14 days, **are** on disk since 2026-10-04:
  the `schedule` block per fixture in `03_samples.json`, and
  `context_flags` on the legs)
- manager identity or a manager change inside the sample window
- weather, pitch condition
- a 1X2 price or any bookmaker consensus
- whether a fixture is a derby
- whether a player starts: a player row carries only his past minutes
  (`PLAYER_MINUTES` note), never tonight's lineup

## Sample construction

`sample_n = 10`, `min_sample = 5`. Pages are read **descending** — they were
read ascending once, which made "the last ten matches" mean the ten oldest and
put median sample freshness at 154 days instead of 5.

Per metric you get three buckets: `side_a`, `side_b`, `h2h`. Each observation
carries `sofascore_event_id`, `match_date_utc`, `opponent`, `value`,
`competition_id`, `season_id`, `venue`.

Friendlies and pre-season tournaments are excluded from every sample
(`bet.sofa.comparability`, since 2026-10-04; 79 `excluded` competition ids in
`config/sofa_friendly_competitions.json` at the 2026-10-07 refit). For a
LEAGUE fixture the goal metrics (`goals_total`, `goals_for`, `goals_1h_for`,
`goals_2h_for`) take the side's newest REGULAR (non-knockout) matches of the
fixture's own competition when it has at least five, else the usual newest
ten; a knockout fixture keeps the usual newest ten.

**`h2h` never reaches a per-team market.** `*_for` gets zero h2h observations
by design — a head-to-head is a fact about a pairing, and a `_for` row is a
claim about one side.

## Where the centre comes from

```
w_c    = n / (n + 15)                     K_CENTRE for football, FITTED
centre = w_c·sample_mean + (1 − w_c)·prior
centre = 0.5·rating + 0.5·centre          where the rating prices the market
```

`prior` is the competition's own baseline from
`config/sofa_league_baselines.json` (a pool of the fixture's teams' leagues,
else the global one; the row says which in a `PRIOR_*` note, `NO_PRIOR` when
there is none and the sample's mean stands). The rating (`FOOTBALL_RATING`
note) is the expected count from `football_rating`: league rate x home / away
ratio x own attack x opponent defence; it is not used on `corners_total`,
`corners_1h_*`, `corners_2h_*`, `cards_points_for`, `offsides_total`, nor on
saves, tackles, throw-ins, goal kicks or xG. Goals, `corners_for`,
`corners_1h_*`, full-match offsides and cards points then go through a
**negative binomial** around that centre; the other football metrics through a
normal CDF with a support floor (`engine.NEGATIVE_BINOMIAL_METRICS`). Either
way `p_central` does not equal the sample hit rate and should not.

At n=10 the league prior owns **60%** of the sample-side centre (and 30% of the
final centre where the rating also enters). On half-match markets say so
explicitly: those baselines are fitted on a smaller and different population
than the full-match ones (2,448 against 598,987 goals observations in the
2026-10-07 fit; `half_match_coherence` reads `OK` there, and read −13% / −17%
for the goals halves earlier), and a stale baselines file once shipped corners
priors 24–32% too high for two days.

## Measured, and worth carrying

- The `corners_2h_total` global baseline rests on **102** observations,
  `corners_1h_total` on 721 (`config/sofa_league_baselines.json`, 2026-10-07).
- First halves carry ~45% of goals, not 50%.
- A team's goals and the match total are one quantity counted twice: measured
  lambda **2.165** over 84 rung pairs, up to 8.37. Across different quantities
  lambda sits in 0.95–1.02 and the product is right.
