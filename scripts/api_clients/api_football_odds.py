"""API-Football /odds client — fetch pre-match odds from api-sports.io.

Uses the same API key and rate limit as api-football (shared key).
Docs: https://www.api-football.com/documentation-v3#tag/Odds
Host: v3.football.api-sports.io
Endpoint: /odds?date=YYYY-MM-DD (paginated)
"""

import re

from .base_client import APISportsClient, CACHE_DIR
from .rate_limiter import RateLimiter

# Map API-Football bet type IDs to standard market keys
BET_TYPE_MAP = {
    1: "h2h",             # Match Winner (Home / Draw / Away)
    5: "totals",          # Goals Over/Under
    6: "totals_corners",  # Corners Over/Under
    40: "totals_cards",   # Cards Over/Under (yellow)
    67: "totals_fouls",   # Fouls Over/Under
}

# Slugify pattern: lowercase, replace non-alphanum with hyphens
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    """Convert bookmaker name to a URL-safe slug."""
    return _SLUG_RE.sub("-", name.lower()).strip("-")


class APIFootballOddsClient(APISportsClient):
    """API-Football /odds — pre-match odds for football fixtures."""

    _SHARES_FOOTBALL_KEY = True

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="api-football",
            base_url="https://v3.football.api-sports.io",
            rate_limiter=rate_limiter,
        )

    # -- Abstract method stubs (this client only fetches odds) ----------------

    def get_fixtures(self, date: str) -> list[dict]:
        raise NotImplementedError("Use APIFootballClient for fixtures")

    def get_fixture_stats(self, fixture_id: str) -> dict:
        raise NotImplementedError("Use APIFootballClient for stats")

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        raise NotImplementedError("Use APIFootballClient for H2H")

    def fetch_odds_for_date(self, date: str) -> list[dict]:
        """Fetch all odds for a given date, paginating through all pages.

        Args:
            date: Date string in YYYY-MM-DD format.

        Returns:
            List of events in the standard snapshot format compatible
            with fetch_odds_api.py output.
        """
        if not self._check_api_key():
            return []

        cache_key = f"football/odds/{date}"
        cached = self._check_cache(cache_key, ttl_hours=3)
        if cached:
            return cached.get("events", [])

        all_items = []
        page = 1

        while True:
            try:
                data = self._request(
                    "/odds",
                    params={"date": date, "page": str(page)},
                )
            except Exception as e:
                print(f"[{self.api_name}] Error fetching odds for {date} page {page}: {e}")
                break

            items = data.get("response", [])
            all_items.extend(items)

            paging = data.get("paging", {})
            total_pages = paging.get("total", 1)
            if page >= total_pages:
                break
            page += 1

        events = [self._transform_item(item) for item in all_items]
        events = [e for e in events if e is not None]

        self._save_cache(cache_key, {
            "events": events,
            "count": len(events),
        })

        print(f"[{self.api_name}] Fetched odds for {len(events)} fixtures on {date}")
        return events

    def _transform_item(self, item: dict) -> dict | None:
        """Transform a single API-Football odds item to the snapshot format."""
        fixture = item.get("fixture", {})
        league = item.get("league", {})
        bookmakers_raw = item.get("bookmakers", [])

        fixture_id = fixture.get("id")
        if not fixture_id:
            return None

        home_team = fixture.get("home") or league.get("home", "")
        away_team = fixture.get("away") or league.get("away", "")

        # Some responses nest teams under fixture or under separate keys
        # Try fallback extraction if empty
        if not home_team or not away_team:
            # The /odds endpoint doesn't always include team names directly;
            # we keep what we have (may be empty strings)
            pass

        bookmakers = []
        for bm in bookmakers_raw:
            bm_name = bm.get("name", "")
            markets = []
            for bet in bm.get("bets", []):
                bet_id = bet.get("id")
                market_key = BET_TYPE_MAP.get(bet_id)
                if not market_key:
                    continue

                outcomes = []
                for val in bet.get("values", []):
                    odd_str = val.get("odd", "0")
                    try:
                        price = float(odd_str)
                    except (ValueError, TypeError):
                        continue
                    outcomes.append({
                        "name": str(val.get("value", "")),
                        "price": price,
                    })

                if outcomes:
                    markets.append({
                        "key": market_key,
                        "outcomes": outcomes,
                    })

            if markets:
                bookmakers.append({
                    "key": _slugify(bm_name),
                    "title": bm_name,
                    "markets": markets,
                })

        if not bookmakers:
            return None

        return {
            "id": str(fixture_id),
            "sport_key": "soccer_api_football",
            "sport_title": league.get("name", ""),
            "commence_time": fixture.get("date", ""),
            "home_team": home_team,
            "away_team": away_team,
            "bookmakers": bookmakers,
            "_our_sport": "football",
            "_odds_source": "api-football",
            "_sport_key": "soccer_api_football",
        }
