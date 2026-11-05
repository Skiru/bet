#!/usr/bin/env python3
"""Measure the bottom-up tennis model (bet.sofa.tennis_point_model) -
read-only. Report: docs/sofa/evidence/tennis_point_model_2026-11-05.md
(rules pre-registered in its section 0 before the first run).

Two measurements:

  * ``history``: walk-forward on the Sofascore history - the model forecasts
    each match from the matches before it; scored on the current
    estimator's history replay rows (``sofa_settled_row``, run_date
    ``cache-calibration``) at one market-like line per (match, market): the
    line whose replayed p is closest to 0.5. Totals only (the replay's
    per-player rows name the player, the history carries ids).
  * ``superbet``: every settled REAL Superbet line (live ``sofa_settled_row``
    rows, both sides priced) - new model vs current p_central vs the
    de-vigged price; days split 2/3 development, 1/3 hold-out; the hold-out
    is computed only with ``--holdout``.

Nothing is written but ``--out-dir``. Never the network.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_point_model.py \\
        --out-dir data/refit_2026-11-05_tennis_point_model [--holdout] \\
        [--history-cache <pickle>] [--replay-cache <sqlite>]
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import random
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

for _p in ("src", "."):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.tennis_point_model import (  # noqa: E402
    MARKETS,
    PointMatch,
    load_point_history,
    market_sim,
    walk_forward,
)

_REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB = _REPO / "data" / "sofa.db"
DEFAULT_RUNS = _REPO / "runs" / "sofa"

# Pre-registered (report section 0).
NONINFERIORITY_BRIER = 0.002
NONINFERIORITY_LOGLOSS = 0.005
MIN_CONF = 0.70
MIN_X = 0.90
OVERROUND = (1.0, 1.30)
BOOT = 2000
LIVE_FROM = "2026-09-18"
HIST_FROM = "2026-01-01"
HIST_TO = "2026-09-17"
HIST_MARKETS = ("games_total", "sets_total", "games_set1_total",
                "games_set2_total", "aces_total", "double_faults_total")

FAMILIES: dict[str, str] = {
    "games_total": "games_total",
    "sets_total": "sets_total",
    "games_set1_total": "set_games",
    "games_set2_total": "set_games",
    "games_won_for": "games_won_for",
    "aces_for": "aces", "aces_total": "aces",
    "double_faults_for": "double_faults", "double_faults_total": "double_faults",
    "serve_points_for": "serve_points", "serve_points_total": "serve_points",
}
for _m in MARKETS:
    if "_set" in _m and _m.split("_set")[0] in (
            "aces", "double_faults", "serve_points"):
        FAMILIES[_m] = "serve_per_set"
FAMILY_ORDER = ("games_total", "sets_total", "set_games", "games_won_for", "aces",
                "double_faults", "serve_points", "serve_per_set")


@dataclass(frozen=True)
class Line:
    """One Superbet line, OVER side carrying the pair."""

    day: str
    eid: int
    market: str
    subject: str
    line: float
    y: int  # 1 = OVER won
    p_cur: float  # current SHEET p_central of OVER
    odds_over: float
    odds_under: float
    side: int | None = None  # fixture orientation: 0 home / 1 away
    p_new: float | None = None

    @property
    def family(self) -> str:
        return FAMILIES[self.market]

    @property
    def p_price(self) -> float:
        io, iu = 1.0 / self.odds_over, 1.0 / self.odds_under
        return io / (io + iu)


def fold(text: str | None) -> str:
    raw = unicodedata.normalize("NFKD", text or "")
    raw = "".join(c for c in raw if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", raw).split())


def side_of(subject: str, home: str, away: str) -> int | None:
    """0 / 1 when the subject names exactly one of the two players."""
    s, h, a = fold(subject), fold(home), fold(away)
    if not s:
        return None
    if s == h and s != a:
        return 0
    if s == a and s != h:
        return 1
    st = set(s.split())
    ht, at = set(h.split()), set(a.split())
    hs, as_ = len(st & ht), len(st & at)
    if hs > as_ and hs > 0:
        return 0
    if as_ > hs and as_ > 0:
        return 1
    return None


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def load_lines(db: Path) -> tuple[list[Line], dict[str, int]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    marks = ",".join("?" * len(FAMILIES))
    rows = conn.execute(
        "SELECT run_date, sofascore_event_id, market, subject, line, direction, "
        "p_central, offered_odds, outcome FROM sofa_settled_row "
        f"WHERE run_date >= ? AND run_date < 'c' AND sport = 'tennis' "
        f"AND market IN ({marks}) AND outcome IN ('WIN', 'LOSS')",
        (LIVE_FROM, *FAMILIES),
    ).fetchall()
    conn.close()
    pairs: dict[tuple[int, str, str, float], dict[str, Any]] = defaultdict(dict)
    for day, eid, market, subject, line, direction, p, odds, outcome in rows:
        pairs[(int(eid), market, subject, float(line))][direction] = (
            day, p, odds, outcome)
    out: list[Line] = []
    drop: dict[str, int] = defaultdict(int)
    for (eid, market, subject, line), d in pairs.items():
        if "OVER" not in d or "UNDER" not in d:
            drop["one_side"] += 1
            continue
        day, p, oo, outcome = d["OVER"]
        ou = d["UNDER"][2]
        if not oo or not ou or oo <= 1.0 or ou <= 1.0:
            drop["no_price"] += 1
            continue
        over_round = 1.0 / oo + 1.0 / ou
        if not OVERROUND[0] <= over_round <= OVERROUND[1]:
            drop["overround"] += 1
            continue
        out.append(Line(day=str(day), eid=eid, market=market, subject=subject,
                        line=line, y=1 if outcome == "WIN" else 0,
                        p_cur=float(p), odds_over=float(oo), odds_under=float(ou)))
    return out, dict(drop)


def load_fixtures(runs: Path) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for path in sorted(runs.glob("2026-*/02_fixtures.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        fixtures = doc if isinstance(doc, list) else doc.get("fixtures", [])
        for f in fixtures:
            if f.get("sport") == "tennis" and f.get("sofascore_event_id"):
                out[int(f["sofascore_event_id"])] = f
    return out


def load_history(args: argparse.Namespace) -> list[PointMatch]:
    cache = Path(args.history_cache) if args.history_cache else None
    if cache and cache.exists():
        with cache.open("rb") as fh:
            data: list[PointMatch] = pickle.load(fh)
        return data
    history = load_point_history(args.db)
    if cache:
        with cache.open("wb") as fh:
            pickle.dump(history, fh)
    return history


def load_replay(args: argparse.Namespace) -> list[tuple[int, str, float, float]]:
    """(event, market, line, p_central OVER) of the replay's total rows."""
    if args.replay_cache:
        conn = sqlite3.connect(f"file:{args.replay_cache}?mode=ro", uri=True)
        q = "SELECT eid, market, line, p FROM r WHERE subject = '' AND market IN (%s)"
    else:
        conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
        q = ("SELECT sofascore_event_id, market, line, p_central FROM sofa_settled_row "
             "WHERE run_date = 'cache-calibration' AND sport = 'tennis' "
             "AND direction = 'OVER' AND subject = '' AND market IN (%s)")
    marks = ",".join("?" * len(HIST_MARKETS))
    rows = [(int(e), str(m), float(li), float(p))
            for e, m, li, p in conn.execute(q % marks, HIST_MARKETS)]
    conn.close()
    return rows


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


