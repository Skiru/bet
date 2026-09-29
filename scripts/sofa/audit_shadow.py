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


# When a cell may be read at all. Lines of one game are correlated, so the
# error of a gap is clustered by game; a gap inside two of those errors is
# noise, and even outside them a cell is only a lead until the data spans
# enough days - one slate is one set of conditions.
MIN_GAMES = 30
MIN_DAYS = 7
SIGNAL_SE = 2.0


def gap_se(rows: list[dict[str, Any]]) -> float | None:
    """Standard error of mean(outcome - fair p), clustered by game: the
    sandwich estimator, centred on the mean gap, with the G/(G-1) correction."""
    rs = [r for r in rows if r.get("fair_p") is not None]
    if len(rs) < 2:
        return None
    resid: dict[str, float] = defaultdict(float)
    count: dict[str, int] = defaultdict(int)
    for r in rs:
        won = 1.0 if r["outcome"] == "WIN" else 0.0
        key = str(r["superbet_event_id"])
        resid[key] += won - r["fair_p"]
        count[key] += 1
    games = len(resid)
    if games < 2:
        return None
    mean = sum(resid.values()) / len(rs)
    centred = sum((resid[g] - count[g] * mean) ** 2 for g in resid)
    return float((games / (games - 1) * centred) ** 0.5 / len(rs))


def read_of(s: FamilyStats, se: float | None, days: int) -> str:
    """What a cell may be read as: never more than the data carries."""
    if s.events < MIN_GAMES or se is None:
        return f"too few (<{MIN_GAMES} games)"
    gap = abs(s.hit - s.fair_p)
    if gap <= 1e-9 or gap <= SIGNAL_SE * se:
        # No gap is no finding, whatever its error (pooled 0.5/0.5 pairs read
        # exactly 0 with an error of exactly 0).
        return "noise"
    if days < MIN_DAYS:
        return f"lead only (<{MIN_DAYS} days)"
    return "signal"


def _stat(rows: list[dict[str, Any]], label: str) -> str | None:
    s = summarize(rows, label)
    if s is None:
        return None
    se = gap_se(rows)
    days = len({r.get("day") for r in rows if r.get("day")})
    se_txt = "-" if se is None else f"{100 * se:.1f}"
    return (
        f"| {s.family} | {s.events} | {s.sides} | {s.fair_p:.3f} | {s.hit:.3f} "
        f"| {100 * (s.hit - s.fair_p):+.1f} | {se_txt} | {s.brier:.3f} "
        f"| {100 * s.roi:+.1f}% | {100 * s.margin:.1f}% | {read_of(s, se, days)} |"
    )


HEADER = [
    "| family | games | sides | fair p | hit | gap pp | SE pp | Brier | ROI "
    "| margin | read |",
    "|---|---|---|---|---|---|---|---|---|---|---|",
]


def _table(cells: list[tuple[list[dict[str, Any]], str]]) -> list[str]:
    return HEADER + [x for rs, label in cells if (x := _stat(rs, label))]


def _family_table(rows: list[dict[str, Any]]) -> list[str]:
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_family[r["family"]].append(r)
    ranked = sorted(by_family.items(), key=lambda kv: -len(kv[1]))
    return _table([(rs, fam) for fam, rs in ranked] + [(rows, "ALL")])


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
        dict(
            r,
            superbet_event_id=ev["superbet_event_id"],
            day=str(ev.get("kickoff_utc") or "")[:10],
        )
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
    out += _table(
        [
            ([r for r in rows if (r.get("fair_p") or 0) >= 0.5], "fair p >= 0.5"),
            ([r for r in rows if (r.get("fair_p") or 1) < 0.5], "fair p < 0.5"),
        ]
    )

    out += ["", "### 4. overtime", ""]
    out += _table(
        [
            ([r for r in fav_side if r.get("overtime")], "overtime"),
            ([r for r in fav_side if not r.get("overtime")], "no overtime"),
        ]
    )

    out += ["", "### 5. price age", ""]
    out += _table(
        [
            (
                [r for r in fav_side if (r.get("minutes_before_kickoff") or 0) <= 60],
                "<= 60 min",
            ),
            (
                [r for r in fav_side if (r.get("minutes_before_kickoff") or 0) > 60],
                "> 60 min",
            ),
        ]
    )
    days = len({r["day"] for r in rows if r.get("day")})
    out += [
        "",
        f"`read`: fewer than {MIN_GAMES} games is too few; a gap inside "
        f"{SIGNAL_SE:g} SE (clustered by game) is noise; outside it, a lead "
        f"until the range spans {MIN_DAYS} days (this one: {days}). With this "
        "many cells about one in twenty reads as a signal by chance alone - "
        "a signal is a question for the next weeks, not a bet.",
    ]
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
