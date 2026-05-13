"""Unified API Client integrating ESPN and Flashscore."""
import logging
from typing import Dict, List, Optional

from .espn import ESPNClient, ESPN_LEAGUES
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

SOURCE_PRIORITY = {
    "football":   ["flashscore", "betexplorer", "soccerway", "espn"],
    "tennis":     ["flashscore", "scores24", "espn"],
    "basketball": ["flashscore", "betexplorer", "scores24", "espn"],
    "hockey":     ["flashscore", "betexplorer", "scores24", "espn"],
    "volleyball": ["flashscore", "betexplorer", "scores24", "espn"],
}

class UnifiedAPIClient:
    """Composite API client integrating data from ESPN and Flashscore."""
    
    def __init__(self):
        # Shared rate limiter across all clients to prevent IP bans
        self._limiter = RateLimiter()
        self._client_cache = {}

    def _create_client(self, name: str):
        if name == "flashscore":
            from .flashscore import FlashscoreClient
            return FlashscoreClient(rate_limiter=self._limiter)
        elif name == "espn":
            # ESPN needs sport+league, handle in get_fixtures directly
            return None  
        elif name == "betexplorer":
            try:
                from .betexplorer import BetExplorerClient
                return BetExplorerClient(rate_limiter=self._limiter)
            except ImportError:
                logger.debug("[UnifiedAPIClient] BetExplorerClient not available")
                return None
        elif name == "oddsportal":
            try:
                from .oddsportal import OddsPortalClient
                return OddsPortalClient(rate_limiter=self._limiter)
            except ImportError:
                logger.debug("[UnifiedAPIClient] OddsPortalClient not available")
                return None
        elif name == "soccerway":
            try:
                from .soccerway import SoccerwayClient
                return SoccerwayClient(rate_limiter=self._limiter)
            except ImportError:
                logger.debug("[UnifiedAPIClient] SoccerwayClient not available")
                return None
        elif name == "scores24":
            try:
                from .scores24 import Scores24Client
                return Scores24Client(rate_limiter=self._limiter)
            except ImportError:
                logger.debug("[UnifiedAPIClient] Scores24Client not available")
                return None
        elif name == "totalcorner":
            try:
                from .totalcorner import TotalCornerClient
                return TotalCornerClient(rate_limiter=self._limiter)
            except ImportError:
                logger.debug("[UnifiedAPIClient] TotalCornerClient not available")
                return None
        return None

    def _get_client(self, name: str):
        """Lazy-init and cache a client by name."""
        if name in self._client_cache:
            return self._client_cache[name]
        client = self._create_client(name)
        if client:
            self._client_cache[name] = client
        return client

    def close(self):
        """Clean up resources from all clients."""
        for client in self._client_cache.values():
            try:
                client.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()
        
    def get_fixtures(self, date: str, sport: str = "football") -> list:
        """Fetch fixtures from configured sources based on SOURCE_PRIORITY.
        """
        sources = SOURCE_PRIORITY.get(sport, ["flashscore", "espn"])
        all_fixtures = []
        seen_matchups = set()

        for source in sources:
            if source == "espn":
                leagues = ESPN_LEAGUES.get(sport, [])
                if not leagues:
                    continue
                fetched_count = 0
                for league in leagues:
                    try:
                        espn = ESPNClient(sport=sport, league=league, rate_limiter=self._limiter)
                        fixtures = espn.get_fixtures(date)
                        for f in fixtures:
                            # Merge + dedup by (home, away)
                            matchup = (f.home_team_name, f.away_team_name)
                            if matchup not in seen_matchups:
                                seen_matchups.add(matchup)
                                all_fixtures.append(f)
                                fetched_count += 1
                    except Exception as e:
                        logger.debug(f"[UnifiedAPIClient] ESPN {sport}/{league} failed: {e}")
                        continue
                if fetched_count > 0:
                    logger.info(f"[UnifiedAPIClient] ESPN returned {fetched_count} {sport} fixtures")
            else:
                client = self._get_client(source)
                if not client:
                    continue
                try:
                    fixtures = client.get_fixtures(date, sport=sport)
                    fetched_count = 0
                    for f in fixtures:
                        matchup = (f.home_team_name, f.away_team_name)
                        if matchup not in seen_matchups:
                            seen_matchups.add(matchup)
                            all_fixtures.append(f)
                            fetched_count += 1
                    if fetched_count > 0:
                        logger.info(f"[UnifiedAPIClient] {source.capitalize()} returned {fetched_count} {sport} fixtures")
                except Exception as e:
                    logger.warning(f"[UnifiedAPIClient] {source.capitalize()} failed for {sport}: {e}")
                    
        return all_fixtures

    def get_fixture_stats(self, event_id: str, source: str | None = None) -> list:
        """Fetch detailed stats from Flashscore."""
        client = self._get_client("flashscore")
        if not client:
            return []
        try:
            res = client.get_fixture_stats(event_id)
            if res:
                return res
        except Exception:
            pass
        return []

    def get_deep_data(self, event_id: str, source: str | None = None) -> dict:
        """Fetch stats + form + H2H + odds from Flashscore."""
        result = {"stats": [], "form": {}, "h2h": {}, "odds": []}
        client = self._get_client("flashscore")
        if not client:
            return result
            
        try:
            preview = client.get_match_preview(event_id)
            if preview:
                result["form"] = {
                    "homeTeam": {"form": preview.get("form_home", [])},
                    "awayTeam": {"form": preview.get("form_away", [])},
                }
                result["h2h"] = {"teamDuel": preview.get("h2h", [])}
        except Exception as e:
            logger.debug(f"Flashscore preview failed for {event_id}: {e}")
        
        try:
            stats = client.get_fixture_stats(event_id)
            if stats:
                result["stats"] = stats
        except Exception as e:
            logger.debug(f"Flashscore stats failed for {event_id}: {e}")
        
        return result
