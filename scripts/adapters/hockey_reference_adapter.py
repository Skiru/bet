"""Site adapter for Hockey-Reference — NHL detailed stats and schedules.

Extracts: match lines (home/away/time/competition), scores.
Hockey-Reference uses clean HTML tables similar to Basketball-Reference.
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse


_SCORE_RE = re.compile(r"(\d+)\s*[-–]\s*(\d+)")


def parse(html: str, url: str) -> List[Dict]:
    """Parse Hockey-Reference HTML for match/schedule data."""
    soup = BeautifulSoup(html, "html.parser")

    results = _parse_schedule_table(soup, url)
    if not results:
        results = _parse_game_rows(soup, url)
    if not results:
        return raw_parse(html, url)
    return results


def _parse_schedule_table(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse Hockey-Reference's schedule tables."""
    results = []
    schedule = soup.find("table", id=re.compile(r"games|schedule|scores", re.I))
    if not schedule:
        return []

    rows = schedule.find_all("tr")
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue

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
                "league": "NHL",
                "sport": "hockey",
                "source_url": url,
                "source_type": "hockey_reference",
                "raw": f"{home} vs {away}"
            })

    return results


def _parse_game_rows(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Fallback: parse game summary blocks."""
    results = []

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
                    "league": "NHL",
                    "sport": "hockey",
                    "source_url": url,
                    "source_type": "hockey_reference",
                    "raw": f"{home} vs {away}"
                })

    return results
