#!/usr/bin/env python3
"""Enrich esports teams with L10/L5/H2H data from VLR.gg + HLTV.

Fills the team_form table for CS2, Valorant, and Dota2 teams using
existing scraper infrastructure.

Usage:
    PYTHONPATH=src .venv/bin/python3 scripts/enrich_esports_stats.py --date 2026-05-25 --verbose
    PYTHONPATH=src .venv/bin/python3 scripts/enrich_esports_stats.py --date 2026-05-25 --sport valorant --verbose
    PYTHONPATH=src .venv/bin/python3 scripts/enrich_esports_stats.py --date 2026-05-25 --team "NAVI" --verbose

Sources:
    - VLR.gg: Valorant (HTTP — team stats, map pool, recent matches, rankings)
    - HLTV.org: CS2 (Playwright stealth — team stats, map pool, match history)
    - GosuGamers: Dota2 community predictions (HTTP)

Writes to DB:
    - team_form: stat_key per row (maps_won, map_win_rate, rounds_won_avg, win_rate_l10, etc.)
    - Each stat stored with l10_avg, l5_avg, l10_values, l5_values
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from bet.db.connection import get_db

logger = logging.getLogger(__name__)

SPORT_IDS = {"cs2": 498, "valorant": 500, "dota2": 499}
SPORT_NAMES = {498: "cs2", 499: "dota2", 500: "valorant"}


def get_esports_fixtures(date_str: str, sport_filter: str | None = None) -> list[dict]:
    """Get all esports fixtures for the target date from DB."""
    sport_ids = list(SPORT_IDS.values())
    if sport_filter:
        sport_ids = [SPORT_IDS[sport_filter]]

    placeholders = ",".join("?" * len(sport_ids))
    with get_db() as db:
        rows = db.execute(f"""
            SELECT f.id, f.sport_id, t1.id, t1.name, t2.id, t2.name, f.kickoff
            FROM fixtures f
            JOIN teams t1 ON f.home_team_id = t1.id
            JOIN teams t2 ON f.away_team_id = t2.id
            WHERE f.sport_id IN ({placeholders})
            AND f.kickoff LIKE ?
            ORDER BY f.sport_id, f.kickoff
        """, (*sport_ids, f"{date_str}%")).fetchall()

    fixtures = []
    for r in rows:
        fixtures.append({
            "fixture_id": r[0],
            "sport_id": r[1],
            "sport": SPORT_NAMES[r[1]],
            "home_team_id": r[2],
            "home_team": r[3],
            "away_team_id": r[4],
            "away_team": r[5],
            "kickoff": r[6],
        })
    return fixtures


def get_unique_teams(fixtures: list[dict]) -> list[dict]:
    """Extract unique (team_id, team_name, sport_id, sport) from fixtures."""
    seen = set()
    teams = []
    for f in fixtures:
        for side in ("home", "away"):
            team_id = f[f"{side}_team_id"]
            if team_id not in seen:
                seen.add(team_id)
                teams.append({
                    "team_id": team_id,
                    "team_name": f[f"{side}_team"],
                    "sport_id": f["sport_id"],
                    "sport": f["sport"],
                })
    return teams


def store_team_stats(team_id: int, sport_id: int, stats: dict, source: str):
    """Write team stats to team_form table. One row per stat_key."""
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as db:
        for stat_key, value in stats.items():
            if value is None:
                continue

            # For scalar stats (win_rate, map_win_rate, etc.) store as l10_avg
            if isinstance(value, (int, float)):
                l10_avg = float(value)
                l5_avg = float(value)
                l10_values = json.dumps([value])
                l5_values = json.dumps([value])
            elif isinstance(value, list):
                # List of values (e.g., match results)
                l10 = value[:10]
                l5 = value[:5]
                l10_avg = round(sum(l10) / len(l10), 2) if l10 else 0.0
                l5_avg = round(sum(l5) / len(l5), 2) if l5 else 0.0
                l10_values = json.dumps(l10)
                l5_values = json.dumps(l5)
            else:
                continue

            db.execute("""
                INSERT OR REPLACE INTO team_form
                    (team_id, sport_id, stat_key, l10_avg, l5_avg, l10_values, l5_values, updated_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (team_id, sport_id, stat_key, l10_avg, l5_avg, l10_values, l5_values, now, source))


