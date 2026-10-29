---
description: "Run one sofa betting day end to end - settle and record D-1 (sofa-settler), refresh the line evidence, build the one coupon of every sport (11_coupon.json -> KUPON_<date>.pdf), have the analysts read it, rebuild, verify (sofa-verifier), report. The only day procedure; sofa-runner follows this file."
argument-hint: "dzisiaj | wczoraj | YYYY-MM-DD"
---

Run one betting day, from nothing to a verified PDF coupon, unattended. Skip a step only
when the operator asked for a bare run, and name the skip in the report.

`$ARGUMENTS`: `dzisiaj`/`today`, `wczoraj`/`yesterday` or `YYYY-MM-DD`; empty = today
(`date -u +%F`). The betting day is UTC. `<D>` (also written `<date>`) = the date, `<D-1>` the day before.

**The coupon** is `runs/sofa/<D>/KUPON_<D>.pdf`, rendered from `11_coupon.json`;
`12_printed.json` is the print record the next rebuild locks started legs from.
`06_coupon.json` and `08_confidence.json` are inputs, never the coupon.

**Stages** (order: `DEFAULT_SEQUENCE` in `scripts/sofa/run_pipeline.py`):

```
BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON
                                          ↘ CONFIDENCE ─────────────┐
   SHADOW / CS2 → SPORT_IDENTITY → SPORT_CONFIDENCE ────────────────┤
                                   COUPON_ASSEMBLY (11_coupon.json) → PDF
   in a rebuild, before CONFIDENCE: FIXTURE_CHECK
   in a live rebuild, first:        LATE_RESOLVE (new fixtures only → OFFER/SAMPLES/SHEET --event-ids)
   in a rebuild, on a sample switch: SAMPLES/SHEET --event-ids for open fixtures (rebuild_plan 1c)
   deliberately separate:           SETTLE → FIT
```

Exit codes: 0 OK, 1 PARTIAL (normal on RESOLVE / OFFER / SAMPLES), 2 FAILED.
Python: `PYTHONPATH=src:. .venv/bin/python`.

## 0. Bridge

```bash
.venv/bin/python scripts/sofa/ensure_bridge.py
```

- Exit 0: up; still read the poll-age line (WARN exits 0). The burst-probe line is INFO;
  only `WARN ... burst probes FAILED` is a fault.
- Exit 1: degraded (a dead tab, or a Chrome without the anti-throttling flags at ~1 req/s).
- Exit 2: it could not - usually Chrome is open without the flags. The operator quits it
  (Cmd+Q), then you re-run. Never quit or kill the operator's Chrome yourself.
- A dead tab = nothing that asks Sofascore can run: stop and tell the operator.
- Leave `SOFA_TARGET_RPS` (20) and `SOFA_MAX_CONCURRENCY` (5 = the window count) at their
  defaults; never lower `MIN_INTERVAL_MS`.

## 1. Settle D-1 - `sofa-settler`

Launch `sofa-settler` with `D-1 <D-1>; scratch <your scratchpad>/settle_<D-1>`. It owns
every command, in this order (`sofa-settler.md`):

1. SETTLE `<D-1>`; CS2_SETTLE only when the D-1 `cs2_daily` loop is done or dead and no
   `cs2_watchdog` covers D-1; SHADOW_SETTLE only when no D-1 `shadow_daily` loop is alive
   (each loop settles its own day at 05:00Z / 05:15Z);
2. `audit_settle_identity`, the `resettle_sweep` (D-14..D-2 + D-5);
3. `audit_shadow` / `audit_cs2`, `record_results` D-8..D-1, `audit_ledger` D-7..D-1 (per
   variant and epoch, never pooled), `audit_clv` D-2..D-1;
4. `audit_settlement` (7c = the coupon's real result per sport, 7i = legs a read removed,
   apart; refunds at 0 u.).

Relay its result into the report (D-1, POMIAR lines). A ledger `MISMATCH` is a defect.

BOARD asks only Superbet: the main session launches the settler with
`run_in_background: true` (you are notified on completion) and runs BOARD meanwhile; a
subagent (`sofa-runner`) launches it in the foreground and runs BOARD after. RESOLVE waits
for the settler's **return** (its scripts hold the DB - `database is locked`) and step
1a's bridge part.

## 1a. Line evidence

`refresh_line_evidence.py`'s step 0 asks the bridge and writes `data/sofa.db`; its fits only
read the DB (`mode=ro`). So, after the settler returns and before RESOLVE, run step 0's
commands as one background Bash call (`run_in_background: true`, 10-30 min):

