# `vetoes.json` and `reads.json` — the schemas, the resolution rules, and the ways they go wrong

## Schema (`Veto` in `src/bet/sofa/contracts.py`, `strict`, `extra="forbid"`)

| field | type | required | meaning |
|---|---|---|---|
| `sofascore_event_id` | int | yes | the fixture. An integer, not a hash. |
| `market` | str \| null | yes (may be null) | `null` = every market on that fixture |
| `subject` | str \| null | yes | `null` = every subject. `""` is *the match-level subject*, which is **not** the same as `null`. |
| `line` | float \| null | yes | `null` = every line |
| `direction` | `"OVER" \| "UNDER"` \| null | yes | `null` = both. A veto has no other side and no period, so a measured-sport leg (`T1`, `ODD`, a set, a map) takes a read, not a veto - see *`reads.json`* below |
| `reason_class` | enum | yes | `SAMPLE_UNINFORMATIVE \| CONTEXT \| PRICE \| OTHER` |
| `reason` | str | yes | free text. The operator reads this; write it for them. |
| `context` | enum \| null | no (defaults to null) | **only with `reason_class: "CONTEXT"`**, and then always set: `MOTIVATION \| ROTATION \| ABSENCES \| DERBY \| SCHEDULE \| CONDITIONS`. Any other class with a `context` fails validation. |

All seven required keys must be present (`sofascore_event_id`, `market`, `subject`,
`line`, `direction`, `reason_class`, `reason`) — including the ones you are
setting to `null`; an omitted key is a validation failure, not a default. `extra="forbid"` means an invented key
(`action`, `player`, `event_id`) fails validation and takes the whole file with
it — and the run stops: COUPON raises (`run_pipeline.py` reports it FAILED,
exit 2) and `run_confidence.py` dies on an uncaught `ValidationError` with
exit 1, which reads as PARTIAL unless the traceback is read. Neither rewrites
its artifact, so the previous build stays on disk looking current.

## Where it lives and who reads it

`runs/sofa/<date>/vetoes.json`, a bare array. Written **after SHEET and before
COUPON**. Read by:

- `scripts/sofa/run_coupon.py` → gates `06_coupon.json` (the old VALUE
  selector, not the coupon), drop reason `VETOED`
- `scripts/sofa/run_confidence.py` → gates `08_confidence.json`, refusal
  reason `VETOED`
- `scripts/sofa/build_coupon.py` (COUPON_ASSEMBLY) → applies the vetoes to
  the measured-sport legs of `08_confidence_sports.json` as it assembles
  `11_coupon.json`, and therefore the PDF

The first two print `UNMATCHED_VETO: {...}` to stderr for an entry that
matched no sheet row, and count `vetoes_applied` / `vetoes_unmatched` in
their summary. A sport veto shows there as unmatched; it acts in
COUPON_ASSEMBLY.

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

If the set is larger than you intended, do **not** emit it. Key it as a
narrow read instead (one `WATCH` per rung you mean, see *`reads.json`*
below), or, if even that cannot be keyed, write it in prose and say it was
not applied. The same count applies to a read: a `WATCH` or `NO_BET` with
`subject: null` hits every subject on the fixture too.

## `reason_class` — pick the one that names the fault

| class | use when | example |
|---|---|---|
| `SAMPLE_UNINFORMATIVE` | the observations do not measure this fixture: wrong squad, wrong surface, wrong format, opponents nothing like today's, all on one side of a line it has never approached | "nine of ten matches are second-tier; today is a cup tie against a top-flight side" |
| `CONTEXT` | the sample is fine and the world has changed: dead rubber, second leg with the tie decided, four starters out, a derby the referee will call differently | "aggregate 4-0 from the first leg; both managers have named reserve XIs" |
| `PRICE` | the rung is unbettable as priced: one-sided ladder, price older than it looks, a rung that exists on our sheet and not on the screen | "the OVER side is not quoted; `market_p` is null and the bar is unanchored" |
| `OTHER` | what the list cannot express. Say why in `reason`. | |

