# DEPRECATED 2026-05-13 — v1 API deprecated, 100% failure rate. DO NOT USE.
"""BallDontLie + nba_api — deep NBA statistics.

DEPRECATED (2026-05-11): BallDontLie v1 API is deprecated and returns 100%
failures. This client is removed from CLIENT_REGISTRY and the basketball
fallback chain. File retained only for nba_api-based methods which are now
served by nba_api_client.py.

BallDontLie API: https://www.balldontlie.io/home.html (paid only since v2)
nba_api: Python package for NBA.com stats (fallback, rate-limited)
"""

import json
import time
from pathlib import Path

from .base_client import BaseAPIClient, CACHE_DIR
from .rate_limiter import RateLimiter
from normalize_stats import NormalizedFixture, NormalizedMatchStats

# Optional nba_api import
try:
    from nba_api.stats.endpoints import teamgamelog, leaguegamefinder
    from nba_api.stats.static import teams as nba_teams
    HAS_NBA_API = True
except ImportError:
    HAS_NBA_API = False


class NBAStatsClient(BaseAPIClient):
    """BallDontLie + nba_api — deep NBA statistics.

    NOTE: As of 2026-05-11, BallDontLie v1 API is deprecated and returns
    100% failures. The service migrated to a paid model requiring a
    registered API key. Without a valid key in config/api_keys.json
    under "balldontlie", this client is disabled.
    """

    _HOST_BROKEN = True  # 100% fail rate as of 2026-05-11, v1 deprecated

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="balldontlie",
            base_url="https://api.balldontlie.io/v1",
            rate_limiter=rate_limiter,
        )

    def _check_api_key(self) -> bool:
        """BallDontLie requires a paid API key since v1 deprecation."""
        return bool(self.api_key)

    def is_available(self) -> bool:
        """Disabled — BallDontLie v1 deprecated, requires paid key."""
        if self._HOST_BROKEN:
            return False
        return bool(self.api_key)

    def _build_headers(self) -> dict:
        """Add Authorization header if API key is available."""
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = self.api_key
        return headers

    def get_fixtures(self, date: str) -> list:
        """DEPRECATED — BallDontLie v1 API is dead. Returns [] immediately."""
        import logging
        logging.getLogger(__name__).warning(
            "[%s] DEPRECATED: v1 API deprecated, 100%% failure rate. Returning [].",
            self.api_name,
        )
        return []

    def _get_fixtures_legacy(self, date: str) -> list:
        """GET /games?dates[]={YYYY-MM-DD} → NBA games on a date.

        LEGACY — kept for reference only. Do not call.
        Returns list of NormalizedFixture.
        """
        cache_key = f"nba/fixtures/{date}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        try:
            data = self._request("/games", params={"dates[]": date})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching fixtures for {date}: {e}")
            return []

        fixtures = []
        for item in data.get("data", []):
            home = item.get("home_team", {})
            visitor = item.get("visitor_team", {})

            fixture = NormalizedFixture(
                fixture_id=str(item.get("id", "")),
                source=self.api_name,
                sport="basketball",
                competition="NBA",
                home_team=home.get("full_name", ""),
                away_team=visitor.get("full_name", ""),
                home_team_id=str(home.get("id", "")),
                away_team_id=str(visitor.get("id", "")),
                kickoff=item.get("date", ""),
                status="FT" if item.get("status") == "Final" else "NS",
            )
            fixtures.append(fixture)

        from dataclasses import asdict
        self._save_cache(cache_key, {
            "fixtures": [asdict(f) for f in fixtures],
            "count": len(fixtures),
        })

        print(f"[{self.api_name}] Found {len(fixtures)} NBA fixtures for {date}")
        return fixtures

    def get_fixture_stats(self, game_id: str) -> dict | None:
        """GET /stats?game_ids[]={id} → player box scores, aggregated to team totals.

        Returns NormalizedMatchStats or None if unavailable.
        """
        cache_key = f"nba/stats/{game_id}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached and "match_stats" in cached:
            return NormalizedMatchStats(**cached["match_stats"])

        try:
            data = self._request("/stats", params={"game_ids[]": game_id})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching stats for game {game_id}: {e}")
            return None

        player_stats = data.get("data", [])
        if not player_stats:
            return None

        # Aggregate player stats into team totals
        team_totals = {}  # team_id → {name, pts, reb, ast, stl, blk, turnover}
        for ps in player_stats:
            team = ps.get("team", {})
            team_id = str(team.get("id", ""))
            if team_id not in team_totals:
                team_totals[team_id] = {
                    "name": team.get("full_name", team.get("name", "")),
                    "points": 0, "rebounds": 0, "assists": 0,
                    "steals": 0, "blocks": 0, "turnovers": 0,
                }
            t = team_totals[team_id]
            t["points"] += ps.get("pts", 0) or 0
            t["rebounds"] += ps.get("reb", 0) or 0
            t["assists"] += ps.get("ast", 0) or 0
            t["steals"] += ps.get("stl", 0) or 0
            t["blocks"] += ps.get("blk", 0) or 0
            t["turnovers"] += ps.get("turnover", 0) or 0

        if len(team_totals) < 2:
            return None

        teams_list = list(team_totals.values())
        home_totals = teams_list[0]
        away_totals = teams_list[1]

        stats = {}
        for stat_key in ["points", "rebounds", "assists", "steals", "blocks", "turnovers"]:
            stats[stat_key] = {
                "home": home_totals.get(stat_key, 0),
                "away": away_totals.get(stat_key, 0),
            }

        match_stats = NormalizedMatchStats(
            fixture_id=str(game_id),
            source=self.api_name,
            sport="basketball",
            home_team=home_totals["name"],
            away_team=away_totals["name"],
            date="",
            stats=stats,
        )

        from dataclasses import asdict
        self._save_cache(cache_key, {"match_stats": asdict(match_stats)})
        return match_stats

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list:
        """Search game logs for matchups between two teams.

        Uses nba_api LeagueGameFinder if available, else returns empty.
        BallDontLie doesn't have a direct H2H endpoint.
        """
        if not HAS_NBA_API:
            print(f"[{self.api_name}] H2H requires nba_api package — not installed")
            return []

        cache_key = f"nba/h2h/{team1_id}-{team2_id}"
        cached = self._check_cache(cache_key, ttl_hours=48)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        try:
            time.sleep(2)  # Rate limit nba_api
            finder = leaguegamefinder.LeagueGameFinder(
                team_id_nullable=team1_id,
                vs_team_id_nullable=team2_id,
            )
            games_df = finder.get_data_frames()[0]

            fixtures = []
            for _, row in games_df.head(last_n).iterrows():
                fixture = NormalizedFixture(
                    fixture_id=str(row.get("GAME_ID", "")),
                    source="nba_api",
                    sport="basketball",
                    competition="NBA",
                    home_team=str(row.get("TEAM_NAME", "")),
                    away_team="",
                    kickoff=str(row.get("GAME_DATE", "")),
                    status="FT",
                )
                fixtures.append(fixture)

            from dataclasses import asdict
            self._save_cache(cache_key, {
                "fixtures": [asdict(f) for f in fixtures],
                "count": len(fixtures),
            })

            return fixtures
        except Exception as e:
            print(f"[{self.api_name}] nba_api H2H error: {e}")
            return []

    def get_team_game_log(self, team_name: str, last_n: int = 10) -> list:
        """Get team game log — try nba_api first (richer), fall back to BallDontLie.

        Returns list of dicts with game stats.
        """
        if HAS_NBA_API:
            result = self._get_game_log_nba_api(team_name, last_n)
            if result:
                return result

        return self._get_game_log_bdl(team_name, last_n)

    def _get_game_log_nba_api(self, team_name: str, last_n: int) -> list:
        """Fetch game log via nba_api."""
        try:
            matches = nba_teams.find_teams_by_full_name(team_name)
            if not matches:
                matches = nba_teams.find_teams_by_city(team_name)
            if not matches:
                return []

            nba_team_id = matches[0]["id"]
            time.sleep(2)  # Rate limit nba_api

            from datetime import datetime
            now = datetime.now()
            # NBA season: Oct-Jun. If before Oct, use previous year start.
            season_start = now.year if now.month >= 10 else now.year - 1
            season_str = f"{season_start}-{str(season_start + 1)[-2:]}"

            log = teamgamelog.TeamGameLog(
                team_id=nba_team_id,
                season=season_str,
            )
            df = log.get_data_frames()[0]

            games = []
            for _, row in df.head(last_n).iterrows():
                games.append({
                    "game_id": str(row.get("Game_ID", "")),
                    "date": str(row.get("GAME_DATE", "")),
                    "matchup": str(row.get("MATCHUP", "")),
                    "result": str(row.get("WL", "")),
                    "points": int(row.get("PTS", 0)),
                    "rebounds": int(row.get("REB", 0)),
                    "assists": int(row.get("AST", 0)),
                    "steals": int(row.get("STL", 0)),
                    "blocks": int(row.get("BLK", 0)),
                    "turnovers": int(row.get("TOV", 0)),
                    "fg_pct": float(row.get("FG_PCT", 0)),
                    "three_pct": float(row.get("FG3_PCT", 0)),
                    "ft_pct": float(row.get("FT_PCT", 0)),
                })

            return games
        except Exception as e:
            print(f"[{self.api_name}] nba_api game log error: {e}")
            return []

    def _get_game_log_bdl(self, team_name: str, last_n: int) -> list:
        """Fetch recent games via BallDontLie — less detailed but always available."""
        team_id = self.resolve_team_id(team_name)
        if not team_id:
            return []

        try:
            # BallDontLie doesn't have a direct "last N" — fetch recent season games
            from datetime import datetime
            season = datetime.now().year if datetime.now().month >= 10 else datetime.now().year - 1
            data = self._request("/games", params={
                "team_ids[]": team_id,
                "seasons[]": str(season),
                "per_page": str(last_n),
            })
        except Exception as e:
            print(f"[{self.api_name}] Error fetching game log for {team_name}: {e}")
            return []

        games = []
        for item in data.get("data", []):
            home = item.get("home_team", {})
            visitor = item.get("visitor_team", {})
            games.append({
                "game_id": str(item.get("id", "")),
                "date": item.get("date", ""),
                "home_team": home.get("full_name", ""),
                "away_team": visitor.get("full_name", ""),
                "home_score": item.get("home_team_score", 0),
                "away_score": item.get("visitor_team_score", 0),
            })

        return games

    def resolve_team_id(self, team_name: str) -> str | None:
        """GET /teams → search for NBA team by name.

        BallDontLie returns all teams; we filter client-side.
        """
        cache_file = CACHE_DIR / "_team_ids" / "balldontlie.json"
        team_ids = {}
        if cache_file.exists():
            try:
                team_ids = json.loads(cache_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        name_lower = team_name.lower().strip()
        if name_lower in team_ids:
            return team_ids[name_lower]

        try:
            data = self._request("/teams")
        except Exception as e:
            print(f"[{self.api_name}] Error fetching teams: {e}")
            return None

        for team in data.get("data", []):
            full_name = team.get("full_name", "").lower()
            city = team.get("city", "").lower()
            abbrev = team.get("abbreviation", "").lower()

            if name_lower in full_name or name_lower == city or name_lower == abbrev:
                team_id = str(team.get("id", ""))
                if team_id:
                    team_ids[name_lower] = team_id
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    cache_file.write_text(
                        json.dumps(team_ids, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                return team_id or None

        return None
