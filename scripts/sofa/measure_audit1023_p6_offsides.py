#!/usr/bin/env python3
"""P6 of the coverage audit 2026-10-23 (B6): a footballer's zero offsides
from his team's rebuilt 0-0 (epochs.PLAYER_OMITTED_ZERO_FROM_UTC), and the
refit of the `player_offsides_for` family it needs. Read-only on the DB.

    PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/measure_audit1023_p6_offsides.py \\
        replay --db-path data/refit_2026-10-23_allin/sofa_copy.db \\
        --rows-out rows.json.gz
    PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/measure_audit1023_p6_offsides.py \\
        report --rows-in rows.json.gz --split 2026-07-01 [--json-out f]
    PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/measure_audit1023_p6_offsides.py \\
        stage --rows-in rows.json.gz \\
        --out config/sofa_confidence_calibration.next.json \\
        --effective-from 2026-10-24T00:00:00Z

`replay`: the history replay of the player rows (calibrate_from_cache's
build_player_rows rules: every finished football match with a cached squad
list, his STARTS in the side's newest sample_n matches - the side he is
found in more often, match_player per squad - at least min_sample, an
all-zero sample refused, centre the sample mean, engine's predictive sd and
count p, the lines Superbet printed for the market) for player_offsides_for
only, read twice: the old reader (players.squad_statistics as it was) and the
new one (omitted_zero=True). Each row keeps both p (None where that reader
gives no row) and the outcome the NEW reader grades (a target match whose
team offsides the feed omitted is a real 0 - Superbet settles it; the old
reader could not grade it), and whether the old reader graded it.

`report`: out of sample by time. Curves (fit_confidence's EDGES, realised per
bucket, per direction) are fitted on rows before `--split` - the old
pipeline on the rows the old reader grades, the new on the new reader's -
and both are scored on every later row both price (graded by the new
reader): log loss and Brier of the bucket realised, new minus old, with a
match bootstrap. Also the installed curve on the old p, and the new curve's
realised minus confidence (its realised_lo95, what CONFIDENCE reads) on the
rows at >= 0.70.

`stage`: the family's curve keys (by_market player_offsides_for,
by_market_direction player_offsides_for|OVER/UNDER,
thin_by_market_direction) fitted on every new-reader row, written into a
copy of the installed calibration with `effective_from`
(confidence.calibration_path_for). Every other key byte for byte.
"""

from __future__ import annotations

