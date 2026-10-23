#!/usr/bin/env python3
"""Coverage audit 2026-10-23 P7 (B8): the CS2 lineup rating without the
team-id gate (epochs.CS2_LINEUP_ELO_UNRATED_FROM_UTC). Read-only.

Walk-forward over the stored CS2 history exactly as the sport curves are
fitted (sport_confidence.cs2_walk_forward_rows: map and player Elo replayed in
time order, the calibrations refitted every REFIT_DAYS_CS2 on the
predictions made before the refit). Each series after the warm-up is priced
twice from the books at its start - gate on (today) and gate off
(RatingModel.lineup_unrated) - and its maps / series result graded:

- `rated`: both team ids MIN_MAPS_RATED - the two numbers must be identical
  (no change elsewhere);
- `gained`: no number today, a number under the switch - judged against
  the coin and the walk-forward home share (log loss, Brier) and for
  calibration (realised minus claimed, overall and by the favourite's band,
  calibration slope), every interval a bootstrap over series (games);
- the rated group's own calibration beside it, as the yardstick.

    PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/measure_audit1023_p7_cs2_lineup_unrated.py \\
        --db-path data/refit_2026-10-23_allin/sofa_copy.db [--warmup-days 120] \\
        [--boot 2000] [--json-out f]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import cs2_engine  # noqa: E402
from bet.sofa import sport_confidence as scf  # noqa: E402

EPS = 1e-6
BANDS = ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01))


def ll(p: float, y: int) -> float:
    p = min(max(p, EPS), 1 - EPS)
    return -math.log(p if y else 1 - p)


def fit_variant(model_u: cs2_engine.RatingModel,
                upoints: list[tuple[int, float, float]], variant: str,
                first_ts: int, warm_days: int) -> None:
    """The unrated calibration: `engine` (cs2_engine.fit_unrated: the rated
    lineup intercept kept, the slope fitted), `both` (intercept and slope
    fitted on every point), `warm` (both, only on points after the history's
    first `warm_days`)."""
    if variant == "engine":
        cs2_engine.fit_unrated(model_u, [(g, y) for _, g, y in upoints])
        return
    cut = first_ts + warm_days * 86400 if variant == "warm" else 0
    pts = [(g, y) for ts, g, y in upoints if ts >= cut]
    if len(pts) >= cs2_engine.MIN_FIT:
        ua, ub = cs2_engine.fit_logistic([g for g, _ in pts], [y for _, y in pts])
        model_u.ua, model_u.ub, model_u.u_fit = ua, max(0.0, ub), len(pts)


def replay(maps: list[cs2_engine.MapRow], series: dict[int, scf.SeriesRow],
           eval_from: int, variant: str = "engine", warm_days: int = 120
           ) -> list[dict[str, Any]]:
    """One record per evaluated series: group, its maps' (p_old, p_new, y)
    in the home orientation, and the series winner's (p_old, p_new, y)."""
    book = cs2_engine.EloBook()
    players = cs2_engine.PlayerEloBook()
    points: list[tuple[float, float]] = []
    ppoints: list[tuple[float, float]] = []
    upoints: list[tuple[int, float, float]] = []
    model = cs2_engine.RatingModel(book)
    model_u = model
    next_refit = 0
    home_wins = home_maps = 0
    by_series: dict[int, list[cs2_engine.MapRow]] = {}
    for m in maps:
        by_series.setdefault(m.event_id, []).append(m)
    out: list[dict[str, Any]] = []
    for eid, smaps in by_series.items():
        start = smaps[0].start_ts
        if start >= next_refit:
            model = scf._cs2_refit(book, players, points, ppoints)
            model_u = replace(model, lineup_unrated=True)
            fit_variant(model_u, upoints, variant, maps[0].start_ts, warm_days)
            next_refit = start + scf.REFIT_DAYS_CS2 * 86400
        home, away = smaps[0].home_id, smaps[0].away_id
        if start >= eval_from and model.p_fit >= cs2_engine.MIN_FIT:
            p_old = model.p_map(home, away, True)
            p_new = model_u.p_map(home, away, True)
            # the variant without its own calibration: the rated pairs' one
            gap = players.gap(home, away)
            p_alt = (None if p_old is not None or gap is None
                     or model.p_fit < cs2_engine.MIN_FIT
                     else cs2_engine._sigmoid(model.pa + model.pb * gap))
            group = ("rated" if p_old is not None else
                     "gained" if p_new is not None else "none")
            srow = series.get(eid)
            rec: dict[str, Any] = {
                "eid": eid, "ts": start, "group": group,
                "home_rate": home_wins / home_maps if home_maps else 0.5,
                "maps": [(p_old, p_new, 1 if m.home_won else 0, p_alt)
                         for m in smaps],
                "series": None,
                "played": (book.played[home], book.played[away]),
            }
            if (srow is not None and srow.best_of and srow.home_maps is not None
                    and srow.away_maps is not None
                    and srow.home_maps != srow.away_maps):
                best_of = int(srow.best_of)

                def sp(p: float | None, bo: int = best_of) -> float | None:
                    if p is None:
                        return None
                    try:
                        dist = cs2_engine.series_distribution(round(p, 6), bo)
                    except ValueError:
                        return None
                    p1 = sum(q for (a, b), q in dist.items() if a > b)
                    p2 = sum(q for (a, b), q in dist.items() if a < b)
                    return cs2_engine.side_given_no_push(p1, p2, True)
                rec["series"] = (sp(p_old), sp(p_new),
                                 1 if srow.home_maps > srow.away_maps else 0,
                                 sp(p_alt))
            out.append(rec)
        if book.rated(home, away):
            d = cs2_engine.logit_diff(book, home, away)
            points.extend((d, 1.0 if m.home_won else 0.0) for m in smaps)
            gap = players.gap(home, away)
            if gap is not None:
                ppoints.extend((gap, 1.0 if m.home_won else 0.0) for m in smaps)
        else:
            gap = players.gap(home, away)
            if gap is not None:
                upoints.extend((start, gap, 1.0 if m.home_won else 0.0)
                               for m in smaps)
        for m in smaps:
            winner, loser = ((m.home_id, m.away_id) if m.home_won
                             else (m.away_id, m.home_id))
            book.update(winner, loser)
            players.update(m)
            home_maps += 1
            home_wins += 1 if m.home_won else 0
    return out


