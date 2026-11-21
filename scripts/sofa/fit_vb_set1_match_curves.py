#!/usr/bin/env python3
"""Fit the history curves of volleyball's "1.Set/Mecz" (Superbet 230059,
epochs.VB_SET1_MATCH_FROM_UTC) - keys set1_match|SAME and set1_match|SPLIT -
from the rally-point model's walk-forward over the cached history, and judge
them on a later hold-out of the same history. Read-only on the database.

The model is the one SPORT_CONFIDENCE prices the market with
(bet.sofa.vb_point_pricer: PARAMS, 4,000 simulations seeded by the Sofascore
event id): every best-of-five match of the history (score_model.load_events
-> sport_confidence.parse_history with the golden-set rule, home = team1) is
forecast as of its start from the matches before it
(volleyball_point_model.walk_forward), simulated, and each of the four sides
"T1/T1" .. "T2/T2" priced (volleyball_point_model.line_p) and graded as
SHADOW_SETTLE grades it (shadow.actual_value / grade: set 1's points, the
sets won). The curves: sport_confidence.fit_curves (MIN_BUCKET 200) over
CURVE_FROM .. CURVE_TO - the window of the rally model's 16 keys
(config/sofa_volleyball_point_curves.json). The hold-out: HOLDOUT_FROM ..
HOLDOUT_TO read through those curves (sport_confidence.evaluate, match
bootstrap); the acceptance rule of the plan (PLAN_NOWE_RYNKI_2026-11-20.md
section 6): on the printable rows (confidence >= 0.70) realised minus
confidence >= -3 pp.

Writes into --out-dir only (history pickle, rows, report, the curves file);
`--install` also writes config/sofa_vb_set1_match_curves.json, and only when
the hold-out passed - never the rally model's file a built day reads.

    SOFA_DB_PATH=<copy> PYTHONPATH=src:. nice -n 10 .venv/bin/python \\
        scripts/sofa/fit_vb_set1_match_curves.py --out-dir <dir> \\
        [--db-path <copy>] [--workers 2] [--install]

`--forward --to <d>` (T-VB-SET1-MATCH-calibration, read-only, no fit): the
SHADOW_SETTLE rows of 230059 from FORWARD_FROM to <d> (WIN / LOSS, pinned and
oriented), each at the rally model's p (vb_point_pricer.BACKFILL) read
through the installed curve; per key, the rows with confidence >= 0.70:
realised minus confidence with a match bootstrap.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_vb_set1_match_curves.py \\
        --forward --to <d>

Exit 0 OK (hold-out passed), 1 hold-out failed (nothing installed), 2 FAILED.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import multiprocessing
import pickle
import random
import sys
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa import vb_point_pricer as vpp  # noqa: E402
from bet.sofa import volleyball_point_model as vpm  # noqa: E402
from bet.sofa.cs2 import SET_MATCH_SET  # noqa: E402
from bet.sofa.score_model import set_format_ok  # noqa: E402
from bet.sofa.shadow import (  # noqa: E402
    SPORTS,
    GameResult,
    ShadowLine,
    actual_value,
    grade,
)

MARKET_ID = 230059
FAMILY = "set1_match"
SIDES = tuple(sorted(SET_MATCH_SET))
SPORT = SPORTS["volleyball"]
CURVE_FROM = "2025-10-01"
CURVE_TO = "2026-09-28"
HOLDOUT_FROM = "2026-09-29"
HOLDOUT_TO = "2026-11-20"
MAX_PRINTABLE_GAP = -0.03
FORWARD_FROM = "2026-11-22"
FORWARD_LINES = 300
FORWARD_GAMES = 40
CURVES_FILE = _REPO / "config" / scf.VB_SET1_MATCH_CURVES_FILE
_STATE: dict[str, Any] = {}


def _ts(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


def load_history(db_path: str, cache: Path) -> list[vpm.VbMatch]:
    """The rally model's history as SPORT_CONFIDENCE builds it (pickled in
    the out-dir: a second run reads the pickle)."""
    if cache.exists():
        with cache.open("rb") as fh:
            out: list[vpm.VbMatch] = pickle.load(fh)
        return out
    from bet.sofa.score_model import load_events

    events = load_events(db_path, SPORT)
    history = vpp.history_matches(scf.parse_history(events, SPORT, golden_set=True))
    del events
    with cache.open("wb") as fh:
        pickle.dump(history, fh)
    return history


def result_of(m: vpm.VbMatch) -> GameResult:
    w1 = sum(1 for a, b in zip(m.home_sets, m.away_sets, strict=True) if a > b)
    w2 = len(m.home_sets) - w1
    return GameResult(m.home_sets, m.away_sets, w1, w2, "T1" if w1 > w2 else "T2",
                      False)


def rows_of(m: vpm.VbMatch, sim: vpm.VbSim) -> list[dict[str, Any]]:
    """The four sides of one match: the model's p, the settled outcome."""
    result = result_of(m)
    out: list[dict[str, Any]] = []
    for side in SIDES:
        line = ShadowLine("", MARKET_ID, FAMILY, 0, "", None, side, 1.0)
        p = vpm.line_p(sim, MARKET_ID, 0, "", None, side)
        actual = actual_value(line, result, SPORT)
        if p is None or actual is None:
            continue
        outcome = grade(line, actual)
        if outcome == "VOID":
            continue
        out.append({"key": scf.curve_key(FAMILY, side), "side": side,
                    "p": round(p, 4), "y": 1 if outcome == "WIN" else 0,
                    "game": f"h:{m.event_id}", "ts": m.ts,
                    "women": m.women})
    return out


