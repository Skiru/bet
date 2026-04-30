"""OddsPortal scraper source — uses Playwright + oddsportal_adapter."""

import sys
import time as _time
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from odds_sources import OddsSource, make_event_id
from api_clients.rate_limiter import RateLimiter

SPORT_URLS = {
    "football": "https://www.oddsportal.com/football/",
    "tennis": "https://www.oddsportal.com/tennis/",
    "basketball": "https://www.oddsportal.com/basketball/",
    "hockey": "https://www.oddsportal.com/hockey/",
    "baseball": "https://www.oddsportal.com/baseball/",
    "volleyball": "https://www.oddsportal.com/volleyball/",
    "handball": "https://www.oddsportal.com/handball/",
    "esports": "https://www.oddsportal.com/esports/",
    "snooker": "https://www.oddsportal.com/snooker/",
    "darts": "https://www.oddsportal.com/darts/",
    "table_tennis": "https://www.oddsportal.com/table-tennis/",
    "mma": "https://www.oddsportal.com/mma/",
    "padel": "https://www.oddsportal.com/padel/",
    "speedway": "https://www.oddsportal.com/speedway/",
}

TWO_WAY_SPORTS = {
    "tennis", "basketball", "volleyball", "handball", "baseball",
    "table_tennis", "esports", "mma", "snooker", "darts", "padel", "speedway",
}


class OddsPortalSource(OddsSource):
    """Scrape odds from OddsPortal via Playwright."""

    name = "oddsportal"

    def __init__(self):
        self._limiter = RateLimiter()

    def supported_sports(self) -> list[str]:
        return list(SPORT_URLS.keys())

    def fetch_odds(self, sport: str, date_from: str, date_to: str) -> list[dict]:
        url = SPORT_URLS.get(sport)
        if not url:
            return []

        if not self._limiter.can_request("oddsportal-scraper"):
            print("[oddsportal] Daily rate limit reached, skipping")
            return []

        try:
            from fetch_with_playwright import fetch as pw_fetch
            from adapters.oddsportal_adapter import parse as op_parse
        except ImportError as e:
            print(f"[oddsportal] Import error: {e}")
            return []

        try:
            html = pw_fetch(url)
        except Exception as e:
            print(f"[oddsportal] Playwright error for {sport}: {e}")
            return []

        self._limiter.record_request("oddsportal-scraper", url)
        _time.sleep(3)

        rows = op_parse(html, url)
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
                "sport_key": f"{sport}_oddsportal",
                "sport_title": sport.replace("_", " ").title(),
                "commence_time": commence,
                "home_team": home,
                "away_team": away,
                "bookmakers": [{
                    "key": "oddsportal-avg",
                    "title": "OddsPortal Average",
                    "markets": [{
                        "key": "h2h",
                        "outcomes": outcomes,
                    }],
                }],
                "_our_sport": sport,
                "_odds_source": self.name,
                "_sport_key": f"{sport}_oddsportal",
            })

        return events

    @staticmethod
    def _build_outcomes(home: str, away: str, odds_raw: list, is_two_way: bool) -> list[dict]:
        """Convert raw odds list to structured outcomes."""
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
        """Combine time-only string with date_from to produce ISO 8601."""
        if not match_time:
            return f"{date_from}T00:00:00Z"
        # match_time is typically "HH:MM"
        clean = match_time.strip()
        if len(clean) == 5 and ":" in clean:
            return f"{date_from}T{clean}:00Z"
        return f"{date_from}T00:00:00Z"


SOURCE = OddsPortalSource()
