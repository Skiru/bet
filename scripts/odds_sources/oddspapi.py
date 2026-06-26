"""OddsPapi odds source for the existing multi-source odds scanner.

Priority use-case: Superbet PL bookmaker odds. Exports `SOURCE` with the same
interface used by `scripts/fetch_odds_multi.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bet.api_clients.oddspapi import OddspapiConfig, OddsPapiClient, SPORT_SLUG_MAP  # noqa: E402
from bet.odds_provider_access import is_odds_source_enabled, odds_source_access_status  # noqa: E402


class OddsPapiSource:
    name = "oddspapi"

    def __init__(self, client: OddsPapiClient | None = None) -> None:
        self._client = client

    def _access_enabled(self) -> bool:
        return self._client is not None or is_odds_source_enabled(self.name, mode="scan")

    def _disabled_log(self, action: str) -> None:
        status = odds_source_access_status(self.name)
        reason = status.get("reason", "disabled")
        print(f"  {self.name}: {action} skipped by access gate -- {reason}")

    def supported_sports(self) -> list[str]:
        if not self._access_enabled():
            self._disabled_log("supported_sports")
            return []
        return sorted(set(SPORT_SLUG_MAP.keys()) - {"soccer"})

    def fetch_odds(
        self,
        sport: str,
        date_from: str | None = None,
        date_to: str | None = None,
        *,
        days_ahead: int = 3,
        hours_back: int = 6,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        if not self._access_enabled():
            self._disabled_log("fetch_odds")
            return []
        if sport not in SPORT_SLUG_MAP:
            return []
        now = datetime.now(timezone.utc)
        from_dt = kwargs.get("from_dt") or date_from or (now - timedelta(hours=hours_back)).isoformat()
        to_dt = kwargs.get("to_dt") or date_to or (now + timedelta(days=days_ahead)).isoformat()
        client = self._client or OddsPapiClient(OddspapiConfig.from_env())
        events = client.fetch_odds(
            sport=sport,
            from_dt=str(from_dt),
            to_dt=str(to_dt),
            league=kwargs.get("league"),
            live=kwargs.get("live"),
        )
        return [event.as_existing_pipeline_dict() for event in events]


SOURCE = OddsPapiSource()
