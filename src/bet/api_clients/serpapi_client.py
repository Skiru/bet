"""SerpAPI client — Google search results with sports data extraction.

Free plan: 250 searches/month. Use sparingly as a SUPPLEMENT to other APIs.
SerpAPI returns structured sports_results when querying team/match info.

API docs: https://serpapi.com/search-api
"""

import json
import sys
from pathlib import Path

import requests

from .base_client import BaseAPIClient, CACHE_DIR
from .rate_limiter import RateLimiter
from normalize_stats import NormalizedFixture, NormalizedMatchStats


SERPAPI_BASE = "https://serpapi.com/search.json"

# Sport → useful search query templates
SEARCH_TEMPLATES = {
    "football": "{team} football statistics last 10 matches",
    "basketball": "{team} basketball statistics season",
    "hockey": "{team} NHL statistics season",
    "tennis": "{player} tennis statistics ATP WTA",
    "volleyball": "{team} volleyball statistics",
}


class SerpAPIClient(BaseAPIClient):
    """SerpAPI client for supplementary sports data via Google search.

    250 searches/month free tier. Used as LAST resort in fallback chains.
    Extracts structured data from Google's sports_results and knowledge_graph.
    """

    TIMEOUT = 20

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="serpapi",
            base_url=SERPAPI_BASE,
            rate_limiter=rate_limiter,
        )

    def _build_headers(self) -> dict:
        return {"Accept": "application/json"}

    def _search(self, query: str) -> dict | None:
        """Execute a SerpAPI search. Returns parsed JSON or None."""
        if not self.api_key or self.api_key == "YOUR_KEY_HERE":
            return None

        if not self.rate_limiter.can_request(self.api_name):
            print(f"[{self.api_name}] Monthly quota exhausted")
            return None

        # Check cache first (24h TTL for sports queries)
        cache_key = f"serpapi/{query.lower().replace(' ', '_')[:80]}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached:
            return cached

        try:
            response = requests.get(
                SERPAPI_BASE,
                params={
                    "q": query,
                    "api_key": self.api_key,
                    "engine": "google",
                },
                timeout=self.TIMEOUT,
            )
            self.rate_limiter.record_request(self.api_name, query, cost=1)

            if response.status_code == 429:
                print(f"[{self.api_name}] Rate limited (HTTP 429)")
                return None
            if response.status_code >= 400:
                print(f"[{self.api_name}] HTTP {response.status_code}")
                return None

            data = response.json()
            self._save_cache(cache_key, data)
            return data

        except requests.exceptions.RequestException as e:
            print(f"[{self.api_name}] Request failed: {e}")
            return None

    def get_fixtures(self, date: str) -> list[NormalizedFixture]:
        """SerpAPI doesn't provide structured fixtures — return empty."""
        return []

    def get_fixture_stats(self, fixture_id: str) -> NormalizedMatchStats | None:
        """SerpAPI doesn't provide per-fixture stats by ID — return None.

        Use get_match_stats(team1, team2) instead for match-level data.
        """
        return None

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list:
        """Get H2H data by querying Google for 'team1 vs team2'.

        Returns list of NormalizedFixture from previous encounters.
        """
        match_data = self.get_match_stats(team1_id, team2_id)
        if not match_data:
            return []

        fixtures = []
        for game in match_data.get("previous_encounters", [])[:last_n]:
            fixtures.append(NormalizedFixture(
                fixture_id=f"serp-h2h-{team1_id}-{team2_id}-{game.get('date', '')}".replace(" ", "_"),
                source=self.api_name,
                sport="",
                competition=game.get("tournament", ""),
                home_team=game.get("home_team", team1_id),
                away_team=game.get("away_team", team2_id),
                kickoff=game.get("date", ""),
                status="FT",
            ))
        return fixtures

    def get_match_stats(self, team1: str, team2: str) -> dict:
        """Query Google for 'team1 vs team2' and extract structured match data.

        Returns dict with keys:
          - game_spotlight: current/next match info (date, teams, scores)
          - match_stats: per-stat breakdown (corners, shots, possession, etc.)
          - previous_encounters: list of H2H results
          - team_form: recent results for each team
          - raw_sports_results: the full sports_results object for manual inspection
        """
        query = f"{team1} vs {team2}"
        data = self._search(query)
        if not data:
            return {}

        result = {}
        sr = data.get("sports_results", {})
        if not sr:
            return {}

        result["raw_sports_results"] = sr

        # Extract game spotlight (upcoming/current match)
        spotlight = sr.get("game_spotlight", sr.get("match", {}))
        if spotlight:
            result["game_spotlight"] = spotlight

        # Extract match statistics (for completed matches)
        # SerpAPI returns these under various keys depending on sport
        for stats_key in ["statistics", "match_statistics", "stats"]:
            if stats_key in sr:
                result["match_stats"] = self._parse_match_statistics(sr[stats_key])
                break

        # Extract previous encounters / H2H
        for h2h_key in ["previous_encounters", "head_to_head", "past_meetings"]:
            if h2h_key in sr:
                encounters = sr[h2h_key]
                if isinstance(encounters, list):
                    result["previous_encounters"] = encounters
                break

        # Extract games list (recent results)
        games = sr.get("games", [])
        if games:
            result["team_form"] = games

        return result

    def _parse_match_statistics(self, stats_raw) -> dict:
        """Parse match statistics into normalized format.

        Input varies: could be list of {"name": "Corners", "home": "5", "away": "3"}
        or dict of {"corners": {"home": 5, "away": 3}}.
        Returns: {"corners": {"home": 5, "away": 3}, ...}
        """
        parsed = {}
        if isinstance(stats_raw, list):
            for item in stats_raw:
                if isinstance(item, dict):
                    name = item.get("name", item.get("label", "")).lower()
                    name = name.replace(" ", "_")
                    if name:
                        home_val = item.get("home", item.get("team1", ""))
                        away_val = item.get("away", item.get("team2", ""))
                        parsed[name] = {
                            "home": self._parse_stat_value(home_val),
                            "away": self._parse_stat_value(away_val),
                        }
        elif isinstance(stats_raw, dict):
            for key, value in stats_raw.items():
                if isinstance(value, dict) and ("home" in value or "team1" in value):
                    parsed[key.lower().replace(" ", "_")] = {
                        "home": self._parse_stat_value(value.get("home", value.get("team1"))),
                        "away": self._parse_stat_value(value.get("away", value.get("team2"))),
                    }
        return parsed

    @staticmethod
    def _parse_stat_value(val) -> int | float | str:
        """Try to parse stat value as number."""
        if val is None:
            return 0
        if isinstance(val, (int, float)):
            return val
        val_str = str(val).strip().rstrip("%")
        try:
            if "." in val_str:
                return float(val_str)
            return int(val_str)
        except (ValueError, TypeError):
            return val

    def resolve_team_id(self, team_name: str, **kwargs) -> str | None:
        """SerpAPI uses team names directly, no ID resolution needed."""
        return team_name if team_name else None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list[NormalizedFixture]:
        """Search Google for team's recent results via sports_results."""
        query = f"{team_id} recent results"
        data = self._search(query)
        if not data:
            return []

        fixtures = []
        sports_results = data.get("sports_results", {})
        games = sports_results.get("games", sports_results.get("game_spotlight", []))

        if isinstance(games, dict):
            games = [games]

        for game in games[:last_n]:
            if not isinstance(game, dict):
                continue
            teams = game.get("teams", [])
            home_name = teams[0].get("name", "") if len(teams) > 0 else ""
            away_name = teams[1].get("name", "") if len(teams) > 1 else ""

            fixtures.append(NormalizedFixture(
                fixture_id=f"serp-{home_name}-{away_name}".replace(" ", "_"),
                source=self.api_name,
                sport="",  # Unknown from search
                competition="",
                home_team=home_name,
                away_team=away_name,
                kickoff=game.get("date", ""),
                status="FT",
            ))

        return fixtures

    def search_team_stats(self, team_name: str, sport: str) -> dict:
        """Search for team statistics and return any structured data found.

        Returns dict with any stats extracted from knowledge_graph
        and sports_results.
        """
        template = SEARCH_TEMPLATES.get(sport, "{team} sports statistics")
        query = template.format(team=team_name, player=team_name)
        data = self._search(query)
        if not data:
            return {}

        result = {}

        # Extract from knowledge_graph
        kg = data.get("knowledge_graph", {})
        if kg:
            result["knowledge_graph"] = {
                "title": kg.get("title", ""),
                "type": kg.get("type", ""),
                "description": kg.get("description", ""),
            }
            # Extract any stats-like attributes
            for key, value in kg.items():
                if any(stat in key.lower() for stat in [
                    "record", "wins", "losses", "points", "goals",
                    "standing", "rank", "coach", "venue", "arena",
                ]):
                    result.setdefault("attributes", {})[key] = value

        # Extract from sports_results
        sr = data.get("sports_results", {})
        if sr:
            result["sports_results"] = sr

        return result

    def is_available(self) -> bool:
        """Available if API key is set."""
        return bool(self.api_key) and self.api_key != "YOUR_KEY_HERE"
