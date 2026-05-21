"""API-Volleyball v1 client — adapted for bet.db.models.

Returns APIFixture and APIMatchStats objects.
"""

import re

from .base_client import APISportsClient
from .rate_limiter import RateLimiter
from .api_football import APIFixture, APIMatchStats

STAT_TYPE_MAP = {
    "points": "points",
    "total_points": "total_points",
    "aces": "aces",
    "blocks": "blocks",
    "attack_pct": "hitting_pct",
    "hitting_pct": "hitting_pct",
    "sets_won": "sets_won",
    "errors": "errors",
    "service_errors": "errors",
}


def _normalize_stat_type(raw_stat_type: str) -> str:
    normalized = str(raw_stat_type or "").lower().replace("%", " pct ")
    normalized = normalized.replace("percentage", "pct")
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")


class APIVolleyballClient(APISportsClient):
    """Volleyball API client using api-sports.io unified platform."""

    _SHARES_FOOTBALL_KEY = True

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="api-volleyball",
            base_url="https://v1.volleyball.api-sports.io",
            rate_limiter=rate_limiter,
        )

    def get_fixtures(self, date: str) -> list[APIFixture]:
        """GET /games?date=YYYY-MM-DD → list of APIFixture."""
        if not self._check_api_key():
            return []

        cache_key = f"volleyball/fixtures/{date}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached:
            return [
                APIFixture(**f) for f in cached.get("fixtures", [])
                if isinstance(f, dict) and "external_id" in f
            ]

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

            status_raw = game.get("status")
            if isinstance(status_raw, dict):
                status = status_raw.get("long", "scheduled")
            else:
                status = str(status_raw or "NS")

            fixture = APIFixture(
                external_id=str(game.get("id", "")),
                source=self.api_name,
                sport="volleyball",
                competition_name=league.get("name", "Unknown"),
                home_team_name=home.get("name", "Unknown"),
                away_team_name=away.get("name", "Unknown"),
                kickoff=game.get("date", ""),
                status=status,
            )
            fixtures.append(fixture)

        from dataclasses import asdict
        self._save_cache(cache_key, {
            "fixtures": [asdict(f) for f in fixtures],
            "count": len(fixtures),
        })

        return fixtures

    def get_fixture_stats(self, fixture_id: str) -> list[APIMatchStats]:
        """GET /games/statistics?id={fixture_id} → list of APIMatchStats."""
        if not self._check_api_key():
            return []

        cache_key = f"volleyball/fixture_stats/{fixture_id}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return [APIMatchStats(**ms) for ms in cached.get("stats", [])]

        try:
            data = self._request("/games/statistics", params={"id": fixture_id})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching stats for {fixture_id}: {e}")
            return []

        stats: dict[str, dict[str, float]] = {}
        teams: dict[str, str] = {}
        for entry in data.get("response", []):
            team_info = entry.get("team", {})
            if team_info:
                side = "home" if not teams else "away"
                teams[side] = team_info.get("name", "")

            for stat in entry.get("statistics", []):
                stat_type = _normalize_stat_type(stat.get("type", ""))
                mapped = STAT_TYPE_MAP.get(stat_type)
                if mapped:
                    home_val = stat.get("home", 0)
                    away_val = stat.get("away", 0)
                    if home_val is not None and away_val is not None:
                        stats[mapped] = {
                            "home": float(home_val),
                            "away": float(away_val),
                        }

        if not stats or not teams.get("home"):
            return []

        result = [APIMatchStats(
            external_id=fixture_id,
            source=self.api_name,
            sport="volleyball",
            home_team_name=teams.get("home", ""),
            away_team_name=teams.get("away", ""),
            stats=stats,
        )]

        from dataclasses import asdict
        self._save_cache(cache_key, {"stats": [asdict(ms) for ms in result]})

        return result

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Get head-to-head history."""
        if not self._check_api_key():
            return []
        try:
            data = self._request(
                "/games",
                params={"h2h": f"{team1_id}-{team2_id}", "last": str(last_n)},
            )
            return data.get("response", [])
        except Exception:
            return []

    def resolve_team_id(self, team_name: str) -> str | None:
        """Search for a team by name → return API team ID."""
        if not self._check_api_key():
            return None
        cache_key = f"volleyball/team_search/{team_name.lower().replace(' ', '_')}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return cached.get("team_id")
        try:
            data = self._request("/teams", params={"search": team_name})
            results = data.get("response", [])
            if results:
                tid = str(results[0].get("id", ""))
                self._save_cache(cache_key, {"team_id": tid})
                return tid
        except Exception:
            pass
        return None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list[dict]:
        """GET /games?team={id}&season=2024 → filter to last N finished."""
        if not self._check_api_key():
            return []
        cache_key = f"volleyball/team_fixtures/{team_id}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return cached.get("fixtures", [])
        try:
            data = self._request(
                "/games",
                params={"team": team_id, "season": "2024"},
            )
            games = data.get("response", [])
            # Filter to finished games only
            finished = []
            for g in games:
                status = g.get("status")
                if isinstance(status, dict):
                    short = status.get("short", "")
                    long_val = status.get("long", "")
                else:
                    short = str(status or "")
                    long_val = ""
                if short == "FT" or "finished" in long_val.lower():
                    finished.append(g)
            # Sort by date descending (most recent first)
            finished.sort(
                key=lambda g: g.get("date", ""),
                reverse=True,
            )
            # Take first last_n
            result = [{"id": g.get("id")} for g in finished[:last_n]]
            self._save_cache(cache_key, {"fixtures": result})
            return result
        except Exception:
            return []
