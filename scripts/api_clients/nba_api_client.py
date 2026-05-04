"""nba_api client — deep NBA stats (pace, ratings, game logs).

Uses the nba_api Python package (pip install nba_api).
Docs: https://github.com/swar/nba_api
Free, no API key needed. Rate limit: ~1 req/sec.
"""
import json
import time
from datetime import datetime
from pathlib import Path

from .base_client import CACHE_DIR

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


class NBAAPIClient:
    """Deep NBA stats via nba_api package."""

    api_name = "nba-api"

    def __init__(self, **kwargs):
        self._cache_dir = CACHE_DIR / "nba_api"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def available(self) -> bool:
        return _HAS_NBA_API

    def _check_cache(self, key: str, ttl_hours: int = 6) -> dict | None:
        path = self._cache_dir / f"{key}.json"
        if path.exists():
            try:
                age_h = (datetime.now().timestamp() - path.stat().st_mtime) / 3600
                if age_h < ttl_hours:
                    return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return None

    def _save_cache(self, key: str, data: dict):
        path = self._cache_dir / f"{key}.json"
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
        cached = self._check_cache(cache_key)
        if cached:
            return cached.get("games", [])

        try:
            time.sleep(0.6)  # Rate limit
            log = teamgamelog.TeamGameLog(team_id=team_id, season=season)
            df = log.get_data_frames()[0]
            games = df.head(last_n).to_dict("records")
            self._save_cache(cache_key, {"games": games})
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
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return cached.get("standings", [])

        try:
            time.sleep(0.6)
            standings = leaguestandings.LeagueStandings(season=season)
            df = standings.get_data_frames()[0]
            rows = df.to_dict("records")
            self._save_cache(cache_key, {"standings": rows})
            return rows
        except Exception as e:
            print(f"[nba-api] Standings error: {e}")
            return []

    def get_box_score(self, game_id: str) -> dict:
        """Get box score for a specific game."""
        if not _HAS_NBA_API:
            return {}

        cache_key = f"boxscore_{game_id}"
        cached = self._check_cache(cache_key, ttl_hours=24)
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
            self._save_cache(cache_key, result)
            return result
        except Exception as e:
            print(f"[nba-api] Box score error for {game_id}: {e}")
            return {}
