"""Site adapter for WhoScored — detailed match stats (passes, shots, touches).

Extracts: match lines (home/away/time/competition), visible stats.
WhoScored relies heavily on JS rendering; this adapter does best-effort
HTML parsing and falls back to raw_adapter.
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse


_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")
_SCORE_RE = re.compile(r"(\d+)\s*[-:–]\s*(\d+)")
_MATCH_RE = re.compile(r"match-link|match-row|result-row|fixture", re.I)


def parse(html: str, url: str) -> List[Dict]:
    """Parse WhoScored HTML for match data."""
    soup = BeautifulSoup(html, "html.parser")

    results = _parse_match_rows(soup, url)
    if not results:
        results = _parse_table_rows(soup, url)
    if not results:
        return raw_parse(html, url)
    return results


def _parse_match_rows(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse WhoScored's match-link based layout."""
    results = []
    current_comp = ""

    # Look for competition/league headers
    for el in soup.find_all(True):
        classes = " ".join(el.get("class", []))

        # Detect league/competition headers
        if re.search(r"stage-header|tournament-header|league-name", classes, re.I):
            current_comp = el.get_text(strip=True)
            continue

        # Detect match rows
        if not _MATCH_RE.search(classes):
            continue

        text = el.get_text(separator=" ", strip=True)
        if not text or len(text) > 300:
            continue

        # Try to find home/away team elements
        home_el = el.find(class_=re.compile(r"home|team-a|team.*left", re.I))
        away_el = el.find(class_=re.compile(r"away|team-b|team.*right", re.I))
        time_el = el.find(class_=re.compile(r"time|ko|kick-off|date", re.I))

        if home_el and away_el:
            home = home_el.get_text(strip=True)
            away = away_el.get_text(strip=True)
            kickoff = time_el.get_text(strip=True) if time_el else ""

            if not home or not away or len(home) > 60 or len(away) > 60:
                continue

            entry = {
                "home_team": home,
                "away_team": away,
                "kickoff": kickoff,
                "competition": current_comp,
                "sport": "football",
                "source": "whoscored.com",
            }

            # Extract visible stats if available
            stats = _extract_stats(el)
            if stats:
                entry["stats"] = stats

            results.append(entry)

    return results


def _parse_table_rows(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Fallback: parse table-based match layouts."""
    results = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            texts = [c.get_text(strip=True) for c in cells]
            # Look for patterns: time | home | score | away
            time_match = None
            for t in texts:
                m = _TIME_RE.search(t)
                if m:
                    time_match = m.group(1)
                    break

            # Try to identify home/away from cells
            teams = [t for t in texts if 3 < len(t) < 60 and not _TIME_RE.match(t) and not _SCORE_RE.match(t)]
            if len(teams) >= 2:
                results.append({
                    "home_team": teams[0],
                    "away_team": teams[1],
                    "kickoff": time_match or "",
                    "competition": "",
                    "sport": "football",
                    "source": "whoscored.com",
                })

    return results


def _extract_stats(el) -> dict:
    """Extract visible match stats from a match element."""
    stats = {}
    stat_patterns = {
        "possession": re.compile(r"possession.*?(\d+)%", re.I),
        "shots": re.compile(r"shots.*?(\d+)", re.I),
        "shots_on_target": re.compile(r"shots?\s*on\s*target.*?(\d+)", re.I),
        "passes": re.compile(r"passes.*?(\d+)", re.I),
        "corners": re.compile(r"corners.*?(\d+)", re.I),
    }
    text = el.get_text(separator=" ", strip=True)
    for stat_name, pattern in stat_patterns.items():
        m = pattern.search(text)
        if m:
            stats[stat_name] = int(m.group(1))
    return stats
