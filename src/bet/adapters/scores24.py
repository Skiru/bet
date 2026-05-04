"""Scores24.live adapter — parse match listings, H2H, form, and trends.

Pure parser: accepts HTML, returns structured dicts. No I/O.
Ported from scripts/adapters/scores24_adapter.py.
"""

import re
from typing import Any

from bs4 import BeautifulSoup

# Map scores24 sport slugs to internal sport names
SPORT_MAP = {
    "soccer": "football",
    "tennis": "tennis",
    "basketball": "basketball",
    "ice-hockey": "hockey",
    "volleyball": "volleyball",
    "snooker": "snooker",
}

_MATCH_URL_RE = re.compile(r"/en/([a-z-]+)/m-(\d{2}-\d{2}-\d{4})-(.+?)(?:#.*)?$")
_LISTING_URL_RE = re.compile(r"/en/([a-z-]+)/?$")


def _detect_sport(url: str) -> str:
    """Detect sport from scores24 URL."""
    m = _MATCH_URL_RE.search(url)
    if m:
        return SPORT_MAP.get(m.group(1), m.group(1))
    m = _LISTING_URL_RE.search(url)
    if m:
        return SPORT_MAP.get(m.group(1), m.group(1))
    return "football"


class Scores24Adapter:
    """Scores24.live HTML parser for listings, H2H, form, and trends."""

    def parse_fixtures(self, html: str, url: str = "") -> list[dict[str, Any]]:
        """Parse a Scores24 listing page into fixture dicts.

        Returns list of {"home": str, "away": str, "time": str|None,
                         "sport": str, "detail_url": str|None}.
        """
        soup = BeautifulSoup(html, "html.parser")
        sport = _detect_sport(url)
        results: list[dict[str, Any]] = []
        seen: set[str] = set()

        # Find match links in the listing
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if href.endswith("-prediction") or "#" in href:
                continue
            if not _MATCH_URL_RE.match(href):
                continue
            if href in seen:
                continue
            seen.add(href)

            text = a_tag.get_text(separator=" ", strip=True)
            # Try "Home - Away" or "Home vs Away"
            parts = re.split(r"\s+[-–—vs.]+\s+", text, maxsplit=1)
            if len(parts) == 2:
                home = parts[0].strip()
                away = parts[1].strip()
                if len(home) > 1 and len(away) > 1:
                    results.append({
                        "home": home,
                        "away": away,
                        "time": None,
                        "sport": sport,
                        "detail_url": href,
                        "source": "scores24",
                    })

        return results

    def parse_match_detail(self, html: str, url: str = "") -> dict[str, Any]:
        """Parse a Scores24 match detail page.

        Returns {"home": str, "away": str, "h2h": list, "form_home": list,
                 "form_away": list, "odds": list, "trends": list}.
        """
        soup = BeautifulSoup(html, "html.parser")
        result: dict[str, Any] = {
            "home": "",
            "away": "",
            "h2h": [],
            "form_home": [],
            "form_away": [],
            "odds": [],
            "trends": [],
        }

        # Extract team names from title or header
        title = soup.find("h1")
        if title:
            text = title.get_text(strip=True)
            parts = re.split(r"\s+[-–—vs.]+\s+", text, maxsplit=1)
            if len(parts) == 2:
                result["home"] = parts[0].strip()
                result["away"] = parts[1].strip()

        # H2H section
        h2h_section = soup.find(True, id=re.compile(r"h2h|head-to-head", re.I))
        if h2h_section:
            for row in h2h_section.find_all("tr"):
                text = row.get_text(separator=" ", strip=True)
                score_match = re.search(r"(\d+)\s*[-:]\s*(\d+)", text)
                if score_match:
                    result["h2h"].append({
                        "score_home": int(score_match.group(1)),
                        "score_away": int(score_match.group(2)),
                        "raw": text[:200],
                    })

        # Form/last results sections
        for section_id, key in [("form-home", "form_home"), ("form-away", "form_away")]:
            section = soup.find(True, id=re.compile(section_id, re.I))
            if section:
                for row in section.find_all("tr"):
                    text = row.get_text(separator=" ", strip=True)
                    score_match = re.search(r"(\d+)\s*[-:]\s*(\d+)", text)
                    if score_match:
                        result[key].append({
                            "score_home": int(score_match.group(1)),
                            "score_away": int(score_match.group(2)),
                            "raw": text[:200],
                        })

        # Trends section
        trends_section = soup.find(True, id=re.compile(r"trends|tips", re.I))
        if trends_section:
            for item in trends_section.find_all(["li", "div", "p"]):
                text = item.get_text(strip=True)
                if len(text) > 10:
                    result["trends"].append(text[:300])

        return result

    def parse_odds(self, html: str) -> list[dict[str, Any]]:
        """Parse odds from a Scores24 match detail page.

        Returns list of {"bookmaker": str, "market": str, "odds": float}.
        """
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict[str, Any]] = []

        odds_section = soup.find(True, id=re.compile(r"odds", re.I))
        if not odds_section:
            return results

        for row in odds_section.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            bm = cells[0].get_text(strip=True)
            for td in cells[1:]:
                text = td.get_text(strip=True)
                try:
                    odds_val = float(text)
                    if 1.01 <= odds_val <= 100.0:
                        results.append({
                            "bookmaker": bm,
                            "market": "h2h",
                            "odds": odds_val,
                        })
                except ValueError:
                    continue

        return results
