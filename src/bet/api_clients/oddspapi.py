"""OddsPapi v4 client. Every fact below was verified live on 2026-09-01.

What the API actually is
------------------------
Base ``https://api.oddspapi.io/v4``. Authentication is a **query parameter**,
``?apiKey=``; there is no header form. Reference data (``/sports``,
``/bookmakers``, ``/markets``, ``/tournaments``, ``/languages``) needs no other
parameter. ``/fixtures`` requires ``from`` and ``to`` when only ``sportId`` is
given, and they must be **less than 10 days apart** -- omitting them is a 400
with ``MISSING_PARAMETERS``, not an empty list. ``/odds`` takes **one**
``fixtureId`` (singular); ``fixtureIds`` is rejected. ``/odds-by-tournaments``
is the bulk form and takes ``bookmaker`` plus a comma-separated
``tournamentIds``.

Two error shapes matter and neither is an outage
------------------------------------------------
1. ``403 RESTRICTED_ACCESS`` -- *"Restricted bookmakers: superbet.pl."* This is
   the whole of the "OddsPapi 403s" folklore. ``/fixtures`` and ``/odds`` work
   perfectly; what the free plan does not carry is the **``superbet.pl``
   bookmaker**. The entitled Superbet slugs are ``superbet`` (a clone of
   ``superbet.ro``), ``superbet.ro`` and ``superbet.rs``, which is why
   ``DEFAULT_BOOKMAKERS`` is ``("superbet",)`` and not ``("superbet.pl",)``.
   ``OddsPapiRestrictedError`` carries the slugs so a caller can say which.
2. ``429 RATE_LIMITED`` -- per *endpoint*, roughly one call every two seconds,
   and the wait is in the JSON body as ``retryMs``, not in a ``Retry-After``
   header. ``_EndpointPacer`` spaces calls so this is rarely reached, and the
   retry reads the body when it is.

The quota is small and it is a total, not a rate
------------------------------------------------
``/account`` reports ``plan``, ``request_count`` and ``request_limit`` (free:
250). ``OddsPapiAccount.remaining`` is the number that decides whether an
optional caller should run at all -- see
``bet.simple_stats.superbet_identity``, which reserves a floor rather than
spending the last request on a nice-to-have.

The Superbet relationship, which is the reason this client exists
-----------------------------------------------------------------
``bookmakerOdds["superbet"]["bookmakerFixtureId"]`` **is** the ``eventId`` of
superbet.pl's own public offer feed -- verified identical on fixture
``id1000001872339758`` / event ``13777819``. One Superbet event id space spans
PL/RO/RS. So OddsPapi can name a Superbet fixture exactly, and
``externalProviders.betradarId`` (populated on 100% of soccer fixtures) is the
key that joins it to the PL feed without matching a single team name.

What it is **not** is the price. Measured on West Ham-Wolves, the two feeds
post the *same line ladder* and prices ~0.5-1.5% apart (RO runs a thinner
margin): corners over 9.5 was 1.69 on OddsPapi and 1.68 on superbet.pl. The PL
feed stays the price of record; this client supplies identity, never a quote
the operator is told they can take.

Market ids are a 32,815-row dictionary
--------------------------------------
``/odds`` returns ``markets`` and ``outcomes`` keyed by bare integers.
``/markets`` is the dictionary that decodes them -- ~9 MB, ``marketId ->
{marketName, marketType, handicap, period, playerProp, outcomes[]}`` -- and it
is static enough to cache on disk. ``MarketCatalog`` wraps it and
``decode_bookmaker_odds`` turns a raw ``/odds`` payload into typed rows.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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
SPORTS_ENDPOINT = "/sports"
BOOKMAKERS_ENDPOINT = "/bookmakers"
MARKETS_ENDPOINT = "/markets"
TOURNAMENTS_ENDPOINT = "/tournaments"
ODDS_BY_TOURNAMENTS_ENDPOINT = "/odds-by-tournaments"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_MARKETS = ("h2h", "totals", "spreads")
# ``superbet.pl`` is in the public catalogue and is **not** in the free plan's
# entitlements: asking for it is a 403 RESTRICTED_ACCESS on every odds call,
# which is the whole of the "OddsPapi 403s" story. ``superbet`` is entitled and
# is a clone of ``superbet.ro`` sharing one Superbet-wide event id space, so it
# names the same fixtures at a marginally different price.
DEFAULT_BOOKMAKERS = ("superbet",)
# Every Superbet storefront OddsPapi knows about, in preference order. Used to
# report which one a plan can actually serve rather than guessing.
SUPERBET_BOOKMAKER_SLUGS = ("superbet.pl", "superbet", "superbet.ro", "superbet.rs", "superbet.bet.br")
# ``/fixtures`` rejects a window of 10 days or more outright.
MAX_FIXTURE_WINDOW_DAYS = 10
# The API rate-limits per endpoint and tells you to wait ~1.9s. Pace at 2.1s so
# the common case never spends a request learning that it was too eager.
DEFAULT_MIN_ENDPOINT_INTERVAL_SECONDS = 2.1
REDACTED_TOKEN = "[REDACTED]"

# Verified against a live ``GET /v4/sports`` on 2026-09-01. Ids are stable
# integers; slugs are the same list keyed the other way. Only the sports this
# pipeline reads are named on the left -- the rest are here so a caller that
# passes an OddsPapi slug straight through still resolves.
SPORT_ID_MAP: dict[str, str] = {
    "football": "10",
    "soccer": "10",
    "basketball": "11",
    "tennis": "12",
    "baseball": "13",
    "american-football": "14",
    "ice-hockey": "15",
    "hockey": "15",
    "esport-dota": "16",
    "dota2": "16",
    "esport-counter-strike": "17",
    "cs2": "17",
    "esport-league-of-legends": "18",
    "darts": "19",
    "mma": "20",
    "boxing": "21",
    "handball": "22",
    "volleyball": "23",
    "snooker": "24",
    "table-tennis": "25",
    "rugby": "26",
    "cricket": "27",
}
SPORT_SLUG_MAP: dict[str, str] = {
    "football": "soccer",
    "soccer": "soccer",
    "basketball": "basketball",
    "tennis": "tennis",
    "hockey": "ice-hockey",
    "volleyball": "volleyball",
    "cs2": "esport-counter-strike",
    "dota2": "esport-dota",
    "valorant": "valorant",
}


class HTTPTransport(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...


class OddsPapiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        # OddsPapi's own machine-readable error code, e.g. RESTRICTED_ACCESS,
        # MISSING_PARAMETERS, RATE_LIMITED. Preserved because the HTTP status
        # alone cannot tell "you asked for a bookmaker you do not have" from
        # "this endpoint is not on your plan", and those need different answers.
        self.code = code


class OddsPapiRestrictedError(OddsPapiError):
    """403 RESTRICTED_ACCESS: the *bookmaker* is not on the plan, not the route.

    Carries the slugs the API named so a caller can retry with an entitled one
    instead of concluding the endpoint is dead -- which is exactly the wrong
    conclusion that kept this provider shelved.
    """

    def __init__(self, message: str, *, bookmakers: tuple[str, ...] = ()) -> None:
        super().__init__(message, http_status=403, code="RESTRICTED_ACCESS")
        self.bookmakers = bookmakers


class OddsPapiRateLimited(OddsPapiError):
    """429 RATE_LIMITED. ``retry_seconds`` comes from the body's ``retryMs``."""

    def __init__(self, message: str, *, retry_seconds: float | None = None) -> None:
        super().__init__(message, http_status=429, code="RATE_LIMITED")
        self.retry_seconds = retry_seconds


