#!/usr/bin/env python3
"""Does a confidence above its price realise? And would a stricter price-band
cap, or an offset per disagreement bin, cure it? Read-only evidence
(bet.sofa.price_gap; docs/sofa/evidence/price_gap_2026-10-12.md).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_price_gap.py \\
        --from <d> --to <d> [--walk-forward] [--md-out f]

Section 1 - the printed football / tennis singles of each day (the coupon
artifact) with a WIN / LOSS in 07_settled.json: realised minus confidence
(match bootstrap) for the legs whose confidence exceeds 1/odds by more than
price_gap.GAP and for the rest, per sport and per day.

Section 2 (--walk-forward) - for each day D the line evidence is refitted on
the stats-only days before D exactly as fit_line_evidence.py fits it (the
curves D reads), and every printed leg of D is read three ways:
V0 the current rules, V1 a strict price-band cap (to the cell's realised rate
whenever it is lower, not only below its Wilson upper bound), V2 V0 plus the
point offset of its (sport, disagreement bin) measured on the earlier days'
sheet rows (>= 50 lines of 30 games, never above 0). A leg prints under a
variant when it clears the coupon's floor and x (the shape gates do not depend
on the variant). Reports what each prints, what each drops and how the dropped
legs did - out of sample. A leg whose V0 differs from its printed confidence
by > 0.002 is counted (10-07 and 10-08 do not reproduce: a mixed day and the
old curves).

Nothing is written but --md-out. Exit 0, 2 on a crash.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import random
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import line_evidence as le  # noqa: E402
from bet.sofa import price_gap as pgap  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    COUPON_PROFILE,
    Calibration,
    calibration_path_for,
    coupon_artifact,
    direction_key,
    is_derived,
    match_class,
)
from bet.sofa.config import SofaConfig  # noqa: E402
from scripts.sofa import fit_line_evidence as fle  # noqa: E402

SPORTS = ("football", "tennis")
BINS = (0.03, 0.06, 0.10)
MIN_BIN_ROWS = le.MIN_OFFSET_ROWS
MIN_BIN_GAMES = le.MIN_OFFSET_GAMES
BOOT = 2000

Leg = dict[str, Any]


def bin_of(gap: float) -> int:
    """Disagreement bin of confidence minus 1/odds: <= 0.03, .. 0.06, .. 0.10, above."""
    for i, edge in enumerate(BINS):
        if round(gap, 9) <= edge:
            return i
    return len(BINS)


def prints(conf: float | None, odds: float) -> bool:
    """The coupon's floor and x (COUPON_PROFILE)."""
    return conf is not None and conf >= COUPON_PROFILE.floor \
        and COUPON_PROFILE.clears_price(conf, odds)


class StrictCap(le.LineEvidence):
    """V1: the price-band cap lowers to the cell's realised rate whenever it is
    lower than the confidence."""

    def band_cap(self, sport: str, key: str, p: float, odds: float | None,
                 value: float) -> tuple[float, str] | None:
        cell = self.band_cell(sport, key, p, odds)
        if cell is None:
            return None
        n, k, label = cell
        if k / n >= value:
            return None
        return round(k / n, 4), label


def days_between(lo: str, hi: str) -> list[str]:
    d0, d1 = date.fromisoformat(lo), date.fromisoformat(hi)
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def _cal(day: str) -> Calibration:
    return dataclasses.replace(Calibration.load(calibration_path_for(day)),
                               gap_shrink_k=0.0, cap_market_by_thin=True,
                               cap_pool_by_neighbour=True)


def _evidence_doc(rows: Iterable[le.Row]) -> dict[str, Any]:
    return {**le.fit(rows), "min_bucket": le.MIN_EVIDENCE_BUCKET,
            "min_cap_cell": le.MIN_CAP_CELL, "min_offset_rows": le.MIN_OFFSET_ROWS,
            "min_offset_games": le.MIN_OFFSET_GAMES,
            "min_sport_offset_games": le.MIN_SPORT_OFFSET_GAMES,
            "min_evidence_games": le.MIN_EVIDENCE_GAMES}


def printed_legs(runs: Path, day: str) -> list[Leg]:
    """The day's printed football / tennis singles with a WIN / LOSS."""
    rd = runs / day
    if not (rd / "07_settled.json").exists():
        return []
    settled = {(r["sofascore_event_id"], r["market"], r.get("subject") or "",
                r["line"], r["direction"]): r
               for r in json.loads(
                   (rd / "07_settled.json").read_text(encoding="utf-8"))}
    doc = json.loads(coupon_artifact(rd).read_text(encoding="utf-8"))
    out: list[Leg] = []
    for leg in doc.get("legs") or []:
        if leg.get("sport") not in SPORTS or not leg.get("offered_odds"):
            continue
        s = settled.get((leg["sofascore_event_id"], leg["market"],
                         leg.get("subject") or "", leg["line"], leg["direction"]))
        if not s or s.get("outcome") not in ("WIN", "LOSS"):
            continue
        out.append({"d": day, "ev": leg["sofascore_event_id"], "sport": leg["sport"],
                    "market": leg["market"], "direction": leg["direction"],
                    "subject": leg.get("subject") or "", "line": leg["line"],
                    "p": s.get("p_central"), "odds": float(leg["offered_odds"]),
                    "printed": float(leg["confidence"]),
                    "y": 1 if s["outcome"] == "WIN" else 0})
    return out


