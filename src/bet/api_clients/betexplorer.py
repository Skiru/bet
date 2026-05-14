import json
import logging
import random
import re
from bs4 import BeautifulSoup
import requests
from datetime import datetime

from .base_client import BaseAPIClient
from .api_football import APIFixture
from .rate_limiter import RateLimiter

try:
    from scripts.stealth_utils import USER_AGENTS
except ImportError:
    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    ]

logger = logging.getLogger(__name__)

class BetExplorerClient(BaseAPIClient):
    """BetExplorer client — HTTP-first odds comparison and fixture discovery."""
    
    SPORT_PATHS = {
        "football": "/football/",
        "tennis": "/tennis/",
        "basketball": "/basketball/",
        "hockey": "/hockey/",
        "volleyball": "/volleyball/",
    }
    
    def __init__(self, rate_limiter: RateLimiter):
        super().__init__("betexplorer", "https://www.betexplorer.com", rate_limiter)
        
    def _load_api_key(self) -> str:
        return "no-key"  # No API key needed for HTML scraping

    def _build_headers(self) -> dict:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.betexplorer.com/"
        }

    def get_fixtures(self, date: str, sport: str = "football") -> list[APIFixture]:
        """Get fixtures for a specific date and sport."""
        # Validate date format
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            logger.error(f"[BetExplorer] Invalid date format: {date} (expected YYYY-MM-DD)")
            return []

        cache_key = f"betexplorer/{sport}/fixtures_{date}"
        cached = self._check_cache(cache_key, 4)
        if cached and "data" in cached:
            return [APIFixture(**c) for c in cached["data"]]

        if sport not in self.SPORT_PATHS:
            logger.warning(f"Unsupported sport: {sport}")
            return []

        path = self.SPORT_PATHS[sport]
        
        # Add year, month, day to path if scraping a specific date
        today_str = datetime.now().strftime("%Y-%m-%d")
        if date >= today_str:
            url = f"{self.base_url}/next{path}?year={date[:4]}&month={date[5:7]}&day={date[8:10]}"
        else:
            url = f"{self.base_url}/results{path}?year={date[:4]}&month={date[5:7]}&day={date[8:10]}"

        if not self.rate_limiter.can_request("betexplorer-scraper"):
            logger.warning("Rate limit exceeded for betexplorer-scraper")
            return []
            
        try:
            resp = requests.get(url, headers=self._build_headers(), timeout=self.TIMEOUT)
            self.rate_limiter.record_request("betexplorer-scraper", url[:100])
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch BetExplorer fixtures: {e}")
            return []

        soup = BeautifulSoup(resp.text, 'html.parser')
        match_tables = soup.find_all("table", class_="table-main")
        
        results = []
        current_league = "Unknown Competition"
        
        for table in match_tables:
            for row in table.find_all("tr"):
                # Check for league header
                th = row.find("th")
                if th:
                    league_link = th.find("a", class_=lambda c: c and "table-main__tournament" in c)
                    if league_link:
                        current_league = league_link.text.strip()
                    continue
                    
                # Parse match row
                time_span = row.find("span", class_="table-main__time")
                time_str = time_span.text.strip() if time_span else ""
                
                # Check for either class (results page might use table-main__tt, fixtures might use h-text-left)
                td_left = row.find("td", class_="h-text-left") or row.find("td", class_="table-main__tt")
                if not td_left:
                    continue
                    
                match_link = td_left.find("a")
                if not match_link:
                    continue
                    
                match_url = match_link.get('href')
                # The text can have strong tags inside span
                match_name_texts = []
                for s in match_link.stripped_strings:
                    match_name_texts.append(s)
                match_name = " ".join(match_name_texts)
                
                parts = match_name.split(" - ", 1)
                home_team = parts[0].strip() if len(parts) > 0 else "Unknown"
                away_team = parts[1].strip() if len(parts) > 1 else "Unknown"
                
                # External ID can be extracted from URL: /sport/country/league/home-away/ID/
                match_id = match_url.rstrip('/').split('/')[-1] if match_url else ""
                
                # Try to parse data-dt from row format "d,m,Y,H,M" => "13,5,2026,10,00"
                dt_attr = row.get("data-dt")
                if dt_attr:
                    try:
                        dt_parts = dt_attr.split(',')
                        if len(dt_parts) == 5:
                            d, m, y, h, min_ = tuple(int(x) for x in dt_parts)
                            kickoff = datetime(y, m, d, h, min_)
                        elif len(dt_parts) == 3:
                            d, m, y = tuple(int(x) for x in dt_parts)
                            kickoff = datetime(y, m, d)
                        else:
                            kickoff = datetime.strptime(date, "%Y-%m-%d")
                    except Exception:
                        kickoff = datetime.strptime(date, "%Y-%m-%d")
                else:
                    if ":" in time_str:
                        dt_str = f"{date} {time_str}:00"
                        try:
                            kickoff = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            kickoff = datetime.strptime(date, "%Y-%m-%d")
                    else:
                        kickoff = datetime.strptime(date, "%Y-%m-%d")

                status = "NS" if date >= datetime.now().strftime("%Y-%m-%d") else "FT"

                fixture = APIFixture(
                    external_id=match_id,
                    source="betexplorer",
                    sport=sport,
                    competition_name=current_league,
                    home_team_name=home_team,
                    away_team_name=away_team,
                    kickoff=kickoff.isoformat(),
                    status=status
                )
                results.append(fixture)

        self._save_cache(cache_key, {"data": [vars(f) for f in results]})
        return results

    def get_odds(self, match_url: str) -> dict:
        """Get odds from a match detail page."""
        return {}

    def get_results(self, date: str, sport: str = "football") -> list[dict]:
        """Get results."""
        return []

    def get_fixture_stats(self, fixture_id: str) -> list:
        """Not supported — BetExplorer provides odds, not match stats."""
        logger.debug(f"[BetExplorer] get_fixture_stats not supported (id={fixture_id})")
        return []

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Not supported — use Flashscore or ESPN for H2H data."""
        logger.debug(f"[BetExplorer] get_h2h not supported ({team1_id} vs {team2_id})")
        return []
