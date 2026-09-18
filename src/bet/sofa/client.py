import json
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import quote

from curl_cffi import requests
from curl_cffi.requests.errors import RequestsError

from bet.sofa.config import SofaConfig
from bet.sofa.errors import CircuitOpenError, ProviderError, TransportError
from bet.sofa.stage import current_stage
from bet.sofa.timeutil import now

logger = logging.getLogger(__name__)


class TransportResponse(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def text(self) -> str: ...

    def json(self) -> Any: ...


class Transport(Protocol):
    def get(self, url: str, timeout: float = 10.0) -> TransportResponse: ...


class CurlCffiTransport:
    def __init__(self) -> None:
        self.session: Any = requests.Session(impersonate="chrome124")
        # These headers match the XHR the Sofascore SPA makes, but be clear about
        # what that buys: since 2026-09-17 this transport gets 403 on every
        # /api/v1/ path regardless of headers, impersonation profile, cookies or
        # IP. Verified against 18 curl_cffi fingerprints and a literal replay of
        # a working browser request. The SPA's x-captcha token carries an `f`
        # claim - a fingerprint of the live connection, recomputed server-side -
        # so no header set reproducible here can pass. Use
        # BrowserBridgeTransport. This class is kept for the day the gate lifts.
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.sofascore.com/",
                "Origin": "https://www.sofascore.com",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site",
            }
        )

    def get(self, url: str, timeout: float = 10.0) -> TransportResponse:
        return self.session.get(url, timeout=timeout)  # type: ignore


class TokenBucket:
    def __init__(self, target_rps: float) -> None:
        self.capacity = 1.0
        self.tokens = 1.0
        self.target_rps = target_rps
        self.last_update = time.monotonic()
        self._lock = threading.Lock()

    def consume(self) -> None:
        with self._lock:
            while True:
                current = time.monotonic()
                elapsed = current - self.last_update
                self.tokens = min(
                    self.capacity, self.tokens + elapsed * self.target_rps
                )
                self.last_update = current

                if self.tokens >= 0.999:
                    self.tokens -= 1.0
                    if self.tokens < 0.0:
                        self.tokens = 0.0
                    return

                sleep_time = (1.0 - self.tokens) / self.target_rps
                time.sleep(max(sleep_time, 0.001))


