"""Fetch enriched league standings from ESPN APIs.

Usage:
    python3 scripts/fetch_espn_standings.py --date 2026-05-07
    python3 scripts/fetch_espn_standings.py --sports football,basketball,hockey
    python3 scripts/fetch_espn_standings.py --league eng.1

Output: betting/data/stats_cache/espn/{sport}/{league}/standings.json
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

CACHE_DIR = Path(__file__).parent.parent / "betting" / "data" / "stats_cache"

# Standings endpoint differs per sport type
# Soccer: site.api.espn.com/apis/v2/sports/soccer/{league}/standings
# US sports: site.api.espn.com/apis/site/v2/sports/{sport}/{league}/standings
SOCCER_STANDINGS_BASE = "https://site.api.espn.com/apis/v2/sports/soccer"
US_STANDINGS_BASE = "https://site.api.espn.com/apis/site/v2/sports"

SPORT_MAP = {
    "football": "soccer",
    "basketball": "basketball",
    "hockey": "hockey",
    "baseball": "baseball",
}

# Default leagues per sport to fetch when no specific league is given
DEFAULT_LEAGUES = {
    "football": ["eng.1", "esp.1", "ger.1", "ita.1", "fra.1", "pol.1", "ned.1", "por.1"],
    "basketball": ["nba"],
    "hockey": ["nhl"],
    "baseball": ["mlb"],
}

TIMEOUT = 15
MAX_RETRIES = 3
BACKOFF_BASE = 1


def _request(url: str, params: dict | None = None) -> dict:
    """Make HTTP request with retries."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                url,
                params=params,
                headers={"Accept": "application/json"},
                timeout=TIMEOUT,
            )
            if response.status_code == 404:
                return {}
            if response.status_code == 429:
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))
                    continue
                return {}
            if response.status_code >= 400:
                return {}
            return response.json()
        except requests.exceptions.RequestException:
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))
    return {}


def _get_stat(stats: list, name: str) -> str:
    """Extract a stat value by name from ESPN stats array."""
    for stat in stats:
        if stat.get("name") == name:
            return stat.get("displayValue", stat.get("value", ""))
    return ""


