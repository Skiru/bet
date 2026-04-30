"""Site adapter for TennisExplorer — match schedules, results, and H2H.

Extracts: match lines (player1/player2/time/tournament), surface info.
TennisExplorer covers ATP, WTA, ITF, and Challenger tours.
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse


_TIME_RE = re.compile(r"\d{1,2}:\d{2}")
_SCORE_RE = re.compile(r"(\d+)\s*[-:]\s*(\d+)")
_SURFACE_RE = re.compile(r"(hard|clay|grass|carpet|indoor|outdoor)", re.I)


def parse(html: str, url: str) -> List[Dict]:
    """Parse TennisExplorer HTML for match data."""
    soup = BeautifulSoup(html, "html.parser")

    results = _parse_match_tables(soup, url)
    if not results:
        results = _parse_match_rows(soup, url)
    if not results:
        return raw_parse(html, url)

    return results


def _parse_match_tables(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse TennisExplorer's table-based layout."""
    results = []
    current_tournament = ""

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            classes = " ".join(row.get("class", []))

            # Tournament/round headers
            if re.search(r"head|round|group", classes, re.I):
                text = row.get_text(strip=True)
                if 3 < len(text) < 120:
                    current_tournament = text
                continue

            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            # Extract player names from links
            links = row.find_all("a")
            players = []
            for link in links:
                href = link.get("href", "")
                name = link.get_text(strip=True)
                if name and len(name) > 2 and ("/player/" in href or "/profile/" in href or _is_player_name(name)):
                    players.append(name)

            if len(players) < 2:
                # Try from cell text
                cell_texts = [c.get_text(strip=True) for c in cells]
                for text in cell_texts:
                    if _is_player_name(text) and text not in players:
                        players.append(text)

            if len(players) >= 2:
                text = row.get_text(separator=" ", strip=True)
                match_time = ""
                time_match = _TIME_RE.search(text)
                if time_match:
                    match_time = time_match.group()

                # Detect surface
                surface = ""
                surface_match = _SURFACE_RE.search(current_tournament + " " + text)
                if surface_match:
                    surface = surface_match.group(1).lower()

                results.append({
                    "home": players[0],
                    "away": players[1],
                    "time": match_time,
                    "odds": "",
                    "league": current_tournament,
                    "sport": "tennis",
                    "source": "tennisexplorer.com",
                    "url": url,
                    "surface": surface,
                })

    return results


def _parse_match_rows(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse TennisExplorer alternative layouts."""
    results = []
    current_tournament = ""

    for el in soup.find_all(True):
        classes = " ".join(el.get("class", []))

        # Tournament headers
        if re.search(r"tournament|event-header|flags", classes, re.I):
            text = el.get_text(strip=True)
            if 3 < len(text) < 120:
                current_tournament = text
                continue

        # Match containers
        if not re.search(r"match|result|game", classes, re.I):
            continue

        text = el.get_text(separator=" ", strip=True)
        if len(text) < 5 or len(text) > 300:
            continue

        links = el.find_all("a")
        players = []
        for link in links:
            name = link.get_text(strip=True)
            if name and _is_player_name(name):
                players.append(name)

        if len(players) >= 2:
            match_time = ""
            time_match = _TIME_RE.search(text)
            if time_match:
                match_time = time_match.group()

            results.append({
                "home": players[0],
                "away": players[1],
                "time": match_time,
                "odds": "",
                "league": current_tournament,
                "sport": "tennis",
                "source": "tennisexplorer.com",
                "url": url,
            })

    return results


def _is_player_name(text: str) -> bool:
    """Heuristic: is this text likely a player name?"""
    if not text or len(text) < 3 or len(text) > 60:
        return False
    if text.isdigit():
        return False
    if _SCORE_RE.match(text):
        return False
    if re.match(r"^\d{1,2}:\d{2}$", text):
        return False
    # Common non-player labels
    skip = {"vs", "v", "-", "FT", "ret.", "w/o", "Completed", "Live", "Q"}
    if text.strip() in skip:
        return False
    # Player names contain letters and possibly dots/hyphens
    if re.search(r"[a-zA-Z]", text):
        return True
    return False
