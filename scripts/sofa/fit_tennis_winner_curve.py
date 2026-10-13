#!/usr/bin/env python3
"""D2 (audit 2026-10-13): the tennis match-winner history curve, measured and
staged - never installed.

Read-only on the database. Writes only into ``--out-dir`` (a scratch
directory, e.g. data/refit_2026-10-13/d2/): ``rows_<variant>.csv``,
``results.json``, ``report.md`` and the staged curve
``tennis_winner_curve.json``. Nothing under config/ is touched unless
``--merge-into`` / ``--merged-out`` are given, and even then the merged copy
goes to the path named (the coordinator installs it).

Method (registered in docs/sofa/evidence/tennis_match_winner_2026-10-13.md
before the run). Walk forward over the cached singles history
(``tennis_rating.load_history``): every match of the window is forecast from
the as-of model of its UTC day (``AsOfRating.model_at``; the scoped tier x
gender table and the tier start, as SHEET builds it), the market's p is
``MatchForecast.p_home`` - exactly what SHEET prices ``match_won_for`` with
(bet.sofa.tennis_winner) - and no price enters anywhere. Population: SHEET's
- completed (no retirement / walkover: Superbet refunds them), best of
three, both players rated (``forecast`` is not None), team cups and
exhibitions out (CONFIDENCE never prints them).

  skill        log-loss of p_home minus the as-of class base rate
               (tier x gender, Laplace), match bootstrap
  calibration  a curve fitted like fit_confidence (EDGES, MIN_MARKET_BUCKET,
               Wilson lower bound) on the train rows (both sides of each
               match), read on the holdout's favoured side: gap = printed
               confidence - realised, per bucket >= 0.70 and pooled
  curve        the same fit on every row of the window (variant ``live``):
               by_market.match_won_for + by_class.tennis_women

    SOFA_DB_PATH=<copy> PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/fit_tennis_winner_curve.py --db <copy> \\
        --out-dir data/refit_2026-10-13/d2 [--from 2026-04-01] \\
        [--holdout-from 2026-08-15] [--to 2026-10-13] [--variants live,clean] \\
        [--rows-from <dir>] [--merge-into config/sofa_confidence_calibration.json \\
         --merged-out <path>]

Exit 0 OK, 2 on a failure.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import tennis_rating as tr  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.calibration_audit import MAX_GAP, MIN_SETTLED  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    CLASS_TENNIS_TEAM_CUP,
    CLASS_TENNIS_WOMEN,
    match_class,
)
from bet.sofa.tennis_winner import MATCH_WON_FOR  # noqa: E402
from scripts.sofa.fit_confidence import (  # noqa: E402
    EDGES,
    MIN_MARKET_BUCKET,
    bucket_of,
    wilson_lo,
)
from scripts.sofa.measure_tennis_outcome_model import (  # noqa: E402
    BaseRates,
    boot_ci,
    class_label,
    clean_config,
    ll_binary,
    load,
    score_code,
)

PRINT_FLOOR = 0.70
SEED = 20261012
ROW_FIELDS = ("event_id", "ts", "cls", "klass", "scope", "p", "y", "b")


# ---------------------------------------------------------------- the walk


def walk(
    history: Sequence[tr.TennisResult],
    meta: Mapping[int, tuple[str, str]],
    coefficients: Mapping[str, Sequence[float]],
    names: Sequence[str],
    tier_start: Mapping[str, float] | None,
    start: int,
    end: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """One row per match of [start, end): p_home as SHEET reads it, the
    outcome, the as-of class base rate."""
    rating = tr.AsOfRating(history, coefficients, names, True, tier_start)
    base: dict[str, BaseRates] = defaultdict(BaseRates)
    skips: dict[str, int] = defaultdict(int)
    rows: list[dict[str, Any]] = []
    j = 0
    for r in history:
        if r.ts < start:
            continue
        if r.ts >= end:
            break
        day = r.ts - r.ts % 86400
        while j < len(history) and history[j].ts < day:
            h = history[j]
            j += 1
            hcat = meta.get(h.event_id, ("", ""))[0]
            if (h.completed and len(h.sets) <= 3
                    and max(sum(a > b for a, b in h.sets),
                            sum(b > a for a, b in h.sets)) == 2
                    and match_class("tennis", hcat) != CLASS_TENNIS_TEAM_CUP):
                base[class_label(h.tier, h.female)].add(
                    h.home_won, h.sets[0][0] > h.sets[0][1], score_code(h.sets))
        cat = meta.get(r.event_id, ("", ""))[0]
        klass = match_class("tennis", cat)
        if klass == CLASS_TENNIS_TEAM_CUP:
            skips["team_cup"] += 1
            continue
        if not r.completed:
            skips["not_completed"] += 1
            continue
        won = max(sum(a > b for a, b in r.sets), sum(b > a for a, b in r.sets))
        if won != 2 or len(r.sets) > 3:
            skips["best_of_five"] += 1
            continue
        fc = rating.model_at(day).forecast(
            r.home_id, r.away_id, cat, r.surface, datetime.fromtimestamp(r.ts, UTC))
        if fc is None:
            skips["unrated"] += 1
            continue
        cls = class_label(r.tier, r.female)
        rows.append({
            "event_id": r.event_id, "ts": r.ts, "cls": cls,
            "klass": klass or "", "scope": fc.table_scope,
            "p": fc.p_home, "y": int(r.home_won),
            "b": base[cls].rates()["match_winner"],
        })
    return rows, dict(skips)


# ---------------------------------------------------------------- the curve


def both_sides(rows: Sequence[Mapping[str, Any]]) -> list[tuple[float, int]]:
    """Each match as its two selections: (p, won) for the home player and for
    the away one - OVER and UNDER of one rung, the curve is symmetric."""
    out: list[tuple[float, int]] = []
    for r in rows:
        p, y = float(r["p"]), int(r["y"])
        out.append((p, y))
        out.append((1.0 - p, 1 - y))
    return out


def fit_curve(rows: Sequence[Mapping[str, Any]],
              floor: int = MIN_MARKET_BUCKET) -> dict[str, dict[str, Any]]:
    """fit_confidence's curve: bucket -> n, realised, realised_lo95, for the
    buckets with at least ``floor`` selections."""
    hits: dict[int, list[int]] = defaultdict(list)
    for p, y in both_sides(rows):
        hits[bucket_of(min(max(p, 0.0), 1.0))].append(y)
    out: dict[str, dict[str, Any]] = {}
    for b, ys in sorted(hits.items()):
        if len(ys) < floor:
            continue
        k, n = sum(ys), len(ys)
        out[f"{EDGES[b]:.3f}-{EDGES[b + 1]:.3f}"] = {
            "n": n, "realised": round(k / n, 4),
            "realised_lo95": round(wilson_lo(k, n), 4),
        }
    return out


def curve_at(curve: Mapping[str, Mapping[str, Any]], p: float) -> float | None:
    for key, entry in curve.items():
        lo, hi = (float(x) for x in key.split("-"))
        if lo <= p < hi:
            return float(entry["realised_lo95"])
    return None


def _gap_ci(conf: list[float], ys: list[int], boot: int) -> tuple[float, float]:
    """95% interval of mean(conf) - mean(y), one selection per match."""
    d = np.array(conf, dtype=float) - np.array(ys, dtype=float)
    lo, hi = boot_ci(d, boot, SEED)
    return lo, hi


def holdout_calibration(
    curve: Mapping[str, Mapping[str, Any]],
    holdout: Sequence[Mapping[str, Any]],
    boot: int,
) -> dict[str, Any]:
    """The favoured side of each holdout match at p >= PRINT_FLOOR, read off
    the train curve: per bucket and pooled n, mean p, printed confidence,
    realised, gap (confidence - realised), its match-bootstrap interval and
    the registered verdict (|gap| <= MAX_GAP at n >= MIN_SETTLED)."""
    by_bucket: dict[str, tuple[list[float], list[float], list[int]]] = (
        defaultdict(lambda: ([], [], [])))
    no_curve = 0
    for r in holdout:
        p, y = float(r["p"]), int(r["y"])
        if p < 0.5:
            p, y = 1.0 - p, 1 - y
        if p < PRINT_FLOOR:
            continue
        conf = curve_at(curve, p)
        if conf is None:
            no_curve += 1
            continue
        b = bucket_of(p)
        key = f"{EDGES[b]:.3f}-{EDGES[b + 1]:.3f}"
        by_bucket[key][0].append(p)
        by_bucket[key][1].append(conf)
        by_bucket[key][2].append(y)

    def cell(ps: list[float], cs: list[float], ys: list[int]) -> dict[str, Any]:
        n = len(ys)
        gap = float(np.mean(cs) - np.mean(ys))
        ci = _gap_ci(cs, ys, boot)
        if n < MIN_SETTLED:
            verdict = "INSUFFICIENT"
        else:
            verdict = "PASS" if abs(gap) <= MAX_GAP + 1e-12 else "FAIL"
        return {
            "n": n, "mean_p": float(np.mean(ps)), "confidence": float(np.mean(cs)),
            "realised": float(np.mean(ys)), "gap_pp": 100.0 * gap,
            "ci_pp": [100.0 * ci[0], 100.0 * ci[1]],
            "interval_holds_0": ci[0] <= 0.0 <= ci[1],
            "verdict": verdict,
        }

    buckets = {k: cell(*v) for k, v in sorted(by_bucket.items())}
    allp = [p for v in by_bucket.values() for p in v[0]]
    allc = [c for v in by_bucket.values() for c in v[1]]
    ally = [y for v in by_bucket.values() for y in v[2]]
    pooled = cell(allp, allc, ally) if ally else None
    decisive = [b["verdict"] for b in buckets.values()
                if b["verdict"] != "INSUFFICIENT"]
    if pooled is not None and pooled["verdict"] != "INSUFFICIENT":
        decisive.append(pooled["verdict"])
    passed = bool(decisive) and all(v == "PASS" for v in decisive)
    return {"buckets": buckets, "pooled_ge_070": pooled,
            "no_curve_bucket": no_curve, "pass": passed}


def skill(rows: Sequence[Mapping[str, Any]], boot: int) -> dict[str, Any]:
    p = np.array([float(r["p"]) for r in rows])
    y = np.array([float(r["y"]) for r in rows])
    b = np.array([float(r["b"]) for r in rows])
    llm, llb = ll_binary(p, y), ll_binary(b, y)
    d = llm - llb
    ci = boot_ci(d, boot, SEED)
    brier_d = (p - y) ** 2 - (b - y) ** 2
    return {
        "n": len(rows), "ll_model": float(llm.mean()), "ll_base": float(llb.mean()),
        "d_vs_base": float(d.mean()), "ci_vs_base": [ci[0], ci[1]],
        "brier_d_vs_base": float(brier_d.mean()),
        "brier_ci": list(boot_ci(brier_d, boot, SEED)),
        "pass": ci[1] < 0.0,
    }


def staged_doc(rows: Sequence[Mapping[str, Any]], stamp: Mapping[str, Any]
               ) -> dict[str, Any]:
    women = [r for r in rows if r["klass"] == CLASS_TENNIS_WOMEN]
    return {
        "_doc": (
            "Staged tennis match-winner curve (audit 2026-10-13 D2, "
            "epochs.TENNIS_MATCH_WINNER_FROM_UTC). Install by merging "
            "by_market.match_won_for into the football / tennis calibration's "
            "by_market and by_class.tennis_women.by_market.match_won_for into "
            "its by_class.tennis_women.by_market (scripts/sofa/"
            "fit_tennis_winner_curve.py --rows-from <this dir> --merge-into "
            "<calibration> --merged-out <path>). No direction curves: OVER is "
            "Superbet's first-listed player, the curve is symmetric. A full "
            "fit_confidence.py refit rebuilds the file from the DB and drops "
            "this key - re-merge after it."
        ),
        "market": MATCH_WON_FOR,
        "fitted_from": dict(stamp),
        "by_market": {MATCH_WON_FOR: fit_curve(rows)},
        "by_class": {CLASS_TENNIS_WOMEN: {"by_market": {
            MATCH_WON_FOR: fit_curve(women)}}},
    }


def merge(calibration: dict[str, Any], staged: Mapping[str, Any]) -> dict[str, Any]:
    """The calibration with the staged match_won_for curves merged in."""
    out: dict[str, Any] = json.loads(json.dumps(calibration))
    out.setdefault("by_market", {})[MATCH_WON_FOR] = (
        staged["by_market"][MATCH_WON_FOR])
    women = staged["by_class"][CLASS_TENNIS_WOMEN]["by_market"][MATCH_WON_FOR]
    if women:
        cls = out.setdefault("by_class", {}).setdefault(CLASS_TENNIS_WOMEN, {})
        cls.setdefault("by_market", {})[MATCH_WON_FOR] = women
    out["match_won_for_fitted_from"] = staged["fitted_from"]
    return out


# ---------------------------------------------------------------- report


def render(results: Mapping[str, Any]) -> str:
    lines = ["# D2 - tennis match winner: skill and holdout calibration", "",
             f"Window {results['from']} .. {results['to']} (exclusive), holdout "
             f"from {results['holdout_from']}. Log-loss in 1e-4 nats, negative = "
             "model better; intervals: match bootstrap 95%."]
    for v, res in results["variants"].items():
        s = res["skill"]
        lines += ["", f"## `{v}`", "", f"Skips: {res['skips']}", "",
                  f"- skill: n {s['n']}, LL model {s['ll_model']:.4f}, base "
                  f"{s['ll_base']:.4f}, d {1e4 * s['d_vs_base']:+.0f} "
                  f"[{1e4 * s['ci_vs_base'][0]:+.0f}, {1e4 * s['ci_vs_base'][1]:+.0f}]"
                  f" -> {'PASS' if s['pass'] else 'FAIL'}",
                  f"- Brier d {1e4 * s['brier_d_vs_base']:+.0f} "
                  f"[{1e4 * s['brier_ci'][0]:+.0f}, {1e4 * s['brier_ci'][1]:+.0f}]",
                  "", "| bucket | n | mean p | confidence | realised | gap pp [95%] "
                  "| verdict |", "|---|---|---|---|---|---|---|"]
        cal = res["calibration"]
        cells = list(cal["buckets"].items())
        if cal["pooled_ge_070"] is not None:
            cells.append((">= 0.70", cal["pooled_ge_070"]))
        for key, c in cells:
            lines.append(
                f"| {key} | {c['n']} | {c['mean_p']:.3f} | {c['confidence']:.3f} | "
                f"{c['realised']:.3f} | {c['gap_pp']:+.1f} [{c['ci_pp'][0]:+.1f}, "
                f"{c['ci_pp'][1]:+.1f}] | {c['verdict']} |")
        lines.append(f"\nHoldout rows >= 0.70 with no train bucket: "
                     f"{cal['no_curve_bucket']}; calibration "
                     f"{'PASS' if cal['pass'] else 'FAIL'}")
    return "\n".join(lines) + "\n"


def _ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def _read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="") as fh:
        return [{"event_id": int(r["event_id"]), "ts": int(r["ts"]), "cls": r["cls"],
                 "klass": r["klass"], "scope": r["scope"], "p": float(r["p"]),
                 "y": int(r["y"]), "b": float(r["b"])}
                for r in csv.DictReader(fh)]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=None,
                    help="the DB copy (default: SOFA_DB_PATH / the config's)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--from", dest="start", default="2026-04-01")
    ap.add_argument("--holdout-from", default="2026-08-15")
    ap.add_argument("--to", default="2026-10-13")
    ap.add_argument("--variants", default="live,clean")
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--rows-from", default=None,
                    help="re-read rows_<variant>.csv from this dir, no walk")
    ap.add_argument("--merge-into", default=None)
    ap.add_argument("--merged-out", default=None)
    args = ap.parse_args(argv)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    start, hold, end = _ts(args.start), _ts(args.holdout_from), _ts(args.to)
    db = args.db
    if db is None:
        from bet.sofa.config import SofaConfig
        db = str(SofaConfig.from_env().db_path)
    history: list[tr.TennisResult] = []
    meta: dict[int, tuple[str, str]] = {}
    if args.rows_from is None:
        history, meta = load(db)
        print(f"history {len(history)} matches ({time.time() - t0:.0f}s)", flush=True)
    results: dict[str, Any] = {"db": db, "from": args.start, "to": args.to,
                               "holdout_from": args.holdout_from, "boot": args.boot,
                               "variants": {}}
    live_rows: list[dict[str, Any]] | None = None
    live_meta: dict[str, Any] = {}
    for variant in args.variants.split(","):
        if args.rows_from is not None:
            rows = _read_rows(Path(args.rows_from) / f"rows_{variant}.csv")
            skips: dict[str, int] = {}
            features: list[str] = []
        else:
            if variant == "live":
                loaded = tr.load_coefficients()
                if loaded is None:
                    print("no config/tennis_rating.json", file=sys.stderr)
                    return 2
                coefficients, cfg = loaded
                names: Sequence[str] = cfg["features"]
                tier_start = cfg.get("tier_start")
            elif variant == "clean":
                coefficients, tier_start = clean_config(history, start)
                names = tr.V5_FEATURES
            else:
                print(f"unknown variant {variant}", file=sys.stderr)
                return 2
            rows, skips = walk(history, meta, coefficients, names, tier_start,
                               start, end)
            features = list(names)
            with (out / f"rows_{variant}.csv").open("w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(ROW_FIELDS))
                w.writeheader()
                w.writerows(rows)
        print(f"{variant}: {len(rows)} rows, skips {skips} "
              f"({time.time() - t0:.0f}s)", flush=True)
        train = [r for r in rows if r["ts"] < hold]
        holdout = [r for r in rows if r["ts"] >= hold]
        curve = fit_curve(train)
        results["variants"][variant] = {
            "skips": skips, "features": features, "rows": len(rows),
            "train_rows": len(train), "holdout_rows": len(holdout),
            "skill": skill(rows, args.boot),
            "skill_holdout": skill(holdout, args.boot),
            "train_curve": curve,
            "calibration": holdout_calibration(curve, holdout, args.boot),
        }
        if variant == "live":
            live_rows = rows
            live_meta = {"skips": skips, "features": features}
    (out / "results.json").write_text(json.dumps(results, indent=1))
    (out / "report.md").write_text(render(results))
    if live_rows is not None:
        stamp = {"db_path": db, "window": [args.start, args.to], "rows": len(live_rows),
                 "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                 "variant": "live (config/tennis_rating.json)", **live_meta}
        staged = staged_doc(live_rows, stamp)
        write_atomic(out / "tennis_winner_curve.json",
                     json.dumps(staged, indent=1) + "\n")
        if args.merge_into and args.merged_out:
            cal = json.loads(Path(args.merge_into).read_text(encoding="utf-8"))
            write_atomic(Path(args.merged_out),
                         json.dumps(merge(cal, staged), indent=1) + "\n")
            print(f"merged copy: {args.merged_out}", flush=True)
    print(f"wrote {out} ({time.time() - t0:.0f}s)", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc!r}", file=sys.stderr)
        raise SystemExit(2) from exc
