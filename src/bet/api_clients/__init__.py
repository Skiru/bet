"""API clients package — adapted from scripts/api_clients/.

Clients return bet.db.models objects (Fixture, MatchStat) instead of raw dicts.
Reuses base_client.py and rate_limiter.py as-is from scripts/api_clients/.

Missing clients are imported from scripts/api_clients/ as fallback to keep
the registry in sync with the full pipeline.
"""

from bet.api_clients.rate_limiter import RateLimiter
from bet.api_clients.base_client import BaseAPIClient, APISportsClient, APIError
from bet.api_clients.playwright_base import PlaywrightBaseClient
from bet.api_clients.unified import UnifiedAPIClient

# Sport → API client name mappings
API_SPORTS = {
    "football": "api-football",
    "basketball": "api-basketball",
    "hockey": "api-hockey",
    "volleyball": "api-volleyball",
}

API_ESPN = {
    "football": "espn-football",
    "basketball": "espn-basketball",
    "hockey": "espn-hockey",
    "volleyball": "espn-volleyball",
}

# Client registry — maps api-name → class
CLIENT_REGISTRY: dict[str, type] = {}


def get_client(api_name: str, rate_limiter: RateLimiter | None = None) -> BaseAPIClient:
    """Factory function to get an API client by name."""
    if rate_limiter is None:
        rate_limiter = RateLimiter()
    if api_name not in CLIENT_REGISTRY:
        raise ValueError(
            f"Unknown API client: {api_name}. Available: {list(CLIENT_REGISTRY.keys())}"
        )
    return CLIENT_REGISTRY[api_name](rate_limiter=rate_limiter)


# Register available clients — src/ implementations
from bet.api_clients.api_football import APIFootballClient
CLIENT_REGISTRY["api-football"] = APIFootballClient

from bet.api_clients.api_basketball import APIBasketballClient
CLIENT_REGISTRY["api-basketball"] = APIBasketballClient

from bet.api_clients.api_hockey import APIHockeyClient
CLIENT_REGISTRY["api-hockey"] = APIHockeyClient

from bet.api_clients.api_volleyball import APIVolleyballClient
CLIENT_REGISTRY["api-volleyball"] = APIVolleyballClient

from bet.api_clients.flashscore import FlashscoreClient
CLIENT_REGISTRY["flashscore"] = FlashscoreClient

# New Playwright-based clients
try:
    from bet.api_clients.oddsportal import OddsPortalClient
    CLIENT_REGISTRY["oddsportal"] = OddsPortalClient
except ImportError:
    pass

try:
    from bet.api_clients.totalcorner import TotalCornerClient
    CLIENT_REGISTRY["totalcorner"] = TotalCornerClient
except ImportError:
    pass

try:
    from bet.api_clients.scores24 import Scores24Client
    CLIENT_REGISTRY["scores24"] = Scores24Client
except ImportError:
    pass

try:
    from bet.api_clients.soccerway import SoccerwayClient
    CLIENT_REGISTRY["soccerway"] = SoccerwayClient
except ImportError:
    pass

# HTTP-based clients
try:
    from bet.api_clients.betexplorer import BetExplorerClient
    CLIENT_REGISTRY["betexplorer"] = BetExplorerClient
except ImportError:
    pass

from bet.api_clients.espn import ESPNClient


def _espn_factory(sport: str, league: str):
    """Create a factory callable for ESPN client registration."""
    def factory(rate_limiter: RateLimiter):
        return ESPNClient(sport=sport, league=league, rate_limiter=rate_limiter)
    return factory


# Register ESPN clients with default leagues
CLIENT_REGISTRY["espn-football"] = _espn_factory("football", "eng.1")
CLIENT_REGISTRY["espn-basketball"] = _espn_factory("basketball", "nba")
CLIENT_REGISTRY["espn-hockey"] = _espn_factory("hockey", "nhl")
CLIENT_REGISTRY["espn-tennis"] = _espn_factory("tennis", "atp")
CLIENT_REGISTRY["espn-volleyball"] = _espn_factory("volleyball", "fivb.m")

# --- Newly consolidated clients (moved from scripts/api_clients/) ---
try:
    from bet.api_clients.football_data_org import FootballDataOrgClient
    CLIENT_REGISTRY["football-data-org"] = FootballDataOrgClient
except ImportError:
    pass

try:
    from bet.api_clients.understat_client import UnderstatClient
    CLIENT_REGISTRY["understat"] = UnderstatClient
except ImportError:
    pass

try:
    from bet.api_clients.nba_api_client import NBAAPIClient
    CLIENT_REGISTRY["nba-api"] = NBAAPIClient
except ImportError:
    pass

try:
    from bet.api_clients.serpapi_client import SerpAPIClient
    CLIENT_REGISTRY["serpapi"] = SerpAPIClient
except ImportError:
    pass

try:
    from bet.api_clients.google_sports_client import GoogleSportsClient
    CLIENT_REGISTRY["google-sports"] = GoogleSportsClient
except ImportError:
    pass

try:
    from bet.api_clients.odds_api_io import OddsAPIioClient
    CLIENT_REGISTRY["odds-api-io"] = OddsAPIioClient
except ImportError:
    pass

try:
    # ESPNMultiLeagueClient for scripts that need multi-league support
    # Note: "espn-*" keys already registered via _espn_factory above (ESPNClient)
    # ESPN_FACTORIES provides "espn-tennis" which _espn_factory doesn't cover
    from bet.api_clients.espn_adapter import ESPN_FACTORIES
    for _k, _v in ESPN_FACTORIES.items():
        if _k not in CLIENT_REGISTRY:
            CLIENT_REGISTRY[_k] = _v
except ImportError:
    pass

try:
    from bet.api_clients.lmstudio_client import LMStudioClient
    CLIENT_REGISTRY["lmstudio"] = LMStudioClient
except ImportError:
    pass

try:
    from bet.api_clients.tennis_abstract import TennisAbstractClient
    CLIENT_REGISTRY["tennis-abstract"] = TennisAbstractClient
except ImportError:
    pass

try:
    from bet.api_clients.sackmann_adapter import SackmannClient
    CLIENT_REGISTRY["sackmann"] = SackmannClient
except ImportError:
    pass

try:
    from bet.api_clients.sofascore import SofascoreClient
    CLIENT_REGISTRY["sofascore"] = SofascoreClient
except ImportError:
    pass

try:
    from bet.api_clients.moneypuck_wrapper import MoneyPuckClient
    CLIENT_REGISTRY["moneypuck"] = MoneyPuckClient
except ImportError:
    pass

try:
    from bet.api_clients.scrapernhl_wrapper import ScraperNHLClient
    CLIENT_REGISTRY["scrapernhl"] = ScraperNHLClient
except ImportError:
    pass

