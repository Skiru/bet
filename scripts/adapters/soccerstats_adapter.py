"""Site adapter for SoccerStats.com — deep football statistical data.

Extracts: match lines plus team statistics (corners, cards, fouls averages).
SoccerStats covers major European leagues with per-team stat breakdowns.
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse


_TIME_RE = re.compile(r"\d{1,2}:\d{2}")
_SCORE_RE = re.compile(r"(\d+)\s*[-:–]\s*(\d+)")
_STAT_RE = re.compile(r"(\d+\.?\d*)\s*/\s*(\d+\.?\d*)", re.I)


def parse(html: str, url: str) -> List[Dict]:
    """Parse SoccerStats HTML for match and statistical data."""
    soup = BeautifulSoup(html, "html.parser")

    results = _parse_match_tables(soup, url)
    if not results:
        results = _parse_stat_tables(soup, url)
    if not results:
        return raw_parse(html, url)

    return results


def _parse_match_tables(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse SoccerStats match/fixture tables."""
    results = []
    current_league = ""

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            # Check for league/heading rows
            th = row.find("th")
            if th:
                text = th.get_text(strip=True)
                if len(text) > 3 and len(text) < 100:
                    current_league = text
                continue

            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            texts = [c.get_text(strip=True) for c in cells]

            home = ""
            away = ""
            match_time = ""
            stats = {}

            for text in texts:
                time_match = _TIME_RE.search(text)
                if time_match and not match_time:
                    match_time = time_match.group()
                    continue
                if not home and _is_team_name(text):
                    home = text
                elif home and not away and _is_team_name(text):
                    away = text

            # Extract stats from row if available
            for cell in cells:
                title = cell.get("title", "")
                text = cell.get_text(strip=True)

                # Look for corners/cards/fouls stats
                if re.search(r"corner", title, re.I):
                    stat_match = _STAT_RE.search(text)
                    if stat_match:
                        stats["corners_home"] = float(stat_match.group(1))
                        stats["corners_away"] = float(stat_match.group(2))
                elif re.search(r"card|yellow", title, re.I):
                    stat_match = _STAT_RE.search(text)
                    if stat_match:
                        stats["cards_home"] = float(stat_match.group(1))
                        stats["cards_away"] = float(stat_match.group(2))
                elif re.search(r"foul", title, re.I):
                    stat_match = _STAT_RE.search(text)
                    if stat_match:
                        stats["fouls_home"] = float(stat_match.group(1))
                        stats["fouls_away"] = float(stat_match.group(2))

            if home and away:
                result = {
                    "home": home,
                    "away": away,
                    "time": match_time,
                    "odds": "",
                    "league": current_league,
                    "sport": "football",
                    "source": "soccerstats.com",
                    "url": url,
                }
                if stats:
                    result["stats"] = stats
                results.append(result)

    return results


def _parse_stat_tables(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse SoccerStats team statistics tables (averages per team)."""
    results = []

    # Look for stat summary tables (corners/game, cards/game etc.)
    for table in soup.find_all("table"):
        header_row = table.find("tr")
        if not header_row:
            continue

        headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]

        # Check if this is a stats table
        stat_headers = {"team", "corners", "cards", "fouls", "shots", "goals"}
        if not stat_headers.intersection(set(headers)):
            continue

        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            row_data = {}
            for i, cell in enumerate(cells):
                if i < len(headers):
                    row_data[headers[i]] = cell.get_text(strip=True)

            team = row_data.get("team", "")
            if team and _is_team_name(team):
                result = {
                    "home": team,
                    "away": "(league stats)",
                    "time": "",
                    "odds": "",
                    "league": "",
                    "sport": "football",
                    "source": "soccerstats.com",
                    "url": url,
                    "data_type": "team_stats",
                    "stats": {k: v for k, v in row_data.items() if k != "team"},
                }
                results.append(result)

    return results


def _is_team_name(text: str) -> bool:
    """Heuristic: is this text likely a team name?"""
    if not text or len(text) < 2 or len(text) > 80:
        return False
    if text.isdigit():
        return False
    if _SCORE_RE.match(text):
        return False
    if re.match(r"^\d{1,2}:\d{2}$", text):
        return False
    skip_words = {"vs", "v", "-", "FT", "HT", "Total", "Average", "Home", "Away"}
    if text in skip_words:
        return False
    return True
