"""API-Basketball v1 client — per-game stats for NBA, Euroleague, and 50+ basketball leagues.

Docs: https://www.api-basketball.com/documentation
Host: v1.basketball.api-sports.io
Auth: x-apisports-key header (shared API-Sports account with api-football)
"""

import json
from pathlib import Path

from .base_client import APISportsClient, CACHE_DIR
from .rate_limiter import RateLimiter
from normalize_stats import NormalizedFixture, NormalizedMatchStats


class APIBasketballClient(APISportsClient):
    """API-Basketball v1 — per-game stats for NBA, Euroleague, and 50+ basketball leagues."""

    _SHARES_FOOTBALL_KEY = True

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="api-basketball",
            base_url="https://v1.basketball.api-sports.io",
            rate_limiter=rate_limiter,
        )

    def get_fixtures(self, date: str) -> list:
        """GET /games?date=YYYY-MM-DD → all basketball games for a date.

        Returns list of NormalizedFixture.
        """
        if not self._check_api_key():
            return []

        cache_key = f"basketball/fixtures/{date}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        try:
            data = self._request("/games", params={"date": date})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching fixtures for {date}: {e}")
            return []

        fixtures = []
        for item in data.get("response", []):
            teams = item.get("teams", {})
            league = item.get("league", {})

            fixture = NormalizedFixture(
                fixture_id=str(item.get("id", "")),
                source=self.api_name,
                sport="basketball",
                competition=league.get("name", ""),
                home_team=teams.get("home", {}).get("name", ""),
                away_team=teams.get("away", {}).get("name", ""),
                home_team_id=str(teams.get("home", {}).get("id", "")),
                away_team_id=str(teams.get("away", {}).get("id", "")),
                kickoff=item.get("date", ""),
                status=item.get("status", {}).get("short", "NS") if isinstance(item.get("status"), dict) else str(item.get("status", "NS")),
            )
            fixtures.append(fixture)

        from dataclasses import asdict
        self._save_cache(cache_key, {
            "fixtures": [asdict(f) for f in fixtures],
            "count": len(fixtures),
        })

        print(f"[{self.api_name}] Found {len(fixtures)} fixtures for {date}")
        return fixtures

    def get_fixture_stats(self, game_id: str) -> dict | None:
        """GET /statistics?id={game_id} → team stats for a basketball game.

        Returns NormalizedMatchStats or None if unavailable.
        """
        if not self._check_api_key():
            return None

        cache_key = f"basketball/stats/{game_id}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached and "match_stats" in cached:
            return NormalizedMatchStats(**cached["match_stats"])

        try:
            data = self._request("/statistics", params={"id": game_id})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching stats for game {game_id}: {e}")
            return None

        response = data.get("response", [])
        if len(response) < 2:
            return None

        stats = {}
        teams = {}
        for team_data in response:
            team_info = team_data.get("team", {})
            team_name = team_info.get("name", "")
            side = "home" if not teams else "away"
            teams[side] = {"name": team_name}

            # Statistics may be a list of dicts or a flat dict — handle both
            raw_stats = team_data.get("statistics", [])
            stat_dict = {}
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
                    stats[norm_key][side] = value

        if not teams.get("home") or not teams.get("away"):
            return None

        match_stats = NormalizedMatchStats(
            fixture_id=str(game_id),
            source=self.api_name,
            sport="basketball",
            home_team=teams["home"]["name"],
            away_team=teams["away"]["name"],
            date="",
            stats=stats,
        )

        from dataclasses import asdict
        self._save_cache(cache_key, {"match_stats": asdict(match_stats)})
        return match_stats

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list:
        """GET /games?h2h={id1}-{id2}&last={n}

        Returns list of NormalizedFixture.
        """
        if not self._check_api_key():
            return []

        cache_key = f"basketball/h2h/{team1_id}-{team2_id}"
        cached = self._check_cache(cache_key, ttl_hours=48)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        try:
            data = self._request(
                "/games",
                params={"h2h": f"{team1_id}-{team2_id}", "last": str(last_n)},
            )
        except Exception as e:
            print(f"[{self.api_name}] Error fetching H2H {team1_id} vs {team2_id}: {e}")
            return []

        fixtures = self._parse_game_list(data)

        from dataclasses import asdict
        self._save_cache(cache_key, {
            "fixtures": [asdict(f) for f in fixtures],
            "count": len(fixtures),
        })

        return fixtures

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list:
        """GET /games?team={id}&season={current}&last={n}

        Returns last N finished games for a team as list of NormalizedFixture.
        """
        if not self._check_api_key():
            return []

        cache_key = f"basketball/team_fixtures/{team_id}_last{last_n}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        try:
            data = self._request(
                "/games",
                params={"team": team_id, "last": str(last_n)},
            )
        except Exception as e:
            print(f"[{self.api_name}] Error fetching last fixtures for team {team_id}: {e}")
            return []

        fixtures = self._parse_game_list(data)

        from dataclasses import asdict
        self._save_cache(cache_key, {
            "fixtures": [asdict(f) for f in fixtures],
            "count": len(fixtures),
        })

        return fixtures

    def resolve_team_id(self, team_name: str) -> str | None:
        """GET /teams?search={name}

        Resolves a team name to API-Basketball team ID.
        """
        cache_file = CACHE_DIR / "_team_ids" / "api-basketball.json"
        team_ids = {}
        if cache_file.exists():
            try:
                team_ids = json.loads(cache_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        name_lower = team_name.lower().strip()
        if name_lower in team_ids:
            return team_ids[name_lower]

        if not self._check_api_key():
            return None

        try:
            data = self._request("/teams", params={"search": team_name})
        except Exception as e:
            print(f"[{self.api_name}] Error searching for team '{team_name}': {e}")
            return None

        results = data.get("response", [])
        if not results:
            return None

        team_id = str(results[0].get("id", ""))
        if team_id:
            team_ids[name_lower] = team_id
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(team_ids, indent=2, ensure_ascii=False), encoding="utf-8"
            )

        return team_id or None

    def _parse_game_list(self, data: dict) -> list:
        """Parse API-Basketball game list into NormalizedFixture list."""
        fixtures = []
        for item in data.get("response", []):
            teams = item.get("teams", {})
            league = item.get("league", {})

            fixture = NormalizedFixture(
                fixture_id=str(item.get("id", "")),
                source=self.api_name,
                sport="basketball",
                competition=league.get("name", ""),
                home_team=teams.get("home", {}).get("name", ""),
                away_team=teams.get("away", {}).get("name", ""),
                home_team_id=str(teams.get("home", {}).get("id", "")),
                away_team_id=str(teams.get("away", {}).get("id", "")),
                kickoff=item.get("date", ""),
                status=item.get("status", {}).get("short", "FT") if isinstance(item.get("status"), dict) else str(item.get("status", "FT")),
            )
            fixtures.append(fixture)

        return fixtures
