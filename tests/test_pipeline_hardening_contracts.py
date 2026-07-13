"""Provider, database, temporal, and analytical-state hardening tests."""
from __future__ import annotations

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bet.db.connection import get_db, get_readonly_db
from bet.pipeline.analysis_status import classify_candidate_status, has_explicit_test_provenance
from bet.provider_runtime import ProviderFailure, ProviderPolicy, ProviderState, execute_provider_call
from bet.utils.time import betting_day_for, betting_day_range, in_betting_day


def test_provider_success_empty_and_failure_states_are_distinct():
    policy = ProviderPolicy(total_timeout_seconds=0.2, retries=0)
    assert execute_provider_call(lambda: [{"event": 1}], policy).state == ProviderState.SUCCESS
    assert execute_provider_call(lambda: [], policy).state == ProviderState.NO_EVENTS
    for state in (ProviderState.RATE_LIMITED, ProviderState.AUTH_BLOCKED, ProviderState.STALE_CACHE):
        result = execute_provider_call(lambda state=state: (_ for _ in ()).throw(ProviderFailure(state)), policy)
        assert result.state == state
        assert result.state != ProviderState.NO_EVENTS


def test_provider_total_deadline_retry_and_sanitized_error():
    started = time.monotonic()
    result = execute_provider_call(
        lambda: time.sleep(0.2),
        ProviderPolicy(total_timeout_seconds=0.03, retries=0),
    )
    assert time.monotonic() - started < 0.15
    assert result.state == ProviderState.NETWORK_TIMEOUT
    assert result.error_class == "TotalDeadlineExceeded"

    attempts = 0
    def flaky() -> list[int]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("secret-bearing transport detail")
        return [1]
    recovered = execute_provider_call(flaky, ProviderPolicy(total_timeout_seconds=1, retries=1, backoff_seconds=0))
    assert recovered.state == ProviderState.SUCCESS
    assert recovered.attempts == 2
    failed = execute_provider_call(lambda: (_ for _ in ()).throw(OSError("private token")), ProviderPolicy(retries=0))
    assert failed.error_class == "OSError"
    assert "private token" not in repr(failed)


def test_non_idempotent_provider_call_is_never_retried():
    attempts = 0

    def failing() -> list[int]:
        nonlocal attempts
        attempts += 1
        raise ProviderFailure(ProviderState.RATE_LIMITED, retry_after_seconds=0)

    result = execute_provider_call(
        failing,
        ProviderPolicy(total_timeout_seconds=1, retries=3, backoff_seconds=0),
        idempotent=False,
    )

    assert result.state == ProviderState.RATE_LIMITED
    assert attempts == 1


def test_canonical_database_pragmas_rollback_readonly_and_competing_writers(tmp_path: Path):
    database = tmp_path / "contract.db"
    with get_db(database) as conn:
        conn.execute("CREATE TABLE values_by_run (run_id TEXT, day TEXT, value INTEGER, UNIQUE(run_id, day))")
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000

    with pytest.raises(RuntimeError):
        with get_db(database) as conn:
            conn.execute("INSERT INTO values_by_run VALUES ('rollback', '2026-07-13', 1)")
            raise RuntimeError("interrupt")
    with get_readonly_db(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM values_by_run WHERE run_id='rollback'").fetchone()[0] == 0
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO values_by_run VALUES ('forbidden', '2026-07-13', 1)")

    def writer(value: int) -> None:
        with get_db(database) as conn:
            conn.execute(
                "INSERT INTO values_by_run VALUES ('run', '2026-07-13', ?) "
                "ON CONFLICT(run_id, day) DO UPDATE SET value=excluded.value",
                (value,),
            )
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(writer, (1, 2)))
    with get_readonly_db(database) as conn:
        rows = conn.execute("SELECT * FROM values_by_run WHERE run_id='run' AND day='2026-07-13'").fetchall()
        assert len(rows) == 1
        assert rows[0]["value"] in {1, 2}


def test_warsaw_half_open_cutover_utc_and_naive_rejection():
    warsaw = ZoneInfo("Europe/Warsaw")
    before = datetime(2026, 7, 13, 5, 59, 59, tzinfo=warsaw)
    at = datetime(2026, 7, 13, 6, 0, 0, tzinfo=warsaw)
    end = datetime(2026, 7, 14, 6, 0, 0, tzinfo=warsaw)
    assert betting_day_for(before) == date(2026, 7, 12)
    assert betting_day_for(at) == date(2026, 7, 13)
    assert in_betting_day(at, date(2026, 7, 13)) is True
    assert in_betting_day(end - timedelta(microseconds=1), date(2026, 7, 13)) is True
    assert in_betting_day(end, date(2026, 7, 13)) is False
    start_utc, end_utc = betting_day_range(date(2026, 7, 13))
    assert start_utc == datetime(2026, 7, 13, 4, 0, tzinfo=timezone.utc)
    assert end_utc == datetime(2026, 7, 14, 4, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="naive"):
        betting_day_for(datetime(2026, 7, 13, 6, 0))


def test_warsaw_dst_windows_and_rescheduling():
    spring_start, spring_end = betting_day_range(date(2026, 3, 28))
    fall_start, fall_end = betting_day_range(date(2026, 10, 24))
    assert spring_end - spring_start == timedelta(hours=23)
    assert fall_end - fall_start == timedelta(hours=25)
    warsaw = ZoneInfo("Europe/Warsaw")
    original = datetime(2026, 7, 14, 5, 30, tzinfo=warsaw)
    rescheduled = datetime(2026, 7, 14, 6, 30, tzinfo=warsaw)
    assert betting_day_for(original) == date(2026, 7, 13)
    assert betting_day_for(rescheduled) == date(2026, 7, 14)


def test_missing_odds_preserves_analysis_but_blocks_pricing_ev_and_stake():
    status = classify_candidate_status(
        analysis_ready=True,
        model_probability=0.6,
        human_operator_odds=None,
        risk_approved=True,
    )
    assert status["analytical_status"] == "ANALYTICAL_READY"
    assert status["pricing_status"] == "PRICE_PENDING_OPERATOR_QUOTE"
    assert status["risk_status"] == "RISK_APPROVED"
    assert status["final_status"] == "NOT_BETTABLE"
    assert status["ev_available"] is status["kelly_available"] is status["stake_available"] is False
    assert status["executable_coupon"] is status["can_place_bet_now"] is False


def test_test_and_fixture_substrings_do_not_define_provenance():
    assert has_explicit_test_provenance({"name": "Contest Fixture United"}) is False
    assert has_explicit_test_provenance({"provenance": {"kind": "LIVE_PROVIDER"}}) is False
    assert has_explicit_test_provenance({"provenance": {"kind": "TEST_FIXTURE"}}) is True
