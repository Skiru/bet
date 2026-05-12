"""Site adapter for Basketball-Reference — deep NBA/WNBA box scores and schedules.

Extracts: match lines (home/away/time/competition), scores.
Basketball-Reference uses clean HTML tables, making parsing reliable.
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse


_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2}\s*[ap]m?)\b", re.I)
_DATE_RE = re.compile(r"\b(\w+\s+\d{1,2},\s*\d{4})\b")
_SCORE_RE = re.compile(r"(\d{2,3})\s*[-–]\s*(\d{2,3})")


def parse(html: str, url: str) -> List[Dict]:
    """Parse Basketball-Reference HTML for match/schedule data."""
    soup = BeautifulSoup(html, "html.parser")

    results = _parse_schedule_table(soup, url)
    if not results:
        results = _parse_game_rows(soup, url)
    if not results:
        return raw_parse(html, url)
    return results


def _parse_schedule_table(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse Basketball-Reference's schedule tables (id='schedule')."""
    results = []
    schedule = soup.find("table", id="schedule")
    if not schedule:
        # Also try other common table IDs
        schedule = soup.find("table", id=re.compile(r"games|schedule|scores", re.I))
    if not schedule:
        return []

    rows = schedule.find_all("tr")
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue

        # Try to extract date, teams, and time
        date_text = ""
        home = ""
        away = ""
        kickoff = ""

        for cell in cells:
            data_stat = cell.get("data-stat", "")
            text = cell.get_text(strip=True)

            if data_stat == "date_game":
                date_text = text
            elif data_stat == "visitor_team_name":
                a = cell.find("a")
                away = a.get_text(strip=True) if a else text
            elif data_stat == "home_team_name":
                a = cell.find("a")
                home = a.get_text(strip=True) if a else text
            elif data_stat == "game_start_time":
                kickoff = text

        if home and away:
            results.append({
                "home": home,
                "away": away,
                "time": kickoff or date_text,
                "league": "NBA",
                "sport": "basketball",
                "source_url": url,
                "source_type": "basketball_reference",
                "raw": f"{home} vs {away}"
            })

    return results


def _parse_game_rows(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Fallback: parse any game summary blocks."""
    results = []

    # Look for game_summary divs (box score pages)
    for div in soup.find_all("div", class_=re.compile(r"game_summary|scorebox", re.I)):
        teams = div.find_all("a", href=re.compile(r"/teams/", re.I))
        if len(teams) >= 2:
            away = teams[0].get_text(strip=True)
            home = teams[1].get_text(strip=True)
            if home and away and len(home) < 60 and len(away) < 60:
                results.append({
                    "home": home,
                    "away": away,
                    "time": "",
                    "league": "NBA",
                    "sport": "basketball",
                    "source_url": url,
                    "source_type": "basketball_reference",
                    "raw": f"{home} vs {away}"
                })

    return results