import argparse
import collections
import functools
import gzip
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
for p in (ROOT / "src", ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from bet.sofa import players  # noqa: E402
from bet.sofa.confidence import Calibration  # noqa: E402
from bet.sofa.contracts import GapReason  # noqa: E402
from bet.sofa.engine import (  # noqa: E402
    outside_model_resolution,
    sheet_count_p_raw,
    sheet_predictive_sd,
    winning_boundary,
)
from bet.sofa.listing_index import entity_indexed_events  # noqa: E402
from bet.sofa.samples import _competition_id, finish_history  # noqa: E402
from bet.sofa.settle import settle  # noqa: E402
from scripts.sofa import calibrate_from_cache as cfc  # noqa: E402
from scripts.sofa.fit_confidence import (  # noqa: E402
    EDGES,
    MIN_MARKET_BUCKET,
    MIN_THIN_BUCKET,
    bucket_of,
    wilson_lo,
)

METRIC = "player_offsides_for"
DIRECTIONS: tuple[Literal["OVER"], Literal["UNDER"]] = ("OVER", "UNDER")
SAMPLE_N = 10
MIN_SAMPLE = 5
FLOOR = 0.70
BOOT = 2000
INSTALLED = ROOT / "config" / "sofa_confidence_calibration.json"


def _p(sample: Sequence[float], line: float,
       direction: Literal["OVER", "UNDER"]) -> float | None:
    """SHEET's player p (calibrate_from_cache.player_rows_for_event)."""
    n = len(sample)
    if n < 1 or all(v == 0.0 for v in sample):
        return None
    mean = statistics.mean(sample)
    var = statistics.variance(sample) if n > 1 else 0.0
    sd = sheet_predictive_sd(METRIC, "football", mean, var, n, mean)
    p = sheet_count_p_raw(METRIC, mean, sd, winning_boundary(line, direction),
                          direction)
    return None if outside_model_resolution(p) else float(p)


def _sided_sample(
    name: str, history: dict[bool, list[Any]], is_home: bool,
) -> list[float] | None:
    """His starts' values in the side's newest SAMPLE_N, when he is found
    more often on his own side and starts MIN_SAMPLE of them."""
    vals: dict[bool, list[float]] = {}
    for side, squads in history.items():
        got = []
        for sq in squads:
            if not sq:
                continue
            key = players.match_player(name, sq)
            if key is None or players.started(sq[key]) is False:
                continue
            v = players.extract_player_metric(METRIC, sq[key])
            if not isinstance(v, GapReason):
                got.append(v)
        vals[side] = got
    if len(vals[True]) == len(vals[False]):
        return None
    if (len(vals[True]) > len(vals[False])) != is_home:
        return None
    own = vals[is_home]
    return own if len(own) >= MIN_SAMPLE else None


def replay(db: str, runs_dir: Path) -> list[dict[str, Any]]:
    ladder = cfc.printed_player_ladder(runs_dir).get(METRIC) or []
    print(f"ladder {ladder}", file=sys.stderr)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    targets = cfc.player_targets(con)
    print(f"targets {len(targets)}", file=sys.stderr)
    cache: collections.OrderedDict[int, dict[str, Any]] = collections.OrderedDict()
    new_reader = functools.partial(players.squad_statistics, omitted_zero=True)

    def squads_of(event_id: int) -> dict[str, Any]:
        if event_id in cache:
            cache.move_to_end(event_id)
            return cache[event_id]
        found = con.execute(
            "SELECT statistics_json, lineups_json FROM sofa_event_stats "
            "WHERE sofascore_event_id = ?", (event_id,)).fetchone()
        stats = json.loads(found[0]) if found and found[0] else None
        lineups = json.loads(found[1]) if found and found[1] else None
        both = {
            "old": {h: players.squad_statistics(lineups, is_home=h,
                                                statistics=stats)
                    for h in (True, False)},
            "new": {h: new_reader(lineups, is_home=h, statistics=stats)
                    for h in (True, False)},
        }
        cache[event_id] = both
        if len(cache) > 40_000:
            cache.popitem(last=False)
        return both

    out: list[dict[str, Any]] = []
    for k, event in enumerate(targets):
        if k % 2000 == 0:
            print(f"{k}/{len(targets)} rows {len(out)}", file=sys.stderr, flush=True)
        kickoff = int(event["startTimestamp"])
        comp = _competition_id(event)
        hist: dict[str, dict[bool, list[Any]]] = {"old": {}, "new": {}}
        for is_home in (True, False):
            entity = int(((event.get("homeTeam" if is_home else "awayTeam"))
                          or {}).get("id") or 0)
            admitted = [
                p for p in entity_indexed_events(
                    con, entity, "last", kickoff, cfc.PLAYER_HISTORY_LISTED)
                if cfc.admitted_football_event(p, entity, kickoff)
                and not cfc.is_same_match(p, event)
            ]
            recent = finish_history(admitted, entity, "football", comp, kickoff,
                                    SAMPLE_N)
            for reader in ("old", "new"):
                hist[reader][is_home] = [
                    squads_of(int(past["id"]))[reader][
                        (past.get("homeTeam") or {}).get("id") == entity]
                    for past in recent
                ]
        target = squads_of(int(event["id"]))
        for is_home in (True, False):
            new_sq = target["new"].get(is_home)
            old_sq = target["old"].get(is_home) or {}
            other = set(target["new"].get(not is_home) or {})
            if not new_sq:
                continue
            for name, st in sorted(new_sq.items()):
                if st.get("minutesPlayed") is None or players.started(st) is False:
                    continue
                if name in other:
                    continue
                actual = players.extract_player_metric(METRIC, st)
                if isinstance(actual, GapReason):
                    continue
                old_actual = players.extract_player_metric(
                    METRIC, old_sq.get(name))
                s_old = _sided_sample(name, hist["old"], is_home)
                s_new = _sided_sample(name, hist["new"], is_home)
                if s_old is None and s_new is None:
                    continue
                for line in ladder:
                    for direction in DIRECTIONS:
                        outcome = settle(actual, line, direction)
                        if outcome not in ("WIN", "LOSS"):
                            continue
                        p_old = None if s_old is None else _p(s_old, line, direction)
                        p_new = None if s_new is None else _p(s_new, line, direction)
                        if p_old is None and p_new is None:
                            continue
                        out.append({
                            "event_id": int(event["id"]), "ts": kickoff,
                            "player": name, "line": line, "direction": direction,
                            "p_old": p_old, "p_new": p_new,
                            "n_old": None if s_old is None else len(s_old),
                            "n_new": None if s_new is None else len(s_new),
                            "won": outcome == "WIN",
                            "old_graded": not isinstance(old_actual, GapReason),
                        })
    con.close()
    return out


def fit_curve(rows: list[dict[str, Any]], p_key: str
              ) -> dict[str, dict[int, tuple[int, int]]]:
    """{direction: {bucket: (n, wins)}}."""
    cells: dict[str, dict[int, list[int]]] = collections.defaultdict(
        lambda: collections.defaultdict(lambda: [0, 0]))
    for r in rows:
        p = r[p_key]
        if p is None:
            continue
        c = cells[r["direction"]][bucket_of(p)]
        c[0] += 1
        c[1] += r["won"]
    return {d: {b: (v[0], v[1]) for b, v in c.items()} for d, c in cells.items()}


def read_curve(curve: dict[str, dict[int, tuple[int, int]]], direction: str,
               p: float, lo: bool = False) -> float | None:
    cell = curve.get(direction, {}).get(bucket_of(p))
    if cell is None or cell[0] < MIN_MARKET_BUCKET:
        return None
    n, k = cell
    return wilson_lo(k, n) if lo else k / n


def _ll(q: float, won: bool) -> float:
    q = min(max(q, 1e-4), 1 - 1e-4)
    return -math.log(q if won else 1 - q)


def _boot_mean(ids: list[int], per: np.ndarray,
               seed: int) -> tuple[float, float, float]:
    """per: (2, n_matches) [sum, count] -> mean with a match bootstrap."""
    w = np.random.default_rng(seed).multinomial(
        len(ids), np.full(len(ids), 1 / len(ids)), size=BOOT)
    d = per @ w.T
    draws = d[0] / d[1]
    return (float(per[0].sum() / per[1].sum()),
            float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975)))


