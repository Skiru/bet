# `vetoes.json` — the schema, the resolution rules, and the ways it goes wrong

## Schema (`Veto` in `src/bet/sofa/contracts.py`, `strict`, `extra="forbid"`)

| field | type | required | meaning |
|---|---|---|---|
| `sofascore_event_id` | int | yes | the fixture. An integer, not a hash. |
| `market` | str \| null | yes (may be null) | `null` = every market on that fixture |
| `subject` | str \| null | yes | `null` = every subject. `""` is *the match-level subject*, which is **not** the same as `null`. |
| `line` | float \| null | yes | `null` = every line |
| `direction` | `"OVER" \| "UNDER"` \| null | yes | `null` = both |
| `reason_class` | enum | yes | `SAMPLE_UNINFORMATIVE \| CONTEXT \| PRICE \| OTHER` |
| `reason` | str | yes | free text. The operator reads this; write it for them. |

All seven keys must be present (`sofascore_event_id`, `market`, `subject`,
`line`, `direction`, `reason_class`, `reason`) — including the ones you are
setting to `null`; an omitted key is a validation failure, not a default. `extra="forbid"` means an invented key
(`action`, `player`, `event_id`) fails validation and takes the whole file with
it — the stage then runs with **no** vetoes at all, and reports zero.

## Where it lives and who reads it

`runs/sofa/<date>/vetoes.json`, a bare array. Written **after SHEET and before
COUPON**. Read by:

- `scripts/sofa/run_coupon.py` → gates `06_coupon.json`, drop reason `VETOED`
- `scripts/sofa/run_confidence.py` → gates `08_confidence.json` and therefore
  the PDF, refusal reason `VETOED`

Both print `UNMATCHED_VETO: {...}` to stderr for an entry that matched no sheet
row, and both count `vetoes_applied` / `vetoes_unmatched` in their summary.

Until 2026-09-21 only the first of those read the file. A veto removed a row
from the singles — which are not the coupon — and left the identical rung
standing as a leg of the Bet Builder the PDF stakes. If you are reading an
artifact from before that date, a veto in it did not reach the product.

## Resolution — most general wins, and that is deliberate

A veto matches a row when **every non-null field** matches. So:

```json
{"sofascore_event_id": 15275920, "market": null, "subject": null,
 "line": null, "direction": null, ...}
```

covers every rung on that fixture. **This is the normal shape.** A sample that
does not describe the fixture is broken at every line, and a per-rung veto
would leave the other eleven rungs of the same broken sample standing.

Narrow only when the fault is genuinely rung-specific — a line sitting exactly
on the sample's mode, a direction the ladder cannot express.

There is **no** override mechanism: a narrow veto does not carve an exception
out of a broad one, because both simply match. Do not write a pair expecting
one to except the other.

## The widening trap

There is **no player field**. A per-player concern expressed as
`(event, market, line, direction)` with `subject: null` hits **every subject on
that fixture**. In the retired pipeline that inverted a day's picks: a veto
meant for one player removed all twenty.

`subject` in `sofa` is the side or player name as the sheet wrote it — e.g. a
team name for `goals_for`, a player name for `aces_for`, `""` for
`corners_total`. Before emitting a narrow veto, **count what it will hit**:

```bash
.venv/bin/python - <<'PY'
import json
rows = json.load(open("runs/sofa/<date>/05_sheet.json"))
hit = [r for r in rows
       if r["sofascore_event_id"] == 15275920
       and r["market"] == "aces_for"]
for r in hit:
    print(r["subject"], r["line"], r["direction"], r["verdict"])
PY
```

If the set is larger than you intended, do **not** emit it. Write it as a
manual WATCH in prose and say it was not applied.

## `reason_class` — pick the one that names the fault

| class | use when | example |
|---|---|---|
| `SAMPLE_UNINFORMATIVE` | the observations do not measure this fixture: wrong squad, wrong surface, wrong format, opponents nothing like today's, all on one side of a line it has never approached | "nine of ten matches are second-tier; today is a cup tie against a top-flight side" |
| `CONTEXT` | the sample is fine and the world has changed: dead rubber, second leg with the tie decided, four starters out, a derby the referee will call differently | "aggregate 4-0 from the first leg; both managers have named reserve XIs" |
| `PRICE` | the rung is unbettable as priced: one-sided ladder, price older than it looks, a rung that exists on our sheet and not on the screen | "the OVER side is not quoted; `market_p` is null and the bar is unanchored" |
| `OTHER` | what the list cannot express. Say why in `reason`. | |

`reason_class` is recorded and read; it does **not** change the arithmetic.
Every class removes the row outright. There is no downgrade in `sofa` — the
retired pipeline had tiers and this one does not.

## What a veto may never be

- **A promotion.** Nothing in `sofa` can raise a row. If your read is that a
  row is *better* than the sheet says, that belongs in prose, and the honest
  framing is that the pipeline does not support acting on it.
- **A price opinion on a market nobody quoted.** That is not a bet.
- **A hedge.** "Slightly thin" is a caveat, and caveats go in the report. A
  veto removes a row from the operator's coupon; write it only when you would
  strike the row.
- **A duplicate of a gate the code already applies.** `STALE_PRICE`,
  `STALE_SAMPLE`, `ODDS_TOO_LOW`, `KICKOFF_TOO_SOON`, `MODE_LOSES`,
  `LINE_BEYOND_SAMPLE`, `THIN_SAMPLE_FOR_BUILDER` are enforced in code. Vetoing
  for one of those adds nothing and hides your real reasons in noise.

## Validating before you hand it over

```bash
.venv/bin/python - <<'PY'
import json, sys
sys.path.insert(0, "src")
from pydantic import RootModel
from bet.sofa.contracts import SheetRow, Veto
from bet.sofa.veto import find_unmatched_vetoes

date = "<date>"
vetoes = RootModel[list[Veto]].model_validate_json(
    open(f"runs/sofa/{date}/vetoes.json").read())
rows = RootModel[list[SheetRow]].model_validate_json(
    open(f"runs/sofa/{date}/05_sheet.json").read())
unmatched = find_unmatched_vetoes(rows.root, vetoes.root)
print(f"{len(vetoes.root)} vetoes, {len(unmatched)} match nothing")
for v in unmatched:
    print("  UNMATCHED:", v.model_dump_json())
PY
```

A validation error here is cheap. The same error at COUPON time silently
discards the whole file.
