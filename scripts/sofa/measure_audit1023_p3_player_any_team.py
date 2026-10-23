#!/usr/bin/env python3
"""P3 / K7 (coverage audit 2026-10-23): does a hockey / basketball player's
history from his peer teams' games (player_model.load_appearances(any_team=
True)) price Superbet's settled player lines better? Read-only evidence.

For every settled game with graded player lines (runs/sofa/shadow/<sport>/
<date>/settled.json; WIN / LOSS with a devigged price), the model is rebuilt
from the database strictly before the earlier kickoff, the graded game
excluded, the player the grade read (the graded game's own box, as
measure_player_props' `recomputed`), under each configuration:

  old        the two teams' games (side rule), the installed constants;
  any        the same plus the peers' games, the installed constants;
  any_refit  the peers' games, the constants of --refit (a file fitted with
             fit_player_model.py --player-team-from-side --any-team);
  old_refit  the two teams' games, the constants of --refit-old (fitted
             with --player-team-from-side only), when given.

The side rule is used on every date for both readers, so the reader is the
only difference between `old` and `any`. Reported per sport: coverage (sides
with a p), and on the sides every configuration prices (common), each one's
log loss and Brier and the paired difference to `old` with a 95% interval
from a bootstrap over GAMES; the same on the sides whose p moved; the
sides only the peers' reader prices (added) - claimed vs realised with a game
bootstrap interval of (y - p); calibration bands. The pre-game name path is
checked too: the player the strict name rule finds (find_player over the
any-team history, as SHADOW's forecast) against the player the box says.

    PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/measure_audit1023_p3_player_any_team.py \\
        --db data/refit_2026-10-23_allin/sofa_copy.db [--refit f.json] \\
        [--refit-old g.json] [--sport hockey] [--json-out report.json]
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
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from bet.sofa import player_model as pm  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.shadow import SETTLED_FILE, is_player_line  # noqa: E402
from scripts.sofa.measure_player_props import (  # noqa: E402
    _event,
    _iso_ts,
    _lineups,
    bootstrap_mean,
)

EPS = 1e-4
BANDS = (0.0, 0.2, 0.35, 0.5, 0.65, 0.7, 0.8, 0.9, 1.0001)
MEMO_MAX = 150_000


def _ll(p: float, y: float) -> float:
    p = min(max(p, EPS), 1.0 - EPS)
    return -(y * math.log(p) + (1.0 - y) * math.log(1.0 - p))


def _br(p: float, y: float) -> float:
    return (p - y) ** 2


def collect(
    runs_dir: str,
    conn: sqlite3.Connection,
    sports: Sequence[str],
    configs: dict[str, tuple[bool, dict[str, pm.SportParams]]],
    dates: Sequence[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    names: dict[str, int] = defaultdict(int)
    for sport in sports:
        memo: dict[tuple[int, int, bool], tuple[list[pm.Appearance], list[int]]] = {}
        base = Path(runs_dir) / "shadow" / sport
        days = sorted(p.name for p in base.glob("*") if (p / SETTLED_FILE).exists())
        for date in days:
            if dates and date not in dates:
                continue
            doc = json.loads((base / date / SETTLED_FILE).read_text(encoding="utf-8"))
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
                box_ids = pm.box_player_ids(_lineups(conn, eid))
                if event is None or box_ids is None:
                    names["no_event_or_box"] += len(graded)
                    continue
                teams = [
                    int(t["id"])
                    for t in (event.get("homeTeam"), event.get("awayTeam"))
                    if isinstance(t, dict) and isinstance(t.get("id"), int)
                ]
                start = event.get("startTimestamp")
                before = pm.history_cutoff(
                    _iso_ts(entry["kickoff_utc"]),
                    int(start) if isinstance(start, int) else None,
                )
                if len(memo) > MEMO_MAX:
                    memo.clear()
                apps_any = pm.load_appearances(
                    conn, sport, teams, before, eid,  # type: ignore[arg-type]
                    team_from_side=True, any_team=True, memo=memo,
                )
                apps_old = [a for a in apps_any if not a.foreign]
                scored: dict[str, list[pm.PlayerProbability]] = {}
                for cname, (any_team, params) in configs.items():
                    scored[cname] = pm.score_rows(
                        graded, sport,  # type: ignore[arg-type]
                        apps_any if any_team else apps_old,
                        box_ids,
                        params=params[sport],
                    )
                for i, g in enumerate(graded):
                    box_pid, _ = pm.match_in_box(str(g.get("subject") or ""), box_ids)
                    row: dict[str, Any] = {
                        "sport": sport,
                        "date": date,
                        "game": f"{sport}:{date}:{sb_id}",
                        "family": g["family"],
                        "subject": g.get("subject"),
                        "side": g["side"],
                        "line": g.get("line"),
                        "odds": float(g["odds"]),
                        "p_price": float(g["fair_p"]),
                        "y": 1.0 if g["outcome"] == "WIN" else 0.0,
                        "box_pid": box_pid,
                    }
                    for cname in configs:
                        mp = scored[cname][i]
                        row[f"p_{cname}"] = mp.p
                        row[f"n_{cname}"] = mp.n
                    rows.append(row)
                # The pre-game name path, one count per subject of the game.
                for subject in sorted({str(g.get("subject") or "") for g in graded}):
                    box_pid, _ = pm.match_in_box(subject, box_ids)
                    if box_pid is None:
                        continue
                    for label, apps, tr in (
                        ("old", apps_old, False),
                        ("any", apps_any, False),
                        ("any_translit", apps_any, True),
                    ):
                        pid, why = pm.find_player(subject, apps, tr)
                        if pid is None:
                            names[f"{sport}:{label}:{why}"] += 1
                        elif pid == box_pid:
                            names[f"{sport}:{label}:SAME_AS_BOX"] += 1
                        else:
                            names[f"{sport}:{label}:OTHER_THAN_BOX"] += 1
    return rows, dict(names)


def _boot_ci(
    by_game: dict[str, list[float]], n_boot: int, seed: int = 11
) -> tuple[float, float, float]:
    return bootstrap_mean(by_game, random.Random(seed), n_boot)


def _paired(
    rows: Sequence[dict[str, Any]], a: str, b: str, fn: Any, n_boot: int
) -> tuple[float, float, float]:
    by_game: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_game[r["game"]].append(fn(r[f"p_{a}"], r["y"]) - fn(r[f"p_{b}"], r["y"]))
    return _boot_ci(by_game, n_boot)


def summarize(
    rows: Sequence[dict[str, Any]], configs: Sequence[str], n_boot: int
) -> dict[str, Any]:
    out: dict[str, Any] = {"sides": len(rows), "games": len({r["game"] for r in rows})}
    out["coverage"] = {
        c: sum(1 for r in rows if r[f"p_{c}"] is not None) for c in configs
    }
    common = [r for r in rows if all(r[f"p_{c}"] is not None for c in configs)]
    for r in common:
        r["p_price_"] = r["p_price"]
    out["common"] = {
        "sides": len(common),
        "games": len({r["game"] for r in common}),
        "logloss": {c: sum(_ll(r[f"p_{c}"], r["y"]) for r in common) / len(common)
                    for c in configs} if common else {},
        "brier": {c: sum(_br(r[f"p_{c}"], r["y"]) for r in common) / len(common)
                  for c in configs} if common else {},
        "logloss_price": (sum(_ll(r["p_price"], r["y"]) for r in common) / len(common))
        if common else None,
    }
    out["common"]["diff_vs_old"] = {
        c: {
            "logloss": _paired(common, c, "old", _ll, n_boot),
            "brier": _paired(common, c, "old", _br, n_boot),
        }
        for c in configs
        if c != "old" and common
    }
    out["common"]["diff_vs_price"] = {
        c: {"logloss": _paired(common, c, "price_", _ll, n_boot)}
        for c in configs
        if common
    }
    moved = [r for r in common if abs(r["p_any"] - r["p_old"]) > 1e-9]
    out["moved"] = {
        "sides": len(moved),
        "games": len({r["game"] for r in moved}),
        "diff_vs_old": {
            c: {
                "logloss": _paired(moved, c, "old", _ll, n_boot),
                "brier": _paired(moved, c, "old", _br, n_boot),
            }
            for c in configs
            if c != "old" and moved
        },
        "mean_n": {c: (sum(r[f"n_{c}"] for r in moved) / len(moved)) if moved else None
                   for c in configs},
    }
    for c in configs:
        if c == "old":
            continue
        added = [r for r in rows if r["p_old"] is None and r[f"p_{c}"] is not None]
        by_game: dict[str, list[float]] = defaultdict(list)
        for r in added:
            by_game[r["game"]].append(r["y"] - r[f"p_{c}"])
        k = max(len(added), 1)
        out[f"added_{c}"] = {
            "sides": len(added),
            "games": len(by_game),
            "claimed": sum(r[f"p_{c}"] for r in added) / k if added else None,
            "hit": sum(r["y"] for r in added) / k if added else None,
            "hit_minus_claimed": _boot_ci(by_game, n_boot) if added else None,
            "logloss": sum(_ll(r[f"p_{c}"], r["y"]) for r in added) / k
            if added else None,
            "logloss_price": sum(_ll(r["p_price"], r["y"]) for r in added) / k
            if added else None,
        }
    out["calibration"] = {}
    for c in configs:
        cells = []
        priced = [r for r in rows if r[f"p_{c}"] is not None]
        for lo, hi in zip(BANDS, BANDS[1:], strict=False):
            band = [r for r in priced if lo <= r[f"p_{c}"] < hi]
            if band:
                cells.append(
                    {
                        "band": f"{lo:.2f}-{min(hi, 1.0):.2f}",
                        "n": len(band),
                        "claimed": round(sum(r[f"p_{c}"] for r in band) / len(band), 4),
                        "hit": round(sum(r["y"] for r in band) / len(band), 4),
                    }
                )
        out["calibration"][c] = cells
    return out


def _load_params(path: str | None) -> dict[str, pm.SportParams]:
    return pm.load_params(Path(path) if path else None)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sport", choices=sorted(pm.MODEL_SPORTS), action="append")
    ap.add_argument("--date", action="append", default=None)
    ap.add_argument("--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"))
    ap.add_argument("--db", default=None, help="default: SofaConfig's db_path")
    ap.add_argument("--refit", default=None, help="constants fitted with --any-team")
    ap.add_argument("--refit-old", default=None, help="constants fitted without it")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--rows-out", default=None)
    ap.add_argument("--bootstrap", type=int, default=1000)
    args = ap.parse_args(argv)
    started = time.monotonic()
    installed = _load_params(None)
    configs: dict[str, tuple[bool, dict[str, pm.SportParams]]] = {
        "old": (False, installed),
        "any": (True, installed),
    }
    if args.refit:
        configs["any_refit"] = (True, _load_params(args.refit))
    if args.refit_old:
        configs["old_refit"] = (False, _load_params(args.refit_old))
    db = args.db or SofaConfig.from_env().db_path
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=60)
    try:
        rows, names = collect(
            args.runs_dir, conn, args.sport or sorted(pm.MODEL_SPORTS), configs,
            args.date,
        )
    finally:
        conn.close()
    report: dict[str, Any] = {
        "db": str(db),
        "configs": {c: {"any_team": a} for c, (a, _) in configs.items()},
        "refit": args.refit,
        "refit_old": args.refit_old,
        "names": names,
        "unfitted_constants": list(pm.UNFITTED),
        "sports": {},
    }
    for sport in sorted({r["sport"] for r in rows}):
        report["sports"][sport] = summarize(
            [r for r in rows if r["sport"] == sport], list(configs), args.bootstrap
        )
    report["runtime_s"] = round(time.monotonic() - started, 1)
    text = json.dumps(report, indent=1)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    if args.rows_out:
        Path(args.rows_out).write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
