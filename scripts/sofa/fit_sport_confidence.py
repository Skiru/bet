#!/usr/bin/env python3
"""Fit the statistics-only confidence curves of the hockey, basketball,
volleyball and CS2 coupon legs (plan 2026-10-05, F4-F6).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_sport_confidence.py \\
        --sport all --before 2026-10-05 [--dry-run] [--rows-out <dir>]

Between days only: a coupon built on one fit and rebuilt on another is two
rules. No price is read anywhere - not by the model, not by the curve.

Per sport:

* history families (hockey / basketball: winner, total, team total, handicap,
  1X2; volleyball: winner, sets total, set handicap, points total, points
  handicap; CS2: map winner, match winner, a team's rounds on a map): a
  walk-forward over the cached results history (bet.sofa.sport_confidence.
  walk_forward_rows / cs2_walk_forward_rows), every game forecast from a
  model built strictly before it. The curve is fitted on
  [before - holdout - fit-days, before - holdout); the last --holdout-days
  are held out;
* period / first-half families: only from settled Superbet SHADOW lines
  (runs/sofa/shadow/<sport>/<d>/settled.json, the model's probability from a
  model built before each day) - the first half of the settled days fits,
  the second half is held out;
* out of sample: the held-out history AND the settled Superbet lines
  (SHADOW: the model's p; CS2: settle_cs2's `model_p`). A key is admitted
  when it has an out-of-sample bucket of >= 200 rows and no such bucket
  prints a confidence more than 3 pp above what it realised
  (sport_confidence.admission); else NOT_CALIBRATED.

Writes config/sofa_sport_confidence_calibration.json (one section per sport
fitted; the other sports' sections are kept), and with --rows-out every
row and the summary, for the report.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.config import SofaConfig, config_path  # noqa: E402
from bet.sofa.score_model import N_SIMS, load_events  # noqa: E402
from bet.sofa.shadow import SPORTS  # noqa: E402

DOC = (
    "Statistics-only confidence of the hockey / basketball / volleyball / CS2 "
    "coupon legs, fitted by scripts/sofa/fit_sport_confidence.py. A leg's "
    "confidence is the realised_lo95 of the bucket its model probability "
    "(score_model / cs2_engine) falls in, for an ADMITTED key "
    "(family|OVER/UNDER/DRAW/TEAM) only; a key in not_calibrated, a bucket "
    "absent from the curve (n < min_bucket) or a sport absent from this file "
    "is NOT_CALIBRATED. No price is an input."
)


def settled_dates(runs_dir: str, sport: str, before: str) -> list[str]:
    base = (Path(runs_dir) / "cs2" if sport == "cs2"
            else Path(runs_dir) / "shadow" / sport)
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir()
                  if p.is_dir() and len(p.name) == 10 and p.name < before
                  and (p / "settled.json").exists())


def _events(db_path: str, sport: str, cache_dir: str | None) -> dict[int, Any]:
    if cache_dir:
        path = Path(cache_dir) / f"{sport}.pkl"
        if path.exists():
            data: dict[int, Any] = pickle.loads(path.read_bytes())
            return data
    return load_events(db_path, SPORTS[sport])  # type: ignore[index]


def fit_sport(sport: str, before: str, args: argparse.Namespace,
              db_path: str, runs_dir: str) -> tuple[dict[str, Any],
                                                     dict[str, list[scf.Row]]]:
    before_ts = scf.day_ts(before)
    hold_ts = before_ts - args.holdout_days * 86400
    fit_start = hold_ts - args.fit_days * 86400
    dates = settled_dates(runs_dir, sport, before)
    rows: dict[str, list[scf.Row]] = {}
    if sport == "cs2":
        maps, series = scf.load_cs2(db_path, before_ts)
        rows["history_fit"] = scf.cs2_walk_forward_rows(
            maps, series, fit_start, hold_ts, "history_fit")
        rows["history_holdout"] = scf.cs2_walk_forward_rows(
            maps, series, hold_ts, before_ts, "history_holdout")
        rows["superbet_settled"] = scf.cs2_settled_rows(runs_dir, dates)
        fit_dates: list[str] = []
        oos_dates = dates
        history_n = len({m.event_id for m in maps})
    else:
        shadow_sport = SPORTS[sport]  # type: ignore[index]
        events = _events(db_path, sport, args.events_cache)
        history = scf.parse_history(events, shadow_sport)
        history = [g for g in history if g.rating.ts < before_ts]
        history_n = len(history)
        rows["history_fit"] = scf.walk_forward_rows(
            history, shadow_sport, fit_start, hold_ts, args.sims, args.max_games,
            "history_fit")
        rows["history_holdout"] = scf.walk_forward_rows(
            history, shadow_sport, hold_ts, before_ts, args.sims,
            args.max_holdout_games, "history_holdout")
        settled = scf.settled_shadow_rows(runs_dir, shadow_sport, dates, events,
                                          history, args.sims)
        only = scf.SETTLED_ONLY_FAMILIES[sport]
        half = len(dates) // 2
        fit_dates, oos_dates = dates[:half], dates[half:]
        rows["settled_fit"] = [r for r in settled
                               if r["family"] in only and r["date"] in fit_dates]
        rows["superbet_settled"] = [
            r for r in settled
            if r["family"] not in only or r["date"] in oos_dates]
    fit_rows = rows["history_fit"] + rows.get("settled_fit", [])
    curves = scf.fit_curves(fit_rows)
    source = {key: ("superbet_settled" if key.split("|")[0]
                    in scf.SETTLED_ONLY_FAMILIES.get(sport, frozenset())
                    else "history") for key in curves}
    checks = {
        "history_holdout": scf.evaluate(curves, rows["history_holdout"]),
        "superbet_settled": scf.evaluate(curves, rows["superbet_settled"]),
    }
    admitted, refused = scf.admission(curves, checks)
    seen = {r["key"] for rs in rows.values() for r in rs}
    for key in sorted(seen - set(curves)):
        refused[key] = f"NO_FIT_BUCKET_WITH_N>={scf.MIN_BUCKET}"
    section = {
        "fitted_from": {
            "before": before,
            "holdout_days": args.holdout_days,
            "fit_window_utc": [_iso(fit_start), _iso(hold_ts)],
            "holdout_window_utc": [_iso(hold_ts), _iso(before_ts)],
            "history_games_before": history_n,
            "settled_dates_fit": fit_dates,
            "settled_dates_oos": oos_dates,
            "rows": {k: len(v) for k, v in rows.items()},
            "games": {k: len({r["game"] for r in v}) for k, v in rows.items()},
            "sims": None if sport == "cs2" else args.sims,
            "max_games": None if sport == "cs2" else args.max_games,
            "forecast_source": "cs2_engine" if sport == "cs2" else "score_model",
        },
        "curves": curves,
        "curve_source": source,
        "admitted": admitted,
        "not_calibrated": dict(sorted(refused.items())),
        "oos": checks,
    }
    return section, rows


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat().replace("+00:00", "Z")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sport", required=True,
                    choices=[*scf.SPORT_KEYS, "all"])
    ap.add_argument("--before", required=True,
                    help="fit on history strictly before this date (UTC)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the summary, write no config")
    ap.add_argument("--holdout-days", type=int, default=30)
    ap.add_argument("--fit-days", type=int, default=365)
    ap.add_argument("--sims", type=int, default=1000,
                    help=f"simulated games per forecast (pipeline: {N_SIMS})")
    ap.add_argument("--max-games", type=int, default=4000,
                    help="games scored in the fit window (evenly thinned)")
    ap.add_argument("--max-holdout-games", type=int, default=3000)
    ap.add_argument("--out", default=None,
                    help="default: config/" + scf.CALIBRATION_FILE)
    ap.add_argument("--rows-out", default=None,
                    help="directory for every row (JSONL) and the summary")
    ap.add_argument("--events-cache", default=None,
                    help="directory of <sport>.pkl score_model.load_events dumps")
    args = ap.parse_args()
    config = SofaConfig.from_env()
    sports = list(scf.SPORT_KEYS) if args.sport == "all" else [args.sport]
    out_path = Path(args.out) if args.out else config_path(scf.CALIBRATION_FILE)
    doc: dict[str, Any] = (json.loads(out_path.read_text(encoding="utf-8"))
                           if out_path.exists() else {})
    doc.setdefault("sports", {})
    summary: dict[str, Any] = {}
    for sport in sports:
        section, rows = fit_sport(sport, args.before, args, config.db_path,
                                  config.runs_dir)
        doc["sports"][sport] = section
        summary[sport] = {"admitted": section["admitted"],
                          "not_calibrated": section["not_calibrated"],
                          "rows": section["fitted_from"]["rows"]}
        if args.rows_out:
            out_dir = Path(args.rows_out)
            out_dir.mkdir(parents=True, exist_ok=True)
            for name, rs in rows.items():
                (out_dir / f"{sport}_{name}.jsonl").write_text(
                    "".join(json.dumps(r) + "\n" for r in rs), encoding="utf-8")
            (out_dir / f"{sport}_section.json").write_text(
                json.dumps(section, indent=1) + "\n", encoding="utf-8")
    doc.update({
        "_doc": DOC,
        "edges": scf.EDGES,
        "min_bucket": scf.MIN_BUCKET,
        "max_overstatement": scf.MAX_OVERSTATEMENT,
        "unfitted_constants": list(scf.UNFITTED_CONSTANTS),
        "fitted_from": {
            "before": args.before,
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "db_path": config.db_path,
            "sports": sorted(doc["sports"]),
            "never_mid_day": True,
        },
    })
    stamp_day = (datetime.strptime(args.before, "%Y-%m-%d")
                 - timedelta(days=1)).strftime("%Y-%m-%d")
    doc["fitted_from"]["max_history_date"] = stamp_day
    if not args.dry_run:
        write_atomic(out_path, json.dumps(doc, indent=1, sort_keys=False) + "\n")
    print(json.dumps({"stage": "FIT_SPORT_CONFIDENCE", "verdict": "OK",
                      "dry_run": args.dry_run, "output_path": str(out_path),
                      "sports": summary}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
