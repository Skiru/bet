---
description: Run one betting day end to end through the sofa pipeline (Sofascore + Superbet) - settle and record D-1 (every sport, the ledger, the settle identity audit), build the one stats-only coupon of every sport (football, tennis, and since 2026-10-05 08:30Z hockey, basketball, volleyball and CS2) into 11_coupon.json and KUPON_<date>.pdf, with the analysts' reads on the best 30 positions and every printed builder leg, then verify it. This is the only pipeline in the repository.
argument-hint: dzisiaj | wczoraj | YYYY-MM-DD
---

Run one betting day through **`sofa`**, from nothing to the PDF coupon, and
verify it. Unattended: do not stop to ask permission between stages.

**Everything below is the default** (operator's order, 2026-09-30, reshaped
by the plan of 2026-10-05, `docs/sofa/history/PLAN_2026-10-05_SETTLE_I_KUPON.md`):
every run settles and records D-1, builds the one coupon of every sport,
has its best 30 positions read, and verifies it. A step is skipped only when
the operator asked for a bare run - and then the report names it as skipped.

| product | file | what it is |
|---|---|---|
| **KUPON** | `runs/sofa/<d>/KUPON_<d>.pdf` | **the coupon** - every sport, one artifact |
| coupon artifact | `runs/sofa/<d>/11_coupon.json` | what the PDF prints: positions 1..N in `coupon_order`, locked legs first, builders B1.., `removed_by_reads` |
| print record | `runs/sofa/<d>/12_printed.json` | written by the PDF; the next rebuild locks the started legs from it |
| ledger | `runs/sofa/ledger/results.jsonl` | every variant's and measurement's settled result, one row per (date, variant): `official`, `official:pre_stats_only`, `removed:reads`, `rule:<sport>`, `measure:<sport>`; read with `audit_ledger.py`, per variant and per epoch, never pooled |

`06_coupon.json` (the priced VALUE selector) and `08_confidence.json` (the
football / tennis selection) are inputs, not the coupon.

**The day's rule** (stats-only epoch, `bet.sofa.epochs.STATS_ONLY_FROM_UTC`
2026-10-05 07:15Z; the measured sports from `SPORTS_ON_COUPON_FROM_UTC`
08:30Z): confidence comes from the statistics alone; the price is only the
condition - confidence x odds >= 0.90, ladder / group margin <= 15%, odds
>= 1/0.9202, not started, a fresh price; floor 0.70; WATCH honoured. Each leg
prints three numbers: **pewność** (calibrated confidence), **próbka** (k/n of
its own sample) and **model** (`forecast_p`, uncalibrated, never a gate).
Order: confidence, then the earlier start, the legs of one match together.

Retired 2026-10-05 (history only): WARIANT and WARIANT WSZYSTKIE (refused
from 07:15Z), the four separate per-sport experimental coupons and their
four parallel runner agents (refused from 08:30Z). Their files up to the
morning of 10-05 stay and are graded as before; nothing builds them again.

`$ARGUMENTS` is `dzisiaj`/`today`, `wczoraj`/`yesterday` or `YYYY-MM-DD`;
empty means today (`date -u +%F`).

Delegate rather than doing it all inline. The agents exist and each carries the
measured history this command cannot restate:

| agent | when |
|---|---|
| `sofa-runner` | the whole run, if you want one owner for it |
| `sofa-settler` | step 1 — D-1 settlement, the identity audit, the ledger, the calibration loop (step 1b stays with you) |
| `sofa-analyst-football` / `sofa-analyst-tennis` | step 5 — the read of their sport's legs in the best 30 positions + builder legs + `read_requests.json`: vetoes and one read (KEEP / WATCH / NO_BET) per leg |
| `sofa-analyst-sport` | step 5 — one per measured sport with legs to read (hockey, basketball, volleyball, CS2): identity, price, context; one read per leg, with its side and period |
| `sofa-verifier` | step 8 — adversarial verification; its rows-not-to-stake come back as reads and the day is rebuilt on them. **Not optional.** |
| `sofa-market-scout` | when a row's availability or price is in question |

