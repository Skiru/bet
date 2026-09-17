import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Literal, Protocol

from curl_cffi import requests
from curl_cffi.requests.errors import RequestsError

from bet.sofa.config import SofaConfig
from bet.sofa.errors import CircuitOpenError, ProviderError
from bet.sofa.timeutil import now

logger = logging.getLogger(__name__)

class TransportResponse(Protocol):
    @property
    def status_code(self) -> int:
        ...

    @property
    def text(self) -> str:
        ...

    def json(self) -> Any:
        ...

class Transport(Protocol):
    def get(self, url: str, timeout: float = 10.0) -> TransportResponse:
        ...

class CurlCffiTransport:
    def __init__(self) -> None:
        self.session: Any = requests.Session(impersonate="chrome124")
        self.session.headers.update({"Referer": "https://www.sofascore.com/"})

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
    def __init__(self, threshold: int) -> None:
        self.threshold = threshold
        self.failures = 0
        self._lock = threading.Lock()

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1

    def record_success(self) -> None:
        with self._lock:
            self.failures = 0

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self.failures >= self.threshold

class SofascoreClient:
    def __init__(
        self, config: SofaConfig, transport: Transport | None = None
    ) -> None:
        self.config = config
        self.transport = transport or CurlCffiTransport()
        self.bucket = TokenBucket(config.target_rps)
        self.breaker = CircuitBreaker(config.breaker_threshold)
        self.log_path = Path(config.runs_dir) / "run.log.jsonl"
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
        self, url: str, stage: str = "CLIENT", timeout: float = 10.0
    ) -> Any | None:
        if self.breaker.is_open:
            raise CircuitOpenError("Circuit breaker is open")

        self.bucket.consume()
        start_t = time.monotonic()

        try:
            resp = self.transport.get(url, timeout=timeout)
        except RequestsError:
            # Timeout or connection error -> 1 retry with backoff
            time.sleep(1.0)
            self.bucket.consume()
            start_t = time.monotonic()
            try:
                resp = self.transport.get(url, timeout=timeout)
            except RequestsError as e:
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
        url = f"https://api.sofascore.com/api/v1/search/all?q={q}"
        return self._execute(url, stage="RESOLVE")

    def entity_events(
        self, entity_id: int, kind: Literal["last", "next"], page: int
    ) -> Any | None:
        url = f"https://api.sofascore.com/api/v1/team/{entity_id}/events/{kind}/{page}"
        return self._execute(url, stage="RESOLVE")

    def event(self, id: int) -> Any | None:
        url = f"https://api.sofascore.com/api/v1/event/{id}"
        return self._execute(url, stage="RESOLVE")

    def event_statistics(self, id: int) -> Any | None:
        url = f"https://api.sofascore.com/api/v1/event/{id}/statistics"
        return self._execute(url, stage="SAMPLES")

    def event_incidents(self, id: int) -> Any | None:
        url = f"https://api.sofascore.com/api/v1/event/{id}/incidents"
        return self._execute(url, stage="SAMPLES")

