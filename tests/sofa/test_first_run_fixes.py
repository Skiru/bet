"""Tests for the defects found during the first live run (FIRST_RUN_FINDINGS.md).

Each test names the finding it pins. They are written to fail against the code
as it stood before the fix, not merely to exercise the new code path.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from bet.sofa.cache import SofaCache
from bet.sofa.client import CircuitBreaker, SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.db import migrate
from bet.sofa.errors import CircuitOpenError


class FakeClock:
    """A clock the test moves by hand, so half-open timing needs no sleeping."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


# --------------------------------------------------------------------------
# F1 — the breaker must be able to close again
# --------------------------------------------------------------------------


def test_f1_breaker_reopens_traffic_after_cooldown() -> None:
    """The original breaker stayed open forever; this is the regression."""
    clock = FakeClock()
    breaker = CircuitBreaker(threshold=3, cooldown_s=30.0, clock=clock)

    for _ in range(3):
        breaker.record_failure()

    assert breaker.is_open
    assert not breaker.allow(), "still inside the cooldown"

    clock.advance(29.0)
    assert not breaker.allow(), "cooldown has not elapsed yet"

    clock.advance(2.0)
    assert breaker.allow(), "after the cooldown one probe must get through"


def test_f1_successful_probe_closes_the_circuit() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(threshold=2, cooldown_s=10.0, clock=clock)
    breaker.record_failure()
    breaker.record_failure()
    clock.advance(11.0)

    assert breaker.allow()
    breaker.record_success()

    assert not breaker.is_open
    assert breaker.failures == 0
    # Fully closed: traffic flows without waiting for another cooldown.
    assert breaker.allow()
    assert breaker.allow()


def test_f1_only_one_probe_is_let_through() -> None:
    """Two callers in the half-open window must not both count as the probe."""
    clock = FakeClock()
    breaker = CircuitBreaker(threshold=1, cooldown_s=10.0, clock=clock)
    breaker.record_failure()
    clock.advance(11.0)

    assert breaker.allow()
    assert not breaker.allow(), "the probe was already taken"


def test_f1_failed_probe_reopens_and_backs_off() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(
        threshold=1, cooldown_s=10.0, max_cooldown_s=40.0, clock=clock
    )
    breaker.record_failure()

    clock.advance(11.0)
    assert breaker.allow()
    breaker.record_failure()  # probe failed -> reopen, cooldown doubles to 20

    clock.advance(11.0)
    assert not breaker.allow(), "cooldown should have doubled to 20s"
    clock.advance(10.0)
    assert breaker.allow()

    breaker.record_failure()  # -> 40s
    clock.advance(30.0)
    assert not breaker.allow()
    clock.advance(11.0)
    assert breaker.allow()

    breaker.record_failure()  # capped at max_cooldown_s, not 80
    clock.advance(41.0)
    assert breaker.allow(), "cooldown must be capped at max_cooldown_s"


def test_f1_client_recovers_after_cooldown(tmp_path: Any) -> None:
    """End to end through the client: a blip must not kill it for good."""

    class FlakyTransport:
        def __init__(self) -> None:
            self.calls = 0
            self.fail_until = 3

        def get(self, url: str, timeout: float = 10.0) -> Any:
            self.calls += 1
            if self.calls <= self.fail_until:
                raise RuntimeError("bridge down")

            class Resp:
                status_code = 200
                text = '{"ok": true}'

                def json(self) -> Any:
                    return {"ok": True}

            return Resp()

    clock = FakeClock()
    config = SofaConfig(
        runs_dir=str(tmp_path),
        target_rps=1000,
        breaker_threshold=3,
        breaker_cooldown_s=30,
    )
    transport = FlakyTransport()
    client = SofascoreClient(config, transport=transport)
    client.breaker = CircuitBreaker(threshold=3, cooldown_s=30.0, clock=clock)

    for _ in range(3):
        with pytest.raises(Exception):
            client.event(1)

    with pytest.raises(CircuitOpenError):
        client.event(1)
    calls_while_open = transport.calls

    clock.advance(31.0)
    assert client.event(1) == {"ok": True}
    assert transport.calls == calls_while_open + 1, "the probe reached the transport"

    # And the circuit is closed now, so normal traffic resumes.
    assert client.event(2) == {"ok": True}


# --------------------------------------------------------------------------
# F4 — a name that resolves to nothing must be remembered
# --------------------------------------------------------------------------


@pytest.fixture
def cache(tmp_path: Any) -> SofaCache:
    db_path = str(tmp_path / "sofa.db")
    migrate(db_path)
    return SofaCache(SofaConfig(db_path=db_path, runs_dir=str(tmp_path)))


