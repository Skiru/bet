#!/usr/bin/env python3
"""Does each market's half split actually sum to its full-match total?

    python3 scripts/simple/audit_half_totals.py
    python3 scripts/simple/audit_half_totals.py --check      # exit 1 on any mismatch

Why this exists. ``goals_1h``/``goals_2h`` are derived by *subtraction* from
the full-time score (``providers.py``'s ``_bzzoiro_history``), and
``half_time_is_possible`` guards that subtraction because a half-time figure
above the full-time one turns into a negative goal count -- caught once, in
10,173 checks, at bzzoiro match 221408.

``corners``/``cards``/``shots``/``fouls``/``offsides`` are built differently:
``_bzzoiro_match_stats`` sums whatever rows the payload tags
``"<stat>_1h"``/``"<stat>_2h"`` directly, independently of the full-match row.
There is no subtraction to protect and therefore no analogous guard -- but
that also means nothing checks that bzzoiro's own ``1h + 2h`` agrees with its
own match total for these five markets. This script is that check, run
offline against dossiers already on disk (``runs/*/*_event_dossiers.json``),
never against the network.

It is deliberately *not* a live guard. Nothing downstream ever reads
``<stat>_1h_total``/``<stat>_2h_total`` for these five markets --
``analyze.py``'s ``_MARKET_STAT_TO_CANONICAL`` maps only ``goals_1h``/
``goals_2h``, and ``market_ranking.py`` keeps the others dossier-only on
purpose -- so a mismatch here cannot reach a priced row today. This script
exists to measure the rate once, put a number next to the claim, and give the
day this stops being true (the day one of these halves gets a market) a
red flag already on disk instead of one that has to be rediscovered by hand.

Method: for each football dossier's metric pair (``<stat>_total`` /
``<stat>_1h_total`` / ``<stat>_2h_total``, and separately the ``_for`` per-team
triple), match bzzoiro-provider rows across the three by ``match_id`` within
the same sample list (``team_a_l10``, ``team_b_l10``, ``h2h``) and check
``1h + 2h == total``. Only ``provider == "bzzoiro"`` rows are read -- the
1h/2h split is bzzoiro-only, no other provider in these dossiers ever emits
it. Checks are deduplicated by ``(market, granularity, match_id)`` across every
dossier and every date on disk, because the same historical match recurs in
many different fixtures' ``l10``/``h2h`` samples and counting it once per
recurrence would inflate the check count without adding information.

Only the plain dated run directories (``runs/YYYY-MM-DD/``) are read.
``runs/`` also holds merged/step/pre-rerun variants of a handful of dates
(``2026-09-04_step4_merged`` and friends) that are re-saved snapshots of the
same underlying matches; including them would count the same mismatch several
times under a different directory name.

Exit codes: 0 = no mismatches (or nothing to check), 1 = at least one mismatch
found (only with --check).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "runs"

# The five markets whose 1h/2h split is summed from independently-tagged rows
# rather than derived by subtraction from the full-match total. Goals is not
# here on purpose -- it is the subtraction path ``half_time_is_possible``
# already guards, a different mechanism with a different failure mode.
MARKETS = ("corners", "cards", "shots", "fouls", "offsides")
GRANULARITIES = ("total", "for")
SAMPLE_LISTS = ("team_a_l10", "team_b_l10", "h2h")

_DATED_RUN_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TOLERANCE = 1e-6


def dossier_files(runs_dir: Path) -> list[Path]:
    return sorted(
        p
        for p in runs_dir.glob("*/*_event_dossiers.json")
        if _DATED_RUN_DIR.match(p.parent.name)
    )


def collect(runs_dir: Path) -> dict[tuple[str, str], dict[str, tuple[float, float, float]]]:
    """``(market, granularity) -> {match_id: (total, h1, h2)}``, deduplicated.

    Later files win on a repeated ``match_id`` (later dossiers reflect any
    re-enrichment); this is a measurement pass, not a betting one, so which
    side wins a rare re-fetch does not matter to the reported rate.
    """
    seen: dict[tuple[str, str], dict[str, tuple[float, float, float]]] = defaultdict(dict)
    for path in dossier_files(runs_dir):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for event in payload.get("dossiers") or []:
            if event.get("sport") != "football":
                continue
            metrics = event.get("metrics") or {}
            for market in MARKETS:
                for granularity in GRANULARITIES:
                    full_key = f"{market}_{granularity}"
                    h1_key = f"{market}_1h_{granularity}"
                    h2_key = f"{market}_2h_{granularity}"
                    if full_key not in metrics or h1_key not in metrics or h2_key not in metrics:
                        continue
                    for sample in SAMPLE_LISTS:
                        full_rows = _bzzoiro_values(metrics[full_key], sample)
                        h1_rows = _bzzoiro_values(metrics[h1_key], sample)
                        h2_rows = _bzzoiro_values(metrics[h2_key], sample)
                        for match_id in full_rows.keys() & h1_rows.keys() & h2_rows.keys():
                            seen[(market, granularity)][match_id] = (
                                full_rows[match_id], h1_rows[match_id], h2_rows[match_id],
                            )
    return seen


def _bzzoiro_values(metric: dict, sample: str) -> dict[str, float]:
    return {
        row["match_id"]: row["value"]
        for row in metric.get(sample) or []
        if row.get("provider") == "bzzoiro" and row.get("match_id") is not None
    }


def report(seen: dict[tuple[str, str], dict[str, tuple[float, float, float]]]) -> list[dict]:
    rows = []
    for (market, granularity), by_match in sorted(seen.items()):
        checks = len(by_match)
        mismatches = [
            (match_id, total, h1, h2)
            for match_id, (total, h1, h2) in by_match.items()
            if abs(total - (h1 + h2)) > _TOLERANCE
        ]
        rows.append({
            "market": market,
            "granularity": granularity,
            "checks": checks,
            "mismatches": len(mismatches),
            "rate": (len(mismatches) / checks) if checks else 0.0,
            "examples": mismatches[:3],
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="exit 1 if any mismatch is found")
    parser.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    args = parser.parse_args()

    seen = collect(args.runs_dir)
    rows = report(seen)
    if not rows:
        print("No dossiers on disk had both a full-match and a half-split reading for any of these markets.")
        return 0

    total_checks = sum(r["checks"] for r in rows)
    total_mismatches = sum(r["mismatches"] for r in rows)
    print(f"{'market':10} {'granularity':11} {'checks':>8} {'mismatches':>10} {'rate':>8}")
    for r in rows:
        print(f"{r['market']:10} {r['granularity']:11} {r['checks']:>8} {r['mismatches']:>10} {r['rate']:>7.2%}")
    overall = (total_mismatches / total_checks) if total_checks else 0.0
    print(f"{'TOTAL':10} {'':11} {total_checks:>8} {total_mismatches:>10} {overall:>7.2%}")

    if args.check and total_mismatches:
        print(f"\n{total_mismatches} mismatch(es) across {total_checks} checks -- see examples above.", file=sys.stderr)
        for r in rows:
            for match_id, total, h1, h2 in r["examples"]:
                print(f"  {r['market']}_{r['granularity']}: match {match_id}: total={total} 1h+2h={h1 + h2} ({h1}+{h2})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
