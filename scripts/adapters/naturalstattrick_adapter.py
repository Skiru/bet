"""NaturalStatTrick adapter — NHL advanced analytics (Corsi, Fenwick, xG).

Extracts team-level and game-level advanced stats from NaturalStatTrick tables.

Page types:
  Team table: /teamtable.php?... — season team stats
  Game log:   /games.php?...     — per-game stats
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse


def parse(html: str, url: str) -> List[Dict]:
    """Parse NaturalStatTrick HTML for advanced hockey analytics."""
    soup = BeautifulSoup(html, "html.parser")
    
    if "teamtable.php" in url:
        results = _parse_team_table(soup, url)
        if results:
            return results
    elif "games.php" in url:
        results = _parse_game_log(soup, url)
        if results:
            return results
    
    return raw_parse(html, url)


def _parse_team_table(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse team-level season stats table."""
    results = []
    
    table = soup.find("table", id=re.compile(r"teams|team", re.I))
    if not table:
        # Fallback: find first table with enough columns
        for t in soup.find_all("table"):
            headers = [th.get_text(strip=True) for th in t.find_all("th")]
            if any("CF%" in h for h in headers):
                table = t
                break
    
    if not table:
        return []
    
    # Parse headers to find column indices
    headers = []
    thead = table.find("thead")
    if thead:
        header_row = thead.find("tr")
        if header_row:
            headers = [th.get_text(strip=True) for th in header_row.find_all("th")]
    
    if not headers:
        # Try first row
        first_row = table.find("tr")
        if first_row:
            headers = [cell.get_text(strip=True) for cell in first_row.find_all(["th", "td"])]
    
    # Build column index map
    col_map = {}
    for i, h in enumerate(headers):
        col_map[h] = i
    
    # Stat columns we want to extract
    STAT_KEYS = {
        "GP": "gp", "W": "wins", "L": "losses", 
        "CF%": "corsi_pct", "FF%": "fenwick_pct",
        "CF": "corsi_for", "CA": "corsi_against",
        "FF": "fenwick_for", "FA": "fenwick_against",
        "SF": "shots_for", "SA": "shots_against", "SF%": "shots_for_pct",
        "GF": "goals_for", "GA": "goals_against", "GF%": "goals_for_pct",
        "xGF": "xgf", "xGA": "xga", "xGF%": "xg_pct",
        "SCF": "scoring_chances_for", "SCA": "scoring_chances_against",
        "HDCF": "high_danger_for", "HDCA": "high_danger_against", "HDCF%": "high_danger_pct",
        "SH%": "shooting_pct", "SV%": "save_pct",
        "Point%": "points_pct",
    }
    
    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]
    
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 5:
            continue
        
        cell_texts = [c.get_text(strip=True) for c in cells]
        
        # First column should be team name
        team_name = cell_texts[0] if cell_texts else ""
        if not team_name or len(team_name) < 2 or team_name in headers:
            continue
        
        stats = {}
        for header_name, stat_key in STAT_KEYS.items():
            if header_name in col_map:
                idx = col_map[header_name]
                if idx < len(cell_texts):
                    try:
                        val = cell_texts[idx].replace("%", "").strip()
                        stats[stat_key] = float(val) if val else None
                    except (ValueError, IndexError):
                        stats[stat_key] = None
        
        if stats:
            results.append({
                "home": team_name,  # team name in home field for consistency
                "away": "",
                "time": "",
                "league": "NHL",
                "sport": "hockey",
                "source_url": url,
                "source_type": "naturalstattrick",
                "data_type": "team_season_stats",
                "stats": stats,
                "raw": f"{team_name} season stats"
            })
    
    return results


def _parse_game_log(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse game-by-game stats table."""
    results = []
    
    table = soup.find("table", id=re.compile(r"games|game", re.I))
    if not table:
        for t in soup.find_all("table"):
            headers = [th.get_text(strip=True) for th in t.find_all("th")]
            if any("CF%" in h for h in headers) and any("Date" in h or "Game" in h for h in headers):
                table = t
                break
    
    if not table:
        return []
    
    # Parse headers
    headers = []
    thead = table.find("thead")
    if thead:
        header_row = thead.find("tr")
        if header_row:
            headers = [th.get_text(strip=True) for th in header_row.find_all("th")]
    
    col_map = {h: i for i, h in enumerate(headers)}
    
    STAT_KEYS = {
        "CF%": "corsi_pct", "FF%": "fenwick_pct",
        "CF": "corsi_for", "CA": "corsi_against",
        "FF": "fenwick_for", "FA": "fenwick_against",
        "SF": "shots_for", "SA": "shots_against",
        "GF": "goals_for", "GA": "goals_against",
        "xGF": "xgf", "xGA": "xga", "xGF%": "xg_pct",
        "HDCF": "high_danger_for", "HDCA": "high_danger_against",
        "SCF": "scoring_chances_for", "SCA": "scoring_chances_against",
    }
    
    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]
    
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 5:
            continue
        
        cell_texts = [c.get_text(strip=True) for c in cells]
        
        # Extract team and opponent from columns
        team = ""
        opponent = ""
        date = ""
        score = ""
        
        for col_name in ("Team", "team"):
            if col_name in col_map and col_map[col_name] < len(cell_texts):
                team = cell_texts[col_map[col_name]]
                break
        
        for col_name in ("Opponent", "Opp", "opponent"):
            if col_name in col_map and col_map[col_name] < len(cell_texts):
                opponent = cell_texts[col_map[col_name]]
                break
        
        for col_name in ("Date", "Game", "date"):
            if col_name in col_map and col_map[col_name] < len(cell_texts):
                date = cell_texts[col_map[col_name]]
                break
        
        for col_name in ("Score", "score"):
            if col_name in col_map and col_map[col_name] < len(cell_texts):
                score = cell_texts[col_map[col_name]]
                break
        
        if not team:
            team = cell_texts[0] if cell_texts else ""
        
        stats = {}
        for header_name, stat_key in STAT_KEYS.items():
            if header_name in col_map:
                idx = col_map[header_name]
                if idx < len(cell_texts):
                    try:
                        val = cell_texts[idx].replace("%", "").strip()
                        stats[stat_key] = float(val) if val else None
                    except (ValueError, IndexError):
                        stats[stat_key] = None
        
        if stats and team:
            results.append({
                "home": team,
                "away": opponent,
                "time": date,
                "league": "NHL",
                "sport": "hockey",
                "source_url": url,
                "source_type": "naturalstattrick",
                "data_type": "game_stats",
                "stats": stats,
                "score": score,
                "raw": f"{team} vs {opponent} ({date})"
            })
    
    return results