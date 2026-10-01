---
description: Run one betting day end to end through the sofa pipeline (Sofascore + Superbet) - settle and record D-1 for every variant and sport, build the PDF coupon with the analysts' vetoes, the WARIANT, the four measured-sport coupons (CS2, hockey, basketball, volleyball) in parallel and WARIANT WSZYSTKIE, then verify all of it. This is the CURRENT pipeline; the simple one is archived in .claude/legacy.
argument-hint: dzisiaj | wczoraj | YYYY-MM-DD
---

Run one betting day through **`sofa`**, from nothing to the PDF coupon, and
verify it. Unattended: do not stop to ask permission between stages.

**Everything below is the default** (operator's order, 2026-09-30): every run
settles and records D-1 for every variant and every sport, builds the
coupon, the WARIANT, the four measured-sport coupons and WARIANT WSZYSTKIE,
and verifies all of them. A step is skipped only when the operator asked
for a bare run - and then the report names it as skipped.

| product | file | what it is |
|---|---|---|
| **KUPON** | `runs/sofa/<d>/KUPON_<d>.pdf` | **the coupon** (football + tennis) |
| WARIANT | `runs/sofa/<d>/KUPON_<d>_WARIANT.pdf` | operator's variant, 7d |
| CS2 / HOKEJ / KOSZYKOWKA / SIATKOWKA | `runs/sofa/cs2/<d>/KUPON_<d>_CS2.pdf`, `runs/sofa/shadow/{hockey,basketball,volleyball}/<d>/KUPON_<d>_{HOKEJ,KOSZYKOWKA,SIATKOWKA}.pdf` | price-only experiment per measured sport |
| WARIANT WSZYSTKIE | `runs/sofa/multi/<d>/KUPON_<d>_WSZYSTKIE.pdf` | the official PDF's printed singles and builders plus the four sport coupons' legs, verbatim, each at its own price (WARIANT is not in it) |
| ledger | `runs/sofa/ledger/results.jsonl` | every variant's and measurement's settled result, one row per (date, variant), including `rule:<sport>` and `measure:<sport>`; read with `audit_ledger.py`, per variant, never pooled |

None of the variants is the coupon, and no result is ever added to another.

`$ARGUMENTS` is `dzisiaj`/`today`, `wczoraj`/`yesterday` or `YYYY-MM-DD`;
empty means today (`date -u +%F`). On a day whose window has closed (06:00
Warsaw on D+1), `run_sport_coupon.py` and `run_multi_coupon.py` refuse with
exit 2 by design - say so and skip steps 4b and 4c; do not report them as
failures.

Delegate rather than doing it all inline. The agents exist and each carries the
measured history this command cannot restate:

| agent | when |
|---|---|
| `sofa-runner` | the whole run, if you want one owner for it |
| `sofa-settler` | step 1 — D-1 settlement, every variant recorded, the calibration loop (step 1b stays with you) |
| `sofa-analyst-football` / `sofa-analyst-tennis` | step 3 — the per-sport read and the vetoes |
| `sofa-sport-runner` ×4 | step 4b — one per measured sport, launched in ONE message so they run in parallel |
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
.venv/bin/python scripts/sofa/ensure_bridge.py      # brings it UP if it is down, then runs check_bridge.py
```

**Start the bridge first, every time** (operator's order, 2026-09-30).
`ensure_bridge.py` does nothing to a bridge that already polls. Otherwise it
starts `bridge_server.py` detached (log `runs/sofa/bridge_server.log`) and,
when Chrome is not running, opens the five windows with
`launch_bridge_browser.py`, then waits for a tab to poll and grades the
result with `check_bridge.py`. Exit 2 means it could not: most often Chrome
is already open without the anti-throttling flags - the operator must quit it
(Cmd+Q) and you re-run the step. Never quit or kill the operator's Chrome
yourself.

Exit 1: the bridge is up but degraded - check_bridge FAILed (server, tab or
Sofascore), or a tab polls from a Chrome started without the anti-throttling
flags (~1 req/s; the operator must Cmd+Q, then re-run). Exit 0 does not rule
out a WARN line: `check_bridge.py` exits 0 on WARN (stale poll, `burst probes
FAILED`, slow round trip), so read the poll-age line whatever the exit code.

Four checks now, and the fourth is advisory. The first three must be OK;
`ok: true` alone is not enough — a dead tab still reports ok, so the line that
matters is the poll age. If the tab is dead, stop and tell the operator:
nothing downstream of BOARD can run.

The fourth is **INFO and must not be read as a health grade.** It bursts four
requests from idle, and that cannot reach the regime a run works in: measured
2026-09-22, four idle probes read 0.10 req/s on exactly the bridge that then
sustained 8.64 req/s over 360 requests with zero non-200. A tab that finishes
a job and found nothing waiting went back into what was then a 20 s `/pull`
(1 s since 2026-09-23; 50 ms while a job is out since 2026-09-29). Only a
`WARN ... burst probes FAILED` line is a real fault.

If you need the capacity number, `scripts/sofa/measure_bridge_capacity.py`
gives it (it sends ~300 requests; run it deliberately, not as a check). Five
windows opened with `launch_bridge_browser.py` sustain ~14.3 req/s and do not
have to be visible - the old "three visible windows" rule is retired
(CLAUDE.md). Measured 2026-09-29 after the /pull fix: 14.63 req/s peak, p50
300-334 ms, zero non-200.

**Leave `SOFA_TARGET_RPS` (20) and `SOFA_MAX_CONCURRENCY` (5) at their
defaults.** The bucket must sit ABOVE the tabs' capacity - starving it is
worse than opening it - and the worker count equals the window count; below
it the bridge collapses (CLAUDE.md's table). **Never lower
`MIN_INTERVAL_MS`**: that is the per-connection pace.

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
today's run for the bridge. Hand it to `sofa-settler` (it settles and records
D-1; step 1b below stays with you, because the settler never touches today),
or run it directly:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only SETTLE
# CS2_SETTLE for D-1 is the D-1 cs2_daily loop's own 05:00Z step (and a cs2_watchdog.py retries it
# hourly, if one was started for that date - `pgrep -f cs2_watchdog`; nothing starts one by default).
# Run it by hand only when runs/sofa/cs2/daily_<D-1>.done exists or the pid in daily_<D-1>.pid
# is not running, and no watchdog covers D-1:
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only CS2_SETTLE
# SHADOW_SETTLE for D-1 is the D-1 loop's own 05:15Z step. Run it by hand only when no
# D-1 loop is alive - runs/sofa/shadow/daily_<D-1>.pid is gone (the loop deletes it on
# exit) or its pid is not running. It resumes, so a repeat is harmless; a concurrent one is not:
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only SHADOW_SETTLE
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settlement.py --date <D-1>
```

SHADOW / SHADOW_SETTLE are the hockey / basketball / volleyball measurement
(`src/bet/sofa/shadow.py`): Superbet's price against Sofascore's score, like
CS2. They write only `runs/sofa/shadow/<sport>/<date>/`, never feed the
coupon, and a PARTIAL or FAILED there never blocks the day. Report is
`audit_shadow.py --from <d> --to <d>`.

`PARTIAL` is the normal verdict (unfinished matches, provider stat gaps).
Read section 7c of the audit — that is the PDF coupon's real result. Sections
7 and 7b are input material, not bets. Section 7d is WARIANT's result, beside
7c, never pooled.

Then grade every variant of D-1 and record the day - this is the data every
later decision about a rule, a floor or a sport is taken from, so it runs
every day, not when someone remembers:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_sport_coupon.py --from <D-2> --to <D-1>   # the four sport coupons, at their printed prices; D-2 too: its legs after 00:00Z settle into D-1's file, graded only this morning
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_multi_coupon.py --from <D-2> --to <D-1>   # WARIANT WSZYSTKIE, section by section
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_shadow.py --from <D-1> --to <D-1>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_cs2.py --from <D-1> --to <D-1>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --from <D-2> --to <D-1>        # the ledger row of every variant and measurement; replaces both dates' rows
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py --from <D-7> --to <D-1>          # read the ledger: one table per variant, never pooled; ROI with its by-day 95% interval
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_clv.py --from <D-2> --to <D-1>             # closing line value per variant - read it first: it answers in tens of legs
```

Exit codes of `settle_sport_coupon.py`, `settle_multi_coupon.py` and
`record_results.py` (since 2026-09-30): **0** = graded as far as the settles
allow - pending legs are shown in the table's `pending` column, never as an
exit code. Pending is the normal shape of D-1: its sport-coupon legs after
00:00Z (NHL/NBA, night CS2) settle into today's snapshot file and are graded
at tomorrow's 05:00Z (`cs2_daily`) / 05:15Z (`shadow_daily`) morning steps -
each loop settles D and D-1, grades both days' sport coupons and records
both days in the ledger - and tomorrow's `--from <D-2>` closes them too.
**1** = a `MISMATCH` (the coupon's grader and the measurement's disagree on a
leg - a defect: name it) or an unreadable file (named in the table).
**2** = a crash, or for `record_results.py` a missing database (nothing is
written then).
Before SHADOW_SETTLE / CS2_SETTLE has written `settled.json`, a sport
coupon's legs read PENDING but `measure:<sport>` is simply absent from the
ledger, not pending - check every `measure:*` row is there, not only the exit
code. Re-run `record_results.py --from <D-2> --to <D-1>` after a late
settle; it replaces those dates' rows. A result is a fact about the day, never
a reason for today's choice.

## Step 1b — start today's measurement loops

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <today> --only CS2
# the whole CS2 day unattended (snapshots to 23:30Z, settle D and D-1 at 05:00Z D+1, grade both days' CS2 coupons,
# record both days); --chain starts D+1's loop at 23:30Z, so D+1's night series are priced. A D-1 loop started with
# --chain already started today's; a second loop for a date refuses (exit 2), so a repeat is harmless:
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/cs2_daily.py --date <today> --chain >> runs/sofa/cs2/daily_<today>.log 2>&1 &
# the shadow day runs itself once started (snapshots to 04:30Z next day, settle 05:15Z).
# A D-1 loop started with --chain starts today's by itself after its 05:15Z settle and audit (~05:20-05:45Z): start one by
# hand only when NEITHER runs/sofa/shadow/daily_<D-1>.pid NOR daily_<today>.pid exists
# (a second loop for a date refuses with exit 2, so a repeat is harmless):
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/shadow_daily.py --date <today> --chain >> runs/sofa/shadow/daily_<today>.log 2>&1 &
```

A loop reads its plan once, when it starts: a loop started before a code
change keeps its old morning steps until it ends (the `--chain` child it
starts runs the new code). After a change to `cs2_daily.py` / `shadow_daily.py`
re-run the new morning steps by hand for the days the old loops cover, and
say so in the report - never kill a loop to pick the change up.

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

Refresh OFFER first if the last one is over 45 minutes old; on a late
refresh run `run_offer.py` directly - `run_pipeline.py` does not take the flag
and exits 2 on it (checked 2026-09-29) - so the stage does not spend ~90
minutes re-pricing fixtures that have already been played:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_offer.py --date <date> --min-minutes-to-kickoff 20
```

```bash
# only if the last OFFER is older than 45 min; late in the day use run_offer.py --min-minutes-to-kickoff 20 (above) instead
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only OFFER
# after any OFFER refresh: rows whose price moved are refused (PRICE_MOVED_SINCE_SHEET)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only SHEET --run-id <id>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only COUPON
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <date>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <date>
# the operator's variant (floor 0.65, confidence x odds >= 0.90, margin <= 15%), beside the coupon, never instead of it
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <date> --profile wariant
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <date> --profile wariant
```

`picks: 0` is a legitimate answer and happens often: a builder needs
`best_for_fixture` **and** positive EV after the measured correlation haircut
(12%; measured range 8.8–19.6%). `ev_if_product_priced` being positive means
nothing on its own — Superbet does not price a slip as the product of its legs.

Read `stakeable_builders` from CONFIDENCE, not `builders`. Both numbers are
reported since 2026-09-21 precisely because they disagree.

Then start the closing-price capture for the printed legs (Superbet only, no
bridge; it exits by itself after the last leg starts), and take a boosts
snapshot - repeat `run_boosts.py` a few times during the day, boosts appear
and disappear:

```bash
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/capture_closing.py --date <date> --loop >> runs/sofa/<date>/capture_closing.log 2>&1 &
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_boosts.py --date <date>
```

CLV (`audit_clv.py`) is the first number to read about yesterday's printed
legs: it answers in tens of legs where ROI needs thousands.

## Step 4b — the four measured sports, in parallel

After the official PDF: WARIANT WSZYSTKIE (step 4c) needs it, and a sport
coupon built more than 6 h before the assembly is excluded from it
(`MAX_SOURCE_AGE`, `src/bet/sofa/multi_coupon.py`) - so build the sport
coupons close to 4c.

First refresh the prices once so the three shadow runners do not each
refetch the same board (Superbet only, no bridge):

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_shadow.py --date <date> --horizon-h 24
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only CS2
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D+1> --only CS2    # night series belong to <date>'s coupon
```

Then launch all four in ONE message so they run concurrently:

```
Task -> sofa-sport-runner  "sport cs2; date <date>; prices refreshed at <HH:MM>Z"
Task -> sofa-sport-runner  "sport hockey; date <date>; prices refreshed at <HH:MM>Z"
Task -> sofa-sport-runner  "sport basketball; date <date>; prices refreshed at <HH:MM>Z"
Task -> sofa-sport-runner  "sport volleyball; date <date>; prices refreshed at <HH:MM>Z"
```

Run all four in the foreground (`run_in_background: false`) and wait for
every one before step 4c.

Each runner builds its sport's coupon, reads every leg, writes vetoes that
only remove, and reports. Check their numbers against the files (md5, leg
count, drop counts) before you quote them.

## Step 4c — WARIANT WSZYSTKIE

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_multi_coupon.py --date <date>
```

It assembles, it does not select: the official PDF's printed singles and
builders, and each sport coupon's legs, verbatim. A section whose source is
stale or missing is printed as excluded with its reason; that, or no single
at all, is exit 1 (PARTIAL). The official section is also refused when
`08_confidence.json` is older than `05_sheet.json` / `vetoes.json` or
`KUPON_<d>.pdf` is older than it (`STALE_CONFIDENCE` /
`PDF_OLDER_THAN_ARTIFACT`). **Any later
rebuild of the official PDF or of a sport coupon makes it stale - re-run this
step after it** (`audit_variants.py` M2 says so). A sport coupon built more
than 6 h before the assembly is excluded (`STALE`): after a late official
rebuild, rebuild the sport coupons (sofa-sport-runner) and then re-assemble.

## Step 5 — verify, and do not skip this

Hand the day to `sofa-verifier`. Its protocol is
`docs/sofa/VERIFY_PROTOCOL.md`, and it starts with:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <date>
```

and, for everything beside the coupon:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <date>
```

which re-derives the four sport coupons from their raw snapshots (every
price, every devig, the selection replayed at build time) and checks that
WARIANT WSZYSTKIE is still exactly what its sources print. Any finding is a
defect to fix before the day is reported, not a note. Exit 0 no findings, 1
findings, 2 a file could not be read. Lines under `notes (not defects):` are
locked sport legs that cannot be re-verified (`UNVERIFIABLE`): not findings
and not a pass - list them in the report.

`audit_variants` C1/C2 also check the official coupon and WARIANT
(`08_confidence[_wariant].json`): the artifact is fresh and of its profile,
its PDF prints it, and every printed single obeys the dials it was built
with. `audit_coupon` never opens WARIANT and no script re-derives its legs
from the samples, so still hand `08_confidence_wariant.json` /
`KUPON_<d>_WARIANT.pdf` to `sofa-verifier` explicitly and name it in the
prompt.

`audit_coupon.py` covers structure and arithmetic **from each row's own fields**. It cannot
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
WARIANT:  runs/sofa/<date>/KUPON_<date>_WARIANT.pdf — <n> pozycji (NIE kupon; 0.65 / x ≥ 0.90)
SHEET:    <n> wierszy, <n> VALUE (<n> piłka / <n> tenis)
RUN:      <run_id> · <verdict> · <n> na tablicy → <n> dopasowanych → <n> READY
WETA:     <n> zastosowanych, <n> bez dopasowania
SETTLE:   D-1 <n> wierszy, PDF-kupon <w>/<n> slipów
POMIAR:   D-1 CS2 <n> serii / hokej <n> / kosz <n> / siatka <n> rozliczonych — pomiar, NIE kupon
SPORTY:   CS2 <n> / HOKEJ <n> / KOSZ <n> / SIATKA <n> pozycji (NIE kupon; cena bez marży, bez modelu); weta <n>
WSZYSTKIE: runs/sofa/multi/<date>/KUPON_<date>_WSZYSTKIE.pdf — <n> pozycji, sekcje <k>/5 (wyłączone: <…>)
D-1 WYNIKI: kupon <u> j. · WARIANT <u> j. · sporty <u>/<u>/<u>/<u> j. · WSZYSTKIE <u> j. (każdy osobno, nigdy sumowane) · pomiar fair p vs trafione per sport → ledger · reguła CS2/HOKEJ/KOSZ/SIATKA <u> j. · MISMATCH <n> (audit_ledger.py)
CLV D-1:    kupon <x%> [lo; hi] · WARIANT <x%> · sporty <x%>/<x%>/<x%>/<x%> (audit_clv.py; każdy osobno)
AUDYT WARIANTÓW: <n> znalezisk
WERYFIKACJA: <n>/<n> arytmetyka, <n>/<n> ceny na żywo, <n> pozycji odrzuconych
UWAGA:    <the day's single biggest weakness>
```

## Hard rules

- Never invent a number, a fixture or an odds quote.
- Never print a combined/parlay price outside what `confidence.py` computed.
- No stake sizing, no automated placement.
- Never read, echo or log `.env` values.
