"""Audit the hockey / basketball / volleyball shadow measurement. Files only.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_shadow.py --from D --to D
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_shadow.py --from D --to D \\
        --sport hockey

Per sport:

1. coverage   - every snapshotted game by SHADOW_SETTLE state, and the
                tournaments with the most games: how much of Superbet's board
                Sofascore can grade at all
2. price      - per market family and overall, on the FAVOURITE side of
                every line: games, lines, the mean devigged price, the hit
                rate, their gap, Brier, flat ROI, the median margin
2b. direction - the same on a FIXED side: OVER of every total, Superbet's
                first-named team (T1) of everything else - a lean toward
                overs or toward the first-named side shows here
3. by price   - every graded side, favourites (fair p >= 0.5) against
                underdogs
4. overtime   - favourite sides, games that went to overtime against not
5. price age  - favourite sides priced within an hour of the start against
                older ones (an event whose late fetches came back empty keeps
                an earlier price; this is where that shows)

Both sides of a line are graded or neither, their fair p sum to one and one of
them wins - so pooled, the mean fair p and the hit rate are 0.500 whatever the
price is worth. Sections 2, 2b, 4 and 5 therefore keep one side per line
(`cs2.one_side_per_line`); the gap between the price and the hit rate there,
and whether it survives the splits, is the measurement. Lines of one game are
correlated - read `games`, not only `sides`. Nothing here is a bet list.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cs2 import FamilyStats, one_side_per_line, summarize  # noqa: E402
from bet.sofa.shadow import SETTLED_FILE, SPORTS, SportKey, shadow_day_dir  # noqa: E402

TOP_TOURNAMENTS = 15


def load(
    runs_dir: str, sport: SportKey, date_from: str, date_to: str
) -> list[dict[str, Any]]:
    """Every game in range, once. A game rescheduled across midnight is in two
    day files; the SETTLED record wins, else the later day's."""
    day = datetime.strptime(date_from, "%Y-%m-%d")
    end = datetime.strptime(date_to, "%Y-%m-%d")
    events: dict[str, dict[str, Any]] = {}
    while day <= end:
        path = shadow_day_dir(runs_dir, sport, day.strftime("%Y-%m-%d")) / SETTLED_FILE
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            for eid, rec in data["events"].items():
                prev = events.get(eid)
                if prev and prev["state"] == "SETTLED" and rec["state"] != "SETTLED":
                    continue
                events[eid] = {**rec, "superbet_event_id": eid}
        day += timedelta(days=1)
    return list(events.values())


def _row(s: FamilyStats) -> str:
    return (
        f"| {s.family} | {s.events} | {s.sides} | {s.fair_p:.3f} | {s.hit:.3f} "
        f"| {100 * (s.hit - s.fair_p):+.1f} | {s.brier:.3f} | {100 * s.roi:+.1f}% "
        f"| {100 * s.margin:.1f}% |"
    )


HEADER = [
    "| family | games | sides | fair p | hit | gap pp | Brier | ROI | margin |",
    "|---|---|---|---|---|---|---|---|---|",
]


def _family_table(rows: list[dict[str, Any]]) -> list[str]:
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_family[r["family"]].append(r)
    stats = [summarize(rs, fam) for fam, rs in by_family.items()]
    table = sorted((s for s in stats if s), key=lambda s: -s.sides)
    total = summarize(rows, "ALL")
    return HEADER + [_row(s) for s in table] + ([_row(total)] if total else [])


def render_sport(sport: SportKey, events: list[dict[str, Any]]) -> list[str]:
    out = [f"## {sport}", "", "### 1. coverage", ""]
    if not events:
        return [*out, "no settled file in range"]
    by_state: dict[str, int] = defaultdict(int)
    by_tour: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for ev in events:
        by_state[ev["state"]] += 1
        by_tour[ev.get("tournament") or "?"][ev["state"]] += 1
    out.append(
        f"games: {len(events)}  "
        + ", ".join(
            f"{k} {v}" for k, v in sorted(by_state.items(), key=lambda kv: -kv[1])
        )
    )
    out += ["", "| tournament | states |", "|---|---|"]
    ranked = sorted(by_tour.items(), key=lambda kv: -sum(kv[1].values()))
    for tour, st in ranked[:TOP_TOURNAMENTS]:
        out.append(f"| {tour} | " + ", ".join(f"{k} {v}" for k, v in st.items()) + " |")
    if len(ranked) > TOP_TOURNAMENTS:
        out.append(f"| ... {len(ranked) - TOP_TOURNAMENTS} more | |")

    rows = [
        dict(r, superbet_event_id=ev["superbet_event_id"])
        for ev in events
        for r in ev.get("graded") or []
    ]
    out += ["", "### 2. price against outcome, by family (favourite side)", ""]
    if not rows:
        return [*out, "no graded lines yet"]
    fav_side = one_side_per_line(rows, "favourite")
    out += _family_table(fav_side)
    out += ["", "### 2b. fixed side: OVER of a total, T1 otherwise", ""]
    out += _family_table(one_side_per_line(rows, "fixed"))

    out += ["", "### 3. by price", ""]
    fav = summarize([r for r in rows if (r.get("fair_p") or 0) >= 0.5], "fair p >= 0.5")
    dog = summarize([r for r in rows if (r.get("fair_p") or 1) < 0.5], "fair p < 0.5")
    out += HEADER + [_row(s) for s in (fav, dog) if s]

    out += ["", "### 4. overtime", ""]
    ot = summarize([r for r in fav_side if r.get("overtime")], "overtime")
    reg = summarize([r for r in fav_side if not r.get("overtime")], "no overtime")
    out += HEADER + [_row(s) for s in (ot, reg) if s]

    out += ["", "### 5. price age", ""]
    fresh = summarize(
        [r for r in fav_side if (r.get("minutes_before_kickoff") or 0) <= 60],
        "<= 60 min",
    )
    old = summarize(
        [r for r in fav_side if (r.get("minutes_before_kickoff") or 0) > 60],
        "> 60 min",
    )
    out += HEADER + [_row(s) for s in (fresh, old) if s]
    return out


def render(
    runs_dir: str, sports: list[SportKey], date_from: str, date_to: str
) -> list[str]:
    out = [f"# Shadow audit {date_from}..{date_to}", ""]
    for sport in sports:
        out += render_sport(sport, load(runs_dir, sport, date_from, date_to))
        out.append("")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="date_from", required=True)
    ap.add_argument("--to", dest="date_to", required=True)
    ap.add_argument("--sport", choices=list(SPORTS), action="append")
    args = ap.parse_args()
    sports: list[SportKey] = args.sport or list(SPORTS)
    lines = render(SofaConfig.from_env().runs_dir, sports, args.date_from, args.date_to)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
