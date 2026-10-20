#!/usr/bin/env python3
"""Football player-prop coverage: which SAMPLES gaps can be closed without a
worse row. Read-only evidence
(docs/sofa/evidence/football_player_coverage_2026-10-21.md).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_player_coverage.py \\
        identity --db-path data/sofa.db [--limit 12000]
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_player_coverage.py \\
        window --db-path data/sofa.db --from 2026-09-01 --to 2026-10-19 \\
        [--json-out f]

`identity` (fix a): over the newest `--limit` cached lineups, every appearing
footballer's `totalShots` against the sum of his shot components, with and
without `hitWoodwork` - the decomposition players.PLAYER_METRICS uses to prove
a missing `onTargetScoringAttempt` zero.

`window` (fix b): the history replay of calibrate_from_cache.build_player_rows
(starts only, his starts in the team's newest matches, match_player per
squad, the side found more often), with a 20-match history. Per starter of a
finished target match and lineup metric, rows are grouped:

  BASE  - >= min_sample starts in the newest sample_n (10): today's row;
  W20   - fewer than min_sample there, >= min_sample starts in the newest 20
          (the sample is his newest starts there, at most sample_n of them,
          the oldest within MAX_BUILDER_SAMPLE_AGE_DAYS) - the recovered row;
  LOW   - the same W20 rows priced from only the 3-4 starts of the newest
          ten (the alternative: lower the floor instead of widening).

Each row is read through the installed curve (Calibration.realised, before
the line evidence; p as the replay prices it, no stretch, for every group
alike). Reported per market / direction: rows at confidence >= 0.70, mean
confidence, realised, realised minus confidence with a match bootstrap, and
W20 minus BASE; plus the log-loss of W20 minus LOW on the rows both price
(negative = the wider window is better). Nothing is written but --json-out.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sqlite3
import statistics
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bet.sofa.confidence import (  # noqa: E402
    MAX_BUILDER_SAMPLE_AGE_DAYS,
    Calibration,
    calibration_path_for,
)
from bet.sofa.contracts import GapReason  # noqa: E402
from bet.sofa.engine import (  # noqa: E402
    outside_model_resolution,
    sheet_count_p_raw,
    sheet_predictive_sd,
    winning_boundary,
)
from bet.sofa.listing_index import entity_indexed_events  # noqa: E402
from bet.sofa.players import (  # noqa: E402
    extract_player_metric,
    match_player,
    squad_statistics,
    started,
)
from bet.sofa.samples import (  # noqa: E402
    FRIENDLY_COMPETITION_IDS,
    _competition_id,
    finish_history,
    one_listing_per_match,
)
from bet.sofa.settle import is_completed_event, settle  # noqa: E402
from scripts.sofa import calibrate_from_cache as cfc  # noqa: E402

Direction = Literal["OVER", "UNDER"]
DIRECTIONS: tuple[Direction, Direction] = ("OVER", "UNDER")
LINEUP_METRICS = (
    "player_shots_for",
    "player_shots_on_target_for",
    "player_fouls_for",
    "player_tackles_for",
    "player_assists_for",
    "player_offsides_for",
)
SAMPLE_N = 10
MIN_SAMPLE = 5
WIDE_N = 20
FLOOR = 0.70
BOOT = 1000
SHOT_PARTS = ("onTargetScoringAttempt", "shotOffTarget", "blockedScoringAttempt")


def identity(db: str, limit: int) -> dict[str, Any]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT sofascore_event_id, lineups_json FROM sofa_event_stats "
        "WHERE lineups_json IS NOT NULL AND length(lineups_json) > 100 "
        "ORDER BY sofascore_event_id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    out: collections.Counter[str] = collections.Counter()
    events = 0
    for _eid, raw in rows:
        try:
            lineups = json.loads(raw)
        except ValueError:
            continue
        events += 1
        for side in ("home", "away"):
            for entry in ((lineups or {}).get(side) or {}).get("players") or []:
                st = (entry or {}).get("statistics") or {}
                if st.get("minutesPlayed") is None or "totalShots" not in st:
                    continue
                sot = "present" if "onTargetScoringAttempt" in st else "absent"
                three = sum(st.get(k, 0) for k in SHOT_PARTS)
                four = three + st.get("hitWoodwork", 0)
                out[f"{sot}:3parts_close"] += three == st["totalShots"]
                out[f"{sot}:4parts_close"] += four == st["totalShots"]
                out[f"{sot}:players"] += 1
                if sot == "absent" and four != st["totalShots"]:
                    out["absent:refused_today(4 parts open)"] += 1
                    out["absent:of_which_hitWoodwork"] += "hitWoodwork" in st
    con.close()
    return {"events": events, **dict(sorted(out.items()))}


def _targets(con: sqlite3.Connection, lo: int, hi: int) -> list[dict[str, Any]]:
    ids = [
        int(r[0])
        for r in con.execute(
            "SELECT s.sofascore_event_id FROM sofa_event_stats s "
            "JOIN sofa_listed_event l ON l.event_id = s.sofascore_event_id "
            "WHERE l.sport = 'football' AND l.start_ts >= ? AND l.start_ts < ? "
            "AND s.lineups_json IS NOT NULL AND length(s.lineups_json) > 10",
            (lo, hi),
        )
    ]
    payloads = cfc._event_payloads(con, ids, False)
    events = [payloads[i] for i in ids if i in payloads]
    kept = []
    for e in one_listing_per_match(events):
        if not is_completed_event(e) or not isinstance(
            e.get("startTimestamp"), int
        ):
            continue
        comp = _competition_id(e)
        if comp is not None and comp in FRIENDLY_COMPETITION_IDS:
            continue
        kept.append(e)
    kept.sort(key=lambda e: (int(e["startTimestamp"]), int(e["id"])))
    return kept


def _p(
    metric: str, sample: Sequence[float], line: float, direction: Direction
) -> float | None:
    n = len(sample)
    if n < 1 or all(v == 0.0 for v in sample):
        return None
    mean = statistics.mean(sample)
    var = statistics.variance(sample) if n > 1 else 0.0
    sd = sheet_predictive_sd(metric, "football", mean, var, n, mean)
    p = sheet_count_p_raw(
        metric, mean, sd, winning_boundary(line, direction), direction
    )
    return None if outside_model_resolution(p) else float(p)


def window(db: str, lo: str, hi: str, runs_dir: Path) -> list[dict[str, Any]]:
    cal = Calibration.load(calibration_path_for(hi))
    ladder = {
        m: v
        for m, v in cfc.printed_player_ladder(runs_dir).items()
        if m in LINEUP_METRICS
    }
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    lo_ts = int(datetime.fromisoformat(lo).replace(tzinfo=UTC).timestamp())
    hi_ts = int(datetime.fromisoformat(hi).replace(tzinfo=UTC).timestamp()) + 86400
    targets = _targets(con, lo_ts, hi_ts)
    print(f"targets {len(targets)}", file=sys.stderr)
    cache: collections.OrderedDict[int, dict[bool, Any]] = collections.OrderedDict()

    def squads_of(event_id: int) -> dict[bool, Any]:
        if event_id in cache:
            cache.move_to_end(event_id)
            return cache[event_id]
        found = con.execute(
            "SELECT statistics_json, lineups_json FROM sofa_event_stats "
            "WHERE sofascore_event_id = ?",
            (event_id,),
        ).fetchone()
        stats = json.loads(found[0]) if found and found[0] else None
        lineups = json.loads(found[1]) if found and found[1] else None
        both = {
            h: squad_statistics(lineups, is_home=h, statistics=stats)
            for h in (True, False)
        }
        cache[event_id] = both
        if len(cache) > 40_000:
            cache.popitem(last=False)
        return both

    out: list[dict[str, Any]] = []
    for k, event in enumerate(targets):
        if k % 1000 == 0:
            print(f"{k}/{len(targets)} rows {len(out)}", file=sys.stderr)
        kickoff = int(event["startTimestamp"])
        comp = _competition_id(event)
        history: dict[bool, list[tuple[int, Any]]] = {}
        for is_home in (True, False):
            entity = int(
                ((event.get("homeTeam" if is_home else "awayTeam")) or {}).get("id")
                or 0
            )
            admitted = [
                p
                for p in entity_indexed_events(
                    con, entity, "last", kickoff, cfc.PLAYER_HISTORY_LISTED
                )
                if cfc.admitted_football_event(p, entity, kickoff)
                and not cfc.is_same_match(p, event)
            ]
            recent = finish_history(admitted, entity, "football", comp, kickoff, WIDE_N)
            side: list[tuple[int, Any]] = []
            for idx, past in enumerate(recent):
                own_home = (past.get("homeTeam") or {}).get("id") == entity
                side.append(
                    (
                        idx,
                        (
                            int(past["startTimestamp"]),
                            squads_of(int(past["id"]))[own_home],
                        ),
                    )
                )
            history[is_home] = side
        target = squads_of(int(event["id"]))
        both = set(target.get(True) or {}) & set(target.get(False) or {})
        for is_home in (True, False):
            squad = target.get(is_home)
            if not squad:
                continue
            for name, stats in sorted(squad.items()):
                if stats.get("minutesPlayed") is None or started(stats) is False:
                    continue
                if name in both:
                    continue
                matched = {
                    s: [
                        (idx, ts, sq, match_player(name, sq) if sq else None)
                        for idx, (ts, sq) in hist
                    ]
                    for s, hist in history.items()
                }
                for metric, lines in ladder.items():
                    actual = extract_player_metric(metric, stats)
                    if isinstance(actual, GapReason):
                        continue
                    vals: dict[bool, list[tuple[int, int, float]]] = {}
                    for s, items in matched.items():
                        got = []
                        for idx, ts, sq, key in items:
                            if key is None or started(sq[key]) is False:
                                continue
                            v = extract_player_metric(metric, sq[key])
                            if not isinstance(v, GapReason):
                                got.append((idx, ts, v))
                        vals[s] = got
                    n10 = {
                        s: sum(1 for i, _, _ in v if i < SAMPLE_N)
                        for s, v in vals.items()
                    }
                    if (
                        n10[True] != n10[False]
                        and (n10[True] > n10[False]) == is_home
                        and n10[is_home] >= MIN_SAMPLE
                    ):
                        group = "BASE"
                        sample = [v for i, _, v in vals[is_home] if i < SAMPLE_N]
                        low = None
                    else:
                        n20 = {s: len(v) for s, v in vals.items()}
                        if (
                            n20[True] == n20[False]
                            or (n20[True] > n20[False]) != is_home
                        ):
                            continue
                        own = vals[is_home][:SAMPLE_N]
                        if len(own) < MIN_SAMPLE:
                            continue
                        oldest = (kickoff - own[-1][1]) / 86400
                        if oldest > MAX_BUILDER_SAMPLE_AGE_DAYS:
                            continue
                        group = "W20"
                        sample = [v for _, _, v in own]
                        low_s = [v for i, _, v in vals[is_home] if i < SAMPLE_N]
                        low = low_s if len(low_s) >= 3 else None
                    for line in lines:
                        for direction in DIRECTIONS:
                            p = _p(metric, sample, line, direction)
                            if p is None:
                                continue
                            outcome = settle(actual, line, direction)
                            if outcome not in ("WIN", "LOSS"):
                                continue
                            hit = cal.realised(metric, p, "football", direction, None)
                            row = {
                                "event_id": int(event["id"]),
                                "market": metric,
                                "direction": direction,
                                "line": line,
                                "group": group,
                                "n": len(sample),
                                "p": p,
                                "confidence": None if hit is None else float(hit[0]),
                                "won": outcome == "WIN",
                            }
                            if low is not None:
                                row["p_low"] = _p(metric, low, line, direction)
                            out.append(row)
    con.close()
    return out


def _boot_gap(
    rows: Sequence[dict[str, Any]], seed: int = 7
) -> tuple[float, float, float]:
    ids = sorted({r["event_id"] for r in rows})
    col = {e: i for i, e in enumerate(ids)}
    a = np.zeros((3, len(ids)))
    for r in rows:
        j = col[r["event_id"]]
        a[0, j] += 1
        a[1, j] += r["won"]
        a[2, j] += r["confidence"]
    w = np.random.default_rng(seed).multinomial(
        len(ids), np.full(len(ids), 1 / len(ids)), size=BOOT
    )
    tot = a.sum(axis=1)
    d = a @ w.T
    draws = (d[1] - d[2]) / d[0]
    return (
        float((tot[1] - tot[2]) / tot[0]),
        float(np.quantile(draws, 0.025)),
        float(np.quantile(draws, 0.975)),
    )


def _boot_diff(
    g: Sequence[dict[str, Any]], b: Sequence[dict[str, Any]], seed: int = 11
) -> tuple[float, float, float]:
    ids = sorted({r["event_id"] for r in g} | {r["event_id"] for r in b})
    col = {e: i for i, e in enumerate(ids)}

    def arr(rows: Sequence[dict[str, Any]]) -> np.ndarray:
        a = np.zeros((3, len(ids)))
        for r in rows:
            j = col[r["event_id"]]
            a[0, j] += 1
            a[1, j] += r["won"]
            a[2, j] += r["confidence"]
        return a

    ga, ba = arr(g), arr(b)
    w = np.random.default_rng(seed).multinomial(
        len(ids), np.full(len(ids), 1 / len(ids)), size=BOOT
    )
    gt, bt = ga.sum(axis=1), ba.sum(axis=1)
    point = (gt[1] - gt[2]) / gt[0] - (bt[1] - bt[2]) / bt[0]
    gd, bd = ga @ w.T, ba @ w.T
    with np.errstate(invalid="ignore", divide="ignore"):
        draws = (gd[1] - gd[2]) / gd[0] - (bd[1] - bd[2]) / bd[0]
    draws = draws[np.isfinite(draws)]
    return (
        float(point),
        float(np.quantile(draws, 0.025)),
        float(np.quantile(draws, 0.975)),
    )


def _ll(p: float, won: bool) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -math.log(p if won else 1 - p)


def _boot_ll(
    rows: Sequence[dict[str, Any]], seed: int = 13
) -> tuple[float, float, float, int]:
    """log-loss(p) - log-loss(p_low), per row mean, match bootstrap."""
    ids = sorted({r["event_id"] for r in rows})
    col = {e: i for i, e in enumerate(ids)}
    a = np.zeros((2, len(ids)))
    for r in rows:
        j = col[r["event_id"]]
        a[0, j] += 1
        a[1, j] += _ll(r["p"], r["won"]) - _ll(r["p_low"], r["won"])
    w = np.random.default_rng(seed).multinomial(
        len(ids), np.full(len(ids), 1 / len(ids)), size=BOOT
    )
    tot = a.sum(axis=1)
    d = a @ w.T
    draws = d[1] / d[0]
    return (
        float(tot[1] / tot[0]),
        float(np.quantile(draws, 0.025)),
        float(np.quantile(draws, 0.975)),
        len(rows),
    )


def report(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| market | dir | group | rows >=0.70 | matches | conf | realised "
        "| gap [95%] | W20 - BASE [95%] |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    printable = [
        r for r in rows if r["confidence"] is not None and r["confidence"] >= FLOOR
    ]
    keys = sorted({(r["market"], r["direction"]) for r in printable})
    for key in keys + [("ALL", "ALL")]:
        scope = [
            r
            for r in printable
            if key == ("ALL", "ALL") or (r["market"], r["direction"]) == key
        ]
        for grp in ("BASE", "W20"):
            g = [r for r in scope if r["group"] == grp]
            if len(g) < 30:
                continue
            gap = _boot_gap(g)
            diff = ""
            if grp == "W20":
                base = [r for r in scope if r["group"] == "BASE"]
                if base:
                    diff = "{:+.1f} [{:+.1f}, {:+.1f}]".format(
                        *(100 * x for x in _boot_diff(g, base))
                    )
            matches = len({r["event_id"] for r in g})
            conf = sum(r["confidence"] for r in g) / len(g)
            won = sum(r["won"] for r in g) / len(g)
            gap_s = "{:+.1f} [{:+.1f}, {:+.1f}]".format(*(100 * x for x in gap))
            lines.append(
                f"| {key[0]} | {key[1]} | {grp} | {len(g)} | {matches} | "
                f"{conf:.3f} | {won:.3f} | {gap_s} | {diff} |"
            )
    both = [r for r in rows if r["group"] == "W20" and r.get("p_low") is not None]
    if both:
        ll = _boot_ll(both)
        lines.append("")
        lines.append(
            f"log-loss W20 - LOW (3-4 starts of the newest ten) on {ll[3]} rows: "
            f"{ll[0]:+.5f} [{ll[1]:+.5f}, {ll[2]:+.5f}] (negative = W20 better)"
        )
    counts = collections.Counter((r["group"]) for r in rows)
    pc = collections.Counter(r["group"] for r in printable)
    lines.append(f"rows: {dict(counts)}; at confidence >= 0.70: {dict(pc)}")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("section", choices=("identity", "window"))
    ap.add_argument("--db-path", required=True)
    ap.add_argument("--limit", type=int, default=12000)
    ap.add_argument("--from", dest="lo", default="2026-09-01")
    ap.add_argument("--to", dest="hi", default="2026-10-19")
    ap.add_argument("--runs-dir", default=str(ROOT / "runs" / "sofa"))
    ap.add_argument("--json-out")
    ap.add_argument("--rows-in", help="re-report a saved --json-out")
    args = ap.parse_args(argv)
    try:
        if args.section == "identity":
            print(json.dumps(identity(args.db_path, args.limit), indent=1))
            return 0
        if args.rows_in:
            rows = json.loads(Path(args.rows_in).read_text(encoding="utf-8"))
        else:
            rows = window(args.db_path, args.lo, args.hi, Path(args.runs_dir))
        if args.json_out:
            Path(args.json_out).write_text(json.dumps(rows), encoding="utf-8")
        print("\n".join(report(rows)))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
