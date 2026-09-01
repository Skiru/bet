"""Superbet PL offer client: the prices the operator can actually take.

Why this exists at all
----------------------
Every other price in this pipeline is a *reference*. ``market_context`` collects
bzzoiro's grid of ~88 bookmakers and **none of them is Superbet** -- that was
true when the grid was first wired in and it is still true. So the pipeline
could say "the market thinks 1.36" and be right, while the operator's screen
said 1.40, or said nothing at all because Superbet does not list that line.

Measured on the 2026-08-31 night slate, that gap was not cosmetic:

* Eight of fifteen singles on the coupon were on lines **Superbet does not
  offer**. Not "priced too low" -- absent. The sheet prices
  ``shots_on_target_total`` at 4.5; Superbet's shots-on-target ladder starts at
  7.5. Same for ``shots_total`` 19.5 (Superbet starts at 24.5) and
  ``offsides_total`` 1.5 (starts at 2.5).
* Every ATP US Open fixture was quoted **best-of-five** (sets 3.5/4.5, games
  24.5-46.5) while the stats sheet only ever emits best-of-three lines (sets
  2.5, games 19.5-23.5). Zero overlap, eight fixtures, no bet possible.
* Of 505 (our row x Superbet line) pairs that *did* line up, three cleared the
  minimum-odds bar.

None of that is visible from a reference price. It is only visible by reading
the book the bet is placed into.

The transport, and why it is this one
-------------------------------------
``OddsPapi`` is in ``config/provider_registry.json`` precisely to serve Superbet
PL odds, and on 2026-08-31 its account probe returned **200 with an active
subscription and 0/250 requests used**, while ``/v4/fixtures`` and ``/v4/odds``
both returned **403**. The plan covers the account endpoint and nothing else.
That is a billing state, not an outage, so this module does not try to route
around it -- it reads Superbet's own public offer API, the one superbet.pl's web
client reads, and says so in every artifact it writes.

The host is resolved from superbet.pl's published app config
(``/static/js/fetchConfig/app``) rather than hardcoded folklore: the older
``production-superbet-offer-web`` host answers 500 with "unknown domain" and is
dead. ``SUPERBET_BASE_URL`` overrides it without a code change, because an
offer host is exactly the kind of thing that moves.

What this client does not do
----------------------------
No authentication, no account, no bet placement, no session. It reads the same
public prematch offer any visitor's browser reads. Nothing here can stake
money, and nothing here should ever learn how.
"""
from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

try:  # requests is already in the pipeline's dependency set.
    import requests
except Exception:  # pragma: no cover - surfaced at call time, not import time
    requests = None  # type: ignore[assignment]


# Resolved 2026-08-31 from https://superbet.pl/static/js/fetchConfig/app.
DEFAULT_BASE_URL = "https://production-superbet-offer-pl.freetls.fastly.net"
DEFAULT_LANG = "pl-PL"
DEFAULT_TIMEOUT_SECONDS = 25.0
DEFAULT_MAX_RETRIES = 2
RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

# Superbet's own sport ids. Only these two are read: everything else in the
# by-date feed is esports, virtuals or simulated football (sportId 75 is
# "Real Madryt (Liam) vs Atletico Madryt (Alexis)" -- a FIFA sim, not a match),
# and letting those through would put player-handle fixtures on a betting sheet.
SPORT_IDS = {"football": 5, "tennis": 2}
SPORT_BY_ID = {value: key for key, value in SPORT_IDS.items()}

# The separator Superbet puts between the two sides of ``matchName``. It is
# U+00B7 MIDDLE DOT, not a full stop and not a hyphen, and splitting on the
# wrong character silently yields a one-sided name that matches nothing.
MATCH_NAME_SEPARATOR = "·"

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class SuperbetError(RuntimeError):
    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


