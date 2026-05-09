"""API clients package — adapted from scripts/api_clients/.

Clients return bet.db.models objects (Fixture, MatchStat) instead of raw dicts.
Reuses base_client.py and rate_limiter.py as-is from scripts/api_clients/.

Missing clients are imported from scripts/api_clients/ as fallback to keep
the registry in sync with the full pipeline.
"""

from bet.api_clients.rate_limiter import RateLimiter
from bet.api_clients.base_client import BaseAPIClient, APISportsClient, APIError

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

# --- Sync with scripts/api_clients/ for clients not yet in src/ ---
# This ensures any code importing from bet.api_clients gets the full registry.
try:
    import scripts.api_clients as _scripts_clients
    _SCRIPTS_REGISTRY = getattr(_scripts_clients, "CLIENT_REGISTRY", {})
    for _name, _cls in _SCRIPTS_REGISTRY.items():
        if _name not in CLIENT_REGISTRY:
            CLIENT_REGISTRY[_name] = _cls
except ImportError:
    pass  # scripts/ not on path — only src/ clients available
