"""Audit the CS2 shadow measurement over a date range. Reads files only.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_cs2.py --from D --to D

1. coverage   - every snapshotted series by CS2_SETTLE state and tournament:
                how much of Superbet's CS2 board Sofascore can grade at all
2. price      - per market family and overall: series, graded sides, the mean
                devigged price, the hit rate, their gap, Brier, flat ROI, the
                median margin
3. by price   - the same, favourites (fair p >= 0.5) against underdogs

Both sides of every graded line are in, so a pooled ROI is minus the margin by
construction; the gap between the price and the hit rate, and whether it
survives the split by family and price, is the measurement. Lines of one
series are correlated - read `series`, not only `sides`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cs2 import SETTLED_FILE, FamilyStats, cs2_day_dir, summarize  # noqa: E402
from bet.sofa.cs2_engine import (  # noqa: E402
    UNFITTED,
    compare_to_price,
    elo_backtest,
    load_history,
)
from bet.sofa.cs2_store import history_summary  # noqa: E402
from bet.sofa.db import get_connection, migrate  # noqa: E402


def load(runs_dir: str, date_from: str, date_to: str) -> list[dict[str, Any]]:
    day = datetime.strptime(date_from, "%Y-%m-%d")
    end = datetime.strptime(date_to, "%Y-%m-%d")
    events: list[dict[str, Any]] = []
    while day <= end:
        path = cs2_day_dir(runs_dir, day.strftime("%Y-%m-%d")) / SETTLED_FILE
        if path.exists():
            for eid, rec in json.loads(path.read_text(encoding="utf-8"))[
                "events"
            ].items():
                events.append({**rec, "superbet_event_id": eid})
        day += timedelta(days=1)
    return events


def _row(s: FamilyStats) -> str:
    return (
        f"| {s.family} | {s.events} | {s.sides} | {s.fair_p:.3f} | {s.hit:.3f} "
        f"| {100 * (s.hit - s.fair_p):+.1f} | {s.brier:.3f} | {100 * s.roi:+.1f}% "
        f"| {100 * s.margin:.1f}% |"
    )


HEADER = [
    "| family | series | sides | fair p | hit | gap pp | Brier | ROI | margin |",
    "|---|---|---|---|---|---|---|---|---|",
]


def render(events: list[dict[str, Any]], date_from: str, date_to: str) -> list[str]:
    out = [f"# CS2 shadow audit {date_from}..{date_to}", "", "## 1. coverage", ""]
    by_state: dict[str, int] = defaultdict(int)
    by_tour: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for ev in events:
        by_state[ev["state"]] += 1
        by_tour[ev.get("tournament") or "?"][ev["state"]] += 1
    out.append(
        f"series: {len(events)}  "
        + ", ".join(
            f"{k} {v}" for k, v in sorted(by_state.items(), key=lambda kv: -kv[1])
        )
    )
    out += ["", "| tournament | states |", "|---|---|"]
    for tour, st in sorted(by_tour.items(), key=lambda kv: -sum(kv[1].values())):
        out.append(f"| {tour} | " + ", ".join(f"{k} {v}" for k, v in st.items()) + " |")

    rows = [
        dict(r, superbet_event_id=ev["superbet_event_id"])
        for ev in events
        for r in ev.get("graded") or []
    ]
    out += ["", "## 2. price against outcome, by family", ""]
    if not rows:
        return [*out, "no graded lines yet"]
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_family[r["family"]].append(r)
    stats = [summarize(rs, fam) for fam, rs in by_family.items()]
    table = sorted((s for s in stats if s), key=lambda s: -s.sides)
    total = summarize(rows, "ALL")
    out += HEADER + [_row(s) for s in table] + ([_row(total)] if total else [])

    out += ["", "## 3. by price", ""]
    fav = summarize([r for r in rows if (r.get("fair_p") or 0) >= 0.5], "fair p >= 0.5")
    dog = summarize([r for r in rows if (r.get("fair_p") or 1) < 0.5], "fair p < 0.5")
    out += HEADER + [_row(s) for s in (fav, dog) if s]
    out += ["", "## 3b. model against price (Brier, lower is better)", ""]
    found = [compare_to_price(rs, fam) for fam, rs in by_family.items()]
    comps = sorted((c for c in found if c is not None), key=lambda c: -c.sides)
    overall = compare_to_price(rows, "ALL")
    if not comps:
        out.append("no graded side carries a model probability yet")
    else:
        out += [
            "| family | series | sides | price | model | blend | model better |",
            "|---|---|---|---|---|---|---|",
        ]
        for c in [*comps, *([overall] if overall else [])]:
            out.append(
                f"| {c.family} | {c.series} | {c.sides} | {c.brier_price:.4f} "
                f"| {c.brier_model:.4f} | {c.brier_blend:.4f} "
                f"| {'yes' if c.model_beats_price else 'no'} |"
            )
        out.append("")
        out.append("UNFITTED_CONSTANTS: " + ", ".join(UNFITTED))
    out += [
        "",
        "ROI is flat, one unit per side, both sides of every line. The pooled",
        "figure is minus the margin by construction; the gap is the measurement.",
    ]
    return out


def render_history(summary: dict[str, Any]) -> list[str]:
    """What the cs2_* tables hold: the history the CS2 engine reads."""

    def day(ts: int | None) -> str:
        return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d") if ts else "-"

    out = [
        "## 4. history (cs2_* in data/sofa.db)",
        "",
        f"series {summary['series']} (complete {summary['series_complete']}), "
        f"{day(summary['first_ts'])}..{day(summary['last_ts'])}, "
        f"teams {summary['teams']}",
        f"finished maps {summary['maps_finished']}, with player rows "
        f"{summary['maps_with_players']}, in overtime {summary['maps_overtime']}; "
        f"player-map rows {summary['player_rows']}",
        "",
        "| tournament | series |",
        "|---|---|",
    ]
    return out + [f"| {t} | {n} |" for t, n in summary["top_tournaments"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="date_from")
    parser.add_argument("--to", dest="date_to")
    parser.add_argument(
        "--history", action="store_true", help="also summarise the cs2_* tables"
    )
    args = parser.parse_args()
    if not args.history and not (args.date_from and args.date_to):
        parser.error("--from and --to, or --history")
    config = SofaConfig.from_env()
    lines: list[str] = []
    if args.date_from and args.date_to:
        events = load(config.runs_dir, args.date_from, args.date_to)
        lines += render(events, args.date_from, args.date_to)
    if args.history:
        migrate(config.db_path)
        with get_connection(config.db_path) as conn:
            lines += ["", *render_history(history_summary(conn))]
            # Cut at now: load_history's LOOKBACK_DAYS runs back from the cut,
            # and a far-future cut once left the window empty ("0 maps").
            bt = elo_backtest(load_history(conn, int(time.time()) + 1, None))

        def fmt(v: float | None) -> str:
            return f"{v:.4f}" if v is not None else "-"

        lines += [
            "",
            f"Rating backtest (each series from the ratings at its start; 0.25 is a "
            f"coin): {bt['maps_predicted']} maps predicted, held-out "
            f"{bt['maps_held_out']}: raw Elo {fmt(bt['brier_raw_held_out'])}, "
            f"calibrated {fmt(bt['brier_calibrated_held_out'])}.",
        ]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