def compare(rows: list[dict[str, Any]], q_old: str, q_new: str,
            seed: int = 7) -> dict[str, Any]:
    """new minus old log loss / Brier on the rows both score."""
    scored = [r for r in rows if r.get(q_old) is not None
              and r.get(q_new) is not None]
    if not scored:
        return {"rows": 0}
    ids = sorted({r["event_id"] for r in scored})
    col = {e: i for i, e in enumerate(ids)}
    ll = np.zeros((2, len(ids)))
    br = np.zeros((2, len(ids)))
    for r in scored:
        j = col[r["event_id"]]
        y = 1.0 if r["won"] else 0.0
        ll[0, j] += _ll(r[q_new], r["won"]) - _ll(r[q_old], r["won"])
        ll[1, j] += 1
        br[0, j] += (r[q_new] - y) ** 2 - (r[q_old] - y) ** 2
        br[1, j] += 1
    a = _boot_mean(ids, ll, seed)
    b = _boot_mean(ids, br, seed + 1)
    return {"rows": len(scored), "matches": len(ids),
            "logloss_new_minus_old": [round(x, 5) for x in a],
            "brier_new_minus_old": [round(x, 5) for x in b]}


def gap(rows: list[dict[str, Any]], q: str, seed: int = 9) -> dict[str, Any]:
    scope = [r for r in rows if r.get(q) is not None]
    if not scope:
        return {"rows": 0}
    ids = sorted({r["event_id"] for r in scope})
    col = {e: i for i, e in enumerate(ids)}
    per = np.zeros((2, len(ids)))
    for r in scope:
        j = col[r["event_id"]]
        per[0, j] += (1.0 if r["won"] else 0.0) - r[q]
        per[1, j] += 1
    g = _boot_mean(ids, per, seed)
    return {"rows": len(scope), "matches": len(ids),
            "confidence": round(sum(r[q] for r in scope) / len(scope), 4),
            "realised": round(sum(r["won"] for r in scope) / len(scope), 4),
            "realised_minus_confidence": [round(x, 4) for x in g]}


def report(rows: list[dict[str, Any]], split: str) -> dict[str, Any]:
    cut = int(datetime.fromisoformat(split).replace(tzinfo=UTC).timestamp())
    train = [r for r in rows if r["ts"] < cut]
    test = [r for r in rows if r["ts"] >= cut]
    old_curve = fit_curve([r for r in train if r["old_graded"]], "p_old")
    new_curve = fit_curve(train, "p_new")
    installed = Calibration.load(INSTALLED)
    for r in test:
        r["q_old"] = (None if r["p_old"] is None
                      else read_curve(old_curve, r["direction"], r["p_old"]))
        r["q_new"] = (None if r["p_new"] is None
                      else read_curve(new_curve, r["direction"], r["p_new"]))
        r["c_new"] = (None if r["p_new"] is None
                      else read_curve(new_curve, r["direction"], r["p_new"], lo=True))
        hit = (None if r["p_old"] is None else installed.realised(
            METRIC, r["p_old"], "football", r["direction"], None))
        r["c_installed"] = None if hit is None else float(hit[0])
    out: dict[str, Any] = {
        "rows": len(rows), "train_rows": len(train), "test_rows": len(test),
        "test_matches": len({r["event_id"] for r in test}),
        "test_rows_old_reader_could_not_grade": sum(
            1 for r in test if not r["old_graded"]),
        "zero_rows_share": {
            "old_graded": round(sum(1 for r in rows if r["old_graded"])
                                / max(1, len(rows)), 4)},
    }
    for direction in ("OVER", "UNDER", "ALL"):
        scope = [r for r in test if direction in ("ALL", r["direction"])]
        out[direction] = {
            "new_minus_old_oos": compare(scope, "q_old", "q_new"),
            "new_minus_old_oos_rows_old_graded": compare(
                [r for r in scope if r["old_graded"]], "q_old", "q_new"),
            "new_curve_printable": gap(
                [r for r in scope if (r["c_new"] or 0) >= FLOOR], "c_new"),
            "installed_curve_printable_old_p": gap(
                [r for r in scope if (r["c_installed"] or 0) >= FLOOR],
                "c_installed"),
            "installed_curve_printable_old_p_old_graded": gap(
                [r for r in scope if (r["c_installed"] or 0) >= FLOOR
                 and r["old_graded"]], "c_installed"),
        }
    return out


