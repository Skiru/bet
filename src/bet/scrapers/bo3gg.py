"""bo3.gg scraper — CS2 statistics (HTTP fallback for HLTV).

Access: Standard HTTP + BeautifulSoup (no Cloudflare issues).
Rate limit: 3 seconds between requests (self-imposed).
Coverage: Professional CS2 — similar to HLTV but less detailed.
Purpose: Fallback when HLTV is blocked by Cloudflare.
"""

import logging
import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup

from bet.scrapers.constants import USER_AGENTS

logger = logging.getLogger(__name__)

BASE_URL = "https://bo3.gg"
RATE_LIMIT_SECONDS = 3.0


class Bo3GGScraper:
    """bo3.gg scraper for CS2 team and match statistics.

    HTTP-accessible fallback when HLTV Cloudflare blocks.
    """

    def __init__(self):
        self._last_request_time = 0.0
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENTS[0]})
        self._team_url_cache: dict[str, str | None] = {}

    def _get(self, url: str) -> BeautifulSoup | None:
        """Rate-limited HTTP GET returning parsed HTML."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < RATE_LIMIT_SECONDS:
            time.sleep(RATE_LIMIT_SECONDS - elapsed)

        try:
            resp = self._session.get(url, timeout=15)
        except requests.RequestException as e:
            self._last_request_time = time.monotonic()
            logger.warning("bo3.gg request failed: %s — %s", url, e)
            return None

        self._last_request_time = time.monotonic()
        if resp.status_code != 200:
            logger.warning("bo3.gg %s returned %d", url, resp.status_code)
            return None
        return BeautifulSoup(resp.text, "html.parser")

    def search_team(self, name: str) -> str | None:
        """Resolve team name → bo3.gg team URL path."""
        lower = name.lower().strip()
        if lower in self._team_url_cache:
            return self._team_url_cache[lower]

        soup = self._get(f"{BASE_URL}/search?q={requests.utils.quote(name)}")
        if not soup:
            self._team_url_cache[lower] = None
            return None

        # Find first team link in search results
        team_link = soup.select_one("a[href*='/team/']")
        if team_link:
            href = team_link.get("href", "")
            self._team_url_cache[lower] = href
            return href

        self._team_url_cache[lower] = None
        return None

    def get_team_stats(self, team_name: str) -> dict:
        """Scrape team statistics from bo3.gg.

        Returns:
            {
                "maps_played": int,
                "maps_won": int,
                "map_win_rate": float,
                "win_rate_l10": float,
                "matches_found": int,
                "rating": float | None,
            }
        """
        team_url = self.search_team(team_name)
        if not team_url:
            logger.warning("bo3.gg: could not find team '%s'", team_name)
            return {}

        soup = self._get(f"{BASE_URL}{team_url}")
        if not soup:
            return {}

        stats: dict[str, Any] = {}

        # Look for overall stats in team profile
        stat_items = soup.select(".team-stat, .stat-item, .stats-row")
        for item in stat_items:
            text = item.get_text().strip().lower()
            # Try to extract maps/wins/losses
            maps_match = re.search(r"maps?[:\s]+(\d+)", text)
            wins_match = re.search(r"wins?[:\s]+(\d+)", text)
            rate_match = re.search(r"win\s*rate[:\s]+([\d.]+)%?", text)

            if maps_match:
                stats["maps_played"] = int(maps_match.group(1))
            if wins_match:
                stats["maps_won"] = int(wins_match.group(1))
            if rate_match:
                stats["map_win_rate"] = float(rate_match.group(1))

        # Recent matches for L10
        matches_soup = self._get(f"{BASE_URL}{team_url}/matches")
        if matches_soup:
            match_rows = matches_soup.select(".match-row, .result-row")[:10]
            wins = 0
            for row in match_rows:
                # Look for win indicator
                if "win" in (row.get("class") or []) or row.select_one(".win, .match-won"):
                    wins += 1
                else:
                    # Check score
                    scores = row.select(".score, .match-score")
                    if len(scores) >= 2:
                        try:
                            s1 = int(re.search(r"\d+", scores[0].get_text()).group())
                            s2 = int(re.search(r"\d+", scores[1].get_text()).group())
                            if s1 > s2:
                                wins += 1
                        except (ValueError, AttributeError):
                            pass

            n = len(match_rows)
            if n > 0:
                stats["win_rate_l10"] = round(wins / n * 100, 1)
                stats["matches_found"] = n

        return stats

    def get_team_map_pool(self, team_name: str) -> dict:
        """Scrape map-specific stats.

        Returns:
            {"map_name": {"played": int, "won": int, "win_rate": float}, ...}
        """
        team_url = self.search_team(team_name)
        if not team_url:
            return {}

        soup = self._get(f"{BASE_URL}{team_url}/maps")
        if not soup:
            return {}

        map_pool: dict[str, dict] = {}
        map_items = soup.select(".map-stat, .map-row")
        for item in map_items:
            name_el = item.select_one(".map-name, .name")
            if not name_el:
                continue
            map_name = name_el.get_text().strip()

            played = 0
            win_rate = 0.0
            # Extract numbers from row
            numbers = re.findall(r"[\d.]+", item.get_text())
            if len(numbers) >= 2:
                try:
                    played = int(numbers[0])
                    win_rate = float(numbers[1])
                except (ValueError, IndexError):
                    pass

            if played > 0:
                map_pool[map_name] = {
                    "played": played,
                    "won": round(played * win_rate / 100),
                    "win_rate": win_rate,
                }

        return map_pool

    def get_h2h(self, team_a: str, team_b: str) -> dict:
        """Head-to-head between two teams.

        Returns:
            {
                "matches_found": int,
                "team_a_wins": int,
                "team_b_wins": int,
            }
        """
        team_a_url = self.search_team(team_a)
        if not team_a_url:
            return {"matches_found": 0, "team_a_wins": 0, "team_b_wins": 0}

        # Try team A's matches page and filter for team B
        soup = self._get(f"{BASE_URL}{team_a_url}/matches")
        if not soup:
            return {"matches_found": 0, "team_a_wins": 0, "team_b_wins": 0}

        team_b_lower = team_b.lower()
        a_wins = 0
        h2h_count = 0

        match_rows = soup.select(".match-row, .result-row")
        for row in match_rows:
            opponent = row.select_one(".opponent, .team-name")
            if not opponent:
                continue
            opp_text = opponent.get_text().strip().lower()
            if team_b_lower not in opp_text and opp_text not in team_b_lower:
                continue

            h2h_count += 1
            if "win" in " ".join(row.get("class", [])) or row.select_one(".win, .match-won"):
                a_wins += 1
            else:
                scores = row.select(".score, .match-score")
                if len(scores) >= 2:
                    try:
                        s1 = int(re.search(r"\d+", scores[0].get_text()).group())
                        s2 = int(re.search(r"\d+", scores[1].get_text()).group())
                        if s1 > s2:
                            a_wins += 1
                    except (ValueError, AttributeError):
                        pass

        return {
            "matches_found": h2h_count,
            "team_a_wins": a_wins,
            "team_b_wins": h2h_count - a_wins,
        }