def _slope(ps: list[float], ys: list[int]) -> float:
    """b of y ~ sigmoid(a + b logit(p)) (1 = calibrated spread)."""
    xs = [math.log(min(max(p, EPS), 1 - EPS) / (1 - min(max(p, EPS), 1 - EPS)))
          for p in ps]
    a, b = 0.0, 1.0
    for _ in range(50):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in zip(xs, ys, strict=True):
            q = 1 / (1 + math.exp(-(a + b * x)))
            w = q * (1 - q)
            ga += q - y
            gb += (q - y) * x
            haa += w
            hab += w * x
            hbb += w * x * x
        det = haa * hbb - hab * hab
        if det <= 1e-12:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a, b = a - da, b - db
        if abs(da) + abs(db) < 1e-10:
            break
    return b


def stats(recs: list[dict[str, Any]], level: str, which: int
          ) -> dict[str, float] | None:
    """Per-row numbers of one group: which = 0 old p, 1 new p."""
    rows: list[tuple[float, int, float]] = []
    for r in recs:
        items = r["maps"] if level == "map" else ([r["series"]] if r["series"] else [])
        for it in items:
            p = it[which]
            if p is not None:
                rows.append((cs2_engine.clamp(p), int(it[2]), r["home_rate"]))
    if not rows:
        return None
    n = len(rows)
    out = {
        "n": n,
        "logloss": sum(ll(p, y) for p, y, _ in rows) / n,
        "logloss_coin": math.log(2),
        "logloss_home_rate": sum(ll(h, y) for _, y, h in rows) / n,
        "brier": sum((p - y) ** 2 for p, y, _ in rows) / n,
        "claimed": sum(p for p, _, _ in rows) / n,
        "realised": sum(y for _, y, _ in rows) / n,
    }
    fav = [(max(p, 1 - p), y if p >= 0.5 else 1 - y) for p, y, _ in rows]
    out["fav_claimed"] = sum(p for p, _ in fav) / n
    out["fav_realised"] = sum(y for _, y in fav) / n
    out["slope"] = _slope([p for p, _, _ in rows], [y for _, y, _ in rows])
    return out


