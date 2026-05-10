#!/usr/bin/env python3
"""Live data seeder — fetches real data from all new deep-stats API clients.

Runs each client against live APIs and seeds the stats_cache with real data
for use in the betting pipeline. Reports findings per sport.

Usage:
    PYTHONPATH=src:. python3 scripts/seed_deep_stats.py
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.api_clients.rate_limiter import RateLimiter


def main():
    """Run all seeders and produce summary report."""
    print("=" * 60)
    print("  DEEP STATS SEEDER — Live API Data Fetch")
    print(f"  Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    rl = RateLimiter()
    all_results = {}

    # Only 5 sports supported: football, volleyball, basketball, tennis, hockey
    # Only 5 sports supported: football, volleyball, basketball, tennis, hockey

    # Final summary
    print("\n" + "=" * 60)
    print("  SEEDING SUMMARY")
    print("=" * 60)
    for sport, data in all_results.items():
        if "error" in data:
            print(f"  ❌ {sport}: ERROR — {data['error']}")
        else:
            stats_count = data.get("with_stats", data.get("recent_results", 0))
            fixtures_count = data.get("fixtures", data.get("pro_matches", data.get("upcoming", 0)))
            print(f"  ✅ {sport}: {fixtures_count} fixtures, {stats_count} with deep stats")

    # Save summary
    summary_path = Path(__file__).parent.parent / "betting" / "data" / "deep_stats_seed_summary.json"
    summary_path.write_text(json.dumps(all_results, indent=2, default=str), encoding="utf-8")
    print(f"\n  Summary saved to: {summary_path}")


if __name__ == "__main__":
    main()
