"""Unified API Client integrating Sofascore, ESPN, and Flashscore."""
import logging
from typing import Dict, List, Optional

from .sofascore import SofascoreClient
from .espn import ESPNClient, ESPN_LEAGUES
from .flashscore import FlashscoreClient
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

class UnifiedAPIClient:
    """Powerful composite API client integrating data from Sofascore, ESPN, and Flashscore."""
    
    def __init__(self):
        # Shared rate limiter across all clients to prevent IP bans
        self._limiter = RateLimiter()
        
        self.sofascore = SofascoreClient(rate_limiter=self._limiter)
        self.flashscore = FlashscoreClient(rate_limiter=self._limiter)

    def close(self):
        """Clean up resources from all clients."""
        try:
            self.flashscore.close()
        except Exception:
            pass
        if hasattr(self.sofascore, 'close'):
            try:
                self.sofascore.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()
        
    def get_fixtures(self, date: str, sport: str = "football") -> list:
        """Fetch fixtures from the best available source.
        
        Priority: Sofascore (one call per sport) → ESPN (iterates all leagues for sport).
        All clients return APIFixture objects for consistent downstream handling.
        """
        # 1. Try Sofascore first — single call gets all events for sport+date
        try:
            sofa_sport = {"hockey": "ice-hockey"}.get(sport, sport)
            res = self.sofascore.get_fixtures(date, sport=sofa_sport)
            if res:
                logger.info(f"[UnifiedAPIClient] Sofascore returned {len(res)} {sport} fixtures")
                return res
        except Exception as e:
            logger.warning(f"[UnifiedAPIClient] Sofascore failed for {sport}: {e}")
        
        # 2. Flashscore fallback
        try:
            res = self.flashscore.get_fixtures(date, sport=sport)
            if res:
                logger.info(f"[UnifiedAPIClient] Flashscore returned {len(res)} fixtures")
                return res
        except Exception as e:
            logger.warning(f"[UnifiedAPIClient] Flashscore failed: {e}")
        
        # 3. ESPN fallback — iterate all leagues for this sport
        leagues = ESPN_LEAGUES.get(sport, [])
        if not leagues:
            logger.warning(f"[UnifiedAPIClient] No ESPN leagues configured for {sport}")
            return []
        
        all_fixtures = []
        seen_ids = set()
        for league in leagues:
            try:
                espn = ESPNClient(sport=sport, league=league, rate_limiter=self._limiter)
                fixtures = espn.get_fixtures(date)
                for f in fixtures:
                    if f.external_id not in seen_ids:
                        seen_ids.add(f.external_id)
                        all_fixtures.append(f)
            except Exception as e:
                logger.debug(f"[UnifiedAPIClient] ESPN {sport}/{league} failed: {e}")
                continue
        
        if all_fixtures:
            logger.info(f"[UnifiedAPIClient] ESPN returned {len(all_fixtures)} {sport} fixtures from {len(leagues)} leagues")
        return all_fixtures

    def get_fixture_stats(self, event_id: str, source: str | None = None) -> list:
        """Fetch detailed stats from the best available source."""
        clients = [self.sofascore, self.flashscore]
        
        if source == "flashscore":
            clients = [self.flashscore, self.sofascore]
        
        # Skip Sofascore for non-numeric IDs
        if not SofascoreClient._is_sofascore_id(event_id):
            clients = [c for c in clients if not isinstance(c, SofascoreClient)]
        
        for client in clients:
            try:
                res = client.get_fixture_stats(event_id)
                if res:
                    return res
            except Exception:
                pass
        return []

    def get_deep_data(self, event_id: str, source: str | None = None) -> dict:
        """Fetch stats + form + H2H + odds, routing to the right source."""
        is_sofa = SofascoreClient._is_sofascore_id(event_id)
        use_flashscore = (source == "flashscore" or not is_sofa)
        
        result = {"stats": [], "form": {}, "h2h": {}, "odds": []}
        
        if use_flashscore:
            try:
                preview = self.flashscore.get_match_preview(event_id)
                if preview:
                    result["form"] = {
                        "homeTeam": {"form": preview.get("form_home", [])},
                        "awayTeam": {"form": preview.get("form_away", [])},
                    }
                    result["h2h"] = {"teamDuel": preview.get("h2h", [])}
            except Exception as e:
                logger.debug(f"Flashscore preview failed for {event_id}: {e}")
            
            try:
                stats = self.flashscore.get_fixture_stats(event_id)
                if stats:
                    result["stats"] = stats
            except Exception as e:
                logger.debug(f"Flashscore stats failed for {event_id}: {e}")
        else:
            try:
                result["stats"] = self.sofascore.get_fixture_stats(event_id) or []
            except Exception:
                pass
            try:
                result["form"] = self.sofascore.get_pregame_form(event_id) or {}
            except Exception:
                pass
            try:
                result["h2h"] = self.sofascore.get_event_h2h(event_id) or {}
            except Exception:
                pass
            try:
                odds_json = self.sofascore.get_event_odds(event_id) or {}
                result["odds"] = odds_json.get("markets", [])
            except Exception:
                pass
        
        return result
