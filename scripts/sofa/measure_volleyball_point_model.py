#!/usr/bin/env python3
"""Measure the volleyball rally-point model (bet.sofa.volleyball_point_model)
- read-only. Report: docs/sofa/evidence/volleyball_point_model_2026-11-06.md
(rules pre-registered in its section 0 before the first run).

Stages (each writes JSON into --out-dir only):

  * ``tune``: the model's constants by coordinate descent on the exact
    set-score log likelihood of matches 2025-11-01 .. 2026-02-28, the rating
    walked over the history before 2026-03-01 only;
  * ``history``: walk-forward 2026-03-01 .. 2026-09-28 on the current score
    model's own history rows (same game, line, side; --current-rows-dir
    volleyball_history_fit.jsonl), plus the model's curve rows on its own
    quantile lines 2025-10-01 .. 2026-09-28 -> curves (sport_confidence.
    fit_curves), never written to config/;
  * ``superbet``: SHADOW_SETTLE lines (runs/sofa/shadow/volleyball/<d>/
    settled.json) - model vs the current score model's p
    (volleyball_superbet_settled.jsonl) vs the de-vigged price, raw and
    after curves; the hold-out days only with --holdout.

The history comes from --history-cache: a pickle of (event id, ts,
competition, home, away, women, home set points, away set points) as
sport_confidence.parse_history(golden_set=True) reads the cache (read-only).
Never the network.

    PYTHONPATH=src:. taskpolicy -b nice -n 10 .venv/bin/python \\
        scripts/sofa/measure_volleyball_point_model.py --stage tune|history|superbet \\
        --history-cache <pkl> --out-dir <dir> [--holdout] [--workers 2]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import multiprocessing
import pickle
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import volleyball_point_model as vpm  # noqa: E402
from bet.sofa.score_model import set_format_ok  # noqa: E402
from bet.sofa.shadow import SPORTS, ShadowLine, actual_value, grade  # noqa: E402
from bet.sofa.sport_confidence import (  # noqa: E402
    DEGENERATE_P,
    HISTORY_MARKETS,
    LINE_QUANTILES,
    MIN_BUCKET,
    _find,
    curve_key,
    fit_curves,
)
from scripts.sofa.measure_tennis_point_model import boot_mean  # noqa: E402

SPORT = SPORTS["volleyball"]
DEFAULT_CURRENT_ROWS = _REPO / "data" / "line_evidence" / "rows_before_2026-11-06"
DEFAULT_CAL = (_REPO / "config"
               / "sofa_sport_confidence_calibration.next.2026-10-28.json")
SHADOW_DIR = _REPO / "runs" / "sofa" / "shadow" / "volleyball"

# Pre-registered (report section 0).
TUNE_FIT_BEFORE = "2026-03-01"
TUNE_VALID_FROM = "2025-11-01"
HIST_FROM = "2026-03-01"
HIST_TO = "2026-09-28"
CURVE_FROM = "2025-10-01"
CURVE_TO = "2026-09-28"
SB_FROM = "2026-09-29"
HOLDOUT_FROM = "2026-10-20"
HOLDOUT_TO = "2026-11-05"
NONINFERIORITY_BRIER = 0.002
MIN_LEGS = 30
TAX = 0.88
SIMS = 4000
BANDS = (("p>=0.70", 0.70, 1.01), ("0.60-0.70", 0.60, 0.70))
VERDICT_FAMILIES = ("points_handicap", "points_total", "set_handicap",
                    "exact_sets", "set_points_total")
SET_MARKETS = (744, 782)
CANONICAL = ("T1", "OVER", "ODD", "YES")

# The tuning grid (coordinate descent from the defaults, two rounds). The
# first run (2026-11-06, before any hold-out) ended with prior_var and
# drift_per_day on the grid's lower edge; the grid was then extended past
# every edge (coordinator 2026-11-06, written into report section 0 before
# the hold-out) and a second run warm-started from the first's optimum
# (--warm-start). Training window only.
GRID: dict[str, tuple[float, ...]] = {
    "sideout_men": (0.48, 0.52, 0.56, 0.60, 0.64, 0.68, 0.72, 0.76),
    "sideout_women": (0.48, 0.52, 0.56, 0.60, 0.64, 0.68, 0.72, 0.76),
    "prior_var": (0.002, 0.005, 0.01, 0.02, 0.03, 0.06, 0.10, 0.20, 0.40),
    "drift_per_day": (0.0, 0.00001, 0.00003, 0.0001, 0.0003, 0.001, 0.003),
    "weight": (0.05, 0.08, 0.15, 0.3, 0.5, 1.0, 2.0),
    "home": (0.0, 0.03, 0.06, 0.10, 0.15),
    "form_var": (0.0, 0.005, 0.01, 0.02, 0.04, 0.08),
    "set_var": (0.0, 0.005, 0.01, 0.02, 0.04),
}


def _ts(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


def _day(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")


def load_history(path: str) -> list[vpm.VbMatch]:
    with open(path, "rb") as fh:
        raw = pickle.load(fh)
    out = [vpm.VbMatch(int(e), int(ts), int(c), int(h), int(a), bool(w),
                       tuple(int(x) for x in hs), tuple(int(x) for x in as_))
           for e, ts, c, h, a, w, hs, as_ in raw]
    out.sort(key=lambda m: (m.ts, m.event_id))
    return out


def params_from(path: Path | None) -> vpm.VbParams:
    if path is None or not path.exists():
        return vpm.VbParams()
    doc = json.loads(path.read_text(encoding="utf-8"))
    return vpm.VbParams(**doc["params"])


# --------------------------------------------------------------------------
# tune
# --------------------------------------------------------------------------


def valid_loglik(history: Sequence[vpm.VbMatch], params: vpm.VbParams) -> float:
    cut = _ts(TUNE_FIT_BEFORE)
    lo = _ts(TUNE_VALID_FROM)
    before = [m for m in history if m.ts < cut]
    valid = [m for m in before if m.ts >= lo
             and set_format_ok(m.home_sets, m.away_sets)]
    fc = vpm.walk_forward(before, {m.event_id for m in valid}, params)
    total = 0.0
    for m in valid:
        total += vpm.match_loglik(fc[m.event_id], m.home_sets, m.away_sets, params)
    return total / max(len(valid), 1)


def run_tune(args: argparse.Namespace, history: list[vpm.VbMatch]) -> dict[str, Any]:
    params = params_from(args.warm_start) if args.warm_start else vpm.VbParams()
    log: list[dict[str, Any]] = []
    best = valid_loglik(history, params)
    log.append({"params": dataclasses.asdict(params), "loglik": best})
    print(f"start {best:.5f}", flush=True)
    for rnd in range(2):
        for name, values in GRID.items():
            for v in values:
                if getattr(params, name) == v:
                    continue
                changes: dict[str, Any] = {name: v}
                cand = dataclasses.replace(params, **changes)
                ll = valid_loglik(history, cand)
                log.append({"round": rnd, name: v, "loglik": ll})
                if ll > best + 1e-6:
                    best, params = ll, cand
            print(f"round {rnd} {name} -> {getattr(params, name)} ({best:.5f})",
                  flush=True)
    base = vpm.VbParams(sideout_men=0.5, sideout_women=0.5)
    iid = valid_loglik(history, dataclasses.replace(
        params, sideout_men=0.5, sideout_women=0.5))
    n_valid = sum(1 for m in history if _ts(TUNE_VALID_FROM) <= m.ts < _ts(
        TUNE_FIT_BEFORE) and set_format_ok(m.home_sets, m.away_sets))
    return {"params": dataclasses.asdict(params), "loglik": best,
            "loglik_iid_rallies_same_params": iid,
            "loglik_defaults_iid": valid_loglik(history, base),
            "valid_matches": n_valid,
            "window": {"fit_before": TUNE_FIT_BEFORE, "valid_from": TUNE_VALID_FROM},
            "log": log}


# --------------------------------------------------------------------------
# Rows of one game (workers fork: module globals are the parent's)
# --------------------------------------------------------------------------

_STATE: dict[str, Any] = {}


def _result_of(m: vpm.VbMatch) -> Any:
    w1 = sum(1 for a, b in zip(m.home_sets, m.away_sets, strict=True) if a > b)
    w2 = len(m.home_sets) - w1
    from bet.sofa.shadow import GameResult
    return GameResult(m.home_sets, m.away_sets, w1, w2, "T1" if w1 > w2 else "T2",
                      False)


def _lines_of(sim: vpm.VbSim) -> list[ShadowLine]:
    from bet.sofa.shadow import spec_of
    out: list[ShadowLine] = []
    for mid in (*HISTORY_MARKETS["volleyball"], *SET_MARKETS):
        spec = spec_of("volleyball", mid)
        assert spec is not None
        periods = (1, 2, 3, 4, 5) if mid in SET_MARKETS else (0,)
        for period in periods:
            if spec.kind in ("winner", "dnb"):
                sides: list[tuple[float | None, str]] = [(None, "T1"), (None, "T2")]
            elif spec.kind == "odd_even":
                sides = [(None, "ODD"), (None, "EVEN")]
            elif spec.kind == "exact":
                sides = [(None, f"{a}:{b}") for a, b in
                         ((3, 0), (3, 1), (3, 2), (2, 3), (1, 3), (0, 3))]
            else:
                cuts = vpm.quantile_lines(sim, mid, period, LINE_QUANTILES)
                if spec.kind == "handicap":
                    sides = [(-c, s) for c in cuts for s in ("T1", "T2")]
                else:
                    sides = [(c, s) for c in cuts for s in ("OVER", "UNDER")]
            team = spec.team or ""
            out += [ShadowLine("", mid, spec.family, period, team, ln, s, 1.0)
                    for ln, s in sides]
    return out


def history_job(eid: int) -> dict[str, Any]:
    m: vpm.VbMatch = _STATE["by_id"][eid]
    f: vpm.VbForecast = _STATE["forecasts"][eid]
    params: vpm.VbParams = _STATE["params"]
    sim = vpm.simulate(f, params, n=SIMS, seed=eid % (2 ** 31))
    result = _result_of(m)
    curve_rows: list[tuple[str, float, int]] = []
    if _STATE["curve_lo"] <= m.ts < _STATE["curve_hi"]:
        for ln in _lines_of(sim):
            p = vpm.line_p(sim, ln.market_id, ln.period, ln.subject, ln.line, ln.side)
            if p is None:
                continue
            if ln.line is not None and not DEGENERATE_P <= p <= 1 - DEGENERATE_P:
                continue
            actual = actual_value(ln, result, SPORT)
            if actual is None:
                continue
            outcome = grade(ln, actual, False)
            if outcome == "VOID":
                continue
            curve_rows.append((curve_key(ln.family, ln.side), round(p, 4),
                               1 if outcome == "WIN" else 0))
    test: list[dict[str, Any]] = []
    for r in _STATE["current_rows"].get(eid, ()):
        p = vpm.line_p(sim, int(r["market_id"]), int(r["period"] or 0),
                       str(r["subject"] or ""), r["line"], str(r["side"]))
        if p is not None:
            test.append({**r, "p_new": p})
    return {"eid": eid, "curve_rows": curve_rows, "test": test}


def _pool(workers: int) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(max_workers=workers,
                               mp_context=multiprocessing.get_context("fork"))


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


def brier(p: float, y: int) -> float:
    return (p - y) ** 2


def logloss(p: float, y: int) -> float:
    p = min(max(p, 1e-4), 1.0 - 1e-4)
    return -math.log(p if y else 1.0 - p)


def canonical(side: str) -> bool:
    return side in CANONICAL or ":" in side or side.startswith("SETS=")


def paired(rows: Sequence[Mapping[str, Any]], arms: Sequence[str]) -> dict[str, Any]:
    """Brier / log-loss of each arm and the differences of every arm against
    the first, match-clustered."""
    g = [r["game"] for r in rows]
    out: dict[str, Any] = {"rows": len(rows), "matches": len(set(g))}
    if not rows:
        return out
    for name, f in (("brier", brier), ("logloss", logloss)):
        vals = {a: [f(float(r[a]), int(r["y"])) for r in rows] for a in arms}
        out[name] = {a: sum(v) / len(v) for a, v in vals.items()}
        for a in arms[1:]:
            out[name][f"{arms[0]}_minus_{a}"] = boot_mean(
                g, [x - y for x, y in zip(vals[arms[0]], vals[a], strict=True)])
        if len(arms) > 2:
            out[name][f"{arms[1]}_minus_{arms[2]}"] = boot_mean(
                g, [x - y for x, y in zip(vals[arms[1]], vals[arms[2]], strict=True)])
    return out


@dataclass(frozen=True)
class Leg:
    game: str
    p: float
    odds: float
    y: int
    p_price: float


def band_stats(legs: Sequence[Leg], lo: float, hi: float) -> dict[str, Any]:
    cell = [x for x in legs if lo <= x.p < hi]
    if not cell:
        return {"n": 0}
    g = [x.game for x in cell]
    out: dict[str, Any] = {
        "n": len(cell), "matches": len(set(g)),
        "claimed": sum(x.p for x in cell) / len(cell),
        "realised": boot_mean(g, [float(x.y) for x in cell]),
        "gap": boot_mean(g, [x.y - x.p for x in cell]),
        "price_nv": sum(x.p_price for x in cell) / len(cell),
    }
    printable = [x for x in cell if x.odds > 1.0 and x.p * x.odds >= 0.90]
    if printable:
        gp = [x.game for x in printable]
        out["x_ge_090"] = {
            "n": len(printable), "matches": len(set(gp)),
            "roi": boot_mean(gp, [x.odds - 1.0 if x.y else -1.0 for x in printable]),
            "roi_after_tax": boot_mean(
                gp, [TAX * x.odds - 1.0 if x.y else -1.0 for x in printable])}
    return out


def conf(curves: Mapping[str, Any], key: str, p: float) -> float | None:
    entry = _find(curves.get(key) or {}, p)
    if entry is None or int(entry["n"]) < MIN_BUCKET:
        return None
    return float(entry["realised_lo95"])


# --------------------------------------------------------------------------
# history
# --------------------------------------------------------------------------


def load_current_history_rows(rows_dir: Path, lo: int, hi: int
                              ) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = defaultdict(list)
    with (rows_dir / "volleyball_history_fit.jsonl").open(encoding="utf-8") as fh:
        for raw in fh:
            r = json.loads(raw)
            if not lo <= int(r["ts"]) < hi:
                continue
            eid = int(str(r["game"]).split(":")[1])
            out[eid].append({k: r[k] for k in ("family", "market_id", "period",
                                               "subject", "line", "side", "key",
                                               "p", "y", "game")})
    return out


def run_history(args: argparse.Namespace, history: list[vpm.VbMatch],
                params: vpm.VbParams) -> dict[str, Any]:
    by_id = {m.event_id: m for m in history}
    hlo, hhi = _ts(HIST_FROM), _ts(HIST_TO) + 86400
    clo, chi = _ts(CURVE_FROM), _ts(CURVE_TO) + 86400
    current = load_current_history_rows(args.current_rows_dir, hlo, hhi)
    wanted = {m.event_id for m in history if clo <= m.ts < chi
              and set_format_ok(m.home_sets, m.away_sets)}
    missing = [e for e in current if e not in by_id]
    wanted |= {e for e in current if e in by_id}
    forecasts = vpm.walk_forward(history, wanted, params)
    _STATE.update(by_id=by_id, forecasts=forecasts, params=params,
                  current_rows=current, curve_lo=clo, curve_hi=chi)
    curve_rows: list[dict[str, Any]] = []
    test_rows: list[dict[str, Any]] = []
    jobs = sorted(e for e in wanted if e in forecasts)
    print(f"history: {len(jobs)} games ({len(current)} with current rows, "
          f"{len(missing)} of them not in the model's history)", flush=True)
    with _pool(args.workers) as pool:
        for i, res in enumerate(pool.map(history_job, jobs, chunksize=32)):
            for key, p, y in res["curve_rows"]:
                curve_rows.append({"key": key, "p": p, "y": y,
                                   "game": f"h:{res['eid']}"})
            test_rows += res["test"]
            if (i + 1) % 1000 == 0:
                print(f"{i + 1} / {len(jobs)}", flush=True)
    curves = fit_curves(curve_rows)
    (args.out_dir / "volleyball_curves.json").write_text(json.dumps(
        {"fitted_from": {"window": [CURVE_FROM, CURVE_TO], "rows": len(curve_rows),
                         "games": len({r["game"] for r in curve_rows}),
                         "params": dataclasses.asdict(params), "sims": SIMS,
                         "lines": "sport_confidence.synthetic_lines rule "
                                  "(LINE_QUANTILES of the game's own simulation)"},
         "curves": curves}, indent=1), encoding="utf-8")
    with (args.out_dir / "volleyball_history_test_rows.jsonl").open("w") as fh:
        for r in test_rows:
            fh.write(json.dumps(r) + "\n")
    out: dict[str, Any] = {"games_with_current_rows": len(current),
                           "not_in_model_history": len(missing),
                           "curve_rows": len(curve_rows), "families": {}}
    fams = sorted({r["family"] for r in test_rows})
    for fam in [*fams, "all"]:
        sel = [{**r, "p_cur": r["p"]} for r in test_rows
               if (fam == "all" or r["family"] == fam) and canonical(str(r["side"]))]
        if not sel:
            continue
        legs_new = [Leg(r["game"], r["p_new"], 0.0, int(r["y"]), 0.5) for r in test_rows
                    if fam == "all" or r["family"] == fam]
        legs_cur = [Leg(r["game"], r["p"], 0.0, int(r["y"]), 0.5) for r in test_rows
                    if fam == "all" or r["family"] == fam]
        out["families"][fam] = {
            "scores": paired(sel, ("p_new", "p_cur")),
            "bands_new": {n: _strip(band_stats(legs_new, lo, hi))
                          for n, lo, hi in BANDS},
            "bands_current": {n: _strip(band_stats(legs_cur, lo, hi))
                              for n, lo, hi in BANDS},
        }
    return out


def _strip(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k not in ("x_ge_090", "price_nv")}


# --------------------------------------------------------------------------
# superbet
# --------------------------------------------------------------------------


def _match_from_settled(ev: Mapping[str, Any], last_comp: Mapping[int, int]
                        ) -> vpm.VbMatch | None:
    """A pinned Superbet match absent from the cached history, rebuilt from
    its settled record (home / away from Sofascore's orientation)."""
    try:
        eid = int(ev["sofascore_event_id"])
        home, away = int(ev["sofascore_home_id"]), int(ev["sofascore_away_id"])
        start = str(ev.get("sofascore_start_utc") or ev["kickoff_utc"])
        ts = int(datetime.fromisoformat(start.replace("Z", "+00:00")).timestamp())
    except (KeyError, TypeError, ValueError):
        return None
    t1, t2 = ev.get("t1_periods") or [], ev.get("t2_periods") or []
    if not t1 or len(t1) != len(t2):
        return None
    hs, as_ = (t1, t2) if ev.get("home_is_team1", True) else (t2, t1)
    women = "(K)" in str(ev.get("tournament") or "") or "Women" in str(
        ev.get("sofascore_tournament") or "")
    comp = last_comp.get(home, last_comp.get(away, -1))
    return vpm.VbMatch(eid, ts, comp, home, away, women,
                       tuple(int(x) for x in hs), tuple(int(x) for x in as_))


def load_superbet(args: argparse.Namespace, last_day: str
                  ) -> tuple[list[dict[str, Any]], dict[int, Any], dict[str, int]]:
    """Every WIN / LOSS line 09-29..last_day with its event's pin."""
    cur: dict[tuple[Any, ...], float] = {}
    with (args.current_rows_dir / "volleyball_superbet_settled.jsonl").open(
            encoding="utf-8") as fh:
        for raw in fh:
            r = json.loads(raw)
            _s, d, sb = str(r["game"]).split(":")
            cur[(d, sb, int(r["market_id"] or 0), int(r["period"] or 0),
                 str(r["subject"] or ""), r["line"], r["side"])] = float(r["p"])
    lines: list[dict[str, Any]] = []
    events: dict[int, Any] = {}
    drops: dict[str, int] = defaultdict(int)
    for day_dir in sorted(SHADOW_DIR.iterdir()):
        d = day_dir.name
        if not (SB_FROM <= d <= last_day) or not (day_dir / "settled.json").exists():
            continue
        doc = json.loads((day_dir / "settled.json").read_text(encoding="utf-8"))
        for ev in doc["events"].values():
            if not ev.get("pinned_id") or ev.get("orientation_unclear"):
                drops["not_pinned_or_unclear"] += 1
                continue
            eid = int(ev["sofascore_event_id"])
            events[eid] = ev
            for g in ev.get("graded", []):
                if g.get("outcome") not in ("WIN", "LOSS") or g.get("fair_p") is None:
                    continue
                sb = str(g["superbet_event_id"])
                key = (d, sb, int(g["market_id"] or 0), int(g["period"] or 0),
                       str(g["subject"] or ""), g["line"], g["side"])
                lines.append({
                    "day": d, "eid": eid, "game": f"s:{d}:{sb}",
                    "family": g["family"], "market_id": int(g["market_id"]),
                    "period": int(g["period"] or 0), "subject": str(g["subject"] or ""),
                    "line": g["line"], "side": str(g["side"]),
                    "odds": float(g["odds"]), "p_price": float(g["fair_p"]),
                    "y": 1 if g["outcome"] == "WIN" else 0,
                    "p_cur": cur.get(key), "home_is_team1": bool(ev.get("home_is_team1",
                                                                         True))})
    return lines, events, dict(drops)


def sb_job(eid: int) -> tuple[int, dict[tuple[Any, ...], float | None]]:
    f = _STATE["forecasts"][eid]
    sim = vpm.simulate(f, _STATE["params"], n=SIMS, seed=eid % (2 ** 31))
    out: dict[tuple[Any, ...], float | None] = {}
    for key in _STATE["sb_keys"][eid]:
        mid, period, subject, line, side, home_t1 = key
        s = sim if home_t1 else sim.swapped()
        out[key] = vpm.line_p(s, mid, period, subject, line, side)
    return eid, out


def run_superbet(args: argparse.Namespace, history: list[vpm.VbMatch],
                 params: vpm.VbParams) -> dict[str, Any]:
    last_day = HOLDOUT_TO if args.holdout else "2026-10-19"
    lines, events, drops = load_superbet(args, last_day)
    by_id = {m.event_id: m for m in history}
    last_comp: dict[int, int] = {}
    for m in history:
        last_comp[m.home] = m.competition
        last_comp[m.away] = m.competition
    added: list[vpm.VbMatch] = []
    for eid, ev in events.items():
        if eid not in by_id:
            rebuilt = _match_from_settled(ev, last_comp)
            if rebuilt is not None:
                added.append(rebuilt)
    full = sorted([*history, *added], key=lambda m: (m.ts, m.event_id))
    forecasts = vpm.walk_forward(full, set(events), params)
    sb_keys: dict[int, set[tuple[Any, ...]]] = defaultdict(set)
    for r in lines:
        if r["eid"] in forecasts:
            sb_keys[r["eid"]].add((r["market_id"], r["period"], r["subject"], r["line"],
                                   r["side"], r["home_is_team1"]))
    _STATE.update(forecasts=forecasts, params=params, sb_keys=sb_keys)
    table: dict[int, dict[tuple[Any, ...], float | None]] = {}
    with _pool(args.workers) as pool:
        for eid, ps in pool.map(sb_job, sorted(sb_keys), chunksize=8):
            table[eid] = ps
    curves_new = json.loads((args.out_dir / "volleyball_curves.json").read_text(
        encoding="utf-8"))["curves"]
    cal = json.loads(Path(args.calibration).read_text(encoding="utf-8"))
    curves_cur = cal["sports"]["volleyball"]["curves"]
    priced: list[dict[str, Any]] = []
    for r in lines:
        found = table.get(r["eid"])
        if found is None:
            drops["no_forecast"] += 1
            continue
        p = found.get((r["market_id"], r["period"], r["subject"], r["line"], r["side"],
                       r["home_is_team1"]))
        if p is None:
            drops["model_no_p"] += 1
            continue
        key = curve_key(r["family"], r["side"])
        priced.append({**r, "p_new": p, "key": key,
                       "c_new": conf(curves_new, key, p),
                       "c_cur": (conf(curves_cur, key, r["p_cur"])
                                 if r["p_cur"] is not None else None)})
    with (args.out_dir / ("volleyball_sb_holdout.jsonl" if args.holdout
                          else "volleyball_sb_dev.jsonl")).open("w") as fh:
        for r in priced:
            fh.write(json.dumps(r) + "\n")
    out: dict[str, Any] = {"lines": len(lines), "priced": len(priced),
                           "events": len(events), "added_from_settled": len(added),
                           "drops": drops}
    out["dev"] = family_report([r for r in priced if r["day"] < HOLDOUT_FROM])
    if args.holdout:
        out["holdout"] = family_report([r for r in priced if r["day"] >= HOLDOUT_FROM])
        out["holdout_verdicts"] = {f: verdict(v) for f, v in out["holdout"].items()
                                   if f in VERDICT_FAMILIES}
    out["dev_verdicts"] = {f: verdict(v) for f, v in out["dev"].items()
                           if f in VERDICT_FAMILIES}
    return out


def family_report(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    fams = sorted({r["family"] for r in rows})
    for fam in [*fams, "all"]:
        sel = [r for r in rows if fam == "all" or r["family"] == fam]
        if not sel:
            continue
        canon = [r for r in sel if canonical(r["side"])]
        both = [r for r in canon if r["p_cur"] is not None]
        arms: dict[str, list[Leg]] = {"model_p": [], "current_p": [],
                                      "model_conf": [], "current_conf": []}
        for r in sel:
            for arm, v in (("model_p", r["p_new"]), ("current_p", r["p_cur"]),
                           ("model_conf", r["c_new"]), ("current_conf", r["c_cur"])):
                if v is not None:
                    arms[arm].append(Leg(r["game"], float(v), r["odds"], r["y"],
                                         r["p_price"]))
        out[fam] = {
            "days": [min(r["day"] for r in sel), max(r["day"] for r in sel)],
            "scores_vs_price": paired(canon, ("p_new", "p_price")),
            "scores_three": paired(both, ("p_new", "p_cur", "p_price")),
            "bands": {arm: {n: band_stats(lg, lo, hi) for n, lo, hi in BANDS}
                      for arm, lg in arms.items()},
        }
    return out


def verdict(fam: Mapping[str, Any]) -> dict[str, str]:
    s3 = fam["scores_three"]
    sp = fam["scores_vs_price"]
    hi_p = sp["brier"]["p_new_minus_p_price"][2] if "brier" in sp else math.inf
    hi_c = (s3["brier"]["p_new_minus_p_cur"][2] if "brier" in s3 else math.inf)
    b = fam["bands"]["model_conf"]["p>=0.70"]
    cal = ("za mało nóg" if b.get("n", 0) < MIN_LEGS
           else "tak" if b["gap"][2] >= 0 else "nie")
    return {"as_good_as_price": "tak" if hi_p <= NONINFERIORITY_BRIER else "nie",
            "no_overpromise_after_curve": cal,
            "better_than_current": "tak" if hi_c < 0 else "nie"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--stage", choices=("tune", "history", "superbet"), required=True)
    ap.add_argument("--history-cache", required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--current-rows-dir", type=Path, default=DEFAULT_CURRENT_ROWS)
    ap.add_argument("--calibration", type=Path, default=DEFAULT_CAL)
    ap.add_argument("--holdout", action="store_true")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--warm-start", type=Path, default=None,
                    help="tune: start from this earlier tune's params")
    ap.add_argument("--tune-out", default="volleyball_tune2.json")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    history = load_history(args.history_cache)
    print(f"history {len(history)} matches", flush=True)
    tuned = args.out_dir / args.tune_out
    if args.stage == "tune":
        res = run_tune(args, history)
        tuned.write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(json.dumps({k: res[k] for k in res if k != "log"}, indent=1), flush=True)
        return 0
    params = params_from(tuned)
    if args.stage == "history":
        res = run_history(args, history, params)
        (args.out_dir / "volleyball_history.json").write_text(
            json.dumps(res, indent=1), encoding="utf-8")
        print(json.dumps({f: v["scores"].get("brier") for f, v in
                          res["families"].items()}, indent=1), flush=True)
        return 0
    res = run_superbet(args, history, params)
    name = "volleyball_holdout.json" if args.holdout else "volleyball_dev.json"
    (args.out_dir / name).write_text(json.dumps(res, indent=1), encoding="utf-8")
    key = "holdout_verdicts" if args.holdout else "dev_verdicts"
    print(json.dumps(res.get(key), indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
