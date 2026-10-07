---
description: Run the sofa analysts over a day that already has its coupon artifact (11_coupon.json) - the first 30 positions, every printed builder leg and the operator's extra positions ("dodatkowo") - merge their vetoes into vetoes.json and their per-leg reads into reads.json, and rebuild the coupon and PDF. No Sofascore, no SAMPLES.
argument-hint: "dzisiaj | wczoraj | YYYY-MM-DD [dodatkowo: <pozycje>]"
---

Take a day whose coupon artifact already exists, get the per-sport human
read, and turn it into the two artifacts the machine consumes:
`vetoes.json` (a broken sample or context - removes everywhere) and
`reads.json` (one KEEP / WATCH / NO_BET per leg read).

Both are read by **CONFIDENCE and COUPON_ASSEMBLY**, so this command always
ends in a rebuild. A veto or a read that is written and not rebuilt has done
nothing.

## Step 0 - the day, the extra positions, and what must be read

`$ARGUMENTS` is `<day> [dodatkowo: <n>, <n>, ...]`. The day is
`dzisiaj`/`today`, `wczoraj`/`yesterday` or `YYYY-MM-DD` (empty = today,
UTC). Everything after `dodatkowo:` is a list of coupon positions the
operator wants read beyond the first 30.

```bash
ls -la runs/sofa/<date>/
```

- No `05_sheet.json` -> nothing to analyse; the day needs `/sofa-day`.
- No `11_coupon.json` (COUPON_ASSEMBLY) -> build the chain first
  (`/sofa-rebuild`): the analysts read **what the coupon prints**, in its
  order, not the VALUE singles of `06_coupon.json`.

### 0a - "dodatkowo": append the operator's requests BEFORE the analysts

Positions shift after every rebuild, so resolve each requested position
against the **current** `11_coupon.json` and store the leg it names
(`group_key` + rung), not the number. Fall back to `{"position": n}` only
when the position names no leg. Append, never rewrite, and validate with
`confidence.load_read_requests` (an entry without `requested_by` and
`at_utc` raises - a request that silently does nothing reads like one that
was honoured):

```bash
PYTHONPATH=src:. .venv/bin/python - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path
from bet.sofa.confidence import load_read_requests

date, asked = "<date>", [31, 45, 52]          # the positions after "dodatkowo:"
run = Path("runs/sofa") / date
doc = json.loads((run / "11_coupon.json").read_text())
by_pos = {int(s["position"]): s for s in doc["singles"] if s.get("position") is not None}
path = run / "read_requests.json"
current = json.loads(path.read_text()) if path.exists() else []
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
for n in asked:
    leg = by_pos.get(n)
    if leg is None:
        print("NO LEG AT POSITION", n, "- stored as a position request")
        current.append({"position": n, "requested_by": "operator", "at_utc": now})
        continue
    current.append({"group_key": leg["group_key"], "market": leg["market"],
                    "line": leg.get("line"), "direction": leg["direction"],
                    "requested_by": "operator", "at_utc": now})
    print(n, leg["match"], leg["market"], leg.get("line"), leg["direction"])
path.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n")
print(len(load_read_requests(path)), "requests in read_requests.json")
PY
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon.py --date <date>   # 11 is STALE_COUPON against a newer read_requests.json
```

`build_coupon.py` prints `UNMATCHED_READ_REQUEST` for a request that covers
nothing - report each.

### 0b - the legs each analyst gets

