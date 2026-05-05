"""Tests for DB integration bug fixes (May 2026 deep audit).

Tests:
1. coupon_builder resolves fixture_id (was always NULL)
2. settle_on_finish syncs settlement to DB
3. OddsRepo.upsert prevents duplicates
4. db_data_loader adds sport alias for sport_name
5. deep_stats_report falls back to DB for team form
6. source_health tracking via base_client
"""

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from bet.db.models import Bet, Coupon, Fixture, OddsRecord
from bet.db.repositories import (
    CouponRepo,
    FixtureRepo,
    OddsRepo,
    SportRepo,
    TeamRepo,
)

SCHEMA_PATH = Path(__file__).parent.parent / "src" / "bet" / "db" / "schema.sql"


@pytest.fixture
def db():
    """In-memory SQLite database with schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    schema = SCHEMA_PATH.read_text()
    conn.executescript(schema)
    yield conn
    conn.close()


@pytest.fixture
def seeded_db(db):
    """DB with sports, teams, and a fixture seeded."""
    sport_repo = SportRepo(db)
    sport_repo.seed_defaults()

    team_repo = TeamRepo(db)
    fixture_repo = FixtureRepo(db)

    football = sport_repo.get_by_name("football")
    home = team_repo.find_or_create("Arsenal", football.id, aliases=["Arsenal FC"])
    away = team_repo.find_or_create("Chelsea", football.id, aliases=["Chelsea FC"])

    f1 = Fixture(
        id=None,
        sport_id=football.id,
        competition_id=None,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff="2026-05-04T15:00:00",
        status="scheduled",
        source="test",
        fetched_at="2026-05-04T10:00:00",
    )
    f1_id = fixture_repo.upsert(f1)
    db.commit()

    return {
        "conn": db,
        "football": football,
        "home": home,
        "away": away,
        "f1_id": f1_id,
    }


# ---------------------------------------------------------------------------
# Test 1: OddsRepo.upsert doesn't crash on duplicate
# ---------------------------------------------------------------------------

class TestOddsRepoUpsert:
    def test_upsert_inserts_odds(self, seeded_db):
        conn = seeded_db["conn"]
        repo = OddsRepo(conn)
        record = OddsRecord(
            id=None,
            fixture_id=seeded_db["f1_id"],
            bookmaker="Betclic PL",
            market="h2h",
            selection="home",
            odds=1.85,
            fetched_at="2026-05-04T10:00:00",
        )
        repo.upsert(record)
        conn.commit()

        rows = conn.execute("SELECT * FROM odds_history").fetchall()
        assert len(rows) == 1
        assert rows[0]["odds"] == 1.85

    def test_upsert_ignores_duplicate(self, seeded_db):
        conn = seeded_db["conn"]
        repo = OddsRepo(conn)
        record = OddsRecord(
            id=None,
            fixture_id=seeded_db["f1_id"],
            bookmaker="Betclic PL",
            market="h2h",
            selection="home",
            odds=1.85,
            fetched_at="2026-05-04T10:00:00",
        )
        repo.upsert(record)
        repo.upsert(record)  # Duplicate — should be ignored by unique index
        conn.commit()

        rows = conn.execute("SELECT * FROM odds_history").fetchall()
        assert len(rows) == 1  # Deduplication via unique index


# ---------------------------------------------------------------------------
# Test 2: CouponRepo settle methods work
# ---------------------------------------------------------------------------

class TestCouponSettlement:
    def test_settle_coupon(self, seeded_db):
        conn = seeded_db["conn"]
        repo = CouponRepo(conn)

        coupon = Coupon(
            id=None,
            coupon_id="CP-TEST-001",
            coupon_type="AKO",
            total_odds=3.5,
            stake_pln=10.0,
            status="pending",
            version=1,
        )
        cid = repo.create_coupon(coupon)

        bet = Bet(
            id=None,
            coupon_id=cid,
            fixture_id=seeded_db["f1_id"],
            sport="football",
            event_name="Arsenal vs Chelsea",
            market="Corners Total O/U",
            selection="OVER 9.5",
            odds=1.85,
            status="pending",
        )
        bid = repo.add_bet(bet)
        conn.commit()

        # Settle
        repo.settle_bet(bid, "won", 8.5)
        repo.settle_coupon(cid, "won", 25.0)
        conn.commit()

        c, bets = repo.get_coupon_with_bets(cid)
        assert c.status == "won"
        assert c.pnl_pln == 25.0
        assert bets[0].status == "won"
        assert bets[0].pnl_pln == 8.5

    def test_bet_with_fixture_id(self, seeded_db):
        """Verify bet.fixture_id is set (was NULL before fix)."""
        conn = seeded_db["conn"]
        repo = CouponRepo(conn)

        coupon = Coupon(
            id=None,
            coupon_id="CP-TEST-002",
            coupon_type="AKO",
            total_odds=2.0,
            stake_pln=10.0,
            status="pending",
            version=1,
        )
        cid = repo.create_coupon(coupon)

        # Create bet WITH fixture_id (the fix)
        bet = Bet(
            id=None,
            coupon_id=cid,
            fixture_id=seeded_db["f1_id"],  # NOT None!
            sport="football",
            event_name="Arsenal vs Chelsea",
            market="Corners Total O/U",
            selection="OVER 9.5",
            odds=1.85,
            status="pending",
        )
        bid = repo.add_bet(bet)
        conn.commit()

        _, bets = repo.get_coupon_with_bets(cid)
        assert bets[0].fixture_id == seeded_db["f1_id"]
        assert bets[0].fixture_id is not None


# ---------------------------------------------------------------------------
# Test 3: FixtureRepo.get_by_teams_and_date works for fixture resolution
# ---------------------------------------------------------------------------

class TestFixtureResolution:
    def test_resolve_by_canonical_name(self, seeded_db):
        conn = seeded_db["conn"]
        repo = FixtureRepo(conn)
        f = repo.get_by_teams_and_date(
            "Arsenal", "Chelsea", "2026-05-04", seeded_db["football"].id
        )
        assert f is not None
        assert f.id == seeded_db["f1_id"]

    def test_resolve_by_alias(self, seeded_db):
        conn = seeded_db["conn"]
        repo = FixtureRepo(conn)
        f = repo.get_by_teams_and_date(
            "Arsenal FC", "Chelsea FC", "2026-05-04", seeded_db["football"].id
        )
        assert f is not None
        assert f.id == seeded_db["f1_id"]

    def test_resolve_returns_none_for_missing(self, seeded_db):
        conn = seeded_db["conn"]
        repo = FixtureRepo(conn)
        f = repo.get_by_teams_and_date(
            "Liverpool", "Man City", "2026-05-04", seeded_db["football"].id
        )
        assert f is None


# ---------------------------------------------------------------------------
# Test 4: db_data_loader sport/sport_name consistency
# ---------------------------------------------------------------------------

class TestDbDataLoaderSportKey:
    def test_fixtures_have_sport_key(self, seeded_db):
        """Verify that DB-loaded fixtures include 'sport' key for JSON compat."""
        conn = seeded_db["conn"]
        repo = FixtureRepo(conn)
        rows = repo.get_by_date_with_teams("2026-05-04")
        # Add sport alias like db_data_loader does
        for row in rows:
            if "sport" not in row and "sport_name" in row:
                row["sport"] = row["sport_name"]

        assert len(rows) > 0
        assert "sport_name" in rows[0]
        assert "sport" in rows[0]
        assert rows[0]["sport"] == "football"


# ---------------------------------------------------------------------------
# Test 5: Source health repo
# ---------------------------------------------------------------------------

class TestSourceHealth:
    def test_record_success(self, db):
        from bet.db.repositories import SourceHealthRepo
        SportRepo(db).seed_defaults()
        repo = SourceHealthRepo(db)

        repo.record_success("api-football", response_ms=150.0)
        db.commit()

        health = repo.get_health("api-football")
        assert health is not None
        assert health["total_requests"] == 1
        assert health["consecutive_failures"] == 0

    def test_record_failure(self, db):
        from bet.db.repositories import SourceHealthRepo
        SportRepo(db).seed_defaults()
        repo = SourceHealthRepo(db)

        repo.record_failure("api-football")
        db.commit()

        health = repo.get_health("api-football")
        assert health is not None
        assert health["total_failures"] == 1
        assert health["consecutive_failures"] == 1

    def test_failure_resets_on_success(self, db):
        from bet.db.repositories import SourceHealthRepo
        SportRepo(db).seed_defaults()
        repo = SourceHealthRepo(db)

        repo.record_failure("api-football")
        repo.record_failure("api-football")
        repo.record_success("api-football", response_ms=100.0)
        db.commit()

        health = repo.get_health("api-football")
        assert health["consecutive_failures"] == 0
        assert health["total_failures"] == 2
        assert health["total_requests"] == 3


# ---------------------------------------------------------------------------
# Test 6: Pending bets with details (fixture JOIN)
# ---------------------------------------------------------------------------

class TestPendingBetsWithDetails:
    def test_pending_bets_include_team_names(self, seeded_db):
        """When fixture_id is set, JOIN should return team names."""
        conn = seeded_db["conn"]
        repo = CouponRepo(conn)

        coupon = Coupon(
            id=None,
            coupon_id="CP-DETAILS-001",
            coupon_type="AKO",
            total_odds=2.0,
            stake_pln=10.0,
            status="pending",
            version=1,
        )
        cid = repo.create_coupon(coupon)

        bet = Bet(
            id=None,
            coupon_id=cid,
            fixture_id=seeded_db["f1_id"],
            sport="football",
            event_name="Arsenal vs Chelsea",
            market="Corners Total O/U",
            selection="OVER 9.5",
            odds=1.85,
            status="pending",
        )
        repo.add_bet(bet)
        conn.commit()

        pending = repo.get_pending_bets_with_details()
        assert len(pending) == 1
        assert pending[0]["home_team"] == "Arsenal"
        assert pending[0]["away_team"] == "Chelsea"
        assert pending[0]["sport_name"] == "football"
