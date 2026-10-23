# Evidence rules - what the artifacts can and cannot tell you

Read this when you grade a football / tennis sample, or before you write a
veto (the "already enforced" table). Which model packages and switches are
on: `.claude/skills/sofa-pipeline/references/model-state.md`.

## The sample is in `03_samples.json`, not in the sheet

The sheet row carries `sample_size`, `sample_mean`, `sample_sd` - a summary
that hides the three commonest faults:

- **every observation on one side of a line the sample never approached** -
  20/20 that could not have said anything else;
- **the modal outcome losing the bet** - a mean above the line whose most
  frequent value is below it;
- **a discontinuity inside the sample** - a manager change, a transfer window,
  a surface change, a return from injury.

Per metric: `metrics[<metric>].side_a / side_b / h2h`, each observation with
`sofascore_event_id`, `match_date_utc`, `opponent`, `opponent_id`, `value`,
`competition_id`, `season_id`, `venue`, `minutes`, and on every `_for` metric
`against` (the opponent's value of the same metric in that match; null on a
total or a player metric). Footballer markets live in
`players["<market>|<player>"]` (`matched_name`, `match_rule`, `side`,
`appearances`, `squad_matches`, `observations`). Summarise one metric of one
match without dumping the file:

```bash
jq -c --argjson id <id> '.[]|select(.sofascore_event_id==$id)|.metrics["<metric>"]|to_entries[]|select(.key!="metric")|[.key,(.value|map([.match_date_utc[:10],.opponent,.opponent_id,.competition_id,.venue,.value]))]' runs/sofa/<d>/03_samples.json
```

The sample's opponents carry only a name, `opponent_id` and `competition_id` -
no ranking, tier or strength offline. Opponent class beyond the competition is
`UNVERIFIED` without the web.

Read `gaps[]` too: every absence has a named reason (`EVENT_NOT_FINISHED`,
`SURFACE_UNKNOWN`, `ENTITY_CONFLICT`, ...). A placeholder result (a 0-0 with
no statistics, incidents or lineups - a forfeit) inside a goals sample is a
defect to report.

Friendlies and pre-season tournaments are out of every sample and rating
(`bet.sofa.comparability`; `config/sofa_friendly_competitions.json`
`excluded`; an 851 men's friendly fixture admits the sides' own 851 matches).
For a football LEAGUE fixture the goal markets (`goals_total`, `goals_for`,
`goals_1h_for`, `goals_2h_for`) sample only the side's REGULAR matches of the
fixture's own competition when it has five or more
(`comparability.pick_same_competition`), so a cup or friendly observation
there is a defect; a knockout fixture keeps the newest ten, cups included.

## How much of the centre is the sample

```
w_c = n / (n + K)    K = K_CENTRE in config/sofa_engine_constants.json:
                     football 15 (per market: by_market.football, the row's k_rule), tennis 8
```

Football then mixes the rating in: `centre = w x rating + (1 - w) x shrunk
sample`, with `w` per market from `config/sofa_rating_weight.json` (else
0.5); the row's `FOOTBALL_RATING` note prints the rating's centre, `W=` and
the sample centre it replaced. Further centre terms (game state, season
phase, opponent correction, supremacy stretches) each leave a note or a
`*_rule` marker on the row - read them, do not re-derive them. State `w_c`
for any row you grade, twice for a `*_1h_*` / `*_2h_*` row (the half
baselines are fitted on a smaller population).

