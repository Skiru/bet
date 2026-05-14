#!/usr/bin/env python3
"""Discover sports events worldwide using SofaScore, The Odds API, and API-Football.

Usage:
    python3 scripts/discover_events.py --date 2026-05-14 --verbose
    python3 scripts/discover_events.py --date 2026-05-14 --sports football,tennis

Replaces scan_events.py with API-first discovery (no web scraping).
Emits AGENT_SUMMARY:{json} on stdout (R19).
Exit codes: 0=OK, 1=PARTIAL, 2=FAILED.
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bet.discovery import discover_events


def main():
    parser = argparse.ArgumentParser(description="Sports Event Discovery")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    parser.add_argument("--sports", default=None, help="Comma-separated sports (default: all 5)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--stats-first", action="store_true", help="Stats-first mode (R10)")
    parser.add_argument("--db-path", default=None, help="Custom DB path")
    args = parser.parse_args()

    sports = args.sports.split(",") if args.sports else None

    if args.verbose:
        print(f"[discover_events] Starting discovery for {args.date}")
        if sports:
            print(f"[discover_events] Sports filter: {sports}")

    result = discover_events(
        date=args.date,
        sports=sports,
        verbose=args.verbose,
        db_path=args.db_path,
    )

    # Print summary
    print(f"\n{'='*60}")
    print(f"DISCOVERY RESULTS for {args.date}")
    print(f"{'='*60}")
    print(f"Verdict:           {result.verdict}")
    print(f"Total discovered:  {result.total_discovered}")
    print(f"After dedup:       {result.total_after_dedup}")
    print(f"By sport:          {json.dumps(result.by_sport)}")
    print()

    for src_name, stats in result.source_stats.items():
        status = "✓" if stats.available and not stats.errors else "✗"
        print(f"  [{status}] {src_name}: {stats.events_fetched} events, "
              f"{stats.duration_seconds}s, sports={stats.sports_covered}")
        for err in stats.errors:
            print(f"      ERROR: {err}")

    if result.issues:
        print(f"\nIssues: {len(result.issues)}")
        for issue in result.issues:
            print(f"  - {issue}")

    # AGENT_SUMMARY (R19)
    summary = {
        "verdict": result.verdict,
        "total_discovered": result.total_discovered,
        "total_after_dedup": result.total_after_dedup,
        "by_sport": result.by_sport,
        "sources": {
            name: {
                "events": s.events_fetched,
                "available": s.available,
                "errors": len(s.errors),
                "duration_s": s.duration_seconds,
            }
            for name, s in result.source_stats.items()
        },
        "issues_count": len(result.issues),
    }
    print(f"\nAGENT_SUMMARY:{json.dumps(summary)}")

    # Exit code
    if result.verdict == "FAILED":
        sys.exit(2)
    elif result.verdict == "PARTIAL":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
