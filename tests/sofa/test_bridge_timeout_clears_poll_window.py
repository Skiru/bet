"""Our own deadline must not kill a job the bridge would still have served.

`bridge_server` holds a /fetch open for exactly the timeout the client sends
(bridge_server.py:242), and a tab can only take work while it is inside
/pull, which blocks for PULL_WAIT_S. A floor below one poll window therefore
produces a 504 that we caused, on a bridge with nothing wrong with it.

Measured 2026-09-22: six concurrent jobs completed in two groups of three,
0.35 s apart - 10.7 req/s, all 200 - while the sustained ramp through this
transport aborted at a target of 4 on exactly that 504. Single requests from
idle took 20.1 s, 20.1 s and 40.1 s: one and two poll cycles.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from bet.sofa.bridge_transport import BrowserBridgeTransport

BRIDGE_SERVER = (
    Path(__file__).parent.parent.parent / "scripts" / "sofa" / "bridge_server.py"
)


@pytest.fixture(scope="module")
def bridge_server():
    spec = importlib.util.spec_from_file_location("bridge_server", BRIDGE_SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _floor_used(monkeypatch) -> float:
    """The timeout the transport actually puts on the wire for a short call."""
    seen: dict[str, float] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def read(self):
            return b'{"status": 200, "body": "{}", "headers": {}}'

    def fake_urlopen(req, timeout=None):
        seen["payload"] = float(__import__("json").loads(req.data)["timeout"])
        return FakeResponse()

    monkeypatch.setattr("bet.sofa.bridge_transport.urlopen", fake_urlopen)
    BrowserBridgeTransport().get("https://api.sofascore.com/api/v1/x", timeout=10.0)
    return seen["payload"]


def test_the_floor_clears_one_poll_window(bridge_server, monkeypatch):
    assert _floor_used(monkeypatch) > bridge_server.PULL_WAIT_S


def test_the_floor_clears_two_poll_windows(bridge_server, monkeypatch):
    """Both observed cold waits were whole cycles, and one was two of them."""
    assert _floor_used(monkeypatch) >= 2 * bridge_server.PULL_WAIT_S


def test_the_floor_stays_inside_the_servers_own_job_timeout(
    bridge_server, monkeypatch
):
    """Past JOB_TIMEOUT_S the server abandons the job anyway, so waiting
    longer than that buys nothing and only delays the retry."""
    assert _floor_used(monkeypatch) <= bridge_server.JOB_TIMEOUT_S
