---
description: Rebuild one sofa day's coupon and PDF from the artifacts already on disk — no bridge, no Sofascore, no SAMPLES. For when code changed, an analyst produced vetoes, or the offer went stale.
argument-hint: dzisiaj | wczoraj | YYYY-MM-DD
---

Rebuild `KUPON_<date>.pdf` from artifacts that already exist. This is the last
mile of `/sofa-day` on its own: the sheet in, the operator's PDF out.

**Nothing here touches Sofascore or the bridge.** RESOLVE and SAMPLES are the
expensive stages and neither runs. The only network call is to Superbet, and
only if you refresh the offer.

Use it when: the code changed since the sheet was built, an analyst handed back
vetoes, the offer behind the file went stale, or you want the PDF regenerated.

Run every step. **Do not stop to ask permission between them.**

## Step 0 — resolve the day and take inventory

`$ARGUMENTS` is `dzisiaj`/`today`, `wczoraj`/`yesterday`, or `YYYY-MM-DD`;
empty means today. The betting day is **UTC**.

```bash
date -u +%F
ls -la runs/sofa/<date>/
```

Two inputs are not optional:

- **`05_sheet.json` missing** → there is nothing to rebuild. The day needs
  `/sofa-day <date>`, not this command. Say so and stop.
- **`02_fixtures.json` missing** → stop as well. Without it COUPON cannot name
  a fixture, cannot apply the kickoff gate, and `determine_side` cannot resolve
  a `subject` to a side.

`04_offer.json` is required by COUPON and CONFIDENCE both. `vetoes.json` is
optional and **`[]` is the healthy default**.

State the resolved date, what is present, and the age of each file. A sheet
built this morning against an offer refreshed at noon is a different object
from one where both are old.

## Step 1 — is the price still a price?

Both COUPON and CONFIDENCE refuse a rung whose `fetched_at_utc` is more than
**45 minutes** old. If the offer is older than that, a rebuild will empty the
coupon for a reason that looks like a modelling result.

```bash
.venv/bin/python -c "
import json, datetime
o = json.load(open('runs/sofa/<date>/04_offer.json'))
ts = [r['fetched_at_utc'] for f in o for r in f.get('rungs', [])]
print('rungs', len(ts), 'oldest', min(ts), 'newest', max(ts))
"
```

If it is stale and the day is still live, refresh:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_offer.py --date <date> --min-minutes-to-kickoff 20
```

`--min-minutes-to-kickoff` matters on a late refresh: without it the stage
re-prices the whole board including matches already played — on 2026-09-20 that
was 890 finished fixtures paid for to reach the 185 still open, at ~90 minutes
for a full pass.

**After a refresh, re-run SHEET** (offline, no bridge):

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only SHEET --run-id <id>
```

A row carries the price SHEET priced it at. Since 2026-09-25 COUPON and
CONFIDENCE refuse a row whose side the refreshed offer quotes at a different
price (`PRICE_MOVED_SINCE_SHEET`) or no longer quotes at all — they do not
swap the new odds in, because `market_p`, `p_central` and `required_odds`
were computed from the old ones. Before that fix they timed the fresh offer
and printed the stale price: 16 of 351 variant legs on 2026-09-25. Skipping
SHEET after a refresh is therefore not wrong, but it silently costs every leg
whose price moved.

If the day is **over**, do not refresh. Say the prices are historical and that
every gate downstream will now refuse them, which is correct behaviour.

## Step 2 — vetoes, if there are any

If an analyst produced vetoes, validate before writing — a malformed entry
fails the whole file and the stage then runs with **no** vetoes and reports
zero:

```bash
.venv/bin/python - <<'PY'
import json, sys
sys.path.insert(0, "src")
from pydantic import RootModel
from bet.sofa.contracts import SheetRow, Veto
from bet.sofa.veto import find_unmatched_vetoes
date = "<date>"
vetoes = RootModel[list[Veto]].model_validate_json(
    open(f"runs/sofa/{date}/vetoes.json").read()).root
rows = RootModel[list[SheetRow]].model_validate_json(
    open(f"runs/sofa/{date}/05_sheet.json").read()).root
unmatched = find_unmatched_vetoes(rows, vetoes)
print(f"{len(vetoes)} vetoes, {len(unmatched)} match nothing")
for v in unmatched:
    print("  UNMATCHED:", v.model_dump_json())
PY
```

Report every unmatched veto. It did nothing, and a silent no-op reads exactly
like a veto that was honoured.

## Step 3 — rebuild

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only COUPON
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <date>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <date>
# the operator's variant (0.65 / price up to 10% below fair), beside the coupon, never instead of it
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <date> --profile wariant
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <date> --profile wariant
```

Both COUPON and CONFIDENCE read `vetoes.json`, so both must be re-run after a
veto changes — rebuilding only the singles leaves the vetoed rung standing as a
leg of the Bet Builder the PDF stakes.

Do **not** re-run SHEET unless OFFER was refreshed (Step 1), or the engine or
a config file changed. If the engine or a config changed,
say which, because a rebuilt sheet is not comparable with the one before it.

Never re-run `fit_constants.py` as part of a rebuild.

## Step 4 — verify

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <date>
```

Then hand it to `sofa-verifier` unless the operator explicitly asked for a bare
rebuild.

## Report back

```
KUPON:    runs/sofa/<date>/KUPON_<date>.pdf — <n> pozycji (było <n>)
WARIANT:  runs/sofa/<date>/KUPON_<date>_WARIANT.pdf — <n> pozycji (NIE kupon; 0.65 / x ≥ 0.90)
SINGLE:   <n> wierszy VALUE → <n> w kuponie, <n> odrzuconych (powody)
WETA:     <n> zastosowanych, <n> bez dopasowania
CENA:     oferta z <ts>, wiek <n> min <"świeża" | "przeterminowana — to tłumaczy pustki">
ZMIANA:   <what moved and why — code, vetoes, or the price>
```

## Hard rules

- A thin rebuild is not fixed by re-running it. If the day produced nothing,
  say so and **say which gate emptied it** — read `06_dropped.json` and count
  by reason. The two that dominate are `DISAGREES_WITH_PRICE` (the model sits
  more than 0.10 above the devigged price — measured negative, not cautious)
  and `KICKOFF_TOO_SOON` (the *earlier* of the two clocks). On 2026-09-21 they
  were 84 and 34 of 118 VALUE rows, and the coupon was correctly empty.
- `06_coupon.json` is not the coupon. The PDF is.
- Never invent a price; never re-run SAMPLES here.
- Never read, echo or log `.env` values.
