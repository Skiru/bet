"""
Shared resilience utilities for the betting pipeline.

Provides tools for robust HTTP requests, atomic file operations, circuit breaking,
and safe JSON handling.

Examples:
    from bet.resilience import retry, resilient_request, safe_json_load, atomic_json_write

    @retry(max_retries=3, exceptions=(ConnectionError,))
    def fetch_data():
        ...

    result = resilient_request("GET", "https://api.example.com", timeout=10.0)
    if result.success:
        print(result.data)

    data = safe_json_load("config.json", default={"key": "value"})
    atomic_json_write("output.json", data)
"""

import asyncio
import functools
import json
import logging
import os
import random
import signal
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar, cast

import requests

logger = logging.getLogger("bet.resilience")

T = TypeVar("T")


class CircuitOpenError(Exception):
    """Raised when an operation is attempted while the circuit breaker is open."""
    pass


@dataclass
class RequestResult:
    success: bool
    data: Any = None
    status_code: int | None = None
    error: str | None = None
    elapsed_ms: float = 0.0
    headers: dict | None = None


def _calculate_delay(attempt: int, base_delay: float, jitter: bool) -> float:
    """Calculate exponential backoff delay with optional jitter."""
    delay = base_delay * (2 ** attempt)
    if jitter:
        # Add jitter up to 50% of the delay
        delay = delay * random.uniform(0.5, 1.5)
    return delay


def retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    jitter: bool = True,
):
    """
    Retry a function with exponential backoff.
    Works with both synchronous and asynchronous functions.
    """
    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                last_exc = None
                for attempt in range(max_retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as e:
                        last_exc = e
                        if attempt == max_retries:
                            logger.error(f"Async '{func.__name__}' failed after {max_retries} retries: {e}")
                            raise
                        delay = _calculate_delay(attempt, base_delay, jitter)
                        logger.warning(f"Async '{func.__name__}' attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s...")
                        await asyncio.sleep(delay)
                raise last_exc  # Should not be reached
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                last_exc = None
                for attempt in range(max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_exc = e
                        if attempt == max_retries:
                            logger.error(f"Sync '{func.__name__}' failed after {max_retries} retries: {e}")
                            raise
                        delay = _calculate_delay(attempt, base_delay, jitter)
                        logger.warning(f"Sync '{func.__name__}' attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s...")
                        time.sleep(delay)
                raise last_exc  # Should not be reached
            return sync_wrapper
    return decorator


def resilient_request(
    method: str,
    url: str,
    session: requests.Session | None = None,
    max_retries: int = 3,
    base_delay: float = 1.0,
    timeout: float = 15.0,
    jitter: bool = True,
    **kwargs,
) -> RequestResult:
    """
    Perform an HTTP request with built-in retries, timeout, and exception handling.
    """
    start_time = time.perf_counter()
    requester = session.request if session else requests.request
    
    retryable_exceptions = (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.HTTPError,
    )

    last_error_msg = None
    last_status = None

    for attempt in range(max_retries + 1):
        try:
            kwargs.setdefault("timeout", timeout)
            response = requester(method, url, **kwargs)
            
            # Raise HTTPError for bad responses to trigger retry if 5xx
            if response.status_code >= 500:
                response.raise_for_status()

            # Parse JSON if possible, otherwise return text
            try:
                data = response.json()
            except json.JSONDecodeError:
                data = response.text

            elapsed = (time.perf_counter() - start_time) * 1000
            return RequestResult(
                success=response.status_code < 400,
                data=data,
                status_code=response.status_code,
                elapsed_ms=elapsed,
                headers=dict(response.headers),
            )

        except retryable_exceptions as e:
            last_error_msg = str(e)
            if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
                last_status = e.response.status_code
                
            if attempt == max_retries:
                logger.error(f"Request {method} {url} failed after {max_retries} retries: {e}")
                break
                
            delay = _calculate_delay(attempt, base_delay, jitter)
            logger.warning(f"Request {method} {url} failed: {e}. Retrying in {delay:.2f}s...")
            time.sleep(delay)
            
        except Exception as e:
            # Non-retryable exception
            last_error_msg = str(e)
            logger.exception(f"Unexpected error during {method} {url}: {e}")
            break

    elapsed = (time.perf_counter() - start_time) * 1000
    return RequestResult(
        success=False,
        status_code=last_status,
        error=last_error_msg,
        elapsed_ms=elapsed,
    )


def safe_json_load(path_or_str: Path | str, default: Any = None) -> Any:
    """
    Safely load a JSON file or string without raising exceptions.
    Returns `default` on error.
    """
    try:
        # Check if it's potentially a file path
        is_file = False
        try:
            if isinstance(path_or_str, Path) or (os.path.exists(path_or_str) and len(str(path_or_str)) < 1024):
                is_file = True
        except OSError:
            pass

        if is_file:
            with open(path_or_str, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return json.loads(str(path_or_str))
            
    except (json.JSONDecodeError, FileNotFoundError, OSError, UnicodeDecodeError) as e:
        context = str(path_or_str)[:100] + ("..." if len(str(path_or_str)) > 100 else "")
        logger.warning(f"safe_json_load failed: {e} | Context: {context}")
        return default


def atomic_write(path: Path | str, content: str | bytes, encoding: str = 'utf-8') -> None:
    """
    Write content to a file atomically by writing to a temp file and replacing.
    Creates parent directories if they don't exist.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    pid = os.getpid()
    rnd = random.randint(0, 999999)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp-{pid}-{rnd}")
    
    try:
        if isinstance(content, bytes):
            with open(tmp_path, 'wb') as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
        else:
            with open(tmp_path, 'w', encoding=encoding) as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
        
        os.replace(tmp_path, path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def atomic_json_write(path: Path | str, data: Any, indent: int = 2) -> None:
    """
    Write JSON data atomically to a file.
    """
    content = json.dumps(data, indent=indent, default=str, ensure_ascii=False)
    atomic_write(path, content, encoding='utf-8')


class CircuitBreaker:
    """
    A simple thread-safe circuit breaker.
    """
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        
        self.state = self.CLOSED
        self.failures = 0
        self.last_failure_time = 0.0
        
        self._lock = threading.Lock()

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            with self:
                return func(*args, **kwargs)
        return wrapper

    def __enter__(self):
        with self._lock:
            if self.state == self.OPEN:
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = self.HALF_OPEN
                    logger.info("CircuitBreaker transitioned to HALF_OPEN")
                else:
                    raise CircuitOpenError("Circuit is OPEN. Rejecting call.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        with self._lock:
            if exc_type is None:
                if self.state == self.HALF_OPEN:
                    self.state = self.CLOSED
                    self.failures = 0
                    logger.info("CircuitBreaker repaired, transitioned to CLOSED")
                elif self.state == self.CLOSED:
                    self.failures = 0
            else:
                self.failures += 1
                self.last_failure_time = time.time()
                if self.failures >= self.failure_threshold or self.state == self.HALF_OPEN:
                    self.state = self.OPEN
                    logger.warning(f"CircuitBreaker tripped! Transitioned to OPEN after {self.failures} failures.")


class timeout_guard:
    """
    Context manager that raises TimeoutError if execution exceeds `seconds`.
    Uses Unix signals; falls back to a no-op on Windows.
    """
    def __init__(self, seconds: int):
        self.seconds = seconds
        self._old_handler = None
        self._is_unix = sys.platform != "win32"

    def _timeout_handler(self, signum, frame):
        raise TimeoutError("Execution timed out")

    def __enter__(self):
        if self._is_unix and self.seconds > 0:
            self._old_handler = signal.signal(signal.SIGALRM, self._timeout_handler)
            signal.alarm(self.seconds)
        return self

    def __exit__(self, type, value, traceback):
        if self._is_unix and self.seconds > 0:
            signal.alarm(0)
            if self._old_handler is not None:
                signal.signal(signal.SIGALRM, self._old_handler)
