"""Site adapter for SoccerStats.com — deep football statistical data.

Extracts: match lines plus team statistics (corners, cards, fouls averages).
SoccerStats covers major European leagues with per-team stat breakdowns.
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse
import logging

logger = logging.getLogger(__name__)


_TIME_RE = re.compile(r"\d{1,2}:\d{2}")
_SCORE_RE = re.compile(r"(\d+)\s*[-:–]\s*(\d+)")
_STAT_RE = re.compile(r"(\d+\.?\d*)\s*/\s*(\d+\.?\d*)", re.I)

def parse(html: str, url: str) -> List[Dict]:
    """Parse SoccerStats HTML for match and statistical data."""
    logger.info(f"SoccerStats parse start: {url} ({len(html)} bytes)")
    soup = BeautifulSoup(html, "html.parser")

    results = _parse_match_tables(soup, url)
    logger.info(f"soccerstats match_tables strategy: {len(results)} matches")
    if not results:
        results = _parse_stat_tables(soup, url)
        logger.info(f"soccerstats stat_tables strategy: {len(results)} entries")
    if not results:
        results = raw_parse(html, url)
        logger.info(f"soccerstats raw fallback: {len(results)} entries")

    logger.info(f"SoccerStats parse complete: {len(results)} entries")
    from adapters import dedup_results
    return dedup_results(results)


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
                        try:
                            stats["corners_home"] = float(stat_match.group(1))
                            stats["corners_away"] = float(stat_match.group(2))
                        except (ValueError, TypeError):
                            pass
                elif re.search(r"card|yellow", title, re.I):
                    stat_match = _STAT_RE.search(text)
                    if stat_match:
                        try:
                            stats["cards_home"] = float(stat_match.group(1))
                            stats["cards_away"] = float(stat_match.group(2))
                        except (ValueError, TypeError):
                            pass
                elif re.search(r"foul", title, re.I):
                    stat_match = _STAT_RE.search(text)
                    if stat_match:
                        try:
                            stats["fouls_home"] = float(stat_match.group(1))
                            stats["fouls_away"] = float(stat_match.group(2))
                        except (ValueError, TypeError):
                            pass

            if home and away:
                result = {
                    "home": home,
                    "away": away,
                    "time": match_time,
                    "odds": "",
                    "league": current_league,
                    "sport": "football",
                    "source_url": url,
                    "source_type": "soccerstats",
                    "raw": f"{home} - {away}"
                }
                if stats:
                    result["stats"] = stats
                    
                    if "corners_home" in stats or "corners_away" in stats:
                        result["corners"] = {
                            "home": stats.get("corners_home"),
                            "away": stats.get("corners_away")
                        }
                    if "cards_home" in stats or "cards_away" in stats:
                        result["cards"] = {
                            "home": stats.get("cards_home"),
                            "away": stats.get("cards_away")
                        }
                    if "fouls_home" in stats or "fouls_away" in stats:
                        result["fouls"] = {
                            "home": stats.get("fouls_home"),
                            "away": stats.get("fouls_away")
                        }
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
                    "source_url": url,
                    "source_type": "soccerstats",
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


def get_deep_links(html: str, url: str) -> list[str]:
    """Extract league/team stat URLs from SoccerStats listing page."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r'/(results|teams|homeaway)\.asp', href, re.I):
            full_url = href
            if full_url.startswith("/"):
                full_url = "https://www.soccerstats.com" + full_url
            elif not full_url.startswith("http"):
                full_url = "https://www.soccerstats.com/" + full_url
            if full_url not in links:
                links.append(full_url)
    logger.info(f"SoccerStats: found {len(links)} deep links")
    return links
