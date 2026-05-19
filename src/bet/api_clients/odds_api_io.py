"""Odds-API.io client — real-time odds comparison from 265 bookmakers across 34 sports.

Docs: https://docs.odds-api.io/
Base URL: https://api.odds-api.io/v3
Auth: ?apiKey=KEY query parameter
Rate limit: 5,000 requests/hour (all plans)

Key endpoints used:
  /sports         — list sports (no auth)
  /events         — list events for a sport
  /odds           — get odds for an event from bookmakers
  /odds/multi     — get odds for up to 10 events (1 API call)
  /value-bets     — pre-calculated EV opportunities (!)
  /participants   — search teams/players
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from .base_client import BaseAPIClient, CACHE_DIR
from .rate_limiter import RateLimiter
from normalize_stats import NormalizedFixture, NormalizedMatchStats


ODDS_API_IO_BASE = "https://api.odds-api.io/v3"

# Map our internal sport names → odds-api.io sport slugs
SPORT_SLUG_MAP = {
    "football": "football",
    "basketball": "basketball",
    "tennis": "tennis",
    "hockey": "ice-hockey",
    "volleyball": "volleyball",
}

# Default bookmakers (free plan: max 2 selected via /bookmakers/selected/select)
DEFAULT_BOOKMAKERS = "Betclic PL,Bet365"


class OddsAPIioClient(BaseAPIClient):
    """Odds-API.io client for odds comparison, value bets, and fixture discovery.

    Covers 34 sports, 265 bookmakers, 5000 req/hour.
    Used for: odds cross-validation, EV calculation, fixture discovery.
    """

    TIMEOUT = 20

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="odds-api-io",
            base_url=ODDS_API_IO_BASE,
            rate_limiter=rate_limiter,
        )

    def _build_headers(self) -> dict:
        return {"Accept": "application/json"}

    def _api_request(self, endpoint: str, params: dict | None = None) -> dict | list | None:
        """Make an authenticated request to odds-api.io.

        Returns parsed JSON or None on error.
        """
        if not self.api_key:
            return None

        if not self.rate_limiter.can_request(self.api_name):
            print(f"[{self.api_name}] Hourly quota exhausted")
            return None

        full_params = {"apiKey": self.api_key}
        if params:
            full_params.update(params)

        url = f"{self.base_url}{endpoint}"

        # Check cache
        cache_key = f"odds-api-io/{endpoint.strip('/')}/{json.dumps(params or {}, sort_keys=True)[:60]}"
        cache_key = cache_key.replace("/", "_").replace("?", "_").replace("&", "_")
        cache_key = cache_key.replace("{", "").replace("}", "").replace('"', "")
        # Sanitize for filesystem
        cache_key = "".join(c for c in cache_key if c.isalnum() or c in "-_")[:120]
        cache_key = f"odds-api-io/{cache_key}"
        cached = self._check_cache(cache_key, ttl_hours=1)
        if cached:
            return cached.get("data", cached)

        try:
            response = requests.get(
                url,
                params=full_params,
                headers=self._build_headers(),
                timeout=self.TIMEOUT,
            )
            self.rate_limiter.record_request(self.api_name, endpoint, cost=1)

            if response.status_code == 429:
                print(f"[{self.api_name}] Rate limited (HTTP 429)")
                return None
            if response.status_code == 401:
                print(f"[{self.api_name}] Unauthorized — check API key")
                return None
            if response.status_code >= 400:
                print(f"[{self.api_name}] HTTP {response.status_code}: {response.text[:200]}")
                return None

            data = response.json()

            # Track rate limit headers
            remaining = response.headers.get("x-ratelimit-remaining", "?")
            print(f"[{self.api_name}] {endpoint} → {response.status_code} (remaining: {remaining})")

            self._save_cache(cache_key, {"data": data})
            return data

        except requests.exceptions.RequestException as e:
            print(f"[{self.api_name}] Request failed: {e}")
            return None

    # ─── Public API Methods ──────────────────────────────────────────

    def list_sports(self) -> list[dict]:
        """GET /sports — list available sports (no auth required)."""
        try:
            resp = requests.get(f"{self.base_url}/sports", timeout=self.TIMEOUT)
            return resp.json() if resp.status_code == 200 else []
        except Exception:
            return []

    def list_leagues(self, sport_slug: str) -> list[dict]:
        """GET /leagues — list leagues for a sport."""
        return self._api_request("/leagues", {"sport": sport_slug}) or []

    def get_events(self, sport_slug: str, status: str = "pending",
                   from_dt: str = None, to_dt: str = None) -> list[dict]:
        """GET /events — list events for a sport."""
        params = {"sport": sport_slug, "status": status}
        if from_dt:
            params["from"] = from_dt
        if to_dt:
            params["to"] = to_dt
        return self._api_request("/events", params) or []

    def get_odds(self, event_id: int | str,
                 bookmakers: str = DEFAULT_BOOKMAKERS) -> dict | None:
        """GET /odds — get odds for a specific event."""
        return self._api_request("/odds", {
            "eventId": str(event_id),
            "bookmakers": bookmakers,
        })

    def get_odds_multi(self, event_ids: list[int | str],
                       bookmakers: str = DEFAULT_BOOKMAKERS) -> list[dict]:
        """GET /odds/multi — get odds for up to 10 events (1 API call)."""
        ids_str = ",".join(str(eid) for eid in event_ids[:10])
        return self._api_request("/odds/multi", {
            "eventIds": ids_str,
            "bookmakers": bookmakers,
        }) or []

    def get_value_bets(self, bookmaker: str = "Bet365",
                       sport: str = None, include_details: bool = True) -> list[dict]:
        """GET /value-bets — pre-calculated EV opportunities."""
        params = {
            "bookmaker": bookmaker,
            "includeEventDetails": str(include_details).lower(),
        }
        if sport:
            params["sport"] = sport
        return self._api_request("/value-bets", params) or []

    def search_participants(self, sport_slug: str, name: str) -> list[dict]:
        """GET /participants — search teams/players."""
        return self._api_request("/participants", {
            "sport": sport_slug,
            "search": name,
        }) or []

    # ─── BaseAPIClient interface (for CLIENT_REGISTRY) ───────────────

    def get_fixtures(self, date: str) -> list[NormalizedFixture]:
        """Fetch pending events across all supported sports for a date."""
        all_fixtures = []
        from_dt = f"{date}T00:00:00Z"
        to_dt = f"{date}T23:59:59Z"

        for our_sport, slug in SPORT_SLUG_MAP.items():
            events = self.get_events(slug, status="pending", from_dt=from_dt, to_dt=to_dt)
            for ev in events:
                nf = NormalizedFixture(
                    fixture_id=str(ev.get("id", "")),
                    source=self.api_name,
                    sport=our_sport,
                    competition=ev.get("league", {}).get("name", ""),
                    home_team=ev.get("home", ""),
                    away_team=ev.get("away", ""),
                    kickoff=ev.get("date", ""),
                    status=ev.get("status", "pending"),
                )
                all_fixtures.append(nf)

        return all_fixtures

    def get_fixture_stats(self, fixture_id: str) -> NormalizedMatchStats | None:
        """Not applicable — odds-api.io provides odds, not match statistics."""
        return None

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list:
        """Not applicable."""
        return []

    def resolve_team_id(self, team_name: str, **kwargs) -> str | None:
        """Resolve team name via /participants endpoint."""
        # Try each sport until we find the team
        for our_sport, slug in SPORT_SLUG_MAP.items():
            results = self.search_participants(slug, team_name)
            if results:
                return str(results[0].get("id", ""))
        return None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list:
        """Not applicable — odds API doesn't provide historical fixtures."""
        return []

    def is_available(self) -> bool:
        return bool(self.api_key) and self.api_key != "YOUR_KEY_HERE"


