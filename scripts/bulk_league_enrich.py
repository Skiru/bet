#!/usr/bin/env python3
"""Bulk league-level enrichment via ESPN — gets all teams' stats per league.

Strategy: Instead of resolving individual team names (error-prone),
fetch standings for each league → get all team IDs → fetch their last fixtures + stats.

Usage:
    python3 scripts/bulk_league_enrich.py --date 2026-05-20 --verbose
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bet.api_clients.espn import (
    ESPNClient, ESPN_LEAGUES, COMPETITION_TO_ESPN_LEAGUE, ESPN_SPORT_MAP,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("bulk_league_enrich")

DB_PATH = Path(__file__).parent.parent / "betting" / "data" / "betting.db"


def get_competitions_for_date(date: str) -> list[dict]:
    """Get unique competitions from today's fixtures with team counts."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT c.name as competition, s.name as sport, COUNT(DISTINCT f.id) as fixture_count,
               GROUP_CONCAT(DISTINCT t.name) as team_names
        FROM fixtures f
        JOIN sports s ON f.sport_id = s.id
        JOIN competitions c ON f.competition_id = c.id
        JOIN teams t ON (t.id = f.home_team_id OR t.id = f.away_team_id)
        WHERE f.kickoff LIKE ?
        GROUP BY c.name, s.name
        ORDER BY fixture_count DESC
    """, (f"{date}%",)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resolve_league_code(competition: str, sport: str) -> str | None:
    """Map competition name to ESPN league code."""
    comp_lower = competition.lower().strip()
    # Direct match
    if comp_lower in COMPETITION_TO_ESPN_LEAGUE:
        return COMPETITION_TO_ESPN_LEAGUE[comp_lower]
    # Partial match
    for key, code in COMPETITION_TO_ESPN_LEAGUE.items():
        if key in comp_lower or comp_lower in key:
            return code
    # Try without common suffixes
    for suffix in [" - regular season", " - playoffs", " - qualification", " regular season"]:
        cleaned = comp_lower.replace(suffix, "").strip()
        if cleaned in COMPETITION_TO_ESPN_LEAGUE:
            return COMPETITION_TO_ESPN_LEAGUE[cleaned]
    return None


def enrich_league(sport: str, league_code: str, competition_name: str, verbose: bool = False) -> dict:
    """Enrich all teams in a league via ESPN stats.
    
    Returns: {"teams_found": N, "teams_enriched": N, "stats_written": N}
    """
    client = ESPNClient(sport=sport, league=league_code)
    
    # Get standings → team list with ESPN IDs
    standings = client.get_standings()
    if not standings:
        return {"teams_found": 0, "teams_enriched": 0, "stats_written": 0, "error": "no standings"}
    
    if verbose:
        log.info("  %s/%s: %d teams in standings", sport, league_code, len(standings))
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    
    teams_enriched = 0
    stats_written = 0
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    for entry in standings:
        team_name = entry.get("team_name", "")
        espn_team_id = entry.get("team_id", "")
        if not team_name or not espn_team_id:
            continue
        
        # Find this team in our DB
        team_row = conn.execute(
            "SELECT t.id FROM teams t JOIN sports s ON t.sport_id = s.id WHERE t.name = ? AND s.name = ?",
            (team_name, sport)
        ).fetchone()
        
        if not team_row:
            # Try fuzzy: check if any DB team name contains this name or vice versa
            fuzzy_rows = conn.execute(
                "SELECT t.id, t.name FROM teams t JOIN sports s ON t.sport_id = s.id WHERE s.name = ? AND (t.name LIKE ? OR ? LIKE '%' || t.name || '%')",
                (sport, f"%{team_name}%", team_name)
            ).fetchall()
            if fuzzy_rows:
                team_row = fuzzy_rows[0]
            else:
                continue
        
        db_team_id = team_row[0]
        
        # Check if already enriched (>=3 stats)
        existing_count = conn.execute(
            "SELECT COUNT(*) FROM team_form WHERE team_id = ? AND l5_avg IS NOT NULL",
            (db_team_id,)
        ).fetchone()[0]
        
        if existing_count >= 3:
            continue  # Already enriched
        
        # Get last 5 fixtures for this team
        try:
            fixtures = client.get_team_last_fixtures(espn_team_id, last_n=5)
        except Exception as e:
            if verbose:
                log.debug("  Fixtures failed for %s: %s", team_name, e)
            continue
        
        if not fixtures:
            continue
        
        # Get stats for each fixture
        stat_accum: dict[str, list[float]] = defaultdict(list)
        for fix in fixtures[:5]:
            fix_id = fix.get("id")
            if not fix_id:
                continue
            try:
                match_stats_list = client.get_fixture_stats(str(fix_id))
                if not match_stats_list:
                    continue
                ms = match_stats_list[0]
                stats = ms.stats if hasattr(ms, "stats") else {}
                
                # Determine which side this team is on
                home_name = ms.home_team_name if hasattr(ms, "home_team_name") else ""
                away_name = ms.away_team_name if hasattr(ms, "away_team_name") else ""
                side = _guess_side(team_name, home_name, away_name)
                
                for stat_key, side_vals in stats.items():
                    if isinstance(side_vals, dict) and side in side_vals:
                        val = side_vals[side]
                        if isinstance(val, (int, float)) and val >= 0:
                            stat_accum[stat_key].append(float(val))
            except Exception:
                continue
        
        if not stat_accum:
            continue
        
        # Write to team_form
        sport_id_row = conn.execute("SELECT id FROM sports WHERE name = ?", (sport,)).fetchone()
        sport_id = sport_id_row[0] if sport_id_row else None
        
        for stat_key, vals in stat_accum.items():
            if vals:
                avg = round(sum(vals) / len(vals), 2)
                vals_json = json.dumps(vals[:5])
                conn.execute("""
                    INSERT OR REPLACE INTO team_form (team_id, sport_id, stat_key, l5_avg, l5_values, updated_at, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (db_team_id, sport_id, stat_key, avg, vals_json, now, "espn"))
                stats_written += 1
        
        teams_enriched += 1
        conn.commit()
        
        if verbose and teams_enriched % 5 == 0:
            log.info("  %s: %d teams enriched, %d stats", league_code, teams_enriched, stats_written)
    
    conn.commit()
    conn.close()
    
    return {"teams_found": len(standings), "teams_enriched": teams_enriched, "stats_written": stats_written}