```bash
PYTHONPATH=src:. .venv/bin/python - <<'PY'
import collections, json
from pathlib import Path
from bet.sofa.confidence import legs_requiring_read, load_read_requests
run = Path("runs/sofa") / "<date>"
doc = json.loads((run / "11_coupon.json").read_text())
sport_of = {f["sofascore_event_id"]: f["sport"]
            for f in json.loads((run / "02_fixtures.json").read_text())}
legs = legs_requiring_read(doc, load_read_requests(run / "read_requests.json"))
by = collections.Counter(x.get("sport") or sport_of.get(x["sofascore_event_id"]) for x in legs)
print("to read", len(legs), dict(by), "| printed singles", len(doc["singles"]),
      "builders", len(doc["builders"]), "removed_by_reads", len(doc["removed_by_reads"]))
print("sports", {k: (v["status"], v["legs"]) for k, v in (doc.get("sports") or {}).items()})
PY
# the run id: the last non-empty run_id of a SAMPLES request on that date (or the id the day was run with)
.venv/bin/python -c "
import json
ids = [r.get('run_id') for r in map(json.loads, open('runs/sofa/run.log.jsonl'))
       if r.get('stage') == 'SAMPLES' and r.get('run_id') and r.get('ts_utc', '').startswith('<date>')]
print('run_id', ids[-1] if ids else 'NOT FOUND - say so')
"
```

