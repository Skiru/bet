#!/usr/bin/env python3
"""API-Sports Tennis client — fixtures, match stats, H2H via api-sports.io.

Endpoint: v1.tennis.api-sports.io
Uses the same API key as API-Football (api-sports.io unified platform).
Free tier: shares quota with other API-Sports APIs.
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
    "aces": "aces",
    "double_faults": "double_faults",
    "first_serve_pct": "first_serve_pct",
    "break_points_won": "break_points_won",
    "games_won": "games_won",
    "sets_won": "sets_won",
    "total_games": "total_games",
}


class APITennisClient(APISportsClient):
    """Tennis API client using api-sports.io unified platform."""

    _SHARES_FOOTBALL_KEY = True

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="api-tennis",
            base_url="https://v1.tennis.api-sports.io",
            rate_limiter=rate_limiter,
        )

    def get_fixtures(self, date: str) -> list:
        """Get all tennis matches on a date (YYYY-MM-DD).

        Returns list of NormalizedFixture.
        """
        if not self._check_api_key():
            return []

        cache_key = f"tennis/fixtures/{date}"
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
            home = game.get("players", {}).get("home", {})
            away = game.get("players", {}).get("away", {})
            league = game.get("league", {})

            fixture = NormalizedFixture(
                fixture_id=str(game.get("id", "")),
                source=self.api_name,
                sport="tennis",
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
        """Get match statistics for a specific fixture."""
        if not self._check_api_key():
            return None

        cache_key = f"tennis/stats/{fixture_id}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached and "match_stats" in cached:
            return NormalizedMatchStats(**cached["match_stats"])

        try:
            data = self._request("/games/statistics", params={"id": fixture_id})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching stats for {fixture_id}: {e}")
            return None

        stats = {}
        for entry in data.get("response", []):
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

        match_stats = NormalizedMatchStats(
            fixture_id=str(fixture_id),
            source=self.api_name,
            sport="tennis",
            home_team="",
            away_team="",
            date="",
            stats=stats,
        )

        from dataclasses import asdict
        self._save_cache(cache_key, {"match_stats": asdict(match_stats)})
        return match_stats

    def get_h2h(self, player1_id: str, player2_id: str, last_n: int = 10) -> list:
        """Get H2H meetings between two players.

        Returns list of NormalizedFixture.
        """
        if not self._check_api_key():
            return []

        cache_key = f"tennis/h2h/{player1_id}-{player2_id}"
        cached = self._check_cache(cache_key, ttl_hours=48)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        try:
            data = self._request("/games/h2h", params={
                "h2h": f"{player1_id}-{player2_id}",
            })
        except Exception as e:
            print(f"[{self.api_name}] Error fetching H2H {player1_id} vs {player2_id}: {e}")
            return []

        fixtures = []
        for game in data.get("response", [])[:last_n]:
            home = game.get("players", {}).get("home", {})
            away = game.get("players", {}).get("away", {})
            league = game.get("league", {})

            fixture = NormalizedFixture(
                fixture_id=str(game.get("id", "")),
                source=self.api_name,
                sport="tennis",
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

    def resolve_team_id(self, player_name: str) -> str | None:
        """Resolve player name to API ID."""
        if not self._check_api_key():
            return None
        try:
            data = self._request("/players", params={"search": player_name})
        except Exception as e:
            print(f"[{self.api_name}] Error resolving player {player_name}: {e}")
            return None
        players = data.get("response", [])
        if players:
            return str(players[0].get("id", ""))
        return None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list:
        """Get last N fixtures for a player."""
        if not self._check_api_key():
            return []
        try:
            data = self._request("/games", params={
                "player_id": team_id,
                "last": str(last_n),
            })
        except Exception as e:
            print(f"[{self.api_name}] Error fetching last fixtures for {team_id}: {e}")
            return []
        return data.get("response", [])