class OddsPapiQuotaExhausted(OddsPapiError):
    """The plan's total request allowance is spent. Not a rate limit; a wall."""


class _EndpointPacer:
    """Keeps one call per endpoint per ``interval``, in process.

    The limit is per endpoint path, not global, so ``/fixtures`` for football
    and ``/fixtures`` for tennis back-to-back is the case that trips it and two
    different endpoints back-to-back is not.
    """

    def __init__(self, interval: float, sleep=time.sleep, clock=time.monotonic) -> None:
        self.interval = max(0.0, interval)
        self._sleep = sleep
        self._clock = clock
        self._last: dict[str, float] = {}

    def wait(self, endpoint: str) -> None:
        if self.interval <= 0:
            return
        previous = self._last.get(endpoint)
        now = self._clock()
        if previous is not None:
            remaining = self.interval - (now - previous)
            if remaining > 0:
                self._sleep(remaining)
                now = self._clock()
        self._last[endpoint] = now


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
    min_endpoint_interval_seconds: float = DEFAULT_MIN_ENDPOINT_INTERVAL_SECONDS

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
        interval = float(os.getenv(
            "ODDSPAPI_MIN_ENDPOINT_INTERVAL_SECONDS", str(DEFAULT_MIN_ENDPOINT_INTERVAL_SECONDS)
        ))
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
            min_endpoint_interval_seconds=max(0.0, interval),
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