def _boot(rs: Sequence[Leg], f: Callable[[Sequence[Leg]], float],
          rng: random.Random) -> tuple[float, float]:
    by: dict[tuple[str, int], list[Leg]] = defaultdict(list)
    for r in rs:
        by[(r["d"], r["ev"])].append(r)
    keys = list(by)
    vals = sorted(f([r for k in rng.choices(keys, k=len(keys)) for r in by[k]])
                  for _ in range(BOOT))
    return vals[int(0.025 * BOOT)], vals[int(0.975 * BOOT)]


def _pnl(r: Mapping[str, Any]) -> float:
    return float(r["odds"]) - 1.0 if r["y"] else -1.0


def describe(name: str, rs: Sequence[Leg], conf: str, rng: random.Random) -> str:
    n = len(rs)
    if not n:
        return f"| {name} | 0 | | | | | | |"

    def gap(s: Sequence[Leg]) -> float:
        return sum(float(r["y"]) - float(r[conf]) for r in s) / len(s)

    def roi(s: Sequence[Leg]) -> float:
        return sum(_pnl(r) for r in s) / len(s)

    glo, ghi = _boot(rs, gap, rng)
    rlo, rhi = _boot(rs, roi, rng)
    return (f"| {name} | {n} | {len({(r['d'], r['ev']) for r in rs})} | "
            f"{sum(r[conf] for r in rs) / n:.3f} | "
            f"{sum(1 / r['odds'] for r in rs) / n:.3f} | "
            f"{sum(r['y'] for r in rs) / n:.3f} | "
            f"{100 * gap(rs):+.1f} pp [{100 * glo:+.1f}, {100 * ghi:+.1f}] | "
            f"{100 * roi(rs):+.1f}% [{100 * rlo:+.1f}, {100 * rhi:+.1f}] |")


HEAD = ("| grupa | nóg | meczów | pewność | 1/kurs | trafiło | trafiło − pewność "
        "| ROI |\n|---|---|---|---|---|---|---|---|")


def section_printed(legs: Sequence[Leg], rng: random.Random) -> list[str]:
    out = ["## 1. Wydrukowane nogi: pewność ponad cenę", "", HEAD]
    for sport in SPORTS:
        rs = [r for r in legs if r["sport"] == sport]
        above = [r for r in rs if r["printed"] - 1 / r["odds"] > pgap.GAP]
        rest = [r for r in rs if r["printed"] - 1 / r["odds"] <= pgap.GAP]
        out.append(describe(f"{sport}: pewność > 1/kurs + {pgap.GAP}", above,
                            "printed", rng))
        out.append(describe(f"{sport}: reszta", rest, "printed", rng))
    out += ["", "| dzień | nóg ponad cenę | trafiło − pewność | reszta "
            "| trafiło − pewność |", "|---|---|---|---|---|"]
    for day in sorted({r["d"] for r in legs}):
        rs = [r for r in legs if r["d"] == day]
        above = [r for r in rs if r["printed"] - 1 / r["odds"] > pgap.GAP]
        rest = [r for r in rs if r["printed"] - 1 / r["odds"] <= pgap.GAP]

        def g(s: Sequence[Leg]) -> str:
            return f"{100 * sum(r['y'] - r['printed'] for r in s) / len(s):+.1f} pp" \
                if s else "-"
        out.append(f"| {day} | {len(above)} | {g(above)} | {len(rest)} | {g(rest)} |")
    return out


