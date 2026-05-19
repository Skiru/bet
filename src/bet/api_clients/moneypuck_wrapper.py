"""MoneyPuck BaseAPIClient wrapper for enrichment pipeline integration.

Wraps the existing moneypuck_client.py (season-aggregate NHL advanced stats)
into the BaseAPIClient interface expected by fetch_api_stats.py.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from .base_client import BaseAPIClient, APIError
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

try:
    from bet.api_clients.moneypuck_client import get_team_stats, TEAM_NAMES
    _HAS_MONEYPUCK = True
except ImportError:
    _HAS_MONEYPUCK = False


class MoneyPuckClient(BaseAPIClient):
    """NHL advanced stats (Corsi, Fenwick, xG) via MoneyPuck CSV data."""

    def __init__(self, rate_limiter: RateLimiter | None = None, **kwargs):
        if rate_limiter is None:
            rate_limiter = RateLimiter()
        super().__init__(
            api_name="moneypuck",
            base_url="https://moneypuck.com",
            rate_limiter=rate_limiter,
        )
        self.api_key = "no-key-needed"

    def is_available(self) -> bool:
        return _HAS_MONEYPUCK

    def _load_api_key(self) -> str | None:
        return "no-key-needed"

    def get_fixtures(self, date: str) -> list:
        return []

    def get_fixture_stats(self, fixture_id: str) -> list:
        return []

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list:
        return []

    def resolve_team_id(self, team_name: str, **kwargs) -> str | None:
        """Resolve team name to MoneyPuck abbreviation."""
        name_lower = team_name.lower()
        for abbr, full_name in TEAM_NAMES.items():
            if name_lower in full_name.lower() or full_name.lower() in name_lower:
                return abbr
            # Match last word (e.g., "Lightning" → "TBL")
            parts = full_name.lower().split()
            if any(part in name_lower or name_lower in part for part in parts):
                return abbr
        return None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list:
        """MoneyPuck provides season aggregates, not per-fixture data.
        
        We return a single synthetic 'fixture' containing the season stats
        so the enrichment pipeline can extract them.
        """
        from normalize_stats import NormalizedFixture
        
        stats_data = get_team_stats(team_id)
        if not stats_data:
            return []
        
        # Return a synthetic fixture so get_fixture_stats can use it
        return [NormalizedFixture(
            fixture_id=f"moneypuck_{team_id}_season",
            source="moneypuck",
            sport="hockey",
            competition="NHL",
            home_team=stats_data.get("team_name", team_id),
            away_team="League Average",
            kickoff=datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z"),
            status="FINISHED",
        )]

    def get_team_season_stats(self, team_name: str) -> dict | None:
        """Direct access to season-aggregate advanced stats."""
        return get_team_stats(team_name)
