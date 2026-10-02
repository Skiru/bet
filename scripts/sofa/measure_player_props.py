#!/usr/bin/env python3
"""Measure bet.sofa.player_model against Superbet's price on graded player lines.

For every settled basketball / hockey game with graded player lines
(runs/sofa/shadow/<sport>/<date>/settled.json), the model is rebuilt from the
database strictly before the earlier of Superbet's kickoff and Sofascore's
start, with the graded game excluded by id. The player is the one the grade
read - the subject matched in the graded game's own stored box by the grade's
matcher (source `recomputed`) - or, where the box is not stored, the strict
name rule over the history (source `recomputed:name`; never pooled with the
box-matched one). Where SHADOW_SETTLE already attached a number (model_source
`pregame` - the last forecast SHADOW wrote before the start - or `settle`),
that number is measured too, per source, never pooled with the recomputed
one. The source key carries everything that makes two numbers different
measurements: a model other than this one or a fitted file other than the
current one (`pregame:player_rate_v2@2026-10-02T22:20:19+00:00`), the teams a
pregame row resolved (`:teams=1`), and `:IN_SAMPLE` for a graded date before
that file's training cut.

Per sport and family: sides, lines (pairs), games, model coverage; Brier and
log loss of the model and of the devigged price on the same sides, with a 95%
interval for (model - price) from a bootstrap over GAMES; calibration in
bands; the combination test b of logit(y) ~ logit(model) + logit(price)
(measure_model_information.bootstrap_b, over games); ROI at the offered odds
of the "model above the price by X" cells - evidence, never a rule; and the
same Brier difference and b on the even and odd Sofascore event ids
(split-half sign check).

A measurement: it writes nothing the pipeline reads. The database is opened
read-only.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_player_props.py \\
        [--sport basketball] [--date 2026-09-30 ...] [--rows-out rows.jsonl] \\
        [--json-out report.json] [--bootstrap 500]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sqlite3
import sys
import time
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.player_model import (  # noqa: E402
    MODEL_NAME,
    MODEL_SPORTS,
    PLAYER_MODEL_FILE,
    UNFITTED,
    box_player_ids,
    config_identity,
    history_cutoff,
    line_key,
    load_appearances,
    params_provenance,
    read_forecasts,
    score_rows,
)
from bet.sofa.shadow import SETTLED_FILE, is_player_line  # noqa: E402
from scripts.sofa.measure_model_information import bootstrap_b, fit  # noqa: E402

EDGES = (0.0, 0.05, 0.10)
BANDS = (0.0, 0.2, 0.35, 0.5, 0.65, 0.8, 1.0001)
MIN_ROWS_B = 30
EPS = 1e-4


def _iso_ts(text: str) -> int:
    return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())


def _event(conn: sqlite3.Connection, eid: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT event_json FROM sofa_listed_event WHERE event_id = ?", (eid,)
    ).fetchone()
    return dict(json.loads(row[0])) if row else None


def _lineups(conn: sqlite3.Connection, eid: int) -> Any:
    row = conn.execute(
        "SELECT lineups_json FROM sofa_event_stats WHERE sofascore_event_id = ?",
        (eid,),
    ).fetchone()
    if not row or not row[0]:
        return None
    try:
        return json.loads(row[0])
    except ValueError:
        return None


def in_sample(date: str, cut_utc: str | None) -> bool:
    """A graded date before the fitted file's training cut was in its
    training data."""
    if not cut_utc:
        return False
    return date < str(cut_utc)[:10]


def attached_source(g: dict[str, Any], date: str, teams_resolved: Any = None) -> str:
    """The attached number's source key: model_source, then whatever makes
    it a different measurement from this model's current numbers - another
    model or another fitted file (`@fitted_at_utc`; a row without one is
    `@?`), a pregame row's resolved team count, and IN_SAMPLE."""
    current = config_identity()
    source = str(g["model_source"])
    model = g.get("model")
    config = g.get("model_config")
    if model not in (None, MODEL_NAME) or config != current["model_config"]:
        source += f":{model}@{config or '?'}"
    if source.startswith("pregame"):
        teams = g.get("model_teams_resolved", teams_resolved)
        source += f":teams={teams if teams is not None else '?'}"
    if in_sample(date, g.get("model_cut_utc")):
        source += ":IN_SAMPLE"
    return source


