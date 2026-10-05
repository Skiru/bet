---
description: Rebuild one sofa day's coupon (11_coupon.json) and PDF from the artifacts already on disk - no SAMPLES; the bridge only for FIXTURE_CHECK. For when code changed, an analyst or the verifier produced vetoes or reads, the operator asked for more reads, or the offer went stale.
argument-hint: dzisiaj | wczoraj | YYYY-MM-DD
---

Rebuild `KUPON_<date>.pdf` from artifacts that already exist. This is the last
mile of `/sofa-day` on its own: the sheet in, the operator's PDF out.

**RESOLVE and SAMPLES never run here** - they are the expensive stages. The
only Sofascore call is FIXTURE_CHECK (one `/event/{id}` per printed match,
through the bridge); the only other network call is to Superbet, and only if
you refresh a price.

Use it when: the code changed since the sheet was built, an analyst or the
verifier handed back vetoes or reads, the operator added `read_requests.json`
entries, a price went stale, or you want the PDF regenerated.

Run every step. **Do not stop to ask permission between them.**

## Step 0 - resolve the day, the epoch, and take inventory

`$ARGUMENTS` is `dzisiaj`/`today`, `wczoraj`/`yesterday`, or `YYYY-MM-DD`;
empty means today. The betting day is **UTC**.

```bash
date -u +%F
ls -la runs/sofa/<date>/
```

Two inputs are not optional:

- **`05_sheet.json` missing** -> there is nothing to rebuild. The day needs
  `/sofa-day <date>`, not this command. Say so and stop.
- **`02_fixtures.json` missing** -> stop as well. Without it no stage can name
  a fixture, apply the kickoff gate, or resolve a `subject` to a side.

`04_offer.json` is required by CONFIDENCE. `vetoes.json` is optional and
**`[]` is the healthy default**. `reads.json` (per-leg KEEP / WATCH / NO_BET
from the analysts and the verifier) and `read_requests.json` (the operator's
extra legs to read) are optional to the code, but `audit_variants` C3 fails
any leg of `confidence.legs_requiring_read` - the first 30 unlocked positions
of `11_coupon.json`, every printed builder leg, every `read_requests.json`
entry - without an analyst's read. A rebuild that moves an unread leg into
that set needs that sport's analyst on exactly those legs (`/sofa-analyze`).

**The epoch (`bet.sofa.epochs`, K0).** A build of a day >= 2026-10-05 made at
or after 07:15Z (`STATS_ONLY_FROM_UTC`) is stats-only: confidence from the
statistics alone, the price only the betting condition, one coupon artifact
`11_coupon.json`. From 08:30Z (`SPORTS_ON_COUPON_FROM_UTC`) the hockey,
basketball, volleyball and CS2 legs print on the same coupon. A rebuild of
such a day always builds under that rule; an older day rebuilds under its
own. State which epoch the rebuild is in. The coupon before and after the
cutover is not one experiment.

State the resolved date, what is present, and the age of each file. A sheet
built this morning against an offer refreshed at noon is a different object
from one where both are old.

## Step 1 - is the price still a price?

CONFIDENCE refuses a rung whose `fetched_at_utc` is more than **45 minutes**
old (`STALE_PRICE`). If the offer is older than that, a rebuild will empty the
coupon for a reason that looks like a modelling result.

```bash
.venv/bin/python -c "
import json
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
re-prices the whole board including matches already played - on 2026-09-20 that
was 890 finished fixtures paid for to reach the 185 still open, at ~90 minutes
for a full pass.

**No SHEET re-run for a refresh on a stats-only day.** No probability read the
price, so CONFIDENCE judges a moved price at the fresh odds (x, margin,
`ODDS_TOO_LOW`). `PRICE_MOVED_SINCE_SHEET` remains only for builds of the old
epoch, where a refresh still needs SHEET first.

**SHEET first when the rule or the engine changed:** a code change to SHEET,
a config file SHEET reads, or a sheet built before the stats-only cutover -
CONFIDENCE refuses (exit 2) a SHEET not built under the stats-only rule on a
stats-only build ("a rebuild starts at SHEET"):

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only SHEET --run-id <id>
```

Say which change forced it: a rebuilt sheet is not comparable with the one
before it. SHEET parses the whole football history - ~30 s on a rebuild, up
to ~10 min when the listings changed; a SHEET that looks hung is parsing.

If the day is **over**, do not refresh. Say the prices are historical and that
every gate downstream will now refuse them, which is correct behaviour.

## Step 2 - vetoes and reads, if there are any

If an analyst produced vetoes, validate before writing and before any
rebuild - a malformed entry stops the run (`extra="forbid"`: one invented key
fails the whole file) and no stage rewrites its artifact, so yesterday's
build stays on disk looking current:

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

If `reads.json` or `read_requests.json` exists, validate them the same way
before the rebuild:

```bash
PYTHONPATH=src:. .venv/bin/python -c "from bet.sofa.veto import load_reads; print(len(load_reads('runs/sofa/<date>/reads.json')))"
PYTHONPATH=src:. .venv/bin/python -c "from pathlib import Path; from bet.sofa.confidence import load_read_requests; print(len(load_read_requests(Path('runs/sofa/<date>/read_requests.json'))))"
```

