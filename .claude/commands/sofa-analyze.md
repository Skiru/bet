---
description: Run the sofa analysts over a day that already has a sheet, merge their vetoes into vetoes.json and their per-leg reads into reads.json, and rebuild the coupon and PDF. No Sofascore, no bridge, no SAMPLES.
argument-hint: dzisiaj | wczoraj | YYYY-MM-DD
---

Take a day whose sheet already exists, get the per-sport human read, and turn
it into the two artifacts the machine consumes: `vetoes.json` (a broken
sample or context - removes everywhere) and `reads.json` (one KEEP / WATCH /
NO_BET per printed leg).

Both are read by **COUPON and CONFIDENCE**, so this command always ends in a
rebuild. A veto or a read that is written and not rebuilt has done nothing.

## Step 0 — check the day is analysable

```bash
ls -la runs/sofa/<date>/
.venv/bin/python -c "
import json, collections
rows = json.load(open('runs/sofa/<date>/05_sheet.json'))
by = collections.Counter((r['sport'], r['verdict']) for r in rows)
print('sheet rows', len(rows))
for k, v in sorted(by.items()): print(' ', k, v)
c = json.load(open('runs/sofa/<date>/08_confidence.json'))
print('legs', len(c['legs']), 'builders', len(c['builders']),
      'stakeable', sum(1 for b in c['builders']
                       if b.get('best_for_fixture') and b.get('ev_after_haircut', -1) > 0))
"
# the run id: the last non-empty run_id of a SAMPLES request on that date (or the id the day was run with)
.venv/bin/python -c "
import json
ids = [r.get('run_id') for r in map(json.loads, open('runs/sofa/run.log.jsonl'))
       if r.get('stage') == 'SAMPLES' and r.get('run_id') and r.get('ts_utc', '').startswith('<date>')]
print('run_id', ids[-1] if ids else 'NOT FOUND - say so')
"
```

No `05_sheet.json` → nothing to analyse; the day needs `/sofa-day`.
No `08_confidence.json` → run `run_confidence.py` first, because the analysts
must grade **what is actually staked**, not only the VALUE singles.

## Step 1 — launch both analysts, concurrently

In **one** message, so they run in parallel:

```
Task -> sofa-analyst-football   "date <date>; run <run_id>; <n> football fixtures, <n> VALUE, <n> legs, <n> stakeable builders; <anything that failed in the run>"
Task -> sofa-analyst-tennis     "date <date>; run <run_id>; <n> tennis fixtures, <n> VALUE, <n> legs, <n> stakeable builders; <anything that failed>"
```

Give each the counts you just computed, the run id, and what failed. Do **not**
give either your own opinion about a fixture — you would be asking it to
confirm you.

Each returns Polish markdown and two fenced JSON arrays: the vetoes (`[]` is
the normal, healthy answer and is not a failed analysis), then the reads -
one `LegRead` (`author: "analyst"`) per printed leg it read. Write them to
`/tmp/<sport>_vetoes.json` and `/tmp/<sport>_reads.json` (`football` /
`tennis`) with a quoted heredoc. An analyst that returned no reads block has
not followed its contract - say so, never invent its reads.

## Step 2 — validate, then merge

```bash
.venv/bin/python - <<'PY'
import json, sys
sys.path.insert(0, "src")
from pydantic import RootModel
from bet.sofa.contracts import SheetRow, Veto
from bet.sofa.veto import find_unmatched_vetoes

date = "<date>"
fresh = json.loads(open("/tmp/football_vetoes.json").read()) \
      + json.loads(open("/tmp/tennis_vetoes.json").read())
# The day may already hold vetoes (an earlier build, a rebuild): keep them.
# A veto can only remove a row, so carrying one over is conservative; list
# them so the operator sees what was not re-issued today.
import os
path = f"runs/sofa/{date}/vetoes.json"
earlier = json.loads(open(path).read()) if os.path.exists(path) else []
key = lambda v: json.dumps(v, sort_keys=True)
carried = [v for v in earlier if key(v) not in {key(x) for x in fresh}]
merged = fresh + carried
print(f"{len(fresh)} fresh vetoes, {len(carried)} carried over from vetoes.json")
for v in carried:
    print("  CARRIED:", json.dumps(v, ensure_ascii=False))

# Validation first: extra="forbid" means an invented key (action, player,
# event_id) fails the whole file, and the run stops: COUPON raises (FAILED,
# exit 2 through run_pipeline.py) and run_confidence.py dies on an uncaught
# ValidationError, exit 1 - which reads as PARTIAL. Neither rewrites its
# artifact, so the previous 06/08 files and PDF stay on disk looking current.
vetoes = RootModel[list[Veto]].model_validate(merged).root
rows = RootModel[list[SheetRow]].model_validate_json(
    open(f"runs/sofa/{date}/05_sheet.json").read()).root

unmatched = find_unmatched_vetoes(rows, vetoes)
print(f"{len(vetoes)} vetoes, {len(unmatched)} match nothing")
for v in unmatched:
    print("  UNMATCHED:", v.model_dump_json())

open(f"runs/sofa/{date}/vetoes.json", "w").write(
    json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
PY
```

Three things to check before you accept a veto list:

1. **Unmatched entries.** Report every one. It did nothing.
2. **Width.** There is no player field. A veto with `subject: null` covers
   every subject on that fixture — count what it hits before writing it.
3. **Duplication of a code gate.** `STALE_PRICE`, `STALE_SAMPLE`,
   `ODDS_TOO_LOW`, `KICKOFF_TOO_SOON`, `MODE_LOSES`, `LINE_BEYOND_SAMPLE`,
   `THIN_SAMPLE_FOR_BUILDER` and (football, official profile)
   `MODEL_ABOVE_OWN_SAMPLE` are already enforced. A veto for one of those adds
   nothing and buries the real reasons in noise.