### `context` — which kind of CONTEXT

Set it on every `CONTEXT` veto. It exists so the settlement audit can grade
each kind separately (`audit_settlement` section 7e, `audit_vetoes.py` across
days): the context read is the one thing Superbet's statistics do not carry,
and until 2026-09-23 there was no way to say whether it removed losers or
winners — 93 of 2026-09-22's 102 vetoes were filed as `OTHER`.

| `context` | use when | example |
|---|---|---|
| `MOTIVATION` | what the result is worth to one side: dead rubber, must-win, title or relegation, second leg already decided, ranking points to defend | "aggregate 4-0; nothing to play for" |
| `ROTATION` | a rested or reserve XI, a league match between two cup ties | "Champions League on Wednesday; the manager said he will rotate" |
| `ABSENCES` | named starters out, injury, suspension | "both first-choice centre-backs suspended" |
| `DERBY` | rivalry, grudge or revenge match, where the sample's normal fixtures do not describe tonight | "city derby; last three meetings 7, 8 and 9 cards" |
| `SCHEDULE` | fatigue, travel, back-to-back days, a long previous match, a qualifier's extra rounds | "3h40 five-setter yesterday, 11 pm finish" |
| `CONDITIONS` | weather, pitch, altitude, indoor/outdoor switch | "heavy rain forecast, waterlogged pitch reported" |

A `CONTEXT` veto's `reason` names **the source domain and its publication time**,
and that time is before the decision point: `"[sportsmole.co.uk, 2026-09-22
09:14 UTC] predicted XI rests five starters"`. A veto written after its fixture
started is excluded from the grade — the audit cannot tell a read from a
leak — so a late rebuild costs the measurement, not only the bet. Where to
look: `context-sources.md`.

`reason_class` is recorded and read; it does **not** change the arithmetic
(except `SAMPLE_UNINFORMATIVE`, which SHEET also reads to price the rung at
the market alone). Every class removes the row outright, from the coupon and from the old VALUE selector alike.
A veto has no softer form; the graded per-leg verdict (KEEP / WATCH /
NO_BET) lives in `reads.json`, below - not in tiers, which the retired
pipeline had and this one does not.

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

A validation error here is cheap. The same error at COUPON / CONFIDENCE
time stops the rebuild and leaves the previous artifacts and PDF in place -
validate before every rebuild.

## `reads.json` — one verdict per leg you read (since 2026-10-04)

`runs/sofa/<date>/reads.json`, a bare array of `LegRead`
(`src/bet/sofa/contracts.py`, `strict`, `extra="forbid"` - an invented key
fails the whole file, as with vetoes). Read by CONFIDENCE
(`run_confidence.py`, football / tennis), COUPON_ASSEMBLY (`build_coupon.py`,
the measured-sport legs) and the old COUPON stage (`run_coupon.py`); written
by the runner from your second JSON block and from the verifier's.

| field | type | meaning |
|---|---|---|
| `sofascore_event_id` | int | the fixture |
| `market` | str \| null | as in `Veto`; for a measured-sport leg the leg's `family` (`total`, `team_total`, `handicap`, `winner`, ...) |
| `subject` / `line` | as in `Veto`, nullable | `null` covers every value - the veto's matching rule, and its widening trap |
| `direction` | str \| null | `OVER` / `UNDER`, or a measured sport's side: `T1` / `T2` / `DRAW` / `ODD` / `EVEN` / `YES` / `NO` / an exact score `"3:1"` (`contracts.READ_SIDES`; anything else fails validation) |
| `period` | int \| null, optional | a measured sport's period - hockey period, basketball quarter, volleyball set, CS2 map; `0` the whole match; `null` (the default) covers every period |
| `verdict` | `"KEEP" \| "WATCH" \| "NO_BET"` | your verdict on the leg |
| `author` | `"analyst" \| "verifier"` | you are always `"analyst"` |
| `reason` | non-empty str | the operator reads it; it rides on the leg as `reads` |
| `context` | enum \| null, optional | the `context` tags above, when the reason is one of them; else leave it out |

