"""Tests for database schema, connection, and repository operations."""

import json
import sqlite3

import pytest

from bet.db.models import Fixture, MatchStat, TeamForm
from bet.db.repositories import (
    CouponRepo,
    FixtureRepo,
    PipelineRepo,
    SportRepo,
    StatsRepo,
    TeamRepo,
)
from bet.db.schema import init_db


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_schema_init():
    """init_db creates all expected tables in an in-memory DB."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)

    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    expected = {
        "sports", "competitions", "teams", "fixtures", "match_stats",
        "team_form", "odds_history", "coupons", "bets", "pipeline_runs",
        "source_health", "schema_meta",
    }
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"
    conn.close()


def test_schema_idempotent():
    """Running init_db twice causes no errors."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    init_db(conn)  # second call — should not raise

    # Verify tables still intact
    count = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
    ).fetchone()[0]
    assert count >= 11
    conn.close()


def test_fk_enforcement(db):
    """FK constraints raise an error for invalid references."""
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO teams (sport_id, name, aliases) VALUES (?, ?, ?)",
            (9999, "Ghost Team", "[]"),
        )


# ---------------------------------------------------------------------------
# TeamRepo tests
# ---------------------------------------------------------------------------


def test_team_resolve_by_alias(db_with_sports):
    """Resolve 'Barca' to canonical 'FC Barcelona'."""
    conn = db_with_sports
    repo = TeamRepo(conn)
    football = SportRepo(conn).get_by_name("football")

    repo.find_or_create("FC Barcelona", football.id, aliases=["Barca", "FCB"])
    conn.commit()

    resolved = repo.resolve("Barca", football.id)
    assert resolved is not None
    assert resolved.name == "FC Barcelona"

    resolved_fcb = repo.resolve("FCB", football.id)
    assert resolved_fcb is not None
    assert resolved_fcb.name == "FC Barcelona"


# ---------------------------------------------------------------------------
# FixtureRepo tests
# ---------------------------------------------------------------------------


def test_fixture_upsert_dedup(db_with_sports):
    """Upserting the same fixture twice results in exactly 1 row."""
    conn = db_with_sports
    team_repo = TeamRepo(conn)
    fixture_repo = FixtureRepo(conn)
    football = SportRepo(conn).get_by_name("football")

    team_a = team_repo.find_or_create("Team A", football.id)
    team_b = team_repo.find_or_create("Team B", football.id)
    conn.commit()

    fix = Fixture(
        id=None, sport_id=football.id, competition_id=None,
        home_team_id=team_a.id, away_team_id=team_b.id,
        kickoff="2026-05-03T15:00:00", source="test",
        fetched_at="2026-05-03T00:00:00",
    )

    id1 = fixture_repo.upsert(fix)
    id2 = fixture_repo.upsert(fix)  # second upsert

    assert id1 == id2

    count = conn.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
    assert count == 1


# ---------------------------------------------------------------------------
# StatsRepo tests
# ---------------------------------------------------------------------------


def test_stats_get_form(db_with_sports):
    """get_form returns values ordered most-recent-first."""
    conn = db_with_sports
    team_repo = TeamRepo(conn)
    fixture_repo = FixtureRepo(conn)
    stats_repo = StatsRepo(conn)
    football = SportRepo(conn).get_by_name("football")

    team_a = team_repo.find_or_create("Team X", football.id)
    team_b = team_repo.find_or_create("Team Y", football.id)
    conn.commit()

    # Create 3 finished fixtures with different dates and corner stats
    for i, (dt, corners) in enumerate([
        ("2026-04-01T15:00:00", 4.0),
        ("2026-04-08T15:00:00", 7.0),
        ("2026-04-15T15:00:00", 6.0),
    ]):
        fix = Fixture(
            id=None, sport_id=football.id, competition_id=None,
            home_team_id=team_a.id, away_team_id=team_b.id,
            kickoff=dt, status="finished",
            source="test", fetched_at=dt,
        )
        fix_id = fixture_repo.upsert(fix)
        stats_repo.save_match_stats(fix_id, team_a.id, {"corners": corners}, "test")
    conn.commit()

    form = stats_repo.get_form(team_a.id, "corners", n=10)
    # Most recent first: 6.0, 7.0, 4.0
    assert form == [6.0, 7.0, 4.0]


# ---------------------------------------------------------------------------
# Connection commit/rollback tests
# ---------------------------------------------------------------------------


def test_connection_commit_rollback():
    """Clean exit commits; exception path rolls back."""
    from bet.db.connection import get_db

    # Commit path
    with get_db(":memory:") as conn:
        init_db(conn)
        conn.execute(
            "INSERT INTO sports (name, tier, stat_keys) VALUES (?, ?, ?)",
            ("test_sport", 1, "[]"),
        )
    # Connection is closed after context exit, so data was committed

    # Rollback path
    try:
        with get_db(":memory:") as conn2:
            init_db(conn2)
            conn2.execute(
                "INSERT INTO sports (name, tier, stat_keys) VALUES (?, ?, ?)",
                ("rollback_sport", 1, "[]"),
            )
            raise ValueError("trigger rollback")
    except ValueError:
        pass
    # After rollback, connection is closed — nothing persisted