def _section(cells: dict[int, list[int]], minimum: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for b in sorted(cells):
        n, k = cells[b]
        if n < minimum:
            continue
        lo_e, hi_e = EDGES[b], min(EDGES[b + 1], 1.0)
        out[f"{lo_e:.3f}-{hi_e:.3f}"] = {
            "n": n, "realised": round(k / n, 4),
            "realised_lo95": round(wilson_lo(k, n), 4)}
    return out


def stage(rows: list[dict[str, Any]], out_path: Path, effective_from: str,
          source: str) -> dict[str, Any]:
    cal = json.loads(INSTALLED.read_text(encoding="utf-8"))
    per_dir: dict[str, dict[int, list[int]]] = collections.defaultdict(
        lambda: collections.defaultdict(lambda: [0, 0]))
    pooled: dict[int, list[int]] = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        if r["p_new"] is None:
            continue
        b = bucket_of(r["p_new"])
        for cell in (per_dir[r["direction"]][b], pooled[b]):
            cell[0] += 1
            cell[1] += r["won"]
    before = {
        "by_market": cal["by_market"].get(METRIC),
        "by_market_direction": {d: cal["by_market_direction"].get(f"{METRIC}|{d}")
                                for d in ("OVER", "UNDER")},
    }
    cal["by_market"][METRIC] = _section(pooled, MIN_MARKET_BUCKET)
    thin = cal.setdefault("thin_by_market_direction", {})
    for d in ("OVER", "UNDER"):
        key = f"{METRIC}|{d}"
        cal["by_market_direction"][key] = _section(per_dir[d], MIN_MARKET_BUCKET)
        thin_cells = {b: v for b, v in per_dir[d].items()
                      if MIN_THIN_BUCKET <= v[0] < MIN_MARKET_BUCKET}
        if thin_cells:
            thin[key] = _section(thin_cells, MIN_THIN_BUCKET)
        else:
            thin.pop(key, None)
    cal["effective_from"] = effective_from
    cal["player_offsides_for_fitted_from"] = {
        "rows": sum(v[0] for v in pooled.values()),
        "source": source,
        "reader": "players.squad_statistics(omitted_zero=True) - "
                  "epochs.PLAYER_OMITTED_ZERO_FROM_UTC (coverage audit 2026-10-23 P6)",
        "rules": "starts only, newest 10, min_sample 5, no coverage window "
                 "(the installed 10-17 fit's player rules)",
        "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    out_path.write_text(json.dumps(cal, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    return {"before": before,
            "after": {"by_market": cal["by_market"][METRIC],
                      "by_market_direction": {
                          d: cal["by_market_direction"][f"{METRIC}|{d}"]
                          for d in ("OVER", "UNDER")}}}


def _load(path: str) -> list[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return list(json.load(fh))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("section", choices=("replay", "report", "stage"))
    ap.add_argument("--db-path")
    ap.add_argument("--runs-dir", default=str(ROOT / "runs" / "sofa"))
    ap.add_argument("--rows-out")
    ap.add_argument("--rows-in")
    ap.add_argument("--split", default="2026-07-01")
    ap.add_argument("--out")
    ap.add_argument("--effective-from", default="2026-10-24T00:00:00Z")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    if args.section == "replay":
        rows = replay(args.db_path, Path(args.runs_dir))
        with gzip.open(args.rows_out, "wt", encoding="utf-8") as fh:
            json.dump(rows, fh)
        print(json.dumps({"rows": len(rows)}))
        return 0
    rows = _load(args.rows_in)
    if args.section == "report":
        res = report(rows, args.split)
    else:
        if not args.out:
            print("--out needed", file=sys.stderr)
            return 2
        if Path(args.out).resolve() == INSTALLED.resolve():
            print("REFUSED: stage writes a staged copy, never the installed "
                  "calibration", file=sys.stderr)
            return 2
        res = stage(rows, Path(args.out), args.effective_from, args.rows_in)
    text = json.dumps(res, indent=1)
    if args.json_out:
        Path(args.json_out).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
