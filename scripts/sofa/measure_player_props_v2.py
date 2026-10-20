#!/usr/bin/env python3
"""Read-only measurements behind epochs.FOOTBALL_PLAYER_PROPS_V2 (evidence:
docs/sofa/evidence/football_player_props_v2_2026-10-21.md).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_player_props_v2.py \\
        --db-path data/sofa.db proof
    ... fouls-drawn [--stage-dir data/refit_player_props_v2_2026-10-21]
    ... cards

`proof`: does a missing `wasFouled` key mean zero? Per team-game, the
squad's wasFouled sum against the opponent's fouls (players' and team
figure), split by whether Sofascore wrote the key for every appearing player
(a feed that writes zeros) or omits zeros. Equal shortfalls = the omitted
keys hide nothing (players.PLAYER_METRICS `opponent_bound`).

`fouls-drawn`: replays player_fouls_drawn_for with the repo's own replay
(calibrate_from_cache.build_player_rows: his starts, SHEET's centre and
spread; the NB of engine.NEGATIVE_BINOMIAL_METRICS) OVER at 0.5-4.5; the
normal the metric would have had is recomputed at the same centre and sd;
log-loss NB - normal with a 95% interval resampling matches; the history
curve fitted before HOLDOUT_FROM, gated on HOLDOUT_FROM..HOLDOUT_TO
(scripts/sofa/new_market_gate, one-sided); with --stage-dir the curve is
written as install_new_market_curves.py's group `player_props_v2`
(curves.json + rows.csv.gz) - staged, never installed.

`cards`: "Zawodnik - otrzyma kartkę" (Superbet quotes "Tak" only): the
share of starts whose shrunk per-start booking rate (his last 10 starts
toward his position's rate, K_CARDS starts of weight, walk-forward) reaches
0.70, the most it reaches, and its log-loss against the position rate;
likewise a red card and the first card.

Nothing is written outside --stage-dir; the database is opened read-only.
"""

from __future__ import annotations

import argparse
import collections
import csv
import gzip
import json
import math
import sqlite3
import sys
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from bet.sofa import engine
from bet.sofa.players import team_totals
from scripts.sofa import calibrate_from_cache as cfc
from scripts.sofa import new_market_gate as gate_mod

METRIC = "player_fouls_drawn_for"
LINES = (0.5, 1.5, 2.5, 3.5, 4.5)
HOLDOUT_FROM = "2026-09-01"
HOLDOUT_TO = "2026-10-13"
K_CARDS = 10.0
MIN_CARD_HISTORY = 5
FIT_FROM_CARDS = "2026-03-01"
GROUP = "player_props_v2"


