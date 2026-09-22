"""SETTLE fetches its events through a pool, and five things must hold.

Measured 2026-09-22: SETTLE ran at 0.094 req/s with p50 latency 20,020 ms
against a bridge measured at 8.64 req/s. 20,020 ms is the tab's /pull poll
window, not network time - the stage asked for one URL at a time, so the
bridge sat at in_flight 1, pending 0 for all 272 requests with zero non-200s.
Nothing was refused; the work never queued deep enough to keep one tab busy.
SAMPLES had the pool, SETTLE did not.
"""

from __future__ import annotations

import importlib.util
import threading
import time
from pathlib import Path

import pytest

from bet.sofa.config import SofaConfig
from bet.sofa.errors import CircuitOpenError, ProviderError
from bet.sofa.stage import current_stage, set_stage

SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "sofa" / "run_settle.py"


@pytest.fixture(scope="module")
def run_settle():
    spec = importlib.util.spec_from_file_location("run_settle", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload(event_id: int):
    return ({"id": event_id}, {}, {})


def _fetch(run_settle, event_ids, workers):
    return list(
        run_settle.fetch_events_concurrently(
            event_ids, None, None, SofaConfig(max_concurrency=workers)
        )
    )


def test_order_follows_the_input_not_the_finishing_order(run_settle, monkeypatch):
    """07_settled.json is read by a human and diffed between runs, so the
    artifact must not depend on which worker finished first."""

    def slow_first(_client, _cache, event_id):
        time.sleep(0.05 if event_id == 0 else 0.001)
        return _payload(event_id)

    monkeypatch.setattr(run_settle, "_event_payload", slow_first)
    out = _fetch(run_settle, list(range(6)), 4)
    assert [f.event_id for f in out] == [0, 1, 2, 3, 4, 5]
    assert all(f.payload is not None and f.reason is None for f in out)


def test_the_events_are_actually_in_flight_together(run_settle, monkeypatch):
    """The defect was not a missing pool but a missing *queue depth*: with one
    job in flight every tab idles and pays a poll cycle. So the property under
    test is concurrent occupancy, not wall-clock."""
    lock = threading.Lock()
    in_flight = 0
    peak = 0

    def occupy(_client, _cache, event_id):
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        time.sleep(0.02)
        with lock:
            in_flight -= 1
        return _payload(event_id)

    monkeypatch.setattr(run_settle, "_event_payload", occupy)
    _fetch(run_settle, list(range(9)), 3)
    assert peak == 3


def test_the_stage_reaches_the_worker_threads(run_settle, monkeypatch):
    """`stage` is a ContextVar, so a fresh thread starts from the default and
    every request a worker made would be billed to stage "CLIENT"."""
    seen: list[str] = []
    lock = threading.Lock()

    def record(_client, _cache, event_id):
        with lock:
            seen.append(current_stage())
        return _payload(event_id)

    monkeypatch.setattr(run_settle, "_event_payload", record)
    set_stage("SETTLE")
    _fetch(run_settle, list(range(4)), 4)
    assert set(seen) == {"SETTLE"}


def test_one_worker_takes_the_sequential_path(run_settle, monkeypatch):
    """An operator who sets SOFA_MAX_CONCURRENCY=1 gets the old behaviour
    exactly: no pool, no extra thread."""
    threads: set[int] = set()

    def record(_client, _cache, event_id):
        threads.add(threading.get_ident())
        return _payload(event_id)

    monkeypatch.setattr(run_settle, "_event_payload", record)
    out = _fetch(run_settle, list(range(4)), 1)
    assert [f.event_id for f in out] == [0, 1, 2, 3]
    assert threads == {threading.get_ident()}


def test_a_breaker_trip_is_reported_as_its_own_thing(run_settle, monkeypatch):
    """CircuitOpenError ends the stage; a plain ProviderError skips one event.

    Collapsing the two is how "the provider refused us" and "one payload was
    malformed" become the same fact about the day.
    """

    def by_id(_client, _cache, event_id):
        if event_id == 1:
            raise ProviderError("boom")
        if event_id == 2:
            raise CircuitOpenError("open")
        if event_id == 3:
            return "NOT_FINISHED"
        return _payload(event_id)

    monkeypatch.setattr(run_settle, "_event_payload", by_id)
    out = _fetch(run_settle, [0, 1, 2, 3], 4)
    assert out[0].payload is not None
    assert (out[1].reason, out[1].circuit_open, out[1].error) == (
        "PROVIDER_ERROR",
        False,
        "boom",
    )
    assert (out[2].reason, out[2].circuit_open) == ("PROVIDER_ERROR", True)
    assert (out[3].reason, out[3].circuit_open) == ("NOT_FINISHED", False)


def test_grading_starts_before_the_last_fetch_lands(run_settle, monkeypatch):
    """The fetch is a generator, and that is the F15 guarantee.

    Materialising every payload first would mean one unexpected exception
    anywhere in the fetch threw away every row already graded - the exact
    defect F15 was raised for, and what
    test_a_crash_partway_keeps_the_rows_already_graded in test_settle_stage
    checks end to end.
    """
    started: list[int] = []
    lock = threading.Lock()

    def record(_client, _cache, event_id):
        with lock:
            started.append(event_id)
        time.sleep(0.01)
        return _payload(event_id)

    monkeypatch.setattr(run_settle, "_event_payload", record)
    stream = run_settle.fetch_events_concurrently(
        list(range(12)), None, None, SofaConfig(max_concurrency=2)
    )
    first = next(stream)
    assert first.event_id == 0
    with lock:
        assert len(started) < 12  # the tail is still unfetched
    stream.close()
