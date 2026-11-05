#!/usr/bin/env python3
"""Tennis games_total / sets_total below the 0.70 floor - read-only measurement.

Operator, 2026-11-05: tennis full-match games total and sets total (best of
three) almost never print; would a lower floor (confidence 0.60-0.70, or the
x = confidence x odds >= 0.90 rule alone) make money or beat the price?

Population: every tennis games_total / sets_total (line 2.5) sheet row of the
settled stats-only days, graded WIN / LOSS by SETTLE (07_settled.json - the
ledger's own grader; a walkover / retirement / refund is not WIN / LOSS there
and is left out), at the price the sheet carried (`offered_odds`, the morning
OFFER - not the price at a later print).

Why a replay: the per-row refusal record is display only (never read
here), is rewritten by every rebuild, and the last rebuild of a day sees
most tennis rows KICKED_OFF, so the confidence of a refused row is not on
disk for any day. The confidence is therefore re-derived as CONFIDENCE
derives it today
(run_confidence.py): the installed football / tennis curve the day reads now
(calibration_path_for, live-only keys stripped, K13 / K13b caps), then line
evidence (LineEvidence.read: offset by d bucket, price-band cap, v2, bucket
design effect) fitted WALK-FORWARD for each day D from the settled stats-only
days strictly before D only (as fit_line_evidence.py --before D does, on the
tennis rows - every tennis evidence quantity is per sport). Current rules
applied to every day: the replay is "what today's rules would have said",
not what the day printed; it is checked against the confidences the days
did record for their legs (08_confidence.json `legs`).

Not modelled (each would only remove legs): CATCH_ALL_BUCKET (p_central <
0.60 is refused after the floor - so a p < 0.60 leg could not print under
R3 without lifting that gate too; R3 is reported with and without it), the
sample shape gates, STALE_PRICE / KICKED_OFF, the analysts' reads.

Usage:
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_totals_floor.py \
        [--from 2026-10-07] [--to 2026-11-04] [--boot 2000] [--json-out F]
Read-only: reads runs/sofa and config, writes nothing unless --json-out.
"""

from __future__ import annotations

import argparse
import bisect
import dataclasses
import json
import random
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import epochs, live_only_curves  # noqa: E402
from bet.sofa import line_evidence as le  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    COUPON_PROFILE,
    MIN_ODDS_FOR_CEILING,
    Calibration,
    calibration_path_for,
    curve_market,
    direction_key,
    match_class,
)
from bet.sofa.epochs import STATS_ONLY_DATE  # noqa: E402

RUNS = _REPO / "runs" / "sofa"
MARKETS = ("games_total", "sets_total")
RULES_DAY = "2026-11-05"  # the rules replayed: today's
BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("<0.55", 0.0, 0.55), ("0.55-0.60", 0.55, 0.60), ("0.60-0.65", 0.60, 0.65),
    ("0.65-0.70", 0.65, 0.70), (">=0.70", 0.70, 9.0))
Row = dict[str, Any]


def _board_sides(run_dir: Path) -> dict[str, tuple[str, str]]:
    path = run_dir / "01_board.json"
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    entries = doc if isinstance(doc, list) else doc.get(
        "fixtures", doc.get("events", []))
    return {str(e["superbet_event_id"]): (str(e.get("side_a") or ""),
                                          str(e.get("side_b") or ""))
            for e in entries if isinstance(e, dict) and e.get("superbet_event_id")}


def load_day(day: str, cal: Calibration) -> list[Row]:
    """Every graded tennis sheet row of `day` (as fit_line_evidence.sheet_rows
    reads it, tennis only) with the fields this measurement needs."""
    run_dir = RUNS / day
    fixtures = {int(f["sofascore_event_id"]): f for f in json.loads(
        (run_dir / "02_fixtures.json").read_text(encoding="utf-8"))}
    sides = _board_sides(run_dir)
    out: list[Row] = []
    for r in json.loads((run_dir / "07_settled.json").read_text(encoding="utf-8")):
        if r.get("sport") != "tennis" or r.get("outcome") not in ("WIN", "LOSS"):
            continue
        if r.get("p_central") is None or not r.get("offered_odds") \
                or not r.get("direction"):
            continue
        fx = fixtures.get(int(r["sofascore_event_id"])) or {}
        board = next((sides[str(i)] for i in fx.get("superbet_event_ids") or []
                      if str(i) in sides), None)
        klass = match_class("tennis", fx.get("category_name"), board,
                            fx.get("competition_id"))
        p = float(r["p_central"])
        hit = cal.realised(curve_market(r), p, "tennis", r["direction"], klass)
        out.append({
            "sport": "tennis",
            "key": le.evidence_key(direction_key(r["market"], r["direction"]), klass),
            "p": p, "y": 1 if r["outcome"] == "WIN" else 0,
            "game": f"{day}:{r['sofascore_event_id']}",
            "base": None if hit is None else float(hit[0]),
            "base_src": None if hit is None else hit[1],
            "base_n": None if hit is None else int(hit[2]),
            "odds": float(r["offered_odds"]),
            "day": day, "event": int(r["sofascore_event_id"]),
            "market": r["market"], "line": float(r["line"]),
            "direction": r["direction"], "klass": klass,
        })
    return out


