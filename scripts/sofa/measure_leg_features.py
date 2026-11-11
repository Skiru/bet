#!/usr/bin/env python3
"""Read-only: which leg fields tell a better leg from a worse one at one price?

The feature search behind bet.sofa.lesser_loss (2026-11-11). Every printed
single of 11_coupon.json graded WIN / LOSS in 13_results.json is read with
ten of its own fields; each field is cut into quintiles on the dev days
(< --split; a two-valued flag into its two values) and the SAME edges are
read on the hold-out (>= --split). Per cell: legs, hit, mean 1/odds, hit
minus 1/odds and ROI before the 12% tax. A field separates when the order of
its cells repeats on the hold-out. A view of the printed legs across ledger
epoch groups - never the ledger.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_leg_features.py \
        --from 2026-10-30 --to 2026-11-10 --split 2026-11-05

Result 2026-11-11: docs/sofa/evidence/mniej_zle_nogi_2026-11-11.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.coupon_results import key_of  # noqa: E402

Row = dict[str, Any]
Field = Callable[[Row], float | None]


def load(runs: Path, start: str, end: str) -> list[Row]:
    rows: list[Row] = []
    for day_dir in sorted(p for p in runs.iterdir() if p.is_dir()):
        day = day_dir.name
        if not (start <= day <= end):
            continue
        res, cpn = day_dir / "13_results.json", day_dir / "11_coupon.json"
        if not (res.exists() and cpn.exists()):
            continue
        graded = json.loads(res.read_text(encoding="utf-8")).get("legs") or {}
        for leg in json.loads(cpn.read_text(encoding="utf-8")).get("singles") or []:
            try:
                g = graded.get(key_of(leg))
            except (KeyError, TypeError, ValueError):
                continue
            if not g or g.get("status") not in ("won", "lost"):
                continue
            if g.get("odds") is None or g.get("confidence") is None:
                continue
            rows.append({"day": day, "won": g["status"] == "won",
                         "odds": float(g["odds"]),
                         "confidence": float(g["confidence"]), "leg": leg})
    return rows


def _num(x: Any) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def _minus_price(name: str) -> Field:
    def f(r: Row) -> float | None:
        v = _num(r["leg"].get(name))
        return None if v is None else v - 1.0 / r["odds"]
    return f


FIELDS: dict[str, Field] = {
    "pewność − 1/kurs": lambda r: r["confidence"] - 1.0 / r["odds"],
    "próbka − 1/kurs": _minus_price("sample_hit_rate"),
    "model − 1/kurs": lambda r: (
        None if (v := _num(r["leg"].get("forecast_p") or r["leg"].get("model_p")))
        is None else v - 1.0 / r["odds"]),
    "marża rynku": lambda r: _num(r["leg"].get("overround")),
    "liczebność próbki": lambda r: _num(r["leg"].get("sample_size")),
    "kurs": lambda r: r["odds"],
    "price_gap": lambda r: float(bool(r["leg"].get("price_gap"))),
    "rating_market_gap": lambda r: float(bool(r["leg"].get("rating_market_gap"))),
    "gwiazdka ★": lambda r: float(bool((r["leg"].get("peer") or {}).get("preferred"))),
    "line_offset": lambda r: _num(r["leg"].get("line_offset")) or 0.0,
}


def cell(rows: list[Row]) -> str:
    if not rows:
        return "—"
    n = len(rows)
    hit = sum(r["won"] for r in rows) / n
    price = sum(1.0 / r["odds"] for r in rows) / n
    roi = sum((r["odds"] - 1.0) if r["won"] else -1.0 for r in rows) / n
    return (f"n={n} weszło={hit:.3f} 1/kurs={price:.3f} "
            f"różnica={100 * (hit - price):+.1f} pp ROI={100 * roi:+.1f}%")


def edges(values: list[float]) -> list[float]:
    distinct = sorted(set(values))
    if len(distinct) <= 2:
        return [0.5] if distinct and max(distinct) <= 1.0 else distinct[1:]
    v = sorted(values)
    return sorted({v[int(len(v) * q)] for q in (0.2, 0.4, 0.6, 0.8)})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--split", required=True, help="first hold-out day")
    ap.add_argument("--runs-dir", default=str(_REPO / "runs" / "sofa"))
    args = ap.parse_args()
    rows = load(Path(args.runs_dir), args.start, args.end)
    dev = [r for r in rows if r["day"] < args.split]
    hold = [r for r in rows if r["day"] >= args.split]
    if not dev or not hold:
        print("dev or hold-out empty", file=sys.stderr)
        return 1
    for name, field in FIELDS.items():
        dv = [(x, r) for r in dev if (x := field(r)) is not None]
        hv = [(x, r) for r in hold if (x := field(r)) is not None]
        cuts = edges([x for x, _ in dv])
        print(f"\n## {name} (granice z dev: {[round(c, 4) for c in cuts]})")
        bounds = [-float("inf"), *cuts, float("inf")]
        for i in range(len(bounds) - 1):
            lo, hi = bounds[i], bounds[i + 1]
            a = [r for x, r in dv if lo <= x < hi]
            b = [r for x, r in hv if lo <= x < hi]
            print(f"- koszyk {i + 1}: dev {cell(a)} | hold-out {cell(b)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
