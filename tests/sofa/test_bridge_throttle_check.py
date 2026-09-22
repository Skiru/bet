"""The preflight must be able to see a browser-throttled tab.

A tab the browser has throttled answers the *same routes* ~11x slower, and
until this check existed the only symptom was a run that took four times as
long with nothing in the log saying why. One overnight run paid the slow mode
on 10,544 requests - about 5.3 hours.

Measured on runs/sofa/run.log.jsonl:
  fast mode  p50   175 ms,  p99  ~250 ms   (15,949 requests)
  slow mode  p10 1,889 ms,  p50 1,997 ms   (10,544 requests)

Confirmed to be our side, not Sofascore and not the clock: hour 21 UTC holds
both modes on different runs (161 ms and 1,997 ms) over identical routes.
"""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "sofa" / "check_bridge.py"

FAST_MODE_P99_MS = 250.0
SLOW_MODE_P10_MS = 1889.0


@pytest.fixture(scope="module")
def check_bridge():
    spec = importlib.util.spec_from_file_location("check_bridge", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_threshold_separates_the_two_measured_modes(check_bridge):
    """A threshold inside either mode is worse than none: it would fire on
    ordinary variance, or never fire at all."""
    assert FAST_MODE_P99_MS < check_bridge.HEALTHY_ROUND_TRIP_MS < SLOW_MODE_P10_MS


def test_threshold_clears_the_userscript_floor(check_bridge):
    """Back-to-back probes are paced by MIN_INTERVAL_MS = 350 in the
    userscript, so a threshold at or below 350 ms would call a perfectly
    healthy tab throttled. Measured live 2026-09-22: 349 ms."""
    assert check_bridge.HEALTHY_ROUND_TRIP_MS > 350.0


def test_the_probe_stays_tiny(check_bridge):
    """This measures our own latency. It must never grow into a throughput
    test against someone else's production API."""
    assert check_bridge.LATENCY_SAMPLES <= 5


def test_a_transport_failure_is_diagnosed_not_raised(check_bridge, monkeypatch, capsys):
    """A 504 from the bridge must print a diagnosis and return 1, not raise.

    A tab Chrome has put into intensive throttling takes ~40 s to claim a job.
    The bridge then answers 504 and `bridge_transport.get` raises
    TransportError - which is not a ProviderError, so this preflight died with
    a stack trace instead of the one sentence it exists to print. Observed
    live 2026-09-22 straight after a capacity ramp.
    """
    import contextlib
    import json

    from bet.sofa.errors import TransportError

    class FakeHealth:
        def read(self):
            return json.dumps({"ok": True, "last_pull_age_s": 5.0}).encode()

    @contextlib.contextmanager
    def fake_urlopen(*_a, **_k):
        yield FakeHealth()

    class Throttled:
        def get(self, *_a, **_k):
            raise TransportError("bridge HTTP 504: bridge timeout")

    monkeypatch.setattr(check_bridge, "urlopen", fake_urlopen)
    monkeypatch.setattr(check_bridge, "BrowserBridgeTransport", lambda: Throttled())
    monkeypatch.setattr(check_bridge.sys, "argv", ["check_bridge.py"])

    rc = check_bridge.main()

    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out
    assert "504" in out
