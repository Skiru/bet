"""Betclic scraper source — uses Playwright + betclic_adapter.

NOTE: Betclic blocks automated access (403). This source handles failures
gracefully and returns [] on any error.
"""

import sys
import time as _time
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from odds_sources import OddsSource, make_event_id
from api_clients.rate_limiter import RateLimiter

SPORT_URLS = {
    "football": "https://www.betclic.pl/pilka-nozna-s1",
    "tennis": "https://www.betclic.pl/tenis-s2",
    "basketball": "https://www.betclic.pl/koszykowka-s4",
    "volleyball": "https://www.betclic.pl/siatkowka-s18",
    "hockey": "https://www.betclic.pl/hokej-na-lodzie-s13",
    "handball": "https://www.betclic.pl/pilka-reczna-s9",
    "baseball": "https://www.betclic.pl/baseball-s14",
    "esports": "https://www.betclic.pl/esport-s42",
    "mma": "https://www.betclic.pl/sporty-walki-s15",
    "snooker": "https://www.betclic.pl/snooker-s36",
    "darts": "https://www.betclic.pl/rzutki-s33",
    "table_tennis": "https://www.betclic.pl/tenis-stolowy-s37",
}

TWO_WAY_SPORTS = {
    "tennis", "basketball", "volleyball", "handball", "baseball",
    "table_tennis", "esports", "mma", "snooker", "darts",
}


class BetclicSource(OddsSource):
    """Scrape odds from Betclic via Playwright.

    Betclic actively blocks automated access. All errors are handled
    gracefully — returns empty list on failure.
    """

    name = "betclic"

    def __init__(self):
        self._limiter = RateLimiter()

    def supported_sports(self) -> list[str]:
        return list(SPORT_URLS.keys())

    def fetch_odds(self, sport: str, date_from: str, date_to: str) -> list[dict]:
        url = SPORT_URLS.get(sport)
        if not url:
            return []

        if not self._limiter.can_request("betclic-scraper"):
            print("[betclic] Daily rate limit reached, skipping")
            return []

        try:
            from fetch_with_playwright import fetch as pw_fetch
            from adapters.betclic_adapter import parse as bc_parse
        except ImportError as e:
            print(f"[betclic] Import error: {e}")
            return []

        try:
            html = pw_fetch(url)
        except Exception as e:
            print(f"[betclic] Playwright error for {sport}: {e} (likely 403)")
            return []

        self._limiter.record_request("betclic-scraper", url)
        _time.sleep(3)

        rows = bc_parse(html, url)
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
                "sport_key": f"{sport}_betclic",
                "sport_title": sport.replace("_", " ").title(),
                "commence_time": commence,
                "home_team": home,
                "away_team": away,
                "bookmakers": [{
                    "key": "betclic",
                    "title": "Betclic",
                    "markets": [{
                        "key": "h2h",
                        "outcomes": outcomes,
                    }],
                }],
                "_our_sport": sport,
                "_odds_source": self.name,
                "_sport_key": f"{sport}_betclic",
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


SOURCE = BetclicSource()
