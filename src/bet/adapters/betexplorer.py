"""BetExplorer adapter — parse odds tables from HTML.

Pure parser: accepts HTML, returns structured dicts. No I/O.
Ported from scripts/adapters/betexplorer_adapter.py.
"""

import re
from typing import Any

from bs4 import BeautifulSoup

ODDS_RE = re.compile(r"^\d+\.\d{2}$")
TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")
LEADING_TIME_RE = re.compile(r"^(\d{1,2}:\d{2})\s*(.+)")
TEAM_SPLIT_RE = re.compile(r"\s+[-–—]\s+|\s+vs\.?\s+", re.I)


class BetExplorerAdapter:
    """BetExplorer HTML parser for odds and fixture data."""

    def parse_fixtures(self, html: str, url: str = "") -> list[dict[str, Any]]:
        """Parse a BetExplorer page into fixture dicts with odds.

        Returns list of {"home": str, "away": str, "time": str|None,
                         "odds": list[str]}.
        """
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict[str, Any]] = []

        for tr in soup.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue

            home = None
            away = None
            match_time = None
            odds: list[str] = []

            for td in cells:
                td_text = td.get_text(separator=" ", strip=True)

                link = td.find("a")
                name_text = link.get_text(separator=" ", strip=True) if link else td_text

                # Extract time
                if match_time is None:
                    time_span = td.find("span", class_=re.compile(r"time", re.I))
                    if time_span:
                        tm = TIME_RE.search(time_span.get_text(strip=True))
                        if tm:
                            match_time = tm.group(1)

                if home is None and TEAM_SPLIT_RE.search(name_text):
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

                cleaned = td_text.strip()
                if ODDS_RE.match(cleaned):
                    odds.append(cleaned)
                    continue

                if match_time is None:
                    tm = TIME_RE.search(td_text)
                    if tm:
                        match_time = tm.group(1)

            if home and away:
                entry: dict[str, Any] = {
                    "home": home,
                    "away": away,
                    "time": match_time,
                    "source": "betexplorer",
                }
                if odds:
                    entry["odds"] = odds
                results.append(entry)

        return results

    def parse_odds_detail(self, html: str) -> list[dict[str, Any]]:
        """Parse a BetExplorer odds detail page.

        Returns list of {"bookmaker": str, "odds_1": str, "odds_x": str, "odds_2": str}.
        """
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict[str, Any]] = []

        for tr in soup.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 3:
                continue

            # First cell typically contains bookmaker name
            bm_link = cells[0].find("a")
            bm_name = bm_link.get_text(strip=True) if bm_link else cells[0].get_text(strip=True)
            if not bm_name or len(bm_name) < 2:
                continue

            odds_vals = []
            for td in cells[1:]:
                text = td.get_text(strip=True)
                if ODDS_RE.match(text):
                    odds_vals.append(text)

            if len(odds_vals) >= 2:
                entry: dict[str, Any] = {"bookmaker": bm_name}
                if len(odds_vals) >= 3:
                    entry["odds_1"] = odds_vals[0]
                    entry["odds_x"] = odds_vals[1]
                    entry["odds_2"] = odds_vals[2]
                else:
                    entry["odds_1"] = odds_vals[0]
                    entry["odds_2"] = odds_vals[1]
                results.append(entry)

        return results