def _guess_side(team_name: str, home: str, away: str) -> str:
    tn = team_name.lower().split()
    h = home.lower()
    a = away.lower()
    home_score = sum(1 for w in tn if len(w) > 2 and w in h)
    away_score = sum(1 for w in tn if len(w) > 2 and w in a)
    return "home" if home_score >= away_score else "away"


def main():
    parser = argparse.ArgumentParser(description="Bulk league-level ESPN enrichment")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--sport", help="Filter by sport (default: all)")
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    competitions = get_competitions_for_date(args.date)
    log.info("Found %d competitions with fixtures on %s", len(competitions), args.date)
    
    total_enriched = 0
    total_stats = 0
    leagues_processed = 0
    leagues_skipped = 0
    
    for comp in competitions:
        sport = comp["sport"]
        competition_name = comp["competition"]
        
        if args.sport and sport != args.sport:
            continue
        
        # Skip tennis (individual sport, needs different approach)
        if sport == "tennis":
            continue
        
        league_code = resolve_league_code(competition_name, sport)
        if not league_code:
            if args.verbose:
                log.debug("  No ESPN league for: %s (%s)", competition_name, sport)
            leagues_skipped += 1
            continue
        
        log.info("Processing: %s → %s/%s (%d fixtures)", competition_name, sport, league_code, comp["fixture_count"])
        
        result = enrich_league(sport, league_code, competition_name, verbose=args.verbose)
        
        if result.get("teams_enriched", 0) > 0:
            log.info("  → enriched %d teams, %d stats written", result["teams_enriched"], result["stats_written"])
        
        total_enriched += result.get("teams_enriched", 0)
        total_stats += result.get("stats_written", 0)
        leagues_processed += 1
    
    log.info("=" * 60)
    log.info("DONE: %d leagues processed, %d skipped", leagues_processed, leagues_skipped)
    log.info("  Teams enriched: %d, Stats written: %d", total_enriched, total_stats)
    
    print("\nAGENT_SUMMARY:" + json.dumps({
        "verdict": "OK" if total_enriched > 50 else "PARTIAL",
        "leagues_processed": leagues_processed,
        "leagues_skipped": leagues_skipped,
        "teams_enriched": total_enriched,
        "stats_written": total_stats,
    }))


if __name__ == "__main__":
    main()
