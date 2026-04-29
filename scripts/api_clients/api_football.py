"""API-Football v3 client — per-match stats for 1000+ football leagues globally.

Docs: https://www.api-football.com/documentation-v3
Host: v3.football.api-sports.io
Auth: x-apisports-key header
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .base_client import APISportsClient, CACHE_DIR
from .rate_limiter import RateLimiter

# Import normalize_stats — works both as package and standalone
try:
    from scripts.normalize_stats import NormalizedFixture, NormalizedMatchStats
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from normalize_stats import NormalizedFixture, NormalizedMatchStats

# Map API-Football stat type names → normalized stat keys
STAT_TYPE_MAP = {
    "Corner Kicks": "corners",
    "Fouls": "fouls",
    "Yellow Cards": "yellow_cards",
    "Red Cards": "red_cards",
    "Total Shots": "shots",
    "Shots on Goal": "shots_on_target",
    "Ball Possession": "possession",
    "Offsides": "offsides",
    "Goalkeeper Saves": "saves",
}


class APIFootballClient(APISportsClient):
    """API-Football v3 — per-match stats for 1000+ football leagues globally."""

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="api-football",
            base_url="https://v3.football.api-sports.io",
            rate_limiter=rate_limiter,
        )

    def get_fixtures(self, date: str) -> list:
        """GET /fixtures?date=YYYY-MM-DD → all fixtures for a date.

        Returns list of NormalizedFixture.
        """
        if not self._check_api_key():
            return []

        cache_key = f"football/fixtures/{date}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached:
            return [
                NormalizedFixture(**f) for f in cached.get("fixtures", [])
            ]

        try:
            data = self._request("/fixtures", params={"date": date})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching fixtures for {date}: {e}")
            return []

        fixtures = []
        for item in data.get("response", []):
            fix = item.get("fixture", {})
            league = item.get("league", {})
            teams = item.get("teams", {})

            fixture = NormalizedFixture(
                fixture_id=str(fix.get("id", "")),
                source=self.api_name,
                sport="football",
                competition=league.get("name", ""),
                home_team=teams.get("home", {}).get("name", ""),
                away_team=teams.get("away", {}).get("name", ""),
                home_team_id=str(teams.get("home", {}).get("id", "")),
                away_team_id=str(teams.get("away", {}).get("id", "")),
                kickoff=fix.get("date", ""),
                status=fix.get("status", {}).get("short", "NS"),
            )
            fixtures.append(fixture)

        # Cache raw fixture dicts
        from dataclasses import asdict
        self._save_cache(cache_key, {
            "fixtures": [asdict(f) for f in fixtures],
            "count": len(fixtures),
        })

        print(f"[{self.api_name}] Found {len(fixtures)} fixtures for {date}")
        return fixtures

    def get_fixture_stats(self, fixture_id: str) -> dict | None:
        """GET /fixtures/statistics?fixture={id} → per-match stats.

        Returns NormalizedMatchStats or None if unavailable.
        """
        if not self._check_api_key():
            return None

        cache_key = f"football/stats/{fixture_id}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached and "match_stats" in cached:
            return NormalizedMatchStats(**cached["match_stats"])

        try:
            data = self._request("/fixtures/statistics", params={"fixture": fixture_id})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching stats for fixture {fixture_id}: {e}")
            return None

        response = data.get("response", [])
        if len(response) < 2:
            return None

        stats = {}
        teams = {}
        for team_data in response:
            team_info = team_data.get("team", {})
            team_name = team_info.get("name", "")
            team_id = str(team_info.get("id", ""))
            side = "home" if not teams else "away"
            teams[side] = {"name": team_name, "id": team_id}

            for stat_entry in team_data.get("statistics", []):
                stat_type = stat_entry.get("type", "")
                value = stat_entry.get("value")

                normalized_key = STAT_TYPE_MAP.get(stat_type)
                if not normalized_key:
                    continue

                # Handle possession percentage string
                if normalized_key == "possession" and isinstance(value, str):
                    value = float(value.replace("%", "").strip() or 0)
                elif value is None:
                    value = 0

                if normalized_key not in stats:
                    stats[normalized_key] = {}
                stats[normalized_key][side] = value

        if not teams.get("home") or not teams.get("away"):
            return None

        match_stats = NormalizedMatchStats(
            fixture_id=str(fixture_id),
            source=self.api_name,
            sport="football",
            home_team=teams["home"]["name"],
            away_team=teams["away"]["name"],
            date="",
            stats=stats,
        )

        from dataclasses import asdict
        self._save_cache(cache_key, {"match_stats": asdict(match_stats)})
        return match_stats

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list:
        """GET /fixtures/headtohead?h2h={id1}-{id2}&last={n}

        Returns list of NormalizedFixture with basic info.
        """
        if not self._check_api_key():
            return []

        cache_key = f"football/h2h/{team1_id}-{team2_id}"
        cached = self._check_cache(cache_key, ttl_hours=48)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        try:
            data = self._request(
                "/fixtures/headtohead",
                params={"h2h": f"{team1_id}-{team2_id}", "last": str(last_n)},
            )
        except Exception as e:
            print(f"[{self.api_name}] Error fetching H2H {team1_id} vs {team2_id}: {e}")
            return []

        fixtures = []
        for item in data.get("response", []):
            fix = item.get("fixture", {})
            league = item.get("league", {})
            teams = item.get("teams", {})

            fixture = NormalizedFixture(
                fixture_id=str(fix.get("id", "")),
                source=self.api_name,
                sport="football",
                competition=league.get("name", ""),
                home_team=teams.get("home", {}).get("name", ""),
                away_team=teams.get("away", {}).get("name", ""),
                home_team_id=str(teams.get("home", {}).get("id", "")),
                away_team_id=str(teams.get("away", {}).get("id", "")),
                kickoff=fix.get("date", ""),
                status=fix.get("status", {}).get("short", "FT"),
            )
            fixtures.append(fixture)

        from dataclasses import asdict
        self._save_cache(cache_key, {
            "fixtures": [asdict(f) for f in fixtures],
            "count": len(fixtures),
        })

        return fixtures

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list:
        """GET /fixtures?team={id}&last={n}&status=FT

        Returns last N finished fixtures for a team as list of NormalizedFixture.
        """
        if not self._check_api_key():
            return []

        cache_key = f"football/team_fixtures/{team_id}_last{last_n}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        try:
            data = self._request(
                "/fixtures",
                params={"team": team_id, "last": str(last_n), "status": "FT"},
            )
        except Exception as e:
            print(f"[{self.api_name}] Error fetching last fixtures for team {team_id}: {e}")
            return []

        fixtures = []
        for item in data.get("response", []):
            fix = item.get("fixture", {})
            league = item.get("league", {})
            teams = item.get("teams", {})

            fixture = NormalizedFixture(
                fixture_id=str(fix.get("id", "")),
                source=self.api_name,
                sport="football",
                competition=league.get("name", ""),
                home_team=teams.get("home", {}).get("name", ""),
                away_team=teams.get("away", {}).get("name", ""),
                home_team_id=str(teams.get("home", {}).get("id", "")),
                away_team_id=str(teams.get("away", {}).get("id", "")),
                kickoff=fix.get("date", ""),
                status=fix.get("status", {}).get("short", "FT"),
            )
            fixtures.append(fixture)

        from dataclasses import asdict
        self._save_cache(cache_key, {
            "fixtures": [asdict(f) for f in fixtures],
            "count": len(fixtures),
        })

        return fixtures

    def get_team_stats(self, team_id: str, league_id: str = None, season: str = None) -> dict:
        """GET /teams/statistics?team={id}&league={lid}&season={year}

        Team season aggregate stats. Returns raw dict.
        """
        if not self._check_api_key():
            return {}

        params = {"team": team_id}
        if league_id:
            params["league"] = league_id
        if season:
            params["season"] = season

        cache_key = f"football/team_stats/{team_id}_{league_id}_{season}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached and "stats" in cached:
            return cached["stats"]

        try:
            data = self._request("/teams/statistics", params=params)
        except Exception as e:
            print(f"[{self.api_name}] Error fetching team stats for {team_id}: {e}")
            return {}

        result = data.get("response", {})
        self._save_cache(cache_key, {"stats": result})
        return result

    def resolve_team_id(self, team_name: str) -> str | None:
        """GET /teams?search={name}

        Resolves a team name to API-Football team ID.
        Cache at betting/data/stats_cache/_team_ids/api-football.json
        """
        # Check team ID cache first
        cache_file = CACHE_DIR / "_team_ids" / "api-football.json"
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

        team_id = str(results[0].get("team", {}).get("id", ""))
        if team_id:
            team_ids[name_lower] = team_id
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(team_ids, indent=2, ensure_ascii=False), encoding="utf-8"
            )

        return team_id or None

    def get_injuries(self, fixture_id: str) -> list:
        """GET /injuries?fixture={id}

        Returns list of injury dicts with player info.
        """
        if not self._check_api_key():
            return []

        try:
            data = self._request("/injuries", params={"fixture": fixture_id})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching injuries for fixture {fixture_id}: {e}")
            return []

        injuries = []
        for item in data.get("response", []):
            player = item.get("player", {})
            team = item.get("team", {})
            injuries.append({
                "player": player.get("name", ""),
                "team": team.get("name", ""),
                "type": player.get("type", ""),
                "reason": player.get("reason", ""),
            })

        return injuries
