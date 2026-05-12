"""MoneyPuck adapter — NHL advanced team stats from CSV data.

MoneyPuck provides free CSV endpoints (no Cloudflare, no API key).
This adapter wraps the moneypuck_client to fit the standard adapter interface.

Since MoneyPuck returns CSV (not HTML), this adapter ignores the html parameter
and fetches data directly via the client. The url parameter is used to detect
season/type.
"""
from typing import List, Dict
import re
import sys
from pathlib import Path

# Ensure api_clients is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from .raw_adapter import parse as raw_parse


def parse(html: str, url: str) -> List[Dict]:
    """Parse MoneyPuck data for NHL team advanced stats.

    Note: html parameter may contain CSV text or be irrelevant.
    The adapter fetches its own data via moneypuck_client when html is not CSV.
    """
    # If html looks like CSV data (has header row with expected columns), parse directly
    if html and "corsiPercentage" in html and "," in html[:200]:
        return _parse_csv_text(html, url)

    # Otherwise, fetch fresh data via the client
    try:
        from api_clients.moneypuck_client import fetch_team_stats
    except ImportError:
        return raw_parse(html, url)

    # Detect season from URL if present
    season = None
    season_type = "regular"
    season_match = re.search(r"/(\d{4})/(regular|playoffs)/", url)
    if season_match:
        season = season_match.group(1)
        season_type = season_match.group(2)

    try:
        teams = fetch_team_stats(season=season, season_type=season_type, situation="all")
    except Exception:
        return raw_parse(html, url)

    return _format_teams(teams, url)


def _parse_csv_text(csv_text: str, url: str) -> List[Dict]:
    """Parse CSV text directly (when scanner passes CSV content)."""
    import csv
    import io

    try:
        from api_clients.moneypuck_client import STAT_MAP, TEAM_NAMES
    except ImportError:
        return []

    reader = csv.DictReader(io.StringIO(csv_text))
    teams = []
    for row in reader:
        if row.get("situation") != "all":
            continue
        team_abbr = row.get("name", "").strip()
        if not team_abbr:
            continue

        team_name = TEAM_NAMES.get(team_abbr, team_abbr)
        stats = {}
        for csv_col, stat_key in STAT_MAP.items():
            val = row.get(csv_col, "")
            if val:
                try:
                    stats[stat_key] = float(val)
                except ValueError:
                    pass

        teams.append({
            "team_abbr": team_abbr,
            "team_name": team_name,
            "stats": stats,
        })

    return _format_teams(teams, url)


def _format_teams(teams: list, url: str) -> List[Dict]:
    """Convert team dicts to standard adapter output format."""
    results = []
    for team in teams:
        stats = team.get("stats", {})
        results.append({
            "home": team.get("team_name", team.get("team_abbr", "")),
            "away": "",
            "time": "",
            "league": "NHL",
            "sport": "hockey",
            "source_url": url,
            "source_type": "moneypuck",
            "data_type": "team_season_stats",
            "stats": stats,
            "raw": f"{team.get('team_name', '')} advanced stats (MoneyPuck)",
        })
    return results
