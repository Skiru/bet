"""Site adapter for HLTV.org — CS2 esports match data.

Extracts: match lines (home/away/time/competition), map info, rankings.
HLTV is the primary source for CS2 (Counter-Strike 2) competitive matches.
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse


_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")
_BO_RE = re.compile(r"(bo[135]|best of [135])", re.I)


def parse(html: str, url: str) -> List[Dict]:
    """Parse HLTV HTML for match data."""
    soup = BeautifulSoup(html, "html.parser")

    results = _parse_match_rows(soup, url)
    if not results:
        results = _parse_upcoming_matches(soup, url)
    if not results:
        return raw_parse(html, url)
    return results


def _parse_match_rows(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse HLTV's match listing page."""
    results = []
    current_event = ""

    for el in soup.find_all(True, class_=re.compile(r"match|upcomingMatch|liveMatch|result", re.I)):
        classes = " ".join(el.get("class", []))

        # Detect event/tournament headers
        if re.search(r"event-header|headline|matchDay", classes, re.I):
            current_event = el.get_text(strip=True)
            continue

        # Find team elements
        team_els = el.find_all(True, class_=re.compile(r"team|matchTeam|teamName|lineup", re.I))
        teams = []
        for t in team_els:
            name = t.get_text(strip=True)
            if name and 2 < len(name) < 60:
                teams.append(name)

        if len(teams) < 2:
            continue

        # Extract time
        time_el = el.find(True, class_=re.compile(r"time|matchTime|date", re.I))
        kickoff = ""
        if time_el:
            kickoff = time_el.get_text(strip=True)

        # Extract event name if embedded
        event_el = el.find(True, class_=re.compile(r"event|matchEvent|tournament", re.I))
        event_name = current_event
        if event_el:
            event_name = event_el.get_text(strip=True) or event_name

        # Detect format (BO1/BO3/BO5)
        text = el.get_text(separator=" ", strip=True)
        bo_match = _BO_RE.search(text)
        match_format = bo_match.group(1).upper() if bo_match else ""

        entry = {
            "home_team": teams[0],
            "away_team": teams[1],
            "kickoff": kickoff,
            "competition": event_name,
            "sport": "esports",
            "source": "hltv.org",
        }
        if match_format:
            entry["format"] = match_format

        # Extract map info if available
        maps = _extract_maps(el)
        if maps:
            entry["maps"] = maps

        results.append(entry)

    return results


def _parse_upcoming_matches(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Fallback: parse upcoming match sections."""
    results = []

    for div in soup.find_all("div", class_=re.compile(r"upcoming|matchListTable", re.I)):
        links = div.find_all("a", href=re.compile(r"/matches/", re.I))
        for link in links:
            text = link.get_text(separator=" ", strip=True)
            # Look for "Team1 vs Team2" pattern
            vs_m = re.search(r"(.{2,30}?)\s+vs\.?\s+(.{2,30})", text, re.I)
            if vs_m:
                results.append({
                    "home_team": vs_m.group(1).strip(),
                    "away_team": vs_m.group(2).strip(),
                    "kickoff": "",
                    "competition": "",
                    "sport": "esports",
                    "source": "hltv.org",
                })

    return results


def _extract_maps(el) -> list:
    """Extract map names from a match element."""
    maps = []
    map_els = el.find_all(True, class_=re.compile(r"map|mapname", re.I))
    for m in map_els:
        name = m.get_text(strip=True)
        if name and len(name) < 30:
            maps.append(name)
    return maps
