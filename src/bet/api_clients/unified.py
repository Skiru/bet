"""Unified API Client integrating Sofascore, ESPN, and Flashscore."""
import logging
from typing import Dict, List, Optional

from .sofascore import SofascoreClient
from .espn import ESPNClient
from .flashscore import FlashscoreClient
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

class UnifiedAPIClient:
    """Powerful composite API client integrating data from Sofascore, ESPN, and Flashscore."""
    
    def __init__(self):
        # Shared rate limiter across all clients to prevent IP bans
        self._limiter = RateLimiter()
        
        self.sofascore = SofascoreClient(rate_limiter=self._limiter)
        # Delaying ESPN client since it requires sport and league logic specifically
        # We will wrap it dynamically or just test with sofascore/flashscore for now
        self.espn = None
        self.flashscore = FlashscoreClient(rate_limiter=self._limiter)
        
        # Priority order for general fetches
        self.clients = [
            c for c in [self.sofascore, self.flashscore, self.espn] if c is not None
        ]
        
    def get_fixtures(self, date: str, sport: str = "football") -> list:
        """Fetch fixtures from the best available source."""
        for client in self.clients:
            try:
                res = client.get_fixtures(date) if hasattr(client, 'get_fixtures') else None
                if getattr(client, "api_name", "") == "sofascore":
                    # Sofascore needs sport param
                    res = client.get_fixtures(date, sport=sport)
                    
                if res:
                    logger.info(f"[UnifiedAPIClient] Successfully fetched {len(res)} fixtures via {client.api_name}")
                    return res
            except Exception as e:
                logger.warning(f"[UnifiedAPIClient] {client.api_name} failed get_fixtures: {e}")
        return []

    def get_fixture_stats(self, event_id: str) -> list:
        """Fetch detailed stats from the best available source."""
        for client in self.clients:
            try:
                res = client.get_fixture_stats(event_id)
                if res:
                    return res
            except Exception as e:
                pass
        return []
