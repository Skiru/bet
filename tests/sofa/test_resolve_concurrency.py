"""RESOLVE resolves its board through a pool, and the merge stays ordered.

Measured 2026-09-22 against a bridge measured at 8.64 req/s: this stage held
`in_flight 1, pending 0` for ten minutes on a 575-entry board, and SETTLE -
the same shape of loop - ran at 0.094 req/s with a p50 latency of 20,020 ms,
which is the tab's /pull poll window and not the network. One job in flight
means every tab idles between jobs and pays that window to be claimed again.

The dedup here makes order load-bearing in a way SAMPLES' does not: the FIRST
board entry to reach a Sofascore event owns the fixture and the rest are
appended as extra superbet ids.
"""

from __future__ import annotations

import importlib.util
import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.sofa.config import SofaConfig
from bet.sofa.contracts import BoardFixture, GapReason
from bet.sofa.errors import CircuitOpenError, ProviderError
from bet.sofa.stage import current_stage, set_stage

SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "sofa" / "run_resolve.py"


@pytest.fixture(scope="module")
def run_resolve():
    spec = importlib.util.spec_from_file_location("run_resolve_mod", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _board_fixture(n: int) -> BoardFixture:
    return BoardFixture(
        superbet_event_id=f"S{n}",
        sport="football",
        match_name=f"Home{n}·Away{n}",
        side_a=f"Home{n}",
        side_b=f"Away{n}",
        kickoff_utc=datetime(2026, 9, 22, 18, 30, tzinfo=UTC),
        tournament_id=1,
        category_id=1,
    )


def _resolve(run_resolve, board, workers):
    return list(
        run_resolve.resolve_board_concurrently(
            board, None, None, None, SofaConfig(max_concurrency=workers)
        )
    )


def test_order_follows_the_board_not_the_finishing_order(run_resolve, monkeypatch):
    """Which board entry owns a fixture must not depend on the pool.

    The first entry is made the slowest, so a pool yielding in completion
    order would hand ownership - and with it the fixture's first superbet id -
    to a different entry than yesterday's run did.
    """

    def slow_first(bf, *_a, **_k):
        n = int(bf.superbet_event_id[1:])
        time.sleep(0.05 if n == 0 else 0.001)
        return run_resolve.ResolveOutcome(bf, event_id=n, fixture=object())

    monkeypatch.setattr(run_resolve, "_resolve_one", slow_first)
    out = _resolve(run_resolve, [_board_fixture(i) for i in range(6)], 4)
    assert [o.board.superbet_event_id for o in out] == [f"S{i}" for i in range(6)]


def test_the_board_entries_are_actually_in_flight_together(run_resolve, monkeypatch):
    """The defect was not a missing pool but a missing queue depth."""
    lock = threading.Lock()
    in_flight = 0
    peak = 0

    def occupy(bf, *_a, **_k):
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        time.sleep(0.02)
        with lock:
            in_flight -= 1
        return run_resolve.ResolveOutcome(bf)

    monkeypatch.setattr(run_resolve, "_resolve_one", occupy)
    _resolve(run_resolve, [_board_fixture(i) for i in range(9)], 3)
    assert peak == 3


def test_the_stage_reaches_the_worker_threads(run_resolve, monkeypatch):
    """`stage` is a ContextVar, so a fresh thread starts from the default.

    Without propagation every request a worker makes would be billed to stage
    "CLIENT" and the per-stage cost accounting (F8, F22) would stop working
    silently. Driven through the real `_resolve_one`, since that is where the
    handover happens.
    """
    seen: list[str] = []
    lock = threading.Lock()

    class RecordingResolver:
        def resolve_entity(self, *_a, **_k):
            with lock:
                seen.append(current_stage())
            return 1, None, False

    set_stage("RESOLVE")
    out = list(
        run_resolve.resolve_board_concurrently(
            [_board_fixture(i) for i in range(4)],
            RecordingResolver(),
            None,
            None,
            SofaConfig(max_concurrency=4),
        )
    )
    # Two calls per entry: side_a, then the side_b retry.
    assert len(seen) == 8
    assert set(seen) == {"RESOLVE"}
    assert all(o.gap is GapReason.NO_MATCHING_EVENT for o in out)


def test_one_worker_takes_the_sequential_path(run_resolve, monkeypatch):
    """An operator who sets SOFA_MAX_CONCURRENCY=1 gets the old behaviour
    exactly: no pool, no extra thread."""
    threads: set[int] = set()

    def record(bf, *_a, **_k):
        threads.add(threading.get_ident())
        return run_resolve.ResolveOutcome(bf)

    monkeypatch.setattr(run_resolve, "_resolve_one", record)
    out = _resolve(run_resolve, [_board_fixture(i) for i in range(4)], 1)
    assert len(out) == 4
    assert threads == {threading.get_ident()}


def test_a_breaker_trip_is_reported_as_its_own_gap(run_resolve, monkeypatch):
    """CircuitOpenError ends the stage; a ProviderError is one hole in the
    slate. `_resolve_one` must translate both without letting either escape
    into the pool, where it would abort the whole board."""

    class FakeResolver:
        def resolve_entity(self, sport, side, *_a, **_k):
            if side == "Home1":
                raise ProviderError("boom")
            if side == "Home2":
                raise CircuitOpenError("open")
            return 1, None, False

        def match_quality(self, *_a, **_k):  # pragma: no cover - not reached
            return 100.0

    resolver = FakeResolver()
    out = [
        run_resolve._resolve_one(_board_fixture(i), resolver, None, None, "RESOLVE")
        for i in (1, 2, 3)
    ]
    assert (out[0].gap, out[0].circuit_open, out[0].error) == (
        GapReason.PROVIDER_ERROR,
        False,
        "boom",
    )
    assert (out[1].gap, out[1].circuit_open) == (GapReason.PROVIDER_ERROR, True)
    # side_a missed and the side_b retry missed too: no event, not a fault.
    assert (out[2].gap, out[2].circuit_open) == (GapReason.NO_MATCHING_EVENT, False)


def test_two_board_entries_on_one_event_merge_in_board_order(tmp_path, monkeypatch):
    """A2/L12 through the concurrent path: one Sofascore event, two superbet
    ids, and the earlier board entry first in the list."""
    import scripts.sofa.run_resolve as stage
    from bet.sofa.contracts import Fixture

    date_dir = tmp_path / "2026-09-22"
    date_dir.mkdir()
    board = [_board_fixture(i) for i in (1, 2)]
    (date_dir / "01_board.json").write_text(
        json.dumps([b.model_dump(mode="json") for b in board])
    )

    def one_event(fixtures, *_a, **_k):
        # Both entries land on event 77, the second one "first" in time -
        # which the generator must not let change the outcome.
        for bf in fixtures:
            yield stage.ResolveOutcome(
                bf,
                event_id=77,
                fixture=Fixture(
                    sofascore_event_id=77,
                    superbet_event_ids=[bf.superbet_event_id],
                    sport="football",
                    kickoff_utc=datetime(2026, 9, 22, 18, 30, tzinfo=UTC),
                    home_name="Home FC",
                    away_name="Away FC",
                    home_entity_id=1,
                    away_entity_id=2,
                    competition_name="Liga",
                    competition_id=1,
                    season_id=1,
                    category_name="Cat",
                    identity="CONFIRMED",
                    round_number=None,
                    round_name=None,
                    cup_round_type=None,
                    previous_leg_event_id=None,
                    venue_name=None,
                    referee=None,
                    ground_type=None,
                    default_period_count=2,
                ),
            )

    monkeypatch.setattr(stage, "resolve_board_concurrently", one_event)
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("SOFA_DB_PATH", str(tmp_path / "sofa.db"))
    monkeypatch.setattr("sys.argv", ["run_resolve", "--date", "2026-09-22"])

    stage.main()

    out = json.loads((date_dir / "02_fixtures.json").read_text())
    assert len(out) == 1
    assert out[0]["superbet_event_ids"] == ["S1", "S2"]
