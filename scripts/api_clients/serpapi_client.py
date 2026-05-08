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
    "baseball": "{team} MLB statistics season",
    "tennis": "{player} tennis statistics ATP WTA",
    "volleyball": "{team} volleyball statistics",
    "handball": "{team} handball statistics",
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
        """SerpAPI doesn't provide per-fixture stats — return None."""
        return None

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list:
        """Not supported by SerpAPI."""
        return []

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
