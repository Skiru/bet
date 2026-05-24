"""OpenDota API client — Dota 2 professional match statistics.

Docs: https://docs.opendota.com/
Base URL: https://api.opendota.com/api
Auth: None required (60 req/min free), optional API key for 1200 req/min.

Key endpoints:
  /proMatches           — Recent pro matches
  /teams/{id}           — Team info + W/L record
  /teams/{id}/matches   — Team match history
  /teams/{id}/heroes    — Hero pool + win rates
  /matches/{id}         — Full match detail
  /search               — Search teams/players by name
"""

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.opendota.com/api"
RATE_LIMIT_SECONDS = 1.1  # Conservative: stay under 60 req/min


class OpenDotaClient:
    """OpenDota API client for Dota 2 professional match statistics.

    Free tier: 60 req/min (no key), 1200 req/min (with free key).
    Used for: L10 form, H2H, team stats, kill averages, duration averages.
    """

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key
        self._last_request_time = 0.0
        self._team_id_cache: dict[str, int | None] = {}
        self._session = requests.Session()

    def _request(self, endpoint: str, params: dict | None = None, _retries: int = 0) -> Any:
        """Make rate-limited request to OpenDota API."""
        # Rate limiting
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < RATE_LIMIT_SECONDS:
            time.sleep(RATE_LIMIT_SECONDS - elapsed)

        url = f"{BASE_URL}{endpoint}"
        req_params = {}
        if self._api_key:
            req_params["api_key"] = self._api_key
        if params:
            req_params.update(params)

        try:
            resp = self._session.get(url, params=req_params, timeout=15)
        except requests.RequestException as e:
            self._last_request_time = time.monotonic()
            logger.warning("OpenDota request failed: %s %s — %s", endpoint, params, e)
            return None

        self._last_request_time = time.monotonic()

        if resp.status_code == 429:
            if _retries >= 3:
                logger.error("OpenDota: max retries exceeded for %s", endpoint)
                return None
            logger.warning("OpenDota rate limited (429). Waiting 60s. Retry %d/3.", _retries + 1)
            time.sleep(60)
            return self._request(endpoint, params, _retries=_retries + 1)
        if resp.status_code == 404:
            return None
        try:
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning("OpenDota HTTP error: %s %s — %s", endpoint, resp.status_code, e)
            return None

    def get_pro_matches(self, limit: int = 100) -> list[dict]:
        """Get recent professional matches."""
        data = self._request("/proMatches")
        if not data:
            return []
        return data[:limit]

    def get_team(self, team_id: int) -> dict | None:
        """Get team info including wins/losses."""
        return self._request(f"/teams/{team_id}")

    def get_team_matches(self, team_id: int, limit: int = 20) -> list[dict]:
        """Get recent matches for a team."""
        data = self._request(f"/teams/{team_id}/matches")
        if not data:
            return []
        return data[:limit]

    def get_team_heroes(self, team_id: int) -> list[dict]:
        """Get hero usage and win rates for a team."""
        data = self._request(f"/teams/{team_id}/heroes")
        return data if data else []

    def get_match(self, match_id: int) -> dict | None:
        """Get full match detail (kills, duration, draft, etc.)."""
        return self._request(f"/matches/{match_id}")

    def search_teams(self, name: str) -> list[dict]:
        """Search for teams by name. Returns list of matches."""
        data = self._request("/search", params={"q": name})
        if not data:
            return []
        # Filter to team results
        return [r for r in data if r.get("similarity", 0) > 0.3]

    def resolve_team_id(self, team_name: str) -> int | None:
        """Resolve team name to OpenDota team_id.

        Uses cache to avoid repeated lookups.
        Strategy: search endpoint first (lightweight), then bulk /teams as fallback.
        """
        lower = team_name.lower().strip()
        if lower in self._team_id_cache:
            return self._team_id_cache[lower]

        # Primary: search endpoint (lightweight, returns ranked results)
        results = self.search_teams(team_name)
        if results:
            best = max(results, key=lambda r: r.get("similarity", 0))
            if best.get("similarity", 0) > 0.5:
                team_id = best.get("id")
                if team_id:
                    self._team_id_cache[lower] = team_id
                    return team_id

        # Fallback: iterate /teams (expensive but catches tag-based matches)
        teams_data = self._request("/teams")
        if teams_data:
            for t in teams_data:
                t_name = (t.get("name") or "").lower()
                t_tag = (t.get("tag") or "").lower()
                if lower == t_name or lower == t_tag:
                    self._team_id_cache[lower] = t["team_id"]
                    return t["team_id"]

        self._team_id_cache[lower] = None
        return None

    def get_team_stats(self, team_name: str, n_matches: int = 10) -> dict:
        """High-level: resolve team → fetch last N matches → compute averages.

        Returns:
            {
                "kills_avg": float,
                "deaths_avg": float,
                "duration_avg_min": float,
                "win_rate_l10": float,
                "hero_pool_size": int,
                "matches_found": int,
            }
        """
        team_id = self.resolve_team_id(team_name)
        if not team_id:
            logger.warning("OpenDota: could not resolve team '%s'", team_name)
            return {}

        matches = self.get_team_matches(team_id, limit=n_matches)
        if not matches:
            return {}

        total_kills = 0
        total_deaths = 0
        total_duration = 0
        wins = 0
        valid_matches = 0

        for m in matches:
            radiant = m.get("radiant", False)
            radiant_score = m.get("radiant_score", 0) or 0
            dire_score = m.get("dire_score", 0) or 0
            duration = m.get("duration", 0) or 0
            radiant_win = m.get("radiant_win")

            if radiant_score == 0 and dire_score == 0:
                continue

            valid_matches += 1
            if radiant:
                total_kills += radiant_score
                total_deaths += dire_score
                if radiant_win:
                    wins += 1
            else:
                total_kills += dire_score
                total_deaths += radiant_score
                if not radiant_win:
                    wins += 1

            total_duration += duration

        if valid_matches == 0:
            return {"matches_found": 0}

        # Hero pool size
        heroes = self.get_team_heroes(team_id)
        hero_pool = len([h for h in heroes if (h.get("games_played") or 0) >= 2]) if heroes else 0

        return {
            "kills_avg": round(total_kills / valid_matches, 1),
            "deaths_avg": round(total_deaths / valid_matches, 1),
            "duration_avg_min": round(total_duration / valid_matches / 60, 1),
            "win_rate_l10": round(wins / valid_matches * 100, 1),
            "hero_pool_size": hero_pool,
            "matches_found": valid_matches,
        }

    def get_h2h(self, team_a: str, team_b: str) -> dict:
        """Find mutual matches between two teams.

        Returns:
            {
                "matches_found": int,
                "team_a_wins": int,
                "team_b_wins": int,
                "avg_total_kills": float,
                "avg_duration_min": float,
            }
        """
        team_a_id = self.resolve_team_id(team_a)
        team_b_id = self.resolve_team_id(team_b)

        if not team_a_id or not team_b_id:
            return {"matches_found": 0, "team_a_wins": 0, "team_b_wins": 0,
                    "avg_total_kills": 0, "avg_duration_min": 0}

        # Get team A matches and filter for opponent = team B
        matches = self.get_team_matches(team_a_id, limit=50)
        h2h_matches = [m for m in matches if m.get("opposing_team_id") == team_b_id]

        if not h2h_matches:
            return {"matches_found": 0, "team_a_wins": 0, "team_b_wins": 0,
                    "avg_total_kills": 0, "avg_duration_min": 0}

        a_wins = 0
        total_kills = 0
        total_duration = 0

        for m in h2h_matches:
            radiant = m.get("radiant", False)
            radiant_win = m.get("radiant_win")
            radiant_score = m.get("radiant_score", 0) or 0
            dire_score = m.get("dire_score", 0) or 0
            duration = m.get("duration", 0) or 0

            total_kills += radiant_score + dire_score
            total_duration += duration

            if (radiant and radiant_win) or (not radiant and not radiant_win):
                a_wins += 1

        n = len(h2h_matches)
        return {
            "matches_found": n,
            "team_a_wins": a_wins,
            "team_b_wins": n - a_wins,
            "avg_total_kills": round(total_kills / n, 1) if n else 0,
            "avg_duration_min": round(total_duration / n / 60, 1) if n else 0,
        }
