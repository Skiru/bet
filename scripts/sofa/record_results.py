#!/usr/bin/env python3
"""Record what every variant and every measurement did on a settled day.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --date 2026-09-30
    ... --from 2026-09-28 --to 2026-09-30

One row per (date, variant) in runs/sofa/ledger/results.jsonl - the running
record the next decision about a rule, a floor or a sport is taken from. A
re-run of a date replaces that date's rows, so the ledger is idempotent.

Variants, each graded at its own printed price and never added to another:

    official         KUPON_<d>.pdf singles and builders (audit_settlement 7c)
    wariant          KUPON_<d>_WARIANT.pdf (7d)
    sport:<sport>    KUPON_<d>_<SPORT>.pdf for cs2 / hockey / basketball / volleyball
    multi            KUPON_<d>_WSZYSTKIE.pdf, its total and its sections

and, not bets but the evidence under the price-only rule:

    measure:<sport>  Superbet's price against the outcome - the favourite side
                     of every graded line (cs2.one_side_per_line), its hit
                     against its devigged probability, Brier and flat ROI

A variant whose artifact does not exist that day is absent, not a zero.
Offline. Exit 0 when every present variant is fully settled, 1 when some
position is still pending.
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

from bet.sofa import multi_coupon as mc  # noqa: E402
from bet.sofa import sport_coupon as sc  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    PROFILES,
    confidence_artifact,
    printed_builders,
    printed_singles,
)
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cs2 import one_side_per_line, summarize, write_atomic  # noqa: E402
from scripts.sofa import settle_multi_coupon, settle_sport_coupon  # noqa: E402

LEDGER_DIR = "ledger"
LEDGER_FILE = "results.jsonl"


def ledger_path(runs_dir: str) -> Path:
    return Path(runs_dir) / LEDGER_DIR / LEDGER_FILE


def _pending(rows: list[dict[str, Any]]) -> int:
    return sum(1 for r in rows if settle_sport_coupon.is_pending(str(r["outcome"])))


def confidence_rows(runs_dir: str, date: str) -> list[dict[str, Any]]:
    out = []
    rows, screen = settle_multi_coupon.official_rows(runs_dir, date)
    for variant, profile in (("official", "standard"), ("wariant", "wariant")):
        path = mc.official_dir(runs_dir, date) / confidence_artifact(PROFILES[profile])
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        singles, builders = settle_multi_coupon.grade_confidence_positions(
            [{"source": s} for s in printed_singles(doc)],
            [{"source": b} for b in printed_builders(doc)],
            rows,
            screen,
        )
        out.append(
            {
                "date": date,
                "variant": variant,
                "singles": mc.summarize_units(singles),
                "builders": mc.summarize_units(builders),
                "total": mc.summarize_units(singles + builders),
                "pending": _pending(singles + builders),
                "settled_rows_on_disk": len(rows),
            }
        )
    return out


def sport_rows(runs_dir: str, date: str) -> list[dict[str, Any]]:
    out = []
    for sport in sc.SPORT_KEYS:
        graded = settle_sport_coupon.settle_day(runs_dir, sport, date)
        if graded is None:
            continue
        out.append(
            {
                "date": date,
                "variant": f"sport:{sport}",
                "total": mc.summarize_units(graded),
                "by_family": {
                    fam: mc.summarize_units([g for g in graded if g["family"] == fam])
                    for fam in sorted({g["family"] for g in graded})
                },
                "pending": _pending(graded),
            }
        )
    return out


def multi_rows(runs_dir: str, date: str) -> list[dict[str, Any]]:
    res = settle_multi_coupon.settle_day(runs_dir, date)
    if res is None:
        return []
    sections = {}
    rows: list[dict[str, Any]] = []
    for key, sec in res["sections"].items():
        if "rows" not in sec:
            sections[key] = {"excluded": sec.get("reason")}
            continue
        sections[key] = mc.summarize_units(sec["rows"])
        rows += sec["rows"]
    return [
        {
            "date": date,
            "variant": "multi",
            "total": res["variant_total"],
            "sections": sections,
            "pending": _pending(rows),
        }
    ]


def measure_rows(runs_dir: str, date: str) -> list[dict[str, Any]]:
    out = []
    for sport in sc.SPORT_KEYS:
        doc = sc.load_settled(runs_dir, sport, date)
        if doc is None:
            continue
        graded = [
            r
            for ev in (doc.get("events") or {}).values()
            for r in ev.get("graded") or []
            if not str(r.get("family", "")).startswith("player_")
        ]
        fav = one_side_per_line(graded, "favourite")
        stats = summarize(fav, "ALL")
        states: dict[str, int] = {}
        for ev in (doc.get("events") or {}).values():
            states[str(ev.get("state"))] = states.get(str(ev.get("state")), 0) + 1
        out.append(
            {
                "date": date,
                "variant": f"measure:{sport}",
                "events": states,
                "favourite_side": None
                if stats is None
                else {
                    "events": stats.events,
                    "sides": stats.sides,
                    "mean_fair_p": round(stats.fair_p, 4),
                    "hit": round(stats.hit, 4),
                    "gap_pp": round(100 * (stats.hit - stats.fair_p), 2),
                    "brier": round(stats.brier, 4),
                    "roi": round(stats.roi, 4),
                    "median_margin": round(stats.margin, 4),
                },
                "pending": 0,
            }
        )
    return out


def record(runs_dir: str, date: str) -> list[dict[str, Any]]:
    rows = (
        confidence_rows(runs_dir, date)
        + sport_rows(runs_dir, date)
        + multi_rows(runs_dir, date)
        + measure_rows(runs_dir, date)
    )
    path = ledger_path(runs_dir)
    kept = []
    if path.exists():
        kept = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        kept = [r for r in kept if r.get("date") != date]
    merged = sorted(kept + rows, key=lambda r: (r["date"], r["variant"]))
    write_atomic(
        path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in merged)
    )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--date")
    parser.add_argument("--from", dest="start")
    parser.add_argument("--to", dest="end")
    args = parser.parse_args()
    if args.date:
        dates = [args.date]
    elif args.start and args.end:
        dates = settle_sport_coupon.days(args.start, args.end)
    else:
        parser.error("--date, or --from and --to")
    runs_dir = SofaConfig.from_env().runs_dir
    pending = 0
    print(
        "| date | variant | positions | settled | won | lost | units | ROI | pending |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    for date in dates:
        for r in record(runs_dir, date):
            pending += r["pending"]
            t = r.get("total")
            if t is None:
                f = r.get("favourite_side") or {}
                print(
                    f"| {date} | {r['variant']} | {f.get('sides', 0)} sides | | "
                    f"hit {f.get('hit', '-')} | fair {f.get('mean_fair_p', '-')} | | "
                    f"{f.get('roi', '-')} | |"
                )
                continue
            roi = "-" if t["roi"] is None else f"{t['roi']:+.1%}"
            print(
                f"| {date} | {r['variant']} | {t['positions']} | {t['settled']} | "
                f"{t['won']} | {t['lost']} | {t['units']:+.2f} | {roi} | "
                f"{r['pending']} |"
            )
    print(f"\nledger: {ledger_path(runs_dir)}")
    return 1 if pending else 0


if __name__ == "__main__":
    sys.exit(main())
