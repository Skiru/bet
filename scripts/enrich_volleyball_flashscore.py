#!/usr/bin/env python3
"""Volleyball Flashscore enrichment — fetches per-match stats for volleyball teams.

Uses VolleyballFlashscoreScraper to get L10 match-by-match stats and stores them
in team_form with source='flashscore-volleyball'.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/enrich_volleyball_flashscore.py --date 2026-05-26 --verbose
    PYTHONPATH=src .venv/bin/python scripts/enrich_volleyball_flashscore.py --date 2026-05-26 --limit 20
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from bet.db.connection import get_db
from bet.db.repositories import SportRepo, TeamRepo, StatsRepo
from bet.db.models import TeamForm
from bet.scrapers.flashscore import VolleyballFlashscoreScraper

logger = logging.getLogger(__name__)

DEFAULT_BUDGET = 100  # Max Flashscore requests per run


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_volleyball_teams_for_date(date: str) -> list[dict]:
    """Get all volleyball teams from today's fixtures needing enrichment."""
    teams = []
    with get_db() as conn:
        sport_repo = SportRepo(conn)
        volleyball = sport_repo.get_by_name("volleyball")
        if not volleyball:
            return []

        rows = conn.execute(
            """
            SELECT DISTINCT t.id, t.name FROM teams t
            JOIN fixtures f ON (f.home_team_id = t.id OR f.away_team_id = t.id)
            WHERE f.sport_id = ? AND date(f.kickoff) = ?
            """,
            (volleyball.id, date),
        ).fetchall()

        for row in rows:
            name = row["name"]
            # Check if we already have fresh flashscore data
            existing = conn.execute(
                """SELECT COUNT(*) FROM team_form 
                   WHERE team_id = ? AND sport_id = ? AND source = 'flashscore-volleyball'
                   AND updated_at > datetime('now', '-24 hours')""",
                (row["id"], volleyball.id),
            ).fetchone()[0]
            
            teams.append({
                "team_id": row["id"],
                "name": name,
                "has_fresh_data": existing > 0,
            })

    return teams


def store_team_match_stats(team_id: int, sport_id: int, stats: dict[str, list[float]]) -> int:
    """Store per-match L10 stats in team_form from Flashscore data."""
    if not stats:
        return 0
    
    stored = 0
    # Volleyball stat keys we want to store
    stat_keys_to_store = ["total_points", "aces", "blocks", "errors"]
    
    with get_db() as conn:
        stats_repo = StatsRepo(conn)
        
        for stat_key in stat_keys_to_store:
            values = stats.get(stat_key, [])
            if not values:
                continue
            
            l10 = [float(v) for v in values[:10]]
            l5 = l10[:5]
            l10_avg = round(sum(l10) / len(l10), 2) if l10 else None
            l5_avg = round(sum(l5) / len(l5), 2) if l5 else None
            
            form = TeamForm(
                id=None,
                team_id=team_id,
                sport_id=sport_id,
                stat_key=stat_key,
                l10_values=l10,
                l5_values=l5,
                l10_avg=l10_avg,
                l5_avg=l5_avg,
                h2h_values=None,
                h2h_opponent_id=None,
                trend="stable",
                updated_at=_now_iso(),
                source="flashscore-volleyball",
            )
            stats_repo.save_team_form(form)
            stored += 1
        
        conn.commit()
    
    return stored


def main():
    parser = argparse.ArgumentParser(description="Volleyball Flashscore Enrichment")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max teams to process")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="Max Flashscore requests")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    print(f"\n{'='*60}")
    print(f"  VOLLEYBALL FLASHSCORE ENRICHMENT — {args.date}")
    print(f"{'='*60}\n")

    # Get teams needing enrichment
    teams = get_volleyball_teams_for_date(args.date)
    needs_enrichment = [t for t in teams if not t["has_fresh_data"]]
    
    if args.limit > 0:
        needs_enrichment = needs_enrichment[:args.limit]

    print(f"Total volleyball teams: {len(teams)}")
    print(f"Already have fresh Flashscore data: {len(teams) - len(needs_enrichment)}")
    print(f"Need enrichment: {len(needs_enrichment)}")
    print(f"Budget: {args.budget} requests\n")

    if not needs_enrichment:
        print("Nothing to enrich — all teams have fresh data.")
        summary = {"eligible": len(teams), "completed": 0, "skipped": len(teams), "failed": 0}
        print(f"\nAGENT_SUMMARY:{json.dumps(summary)}")
        return

    # Initialize scraper
    scraper = VolleyballFlashscoreScraper()
    
    # Get sport_id
    with get_db() as conn:
        sport_repo = SportRepo(conn)
        volleyball = sport_repo.get_by_name("volleyball")
        if not volleyball:
            print("[ERROR] 'volleyball' sport not found in DB — run discover_events.py first")
            sys.exit(1)
        sport_id = volleyball.id

    completed = 0
    failed = 0
    requests_used = 0

    for i, team in enumerate(needs_enrichment, 1):
        if requests_used >= args.budget:
            print(f"\n[BUDGET EXHAUSTED] Used {requests_used}/{args.budget} requests")
            break

        print(f"[{i}/{len(needs_enrichment)}] {team['name']}...", end=" ")
        
        try:
            stats, error = scraper.fetch_team_stats(team["name"])
            requests_used += 1
            
            if stats:
                stored = store_team_match_stats(team["team_id"], sport_id, stats)
                print(f"✓ {len(stats)} stat keys, {stored} stored")
                completed += 1
            else:
                print(f"✗ {error or 'no stats found'}")
                failed += 1
        except Exception as e:
            print(f"✗ error: {e}")
            failed += 1

    # Summary
    skipped = len(teams) - len(needs_enrichment)
    summary = {
        "eligible": len(teams),
        "completed": completed,
        "failed": failed,
        "skipped": skipped,
        "requests_used": requests_used,
        "budget": args.budget,
    }

    print(f"\n{'='*60}")
    print(f"  RESULTS: {completed} enriched, {failed} failed, {skipped} skipped")
    print(f"  Requests used: {requests_used}/{args.budget}")
    print(f"{'='*60}")
    print(f"\nAGENT_SUMMARY:{json.dumps(summary)}")


if __name__ == "__main__":
    main()