## Read this first — there is no DISCOVER stage

`sofa` does not share stage names with the archived `simple` pipeline, and
reaching for `simple`'s vocabulary is the single most common way to start this
wrong. The source of truth is `DEFAULT_SEQUENCE` in
`scripts/sofa/run_pipeline.py` (BOARD, RESOLVE, OFFER, SAMPLES, OFFER, SHEET,
COUPON); everything after COUPON is run by name, outside the sequence.

| # | sofa stage | what it actually is | artifact |
|---|---|---|---|
| E3 | **BOARD** | the day's fixtures, from Superbet's board. This is "discovery". One HTTP request, no Sofascore. | `01_board.json` |
| E4 | **RESOLVE** | attach a Sofascore event id to each board fixture | `02_fixtures.json` |
| E5 | **OFFER** (1st) | which markets carry a price at all, so SAMPLES only pays for those | `04_offer.json` |
| E6 | **SAMPLES** | each side's last N matches per metric | `03_samples.json` |
| E5 | **OFFER** (2nd) | refresh: the latest price, the betting condition | `04_offer.json` |
| E8 | **SHEET** | every rung: `p_central` from the statistics (stats-only), `forecast_p`; the priced `p_bar` / verdict beside it | `05_sheet.json` |
| E9 | **COUPON** | the old priced VALUE singles, with every exclusion recorded - not the coupon | `06_coupon.*`, `06_dropped.json` |
| — | **CONFIDENCE** | football / tennis singles and Bet Builders by calibrated confidence (`run_confidence.py`) | `08_confidence.*` |
| — | **SHADOW** / **CS2** | fresh Superbet snapshots of the measured sports (Superbet only) | `runs/sofa/shadow/<sport>/<d>/`, `runs/sofa/cs2/<d>/` |
| — | **SPORT_IDENTITY** | the Sofascore id of every measured-sport event, pinned before the start (bridge) | `sport_fixtures.json` |
| — | **SPORT_CONFIDENCE** | the measured sports' legs, confidence from the score model / CS2 engine calibrated without prices | `08_confidence_sports.json` |
| — | **FIXTURE_CHECK** | in a rebuild: is a printed match still the match RESOLVE froze - status and a fresh start (bridge) | `fixture_status.json` |
| — | **COUPON_ASSEMBLY** | the one coupon of every sport (`build_coupon.py`) | `11_coupon.json` |
| — | **PDF** | **the coupon the operator stakes** | `KUPON_<date>.pdf`, `12_printed.json` |
| E10 | **SETTLE** | grade a finished day (D-1, never today) | `07_settled.json`, `07_settled_printed.json` |

**OFFER runs twice on purpose.** Once before SAMPLES so sampling is not paid
for markets nobody prices, once after so the condition meets a fresh price.