That set is `confidence.legs_requiring_read`: the first 30 unlocked
positions of `11_coupon.json`, every printed builder leg, and every
`read_requests.json` entry - exactly what `audit_variants` C3 checks. The
rest of the coupon prints unread (the operator's order of 2026-10-05). A
`locked` leg (printed by an earlier build, its match started) stays as
printed whatever a read says.

At the start of **every** analyst pass (the first, and each C3 re-read in
Step 3) clear the hand-off files of the pass before. Name them, never glob
them: under zsh a pattern that matches nothing aborts the whole command with
`no matches found` and removes nothing (`rm -f /tmp/*_reads.json
/tmp/*_vetoes.json` fails whenever one of the two has no file).

```bash
for s in football tennis hockey basketball volleyball cs2; do
  rm -f "/tmp/${s}_reads.json" "/tmp/${s}_vetoes.json"
done
find /tmp -maxdepth 1 \( -name '*_reads.json' -o -name '*_vetoes.json' \)   # what is left (find has no nomatch)
```

## Step 1 - launch the analysts, concurrently

One analyst per sport that has legs in the set, all in **one** message so
they run in parallel:

```
Task -> sofa-analyst-football   "date <date>; run <run_id>; <n> football legs to read (<k> asked by the operator: positions ...); <anything that failed in the run>"
Task -> sofa-analyst-tennis     "date <date>; run <run_id>; <n> tennis legs to read (...); <anything that failed>"
Task -> sofa-analyst-sport      "sport hockey; date <date>; <n> legs to read (...); <anything that failed>"   # one per measured sport with legs: hockey / basketball / volleyball / cs2
```

Give each the counts you just computed, the run id, the operator's extra
positions and what failed. Do **not** give any of them your own opinion
about a fixture - you would be asking it to confirm you. A sport with no
legs in the set gets no analyst; say so.

Each returns Polish markdown and fenced JSON: the football and tennis
analysts return the vetoes (`[]` is the normal, healthy answer) and then the
reads; `sofa-analyst-sport` returns reads only (a veto's direction is only
`OVER` / `UNDER` and has no period, so it cannot name a sport side). Write
them to `/tmp/<sport>_vetoes.json` and `/tmp/<sport>_reads.json` with a
quoted heredoc (`<sport>` is `football`, `tennis`, `hockey`, `basketball`,
`volleyball` or `cs2`; a sport analyst writes no vetoes file). An analyst that returned no reads block has not followed its
contract - say so, never invent its reads.

## Step 2 - validate, then merge

```bash
.venv/bin/python - <<'PY'
import json, os, sys
sys.path.insert(0, "src")
from pydantic import RootModel
from bet.sofa.contracts import SheetRow, Veto
from bet.sofa.veto import find_unmatched_vetoes

date = "<date>"
fresh = [v for s in ("football", "tennis") if os.path.exists(f"/tmp/{s}_vetoes.json")
         for v in json.loads(open(f"/tmp/{s}_vetoes.json").read())]
# The day may already hold vetoes (an earlier build, a rebuild): keep them.
# A veto can only remove a row, so carrying one over is conservative; list
# them so the operator sees what was not re-issued today.
path = f"runs/sofa/{date}/vetoes.json"
earlier = json.loads(open(path).read()) if os.path.exists(path) else []
key = lambda v: json.dumps(v, sort_keys=True)
carried = [v for v in earlier if key(v) not in {key(x) for x in fresh}]
merged = fresh + carried
print(f"{len(fresh)} fresh vetoes, {len(carried)} carried over from vetoes.json")
for v in carried:
    print("  CARRIED:", json.dumps(v, ensure_ascii=False))

# Validation first: extra="forbid" means an invented key (action, player,
# event_id) fails the whole file, and every stage that reads it refuses -
# the previous artifacts and PDF stay on disk looking current.
vetoes = RootModel[list[Veto]].model_validate(merged).root
rows = RootModel[list[SheetRow]].model_validate_json(
    open(f"runs/sofa/{date}/05_sheet.json").read()).root

unmatched = find_unmatched_vetoes(rows, vetoes)
print(f"{len(vetoes)} vetoes, {len(unmatched)} match nothing")
for v in unmatched:
    print("  UNMATCHED:", v.model_dump_json())

open(path, "w").write(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
PY
```

Three things to check before you accept a veto list:

1. **Unmatched entries.** Report every one. It did nothing.
2. **Width.** There is no player field. A veto with `subject: null` covers
   every subject on that fixture - count what it hits before writing it.
3. **Duplication of a code gate.** `STALE_PRICE`, `STALE_SAMPLE`,
   `ODDS_TOO_LOW`, `KICKED_OFF`, `MODE_LOSES`, `LINE_BEYOND_SAMPLE`,
   `THIN_SAMPLE_FOR_BUILDER`, `SAMPLE_CROSSES_SEASON`,
   `CROSS_LEAGUE_UNLINKED`, `NO_CLASS_CURVE`, `NO_LINE_EVIDENCE`,
   `FIXTURE_NOT_AS_SCHEDULED` and (football) `MODEL_ABOVE_OWN_SAMPLE` are
   already enforced. A veto for one of those adds nothing and buries the
   real reasons in noise.

Then merge the reads of every analyst - appended to whatever `reads.json`
holds (an earlier pass, the verifier), never editing or dropping one: WATCH
and NO_BET win over KEEP whoever wrote them, so carrying one over is
conservative.

```bash
.venv/bin/python - <<'PY'
import json, os, sys
sys.path.insert(0, "src")
from pydantic import RootModel
from bet.sofa.contracts import LegRead

date = "<date>"
# the analysts of THIS pass, by name (never a glob: a stale or foreign
# /tmp/*_reads.json would be merged in); the verifier's reads are appended by
# whoever ran it, not here
fresh = [r for s in ("football", "tennis", "hockey", "basketball", "volleyball", "cs2")
         if os.path.exists(f"/tmp/{s}_reads.json")
         for r in json.loads(open(f"/tmp/{s}_reads.json").read())]
path = f"runs/sofa/{date}/reads.json"
earlier = json.loads(open(path).read()) if os.path.exists(path) else []
key = lambda r: json.dumps(r, sort_keys=True)
seen = {key(r) for r in earlier}
merged = earlier + [r for r in fresh if key(r) not in seen]
# strict, extra="forbid": one bad entry fails the whole file - and
# CONFIDENCE and COUPON_ASSEMBLY with it. Validate before writing.
RootModel[list[LegRead]].model_validate_json(json.dumps(merged))
open(path, "w").write(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
print(f"{len(fresh)} fresh reads, {len(merged)} in reads.json:",
      {v: sum(r["verdict"] == v for r in merged) for v in ("KEEP", "WATCH", "NO_BET")})
PY
PYTHONPATH=src:. .venv/bin/python -c "from bet.sofa.veto import load_reads; print(len(load_reads('runs/sofa/<date>/reads.json')))"
```

What a read does: `WATCH` and `NO_BET` both remove the leg from the coupon;
a leg that passed every gate and a read (or the automatic football
`MODEL_ABOVE_OWN_SAMPLE`) removed lands in `removed_by_reads` of
`11_coupon.json`, graded on its own (audit_settlement 7i, ledger
`removed:reads`) and never in the coupon's result. `KEEP` removes nothing
and records that the leg was read. Count what each WATCH / NO_BET will hit,
as for a veto - `subject: null` covers every subject on the fixture, a
`period: null` every period of a sport leg.

## Step 3 - rebuild

The one rebuild command, nothing else (`/sofa-rebuild`; plan production
grade F0.2). It refreshes a stale football / tennis offer or sport snapshot
first (only while the day is live - on a stats-only day a moved price
re-prices the leg at the fresh odds, no SHEET re-run), re-runs COUPON
(`06_coupon.json`, the priced VALUE selector `audit_coupon` checks - not the
coupon) when it is older than the vetoes / reads, then FIXTURE_CHECK,
CONFIDENCE, SPORT_CONFIDENCE, COUPON_ASSEMBLY, the PDF and both audits:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <date> --dry-run   # the plan and its reasons
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <date>
```

`build_coupon_pdf.py` refuses `STALE_CONFIDENCE` (08 older than
`05_sheet.json` / `vetoes.json` / `reads.json` / the calibration) and
`STALE_COUPON` (11 older than `08_confidence.json` /
`08_confidence_sports.json` / `read_requests.json` / `09_screen_prices.json` /
the coupon form); the rebuild runs them in the only order that renders.
It re-runs SHEET only for an old epoch or link rule, **not** after a change
of the SHEET estimator (from 2026-10-07 14:05Z: tennis rating prices,
football marginal centres, basketball freshness): a `05_sheet.json` older
than the switch must be re-run first, `run_pipeline.py --date <date> --only
SHEET --run-id <id>` (`/sofa-rebuild`) - say so rather than reading stale
`p_central`s. Read each summary's `refused` counts (`WATCHED`,
`READ_NO_BET`, `MODEL_ABOVE_OWN_SAMPLE`). `run_confidence.py` sees only
football and tennis rows: it prints a sport read as `UNMATCHED_READ` on
stderr, which is expected - sport reads take effect in COUPON_ASSEMBLY, so
confirm each in `11_coupon.json` (`removed_by_reads`, or the leg's `reads`).
Any other `UNMATCHED_READ` is a read that did nothing - report it.

`audit_variants` C3 fails a leg in the read set without an `author:
"analyst"` read, or a printed leg carrying WATCH / NO_BET. A rebuild moves
positions: a removed leg lets the next one into the first 30, and a removed
builder leg lets a builder take another. Send exactly those legs to that
sport's analyst, merge its reads, rebuild and re-audit until C3 is clean. A
refusing read on a locked leg is a note, not a defect.

## Step 4 - save the read and report the delta

Save each analyst's markdown as `runs/sofa/<date>/<date>_analiza_<sport>.md`.

```
ANALIZA:  piłka <n> nóg przeczytanych · tenis <n> · hokej / kosz / siatka / CS2 <n> · dodatkowo (operator) <n> pozycji
WETA:     <n> zastosowanych (<n> SAMPLE_UNINFORMATIVE / <n> CONTEXT / <n> PRICE / <n> OTHER), <n> bez dopasowania
READS:    <n> (KEEP <n> / WATCH <n> / NO_BET <n>) · UNMATCHED_READ <n> (poza odczytami sportów) · C3 <n> (musi być 0)
KUPON:    runs/sofa/<date>/KUPON_<date>.pdf — pozycje <n> → <n>, buildery <n> → <n>, nogi w grze (zablokowane) <n>
ZDJĘTE:   <removed_by_reads: each leg, the read and its author>
POZA TOP 30: <n> pozycji drukowanych bez odczytu (zasada operatora)
NIE PRZECZYTANO: <legs in the read set no analyst reached, and why>
```

Say explicitly which legs of the read set were **not** read. An unread leg
must be named rather than silently absent.

## Hard rules

- Never edit an analyst's veto or read reasons to make them fit. If an entry
  is wrong, drop it and say you dropped it.
- Never write a veto or a read of your own into the files. You merge; the
  analysts (and the verifier) judge. The operator's `read_requests.json`
  entries are requests to read, never verdicts.
- A veto can only remove. There is no promotion in `sofa`.
- Never print a combined / builder price outside what `confidence.py`
  computed; no stake sizing.
- Never read, echo or log `.env` values.
