#!/usr/bin/env python3
"""Read the results ledger across days - per variant, never pooled.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py \\
        --from 2026-09-19 --to 2026-09-30
    ... --variant sport:hockey        # one variant, with its families

The reader of runs/sofa/ledger/results.jsonl (record_results.py writes it).
Every variant is its own table: the coupon, WARIANT, each sport coupon, the
multi-sport variant and each rule replay; the measurements are a separate
table (price against outcome, two-way favourite side). Nothing here adds one
variant's units to another's. Offline. Exit 0, or 2 on a missing ledger.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.config import SofaConfig  # noqa: E402
from scripts.sofa.record_results import ledger_path  # noqa: E402


def load(runs_dir: str, start: str, end: str) -> list[dict[str, Any]]:
    path = ledger_path(runs_dir)
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [r for r in rows if start <= r["date"] <= end]


def totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """One variant's days summed - positions graded at their own prices."""
    t: dict[str, Any] = {
        "days": len(rows),
        "positions": 0,
        "settled": 0,
        "won": 0,
        "lost": 0,
        "units": 0.0,
    }
    for r in rows:
        for k in ("positions", "settled", "won", "lost"):
            t[k] += int((r.get("total") or {}).get(k, 0))
        t["units"] += float((r.get("total") or {}).get("units", 0.0))
    t["units"] = round(t["units"], 4)
    t["roi"] = round(t["units"] / t["settled"], 4) if t["settled"] else None
    return t


def render(rows: list[dict[str, Any]], variant: str | None) -> list[str]:
    out: list[str] = []
    by_variant: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_variant.setdefault(r["variant"], []).append(r)
    bets = sorted(v for v in by_variant if not v.startswith("measure:"))
    out += [
        "| variant | days | positions | settled | won | lost | units | ROI |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for v in bets:
        if variant and v != variant:
            continue
        t = totals(by_variant[v])
        roi = "-" if t["roi"] is None else f"{t['roi']:+.1%}"
        out.append(
            f"| {v} | {t['days']} | {t['positions']} | {t['settled']} | "
            f"{t['won']} | {t['lost']} | {t['units']:+.2f} | {roi} |"
        )
    if variant and variant in by_variant:
        fams: dict[str, dict[str, float]] = {}
        for r in by_variant[variant]:
            for fam, f in (r.get("by_family") or {}).items():
                if not f:
                    continue
                acc = fams.setdefault(fam, {"settled": 0, "won": 0, "units": 0.0})
                acc["settled"] += int(f.get("settled", f.get("n", 0)) or 0)
                acc["won"] += int(f.get("won", f.get("wins", 0)) or 0)
                if "units" in f:
                    acc["units"] += float(f["units"])
                elif "roi" in f and f.get("n"):
                    acc["units"] += float(f["roi"]) * int(f["n"])
        if fams:
            out += [
                "",
                f"## {variant} by family",
                "",
                "| family | settled | won | units | ROI |",
                "|---|---|---|---|---|",
            ]
            for fam, a in sorted(fams.items(), key=lambda kv: -kv[1]["settled"]):
                roi = f"{a['units'] / a['settled']:+.1%}" if a["settled"] else "-"
                out.append(
                    f"| {fam} | {int(a['settled'])} | {int(a['won'])} | "
                    f"{a['units']:+.2f} | {roi} |"
                )
    measures = sorted(v for v in by_variant if v.startswith("measure:"))
    if measures and not variant:
        out += [
            "",
            "| measurement | days | sides | mean fair p | hit | gap pp |",
            "|---|---|---|---|---|---|",
        ]
        for v in measures:
            sides = hit_w = fair_w = 0.0
            days = 0
            for r in by_variant[v]:
                f = r.get("favourite_side") or {}
                n = float(f.get("sides", 0) or 0)
                if n:
                    days += 1
                    sides += n
                    hit_w += n * float(f["hit"])
                    fair_w += n * float(f["mean_fair_p"])
            if sides:
                out.append(
                    f"| {v} | {days} | {int(sides)} | {fair_w / sides:.3f} | "
                    f"{hit_w / sides:.3f} | {100 * (hit_w - fair_w) / sides:+.1f} |"
                )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--variant")
    args = parser.parse_args()
    runs_dir = SofaConfig.from_env().runs_dir
    if not ledger_path(runs_dir).exists():
        print(f"no ledger at {ledger_path(runs_dir)} - run record_results.py first")
        return 2
    rows = load(runs_dir, args.start, args.end)
    print(f"# Ledger {args.start}..{args.end} (each variant alone; never pooled)\n")
    print("\n".join(render(rows, args.variant)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
