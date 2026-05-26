#!/usr/bin/env python3
"""Volleyball enrichment pipeline — combines Flashscore + API-Volleyball + Sofascore.

Runs enrichment from multiple sources following the fallback chain:
  1. Flashscore (total_points, aces, blocks, errors)
  2. API-Volleyball via rich completion (aces, blocks, hitting_pct, points)
  3. Sofascore fallback (aggregates)

Usage:
    PYTHONPATH=src .venv/bin/python scripts/enrich_volleyball_stats.py --date 2026-05-26 --verbose
"""

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from bet.db.connection import get_db
from bet.db.repositories import SportRepo

logger = logging.getLogger(__name__)


def get_volleyball_enrichment_status(date: str) -> dict:
    """Check current enrichment coverage for volleyball teams with fixtures."""
    with get_db() as conn:
        sport_repo = SportRepo(conn)
        volleyball = sport_repo.get_by_name("volleyball")
        if not volleyball:
            return {"total_teams": 0, "enriched": 0, "coverage_pct": 0}

        total = conn.execute(
            """SELECT COUNT(DISTINCT t.id) FROM teams t
               JOIN fixtures f ON (f.home_team_id = t.id OR f.away_team_id = t.id)
               WHERE f.sport_id = ? AND date(f.kickoff) = ?""",
            (volleyball.id, date),
        ).fetchone()[0]

        enriched = conn.execute(
            """SELECT COUNT(DISTINCT tf.team_id) FROM team_form tf
               WHERE tf.sport_id = ?
               AND json_array_length(tf.l10_values) >= 3
               AND tf.updated_at > datetime('now', '-24 hours')""",
            (volleyball.id,),
        ).fetchone()[0]

        return {
            "total_teams": total,
            "enriched": enriched,
            "coverage_pct": round(100 * enriched / total, 1) if total > 0 else 0,
        }


def run_flashscore_enrichment(date: str, verbose: bool = False, limit: int = 0) -> dict:
    """Run Flashscore enrichment for volleyball."""
    cmd = [
        sys.executable, str(Path(__file__).parent / "enrich_volleyball_flashscore.py"),
        "--date", date,
    ]
    if verbose:
        cmd.append("--verbose")
    if limit > 0:
        cmd.extend(["--limit", str(limit)])

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(Path(__file__).parent.parent))

    summary = {}
    for line in result.stdout.split("\n"):
        if line.startswith("AGENT_SUMMARY:"):
            try:
                summary = json.loads(line[len("AGENT_SUMMARY:"):])
            except json.JSONDecodeError:
                pass

    if verbose:
        print(result.stdout)
    if result.returncode != 0 and verbose:
        print(f"[WARNING] Flashscore enrichment returned code {result.returncode}")
        if result.stderr:
            print(result.stderr[:500])

    return summary


def run_rich_completion(date: str, verbose: bool = False) -> dict:
    """Run rich completion for teams still missing data after Flashscore."""
    try:
        from _helpers.volleyball_rich_completion import try_volleyball_rich_completion
    except ImportError:
        logger.warning("volleyball_rich_completion not available — skipping rich completion")
        return {"completed": 0, "failed": 0, "skipped": True}

    completed = 0
    failed = 0

    with get_db() as conn:
        sport_repo = SportRepo(conn)
        volleyball = sport_repo.get_by_name("volleyball")
        if not volleyball:
            return {"completed": 0, "failed": 0}

        rows = conn.execute(
            """SELECT DISTINCT t.id, t.name FROM teams t
               JOIN fixtures f ON (f.home_team_id = t.id OR f.away_team_id = t.id)
               WHERE f.sport_id = ? AND date(f.kickoff) = ?
               AND t.id NOT IN (
                   SELECT DISTINCT team_id FROM team_form
                   WHERE sport_id = ? AND json_array_length(l10_values) >= 3
                   AND updated_at > datetime('now', '-24 hours')
               )""",
            (volleyball.id, date, volleyball.id),
        ).fetchall()

    for row in rows:
        try:
            result = try_volleyball_rich_completion(row["name"], volleyball.id)
            if result and result.get("keys_stored", 0) > 0:
                completed += 1
                if verbose:
                    print(f"  ✓ {row['name']}: {result['keys_stored']} keys via rich completion")
            else:
                failed += 1
        except Exception as e:
            failed += 1
            if verbose:
                print(f"  ✗ {row['name']}: {e}")

    return {"completed": completed, "failed": failed}


def main():
    parser = argparse.ArgumentParser(description="Volleyball Enrichment Pipeline")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max teams for Flashscore step")
    parser.add_argument("--skip-flashscore", action="store_true", help="Skip Flashscore step")
    parser.add_argument("--skip-rich", action="store_true", help="Skip rich completion step")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    print(f"\n{'='*60}")
    print(f"  VOLLEYBALL ENRICHMENT PIPELINE — {args.date}")
    print(f"{'='*60}\n")

    status_before = get_volleyball_enrichment_status(args.date)
    print(f"Before: {status_before['enriched']}/{status_before['total_teams']} teams enriched "
          f"({status_before['coverage_pct']}%)\n")

    # Step 1: Flashscore
    fs_summary = {}
    if not args.skip_flashscore:
        print("── Step 1: Flashscore Enrichment ──")
        fs_summary = run_flashscore_enrichment(args.date, args.verbose, args.limit)
        print(f"  Flashscore: {fs_summary.get('completed', 0)} enriched, "
              f"{fs_summary.get('failed', 0)} failed\n")

    # Step 2: Rich completion (API-volleyball + Sofascore fallback)
    rc_summary = {}
    if not args.skip_rich:
        print("── Step 2: Rich Completion (API-Volleyball + Sofascore) ──")
        rc_summary = run_rich_completion(args.date, args.verbose)
        print(f"  Rich completion: {rc_summary.get('completed', 0)} enriched, "
              f"{rc_summary.get('failed', 0)} failed\n")

    # Post-check
    status_after = get_volleyball_enrichment_status(args.date)
    improvement = status_after['coverage_pct'] - status_before['coverage_pct']

    print(f"{'='*60}")
    print(f"  After: {status_after['enriched']}/{status_after['total_teams']} teams enriched "
          f"({status_after['coverage_pct']}%)")
    print(f"  Improvement: +{improvement:.1f}%")
    print(f"{'='*60}")

    summary = {
        "before_coverage": status_before['coverage_pct'],
        "after_coverage": status_after['coverage_pct'],
        "flashscore": fs_summary,
        "rich_completion": rc_summary,
        "improvement": improvement,
    }
    print(f"\nAGENT_SUMMARY:{json.dumps(summary)}")


if __name__ == "__main__":
    main()
