---
description: "Run the sofa analysts over a day that already has 11_coupon.json - the C3 read set (20 best-value matches, printed builder legs, the operator's 'dodatkowo' positions, or with 'okno 14-17' the window's 20 best matches on fresh prices) - via read_set.py, merge their reports with merge_reads.py, rebuild with rebuild_day.py, repeat until C3 is clean. No SAMPLES by hand."
argument-hint: "dzisiaj | wczoraj | YYYY-MM-DD [okno <od>-<do>] [dodatkowo: <pozycje>]"
---

Get the analysts' read of a built day into `vetoes.json` / `reads.json`. CONFIDENCE and COUPON_ASSEMBLY read both, so this always ends in a
rebuild: a read not rebuilt did nothing. You merge; the analysts judge.

Python: `PYTHONPATH=src:. .venv/bin/python`.

## 0. Arguments and preconditions

`$ARGUMENTS` = `<day> [okno <od>-<do>] [dodatkowo: <n>, <n>, ...]`; day = `dzisiaj`/`today`,
`wczoraj`/`yesterday`, `YYYY-MM-DD`, empty = today (UTC). The numbers after
`dodatkowo:` are coupon positions the operator wants read beyond the read set.
`okno 14-17` (also `okno 14:30-17`) is a kickoff window in local time (Europe/Warsaw):
step 1a.

- No `runs/sofa/<date>/05_sheet.json` -> the day needs `/sofa-day`.
- No `11_coupon.json` -> run `/sofa-rebuild` first: analysts read what the coupon prints.

## 1. "dodatkowo" -> read_requests.json (before the analysts)

Positions move after every rebuild, so store the leg the position names now
(`group_key`, `market`, `line`, `direction`), and `{"position": n}` only when no leg is
there. Append, never rewrite; every entry carries `requested_by` and `at_utc`, and
`confidence.load_read_requests` validates the file (an entry without them, or without a
position or group_key, stops the build):

```bash
PYTHONPATH=src:. .venv/bin/python - <date> <n> <n> <<'PY'
import json, sys, datetime as dt; from pathlib import Path; from bet.sofa.confidence import load_read_requests
d, asked = sys.argv[1], [int(n) for n in sys.argv[2:]]; run = Path("runs/sofa") / d; p = run / "read_requests.json"
legs = {int(s["position"]): s for s in json.loads((run / "11_coupon.json").read_text())["singles"] if s.get("position") is not None}
now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"); cur = load_read_requests(p)
cur += [{**({k: legs[n].get(k) for k in ("group_key", "market", "line", "direction")} if n in legs else {"position": n}), "requested_by": "operator", "at_utc": now} for n in asked]
p.write_text(json.dumps(cur, indent=2, ensure_ascii=False) + "\n"); print(len(load_read_requests(p)), "requests; no leg at", [n for n in asked if n not in legs])
PY
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon.py --date <date>
```

`build_coupon.py` prints `UNMATCHED_READ_REQUEST` for a request that covers nothing -
report each.

## 1a. "okno" -> fresh prices, then the window's matches (before the analysts)

The operator plays these hours, so they are read on fresh prices: rebuild first (it
re-asks stale prices, then FIXTURE_CHECK .. PDF and the iCloud copy), then append the
window's 20 best-value matches - every match when fewer are left, a match starting within
30 min skipped (the 15-min kickoff margin at which an analyst skips a match + 15 min
to read it) - as whole-match requests (every market), then re-assemble:

```bash
.venv/bin/python scripts/sofa/ensure_bridge.py
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <date>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/window_reads.py --date <date> --start-from <od> --start-to <do>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon.py --date <date>
```