What each verdict does, in code (`veto.read_refusal`, the coupon honours
WATCH; `coupon_sports.apply_reads` for a sport leg):

| verdict | the coupon (`11_coupon.json`, `KUPON_<d>.pdf`; also `06_coupon`) |
|---|---|
| `KEEP` | nothing removed; records that the leg was read |
| `WATCH` | removed, refusal `WATCHED`, into `removed_by_reads` |
| `NO_BET` | removed, refusal `READ_NO_BET`, into `removed_by_reads` |

A leg that passed every gate and a read removed (or the automatic
`MODEL_ABOVE_OWN_SAMPLE` WATCH on a football leg) is listed in
`removed_by_reads` of `11_coupon.json` and graded on its own at its printed
price: audit_settlement 7h ("Nogi zdjęte przez odczyt"), ledger variant
`removed:reads`. It is never in the coupon's result.

- **Who reads what.** One read per leg of your read set:
  `confidence.legs_requiring_read(doc, load_read_requests(run /
  "read_requests.json"))` - the first 30 unlocked positions of
  `11_coupon.json`, every printed builder leg, and every entry of
  `read_requests.json` (`{"position": n}` or `{"group_key": "sofa:<id>",
  "market"?, "line"?, "direction"?}`, each with `requested_by` and
  `at_utc`; the operator's "dodatkowo" in `/sofa-analyze`), your sport's
  part of it. `audit_variants.py` C3 fails the day when one of those legs
  has no read with `author: "analyst"`, or any printed leg carries WATCH /
  NO_BET - so a leg you read and kept still needs its `KEEP`. A
  fixture-wide `KEEP` (`market: null`) covers every rung on it and is fine
  when that is your read of the whole fixture.
- **A locked leg** (printed by an earlier build, match started, carried from
  `12_printed.json`) stays on the coupon whatever a read now says; C3 reads
  it as of its print, and a refusing read on it is a note, not a defect.
- **A read is a verdict on a leg; a veto is a verdict on a sample.** A sample
  that does not describe the fixture, or a context that breaks every rung,
  is still a veto (`SAMPLE_UNINFORMATIVE`, `CONTEXT`, ...): it removes
  everywhere and is graded by class in 7e. Do not write the same fault twice
  as a veto and a `NO_BET`. The exception is a measured-sport leg: a veto
  cannot name its side or period, so write a `NO_BET` read.
- `WATCH` is for the leg you would not stake but cannot call broken - the
  2026-10-04 Farense - Chaves UNDER 3.5 (analyst WATCH: Chaves 4/5/4/5 goals;
  the read had no field and the leg was printed and lost 4-0). `BUY ≈ KILL`
  is a WATCH.
- A read that matches nothing prints `UNMATCHED_READ` and is counted as
  `reads_unmatched` in CONFIDENCE's summary. `run_confidence.py` sees only
  football and tennis rows, so a measured-sport read always shows there as
  unmatched; it takes effect in COUPON_ASSEMBLY - confirm it in
  `11_coupon.json` (`removed_by_reads`, or the leg's `reads`).

A measured-sport read:

```json
[{"sofascore_event_id": 16310568, "market": "total", "subject": null,
  "line": 3.5, "direction": "OVER", "period": 0, "verdict": "NO_BET",
  "author": "analyst", "context": "SCHEDULE",
  "reason": "mecz przełożony (hltv.org, liquipedia.net)"}]
```

Validate before you hand it over:

```bash
.venv/bin/python - <<'PY'
import json, sys
sys.path.insert(0, "src")
from pydantic import RootModel
from bet.sofa.contracts import LegRead
raw = r"""<paste the reads array here>"""
reads = RootModel[list[LegRead]].model_validate_json(raw).root   # load_reads() reads it the same way
print(len(reads), "reads;", {v: sum(r.verdict == v for r in reads) for v in ("KEEP", "WATCH", "NO_BET")})
PY
```
