#!/usr/bin/env python3
"""Fit the shot-detail estimator (bet.sofa.shot_detail) and its history curve,
on a COPY of the tables it reads - never installed by this script.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_shot_detail.py \\
        --before <d> [--out-dir data/refit_shot_detail_<d>] \\
        [--holdout-from 2026-09-01 [--holdout-to 2026-10-14]] \\
        [--estimator config/sofa_shot_detail.json] [--copy-from <db>]

1. Copy: the shotmap rows of sofa_event_extra, the lineups of those events and
   their kickoff from sofa_listing_event go into <out-dir>/shot_detail.db
   (CLAUDE.md "Changing the pipeline" 4: fits run on a copy; only these three
   tables are needed, so the copy is small). An existing copy is reused;
   `--copy-from` copies another (read-only) copy instead of the live DB.
2. Estimator, on starts kicked off before the cut: each metric's position
   means (and the all-positions mean) and K, the pseudo-starts that minimise
   the walk-forward log-loss summed over lines 0.5 / 1.5 / 2.5
   (measure_shot_detail.measure: a start is forecast only from earlier ones).
3. Forecasts: every start with >= MIN_STARTS earlier starts of the player is
   priced by `shot_detail.forecast` - SHEET's own function - with the fitted
   estimator (fixed position pools, K) and the player's last WINDOW earlier
   starts, at lines 0.5 / 1.5 / 2.5.
4. Curve: those forecasts bucketed per "<metric>|OVER" (new_market_gate:
   fit_confidence.EDGES, MIN_MARKET_BUCKET, realised and Wilson lo95).

Without --holdout-from: the estimator (or --estimator's file) and the curve
on every start before --before (the 2026-10-14 staged fit).

With --holdout-from (plan PLAN_KRZYWE_NOWE_RYNKI_2026-10-14 step 4): the
estimator AND the curve are fitted on starts before --holdout-from only; the
starts of [--holdout-from, --holdout-to) are priced by that training estimator
(their players' earlier starts, training ones included, as history) and read
through the training curve - new_market_gate.gate decides PASS / FAIL per key.
The final curve is then refitted on every start before --before with the
estimator SHEET prices with (--estimator, else one refitted on the same
starts), and only PASSING keys are written to curves.json `by_market_direction`;
every key's verdict is in `gate` and gate_report.md.

Writes <out-dir>/sofa_shot_detail.json (an estimator fitted here), curves.json
(by_market_direction entries to merge into config/sofa_confidence_calibration
.json at an install the operator approves - scripts/sofa/
install_new_market_curves.py), fit_report.md / gate_report.md, and with a
holdout rows_holdout.csv.gz (every holdout forecast) and rows_final.csv.gz
(the final forecasts at p >= 0.60). Exit 0, 2 on a crash.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sqlite3
import sys
from collections import defaultdict, deque
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import shot_detail as sd  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from scripts.sofa import new_market_gate as gate_mod  # noqa: E402
from scripts.sofa.measure_shot_detail import (  # noqa: E402
    KS,
    LINES,
    ll,
    measure,
    starts,
)

TARGET = "config/sofa_confidence_calibration.json"
FINAL_ROWS_FROM_P = 0.60

Row = tuple[int, int, int, str, dict[str, int]]  # ts, event, player, position, counts
# metric -> [(p, y, event, ts, player, line)]
Forecasts = dict[str, list[tuple[float, int, int, int, int, float]]]


def make_copy(source: str, target: Path) -> None:
    """The three tables the fit reads, for the events that have a shotmap."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp)
    conn.execute("ATTACH DATABASE ? AS live", (f"file:{source}?mode=ro",))
    conn.executescript("""
        CREATE TABLE sofa_event_extra AS SELECT * FROM live.sofa_event_extra
            WHERE kind = 'shotmap' AND length(payload_json) > 2;
        CREATE INDEX x_id ON sofa_event_extra (sofascore_event_id);
        CREATE TABLE sofa_event_stats AS
            SELECT s.sofascore_event_id, s.lineups_json FROM live.sofa_event_stats s
            JOIN sofa_event_extra x USING (sofascore_event_id);
        CREATE TABLE sofa_listing_event AS
            SELECT l.event_id, l.start_ts FROM live.sofa_listing_event l
            JOIN sofa_event_extra x ON x.sofascore_event_id = l.event_id;
    """)
    conn.commit()
    conn.close()
    tmp.replace(target)


