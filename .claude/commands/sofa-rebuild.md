---
description: "Rebuild one sofa day's coupon (11_coupon.json) and PDF from the artifacts on disk with the one command scripts/sofa/rebuild_day.py - stale prices first, then FIXTURE_CHECK .. PDF and the audits; no SAMPLES. Use after a code change, new vetoes / reads / read requests, or a stale offer."
argument-hint: "dzisiaj | wczoraj | YYYY-MM-DD"
---

Rebuild `KUPON_<date>.pdf` from artifacts that already exist. RESOLVE and SAMPLES never
run here. Sofascore is asked only by FIXTURE_CHECK (one `/event` per printed match) and by
SPORT_IDENTITY after a fresh sport snapshot; Superbet only when the plan refreshes a price.
Do not stop to ask.

Python: `PYTHONPATH=src:. .venv/bin/python`.

## 0. The day and its inventory

`$ARGUMENTS`: `dzisiaj`/`today`, `wczoraj`/`yesterday`, `YYYY-MM-DD`; empty = today (UTC).

```bash
ls -la runs/sofa/<date>/
```

- No `05_sheet.json` or no `02_fixtures.json` -> nothing to rebuild; the day needs
  `/sofa-day`. Say so and stop.
- `04_offer.json` is required by CONFIDENCE. `vetoes.json` (`[]` is healthy), `reads.json`,
  `read_requests.json` are optional; write them only through `merge_reads.py` /
  `/sofa-analyze`, never by hand.
- Never rebuild, re-PDF or re-read **2026-10-08** (built under the old estimator).
- A rebuild reads `bet.sofa.epochs` on the day built AND the clock, and `config/` as it is
  now: after a refit install or the morning's `refresh_line_evidence.py` the same day prints
  under the new curves / evidence - say so in ZMIANA. Legs locked from an earlier print keep
  what they were printed under.

State the date, the files and their ages.

## 1. The plan

Never run the stage scripts by hand for a rebuild (a CONFIDENCE on a >45 min offer empties
08 to the locked legs; a SHADOW with its default horizon leaves late games stale).

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <date> --dry-run
```

It reads file ages and the clock (`bet.sofa.rebuild_plan`, no network) and prints each step
with its reason:

| step | when |
|---|---|
| OFFER (`--min-minutes-to-kickoff 20`) | an open fixture's price would pass CONFIDENCE's 45 min before it runs; a moved price re-prices the leg, no SHEET |
| SHADOW (horizon to the farthest open start) / CS2 | a sport price nears `sport_day.MAX_PRICE_AGE` (3 h), or SHADOW skipped an event beyond its horizon |
| `ensure_bridge.py` + SPORT_IDENTITY | after a fresh snapshot, or `sport_fixtures.json` missing |
| SHEET | the sheet is not stats-only, rated under the old link rule, or lacks the row marker / row of a switch now on |
| COUPON (06, `audit_coupon`'s input, not the coupon) | older than sheet / vetoes / reads |
| then always | `ensure_bridge.py`, FIXTURE_CHECK, CONFIDENCE, SPORT_CONFIDENCE, COUPON_ASSEMBLY, PDF, `audit_variants.py`, `audit_coupon.py` |

**SHEET by hand.** The plan never re-runs SHEET for a SHEET code change or a config SHEET
reads (`CONFIG_CHANGED` note: an install never enters a built day without the operator's
go). When one applies and is approved, run it first and name the cause (~30 s cached, up to
~10 min when listings changed; do not kill a quiet SHEET):

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only SHEET --run-id <id>
```

A day that is over refreshes no price (`DAY_OVER` in the notes): every gate refuses its
historical prices - correct, report it.

## 2. Rebuild

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <date>
```

One line per step (post them as they come); full output in
`runs/sofa/<date>/rebuild_<ts>.log` (read it with `grep` / `tail`), a final `SOFA_SUMMARY`
(`stage: REBUILD`). Exit 0 / 1 PARTIAL / 2 FAILED. A FAILED step stops the rest except the
bridge steps, the sport snapshots and COUPON (06), which make it PARTIAL. `--skip-audits`
leaves the audits out and says so - a skipped audit is not a passed one.

- FIXTURE_CHECK: no bridge = `UNVERIFIED`, nothing refused (say so); a postponed / cancelled
  printed match is `FIXTURE_NOT_AS_SCHEDULED`; a 403 stops it - never retry into a refusal.
- Locked legs (`12_printed.json`, match started) stay as printed, first and unnumbered; a leg
  removed before its start stays removed. Not a defect.
- `build_coupon_pdf.py` refuses `STALE_CONFIDENCE` / `STALE_COUPON`: fix the cause and re-run
  the whole rebuild, never only the PDF.
- SPORT_CONFIDENCE exit 1 = a sport `NOT_CALIBRATED` or without `sport_fixtures.json`;
  the rest builds - name the sport.
- Report every `UNMATCHED_VETO` / `UNMATCHED_READ` / `UNMATCHED_READ_REQUEST` line; a sport
  read is `reads_sport` and acts in COUPON_ASSEMBLY.
- A thin coupon is not fixed by re-running: name the gate that emptied it (`refused`
  counts).

Never run `refresh_line_evidence.py`, `prepare_refit.py` or a `fit_*` in a rebuild.

## 3. Audits and reads

`audit_variants` (C1-C3, U1-U3) and `audit_coupon` must be clean. A C3 finding (a moved
position put an unread leg into the read set) goes to `/sofa-analyze`'s C3 loop
(`read_set.py --date <date> --unread --split 12`), not its whole pass. Then hand the day to `/sofa-verify` unless the operator asked for
a bare rebuild.

## Report

```
EPOKA:    <stats_only | old> · ZMIANA config: <krzywe / dowody linii / brak>
KUPON:    runs/sofa/<date>/KUPON_<date>.pdf — <n> pozycji (było <n>) · buildery <n> · zablokowane <n>
SPORTY:   hokej <n> · kosz <n> · siatka <n> · CS2 <n> nóg · <sport>: NOT_CALIBRATED / brak sport_fixtures.json
START:    FIXTURE_CHECK <OK | UNVERIFIED> · FIXTURE_NOT_AS_SCHEDULED <n>
READS:    weta <n> (bez dopasowania <n>) · KEEP/WATCH/NO_BET <n/n/n> · removed_by_reads <n> · UNMATCHED_READ <n> · C3 <n>
CENA:     oferta z <ts>, wiek <n> min
ZMIANA:   <co się ruszyło i dlaczego — kod, weta, odczyty, cena>
```

## Hard rules

- `11_coupon.json` / the PDF is the coupon; `06_coupon.json` and `08_confidence.json` are not.
- Never invent a price; never re-run SAMPLES here; never print a combined / builder price.
