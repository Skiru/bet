"""Measure, per metric, how the two sides of a match correlate.

`joint.py` needs one number per metric: the correlation between what side A
records and what side B records in the same match. It is not a modelling
choice, it is a measurement, and it is the difference between pricing "każda z
drużyn powyżej 3.5 rzutów rożnych" correctly and pricing it as though the two
teams played separate games.

The number it needs is the **residual** correlation, after each team's own
mean is removed — not the raw one. The raw correlation of two teams' corner
counts is -0.1978, but a large part of that is simply strong teams taking many
corners while their opponents take few, and `joint.py` already carries that:
each side's marginal is built from that side's own sample, so the strength
difference is in the means before any dependence is applied. Feeding the raw
number in would count the same effect twice. Measured on the same pool, the
residual is -0.1452 for corners and -0.0928 for shots — roughly a third of the
raw figure for shots, which is the size of the double count.

Both are written out. `correlation` is the residual, because that is what the
model consumes; `raw_correlation` is kept beside it so the gap between them
stays visible rather than being quietly resolved in one direction.

The pool is every finished match already cached in `sofa_event_stats` and
`sofa_event_detail`, not the day's samples: the day's samples are a few
thousand observations chosen for today's fixtures, and a dependence parameter
fitted on them would move every time the slate moves.

Writes config/sofa_side_correlations.json. A metric whose pool is smaller than
MIN_PAIRS is written with a null correlation and `joint.py` then treats the two
sides as independent, which is the honest default when nothing was measured.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from bet.sofa.config import SofaConfig
from bet.sofa.metrics import calculate_cards_points, extract_flat_statistics

MIN_PAIRS = 200

# A team needs a few matches of its own before its mean is worth subtracting.
MIN_MATCHES_PER_TEAM = 4

# metric base name -> Sofascore statistics key
STAT_KEYS = {
    "corners": "cornerKicks",
    "shots": "totalShotsOnGoal",
    "shots_on_target": "shotsOnGoal",
    "fouls": "fouls",
    "offsides": "offsides",
    "aces": "aces",
    "double_faults": "doubleFaults",
    "games": "gamesWon",
}


def pearson(pairs: list[tuple[float, float]]) -> float | None:
    n = len(pairs)
    if n < 2:
        return None
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sx = math.sqrt(sum((p[0] - mx) ** 2 for p in pairs))
    sy = math.sqrt(sum((p[1] - my) ** 2 for p in pairs))
    if sx == 0.0 or sy == 0.0:
        return None
    return sum((p[0] - mx) * (p[1] - my) for p in pairs) / (sx * sy)


def event_sides(conn: sqlite3.Connection) -> dict[int, tuple[int, int]]:
    """Which two entities played each cached event.

    /statistics does not name the teams, so the pairing comes off the listings
    the sampler already stores. Without it the two columns cannot be attributed
    to teams and no mean can be removed.
    """
    sides: dict[int, tuple[int, int]] = {}
    for (events_json,) in conn.execute("SELECT events_json FROM sofa_entity_events"):
        try:
            events = json.loads(events_json)
        except ValueError:
            continue
        if isinstance(events, dict):
            events = events.get("events", [])
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            event_id = event.get("id")
            home = (event.get("homeTeam") or {}).get("id")
            away = (event.get("awayTeam") or {}).get("id")
            if event_id and home and away:
                sides[event_id] = (home, away)
    return sides


def residual_pearson(
    rows: list[tuple[int, int, float, float]],
) -> tuple[float | None, int]:
    """Correlation of the two sides after each side's own mean is removed."""
    totals: dict[int, list[float]] = defaultdict(list)
    for home, away, home_value, away_value in rows:
        totals[home].append(home_value)
        totals[away].append(away_value)
    means = {
        entity: sum(values) / len(values)
        for entity, values in totals.items()
        if len(values) >= MIN_MATCHES_PER_TEAM
    }
    residuals = [
        (home_value - means[home], away_value - means[away])
        for home, away, home_value, away_value in rows
        if home in means and away in means
    ]
    return pearson(residuals), len(residuals)