def fit_estimator(rows: list[Row]) -> tuple[dict[str, Any], list[str]]:
    """Each metric's K (walk-forward log-loss) and position means."""
    pool_sum: dict[tuple[str, str], float] = defaultdict(float)
    pool_n: dict[str, int] = defaultdict(int)
    for _ts, _e, _p, pos, start in rows:
        pool_n[pos] += 1
        for m in sd.METRICS:
            pool_sum[(pos, m)] += start[m]
    n_all = sum(pool_n.values())
    preds = measure(rows, sd.MIN_STARTS, sd.WINDOW)["preds"]
    metrics: dict[str, Any] = {}
    report = [f"starts: {n_all}", ""]
    for m in sd.METRICS:
        total = {k: sum(sum(ll(p[k], y) for p, _, y in preds[(m, line)])
                        for line in LINES) for k in KS}
        best = min(total, key=lambda k: total[k])
        metrics[m] = {
            "k": best,
            "pool": {pos: round(pool_sum[(pos, m)] / n, 5)
                     for pos, n in pool_n.items() if n >= 200},
            "pool_all": round(sum(pool_sum[(pos, m)] for pos in pool_n) / n_all, 5),
        }
        report.append(f"- {m}: K={best}; " + ", ".join(
            f"K={k} {v / max(1, sum(len(preds[(m, ln)]) for ln in LINES)):.4f}"
            for k, v in total.items()))
    return metrics, report


def forecasts(rows: list[Row], fitted: Mapping[str, Any], from_ts: int,
              to_ts: int) -> Forecasts:
    """SHEET's forecast of every start in [from_ts, to_ts), from the player's
    earlier starts (every row before it, the window before from_ts included)."""
    hist: dict[int, deque[dict[str, int]]] = defaultdict(
        lambda: deque(maxlen=sd.WINDOW))
    out: Forecasts = defaultdict(list)
    for ts, eid, pid, pos, counts in rows:
        if ts >= to_ts:
            break
        prior = hist[pid]
        if ts >= from_ts and len(prior) >= sd.MIN_STARTS:
            for m in sd.METRICS:
                values = [float(c[m]) for c in prior]
                for line in LINES:
                    p = sd.forecast(values, pos, m, line, fitted)
                    if p is not None:
                        out[m].append((p, 1 if counts[m] > line else 0, eid, ts,
                                       pid, line))
        prior.append(counts)
    return out


def curves_of(fc: Forecasts) -> dict[str, dict[str, Any]]:
    out = {}
    for m in sd.METRICS:
        c = gate_mod.fit_curve((p, y) for p, y, *_ in fc.get(m, []))
        if c:
            out[f"{m}|OVER"] = c
    return out


def write_rows(path: Path, fc: Forecasts, min_p: float = 0.0,
               curve: Mapping[str, Mapping[str, Any]] | None = None) -> int:
    n = 0
    with gzip.open(path, "wt", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["key", "line", "start_ts", "event_id", "player_id", "p", "y",
                    "curve_value"])
        for m in sorted(fc):
            key = f"{m}|OVER"
            for p, y, eid, ts, pid, line in fc[m]:
                if p < min_p:
                    continue
                cv = (gate_mod.curve_value(curve.get(key, {}), p)
                      if curve is not None else None)
                w.writerow([key, line, ts, eid, pid, round(p, 6), y,
                            "" if cv is None else cv])
                n += 1
    return n


