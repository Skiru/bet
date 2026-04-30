"""API clients package for fetching sports statistics from external APIs."""

from .rate_limiter import RateLimiter
from .base_client import BaseAPIClient, APISportsClient

# Client registry — import clients as they're created
CLIENT_REGISTRY = {}


def get_client(api_name: str, rate_limiter: RateLimiter = None) -> BaseAPIClient:
    """Factory function to get an API client by name."""
    if rate_limiter is None:
        rate_limiter = RateLimiter()
    if api_name not in CLIENT_REGISTRY:
        raise ValueError(f"Unknown API client: {api_name}. Available: {list(CLIENT_REGISTRY.keys())}")
    return CLIENT_REGISTRY[api_name](rate_limiter=rate_limiter)


# Register available clients
from .api_football import APIFootballClient
CLIENT_REGISTRY["api-football"] = APIFootballClient

from .football_data_org import FootballDataOrgClient
CLIENT_REGISTRY["football-data-org"] = FootballDataOrgClient

from .understat_client import UnderstatClient
CLIENT_REGISTRY["understat"] = UnderstatClient

from .api_basketball import APIBasketballClient
CLIENT_REGISTRY["api-basketball"] = APIBasketballClient

from .api_hockey import APIHockeyClient
CLIENT_REGISTRY["api-hockey"] = APIHockeyClient

from .balldontlie import NBAStatsClient
CLIENT_REGISTRY["balldontlie"] = NBAStatsClient

from .thesportsdb import TheSportsDBClient
CLIENT_REGISTRY["thesportsdb"] = TheSportsDBClient

# New sport-specific API clients
from .api_tennis import APITennisClient
CLIENT_REGISTRY["api-tennis"] = APITennisClient

from .api_volleyball import APIVolleyballClient
CLIENT_REGISTRY["api-volleyball"] = APIVolleyballClient

from .api_handball import APIHandballClient
CLIENT_REGISTRY["api-handball"] = APIHandballClient

from .api_baseball import APIBaseballClient
CLIENT_REGISTRY["api-baseball"] = APIBaseballClient