def job(eid: int) -> list[dict[str, Any]]:
    m: vpm.VbMatch = _STATE["by_id"][eid]
    f: vpm.VbForecast = _STATE["forecasts"][eid]
    sim = vpm.simulate(f, vpp.PARAMS, n=vpp.N_SIMS, seed=vpp.seed_of(eid))
    return rows_of(m, sim)


def walk(history: Sequence[vpm.VbMatch], workers: int) -> list[dict[str, Any]]:
    lo, hi = _ts(CURVE_FROM), _ts(HOLDOUT_TO) + 86400
    wanted = {m.event_id for m in history if lo <= m.ts < hi
              and set_format_ok(m.home_sets, m.away_sets)}
    forecasts = vpm.walk_forward(history, wanted, vpp.PARAMS)
    _STATE.update(by_id={m.event_id: m for m in history}, forecasts=forecasts)
    jobs = sorted(e for e in wanted if e in forecasts)
    print(f"walk-forward: {len(jobs)} matches", flush=True)
    rows: list[dict[str, Any]] = []
    ctx = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
        for i, got in enumerate(pool.map(job, jobs, chunksize=32)):
            rows += got
            if (i + 1) % 2000 == 0:
                print(f"{i + 1} / {len(jobs)}", flush=True)
    return rows


def judge(holdout: dict[str, Any]) -> dict[str, Any]:
    """The plan's rule per key: printable realised - confidence >= -3 pp
    (the point estimate; a key with no printable hold-out row is no
    evidence - reported, and SAME must have them)."""
    out: dict[str, Any] = {}
    for key, summary in holdout.items():
        printable = summary.get("printable")
        if not printable:
            out[key] = "NO_PRINTABLE_ROWS"
            continue
        gap = float(printable["realised_minus_confidence"][0])
        out[key] = "PASSED" if gap >= MAX_PRINTABLE_GAP else "FAILED"
    same = scf.curve_key(FAMILY, "T1/T1")
    passed = (out.get(same) == "PASSED"
              and all(v != "FAILED" for v in out.values()))
    return {"keys": out, "passed": passed}


def curves_doc(curves: dict[str, Any], fit_rows: Sequence[dict[str, Any]],
               report: dict[str, Any]) -> dict[str, Any]:
    return {
        "_doc": ("Volleyball \"1.Set/Mecz\" (230059, epochs.VB_SET1_MATCH): the "
                 "rally model's history curves of set1_match|SAME / |SPLIT, "
                 "overlaid by sport_confidence.with_vb_point_curves onto the "
                 "day's sport calibration while the switch is on for the day "
                 "and the build clock. Fitted on history only "
                 "(scripts/sofa/fit_vb_set1_match_curves.py); never merged into "
                 "config/sofa_volleyball_point_curves.json."),
        "vb_set1_match_curves": {
            "keys": sorted(curves),
            "fitted_from": {
                "window": [CURVE_FROM, CURVE_TO],
                "rows": len(fit_rows),
                "games": len({r["game"] for r in fit_rows}),
                "params": dataclasses.asdict(vpp.PARAMS),
                "sims": vpp.N_SIMS,
                "lines": "the four sides of every best-of-five history match "
                         "(home = team1), graded as SHADOW_SETTLE",
            },
            "holdout": report,
            "estimator": ("bet.sofa.volleyball_point_model through "
                          "bet.sofa.vb_point_pricer (epochs.VB_SET1_MATCH)"),
            "source": "scripts/sofa/fit_vb_set1_match_curves.py, "
                      "sport_confidence.fit_curves, MIN_BUCKET 200",
        },
        "curves": curves,
    }


