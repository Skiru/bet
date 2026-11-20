#!/usr/bin/env python3
"""Where does a printed leg's confidence beat Superbet's de-vigged price out of
sample? Edge (win - fair p at the taken price) and CLV (taken price x de-vigged
closing probability - 1) per cell (sport x market|DIR x competition x band of
confidence - 1/odds x hours from print to start), dev 10-13..11-09, hold-out
11-10..11-19, match bootstrap, Bonferroni over the hold-out candidates.

The frozen rules are docs/sofa/evidence/przewaga_nad_cena_2026-11-20/PROTOCOL.md;
the script refuses to run when that file's sha256 differs from PROTOCOL_SHA256.
Read-only: day files only (13_results / 11_coupon / 08_confidence* /
closing.jsonl / the sports' settled.json and snapshots.jsonl), never the DB.
An analysis tool; it writes nothing the pipeline reads.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_price_edge.py \\
        --out-dir docs/sofa/evidence/przewaga_nad_cena_2026-11-20
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from bet.sofa.clv import group_close, is_close, two_way_close
from bet.sofa.coupon_results import key_of
from bet.sofa.engine import devig

REPO = Path(__file__).resolve().parents[2]
PROTOCOL = REPO / "docs/sofa/evidence/przewaga_nad_cena_2026-11-20/PROTOCOL.md"
PROTOCOL_SHA256 = "264e4521b97ea111a0832a8d72c55a6cb75baedd3082587f30df2e4b2277c954"

DEV = ("2026-10-13", "2026-11-09")
HOLD = ("2026-11-10", "2026-11-19")
MIN_N = 300
ALPHA = 0.05
B_SCAN = 2000
B_HOLD = 20000
SEED = 20261120
BH_Q = 0.10

BAND_EDGES = (-0.05, -0.02, 0.0, 0.03, 0.06)
BAND_LABELS = ("<-0.05", "-0.05..-0.02", "-0.02..0", "0..0.03", "0.03..0.06", ">=0.06")
TTS_EDGES = (1.0, 3.0, 6.0, 12.0)
TTS_LABELS = ("<1", "1-3", "3-6", "6-12", ">=12")
MEASURED = ("hockey", "basketball", "volleyball", "cs2")
SPORT_SUB = {
    "cs2": "cs2",
    "hockey": "shadow/hockey",
    "basketball": "shadow/basketball",
    "volleyball": "shadow/volleyball",
}
CS2_KEY = ("superbet_event_id", "family", "map_nr", "subject", "line", "side")
SHADOW_KEY = ("superbet_event_id", "market_id", "period", "subject", "line", "side")

FAMILIES: dict[str, tuple[str, ...]] = {
    "F1": ("sport",),
    "F2": ("sport", "md"),
    "F3": ("sport", "comp"),
    "F4": ("sport", "band"),
    "F5": ("sport", "tts"),
    "F6": ("sport", "md", "band"),
    "F7": ("sport", "md", "tts"),
    "F8": ("sport", "comp", "band"),
    "F9": ("sport", "over"),
    "F10": ("sport", "md", "over"),
    "F11": ("sport", "comp", "over"),
}


# ---------------------------------------------------------------- pure parts


def days(a: str, b: str) -> list[str]:
    d0 = datetime.strptime(a, "%Y-%m-%d")
    d1 = datetime.strptime(b, "%Y-%m-%d")
    return [
        (d0 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((d1 - d0).days + 1)
    ]


def split_of(day: str) -> str | None:
    if DEV[0] <= day <= DEV[1]:
        return "dev"
    if HOLD[0] <= day <= HOLD[1]:
        return "hold"
    return None


def band(d: float) -> str:
    for edge, label in zip(BAND_EDGES, BAND_LABELS, strict=False):
        if d < edge:
            return label
    return BAND_LABELS[-1]


def tts_bucket(hours: float | None) -> str | None:
    if hours is None:
        return None
    for edge, label in zip(TTS_EDGES, TTS_LABELS, strict=False):
        if hours < edge:
            return label
    return TTS_LABELS[-1]


def _utc(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def hours_to_start(printed_at: Any, kickoff: Any) -> float | None:
    p, k = _utc(printed_at), _utc(kickoff)
    if p is None or k is None:
        return None
    return (k - p).total_seconds() / 3600.0


def fair_football(market_p: Any, offered_odds: Any, odds: float) -> float | None:
    """market_p (power de-vig over the ladder at offered_odds) moved to the
    taken price: the fair / implied ratio is kept."""
    try:
        mp, off = float(market_p), float(offered_odds)
    except (TypeError, ValueError):
        return None
    if not (0 < mp < 1) or off <= 1 or odds <= 1:
        return None
    p = mp * off / odds
    return p if 0 < p < 1 else None


def fair_two_way(odds: float, overround: Any) -> float | None:
    """Power de-vig of the pair rebuilt from the leg's overround (two-way only)."""
    try:
        ov = float(overround)
    except (TypeError, ValueError):
        return None
    if odds <= 1:
        return None
    other_implied = 1.0 + ov - 1.0 / odds
    if other_implied <= 0 or other_implied >= 1:
        return None
    pair = devig(odds, 1.0 / other_implied)
    return None if pair is None else pair[0]