def test_f4_miss_is_remembered(cache: SofaCache) -> None:
    assert cache.get_entity_miss("football", "nonexistent fc") is False
    cache.save_entity_miss("football", "nonexistent fc")
    assert cache.get_entity_miss("football", "nonexistent fc") is True


def test_f4_miss_is_scoped_to_sport_and_name(cache: SofaCache) -> None:
    cache.save_entity_miss("football", "dynamo")
    assert cache.get_entity_miss("tennis", "dynamo") is False
    assert cache.get_entity_miss("football", "other") is False


def test_f4_miss_expires(tmp_path: Any) -> None:
    """A team Sofascore adds later must eventually be looked up again."""
    db_path = str(tmp_path / "sofa.db")
    migrate(db_path)
    config = SofaConfig(
        db_path=db_path, runs_dir=str(tmp_path), entity_miss_ttl_min=60
    )
    cache = SofaCache(config)
    cache.save_entity_miss("football", "newly added fc")
    assert cache.get_entity_miss("football", "newly added fc") is True

    stale = (datetime.now(UTC) - timedelta(minutes=61)).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE sofa_entity_miss SET missed_at = ?", (stale,))
        conn.commit()

    assert cache.get_entity_miss("football", "newly added fc") is False


def test_f4_miss_is_cleared_when_the_name_resolves(cache: SofaCache) -> None:
    cache.save_entity_miss("football", "promoted fc")
    assert cache.get_entity_miss("football", "promoted fc") is True
    cache.clear_entity_miss("football", "promoted fc")
    assert cache.get_entity_miss("football", "promoted fc") is False


def test_f4_resolver_skips_the_network_for_a_known_miss(tmp_path: Any) -> None:
    """The point of the fix: a cached miss must cost zero requests."""
    from bet.sofa.resolve import SofaResolver

    db_path = str(tmp_path / "sofa.db")
    migrate(db_path)
    config = SofaConfig(db_path=db_path, runs_dir=str(tmp_path))
    cache = SofaCache(config)

    class CountingClient:
        def __init__(self) -> None:
            self.searches = 0

        def search(self, q: str) -> Any:
            self.searches += 1
            return {"results": []}

        def entity_events(self, *a: Any, **k: Any) -> Any:
            raise AssertionError("must not be called for a known miss")

    client = CountingClient()
    resolver = SofaResolver(config, client, cache)  # type: ignore[arg-type]
    kickoff = datetime(2026, 9, 18, 18, 0, tzinfo=UTC)

    first = resolver.resolve_entity("football", "Nowhere FC", kickoff, "Somebody")
    assert first == (None, None, False)
    assert client.searches == 1, "the first lookup must hit the network"

    second = resolver.resolve_entity("football", "Nowhere FC", kickoff, "Somebody")
    assert second == (None, None, False)
    assert client.searches == 1, "the second must be served from the miss cache"


# --------------------------------------------------------------------------
# F11 — one fixture's provider failure must not cost the whole stage
# --------------------------------------------------------------------------


def test_f11_resolve_loop_isolates_provider_errors(tmp_path: Any) -> None:
    """A ProviderError on one fixture leaves the rest of the slate intact.

    Reproduces the 2026-09-18 abort: a single `bridge HTTP 504` on fixture 420
    of 613 ended the stage and no artifact was written.
    """
    import json
    import subprocess
    import sys
    import textwrap

    run_dir = tmp_path / "runs"
    date = "2026-09-18"
    (run_dir / date).mkdir(parents=True)

    board = [
        {
            "superbet_event_id": str(i),
            "sport": "football",
            "match_name": f"Team A{i} · Team B{i}",
            "side_a": f"Team A{i}",
            "side_b": f"Team B{i}",
            "kickoff_utc": "2026-09-18T18:00:00Z",
        }
        for i in range(3)
    ]
    (run_dir / date / "01_board.json").write_text(json.dumps(board), encoding="utf-8")

    # A resolver that blows up on the middle fixture only.
    harness = textwrap.dedent(
        """
        import sys
        sys.path.insert(0, "src")
        from bet.sofa.errors import ProviderError
        import bet.sofa.resolve as R

        calls = {"n": 0}
        def fake_resolve(self, sport, side, kickoff, opponent, **kw):
            calls["n"] += 1
            if "A1" in side or "B1" in side:
                raise ProviderError("bridge HTTP 504: bridge timeout")
            return None, None, False

        R.SofaResolver.resolve_entity = fake_resolve
        sys.argv = ["run_resolve", "--date", "__DATE__"]
        import runpy
        try:
            runpy.run_path("scripts/sofa/run_resolve.py", run_name="__main__")
        except SystemExit as e:
            print("EXIT", e.code)
        """
    ).replace("__DATE__", date)
    script = tmp_path / "harness.py"
    script.write_text(harness, encoding="utf-8")

    env = {
        "SOFA_RUNS_DIR": str(run_dir),
        "SOFA_DB_PATH": str(tmp_path / "sofa.db"),
        "PATH": "/usr/bin:/bin",
        "SOFA_TRANSPORT": "direct",
    }
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env=env,
        cwd=".",
    )

    # The stage must finish, not crash with a traceback.
    assert "Traceback" not in proc.stderr, proc.stderr
    assert "SOFA_SUMMARY" in proc.stdout, proc.stdout

    summary = json.loads(proc.stdout.split("SOFA_SUMMARY: ")[1].splitlines()[0])
    assert summary["metrics"]["gaps"].get("PROVIDER_ERROR", 0) >= 1
    # It saw all three fixtures, not just the two before the failure.
    assert summary["metrics"]["input_board"] == 3

    # F5: the artifact exists even though a fixture failed.
    assert (run_dir / date / "02_fixtures.json").exists()


