"""Transport that routes Sofascore calls through a real browser tab.

Drop-in replacement for `CurlCffiTransport`. Same `Transport` protocol, so
`SofascoreClient` — its token bucket, circuit breaker and logging — is unchanged.

The browser half is `userscripts/sofascore-bridge.user.js`; the queue between
them is `scripts/sofa/bridge_server.py`. See that module for why
direct HTTP cannot work.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bet.sofa.errors import ProviderError

DEFAULT_BRIDGE_URL = "http://127.0.0.1:8787"


class BridgeResponse:
    """Mirrors the slice of the curl_cffi response that the client actually uses."""

    def __init__(self, status_code: int, text: str) -> None:
        self._status_code = status_code
        self._text = text

    @property
    def status_code(self) -> int:
        return self._status_code

    @property
    def text(self) -> str:
        return self._text

    def json(self) -> Any:
        return json.loads(self._text)


class BrowserBridgeTransport:
    def __init__(self, bridge_url: str | None = None) -> None:
        self.bridge_url = (
            bridge_url or os.environ.get("SOFA_BRIDGE_URL") or DEFAULT_BRIDGE_URL
        ).rstrip("/")

    def get(self, url: str, timeout: float = 10.0) -> BridgeResponse:
        # The browser leg adds its own pacing on top of the client's token
        # bucket, so the round trip can outlast the caller's nominal timeout.
        # Give the bridge headroom rather than abandoning jobs it will still run.
        bridge_timeout = max(timeout, 30.0)
        payload = json.dumps({"url": url, "timeout": bridge_timeout}).encode("utf-8")
        req = Request(
            self.bridge_url + "/fetch",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=bridge_timeout + 10.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            # The bridge answered, so it is running. Surface what it said rather
            # than blaming the connection - a 504 here means the browser tab
            # never returned a result, which is a different problem entirely.
            try:
                detail = json.loads(e.read().decode("utf-8")).get("error", "")
            except Exception:
                detail = ""
            raise ProviderError(f"bridge HTTP {e.code}: {detail or e.reason}")
        except URLError as e:
            raise ProviderError(
                f"sofa bridge unreachable at {self.bridge_url} "
                f"(start scripts/sofa/bridge_server.py): {e}"
            )

        if data.get("error"):
            raise ProviderError(f"bridge error: {data['error']}")

        status = data.get("status")
        if not isinstance(status, int):
            raise ProviderError(f"bridge returned no status: {data!r}")

        return BridgeResponse(status, data.get("body") or "")


def make_transport() -> Any:
    """Pick a transport from the environment.

    Defaults to the browser bridge: as of 2026-09-17 direct HTTP is a guaranteed
    403, so making the working path opt-out rather than opt-in keeps callers
    from silently retrying something that cannot succeed.
    """
    mode = os.environ.get("SOFA_TRANSPORT", "bridge").lower()
    if mode == "bridge":
        return BrowserBridgeTransport()
    if mode == "direct":
        from bet.sofa.client import CurlCffiTransport

        return CurlCffiTransport()
    raise ValueError(f"unknown SOFA_TRANSPORT={mode!r} (expected 'bridge' or 'direct')")
