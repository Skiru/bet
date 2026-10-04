#!/usr/bin/env python3
"""Is a sample mis-centred on a make-up fixture, after a layoff, in a
congested week? Measured on the cache before any gate reads bet.sofa.schedule.

For every finished REGULAR league match (comparability.match_kind) from
--start on with both sides' ten-match sample (SAMPLES' reading: goals at 90
minutes, no statistic of an extra-time match, friendlies out, the goal
markets from the fixture's competition - comparability.pick_same_competition)
the forecast of a metric is the sample mean, and the residual is
actual - forecast. Matches are grouped by the context bet.sofa.schedule
computes:

  makeup        a not-played (postponed / canceled / interrupted / suspended)
                event of the same two sides in the same competition before it
  rest          the smaller of the two sides' days since its last finished
                competitive match: <4, 4-7, 8-14, 15-20, >=21 (LONG_LAYOFF)
  congested     either side played >= 3 matches in the 7 days before

Per group: matches, mean residual with a 95% interval (resampling matches),
and the two event-id halves. A group whose residual differs from the rest is
a context the sample does not describe; one that does not is a flag worth
showing and nothing more.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_schedule_context.py \\
        [--start 2025-08-01] [--end 2026-10-03] [--metrics goals_total corners_total]
"""

from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

from bet.sofa.comparability import (  # noqa: E402
    SAME_COMPETITION_METRICS,
    MatchKind,
    competition_id,
    pick_same_competition,
)
from bet.sofa.schedule import CONGESTED_7D, LONG_LAYOFF_DAYS  # noqa: E402
from scripts.sofa.measure_sample_composition import (  # noqa: E402
    Past,
    Target,
    before,
    load,
)

_NOT_PLAYED = ("postponed", "canceled", "interrupted", "suspended")
REST_BINS = (
    (0, 4), (4, 8), (8, 15), (15, LONG_LAYOFF_DAYS), (LONG_LAYOFF_DAYS, 10_000)
)


def not_played_pairs(db: Path) -> dict[tuple[frozenset[int], int], list[int]]:
    """(pair of sides, competition) -> start times of their not-played events."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out: dict[tuple[frozenset[int], int], list[int]] = defaultdict(list)
    marks = ",".join("?" * len(_NOT_PLAYED))
    for (js,) in con.execute(
        "SELECT event_json FROM sofa_listed_event WHERE sport = 'football' "
        f"AND json_extract(event_json, '$.status.type') IN ({marks})",
        _NOT_PLAYED,
    ):
        e = json.loads(js)
        comp, ts = competition_id(e), e.get("startTimestamp")
        try:
            pair = frozenset((int(e["homeTeam"]["id"]), int(e["awayTeam"]["id"])))
        except (KeyError, TypeError, ValueError):
            continue
        if comp is not None and isinstance(ts, int):
            out[(pair, comp)].append(ts)
    return out


def sample(history: Sequence[Past], t: Target, metric: str, n: int = 10) -> list[Past]:
    b = before(history, t.ts, metric)
    if metric in SAME_COMPETITION_METRICS:
        picked = pick_same_competition(
            b, t.competition, n, lambda p: p.competition,
            lambda p: p.kind is MatchKind.REGULAR,
        )
        if picked is not None:
            return picked
    return [p for p in b if p.kind is not MatchKind.FRIENDLY][:n]


def rest_days(history: Sequence[Past], ts: int) -> tuple[float | None, int]:
    keys = [p.ts for p in history]
    prior = [p for p in history[: bisect.bisect_left(keys, ts)]
             if p.kind is not MatchKind.FRIENDLY]
    if not prior:
        return None, 0
    week = sum(1 for p in prior if ts - p.ts <= 7 * 86400)
    return (ts - prior[-1].ts) / 86400, week


def interval(values: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    idx = rng.integers(0, len(values), size=(1000, len(values)))
    means = values[idx].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--db", type=Path, default=Path("data/sofa.db"))
    ap.add_argument("--start", default="2025-08-01")
    ap.add_argument("--end", default="2026-10-03")
    ap.add_argument("--metrics", nargs="+", default=["goals_total", "corners_total"])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    start = int(datetime.fromisoformat(args.start).replace(tzinfo=UTC).timestamp())
    end = int(datetime.fromisoformat(args.end).replace(tzinfo=UTC).timestamp()) + 86400
    with_stats = any(not m.startswith("goals") for m in args.metrics)
    history, targets, _season = load(args.db, with_stats)
    pending = not_played_pairs(args.db)
    rng = np.random.default_rng(20261004)
    text = [f"# Schedule context vs the sample, {args.start}..{args.end}", "",
            "residual = actual - sample mean; 95% from resampling matches.", ""]
    for metric in args.metrics:
        stat = metric.rsplit("_", 1)[0]
        groups: dict[str, list[tuple[int, float]]] = defaultdict(list)
        for t in targets:
            if not start <= t.ts < end or stat not in t.values:
                continue
            a = sample(history.get(t.home, []), t, metric)
            b = sample(history.get(t.away, []), t, metric)
            if len(a) < 10 or len(b) < 10:
                continue
            values = [p.value(metric) or 0.0 for p in a + b]
            forecast = sum(values) / len(values)
            actual = t.values[stat][0] + t.values[stat][1]
            resid = actual - forecast
            groups["all"].append((t.event_id, resid))
            makeup = any(
                s < t.ts
                for s in pending.get((frozenset((t.home, t.away)), t.competition), [])
            )
            groups["makeup" if makeup else "not makeup"].append((t.event_id, resid))
            ra, wa = rest_days(history.get(t.home, []), t.ts)
            rb, wb = rest_days(history.get(t.away, []), t.ts)
            rests = [r for r in (ra, rb) if r is not None]
            if rests:
                low = min(rests)
                for lo, hi in REST_BINS:
                    if lo <= low < hi:
                        groups[f"rest {lo}-{hi if hi < 10_000 else 'inf'} d"].append(
                            (t.event_id, resid))
                if max(rests) >= LONG_LAYOFF_DAYS:
                    groups["either side >= 21 d"].append((t.event_id, resid))
            congested = max(wa, wb) >= CONGESTED_7D
            groups["congested" if congested else "not congested"].append(
                (t.event_id, resid))
        text += [f"## {metric}", "",
                 "| group | matches | mean residual [95%] | even | odd |",
                 "|---|---|---|---|---|"]
        for name, rows in groups.items():
            ids = np.asarray([r[0] for r in rows])
            res = np.asarray([r[1] for r in rows])
            ci_lo, ci_hi = interval(res, rng)
            even, odd = res[ids % 2 == 0], res[ids % 2 == 1]
            text.append(
                f"| {name} | {len(rows)} | {res.mean():+.3f} "
                f"[{ci_lo:+.3f}; {ci_hi:+.3f}] | "
                f"{even.mean() if len(even) else float('nan'):+.3f} | "
                f"{odd.mean() if len(odd) else float('nan'):+.3f} |"
            )
        text.append("")
        print("\n".join(text[-(len(groups) + 4):]), flush=True)
    if args.out:
        args.out.write_text("\n".join(text) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
