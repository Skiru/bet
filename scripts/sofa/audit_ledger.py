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

from bet.sofa.clv import MIN_CLUSTERS, cluster_ratio_interval  # noqa: E402
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


# Bets for a 3% edge to show at 2 sigma when one bet's return has sd ~1
# (practitioner arithmetic, 2026-10-01 review): (2 / 0.03)^2.
BETS_FOR_3PCT = 4400


def match_clusters(
    rows: list[dict[str, Any]],
) -> dict[str, tuple[float, int]] | None:
    """{match: (units, settled)} over a variant's days, merged by match (a
    leg graded a day late is still its match). None when a day with settled
    positions carries no per-match record (written before 2026-10-01, or a
    rule replay, which records only its totals) - its positions cannot be
    clustered, and dropping them would bias the interval."""
    out: dict[str, tuple[float, int]] = {}
    for r in rows:
        settled = int((r.get("total") or {}).get("settled", 0) or 0)
        matches = r.get("by_match")
        if matches is None:
            if settled:
                return None
            continue
        for key, (units, count) in matches.items():
            u, c = out.get(key, (0.0, 0))
            out[key] = (u + float(units), c + int(count))
    return out


def roi_interval(rows: list[dict[str, Any]], seed: int = 7,
                 n: int = 2000) -> tuple[float, float] | None:
    """95% interval of ROI from resampling whole MATCHES - legs of one match
    share its game script, and a day is not the unit either: with two days
    the old by-day bootstrap could only return the two days' own ROIs.
    None without a per-match record, or under MIN_CLUSTERS matches."""
    clusters = match_clusters(rows)
    if clusters is None:
        return None
    return cluster_ratio_interval(clusters, seed, n)


def interval_text(rows: list[dict[str, Any]]) -> str:
    clusters = match_clusters(rows)
    if clusters is None:
        return "- (no per-match record)"
    ci = cluster_ratio_interval(clusters)
    if ci is None:
        return f"- (<{MIN_CLUSTERS} matches)"
    return f"[{ci[0]:+.1%}, {ci[1]:+.1%}]"


def estimated_text(rows: list[dict[str, Any]]) -> str:
    """Units of the builders graded at the haircut estimate (no screen
    price recorded) - audit_settlement 7c's "(szac.)". "?" counts the days
    whose record predates the field but had builders."""
    units = 0.0
    settled = unknown = 0
    for r in rows:
        est = r.get("estimated_builders")
        if est is None:
            if int((r.get("builders") or {}).get("positions", 0) or 0):
                unknown += 1
            continue
        units += float(est.get("units", 0.0))
        settled += int(est.get("settled", 0))
    text = "-" if not settled else f"{units:+.2f} in {settled}"
    if unknown:
        text += f" (+? on {unknown} unrecorded day{'s' if unknown > 1 else ''})"
    return text


# The comparability groups a variant's days fall in (plan 2026-10-05, K7):
# the rules changed on the morning of 10-05 (official dials) and again at the
# stats-only cutover (bet.sofa.epochs). One table row per (variant, group),
# never summed across groups.
EPOCH_GROUPS = ("do 10-04", "10-05 rano", "stats_only")


def epoch_group(row: dict[str, Any]) -> str:
    if row.get("epoch") == "stats_only":
        return "stats_only"
    if str(row.get("date", "")) < "2026-10-05":
        return "do 10-04"
    return "10-05 rano"


def render(rows: list[dict[str, Any]], variant: str | None) -> list[str]:
    out: list[str] = []
    by_variant: dict[str, list[dict[str, Any]]] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_variant.setdefault(r["variant"], []).append(r)
        if not str(r["variant"]).startswith("measure:"):
            grouped.setdefault(f"{r['variant']} [{epoch_group(r)}]", []).append(r)
    bets = sorted(
        grouped,
        key=lambda k: (k.rsplit(" [", 1)[0],
                       EPOCH_GROUPS.index(k.rsplit(" [", 1)[1].rstrip("]"))),
    )
    out += [
        "| variant | days | positions | settled | won | lost | units "
        "| of which estimated builders | ROI | ROI 95% (by match) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for v in bets:
        if variant and v.rsplit(" [", 1)[0] != variant:
            continue
        t = totals(grouped[v])
        roi = "-" if t["roi"] is None else f"{t['roi']:+.1%}"
        out.append(
            f"| {v} | {t['days']} | {t['positions']} | {t['settled']} | "
            f"{t['won']} | {t['lost']} | {t['units']:+.2f} | "
            f"{estimated_text(grouped[v])} | {roi} | "
            f"{interval_text(grouped[v])} |"
        )
    out += ["", "Each variant is split by rule epoch (do 10-04 / 10-05 rano / "
            "stats_only): the coupon before and after each cutover is not one "
            "experiment, so the groups are never added."]
    out += ["", f"A 3% edge needs ~{BETS_FOR_3PCT} settled positions to show at "
            "2 sigma; a ROI over a few dozen is noise until its interval says "
            "otherwise. CLV (audit_clv.py) answers sooner. An estimated builder "
            "is graded "
            "at odds_if_product x the haircut (no screen price recorded) - "
            "its units are not a price Superbet printed."]
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
