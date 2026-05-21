#!/usr/bin/env python3
"""Bridge league_profiles → team_form for teams missing deep stats.

For teams playing today that only have "goals" data, applies league-average
values (corners, fouls, shots, yellow_cards, etc.) from league_profiles as 
baseline team_form entries.

Uses fuzzy competition name matching to map fixture competitions to
league_profiles competitions (which use different naming: "eng.1" vs "Premier League").

Usage:
    python3 scripts/bridge_league_to_team_form.py --date 2026-05-20 --sport football
    python3 scripts/bridge_league_to_team_form.py --date 2026-05-20 --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("bridge_lp")

DB_PATH = Path(__file__).parent.parent / "betting" / "data" / "betting.db"

# Map league_profiles competition names (ESPN/FBref style) to common fixture competition names
# Key = league_profiles comp name, Value = list of fixture competition names it should match
COMP_NAME_MAP = {
    # FBref/soccerdata style → common name patterns (EXACT matches only)
    "eng.1": ["English Premier League", "EPL"],
    "eng.2": ["EFL Championship", "Championship"],
    "eng.3": ["EFL League One", "League One"],
    "esp.1": ["La Liga", "LaLiga"],
    "esp.2": ["Segunda Division", "LaLiga2"],
    "ger.1": ["1. Bundesliga"],
    "ger.2": ["2. Bundesliga"],
    "ita.1": ["Serie A"],
    "ita.2": ["Serie B"],
    "fra.1": ["Ligue 1"],
    "fra.2": ["Ligue 2"],
    "ned.1": ["Eredivisie"],
    "ned.2": ["Eerste Divisie"],
    "por.1": ["Primeira Liga", "Liga Portugal"],
    "bel.1": ["Jupiler Pro League", "Pro League A"],
    "tur.1": ["Super Lig"],
    "sco.1": ["Scottish Premiership"],
    "aut.1": ["Austrian Bundesliga"],
    "gre.1": ["Greek Super League"],
    "den.1": ["Danish Superliga", "Superligaen"],
    "nor.1": ["Eliteserien"],
    "swe.1": ["Allsvenskan"],
    "aus.1": ["A-League Men", "A-League"],
    "jpn.1": ["J1 League", "J-League"],
    "bra.1": ["Brasileiro Serie A"],
    "arg.1": ["Liga Profesional"],
    "mex.1": ["Liga MX"],
    "usa.1": ["MLS", "Major League Soccer"],
    "col.1": ["Liga BetPlay"],
    "chn.1": ["Chinese Super League"],
    "rus.1": ["Russian Premier League"],
    "cyp.1": ["Cypriot First Division"],
    "rsa.1": ["Premier Soccer League", "PSL"],
    "ind.1": ["Indian Super League", "ISL"],
    "per.1": ["Liga 1 Peru"],
    "uefa.champions": ["Champions League", "UEFA Champions League"],
    "uefa.europa": ["Europa League", "UEFA Europa League"],
    "uefa.europa.conf": ["Conference League", "UEFA Europa Conference League"],
    "conmebol.libertadores": ["Copa Libertadores", "Libertadores"],
    "conmebol.sudamericana": ["Copa Sudamericana", "CONMEBOL Sudamericana"],
    # ESPN-style "Premier League" (id=2897) is English PL
    "Premier League": ["Premier League"],
}

# Stat keys we want to bridge (relevant for statistical betting markets)
TARGET_STAT_KEYS = [
    "corners", "fouls", "yellow_cards", "red_cards",
    "shots", "shots_on_target", "possession", "offsides", "saves",
    "accurate_passes", "pass_accuracy", "crosses", "blocked_shots",
    "clearances", "interceptions", "tackles",
]


def build_comp_mapping(conn: sqlite3.Connection) -> dict[int, int]:
    """Build mapping: fixture competition_id → league_profiles competition_id.
    
    Uses exact name matching first, then mapped aliases. No fuzzy/partial matching
    to avoid wrong associations (e.g. "FKF Premier League" ≠ "Premier League").
    """
    # Get all league_profiles competitions with corners data
    lp_comps = conn.execute("""
        SELECT DISTINCT c.id, c.name FROM league_profiles lp
        JOIN competitions c ON c.id = lp.competition_id
        WHERE lp.stat_key = 'corners'
    """).fetchall()
    
    # Build reverse lookup: alias → lp comp_id (exact matches only)
    alias_to_lp: dict[str, int] = {}
    lp_name_to_id: dict[str, int] = {}
    
    for lp_id, lp_name in lp_comps:
        lp_name_to_id[lp_name] = lp_id
        # Add mapped aliases
        if lp_name in COMP_NAME_MAP:
            for alias in COMP_NAME_MAP[lp_name]:
                alias_to_lp[alias.lower()] = lp_id
    
    # Get all fixture competitions
    fix_comps = conn.execute("""
        SELECT DISTINCT c.id, c.name FROM fixtures f
        JOIN competitions c ON c.id = f.competition_id
        JOIN sports s ON s.id = f.sport_id
        WHERE s.name = 'football'
    """).fetchall()
    
    # Map fixture competitions (exact match only)
    mapping: dict[int, int] = {}
    for fix_id, fix_name in fix_comps:
        fix_lower = fix_name.lower()
        # Try exact alias match
        if fix_lower in alias_to_lp:
            mapping[fix_id] = alias_to_lp[fix_lower]
            continue
        # Try exact lp_name match
        if fix_name in lp_name_to_id:
            mapping[fix_id] = lp_name_to_id[fix_name]
            continue
    
    return mapping


def get_teams_needing_bridge(conn: sqlite3.Connection, date: str, sport: str = "football") -> list[dict]:
    """Get teams playing today with only goals data (no corners/shots/fouls)."""
    rows = conn.execute("""
        SELECT DISTINCT t.id as team_id, t.name as team_name, 
               f.competition_id, s.id as sport_id
        FROM fixtures f
        JOIN teams t ON t.id IN (f.home_team_id, f.away_team_id)
        JOIN sports s ON s.id = f.sport_id
        WHERE s.name = ? AND f.kickoff LIKE ?
        AND (SELECT COUNT(DISTINCT stat_key) FROM team_form 
             WHERE team_id=t.id AND stat_key IN ('corners','shots','fouls','yellow_cards')) = 0
    """, (sport, f"{date}%")).fetchall()
    return [{"team_id": r[0], "team_name": r[1], "competition_id": r[2], "sport_id": r[3]} for r in rows]


def bridge_stats(conn: sqlite3.Connection, teams: list[dict], comp_mapping: dict[int, int], dry_run: bool = False) -> dict:
    """Write league-average stats to team_form for teams missing deep data."""
    now = datetime.now(timezone.utc).isoformat()
    written = 0
    skipped_no_mapping = 0
    skipped_no_data = 0
    
    for team in teams:
        comp_id = team["competition_id"]
        lp_comp_id = comp_mapping.get(comp_id)
        
        if not lp_comp_id:
            skipped_no_mapping += 1
            continue
        
        # Get league profile stats for this competition
        lp_data = conn.execute("""
            SELECT stat_key, avg_value, std_dev FROM league_profiles
            WHERE competition_id = ? AND stat_key IN ({})
        """.format(",".join("?" for _ in TARGET_STAT_KEYS)), 
            [lp_comp_id] + TARGET_STAT_KEYS
        ).fetchall()
        
        if not lp_data:
            skipped_no_data += 1
            continue
        
        for stat_key, avg_val, std_dev in lp_data:
            if avg_val is None:
                continue
            
            # Create synthetic L10/L5 values around the league average
            # Use std_dev to create realistic-looking variation
            avg = round(avg_val, 2)
            
            if not dry_run:
                conn.execute("""
                    INSERT OR IGNORE INTO team_form 
                    (team_id, sport_id, stat_key, l5_avg, l5_values, l10_avg, l10_values, updated_at, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    team["team_id"], team["sport_id"], stat_key,
                    avg, json.dumps([avg]),  # l5
                    avg, json.dumps([avg]),  # l10
                    now, "league-profile-baseline"
                ))
            written += 1
    
    if not dry_run:
        conn.commit()
    
    return {
        "written": written,
        "skipped_no_mapping": skipped_no_mapping,
        "skipped_no_data": skipped_no_data,
        "total_teams": len(teams),
        "mapped_competitions": len(comp_mapping),
    }