Where the football prior came from is on the row: no note = the fitted
league entry; `PRIOR_FROM_DAY_SAMPLES`; `PRIOR_FROM_TEAMS_LEAGUES` (a cup tie
on its sides' leagues); `NO_PRIOR`; `PRIOR_GLOBAL` / `PRIOR_GLOBAL_WOMEN`
(no fitted baseline: the global pool of every league) - say so, because it
owns most of a thin row's centre.

A `_total` row exists only when both sides have `min_sample` own
observations; one side's history is refused as `THIN_SAMPLE`. A player sample
carrying a `THIN_SAMPLE` gap with detail `PLAYER_HISTORY_ANY_TEAM` was topped up
and is used. An `ENTITY_CONFLICT` gap with "sample cut at the clash" is a kept
sample, not an absence.

## Context in `02_fixtures.json`

| field | what it lets you say | limits |
|---|---|---|
| `competition_name`, `category_name`, `competition_id`, `season_id` | which competition, which tier | |
| `round_number`, `round_name`, `cup_round_type` | knockout vs league, which round | often null for tennis |
| `previous_leg_event_id` | this is a second leg | not the aggregate |
| `referee` (`RefereeRecord`: `name`, `games`, yellow / red / second-yellow counts) | the official's rate | filled on a small minority of fixtures; absence is the default |
| `venue_name` | home / away / neutral | few fixtures |
| `ground_type` | tennis surface | null at the thin end of the calendar |
| `default_period_count` | tennis best-of (3 or 5) | for football the number of halves - says nothing |
| `identity` | `CONFIRMED` or `FUZZY` (names differ beyond a folded exact match - compare them) | never call `FUZZY` confirmed |
| `kickoff_utc`, `superbet_kickoff_utc`, `kickoff_disagreement_h` | the decision point | |

## The clocks

`kickoff_utc` is Sofascore's, `superbet_kickoff_utc` Superbet's; on ITF tennis
they disagree by up to 11 h and the error makes a finished match look
upcoming. The code gates on the earliest of RESOLVE's clock, Superbet's start
signal (`04_offer.json` `superbet_started_utc`, `superbet_kickoff_seen_utc`)
and FIXTURE_CHECK's fresh start (`fixture_status.json`). Take the earlier for
your decision point; quote both when they differ by more than an hour.

## What the pipeline does not know, and you might

None of these is in the artifacts; each is a CONTEXT opening:

- what is at stake beyond the `stakes` flag - a dead rubber, a decided tie,
  a play-off;
- a second leg's aggregate score;
- absences, suspensions, a rested XI;
- a manager change inside the sample window;
- weather, pitch, altitude;
- a tennis player's withdrawal or walkover announced before the start;
- whether a match is a derby;
- *why* a make-up fixture was postponed and whether the cause still holds.

## Already enforced - never veto or WATCH for these

| gate | refusal |
|---|---|
| price older than 45 min (football / tennis), 3 h (sports) | `STALE_PRICE`, `NO_FETCHED_AT` |
| started on the earliest clock, or within 15 min of it | `KICKED_OFF` |
| printed match postponed / cancelled per FIXTURE_CHECK | `FIXTURE_NOT_AS_SCHEDULED` |
| newest observation older than 60 days / oldest older than 180 (national teams by count) | `STALE_SAMPLE` / `SAMPLE_CROSSES_SEASON` |
| odds below 1.0867 | `ODDS_TOO_LOW` |
| x = confidence x odds below 0.90 | `NEGATIVE_LEG_EV` (sports `BELOW_MIN_X`) |
| confidence below 0.70 | `BELOW_CONFIDENCE_FLOOR` (sports `BELOW_FLOOR`) |
| ladder margin above 15% | not printed as a single (the leg's `overround`; sports `MARGIN_TOO_HIGH`) |
| line outside everything the sample has seen; modal outcome loses; fewer than 10 observations | `LINE_BEYOND_SAMPLE`, `MODE_LOSES`, `THIN_SAMPLE_FOR_BUILDER` - except a football player leg on `confidence.PLAYER_SHAPE_GATE_MARKETS`, which needs 5 starts and skips the first two; it carries `player_sample_rule` and its shape is yours to judge |
| football `model_p` more than 0.15 above the own sample's hit rate (n >= 5, props excluded) | `MODEL_ABOVE_OWN_SAMPLE` (automatic WATCH into `removed_by_reads`) |
| no curve at p and too few own Superbet lines | `NO_LINE_EVIDENCE` |
| no usable curve | `NOT_CALIBRATED` |
| two football leagues the rating cannot link | `CROSS_LEAGUE_UNLINKED` |
| women's / team-cup class without its class curve | `NO_CLASS_CURVE` |
| (competition, family) that does not settle | `NOT_SETTLEABLE` |
| builder legs disagreeing about tempo | `BUILDER_LEGS_INCOHERENT` |
| sport leg: identity not pinned, no model p, CS2 team-rounds line outside 9.5-12.5 | `NOT_IDENTIFIED` / `DUPLICATE_*`, `NO_MODEL_P`, `LINE_OUTSIDE_FIT` |

The day's counts per refusal are in the CONFIDENCE `SOFA_SUMMARY` line of
the latest `runs/sofa/<d>/rebuild_*.log` (`metrics.refused`) - counts, not
rows. Your value is in what these cannot see.

## One provider, no corroboration

`sofa` has one statistics provider: no cross-provider agreement exists. Say
so once in the header; never present a row as corroborated. Never fetch odds
from the web or another book; a live re-quote of Superbet goes through the
pipeline's own `OfferFetcher` (`sofa-market-scout`'s job, not yours).
