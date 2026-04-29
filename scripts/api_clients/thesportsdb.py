"""TheSportsDB client — universal sports fixture database.

Docs: https://www.thesportsdb.com/api.php
Free tier key: "3" (default). Premium key goes in URL path.
"""

import json
from pathlib import Path

from .base_client import BaseAPIClient, CACHE_DIR
from .rate_limiter import RateLimiter

try:
    from scripts.normalize_stats import NormalizedFixture
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from normalize_stats import NormalizedFixture

# TheSportsDB sport name → our internal sport key
SPORT_MAP = {
    "Soccer": "football",
    "Basketball": "basketball",
    "Ice Hockey": "hockey",
    "Tennis": "tennis",
    "Volleyball": "volleyball",
    "Handball": "handball",
    "Baseball": "baseball",
    "American Football": "football_am",
    "Motorsport": "motorsport",
    "Fighting": "mma",
}


class TheSportsDBClient(BaseAPIClient):
    """TheSportsDB — universal sports fixture database. Basic data only."""

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="thesportsdb",
            base_url="https://www.thesportsdb.com/api/v1/json",
            rate_limiter=rate_limiter,
        )

    def _get_base_url(self) -> str:
        """Build base URL with API key in path."""
        key = self._load_api_key() or "3"
        return f"https://www.thesportsdb.com/api/v1/json/{key}"

    def _request(self, endpoint: str, params: dict | None = None, cost: int = 1) -> dict:
        """Override _request to use key-in-URL pattern instead of base_url."""
        # TheSportsDB puts the key in the URL path, not in headers
        original_base = self.base_url
        self.base_url = self._get_base_url()
        try:
            return super()._request(endpoint, params=params, cost=cost)
        finally:
            self.base_url = original_base

    def get_fixtures(self, date: str) -> list:
        """GET /{key}/eventsday.php?d={YYYY-MM-DD} → events on a date.

        Returns list of NormalizedFixture across all sports.
        """
        cache_key = f"thesportsdb/fixtures/{date}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        try:
            data = self._request("/eventsday.php", params={"d": date})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching fixtures for {date}: {e}")
            return []

        events = data.get("events") or []
        fixtures = []
        for event in events:
            sport_raw = event.get("strSport", "")
            sport = SPORT_MAP.get(sport_raw, sport_raw.lower().replace(" ", "_"))

            fixture = NormalizedFixture(
                fixture_id=str(event.get("idEvent", "")),
                source=self.api_name,
                sport=sport,
                competition=event.get("strLeague", ""),
                home_team=event.get("strHomeTeam", ""),
                away_team=event.get("strAwayTeam", ""),
                kickoff=event.get("strTimestamp", event.get("dateEvent", "")),
                status="scheduled",
            )
            fixtures.append(fixture)

        from dataclasses import asdict
        self._save_cache(cache_key, {
            "fixtures": [asdict(f) for f in fixtures],
            "count": len(fixtures),
        })

        print(f"[{self.api_name}] Found {len(fixtures)} events for {date}")
        return fixtures

    def get_fixture_stats(self, fixture_id: str) -> dict | None:
        """TheSportsDB free tier has no per-game stats. Returns None."""
        return None

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list:
        """TheSportsDB free tier has no H2H endpoint. Returns empty list."""
        return []

    def search_team(self, team_name: str) -> dict | None:
        """GET /{key}/searchteams.php?t={team} → team search.

        Returns first matching team dict or None.
        """
        cache_key = f"thesportsdb/team_search/{team_name.lower().replace(' ', '_')}"
        cached = self._check_cache(cache_key, ttl_hours=168)  # 1 week
        if cached and "team" in cached:
            return cached["team"]

        try:
            data = self._request("/searchteams.php", params={"t": team_name})
        except Exception as e:
            print(f"[{self.api_name}] Error searching for team '{team_name}': {e}")
            return None

        teams = data.get("teams") or []
        if not teams:
            return None

        team = teams[0]
        self._save_cache(cache_key, {"team": team})
        return team

    def get_event_details(self, event_id: str) -> dict | None:
        """GET /{key}/lookupevent.php?id={id} → event details."""
        try:
            data = self._request("/lookupevent.php", params={"id": event_id})
        except Exception as e:
            print(f"[{self.api_name}] Error looking up event {event_id}: {e}")
            return None

        events = data.get("events") or []
        return events[0] if events else None

    def resolve_team_id(self, team_name: str) -> str | None:
        """Resolve team name to TheSportsDB team ID."""
        team = self.search_team(team_name)
        if team:
            return str(team.get("idTeam", "")) or None
        return None
