"""Measure football DNB / double chance / 1X2 from the pure rating centre with
the season-phase term (audit 2026-10-13 D1 after C1).

Pre-registered in docs/sofa/evidence/football_result_phase_2026-10-13.md.
Built on scripts/sofa/measure_football_result_model.py (the C2 measurement of
RAPORT_NOC_2026-10-12.md): the walk-forward rows (`collect_rows`, every state
as of the match), the `nb_rating` model (independent NB goals on the as-of
rating centres, one r fitted on TRAIN), the base rate, the bucket curves
(`fit_curves` on TRAIN). Variant B multiplies both sides' goals centres by
exp(c[phase]) (season_phase.fit_coefficients on TRAIN's rating centres, the
phase as of the kickoff from season_phase.phases_by_event) and refits r on
them; variant A is C2's model. UNLINKED fixtures are left out of TRAIN and
TEST (SHEET refuses them).

Reported per market (dnb, double_chance, 1x2): d log-loss B - A and B - base
per match (95% from resampling matches, 2000, seed 0); after the curve, the
calibration of the selections at p >= 0.70 over TEST and over August -
September 2026 (season start), for A and B.

Read-only: the history pickle is opened read-only; writes only --json-out.

    SOFA_DB_PATH=... PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/measure_football_result_phase.py \\
        [--train-from 2024-10-01] [--test-from 2026-06-09] \\
        [--test-to 2026-10-12] [--json-out <file>]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa import season_phase as sp  # noqa: E402
from bet.sofa.count_dispersion import load_table  # noqa: E402
from scripts.sofa.measure_football_result_model import (  # noqa: E402
    LINKS,
    PRINTABLE,
    Selection,
    apply_curves,
    collect_rows,
    fit_curves,
    fit_params,
    match_loglosses,
    price,
    subset,
)
from scripts.sofa.measure_season_phase import (  # noqa: E402
    boot_by_match,
    load_history,
    ts_of,
)

F64 = NDArray[np.float64]
MODEL = "nb_rating"
MARKETS = ("dnb", "double_chance", "1x2")
SEASON_START = ("2026-08-01", "2026-10-01")
MIN_N = 300
MAX_GAP = 0.02


def with_phase(d: dict[str, F64], phase: list[str | None],
               coefs: dict[str, float]) -> dict[str, F64]:
    """The rows with both sides' full-time rating centres x exp(c[phase])."""
    mult = np.array([math.exp(coefs[p]) if p in coefs else 1.0 for p in phase])
    out = dict(d)
    out["lh"] = d["lh"] * mult
    out["la"] = d["la"] * mult
    return out


def calib(sels: list[Selection], d: dict[str, F64], market: str,
          mask: NDArray[np.bool_] | None = None) -> dict[str, Any]:
    """realised - p of the market's selections at p >= PRINTABLE (matches in
    `mask` only), 95% resampling matches."""
    ms = [s for s in sels if s.market == market]
    p = np.concatenate([s.p for s in ms])
    o = np.concatenate([s.o for s in ms])
    m = np.concatenate([s.match for s in ms])
    sel = p >= PRINTABLE
    if mask is not None:
        sel &= mask[m]
    gap = boot_by_match(d["eid"][m[sel]].astype(np.int64), o[sel] - p[sel])
    return {"n": int(sel.sum()), "matches": gap[4],
            "mean_p": float(p[sel].mean()) if sel.any() else None,
            "realised": float(o[sel].mean()) if sel.any() else None,
            "gap": list(gap[:3]),
            "pass": bool(sel.sum() >= MIN_N and abs(gap[0]) <= MAX_GAP)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-from", default="2024-10-01")
    ap.add_argument("--test-from", default="2026-06-09")
    ap.add_argument("--test-to", default="2026-10-12")
    ap.add_argument("--history", help="the parsed history pickle (read-only)")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    history = load_history(Path(args.history) if args.history else None)
    print(f"history {len(history)}", flush=True)
    phases = sp.phases_by_event(history)
    rows = collect_rows(history, ts_of(args.train_from), ts_of(args.test_to) + 86400)
    del history
    rows = subset(rows, rows["link"] != LINKS.index(fr.UNLINKED))
    t0 = ts_of(args.test_from)
    train, test = subset(rows, rows["ts"] < t0), subset(rows, rows["ts"] >= t0)
    print(f"train {len(train['ts'])} test {len(test['ts'])}", flush=True)
    ph_train = [phases.get(int(e)) for e in train["eid"]]
    ph_test = [phases.get(int(e)) for e in test["eid"]]
    coefs = sp.fit_coefficients(
        np.concatenate([train["lh"], train["la"]]).tolist(),
        np.concatenate([train["x"], train["y"]]).tolist(), ph_train + ph_train)
    print(f"phase coefficients (rating centre) {coefs}", flush=True)
    table = load_table()
    variants = {"A": (train, test), "B": (with_phase(train, ph_train, coefs),
                                          with_phase(test, ph_test, coefs))}
    months = np.array([datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d")
                       for t in test["ts"]])
    start_mask = (months >= SEASON_START[0]) & (months < SEASON_START[1])
    out: dict[str, Any] = {
        "windows": vars(args) | {"season_start": list(SEASON_START)},
        "phase_coefficients": coefs,
        "test_matches": int(len(test["ts"])),
        "test_matches_by_phase": {str(p): ph_test.count(p) for p in (*sp.PHASES, None)},
    }
    lls: dict[str, dict[str, tuple[F64, F64]]] = {}
    for name, (tr, te) in variants.items():
        par = fit_params(tr)
        curves = fit_curves(price(tr, MODEL, par, table).sels)
        pr = price(te, MODEL, par, table)
        lls[name] = match_loglosses(pr.mp, pr.ht, te, te["x"], te["y"], te["x1"],
                                    te["y1"], pr.ht_mask)
        curved = apply_curves(pr.sels, curves)
        out[name] = {"r": par["r_rating"], "markets": {}}
        for market in MARKETS:
            lm, lb = lls[name][market]
            ids = te["eid"].astype(np.int64)
            if market == "dnb":
                ids = ids[te["x"] != te["y"]]
            out[name]["markets"][market] = {
                "vs_base": list(boot_by_match(ids, lm - lb)),
                "calibration_raw": calib(pr.sels, te, market),
                "calibration_curve": calib(curved, te, market),
                "calibration_curve_season_start": calib(curved, te, market,
                                                        start_mask),
                "calibration_raw_season_start": calib(pr.sels, te, market,
                                                      start_mask),
            }
        print(name, json.dumps(out[name]), flush=True)
    out["B_minus_A"] = {}
    for market in MARKETS:
        ids = test["eid"].astype(np.int64)
        if market == "dnb":
            ids = ids[test["x"] != test["y"]]
        d = lls["B"][market][0] - lls["A"][market][0]
        out["B_minus_A"][market] = list(boot_by_match(ids, d))
    print("B-A", json.dumps(out["B_minus_A"]), flush=True)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