def evidence_for(rows: Iterable[Row]) -> le.LineEvidence:
    fitted = le.fit(rows)
    doc = {
        "min_bucket": le.MIN_EVIDENCE_BUCKET, "min_cap_cell": le.MIN_CAP_CELL,
        "min_offset_rows": le.MIN_OFFSET_ROWS, "min_offset_games": le.MIN_OFFSET_GAMES,
        "min_sport_offset_games": le.MIN_SPORT_OFFSET_GAMES,
        "min_evidence_games": le.MIN_EVIDENCE_GAMES,
        "price_gap_shrink_k": le.PRICE_GAP_SHRINK_K,
        **fitted,
    }
    return le.LineEvidence(
        doc, v2=epochs.line_evidence_v2(RULES_DAY),
        bucket_deff=epochs.bucket_design_effect(RULES_DAY),
        price_gap_sports=epochs.price_gap_offset_sports(RULES_DAY))


def pair_devig(rows: list[Row]) -> None:
    """fair = (1/o) / (1/o_over + 1/o_under) and the rung's margin, where both
    sides of the rung are on the sheet."""
    by: dict[tuple[Any, ...], dict[str, Row]] = defaultdict(dict)
    for r in rows:
        by[(r["day"], r["event"], r["market"], r["line"])][r["direction"]] = r
    for pair in by.values():
        if len(pair) != 2:
            continue
        s = sum(1.0 / q["odds"] for q in pair.values())
        for q in pair.values():
            q["fair"] = (1.0 / q["odds"]) / s
            q["margin"] = s - 1.0


# --- statistics ---------------------------------------------------------------

def cluster_boot(rows: Sequence[Row], value: Callable[[Row], float], n_boot: int,
                 seed: int = 11) -> tuple[float, float, float] | None:
    """Mean of value over rows, 95% interval resampling matches (day, event)."""
    if not rows:
        return None
    clusters: dict[tuple[str, int], list[float]] = defaultdict(list)
    for r in rows:
        clusters[(r["day"], r["event"])].append(value(r))
    sums = np.array([sum(v) for v in clusters.values()])
    counts = np.array([len(v) for v in clusters.values()], dtype=float)
    point = float(sums.sum() / counts.sum())
    rng = np.random.default_rng(seed)
    w = rng.multinomial(len(sums), np.full(len(sums), 1.0 / len(sums)), size=n_boot)
    stats = sorted((w @ sums) / (w @ counts))
    lo, hi = stats[int(0.025 * n_boot)], stats[int(0.975 * n_boot) - 1]
    return point, float(lo), float(hi)


def roi(r: Row) -> float:
    return float(r["y"] * r["odds"] - 1.0)


def summary(rows: Sequence[Row], n_boot: int) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    n = len(rows)
    fair = [r["fair"] for r in rows if r.get("fair") is not None]
    return {
        "n": n, "matches": len({(r["day"], r["event"]) for r in rows}),
        "hit": sum(r["y"] for r in rows) / n,
        "conf": sum(r["conf"] for r in rows) / n,
        "implied": sum(1.0 / r["odds"] for r in rows) / n,
        "fair": sum(fair) / len(fair) if fair else None, "n_fair": len(fair),
        "roi": cluster_boot(rows, roi, n_boot),
        "hit_minus_implied": cluster_boot(rows, lambda r: r["y"] - 1.0 / r["odds"],
                                          n_boot),
        # operator 2026-11-05: calibration (does the printed number
        # over-promise?) and the de-vigged price (as good as the price?)
        "hit_minus_conf": cluster_boot(rows, lambda r: r["y"] - r["conf"], n_boot),
        "hit_minus_fair": cluster_boot(
            [r for r in rows if r.get("fair") is not None],
            lambda r: r["y"] - r["fair"], n_boot),
    }


def one_rung(rows: Sequence[Row]) -> list[Row]:
    """One rung per (day, match, market, direction): the highest x."""
    best: dict[tuple[Any, ...], Row] = {}
    for r in rows:
        key = (r["day"], r["event"], r["market"], r["direction"])
        if key not in best or r["x"] > best[key]["x"]:
            best[key] = r
    return list(best.values())


