"""API-Basketball v1 client — adapted for bet.db.models.

Returns APIFixture and APIMatchStats objects.
"""

from .base_client import APISportsClient
from .rate_limiter import RateLimiter
from .api_football import APIFixture, APIMatchStats


class APIBasketballClient(APISportsClient):
    """API-Basketball v1 — per-game stats for NBA, Euroleague, and 50+ leagues."""

    _SHARES_FOOTBALL_KEY = True

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="api-basketball",
            base_url="https://v1.basketball.api-sports.io",
            rate_limiter=rate_limiter,
        )

    def get_fixtures(self, date: str) -> list[APIFixture]:
        """GET /games?date=YYYY-MM-DD → list of APIFixture."""
        if not self._check_api_key():
            return []

        cache_key = f"basketball/fixtures/{date}"
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
        for item in data.get("response", []):
            teams = item.get("teams", {})
            league = item.get("league", {})
            status_raw = item.get("status")
            if isinstance(status_raw, dict):
                status = status_raw.get("short", "NS")
            else:
                status = str(status_raw or "NS")

            fixture = APIFixture(
                external_id=str(item.get("id", "")),
                source=self.api_name,
                sport="basketball",
                competition_name=league.get("name", ""),
                home_team_name=teams.get("home", {}).get("name", ""),
                away_team_name=teams.get("away", {}).get("name", ""),
                kickoff=item.get("date", ""),
                status=status,
            )
            fixtures.append(fixture)

        from dataclasses import asdict
        self._save_cache(cache_key, {
            "fixtures": [asdict(f) for f in fixtures],
            "count": len(fixtures),
        })

        return fixtures

    def get_fixture_stats(self, game_id: str) -> list[APIMatchStats]:
        """GET /statistics?id={game_id} → list of APIMatchStats."""
        if not self._check_api_key():
            return []

        cache_key = f"basketball/fixture_stats/{game_id}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return [APIMatchStats(**ms) for ms in cached.get("stats", [])]

        try:
            data = self._request("/statistics", params={"id": game_id})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching stats for game {game_id}: {e}")
            return []

        response = data.get("response", [])
        if len(response) < 2:
            return []

        stats: dict[str, dict[str, float]] = {}
        teams: dict[str, str] = {}
        for team_data in response:
            team_info = team_data.get("team", {})
            team_name = team_info.get("name", "")
            side = "home" if not teams else "away"
            teams[side] = team_name

            raw_stats = team_data.get("statistics", [])
            stat_dict: dict = {}
            if isinstance(raw_stats, list):
                for entry in raw_stats:
                    if isinstance(entry, dict):
                        stat_dict.update(entry)
            elif isinstance(raw_stats, dict):
                stat_dict = raw_stats

            stat_mapping = {
                "points": ["points", "totalPoints"],
                "rebounds": ["totalRebounds", "rebounds"],
                "assists": ["assists"],
                "steals": ["steals"],
                "blocks": ["blocks"],
                "turnovers": ["turnovers"],
                "fg_pct": ["fieldGoalsPercentage", "fgPct"],
                "three_pct": ["threePointsPercentage", "threePct"],
                "ft_pct": ["freeThrowsPercentage", "ftPct"],
                "offensive_rebounds": ["offRebounds", "offensiveRebounds"],
                "defensive_rebounds": ["defRebounds", "defensiveRebounds"],
                "fast_break_points": ["fastBreakPoints"],
                "points_in_paint": ["pointsInPaint"],
                "fouls": ["personalFouls", "fouls"],
            }

            for norm_key, api_keys in stat_mapping.items():
                value = None
                for api_key in api_keys:
                    if api_key in stat_dict and stat_dict[api_key] is not None:
                        value = stat_dict[api_key]
                        break
                if value is not None:
                    if isinstance(value, str):
                        try:
                            value = float(value.replace("%", "").strip())
                        except (ValueError, AttributeError):
                            value = 0
                    if norm_key not in stats:
                        stats[norm_key] = {}
                    stats[norm_key][side] = float(value)

        if not teams.get("home") or not teams.get("away"):
            return []

        result = [APIMatchStats(
            external_id=game_id,
            source=self.api_name,
            sport="basketball",
            home_team_name=teams["home"],
            away_team_name=teams["away"],
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
        import re
        safe_name = re.sub(r"[^a-z0-9_]", "_", team_name.lower())
        cache_key = f"basketball/team_search/{safe_name}"
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
        """GET /games?team={id}&season=2024-2025 → filter to last N finished."""
        if not self._check_api_key():
            return []
        cache_key = f"basketball/team_fixtures/{team_id}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return cached.get("fixtures", [])
        try:
            from datetime import datetime
            now = datetime.now()
            season_start = now.year if now.month >= 10 else now.year - 1
            season_str = f"{season_start}-{season_start + 1}"

            data = self._request(
                "/games",
                params={"team": team_id, "season": season_str},
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
                if short in ("FT", "AOT") or long_val == "Game Finished":
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