Then merge the reads - appended to whatever `reads.json` holds (an earlier
pass, the verifier), never editing or dropping one: WATCH and NO_BET win
over KEEP whoever wrote them, so carrying one over is conservative.

```bash
.venv/bin/python - <<'PY'
import json, os, sys
sys.path.insert(0, "src")
from pydantic import RootModel
from bet.sofa.contracts import LegRead

date = "<date>"
fresh = [r for f in ("/tmp/football_reads.json", "/tmp/tennis_reads.json")
         for r in json.loads(open(f).read())]
path = f"runs/sofa/{date}/reads.json"
earlier = json.loads(open(path).read()) if os.path.exists(path) else []
key = lambda r: json.dumps(r, sort_keys=True)
seen = {key(r) for r in earlier}
merged = earlier + [r for r in fresh if key(r) not in seen]
# strict, extra="forbid": one bad entry fails the whole file - and COUPON and
# CONFIDENCE with it. Validate before writing.
RootModel[list[LegRead]].model_validate_json(json.dumps(merged))
open(path, "w").write(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
print(f"{len(fresh)} fresh reads, {len(merged)} in reads.json:",
      {v: sum(r["verdict"] == v for r in merged) for v in ("KEEP", "WATCH", "NO_BET")})
PY
PYTHONPATH=src:. .venv/bin/python -c "from bet.sofa.veto import load_reads; print(len(load_reads('runs/sofa/<date>/reads.json')))"
```

What a read does: `NO_BET` removes the leg from every profile
(`READ_NO_BET`); `WATCH` removes it from the official coupon (`WATCHED`) and
**keeps** it in the WARIANT, printed `WATCH (<author>): <reason>` - the
operator's decision of 2026-10-04, so the ledger can measure whether WATCH
removes losers; `KEEP` removes nothing. Count what each WATCH / NO_BET will
hit, as for a veto - `subject: null` covers every subject on the fixture.

## Step 3 — rebuild

If the offer is more than 45 minutes old and the day is still live, refresh it
first and re-run SHEET before the rebuild below - a moved price is refused
(`PRICE_MOVED_SINCE_SHEET`) otherwise, and the empty result will look like an
analytical conclusion:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_offer.py --date <date> --min-minutes-to-kickoff 20
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only SHEET
```

Then:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only COUPON
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <date>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <date>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <date> --profile wariant
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <date> --profile wariant
# WARIANT WSZYSTKIE prints the official singles verbatim: re-assemble it after any rebuild
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_multi_coupon.py --date <date>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <date>
```

The variant is rebuilt too: it reads the same `vetoes.json` and
`reads.json`, and a variant PDF built before the merge prints legs the
analysts just vetoed. `build_coupon_pdf.py` refuses (exit 2,
`STALE_CONFIDENCE`) a profile whose confidence artifact is older than
`vetoes.json` or `05_sheet.json` - but **not** `reads.json`; only
`audit_variants` C1 catches that, so never skip `run_confidence.py` after a
reads merge. Read each summary's `refused` counts (`WATCHED`, `READ_NO_BET`,
`MODEL_ABOVE_OWN_SAMPLE`) and every `UNMATCHED_READ` line on stderr.

`audit_variants` C3 (days from 2026-10-05) fails a leg the official PDF
prints without an analyst's read, or despite a WATCH / NO_BET. A rebuild can
put a leg on the PDF that no analyst read (a removed leg lets a builder take
another): send exactly those legs to that sport's analyst, merge its reads,
rebuild and re-audit.

WARIANT WSZYSTKIE excludes a sport coupon built more than 6 h before the
assembly (`STALE`): rebuild that sport with a `sofa-sport-runner` first if the
operator wants it on the page. After 06:00 Warsaw on D+1 the day's window is
closed and `run_multi_coupon.py` refuses (exit 2) - the variant is final;
skip it and say so.

## Step 4 — save the read and report the delta

Save each analyst's markdown as `runs/sofa/<date>/<date>_analiza_<sport>.md`.

```
ANALIZA:  piłka <n> meczów przeczytanych z <n>; tenis <n> z <n>
WETA:     <n> zastosowanych (<n> SAMPLE_UNINFORMATIVE / <n> CONTEXT / <n> PRICE / <n> OTHER), <n> bez dopasowania
READS:    <n> (KEEP <n> / WATCH <n> / NO_BET <n>) · UNMATCHED_READ <n> · C3 <n> drukowanych nóg bez odczytu (musi być 0)
KUPON:    single <n> → <n>; PDF <n> → <n> pozycji
WARIANT:  PDF <n> → <n> pozycji (NIE kupon)
WSZYSTKIE: runs/sofa/multi/<date>/KUPON_<date>_WSZYSTKIE.pdf — <n> pozycji, sekcje <k>/5 · audyt wariantów <n> znalezisk
ZDJĘTE:   <which rows the vetoes and the WATCH / NO_BET reads removed, and from which product; WATCH legs kept in the WARIANT>
NIE PRZECZYTANO: <fixtures neither analyst reached, and why>
```

Say explicitly which fixtures were **not** read. On a Sunday board of 1000+
football fixtures nobody reads them all, and an unread fixture must be named
rather than silently absent.

## Hard rules

- Never edit an analyst's veto reasons to make them fit. If an entry is wrong,
  drop it and say you dropped it.
- Never write a veto or a read of your own into the files. You merge; the
  analysts (and the verifier) judge.
- A veto can only remove. There is no promotion in `sofa`.
- Never read, echo or log `.env` values.