def auc(scores: Sequence[float], ys: Sequence[int]) -> float | None:
    pos = sorted(s for s, y in zip(scores, ys, strict=True) if y == 1)
    neg = sorted(s for s, y in zip(scores, ys, strict=True) if y == 0)
    if not pos or not neg:
        return None
    total = 0.0
    for s in pos:
        lo = bisect.bisect_left(neg, s)
        hi = bisect.bisect_right(neg, s)
        total += lo + 0.5 * (hi - lo)
    return total / (len(pos) * len(neg))


def auc_compare(rows: Sequence[Row], n_boot: int, seed: int = 5
                ) -> dict[str, Any] | None:
    if len(rows) < 30:
        return None
    a_model = auc([r["p"] for r in rows], [r["y"] for r in rows])
    a_price = auc([1.0 / r["odds"] for r in rows], [r["y"] for r in rows])
    if a_model is None or a_price is None:
        return None
    clusters: dict[tuple[str, int], list[Row]] = defaultdict(list)
    for r in rows:
        clusters[(r["day"], r["event"])].append(r)
    keys = list(clusters)
    rng = random.Random(seed)
    diffs = []
    for _ in range(n_boot):
        sample = [r for _ in keys for r in clusters[keys[rng.randrange(len(keys))]]]
        ys = [r["y"] for r in sample]
        am = auc([r["p"] for r in sample], ys)
        ap = auc([1.0 / r["odds"] for r in sample], ys)
        if am is not None and ap is not None:
            diffs.append(am - ap)
    diffs.sort()
    m = len(diffs)
    return {"n": len(rows), "matches": len(keys), "auc_model": a_model,
            "auc_price": a_price, "diff": a_model - a_price,
            "diff_lo": diffs[int(0.025 * m)], "diff_hi": diffs[int(0.975 * m) - 1]}


# --- the rules (frozen before any ROI was read) ---------------------------------

def _printable(r: Row) -> bool:
    """The coupon's other price gates: margin <= 15% where both sides are
    quoted (a one-sided rung is not judged here), odds >= the ceiling's."""
    margin = r.get("margin")
    return r["odds"] >= MIN_ODDS_FOR_CEILING and (
        margin is None or margin <= COUPON_PROFILE.max_overround)


RULES: dict[str, Callable[[Row], bool]] = {
    "R0 obecna: conf>=0.70 & x>=0.90":
        lambda r: r["conf"] >= 0.70 and r["x"] >= 0.90,
    "R1: conf>=0.60 & x>=0.90":
        lambda r: r["conf"] >= 0.60 and r["x"] >= 0.90,
    "R2: conf>=0.65 & x>=0.90":
        lambda r: r["conf"] >= 0.65 and r["x"] >= 0.90,
    "R3: x>=0.95 (dowolna conf)":
        lambda r: r["x"] >= 0.95,
    "R3 bez p<0.60 (CATCH_ALL_BUCKET zostaje)":
        lambda r: r["x"] >= 0.95 and r["p"] >= 0.60,
}


def _fmt_ci(t: tuple[float, float, float] | None, pct: bool = True) -> str:
    if t is None:
        return "-"
    f = 100.0 if pct else 1.0
    return f"{t[0] * f:+.1f} [{t[1] * f:+.1f}, {t[2] * f:+.1f}]"


def _line(label: str, s: dict[str, Any]) -> str:
    if not s.get("n"):
        return f"| {label} | 0 | 0 | - | - | - | - | - | - | - | - |"
    fair = "-" if s["fair"] is None else f"{s['fair']:.3f}"
    return (f"| {label} | {s['n']} | {s['matches']} | {s['hit']:.3f} | "
            f"{s['conf']:.3f} | {s['implied']:.3f} | {fair} | "
            f"{_fmt_ci(s['hit_minus_conf'])} | {_fmt_ci(s['hit_minus_fair'])} | "
            f"{_fmt_ci(s['hit_minus_implied'])} | {_fmt_ci(s['roi'])} |")


def verdict(s: dict[str, Any]) -> str:
    """Operator 2026-11-05: 'calibrated' - realised minus confidence interval
    contains 0 or lies above it; 'at the price' - realised minus the
    de-vigged price likewise; 'money' - ROI's lower bound above 0."""
    if not s.get("n"):
        return "brak nóg"
    conf, fair, roi_ = s["hit_minus_conf"], s["hit_minus_fair"], s["roi"]
    parts = [
        "skalibrowane" if conf is not None and conf[2] >= 0.0
        else "NIE skalibrowane (obiecuje za dużo)",
        "-" if fair is None else ("na poziomie ceny" if fair[2] >= 0.0
                                  else "PONIŻEJ ceny (de-vig)"),
        "zarabia" if roi_ is not None and roi_[1] > 0.0 else "nie zarabia",
    ]
    return ", ".join(parts)