`WATCH` and `NO_BET` both remove the leg from the coupon into
`removed_by_reads` (graded apart, audit_settlement 7h); `KEEP` removes
nothing. CONFIDENCE prints `UNMATCHED_READ` on stderr for a read that matched
no football / tennis row - a sport read always shows there and takes effect
in COUPON_ASSEMBLY; any other one is a read that did nothing - report it.

## Step 3 - rebuild, in this order

```bash
# 1. FIXTURE_CHECK (bridge): /event/{id} for the printed matches and the moved clocks -> fixture_status.json
.venv/bin/python scripts/sofa/ensure_bridge.py
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only FIXTURE_CHECK
# 2. CONFIDENCE (football, tennis) -> 08_confidence.json
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <date>
# 3. only when the sport prices are stale (older than sport_coupon.MAX_PRICE_AGE, 3 h) and the day is live:
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only SHADOW
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only CS2
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only SPORT_IDENTITY     # bridge; only new events are asked, an IDENTIFIED one is pinned
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only SPORT_CONFIDENCE   # -> 08_confidence_sports.json
# 4. COUPON_ASSEMBLY -> 11_coupon.json (vetoes and reads on the sport legs are applied here)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon.py --date <date>
# 5. PDF -> KUPON_<date>.pdf and 12_printed.json (what was printed; the next rebuild locks from it)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <date>
# 6. the audit of the coupon artifact
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <date>
```

- **FIXTURE_CHECK** replaces RESOLVE's frozen Sofascore clock with a fresh
  `/event` start (K12) for the gate, the lock and `capture_closing`; a
  postponed / cancelled / abandoned printed match is
  `FIXTURE_NOT_AS_SCHEDULED` and CONFIDENCE refuses it (K14). **No bridge =
  UNVERIFIED, not a refusal:** it exits 1, the status is shown on the page,
  nothing is refused - say so in the report. A 403 stops it at once; never
  retry into a refusal.
- **Locked legs** - the legs `12_printed.json` holds whose match has started -
  are carried over as printed (`locked: true`, `printed_at_utc`,
  `printed_under`, first on the page and unnumbered). That is the operator's
  rule (a leg printed before its start counts), not a defect; a leg removed
  before its start stays removed.
- `build_coupon.py` refuses an `08_confidence.json` not built under the
  stats-only rule, or one stale against `05_sheet.json` / `vetoes.json` /
  `reads.json` / the calibration. `build_coupon_pdf.py` refuses
  `STALE_CONFIDENCE` and `STALE_COUPON` (11 older than `08_confidence.json`,
  `08_confidence_sports.json` or `read_requests.json`). After any change to
  vetoes, reads or requests, re-run from step 2.
- `SPORT_CONFIDENCE` exits 1 when a sport is `NOT_CALIBRATED` or
  `sport_fixtures.json` is missing; the artifact is still written and the
  football / tennis coupon is still built - name the sport that is absent.
- `run_pipeline.py --only COUPON` writes `06_coupon.json`, the priced VALUE
  selector that `audit_coupon.py` audits. It is not the coupon; re-run it
  only to keep that audit in step with the vetoes.

Never re-run `fit_constants.py` or any `fit_*` as part of a rebuild.

## Step 4 - verify

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <date>
```

`audit_variants` C1-C3 and U1-U3 must be clean (U3 re-derives every fresh
sport leg from the raw Superbet snapshot). Then hand the day to
`sofa-verifier` unless the operator explicitly asked for a bare rebuild.

## Report back

```
EPOKA:    <stats_only | old> · sporty na kuponie: <tak/nie>
KUPON:    runs/sofa/<date>/KUPON_<date>.pdf — <n> pozycji (było <n>) · buildery <n> · w grze (zablokowane) <n>
SPORTY:   hokej <n> · kosz <n> · siatka <n> · CS2 <n> nóg · <sport>: NOT_CALIBRATED / brak sport_fixtures.json
START:    FIXTURE_CHECK <OK | UNVERIFIED (brak mostka)> · FIXTURE_NOT_AS_SCHEDULED <n>
WETA:     <n> zastosowanych, <n> bez dopasowania
READS:    <n> (KEEP <n> / WATCH <n> / NO_BET <n>) · removed_by_reads <n> · UNMATCHED_READ <n> (poza sportami) · C3 <n>
CENA:     oferta z <ts>, wiek <n> min <"świeża" | "przeterminowana — to tłumaczy pustki">
ZMIANA:   <what moved and why — code, vetoes, reads, or the price>
```

## Hard rules

- A thin rebuild is not fixed by re-running it. If the day produced nothing,
  say so and **say which gate emptied it** - read the `refused` counts in the
  CONFIDENCE summary and in `08_confidence_sports.json`.
- `06_coupon.json` is not the coupon, and neither is `08_confidence.json`.
  The PDF is; `11_coupon.json` is what it prints.
- Never invent a price; never re-run SAMPLES here.
- Never print a combined / builder price outside what `confidence.py`
  computed.
- Never read, echo or log `.env` values.

Retired 2026-10-05: the WARIANT (refused from 07:15Z) and the separate sport
coupons with their assembly (from 08:30Z). A rebuild no longer builds them;
their files up to that morning stay as the historical record.
