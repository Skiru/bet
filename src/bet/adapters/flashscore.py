"""Flashscore adapter — parse fixture lists and match details from HTML.

Pure parser: accepts HTML, returns structured dicts. No I/O.
Ported from scripts/adapters/flashscore_adapter.py — simplified for 7 sports.
"""

import re
from typing import Any

from bs4 import BeautifulSoup

# Flashscore URL patterns per sport
SPORT_URLS = {
    "football": "https://www.flashscore.com/football/",
    "basketball": "https://www.flashscore.com/basketball/",
    "hockey": "https://www.flashscore.com/hockey/",
    "tennis": "https://www.flashscore.com/tennis/",
    "volleyball": "https://www.flashscore.com/volleyball/",
    "snooker": "https://www.flashscore.com/snooker/",
    "speedway": "https://www.flashscore.com/motorsport/speedway/",
}

# Patterns for identifying match row elements
_MATCH_CLASS_RE = re.compile(r"event__match|event__participant", re.I)
_HOME_RE = re.compile(r"homeParticipant|participant--home", re.I)
_AWAY_RE = re.compile(r"awayParticipant|participant--away", re.I)
_HEADER_CLASS_RE = re.compile(
    r"event__header|event__title|league-header|tournament-header", re.I
)
_TIME_CLASS_RE = re.compile(r"event__time|event__stage|event__startTime", re.I)

# Garbage patterns — page chrome, not real matches
_GARBAGE_RE = re.compile(
    r"today's matches|pinned leagues|my teams|add the team|advertisement|"
    r"overview|preview|head-to-head|line-ups|"
    r"completed|match stats|pregame report|postgame",
    re.I,
)


def _is_garbage(home: str, away: str) -> bool:
    """Return True if parsed home/away looks like page chrome."""
    if not home or not away:
        return True
    if len(home) > 60 or len(away) > 60:
        return True
    if home.strip().lower() == away.strip().lower():
        return True
    if _GARBAGE_RE.search(home) or _GARBAGE_RE.search(away):
        return True
    if " / " in home or " / " in away:
        return True
    return False


class FlashscoreAdapter:
    """Flashscore HTML parser for fixture lists and match details."""

    def parse_fixtures(self, html: str, sport: str) -> list[dict[str, Any]]:
        """Parse a Flashscore listing page into fixture dicts.

        Returns list of {"home": str, "away": str, "time": str|None,
                         "league": str, "kickoff": str|None}.
        """
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict[str, Any]] = []
        current_league = ""

        # Strategy 1: Flashscore event__ class structure
        all_elements = soup.find_all(
            True,
            class_=lambda c: c and (
                _MATCH_CLASS_RE.search(" ".join(c) if isinstance(c, list) else c)
                or _HEADER_CLASS_RE.search(" ".join(c) if isinstance(c, list) else c)
            ),
        )

        for el in all_elements:
            classes = " ".join(el.get("class", []))

            # Update league context from headers
            if _HEADER_CLASS_RE.search(classes):
                current_league = el.get_text(strip=True)[:100]
                continue

            # Look for match container
            if not _MATCH_CLASS_RE.search(classes):
                continue

            # Find home/away participants
            home_el = el.find(True, class_=lambda c: c and _HOME_RE.search(
                " ".join(c) if isinstance(c, list) else c))
            away_el = el.find(True, class_=lambda c: c and _AWAY_RE.search(
                " ".join(c) if isinstance(c, list) else c))

            if not home_el or not away_el:
                continue

            home = home_el.get_text(strip=True)
            away = away_el.get_text(strip=True)

            if _is_garbage(home, away):
                continue

            # Extract time
            match_time = None
            time_el = el.find(True, class_=lambda c: c and _TIME_CLASS_RE.search(
                " ".join(c) if isinstance(c, list) else c))
            if time_el:
                match_time = time_el.get_text(strip=True)

            results.append({
                "home": home,
                "away": away,
                "time": match_time,
                "league": current_league,
                "source": "flashscore",
            })

        # Strategy 2: Fallback — find "Home - Away" patterns in text
        if not results:
            results = self._fallback_parse(soup)

        return results

    def parse_match_detail(self, html: str, sport: str) -> list[dict[str, Any]]:
        """Parse a Flashscore match detail page for statistics.

        Returns list of {"stat_key": str, "home_value": float, "away_value": float}.
        """
        soup = BeautifulSoup(html, "html.parser")
        stats: list[dict[str, Any]] = []

        # Look for stat rows: typically <div class="stat__...">
        stat_rows = soup.find_all(
            True,
            class_=lambda c: c and re.search(r"stat__row|statistic", " ".join(c) if isinstance(c, list) else c, re.I),
        )

        for row in stat_rows:
            text = row.get_text(separator="|", strip=True)
            parts = text.split("|")
            if len(parts) >= 3:
                try:
                    home_val = float(parts[0].replace("%", "").strip())
                    stat_name = parts[1].strip().lower().replace(" ", "_")
                    away_val = float(parts[2].replace("%", "").strip())
                    stats.append({
                        "stat_key": stat_name,
                        "home_value": home_val,
                        "away_value": away_val,
                    })
                except (ValueError, IndexError):
                    continue

        return stats

    def parse_h2h(self, html: str) -> list[dict[str, Any]]:
        """Parse H2H section from Flashscore match detail page."""
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict[str, Any]] = []

        h2h_rows = soup.find_all(
            True,
            class_=lambda c: c and re.search(r"h2h|rows", " ".join(c) if isinstance(c, list) else c, re.I),
        )

        for row in h2h_rows:
            text = row.get_text(separator=" ", strip=True)
            # Try to parse "Team1 score - score Team2"
            match = re.search(r"(\d+)\s*[-:]\s*(\d+)", text)
            if match:
                results.append({
                    "score_home": int(match.group(1)),
                    "score_away": int(match.group(2)),
                    "raw": text[:200],
                })

        return results

    def _fallback_parse(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Fallback: find team pairs from link text or table rows."""
        results: list[dict[str, Any]] = []
        separator_re = re.compile(r"\s+[-–—vs.]+\s+")

        for link in soup.find_all("a", href=True):
            text = link.get_text(strip=True)
            if separator_re.search(text):
                parts = separator_re.split(text, maxsplit=1)
                if len(parts) == 2:
                    home, away = parts[0].strip(), parts[1].strip()
                    if not _is_garbage(home, away) and len(home) > 1 and len(away) > 1:
                        results.append({
                            "home": home,
                            "away": away,
                            "time": None,
                            "league": "",
                            "source": "flashscore",
                        })

        return results
