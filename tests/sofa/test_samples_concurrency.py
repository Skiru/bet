"""SAMPLES runs a thread pool, and three things must survive the switch.

`SOFA_MAX_CONCURRENCY` was dead config until 2026-09-22: defined, read from
the environment, asserted in test_config, and referenced by nothing. The
pipeline had no parallelism anywhere. The bridge, meanwhile, has always been
able to serve several tabs at once - `bridge_server.claim()` is not bound to a
tab - so the missing half was here.
"""

from __future__ import annotations

import importlib.util
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture
from bet.sofa.stage import current_stage, set_stage

SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "sofa" / "run_samples.py"


@pytest.fixture(scope="module")
def run_samples():
    spec = importlib.util.spec_from_file_location("run_samples", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture(event_id: int) -> Fixture:
    return Fixture(
        sofascore_event_id=event_id,
        superbet_event_ids=[str(event_id)],
        sport="football",
        kickoff_utc=datetime(2026, 9, 22, 18, 0, tzinfo=UTC),
        home_name="A",
        away_name="B",
        home_entity_id=10,
        away_entity_id=20,
        competition_name="Liga",
        competition_id=1,
        season_id=1,
        category_name="Cat",
        identity="CONFIRMED",
        round_number=1,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type=None,
        default_period_count=None,
    )


def test_order_follows_the_input_not_the_finishing_order(run_samples, monkeypatch):
    """03_samples.json is diffed against the previous run and read by a human.

    The first fixture is made the slowest, so a pool that yielded in
    completion order would put it last.
    """
    fixtures = [_fixture(i) for i in range(6)]

    def slow_first(fixture, *_args, **_kwargs):
        time.sleep(0.05 if fixture.sofascore_event_id == 0 else 0.001)
        return fixture.sofascore_event_id

    monkeypatch.setattr(run_samples, "process_fixture_samples", slow_first)
    out = run_samples.sample_fixtures_concurrently(
        fixtures, None, None, SofaConfig(max_concurrency=4), {}
    )
    assert out == [0, 1, 2, 3, 4, 5]


def test_the_stage_reaches_the_worker_threads(run_samples, monkeypatch):
    """`stage` is a ContextVar, so a fresh thread starts from the default.

    Without propagation every request a worker makes would log stage "CLIENT"
    and the per-stage cost accounting (F8, F22) would stop working silently -
    which is exactly the defect F20 was raised for.
    """
    seen: list[str] = []
    lock = threading.Lock()

    def record(fixture, *_args, **_kwargs):
        with lock:
            seen.append(current_stage())
        return fixture.sofascore_event_id

    monkeypatch.setattr(run_samples, "process_fixture_samples", record)
    set_stage("SAMPLES")
    run_samples.sample_fixtures_concurrently(
        [_fixture(i) for i in range(4)], None, None,
        SofaConfig(max_concurrency=4), {},
    )
    assert set(seen) == {"SAMPLES"}


def test_each_thread_gets_its_own_superbet_client(run_samples, monkeypatch):
    """SuperbetClient wraps a curl_cffi Session, which is not documented
    thread-safe, and the fallback path in SAMPLES does reach it."""
    created: list[object] = []
    lock = threading.Lock()

    class FakeSuperbet:
        def __init__(self) -> None:
            with lock:
                created.append(self)

    monkeypatch.setattr(run_samples, "SuperbetClient", FakeSuperbet)
    monkeypatch.setattr(run_samples._THREAD_LOCAL, "superbet", None, raising=False)

    per_thread: dict[int, object] = {}

    def record(fixture, _client, _cache, superbet, *_a, **_k):
        per_thread[threading.get_ident()] = superbet
        time.sleep(0.01)
        return fixture.sofascore_event_id

    monkeypatch.setattr(run_samples, "process_fixture_samples", record)
    run_samples.sample_fixtures_concurrently(
        [_fixture(i) for i in range(8)], None, None,
        SofaConfig(max_concurrency=4), {},
    )
    # One client per thread that ran, and never one shared between two.
    assert len(set(map(id, per_thread.values()))) == len(per_thread)


def test_one_worker_takes_the_sequential_path(run_samples, monkeypatch):
    """The default is max_concurrency=2, but an operator who sets 1 must get
    the old behaviour exactly, with no pool and no extra thread."""
    threads: set[int] = set()

    def record(fixture, *_args, **_kwargs):
        threads.add(threading.get_ident())
        return fixture.sofascore_event_id

    monkeypatch.setattr(run_samples, "process_fixture_samples", record)
    out = run_samples.sample_fixtures_concurrently(
        [_fixture(i) for i in range(4)], None, None,
        SofaConfig(max_concurrency=1), {},
    )
    assert out == [0, 1, 2, 3]
    assert threads == {threading.get_ident()}
