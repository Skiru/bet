#!/usr/bin/env python3
"""Tennis Flashscore enrichment — fetches per-match serve stats for tennis players.

Uses TennisFlashscoreScraper to get L10 match-by-match stats and stores them
in team_form with source='flashscore-tennis'.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/enrich_tennis_flashscore.py --date 2026-05-26 --verbose
    PYTHONPATH=src .venv/bin/python scripts/enrich_tennis_flashscore.py --date 2026-05-26 --limit 20
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
from bet.scrapers.flashscore import TennisFlashscoreScraper

logger = logging.getLogger(__name__)

DEFAULT_BUDGET = 100  # Max Flashscore requests per run


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_tennis_players_for_date(date: str) -> list[dict]:
    """Get all tennis players from today's fixtures needing enrichment."""
    players = []
    with get_db() as conn:
        sport_repo = SportRepo(conn)
        tennis = sport_repo.get_by_name("tennis")
        if not tennis:
            return []

        rows = conn.execute(
            """
            SELECT DISTINCT t.id, t.name FROM teams t
            JOIN fixtures f ON (f.home_team_id = t.id OR f.away_team_id = t.id)
            WHERE f.sport_id = ? AND date(f.kickoff) = ?
            """,
            (tennis.id, date),
        ).fetchall()

        for row in rows:
            # Skip doubles (contain " / " or " & ")
            name = row["name"]
            if " / " in name or " & " in name:
                continue
            
            # Check if we already have fresh flashscore data
            existing = conn.execute(
                """SELECT COUNT(*) FROM team_form 
                   WHERE team_id = ? AND sport_id = ? AND source = 'flashscore-tennis'
                   AND updated_at > datetime('now', '-24 hours')""",
                (row["id"], tennis.id),
            ).fetchone()[0]
            
            players.append({
                "team_id": row["id"],
                "name": name,
                "has_fresh_data": existing > 0,
            })

    return players


def store_player_match_stats(team_id: int, sport_id: int, matches: list[dict]) -> int:
    """Store per-match L10 stats in team_form from Flashscore data."""
    if not matches:
        return 0
    
    stored = 0
    stat_keys_to_store = ["total_games", "games_won", "sets_won", "total_sets"]
    
    with get_db() as conn:
        stats_repo = StatsRepo(conn)
        
        for stat_key in stat_keys_to_store:
            values = []
            for m in matches:
                val = m.get(stat_key)
                if val is not None:
                    values.append(float(val))
            
            if not values:
                continue
            
            l10 = values[:10]
            l5 = values[:5]
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
                source="flashscore-tennis",
            )
            stats_repo.save_team_form(form)
            stored += 1
        
        conn.commit()
    
    return stored


def main():
    parser = argparse.ArgumentParser(description="Tennis Flashscore Enrichment")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max players to process")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="Max Flashscore requests")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    print(f"\n{'='*60}")
    print(f"  TENNIS FLASHSCORE ENRICHMENT — {args.date}")
    print(f"{'='*60}\n")

    # Get players needing enrichment
    players = get_tennis_players_for_date(args.date)
    needs_enrichment = [p for p in players if not p["has_fresh_data"]]
    
    if args.limit > 0:
        needs_enrichment = needs_enrichment[:args.limit]

    print(f"Total tennis players: {len(players)}")
    print(f"Already have fresh Flashscore data: {len(players) - len(needs_enrichment)}")
    print(f"Need enrichment: {len(needs_enrichment)}")
    print(f"Budget: {args.budget} requests\n")

    if not needs_enrichment:
        print("Nothing to enrich — all players have fresh data.")
        summary = {"eligible": len(players), "completed": 0, "skipped": len(players), "failed": 0}
        print(f"\nAGENT_SUMMARY:{json.dumps(summary)}")
        return

    # Initialize scraper
    scraper = TennisFlashscoreScraper()
    
    # Get sport_id
    with get_db() as conn:
        sport_repo = SportRepo(conn)
        tennis = sport_repo.get_by_name("tennis")
        if not tennis:
            print("[ERROR] 'tennis' sport not found in DB — run discover_events.py first")
            sys.exit(1)
        sport_id = tennis.id

    completed = 0
    failed = 0
    requests_used = 0

    for i, player in enumerate(needs_enrichment, 1):
        if requests_used >= args.budget:
            print(f"\n[BUDGET EXHAUSTED] Used {requests_used}/{args.budget} requests")
            break

        print(f"[{i}/{len(needs_enrichment)}] {player['name']}...", end=" ")
        
        try:
            matches = scraper.fetch_player_recent_matches(player["name"], last_n=10)
            # Each player costs ~1 (results page) + N (match stats) requests
            requests_used += 1 + len(matches)
            
            if matches:
                stored = store_player_match_stats(player["team_id"], sport_id, matches)
                print(f"✓ {len(matches)} matches, {stored} stat keys stored")
                completed += 1
            else:
                print("✗ no matches found")
                failed += 1
        except Exception as e:
            print(f"✗ error: {e}")
            failed += 1

    # Summary
    skipped = len(players) - len(needs_enrichment)
    summary = {
        "eligible": len(players),
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