**The PDF is the coupon.** `06_coupon.json` holds the old priced VALUE
singles, and that selector's measured record is bad — it returned −20.4% on
2026-09-20 while the PDF returned +8.2% the same day. Reporting `06_coupon` as
"the coupon" inverts the day. `p_bar`, `required_odds` and surplus are that
selector's priced arithmetic; none of them is the confidence.

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
# was every settled match the match it claims to be (offline; exit 1 = a finding, all listed):
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settle_identity.py --from <D-1> --to <D-1>
# Statistic gaps close days later (2026-10-01): Sofascore publishes a lower league's corners/shots/fouls
# days after the cards, and the cache re-asks only a match >= 4 days old - so re-settle D-5 every morning
# (inserts only the rows that were missing) and correct rows graded off an early snapshot:
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_settle.py --date <D-5> --refetch-stat-gaps
PYTHONPATH=src:. .venv/bin/python scripts/sofa/regrade_settled.py --apply
```

SHADOW / SHADOW_SETTLE and CS2 / CS2_SETTLE stay a measurement of
Superbet's price against Sofascore's score (`src/bet/sofa/shadow.py`,
`src/bet/sofa/cs2.py`), written into `runs/sofa/shadow/<sport>/<date>/` and
`runs/sofa/cs2/<date>/`. Since 2026-10-05 08:30Z they are also what the
coupon's measured-sport legs are priced from and graded by - against the
Sofascore id SPORT_IDENTITY pinned before the match (a different id is
`NOT_GRADED:ID_CHANGED`). A PARTIAL or FAILED there never blocks the day.
Report is `audit_shadow.py --from <d> --to <d>` / `audit_cs2.py`.

`PARTIAL` is the normal verdict (unfinished matches, provider stat gaps).
Read section **7c** of the audit — that is the PDF coupon's real result: on
a stats-only day one table per sport and epoch, the measured sports' own
table graded at the printed price, and the coupon's sum. A match moved more
than 48 h (`MOVED_BEYOND_VOID`) or awarded (`AWARDED`) is a **refund** (0
units, its own count) - never a loss and never a `sofa_settled_row`. A
printed leg without a sheet row is graded into `07_settled_printed.json`.
Section **7i** grades the legs a read removed (`removed_by_reads`) - apart,
never in the coupon's result. Sections 7 and 7b are input material, not bets.

Then record the day - this is the data every later decision about a rule,
a floor or a sport is taken from, so it runs every day, not when someone
remembers:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_shadow.py --from <D-1> --to <D-1>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_cs2.py --from <D-1> --to <D-1>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --from <D-8> --to <D-1>        # the ledger row of every variant and measurement; replaces those dates' rows
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py --from <D-7> --to <D-1>          # one table per variant and epoch group, never pooled; ROI with its by-match 95% interval ("-" under 20 matches)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_clv.py --from <D-2> --to <D-1>             # closing line value per variant - read it first: it answers in tens of legs
```

The ledger's variants on a stats-only day: `official` (the coupon, every
sport), `official:pre_stats_only` (legs locked from the 10-05 morning print -
a different experiment), `removed:reads` (7i). `audit_ledger.py` keeps the
epoch groups apart (10-04 / 10-05 rano / stats_only) and never sums them.

Exit codes of `record_results.py`: **0** = graded as far as the settles
allow - pending legs are shown in the table's `pending` column, never as an
exit code. Pending is the normal shape of D-1: its measured-sport legs after
00:00Z (NHL/NBA, night CS2) settle into today's snapshot file at the
05:00Z (`cs2_daily`) / 05:15Z (`shadow_daily`) morning steps, and tomorrow's
`--from <D-8>` closes them. **1** = a `MISMATCH` (two graders disagree on a
leg - a defect: name it) or an unreadable file. **2** = a crash or a missing
database (nothing is written then). Before SHADOW_SETTLE / CS2_SETTLE has
written `settled.json`, `measure:<sport>` is simply absent from the ledger,
not pending - check every `measure:*` row is there, not only the exit code.
Re-run `record_results.py --from <D-8> --to <D-1>` after a late settle or a
`regrade_settled.py`. A result is a fact about the day, never a reason for
today's choice.