`window_reads.py` lists the matches it chose (exit 1 = no match left in the window: say
so and stop). Then step 2 with `--unread --buffer 0 --split 5` (legs read earlier today
are not read again; the window's matches are now part of C3, beside whatever the fresh
prices moved into the day's 20; parts of 5 matches read in parallel - a part of 86 legs
took 8.6 min on 10-27, and the window's first kickoffs do not wait) and steps 3-6 as usual; the final
rebuild re-renders the PDF / HTML and the iCloud copy. Report the window's matches by
name with their read verdicts.

## 2. The read set

```bash
.venv/bin/python scripts/sofa/ensure_bridge.py
PYTHONPATH=src:. .venv/bin/python scripts/sofa/read_set.py --date <date> --buffer 25 --split 6
```

- `--buffer 25` on a provisional build (the rebuild reshuffles the 20 best-value matches;
  legs read now save a C3 round); `--buffer 0` on a final rebuild; `--unread` on every
  re-read pass (step 5).
- `--split 6`: parts of <= 6 whole matches, one analyst each (operator 2026-10-29; the
  flag applies to every sport - tennis / measured-sport parts are small anyway).
- Output: one line per sport / part, `<sport>: <n> legs, <n> matches (<n> required, <n>
  buffer) -> runs/sofa/<date>/read_set/read_set_<sport>[_<i>].json` (required / buffer are
  legs). `read set: empty` = nothing to read.
- Run id: the day's, from its build log:
  `grep -ho '"run_id": "[0-9a-f]*"' runs/sofa/<date>/pipeline_board.log runs/sofa/<date>/pipeline_resolve.log 2>/dev/null | tail -1`.
  If absent (neither log), skip it: write `run_id -` in the prompt (the analysts do not use it).

## 3. Launch the analysts

One instance per file, **all in one message, foreground** (`run_in_background: false`):
`football` -> `sofa-analyst-football`, `tennis` -> `sofa-analyst-tennis`, `hockey` /
`basketball` / `volleyball` / `cs2` -> `sofa-analyst-sport`. A sport without a file gets no
analyst; say so. **A re-read round** (`--unread`, step 5) whose measured-sport files hold at
most 6 matches together gives them to **one** `sofa-analyst-sport` instance (`sport` = the
list, every file named, one report `runs/sofa/<date>/<date>_analiza_sports_r<n>.md`): each
instance costs its whole preloaded contract before the first leg, and a round of 1-2 matches
a sport is mostly that cost. Give the path `runs/sofa/<date>/<date>_analiza_<sport>[_<i>].md`; if it
exists, the next free `_r<n>` - never overwrite. The prompt, exactly, with no opinion of yours:

```
date <date>; run_id <id>; sport <sport>; read set: runs/sofa/<date>/read_set/read_set_<sport>[_<i>].json;
write your report to: runs/sofa/<date>/<date>_analiza_<sport>[_<i>][_r<n>].md
```

The combined sport instance of a re-read round gets the same prompt with `sport <s1>,<s2>`,
one `read set:` path per sport (comma-separated) and the report
`runs/sofa/<date>/<date>_analiza_sports_r<n>.md`.

A leg of a match analysed earlier today carries `prior_analysis` (`read_set.py`, from
`analyses.json`): the analyst reads that section and does only a delta pass - say nothing
about it in the prompt. Each writes its own report and returns <= 12 lines with the path it **actually wrote** (it
may re-suffix `_r<n>`; one part = one report - you split, via `--split`). Never re-type its text or arrays.

## 4. Merge, then rebuild

Merge the **returned** paths; one call may take several `--report`, never two calls at once:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/merge_reads.py --date <date> --author analyst --report <returned path> [--report <returned path> ...]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <date> --dry-run
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <date>
```

- `merge_reads.py` also stamps each read (`read_at_utc`) and files each report's match
  sections in `analyses.json` (the HTML / PDF show them at the legs); `NO_SECTIONS: <file>`
  = no heading carried `sofa:<id>` - report it, the merge stands.
- `merge_reads.py`: exit 0 merged; 1 merged with an `UNMATCHED_VETO` (it did nothing -
  report it); 2 refused, nothing written (also a removal without a fact: USUNIĘCIE BEZ
  FAKTU, RYNEK TYLKO WATCH, RYNEK BEZ TAGU, WETO BEZ FAKTU) - relaunch that instance with the
  refusal line / findings and a new `_r<n>` path (never fix its JSON yourself; after 2 relaunches report the failure). It carries earlier vetoes over and only appends reads (WATCH / NO_BET
  win over KEEP). A report without a reads block broke its contract: say so, never invent reads.
- `rebuild_day.py`: `/sofa-rebuild` owns its plan. Report every `UNMATCHED_READ` (a read that
  did nothing); a measured-sport read counts as `reads_sport` and acts in COUPON_ASSEMBLY -
  confirm it in `11_coupon.json` `removed_by_reads`.

## 5. C3 loop

The rebuild ends with `audit_variants`; C3 fails a read-set leg without an analyst read or a
printed leg carrying WATCH / NO_BET. Positions moved, so:

```bash
.venv/bin/python scripts/sofa/ensure_bridge.py
PYTHONPATH=src:. .venv/bin/python scripts/sofa/read_set.py --date <date> --unread --split 6
```

(`--buffer 5` while early kickoffs pull new matches in) and steps 3-4 on those files only
(paths `_r<n>`) until C3 is clean. `read set: empty` with C3 still red = a printed leg carries
WATCH / NO_BET or `reads.json` is missing: run `rebuild_day.py`, not another read. A `started:` line names the matches a re-read pass left out (kickoff within the 15-min
margin; their analyst would skip them and a read cannot change their legs): C3 keeps listing
them - report them, never read them. At most 3
rounds, then report the C3 lines left. A WATCH / NO_BET on a
builder leg makes that fixture's builder take its next candidate: add to that re-read's
prompt "also read every leg of this fixture's builder candidates in 08_confidence.json
`builders`". A refusing read on a locked leg is a note, not a defect.

Last: `PYTHONPATH=src:. .venv/bin/python scripts/sofa/day_status.py --date <date>` -> `icloud`
must be OK (md5 local = iCloud copy of KUPON pdf + html); a WARN = re-copy with
`build_coupon_html.py --date <date>` (safe on a results day: it keeps the results) and check again; say it in the report (SKIPPED /
NOT_CHECKED named).

## 6. Report

```
ANALIZA:  piłka <n> · tenis <n> · hokej / kosz / siatka / CS2 <n> nóg · dodatkowo (operator) <n> · bufor <n>
RAPORTY:  <ścieżki>
WETA:     <n> zastosowanych, <n> bez dopasowania
READS:    KEEP <n> / WATCH <n> / NO_BET <n> · UNMATCHED_READ <n> · reads_sport <n> · rundy C3 <n> (C3 musi być 0)
KUPON:    runs/sofa/<date>/KUPON_<date>.pdf — pozycje <n> → <n>, buildery <n> → <n>, zablokowane <n>
ZDJĘTE:   <removed_by_reads: noga, odczyt, autor>
iCloud:   Kupony/<DD.MM.YYYY>/ — pdf + html <OK / WARN / SKIPPED> (day_status icloud)
NIE PRZECZYTANO: <nogi zbioru C3 bez odczytu i dlaczego>
```

## Hard rules

- Never write a veto or read of your own, never edit an analyst's report or reasons; a
  `read_requests.json` entry is a request, never a verdict.
- A veto or read only removes; nothing in `sofa` promotes a leg.
- Never print a combined / builder price; no stake sizing.
