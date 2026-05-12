"""TheSportsDB client — universal sports fixture database.

Docs: https://www.thesportsdb.com/api.php
Free tier key: "3" (default). Premium key goes in URL path.
"""

import json
from pathlib import Path

from .base_client import BaseAPIClient, CACHE_DIR
from .rate_limiter import RateLimiter
from normalize_stats import NormalizedFixture

# TheSportsDB sport name → our internal sport key
SPORT_MAP = {
    "Soccer": "football",
    "Basketball": "basketball",
    "Ice Hockey": "hockey",
    "Tennis": "tennis",
    "Volleyball": "volleyball",
}


class TheSportsDBClient(BaseAPIClient):
    """TheSportsDB — universal sports fixture database. Basic data only.

    NOTE: As of 2026-05-11, TheSportsDB free tier (key "3") has a 97.8%
    failure rate. The free API appears to be deprecated or severely
    rate-limited. Premium keys may still work. This client is disabled
    until a working key or endpoint is confirmed.
    """

    _HOST_BROKEN = True  # 97.8% fail rate as of 2026-05-11

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="thesportsdb",
            base_url="https://www.thesportsdb.com/api/v1/json",
            rate_limiter=rate_limiter,
        )

    def is_available(self) -> bool:
        """Disabled — free tier no longer reliable (97.8% fail rate)."""
        if self._HOST_BROKEN:
            return False
        return super().is_available()

    def _get_base_url(self) -> str:
        """Build base URL with API key in path."""
        key = self._load_api_key() or "3"
        return f"https://www.thesportsdb.com/api/v1/json/{key}"

    def _request(self, endpoint: str, params: dict | None = None, cost: int = 1) -> dict:
        """Override _request to use key-in-URL pattern.

        Builds a thread-safe URL without mutating self.base_url, so
        concurrent threads sharing this client instance won't race.
        """
        import requests as _requests
        from .base_client import (
            APIRateLimitError, APINotFoundError, APIError, _record_source_health,
        )

        if not self.rate_limiter.can_request(self.api_name, cost):
            remaining = self.rate_limiter.get_remaining(self.api_name)
            raise APIRateLimitError(
                f"[{self.api_name}] Daily quota exhausted. Remaining: {remaining}"
            )

        url = f"{self._get_base_url()}{endpoint}"
        last_error = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = _requests.get(
                    url, params=params, headers=self._build_headers(),
                    timeout=self.TIMEOUT,
                )
                if response.status_code == 429:
                    raise APIRateLimitError(
                        f"[{self.api_name}] HTTP 429", status_code=429)
                if response.status_code == 404:
                    raise APINotFoundError(
                        f"[{self.api_name}] Not found: {endpoint}", status_code=404)
                if response.status_code >= 400:
                    raise APIError(
                        f"[{self.api_name}] HTTP {response.status_code}: {response.text[:200]}",
                        status_code=response.status_code)

                self.rate_limiter.record_request(self.api_name, endpoint, cost)
                _record_source_health(self.api_name, success=True)
                return response.json()

            except APIRateLimitError:
                _record_source_health(self.api_name, success=False)
                raise
            except APINotFoundError:
                raise
            except APIError:
                _record_source_health(self.api_name, success=False)
                raise
            except _requests.exceptions.RequestException as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    import time
                    backoff = self.BACKOFF_BASE * (2 ** (attempt - 1))
                    time.sleep(backoff)

        _record_source_health(self.api_name, success=False)
        raise APIError(f"[{self.api_name}] Failed after {self.MAX_RETRIES} attempts: {last_error}")

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