Historical, until 2026-10-13 (while D-8 still reaches 2026-10-05): the
retired variants of days up to the 10-05 morning are graded by their own
scripts and recorded under their old ledger names - the daily loops run
those steps for their days; by hand only for a date a loop did not cover:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_sport_coupon.py --from <D-8> --to <D-1>   # retired 2026-10-05 08:30Z: old days' per-sport coupons only
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_multi_coupon.py --from <D-8> --to <D-1>   # retired 2026-10-05 07:15Z: old days' WSZYSTKIE only
```

## Step 1b — start today's measurement loops

The loops snapshot the measured sports' prices all day (the coupon's
measured-sport legs are priced from those snapshots) and settle them the
next morning.

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <today> --only CS2
# the whole CS2 day unattended (snapshots to 23:30Z, settle D and D-1 at 05:00Z D+1, grade and
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
RESOLVE cannot: start it when the WHOLE of step 1 has returned, not when
the `--only SETTLE` process ends - on 2026-10-01 RESOLVE died on
`database is locked` while the settler's later scripts read the database
(the DB is in WAL mode since that day and a busy commit is retried, so this
is a second line of defence, not the only one).

A FAILED stage now stops the stages after it (`SKIPPED`, their artifacts
untouched) and a RESOLVE that died leaves `02_fixtures.json.INCOMPLETE`,
which every later stage refuses with `UPSTREAM_INCOMPLETE`. Re-run from the
failed stage; `--continue-on-failure` exists for a deliberate exception.

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only BOARD --run-id <id>
# once step 1 (the whole settler) is done:
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --from-stage RESOLVE --run-id <id>
```

Budget **2.5–3 h**. SAMPLES is most of it. Monitor stage transitions rather
than polling:

```bash
tail -f -n 0 <log> | grep -E "^--- |: OK|: PARTIAL|: FAILED|STAGE_EXCEPTION|Traceback"
```

`PARTIAL` on RESOLVE / OFFER / SAMPLES is the **normal shape of a healthy run**,
not a failure. Only `FAILED` stops you.

## Step 3 — CONFIDENCE, football and tennis (provisional)

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <date>
```

It refuses (exit 2) a `05_sheet.json` not built under the stats-only rule -
then the SHEET is the old rule's and the day is rebuilt from SHEET. Report
from its summary the `refused` counts, among them `WATCHED`, `READ_NO_BET`,
`MODEL_ABOVE_OWN_SAMPLE` (a football leg whose `model_p` is more than 0.15
above its own sample's hit rate - automatic, no read needed),
`FIXTURE_NOT_AS_SCHEDULED`, `KICKED_OFF`, `STALE_PRICE`, `ODDS_TOO_LOW`, and
every `UNMATCHED_VETO` / `UNMATCHED_READ` line on stderr.

**Do not render a PDF from a provisional build.** A rebuild locks (keeps as
printed, `locked: true`, unnumbered, first) the legs of the last PRINTED
coupon whose match has started - read from `12_printed.json`, which only the
PDF writes. A provisional PDF would turn every leg in it into a counted bet
the moment its match starts, read or not. Locked legs, and
`LOCKED_DESPITE_LATE_REFUSAL` lines on stderr, are the operator's rule
working, not a defect.

## Step 4 — the measured sports, then the one coupon

Fresh prices first (Superbet only, no bridge) - the sport legs are priced
from the newest pre-start snapshot and refused as `STALE_PRICE` past
`sport_coupon.MAX_PRICE_AGE`; night games live in D+1's file:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only SHADOW
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only CS2
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D+1> --only CS2
```