# ─── Standalone Functions (for pipeline scripts) ─────────────────────


def fetch_odds_snapshot(date: str, sports: list[str] | None = None,
                        bookmakers: str = DEFAULT_BOOKMAKERS) -> dict:
    """Fetch odds for all events on a date and save snapshot.

    Returns summary dict with event count, odds data, and value bets.
    """
    from .rate_limiter import RateLimiter

    rl = RateLimiter()
    client = OddsAPIioClient(rate_limiter=rl)

    if not client.is_available():
        print("[odds-api-io] No API key configured — skipping")
        return {"events": 0}

    data_dir = Path(__file__).parent.parent.parent / "betting" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    all_events = []
    from_dt = f"{date}T00:00:00Z"
    to_dt = f"{date}T23:59:59Z"

    sports_to_scan = sports or list(SPORT_SLUG_MAP.keys())

    for our_sport in sports_to_scan:
        slug = SPORT_SLUG_MAP.get(our_sport)
        if not slug:
            continue

        events = client.get_events(slug, status="pending", from_dt=from_dt, to_dt=to_dt)
        if not events:
            continue

        print(f"[odds-api-io] {our_sport}: {len(events)} events")

        # Fetch odds in batches of 10 (multi endpoint = 1 API call per batch)
        event_ids = [ev.get("id") for ev in events if ev.get("id")]
        for i in range(0, len(event_ids), 10):
            batch = event_ids[i:i + 10]
            odds_data = client.get_odds_multi(batch, bookmakers=bookmakers)
            if odds_data:
                for od in odds_data:
                    od["_our_sport"] = our_sport
                    od["_source"] = "odds-api-io"
                all_events.extend(odds_data)

    # Fetch value bets (unique feature — pre-calculated EV)
    value_bets = []
    for bookie in ["Bet365", "Unibet", "Pinnacle"]:
        vb = client.get_value_bets(bookmaker=bookie)
        if vb:
            value_bets.extend(vb)

    # Save snapshot
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "odds-api-io",
        "total_events_with_odds": len(all_events),
        "total_value_bets": len(value_bets),
        "events": all_events,
        "value_bets": value_bets,
    }

    output_file = data_dir / "odds_api_io_snapshot.json"
    output_file.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[odds-api-io] Saved {len(all_events)} events + {len(value_bets)} value bets → {output_file}")

    return snapshot
