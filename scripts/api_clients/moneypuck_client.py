"""MoneyPuck CSV client — NHL advanced team stats (xG, Corsi, Fenwick).

MoneyPuck provides free CSV data at:
  https://moneypuck.com/moneypuck/playerData/seasonSummary/{season}/{type}/teams.csv

No API key required. No Cloudflare protection.
Columns (102): xGoalsPercentage, corsiPercentage, fenwickPercentage, shots, goals,
high-danger chances, rebounds, scoring chances, etc.
"""

import csv
import io
import json
import time
from pathlib import Path

import requests

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "betting" / "data" / "moneypuck.com"
BASE_URL = "https://moneypuck.com/moneypuck/playerData/seasonSummary"
CACHE_TTL_HOURS = 12

# MoneyPuck abbreviation → full team name mapping (NHL)
TEAM_NAMES = {
    "ANA": "Anaheim Ducks", "ARI": "Arizona Coyotes", "BOS": "Boston Bruins",
    "BUF": "Buffalo Sabres", "CAR": "Carolina Hurricanes", "CBJ": "Columbus Blue Jackets",
    "CGY": "Calgary Flames", "CHI": "Chicago Blackhawks", "COL": "Colorado Avalanche",
    "DAL": "Dallas Stars", "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers",
    "FLA": "Florida Panthers", "LAK": "Los Angeles Kings", "MIN": "Minnesota Wild",
    "MTL": "Montreal Canadiens", "NJD": "New Jersey Devils", "NSH": "Nashville Predators",
    "NYI": "New York Islanders", "NYR": "New York Rangers", "OTT": "Ottawa Senators",
    "PHI": "Philadelphia Flyers", "PIT": "Pittsburgh Penguins", "SJS": "San Jose Sharks",
    "SEA": "Seattle Kraken", "STL": "St. Louis Blues", "TBL": "Tampa Bay Lightning",
    "TOR": "Toronto Maple Leafs", "UTA": "Utah Hockey Club", "VAN": "Vancouver Canucks",
    "VGK": "Vegas Golden Knights", "WPG": "Winnipeg Jets", "WSH": "Washington Capitals",
    # Legacy abbreviations (other sources may use these)
    "L.A": "Los Angeles Kings", "N.J": "New Jersey Devils", "S.J": "San Jose Sharks",
    "T.B": "Tampa Bay Lightning",
}

# Key stat columns to extract (MoneyPuck CSV column → our stat key)
STAT_MAP = {
    "xGoalsPercentage": "xg_pct",
    "corsiPercentage": "corsi_pct",
    "fenwickPercentage": "fenwick_pct",
    "games_played": "gp",
    "iceTime": "ice_time",
    # For
    "xOnGoalFor": "xog_for",
    "xGoalsFor": "xgf",
    "shotsOnGoalFor": "shots_for",
    "missedShotsFor": "missed_shots_for",
    "blockedShotAttemptsFor": "blocked_shots_for",
    "shotAttemptsFor": "corsi_for",
    "goalsFor": "goals_for",
    "reboundsFor": "rebounds_for",
    "savedShotsOnGoalFor": "saved_shots_for",
    "penalityMinutesFor": "pim_for",  # NOTE: "penality" is MoneyPuck's CSV typo — intentional match
    "faceOffsWonFor": "faceoffs_won",
    "hitsFor": "hits_for",
    "takeawaysFor": "takeaways_for",
    "giveawaysFor": "giveaways_for",
    "highDangerShotsFor": "high_danger_shots_for",
    "highDangerGoalsFor": "high_danger_goals_for",
    "mediumDangerShotsFor": "medium_danger_shots_for",
    "mediumDangerGoalsFor": "medium_danger_goals_for",
    "lowDangerShotsFor": "low_danger_shots_for",
    "lowDangerGoalsFor": "low_danger_goals_for",
    # Against
    "xOnGoalAgainst": "xog_against",
    "xGoalsAgainst": "xga",
    "shotsOnGoalAgainst": "shots_against",
    "shotAttemptsAgainst": "corsi_against",
    "goalsAgainst": "goals_against",
    "highDangerShotsAgainst": "high_danger_shots_against",
    "highDangerGoalsAgainst": "high_danger_goals_against",
    "penalityMinutesAgainst": "pim_against",
    "faceOffsWonAgainst": "faceoffs_lost",
    "hitsAgainst": "hits_against",
    "takeawaysAgainst": "takeaways_against",
    "giveawaysAgainst": "giveaways_against",
    # Percentages
    "shootingPercentageFor": "shooting_pct",
    "savePctgFor": "save_pct",
    "PDOFor": "pdo",
}