Then pin each event's Sofascore id before it starts (bridge: one request
per match, once a day, after `ensure_bridge.py`; a 403 stops the run, never
retried; a re-run asks only for events not yet identified):

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only SPORT_IDENTITY
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only SPORT_CONFIDENCE
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only COUPON_ASSEMBLY
```

- SPORT_IDENTITY writes `runs/sofa/<date>/sport_fixtures.json`. An
  `IDENTIFIED` record is pinned - SETTLE grades the leg by that id and never
  searches again. Exit 1 = an event not identified or the bridge refused
  (those events are `NOT_IDENTIFIED`, off the coupon); exit 2 = no snapshot
  of any sport.
- SPORT_CONFIDENCE writes `runs/sofa/<date>/08_confidence_sports.json`
  (no bridge): confidence = the calibrated bucket of the score model / CS2
  engine probability (`config/sofa_sport_confidence_calibration.json`,
  fitted without prices, between days only), then the coupon's price
  filters. Exit 1 when a sport is `NOT_CALIBRATED` or `sport_fixtures.json`
  is missing - the artifact is still written and the football / tennis
  coupon still builds. `11_coupon.json` carries the per-sport `sports`
  status block; the PDF does not print it, so the report must: the per-sport
  `status` and `refused` counts.
- COUPON_ASSEMBLY (`scripts/sofa/build_coupon.py`) writes
  `runs/sofa/<date>/11_coupon.json` + `11_coupon.md` from
  `08_confidence.json` and `08_confidence_sports.json`: positions 1..N in
  `confidence.coupon_order`, locked legs first and unnumbered, builders
  B1.., `removed_by_reads`, the operator's `read_requests`. It refuses
  (exit 2) an `08_confidence.json` that is not the standard profile, not
  stats-only, or older than its sheet / vetoes / reads. Reads only files.

This 11 is provisional too: it is what the analysts read.

## Step 5 — the analysts, on the legs that need a read

`audit_variants` C3 requires an analyst's read on
`confidence.legs_requiring_read`: the **first 30 unlocked positions** of
`11_coupon.json`, **every printed builder leg**, and every entry of
`runs/sofa/<date>/read_requests.json` (the operator's "dodatkowo", added by
`/sofa-analyze`). The rest of the coupon prints unread - the operator's
limit; pass it to the analysts. Count the set per sport:

```bash
PYTHONPATH=src:. .venv/bin/python - <<'PY'
import json, collections
from pathlib import Path
from bet.sofa.confidence import legs_requiring_read, load_read_requests
run = Path("runs/sofa/<date>")
doc = json.loads((run / "11_coupon.json").read_text())
legs = legs_requiring_read(doc, load_read_requests(run / "read_requests.json"))
# a builder leg carries no `sport`: take it from its fixture
sport_of = {f["sofascore_event_id"]: f["sport"]
            for f in json.loads((run / "02_fixtures.json").read_text())}
print(doc["positions"], "positions;", collections.Counter(
    x.get("sport") or sport_of.get(x["sofascore_event_id"], "?") for x in legs))
