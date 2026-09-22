---
description: Run one betting day end to end through the sofa pipeline (Sofascore + Superbet), take the analysts' vetoes, and produce the PDF coupon. This is the CURRENT pipeline; the simple one is archived in .claude/legacy.
argument-hint: dzisiaj | wczoraj | YYYY-MM-DD
---

Run one betting day through **`sofa`**, from nothing to the PDF coupon, and
verify it. Unattended: do not stop to ask permission between stages.

Delegate rather than doing it all inline. The agents exist and each carries the
measured history this command cannot restate:

| agent | when |
|---|---|
| `sofa-runner` | the whole run, if you want one owner for it |
| `sofa-settler` | step 1 — D-1 settlement and the calibration loop |
| `sofa-analyst-football` / `sofa-analyst-tennis` | step 3 — the per-sport read and the vetoes |
| `sofa-verifier` | step 5 — adversarial verification. **Not optional.** |
| `sofa-market-scout` | when a row's availability or price is in question |

## Read this first — there is no DISCOVER stage

`sofa` does not share stage names with the archived `simple` pipeline, and
reaching for `simple`'s vocabulary is the single most common way to start this
wrong. The source of truth is `DEFAULT_SEQUENCE` in
`scripts/sofa/run_pipeline.py`.

| # | sofa stage | what it actually is | artifact |
|---|---|---|---|
| E3 | **BOARD** | the day's fixtures, from Superbet's board. This is "discovery". One HTTP request, no Sofascore. | `01_board.json` |
| E4 | **RESOLVE** | attach a Sofascore event id to each board fixture | `02_fixtures.json` |
| E5 | **OFFER** (1st) | which markets carry a price at all, so SAMPLES only pays for those | `04_offer.json` |
| E6 | **SAMPLES** | each side's last N matches per metric | `03_samples.json` |
| E5 | **OFFER** (2nd) | refresh: the price the bar is measured against | `04_offer.json` |
| E8 | **SHEET** | every rung priced: `p_central`, `p_bar`, verdict | `05_sheet.json` |
| E9 | **COUPON** | VALUE singles, with every exclusion recorded | `06_coupon.*`, `06_dropped.json` |
| — | **CONFIDENCE** | Bet Builders ranked by measured reliability | `08_confidence.*` |
| — | **PDF** | **the coupon the operator stakes** | `KUPON_<date>.pdf` |
| E10 | **SETTLE** | grade a finished day (D-1, never today) | `07_settled.json` |

**OFFER runs twice on purpose.** Once before SAMPLES so sampling is not paid
for markets nobody prices, once after so the bar meets a fresh price.

**The PDF is the coupon.** `06_coupon.json` holds VALUE singles, and that
selector's measured record is bad — it returned −20.4% on 2026-09-20 while the
PDF's Bet Builders returned +8.2% the same day. Reporting `06_coupon` as "the
coupon" inverts the day.

## Step 0 — the bridge, before anything else

Sofascore answers 403 to every non-browser client. Everything except BOARD
goes through a real browser tab.

```bash
.venv/bin/python scripts/sofa/check_bridge.py
```

Four checks now, and the fourth is advisory. The first three must be OK;
`ok: true` alone is not enough — a dead tab still reports ok, so the line that
matters is the poll age. If the tab is dead, stop and tell the operator:
nothing downstream of BOARD can run.

The fourth is **INFO and must not be read as a health grade.** It bursts four
requests from idle, and that cannot reach the regime a run works in: measured
2026-09-22, four idle probes read 0.10 req/s on exactly the bridge that then
sustained 8.64 req/s over 360 requests with zero non-200. A tab that finishes
a job and finds nothing waiting goes back into a 20 s `/pull`. Only a
`WARN ... burst probes FAILED` line is a real fault.

If you need the capacity number, `scripts/sofa/measure_bridge_capacity.py`
gives it. A genuinely low sustained figure means the windows are not visible —
three tabs in ONE window is one working tab, since only the active tab counts
as visible.

**Set `SOFA_TARGET_RPS` from `scripts/sofa/measure_bridge_capacity.py`, never
above the plateau it reports** — 3.9 req/s on three tabs (2026-09-22, 360
requests, zero non-200). Above the plateau the queue grows, not the throughput.
**Never lower `MIN_INTERVAL_MS`**: that is the per-connection pace.

Check the tabs before blaming the rate. A tab Chrome has throttled answers the
same routes in ~2,000 ms instead of ~175 ms and takes ~40 s to claim a job;
`check_bridge.py` warns above 600 ms. One overnight run paid ~5.3 hours for it.

## Step 0b — use the right interpreter

`.venv` contains **two** interpreters. `.venv/bin/python` is 3.12 and runs the
pipeline; `.venv/bin/pip` belongs to 3.14. Installing with `.venv/bin/pip`
reports success and the import still fails.

```bash
.venv/bin/python -m pip install <pkg>     # correct
.venv/bin/pip install <pkg>               # lands in 3.14, invisible to the run
```

## Step 1 — settle yesterday

Do this before today's run: it is what feeds calibration, and it competes with
today's run for the bridge. Hand it to `sofa-settler`, or run it directly:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only SETTLE
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settlement.py --date <D-1>
```

`PARTIAL` is the normal verdict (unfinished matches, provider stat gaps).
Read section 7c of the audit — that is the PDF coupon's real result. Sections
7 and 7b are input material, not bets.

## Step 2 — today

BOARD touches only Superbet, so it can run while SETTLE is still going.

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only BOARD --run-id <id>
# once SETTLE is done:
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --from-stage RESOLVE --run-id <id>
```

