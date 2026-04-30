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

            if home is None and TEAM_SPLIT_RE.search(name_text):
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