PY
```

Launch every analyst with legs to read in **one message** so they run
concurrently, in the foreground (`run_in_background: false`; nothing wakes
you if they run in the background):

```
Task -> sofa-analyst-football  "date <date>; run <run_id>; stage verdicts; 11_coupon.json: <n> positions, <n> football legs to read (top 30 + builders + read_requests); return vetoes AND reads"
Task -> sofa-analyst-tennis    "date <date>; run <run_id>; stage verdicts; 11_coupon.json: <n> tennis legs to read; return vetoes AND reads"
Task -> sofa-analyst-sport     "sport hockey; date <date>; 11_coupon.json: <n> hockey legs to read; return reads"
Task -> sofa-analyst-sport     "sport cs2; date <date>; ..."   # one per measured sport with legs in the set
```

Do not give them your own opinion about a fixture. The football and tennis
analysts return Polish markdown and two fenced JSON arrays (vetoes, then
reads); `sofa-analyst-sport` returns markdown and one array (reads - a veto
cannot name a sport side). Save each markdown as
`runs/sofa/<date>/<date>_analiza_<sport>.md` (`football`, `tennis`,
`hockey`, `basketball`, `volleyball`, `cs2`), verbatim, as `/sofa-analyze`
does. An analyst that returned no reads block has not followed its contract
- say so, never invent its reads.

Skip this step only if the operator asked for a bare run — and then say you
skipped it.

## Step 6 — merge the vetoes and the reads

`vetoes.json` and `reads.json` are read by COUPON, CONFIDENCE and
COUPON_ASSEMBLY. Merge the veto arrays into `runs/sofa/<date>/vetoes.json`,
**validating first** — a malformed entry stops the run: COUPON raises
(`run_pipeline.py` reports it FAILED, exit 2) and `run_confidence.py` dies on
an uncaught `ValidationError` with exit 1 - which reads as PARTIAL unless the
traceback is read. Neither writes its artifact, so the earlier build stays on
disk looking current. Report any `UNMATCHED_VETO`: it did nothing, and a
silent no-op reads exactly like a veto that was honoured. An empty
`vetoes.json` is the healthy default.

Merge the reads arrays into `runs/sofa/<date>/reads.json` (append; an
earlier read is never edited or dropped - WATCH and NO_BET win over KEEP
whoever wrote them), validating the merged array as `list[LegRead]`
(`src/bet/sofa/contracts.py`, strict, `extra="forbid"`) before writing - both
snippets are in `.claude/agents/sofa-runner.md` step 6 - and then:

```bash
PYTHONPATH=src:. .venv/bin/python -c "from bet.sofa.veto import load_reads; print(len(load_reads('runs/sofa/<date>/reads.json')))"
```

What a read does: `NO_BET` and `WATCH` both remove the leg from the coupon
(`READ_NO_BET` / `WATCHED`) into `removed_by_reads` - graded on its own in
audit_settlement 7i and the ledger's `removed:reads`, never in the coupon's
result; `KEEP` removes nothing and records that the leg was read. A
measured-sport read (`market` = family, `direction` = side, `period`)
matches no football / tennis sheet row, so `run_confidence.py` lists it as
`UNMATCHED_READ` - expected; it takes effect in COUPON_ASSEMBLY (check
`removed_by_reads` in `11_coupon.json`).

## Step 7 — rebuild and the PDF

The rebuild is ONE command (plan production grade F0.2) - never the stage
scripts by hand: on 2026-10-05 a hand-run CONFIDENCE on a >45-min offer
emptied `08_confidence.json` to its locked legs, and a SHADOW with its 3 h
horizon left a 15:30Z hockey game on a stale price. Dry run first, then run:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <date> --dry-run
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <date>
```

It decides from the files' ages and the clock (`bet.sofa.rebuild_plan`) and
runs, in order: OFFER (`run_offer.py --min-minutes-to-kickoff 20`) when an
open fixture's price would be past CONFIDENCE's 45 min by the time it runs;
SHADOW (`run_shadow.py --horizon-h` to the farthest open start) / CS2 when a
sport price nears its 3 h limit or SHADOW skipped an event beyond its
horizon, then `ensure_bridge.py` + SPORT_IDENTITY; SHEET only when
CONFIDENCE would refuse the sheet's epoch; COUPON (06, audit_coupon's input)
when older than its inputs; then FIXTURE_CHECK (bridge; no bridge =
UNVERIFIED, nothing refused), CONFIDENCE, SPORT_CONFIDENCE, COUPON_ASSEMBLY,
PDF (`11_coupon.json` -> `KUPON_<date>.pdf` + `12_printed.json`),
`audit_variants.py` and `audit_coupon.py`. A day that is over refreshes no
price (`DAY_OVER` in its notes). One compact line per step, the full output
in `runs/sofa/<date>/rebuild_<ts>.log`, a final `SOFA_SUMMARY` (`stage:
REBUILD`); exit 0 / 1 PARTIAL / 2 FAILED - a FAILED step stops the rest,
except the bridge steps, the sport snapshots and COUPON (PARTIAL). A SHEET
forced by a code change to SHEET is not detected: run `--only SHEET` first
and say why. In the stats-only epoch a moved price re-prices the leg (x at
the fresh odds), so an OFFER refresh needs no SHEET re-run.

`build_coupon_pdf.py` renders `11_coupon.json` (it refuses a stats-only day
without one) and writes `12_printed.json`. It exits 2 on `STALE_CONFIDENCE`
(`08_confidence.json` older than `05_sheet.json`, `vetoes.json`,
`reads.json` or the calibration file) and on `STALE_COUPON` (`11_coupon.json`
older than `08_confidence.json`, `08_confidence_sports.json` or
`read_requests.json`): fix the cause and re-run `rebuild_day.py`, never work
around it. After any reads merge run the whole rebuild - never only the PDF.