# --- typed views of the three payloads this pipeline reads -----------------
#
# The generic ``summarize_account_payload`` below predates knowing the shape and
# hunts for keys anywhere in the tree. These read the documented shape directly,
# because a quota number found by guessing is worse than no quota number.


@dataclass(frozen=True)
class OddsPapiAccount:
    """``GET /v4/account``, as the fields that decide whether to call again."""

    plan: str
    request_count: int
    request_limit: int
    active: bool
    bookmakers: frozenset[str]
    sport_ids: frozenset[int]
    email: str | None = None
    websocket_access: bool = False

    @property
    def remaining(self) -> int:
        return max(0, self.request_limit - self.request_count)

    def serves(self, bookmaker: str) -> bool:
        return bookmaker.strip().lower() in self.bookmakers

    def first_served(self, candidates: Iterable[str]) -> str | None:
        """The first entitled slug, in the caller's own preference order.

        Preference order matters and is the caller's: ``superbet.pl`` is the
        book the operator actually bets into, so it is asked for first and
        declined first, and only then does ``superbet`` (Romania) stand in.
        """
        for candidate in candidates:
            if self.serves(candidate):
                return candidate.strip().lower()
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan,
            "request_count": self.request_count,
            "request_limit": self.request_limit,
            "remaining": self.remaining,
            "active": self.active,
            "bookmakers": len(self.bookmakers),
            "sport_ids": sorted(self.sport_ids),
            "websocket_access": self.websocket_access,
        }


def parse_account(payload: Any) -> OddsPapiAccount:
    """Read the *current* subscription, not the first one in the list.

    An account can hold an expired subscription alongside a live one, and the
    payload names which is live in ``current_subscription_id``. Falling back to
    ``subscriptions[0]`` would report a lapsed plan's entitlements as though
    they were in force.
    """
    if not isinstance(payload, Mapping):
        raise OddsPapiError("OddsPapi account payload is not an object")
    subscriptions = [item for item in _as_list(payload.get("subscriptions")) if isinstance(item, Mapping)]
    current_id = payload.get("current_subscription_id")
    chosen: Mapping[str, Any] | None = None
    for item in subscriptions:
        if current_id and item.get("subscription_id") == current_id:
            chosen = item
            break
    if chosen is None:
        chosen = next((item for item in subscriptions if item.get("is_active")), None)
    if chosen is None:
        chosen = subscriptions[0] if subscriptions else {}

    raw_bookmakers = chosen.get("bookmakers")
    if isinstance(raw_bookmakers, Mapping):
        bookmakers = frozenset(str(key).strip().lower() for key in raw_bookmakers)
    else:
        bookmakers = frozenset(str(item).strip().lower() for item in _as_list(raw_bookmakers) if item)

    sport_ids: set[int] = set()
    for item in _as_list(chosen.get("sport_ids")):
        try:
            sport_ids.add(int(item))
        except (TypeError, ValueError):
            continue

    return OddsPapiAccount(
        plan=str(chosen.get("plan") or "unknown"),
        request_count=_as_int(chosen.get("request_count"), 0),
        request_limit=_as_int(chosen.get("request_limit"), 0),
        active=bool(chosen.get("is_active", False)),
        bookmakers=bookmakers,
        sport_ids=frozenset(sport_ids),
        email=str(payload.get("email")) if payload.get("email") else None,
        websocket_access=bool(_as_int(chosen.get("websocket_access"), 0)),
    )


