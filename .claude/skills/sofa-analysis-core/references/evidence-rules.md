# Evidence rules — what the artifacts can and cannot tell you

## The sample is in `03_samples.json`, not in the sheet

The sheet carries `sample_size`, `sample_mean`, `sample_sd`. That is a summary,
and three of the most common faults are invisible in it:

- **every observation on the same side of a line the sample has never
  approached.** 20/20 that says nothing, because it could not have said
  anything else. (`line_is_beyond_sample` catches the extreme case for builder
  legs; it does not gate singles.)
- **the modal outcome losing the bet.** A mean comfortably above the line whose
  single most frequent value is below it.
- **the sample spanning a discontinuity** — a manager change, a transfer
  window, a surface change, a return from injury.

So open the observations. Per metric you get `side_a[]`, `side_b[]`, `h2h[]`,
each observation carrying `sofascore_event_id`, `match_date_utc`, `opponent`,
`value`, `competition_id`, `season_id`, `venue`.

```bash
.venv/bin/python - <<'PY'
import json, statistics
d = "runs/sofa/<date>/"
s = {x["sofascore_event_id"]: x for x in json.load(open(d + "03_samples.json"))}
m = s[15275920]["metrics"]["corners_total"]
for side in ("side_a", "side_b", "h2h"):
    vals = [o["value"] for o in m[side]]
    if not vals:
        continue
    print(side, "n=%d" % len(vals), "mean=%.2f" % statistics.mean(vals),
          "mode=%s" % statistics.mode(vals), "range=%s-%s" % (min(vals), max(vals)))
    for o in sorted(m[side], key=lambda o: o["match_date_utc"], reverse=True):
        print("   ", o["match_date_utc"][:10], o["opponent"], o["venue"], o["value"])
PY
```

Also read `gaps[]`. Every absence has a named `GapReason`; if you cannot find
why a metric is missing, you are reading the wrong file, not looking at a
silent drop.

## How much of the centre is the sample, and how much is the league

```
w_c = n / (n + K_CENTRE)      football K_CENTRE = 25, tennis 2
```

At n=10 a football row's centre is **29%** its own sample and 71% the league
baseline. At n=8 it is 24%. State this number for any row you grade, and
always for a `*_1h_*` / `*_2h_*` row — the half-match baselines are fitted on a
smaller, different population than the full-match ones, and a stale baselines
file has already shipped corners priors 24–32% too high for two days.

Tennis at `K_CENTRE = 2` is nearly all sample, which is why tennis
`p_central` equals the sample's own hit rate.

## Context available in `02_fixtures.json`

| field | what it lets you say | limits |
|---|---|---|
| `competition_name`, `category_name`, `season_id` | which competition, which tier | absent before RESOLVE; Superbet sends no name at all |
| `round_number`, `round_name`, `cup_round_type` | knockout vs league, which round | |
| `previous_leg_event_id` | **this is a second leg** | present only when Sofascore linked it |
| `referee` (`RefereeRecord`) | name, games, yellows, reds, second yellows | **filled for ~9% of fixtures** — announced late. Absence is the default, not a gap to chase. |
| `venue_name` | home/away/neutral questions | |
| `ground_type` | tennis surface | |
| `default_period_count` | tennis: the real best-of (3 or 5) | football: the number of halves. It says nothing useful about a football fixture. |
| `identity` | `CONFIRMED` or `FUZZY` | a `FUZZY` fixture may be the wrong match entirely. Never present one as confirmed. |
| `kickoff_utc` + `superbet_kickoff_utc` + `kickoff_disagreement_h` | the decision point | see below |

## The two clocks

`kickoff_utc` is Sofascore's, `superbet_kickoff_utc` is Superbet's. For ITF
tennis they disagree by up to 11 h, and the error runs the wrong way: **a
finished match looks upcoming** on Sofascore's clock. COUPON takes the
earlier of the two; CONFIDENCE reads Sofascore's.

For your own decision point, take the **earlier**. Quote both when they
disagree by more than an hour, and say so.

## What the pipeline does NOT know, and you might

These are the openings for a `CONTEXT` veto. None of them is anywhere in the
artifacts:

- what is at stake — a dead rubber, a decided tie, a promotion play-off
- a second leg's aggregate score (the link is there, the score is not)
- announced absences, suspensions, a rested XI in a cup tie
- a manager change inside the sample window
- weather, a waterlogged pitch, altitude
- a tennis player's retirement mid-event, a walkover, a late withdrawal
- whether a derby is a derby

## What the pipeline knows better than you

Do not re-derive these, and do not veto for them — the gate already fired:

| already enforced | where |
|---|---|
| price older than 45 min | COUPON `STALE_PRICE`, CONFIDENCE `STALE_PRICE` |
| newest observation older than 60 days | COUPON `STALE_SAMPLE` |
| kickoff less than 15 min out, on the earlier clock | COUPON `KICKOFF_TOO_SOON` |
| odds below 1.25 (singles) / 1.0867 (legs) | `ODDS_TOO_LOW` |
| line outside everything the sample has seen | CONFIDENCE `LINE_BEYOND_SAMPLE` |
| `p_central` at or above this market's own measured calibration ceiling | COUPON `ABOVE_MEASURED_CEILING`, CONFIDENCE `NOT_CALIBRATED` |
| a second row of the same mechanism family on one fixture | COUPON `FAMILY_SLOT_TAKEN` |
| modal outcome loses | CONFIDENCE `MODE_LOSES` |
| fewer than 10 observations for a builder leg | `THIN_SAMPLE_FOR_BUILDER` |
| oldest observation past 180 days for a builder leg | `SAMPLE_CROSSES_SEASON` |
| model more than 0.10 above the devigged price | `DISAGREES_WITH_PRICE` |
| a joint/comparative market has no calibration | `DERIVED_NOT_CALIBRATABLE` |
| a builder mixing `goals UNDER` with `corners OVER` | `BUILDER_LEGS_INCOHERENT` |

Your value is in what these cannot see.

## Corroboration and sources

`sofa` has **one** statistics provider. There is no cross-provider agreement
field, no second opinion inside the artifacts, and no `SINGLE_SOURCE` flag —
because every row is single-source. Say so once in the header; do not present
any row as corroborated.

External verification, when you do it:

- **Football:** bzzoiro MCP is an independent source of record and is by-id.
  It is *not* what `sofa` samples from, so it can confirm a fixture's status,
  kickoff and lineup without contaminating the model. Tag
  `[BZZOIRO-MCP: <tool>, fetched <UTC>]`. On a live day anything but
  `notstarted` is a veto.
- **Tennis:** there is no MCP source. `bzzoiro-tennis` answers
  `402 addon_required`. Verification is WebFetch against the tournament's
  official order of play plus one independent domain, tagged
  `[WEB: domain, fetched <UTC>]`; one domain alone is "unconfirmed". Game-level
  ITF statistics are not available free — say **unverified** rather than
  manufacturing a source.
- Never fetch odds off the open web. bzzoiro's `compare_odds` / `get_best_odds`
  span ~88 books, **none of which is Superbet**; they are a reference, not a
  price. Tag `[BZZOIRO-ODDS: fetched <ts>]`.
- If a tool returns `requires re-authorization`, stop retrying and list the
  checks you therefore did not make. Silence about a skipped check reads as a
  passed check.