def _parse_int(value: str) -> int:
    """Safely parse an integer from a string."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def fetch_soccer_standings(league: str) -> list[dict]:
    """Fetch soccer standings using the /apis/v2/ endpoint."""
    url = f"{SOCCER_STANDINGS_BASE}/{league}/standings"
    data = _request(url)
    if not data:
        return []

    teams = []
    children = data.get("children", [])
    for group in children:
        standings = group.get("standings", {})
        entries = standings.get("entries", [])
        for entry in entries:
            team_info = entry.get("team", {})
            stats = entry.get("stats", [])

            team = {
                "name": team_info.get("displayName", ""),
                "id": team_info.get("id", ""),
                "rank": _parse_int(_get_stat(stats, "rank")),
                "wins": _parse_int(_get_stat(stats, "wins")),
                "draws": _parse_int(_get_stat(stats, "ties")),
                "losses": _parse_int(_get_stat(stats, "losses")),
                "games_played": _parse_int(_get_stat(stats, "gamesPlayed")),
                "goals_for": _parse_int(_get_stat(stats, "pointsFor")),
                "goals_against": _parse_int(_get_stat(stats, "pointsAgainst")),
                "goal_diff": _parse_int(_get_stat(stats, "goalDifference")),
                "points": _parse_int(_get_stat(stats, "points")),
                "form": _get_stat(stats, "form"),
                "streak": _get_stat(stats, "streak"),
                "home": {
                    "wins": _parse_int(_get_stat(stats, "homeWins")),
                    "draws": _parse_int(_get_stat(stats, "homeTies")),
                    "losses": _parse_int(_get_stat(stats, "homeLosses")),
                },
                "away": {
                    "wins": _parse_int(_get_stat(stats, "awayWins")),
                    "draws": _parse_int(_get_stat(stats, "awayTies")),
                    "losses": _parse_int(_get_stat(stats, "awayLosses")),
                },
                "group": group.get("name", ""),
            }
            teams.append(team)
    return teams


def fetch_us_sport_standings(sport_slug: str, league: str) -> list[dict]:
    """Fetch US sport standings using the /site/v2/ endpoint."""
    url = f"{US_STANDINGS_BASE}/{sport_slug}/{league}/standings"
    data = _request(url)
    if not data:
        return []

    teams = []
    children = data.get("children", [])
    for group in children:
        standings = group.get("standings", {})
        entries = standings.get("entries", [])
        for entry in entries:
            team_info = entry.get("team", {})
            stats = entry.get("stats", [])

            team = {
                "name": team_info.get("displayName", ""),
                "id": team_info.get("id", ""),
                "rank": _parse_int(_get_stat(stats, "playoffSeed"))
                or _parse_int(_get_stat(stats, "rank")),
                "wins": _parse_int(_get_stat(stats, "wins")),
                "draws": 0,
                "losses": _parse_int(_get_stat(stats, "losses")),
                "games_played": _parse_int(_get_stat(stats, "gamesPlayed")),
                "goals_for": 0,
                "goals_against": 0,
                "goal_diff": 0,
                "points": _parse_int(_get_stat(stats, "points")),
                "win_pct": _get_stat(stats, "winPercent"),
                "streak": _get_stat(stats, "streak"),
                "differential": _get_stat(stats, "differential"),
                "form": "",
                "home": {
                    "wins": _parse_int(_get_stat(stats, "homeWins")),
                    "draws": 0,
                    "losses": _parse_int(_get_stat(stats, "homeLosses")),
                },
                "away": {
                    "wins": _parse_int(_get_stat(stats, "awayWins")),
                    "draws": 0,
                    "losses": _parse_int(_get_stat(stats, "awayLosses")),
                },
                "conference": group.get("name", ""),
            }
            teams.append(team)
    return teams


def fetch_standings(sport: str, league: str) -> list[dict]:
    """Fetch standings for a given sport and league."""
    slug = SPORT_MAP.get(sport, sport)
    if slug == "soccer":
        return fetch_soccer_standings(league)
    return fetch_us_sport_standings(slug, league)


def save_standings(sport: str, league: str, teams: list[dict], date: str) -> Path:
    """Save standings to cache file."""
    slug = SPORT_MAP.get(sport, sport)
    out_dir = CACHE_DIR / "espn" / slug / league
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "standings.json"

    payload = {
        "sport": sport,
        "league": league,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "date": date,
        "source": "espn-standings",
        "teams": teams,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _persist_standings_to_db(sport: str, league: str, teams: list[dict]) -> int:
    """Persist standings data to SQLite database."""
    try:
        from bet.db.connection import get_db
        from bet.db.schema import init_db
        from bet.db.models import Standing
        from bet.db.repositories import StandingRepo
    except ImportError:
        return 0

    db_path = Path(__file__).parent.parent / "betting" / "data" / "betting.db"
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    try:
        with get_db(db_path) as conn:
            init_db(conn)
            standing_repo = StandingRepo(conn)

            # Get sport_id
            sport_row = conn.execute("SELECT id FROM sports WHERE name = ?", (sport,)).fetchone()
            if not sport_row:
                return 0
            sport_id = sport_row["id"]

            # Get or create competition
            comp_row = conn.execute(
                "SELECT id FROM competitions WHERE name = ? AND sport_id = ?",
                (league, sport_id),
            ).fetchone()
            if not comp_row:
                conn.execute(
                    "INSERT INTO competitions (name, sport_id, country) VALUES (?, ?, ?)",
                    (league, sport_id, ""),
                )
                comp_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            else:
                comp_id = comp_row["id"]

            for team_data in teams:
                team_name = team_data.get("name", "")
                if not team_name:
                    continue

                # Get or create team
                team_row = conn.execute(
                    "SELECT id FROM teams WHERE name = ? AND sport_id = ?",
                    (team_name, sport_id),
                ).fetchone()
                if not team_row:
                    conn.execute(
                        "INSERT INTO teams (name, sport_id, competition_id) VALUES (?, ?, ?)",
                        (team_name, sport_id, comp_id),
                    )
                    team_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                else:
                    team_id = team_row["id"]

                standing = Standing(
                    id=None,
                    competition_id=comp_id,
                    team_id=team_id,
                    season=team_data.get("season", ""),
                    rank=team_data.get("rank"),
                    wins=team_data.get("wins", 0),
                    draws=team_data.get("draws", 0),
                    losses=team_data.get("losses", 0),
                    goals_for=team_data.get("gf", team_data.get("points_for", 0)),
                    goals_against=team_data.get("ga", team_data.get("points_against", 0)),
                    goal_diff=team_data.get("gd", team_data.get("goal_diff", 0)),
                    points=team_data.get("points", 0),
                    form=team_data.get("form", ""),
                    home_wins=team_data.get("home_wins", 0),
                    home_draws=team_data.get("home_draws", 0),
                    home_losses=team_data.get("home_losses", 0),
                    away_wins=team_data.get("away_wins", 0),
                    away_draws=team_data.get("away_draws", 0),
                    away_losses=team_data.get("away_losses", 0),
                    streak=team_data.get("streak", ""),
                    source="espn",
                    updated_at=now,
                )
                standing_repo.upsert(standing)
                count += 1

            conn.commit()
    except Exception as e:
        print(f"  [DB] Error: {e}")
    return count


def main():
    parser = argparse.ArgumentParser(description="Fetch ESPN league standings")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Date context (YYYY-MM-DD)")
    parser.add_argument("--sports", default=None, help="Comma-separated sports to fetch (default: all)")
    parser.add_argument("--league", default=None, help="Specific league slug (e.g., eng.1, nba)")
    args = parser.parse_args()

    # Determine which sport/league combos to fetch
    if args.league:
        # Infer sport from league
        sport = None
        for s, leagues in DEFAULT_LEAGUES.items():
            if args.league in leagues:
                sport = s
                break
        if not sport:
            # Default to football for unknown leagues (most common)
            sport = "football"
        combos = [(sport, args.league)]
    elif args.sports:
        sports_list = [s.strip() for s in args.sports.split(",")]
        combos = []
        for sport in sports_list:
            for league in DEFAULT_LEAGUES.get(sport, []):
                combos.append((sport, league))
    else:
        combos = []
        for sport, leagues in DEFAULT_LEAGUES.items():
            for league in leagues:
                combos.append((sport, league))

    print(f"Fetching standings for {len(combos)} sport/league combos (date: {args.date})")
    total_teams = 0
    errors = []

    for sport, league in combos:
        teams = fetch_standings(sport, league)
        if teams:
            out_path = save_standings(sport, league, teams, args.date)
            print(f"  ✓ {sport}/{league}: {len(teams)} teams → {out_path.relative_to(Path.cwd())}")
            db_count = _persist_standings_to_db(sport, league, teams)
            if db_count:
                print(f"      [DB] {db_count} standings persisted")
            total_teams += len(teams)
        else:
            errors.append(f"{sport}/{league}")
            print(f"  ✗ {sport}/{league}: no data")

    print(f"\nDone: {total_teams} teams from {len(combos) - len(errors)}/{len(combos)} leagues")
    if errors:
        print(f"Failed: {', '.join(errors)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