@dataclass(frozen=True)
class OddsPapiFixture:
    """One row of ``GET /v4/fixtures``, reduced to what a join needs."""

    fixture_id: str
    sport_id: int
    start_time: datetime | None
    home: str
    away: str
    tournament_id: int | None = None
    tournament_name: str = ""
    category_name: str = ""
    status_id: int | None = None
    status_name: str = ""
    has_odds: bool = False
    # ``externalProviders.betradarId``. Populated on 100% of soccer fixtures in
    # the live sample, and it is the id superbet.pl publishes on every one of
    # its own events, so it joins the two feeds without a name comparison.
    betradar_id: str | None = None
    external_ids: Mapping[str, str] = field(default_factory=dict)


def parse_fixtures(payload: Any) -> list[OddsPapiFixture]:
    parsed: list[OddsPapiFixture] = []
    for raw in _extract_fixture_list(payload):
        fixture_id = str(raw.get("fixtureId") or raw.get("id") or "").strip()
        if not fixture_id:
            continue
        external = raw.get("externalProviders")
        external_ids: dict[str, str] = {}
        if isinstance(external, Mapping):
            external_ids = {
                str(key): str(value)
                for key, value in external.items()
                if value not in (None, "")
            }
        parsed.append(
            OddsPapiFixture(
                fixture_id=fixture_id,
                sport_id=_as_int(raw.get("sportId"), 0),
                start_time=_parse_utc(raw.get("startTime")),
                home=str(raw.get("participant1Name") or "").strip(),
                away=str(raw.get("participant2Name") or "").strip(),
                tournament_id=_as_int(raw.get("tournamentId"), 0) or None,
                tournament_name=str(raw.get("tournamentName") or ""),
                category_name=str(raw.get("categoryName") or ""),
                status_id=None if raw.get("statusId") is None else _as_int(raw.get("statusId"), 0),
                status_name=str(raw.get("statusName") or ""),
                has_odds=bool(raw.get("hasOdds")),
                betradar_id=external_ids.get("betradarId"),
                external_ids=external_ids,
            )
        )
    return parsed


@dataclass(frozen=True)
class MarketDefinition:
    market_id: int
    name: str
    market_type: str
    handicap: float | None
    period: str | None
    player_prop: bool
    sport_id: int
    outcomes: Mapping[int, str]


class MarketCatalog:
    """``GET /v4/markets`` as a lookup. ~33k rows, ~9 MB, effectively static.

    Kept as its own object rather than a dict so a caller can build it from a
    cached file without going near the network -- which is the point, because
    re-downloading nine megabytes to decode one fixture would be the most
    expensive request in the pipeline.
    """

    def __init__(self, definitions: Iterable[MarketDefinition]) -> None:
        self._by_id: dict[int, MarketDefinition] = {item.market_id: item for item in definitions}

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, market_id: Any) -> bool:
        return _as_int(market_id, -1) in self._by_id

    def get(self, market_id: Any) -> MarketDefinition | None:
        return self._by_id.get(_as_int(market_id, -1))

    @classmethod
    def from_payload(cls, payload: Any) -> "MarketCatalog":
        rows = payload if isinstance(payload, list) else _as_list((payload or {}).get("data"))
        definitions: list[MarketDefinition] = []
        for raw in rows:
            if not isinstance(raw, Mapping):
                continue
            market_id = _as_int(raw.get("marketId"), -1)
            if market_id < 0:
                continue
            outcomes: dict[int, str] = {}
            for outcome in _as_list(raw.get("outcomes")):
                if not isinstance(outcome, Mapping):
                    continue
                outcome_id = _as_int(outcome.get("outcomeId"), -1)
                if outcome_id >= 0:
                    outcomes[outcome_id] = str(outcome.get("outcomeName") or "")
            handicap = raw.get("handicap")
            definitions.append(
                MarketDefinition(
                    market_id=market_id,
                    name=str(raw.get("marketName") or ""),
                    market_type=str(raw.get("marketType") or ""),
                    handicap=None if handicap is None else _as_float(handicap),
                    period=str(raw.get("period")) if raw.get("period") else None,
                    player_prop=bool(raw.get("playerProp")),
                    sport_id=_as_int(raw.get("sportId"), 0),
                    outcomes=outcomes,
                )
            )
        return cls(definitions)


@dataclass(frozen=True)
class DecodedOdd:
    """One priced outcome from ``/v4/odds``, with its integer keys resolved."""

    market_id: int
    market_type: str
    market_name: str
    period: str | None
    handicap: float | None
    outcome_id: int
    outcome_name: str
    price: float
    player_name: str | None
    active: bool
    main_line: bool


