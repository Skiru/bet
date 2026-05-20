"""Volleyball data client — fetches team/player stats for volleyball leagues.

Primary sources: ESPN and api-volleyball for match-level stats.
Secondary source: volleybox.net for detailed player stats.
Fallback: Generic web research.

Rate limited, curl_cffi based.
"""

import logging
import re
import time

logger = logging.getLogger(__name__)

try:
    from curl_cffi import requests as c_requests
except ImportError:
    c_requests = None


# Volleyball stat keys we want to extract
VOLLEYBALL_STATS = [
    "points", "aces", "blocks", "attack_pct",
    "sets_won", "total_points", "errors",
    "service_errors", "reception_pct",
]

# Flashscore volleyball sport_id = 12
FLASHSCORE_SPORT_ID = 12


class VolleyballDataClient:
    """Volleyball statistics client using Flashscore + volleybox.net."""

    VOLLEYBOX_BASE = "https://volleybox.net"
    HEADERS = {
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }
    _last_request = 0.0
    _min_interval = 3.0

    def __init__(self):
        if c_requests is None:
            raise ImportError("curl_cffi required for VolleyballDataClient")

    def _rate_limit(self):
        now = time.time()
        elapsed = now - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.time()

    def fetch_team_stats(self, team_name: str, competition: str = "") -> dict | None:
        """Fetch team statistics from volleybox.net.

        Returns dict with stat keys (aces, blocks, attack_pct, etc.) or None.
        """
        slug = self._slugify(team_name)
        url = f"{self.VOLLEYBOX_BASE}/team/{slug}"

        self._rate_limit()
        try:
            resp = c_requests.get(
                url,
                headers=self.HEADERS,
                impersonate="chrome110",
                timeout=15,
            )
            if resp.status_code != 200:
                logger.debug(f"Volleybox {resp.status_code} for {team_name}")
                return None

            return self._parse_team_page(resp.text)

        except Exception as e:
            logger.warning(f"Volleybox fetch failed for {team_name}: {e}")
            return None

    def _parse_team_page(self, html: str) -> dict | None:
        """Parse volleybox team page for aggregate stats."""
        stats = {}

        # Look for stat table patterns
        # volleybox.net uses tables with stat names and values
        patterns = {
            "aces": r"Aces?\s*(?:per set)?.*?(\d+\.?\d*)",
            "blocks": r"Blocks?\s*(?:per set)?.*?(\d+\.?\d*)",
            "attack_pct": r"Attack\s*%.*?(\d+\.?\d*)",
            "reception_pct": r"Reception\s*%.*?(\d+\.?\d*)",
            "service_errors": r"Service\s*errors?.*?(\d+\.?\d*)",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                try:
                    stats[key] = float(match.group(1))
                except (ValueError, TypeError):
                    pass

        return stats if stats else None

    def fetch_match_stats(self, match_id: str) -> dict | None:
        """Fetch volleyball match-level stats from canonical providers.

        Return the first provider-backed stats payload that succeeds.
        """
        try:
            from bet.api_clients import get_client
        except ImportError as e:
            logger.debug(f"Volleyball stats client registry unavailable: {e}")
            return None

        for client_name in ("espn-volleyball", "api-volleyball"):
            try:
                client = get_client(client_name)
                raw_stats = client.get_fixture_stats(match_id)
            except Exception as e:
                logger.debug(f"{client_name} match stats unavailable: {e}")
                continue

            if not raw_stats:
                continue
            payload = raw_stats[0] if isinstance(raw_stats, list) else raw_stats
            stats = getattr(payload, "stats", None)
            if stats is None and isinstance(payload, dict):
                stats = payload.get("stats")
            if isinstance(stats, dict):
                return stats

        return None

    @staticmethod
    def _slugify(name: str) -> str:
        s = name.lower().strip()
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"[\s_]+", "-", s)
        return s