Budget **2.5–3 h**. SAMPLES is most of it. Monitor stage transitions rather
than polling:

```bash
tail -f -n 0 <log> | grep -E "^--- |: OK|: PARTIAL|: FAILED|STAGE_EXCEPTION|Traceback"
```

`PARTIAL` on RESOLVE / OFFER / SAMPLES is the **normal shape of a healthy run**,
not a failure. Only `FAILED` stops you.

## Step 3 — the analysts, and the vetoes

`vetoes.json` is read by **COUPON and CONFIDENCE both**, so the analysts run
after SHEET and the day is rebuilt afterwards. Launch both in one message so
they run concurrently:

```
Task -> sofa-analyst-football   "date <date>; run <run_id>; stage verdicts; <n> football VALUE"
Task -> sofa-analyst-tennis     "date <date>; run <run_id>; stage verdicts; <n> tennis VALUE"
```

Merge their JSON arrays into `runs/sofa/<date>/vetoes.json`, **validating
first** — a malformed entry fails the whole file and the stage then runs with
no vetoes at all and reports zero. Report any `UNMATCHED_VETO`: it did nothing,
and a silent no-op reads exactly like a veto that was honoured.

An empty `vetoes.json` is the healthy default. On most days it is `[]`.

Skip this step only if the operator asked for a bare run — and then say you
skipped it.

## Step 4 — rebuild, confidence and the PDF

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only OFFER
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only COUPON
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <date>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <date>
```

Refresh OFFER first if the last one is over 45 minutes old; on a late refresh
pass `--min-minutes-to-kickoff` so the stage does not spend ~90 minutes
re-pricing fixtures that have already been played.

`picks: 0` is a legitimate answer and happens often: a builder needs
`best_for_fixture` **and** positive EV after the measured correlation haircut
(12%; measured range 8.8–19.6%). `ev_if_product_priced` being positive means
nothing on its own — Superbet does not price a slip as the product of its legs.

Read `stakeable_builders` from CONFIDENCE, not `builders`. Both numbers are
reported since 2026-09-21 precisely because they disagree.

## Step 5 — verify, and do not skip this

Hand the day to `sofa-verifier`. Its protocol is
`docs/sofa/VERIFY_PROTOCOL.md`, and it starts with:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <date>
```

That covers structure and arithmetic **from each row's own fields**. It cannot
catch a row whose fields are all mutually consistent and all built on the
wrong sample, which is why the agent then rebuilds from `03_samples.json`,
re-checks that `subject` maps to the side it claims, re-asks Superbet for every
leg's live price through `OfferFetcher`, and tests the day's distributions for
anti-selection.

## Traps that have actually cost something

- **`06_coupon.json` is not the coupon.** The PDF is.
- **Anti-selection is structural.** `coupon.py` ranks on relative price
  advantage (`surplus / required_odds`), and surplus grows as `p` is
  overstated, so the rows most likely to be wrong are the rows most likely to
  be picked. A surplus above +0.40 is suspect *by definition*. Take every one
  apart by hand.
- **Half-match football rows lean on a global prior.** At `K_CENTRE = 25` a
  sample of n=8 contributes 24% of its own centre. Before trusting a
  `*_1h_*` / `*_2h_*` row, compute `n/(n+25)`.
- **`coverage_floor` is weekday-blind.** Its median is built from recent runs,
  so a Monday slate (~100 football fixtures against a weekend's ~1000) trips
  "matching regression" every time. Check the RESOLVE rate instead — 72–90% is
  normal — before believing it.
- **Clock disagreement is tennis and structural.** Superbet posts a nominal
  "not before" time for ITF matches, Sofascore the real one; gaps to 11 h are
  normal and `CONFIRMED`. `coupon.py` takes the **earlier** of the two, which
  conservatively refuses some un-started matches. That is deliberate.
- **Subagent numbers need verification.** They have been wrong in ways that
  inverted an argument. Check any claim you can check locally.
- **Constants are fitted deliberately, not daily.** `fit_constants.py` (E11) is
  not in `DEFAULT_SEQUENCE`. Re-fitting mid-day breaks comparability with
  yesterday. But **do** check `config/sofa_league_baselines.json`'s
  `fitted_from` and `half_match_coherence` — a stale baselines file shipped a
  corners prior 24–32% too high for two days before anyone noticed.

## Report back, short

```
KUPON:    runs/sofa/<date>/KUPON_<date>.pdf — <n> pozycji
SHEET:    <n> wierszy, <n> VALUE (<n> piłka / <n> tenis)
RUN:      <run_id> · <verdict> · <n> na tablicy → <n> dopasowanych → <n> READY
WETA:     <n> zastosowanych, <n> bez dopasowania
SETTLE:   D-1 <n> wierszy, PDF-kupon <w>/<n> slipów
WERYFIKACJA: <n>/<n> arytmetyka, <n>/<n> ceny na żywo, <n> pozycji odrzuconych
UWAGA:    <the day's single biggest weakness>
```

## Hard rules

- Never invent a number, a fixture or an odds quote.
- Never print a combined/parlay price outside what `confidence.py` computed.
- No stake sizing, no automated placement.
- Never read, echo or log `.env` values.