```bash
mkdir -p runs/sofa/<D>
{ PYTHONPATH=src:. .venv/bin/python scripts/sofa/refresh_sport_history.py --max-minutes 12; echo "history exit $?"
  for s in hockey basketball volleyball; do PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_event_stats.py --sport $s --days 7 --with-lineups --max-minutes 6; echo "$s exit $?"; done
  PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_referees.py --days 14 --max-minutes 8; echo "referees exit $?"
  echo BRIDGE_PART_DONE; } > runs/sofa/<D>/line_evidence_bridge.log 2>&1
```

Name a non-zero `exit` (no bridge, a refusal); the fits run on what is cached. When
`BRIDGE_PART_DONE` is in the log (never earlier - two writers on the bridge and the DB),
start step 2's RESOLVE.

Then start the fits beside RESOLVE:

```bash
nohup sh -c 'PYTHONPATH=src:. .venv/bin/python scripts/sofa/refresh_line_evidence.py --before <D> --skip-history; echo "EXIT $?"' > runs/sofa/<D>/refresh_line_evidence.log 2>&1 &
```

`EXIT 0` written; 1 = a sport's row fit failed (that sport reuses earlier rows - name it;
a `Traceback` in the log is a crash, also 1) - with `--skip-history` the history /
statistics part is the bridge call above, with its own `exit` lines; 2 =
`fit_line_evidence.py` failed, today builds on the previous file (say so).
`config/sofa_superbet_line_evidence.json` `fitted_from.before` must read `<D>`.
**Step 3 waits for `EXIT`** - a build on yesterday's evidence reshuffles the 20 best-value
matches on the rebuild and leaves read legs unread.

## 1b. Loops

```bash
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/cs2_daily.py --date <D> --chain >> runs/sofa/cs2/daily_<D>.log 2>&1 &
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/shadow_daily.py --date <D> --chain >> runs/sofa/shadow/daily_<D>.log 2>&1 &
```