def walk_forward(runs: Path, legs: list[Leg]) -> list[Leg]:
    """V0 / V1 / V2 confidences of each leg from evidence of the earlier days."""
    out: list[Leg] = []
    for day in sorted({r["d"] for r in legs}):
        cal = _cal(day)
        train = list(fle.sheet_rows(runs, fle.stats_only_days(runs, day), cal))
        doc = _evidence_doc(train)
        v0, v1 = le.LineEvidence(doc, v2=True), StrictCap(doc, v2=True)
        acc: dict[tuple[str, int], list[float]] = defaultdict(list)
        games: dict[tuple[str, int], set[str]] = defaultdict(set)
        for t in train:
            rd = v0.read(str(t["sport"]), str(t["key"]), float(t["p"]),
                         None if t["base"] is None else (float(t["base"]), "", 0),
                         t["odds"])
            if rd is None or rd.value < le.PRINTABLE_FROM:
                continue
            b = (str(t["sport"]), bin_of(rd.value - 1 / float(t["odds"])))
            acc[b].append(int(t["y"]) - rd.value)
            games[b].add(str(t["game"]))
        offset = {b: min(0.0, sum(v) / len(v)) if len(v) >= MIN_BIN_ROWS
                  and len(games[b]) >= MIN_BIN_GAMES else 0.0 for b, v in acc.items()}
        rd_dir = runs / day
        fixtures = {int(f["sofascore_event_id"]): f for f in json.loads(
            (rd_dir / "02_fixtures.json").read_text(encoding="utf-8"))}
        sides = fle._board_sides(rd_dir)
        for r in (x for x in legs if x["d"] == day):
            if r["p"] is None:
                continue
            fx = fixtures.get(int(r["ev"])) or {}
            board = next((sides[str(i)] for i in fx.get("superbet_event_ids") or []
                          if str(i) in sides), None)
            klass = match_class(
                r["sport"], fx.get("category_name") if r["sport"] == "tennis"
                else fx.get("competition_name"), board, fx.get("competition_id"))
            p = float(r["p"])
            hit = None if is_derived(r["market"]) else cal.realised(
                r["market"], p, r["sport"], r["direction"], klass)
            key = le.evidence_key(direction_key(r["market"], r["direction"]), klass)
            r0 = v0.read(r["sport"], key, p, hit, r["odds"])
            r1 = v1.read(r["sport"], key, p, hit, r["odds"])
            if r0 is None:
                continue
            c2 = round(max(0.0, r0.value + offset.get(
                (r["sport"], bin_of(r0.value - 1 / r["odds"])), 0.0)), 4)
            out.append({**r, "c0": r0.value,
                        "c1": None if r1 is None else r1.value, "c2": c2})
        print(f"{day}: {sum(1 for x in out if x['d'] == day)} legs, trained on "
              f"{len(train)} sheet rows", file=sys.stderr)
    return out


def section_walk_forward(rows: Sequence[Leg], rng: random.Random) -> list[str]:
    repro = sum(abs(r["c0"] - r["printed"]) <= 0.002 for r in rows)
    out = ["## 2. Walk-forward: V0 (dziś), V1 (ostry cap pasma), V2 (offset rozjazdu)",
           "", f"V0 odtwarza wydrukowaną pewność (±0,002) na {repro} z "
           f"{len(rows)} nóg.",
           ""]
    for sport in (*SPORTS, None):
        pop = [r for r in rows if sport is None or r["sport"] == sport]
        p0 = [r for r in pop if prints(r["c0"], r["odds"])]
        out += [f"### {sport or 'piłka + tenis'}", "", HEAD]
        out.append(describe("V0 drukuje (pewność V0)", p0, "c0", rng))
        for v in ("c1", "c2"):
            kept = [r for r in p0 if prints(r[v], r["odds"])]
            drop = [r for r in p0 if not prints(r[v], r["odds"])]
            low = [r for r in kept if r[v] < r["c0"] - 1e-9]
            name = "V1" if v == "c1" else "V2"
            out.append(describe(f"{name} drukuje (pewność {name})", kept, v, rng))
            out.append(describe(f"{name} zdejmuje (pewność V0)", drop, "c0", rng))
            out.append(describe(f"{name} obniża, zostawia (pewność V0)", low,
                                "c0", rng))
            out.append(describe(f"{name} obniża, zostawia (pewność {name})", low,
                                v, rng))
            out.append(describe(
                f"{name}: pewność > 1/kurs + {pgap.GAP} (pewność {name})",
                [r for r in kept if r[v] - 1 / r["odds"] > pgap.GAP], v, rng))
        out.append(describe(f"V0: pewność > 1/kurs + {pgap.GAP} (pewność V0)",
                            [r for r in p0 if r["c0"] - 1 / r["odds"] > pgap.GAP],
                            "c0", rng))
        out.append("")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="date_from", required=True)
    ap.add_argument("--to", dest="date_to", required=True)
    ap.add_argument("--walk-forward", action="store_true")
    ap.add_argument("--md-out", default=None)
    args = ap.parse_args()
    runs = Path(SofaConfig.from_env().runs_dir)
    rng = random.Random(11)
    legs = [r for d in days_between(args.date_from, args.date_to)
            for r in printed_legs(runs, d)]
    lines = [f"# Pewność ponad cenę - {args.date_from}..{args.date_to}", "",
             f"Nóg: {len(legs)} (piłka / tenis, wydrukowane, WIN / LOSS); "
             "bootstrap po meczach.", "", *section_printed(legs, rng), ""]
    if args.walk_forward:
        lines += section_walk_forward(walk_forward(runs, legs), rng)
    text = "\n".join(lines) + "\n"
    if args.md_out:
        Path(args.md_out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - exit code contract: 2 on a crash
        print(f"MEASURE_PRICE_GAP_FAILED: {exc!r}", file=sys.stderr)
        sys.exit(2)
