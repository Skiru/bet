---
description: Verify a built sofa day adversarially through the sofa-verifier agent, merge its reads (author verifier) into reads.json with merge_reads.py, rebuild with rebuild_day.py and audit again.
argument-hint: dzisiaj | wczoraj | YYYY-MM-DD
---

The method lives in `sofa-verifier`; this command launches it, merges its
reads and rebuilds.

## Argument

`$ARGUMENTS`: `dzisiaj` (default) / `wczoraj` / `YYYY-MM-DD` -> `<d>`
(`date -u +%F`; the pipeline's logs are local time). Require
`runs/sofa/<d>/11_coupon.json`; without it, stop and say the day is not built.

## Procedure

1. Pick the report path: `runs/sofa/<d>/<d>_weryfikacja.md`, or the next
   free `_r<n>` (`_r1`, `_r2`, ...) when it exists - never overwrite.
2. Launch `sofa-verifier` in the **foreground** with `<d>` and that path.
   It writes the report itself and returns <= 12 lines with the path it
   **actually wrote**; never re-type its report or its JSON. If it still
   comes back as a background task, wait for its completion notification
   and check the report file exists before step 3 (2026-10-29).
3. Merge its reads from that returned path (dry run first):

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/merge_reads.py --date <d> --report <returned path> --author verifier --dry-run
PYTHONPATH=src:. .venv/bin/python scripts/sofa/merge_reads.py --date <d> --report <returned path> --author verifier
```

   Exit 0 merged, 1 merged with an `UNMATCHED_VETO`, 2 refused (nothing
   written; a removal without a fact too): relaunch the verifier with the refusal line / findings and the next `_r<n>`
   path - never fix its JSON or `reads.json` yourself; after 2 relaunches
   report the failure. On a past day whose
   legs have all started, stop here: report the reads as not applied.
4. Rebuild with the one rebuild command (dry run first, never stage scripts
   by hand - a CONFIDENCE on a stale offer empties the coupon to its locked
   legs):

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <d> --dry-run
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <d>
```

5. The rebuild ends with `audit_variants` / `audit_coupon` - read them there; re-run
   them by hand only after `rebuild_day.py --skip-audits`. A removed leg lets the next match into the read set: when C3 names unread
   legs, run `/sofa-analyze`'s C3 loop (step 5) - not its whole pass:
   `.venv/bin/python scripts/sofa/ensure_bridge.py`, then
   `PYTHONPATH=src:. .venv/bin/python scripts/sofa/read_set.py --date <d> --unread --split 6`,
   analysts on those files, merge, rebuild, audit, until C3 is clean.
   If the verifier asked for a SHEET re-run, that is the operator's call -
   report it, do not run it here.
6. iCloud: `PYTHONPATH=src:. .venv/bin/python scripts/sofa/day_status.py --date <d>` -> `icloud`
   must be OK (md5 local = iCloud copy of KUPON pdf + html); a WARN = re-copy with
   `build_coupon_html.py --date <d>` (safe on a results day: it keeps the results) and check again; say it in the report (SKIPPED /
   NOT_CHECKED named).

## Report (Polish, to the operator)

- The verifier's report path and its 12-line summary as returned.
- Its `verify_legs.py --all` screen line (legs, DEFECT / NOTE).
- merge_reads' exit code and the WATCH / NO_BET lines it printed.
- rebuild_day's exit code, the legs before / after, C1-C3 / U1-U3 result.
- `day_status` `icloud` OK / WARN / SKIPPED.
- Every skipped check named; a verdict with **no stake recommendation**.