Read `stakeable_builders`, not `builders`. A builder is chosen and ordered by
`combined_probability` and stakeable when combined probability x odds after
the 12% correlation haircut >= 0.90; `picks: 0` is a legitimate answer. Never
present `odds_if_product` as a price - Superbet does not price a slip as the
product of its legs.

Then start the closing-price capture for the printed legs (Superbet only, no
bridge; it reads the coupon artifact on every pass and exits after the last
leg starts - start it again after a rebuild that adds legs), and take a
boosts snapshot - repeat `run_boosts.py` a few times during the day:

```bash
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/capture_closing.py --date <date> --loop >> runs/sofa/<date>/capture_closing.log 2>&1 &
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_boosts.py --date <date>
```

## Step 8 — verify, and do not skip this

`rebuild_day.py` ran both audits as its last steps (their verdicts are in its
summary); read their full output in its log, or re-run them:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <date>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <date>
```

`audit_coupon` covers structure and arithmetic of `05_sheet.json` /
`06_coupon.json` from each row's own fields. `audit_variants` covers the
coupon: C1 (the artifact of its profile, fresh, its PDF prints it), C2
(every printed single obeys the dials it was built with; a locked single
against the build that printed it), C3 (every leg of
`legs_requiring_read` has an `author: "analyst"` read, none printed carries
WATCH / NO_BET), U1 (`11_coupon.json` in `coupon_order`, numbered 1..N,
locked first), U2 (every fresh football / tennis single carries the
stats-only epoch), U3 (every fresh measured-sport leg re-derived from the
raw Superbet snapshot: odds, price age, group margin, x, the calibration
bucket). Exit 0 no findings, 1 findings, 2 a file could not be read. Any
finding is a defect to fix before the day is reported; lines under `notes
(not defects):` (a locked leg read as of its print, the 10-05 morning
records) are listed in the report, not fixed.

One C3 finding you close yourself: `printed without an analyst's read` (a
rebuild put an unread leg into the read set) - send exactly those legs to
that sport's analyst, merge its reads (step 6), rebuild (step 7) and re-run
the audit.

Then hand the day to `sofa-verifier` (protocol `docs/sofa/VERIFY_PROTOCOL.md`),
in the foreground. It rebuilds staked rows from `03_samples.json`, checks the
subject maps to its side, re-asks Superbet for live prices, tests the day's
distributions for anti-selection, and checks the sport legs against their
snapshots and pinned identities. Locked legs are not defects. It ends with
its rows-not-to-stake as a fenced JSON array of `LegRead` (`author:
"verifier"`; WATCH for a judgement, NO_BET for a defect). **Append** it to
`reads.json` (step 6), rebuild (step 7: `rebuild_day.py`, which re-runs
`audit_variants.py` and `audit_coupon.py`) - C1 and C3 clean. An empty verifier array needs no rebuild; say so.

## Traps that have actually cost something

- **`06_coupon.json` is not the coupon, and neither is `08_confidence.json`**
  on a stats-only day. `11_coupon.json` and its PDF are.
- **Positions move after a rebuild.** A read request or a report that names
  "position 31" names another leg after the next build; name the match
  (`group_key`), market, line and direction.
- **Half-match football rows lean on a global prior.** At `K_CENTRE = 15`
  a sample of n=8 contributes 35% of its own centre. Before trusting a
  `*_1h_*` / `*_2h_*` row, compute `n/(n+15)`.