def enrich_valorant_teams(teams: list[dict], verbose: bool = False) -> dict:
    """Enrich Valorant teams via VLR.gg (HTTP — fast)."""
    from bet.scrapers.vlr import VLRScraper

    vlr = VLRScraper()
    results = {"enriched": 0, "failed": 0, "skipped": 0}

    for i, team in enumerate(teams):
        team_name = team["team_name"]
        team_id = team["team_id"]
        sport_id = team["sport_id"]

        if verbose:
            logger.info("[%d/%d] VLR enriching: %s", i + 1, len(teams), team_name)

        try:
            stats = vlr.get_team_stats(team_name)
            if not stats:
                if verbose:
                    logger.warning("  MISS: %s — no VLR data", team_name)
                results["failed"] += 1
                continue

            # Store stats
            store_team_stats(team_id, sport_id, stats, source="vlr.gg")
            results["enriched"] += 1

            if verbose:
                logger.info("  OK: %s — %s", team_name, stats)

        except Exception as e:
            logger.warning("  ERROR enriching %s: %s", team_name, e)
            results["failed"] += 1

    return results


def enrich_cs2_teams(teams: list[dict], verbose: bool = False) -> dict:
    """Enrich CS2 teams via bo3.gg match detail pages (Playwright).
    
    Since HLTV search is blocked and bo3.gg search is 404, we use
    match detail pages which contain form, map winrates, H2H, and lineups.
    """
    from bet.scrapers.bo3gg import Bo3GGScraper

    results = {"enriched": 0, "failed": 0, "skipped": 0}

    with Bo3GGScraper() as scraper:
        # Get current CS2 matches from bo3.gg
        if verbose:
            logger.info("Fetching CS2 match list from bo3.gg...")
        matches = scraper.get_cs2_matches_with_odds()
        if verbose:
            logger.info("Found %d CS2 matches on bo3.gg", len(matches))

        if not matches:
            logger.warning("No CS2 matches found on bo3.gg")
            return results

        # Build team name → match URL mapping
        team_match_urls: dict[str, str] = {}
        for m in matches:
            home = m["home_team"].strip()
            away = m["away_team"].strip()
            url = m["match_url"]
            # Clean team names (bo3.gg adds prefixes like "Live ")
            home_clean = re.sub(r"^(Live\s+)", "", home).strip()
            away_clean = re.sub(r"^(Live\s+)", "", away).strip()
            # Remove single-letter prefix artifacts and trailing markers
            home_clean = re.sub(r"^[a-z]\s+", "", home_clean).strip()
            away_clean = re.sub(r"^[a-z]\s+", "", away_clean).strip()
            home_clean = re.sub(r"\s+\d+\s*[-–]\s*$", "", home_clean).strip()
            away_clean = re.sub(r"\s+\d+\s*[-–]\s*$", "", away_clean).strip()

            if home_clean:
                team_match_urls[home_clean.lower()] = url
            if away_clean:
                team_match_urls[away_clean.lower()] = url

        if verbose:
            logger.info("Team→URL map: %d entries", len(team_match_urls))

        # Track which match URLs we've already fetched (avoid duplicate fetches)
        fetched_details: dict[str, dict] = {}

        for i, team in enumerate(teams):
            team_name = team["team_name"]
            team_id = team["team_id"]
            sport_id = team["sport_id"]

            if verbose:
                logger.info("[%d/%d] CS2 enriching: %s", i + 1, len(teams), team_name)

            # Find match URL for this team
            match_url = None
            team_lower = team_name.lower()
            for key, url in team_match_urls.items():
                if team_lower in key or key in team_lower:
                    match_url = url
                    break
            # Try partial matching
            if not match_url:
                for key, url in team_match_urls.items():
                    # Try first word match
                    first_word = team_lower.split()[0] if team_lower.split() else ""
                    if first_word and len(first_word) > 2 and first_word in key:
                        match_url = url
                        break

            if not match_url:
                if verbose:
                    logger.warning("  MISS: %s — not found on bo3.gg", team_name)
                results["failed"] += 1
                continue

            try:
                # Fetch detail (with caching)
                if match_url not in fetched_details:
                    detail = scraper.get_cs2_match_detail(match_url)
                    fetched_details[match_url] = detail
                else:
                    detail = fetched_details[match_url]

                if not detail:
                    results["failed"] += 1
                    continue

                # Determine if this team is home or away
                is_home = team_lower in detail.get("home_team", "").lower()

                stats = {}

                # ML odds → implied win probability (stored separately, NOT as win_rate_l10)
                ml_odds = detail.get("ml_odds", {})
                if is_home and ml_odds.get("home"):
                    implied_wr = round(1 / ml_odds["home"] * 100, 1)
                    stats["implied_win_prob"] = implied_wr
                elif not is_home and ml_odds.get("away"):
                    implied_wr = round(1 / ml_odds["away"] * 100, 1)
                    stats["implied_win_prob"] = implied_wr

                # Map winrates
                map_wr = detail.get("map_winrate_home" if is_home else "map_winrate_away", {})
                if map_wr:
                    avg_map_wr = round(sum(map_wr.values()) / len(map_wr), 1)
                    stats["map_win_rate"] = avg_map_wr
                    stats["maps_played"] = len(map_wr)

                # Form
                form = detail.get("form_home" if is_home else "form_away", [])
                if form:
                    wins = sum(1 for x in form if x == "W")
                    stats["win_rate_l10"] = round(wins / len(form) * 100, 1)

                # Lineups count (as data quality indicator)
                lineups = detail.get("lineups_home" if is_home else "lineups_away", [])
                if lineups:
                    stats["roster_size"] = len(lineups)

                if stats:
                    store_team_stats(team_id, sport_id, stats, source="bo3.gg")
                    results["enriched"] += 1
                    if verbose:
                        logger.info("  OK: %s — %s", team_name, stats)
                else:
                    results["failed"] += 1

            except Exception as e:
                logger.warning("  ERROR enriching %s: %s", team_name, e)
                results["failed"] += 1

    return results


