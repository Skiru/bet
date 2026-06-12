"""API-Volleyball v1 client — adapted for bet.db.models.

Returns APIFixture and APIMatchStats objects.
"""

import re

from .api_football import APIFixture, APIMatchStats
from .base_client import APISportsClient, SourceOperationResult, SourceResultStatus
from .rate_limiter import RateLimiter

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
        """Search for a team by name → return API team ID.

        Prefers men's teams (excludes names ending in ' W') for ambiguous searches.
        """
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
                # Prefer exact match or men's team (not ending in " W")
                best = None
                for r in results:
                    name = r.get("name", "")
                    if name.lower() == team_name.lower():
                        best = r
                        break
                    if not name.endswith(" W") and best is None:
                        best = r
                if best is None:
                    best = results[0]
                tid = str(best.get("id", ""))
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
            # Take first last_n and preserve enough identity to backfill fixture_sources.
            result = []
            for g in finished[:last_n]:
                teams = g.get("teams", {})
                result.append(
                    {
                        "id": str(g.get("id", "")),
                        "date": g.get("date", ""),
                        "home_team": teams.get("home", {}).get("name", ""),
                        "away_team": teams.get("away", {}).get("name", ""),
                    }
                )
            self._save_cache(cache_key, {"fixtures": result})
            return result
        except Exception:
            return []

    def get_match_stats(self, game_id: str) -> dict[str, float] | None:
        """GET /games?id={game_id} → per-match stat dict from scores/periods.

        The volleyball API does NOT have a separate statistics endpoint.
        Stats are extracted from the game response: sets won, total points per set.
        Returns dict like {"sets_won_home": 3, "sets_won_away": 2, "total_points": 186}
        for one game, or None if game not finished.
        """
        if not self._check_api_key():
            return None

        cache_key = f"volleyball/match_stats/{game_id}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return cached.get("stats")

        try:
            data = self._request("/games", params={"id": game_id})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching match {game_id}: {e}")
            return None

        games = data.get("response", [])
        if not games:
            return None

        game = games[0]
        status = game.get("status", {})
        if isinstance(status, dict) and status.get("short") != "FT":
            return None

        scores = game.get("scores", {})
        periods = game.get("periods", {})

        if not scores or not periods:
            return None

        home_points = 0
        away_points = 0
        sets_played = 0
        for period_name in ("first", "second", "third", "fourth", "fifth"):
            period = periods.get(period_name, {})
            if period and period.get("home") is not None:
                home_points += int(period["home"])
                away_points += int(period["away"])
                sets_played += 1

        match_stats: dict[str, float] = {
            "total_points": float(home_points + away_points),
            "sets_won": float(max(scores.get("home", 0), scores.get("away", 0))),
            "sets_played": float(sets_played),
            "points_home": float(home_points),
            "points_away": float(away_points),
        }

        self._save_cache(cache_key, {"stats": match_stats})
        return match_stats

    def get_team_l10_stats(self, team_name: str) -> dict[str, list[float]] | None:
        """Build L10 per-match stat arrays for a team.

        Resolves team → ID, fetches last 10 finished games, gets stats per game.
        Returns dict like {"aces": [5,3,7,...], "blocks": [8,6,9,...], ...}
        """
        team_id = self.resolve_team_id(team_name)
        if not team_id:
            return None

        fixtures = self.get_team_last_fixtures(team_id, last_n=10)
        if not fixtures:
            return None

        l10: dict[str, list[float]] = {}
        for fix in fixtures:
            game_id = str(fix.get("id", ""))
            if not game_id:
                continue
            stats = self.get_match_stats(game_id)
            if not stats:
                continue
            for key, val in stats.items():
                l10.setdefault(key, []).append(val)

        return l10 if l10 else None

    def get_fixtures_result(self, date: str) -> SourceOperationResult:
        """GET /games?date=YYYY-MM-DD with evidence capture.

        Returns SourceOperationResult containing list[APIFixture] on success.
        """
        if not self._check_api_key():
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                error_code="missing_api_key",
            )

        result = self._request_with_evidence(
            endpoint="/games",
            params={"date": date},
            operation="get_fixtures",
            source_event_id=None,
        )

        if result.status != SourceResultStatus.SUCCESS or result.value is None:
            return result

        fixtures = []
        for game in result.value.get("response", []):
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

        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=fixtures,
            http_status=result.http_status,
            evidence_refs=result.evidence_refs,
        )