def _current_season() -> str:
    """Detect current NHL season year (MoneyPuck uses start year, e.g. '2025' for 2025-26)."""
    from datetime import date
    today = date.today()
    # NHL season starts in October. If month >= October, it's a new season.
    if today.month >= 10:
        return str(today.year)
    return str(today.year - 1)


def _cache_path(season: str, season_type: str) -> Path:
    return CACHE_DIR / f"teams_{season}_{season_type}.json"


def _is_cache_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    age_hours = (time.time() - path.stat().st_mtime) / 3600
    return age_hours < CACHE_TTL_HOURS


def fetch_team_stats(season: str | None = None, season_type: str = "regular",
                     situation: str = "all") -> list[dict]:
    """Fetch team-level advanced stats from MoneyPuck CSV.

    Args:
        season: NHL season start year (e.g. "2025" for 2025-26). Auto-detected if None.
        season_type: "regular" or "playoffs"
        situation: Filter rows by situation: "all", "5on5", "4on5", "5on4", "other"

    Returns:
        List of dicts with team stats, one per team.
    """
    if season is None:
        season = _current_season()

    cache = _cache_path(season, season_type)

    # Check cache
    if _is_cache_fresh(cache):
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            data = [d for d in data if d.get("_situation") == situation]
            return data
        except (json.JSONDecodeError, OSError):
            pass

    # Fetch CSV
    url = f"{BASE_URL}/{season}/{season_type}/teams.csv"
    try:
        resp = requests.get(url, timeout=15,
                            headers={"User-Agent": "Mozilla/5.0 (compatible)"})
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[moneypuck] Failed to fetch {url}: {e}")
        # Return stale cache if available
        if cache.exists():
            try:
                return json.loads(cache.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    # Parse CSV
    reader = csv.DictReader(io.StringIO(resp.text))
    all_teams = []

    for row in reader:
        team_abbr = row.get("name", "").strip()
        if not team_abbr:
            continue

        team_name = TEAM_NAMES.get(team_abbr, team_abbr)
        row_situation = row.get("situation", "all")

        stats = {}
        for csv_col, stat_key in STAT_MAP.items():
            val = row.get(csv_col, "")
            if val:
                try:
                    stats[stat_key] = float(val)
                except ValueError:
                    pass

        all_teams.append({
            "team_abbr": team_abbr,
            "team_name": team_name,
            "season": season,
            "season_type": season_type,
            "_situation": row_situation,
            "stats": stats,
        })

    # Cache all situations
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(all_teams, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[moneypuck] Cached {len(all_teams)} team rows for {season}/{season_type}")

    # Filter by requested situation ("all" is the aggregate row, not "return everything")
    all_teams = [d for d in all_teams if d.get("_situation") == situation]

    return all_teams


def get_team_stats(team_name: str, season: str | None = None,
                   season_type: str = "regular", situation: str = "all") -> dict | None:
    """Get stats for a specific team by name (fuzzy match).

    Returns dict with team stats, or None if not found.
    """
    all_teams = fetch_team_stats(season=season, season_type=season_type, situation=situation)

    team_lower = team_name.lower()
    for team in all_teams:
        if (team_lower in team["team_name"].lower() or
                team_lower == team["team_abbr"].lower()):
            return team

    # Partial match fallback
    for team in all_teams:
        full_lower = team["team_name"].lower()
        # Match on substring of full name (e.g., "Tampa Bay" in "Tampa Bay Lightning")
        if team_lower in full_lower:
            return team
        # Match on last word of team name (e.g., "Lightning" matches "Tampa Bay Lightning")
        name_parts = full_lower.split()
        if any(part in team_lower or team_lower in part for part in name_parts):
            return team

    return None
