"""BetExplorer scraper source — uses Playwright + betexplorer_adapter."""

import sys
import time as _time
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from odds_sources import OddsSource, make_event_id
from api_clients.rate_limiter import RateLimiter

SPORT_URLS = {
    "football": "https://www.betexplorer.com/football/",
    "tennis": "https://www.betexplorer.com/tennis/",
    "basketball": "https://www.betexplorer.com/basketball/",
    "hockey": "https://www.betexplorer.com/hockey/",
    "volleyball": "https://www.betexplorer.com/volleyball/",
}

TWO_WAY_SPORTS = {
    "tennis", "basketball", "volleyball",
}


class BetExplorerSource(OddsSource):
    """Scrape odds from BetExplorer via Playwright."""

    name = "betexplorer"

    def __init__(self):
        self._limiter = RateLimiter()

    def supported_sports(self) -> list[str]:
        return list(SPORT_URLS.keys())

    def fetch_odds(self, sport: str, date_from: str, date_to: str) -> list[dict]:
        url = SPORT_URLS.get(sport)
        if not url:
            return []

        if not self._limiter.can_request("betexplorer-scraper"):
            print("[betexplorer] Daily rate limit reached, skipping")
            return []

        try:
            from fetch_with_playwright import fetch as pw_fetch
            from adapters.betexplorer_adapter import parse as be_parse
        except ImportError as e:
            print(f"[betexplorer] Import error: {e}")
            return []

        try:
            html = pw_fetch(url)
        except Exception as e:
            print(f"[betexplorer] Playwright error for {sport}: {e}")
            return []

        self._limiter.record_request("betexplorer-scraper", url)
        _time.sleep(3)

        rows = be_parse(html, url)
        is_two_way = sport in TWO_WAY_SPORTS
        events = []

        for row in rows:
            home = row.get("home", "")
            away = row.get("away", "")
            if not home or not away:
                continue

            odds_raw = row.get("odds", [])
            outcomes = self._build_outcomes(home, away, odds_raw, is_two_way)
            if not outcomes:
                continue

            match_time = row.get("time", "")
            commence = self._build_commence_time(match_time, date_from)
            event_id = make_event_id(self.name, sport, home, away, match_time or "0000")

            events.append({
                "id": event_id,
                "sport_key": f"{sport}_betexplorer",
                "sport_title": sport.replace("_", " ").title(),
                "commence_time": commence,
                "home_team": home,
                "away_team": away,
                "bookmakers": [{
                    "key": "betexplorer-avg",
                    "title": "BetExplorer Average",
                    "markets": [{
                        "key": "h2h",
                        "outcomes": outcomes,
                    }],
                }],
                "_our_sport": sport,
                "_odds_source": self.name,
                "_sport_key": f"{sport}_betexplorer",
            })

        return events

    @staticmethod
    def _build_outcomes(home: str, away: str, odds_raw: list, is_two_way: bool) -> list[dict]:
        try:
            odds = [float(o) for o in odds_raw]
        except (ValueError, TypeError):
            return []

        if is_two_way and len(odds) >= 2:
            return [
                {"name": home, "price": odds[0]},
                {"name": away, "price": odds[1]},
            ]
        elif not is_two_way and len(odds) >= 3:
            return [
                {"name": home, "price": odds[0]},
                {"name": "Draw", "price": odds[1]},
                {"name": away, "price": odds[2]},
            ]
        return []

    @staticmethod
    def _build_commence_time(match_time: str, date_from: str) -> str:
        if not match_time:
            return f"{date_from}T00:00:00Z"
        clean = match_time.strip()
        if len(clean) == 5 and ":" in clean:
            return f"{date_from}T{clean}:00Z"
        return f"{date_from}T00:00:00Z"

    def fetch_match_totals(self, match_url: str) -> dict:
        """Fetch Over/Under totals odds from a BetExplorer match detail page.

        Args:
            match_url: Full URL to a BetExplorer match page.

        Returns:
            Dict with totals data, e.g.:
            {"line": 2.5, "over": 1.85, "under": 1.95, "bookmaker": "betexplorer-avg"}
            Returns {} if totals tab not found or page too complex to parse.
        """
        # TODO: Implement full totals parsing. BetExplorer match pages have
        # an "Over/Under" tab that loads via AJAX. The URL pattern is typically:
        # {match_url}/#/over-under/
        # Requires Playwright to click the tab and extract the rendered table.
        return {}

    def fetch_top_match_totals(self, sport: str, date_from: str,
                               max_matches: int = 20) -> list[dict]:
        """Fetch totals for top N matches in a sport (stub).

        Args:
            sport: Internal sport key.
            date_from: Date string YYYY-MM-DD.
            max_matches: Maximum number of matches to fetch totals for.

        Returns:
            List of dicts with match info and totals odds.
        """
        # TODO: Implement once fetch_match_totals works.
        # Plan: 1) Fetch listing page, 2) Extract match detail URLs,
        # 3) Call fetch_match_totals for top N matches.
        return []


SOURCE = BetExplorerSource()