def decode_bookmaker_odds(
    payload: Any,
    *,
    bookmaker: str,
    catalog: MarketCatalog,
) -> list[DecodedOdd]:
    """``bookmakerOdds -> markets -> outcomes -> players`` into flat typed rows.

    Markets absent from the catalogue are **skipped, not guessed**: an integer
    with no dictionary entry is an unknown market, and inventing a name for it
    is how a woodwork line ends up labelled as shots on target.
    """
    if not isinstance(payload, Mapping):
        return []
    book = (payload.get("bookmakerOdds") or {}).get(bookmaker)
    if not isinstance(book, Mapping):
        return []
    rows: list[DecodedOdd] = []
    for raw_market_id, raw_market in (book.get("markets") or {}).items():
        definition = catalog.get(raw_market_id)
        if definition is None or not isinstance(raw_market, Mapping):
            continue
        for raw_outcome_id, raw_outcome in (raw_market.get("outcomes") or {}).items():
            if not isinstance(raw_outcome, Mapping):
                continue
            outcome_id = _as_int(raw_outcome_id, -1)
            for raw_player in (raw_outcome.get("players") or {}).values():
                if not isinstance(raw_player, Mapping):
                    continue
                price = raw_player.get("price")
                if not valid_decimal_odds(price):
                    continue
                rows.append(
                    DecodedOdd(
                        market_id=definition.market_id,
                        market_type=definition.market_type,
                        market_name=definition.name,
                        period=definition.period,
                        handicap=definition.handicap,
                        outcome_id=outcome_id,
                        outcome_name=definition.outcomes.get(outcome_id, ""),
                        price=float(price),
                        player_name=(str(raw_player.get("playerName")) or None) if raw_player.get("playerName") else None,
                        active=bool(raw_player.get("active", True)),
                        main_line=bool(raw_player.get("mainLine", False)),
                    )
                )
    return rows


