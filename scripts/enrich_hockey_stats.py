#!/usr/bin/env python3
"""Hockey enrichment combo pipeline — Flashscore + rich completion.

Step 1: Run flashscore enrichment (European leagues).
Step 2: Run rich completion for remaining gaps (MoneyPuck, ESPN fallback).

Usage:
    PYTHONPATH=src .venv/bin/python scripts/enrich_hockey_stats.py --date 2026-05-26 --verbose
"""

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent / "_helpers"))

from bet.db.connection import get_db
from bet.db.repositories import SportRepo

logger = logging.getLogger(__name__)


def get_coverage_stats(date: str) -> dict:
    """Calculate hockey team coverage for date."""
    with get_db() as conn:
        sport_repo = SportRepo(conn)
        hockey = sport_repo.get_by_name("hockey")
        if not hockey:
            return {"total": 0, "enriched": 0}

        total = conn.execute(
            """SELECT COUNT(DISTINCT t.id) FROM teams t
               JOIN fixtures f ON (f.home_team_id = t.id OR f.away_team_id = t.id)
               WHERE f.sport_id = ? AND date(f.kickoff) = ?""",
            (hockey.id, date),
        ).fetchone()[0]

        enriched = conn.execute(
            """SELECT COUNT(DISTINCT tf.team_id) FROM team_form tf
               JOIN fixtures f ON (f.home_team_id = tf.team_id OR f.away_team_id = tf.team_id)
               WHERE tf.sport_id = ? AND date(f.kickoff) = ?
               AND tf.updated_at > datetime('now', '-48 hours')""",
            (hockey.id, date),
        ).fetchone()[0]

    return {"total": total, "enriched": enriched}


def main():
    parser = argparse.ArgumentParser(description="Hockey Stats Combo Enrichment")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    before = get_coverage_stats(args.date)
    pct_before = round(before["enriched"] / before["total"] * 100, 1) if before["total"] else 0

    print(f"\n{'='*60}")
    print(f"  HOCKEY ENRICHMENT COMBO — {args.date}")
    print(f"  Coverage before: {before['enriched']}/{before['total']} teams ({pct_before}%)")
    print(f"{'='*60}\n")

    # Step 1: Flashscore
    print("─── Step 1: Flashscore (European leagues) ───")
    cmd = [
        sys.executable, str(Path(__file__).parent / "enrich_hockey_flashscore.py"),
        "--date", args.date,
    ]
    if args.verbose:
        cmd.append("--verbose")
    if args.limit:
        cmd.extend(["--limit", str(args.limit)])

    result = subprocess.run(cmd, capture_output=not args.verbose, text=True)
    if result.returncode != 0 and not args.verbose:
        print(f"  [WARN] Flashscore step failed: {result.stderr[:200]}")
    elif not args.verbose:
        # Extract summary
        for line in (result.stdout or "").splitlines():
            if "AGENT_SUMMARY" in line:
                print(f"  {line}")

    # Step 2: Rich completion
    print("\n─── Step 2: Rich completion (MoneyPuck/ESPN) ───")
    try:
        from hockey_rich_completion import hockey_rich_completion
        rich_result = hockey_rich_completion(args.date, verbose=args.verbose)
        if rich_result:
            print(f"  Rich completion: {rich_result.get('enriched', 0)} teams updated")
    except ImportError:
        print("  [INFO] hockey_rich_completion not available, skipping")
    except Exception as e:
        print(f"  [WARN] Rich completion failed: {e}")

    # Coverage after
    after = get_coverage_stats(args.date)
    pct_after = round(after["enriched"] / after["total"] * 100, 1) if after["total"] else 0

    print(f"\n{'='*60}")
    print(f"  Coverage: {pct_before}% → {pct_after}%")
    print(f"  Teams: {after['enriched']}/{after['total']}")
    print(f"{'='*60}")

    summary = {
        "before_pct": pct_before,
        "after_pct": pct_after,
        "total_teams": after["total"],
        "enriched_teams": after["enriched"],
    }
    print(f"\nAGENT_SUMMARY:{json.dumps(summary)}")


if __name__ == "__main__":
    main()
