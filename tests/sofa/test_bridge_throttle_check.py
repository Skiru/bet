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

@pytest.fixture(scope="module")
def check_bridge():
    spec = importlib.util.spec_from_file_location("check_bridge", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_preflight_does_not_grade_the_burst(check_bridge):
    """A burst from idle cannot see the regime a run works in, so grading it
    cries wolf on a healthy bridge - and CLAUDE.md runs this check first.

    Measured 2026-09-22 on three visible windows: four probes from idle read
    0.10-0.20 req/s on exactly the bridge that then sustained 8.64 req/s over
    360 requests with zero non-200. The rate is reported, never judged; only
    an outright probe FAILURE is a fault.
    """
    import inspect

    src = inspect.getsource(check_bridge.main)
    assert not hasattr(check_bridge, "HEALTHY_BURST_RPS"), (
        "a pass/fail threshold on the idle burst is the bug this removed"
    )
    assert "INFO  bridge served" in src
    assert "burst probes FAILED" in src


def test_the_expected_plateau_is_the_sustained_measurement(check_bridge):
    """The number quoted to the operator must be the saturated one measured
    over 360 requests, reproduced twice within 0.03 req/s - not a burst."""
    assert check_bridge.EXPECTED_PLATEAU_RPS == 8.6


def test_the_probe_stays_tiny(check_bridge):
    """This measures our own latency. It must never grow into a throughput
    test against someone else's production API: two bursts are sent, one
    discarded as the wake-up."""
    assert check_bridge.BURST_SAMPLES <= 6


def test_a_cold_probe_is_given_more_than_one_poll_cycle(check_bridge):
    """The userscript long-polls /pull for 20 s. A first request that lands
    while every tab is mid-poll waits for the next cycle - measured 20.1 s,
    20.1 s and 40.1 s on a bridge that was provably healthy. A timeout at or
    under one cycle turns that into a FAIL, and CLAUDE.md runs this first."""
    assert check_bridge.COLD_PROBE_TIMEOUT_S > 2 * 20.0


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


def test_the_throttled_tab_check_exists_again(check_bridge):
    """Regression guard for the gap that cost 2026-09-22.

    740b5d3f shipped this check at 08:55. 7318e08a removed it two hours later
    while fixing a real and different bug - the preflight was grading the
    *rate* of an idle burst and failing a healthy bridge. The latency grade
    went out with it, so at 10:47 check_bridge.py reported 3/3 OK on tabs that
    were clamped to ~2,000 ms, and the morning was spent finding that by hand.

    The two are not the same measurement and only one of them is safe to
    grade. Rate from idle says nothing; round trip says everything.
    """
    assert check_bridge.HEALTHY_ROUND_TRIP_MS == 600.0


def test_the_round_trip_threshold_separates_the_two_measured_modes(check_bridge):
    """Measured over 80,964 requests: fast p50 175 ms, slow p10 1,889 ms. The
    threshold must sit above the userscript's own 350 ms pacing floor - or a
    healthy back-to-back tab gets called throttled - and below the slow p10."""
    assert 350.0 < check_bridge.HEALTHY_ROUND_TRIP_MS < 1889.0


def test_the_grade_is_the_minimum_not_the_median(check_bridge):
    """BURST_SAMPLES exceeds max_concurrency, so at least one probe always
    queues behind a busy tab and measures the queue rather than the tab. The
    minimum is the only sample guaranteed to have been served immediately.

    Grading a sequential probe is what got this check deleted: a request from
    idle pays the 20 s /pull cycle to be claimed, so it measures the poll
    window and reads as 20,000 ms on a perfectly healthy bridge.
    """
    import inspect

    source = inspect.getsource(check_bridge.main)
    assert "min(latencies_ms)" in source
    assert "statistics.median" not in source
