---
description: Run the sofa analysts over a day that already has a sheet, merge their vetoes into vetoes.json, and rebuild the coupon and PDF. No Sofascore, no bridge, no SAMPLES.
argument-hint: dzisiaj | wczoraj | YYYY-MM-DD
---

Take a day whose sheet already exists, get the per-sport human read, and turn
it into the one artifact the machine consumes.

`vetoes.json` is read by **COUPON and CONFIDENCE both**, so this command always
ends in a rebuild. A veto that is written and not rebuilt has done nothing.

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
```

No `05_sheet.json` → nothing to analyse; the day needs `/sofa-day`.
No `08_confidence.json` → run `run_confidence.py` first, because the analysts
must grade **what is actually staked**, not only the VALUE singles.

## Step 1 — launch both analysts, concurrently

In **one** message, so they run in parallel:

```
Task -> sofa-analyst-football   "date <date>; <n> football fixtures, <n> VALUE, <n> legs, <n> stakeable builders; <anything that failed in the run>"
Task -> sofa-analyst-tennis     "date <date>; <n> tennis fixtures, <n> VALUE, <n> legs, <n> stakeable builders; <anything that failed>"
```

Give each the counts you just computed, the run id, and what failed. Do **not**
give either your own opinion about a fixture — you would be asking it to
confirm you.

Each returns Polish markdown and one fenced JSON array. `[]` is the normal,
healthy answer and is not a failed analysis.

## Step 2 — validate, then merge

```bash
.venv/bin/python - <<'PY'
import json, sys
sys.path.insert(0, "src")
from pydantic import RootModel
from bet.sofa.contracts import SheetRow, Veto
from bet.sofa.veto import find_unmatched_vetoes

date = "<date>"
merged = json.loads(open("/tmp/football_vetoes.json").read()) \
       + json.loads(open("/tmp/tennis_vetoes.json").read())

# Validation first: extra="forbid" means an invented key (action, player,
# event_id) fails the whole file, and COUPON then runs with NO vetoes at all
# and reports zero.
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
   `ODDS_TOO_LOW`, `KICKOFF_TOO_SOON`, `MODE_LOSES`, `LINE_BEYOND_SAMPLE` and
   `THIN_SAMPLE_FOR_BUILDER` are already enforced. A veto for one of those adds
   nothing and buries the real reasons in noise.

## Step 3 — rebuild

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only COUPON
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <date>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <date>
```

If the offer is more than 45 minutes old and the day is still live, refresh it
first (`run_offer.py --date <date> --min-minutes-to-kickoff 20`) — otherwise
both stages will refuse every price and the empty result will look like an
analytical conclusion.

## Step 4 — save the read and report the delta

Save each analyst's markdown as `runs/sofa/<date>/<date>_analiza_<sport>.md`.

```
ANALIZA:  piłka <n> meczów przeczytanych z <n>; tenis <n> z <n>
WETA:     <n> zastosowanych (<n> SAMPLE_UNINFORMATIVE / <n> CONTEXT / <n> PRICE / <n> OTHER), <n> bez dopasowania
KUPON:    single <n> → <n>; PDF <n> → <n> pozycji
ZDJĘTE:   <which rows the vetoes removed, and from which product>
NIE PRZECZYTANO: <fixtures neither analyst reached, and why>
```

Say explicitly which fixtures were **not** read. On a Sunday board of 1000+
football fixtures nobody reads them all, and an unread fixture must be named
rather than silently absent.

## Hard rules

- Never edit an analyst's veto reasons to make them fit. If an entry is wrong,
  drop it and say you dropped it.
- Never write a veto of your own into the file. You merge; the analysts judge.
- A veto can only remove. There is no promotion in `sofa`.
- Never read, echo or log `.env` values.
