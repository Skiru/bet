#!/usr/bin/env python3
"""runs/sofa/<d>/family_record.json - every market family's record on the
official coupon's printed legs of the days before <d> (bet.sofa.family_record),
graded as the ledger grades them. Read by the HTML view only.

build_coupon_pdf.py / build_coupon_html.py call `ensure` before the page: the
record is recomputed when absent, made for another day, or older than the
ledger (record_results.py wrote since). Read-only on the DB.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_family_record.py \\
        --date <d> [--force]

Exit 0 OK, 2 failed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import family_record as fr  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.timeutil import now  # noqa: E402
from scripts.sofa.record_results import graded_confidence, ledger_path  # noqa: E402


def graded_day(runs_dir: str, day: str, db_path: str) -> list[fr.Graded]:
    out: list[fr.Graded] = []
    for g in graded_confidence(runs_dir, day, db_path):
        if g["variant"] != fr.VARIANT:
            continue
        for s in g["singles"]:
            src = s["source"]
            odds = s.get("odds") or src.get("offered_odds")
            out.append((src, str(s.get("outcome")),
                        None if odds is None else float(odds)))
    return out


def compute(runs_dir: str, day: str, db_path: str) -> dict[str, Any]:
    graded = {d: graded_day(runs_dir, d, db_path) for d in fr.window(day)}
    return fr.build(day, graded, now())


def is_fresh(runs_dir: str, day: str) -> bool:
    run = Path(runs_dir) / day
    if fr.load(run, day) is None:
        return False
    ledger = ledger_path(runs_dir)
    return not ledger.exists() or (
        (run / fr.FILE).stat().st_mtime >= ledger.stat().st_mtime)


def ensure(runs_dir: str, day: str, db_path: str, force: bool = False) -> Path:
    """The day's record on disk, recomputed only when needed."""
    path = Path(runs_dir) / day / fr.FILE
    if force or not is_fresh(runs_dir, day):
        write_atomic(path, json.dumps(compute(runs_dir, day, db_path), indent=1,
                                      ensure_ascii=False))
    return path


def ensure_quietly(runs_dir: str, day: str, db_path: str | None = None) -> str:
    """`ensure` for the page renders: never raises - the error text, or ""
    (the page then reads whatever record of the day is on disk, or none)."""
    try:
        ensure(runs_dir, day, db_path or SofaConfig.from_env().db_path)
    except Exception as exc:  # noqa: BLE001 - the page is a view; never fail it
        return f"{type(exc).__name__}: {exc}"
    return ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"))
    ap.add_argument("--db-path", default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    db = args.db_path or SofaConfig.from_env().db_path
    try:
        path = ensure(args.runs_dir, args.date, db, force=args.force)
    except Exception as exc:  # noqa: BLE001 - reported, exit 2
        print(json.dumps({"stage": "FAMILY_RECORD", "verdict": "FAILED",
                          "error": f"{type(exc).__name__}: {exc}"}))
        return 2
    doc = json.loads(path.read_text(encoding="utf-8"))
    plus = [k for k, v in doc["families"].items() if fr.on_plus(v, doc["min_legs"])]
    print(json.dumps({"stage": "FAMILY_RECORD", "verdict": "OK",
                      "output_path": str(path), "days": doc["days"],
                      "families": len(doc["families"]), "on_plus": plus},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
