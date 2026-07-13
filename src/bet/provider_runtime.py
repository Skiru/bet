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
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_ERROR = "AUTH_ERROR"
    PARSE_ERROR = "PARSE_ERROR"
    STALE_CACHE = "STALE_CACHE"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"


class ProviderFailure(RuntimeError):
    def __init__(self, state: ProviderState):
        super().__init__(state.value)
        self.state = state


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


RETRYABLE = {ProviderState.TIMEOUT, ProviderState.RATE_LIMITED, ProviderState.TRANSPORT_ERROR}


def execute_provider_call(call: Callable[[], Any], policy: ProviderPolicy) -> ProviderResult:
    """Execute a provider call under a total deadline; never converts failure to NO_EVENTS."""
    deadline = time.monotonic() + policy.total_timeout_seconds
    for attempt in range(1, policy.retries + 2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return ProviderResult(ProviderState.TIMEOUT, attempts=attempt, error_class="TotalDeadlineExceeded")
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            value = pool.submit(call).result(timeout=remaining)
            if value is None:
                raise ProviderFailure(ProviderState.PARSE_ERROR)
            if isinstance(value, (list, tuple, dict)) and len(value) == 0:
                return ProviderResult(ProviderState.NO_EVENTS, data=value, attempts=attempt)
            return ProviderResult(ProviderState.SUCCESS, data=value, attempts=attempt)
        except FutureTimeout:
            state = ProviderState.TIMEOUT
            error_class = "TotalDeadlineExceeded"
        except ProviderFailure as exc:
            state = exc.state
            error_class = exc.__class__.__name__
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            state = ProviderState.PARSE_ERROR
            error_class = exc.__class__.__name__
        except Exception as exc:  # Provider adapters normalize library-specific transport exceptions here.
            state = ProviderState.TRANSPORT_ERROR
            error_class = exc.__class__.__name__
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        if state not in RETRYABLE or attempt > policy.retries:
            return ProviderResult(state, attempts=attempt, error_class=error_class)
        delay = min(policy.backoff_seconds * (2 ** (attempt - 1)), max(0.0, deadline - time.monotonic()))
        if delay:
            time.sleep(delay)
    raise AssertionError("bounded provider loop exhausted unexpectedly")