def brier(p: float, y: int) -> float:
    return (p - y) ** 2


def logloss(p: float, y: int) -> float:
    p = min(max(p, 1e-4), 1.0 - 1e-4)
    return -math.log(p if y else 1.0 - p)


def boot_mean(groups: Sequence[str | int], values: Sequence[float],
              seed: int = 1) -> tuple[float, float, float]:
    """Mean of values with a 95% interval resampling whole groups."""
    by: dict[str | int, list[float]] = defaultdict(list)
    for g, v in zip(groups, values, strict=True):
        by[g].append(v)
    keys = list(by)
    sums = np.array([sum(by[k]) for k in keys])
    ns = np.array([len(by[k]) for k in keys], dtype=np.float64)
    if not keys:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), (BOOT, len(keys)))
    means = sums[idx].sum(axis=1) / ns[idx].sum(axis=1)
    point = float(sums.sum() / ns.sum())
    return point, float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def fmt(t: tuple[float, float, float], digits: int = 4) -> str:
    p, lo, hi = t
    return f"{p:+.{digits}f} [{lo:+.{digits}f}, {hi:+.{digits}f}]"


def _diff(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [x - y for x, y in zip(a, b, strict=True)]


def scores(lines: Sequence[Line]) -> dict[str, Any]:
    """Brier / log-loss of new, current and price on OVER rows with match
    intervals on the differences."""
    g = [ln.eid for ln in lines]
    out: dict[str, Any] = {"n_lines": len(lines), "n_matches": len(set(g))}
    if not lines:
        return out
    for name, f in (("brier", brier), ("logloss", logloss)):
        new = [f(ln.p_new or 0.0, ln.y) for ln in lines]
        cur = [f(ln.p_cur, ln.y) for ln in lines]
        prc = [f(ln.p_price, ln.y) for ln in lines]
        out[name] = {
            "new": sum(new) / len(new), "current": sum(cur) / len(cur),
            "price": sum(prc) / len(prc),
            "new_minus_price": boot_mean(g, _diff(new, prc)),
            "new_minus_current": boot_mean(g, _diff(new, cur)),
            "current_minus_price": boot_mean(g, _diff(cur, prc)),
        }
    return out


@dataclass(frozen=True)
class Leg:
    eid: int
    p: float
    odds: float
    y: int
    p_price: float


def legs(lines: Iterable[Line], which: Callable[[Line], float]) -> list[Leg]:
    """Both directions of every line as a leg with the given p of OVER."""
    out: list[Leg] = []
    for ln in lines:
        p = which(ln)
        out.append(Leg(ln.eid, p, ln.odds_over, ln.y, ln.p_price))
        out.append(Leg(ln.eid, 1.0 - p, ln.odds_under, 1 - ln.y, 1.0 - ln.p_price))
    return out


def calibration(lg: Sequence[Leg]) -> list[dict[str, Any]]:
    rows = []
    for lo in [i / 10 for i in range(10)]:
        hi = lo + 0.1
        cell = [x for x in lg if lo <= x.p < hi or (hi >= 1.0 and x.p == 1.0)]
        if not cell:
            continue
        y = boot_mean([x.eid for x in cell], [float(x.y) for x in cell])
        rows.append({"bucket": f"{lo:.1f}-{hi:.1f}", "n": len(cell),
                     "matches": len({x.eid for x in cell}),
                     "claimed": sum(x.p for x in cell) / len(cell),
                     "realised": y,
                     "price_nv": sum(x.p_price for x in cell) / len(cell)})
    return rows


def high_legs(lg: Sequence[Leg], gate_x: bool) -> dict[str, Any]:
    cell = [x for x in lg if x.p >= MIN_CONF and (not gate_x or x.p * x.odds >= MIN_X)]
    if not cell:
        return {"n": 0}
    g = [x.eid for x in cell]
    return {
        "n": len(cell), "matches": len(set(g)),
        "claimed": sum(x.p for x in cell) / len(cell),
        "realised": boot_mean(g, [float(x.y) for x in cell]),
        "gap": boot_mean(g, [x.y - x.p for x in cell]),
        "price_nv": sum(x.p_price for x in cell) / len(cell),
        "roi": boot_mean(g, [(x.odds - 1.0) if x.y else -1.0 for x in cell]),
    }


# --------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------


def orient(match: PointMatch, fixture: dict[str, Any] | None) -> bool | None:
    """True when the fixture's home is the history's away (sides swapped)."""
    if fixture is None:
        return False
    hid, aid = fixture.get("home_entity_id"), fixture.get("away_entity_id")
    if hid == match.home_id and aid == match.away_id:
        return False
    if hid == match.away_id and aid == match.home_id:
        return True
    return None


def price_lines(lines: list[Line], history: list[PointMatch],
                fixtures: dict[int, dict[str, Any]], sims: int,
                drops: dict[str, int]) -> list[Line]:
    by_id = {m.event_id: m for m in history}
    wanted = {ln.eid for ln in lines}
    forecasts = walk_forward(history, wanted)
    by_event: dict[int, list[Line]] = defaultdict(list)
    for ln in lines:
        by_event[ln.eid].append(ln)
    out: list[Line] = []
    for eid, group in sorted(by_event.items()):
        m = by_id.get(eid)
        if m is None or eid not in forecasts:
            drops["not_in_history"] = drops.get("not_in_history", 0) + len(group)
            continue
        if not m.completed or m.best_of == 5:
            drops["retired_or_bo5"] = drops.get("retired_or_bo5", 0) + len(group)
            continue
        fx = fixtures.get(eid)
        swap = orient(m, fx)
        if swap is None:
            drops["sides_disagree"] = drops.get("sides_disagree", 0) + len(group)
            continue
        ms = market_sim(forecasts[eid], n=sims, seed=eid % (2 ** 31))
        for ln in group:
            side: int | None = None
            if ln.market.endswith("_for"):
                if fx is None:
                    drops["no_fixture"] = drops.get("no_fixture", 0) + 1
                    continue
                side = side_of(ln.subject, str(fx.get("home_name") or ""),
                               str(fx.get("away_name") or ""))
                if side is None:
                    drops["subject_unmapped"] = drops.get("subject_unmapped", 0) + 1
                    continue
            hist_side = None if side is None else (1 - side if swap else side)
            p = ms.p_over(ln.market, hist_side, ln.line)
            if p is None:
                drops["not_priced"] = drops.get("not_priced", 0) + 1
                continue
            out.append(replace(ln, side=side, p_new=p))
    return out


def split_days(lines: Sequence[Line]) -> tuple[set[str], set[str]]:
    days = sorted({ln.day for ln in lines})
    cut = math.ceil(len(days) * 2 / 3)
    return set(days[:cut]), set(days[cut:])


def family_report(lines: Sequence[Line]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for fam in FAMILY_ORDER + ("all",):
        sel = [ln for ln in lines if fam == "all" or ln.family == fam]
        if not sel:
            continue
        new_legs = legs(sel, lambda ln: ln.p_new or 0.0)
        cur_legs = legs(sel, lambda ln: ln.p_cur)
        out[fam] = {
            "scores": scores(sel),
            "calibration_new": calibration(new_legs),
            "calibration_current": calibration(cur_legs),
            "high_new": high_legs(new_legs, gate_x=False),
            "high_new_x": high_legs(new_legs, gate_x=True),
            "high_current": high_legs(cur_legs, gate_x=False),
            "days": [min(ln.day for ln in sel), max(ln.day for ln in sel)],
        }
    return out


def verdicts(rep: dict[str, Any]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for fam, r in rep.items():
        s = r["scores"]
        if "brier" not in s:
            continue
        _, _, hi_p = s["brier"]["new_minus_price"]
        _, _, hi_c = s["brier"]["new_minus_current"]
        h = r["high_new"]
        if h.get("n", 0) < 30:
            cal = "za mało nóg"
        else:
            _, lo, hi = h["realised"]
            cal = "tak" if lo <= h["claimed"] <= hi else "nie"
        out[fam] = {
            "as_good_as_price": "tak" if hi_p <= NONINFERIORITY_BRIER else "nie",
            "better_than_current": "tak" if hi_c < 0 else "nie",
            "calibrated_at_070": cal,
        }
    return out


def run_superbet(args: argparse.Namespace, history: list[PointMatch]) -> dict[str, Any]:
    lines, drops = load_lines(args.db)
    fixtures = load_fixtures(args.runs_dir)
    dev_days, hold_days = split_days(lines)
    use = dev_days | hold_days if args.holdout else dev_days
    priced = price_lines([ln for ln in lines if ln.day in use], history, fixtures,
                         args.sims, drops)
    dev = [ln for ln in priced if ln.day in dev_days]
    hold = [ln for ln in priced if ln.day in hold_days]
    out: dict[str, Any] = {
        "lines_loaded": len(lines), "drops": drops,
        "dev_days": [min(dev_days), max(dev_days)],
        "holdout_days": [min(hold_days), max(hold_days)] if hold_days else None,
        "dev": family_report(dev),
    }
    out["dev_verdicts"] = verdicts(out["dev"])
    if args.holdout:
        out["holdout"] = family_report(hold)
        out["holdout_verdicts"] = verdicts(out["holdout"])
    with (args.out_dir / "superbet_lines.jsonl").open("w", encoding="utf-8") as fh:
        for ln in (priced if args.holdout else dev):
            fh.write(json.dumps({**ln.__dict__, "p_price": ln.p_price,
                                 "family": ln.family}) + "\n")
    return out


def run_history(args: argparse.Namespace, history: list[PointMatch]) -> dict[str, Any]:
    lo = int(datetime.fromisoformat(HIST_FROM).replace(tzinfo=UTC).timestamp())
    hi = int(datetime.fromisoformat(HIST_TO).replace(tzinfo=UTC).timestamp()) + 86400
    by_id = {m.event_id: m for m in history}
    rows = load_replay(args)
    chosen: dict[tuple[int, str], tuple[float, float]] = {}
    for eid, market, line, p in rows:
        m = by_id.get(eid)
        if m is None or not lo <= m.ts < hi or not m.completed or m.best_of != 3:
            continue
        key = (eid, market)
        if key not in chosen or abs(p - 0.5) < abs(chosen[key][1] - 0.5):
            chosen[key] = (line, p)
    events = sorted({e for e, _ in chosen})
    if args.hist_max_matches and len(events) > args.hist_max_matches:
        events = sorted(random.Random(5).sample(events, args.hist_max_matches))
    forecasts = walk_forward(history, set(events))
    lines: list[Line] = []
    for eid in events:
        m = by_id[eid]
        ms = market_sim(forecasts[eid], n=args.sims, seed=eid % (2 ** 31))
        actual = _actuals(m)
        for market in HIST_MARKETS:
            if (eid, market) not in chosen or actual.get(market) is None:
                continue
            line, p_cur = chosen[(eid, market)]
            p_new = ms.p_over(market, None, line)
            if p_new is None:
                continue
            value = actual[market]
            assert value is not None
            day = datetime.fromtimestamp(m.ts, UTC).strftime("%Y-%m-%d")
            lines.append(Line(day=day, eid=eid, market=market, subject="", line=line,
                              y=int(value > line), p_cur=p_cur, odds_over=2.0,
                              odds_under=2.0, p_new=p_new))
    out: dict[str, Any] = {"events": len(events), "lines": len(lines)}
    for market in HIST_MARKETS + ("all",):
        sel = [ln for ln in lines if market == "all" or ln.market == market]
        if not sel:
            continue
        sc = scores(sel)
        for k in ("brier", "logloss"):
            sc[k].pop("new_minus_price", None)
            sc[k].pop("current_minus_price", None)
            sc[k].pop("price", None)
        out[market] = {
            "scores": sc,
            "calibration_new": calibration(legs(sel, lambda ln: ln.p_new or 0.0)),
            "calibration_current": calibration(legs(sel, lambda ln: ln.p_cur)),
            "high_new": high_legs(legs(sel, lambda ln: ln.p_new or 0.0), gate_x=False),
            "high_current": high_legs(legs(sel, lambda ln: ln.p_cur), gate_x=False),
        }
    return out


def _actuals(m: PointMatch) -> dict[str, float | None]:
    games = sum(a + b for a, b in m.sets)
    aces = (None if m.home is None or m.away is None or m.home.aces is None
            or m.away.aces is None else float(m.home.aces + m.away.aces))
    dfs = (None if m.home is None or m.away is None or m.home.dfs is None
           or m.away.dfs is None else float(m.home.dfs + m.away.dfs))
    return {
        "games_total": float(games), "sets_total": float(len(m.sets)),
        "games_set1_total": float(sum(m.sets[0])),
        "games_set2_total": float(sum(m.sets[1])) if len(m.sets) > 1 else None,
        "aces_total": aces, "double_faults_total": dfs,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--history-cache", default=None)
    ap.add_argument("--replay-cache", default=None)
    ap.add_argument("--stage", choices=("history", "superbet", "all"), default="all")
    ap.add_argument("--holdout", action="store_true",
                    help="also score the hold-out days (once)")
    ap.add_argument("--sims", type=int, default=4000)
    ap.add_argument("--hist-max-matches", type=int, default=15000)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    history = load_history(args)
    print(f"history: {len(history)} matches, "
          f"{sum(1 for m in history if m.home is not None)} with serve counts",
          flush=True)
    if args.stage in ("superbet", "all"):
        res = run_superbet(args, history)
        name = "superbet_holdout.json" if args.holdout else "superbet_dev.json"
        (args.out_dir / name).write_text(json.dumps(res, indent=1), encoding="utf-8")
        key = "holdout_verdicts" if args.holdout else "dev_verdicts"
        print(json.dumps(res.get(key), indent=1), flush=True)
    if args.stage in ("history", "all"):
        res = run_history(args, history)
        (args.out_dir / "history.json").write_text(json.dumps(res, indent=1),
                                                   encoding="utf-8")
        print("history done", res.get("events"), res.get("lines"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