- `cs2_daily`: always safe - a second loop for a date refuses (exit 2).
- `shadow_daily`: start by hand **only when neither** `runs/sofa/shadow/daily_<D-1>.pid`
  **nor** `daily_<D>.pid` exists (the D-1 chain starts today's after its 05:15Z settle).
- `capture_closing`: the daily loops start it (`ensure_loop`); by hand only per step 9.
- A loop reads its plan at start: after a code change, run the new morning steps by hand
  for days old loops cover; say so. Never kill a loop.

## 2. Build today

BOARD mints the run id (`run_pipeline.py` without `--run-id`); read it back from its
`SOFA_SUMMARY` line and reuse it for the day:

```bash
mkdir -p runs/sofa/<D>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D> --only BOARD > runs/sofa/<D>/pipeline_board.log 2>&1
grep -o '"run_id": "[0-9a-f]*"' runs/sofa/<D>/pipeline_board.log | tail -1
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/run_pipeline.py --date <D> --from-stage RESOLVE --run-id <id> > runs/sofa/<D>/pipeline_resolve.log 2>&1 &
```

RESOLVE..COUPON runs 2.5-3 h. Follow it with short Bash calls - never `tail -f`, never a
foreground call near its 600000 ms limit:
`grep -E "^--- |: (OK|PARTIAL|FAILED|SKIPPED)|STAGE_EXCEPTION|Traceback" runs/sofa/<D>/pipeline_resolve.log | tail -5`.
It is over when a `SOFA_SUMMARY: {"stage": "PIPELINE"` line appears.

- A FAILED stage SKIPs the rest; a died RESOLVE leaves `02_fixtures.json.INCOMPLETE`
  (refused downstream as `UPSTREAM_INCOMPLETE`). Re-run `--from-stage <failed>` with the same id.
- A SHEET quiet for 10 min is parsing the history - do not kill it.
- False alarms: `coverage_floor` "matching regression" (RESOLVE 72-90% is healthy);
  board size follows the calendar.

Once `04_offer.json` exists, label what OFFER could not read (report only; exit 1 =
UNCLASSIFIED names, report the count):

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/report_market_coverage.py --date <D>
```

## 3. CONFIDENCE (provisional)

After step 2 and step 1a's `EXIT` line:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <D>
```

Exit 2 = refused, nothing written - read the `REFUSED` / stderr line: a frozen
`SOFA_NOW`, `--calibration` on the real runs dir, `02_fixtures.json.INCOMPLETE` (re-run
RESOLVE, step 2), an unreadable previous coupon or print record (stop and report - it is
the record of what was printed). Only `REFUSED: this is a stats-only build and
05_sheet.json was not built under that rule` means re-run SHEET (step 7). Report `refused` counts, every
`UNMATCHED_VETO` / `UNMATCHED_READ` and a `LINE_EVIDENCE_NOT_FITTED` (evidence file missing).

## 4. Measured sports and the coupon (provisional)

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D> --only SHADOW
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D> --only CS2
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D+1> --only CS2
.venv/bin/python scripts/sofa/ensure_bridge.py
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D> --only SPORT_IDENTITY
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D> --only SPORT_CONFIDENCE
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D> --only COUPON_ASSEMBLY
```

- `ensure_bridge.py` right before SPORT_IDENTITY (a dead bridge lost 10 h of identities on
  10-20); exit 2 = stop and tell the operator.
- SPORT_IDENTITY (bridge): exit 1 = an event not identified or a refusal (off the coupon);
  2 = no snapshot of any sport. A 403 stops it - never retry into a refusal.
- SPORT_CONFIDENCE exit 1 = a sport `NOT_CALIBRATED` or without `sport_fixtures.json`; the
  rest still builds. Report each sport's `status` and `refused` from `11_coupon.json` `sports`.
- COUPON_ASSEMBLY exit 1 = `08_confidence_sports.json` absent (football / tennis only - say
  so); exit 2 = `08_confidence.json` not the standard profile, not stats-only or stale.
- **No PDF here** - a provisional PDF would lock every leg whose match starts, read or not;
  the first PDF comes from step 7.

## 5. Analysts

`/sofa-analyze`'s pass (it owns the details). Buffer 25 (the rebuild reshuffles the 20
best-value matches - 20 since 2026-10-27, `READ_SCOPE_FROM_UTC`; legs read now save a C3
round), parts of <= 6 matches (`--split` applies to every sport; tennis / sport parts are
small anyway):

```bash
.venv/bin/python scripts/sofa/ensure_bridge.py
PYTHONPATH=src:. .venv/bin/python scripts/sofa/read_set.py --date <D> --buffer 25 --split 6
```

It prints one line per sport / part: `<sport>: <n> legs, <n> matches (<n> required, <n>
buffer) -> <file>` - the required / buffer counts are legs. A sport without a file gets no
analyst. Run id: the one BOARD minted.

Launch one instance per file, **all in one message, in the foreground** - nothing wakes
you if they run in the background; if one still comes back as a background task, **wait for its
completion notification** and check its report file exists before `merge_reads.py` - never
merge or rebuild while an analyst of the round runs (2026-10-29). `football` -> `sofa-analyst-football`, `tennis` ->
`sofa-analyst-tennis`, `hockey` / `basketball` / `volleyball` / `cs2` -> `sofa-analyst-sport`.
Give the path `runs/sofa/<D>/<D>_analiza_<sport>[_<i>].md` (next free `_r<n>` if it exists;
never overwrite). Prompt, nothing else - no opinion of yours about any fixture:

```
date <D>; run_id <id>; sport <sport>; read set: runs/sofa/<D>/read_set/read_set_<sport>[_<i>].json;
write your report to: runs/sofa/<D>/<D>_analiza_<sport>[_<i>][_r<n>].md
```

Each analyst writes its own report and returns <= 12 lines (the path it **actually wrote** -
it may re-suffix `_r<n>`; one part = one report -, legs read, KEEP / WATCH / NO_BET,
vetoes). Do not re-type its text or arrays.

## 6. Merge

Merge every path the analysts **returned** (not the one you gave); one call may take
several `--report`; never two merge calls at once:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/merge_reads.py --date <D> --author analyst --report <returned path> [--report <returned path> ...]
```

Exit 0 merged; 1 merged with an `UNMATCHED_VETO` (it did nothing - report it); 2 refused,
nothing written (also a removal without a fact - USUNIĘCIE BEZ FAKTU, RYNEK TYLKO WATCH,
RYNEK BEZ TAGU, WETO BEZ FAKTU): relaunch that instance with the refusal line and a new `_r<n>` path -
never fix its JSON yourself; after 2 relaunches report the failure and go on. A report with
no reads block broke the contract - say so, never invent reads. List every WATCH / NO_BET
it prints.

## 7. Rebuild and print

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <D> --dry-run
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <D>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/day_status.py --date <D> | grep -i icloud
```

`/sofa-rebuild` owns the plan. After every `rebuild_day.py` (step 7, C3 rounds, step 8) the
`icloud` line is read; the last state goes into the report. Never run stage scripts by hand for a rebuild (a CONFIDENCE
on a >45 min offer empties 08 to the locked legs). SHEET re-runs
itself only on the epoch / link rule / a switch's missing marker; after a SHEET code change
or a `CONFIG_CHANGED` note the operator approved, run
`PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D> --only SHEET --run-id <id>`
first and say why. Read the CONFIDENCE `refused` counts; a sport read counts as
`reads_sport` and takes effect in COUPON_ASSEMBLY (confirm in `11_coupon.json`
`removed_by_reads`); every `UNMATCHED_READ` did nothing - report it.

**C3 loop.** The rebuild ends with `audit_variants`; C3 lists read-set legs with no
analyst read (positions moved) or a printed leg carrying WATCH / NO_BET. Then:

```bash
.venv/bin/python scripts/sofa/ensure_bridge.py
PYTHONPATH=src:. .venv/bin/python scripts/sofa/read_set.py --date <D> --unread --split 6
```

(add `--buffer 5` while early kickoffs keep pulling new matches in), then repeat step 5's
launch and steps 6 and 7 on those files only (paths `_r<n>`) - never step 5's full
`read_set.py` line; measured-sport files of at most 6 matches together go to
one `sofa-analyst-sport` instance with this prompt:

```
date <D>; run_id <id>; sport <s1>,<s2>; read set: runs/sofa/<D>/read_set/read_set_<s1>.json, runs/sofa/<D>/read_set/read_set_<s2>.json;
write your report to: runs/sofa/<D>/<D>_analiza_sports_r<n>.md
```

and a leg of a match read
earlier today carries `prior_analysis` (the analyst's delta pass). `read set: empty` while C3 is still red = a printed leg
carries WATCH / NO_BET or `reads.json` is missing: run `rebuild_day.py`, not another read. A `started:` line names the matches a re-read pass left out (kickoff within the 15-min
margin; their analyst would skip them and a read cannot change their legs): C3 keeps listing
them - report them, never read them.
At most 3 rounds, then report the C3 lines left. A WATCH / NO_BET on a builder leg makes
that fixture's builder take its next candidate: in the re-read prompt add "also read every
leg of this fixture's builder candidates in 08_confidence.json `builders`". A refusing read
on a locked leg is a note, not a defect. The PDF prints even with C3 findings: legs that
started meanwhile are locked unread - name them.

## 8. Verify - not optional

Launch `sofa-verifier` in the foreground with `date <D>; run_id <id>; write your report to:
runs/sofa/<D>/<D>_weryfikacja[_r<n>].md` (next free). It screens every printed leg
mechanically (`scripts/sofa/verify_legs.py --all`) besides the read set, and returns that
screen's line (legs, DEFECT / NOTE). Then, with the path it **returned**:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/merge_reads.py --date <D> --report <returned path> --author verifier --dry-run
PYTHONPATH=src:. .venv/bin/python scripts/sofa/merge_reads.py --date <D> --report <returned path> --author verifier
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <D>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/day_status.py --date <D> | grep -i icloud
```

merge_reads: exit 0 merged, 1 merged with an `UNMATCHED_VETO`, 2 refused (nothing written; a
removal without a fact too) = relaunch the verifier with the refusal line / findings and the next `_r<n>` path (at most 2 relaunches,
then report it). No verifier reads = no rebuild; say so. The rebuild ends with the audits -
do not re-run them. After the rebuild C1 and C3 must be clean (a
C3 finding goes back through the C3 loop). Any other `audit_variants` / `audit_coupon`
finding is a defect to fix before reporting; lines under `notes (not defects):` are
listed, not fixed.

## 9. Status, closing prices, boosts

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/day_status.py --date <D>
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/capture_closing.py --date <date> --loop >> runs/sofa/<date>/capture_closing.log 2>&1 &   # only on a day_status loop:capture_closing WARN
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_boosts.py --date <D>
```

- `day_status.py` (no network) = STATUS. BROKEN (ledger MISMATCH, STALE_COUPON, a PDF older
  than 11) is fixed before reporting; its `bridge` is always NOT_CHECKED, never a pass.
- **iCloud copy (the last step, operator 2026-10-25):** every PDF render (step 7, step 8's
  rebuild, the evening rebuild, a results render) copies `KUPON_<D>.pdf` + `.html` over
  `~/Library/Mobile Documents/com~apple~CloudDocs/Kupony/<DD.MM.YYYY>/` itself
  (`bet.sofa.icloud_sync`; the PDF stage's JSON line carries `icloud`). `day_status.py`
  `icloud` must be OK (byte-equal); a WARN (missing / differs) = re-copy with
  `PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_html.py --date <D>` (no print
  record; safe on a results day - it keeps `13_results.json`'s colours) and check again; SKIPPED / NOT_CHECKED (no iCloud Drive) is named in the report.
- `capture_closing.py`: a missing close is a CLV hole, not a zero. `run_boosts.py`: a few
  times a day.

## 10. Evening rebuild (from 2026-10-23; the operator's, by hand - not part of this run)

A measured sport's day runs to D+1 05:00Z (`epochs.SPORT_LATE_WINDOW_FROM_UTC`,
`sport_identity.day_window`): hockey / basketball / volleyball / CS2 games after midnight
UTC are D's legs (`window: "late"`). The morning prices only those already fresh and
pinned; the operator runs `/sofa-rebuild <D>` (`rebuild_day.py --date <D>`) at ~20:00-21:00Z,
which refreshes SHADOW / CS2 / SPORT_IDENTITY and appends them - morning legs stay locked;
then `/sofa-analyze` for the new unread legs. Football and tennis keep the UTC day. In the
report, say the evening rebuild is still to come.

## Traps that cost money

- Positions move on every rebuild: name a leg by `group_key`, market, line, direction;
  in chat in Superbet's words (`superbet_market: superbet_selection`).
- Tennis clock gaps up to 11 h (ITF) are structural. Start clock = earliest of RESOLVE's
  clocks and Superbet's (`superbet_kickoff_seen_utc`), or - once FIXTURE_CHECK read a fresh
  `/event` start - of that start and Superbet's newest clock (it replaces RESOLVE's frozen
  ones, `locked_print.kickoff_clocks`: a match moved later is not gated on its dawn start);
  Superbet's start signal (`superbet_started_utc`) counts as started.
- Check a subagent's number locally where you can.
- No curve or constant is refitted or installed from a day's run (operator's go only;
  `refresh_line_evidence.py` never touches a curve).

## Report (short, Polish, opens with the coupon)

```
KUPON:    runs/sofa/<D>/KUPON_<D>.pdf — <n> pozycji (piłka / tenis / hokej / kosz / siatka / CS2), <n> zablokowanych, <n> Bet Builderów
iCloud:   Kupony/<DD.MM.YYYY>/ — pdf + html <OK / WARN / NOT_CHECKED> (day_status icloud)
SPORTY:   hokej / kosz / siatka / CS2 <status, refused> (każdy inny niż OK z powodem)
RUN:      <run_id> · werdykt każdego etapu · <n> na tablicy → <n> dopasowanych → <n> READY
SHEET:    <n> wierszy (<n> piłka / <n> tenis), epoka stats_only
DOWODY:   refresh_line_evidence exit <n> · fitted_from.before <D> (albo: pominięty)
ODCZYTY:  przeczytane <n>/<n> wymaganych (+ bufor <n>) · rundy C3 <n> · nieprzeczytane: <które i dlaczego>
READS:    analityk KEEP/WATCH/NO_BET <n/n/n> · weryfikator WATCH/NO_BET <n/n> · UNMATCHED_READ <n> · weta <n> (bez dopasowania <n>)
ZDJĘTE:   removed_by_reads <n> — <mecz, rynek, linia, kierunek, autor, powód>
RAPORTY:  <ścieżki analiz i weryfikacji>
POMIAR:   D-1 CS2 <n> serii / hokej <n> / kosz <n> / siatka <n> rozliczonych — pomiar
D-1:      7c <u> j. per sport · 7i <u> j. osobno · zwroty <n> · tożsamość <n> · MISMATCH <n> · CLV <x%> [lo; hi]
STATUS:   day_status <OK/WARN/BROKEN> · pętle · UNVERIFIED <n> · mostek NOT_CHECKED
AUDYT:    audit_coupon <n> · audit_variants <n> (C3 0)
WERYFIKACJA: <n>/<n> arytmetyka · <n>/<n> ceny na żywo · <n> pozycji odrzuconych (w reads.json i przebudowane: tak/nie) · verify_legs --all: <n> nóg, DEFECT <n>, NOTE <n>
UWAGA:    <największa słabość dnia>
```

Count positions per sport yourself from `11_coupon.json`. Never pool variants or epochs;
no combined / builder price, no stake; never strip `UNFITTED_CONSTANTS`.
