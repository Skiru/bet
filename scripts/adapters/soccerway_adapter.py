"""Site adapter for Soccerway — global football coverage with deep league data.

Extracts: match lines (home/away/time/league), scores, and league context.
Soccerway covers 1000+ football leagues worldwide.
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse


_MATCH_ROW_RE = re.compile(r"match|fixture|game-row", re.I)
_SCORE_RE = re.compile(r"(\d+)\s*[-:–]\s*(\d+)")
_TIME_RE = re.compile(r"\d{1,2}:\d{2}")


def parse(html: str, url: str) -> List[Dict]:
    """Parse Soccerway HTML for match data."""
    soup = BeautifulSoup(html, "html.parser")

    results = _parse_match_tables(soup, url)
    if not results:
        results = _parse_match_blocks(soup, url)
    if not results:
        return raw_parse(html, url)

    return results


def _parse_match_tables(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse Soccerway's table-based match layout."""
    results = []
    current_league = ""

    # Look for table rows with match data
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            # Check if this is a group/league header
            th = row.find("th")
            if th:
                text = th.get_text(strip=True)
                if len(text) > 3 and len(text) < 100:
                    current_league = text
                continue

            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            # Try to extract teams and score
            texts = [c.get_text(strip=True) for c in cells]

            home = ""
            away = ""
            score_text = ""
            match_time = ""

            for i, text in enumerate(texts):
                time_match = _TIME_RE.search(text)
                if time_match and not match_time:
                    match_time = time_match.group()
                    continue
                score_match = _SCORE_RE.search(text)
                if score_match and not score_text:
                    score_text = text
                    continue
                if not home and _is_team_name(text):
                    home = text
                elif home and not away and _is_team_name(text):
                    away = text

            if home and away:
                match_url = ""
                for cell in cells:
                    a = cell.find("a", href=re.compile(r"/matches/"))
                    if a and a.get("href"):
                        match_url = a.get("href")
                        break
                
                entry = {
                    "home": home,
                    "away": away,
                    "time": match_time,
                    "score": score_text if score_text else "",
                    "odds": None,
                    "league": current_league,
                    "sport": "football",
                    "source_url": url,
                    "source_type": "soccerway",
                    "raw": f"{home} vs {away}"
                }
                if match_url:
                    entry["match_url"] = match_url
                results.append(entry)

    return results


def _parse_match_blocks(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse Soccerway's block-based match layout (alternative DOM)."""
    results = []
    current_league = ""

    for el in soup.find_all(True):
        classes = " ".join(el.get("class", []))

        # League headers
        if re.search(r"group-head|competition-title|block_competition", classes, re.I):
            text = el.get_text(strip=True)
            if 3 < len(text) < 100:
                current_league = text
                continue

        # Match rows
        if not _MATCH_ROW_RE.search(classes):
            continue

        text = el.get_text(separator=" ", strip=True)
        if len(text) < 5 or len(text) > 300:
            continue

        # Try to extract teams from links
        links = el.find_all("a")
        team_names = []
        for link in links:
            href = link.get("href", "")
            name = link.get_text(strip=True)
            if name and _is_team_name(name) and ("/teams/" in href or len(name) > 2):
                team_names.append(name)

        if len(team_names) >= 2:
            match_time = ""
            time_match = _TIME_RE.search(text)
            if time_match:
                match_time = time_match.group()

            match_url = ""
            for link in links:
                href = link.get("href", "")
                if "/matches/" in href:
                    match_url = href
                    break
            
            entry = {
                "home": team_names[0],
                "away": team_names[1],
                "time": match_time,
                "score": "",
                "odds": None,
                "league": current_league,
                "sport": "football",
                "source_url": url,
                "source_type": "soccerway",
                "raw": f"{team_names[0]} vs {team_names[1]}"
            }
            if match_url:
                entry["match_url"] = match_url
            results.append(entry)

    return results


def _is_team_name(text: str) -> bool:
    """Heuristic: is this text likely a team name?"""
    if not text or len(text) < 2 or len(text) > 80:
        return False
    # Not a score, date, or number-only
    if _SCORE_RE.match(text):
        return False
    if text.isdigit():
        return False
    if re.match(r"^\d{1,2}:\d{2}$", text):
        return False
    # Not common non-team labels
    skip_words = {"vs", "v", "-", "FT", "HT", "Postp.", "Canc.", "AET", "AP"}
    if text in skip_words:
        return False
    return True