def _ts(day: str) -> int:
    d = date.fromisoformat(day)
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--before", required=True)
    ap.add_argument("--out-dir")
    ap.add_argument("--holdout-from", help="fit on starts before it, judge after")
    ap.add_argument("--holdout-to", help="end of the holdout (exclusive); "
                    "default --before")
    ap.add_argument("--estimator", help="the estimator file the FINAL curve is "
                    "priced with (e.g. config/sofa_shot_detail.json); default: "
                    "refitted on every start before --before")
    ap.add_argument("--copy-from", help="make the copy from this DB, not the live one")
    args = ap.parse_args()
    out = Path(args.out_dir or f"data/refit_shot_detail_{args.before}")
    out.mkdir(parents=True, exist_ok=True)
    copy = out / "shot_detail.db"
    if not copy.exists():
        make_copy(args.copy_from or SofaConfig.from_env().db_path, copy)
    db = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
    cut = _ts(args.before)
    rows = [r for r in starts(db) if r[0] < cut]
    report = [f"# Shot detail fit, before {args.before}", ""]
    fitted_from: dict[str, Any] = {
        "db_path": str(copy), "before": args.before,
        "fitted_at_utc": datetime.now(UTC).isoformat(),
        "starts": len(rows), "matches": len({r[1] for r in rows}),
        "script": "scripts/sofa/fit_shot_detail.py",
        "curve": "shot_detail.forecast with the fitted estimator, lines "
                 f"{list(LINES)} pooled per metric|OVER"}

    gates: dict[str, Any] = {}
    training: dict[str, Any] = {}
    if args.holdout_from:
        h0 = _ts(args.holdout_from)
        h1 = _ts(args.holdout_to) if args.holdout_to else cut
        train_rows = [r for r in rows if r[0] < h0]
        est_train, est_report = fit_estimator(train_rows)
        training = curves_of(forecasts(train_rows, {"metrics": est_train}, 0, h0))
        hold = forecasts(rows, {"metrics": est_train}, h0, h1)
        for m in sd.METRICS:
            key = f"{m}|OVER"
            gates[key] = gate_mod.gate(
                training.get(key, {}), [(p, y, e) for p, y, e, *_ in hold.get(m, [])])
        write_rows(out / "rows_holdout.csv.gz", hold, curve=training)
        fitted_from["holdout"] = {
            "train_before": args.holdout_from,
            "holdout_window": [args.holdout_from, args.holdout_to or args.before],
            "train_starts": len(train_rows),
            "holdout_starts": sum(1 for r in rows if h0 <= r[0] < h1),
            "train_estimator": est_train,
            "rule": f"curve value >= {gate_mod.PRINT_FLOOR}: |realised - curve| "
                    f"<= {gate_mod.MAX_GAP}, n >= {gate_mod.MIN_N}"}
        report += ["## Training estimator (before " + args.holdout_from + ")", "",
                   *est_report, ""]

    if args.estimator:
        est_doc = json.loads(Path(args.estimator).read_text(encoding="utf-8"))
        est_final = est_doc["metrics"]
        fitted_from["estimator"] = {"path": args.estimator,
                                    "fitted_from": est_doc.get("fitted_from")}
    else:
        est_final, est_report = fit_estimator(rows)
        fitted_from["estimator"] = {"path": str(out / "sofa_shot_detail.json")}
        report += ["## Estimator (before " + args.before + ")", "", *est_report, ""]
        (out / "sofa_shot_detail.json").write_text(json.dumps(
            {"fitted_from": fitted_from, "window": sd.WINDOW,
             "min_starts": sd.MIN_STARTS, "outside_x": sd.OUTSIDE_X,
             "metrics": est_final}, indent=1) + "\n")
    final_fc = forecasts(rows, {"metrics": est_final}, 0, cut)
    final = curves_of(final_fc)
    if args.holdout_from:
        installable = {k: v for k, v in final.items() if gates.get(k, {}).get("pass")}
        write_rows(out / "rows_final.csv.gz", final_fc, min_p=FINAL_ROWS_FROM_P)
    else:
        installable = final
    doc: dict[str, Any] = {"target": TARGET, "group": "shot_detail",
                           "fitted_from": fitted_from,
                           "by_market_direction": installable}
    if args.holdout_from:
        doc["gate"] = gates
        doc["training_curves"] = training
        doc["final_curves_all_keys"] = final
    (out / "curves.json").write_text(json.dumps(doc, indent=1) + "\n")
    for key, c in final.items():
        report.append(f"## {key}" + (f" - {'PASS' if gates[key]['pass'] else 'FAIL'}"
                                     if gates else ""))
        report += [f"- {b}: n {e['n']}, realised {e['realised']}, lo95 "
                   f"{e['realised_lo95']}" for b, e in c.items()]
        report.append("")
    (out / "fit_report.md").write_text("\n".join(report) + "\n")
    if gates:
        lines = [f"# Shot detail - holdout gate ({args.holdout_from} .. "
                 f"{args.holdout_to or args.before})", ""]
        for key in sorted(gates):
            lines += gate_mod.gate_lines(key, gates[key])
        (out / "gate_report.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"out_dir": str(out), "starts": len(rows),
                      "pass": sorted(k for k, g in gates.items() if g["pass"]),
                      "fail": sorted(k for k, g in gates.items() if not g["pass"]),
                      "curves": {k: len(v) for k, v in installable.items()}}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc!r}", file=sys.stderr)
        raise SystemExit(2) from exc