def _forecast_teams(day: Path) -> dict[tuple[Any, ...], Any]:
    """(superbet id, line key, fetched_at) -> teams_resolved of the day's
    pre-game rows, for a graded row attached before it carried the count."""
    out: dict[tuple[Any, ...], Any] = {}
    for r in read_forecasts(day / PLAYER_MODEL_FILE):
        key = (str(r["superbet_event_id"]), line_key(r), r.get("fetched_at_utc"))
        out[key] = r.get("teams_resolved")
    return out


def collect(
    runs_dir: str,
    conn: sqlite3.Connection,
    sports: Sequence[str],
    dates: Sequence[str] | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Every graded player side with an outcome: one row per source that has
    a p for it (recomputed always tried; pregame / settle when attached)."""
    rows: list[dict[str, Any]] = []
    skipped: dict[str, int] = defaultdict(int)
    for sport in sports:
        base = Path(runs_dir) / "shadow" / sport
        days = sorted(p.name for p in base.glob("*") if (p / SETTLED_FILE).exists())
        for date in days:
            if dates and date not in dates:
                continue
            doc = json.loads((base / date / SETTLED_FILE).read_text(encoding="utf-8"))
            teams_of = _forecast_teams(base / date)
            current = config_identity()
            for sb_id, entry in sorted(doc.get("events", {}).items()):
                if entry.get("state") != "SETTLED":
                    continue
                graded = [
                    g
                    for g in entry.get("graded") or []
                    if is_player_line(sport, int(g["market_id"]))  # type: ignore[arg-type]
                    and g.get("outcome") in ("WIN", "LOSS")
                    and g.get("fair_p") is not None
                ]
                if not graded:
                    continue
                eid = int(entry["sofascore_event_id"])
                event = _event(conn, eid)
                box_ids = box_player_ids(_lineups(conn, eid))
                recomputed = "recomputed" if box_ids is not None else "recomputed:name"
                if in_sample(date, current["model_cut_utc"]):
                    recomputed += ":IN_SAMPLE"
                if event is None:
                    skipped["no_listed_event"] += len(graded)
                    scored: list[Any] = [None] * len(graded)
                else:
                    teams = [
                        int(t["id"])
                        for t in (event.get("homeTeam"), event.get("awayTeam"))
                        if isinstance(t, dict) and isinstance(t.get("id"), int)
                    ]
                    start = event.get("startTimestamp")
                    before = history_cutoff(
                        _iso_ts(entry["kickoff_utc"]),
                        int(start) if isinstance(start, int) else None,
                    )
                    apps = load_appearances(conn, sport, teams, before, eid)  # type: ignore[arg-type]
                    scored = score_rows(graded, sport, apps, box_ids)  # type: ignore[arg-type]
                for g, mp in zip(graded, scored, strict=True):
                    common = {
                        "sport": sport,
                        "date": date,
                        "game": f"{sport}:{date}:{sb_id}",
                        "event_id": eid,
                        "family": g["family"],
                        "subject": g.get("subject"),
                        "line": g.get("line"),
                        "side": g["side"],
                        "odds": float(g["odds"]),
                        "p_price": float(g["fair_p"]),
                        "y": 1.0 if g["outcome"] == "WIN" else 0.0,
                    }
                    if mp is not None and mp.p is not None:
                        rows.append(
                            {
                                **common,
                                "source": recomputed,
                                "p_model": mp.p,
                                "model_n": mp.n,
                                "model_mean": mp.mean,
                                "model_config": current["model_config"],
                            }
                        )
                    else:
                        reason = "no_listed_event" if mp is None else str(mp.reason)
                        skipped[f"{sport}:{recomputed}:{reason}"] += 1
                    if g.get("model_p") is not None and g.get("model_source"):
                        rows.append(
                            {
                                **common,
                                "source": attached_source(
                                    g,
                                    date,
                                    teams_of.get(
                                        (
                                            str(sb_id),
                                            line_key(g),
                                            g.get("model_fetched_at_utc"),
                                        )
                                    ),
                                ),
                                "p_model": float(g["model_p"]),
                                "model_n": g.get("model_n"),
                                "model_mean": g.get("model_mean"),
                                "model_config": g.get("model_config"),
                            }
                        )
    return rows, dict(skipped)


def _brier(p: float, y: float) -> float:
    return (p - y) ** 2


def _logloss(p: float, y: float) -> float:
    p = min(max(p, EPS), 1.0 - EPS)
    return -(y * math.log(p) + (1.0 - y) * math.log(1.0 - p))


def bootstrap_mean(
    by_game: dict[str, list[float]], rng: random.Random, n: int
) -> tuple[float, float, float]:
    """Mean over lines and its 95% interval, resampling whole games."""
    games = list(by_game)
    total = sum(sum(v) for v in by_game.values())
    count = sum(len(v) for v in by_game.values())
    if not count:
        return (0.0, 0.0, 0.0)
    stats = []
    for _ in range(n):
        pick = [games[rng.randrange(len(games))] for _ in games]
        s = sum(sum(by_game[g]) for g in pick)
        c = sum(len(by_game[g]) for g in pick)
        stats.append(s / c if c else 0.0)
    stats.sort()
    return total / count, stats[int(0.025 * n)], stats[min(int(0.975 * n), n - 1)]


def summarize(
    rows: Sequence[dict[str, Any]], n_boot: int, seed: int = 7
) -> dict[str, Any]:
    """Every number of the report for one group of rows."""
    rng = random.Random(seed)
    n = len(rows)
    lines = {(r["game"], r["family"], r["subject"], r["line"]) for r in rows}
    games = {r["game"] for r in rows}
    out: dict[str, Any] = {"sides": n, "lines": len(lines), "games": len(games)}
    if not n:
        return out
    out["brier_price"] = sum(_brier(r["p_price"], r["y"]) for r in rows) / n
    out["brier_model"] = sum(_brier(r["p_model"], r["y"]) for r in rows) / n
    out["logloss_price"] = sum(_logloss(r["p_price"], r["y"]) for r in rows) / n
    out["logloss_model"] = sum(_logloss(r["p_model"], r["y"]) for r in rows) / n
    diff: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        diff[r["game"]].append(
            _brier(r["p_model"], r["y"]) - _brier(r["p_price"], r["y"])
        )
    out["brier_model_minus_price"] = bootstrap_mean(diff, rng, n_boot)
    out["calibration"] = []
    for lo, hi in zip(BANDS, BANDS[1:], strict=False):
        band = [r for r in rows if lo <= r["p_model"] < hi]
        if band:
            out["calibration"].append(
                {
                    "band": f"{lo:.2f}-{min(hi, 1.0):.2f}",
                    "n": len(band),
                    "mean_model": sum(r["p_model"] for r in band) / len(band),
                    "mean_price": sum(r["p_price"] for r in band) / len(band),
                    "hit": sum(r["y"] for r in band) / len(band),
                }
            )
    if n >= MIN_ROWS_B and len(games) >= 3:
        b, lo, hi = bootstrap_b(list(rows), n=n_boot)
        out["b"] = [b, lo, hi]
    out["roi_cells"] = []
    for edge in EDGES:
        cell = [r for r in rows if r["p_model"] - r["p_price"] > edge]
        by_game: dict[str, list[float]] = defaultdict(list)
        for r in cell:
            by_game[r["game"]].append(r["odds"] * r["y"] - 1.0)
        roi = bootstrap_mean(by_game, rng, n_boot) if cell else (0.0, 0.0, 0.0)
        out["roi_cells"].append(
            {
                "edge": edge,
                "n": len(cell),
                "games": len(by_game),
                "hit": (sum(r["y"] for r in cell) / len(cell)) if cell else None,
                "roi": roi,
            }
        )
    halves: dict[str, Any] = {}
    for name, parity in (("even", 0), ("odd", 1)):
        half = [r for r in rows if int(r["event_id"]) % 2 == parity]
        if not half:
            halves[name] = None
            continue
        d = sum(
            _brier(r["p_model"], r["y"]) - _brier(r["p_price"], r["y"]) for r in half
        ) / len(half)
        hb = None
        if len(half) >= MIN_ROWS_B and len({r["game"] for r in half}) >= 2:
            hb = fit(half)[1]
        halves[name] = {
            "sides": len(half),
            "games": len({r["game"] for r in half}),
            "brier_diff": d,
            "b": hb,
        }
    out["split_half"] = halves
    return out


def _fmt_ci(t: Sequence[float]) -> str:
    return f"{t[0]:+.4f} [{t[1]:+.4f},{t[2]:+.4f}]"


def render(report: dict[str, Any]) -> str:
    out: list[str] = []
    for key, s in report["groups"].items():
        if not s.get("sides"):
            continue
        head = (
            f"{key:44s} sides={s['sides']:5d} lines={s['lines']:5d} "
            f"games={s['games']:3d}"
        )
        if "brier_price" not in s:
            out.append(head)
            continue
        b = s.get("b")
        sh = s["split_half"]
        halves = " ".join(
            f"{h}:{'-' if v is None else format(v['brier_diff'], '+.4f')}"
            f"/b={'-' if v is None or v['b'] is None else format(v['b'], '+.2f')}"
            for h, v in sh.items()
        )
        out.append(
            head
            + f" brier price {s['brier_price']:.4f} model {s['brier_model']:.4f}"
            + f" diff {_fmt_ci(s['brier_model_minus_price'])}"
            + f" logloss {s['logloss_price']:.4f}/{s['logloss_model']:.4f}"
            + (f" b {_fmt_ci(b)}" if b else " b -")
            + f" | {halves}"
        )
        cells = " ".join(
            f">{c['edge']:.2f}: n={c['n']} roi={c['roi'][0]:+.3f}"
            f"[{c['roi'][1]:+.3f},{c['roi'][2]:+.3f}]"
            for c in s["roi_cells"]
        )
        out.append(f"    roi(model-price>X) {cells}")
        cal = " ".join(
            f"{c['band']}: n={c['n']} m={c['mean_model']:.2f} "
            f"p={c['mean_price']:.2f} hit={c['hit']:.2f}"
            for c in s["calibration"]
        )
        out.append(f"    calibration {cal}")
    return "\n".join(out)


def build_report(rows: Sequence[dict[str, Any]], n_boot: int) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[f"{r['sport']}|{r['source']}|ALL"].append(r)
        groups[f"{r['sport']}|{r['source']}|{r['family']}"].append(r)
    ordered = sorted(
        groups,
        key=lambda k: (k.split("|")[:2], k.split("|")[2] != "ALL", -len(groups[k])),
    )
    return {
        "model": MODEL_NAME,
        "unfitted_constants": list(UNFITTED),
        "fitted_constants": params_provenance(),
        "config_identity": config_identity(),
        "groups": {k: summarize(groups[k], n_boot) for k in ordered},
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sport", choices=sorted(MODEL_SPORTS), action="append")
    ap.add_argument("--date", action="append", default=None)
    ap.add_argument("--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"))
    ap.add_argument("--db", default=None, help="default: SofaConfig's db_path")
    ap.add_argument("--rows-out", default=None, help="every scored side, JSONL")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--bootstrap", type=int, default=500)
    args = ap.parse_args(argv)
    started = time.monotonic()
    db = args.db or SofaConfig.from_env().db_path
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=60)
    try:
        rows, skipped = collect(
            args.runs_dir, conn, args.sport or sorted(MODEL_SPORTS), args.date
        )
    finally:
        conn.close()
    if args.rows_out:
        Path(args.rows_out).write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
    report = build_report(rows, args.bootstrap)
    report["skipped"] = skipped
    report["runtime_s"] = round(time.monotonic() - started, 1)
    print(f"model={MODEL_NAME} unfitted={','.join(UNFITTED)}")
    print(f"skipped (no model p): {json.dumps(skipped, sort_keys=True)}")
    print(render(report))
    print(f"runtime {report['runtime_s']} s")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