HEADER = ("| komórka | n nóg | n meczów | trafienia | śr. pewność | śr. 1/kurs | "
          "śr. fair (de-vig) | trafienia - pewność, pp [95%] | "
          "trafienia - fair, pp [95%] | trafienia - 1/kurs, pp [95%] | "
          "ROI % [95%] |\n"
          "|---|---|---|---|---|---|---|---|---|---|---|")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="date_from", default="2026-10-07")
    ap.add_argument("--to", dest="date_to", default="2026-11-04")
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    cal = dataclasses.replace(Calibration.load(calibration_path_for(RULES_DAY)),
                              gap_shrink_k=0.0, cap_market_by_thin=True,
                              cap_pool_by_neighbour=True)
    cal = live_only_curves.for_day(cal, RULES_DAY)
    days = sorted(d.name for d in RUNS.iterdir()
                  if d.is_dir() and len(d.name) == 10 and d.name[4] == "-"
                  and STATS_ONLY_DATE <= d.name <= args.date_to
                  and (d / "07_settled.json").exists())
    rows_by_day = {d: load_day(d, cal) for d in days}
    print(f"loaded {sum(len(v) for v in rows_by_day.values())} graded tennis rows "
          f"of {len(days)} days {days[0]}..{days[-1]}", file=sys.stderr)

    test_days = [d for d in days if d >= args.date_from]
    legs: list[Row] = []
    no_evidence = 0
    for day in test_days:
        ev = evidence_for(r for d in days if d < day for r in rows_by_day[d])
        day_rows = rows_by_day[day]
        print(f"evidence fitted for {day}", file=sys.stderr, flush=True)
        pair_devig(day_rows)
        for r in day_rows:
            if r["market"] not in MARKETS:
                continue
            if r["market"] == "sets_total" and r["line"] != 2.5:
                continue
            base = None if r["base"] is None else (r["base"], r["base_src"],
                                                   r["base_n"])
            read = ev.read("tennis", r["key"], r["p"], base, r["odds"])
            if read is None:
                no_evidence += 1
                continue
            leg = dict(r)
            leg["conf"] = float(read.value)
            leg["x"] = leg["conf"] * leg["odds"]
            leg["printable"] = _printable(leg)
            legs.append(leg)
    print(f"{len(legs)} rows with a replayed confidence, {no_evidence} "
          "NO_LINE_EVIDENCE", file=sys.stderr)

    half = test_days[len(test_days) // 2]
    halves = {
        f"I połowa {test_days[0]}..{max(d for d in test_days if d < half)}":
            [r for r in legs if r["day"] < half],
        f"II połowa {half}..{test_days[-1]} (hold-out)":
            [r for r in legs if r["day"] >= half],
    }
    out: list[str] = []
    result: dict[str, Any] = {"days": test_days, "half_from": half}

    # 0. replay vs recorded confidences
    out.append("## 0. Replay a zapisane pewności\n")
    recorded: list[tuple[float, float]] = []
    by_key = {(r["day"], r["event"], r["market"], r["line"], r["direction"]): r
              for r in legs}
    for day in test_days:
        conf_path = RUNS / day / "08_confidence.json"
        if conf_path.exists():
            doc = json.loads(conf_path.read_text(encoding="utf-8"))
            for leg in doc.get("legs") or []:
                if leg.get("sport") != "tennis" or leg.get("market") not in MARKETS:
                    continue
                k = (day, int(leg["sofascore_event_id"]), leg["market"],
                     float(leg["line"]), leg["direction"])
                if k in by_key and leg.get("confidence") is not None:
                    recorded.append((float(leg["confidence"]), by_key[k]["conf"]))
    if recorded:
        diffs = sorted(abs(a - b) for a, b in recorded)
        within = sum(1 for d in diffs if d <= 0.02) / len(diffs)
        both = sum(1 for a, b in recorded if (a >= 0.70) == (b >= 0.70)) / len(diffs)
        out.append(f"Nogi 08_confidence.json z zapisaną pewnością: "
                   f"{len(recorded)}; |zapis - replay| mediana "
                   f"{diffs[len(diffs) // 2]:.4f}, <= 0.02 w {within:.1%}, ta sama "
                   f"strona progu 0.70 w {both:.1%}.\n")
        result["replay_check"] = {"n": len(recorded),
                                  "median_abs": diffs[len(diffs) // 2],
                                  "within_002": within, "same_side_070": both}

    # 1. buckets
    out.append("## 1. Kubełki pewności (wszystkie szczeble, wszystkie dni testu)\n")
    result["buckets"] = {}
    for market in MARKETS:
        for direction in ("OVER", "UNDER"):
            out.append(f"### {market} {direction}\n\n{HEADER}")
            for label, lo, hi in BUCKETS:
                cell = [r for r in legs if r["market"] == market
                        and r["direction"] == direction and lo <= r["conf"] < hi]
                s = summary(cell, args.boot)
                s1 = summary(one_rung(cell), args.boot)
                result["buckets"][f"{market}|{direction}|{label}"] = {
                    "all": s, "one_rung": s1}
                out.append(_line(f"{label}", s))
                out.append(_line(f"{label} (1 szczebel / mecz, max x)", s1))
            out.append("")

    # 2. rules
    out.append("## 2. Reguły (zamrożone przed ROI), po połowach\n")
    result["rules"] = {}
    for name, rule in RULES.items():
        out.append(f"### {name}\n\n{HEADER}")
        for hname, hrows in halves.items():
            for market in (*MARKETS, "oba"):
                cell = [r for r in hrows if r["printable"] and rule(r)
                        and (market == "oba" or r["market"] == market)]
                s = summary(cell, args.boot)
                s1 = summary(one_rung(cell), args.boot)
                result["rules"][f"{name}|{hname}|{market}"] = {"all": s, "one_rung": s1}
                out.append(_line(f"{hname} · {market}", s))
                out.append(_line(f"{hname} · {market} · 1 szczebel", s1))
        out.append("")
        # the increment: legs the rule adds over R0
        if not name.startswith("R0"):
            out.append(f"Przyrost względem R0 ({name}):\n\n{HEADER}")
            for hname, hrows in halves.items():
                cell = [r for r in hrows if r["printable"] and rule(r)
                        and not RULES["R0 obecna: conf>=0.70 & x>=0.90"](r)]
                s = summary(cell, args.boot)
                result["rules"][f"{name}|{hname}|increment"] = {"all": s}
                out.append(_line(f"{hname} · tylko dodane", s))
            out.append("")

    # 2b. verdicts on the hold-out half (operator 2026-11-05)
    hold_name, hold_rows = list(halves.items())[1]
    out.append(f"## 2b. Werdykty, {hold_name}\n")
    out.append("| reguła | rynek | wariant | n | werdykt |\n|---|---|---|---|---|")
    result["verdicts"] = {}
    r0 = RULES["R0 obecna: conf>=0.70 & x>=0.90"]
    for name, rule in RULES.items():
        for market in (*MARKETS, "oba"):
            base_cell = [r for r in hold_rows if r["printable"] and rule(r)
                         and (market == "oba" or r["market"] == market)]
            variants = {"wszystkie nogi": base_cell,
                        "1 szczebel / mecz": one_rung(base_cell)}
            if not name.startswith("R0"):
                variants["tylko dodane do R0"] = [r for r in base_cell if not r0(r)]
            for vname, cell in variants.items():
                s = summary(cell, args.boot)
                v = verdict(s)
                result["verdicts"][f"{name}|{market}|{vname}"] = v
                out.append(f"| {name} | {market} | {vname} | {s['n']} | {v} |")
    out.append("")

    # 3. AUC inside the catch-all bucket
    out.append("## 3. Czy kubełek 0-0.60 krzywej ukrywa dyskryminację? "
               "(AUC p_central vs AUC 1/kurs, te same wiersze)\n")
    out.append("| rynek | kierunek | n | mecze | AUC model | AUC cena | "
               "różnica [95% bootstrap meczów] |\n|---|---|---|---|---|---|---|")
    result["auc"] = {}
    for market in MARKETS:
        for direction in ("OVER", "UNDER"):
            cell = [r for r in legs if r["market"] == market
                    and r["direction"] == direction and r["p"] < 0.60]
            a = auc_compare(cell, min(args.boot, 500))
            result["auc"][f"{market}|{direction}"] = a
            if a is None:
                out.append(f"| {market} | {direction} | {len(cell)} | - | - | - | - |")
                continue
            out.append(f"| {market} | {direction} | {a['n']} | {a['matches']} | "
                       f"{a['auc_model']:.3f} | {a['auc_price']:.3f} | "
                       f"{a['diff']:+.3f} [{a['diff_lo']:+.3f}, {a['diff_hi']:+.3f}] |")
    out.append("")
    print("\n".join(out))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=1, default=str),
                                       encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