def _ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def _connect(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


def _appearing(lineups: dict[str, Any], side: str) -> list[dict[str, Any]]:
    out = []
    for entry in (lineups.get(side) or {}).get("players") or []:
        stats = (entry or {}).get("statistics") or {}
        if stats.get("minutesPlayed") is not None:
            out.append(stats)
    return out


def proof(db: Path) -> dict[str, Any]:
    conn = _connect(db)
    shortfall: dict[str, collections.Counter[int]] = {
        "full": collections.Counter(), "omitting": collections.Counter()}
    team_rows: dict[str, collections.Counter[str]] = {
        "full": collections.Counter(), "omitting": collections.Counter()}
    q = ("SELECT statistics_json, lineups_json FROM sofa_event_stats "
         "WHERE lineups_json LIKE '%wasFouled%'")
    for stats_json, lineups_json in conn.execute(q):
        lineups = json.loads(lineups_json)
        stats = json.loads(stats_json) if stats_json else None
        sides = {s: _appearing(lineups, s) for s in ("home", "away")}
        for side, other in (("home", "away"), ("away", "home")):
            own, opp = sides[side], sides[other]
            if not own or not opp:
                continue
            kind = ("full" if all("wasFouled" in x for x in own)
                    and all("fouls" in x for x in opp) else "omitting")
            drawn = sum(float(x.get("wasFouled", 0)) for x in own)
            committed = sum(float(x.get("fouls", 0)) for x in opp)
            shortfall[kind][int(round(committed - drawn))] += 1
            team = team_totals(stats, is_home=(other == "home")).get("fouls")
            if team is not None:
                rows = team_rows[kind]
                rows["n"] += 1
                rows["sum_above_team"] += drawn > team + 1e-9
                rows["within_bound"] += 0 <= team - drawn <= 4 + 1e-9
    conn.close()
    out: dict[str, Any] = {}
    for kind, counter in shortfall.items():
        n = sum(counter.values())
        mean = sum(k * v for k, v in counter.items()) / max(n, 1)
        out[kind] = {
            "team_games": n, "mean_shortfall_vs_opponent_players": round(mean, 3),
            "share_equal": round(counter[0] / max(n, 1), 4),
            "share_above": round(sum(v for k, v in counter.items() if k < 0)
                                 / max(n, 1), 4),
            "shortfall": dict(sorted(counter.items())),
            "vs_team_fouls": dict(team_rows[kind]),
        }
    return out


def _logloss(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    q = np.clip(p, 1e-4, 1 - 1e-4)
    out: np.ndarray = -(y * np.log(q) + (1 - y) * np.log(1 - q))
    return out


def _boot(diff: np.ndarray, ids: np.ndarray, reps: int = 1000) -> tuple[float, float]:
    uniq, inv = np.unique(ids, return_inverse=True)
    num = np.bincount(inv, weights=diff)
    den = np.bincount(inv).astype(np.float64)
    rng = np.random.default_rng(0)
    draws = rng.integers(0, len(uniq), size=(reps, len(uniq)))
    stats = num[draws].sum(axis=1) / den[draws].sum(axis=1)
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def fouls_drawn(db: Path, stage_dir: Path | None) -> dict[str, Any]:
    start: dict[int, int] = {}

    def hook(event: dict[str, Any], *_: Any) -> None:
        start[int(event["id"])] = int(event["startTimestamp"])

    rows, counts = cfc.build_player_rows(
        db, {METRIC: list(LINES)}, sample_n=10, min_sample=5, starts_only=True,
        on_sample=hook)
    over = [r for r in rows if r.direction == "OVER" and r.market == METRIC]
    p_nb, p_normal, y, ids, ts, lines = [], [], [], [], [], []
    for r in over:
        n = r.sample_size
        var = r.sample_sd * r.sample_sd
        sd = engine.sheet_predictive_sd(METRIC, "football", r.sample_mean, var, n,
                                        r.sample_mean)
        boundary = engine.winning_boundary(r.line, "OVER")
        normal = engine.calc_p_central_raw(r.sample_mean, sd, boundary, "OVER",
                                           engine.COUNT_SUPPORT_FLOOR)
        p_nb.append(r.p_central)
        p_normal.append(normal)
        y.append(1 if r.won else 0)
        ids.append(r.event_id)
        ts.append(start.get(r.event_id, 0))
        lines.append(r.line)
    pn, pb = np.array(p_normal), np.array(p_nb)
    ya, ia, ta, la = np.array(y), np.array(ids), np.array(ts), np.array(lines)
    both = (pn >= engine.P_FLOOR) & (pn <= engine.P_CEILING)
    diff = _logloss(pb, ya) - _logloss(pn, ya)
    lo, hi = _boot(diff[both], ia[both])
    by_line = {}
    for line in LINES:
        m = both & (la == line)
        if m.sum() >= 100:
            llo, lhi = _boot(diff[m], ia[m])
            by_line[str(line)] = {
                "n": int(m.sum()), "realised": round(float(ya[m].mean()), 4),
                "normal": round(float(pn[m].mean()), 4),
                "nb": round(float(pb[m].mean()), 4),
                "d_logloss": round(float(diff[m].mean()), 5),
                "ci95": [round(llo, 5), round(lhi, 5)]}
    fit_end, hold_end = _ts(HOLDOUT_FROM), _ts(HOLDOUT_TO) + 86400
    train = ta < fit_end
    hold = (ta >= fit_end) & (ta < hold_end)
    curve = gate_mod.fit_curve(zip(pb[train].tolist(), ya[train].tolist()))
    verdict = gate_mod.gate(curve, list(zip(pb[hold].tolist(), ya[hold].tolist(),
                                            ia[hold].tolist())))
    final_mask = ta < hold_end
    final = gate_mod.fit_curve(zip(pb[final_mask].tolist(), ya[final_mask].tolist()))
    gate_mod.require_final(verdict, final)
    out: dict[str, Any] = {
        "rows_over": len(over), "events": len(set(ids)),
        "first_day": datetime.fromtimestamp(min(ts), UTC).date().isoformat()
        if ts else None,
        "counts": {k: v for k, v in counts.items()},
        "nb_minus_normal_logloss": round(float(diff[both].mean()), 5),
        "ci95": [round(lo, 5), round(hi, 5)], "rows_compared": int(both.sum()),
        "by_line": by_line, "train_rows": int(train.sum()),
        "holdout_rows": int(hold.sum()), "gate": verdict, "final_curve": final,
    }
    if stage_dir is not None:
        _stage(stage_dir, final, verdict, over, start)
    return out


def _stage(stage_dir: Path, final: dict[str, Any], verdict: dict[str, Any],
           over: Sequence[cfc.SettledRow], start: dict[int, int]) -> None:
    group = stage_dir / GROUP
    group.mkdir(parents=True, exist_ok=True)
    key = f"{METRIC}|OVER"
    doc = {
        "target": "sofa_confidence_calibration.json", "group": GROUP,
        "fitted_from": {
            "holdout_from": HOLDOUT_FROM, "holdout_to": HOLDOUT_TO,
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "script": "scripts/sofa/measure_player_props_v2.py fouls-drawn",
            "replay": "calibrate_from_cache.build_player_rows starts_only, "
                      "engine NB (NEGATIVE_BINOMIAL_METRICS)",
            "final_curve_rows_before": "2026-10-14",
        },
        "by_market_direction": {key: final},
        "gate": {key: verdict},
    }
    (group / "curves.json").write_text(json.dumps(doc, indent=1, default=float) + "\n",
                                       encoding="utf-8")
    with gzip.open(group / "rows.csv.gz", "wt", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["event_id", "start_ts", "subject", "line", "p_central",
                         "actual", "outcome", "sample_size"])
        for r in over:
            writer.writerow([r.event_id, start.get(r.event_id, 0), r.subject, r.line,
                             r.p_central, r.actual, r.outcome, r.sample_size])
    (group / "gate_report.md").write_text(
        "\n".join(gate_mod.gate_lines(key, verdict)) + "\n", encoding="utf-8")


def _card_records(
    conn: sqlite3.Connection,
) -> Iterable[tuple[int, list[tuple[Any, ...]]]]:
    ids = [int(r[0]) for r in conn.execute(
        "SELECT sofascore_event_id FROM sofa_event_stats WHERE lineups_json IS NOT NULL"
        " AND length(lineups_json) > 10 AND incidents_json IS NOT NULL")]
    starts: dict[int, int] = {}
    for i in range(0, len(ids), 900):
        chunk = ids[i:i + 900]
        marks = ",".join("?" * len(chunk))
        for eid, ts, sport, raw in conn.execute(
                "SELECT event_id, start_ts, sport, event_json FROM sofa_listed_event"
                f" WHERE event_id IN ({marks})", chunk):
            if sport == "football" and (json.loads(raw).get("status") or {}).get(
                    "type") == "finished" and ts:
                starts[int(eid)] = int(ts)
    for eid in sorted(starts, key=lambda e: starts[e]):
        lj, ij = conn.execute(
            "SELECT lineups_json, incidents_json FROM sofa_event_stats "
            "WHERE sofascore_event_id = ?", (eid,)).fetchone()
        lineups = json.loads(lj)
        incidents = (json.loads(ij) or {}).get("incidents") or []
        cards = sorted((i for i in incidents if i.get("incidentType") == "card"
                        and not i.get("rescinded")),
                       key=lambda i: (i.get("time") or 0, i.get("addedTime") or 0))
        booked: set[Any] = set()
        red: set[Any] = set()
        for card in cards:
            pid = (card.get("player") or {}).get("id")
            booked.add(pid)
            if card.get("incidentClass") in ("red", "yellowRed"):
                red.add(pid)
        first = (cards[0].get("player") or {}).get("id") if cards else None
        players = []
        for side in ("home", "away"):
            for entry in (lineups.get(side) or {}).get("players") or []:
                stats = entry.get("statistics") or {}
                if entry.get("substitute") is not False or stats.get(
                        "minutesPlayed") is None:
                    continue
                pid = (entry.get("player") or {}).get("id")
                if pid is None:
                    continue
                players.append((pid, entry.get("position") or "?", pid in booked,
                                pid in red, pid == first))
        if len(players) >= 18:
            yield starts[eid], players


def cards(db: Path) -> dict[str, Any]:
    conn = _connect(db)
    history: dict[Any, collections.deque[tuple[bool, bool, bool]]] = (
        collections.defaultdict(lambda: collections.deque(maxlen=10)))
    by_position: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0, 0, 0])
    stats = {m: {"n": 0, "y": 0, "ge70": 0, "ge50": 0, "max_p": 0.0,
                 "ll_model": 0.0, "ll_base": 0.0, "sum_p": 0.0}
             for m in ("booked", "red", "first")}
    fit_from = _ts(FIT_FROM_CARDS)
    for ts, players in _card_records(conn):
        for pid, pos, *flags in players:
            past = history[pid]
            cell = by_position[pos]
            if ts >= fit_from and len(past) >= MIN_CARD_HISTORY and cell[0] > 1000:
                for i, name in enumerate(("booked", "red", "first")):
                    base = cell[i + 1] / cell[0]
                    k = sum(1 for h in past if h[i])
                    p = (k + K_CARDS * base) / (len(past) + K_CARDS)
                    y = 1 if flags[i] else 0
                    s = stats[name]
                    s["n"] += 1
                    s["y"] += y
                    s["sum_p"] += p
                    s["ge70"] += p >= 0.70
                    s["ge50"] += p >= 0.50
                    s["max_p"] = max(float(s["max_p"]), p)
                    pc = min(max(p, 1e-6), 1 - 1e-6)
                    bc = min(max(base, 1e-6), 1 - 1e-6)
                    s["ll_model"] -= y * math.log(pc) + (1 - y) * math.log(1 - pc)
                    s["ll_base"] -= y * math.log(bc) + (1 - y) * math.log(1 - bc)
        for pid, pos, *flags in players:
            history[pid].append((bool(flags[0]), bool(flags[1]), bool(flags[2])))
            cell = by_position[pos]
            cell[0] += 1
            for i in range(3):
                cell[i + 1] += bool(flags[i])
    conn.close()
    out: dict[str, Any] = {}
    for name, s in stats.items():
        n = max(int(s["n"]), 1)
        out[name] = {
            "starts": int(s["n"]), "realised": round(s["y"] / n, 4),
            "mean_p": round(s["sum_p"] / n, 4), "p_ge_0.70": int(s["ge70"]),
            "p_ge_0.50": int(s["ge50"]), "max_p": round(float(s["max_p"]), 4),
            "d_logloss_vs_position_rate": round(
                (s["ll_model"] - s["ll_base"]) / n, 5)}
    out["position_rates"] = {
        pos: {"starts": c[0], "booked": round(c[1] / max(c[0], 1), 4)}
        for pos, c in sorted(by_position.items())}
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--db-path", type=Path, default=Path("data/sofa.db"))
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("proof")
    fd = sub.add_parser("fouls-drawn")
    fd.add_argument("--stage-dir", type=Path, default=None)
    sub.add_parser("cards")
    args = parser.parse_args(argv)
    if args.cmd == "proof":
        result = proof(args.db_path)
    elif args.cmd == "fouls-drawn":
        result = fouls_drawn(args.db_path, args.stage_dir)
    else:
        result = cards(args.db_path)
    json.dump(result, sys.stdout, indent=1, default=float)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
