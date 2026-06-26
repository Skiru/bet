"""Betclic-focused The Odds API source for scripts/fetch_odds_multi.py."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bet.api_clients.the_odds_api_betclic import TheOddsApiBetclicClient, TheOddsApiConfig  # noqa: E402


class TheOddsApiBetclicSource:
    name = "the-odds-api-betclic"

    def __init__(self, client: TheOddsApiBetclicClient | None = None) -> None:
        self._client = client

    def supported_sports(self) -> list[str]:
        return ["basketball", "football", "hockey", "tennis"]

    def fetch_odds(
        self,
        sport: str,
        date_from: str | None = None,
        date_to: str | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        client = self._client or TheOddsApiBetclicClient(TheOddsApiConfig.from_env())
        commence_from = kwargs.get("commence_time_from") or (f"{date_from}T00:00:00Z" if date_from and "T" not in date_from else date_from)
        commence_to = kwargs.get("commence_time_to") or (f"{date_to}T23:59:59Z" if date_to and "T" not in date_to else date_to)
        return client.fetch_odds(sport, commence_time_from=commence_from, commence_time_to=commence_to)


SOURCE = TheOddsApiBetclicSource()