class CircuitBreaker:
    """Opens after `threshold` consecutive failures, then heals on its own.

    The first version had no way back: once it opened it stayed open for the
    life of the client. That turned any blip - the browser tab reloading to
    mint a fresh x-captcha, which happens roughly hourly by design - into a
    dead client for the rest of a multi-hour run.

    Now an open circuit goes half-open after `cooldown_s` and lets exactly one
    request through to test the water. Success closes it; failure reopens it
    and doubles the wait, capped at `max_cooldown_s`, so a provider that is
    genuinely down is not hammered while a provider that merely hiccuped is
    picked up within seconds.

    `clock` is injectable so the half-open timing can be tested without
    sleeping.
    """

    def __init__(
        self,
        threshold: int,
        cooldown_s: float = 30.0,
        max_cooldown_s: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.threshold = threshold
        self.base_cooldown_s = cooldown_s
        self.max_cooldown_s = max_cooldown_s
        self.failures = 0
        self._clock = clock
        self._lock = threading.Lock()
        self._opened_at: float | None = None
        self._cooldown_s = cooldown_s
        # True while a half-open probe is in flight, so two threads cannot both
        # decide they are the one trial request.
        self._probe_in_flight = False

    def allow(self) -> bool:
        """May a request go out right now? Marks the half-open probe as taken."""
        with self._lock:
            if self._opened_at is None:
                return True
            if self._clock() - self._opened_at < self._cooldown_s:
                return False
            if self._probe_in_flight:
                return False
            self._probe_in_flight = True
            return True

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self._probe_in_flight:
                # The probe failed: reopen, and wait longer next time.
                self._probe_in_flight = False
                self._opened_at = self._clock()
                self._cooldown_s = min(self._cooldown_s * 2, self.max_cooldown_s)
            elif self.failures >= self.threshold and self._opened_at is None:
                self._opened_at = self._clock()

    def record_success(self) -> None:
        with self._lock:
            self.failures = 0
            self._opened_at = None
            self._probe_in_flight = False
            self._cooldown_s = self.base_cooldown_s

    @property
    def is_open(self) -> bool:
        """Whether the circuit is currently refusing traffic.

        False once the cooldown has elapsed, because at that point the next
        caller will be let through as the probe.
        """
        with self._lock:
            if self._opened_at is None:
                return False
            return self._clock() - self._opened_at < self._cooldown_s


class SofascoreClient:
    # See SuperbetClient: a stubbed constructor must still produce a valid
    # log row rather than an AttributeError deep inside _log.
    run_id: str = ""

    def __init__(self, config: SofaConfig, transport: Transport | None = None) -> None:
        self.config = config
        if transport is None:
            from bet.sofa.bridge_transport import make_transport

            transport = make_transport()
        self.transport = transport
        self.bucket = TokenBucket(config.target_rps)
        self.breaker = CircuitBreaker(
            config.breaker_threshold,
            cooldown_s=config.breaker_cooldown_s,
            max_cooldown_s=config.breaker_max_cooldown_s,
        )
        self.log_path = Path(config.runs_dir) / "run.log.jsonl"
        self.run_id = config.run_id
        self._log_lock = threading.Lock()

    def _log(
        self,
        stage: str,
        method: str,
        url: str,
        status: int | None,
        elapsed_ms: int,
        cache_hit: bool,
        breaker_state: str,
    ) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts_utc": now().isoformat().replace("+00:00", "Z"),
            "run_id": self.run_id,
            "stage": stage,
            "method": method,
            "url": url,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "cache_hit": cache_hit,
            "breaker_state": breaker_state,
        }
        with self._log_lock:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")

    def _execute(
        self, url: str, stage: str | None = None, timeout: float = 10.0
    ) -> Any | None:
        # The stage comes from the caller's context, not from the method that
        # happens to build the URL (F22). An explicit argument still wins, for
        # the caller that knows better than its own context.
        stage = stage or current_stage()
        if not self.breaker.allow():
            raise CircuitOpenError("Circuit breaker is open")

        self.bucket.consume()
        start_t = time.monotonic()

        try:
            resp = self.transport.get(url, timeout=timeout)
        except (TransportError, RequestsError):
            # Timeout or connection error -> 1 retry with backoff.
            #
            # This caught only RequestsError, which comes from curl_cffi and so
            # only the direct transport ever raised. The browser bridge has been
            # the only working transport since 2026-09-17 and raised
            # ProviderError for everything, which fell to the catch-all below —
            # so this branch was unreachable and there were no retries at all
            # (F21). Both transports now raise TransportError for a request
            # that did not complete, and that is what gets another try.
            time.sleep(1.0)
            self.bucket.consume()
            start_t = time.monotonic()
            try:
                resp = self.transport.get(url, timeout=timeout)
            except (TransportError, RequestsError) as e:
                self.breaker.record_failure()
                elapsed = int((time.monotonic() - start_t) * 1000)
                state = "OPEN" if self.breaker.is_open else "CLOSED"
                self._log(stage, "GET", url, None, elapsed, False, state)
                raise ProviderError(f"Network error after retry: {e}")
        except Exception as e:
            # Other errors
            self.breaker.record_failure()
            elapsed = int((time.monotonic() - start_t) * 1000)
            state = "OPEN" if self.breaker.is_open else "CLOSED"
            self._log(stage, "GET", url, None, elapsed, False, state)
            raise ProviderError(f"Unexpected error: {e}")

        elapsed = int((time.monotonic() - start_t) * 1000)
        status = resp.status_code

        if status == 404:
            self.breaker.record_success()
            self._log(stage, "GET", url, status, elapsed, False, "CLOSED")
            return None

        if status in (403, 429) or 500 <= status < 600:
            self.breaker.record_failure()
            state = "OPEN" if self.breaker.is_open else "CLOSED"
            self._log(stage, "GET", url, status, elapsed, False, state)
            raise ProviderError(f"HTTP {status}")

        if status == 200:
            try:
                data = resp.json()
            except Exception:
                self.breaker.record_failure()
                state = "OPEN" if self.breaker.is_open else "CLOSED"
                self._log(stage, "GET", url, status, elapsed, False, state)
                raise ProviderError("HTML instead of JSON")

            self.breaker.record_success()
            self._log(stage, "GET", url, status, elapsed, False, "CLOSED")
            return data

        # Unhandled status
        self.breaker.record_failure()
        state = "OPEN" if self.breaker.is_open else "CLOSED"
        self._log(stage, "GET", url, status, elapsed, False, state)
        raise ProviderError(f"Unexpected HTTP {status}")

    def search(self, q: str) -> Any | None:
        # quote() is not optional: team names carry spaces, "&" and non-ASCII,
        # and pasting them raw into the query string silently searches for
        # something else.
        url = "https://api.sofascore.com/api/v1/search/all?q=" + quote(q, safe="")
        return self._execute(url)

    def entity_events(
        self, entity_id: int, kind: Literal["last", "next"], page: int
    ) -> Any | None:
        url = f"https://api.sofascore.com/api/v1/team/{entity_id}/events/{kind}/{page}"
        return self._execute(url)

    def season_events(
        self,
        unique_tournament_id: int,
        season_id: int,
        kind: Literal["last", "next"],
        page: int,
    ) -> Any | None:
        """One page of a season's events. Used by the E10 backfill."""
        url = (
            f"https://api.sofascore.com/api/v1/unique-tournament/"
            f"{unique_tournament_id}/season/{season_id}/events/{kind}/{page}"
        )
        return self._execute(url)

    def event(self, id: int) -> Any | None:
        url = f"https://api.sofascore.com/api/v1/event/{id}"
        return self._execute(url)

    def event_statistics(self, id: int) -> Any | None:
        url = f"https://api.sofascore.com/api/v1/event/{id}/statistics"
        return self._execute(url)

    def event_incidents(self, id: int) -> Any | None:
        url = f"https://api.sofascore.com/api/v1/event/{id}/incidents"
        return self._execute(url)
