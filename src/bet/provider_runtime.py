"""Bounded provider execution with explicit non-success states."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class ProviderState(str, Enum):
    SUCCESS = "SUCCESS"
    NO_EVENTS = "NO_EVENTS"
    NO_DATA = "NO_DATA"
    PARTIAL = "PARTIAL"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_BLOCKED = "AUTH_BLOCKED"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    PARSER_ERROR = "PARSER_ERROR"
    SCHEMA_ERROR = "SCHEMA_ERROR"
    STALE_CACHE = "STALE_CACHE"
    TERMS_BLOCKED = "TERMS_BLOCKED"
    UNSUPPORTED = "UNSUPPORTED"
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"


class ProviderFailure(RuntimeError):
    def __init__(self, state: ProviderState, *, retry_after_seconds: float | None = None):
        super().__init__(state.value)
        self.state = state
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class ProviderPolicy:
    connect_timeout_seconds: float = 3.0
    read_timeout_seconds: float = 10.0
    total_timeout_seconds: float = 15.0
    retries: int = 1
    backoff_seconds: float = 0.1

    def __post_init__(self) -> None:
        if min(self.connect_timeout_seconds, self.read_timeout_seconds, self.total_timeout_seconds) <= 0:
            raise ValueError("provider deadlines must be positive")
        if self.retries < 0 or self.retries > 3 or self.backoff_seconds < 0:
            raise ValueError("provider retry policy is out of bounds")

    @property
    def requests_timeout(self) -> tuple[float, float]:
        return (self.connect_timeout_seconds, self.read_timeout_seconds)


@dataclass(frozen=True)
class ProviderResult:
    state: ProviderState
    data: Any = None
    attempts: int = 1
    error_class: str | None = None

    @property
    def success(self) -> bool:
        return self.state in {ProviderState.SUCCESS, ProviderState.NO_EVENTS}


RETRYABLE = {ProviderState.NETWORK_TIMEOUT, ProviderState.RATE_LIMITED}


def execute_provider_call(
    call: Callable[[], Any],
    policy: ProviderPolicy,
    *,
    idempotent: bool = True,
) -> ProviderResult:
    """Execute a provider call under a total deadline; never converts failure to NO_EVENTS."""
    deadline = time.monotonic() + policy.total_timeout_seconds
    for attempt in range(1, policy.retries + 2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return ProviderResult(
                ProviderState.NETWORK_TIMEOUT,
                attempts=attempt,
                error_class="TotalDeadlineExceeded",
            )
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            value = pool.submit(call).result(timeout=remaining)
            if value is None:
                raise ProviderFailure(ProviderState.PARSER_ERROR)
            if isinstance(value, (list, tuple, dict)) and len(value) == 0:
                return ProviderResult(ProviderState.NO_EVENTS, data=value, attempts=attempt)
            return ProviderResult(ProviderState.SUCCESS, data=value, attempts=attempt)
        except FutureTimeout:
            state = ProviderState.NETWORK_TIMEOUT
            error_class = "TotalDeadlineExceeded"
            retry_after = None
        except ProviderFailure as exc:
            state = exc.state
            error_class = exc.__class__.__name__
            retry_after = exc.retry_after_seconds
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            state = ProviderState.PARSER_ERROR
            error_class = exc.__class__.__name__
            retry_after = None
        except Exception as exc:  # Provider adapters normalize library-specific transport exceptions here.
            state = ProviderState.NETWORK_TIMEOUT
            error_class = exc.__class__.__name__
            retry_after = None
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        if state not in RETRYABLE or attempt > policy.retries or not idempotent:
            return ProviderResult(state, attempts=attempt, error_class=error_class)
        backoff = policy.backoff_seconds * (2 ** (attempt - 1))
        delay = min(
            max(backoff, retry_after or 0.0),
            max(0.0, deadline - time.monotonic()),
        )
        if delay:
            time.sleep(delay)
    raise AssertionError("bounded provider loop exhausted unexpectedly")
