"""Site adapter for BetExplorer (table-based odds layout).

BetExplorer uses HTML tables with match rows. Each ``<tr>`` typically contains
team names (in links), match time, and 1X2 odds in ``<td>`` cells.
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse

ODDS_RE = re.compile(r"^\d+\.\d{2}$")
TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")
# Leading time prefix like "16:55Team Name" or "16:55 Team Name"
LEADING_TIME_RE = re.compile(r"^(\d{1,2}:\d{2})\s*(.+)")
# "Home - Away" or "Home vs Away" with required whitespace around separator
TEAM_SPLIT_RE = re.compile(r"\s+[-–—]\s+|\s+vs\.?\s+", re.I)


def parse(html: str, url: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for tr in soup.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue

        # Strategy 1: find a cell/link containing "Home - Away" team pattern
        home = None
        away = None
        match_time = None
        odds: List[str] = []

        for td in cells:
            td_text = td.get_text(separator=" ", strip=True)

            # Try to extract team names from links first, then plain text
            link = td.find("a")
            name_text = link.get_text(separator=" ", strip=True) if link else td_text

            # Extract time from a span with class "table-main__time" in the same cell
            if match_time is None:
                time_span = td.find("span", class_=re.compile(r"time", re.I))
                if time_span:
                    tm = TIME_RE.search(time_span.get_text(strip=True))
                    if tm:
                        match_time = tm.group(1)

            if home is None and TEAM_SPLIT_RE.search(name_text):
                # Strip leading time prefix (e.g., "16:55Arsenal - Chelsea")
                time_prefix = LEADING_TIME_RE.match(name_text)
                if time_prefix:
                    if match_time is None:
                        match_time = time_prefix.group(1)
                    name_text = time_prefix.group(2)

                parts = TEAM_SPLIT_RE.split(name_text, maxsplit=1)
                if len(parts) >= 2:
                    h = parts[0].strip()
                    a = parts[1].strip()
                    if len(h) >= 2 and len(a) >= 2:
                        home = h
                        away = a
                        continue

            # Check for odds value
            cleaned = td_text.strip()
            if ODDS_RE.match(cleaned):
                odds.append(cleaned)
                continue

            # Check for time
            if match_time is None:
                tm = TIME_RE.search(td_text)
                if tm:
                    match_time = tm.group(1)

        if home and away:
            entry: Dict = {
                "home": home,
                "away": away,
                "time": match_time,
                "source_url": url,
                "raw": f"{home} - {away}",
            }
            if odds:
                entry["odds"] = odds
            results.append(entry)

    if results:
        from adapters import dedup_results
        return dedup_results(
            results,
            key_fn=lambda r: (r.get("home"), r.get("away"), tuple(r.get("odds", []))),
        )

    return raw_parse(html, url)
