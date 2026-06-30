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
    if sports and any(s.lower() == "all" for s in sports):
        sports = None

    if args.verbose:
        print(f"[discover_events] Starting discovery for {args.date}")
        if sports:
            print(f"[discover_events] Sports filter: {sports}")
        if args.stats_first:
            print(f"[discover_events] Stats-first mode: events without odds will be included")

    try:
        result = discover_events(
            date=args.date,
            sports=sports,
            verbose=args.verbose,
            db_path=args.db_path,
        )
    except Exception as e:
        import traceback
        import sqlite3
        print("\nFATAL ERROR DURING EVENT DISCOVERY", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        
        # Check if this looks like a schema/migration mismatch or SQLite operational error
        err_msg = str(e).lower()
        is_schema = (
            isinstance(e, sqlite3.Error) or
            any(x in err_msg for x in ("schema", "column", "migration", "table", "preflight", "duplicate", "savepoint", "sqlite3", "unable to open", "database"))
        )
        
        verdict = "BLOCKED_DISCOVERY_DB_SCHEMA_MISMATCH" if is_schema else "FAILED"
        if is_schema:
            print("BLOCKED_DISCOVERY_DB_SCHEMA_MISMATCH")
        else:
            print("BLOCKED_DISCOVERY_FAILED")
            
        summary = {
            "verdict": verdict,
            "total_discovered": 0,
            "total_after_dedup": 0,
            "requested_sports": sports or [],
            "raw_by_sport": {},
            "by_sport": {},
            "provider_counts_by_sport": {},
            "provider_errors_by_sport": {},
            "sources": {},
            "issues_count": 1,
            "db_schema_verdict": "FAIL",
            "fallback_used": False,
            "fallback_reason": str(e),
        }
        print(f"\nAGENT_SUMMARY:{json.dumps(summary)}")
        sys.exit(2)

    # 0 raw events checks
    if result.total_discovered == 0:
        # Determine if any providers failed / are unavailable
        any_failed = any(not s.available or s.errors for s in result.source_stats.values())
        if any_failed:
            verdict = "BLOCKED_DISCOVERY_PROVIDER_UNAVAILABLE"
            print("BLOCKED_DISCOVERY_PROVIDER_UNAVAILABLE")
        else:
            verdict = "BLOCKED_DISCOVERY_EMPTY_UNIVERSE"
            print("BLOCKED_DISCOVERY_EMPTY_UNIVERSE")
            
        summary = {
            "verdict": verdict,
            "total_discovered": 0,
            "total_after_dedup": 0,
            "requested_sports": result.requested_sports,
            "raw_by_sport": result.raw_by_sport,
            "by_sport": {},
            "provider_counts_by_sport": {
                sport: {
                    name: stats.per_sport_counts.get(sport, 0)
                    for name, stats in result.source_stats.items()
                    if sport in stats.per_sport_counts or sport in stats.per_sport_errors
                }
                for sport in result.requested_sports
            },
            "provider_errors_by_sport": {
                sport: [
                    error
                    for stats in result.source_stats.values()
                    for error in stats.per_sport_errors.get(sport, [])
                ]
                for sport in result.requested_sports
            },
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
            "db_schema_verdict": "PASS",
            "fallback_used": False,
            "fallback_reason": "No events returned from providers",
        }
        print(f"\nAGENT_SUMMARY:{json.dumps(summary)}")
        sys.exit(2)

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
        "requested_sports": result.requested_sports,
        "raw_by_sport": result.raw_by_sport,
        "by_sport": result.by_sport,
        "provider_counts_by_sport": {
            sport: {
                name: stats.per_sport_counts.get(sport, 0)
                for name, stats in result.source_stats.items()
                if sport in stats.per_sport_counts or sport in stats.per_sport_errors
            }
            for sport in result.requested_sports
        },
        "provider_errors_by_sport": {
            sport: [
                error
                for stats in result.source_stats.values()
                for error in stats.per_sport_errors.get(sport, [])
            ]
            for sport in result.requested_sports
        },
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
        "db_schema_verdict": "PASS",
        "fallback_used": False,
        "fallback_reason": "N/A",
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