def cell_key(leg: dict[str, Any], dims: Sequence[str]) -> tuple[Any, ...] | None:
    vals = []
    for d in dims:
        v = leg.get(d)
        if v is None:
            return None
        vals.append(v)
    return (leg["priced"], *vals)


def bootstrap(
    values: Sequence[float], clusters: Sequence[Any], b: int, rng: np.random.Generator
) -> np.ndarray:
    """Leg-weighted mean of `values` over `b` resamples of whole clusters."""
    sums: dict[Any, float] = defaultdict(float)
    cnts: dict[Any, int] = defaultdict(int)
    for v, c in zip(values, clusters, strict=True):
        sums[c] += v
        cnts[c] += 1
    keys = list(sums)
    s = np.array([sums[k] for k in keys])
    n = np.array([cnts[k] for k in keys], dtype=float)
    m = len(keys)
    out = np.empty(b)
    chunk = max(1, 2_000_000 // max(m, 1))
    i = 0
    while i < b:
        j = min(b, i + chunk)
        idx = rng.integers(0, m, size=(j - i, m))
        out[i:j] = s[idx].sum(axis=1) / n[idx].sum(axis=1)
        i = j
    return out


def interval(boot: np.ndarray, level: float) -> tuple[float, float]:
    tail = (1.0 - level) / 2.0
    return float(np.quantile(boot, tail)), float(np.quantile(boot, 1.0 - tail))


def bh(pvals: Sequence[float], q: float) -> list[bool]:
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    cut = 0
    for rank, i in enumerate(order, 1):
        if pvals[i] <= q * rank / m:
            cut = rank
    passed = [False] * m
    for rank, i in enumerate(order, 1):
        passed[i] = rank <= cut
    return passed


# ---------------------------------------------------------------- loading


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _sport_graded(runs: Path, sport: str, day: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    d1 = (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    for d in (day, d1):
        doc = _json(runs / SPORT_SUB[sport] / d / "settled.json")
        if not doc:
            continue
        ev = doc.get("events", {})
        for e in ev.values() if isinstance(ev, dict) else ev:
            if isinstance(e, dict):
                out += [g for g in e.get("graded", []) if isinstance(g, dict)]
    return out


def _skey(sport: str, x: dict[str, Any]) -> tuple[Any, ...]:
    fields = CS2_KEY if sport == "cs2" else SHADOW_KEY
    vals: list[Any] = []
    for f in fields:
        v = x.get(f)
        if f == "line":
            v = None if v is None else float(v)
        elif f in ("market_id", "period", "map_nr"):
            v = int(v or 0)
        elif f in ("superbet_event_id", "subject", "family", "side"):
            v = str(v or "")
        vals.append(v)
    return tuple(vals)


def _first_snapshots(
    runs: Path, sport: str, day: str, wanted: set[tuple[Any, ...]]
) -> dict[tuple[Any, ...], tuple[str, float]]:
    """First snapshot (fetch time, odds) of each wanted line - the loop's
    earliest view, not Superbet's true opening."""
    first: dict[tuple[Any, ...], tuple[str, float]] = {}
    d1 = (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    wanted_events = {k[0] for k in wanted}
    for d in (day, d1):
        path = runs / SPORT_SUB[sport] / d / "snapshots.jsonl"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as fh:
            for raw in fh:
                if not any(f'"{e}"' in raw[:400] for e in wanted_events):
                    continue
                try:
                    snap = json.loads(raw)
                except ValueError:
                    continue
                ts = str(snap.get("fetched_at_utc") or "")
                for ln in snap.get("lines") or []:
                    if sport == "cs2":
                        ln = {
                            **ln,
                            "superbet_event_id": ln.get("superbet_event_id")
                            or snap.get("superbet_event_id"),
                        }
                    k = _skey(sport, ln)
                    if k not in wanted or ln.get("odds") is None:
                        continue
                    if k not in first or ts < first[k][0]:
                        first[k] = (ts, float(ln["odds"]))
    return first


def _football_closes(runs: Path, day: str) -> dict[str, dict[str, Any]]:
    """leg_key -> the latest priced close record (audit_clv.closing_rows)."""
    path = runs / day / "closing.jsonl"
    latest: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return latest
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if rec.get("variant") != "official" or not is_close(rec.get("minutes_before")):
            continue
        k = rec["leg_key"]
        rank = (not rec.get("missing") and not rec.get("error"), rec["fetched_at_utc"])
        held = latest.get(k)
        if held is None or rank > (
            not held.get("missing") and not held.get("error"),
            held["fetched_at_utc"],
        ):
            latest[k] = rec
    return latest


def closing_leg_key(leg: dict[str, Any]) -> str:
    """capture_closing.leg_key's format."""
    return (
        f"{leg.get('sofascore_event_id')}|{leg.get('market')}"
        f"|{leg.get('subject') or ''}|{leg.get('line')}|{leg.get('direction')}"
    )


def ts_of_print_file(name: str) -> str | None:
    """printed/20261020T063446.785577Z.json -> ISO UTC."""
    try:
        t = datetime.strptime(name.split(".")[0], "%Y%m%dT%H%M%S")
    except ValueError:
        return None
    return t.replace(tzinfo=UTC).isoformat()


def first_prints(runs: Path, day: str) -> dict[str, str]:
    """key_of(leg) -> time of the earliest printed/<ts>.json holding it."""
    out: dict[str, str] = {}
    folder = runs / day / "printed"
    if not folder.is_dir():
        return out
    for path in sorted(folder.glob("*.json")):
        ts = ts_of_print_file(path.name)
        doc = _json(path)
        if ts is None or not isinstance(doc, dict):
            continue
        for leg in doc.get("singles") or []:
            try:
                k = key_of(leg)
            except (KeyError, TypeError, ValueError):
                continue
            out.setdefault(k, ts)
    return out


def load_day(runs: Path, day: str, stats: dict[str, Any]) -> list[dict[str, Any]]:
    res = _json(runs / day / "13_results.json")
    if not res:
        return []
    results: dict[str, Any] = res.get("legs") or {}
    coupon = _json(runs / day / "11_coupon.json")
    if coupon:
        src = list(coupon.get("singles") or [])
        stats["days_with_11_coupon"].append(day)
    else:
        conf = _json(runs / day / "08_confidence.json") or {}
        sp = _json(runs / day / "08_confidence_sports.json") or {}
        src = list(conf.get("legs") or []) + list(sp.get("legs") or [])
        stats["days_without_11_coupon"].append(day)
    by_key = {}
    for leg in src:
        try:
            by_key[key_of(leg)] = leg
        except (KeyError, TypeError, ValueError):
            continue
    closes = _football_closes(runs, day)
    prints = first_prints(runs, day)
    graded: dict[str, dict[tuple[Any, ...], dict[str, Any]]] = {}
    for s in MEASURED:
        graded[s] = {_skey(s, g): g for g in _sport_graded(runs, s, day)}
    out: list[dict[str, Any]] = []
    sport_legs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for k, r in results.items():
        st = r.get("status")
        sport = str(r.get("sport") or "football")
        stats["results_status"][f"{sport}:{st}"] += 1
        if st not in ("won", "lost"):
            continue
        leg = by_key.get(k)
        if leg is None:
            stats["no_leg_fields"][sport] += 1
            continue
        odds = float(r.get("odds") or leg.get("odds") or leg.get("offered_odds") or 0)
        conf = r.get("confidence", leg.get("confidence"))
        if odds <= 1 or conf is None:
            stats["no_odds_or_conf"][sport] += 1
            continue
        conf = float(conf)
        row: dict[str, Any] = {
            "day": day,
            "split": split_of(day),
            "sport": sport,
            "eid": int(leg.get("sofascore_event_id") or 0),
            "kickoff": str(leg.get("kickoff_utc") or ""),
            "comp": str(leg.get("competition") or "?"),
            "conf": conf,
            "odds": odds,
            "win": 1 if st == "won" else 0,
            "band": band(conf - 1.0 / odds),
            "tts_h": hours_to_start(
                prints.get(k) or leg.get("printed_at_utc"), leg.get("kickoff_utc")
            ),
        }
        row["tts"] = tts_bucket(row["tts_h"])
        fair: float | None = None
        if sport in MEASURED:
            fam = leg.get("family") or leg.get("market")
            row["md"] = f"{fam}|{leg.get('side') or leg.get('direction')}"
            g = graded[sport].get(_skey(sport, leg))
            group = g.get("group_odds") if g else None
            multi = isinstance(group, dict) and len(group) > 2
            if g is not None and not multi:
                fair = fair_two_way(odds, leg.get("overround"))
            if g is not None:
                minutes = g.get("minutes_before_kickoff")
                if (
                    minutes is None
                    and g.get("fetched_at_utc")
                    and leg.get("kickoff_utc")
                ):
                    a, b = _utc(leg["kickoff_utc"]), _utc(g["fetched_at_utc"])
                    minutes = (
                        None if a is None or b is None else (a - b).total_seconds() / 60
                    )
                if is_close(minutes):
                    if multi and isinstance(group, dict):
                        p = group_close(
                            {str(x): float(y) for x, y in group.items()}, str(g["side"])
                        )
                    else:
                        p = two_way_close(g.get("odds"), g.get("partner_odds"))
                    if p is not None and math.isfinite(p):
                        row["clv"] = odds * p - 1.0
                        row["close_odds"] = float(g["odds"])
            sport_legs[sport].append(row)
            row["_skey"] = _skey(sport, leg)
        else:
            row["md"] = f"{leg.get('market')}|{leg.get('direction')}"
            if leg.get("market_p") is not None:
                fair = fair_football(leg.get("market_p"), leg.get("offered_odds"), odds)
            rec = closes.get(closing_leg_key(leg))
            if rec is not None:
                p = two_way_close(rec.get("odds_close"), rec.get("partner_close"))
                if rec.get("odds_close"):
                    row["close_odds"] = float(rec["odds_close"])
                if p is not None and math.isfinite(p):
                    row["clv"] = odds * p - 1.0
        row["fair_p"] = fair
        row["priced"] = "fair" if fair is not None else "raw"
        row["edge"] = row["win"] - (fair if fair is not None else 1.0 / odds)
        row["roi"] = odds * row["win"] - 1.0
        row["over"] = None if fair is None else ("tak" if conf > fair else "nie")
        out.append(row)
    for sport, rows in sport_legs.items():
        wanted = {r["_skey"] for r in rows}
        first = _first_snapshots(runs, sport, day, wanted)
        for r in rows:
            f = first.get(r["_skey"])
            if f is not None:
                r["open_odds"] = f[1]
                r["open_ts"] = f[0]
    for r in out:
        r.pop("_skey", None)
    return out


# ---------------------------------------------------------------- cells


def summarize(rows: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    vals = [r[metric] for r in rows if r.get(metric) is not None]
    sub = [r for r in rows if r.get(metric) is not None]
    n = len(vals)
    out: dict[str, Any] = {"n": n, "matches": len({r["eid"] for r in sub})}
    if n:
        out["mean"] = sum(vals) / n
        out["hit"] = sum(r["win"] for r in sub) / n
        out["conf"] = sum(r["conf"] for r in sub) / n
        out["implied"] = sum(1.0 / r["odds"] for r in sub) / n
        fp = [r["fair_p"] for r in sub if r.get("fair_p") is not None]
        out["fair"] = sum(fp) / len(fp) if fp else None
        out["roi"] = sum(r["roi"] for r in sub) / n
    return out


def build_cells(
    legs: list[dict[str, Any]], metric: str
) -> dict[tuple[str, tuple[Any, ...]], dict[str, list[dict[str, Any]]]]:
    cells: dict[tuple[str, tuple[Any, ...]], dict[str, list[dict[str, Any]]]] = (
        defaultdict(lambda: {"dev": [], "hold": []})
    )
    for leg in legs:
        if leg["split"] is None or leg.get(metric) is None:
            continue
        for fam, dims in FAMILIES.items():
            if "over" in dims and leg["priced"] != "fair":
                continue
            k = cell_key(leg, dims)
            if k is not None:
                cells[(fam, k)][leg["split"]].append(leg)
    return cells


def evaluate(
    legs: list[dict[str, Any]], metric: str, rng: np.random.Generator
) -> dict[str, Any]:
    cells = build_cells(legs, metric)
    rows: list[dict[str, Any]] = []
    for (fam, key), parts in cells.items():
        dev, hold = parts["dev"], parts["hold"]
        row: dict[str, Any] = {
            "family": fam,
            "cell": list(key),
            "dev": summarize(dev, metric),
            "hold": summarize(hold, metric),
        }
        for split, data in (("dev", dev), ("hold", hold)):
            if len(data) >= MIN_N:
                boot = bootstrap(
                    [r[metric] for r in data], [r["eid"] for r in data], B_SCAN, rng
                )
                lo, hi = interval(boot, 0.95)
                row[split].update(lo=lo, hi=hi, p_one=float((boot <= 0).mean()))
        row["candidate"] = row["dev"]["n"] >= MIN_N and row["dev"].get("lo", -1) > 0
        rows.append(row)
    cands = [r for r in rows if r["candidate"] and r["hold"]["n"] >= MIN_N]
    k = len(cands)
    level = 1.0 - ALPHA / k if k else 0.95
    for r in cands:
        data = cells[(r["family"], tuple(r["cell"]))]["hold"]
        boot = bootstrap(
            [x[metric] for x in data], [x["eid"] for x in data], B_HOLD, rng
        )
        lo, hi = interval(boot, level)
        r["hold"].update(lo_bonf=lo, hi_bonf=hi)
        r["passed"] = lo > 0
    scan = [r for r in rows if r["hold"]["n"] >= MIN_N]
    flags = bh([r["hold"]["p_one"] for r in scan], BH_Q)
    for r, f in zip(scan, flags, strict=True):
        r["bh_hold"] = f
    return {
        "metric": metric,
        "cells_total": len(rows),
        "cells_dev_n300": sum(1 for r in rows if r["dev"]["n"] >= MIN_N),
        "candidates_dev": sum(1 for r in rows if r["candidate"]),
        "candidates_tested_hold": k,
        "bonferroni_level": level,
        "passed": [r for r in cands if r.get("passed")],
        "scan_tested_hold": len(scan),
        "scan_bh_discoveries": [r for r in scan if r.get("bh_hold")],
        "rows": rows,
    }


# ---------------------------------------------------------------- descriptive


def coverage(legs: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    by: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for leg in legs:
        by[(leg["sport"], leg["split"] or "-")].append(leg)
    for (sport, split), rows in sorted(by.items()):
        n = len(rows)
        out[f"{sport}:{split}"] = {
            "legs": n,
            "matches": len({r["eid"] for r in rows}),
            "fair": sum(1 for r in rows if r["priced"] == "fair"),
            "clv": sum(1 for r in rows if r.get("clv") is not None),
            "close_odds": sum(1 for r in rows if r.get("close_odds") is not None),
            "open_odds": sum(1 for r in rows if r.get("open_odds") is not None),
            "tts": sum(1 for r in rows if r.get("tts") is not None),
            "days": sorted({r["day"] for r in rows}),
        }
    return out


def movement(legs: list[dict[str, Any]]) -> dict[str, Any]:
    """Descriptive price path: open (sports' first snapshot) -> taken -> close."""
    out: dict[str, Any] = {}
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for leg in legs:
        by[leg["sport"]].append(leg)
    for sport, rows in sorted(by.items()):
        tc = [
            math.log(r["odds"] / r["close_odds"]) for r in rows if r.get("close_odds")
        ]
        ot = [math.log(r["open_odds"] / r["odds"]) for r in rows if r.get("open_odds")]
        out[sport] = {
            "n_taken_close": len(tc),
            "mean_log_taken_over_close": sum(tc) / len(tc) if tc else None,
            "share_taken_gt_close": (sum(1 for x in tc if x > 1e-9) / len(tc))
            if tc
            else None,
            "share_taken_lt_close": (sum(1 for x in tc if x < -1e-9) / len(tc))
            if tc
            else None,
            "n_open_taken": len(ot),
            "mean_log_open_over_taken": sum(ot) / len(ot) if ot else None,
        }
    return out


def edge_clv_corr(legs: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for leg in legs:
        if leg.get("fair_p") is not None and leg.get("clv") is not None:
            by[leg["sport"]].append(leg)
    for sport, rows in sorted(by.items()):
        if len(rows) < 30:
            continue
        x = np.array([r["conf"] - r["fair_p"] for r in rows])
        y = np.array([r["clv"] for r in rows])
        over = [r["clv"] for r in rows if r["over"] == "tak"]
        under = [r["clv"] for r in rows if r["over"] == "nie"]
        out[sport] = {
            "n": len(rows),
            "corr_gap_clv": float(np.corrcoef(x, y)[0, 1]),
            "clv_over": sum(over) / len(over) if over else None,
            "n_over": len(over),
            "clv_not_over": sum(under) / len(under) if under else None,
            "n_not_over": len(under),
        }
    return out


# ---------------------------------------------------------------- forward tests
# Registered 2026-11-20 (config/sofa_test_registry.json), data from 2026-11-21.
# T-PRICE-EDGE-CELLS-FORWARD: the 20 dev candidates of the frozen run (dev CI
# above zero, untested by the hold-out - the international break), each judged
# once on its first 300 legs in kickoff order, Bonferroni over the 20.
# T-PRICE-EDGE-VB-RAW-FORWARD: volleyball printed singles, win - 1/odds.

FORWARD_FROM = "2026-11-21"
FORWARD_N = 300
FORWARD_B = 20000
FORWARD_CELLS: tuple[tuple[str, ...], ...] = (
    ("F2", "fair", "football", "corners_total|OVER"),
    ("F11", "fair", "football", "UEFA Champions League", "nie"),
    ("F10", "fair", "football", "corners_total|OVER", "tak"),
    ("F7", "fair", "football", "shots_total|OVER", "6-12"),
    ("F7", "fair", "football", "red_cards_total|UNDER", "6-12"),
    ("F2", "fair", "football", "penalties_total|UNDER"),
    ("F7", "fair", "football", "penalties_total|UNDER", "6-12"),
    ("F10", "fair", "football", "penalties_total|UNDER", "tak"),
    ("F3", "fair", "football", "2. Bundesliga"),
    ("F11", "fair", "football", "2. Bundesliga", "tak"),
    ("F8", "fair", "football", "LaLiga", "<-0.05"),
    ("F11", "fair", "football", "Ekstraklasa", "tak"),
    ("F3", "fair", "football", "Trendyol Süper Lig"),
    ("F11", "fair", "football", "Trendyol Süper Lig", "tak"),
    ("F11", "fair", "football", "Serie B", "tak"),
    ("F3", "fair", "football", "OTP Bank Liga"),
    ("F3", "fair", "football", "Liga Portugal Betclic"),
    ("F11", "fair", "football", "Liga Portugal Betclic", "nie"),
    ("F8", "fair", "football", "Liga Portugal Betclic", "<-0.05"),
    ("F2", "fair", "football", "penalties_for|UNDER"),
)
FORWARD_CELLS_LEVEL = 1.0 - ALPHA / len(FORWARD_CELLS)
TAX_PAYOUT = 0.88


def first_legs(rows: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """The first n legs in kickoff order (ties: day, match, market)."""
    order = sorted(rows, key=lambda r: (r["kickoff"], r["day"], r["eid"], r["md"]))
    return order[:n]


def judge(
    rows: list[dict[str, Any]], metric: str, level: float, rng: np.random.Generator
) -> dict[str, Any]:
    """Status of one forward cell: PENDING below FORWARD_N legs, else judged once
    on the first FORWARD_N (PASSED = lower bound at `level` above zero)."""
    out: dict[str, Any] = {"n_seen": len(rows), "level": level}
    if len(rows) < FORWARD_N:
        out["status"] = "PENDING"
        return out
    first = first_legs(rows, FORWARD_N)
    vals = [r[metric] for r in first]
    boot = bootstrap(vals, [r["eid"] for r in first], FORWARD_B, rng)
    lo, hi = interval(boot, level)
    out.update(
        status="PASSED" if lo > 0 else "NOT_PASSED",
        mean=sum(vals) / len(vals),
        lo=lo,
        hi=hi,
        matches=len({r["eid"] for r in first}),
        last_kickoff=first[-1]["kickoff"],
        roi=sum(r["roi"] for r in first) / len(first),
        roi_after_tax=sum(TAX_PAYOUT * r["odds"] * r["win"] - 1.0 for r in first)
        / len(first),
    )
    return out


def forward_cells(
    legs: list[dict[str, Any]], rng: np.random.Generator
) -> dict[str, Any]:
    cells = []
    for spec in FORWARD_CELLS:
        fam, key = spec[0], tuple(spec[1:])
        rows = [r for r in legs if cell_key(r, FAMILIES[fam]) == key]
        cells.append(
            {
                "family": fam,
                "cell": list(key),
                **judge(rows, "edge", FORWARD_CELLS_LEVEL, rng),
            }
        )
    passed = [c for c in cells if c["status"] == "PASSED"]
    pending = [c for c in cells if c["status"] == "PENDING"]
    return {
        "test": "T-PRICE-EDGE-CELLS-FORWARD",
        "cells": cells,
        "verdict": "PASSED" if passed else ("PENDING" if pending else "NOT_PASSED"),
    }


def forward_volleyball(
    legs: list[dict[str, Any]], rng: np.random.Generator
) -> dict[str, Any]:
    rows = [
        {**r, "raw_edge": r["win"] - 1.0 / r["odds"]}
        for r in legs
        if r["sport"] == "volleyball"
    ]
    res = judge(rows, "raw_edge", 0.95, rng)
    return {"test": "T-PRICE-EDGE-VB-RAW-FORWARD", **res, "verdict": res["status"]}


# ---------------------------------------------------------------- main


def check_protocol() -> None:
    sha = hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    if sha != PROTOCOL_SHA256:
        raise SystemExit(f"PROTOCOL sha256 {sha} != frozen {PROTOCOL_SHA256}")


def _flat(r: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "family": r["family"],
        "priced": r["cell"][0],
        "cell": " / ".join(str(x) for x in r["cell"][1:]),
        "candidate": r["candidate"],
        "passed": r.get("passed"),
        "bh_hold": r.get("bh_hold"),
    }
    for split in ("dev", "hold"):
        for k, v in r[split].items():
            out[f"{split}_{k}"] = v
    return out


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    flat = [_flat(r) for r in rows]
    if not flat:
        path.write_text("", encoding="utf-8")
        return
    cols: list[str] = []
    for f in flat:
        cols += [c for c in f if c not in cols]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for f in flat:
            w.writerow(
                {k: (round(v, 5) if isinstance(v, float) else v) for k, v in f.items()}
            )


def run_forward(runs: Path, test: str, date_from: str, date_to: str | None) -> int:
    if date_from < FORWARD_FROM:
        raise SystemExit(f"a forward test reads data from {FORWARD_FROM} only")
    end = date_to or (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
    stats: dict[str, Any] = {
        "days_with_11_coupon": [],
        "days_without_11_coupon": [],
        "results_status": defaultdict(int),
        "no_leg_fields": defaultdict(int),
        "no_odds_or_conf": defaultdict(int),
    }
    legs: list[dict[str, Any]] = []
    for day in days(date_from, end):
        legs += load_day(runs, day, stats)
    rng = np.random.default_rng(SEED)
    out = forward_cells(legs, rng) if test == "cells" else forward_volleyball(legs, rng)
    out.update(window=[date_from, end], legs=len(legs))
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs", default=str(REPO / "runs/sofa"))
    ap.add_argument("--out-dir")
    ap.add_argument(
        "--forward",
        choices=("cells", "volleyball"),
        help="judge a registered forward test instead of the frozen run",
    )
    ap.add_argument("--from", dest="date_from", default=FORWARD_FROM)
    ap.add_argument("--to", dest="date_to")
    args = ap.parse_args(argv)
    check_protocol()
    if args.forward:
        return run_forward(Path(args.runs), args.forward, args.date_from, args.date_to)
    if not args.out_dir:
        ap.error("--out-dir is required for the frozen run")
    runs, out_dir = Path(args.runs), Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stats: dict[str, Any] = {
        "days_with_11_coupon": [],
        "days_without_11_coupon": [],
        "results_status": defaultdict(int),
        "no_leg_fields": defaultdict(int),
        "no_odds_or_conf": defaultdict(int),
    }
    legs: list[dict[str, Any]] = []
    for day in days(DEV[0], HOLD[1]):
        got = load_day(runs, day, stats)
        print(f"{day}: {len(got)} legs", file=sys.stderr, flush=True)
        legs += got
    rng = np.random.default_rng(SEED)
    edge = evaluate(legs, "edge", rng)
    clv = evaluate(legs, "clv", rng)
    clv_over = evaluate([x for x in legs if x.get("over") == "tak"], "clv", rng)
    summary: dict[str, Any] = {
        "protocol_sha256": PROTOCOL_SHA256,
        "dev": DEV,
        "hold": HOLD,
        "stats": {
            k: (dict(v) if isinstance(v, defaultdict) else v) for k, v in stats.items()
        },
        "coverage": coverage(legs),
        "movement": movement(legs),
        "edge_clv": edge_clv_corr(legs),
    }
    for name, ev in (("edge", edge), ("clv", clv), ("clv_over", clv_over)):
        summary[name] = {
            k: v
            for k, v in ev.items()
            if k != "rows" and k not in ("passed", "scan_bh_discoveries")
        }
        summary[name]["passed"] = [_flat(r) for r in ev["passed"]]
        summary[name]["scan_bh_discoveries"] = [
            _flat(r) for r in ev["scan_bh_discoveries"]
        ]
        big = [
            r for r in ev["rows"] if r["dev"]["n"] >= MIN_N or r["hold"]["n"] >= MIN_N
        ]
        write_csv(out_dir / f"cells_{name}.csv", big)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False, default=str), encoding="utf-8"
    )
    for name in ("edge", "clv", "clv_over"):
        s = summary[name]
        print(
            f"{name}: cells {s['cells_total']}, dev n>=300 {s['cells_dev_n300']}, "
            f"candidates {s['candidates_dev']}, "
            f"tested on hold {s['candidates_tested_hold']}, "
            f"passed {len(s['passed'])}; scan {s['scan_tested_hold']} cells, "
            f"BH {len(s['scan_bh_discoveries'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
