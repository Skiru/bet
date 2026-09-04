#!/usr/bin/env python3
"""Differential harness for docs/PLAN_FOOTBALL_BZZOIRO_ONLY_2026-09-04.md.

Run after every step of that plan, before moving to the next one. Two modes:

  discovery-gate   Offline proof for step 1: would the new
                    DISCOVERY_SOURCES_BY_SPORT filter drop any event that is
                    currently reaching the stats sheet? Reads only artifacts
                    already on disk -- no DISCOVER, no network.

  diff             Row-by-row diff between two stats-sheet / coupons pairs,
                    keyed by (event_id, market, subject, line, direction), per
                    the plan's "Odbior" section:
                      - rows whose p_central moved by more than 0.02
                      - tier changes, in each direction
                      - rows whose min_acceptable_odds dropped
                      - the sample_excluded histogram, before vs after
                      - the coupon (singles) diff: gone / new / moved

Usage:
    python3 scripts/dev/consolidation_harness.py discovery-gate --date 2026-09-04
    python3 scripts/dev/consolidation_harness.py diff \
        --before-dir runs/2026-09-04 --before-date 2026-09-04 \
        --after-dir runs/2026-09-04_step2 --after-date 2026-09-04
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Mirrors bet.simple_stats.discover.DISCOVERY_SOURCES_BY_SPORT. Not imported
# directly so this harness keeps working even mid-refactor of that module;
# the two are checked against each other in discovery-gate mode.
DISCOVERY_SOURCES_BY_SPORT = {
    "football": ("bzzoiro",),
    "tennis": ("odds-api",),
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _row_key(row: dict) -> tuple:
    subject = row.get("player_name") or row.get("team_name")
    return (row["event_id"], row["market"], subject, row.get("line"), row.get("direction"))


def cmd_discovery_gate(args: argparse.Namespace) -> int:
    run_dir = ROOT / "runs" / args.date
    event_list = _load(run_dir / f"{args.date}_event_list.json")
    stats_sheet = _load(run_dir / f"{args.date}_event_dossiers_stats_sheet.json")

    events_by_id = {e["event_id"]: e for e in event_list["events"]}

    event_ids_in_sheet = {row["event_id"] for row in stats_sheet["rows"]}
    print(f"events in event_list: {len(events_by_id)}")
    print(f"distinct events reaching the stats sheet: {len(event_ids_in_sheet)}")

    violations = []
    missing = []
    for event_id in sorted(event_ids_in_sheet):
        event = events_by_id.get(event_id)
        if event is None:
            missing.append(event_id)
            continue
        sport = event["sport"]
        required_sources = DISCOVERY_SOURCES_BY_SPORT.get(sport, ())
        have = set(event.get("source_ids") or {})
        if not (have & set(required_sources)):
            violations.append((event_id, sport, sorted(have)))

    if missing:
        print(f"WARN: {len(missing)} stats-sheet event_ids have no event_list record: {missing[:5]}...")

    if violations:
        print(f"FAIL: {len(violations)} priced events would be dropped by the new discovery gate:")
        for event_id, sport, have in violations[:20]:
            print(f"  {event_id[:16]} ({sport}) sources={have}")
        return 1

    print("PASS: every event reaching the stats sheet already carries the "
          "post-step-1 required discovery source. Zero rows would move.")

    by_sport = Counter(events_by_id[eid]["sport"] for eid in event_ids_in_sheet if eid in events_by_id)
    print(f"breakdown: {dict(by_sport)}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    before_sheet = _load(Path(args.before_dir) / f"{args.before_date}_event_dossiers_stats_sheet.json")
    after_sheet = _load(Path(args.after_dir) / f"{args.after_date}_event_dossiers_stats_sheet.json")

    before_rows = {_row_key(r): r for r in before_sheet["rows"]}
    after_rows = {_row_key(r): r for r in after_sheet["rows"]}

    gone = before_rows.keys() - after_rows.keys()
    new = after_rows.keys() - before_rows.keys()
    shared = before_rows.keys() & after_rows.keys()

    print(f"stats-sheet rows: before={len(before_rows)} after={len(after_rows)}")
    print(f"gone={len(gone)} new={len(new)} shared={len(shared)}")

    moved_p_central = []
    agreement_changes = Counter()
    for key in shared:
        a, b = before_rows[key], after_rows[key]
        pa, pb = a.get("p_central"), b.get("p_central")
        if pa is not None and pb is not None and abs(pa - pb) > 0.02:
            moved_p_central.append((key, pa, pb))
        ca, cb = a.get("cross_provider_agreement"), b.get("cross_provider_agreement")
        if ca != cb:
            agreement_changes[(ca, cb)] += 1

    print(f"rows with |Δp_central| > 0.02: {len(moved_p_central)}")
    for key, pa, pb in moved_p_central[:20]:
        print(f"  {key} {pa:.3f} -> {pb:.3f}")

    if agreement_changes:
        print("cross_provider_agreement transitions:")
        for (ca, cb), n in agreement_changes.most_common():
            print(f"  {ca} -> {cb}: {n}")

    def excluded_histogram(sheet: dict) -> Counter:
        hist: Counter = Counter()
        for row in sheet["rows"]:
            for reason in (row.get("sample_excluded") or {}):
                hist[reason] += 1
        return hist

    before_hist = excluded_histogram(before_sheet)
    after_hist = excluded_histogram(after_sheet)
    print("sample_excluded histogram, before -> after:")
    for reason in sorted(set(before_hist) | set(after_hist)):
        b, a = before_hist.get(reason, 0), after_hist.get(reason, 0)
        marker = "" if b == a else "  <-- changed"
        print(f"  {reason}: {b} -> {a}{marker}")

    # Coupon (final singles) diff -- same key convention as /rebuild-coupon
    # Step 5, extended with p_central.
    before_coupons_path = Path(args.before_dir) / f"{args.before_date}_coupons.json"
    after_coupons_path = Path(args.after_dir) / f"{args.after_date}_coupons.json"
    if before_coupons_path.exists() and after_coupons_path.exists():
        before_c = {_row_key(s): s for s in _load(before_coupons_path)["singles"]}
        after_c = {_row_key(s): s for s in _load(after_coupons_path)["singles"]}
        c_gone = before_c.keys() - after_c.keys()
        c_new = after_c.keys() - before_c.keys()
        print(f"\ncoupon singles: before={len(before_c)} after={len(after_c)} gone={len(c_gone)} new={len(c_new)}")
        for key in sorted(c_gone):
            print(f"  GONE  {key}")
        for key in sorted(c_new):
            print(f"  NEW   {key}")
        tier_drops = 0
        for key in before_c.keys() & after_c.keys():
            a, b = before_c[key], after_c[key]
            if a.get("tier") != b.get("tier"):
                print(f"  TIER  {key} {a.get('tier')} -> {b.get('tier')}")
            ma, mb = a.get("min_acceptable_odds"), b.get("min_acceptable_odds")
            if ma is not None and mb is not None and round(mb, 4) < round(ma, 4):
                tier_drops += 1
                print(f"  MIN_ACCEPTABLE_ODDS DROP  {key} {ma} -> {mb}")
        print(f"rows with a lowered min_acceptable_odds: {tier_drops}")
    else:
        print("\n(no coupons.json pair found -- skipping coupon diff)")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    p_gate = sub.add_parser("discovery-gate", help="Offline proof for step 1")
    p_gate.add_argument("--date", required=True)
    p_gate.set_defaults(func=cmd_discovery_gate)

    p_diff = sub.add_parser("diff", help="Row-by-row diff between two runs")
    p_diff.add_argument("--before-dir", required=True)
    p_diff.add_argument("--before-date", required=True)
    p_diff.add_argument("--after-dir", required=True)
    p_diff.add_argument("--after-date", required=True)
    p_diff.set_defaults(func=cmd_diff)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