def collect(db_path: Path) -> dict[str, list[tuple[int, int, float, float]]]:
    pools: dict[str, list[tuple[int, int, float, float]]] = defaultdict(list)
    conn = sqlite3.connect(str(db_path))
    try:
        sides = event_sides(conn)
        cursor = conn.execute(
            "SELECT sofascore_event_id, statistics_json, incidents_json, status_type "
            "FROM sofa_event_stats"
        )
        for event_id, statistics_json, incidents_json, status_type in cursor:
            if status_type != "finished":
                continue
            pairing = sides.get(event_id)
            if pairing is None:
                continue
            home_id, away_id = pairing

            if statistics_json:
                try:
                    stats_raw = json.loads(statistics_json)
                except ValueError:
                    stats_raw = None
                if stats_raw:
                    flat = extract_flat_statistics(stats_raw)
                    all_period: dict[str, Any] = flat.get("ALL", {})
                    for base, key in STAT_KEYS.items():
                        value = all_period.get(key)
                        if value is None:
                            continue
                        home, away = value
                        pools[base].append(
                            (home_id, away_id, float(home), float(away))
                        )

            if incidents_json:
                try:
                    incidents_raw = json.loads(incidents_json)
                except ValueError:
                    incidents_raw = None
                if incidents_raw:
                    points = calculate_cards_points(incidents_raw)
                    if not isinstance(points, str) and points is not None:
                        home_pts, away_pts = points
                        pools["cards_points"].append(
                            (home_id, away_id, float(home_pts), float(away_pts))
                        )
    finally:
        conn.close()
    return pools


def collect_goals(db_path: Path) -> list[tuple[int, int, float, float]]:
    """Goals come off the listing, not /statistics — the same route metrics.py
    uses. `Obie drużyny strzelą` is a both-sides market like any other and
    needs the same dependence parameter."""
    pairs: list[tuple[int, int, float, float]] = []
    seen: set[int] = set()
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute("SELECT events_json FROM sofa_entity_events")
        for (events_json,) in cursor:
            try:
                events = json.loads(events_json)
            except ValueError:
                continue
            if isinstance(events, dict):
                events = events.get("events", [])
            if not isinstance(events, list):
                continue
            for event in events:
                if not isinstance(event, dict):
                    continue
                event_id = event.get("id")
                if not isinstance(event_id, int) or event_id in seen:
                    continue
                status = event.get("status") or {}
                if status.get("type") != "finished":
                    continue
                sport = (
                    ((event.get("tournament") or {}).get("category") or {}).get(
                        "sport"
                    )
                    or {}
                ).get("slug")
                if sport != "football":
                    continue
                home = (event.get("homeScore") or {}).get("current")
                away = (event.get("awayScore") or {}).get("current")
                home_id = (event.get("homeTeam") or {}).get("id")
                away_id = (event.get("awayTeam") or {}).get("id")
                if home is None or away is None or not home_id or not away_id:
                    continue
                seen.add(event_id)
                pairs.append((home_id, away_id, float(home), float(away)))
    finally:
        conn.close()
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="config/sofa_side_correlations.json")
    args = parser.parse_args()

    config = SofaConfig.from_env()
    db_path = Path(config.db_path)

    pools = collect(db_path)
    pools["goals"] = collect_goals(db_path)

    out: dict[str, Any] = {
        "_provenance": (
            "`correlation` is the RESIDUAL Pearson correlation between the "
            "two sides of one match, after each side's own mean is removed - "
            "that is the quantity bet.sofa.joint consumes, because each "
            "side's marginal already carries its own level. `raw_correlation` "
            "is the unadjusted figure, kept so the double count stays "
            "visible. Measured over every finished match cached in sofa.db. "
            "Regenerate with scripts/sofa/measure_side_correlations.py."
        ),
        "_min_pairs": MIN_PAIRS,
    }
    for base in sorted(pools):
        rows = pools[base]
        raw = (
            pearson([(h, a) for _, _, h, a in rows])
            if len(rows) >= MIN_PAIRS
            else None
        )
        residual, residual_n = (
            residual_pearson(rows) if len(rows) >= MIN_PAIRS else (None, 0)
        )
        if residual is not None and residual_n < MIN_PAIRS:
            residual = None
        out[base] = {
            "correlation": round(residual, 4) if residual is not None else None,
            "raw_correlation": round(raw, 4) if raw is not None else None,
            "pairs": len(rows),
            "residual_pairs": residual_n,
        }

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    measured = sum(
        1
        for k, v in out.items()
        if not k.startswith("_") and v["correlation"] is not None
    )
    summary = {
        "stage": "SIDE_CORRELATIONS",
        "verdict": "OK",
        "metrics": {"measured": measured, "total": len(pools)},
        "output_path": str(path),
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
