"""Lightweight telemetry wrapper for HTTP and headless requests.

Provides a production-grade instrumentation layer that wraps any
request call (requests, curl_cffi, httpx) with:
- elapsed timing (ms)
- status code capture
- exception classification
- JSONL telemetry logging to betting/data/.telemetry/

This is a first-slice implementation. Full UnifiedTransport (Phase 2)
will replace this with circuit breakers, token-bucket rate limiting,
conditional GET caching, and deterministic SHA-256 keys.
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

TELEMETRY_DIR = (
    Path(__file__).parent.parent.parent.parent / "betting" / "data" / ".telemetry"
)

logger = logging.getLogger(__name__)


@dataclass
class TransportError:
    type: str  # timeout, rate_limit, connection, http, parse, unknown
    message: str
    retryable: bool = False
    backoff_seconds: Optional[float] = None


@dataclass
class TransportResult:
    success: bool
    status_code: Optional[int] = None
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    elapsed_ms: float = 0.0
    retry_count: int = 0
    cache_hit: bool = False
    quota_consumed: int = 0
    error: Optional[TransportError] = None
    telemetry: Dict[str, Any] = field(default_factory=dict)


def _ensure_dir() -> None:
    TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)


def _log_telemetry(record: dict) -> None:
    """Append a single JSON line to today's telemetry file."""
    _ensure_dir()
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = TELEMETRY_DIR / f"telemetry_{today}.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def wrap_request(
    provider: str,
    request_fn,
    url: str,
    method: str = "GET",
    scope_id: str = "",
    idempotency_key: str = "",
    **kwargs,
) -> TransportResult:
    """Wrap a request callable with telemetry.

    request_fn: a callable like requests.get or c_requests.get that accepts
    (url, **kwargs) and returns an object with .status_code, .headers, .content/.text

    Returns a TransportResult with timing and error classification.
    """
    start = time.monotonic()
    error = None
    status_code = None
    headers = {}
    body = b""
    success = False

    try:
        resp = request_fn(url, **kwargs)
        # Normalize response interface (requests vs curl_cffi vs httpx)
        status_code = getattr(resp, "status_code", None)
        headers = dict(getattr(resp, "headers", {}))
        text = getattr(resp, "text", None)
        content = getattr(resp, "content", None)

        # If text is a mock or not a real string/bytes, try to use .json() to
        # reconstruct a serialized body (helps with mocked responses in tests).
        if text is not None and not isinstance(text, (str, bytes)):
            try:
                json_data = resp.json()
                text = json.dumps(json_data)
                content = text.encode("utf-8")
            except Exception:
                pass

        # MagicMock defense: mocked responses often have .text explicitly set
        # while .content defaults to a MagicMock.  Treat any remaining mock as None.
        if content is not None and type(content).__name__ == "MagicMock":
            content = None
        if text is not None and type(text).__name__ == "MagicMock":
            text = None

        # Prefer .content (bytes) then .text (str), with MagicMock already filtered
        if content is not None and isinstance(content, bytes):
            body = content
        elif content is not None and isinstance(content, str):
            body = content.encode("utf-8")
        elif text is not None and isinstance(text, str):
            body = text.encode("utf-8")
        elif text is not None and isinstance(text, bytes):
            body = text
        else:
            body = b""
        success = status_code is not None and 200 <= status_code < 300
    except Exception as exc:
        error = TransportError(
            type=_classify_exception(exc),
            message=str(exc)[:200],
            retryable=_is_retryable(exc),
        )

    elapsed_ms = (time.monotonic() - start) * 1000

    # Build idempotency key from URL+params if not provided
    if not idempotency_key:
        key_input = f"{method}:{url}:{json.dumps(kwargs, sort_keys=True, default=str)}"
        idempotency_key = hashlib.sha256(key_input.encode()).hexdigest()[:32]

    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": provider,
        "scope_id": scope_id,
        "method": method,
        "url": url,
        "status_code": status_code,
        "elapsed_ms": round(elapsed_ms, 2),
        "success": success,
        "error_type": error.type if error else None,
        "error_message": error.message if error else None,
        "retryable": error.retryable if error else None,
        "idempotency_key": idempotency_key,
    }

    # Log silently; never raise on telemetry failure
    try:
        _log_telemetry(record)
    except Exception as e:
        logger.debug("Telemetry logging failed: %s", e)

    return TransportResult(
        success=success,
        status_code=status_code,
        headers=headers,
        body=body,
        elapsed_ms=elapsed_ms,
        error=error,
        telemetry=record,
    )


def _classify_exception(exc: Exception) -> str:
    """Classify an exception into a TransportError type."""
    name = type(exc).__name__
    if "timeout" in name.lower():
        return "timeout"
    if "connection" in name.lower() or "connect" in name.lower():
        return "connection"
    if "rate" in name.lower() or "429" in str(exc):
        return "rate_limit"
    if "http" in name.lower():
        return "http"
    return "unknown"


def _is_retryable(exc: Exception) -> bool:
    """Determine if an exception is likely retryable."""
    name = type(exc).__name__
    if any(k in name.lower() for k in ("timeout", "connection", "connect")):
        return True
    if "429" in str(exc):
        return True
    if "503" in str(exc) or "502" in str(exc) or "504" in str(exc):
        return True
    return False
