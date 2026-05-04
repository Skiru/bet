"""Odds-API.io odds source — wrapper around api_clients/odds_api_io.py."""

import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from odds_sources import OddsSource
from api_clients.odds_api_io import OddsAPIioClient, SPORT_SLUG_MAP
from api_clients.rate_limiter import RateLimiter


class OddsAPIioSource(OddsSource):
    """Odds-API.io source — 265 bookmakers, 34 sports, value bets."""

    name = "odds-api-io"

    def __init__(self):
        self._limiter = RateLimiter()
        self._client = OddsAPIioClient(rate_limiter=self._limiter)

    def supported_sports(self) -> list[str]:
        return list(SPORT_SLUG_MAP.keys())

    def fetch_odds(self, sport: str, date_from: str, date_to: str) -> list[dict]:
        if sport not in SPORT_SLUG_MAP:
            return []

        slug = SPORT_SLUG_MAP[sport]

        try:
            from_dt = f"{date_from}T00:00:00Z"
            to_dt = f"{date_to}T23:59:59Z"
            events = self._client.get_events(slug, status="pending",
                                             from_dt=from_dt, to_dt=to_dt)
            if not events:
                return []

            # Batch fetch odds using multi endpoint (up to 10 per call)
            results = []
            event_map = {str(ev.get("id", "")): ev for ev in events if ev.get("id")}
            event_ids = list(event_map.keys())

            for i in range(0, len(event_ids), 10):
                batch = event_ids[i:i + 10]
                odds_batch = self._client.get_odds_multi(batch)
                if not odds_batch:
                    # Fallback: fetch individually
                    for eid in batch:
                        odds_data = self._client.get_odds(eid)
                        if odds_data:
                            odds_batch.append(odds_data) if isinstance(odds_data, dict) else None

                if not isinstance(odds_batch, list):
                    odds_batch = [odds_batch] if odds_batch else []

                for odds_item in odds_batch:
                    if not isinstance(odds_item, dict):
                        continue

                    event_id = str(odds_item.get("eventId", odds_item.get("id", "")))
                    event = event_map.get(event_id, odds_item)

                    std_event = {
                        "id": event_id,
                        "sport_key": f"{sport}_odds_api_io",
                        "sport_title": sport.replace("_", " ").title(),
                        "commence_time": event.get("date", event.get("start_time", "")),
                        "home_team": event.get("home", odds_item.get("home", "")),
                        "away_team": event.get("away", odds_item.get("away", "")),
                        "bookmakers": [],
                        "_our_sport": sport,
                        "_odds_source": self.name,
                        "_sport_key": f"{sport}_odds_api_io",
                    }

                    # Parse bookmakers from odds response
                    bookmakers_data = odds_item.get("bookmakers", {})
                    if isinstance(bookmakers_data, dict):
                        for bookie_name, markets in bookmakers_data.items():
                            bm = {
                                "key": bookie_name.lower().replace(" ", "_"),
                                "title": bookie_name,
                                "markets": [],
                            }
                            if isinstance(markets, list):
                                for market in markets:
                                    m_name = market.get("name", "")
                                    m = {"key": m_name.lower().replace(" ", "_"), "outcomes": []}
                                    for entry in market.get("odds", []):
                                        if isinstance(entry, dict):
                                            for side, price in entry.items():
                                                try:
                                                    m["outcomes"].append({
                                                        "name": side,
                                                        "price": float(price),
                                                    })
                                                except (ValueError, TypeError):
                                                    pass
                                    if m["outcomes"]:
                                        bm["markets"].append(m)
                            if bm["markets"]:
                                std_event["bookmakers"].append(bm)
                    elif isinstance(bookmakers_data, list):
                        # Alternative format: list of bookmaker dicts
                        for bm_item in bookmakers_data:
                            if not isinstance(bm_item, dict):
                                continue
                            bm_name = bm_item.get("name", bm_item.get("key", "unknown"))
                            bm = {
                                "key": bm_name.lower().replace(" ", "_"),
                                "title": bm_name,
                                "markets": [],
                            }
                            for market in bm_item.get("markets", []):
                                m_key = market.get("key", market.get("name", "")).lower()
                                m = {"key": m_key, "outcomes": []}
                                for outcome in market.get("outcomes", []):
                                    try:
                                        m["outcomes"].append({
                                            "name": outcome.get("name", ""),
                                            "price": float(outcome.get("price", 0)),
                                        })
                                    except (ValueError, TypeError):
                                        pass
                                if m["outcomes"]:
                                    bm["markets"].append(m)
                            if bm["markets"]:
                                std_event["bookmakers"].append(bm)

                    if std_event["bookmakers"]:
                        results.append(std_event)

            return results
        except Exception as e:
            print(f"[odds-api-io] Error fetching {sport} odds: {e}")
            return []


SOURCE = OddsAPIioSource()