def superbet_event_id(payload: Any, *, bookmaker: str) -> str | None:
    """``bookmakerFixtureId`` -- which *is* superbet.pl's own ``eventId``."""
    if not isinstance(payload, Mapping):
        return None
    book = (payload.get("bookmakerOdds") or {}).get(bookmaker)
    if not isinstance(book, Mapping):
        return None
    value = book.get("bookmakerFixtureId")
    return str(value) if value not in (None, "") else None


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class OddsPapiClient:
    """Small hardened client around the documented OddsPapi v4 flow."""

    def __init__(
        self,
        config: OddspapiConfig | None = None,
        transport: HTTPTransport | None = None,
        *,
        pacer: _EndpointPacer | None = None,
    ) -> None:
        if requests is None and transport is None:
            raise RuntimeError("requests is required unless a transport is injected")
        self.config = config or OddspapiConfig.from_env()
        self.transport: HTTPTransport = transport or requests.Session()  # type: ignore[union-attr]
        self._pacer = pacer or _EndpointPacer(self.config.min_endpoint_interval_seconds)
        # Requests this client has actually sent. The server's own
        # ``request_count`` lags and costs a request to read, so a caller that
        # needs to bound its spend within one run reads this instead.
        self.request_count = 0

    def get_account(self) -> Mapping[str, Any] | list[Any]:
        payload = self._request_json(endpoint=self.config.account_endpoint, params={})
        if isinstance(payload, (Mapping, list)):
            return payload
        raise OddsPapiError("OddsPapi account probe returned unexpected payload type")

    def account(self) -> OddsPapiAccount:
        """The typed account: plan, quota, entitled bookmakers. One request."""
        return parse_account(self.get_account())

    def summarize_account(self, account_payload: Any) -> dict[str, Any]:
        return summarize_account_payload(account_payload)

    # --- reference data ----------------------------------------------------

    def list_sports(self) -> list[dict[str, Any]]:
        return _as_list(self._request_json(endpoint=SPORTS_ENDPOINT, params={}))

    def list_bookmakers(self) -> list[dict[str, Any]]:
        return _as_list(self._request_json(endpoint=BOOKMAKERS_ENDPOINT, params={}))

    def list_tournaments(self, sport: str) -> list[dict[str, Any]]:
        return _as_list(
            self._request_json(
                endpoint=TOURNAMENTS_ENDPOINT, params={"sportId": self._sport_id_for(sport)}
            )
        )

    def market_catalog(self) -> MarketCatalog:
        """The market dictionary. ~9 MB -- fetch once and cache it on disk."""
        return MarketCatalog.from_payload(self._request_json(endpoint=MARKETS_ENDPOINT, params={}))

    # --- fixtures and odds -------------------------------------------------

    def fixtures(
        self,
        sport: str,
        start: datetime,
        end: datetime,
        *,
        only_prematch: bool = True,
        only_with_odds: bool = True,
    ) -> list[OddsPapiFixture]:
        """Typed fixtures for one sport over one window. **One request.**

        The window is required by the API and must be under ten days; passing a
        wider one is a 400, so it is refused here with a message that says which
        limit was hit rather than letting the provider phrase it.
        """
        if end < start:
            raise ValueError("OddsPapi fixtures window requires end >= start")
        if (end - start) >= timedelta(days=MAX_FIXTURE_WINDOW_DAYS):
            raise ValueError(
                f"OddsPapi /fixtures rejects a window of {MAX_FIXTURE_WINDOW_DAYS} days or more"
            )
        params: dict[str, Any] = {
            "sportId": self._sport_id_for(sport),
            "from": _iso_z(start),
            "to": _iso_z(end),
        }
        if only_prematch:
            params["statusId"] = 0
        if only_with_odds:
            params["hasOdds"] = "true"
        return parse_fixtures(self._request_json(endpoint=self.config.fixtures_endpoint, params=params))

    def odds_for_fixture(self, fixture_id: str, *, bookmaker: str | None = None) -> dict[str, Any]:
        """Raw ``/v4/odds`` for one fixture. ``fixtureId`` is singular by design.

        Returned raw rather than normalised because the integer market keys are
        only meaningful next to a ``MarketCatalog``, and forcing a 9 MB download
        on every odds call to hide that would be the wrong trade.
        """
        payload = self._request_json(
            endpoint=self.config.odds_endpoint,
            params={
                "fixtureId": fixture_id,
                "bookmaker": bookmaker or ",".join(self.config.bookmaker_filter),
                "oddsFormat": "decimal",
            },
        )
        return dict(payload) if isinstance(payload, Mapping) else {}

    def odds_by_tournaments(
        self, tournament_ids: Iterable[Any], *, bookmaker: str | None = None
    ) -> list[dict[str, Any]]:
        """The bulk form: many tournaments, one request. Both params required."""
        ids = [str(item).strip() for item in tournament_ids if str(item).strip()]
        if not ids:
            return []
        return _as_list(
            self._request_json(
                endpoint=ODDS_BY_TOURNAMENTS_ENDPOINT,
                params={
                    "bookmaker": bookmaker or ",".join(self.config.bookmaker_filter),
                    "tournamentIds": ",".join(ids),
                    "oddsFormat": "decimal",
                },
            )
        )

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
        sport_id = SPORT_ID_MAP.get(str(sport).strip().lower())
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
                self._pacer.wait(endpoint)
                response = self.transport.get(url, params=clean_params, headers=headers, timeout=self.config.timeout_seconds)
                self.request_count += 1
                status = int(getattr(response, "status_code", 0))
                if status >= 400:
                    error = _error_from_response(response, status)
                    # A restriction and a bad parameter are permanent: retrying
                    # them spends quota to be told the same thing again.
                    if status in DEFAULT_RETRY_STATUS_CODES and attempt < self.config.max_retries:
                        wait = getattr(error, "retry_seconds", None)
                        if wait is None:
                            wait = _safe_retry_after(getattr(response, "headers", {}) or {})
                        _sleep_before_retry(attempt, wait)
                        last_error = error
                        continue
                    raise error
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
        raise _redacted(last_error, self.config.api_key) from last_error


def _iso_z(value: datetime) -> str:
    moment = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _error_body(response: Any) -> Mapping[str, Any]:
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001 - an unparseable error body is still an error
        return {}
    if isinstance(payload, Mapping) and isinstance(payload.get("error"), Mapping):
        return payload["error"]
    return payload if isinstance(payload, Mapping) else {}


# Non-greedy, and terminated on a period *followed by whitespace* rather than
# on any period at all: the slugs are domains, so "superbet.pl. You do not have
# access" would otherwise yield "superbet".
_RESTRICTED_RE = re.compile(r"restricted bookmakers?:\s*(.+?)(?:\.\s|\.?$)", re.IGNORECASE)


