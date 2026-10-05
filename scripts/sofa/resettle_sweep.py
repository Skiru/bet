#!/usr/bin/env python3
"""Re-settle every recent day that still holds an ungraded printed leg
(plan 2026-10-05, F0.6).

Statistics of some leagues close days after the match (National League,
Primera B Nacional, Liga AUF: corners at D+5..D+7), and the morning step
re-settled D-5 alone, so a leg whose statistic arrived on another day was
never graded (ANALIZA_WYNIKOW_2026-10-04 3.5: 85 corner legs had their
statistic in the DB and still read unsettled). For every day in
[--from, --to] (the morning: D-14 .. D-2) whose printed legs are not all
graded and at least one could still be (settleability.resettle_worthy: a
statistic gap, a match not finished or postponed, a failed request, no
reason on record), this runs

    run_settle.py --date <d> --refetch-stat-gaps

(SETTLE merges into the day's files and never inserts a graded row twice),
and then once ``regrade_settled.py --apply`` for the rows whose statistics
were re-fetched after they were graded. ``--include-day`` forces a day into
the plan (the morning's D-5, whose unpriced sheet rows the fits read).

--refetch-stat-gaps asks Sofascore past the cache, so the bridge is
required: without one (GET /health, a tab polled within 60 s) nothing is
re-settled and the sweep exits 1 PARTIAL, saying so. ``--dry-run`` prints
the plan only and needs no bridge.

Exit 0 OK, 1 PARTIAL (no bridge, a day FAILED, the breaker opened, regrade
failed), 2 FAILED (every planned day FAILED, or the DB unreadable).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/resettle_sweep.py \\
        --from <D-14> --to <D-2> [--include-day <D-5>] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import settleability as st  # noqa: E402
from bet.sofa.bridge_transport import DEFAULT_BRIDGE_URL  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.timeutil import now  # noqa: E402

SETTLE = _REPO / "scripts" / "sofa" / "run_settle.py"
REGRADE = _REPO / "scripts" / "sofa" / "regrade_settled.py"


def bridge_health() -> dict[str, Any] | None:
    """The bridge server's /health document, or None when it does not answer."""
    try:
        with urllib.request.urlopen(DEFAULT_BRIDGE_URL + "/health", timeout=5) as r:
            doc = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    return doc if isinstance(doc, dict) else None


def plan(
    runs_dir: Path, db_path: str, days: list[str], include: list[str]
) -> dict[str, int]:
    """{day: printed legs SETTLE could still grade}, plus the forced days."""
    conn = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)
    try:
        first = st.first_graded_times(st.load_regrade_logs(runs_dir))
        states = {d: st.day_states(conn, runs_dir, d, first) for d in days}
    finally:
        conn.close()
    out = st.days_needing_resettle(states)
    for d in include:
        out.setdefault(d, 0)
    return dict(sorted(out.items()))


def _summary(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        if line.startswith("SOFA_SUMMARY: "):
            try:
                doc = json.loads(line[len("SOFA_SUMMARY: "):])
            except ValueError:
                return {}
            return doc if isinstance(doc, dict) else {}
    return {}


def run(cmd: list[str]) -> tuple[int, dict[str, Any]]:
    """Run one stage, its output passed through; (exit code, SOFA_SUMMARY)."""
    env = {**os.environ,
           "PYTHONPATH": os.pathsep.join([str(_REPO / "src"), str(_REPO)])}
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False,
                          cwd=str(_REPO), env=env)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode, _summary(proc.stdout)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    default_from, default_to = st.sweep_range(now().strftime("%Y-%m-%d"))
    ap.add_argument("--from", dest="start", default=default_from)
    ap.add_argument("--to", dest="end", default=default_to)
    ap.add_argument("--include-day", action="append", default=[],
                    help="re-settle this day whatever its printed legs say")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan only (no bridge, nothing written)")
    args = ap.parse_args()
    config = SofaConfig.from_env()
    runs_dir = Path(config.runs_dir)
    try:
        todo = plan(runs_dir, config.db_path, st.date_range(args.start, args.end),
                    args.include_day)
    except sqlite3.Error as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2
    for day, n in todo.items():
        print(f"PLAN {day}: {n} printed leg(s) still gradable", flush=True)
    if not todo:
        print("PLAN nothing to re-settle", flush=True)

    metrics: dict[str, Any] = {"from": args.start, "to": args.end,
                               "planned": todo, "dry_run": args.dry_run}
    if args.dry_run:
        print("SOFA_SUMMARY: " + json.dumps(
            {"stage": "RESETTLE_SWEEP", "verdict": "OK", "metrics": metrics}))
        return 0

    bridge_ok, why = (True, "") if not todo else st.bridge_ready(bridge_health())
    codes: dict[str, int] = {}
    breaker = False
    regrade_code: int | None = None
    if not bridge_ok:
        print(
            f"NO_BRIDGE: {why}. --refetch-stat-gaps needs the bridge; nothing "
            f"re-settled ({len(todo)} day(s) planned). Bring it up "
            "(ensure_bridge.py) and run the sweep again.",
            file=sys.stderr, flush=True,
        )
    else:
        for day in todo:
            code, summary = run(
                [sys.executable, str(SETTLE), "--date", day, "--refetch-stat-gaps"])
            codes[day] = code
            if (summary.get("metrics") or {}).get("breaker_open"):
                breaker = True
                print(f"BREAKER_OPEN on {day}: the sweep stops here",
                      file=sys.stderr, flush=True)
                break
        if codes:
            regrade_code, _ = run([sys.executable, str(REGRADE), "--apply"])
    verdict = st.sweep_verdict(codes, breaker, bridge_ok, regrade_code)
    metrics.update({"bridge": bridge_ok, "settle_exit": codes,
                    "breaker_open": breaker, "regrade_exit": regrade_code})
    print("SOFA_SUMMARY: " + json.dumps(
        {"stage": "RESETTLE_SWEEP", "verdict": verdict, "metrics": metrics}),
        flush=True)
    return {"OK": 0, "PARTIAL": 1, "FAILED": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