def boot(recs: list[dict[str, Any]], level: str, which: int, n_boot: int,
         seed: int = 7) -> dict[str, list[float]]:
    rng = random.Random(seed)
    keys = ("fav_gap", "gap", "ll_vs_coin", "ll_vs_home_rate", "slope")
    acc: dict[str, list[float]] = {k: [] for k in keys}
    for _ in range(n_boot):
        sample = [recs[rng.randrange(len(recs))] for _ in recs]
        s = stats(sample, level, which)
        if s is None:
            continue
        acc["fav_gap"].append(s["fav_realised"] - s["fav_claimed"])
        acc["gap"].append(s["realised"] - s["claimed"])
        acc["ll_vs_coin"].append(s["logloss"] - s["logloss_coin"])
        acc["ll_vs_home_rate"].append(s["logloss"] - s["logloss_home_rate"])
        acc["slope"].append(s["slope"])
    out: dict[str, list[float]] = {}
    for k, v in acc.items():
        v.sort()
        if v:
            out[k] = [round(v[int(0.025 * len(v))], 4),
                      round(v[int(0.975 * len(v)) - 1], 4)]
    return out


def bands(recs: list[dict[str, Any]], level: str, which: int
          ) -> list[dict[str, Any]]:
    rows: list[tuple[float, int]] = []
    for r in recs:
        items = r["maps"] if level == "map" else ([r["series"]] if r["series"] else [])
        for it in items:
            p = it[which]
            if p is not None:
                p = cs2_engine.clamp(p)
                rows.append((max(p, 1 - p), it[2] if p >= 0.5 else 1 - it[2]))
    out = []
    for lo, hi in BANDS:
        cell = [(p, y) for p, y in rows if lo <= p < hi]
        if cell:
            out.append({"band": f"{lo:.1f}-{min(hi, 1.0):.1f}", "n": len(cell),
                        "claimed": round(sum(p for p, _ in cell) / len(cell), 4),
                        "realised": round(sum(y for _, y in cell) / len(cell), 4)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db-path", required=True)
    ap.add_argument("--before", default=None, help="UTC date; default today")
    ap.add_argument("--warmup-days", type=int, default=120)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--variant", choices=("engine", "both", "warm"),
                    default="engine",
                    help="the unrated pairs' calibration (fit_variant)")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    before = (datetime.fromisoformat(args.before).replace(tzinfo=UTC)
              if args.before else datetime.now(UTC))
    maps, series = scf.load_cs2(args.db_path, int(before.timestamp()))
    first = maps[0].start_ts
    eval_from = first + args.warmup_days * 86400
    recs = replay(maps, series, eval_from, args.variant, args.warmup_days)
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in recs:
        groups.setdefault(r["group"], []).append(r)
    mismatch = sum(1 for r in groups.get("rated", []) for po, pn, *_ in r["maps"]
                   if po != pn)
    report: dict[str, Any] = {
        "db": args.db_path, "before": before.isoformat(),
        "variant": args.variant,
        "history_from": datetime.fromtimestamp(first, UTC).isoformat(),
        "eval_from": datetime.fromtimestamp(eval_from, UTC).isoformat(),
        "series_by_group": {g: len(v) for g, v in groups.items()},
        "maps_by_group": {g: sum(len(r["maps"]) for r in v)
                          for g, v in groups.items()},
        "rated_rows_changed": mismatch,
    }
    last30 = int(before.timestamp()) - 30 * 86400
    report["last_30_days_series_by_group"] = {
        g: sum(1 for r in v if r["ts"] >= last30) for g, v in groups.items()}
    gained = groups.get("gained", [])
    report["gained_team_maps_played"] = sorted(
        min(r["played"]) for r in gained)[:: max(1, len(gained) // 20)]
    for level in ("map", "series"):
        report[level] = {
            "gained_new": stats(gained, level, 1),
            "gained_new_ci": boot(gained, level, 1, args.boot) if gained else {},
            "gained_new_bands": bands(gained, level, 1),
            "gained_rated_calibration": stats(gained, level, 3),
            "gained_rated_calibration_ci": (boot(gained, level, 3, args.boot)
                                            if gained else {}),
            "gained_rated_calibration_bands": bands(gained, level, 3),
            "rated": stats(groups.get("rated", []), level, 0),
            "rated_ci": boot(groups.get("rated", []), level, 0,
                             max(200, args.boot // 5)),
            "rated_bands": bands(groups.get("rated", []), level, 0),
        }
    text = json.dumps(report, indent=1, default=str)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