def _error_from_response(response: Any, status: int) -> OddsPapiError:
    """Turn an HTTP error into the *specific* error, using OddsPapi's own code.

    The distinction that matters: ``403 RESTRICTED_ACCESS`` names a bookmaker
    the plan does not carry and says nothing about the endpoint. Reading it as
    "``/v4/odds`` is not on this plan" is what shelved the provider for a month.
    """
    body = _error_body(response)
    code = str(body.get("code") or "").strip().upper() or None
    message = str(body.get("message") or f"OddsPapi request failed with HTTP {status}").strip()
    details = str(body.get("details") or "").strip()
    full = f"{message} {details}".strip()

    if code == "RESTRICTED_ACCESS" or (status == 403 and "restricted bookmaker" in full.lower()):
        found = _RESTRICTED_RE.search(full)
        slugs = tuple(
            part.strip().lower()
            for part in (found.group(1).split(",") if found else [])
            if part.strip()
        )
        return OddsPapiRestrictedError(f"OddsPapi 403 RESTRICTED_ACCESS: {full}", bookmakers=slugs)
    if code == "RATE_LIMITED" or status == 429:
        retry_ms = body.get("retryMs")
        retry_seconds: float | None
        try:
            retry_seconds = max(0.0, min(float(retry_ms) / 1000.0, 30.0))
        except (TypeError, ValueError):
            retry_seconds = None
        return OddsPapiRateLimited(f"OddsPapi 429 RATE_LIMITED: {full}", retry_seconds=retry_seconds)
    if code in {"QUOTA_EXCEEDED", "REQUEST_LIMIT_REACHED"} or "request limit" in full.lower():
        return OddsPapiQuotaExhausted(f"OddsPapi quota exhausted: {full}", http_status=status, code=code)
    return OddsPapiError(f"OddsPapi HTTP {status}: {full}", http_status=status, code=code)


def _redacted(error: Exception, api_key: str) -> OddsPapiError:
    """Re-raise as the same class, with the key scrubbed from the message."""
    message = _redact_provider_error_message(str(error), api_key)
    if isinstance(error, OddsPapiRestrictedError):
        return OddsPapiRestrictedError(message, bookmakers=error.bookmakers)
    if isinstance(error, OddsPapiRateLimited):
        return OddsPapiRateLimited(message, retry_seconds=error.retry_seconds)
    if isinstance(error, OddsPapiQuotaExhausted):
        return OddsPapiQuotaExhausted(message, http_status=error.http_status, code=error.code)
    if isinstance(error, OddsPapiError):
        return OddsPapiError(message, http_status=error.http_status, code=error.code)
    return OddsPapiError(message)


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
    # The two entitlement questions are answered from the *whole* subscription,
    # not from the five-slug sample above. ``bookmaker_slugs_sample`` is a
    # human-readable excerpt for a healthcheck report; asking "is superbet.pl in
    # the first five of 388 slugs" answers a different question and answers it
    # wrong. Falls back to the sample only when the payload has no recognisable
    # subscription at all, so a caller handed something unexpected still gets a
    # best effort rather than a confident None.
    try:
        parsed = parse_account(account_payload)
    except OddsPapiError:
        parsed = None
    if parsed is not None and parsed.bookmakers:
        has_superbet_pl = parsed.serves("superbet.pl")
        usable_superbet_slug = parsed.first_served(SUPERBET_BOOKMAKER_SLUGS)
    else:
        has_superbet_pl = "superbet.pl" in bookmaker_slugs_sample if bookmaker_slugs_sample else None
        usable_superbet_slug = next(
            (slug for slug in SUPERBET_BOOKMAKER_SLUGS if slug in bookmaker_slugs_sample), None
        )
    if parsed is not None and parsed.sport_ids:
        has_sport_10 = 10 in parsed.sport_ids
    else:
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
        # The Superbet storefront this plan *can* serve, if any. Without it a
        # report says "no superbet.pl" and stops, which reads as "no Superbet
        # data" when in fact ``superbet`` (the superbet.ro clone) is available
        # and shares the same event ids.
        "usable_superbet_slug": usable_superbet_slug,
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
