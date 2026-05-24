"""GosuGamers scraper — Esports community predictions.

Access: Standard HTTP + BeautifulSoup.
Rate limit: 1 request per 3 seconds (self-imposed).
Coverage: CS2, Dota 2, Valorant.
"""

import logging
import time

import requests
from bs4 import BeautifulSoup

from bet.scrapers.constants import USER_AGENTS

logger = logging.getLogger(__name__)

RATE_LIMIT_SECONDS = 3.0

class GosuGamersScraper:
    """GosuGamers community predictions for CS2/Dota2/Valorant."""
    
    URLS = {
        "cs2": "https://www.gosugamers.net/counterstrike/matches",
        "dota2": "https://www.gosugamers.net/dota2/matches",
        "valorant": "https://www.gosugamers.net/valorant/matches",
    }
    
    def __init__(self):
        self._last_request_time = 0.0
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENTS[0]})

    def _get(self, url: str) -> BeautifulSoup | None:
        """Rate-limited HTTP GET returning parsed HTML."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < RATE_LIMIT_SECONDS:
            time.sleep(RATE_LIMIT_SECONDS - elapsed)

        try:
            resp = self._session.get(url, timeout=15)
            self._last_request_time = time.monotonic()
            if resp.status_code != 200:
                logger.warning("GosuGamers %s returned %d", url, resp.status_code)
                return None
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as e:
            logger.warning("GosuGamers request failed: %s — %s", url, e)
            return None

    def get_predictions(self, sport: str, date: str | None = None) -> list[dict]:
        """Scrape community poll percentages for upcoming matches.
        
        Args:
            sport: "cs2", "dota2", or "valorant"
            date: optional YYYY-MM-DD filter (if None, return all upcoming)
        
        Returns: [{
            "home_team": str,
            "away_team": str,
            "home_pct": float,  # e.g., 72.0
            "away_pct": float,  # e.g., 28.0
            "total_votes": int,
            "competition": str,
            "match_time": str,
        }, ...]
        """
        if sport not in self.URLS:
            logger.warning("GosuGamers: unknown sport '%s'", sport)
            return []
            
        url = self.URLS[sport]
        soup = self._get(url)
        if not soup:
            return []
            
        predictions = []
        
        # GosuGamers match cards often use a variety of generic class names or custom div tags.
        # This is a best-effort structural parse based on common patterns.
        # Often matches are linked with '/matches/' in the href
        match_links = soup.find_all("a", href=lambda h: h and "/matches/" in h)
        
        for link in match_links:
            try:
                # Some basic defensive parsing
                text_content = link.get_text(separator="|", strip=True)
                parts = [p.strip() for p in text_content.split("|") if p.strip()]
                
                # Check if it looks like a match block (e.g. Team A VS Team B)
                if "VS" not in parts:
                    continue
                    
                vs_idx = parts.index("VS")
                if vs_idx < 1 or vs_idx >= len(parts) - 1:
                    continue
                    
                home_team = parts[vs_idx - 1]
                away_team = parts[vs_idx + 1]
                
                # Try to find percentages in the block (e.g., "72%", "28%")
                home_pct: float | None = None
                away_pct: float | None = None
                pct_texts = [p for p in parts if "%" in p]
                
                if len(pct_texts) >= 2:
                    try:
                        home_pct = float(pct_texts[0].replace('%', '').strip())
                        away_pct = float(pct_texts[1].replace('%', '').strip())
                    except ValueError:
                        pass
                
                # Skip matches where predictions couldn't be parsed
                if home_pct is None or away_pct is None:
                    continue

                # Competition: elements after away_team are more likely event names
                competition = "Unknown"
                if len(parts) > vs_idx + 2:
                    competition = parts[vs_idx + 2]
                
                predictions.append({
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_pct": home_pct,
                    "away_pct": away_pct,
                    "competition": competition,
                    "match_time": "",
                })
            except Exception as e:
                logger.debug("Failed to parse a match block: %s", e)
                continue

        # Optional date filtering could be applied here if match_time was dependably parsed.
        # For this skeleton, we return all found matches that we could loosely parse.
        
        return predictions