def main():
    parser = argparse.ArgumentParser(description="Bridge league_profiles to team_form")
    parser.add_argument("--date", required=True)
    parser.add_argument("--sport", default="football")
    parser.add_argument("--dry-run", action="store_true", help="Don't write, just report")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    
    # Build competition mapping
    comp_mapping = build_comp_mapping(conn)
    log.info("Competition mapping: %d fixture comps → league_profiles", len(comp_mapping))
    if args.verbose:
        for fix_id, lp_id in list(comp_mapping.items())[:10]:
            fix_name = conn.execute("SELECT name FROM competitions WHERE id=?", (fix_id,)).fetchone()
            lp_name = conn.execute("SELECT name FROM competitions WHERE id=?", (lp_id,)).fetchone()
            log.debug("  %s (id=%d) → %s (id=%d)", fix_name[0] if fix_name else "?", fix_id, lp_name[0] if lp_name else "?", lp_id)
    
    # Get teams needing data
    teams = get_teams_needing_bridge(conn, args.date, args.sport)
    log.info("Teams needing bridge: %d", len(teams))
    
    if not teams:
        print("AGENT_SUMMARY:" + json.dumps({"verdict": "OK", "message": "All teams have deep stats"}))
        conn.close()
        return
    
    # Bridge stats
    result = bridge_stats(conn, teams, comp_mapping, dry_run=args.dry_run)
    conn.close()
    
    log.info("=" * 60)
    log.info("RESULT: written=%d, no_mapping=%d, no_data=%d (dry_run=%s)",
             result["written"], result["skipped_no_mapping"], result["skipped_no_data"], args.dry_run)
    
    print("\nAGENT_SUMMARY:" + json.dumps({
        "verdict": "OK" if result["written"] > 0 else "PARTIAL",
        "stats_written": result["written"],
        "teams_processed": result["total_teams"],
        "skipped_no_mapping": result["skipped_no_mapping"],
        "skipped_no_data": result["skipped_no_data"],
        "competition_mappings": result["mapped_competitions"],
        "dry_run": args.dry_run,
    }))


if __name__ == "__main__":
    main()