def enrich_dota2_teams(teams: list[dict], verbose: bool = False) -> dict:
    """Enrich Dota2 teams — limited sources. Try GosuGamers or web search."""
    import requests
    from bs4 import BeautifulSoup

    results = {"enriched": 0, "failed": 0, "skipped": 0}
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    for i, team in enumerate(teams):
        team_name = team["team_name"]
        team_id = team["team_id"]
        sport_id = team["sport_id"]

        if verbose:
            logger.info("[%d/%d] Dota2 enriching: %s", i + 1, len(teams), team_name)

        try:
            # Try Liquipedia API for Dota2 team data
            search_url = f"https://liquipedia.net/dota2/api.php?action=opensearch&search={team_name}&limit=1&format=json"
            resp = requests.get(search_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data and len(data) >= 4 and data[3]:
                    # Found on Liquipedia — but do NOT store fake 50% win rate.
                    # Only store a presence marker without fabricated stats.
                    # Real stats should come from OpenDota API or match results.
                    if verbose:
                        logger.info("  FOUND: %s on Liquipedia (no stats stored — no real data)", team_name)
                    results.setdefault("skipped", 0)
                    results["skipped"] += 1
                    continue

            results["failed"] += 1
            if verbose:
                logger.warning("  MISS: %s — no Dota2 data found", team_name)

        except Exception as e:
            logger.warning("  ERROR enriching %s: %s", team_name, e)
            results["failed"] += 1

        time.sleep(2)  # Rate limit

    return results


def enrich_h2h(fixtures: list[dict], verbose: bool = False) -> dict:
    """Enrich H2H data for matchups using VLR (Valorant) and HLTV (CS2)."""
    from bet.scrapers.vlr import VLRScraper
    from bet.scrapers.hltv import HLTVScraper

    now = datetime.now(timezone.utc).isoformat()
    results = {"enriched": 0, "failed": 0}

    vlr = VLRScraper()
    hltv_instance = None

    for i, f in enumerate(fixtures):
        sport = f["sport"]
        home = f["home_team"]
        away = f["away_team"]

        if verbose:
            logger.info("[%d/%d] H2H: %s vs %s (%s)", i + 1, len(fixtures), home, away, sport)

        try:
            h2h_data = None
            if sport == "valorant":
                h2h_data = vlr.get_h2h(home, away)
            elif sport == "cs2":
                if hltv_instance is None:
                    hltv_instance = HLTVScraper()
                h2h_data = hltv_instance.get_h2h(home, away)

            if h2h_data and h2h_data.get("matches_found", 0) > 0:
                home_team_id = f["home_team_id"]
                away_team_id = f["away_team_id"]
                sport_id = f["sport_id"]

                h2h_json = json.dumps(h2h_data)
                with get_db() as db:
                    db.execute("""
                        INSERT OR REPLACE INTO team_form
                            (team_id, sport_id, stat_key, l10_avg, l5_avg,
                             h2h_values, h2h_opponent_id, updated_at, source)
                        VALUES (?, ?, 'h2h', ?, ?, ?, ?, ?, ?)
                    """, (
                        home_team_id, sport_id,
                        h2h_data.get("team_a_wins", 0),
                        h2h_data.get("team_a_wins", 0),
                        h2h_json, away_team_id, now,
                        "vlr.gg" if sport == "valorant" else "hltv.org"
                    ))
                results["enriched"] += 1
                if verbose:
                    logger.info("  OK: %s", h2h_data)
            else:
                results["failed"] += 1

        except Exception as e:
            logger.warning("  H2H ERROR: %s vs %s: %s", home, away, e)
            results["failed"] += 1

    if hltv_instance:
        hltv_instance.close()

    return results


def main():
    parser = argparse.ArgumentParser(description="Enrich esports team data")
    parser.add_argument("--date", required=True, help="Target date (YYYY-MM-DD)")
    parser.add_argument("--sport", choices=["cs2", "valorant", "dota2"], help="Filter by sport")
    parser.add_argument("--team", help="Enrich only this team (partial match)")
    parser.add_argument("--h2h", action="store_true", help="Also enrich H2H data")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be enriched")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info("=== Esports Enrichment: %s ===", args.date)

    # Get fixtures
    fixtures = get_esports_fixtures(args.date, args.sport)
    logger.info("Found %d esports fixtures", len(fixtures))

    if not fixtures:
        logger.warning("No esports fixtures found for %s", args.date)
        sys.exit(0)

    # Get unique teams
    all_teams = get_unique_teams(fixtures)
    logger.info("Unique teams to enrich: %d", len(all_teams))

    # Filter by team name if specified
    if args.team:
        all_teams = [t for t in all_teams if args.team.lower() in t["team_name"].lower()]
        logger.info("Filtered to %d teams matching '%s'", len(all_teams), args.team)

    if args.dry_run:
        print(f"\n{'='*60}")
        print(f"DRY RUN — would enrich {len(all_teams)} teams:")
        for sport in ("valorant", "cs2", "dota2"):
            sport_teams = [t for t in all_teams if t["sport"] == sport]
            if sport_teams:
                print(f"\n  {sport.upper()} ({len(sport_teams)} teams):")
                for t in sport_teams:
                    print(f"    - {t['team_name']} (id={t['team_id']})")
        sys.exit(0)

    # Split by sport and enrich
    val_teams = [t for t in all_teams if t["sport"] == "valorant"]
    cs2_teams = [t for t in all_teams if t["sport"] == "cs2"]
    dota2_teams = [t for t in all_teams if t["sport"] == "dota2"]

    total_results = {"enriched": 0, "failed": 0, "skipped": 0}

    # Valorant (fast — HTTP)
    if val_teams:
        logger.info("\n--- Valorant (%d teams via VLR.gg) ---", len(val_teams))
        val_results = enrich_valorant_teams(val_teams, args.verbose)
        logger.info("Valorant: enriched=%d, failed=%d", val_results["enriched"], val_results["failed"])
        for k in total_results:
            total_results[k] += val_results.get(k, 0)

    # CS2 (slower — Playwright/HLTV)
    if cs2_teams:
        logger.info("\n--- CS2 (%d teams via HLTV.org) ---", len(cs2_teams))
        cs2_results = enrich_cs2_teams(cs2_teams, args.verbose)
        logger.info("CS2: enriched=%d, failed=%d", cs2_results["enriched"], cs2_results["failed"])
        for k in total_results:
            total_results[k] += cs2_results.get(k, 0)

    # Dota2 (limited)
    if dota2_teams:
        logger.info("\n--- Dota2 (%d teams via Liquipedia) ---", len(dota2_teams))
        dota2_results = enrich_dota2_teams(dota2_teams, args.verbose)
        logger.info("Dota2: enriched=%d, failed=%d", dota2_results["enriched"], dota2_results["failed"])
        for k in total_results:
            total_results[k] += dota2_results.get(k, 0)

    # H2H enrichment
    if args.h2h:
        logger.info("\n--- H2H enrichment ---")
        h2h_results = enrich_h2h(fixtures, args.verbose)
        logger.info("H2H: enriched=%d, failed=%d", h2h_results["enriched"], h2h_results["failed"])

    # Summary
    print(f"\n{'='*60}")
    print(f"AGENT_SUMMARY: {json.dumps(total_results)}")
    print(f"Total: enriched={total_results['enriched']}/{len(all_teams)} teams")
    print(f"  Valorant: {len(val_teams)} teams")
    print(f"  CS2: {len(cs2_teams)} teams")
    print(f"  Dota2: {len(dota2_teams)} teams")
    if total_results["failed"] > 0:
        print(f"  Failed: {total_results['failed']}")


if __name__ == "__main__":
    main()
