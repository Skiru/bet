"""Football-Data.org client — EU football fixtures, results, standings.

Docs: https://docs.football-data.org/general/v4/index.html
Host: api.football-data.org/v4
Auth: X-Auth-Token header
Rate limit: 10 requests/minute (free tier)
"""

from pathlib import Path

from .base_client import BaseAPIClient
from .rate_limiter import RateLimiter
from bet.models.normalized import NormalizedFixture, NormalizedMatchStats


class FootballDataOrgClient(BaseAPIClient):
    """Football-Data.org — EU football fixtures, results, standings. Fallback for API-Football."""

    COMPETITION_CODES = {
        "PL": "Premier League",
        "BL1": "Bundesliga",
        "SA": "Serie A",
        "PD": "La Liga",
        "FL1": "Ligue 1",
        "DED": "Eredivisie",
        "PPL": "Primeira Liga",
        "ELC": "Championship",
        "BSA": "Brasileirão",
        "CLI": "Copa Libertadores",
    }

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="football-data-org",
            base_url="https://api.football-data.org/v4",
            rate_limiter=rate_limiter,
        )

    def _build_headers(self) -> dict:
        """Override to use X-Auth-Token header."""
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-Auth-Token"] = self.api_key
        return headers

    def _check_api_key(self) -> bool:
        """Return True if API key is available."""
        if not self.api_key:
            print(f"[{self.api_name}] Skipping — no API key configured")
            return False
        return True

    def get_fixtures(self, date: str) -> list:
        """GET /matches?dateFrom={date}&dateTo={date}

        Returns list of NormalizedFixture.
        Note: Does NOT provide per-match corner/foul stats — only scores.
        """
        if not self._check_api_key():
            return []

        cache_key = f"football-data-org/fixtures/{date}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        try:
            data = self._request(
                "/matches",
                params={"dateFrom": date, "dateTo": date},
            )
        except Exception as e:
            print(f"[{self.api_name}] Error fetching fixtures for {date}: {e}")
            return []

        fixtures = []
        for match in data.get("matches", []):
            home = match.get("homeTeam", {})
            away = match.get("awayTeam", {})
            competition = match.get("competition", {})

            fixture = NormalizedFixture(
                fixture_id=str(match.get("id", "")),
                source=self.api_name,
                sport="football",
                competition=competition.get("name", ""),
                home_team=home.get("name", ""),
                away_team=away.get("name", ""),
                home_team_id=str(home.get("id", "")),
                away_team_id=str(away.get("id", "")),
                kickoff=match.get("utcDate", ""),
                status=match.get("status", "SCHEDULED"),
            )
            fixtures.append(fixture)

        from dataclasses import asdict
        self._save_cache(cache_key, {
            "fixtures": [asdict(f) for f in fixtures],
            "count": len(fixtures),
        })

        print(f"[{self.api_name}] Found {len(fixtures)} fixtures for {date}")
        return fixtures

    def get_fixture_stats(self, fixture_id: str) -> dict:
        """Not supported — Football-Data.org does not provide per-match detailed stats.

        Returns empty dict.
        """
        return {}

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list:
        """Not directly supported. Returns empty list."""
        return []

    def get_team_matches(self, team_id: str, last_n: int = 10) -> list:
        """GET /teams/{id}/matches?status=FINISHED&limit={n}

        Returns list of NormalizedFixture for recent finished matches.
        """
        if not self._check_api_key():
            return []

        cache_key = f"football-data-org/team_matches/{team_id}_last{last_n}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        try:
            data = self._request(
                f"/teams/{team_id}/matches",
                params={"status": "FINISHED", "limit": str(last_n)},
            )
        except Exception as e:
            print(f"[{self.api_name}] Error fetching matches for team {team_id}: {e}")
            return []

        fixtures = []
        for match in data.get("matches", []):
            home = match.get("homeTeam", {})
            away = match.get("awayTeam", {})
            competition = match.get("competition", {})

            fixture = NormalizedFixture(
                fixture_id=str(match.get("id", "")),
                source=self.api_name,
                sport="football",
                competition=competition.get("name", ""),
                home_team=home.get("name", ""),
                away_team=away.get("name", ""),
                home_team_id=str(home.get("id", "")),
                away_team_id=str(away.get("id", "")),
                kickoff=match.get("utcDate", ""),
                status="FT",
            )
            fixtures.append(fixture)

        from dataclasses import asdict
        self._save_cache(cache_key, {
            "fixtures": [asdict(f) for f in fixtures],
            "count": len(fixtures),
        })

        return fixtures

    def get_standings(self, competition: str) -> dict:
        """GET /competitions/{code}/standings

        Returns standings data for a competition code (e.g. 'PL', 'BL1').
        """
        if not self._check_api_key():
            return {}

        cache_key = f"football-data-org/standings/{competition}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached and "standings" in cached:
            return cached["standings"]

        try:
            data = self._request(f"/competitions/{competition}/standings")
        except Exception as e:
            print(f"[{self.api_name}] Error fetching standings for {competition}: {e}")
            return {}

        result = data.get("standings", [])
        self._save_cache(cache_key, {"standings": result})
        return result
