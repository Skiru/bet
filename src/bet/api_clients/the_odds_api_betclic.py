"""Hardened The Odds API client focused on Betclic coverage."""

from __future__ import annotations

from dataclasses import dataclass
import os
import random
import time
from typing import Any, Mapping, Protocol

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore[assignment]


THE_ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"
DEFAULT_BETCLIC_BOOKMAKERS = ("betclic_fr",)
DEFAULT_MARKETS = ("h2h", "spreads", "totals")
DEFAULT_REGIONS = ("eu",)
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

SPORT_KEY_MAP: dict[str, tuple[str, ...]] = {
    "football": ("soccer_epl", "soccer_uefa_champs_league", "soccer_france_ligue_one", "soccer_poland_ekstraklasa"),
    "basketball": ("basketball_nba", "basketball_euroleague"),
    "tennis": ("tennis_atp", "tennis_wta"),
    "hockey": ("icehockey_nhl",),
}


class HTTPTransport(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class TheOddsApiConfig:
    api_key: str
    base_url: str = THE_ODDS_API_BASE_URL
    timeout_seconds: float = 20.0
    max_retries: int = 2
    regions: tuple[str, ...] = DEFAULT_REGIONS
    bookmakers: tuple[str, ...] = DEFAULT_BETCLIC_BOOKMAKERS
    markets: tuple[str, ...] = DEFAULT_MARKETS

    @classmethod
    def from_env(cls) -> "TheOddsApiConfig":
        api_key = os.getenv("THE_ODDS_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("THE_ODDS_API_KEY is required for The Odds API Betclic odds")
        max_retries = int(os.getenv("THE_ODDS_API_MAX_RETRIES", "2"))
        timeout_seconds = float(os.getenv("THE_ODDS_API_TIMEOUT_SECONDS", "20"))
        return cls(
            api_key=api_key,
            base_url=os.getenv("THE_ODDS_API_BASE_URL", THE_ODDS_API_BASE_URL).strip().rstrip("/"),
            timeout_seconds=timeout_seconds,
            max_retries=max(0, min(max_retries, 5)),
            regions=_split_env_csv("THE_ODDS_API_REGIONS", DEFAULT_REGIONS),
            bookmakers=_split_env_csv("THE_ODDS_API_BOOKMAKERS", DEFAULT_BETCLIC_BOOKMAKERS),
            markets=_split_env_csv("THE_ODDS_API_MARKETS", DEFAULT_MARKETS),
        )


def _split_env_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


class TheOddsApiBetclicClient:
    def __init__(self, config: TheOddsApiConfig, transport: HTTPTransport | None = None) -> None:
        if requests is None and transport is None:
            raise RuntimeError("requests is required unless a transport is injected")
        self.config = config
        self.transport: HTTPTransport = transport or requests.Session()  # type: ignore[union-attr]

    def fetch_sport_key(
        self,
        sport_key: str,
        *,
        commence_time_from: str | None = None,
        commence_time_to: str | None = None,
    ) -> list[dict[str, Any]]:
        url = f"{self.config.base_url}/sports/{sport_key}/odds"
        params = {
            "apiKey": self.config.api_key,
            "regions": ",".join(self.config.regions),
            "bookmakers": ",".join(self.config.bookmakers),
            "markets": ",".join(self.config.markets),
            "oddsFormat": "decimal",
            "dateFormat": "iso",
            "commenceTimeFrom": commence_time_from,
            "commenceTimeTo": commence_time_to,
        }
        payload = self._request_json(url, params)
        if not isinstance(payload, list):
            raise RuntimeError("The Odds API returned unexpected non-list payload")
        return [_normalise_event(event, sport_key) for event in payload if isinstance(event, Mapping)]

    def fetch_odds(
        self,
        sport: str,
        *,
        commence_time_from: str | None = None,
        commence_time_to: str | None = None,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for sport_key in SPORT_KEY_MAP.get(sport, ()): 
            events.extend(
                self.fetch_sport_key(
                    sport_key,
                    commence_time_from=commence_time_from,
                    commence_time_to=commence_time_to,
                )
            )
        return events

    def _request_json(self, url: str, params: Mapping[str, Any]) -> Any:
        clean_params = {key: value for key, value in params.items() if value not in (None, "")}
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.transport.get(url, params=clean_params, timeout=self.config.timeout_seconds)
                status = int(getattr(response, "status_code", 0))
                if status in RETRY_STATUS_CODES and attempt < self.config.max_retries:
                    _sleep_before_retry(attempt, _safe_retry_after(getattr(response, "headers", {}) or {}))
                    continue
                if status >= 400:
                    raise RuntimeError(f"The Odds API request failed with HTTP {status}")
                try:
                    return response.json()
                except Exception as exc:
                    raise RuntimeError("The Odds API returned non-JSON response") from exc
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                _sleep_before_retry(attempt, None)
        raise RuntimeError(f"The Odds API request failed after retries: {last_error}")


def _safe_retry_after(headers: Mapping[str, Any]) -> float | None:
    raw = headers.get("Retry-After") if hasattr(headers, "get") else None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(value, 30.0))


def _sleep_before_retry(attempt: int, retry_after: float | None) -> None:
    delay = retry_after if retry_after is not None else min(0.25 * (2**attempt) + random.random() * 0.05, 2.0)
    time.sleep(delay)


def _normalise_event(raw: Mapping[str, Any], sport_key: str) -> dict[str, Any]:
    event = dict(raw)
    event.setdefault("sport_key", sport_key)
    event["_odds_source"] = "the-odds-api-betclic"
    return event