class HTTPTransport(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class SuperbetConfig:
    base_url: str = DEFAULT_BASE_URL
    lang: str = DEFAULT_LANG
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES

    @classmethod
    def from_env(cls) -> SuperbetConfig:
        return cls(
            base_url=os.getenv("SUPERBET_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/"),
            lang=os.getenv("SUPERBET_LANG", DEFAULT_LANG).strip() or DEFAULT_LANG,
            timeout_seconds=float(os.getenv("SUPERBET_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))),
            max_retries=max(0, min(int(os.getenv("SUPERBET_MAX_RETRIES", str(DEFAULT_MAX_RETRIES))), 5)),
        )


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def format_window(value: datetime) -> str:
    """The exact shape ``by-date`` wants: ``YYYY-MM-DD HH:MM:SS``, UTC, no zone.

    An ISO-8601 string with a ``T`` and a ``Z`` is accepted by the endpoint and
    then interpreted differently, so the format is pinned here rather than left
    to each caller's ``isoformat()``.
    """
    return _as_utc(value).strftime("%Y-%m-%d %H:%M:%S")


class SuperbetClient:
    """Read-only reader for Superbet PL's public prematch offer."""

    def __init__(
        self,
        config: SuperbetConfig | None = None,
        transport: HTTPTransport | None = None,
    ) -> None:
        self.config = config or SuperbetConfig.from_env()
        self._transport = transport
        self.request_count = 0

    @property
    def transport(self) -> HTTPTransport:
        if self._transport is not None:
            return self._transport
        if requests is None:  # pragma: no cover - dependency guard
            raise SuperbetError("requests is not installed; cannot read the Superbet offer")
        return requests  # type: ignore[return-value]

    # --- HTTP -------------------------------------------------------------

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.config.base_url}{path}"
        headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
        last: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                self.request_count += 1
                response = self.transport.get(
                    url,
                    params=params or {},
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                )
                status = getattr(response, "status_code", 200)
                if status in RETRY_STATUS_CODES and attempt < self.config.max_retries:
                    time.sleep(min(2.0 ** attempt, 4.0) + random.random() * 0.2)
                    continue
                if status >= 400:
                    raise SuperbetError(
                        f"Superbet offer returned HTTP {status} for {path}", http_status=status
                    )
                try:
                    payload = response.json()
                except (ValueError, json.JSONDecodeError) as exc:
                    raise SuperbetError(f"Superbet offer returned non-JSON for {path}") from exc
                if not isinstance(payload, dict):
                    raise SuperbetError(f"Superbet offer returned a non-object body for {path}")
                # The envelope carries its own error flag independently of the
                # HTTP status, so a 200 can still be a refusal.
                if payload.get("error"):
                    raise SuperbetError(f"Superbet offer reported error=true for {path}")
                return payload.get("data")
            except SuperbetError:
                raise
            except Exception as exc:  # network-level
                last = exc
                if attempt >= self.config.max_retries:
                    break
                time.sleep(min(2.0 ** attempt, 4.0) + random.random() * 0.2)
        raise SuperbetError(f"Superbet offer request failed for {path}: {last}")

    # --- endpoints --------------------------------------------------------

    def events_by_date(
        self,
        window_start: datetime,
        window_end: datetime,
        *,
        offer_state: str = "prematch",
    ) -> list[dict[str, Any]]:
        """Every event in a UTC window. One call, and it carries no odds.

        ``marketCount`` on these rows is the count Superbet will *serve*, and it
        is 0 for anything already finished. The odds themselves need one
        ``event_odds`` call each -- there is no bulk odds endpoint, which is why
        the offer step is sized per fixture rather than per day.
        """
        data = self._get_json(
            f"/v2/{self.config.lang}/events/by-date",
            {
                "startDate": format_window(window_start),
                "endDate": format_window(window_end),
                "offerState": offer_state,
            },
        )
        return [row for row in (data or []) if isinstance(row, dict)]

    def event_odds(self, event_id: int | str) -> dict[str, Any] | None:
        """One event with its full ``odds`` list. Returns None when unknown.

        The response is a single-element list, not an object -- the endpoint is
        the collection endpoint filtered to one id, and treating it as an object
        raises on every call.
        """
        data = self._get_json(f"/v2/{self.config.lang}/events/{event_id}")
        if not data:
            return None
        first = data[0] if isinstance(data, list) else data
        return first if isinstance(first, dict) else None


def split_match_name(match_name: str | None) -> tuple[str, str]:
    """``"Remo·Coritiba"`` -> ``("Remo", "Coritiba")``.

    Falls back to a single-sided split rather than raising: an unnamed away side
    still lets the home name participate in matching, and a hard failure here
    would drop a fixture the operator can see on his screen.
    """
    if not match_name:
        return ("", "")
    parts = [part.strip() for part in match_name.split(MATCH_NAME_SEPARATOR)]
    if len(parts) >= 2:
        return (parts[0], parts[1])
    return (parts[0] if parts else "", "")
