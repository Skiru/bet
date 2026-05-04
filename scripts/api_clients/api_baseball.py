#!/usr/bin/env python3
"""API-Sports Baseball client — fixtures, match stats, H2H.

Endpoint: v1.baseball.api-sports.io
Uses the same API key as API-Football (api-sports.io unified platform).
"""

import json
from pathlib import Path

from .base_client import APISportsClient, CACHE_DIR
from .rate_limiter import RateLimiter

try:
    from scripts.normalize_stats import NormalizedFixture, NormalizedMatchStats
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from normalize_stats import NormalizedFixture, NormalizedMatchStats


STAT_TYPE_MAP = {
    "runs": "runs",
    "total_runs": "total_runs",
    "hits": "hits",
    "errors": "errors",
    "strikeouts": "strikeouts",
    "walks": "walks",
    "home_runs": "home_runs",
}


class APIBaseballClient(APISportsClient):
    """Baseball API client using api-sports.io unified platform."""

    _SHARES_FOOTBALL_KEY = True

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="api-baseball",
            base_url="https://v1.baseball.api-sports.io",
            rate_limiter=rate_limiter,
        )

    def get_fixtures(self, date: str) -> list:
        """Get all baseball games on a date (YYYY-MM-DD).

        Returns list of NormalizedFixture.
        """
        if not self._check_api_key():
            return []

        cache_key = f"baseball/fixtures/{date}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        try:
            data = self._request("/games", params={"date": date})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching fixtures for {date}: {e}")
            return []

        fixtures = []
        for game in data.get("response", []):
            teams = game.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            league = game.get("league", {})

            fixture = NormalizedFixture(
                fixture_id=str(game.get("id", "")),
                source=self.api_name,
                sport="baseball",
                competition=league.get("name", "Unknown"),
                home_team=home.get("name", "Unknown"),
                away_team=away.get("name", "Unknown"),
                home_team_id=str(home.get("id", "")),
                away_team_id=str(away.get("id", "")),
                kickoff=game.get("date", ""),
                status=game.get("status", {}).get("long", "scheduled") if isinstance(game.get("status"), dict) else str(game.get("status", "NS")),
            )
            fixtures.append(fixture)

        from dataclasses import asdict
        self._save_cache(cache_key, {
            "fixtures": [asdict(f) for f in fixtures],
            "count": len(fixtures),
        })

        print(f"[{self.api_name}] Found {len(fixtures)} fixtures for {date}")
        return fixtures

    def get_fixture_stats(self, fixture_id: str) -> dict | None:
        """Get game statistics for a specific fixture."""
        if not self._check_api_key():
            return None

        cache_key = f"baseball/stats/{fixture_id}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached and "match_stats" in cached:
            return NormalizedMatchStats(**cached["match_stats"])

        try:
            data = self._request("/games/statistics", params={"id": fixture_id})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching stats for {fixture_id}: {e}")
            return None

        stats = {}
        teams = {}
        for entry in data.get("response", []):
            # Extract team info from response entries
            team_info = entry.get("team", {})
            if team_info:
                side = "home" if not teams else "away"
                teams[side] = {
                    "name": team_info.get("name", ""),
                    "id": str(team_info.get("id", "")),
                }
            for stat in entry.get("statistics", []):
                stat_type = stat.get("type", "").lower().replace(" ", "_")
                mapped = STAT_TYPE_MAP.get(stat_type)
                if mapped:
                    stats[mapped] = {
                        "home": stat.get("home", 0),
                        "away": stat.get("away", 0),
                    }

        if not stats:
            return None

        # Get date from fixture cache if available
        fixture_date = ""
        fixture_cache_key = f"baseball/fixtures_detail/{fixture_id}"
        fixture_cached = self._check_cache(fixture_cache_key, ttl_hours=24)
        if fixture_cached:
            fixture_date = fixture_cached.get("date", "")

        match_stats = NormalizedMatchStats(
            fixture_id=str(fixture_id),
            source=self.api_name,
            sport="baseball",
            home_team=teams.get("home", {}).get("name", ""),
            away_team=teams.get("away", {}).get("name", ""),
            date=fixture_date,
            stats=stats,
        )

        from dataclasses import asdict
        self._save_cache(cache_key, {"match_stats": asdict(match_stats)})
        return match_stats

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list:
        """Get H2H meetings between two teams.

        Returns list of NormalizedFixture.
        """
        if not self._check_api_key():
            return []

        cache_key = f"baseball/h2h/{team1_id}-{team2_id}"
        cached = self._check_cache(cache_key, ttl_hours=48)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        try:
            data = self._request("/games", params={
                "h2h": f"{team1_id}-{team2_id}",
                "last": str(last_n),
            })
        except Exception as e:
            print(f"[{self.api_name}] Error fetching H2H {team1_id} vs {team2_id}: {e}")
            return []

        fixtures = []
        for game in data.get("response", []):
            teams = game.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            league = game.get("league", {})

            fixture = NormalizedFixture(
                fixture_id=str(game.get("id", "")),
                source=self.api_name,
                sport="baseball",
                competition=league.get("name", ""),
                home_team=home.get("name", ""),
                away_team=away.get("name", ""),
                home_team_id=str(home.get("id", "")),
                away_team_id=str(away.get("id", "")),
                kickoff=game.get("date", ""),
                status="FT",
            )
            fixtures.append(fixture)

        from dataclasses import asdict
        self._save_cache(cache_key, {
            "fixtures": [asdict(f) for f in fixtures],
            "count": len(fixtures),
        })

        return fixtures

    def resolve_team_id(self, team_name: str) -> str | None:
        """Resolve team name to API ID."""
        if not self._check_api_key():
            return None
        try:
            data = self._request("/teams", params={"search": team_name})
        except Exception as e:
            print(f"[{self.api_name}] Error resolving team {team_name}: {e}")
            return None
        teams = data.get("response", [])
        if teams:
            return str(teams[0].get("id", ""))
        return None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list:
        """Get last N fixtures for a team."""
        if not self._check_api_key():
            return []
        try:
            data = self._request("/games", params={
                "team": team_id,
                "last": str(last_n),
            })
        except Exception as e:
            print(f"[{self.api_name}] Error fetching last fixtures for {team_id}: {e}")
            return []
        return data.get("response", [])
