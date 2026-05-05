"""nba_api client — deep NBA stats (pace, ratings, game logs).

Uses the nba_api Python package (pip install nba_api).
Docs: https://github.com/swar/nba_api
Free, no API key needed. Rate limit: ~1 req/sec.
"""
import json
import time
from datetime import datetime
from pathlib import Path

from .base_client import BaseAPIClient, CACHE_DIR
from .rate_limiter import RateLimiter

try:
    from scripts.normalize_stats import NormalizedFixture, NormalizedMatchStats
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from normalize_stats import NormalizedFixture, NormalizedMatchStats

# Guard import — nba_api is optional
try:
    from nba_api.stats.endpoints import (
        leaguegamefinder,
        teamgamelog,
        boxscoretraditionalv2,
        leaguestandings,
    )
    from nba_api.stats.static import teams as nba_teams
    _HAS_NBA_API = True
except ImportError:
    _HAS_NBA_API = False


class NBAAPIClient(BaseAPIClient):
    """Deep NBA stats via nba_api package.

    Implements BaseAPIClient interface so it works correctly with
    get_client() factory and fallback chains.
    """

    def __init__(self, rate_limiter: RateLimiter | None = None, **kwargs):
        if rate_limiter is None:
            rate_limiter = RateLimiter()
        super().__init__(
            api_name="nba-api",
            base_url="https://stats.nba.com",
            rate_limiter=rate_limiter,
        )
        self._cache_dir = CACHE_DIR / "nba_api"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def is_available(self) -> bool:
        """nba_api doesn't need an API key — just the package."""
        return _HAS_NBA_API

    def _load_api_key(self) -> str | None:
        """nba_api doesn't need an API key."""
        return "no-key-needed"

    def get_fixtures(self, date: str) -> list:
        """Get NBA games on a date. Returns list of NormalizedFixture."""
        if not _HAS_NBA_API:
            return []

        cache_key = f"nba_api/fixtures/{date}"
        cached = self._nba_check_cache(cache_key)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        try:
            time.sleep(0.6)
            finder = leaguegamefinder.LeagueGameFinder(
                date_from_nullable=date.replace("-", ""),
                date_to_nullable=date.replace("-", ""),
                league_id_nullable="00",
            )
            df = finder.get_data_frames()[0]
            if df.empty:
                return []

            # Group by game — each game has 2 rows (home + away)
            games = {}
            for _, row in df.iterrows():
                game_id = row.get("GAME_ID", "")
                if game_id not in games:
                    games[game_id] = {}
                matchup = str(row.get("MATCHUP", ""))
                if " vs. " in matchup:
                    games[game_id]["home"] = row.get("TEAM_NAME", "")
                elif " @ " in matchup:
                    games[game_id]["away"] = row.get("TEAM_NAME", "")

            fixtures = []
            for game_id, teams in games.items():
                if "home" in teams and "away" in teams:
                    from dataclasses import asdict
                    fixtures.append(NormalizedFixture(
                        fixture_id=str(game_id),
                        source="nba-api",
                        sport="basketball",
                        competition="NBA",
                        home_team=teams["home"],
                        away_team=teams["away"],
                        kickoff=date,
                        status="scheduled",
                    ))

            self._nba_save_cache(cache_key, {
                "fixtures": [f.__dict__ if hasattr(f, '__dict__') else {} for f in fixtures],
                "count": len(fixtures),
            })
            return fixtures
        except Exception as e:
            print(f"[nba-api] Fixtures error for {date}: {e}")
            return []

    def get_fixture_stats(self, fixture_id: str) -> NormalizedMatchStats | None:
        """Get box score stats for a specific game."""
        box = self.get_box_score(fixture_id)
        if not box or not box.get("teams"):
            return None

        teams_data = box["teams"]
        stats = {}
        home_name = ""
        away_name = ""

        for i, team_row in enumerate(teams_data[:2]):
            side = "home" if i == 0 else "away"
            if side == "home":
                home_name = team_row.get("TEAM_NAME", "")
            else:
                away_name = team_row.get("TEAM_NAME", "")

            stat_mapping = {
                "PTS": "points", "REB": "rebounds", "AST": "assists",
                "STL": "steals", "BLK": "blocks", "TOV": "turnovers",
                "FG_PCT": "fg_pct", "FG3_PCT": "three_pct", "FT_PCT": "ft_pct",
            }
            for api_key, our_key in stat_mapping.items():
                val = team_row.get(api_key)
                if val is not None:
                    stats.setdefault(our_key, {})[side] = float(val)

        if not stats:
            return None

        return NormalizedMatchStats(
            fixture_id=str(fixture_id),
            source="nba-api",
            sport="basketball",
            home_team=home_name,
            away_team=away_name,
            date="",
            stats=stats,
        )

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list:
        """H2H not directly supported by nba_api free tier — returns empty."""
        return []

    def resolve_team_id(self, team_name: str, **kwargs) -> str | None:
        """Resolve team name to NBA team ID."""
        tid = self.get_team_id(team_name)
        return str(tid) if tid else None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list:
        """Get last N games as NormalizedFixture."""
        games = self.get_team_game_log(int(team_id), last_n=last_n)
        fixtures = []
        for g in games:
            matchup = str(g.get("MATCHUP", ""))
            home = ""
            away = ""
            if " vs. " in matchup:
                parts = matchup.split(" vs. ")
                home = parts[0].strip()
                away = parts[1].strip() if len(parts) > 1 else ""
            elif " @ " in matchup:
                parts = matchup.split(" @ ")
                away = parts[0].strip()
                home = parts[1].strip() if len(parts) > 1 else ""

            fixtures.append(NormalizedFixture(
                fixture_id=str(g.get("GAME_ID", "")),
                source="nba-api",
                sport="basketball",
                competition="NBA",
                home_team=home,
                away_team=away,
                kickoff=str(g.get("GAME_DATE", ""))[:10],
                status="FT",
            ))
        return fixtures

    def _nba_check_cache(self, key: str, ttl_hours: int = 6) -> dict | None:
        """NBAAPIClient-specific cache (separate from BaseAPIClient cache)."""
        path = self._cache_dir / f"{key}.json"
        if path.exists():
            try:
                age_h = (datetime.now().timestamp() - path.stat().st_mtime) / 3600
                if age_h < ttl_hours:
                    return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return None

    def _nba_save_cache(self, key: str, data: dict):
        """NBAAPIClient-specific cache save."""
        path = self._cache_dir / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_team_id(self, name: str) -> int | None:
        """Resolve team name to NBA team ID."""
        if not _HAS_NBA_API:
            return None
        all_teams = nba_teams.get_teams()
        name_lower = name.lower()
        for t in all_teams:
            if name_lower in t["full_name"].lower() or name_lower in t["nickname"].lower():
                return t["id"]
        return None

    def get_team_game_log(self, team_id: int, season: str = "2025-26", last_n: int = 10) -> list[dict]:
        """Get team game log with per-game stats."""
        if not _HAS_NBA_API:
            return []

        cache_key = f"gamelog_{team_id}_{season}_{last_n}"
        cached = self._nba_check_cache(cache_key)
        if cached:
            return cached.get("games", [])

        try:
            time.sleep(0.6)  # Rate limit
            log = teamgamelog.TeamGameLog(team_id=team_id, season=season)
            df = log.get_data_frames()[0]
            games = df.head(last_n).to_dict("records")
            self._nba_save_cache(cache_key, {"games": games})
            return games
        except Exception as e:
            print(f"[nba-api] Game log error for {team_id}: {e}")
            return []

    def get_team_stats(self, team_id: int, season: str = "2025-26", last_n: int = 10) -> dict:
        """Get aggregated team stats from game log."""
        games = self.get_team_game_log(team_id, season, last_n)
        if not games:
            return {}

        stat_keys = ["PTS", "REB", "AST", "STL", "BLK", "TOV", "FG_PCT", "FG3_PCT", "FT_PCT"]
        result = {}
        for key in stat_keys:
            values = [g[key] for g in games if key in g and g[key] is not None]
            if values:
                result[key.lower()] = {
                    "l10_avg": sum(values) / len(values),
                    "l5_avg": sum(values[:5]) / len(values[:5]) if len(values) >= 5 else sum(values) / len(values),
                    "values": values,
                }

        return result

    def get_standings(self, season: str = "2025-26") -> list[dict]:
        """Get current league standings."""
        if not _HAS_NBA_API:
            return []

        cache_key = f"standings_{season}"
        cached = self._nba_check_cache(cache_key, ttl_hours=12)
        if cached:
            return cached.get("standings", [])

        try:
            time.sleep(0.6)
            standings = leaguestandings.LeagueStandings(season=season)
            df = standings.get_data_frames()[0]
            rows = df.to_dict("records")
            self._nba_save_cache(cache_key, {"standings": rows})
            return rows
        except Exception as e:
            print(f"[nba-api] Standings error: {e}")
            return []

    def get_box_score(self, game_id: str) -> dict:
        """Get box score for a specific game."""
        if not _HAS_NBA_API:
            return {}

        cache_key = f"boxscore_{game_id}"
        cached = self._nba_check_cache(cache_key, ttl_hours=24)
        if cached:
            return cached

        try:
            time.sleep(0.6)
            box = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
            frames = box.get_data_frames()
            result = {
                "players": frames[0].to_dict("records") if len(frames) > 0 else [],
                "teams": frames[1].to_dict("records") if len(frames) > 1 else [],
            }
            self._nba_save_cache(cache_key, result)
            return result
        except Exception as e:
            print(f"[nba-api] Box score error for {game_id}: {e}")
            return {}