- **`coverage_floor` is weekday-blind.** Its median is built from recent runs,
  so a Monday slate (~100 football fixtures against a weekend's ~1000) trips
  "matching regression" every time. Check the RESOLVE rate instead — 72–90% is
  normal — before believing it.
- **Clock disagreement is tennis and structural.** Superbet posts a nominal
  "not before" time for ITF matches, Sofascore the real one; gaps to 11 h are
  normal and `CONFIRMED`. The gate takes the **earliest** clock (FIXTURE_CHECK's
  fresh start replaces RESOLVE's frozen one), which conservatively refuses some
  un-started matches. That is deliberate.
- **Subagent numbers need verification.** They have been wrong in ways that
  inverted an argument. Check any claim you can check locally.
- **Constants are fitted deliberately, not daily.** `fit_constants.py` (E11),
  `fit_confidence.py` and `fit_sport_confidence.py` are not in
  `DEFAULT_SEQUENCE`. Re-fitting mid-day breaks comparability with yesterday.
  But **do** check `config/sofa_league_baselines.json`'s `fitted_from` and
  `half_match_coherence` — a stale baselines file shipped a corners prior
  24–32% too high for two days before anyone noticed.

## Report back, short

```
KUPON:    runs/sofa/<date>/KUPON_<date>.pdf — <n> pozycji (<n> piłka / <n> tenis / <n> hokej / <n> kosz / <n> siatka / <n> CS2), <n> w grze (zablokowane), <n> Bet Builderów
SPORTY:   hokej <status> / kosz <status> / siatka <status> / CS2 <status> (08_confidence_sports.json; NOT_CALIBRATED / NOT_IDENTIFIED <n>)
SHEET:    <n> wierszy (<n> piłka / <n> tenis), epoka stats_only
RUN:      <run_id> · <verdict każdego etapu> · <n> na tablicy → <n> dopasowanych → <n> READY
ODCZYTY:  przeczytane <n> z <n> wymaganych (top 30 + <n> nóg builderów + <n> dodatkowych) · poza top 30 drukowanych bez odczytu: <n>
READS:    analityk <n> (KEEP <n> / WATCH <n> / NO_BET <n>) · weryfikator <n> (WATCH <n> / NO_BET <n>) · UNMATCHED_READ <n> (w tym sporty: <n>, oczekiwane)
ZDJĘTE:   removed_by_reads <n> - <każda zdjęta noga: mecz, rynek, linia, kierunek, autor, powód>; MODEL_ABOVE_OWN_SAMPLE <n>; FIXTURE_NOT_AS_SCHEDULED <n>
WETA:     <n> zastosowanych, <n> bez dopasowania
ANALIZY:  runs/sofa/<date>/<date>_analiza_<sport>.md (każdy sport z nogami do odczytu)
SETTLE:   D-1 <n> wierszy; 7c kupon <u> j. (per sport), zwroty <n>; 7i zdjęte przez odczyt <u> j. (osobno); tożsamość: <n> znalezisk (audit_settle_identity)
POMIAR:   D-1 CS2 <n> serii / hokej <n> / kosz <n> / siatka <n> rozliczonych — pomiar
D-1 WYNIKI: official <u> j. · official:pre_stats_only <u> j. · removed:reads <u> j. (każdy osobno, nigdy sumowane) · MISMATCH <n> (audit_ledger.py)
CLV D-1:  kupon <x%> [lo; hi] (audit_clv.py)
AUDYT:    audit_coupon <n> · audit_variants <n> znalezisk (C3: <n> nóg bez odczytu analityka - musi być 0; U3: <n>)
WERYFIKACJA: <n>/<n> arytmetyka, <n>/<n> ceny na żywo, <n> pozycji odrzuconych (zapisane w reads.json i przebudowane: tak/nie)
UWAGA:    <the day's single biggest weakness>
```

## Hard rules

- Never invent a number, a fixture or an odds quote.
- Never print a combined/parlay price outside what `confidence.py` computed.
- No stake sizing, no automated placement.
- Never read, echo or log `.env` values.
- Never strip `UNFITTED_CONSTANTS` from a report to make it read better.
