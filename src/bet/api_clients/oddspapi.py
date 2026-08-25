"""Production-oriented OddsPapi client for bookmaker odds.

Primary purpose: Superbet PL odds without sportsbook scraping.

Design goals:
- provider-facing HTTP boundary with timeout, bounded retry, backoff, JSON guardrails;
- env-driven endpoint/bookmaker/market config because odds providers evolve;
- normalization for both generic odds payloads and OddsPapi v4 documented
  `bookmakerOdds -> markets -> outcomes -> players` shape;
- output compatible with the existing `scripts/odds_sources` snapshot format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from .env import get_env
import re
import random
import time
from typing import Any, Mapping, Protocol

try:  # requests is already used by the existing scripts/requirements.txt stack.
    import requests
except Exception:  # pragma: no cover - import failure is surfaced at runtime.
    requests = None  # type: ignore[assignment]


DEFAULT_BASE_URL = "https://api.oddspapi.io/v4"
DEFAULT_ACCOUNT_ENDPOINT = "/account"
DEFAULT_FIXTURES_ENDPOINT = "/fixtures"
DEFAULT_ODDS_ENDPOINT = "/odds"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_MARKETS = ("h2h", "totals", "spreads")
# Public OddsPapi Superbet PL guide documents bookmaker slug `superbet.pl`.
DEFAULT_BOOKMAKERS = ("superbet.pl",)
REDACTED_TOKEN = "[REDACTED]"

# Conservative sport IDs/slugs. The public docs show soccer as sportId=10.
# Unknown sports still fall back to slug so the integration can be env-extended.
SPORT_ID_MAP: dict[str, str] = {
    "football": "10",
    "soccer": "10",
}
SPORT_SLUG_MAP: dict[str, str] = {
    "football": "football",
    "soccer": "football",
    "basketball": "basketball",
    "tennis": "tennis",
    "hockey": "hockey",
    "volleyball": "volleyball",
    "cs2": "cs2",
    "dota2": "dota2",
    "valorant": "valorant",
}


class HTTPTransport(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...


class OddsPapiError(RuntimeError):
    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


@dataclass(frozen=True)
class OddspapiConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    account_endpoint: str = DEFAULT_ACCOUNT_ENDPOINT
    fixtures_endpoint: str = DEFAULT_FIXTURES_ENDPOINT
    odds_endpoint: str = DEFAULT_ODDS_ENDPOINT
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = 2
    bookmaker_filter: tuple[str, ...] = DEFAULT_BOOKMAKERS
    markets: tuple[str, ...] = DEFAULT_MARKETS

    @classmethod
    def from_env(cls) -> "OddspapiConfig":
        api_key = get_env("ODDSPAPI_API_KEY")
        if not api_key:
            raise RuntimeError("ODDSPAPI_API_KEY is required for OddsPapi Superbet odds")
        base_url = os.getenv("ODDSPAPI_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
        account_endpoint = os.getenv("ODDSPAPI_ACCOUNT_ENDPOINT", DEFAULT_ACCOUNT_ENDPOINT).strip()
        fixtures_endpoint = os.getenv("ODDSPAPI_FIXTURES_ENDPOINT", DEFAULT_FIXTURES_ENDPOINT).strip()
        odds_endpoint = os.getenv("ODDSPAPI_ODDS_ENDPOINT", DEFAULT_ODDS_ENDPOINT).strip()
        bookmakers = _split_env_csv("ODDSPAPI_BOOKMAKERS", DEFAULT_BOOKMAKERS)
        markets = _split_env_csv("ODDSPAPI_MARKETS", DEFAULT_MARKETS)
        max_retries = int(os.getenv("ODDSPAPI_MAX_RETRIES", "2"))
        timeout_seconds = float(os.getenv("ODDSPAPI_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
        return cls(
            api_key=api_key,
            base_url=base_url,
            account_endpoint=account_endpoint,
            fixtures_endpoint=fixtures_endpoint,
            odds_endpoint=odds_endpoint,
            timeout_seconds=timeout_seconds,
            max_retries=max(0, min(max_retries, 5)),
            bookmaker_filter=bookmakers,
            markets=markets,
        )


def _split_env_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalise_key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def canonical_market_key(raw: Any, *, raw_market: Mapping[str, Any] | None = None) -> str:
    key = _normalise_key(raw)
    aliases = {
        "moneyline": "h2h",
        "match_winner": "h2h",
        "winner": "h2h",
        "1x2": "h2h",
        "h2h": "h2h",
        "101": "h2h",  # OddsPapi public docs use market id 101 for home/draw/away.
        "total": "totals",
        "totals": "totals",
        "over_under": "totals",
        "over/under": "totals",
        "spread": "spreads",
        "spreads": "spreads",
        "handicap": "spreads",
        "asian_handicap": "spreads",
    }
    if key in aliases:
        return aliases[key]
    inferred = _infer_market_key(raw_market or {})
    return inferred or key


def _infer_market_key(raw_market: Mapping[str, Any]) -> str | None:
    blob = str(raw_market).lower()
    if all(token in blob for token in ("home", "away")) and "draw" in blob:
        return "h2h"
    if "over" in blob and "under" in blob:
        return "totals"
    if "handicap" in blob or "spread" in blob or "hdp" in blob:
        return "spreads"
    return None


def valid_decimal_odds(price: Any) -> bool:
    try:
        decimal = float(price)
    except (TypeError, ValueError):
        return False
    return 1.0 < decimal < 1000.0


@dataclass(frozen=True)
class NormalizedOutcome:
    name: str
    price: float
    point: float | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedMarket:
    key: str
    outcomes: tuple[NormalizedOutcome, ...]
    raw_key: str | None = None


@dataclass(frozen=True)
class NormalizedBookmaker:
    key: str
    title: str
    markets: tuple[NormalizedMarket, ...]
    last_update: str | None = None


@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    sport_key: str
    commence_time: str | None
    home_team: str | None
    away_team: str | None
    bookmakers: tuple[NormalizedBookmaker, ...]
    source: str = "oddspapi"

    def as_existing_pipeline_dict(self) -> dict[str, Any]:
        return {
            "id": self.event_id,
            "sport_key": self.sport_key,
            "commence_time": self.commence_time,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "bookmakers": [
                {
                    "key": bookmaker.key,
                    "title": bookmaker.title,
                    "last_update": bookmaker.last_update,
                    "markets": [
                        {
                            "key": market.key,
                            "outcomes": [
                                {
                                    "name": outcome.name,
                                    "price": outcome.price,
                                    **({"point": outcome.point} if outcome.point is not None else {}),
                                }
                                for outcome in market.outcomes
                            ],
                        }
                        for market in bookmaker.markets
                    ],
                }
                for bookmaker in self.bookmakers
            ],
            "_odds_source": self.source,
        }


class OddsPapiClient:
    """Small hardened client around the documented OddsPapi v4 flow."""

    def __init__(self, config: OddspapiConfig, transport: HTTPTransport | None = None) -> None:
        if requests is None and transport is None:
            raise RuntimeError("requests is required unless a transport is injected")
        self.config = config
        self.transport: HTTPTransport = transport or requests.Session()  # type: ignore[union-attr]

    def get_account(self) -> Mapping[str, Any] | list[Any]:
        payload = self._request_json(endpoint=self.config.account_endpoint, params={})
        if isinstance(payload, (Mapping, list)):
            return payload
        raise OddsPapiError("OddsPapi account probe returned unexpected payload type")

    def summarize_account(self, account_payload: Any) -> dict[str, Any]:
        return summarize_account_payload(account_payload)

    def fetch_fixtures(
        self,
        sport: str,
        date_from: str,
        date_to: str,
        bookmaker: str = "superbet.pl",
        *,
        allow_wide_window: bool = False,
    ) -> list[dict[str, Any]]:
        if not allow_wide_window:
            _validate_fixtures_window(date_from, date_to, max_hours=48)
        provider_params: dict[str, Any] = {
            "sportId": self._sport_id_for(sport),
            "from": date_from,
            "to": date_to,
            "statusId": 0,
            "hasOdds": "true",
            "bookmakers": bookmaker,
            "language": "en",
        }
        payload = self._request_json(endpoint=self.config.fixtures_endpoint, params=provider_params)
        return _extract_fixture_list(payload)

    def fetch_fixture_odds(
        self,
        fixture_id: Any,
        bookmaker: str = "superbet.pl",
        *,
        sport: str = "football",
    ) -> list[NormalizedEvent]:
        provider_params: dict[str, Any] = {
            "fixtureId": fixture_id,
            "bookmakers": bookmaker,
            "oddsFormat": "decimal",
            "language": "en",
            "verbosity": 3,
        }
        payload = self._request_json(endpoint=self.config.odds_endpoint, params=provider_params)
        return normalize_oddspapi_payload(payload, sport_key=sport)

    def fetch_odds(
        self,
        *,
        sport: str,
        from_dt: str | None = None,
        to_dt: str | None = None,
        league: str | None = None,
        live: bool | None = None,
        bookmaker: str | None = None,
        max_fixtures: int = 1,
        allow_wide_window: bool = True,
    ) -> list[NormalizedEvent]:
        del league, live
        bookmaker_slug = bookmaker or ",".join(self.config.bookmaker_filter)
        if os.getenv("ODDSPAPI_ENABLE_LEGACY_SPORT_ODDS", "").strip() == "1":
            return self._fetch_legacy_sport_odds(
                sport=sport,
                from_dt=from_dt,
                to_dt=to_dt,
                bookmaker_slug=bookmaker_slug,
            )
        fixtures = self.fetch_fixtures(
            sport,
            str(from_dt or ""),
            str(to_dt or ""),
            bookmaker=bookmaker_slug,
            allow_wide_window=allow_wide_window,
        )
        if not fixtures:
            return []
        normalized: list[NormalizedEvent] = []
        seen_event_ids: set[str] = set()
        for fixture in fixtures[: max(1, max_fixtures)]:
            fixture_id = fixture.get("fixtureId") or fixture.get("id") or fixture.get("eventId")
            if fixture_id in (None, ""):
                continue
            for event in self.fetch_fixture_odds(fixture_id, bookmaker=bookmaker_slug, sport=sport):
                if event.event_id in seen_event_ids:
                    continue
                seen_event_ids.add(event.event_id)
                normalized.append(event)
        return normalized

    def _fetch_legacy_sport_odds(
        self,
        *,
        sport: str,
        from_dt: str | None,
        to_dt: str | None,
        bookmaker_slug: str,
    ) -> list[NormalizedEvent]:
        provider_params: dict[str, Any] = {
            "from": from_dt,
            "to": to_dt,
            "bookmakers": bookmaker_slug,
            "sportsbooks": bookmaker_slug,
            "markets": ",".join(self.config.markets),
            "oddsFormat": "decimal",
        }
        sport_id = SPORT_ID_MAP.get(sport)
        if sport_id:
            provider_params["sportId"] = sport_id
        else:
            provider_params["sport"] = SPORT_SLUG_MAP.get(sport, sport)
        payload = self._request_json(endpoint=self.config.odds_endpoint, params=provider_params)
        return normalize_oddspapi_payload(payload, sport_key=sport)

    def _sport_id_for(self, sport: str) -> str:
        sport_id = SPORT_ID_MAP.get(sport)
        if sport_id:
            return sport_id
        raise ValueError(f"OddsPapi fixtures discovery requires a mapped sportId for sport={sport}")

    def _request_json(self, *, endpoint: str, params: Mapping[str, Any]) -> Any:
        url = f"{self.config.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        clean_params = {key: value for key, value in params.items() if value not in (None, "")}
        headers = {"Accept": "application/json"}
        clean_params["apiKey"] = self.config.api_key
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.transport.get(url, params=clean_params, headers=headers, timeout=self.config.timeout_seconds)
                status = int(getattr(response, "status_code", 0))
                if status in DEFAULT_RETRY_STATUS_CODES and attempt < self.config.max_retries:
                    retry_after = _safe_retry_after(getattr(response, "headers", {}) or {})
                    _sleep_before_retry(attempt, retry_after)
                    continue
                if status >= 400:
                    raise OddsPapiError(f"OddsPapi request failed with HTTP {status}", http_status=status)
                try:
                    return response.json()
                except Exception as exc:  # JSONDecodeError without importing requests internals.
                    raise OddsPapiError("OddsPapi returned non-JSON response") from exc
            except Exception as exc:  # noqa: BLE001 - boundary converts provider errors.
                last_error = exc
                if isinstance(exc, OddsPapiError) and exc.http_status not in DEFAULT_RETRY_STATUS_CODES:
                    break
                if attempt >= self.config.max_retries:
                    break
                _sleep_before_retry(attempt, None)
        if last_error is None:
            raise OddsPapiError("OddsPapi request failed after retries")
        if isinstance(last_error, OddsPapiError):
            raise OddsPapiError(
                _redact_provider_error_message(str(last_error), self.config.api_key),
                http_status=last_error.http_status,
            ) from last_error
        raise OddsPapiError(_redact_provider_error_message(str(last_error), self.config.api_key)) from last_error


def _validate_fixtures_window(date_from: str, date_to: str, *, max_hours: int) -> None:
    start = _parse_iso_datetime(date_from)
    end = _parse_iso_datetime(date_to)
    delta_hours = (end - start).total_seconds() / 3600
    if delta_hours < 0:
        raise ValueError("OddsPapi fixtures discovery requires date_to >= date_from")
    if delta_hours > max_hours:
        raise ValueError(f"OddsPapi fixtures discovery window exceeds {max_hours}h safety limit")


def _parse_iso_datetime(value: str) -> Any:
    text = str(value or "").strip()
    if not text:
        raise ValueError("OddsPapi date window requires non-empty ISO timestamps")
    if "T" not in text:
        text = f"{text}T00:00:00+00:00"
    text = text.replace("Z", "+00:00")
    return __import__("datetime").datetime.fromisoformat(text)


def _extract_fixture_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("data", "fixtures", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
        if any(key in payload for key in ("fixtureId", "id", "eventId")):
            return [dict(payload)]
    raise OddsPapiError("OddsPapi fixtures discovery returned unexpected payload shape")


def summarize_account_payload(account_payload: Any) -> dict[str, Any]:
    request_limit = _find_first_value(account_payload, {"request_limit", "requestlimit", "requests_limit", "requestslimit", "limit"})
    request_count = _find_first_value(account_payload, {"request_count", "requestcount", "requests_count", "requestscount", "count", "used"})
    subscription_count = _count_nested_collection(account_payload, {"subscriptions", "plans"})
    bookmaker_slugs_sample = _collect_sample_strings(
        account_payload,
        target_keys={"bookmakers", "bookmaker", "bookmaker_slug", "bookmakerslug", "bookmaker_name", "bookmakername", "sportsbooks"},
    )
    sport_ids_sample = _collect_sample_integers(
        account_payload,
        target_keys={"sportid", "sport_id", "sportids", "sport_ids", "sports"},
    )
    has_superbet_pl = "superbet.pl" in bookmaker_slugs_sample if bookmaker_slugs_sample else None
    has_sport_10 = 10 in sport_ids_sample if sport_ids_sample else None
    return {
        "current_subscription_active": _coerce_bool(
            _find_first_value(
                account_payload,
                {
                    "current_subscription_active",
                    "currentsubscriptionactive",
                    "subscription_active",
                    "subscriptionactive",
                    "active",
                    "is_active",
                    "isactive",
                },
            )
        ),
        "request_limit": request_limit,
        "request_count": request_count,
        "subscription_count": subscription_count,
        "has_superbet_pl": has_superbet_pl,
        "has_sport_10": has_sport_10,
        "bookmaker_slugs_sample": bookmaker_slugs_sample,
        "sport_ids_sample": sport_ids_sample,
    }


def _find_first_value(payload: Any, target_keys: set[str]) -> Any:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if _normalise_key(key) in target_keys:
                return value
        for value in payload.values():
            nested = _find_first_value(value, target_keys)
            if nested is not None:
                return nested
    elif isinstance(payload, list):
        for item in payload:
            nested = _find_first_value(item, target_keys)
            if nested is not None:
                return nested
    return None


def _count_nested_collection(payload: Any, target_keys: set[str]) -> int | None:
    collection = _find_first_value(payload, target_keys)
    if isinstance(collection, (list, tuple, set)):
        return len(collection)
    if isinstance(collection, Mapping):
        return len(collection)
    return None


def _collect_sample_strings(payload: Any, *, target_keys: set[str], limit: int = 5) -> list[str]:
    values: list[str] = []

    def visit(node: Any, parent_key: str | None = None) -> None:
        if len(values) >= limit:
            return
        if isinstance(node, Mapping):
            for key, value in node.items():
                visit(value, _normalise_key(key))
                if len(values) >= limit:
                    return
        elif isinstance(node, list):
            for item in node:
                visit(item, parent_key)
                if len(values) >= limit:
                    return
        elif parent_key in target_keys:
            text = str(node or "").strip().lower()
            if text and text not in values and re.fullmatch(r"[a-z0-9._-]+", text):
                values.append(text)

    visit(payload)
    return values


def _collect_sample_integers(payload: Any, *, target_keys: set[str], limit: int = 5) -> list[int]:
    values: list[int] = []

    def visit(node: Any, parent_key: str | None = None) -> None:
        if len(values) >= limit:
            return
        if isinstance(node, Mapping):
            for key, value in node.items():
                visit(value, _normalise_key(key))
                if len(values) >= limit:
                    return
        elif isinstance(node, list):
            for item in node:
                visit(item, parent_key)
                if len(values) >= limit:
                    return
        elif parent_key in target_keys:
            try:
                integer = int(node)
            except (TypeError, ValueError):
                return
            if integer not in values:
                values.append(integer)

    visit(payload)
    return values


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "active", "enabled"}:
            return True
        if lowered in {"false", "no", "inactive", "disabled"}:
            return False
    return None


def _redact_provider_error_message(message: str, api_key: str) -> str:
    redacted = message.replace(api_key, REDACTED_TOKEN) if api_key else message
    redacted = re.sub(r"([?&]apiKey=)[^&\s]+", rf"\1{REDACTED_TOKEN}", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"(Bearer\s+)[^\s]+", rf"\1{REDACTED_TOKEN}", redacted, flags=re.IGNORECASE)
    return redacted


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


def normalize_oddspapi_payload(payload: Any, *, sport_key: str) -> list[NormalizedEvent]:
    """Normalize several observed/provider-documented odds response shapes."""
    raw_events = _extract_event_list(payload)
    events: list[NormalizedEvent] = []
    for index, raw in enumerate(raw_events):
        if not isinstance(raw, Mapping):
            continue
        raw_bookmakers = (
            raw.get("bookmakerOdds")
            or raw.get("bookmakers")
            or raw.get("sportsbooks")
            or raw.get("odds")
            or {}
        )
        bookmakers = _parse_bookmakers(raw_bookmakers)
        if not bookmakers:
            continue
        event_id = str(raw.get("fixtureId") or raw.get("id") or raw.get("event_id") or raw.get("eventId") or f"oddspapi:{sport_key}:{index}")
        home, away = _extract_participants(raw)
        event = NormalizedEvent(
            event_id=event_id,
            sport_key=str(raw.get("sport_key") or raw.get("sport") or raw.get("sportId") or sport_key),
            commence_time=raw.get("commence_time") or raw.get("start_time") or raw.get("startTime") or raw.get("date"),
            home_team=raw.get("home_team") or raw.get("home") or raw.get("homeTeam") or home,
            away_team=raw.get("away_team") or raw.get("away") or raw.get("awayTeam") or away,
            bookmakers=tuple(bookmakers),
        )
        events.append(event)
    return events


def _extract_event_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping):
        for key in ("data", "events", "results", "fixtures", "odds"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        # Single event payload.
        if any(key in payload for key in ("bookmakerOdds", "bookmakers", "sportsbooks", "home_team", "homeTeam", "participants")):
            return [payload]
    return []


def _extract_participants(raw: Mapping[str, Any]) -> tuple[str | None, str | None]:
    participants = raw.get("participants")
    if isinstance(participants, Mapping):
        home_raw = participants.get("home") or participants.get("participant1") or participants.get("1")
        away_raw = participants.get("away") or participants.get("participant2") or participants.get("2")
        home = home_raw.get("name") if isinstance(home_raw, Mapping) else home_raw
        away = away_raw.get("name") if isinstance(away_raw, Mapping) else away_raw
        return (str(home) if home else None, str(away) if away else None)
    if isinstance(participants, list) and len(participants) >= 2:
        home = participants[0].get("name") if isinstance(participants[0], Mapping) else participants[0]
        away = participants[1].get("name") if isinstance(participants[1], Mapping) else participants[1]
        return (str(home) if home else None, str(away) if away else None)
    return None, None


def _parse_bookmakers(raw_bookmakers: Any) -> list[NormalizedBookmaker]:
    parsed: list[NormalizedBookmaker] = []
    if isinstance(raw_bookmakers, Mapping):
        iterable = raw_bookmakers.items()
    else:
        iterable = [(None, item) for item in _as_list(raw_bookmakers)]

    for maybe_key, raw in iterable:
        if not isinstance(raw, Mapping):
            continue
        key = _normalise_key(raw.get("key") or raw.get("id") or raw.get("name") or maybe_key)
        title = str(raw.get("title") or raw.get("name") or maybe_key or key)
        last_update = raw.get("last_update") or raw.get("updated_at") or raw.get("lastUpdate") or raw.get("updatedAt")
        raw_markets = raw.get("markets") or raw.get("odds") or raw.get("prices") or raw.get("lines") or {}
        markets = _parse_markets(raw_markets)
        if markets:
            parsed.append(NormalizedBookmaker(key=key, title=title, last_update=last_update, markets=tuple(markets)))
    return parsed


def _parse_markets(raw_markets: Any) -> list[NormalizedMarket]:
    markets: list[NormalizedMarket] = []
    if isinstance(raw_markets, Mapping):
        iterable = raw_markets.items()
    else:
        iterable = [(None, item) for item in _as_list(raw_markets)]

    for maybe_key, raw in iterable:
        if isinstance(raw, Mapping):
            raw_key = str(raw.get("key") or raw.get("name") or raw.get("market") or maybe_key or "")
            raw_outcomes = raw.get("outcomes") or raw.get("prices") or raw.get("odds") or raw.get("selections") or raw
        else:
            raw_key = str(maybe_key or "")
            raw_outcomes = raw
        key = canonical_market_key(raw_key, raw_market=raw if isinstance(raw, Mapping) else None)
        outcomes = _parse_outcomes(raw_outcomes)
        if key and outcomes:
            markets.append(NormalizedMarket(key=key, raw_key=raw_key, outcomes=tuple(outcomes)))
    return markets


def _parse_outcomes(raw_outcomes: Any) -> list[NormalizedOutcome]:
    outcomes: list[NormalizedOutcome] = []
    if isinstance(raw_outcomes, Mapping):
        iterable = raw_outcomes.items()
    else:
        iterable = [(None, item) for item in _as_list(raw_outcomes)]

    for maybe_name, raw in iterable:
        if isinstance(raw, Mapping) and isinstance(raw.get("players"), Mapping):
            outcomes.extend(_parse_player_price_outcomes(maybe_name, raw))
            continue
        if isinstance(raw, Mapping):
            name = str(raw.get("name") or raw.get("label") or raw.get("outcome") or raw.get("bookmakerOutcomeId") or maybe_name or "").strip()
            price = raw.get("price") or raw.get("odds") or raw.get("decimal") or raw.get("value")
            point = raw.get("point") or raw.get("line") or raw.get("handicap") or raw.get("hdp")
        else:
            name = str(maybe_name or "").strip()
            price = raw
            point = None
        if not name or not valid_decimal_odds(price):
            continue
        outcomes.append(
            NormalizedOutcome(
                name=name,
                price=float(price),
                point=float(point) if point not in (None, "") else None,
                raw=raw if isinstance(raw, Mapping) else {},
            )
        )
    return outcomes


def _parse_player_price_outcomes(maybe_name: Any, raw_outcome: Mapping[str, Any]) -> list[NormalizedOutcome]:
    parsed: list[NormalizedOutcome] = []
    players = raw_outcome.get("players")
    if not isinstance(players, Mapping):
        return parsed
    for _player_id, player_raw in players.items():
        if not isinstance(player_raw, Mapping):
            continue
        name = str(
            player_raw.get("playerName")
            or player_raw.get("bookmakerOutcomeId")
            or raw_outcome.get("bookmakerOutcomeId")
            or raw_outcome.get("name")
            or maybe_name
            or ""
        ).strip()
        price = player_raw.get("price") or player_raw.get("odds") or player_raw.get("decimal") or player_raw.get("value")
        point = player_raw.get("point") or player_raw.get("line") or player_raw.get("handicap") or player_raw.get("hdp")
        if not name or not valid_decimal_odds(price):
            continue
        parsed.append(
            NormalizedOutcome(
                name=name,
                price=float(price),
                point=float(point) if point not in (None, "") else None,
                raw=player_raw,
            )
        )
    return parsed
