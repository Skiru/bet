"""The Odds API source — thin wrapper around scripts/fetch_odds_api.py."""

import sys
from pathlib import Path

# Ensure scripts/ is importable
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from odds_sources import OddsSource, PREFERRED_BOOKMAKERS

registry_load_failed = False
registry_load_error = None

try:
    from fetch_odds_api import SPORT_KEY_MAP, get_api_key, fetch_odds as _fetch_odds, discover_active_sport_keys
except Exception as e:
    registry_load_failed = True
    registry_load_error = str(e) or "ImportError"

# The-Odds-API bookmaker keys to include when available
# See: https://the-odds-api.com/liveapi/guides/v4/#bookmakers
_API_BOOKMAKER_KEYS = "bet365,pinnacle,unibet,betfair_ex_eu"


class ProviderRegistryLoadFailedError(Exception):
    pass


class TheOddsAPISource(OddsSource):
    """Wrapper around the existing fetch_odds_api.py module."""

    name = "the-odds-api"
    _active_map = None

    def _check_registry(self):
        if registry_load_failed:
            raise ProviderRegistryLoadFailedError("PROVIDER_REGISTRY_LOAD_FAILED")

    def _get_active_map(self) -> dict:
        """Get sport key map with auto-discovered seasonal keys (cached)."""
        self._check_registry()
        if self._active_map is None:
            try:
                api_key = get_api_key()
                self._active_map = discover_active_sport_keys(api_key)
            except (SystemExit, Exception):
                self._active_map = dict(SPORT_KEY_MAP)
        return self._active_map

    def supported_sports(self) -> list[str]:
        self._check_registry()
        return [sport for sport, keys in self._get_active_map().items() if keys]

    def fetch_odds(self, sport: str, date_from: str, date_to: str) -> list[dict]:
        self._check_registry()
        active_map = self._get_active_map()
        sport_keys = active_map.get(sport, [])
        if not sport_keys:
            return []

        try:
            api_key = get_api_key()
        except SystemExit:
            raise ValueError("PROVIDER_AUTH_BLOCKED")

        # Build ISO 8601 time range from dates
        commence_from = f"{date_from}T00:00:00Z"
        commence_to = f"{date_to}T23:59:59Z"

        all_events = []
        for sport_key in sport_keys:
            try:
                events, _headers = _fetch_odds(
                    api_key, sport_key,
                    commence_from=commence_from,
                    commence_to=commence_to,
                )
            except Exception as e:
                err_msg = str(e).upper()
                if "AUTH" in err_msg or "KEY" in err_msg or "UNAUTHORIZED" in err_msg or "401" in err_msg or "403" in err_msg:
                    raise ValueError("PROVIDER_AUTH_BLOCKED") from e
                if "TIMEOUT" in err_msg or "408" in err_msg or "504" in err_msg or "CONNECTION" in err_msg:
                    raise ValueError("PROVIDER_TIMEOUT") from e
                if "SCHEMA" in err_msg or "PARSE" in err_msg or "JSON" in err_msg:
                    raise ValueError("PROVIDER_SCHEMA_INVALID") from e

                print(f"[the-odds-api] Error fetching {sport_key}: {e}")
                raise

            if not isinstance(events, list):
                raise ValueError("PROVIDER_SCHEMA_INVALID")

            for event in events:
                event["_odds_source"] = self.name
                event["_our_sport"] = sport
                event.setdefault("_sport_key", sport_key)
                all_events.append(event)

        return all_events


SOURCE = TheOddsAPISource()
