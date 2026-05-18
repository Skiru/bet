"""The Odds API source adapter — fixture discovery with odds attached.

Conservative credit usage: top 10 football leagues only (configurable).
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

from ..models import DiscoveredEvent
from .base import AbstractSourceAdapter

BASE_URL = "https://api.the-odds-api.com/v4"
CONFIG_DIR = Path(__file__).parent.parent.parent.parent.parent / "config"

# Top 10 football leagues (conservative credit budget)
TOP_FOOTBALL_KEYS = [
    "soccer_epl", "soccer_germany_bundesliga", "soccer_spain_la_liga",
    "soccer_italy_serie_a", "soccer_france_ligue_one",
    "soccer_usa_mls", "soccer_brazil_campeonato",
    "soccer_uefa_champs_league", "soccer_uefa_europa_league",
    "soccer_poland_ekstraklasa",
]

SPORT_KEY_MAP = {
    "football": TOP_FOOTBALL_KEYS,
    "basketball": ["basketball_nba", "basketball_euroleague"],
    "hockey": ["icehockey_nhl", "icehockey_shl"],
    "tennis": [],  # populated via auto-discovery
}

# Mapping from API prefix → our sport name
PREFIX_MAP = {
    "soccer_": "football",
    "tennis_": "tennis",
    "basketball_": "basketball",
    "icehockey_": "hockey",
}

logger = logging.getLogger(__name__)


class OddsAPIAdapter(AbstractSourceAdapter):
    """Secondary source — events with odds. No volleyball coverage."""

    name = "odds-api"
    priority = 2
    supported_sports = ["football", "basketball", "hockey", "tennis"]

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or self._load_api_key()
        self._active_keys: dict[str, list[str]] | None = None
        self._auth_failed: bool = False
        super().__init__()

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _fetch_events_impl(self, date: str, sport: str) -> list[DiscoveredEvent]:
        sport_keys = self._get_sport_keys(sport)
        if not sport_keys:
            return []

        all_events: list[DiscoveredEvent] = []
        for key in sport_keys:
            if self._auth_failed:
                break
            events = self._fetch_for_key(key, sport, date)
            all_events.extend(events)

        return all_events

    def _fetch_for_key(
        self, sport_key: str, sport: str, date: str
    ) -> list[DiscoveredEvent]:
        """Fetch odds for one sport key. Returns events for the target date."""
        params = {
            "apiKey": self._api_key,
            "regions": "eu",
            "markets": "h2h,totals",
            "oddsFormat": "decimal",
        }

        try:
            resp = requests.get(
                f"{BASE_URL}/sports/{sport_key}/odds",
                params=params,
                timeout=15,
            )
            if resp.status_code == 401:
                self._auth_failed = True
                self.logger.warning("Odds API auth failed (401) — key expired or credits exhausted. Skipping remaining.")
                return []
            if resp.status_code in (404, 422):
                return []
            resp.raise_for_status()
        except requests.RequestException as e:
            self.logger.warning("Odds API %s failed: %s", sport_key, e)
            return []

        remaining = resp.headers.get("x-requests-remaining", "?")
        self.logger.debug(
            "Odds API %s: credits remaining=%s", sport_key, remaining
        )

        events = []
        for item in resp.json():
            try:
                commence = item.get("commence_time", "")
                kickoff = datetime.fromisoformat(
                    commence.replace("Z", "+00:00")
                )

                # Filter to target date only
                if kickoff.strftime("%Y-%m-%d") != date:
                    continue

                # Extract best odds
                odds_data = self._extract_odds(item)

                events.append(DiscoveredEvent(
                    source="odds-api",
                    external_id=item.get("id", ""),
                    sport=sport,
                    competition=item.get("sport_title", ""),
                    home_team=item.get("home_team", ""),
                    away_team=item.get("away_team", ""),
                    kickoff=kickoff,
                    status="scheduled",
                    odds=odds_data,
                    raw_data={"sport_key": sport_key},
                ))
            except Exception as e:
                self.logger.debug("Skipping Odds API event: %s", e)
                continue

        return events

    def _get_sport_keys(self, sport: str) -> list[str]:
        """Get sport keys, with auto-discovery for tennis."""
        if self._active_keys is None:
            self._active_keys = dict(SPORT_KEY_MAP)
            self._discover_active_keys()

        return self._active_keys.get(sport, [])

    def _discover_active_keys(self) -> None:
        """Fetch live sport keys from API (FREE, 0 credits) — for tennis."""
        if not self._api_key:
            return

        try:
            resp = requests.get(
                f"{BASE_URL}/sports",
                params={"apiKey": self._api_key},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException:
            return

        for s in resp.json():
            if not s.get("active", False):
                continue
            key = s["key"]
            if "winner" in key:
                continue
            for prefix, sport_name in PREFIX_MAP.items():
                if key.startswith(prefix) and key not in self._active_keys.get(sport_name, []):
                    self._active_keys.setdefault(sport_name, []).append(key)
                    break

    @staticmethod
    def _extract_odds(item: dict) -> dict | None:
        """Extract structured odds from an Odds API event."""
        bookmakers = item.get("bookmakers", [])
        if not bookmakers:
            return None

        odds: dict = {}
        for bm in bookmakers[:3]:  # top 3 bookmakers
            bm_key = bm.get("key", "unknown")
            for market in bm.get("markets", []):
                mkey = market.get("key", "")
                for outcome in market.get("outcomes", []):
                    label = f"{bm_key}|{mkey}|{outcome.get('name', '')}"
                    odds[label] = outcome.get("price", 0.0)

        return odds if odds else None

    @staticmethod
    def _load_api_key() -> str | None:
        """Load Odds API key from config."""
        import os

        key = os.environ.get("ODDS_API_KEY")
        if key and key.strip():
            return key.strip()

        keys_file = CONFIG_DIR / "api_keys.json"
        if keys_file.exists():
            try:
                data = json.loads(keys_file.read_text(encoding="utf-8"))
                k = data.get("odds-api", "")
                if k and k.strip():
                    return k.strip()
            except (json.JSONDecodeError, OSError):
                pass

        key_file = CONFIG_DIR / "odds_api_key.txt"
        if key_file.exists():
            for line in key_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    return line

        return None
