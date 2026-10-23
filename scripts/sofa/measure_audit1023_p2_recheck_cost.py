#!/usr/bin/env python3
"""The bridge cost of IDENTITY_FRESH_RECHECK_ALL (coverage audit 2026-10-23
P2; offline, read-only): how many extra `team/<id>/events/next/0` requests a
day the switch would have asked, from the day's SPORT_IDENTITY records and
the loops' run clocks.

Per (day, sport) the SPORT_IDENTITY runs are the loops' own command lines
(runs/sofa/shadow/daily_<d>.log, runs/sofa/cs2/daily_<d>.log: "[ts] $
scripts/sofa/run_sport_identity.py --date <D> ..."). Per event whose LAST
record is NOT_IDENTIFIED with a queried team (the event was asked by every
run until its start), every run before the start:

- in FRESH_RECHECK_WITHIN (3 h) of it: one fresh re-ask of the queried team
  when its page came from the cache and the reason is not K5's own
  NO_GAME_WITHIN_1H (those the old rule already re-asked), and one fresh
  page of the second team when it has an id (or the event is query-only: an
  upper bound, its query id is not replayed);
- before that window: the second team's cached page, one request per 6 h
  (events TTL) from the first run.

An upper bound: the per-run "once per team" rule and a second team with no
query id are not replayed, and an event later IDENTIFIED (its earlier
refusals overwritten) is not counted - its misses are not in the file.

  PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_audit1023_p2_recheck_cost.py \\
      --from 2026-10-21 --to 2026-10-23
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import sport_identity as si  # noqa: E402

RUN = re.compile(r"^\[(?P<ts>[^\]]+)\] \$ scripts/sofa/run_sport_identity\.py "
                 r"--date (?P<date>\S+)(?P<rest>.*)$")
TTL = timedelta(hours=6)


def run_clocks(runs_dir: Path, day: str) -> dict[str, list[datetime]]:
    """sport -> the SPORT_IDENTITY run clocks for `day` (any loop log)."""
    out: dict[str, list[datetime]] = defaultdict(list)
    logs = sorted(runs_dir.glob("shadow/daily_*.log")) + sorted(
        runs_dir.glob("cs2/daily_*.log"))
    for log in logs:
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            m = RUN.match(line)
            if not m or m["date"] != day:
                continue
            sports = re.findall(r"--sport (\S+)", m["rest"]) or list(si.SPORT_KEYS)
            at = datetime.fromisoformat(m["ts"])
            for sp in sports:
                out[sp].append(at)
    return {k: sorted(v) for k, v in out.items()}


def cost(runs_dir: Path, day: str) -> dict[str, Any]:
    doc = json.loads((runs_dir / day / si.FIXTURES_FILE).read_text(encoding="utf-8"))
    clocks = run_clocks(runs_dir, day)
    per: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in doc.get("fixtures") or []:
        sport = str(r["sport"])
        per[sport]["events"] += 1
        if r.get("status") != si.NOT_IDENTIFIED:
            continue
        if not isinstance(r.get("queried_team_id"), int):
            continue
        per[sport]["missed_with_query"] += 1
        kick = datetime.fromisoformat(str(r["kickoff_utc"]).replace("Z", "+00:00"))
        runs = [t for t in clocks.get(sport, []) if t < kick]
        near = [t for t in runs if kick - t <= si.FRESH_RECHECK_WITHIN]
        far = [t for t in runs if kick - t > si.FRESH_RECHECK_WITHIN]
        q_is_t1 = r.get("team1_id") is not None or (
            r.get("team2_id") is None)  # query-only: team1's query first
        second = r.get("team2_id") if q_is_t1 else r.get("team1_id")
        has_second = isinstance(second, int) or bool(r.get("query_only"))
        old_k5 = r.get("reason") == "NO_GAME_WITHIN_1H"
        if r.get("listing_from_cache") and not old_k5:
            per[sport]["fresh_first"] += len(near)
        if has_second:
            per[sport]["second_near"] += len(near)
            if far:
                span = far[-1] - far[0]
                per[sport]["second_far"] += 1 + int(span / TTL)
        per[sport]["events_charged"] += 1
    total = {k: sum(v.get(k, 0) for v in per.values())
             for k in ("fresh_first", "second_near", "second_far")}
    return {"day": day, "sports": {k: dict(v) for k, v in per.items()},
            "runs": {k: len(v) for k, v in clocks.items()},
            "extra_requests": sum(total.values()), **total}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument("--from", dest="first", default="2026-10-21")
    ap.add_argument("--to", dest="last", default="2026-10-23")
    args = ap.parse_args()
    d = datetime.fromisoformat(args.first)
    while d.strftime("%Y-%m-%d") <= args.last:
        day = d.strftime("%Y-%m-%d")
        if (Path(args.runs_dir) / day / si.FIXTURES_FILE).exists():
            print(json.dumps(cost(Path(args.runs_dir), day), ensure_ascii=False))
        d += timedelta(days=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
