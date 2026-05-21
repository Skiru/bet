"""Volleyball data client with provider-backed match stats and Volleybox aggregates.

Canonical match-level completion comes from `api-volleyball`, with
`espn-volleyball` kept as bounded support for its supported scope. Volleybox
remains aggregate-only team-page support and cannot satisfy rich completion on
its own.
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
    "points", "aces", "blocks", "hitting_pct",
    "sets_won", "total_points", "errors",
    "service_errors", "reception_pct",
]


class VolleyballDataClient:
    """Volleyball client with provider-backed match stats and aggregate team pages."""

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
        """Fetch aggregate team-page statistics from Volleybox.

        Returns aggregate-only stats (aces, blocks, hitting_pct, etc.) or None.
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
                logger.debug(f"Volleybox aggregate page {resp.status_code} for {team_name}")
                return None

            return self._parse_team_page(resp.text)

        except Exception as e:
            logger.warning(f"Volleybox aggregate fetch failed for {team_name}: {e}")
            return None

    def _parse_team_page(self, html: str) -> dict | None:
        """Parse volleybox team page for aggregate stats."""
        stats = {}

        # Look for stat table patterns
        # volleybox.net uses tables with stat names and values
        patterns = {
            "aces": r"Aces?\s*(?:per set)?.*?(\d+\.?\d*)",
            "blocks": r"Blocks?\s*(?:per set)?.*?(\d+\.?\d*)",
            "hitting_pct": r"Attack\s*%.*?(\d+\.?\d*)",
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
        """Fetch volleyball match-level stats from the canonical provider path.

        Return the first provider-backed per-match stats payload that succeeds.
        """
        try:
            from bet.api_clients import get_client
        except ImportError as e:
            logger.debug(f"Volleyball stats client registry unavailable: {e}")
            return None

        for client_name in ("api-volleyball", "espn-volleyball"):
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
                normalized = dict(stats)
                attack_pct = normalized.pop("attack_pct", None)
                if attack_pct is not None and "hitting_pct" not in normalized:
                    normalized["hitting_pct"] = attack_pct
                return normalized

        return None

    @staticmethod
    def _slugify(name: str) -> str:
        s = name.lower().strip()
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"[\s_]+", "-", s)
        return s
