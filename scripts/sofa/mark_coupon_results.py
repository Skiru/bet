#!/usr/bin/env python3
"""Mark a settled day's coupon with its results: KUPON_<d>.pdf and .html.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/mark_coupon_results.py \
        --date 2026-10-17
    ... --from 2026-10-13 --to 2026-10-17 [--force] [--no-render]

Grades every printed position exactly as the ledger does
(record_results.graded_confidence), writes runs/sofa/<d>/13_results.json
(bet.sofa.coupon_results) and re-renders the day's PDF and HTML with each row
coloured (green won, red lost, yellow not known / refund), the leg's claim
beside what the market actually counted, and a percent summary at the end.

The re-render is a view of a finished day, not a print: it records no
printed/<ts>.json and skips the freshness guards that refuse a coupon priced
on older curves (build_coupon_pdf.py --with-results). It runs only when the
results changed or the PDF is older than them (--force: always).
record_results.py calls it for every date it records.

Offline (the database and the day's artifacts). Exit 0 marked (pending legs
shown yellow), 1 a day not marked (no coupon, a render failed), 2 a crash.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import coupon_results as cr  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    coupon_artifact,
    is_sheet_sport,
    printed_builders,
    printed_singles,
)
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cs2 import write_atomic  # noqa: E402
from bet.sofa.settleability import date_range  # noqa: E402
from bet.sofa.timeutil import now  # noqa: E402
from scripts.sofa.record_results import graded_confidence  # noqa: E402

PDF_SCRIPT = _REPO / "scripts" / "sofa" / "build_coupon_pdf.py"


def results_doc(runs_dir: str, date: str, db_path: str) -> dict[str, Any] | None:
    """The day's results document, None when the day has no coupon."""
    path = coupon_artifact(Path(runs_dir) / date)
    if path.name != "11_coupon.json" or not path.exists():
        return None
    coupon = json.loads(path.read_text(encoding="utf-8"))
    graded = graded_confidence(runs_dir, date, db_path)
    ids = {int(s["sofascore_event_id"]) for s in printed_singles(coupon)
           if is_sheet_sport(s)}
    ids |= {int(b["sofascore_event_id"]) for b in printed_builders(coupon)}
    stamp = now().isoformat().replace("+00:00", "Z")
    return cr.compute(date, graded, cr.match_scores(db_path, ids), stamp)


def _same(old: dict[str, Any] | None, new: dict[str, Any]) -> bool:
    return old is not None and all(old.get(k) == new.get(k)
                                   for k in ("legs", "builders"))


def render(runs_dir: str, date: str) -> tuple[bool, str]:
    """build_coupon_pdf.py --with-results (it writes the HTML too)."""
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(
        [str(_REPO / "src"), str(_REPO), os.environ.get("PYTHONPATH", "")])}
    proc = subprocess.run(
        [sys.executable, str(PDF_SCRIPT), "--date", date, "--runs-dir", runs_dir,
         "--with-results"],
        capture_output=True, text=True, env=env, check=False)
    tail = (proc.stdout.strip().splitlines() or [""])[-1]
    return proc.returncode == 0, tail if proc.returncode == 0 else proc.stderr.strip()


def mark(runs_dir: str, date: str, db_path: str, force: bool = False,
         do_render: bool = True) -> tuple[str, dict[str, Any] | None]:
    """(verdict, summary): MARKED / UNCHANGED / NO_COUPON / RENDER_FAILED: ..."""
    run = Path(runs_dir) / date
    doc = results_doc(runs_dir, date, db_path)
    if doc is None:
        return "NO_COUPON", None
    old = cr.load(run)
    out = run / cr.RESULTS_FILE
    pdf = run / f"KUPON_{date}.pdf"
    changed = not _same(old, doc)
    if changed:
        write_atomic(out, json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    summary = cr.builders_summary(doc["builders"].values())
    stale_pdf = not pdf.exists() or pdf.stat().st_mtime < out.stat().st_mtime
    if not do_render or not (changed or stale_pdf or force):
        return ("WRITTEN" if changed else "UNCHANGED"), summary
    ok, msg = render(runs_dir, date)
    return ("MARKED" if ok else f"RENDER_FAILED: {msg}"), summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date")
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    ap.add_argument("--force", action="store_true",
                    help="re-render even when the results did not change")
    ap.add_argument("--no-render", action="store_true",
                    help="write 13_results.json only")
    args = ap.parse_args()
    if args.date:
        dates = [args.date]
    elif args.start and args.end:
        dates = date_range(args.start, args.end)
    else:
        ap.error("--date, or --from and --to")
    config = SofaConfig.from_env()
    failed = 0
    try:
        for date in dates:
            verdict, _ = mark(config.runs_dir, date, config.db_path,
                              args.force, not args.no_render)
            results = cr.load(Path(config.runs_dir) / date)
            counts = cr.builders_summary((results or {}).get("legs", {}).values())
            print(json.dumps({"stage": "MARK_RESULTS", "date": date,
                              "verdict": verdict, "legs": counts}))
            failed += verdict.startswith("RENDER_FAILED") or verdict == "NO_COUPON"
    except Exception as exc:  # noqa: BLE001 - a crash is FAILED, never pending
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