# --------------------------------------------------------------------------
# F6 — EVENT_NOT_FINISHED must actually be emitted
# --------------------------------------------------------------------------


def test_f6_unfinished_event_is_reported_as_a_gap(tmp_path: Any) -> None:
    from bet.sofa.contracts import GapEntry, GapReason
    from bet.sofa.samples import get_historical_events

    db_path = str(tmp_path / "sofa.db")
    migrate(db_path)
    config = SofaConfig(db_path=db_path, runs_dir=str(tmp_path), sample_n=5)
    cache = SofaCache(config)

    kickoff = datetime(2026, 9, 18, 18, 0, tzinfo=UTC)
    past = int((kickoff - timedelta(days=5)).timestamp())

    events = [
        {
            "id": 1,
            "startTimestamp": past,
            "status": {"type": "inprogress"},
            "winnerCode": 0,
        },
    ]

    class StubClient:
        def entity_events(self, entity_id: int, kind: str, page: int) -> Any:
            return {"events": events, "hasNextPage": False} if page == 0 else None

    class StubFixture:
        kickoff_utc = kickoff
        ground_type = None
        best_of = None

    gaps: list[GapEntry] = []
    got = get_historical_events(
        StubClient(),  # type: ignore[arg-type]
        cache,
        42,
        "football",
        StubFixture(),  # type: ignore[arg-type]
        config,
        gaps,
    )

    assert got == [], "an unfinished event must not enter the sample"
    assert any(g.reason == GapReason.EVENT_NOT_FINISHED for g in gaps), (
        "the exclusion must be reported, not silent"
    )


# --------------------------------------------------------------------------
# F3 — the backfill must resume rather than restart
# --------------------------------------------------------------------------


def test_f3_backfill_checkpoint_reads_settled_events(tmp_path: Any) -> None:
    import importlib.util

    db_path = str(tmp_path / "sofa.db")
    migrate(db_path)

    spec = importlib.util.spec_from_file_location(
        "run_backfill", "scripts/sofa/run_backfill.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.already_settled_event_ids(db_path) == set()

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sofa_settled_row
              (sofascore_event_id, run_date, sport, market, subject, line,
               direction, sample_size, sample_mean, sample_sd, p_central,
               p_bar, actual_value, outcome, settled_at)
            VALUES (777, '2026-09-18', 'football', 'corners_total', 'match',
                    9.5, 'OVER', 10, 9.9, 2.0, 0.55, 0.5, 11.0, 'WIN',
                    '2026-09-18T00:00:00Z')
            """
        )
        conn.commit()

    assert module.already_settled_event_ids(db_path) == {777}


# --------------------------------------------------------------------------
# F8 — a run must be identifiable in the log
# --------------------------------------------------------------------------


def test_f8_log_rows_carry_the_run_id(tmp_path: Any) -> None:
    import json

    class OkTransport:
        def get(self, url: str, timeout: float = 10.0) -> Any:
            class Resp:
                status_code = 200
                text = "{}"

                def json(self) -> Any:
                    return {}

            return Resp()

    config = SofaConfig(runs_dir=str(tmp_path), target_rps=1000, run_id="abc123")
    client = SofascoreClient(config, transport=OkTransport())
    client.event(1)

    rows = [
        json.loads(line)
        for line in (tmp_path / "run.log.jsonl").read_text().splitlines()
    ]
    assert rows, "the request must be logged"
    assert all(r["run_id"] == "abc123" for r in rows)