def forward(runs_dir: Path, to: str) -> dict[str, Any]:
    """T-VB-SET1-MATCH-calibration: the settled lines read as SPORT_CONFIDENCE
    reads them (the rally p, the installed curve), never refitted."""
    from scripts.sofa.backfill_vb_point_p import key_of, settled_lines

    doc = json.loads(CURVES_FILE.read_text(encoding="utf-8"))
    cal = scf.SportCalibration({"sports": {"volleyball": {
        "curves": doc["curves"]}}})
    table = vpp.load_backfill()
    end = (datetime.fromisoformat(to) + timedelta(days=1)).strftime("%Y-%m-%d")
    rows: list[dict[str, Any]] = []
    missing = 0
    for day, ev, g in settled_lines(runs_dir, end):
        if day < FORWARD_FROM or int(g["market_id"]) != MARKET_ID:
            continue
        p = table.get(key_of(day, g))
        if p is None:
            missing += 1
            continue
        conf = cal.lookup("volleyball", FAMILY, str(g["side"]), float(p),
                          require_admitted=False)
        if conf is None:
            continue
        rows.append({"key": scf.curve_key(FAMILY, str(g["side"])), "p": float(p),
                     "conf": conf.value, "y": 1 if g["outcome"] == "WIN" else 0,
                     "game": f"s:{day}:{ev.get('sofascore_event_id')}"})
    out: dict[str, Any] = {"test": "T-VB-SET1-MATCH-calibration",
                           "window": [FORWARD_FROM, to], "no_p": missing,
                           "keys": {}}
    for key in sorted({r["key"] for r in rows}):
        band = [r for r in rows if r["key"] == key and r["conf"] >= 0.70]
        games = {r["game"] for r in band}
        entry: dict[str, Any] = {"lines": len(band), "games": len(games)}
        if band:
            by_game: dict[str, list[float]] = {}
            for r in band:
                by_game.setdefault(r["game"], []).append(r["y"] - r["conf"])
            ids = sorted(by_game)
            gap = sum(sum(v) for v in by_game.values()) / len(band)
            rng = random.Random(20261122)
            stats = []
            for _ in range(2000):
                pick = [by_game[ids[rng.randrange(len(ids))]] for _ in ids]
                n = sum(len(v) for v in pick)
                stats.append(sum(sum(v) for v in pick) / n)
            stats.sort()
            entry["realised_minus_confidence"] = [
                round(gap, 4), round(stats[50], 4), round(stats[1949], 4)]
            entry["status"] = ("PENDING" if len(band) < FORWARD_LINES
                               or len(games) < FORWARD_GAMES else
                               "PASSED" if stats[50] >= -0.03 and stats[1949] <= 0.03
                               and stats[50] <= 0 <= stats[1949]
                               else "FAILED" if stats[1949] < -0.03
                               else "NOT_PASSED")
        out["keys"][key] = entry
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--forward", action="store_true",
                    help="T-VB-SET1-MATCH-calibration on the settled lines")
    ap.add_argument("--to", default=None, help="--forward: the last day")
    ap.add_argument("--db-path", default=None,
                    help="default: SOFA_DB_PATH (SofaConfig) - a COPY")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--install", action="store_true",
                    help=f"write {CURVES_FILE.name} when the hold-out passed")
    args = ap.parse_args()
    from bet.sofa.config import SofaConfig

    config = SofaConfig.from_env()
    if args.forward:
        if not args.to:
            ap.error("--forward needs --to")
        print(json.dumps(forward(Path(config.runs_dir), args.to), indent=1))
        return 0
    if args.out_dir is None:
        ap.error("--out-dir is required")
    db_path = args.db_path or config.db_path
    args.out_dir.mkdir(parents=True, exist_ok=True)
    try:
        history = load_history(db_path, args.out_dir / "vb_history.pkl")
        print(f"history {len(history)} matches", flush=True)
        rows = walk(history, args.workers)
    except Exception as exc:  # noqa: BLE001 - one verdict line, then exit 2
        print(json.dumps({"stage": "FIT_VB_SET1_MATCH", "verdict": "FAILED",
                          "error": repr(exc)}))
        return 2
    with (args.out_dir / "set1_match_rows.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    clo, chi = _ts(CURVE_FROM), _ts(CURVE_TO) + 86400
    hlo = _ts(HOLDOUT_FROM)
    fit_rows = [r for r in rows if clo <= r["ts"] < chi]
    hold_rows = [r for r in rows if r["ts"] >= hlo]
    curves = scf.fit_curves(fit_rows)
    holdout = scf.evaluate(curves, hold_rows)
    verdict = judge(holdout)
    report = {"window": [HOLDOUT_FROM, HOLDOUT_TO], "rows": len(hold_rows),
              "games": len({r["game"] for r in hold_rows}),
              "rule": "printable (confidence >= 0.70) realised - confidence "
                      ">= -3 pp, point estimate, match bootstrap",
              "evaluate": holdout, **verdict}
    doc = curves_doc(curves, fit_rows, report)
    (args.out_dir / "vb_set1_match_curves.json").write_text(
        json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    installed = None
    if args.install and verdict["passed"]:
        CURVES_FILE.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        installed = str(CURVES_FILE)
    print(json.dumps({"stage": "FIT_VB_SET1_MATCH",
                      "verdict": "OK" if verdict["passed"] else "HOLDOUT_FAILED",
                      "fit_rows": len(fit_rows), "holdout_rows": len(hold_rows),
                      "keys": verdict["keys"], "installed": installed}))
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
