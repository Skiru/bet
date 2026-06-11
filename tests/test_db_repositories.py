"""Unit tests for new DB repository methods (Phases 1-3)."""

import json
import sqlite3
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bet.db.connection import get_db
from bet.db.models import Fixture, OddsRecord, TeamForm
from bet.db.repositories import (
    CompetitionRepo,
    FixtureRepo,
    OddsRepo,
    PipelineRepo,
    SportRepo,
    StatsRepo,
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
    """DB with sports, teams, competitions, and fixtures seeded."""
    sport_repo = SportRepo(db)
    sport_repo.seed_defaults()

    team_repo = TeamRepo(db)
    comp_repo = CompetitionRepo(db)
    fixture_repo = FixtureRepo(db)

    # Get football sport
    football = sport_repo.get_by_name("football")
    assert football is not None

    # Create teams
    home = team_repo.find_or_create("Arsenal", football.id, aliases=["Arsenal FC"])
    away = team_repo.find_or_create("Chelsea", football.id, aliases=["Chelsea FC"])
    third = team_repo.find_or_create("Liverpool", football.id)

    # Create competition
    comp_id = comp_repo.find_or_create("Premier League", football.id, country="England")

    # Create fixtures
    f1 = Fixture(
        id=None,
        sport_id=football.id,
        competition_id=comp_id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff="2026-05-04T15:00:00",
        status="scheduled",
        external_id="ext-001",
        source="test",
        fetched_at="2026-05-04T10:00:00",
    )
    f2 = Fixture(
        id=None,
        sport_id=football.id,
        competition_id=comp_id,
        home_team_id=third.id,
        away_team_id=home.id,
        kickoff="2026-05-04T17:30:00",
        status="scheduled",
        source="test",
        fetched_at="2026-05-04T10:00:00",
    )
    f1_id = fixture_repo.upsert(f1)
    f2_id = fixture_repo.upsert(f2)

    db.commit()
    return {
        "conn": db,
        "football": football,
        "home": home,
        "away": away,
        "third": third,
        "comp_id": comp_id,
        "f1_id": f1_id,
        "f2_id": f2_id,
    }


# ---------------------------------------------------------------------------
# Phase 1: FixtureRepo new methods
# ---------------------------------------------------------------------------

class TestFixtureRepoGetByDateWithTeams:
    def test_returns_joined_data(self, seeded_db):
        repo = FixtureRepo(seeded_db["conn"])
        results = repo.get_by_date_with_teams("2026-05-04")
        assert len(results) == 2
        # Check first fixture has team names
        r = results[0]
        assert r["home_team"] == "Arsenal"
        assert r["away_team"] == "Chelsea"
        assert r["competition"] == "Premier League"
        assert "fixture_id" in r
        assert "sport_name" in r

    def test_filter_by_sport(self, seeded_db):
        repo = FixtureRepo(seeded_db["conn"])
        football = seeded_db["football"]
        results = repo.get_by_date_with_teams("2026-05-04", sport_id=football.id)
        assert len(results) == 2

    def test_no_results_wrong_date(self, seeded_db):
        repo = FixtureRepo(seeded_db["conn"])
        results = repo.get_by_date_with_teams("2026-12-25")
        assert len(results) == 0


class TestPipelineRepoPhaseReceipts:
    def test_roundtrip_validated_phase_receipt(self, db):
        repo = PipelineRepo(db)

        repo.start_phase(
            "2026-06-05",
            "PHASE_B",
            {"completed_steps": ["S1", "S1e"], "artifacts": []},
        )
        repo.complete_phase(
            "2026-06-05",
            "PHASE_B",
            {
                "completed_steps": ["S1", "S1e", "P1", "P2"],
                "gate_verdict": "passed",
                "artifacts": [{"path": "betting/data/2026-06-05_s2_shortlist.json", "exists": False}],
            },
        )

        receipt = repo.get_phase_receipt("2026-06-05", "PHASE_B")

        assert receipt is not None
        assert receipt["status"] == "completed"
        assert receipt["receipt"]["status"] == "validated"
        assert receipt["receipt"]["next_phase"] == "PHASE_C"
        assert receipt["receipt"]["completed_steps"][-1] == "P2"

    def test_get_next_resume_phase_uses_first_non_validated_phase(self, db):
        repo = PipelineRepo(db)

        repo.start_phase("2026-06-05", "PHASE_A")
        repo.complete_phase("2026-06-05", "PHASE_A", {"completed_steps": ["S0", "P0"]})
        repo.start_phase("2026-06-05", "PHASE_B")
        repo.fail_phase("2026-06-05", "PHASE_B", "matrix drift")

        assert repo.get_next_resume_phase("2026-06-05") == "PHASE_B"

    def test_complete_phase_upserts_without_prior_start(self, db):
        repo = PipelineRepo(db)

        repo.complete_phase("2026-06-05", "PHASE_C", {"completed_steps": ["S2", "P3"]})

        receipt = repo.get_phase_receipt("2026-06-05", "PHASE_C")

        assert receipt is not None
        assert receipt["status"] == "completed"
        assert receipt["receipt"]["status"] == "validated"

    def test_get_next_resume_phase_requires_contiguous_prefix(self, db):
        repo = PipelineRepo(db)

        repo.complete_phase("2026-06-05", "PHASE_B", {"completed_steps": ["S1", "S1e"]})

        assert repo.get_next_resume_phase("2026-06-05") == "PHASE_A"

    def test_get_last_validated_phase_skips_failed_and_malformed_receipts(self, db):
        repo = PipelineRepo(db)

        repo.start_phase("2026-06-05", "PHASE_A")
        repo.complete_phase("2026-06-05", "PHASE_A", {"completed_steps": ["S0"]})
        db.execute(
            "INSERT INTO pipeline_runs (date, step, status, started_at, completed_at, stats) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "2026-06-05",
                "PHASE_B",
                "completed",
                "2026-06-05T10:00:00+00:00",
                "2026-06-05T10:05:00+00:00",
                "{bad json",
            ),
        )

        last_validated = repo.get_last_validated_phase("2026-06-05")

        assert last_validated is not None
        assert last_validated["phase_id"] == "PHASE_A"


class TestSportRepoSeedDefaults:
    def test_hockey_is_seeded_as_tier_1(self, db):
        repo = SportRepo(db)
        repo.seed_defaults()

        hockey = repo.get_by_name("hockey")

        assert hockey is not None
        assert hockey.tier == 1


class TestFixtureRepoGetByTeamsAndDate:
    def test_finds_by_canonical_names(self, seeded_db):
        repo = FixtureRepo(seeded_db["conn"])
        football = seeded_db["football"]
        fixture = repo.get_by_teams_and_date(
            "Arsenal", "Chelsea", "2026-05-04", football.id
        )
        assert fixture is not None
        assert fixture.id == seeded_db["f1_id"]

    def test_finds_by_alias(self, seeded_db):
        repo = FixtureRepo(seeded_db["conn"])
        football = seeded_db["football"]
        fixture = repo.get_by_teams_and_date(
            "Arsenal FC", "Chelsea FC", "2026-05-04", football.id
        )
        assert fixture is not None
        assert fixture.id == seeded_db["f1_id"]

    def test_returns_none_when_not_found(self, seeded_db):
        repo = FixtureRepo(seeded_db["conn"])
        football = seeded_db["football"]
        fixture = repo.get_by_teams_and_date(
            "Man City", "Man United", "2026-05-04", football.id
        )
        assert fixture is None


class TestFixtureRepoBulkUpsert:
    def test_bulk_upsert_returns_ids(self, seeded_db):
        conn = seeded_db["conn"]
        repo = FixtureRepo(conn)
        football = seeded_db["football"]
        team_repo = TeamRepo(conn)

        t1 = team_repo.find_or_create("Tottenham", football.id)
        t2 = team_repo.find_or_create("West Ham", football.id)
        t3 = team_repo.find_or_create("Everton", football.id)

        fixtures = [
            Fixture(
                id=None, sport_id=football.id, competition_id=None,
                home_team_id=t1.id, away_team_id=t2.id,
                kickoff="2026-05-05T15:00:00", source="test",
                fetched_at="2026-05-04T10:00:00",
            ),
            Fixture(
                id=None, sport_id=football.id, competition_id=None,
                home_team_id=t2.id, away_team_id=t3.id,
                kickoff="2026-05-05T17:30:00", source="test",
                fetched_at="2026-05-04T10:00:00",
            ),
        ]
        ids = repo.bulk_upsert(fixtures)
        assert len(ids) == 2
        assert all(isinstance(i, int) for i in ids)

    def test_bulk_upsert_deduplicates(self, seeded_db):
        conn = seeded_db["conn"]
        repo = FixtureRepo(conn)

        # Re-upsert existing fixture — should return same ID
        home = seeded_db["home"]
        away = seeded_db["away"]
        football = seeded_db["football"]

        fixture = Fixture(
            id=None, sport_id=football.id, competition_id=seeded_db["comp_id"],
            home_team_id=home.id, away_team_id=away.id,
            kickoff="2026-05-04T15:00:00", source="test-update",
            fetched_at="2026-05-04T12:00:00",
        )
        # Count fixtures before
        count_before = conn.execute("SELECT COUNT(*) as c FROM fixtures").fetchone()["c"]

        ids = repo.bulk_upsert([fixture])
        assert len(ids) == 1

        # Count should not increase (upsert, not insert)
        count_after = conn.execute("SELECT COUNT(*) as c FROM fixtures").fetchone()["c"]
        assert count_after == count_before


# ---------------------------------------------------------------------------
# Phase 2: StatsRepo new methods
# ---------------------------------------------------------------------------

class TestStatsRepoGetAllFormForTeam:
    def test_returns_all_stat_keys(self, seeded_db):
        conn = seeded_db["conn"]
        stats_repo = StatsRepo(conn)
        home = seeded_db["home"]
        football = seeded_db["football"]

        # Save two form records
        for stat_key in ["corners", "fouls"]:
            stats_repo.save_team_form(TeamForm(
                id=None, team_id=home.id, sport_id=football.id,
                stat_key=stat_key, l10_values=[5.0, 6.0],
                l5_values=[5.5], l10_avg=5.5, l5_avg=5.5,
                trend="→", updated_at="2026-05-04T10:00:00", source="test",
            ))
        conn.commit()

        results = stats_repo.get_all_form_for_team(home.id, football.id)
        assert len(results) == 2
        keys = {r.stat_key for r in results}
        assert keys == {"corners", "fouls"}

    def test_excludes_h2h_records(self, seeded_db):
        conn = seeded_db["conn"]
        stats_repo = StatsRepo(conn)
        home = seeded_db["home"]
        away = seeded_db["away"]
        football = seeded_db["football"]

        # Save one regular and one H2H form record
        stats_repo.save_team_form(TeamForm(
            id=None, team_id=home.id, sport_id=football.id,
            stat_key="corners", l10_values=[5.0], l5_values=[5.0],
            l10_avg=5.0, l5_avg=5.0, trend="→",
            updated_at="2026-05-04T10:00:00", source="test",
        ))
        stats_repo.save_team_form(TeamForm(
            id=None, team_id=home.id, sport_id=football.id,
            stat_key="corners", l10_values=[4.0], l5_values=[4.0],
            l10_avg=4.0, l5_avg=4.0, h2h_opponent_id=away.id,
            trend="↓", updated_at="2026-05-04T10:00:00", source="test",
        ))
        conn.commit()

        results = stats_repo.get_all_form_for_team(home.id, football.id)
        assert len(results) == 1
        assert results[0].h2h_opponent_id is None


class TestStatsRepoGetTeamFormRecord:
    def test_finds_non_h2h_record(self, seeded_db):
        conn = seeded_db["conn"]
        stats_repo = StatsRepo(conn)
        home = seeded_db["home"]
        football = seeded_db["football"]

        stats_repo.save_team_form(TeamForm(
            id=None, team_id=home.id, sport_id=football.id,
            stat_key="corners", l10_values=[5.0], l5_values=[5.0],
            l10_avg=5.0, l5_avg=5.0, trend="→",
            updated_at="2026-05-04T10:00:00", source="test",
        ))
        conn.commit()

        result = stats_repo.get_team_form_record(home.id, "corners")
        assert result is not None
        assert result.l10_avg == 5.0

    def test_finds_h2h_record(self, seeded_db):
        conn = seeded_db["conn"]
        stats_repo = StatsRepo(conn)
        home = seeded_db["home"]
        away = seeded_db["away"]
        football = seeded_db["football"]

        stats_repo.save_team_form(TeamForm(
            id=None, team_id=home.id, sport_id=football.id,
            stat_key="corners", l10_values=[4.0], l5_values=[4.0],
            l10_avg=4.0, l5_avg=4.0, h2h_opponent_id=away.id,
            trend="↓", updated_at="2026-05-04T10:00:00", source="test",
        ))
        conn.commit()

        result = stats_repo.get_team_form_record(home.id, "corners", h2h_opponent_id=away.id)
        assert result is not None
        assert result.l10_avg == 4.0
        assert result.h2h_opponent_id == away.id

    def test_returns_none_when_not_found(self, seeded_db):
        conn = seeded_db["conn"]
        stats_repo = StatsRepo(conn)
        result = stats_repo.get_team_form_record(999, "nonexistent")
        assert result is None


class TestStatsRepoSportNameCache:
    def test_cache_is_instance_scoped(self):
        def make_conn() -> sqlite3.Connection:
            conn = sqlite3.connect(":memory:")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.row_factory = sqlite3.Row
            conn.executescript(SCHEMA_PATH.read_text())
            return conn

        conn_one = make_conn()
        conn_two = make_conn()
        try:
            conn_one.execute(
                "INSERT INTO sports (id, name, tier, stat_keys) VALUES (?, ?, ?, ?)",
                (1, "football", 1, "[]"),
            )
            conn_two.execute(
                "INSERT INTO sports (id, name, tier, stat_keys) VALUES (?, ?, ?, ?)",
                (1, "tennis", 1, "[]"),
            )

            repo_one = StatsRepo(conn_one)
            repo_two = StatsRepo(conn_two)

            assert repo_one._get_sport_name(1) == "football"
            assert repo_two._get_sport_name(1) == "tennis"
        finally:
            conn_one.close()
            conn_two.close()


class TestStatsRepoValueFiltering:
    def test_clears_l5_avg_when_all_l5_values_are_rejected(self, seeded_db):
        conn = seeded_db["conn"]
        stats_repo = StatsRepo(conn)
        home = seeded_db["home"]
        football = seeded_db["football"]

        stats_repo.save_team_form(TeamForm(
            id=None,
            team_id=home.id,
            sport_id=football.id,
            stat_key="corners",
            l10_values=[5.0, 6.0],
            l5_values=[999.0],
            l10_avg=5.5,
            l5_avg=999.0,
            trend="→",
            updated_at="2026-05-04T10:00:00",
            source="test",
        ))
        conn.commit()

        result = stats_repo.get_team_form_record(home.id, "corners")
        assert result is not None
        assert result.l5_values == []
        assert result.l5_avg is None



class TestStatsRepoBulkSaveMatchStats:
    def test_saves_batch(self, seeded_db):
        conn = seeded_db["conn"]
        stats_repo = StatsRepo(conn)

        rows = [
            (seeded_db["f1_id"], seeded_db["home"].id, "corners", 5.0, "test"),
            (seeded_db["f1_id"], seeded_db["home"].id, "fouls", 12.0, "test"),
            (seeded_db["f1_id"], seeded_db["away"].id, "corners", 3.0, "test"),
        ]
        stats_repo.bulk_save_match_stats(rows)
        conn.commit()

        # Verify
        count = conn.execute("SELECT COUNT(*) as c FROM match_stats").fetchone()["c"]
        assert count == 3

    def test_replaces_on_conflict(self, seeded_db):
        conn = seeded_db["conn"]
        stats_repo = StatsRepo(conn)

        rows = [
            (seeded_db["f1_id"], seeded_db["home"].id, "corners", 5.0, "test"),
        ]
        stats_repo.bulk_save_match_stats(rows)
        conn.commit()

        # Update with new value
        rows_updated = [
            (seeded_db["f1_id"], seeded_db["home"].id, "corners", 7.0, "test"),
        ]
        stats_repo.bulk_save_match_stats(rows_updated)
        conn.commit()

        count = conn.execute("SELECT COUNT(*) as c FROM match_stats").fetchone()["c"]
        assert count == 1
        val = conn.execute(
            "SELECT stat_value FROM match_stats WHERE stat_key = 'corners'"
        ).fetchone()["stat_value"]
        assert val == 7.0

    def test_get_match_stats_returns_rows(self, seeded_db):
        conn = seeded_db["conn"]
        stats_repo = StatsRepo(conn)

        rows = [
            (seeded_db["f1_id"], seeded_db["home"].id, "corners", 5.0, "test"),
            (seeded_db["f1_id"], seeded_db["away"].id, "corners", 3.0, "test"),
        ]
        stats_repo.bulk_save_match_stats(rows)
        conn.commit()

        result = stats_repo.get_match_stats(seeded_db["f1_id"])

        assert len(result) == 2
        assert {row.stat_value for row in result} == {5.0, 3.0}
        assert {row.stat_key for row in result} == {"corners"}


# ---------------------------------------------------------------------------
# Phase 3: OddsRepo new methods
# ---------------------------------------------------------------------------

class TestOddsRepoGetAllForDate:
    def test_returns_odds_keyed_by_fixture(self, seeded_db):
        conn = seeded_db["conn"]
        odds_repo = OddsRepo(conn)

        # Insert odds for fixture 1
        odds_repo.save_odds(OddsRecord(
            id=None, fixture_id=seeded_db["f1_id"],
            bookmaker="Betclic", market="h2h", selection="Arsenal",
            odds=1.85, fetched_at="2026-05-04T10:00:00",
        ))
        odds_repo.save_odds(OddsRecord(
            id=None, fixture_id=seeded_db["f1_id"],
            bookmaker="Betclic", market="h2h", selection="Chelsea",
            odds=3.50, fetched_at="2026-05-04T10:00:00",
        ))
        # Insert odds for fixture 2
        odds_repo.save_odds(OddsRecord(
            id=None, fixture_id=seeded_db["f2_id"],
            bookmaker="Betclic", market="totals", selection="Over",
            odds=1.90, line=2.5, fetched_at="2026-05-04T10:00:00",
        ))
        conn.commit()

        result = odds_repo.get_all_for_date("2026-05-04")
        assert seeded_db["f1_id"] in result
        assert seeded_db["f2_id"] in result
        assert len(result[seeded_db["f1_id"]]) == 2
        assert len(result[seeded_db["f2_id"]]) == 1

    def test_empty_for_wrong_date(self, seeded_db):
        conn = seeded_db["conn"]
        odds_repo = OddsRepo(conn)
        result = odds_repo.get_all_for_date("2026-12-25")
        assert result == {}


class TestOddsRepoGetAllForFixtures:
    def test_batch_lookup(self, seeded_db):
        conn = seeded_db["conn"]
        odds_repo = OddsRepo(conn)

        odds_repo.save_odds(OddsRecord(
            id=None, fixture_id=seeded_db["f1_id"],
            bookmaker="Betclic", market="h2h", selection="Arsenal",
            odds=1.85, fetched_at="2026-05-04T10:00:00",
        ))
        odds_repo.save_odds(OddsRecord(
            id=None, fixture_id=seeded_db["f2_id"],
            bookmaker="Betclic", market="h2h", selection="Liverpool",
            odds=2.10, fetched_at="2026-05-04T10:00:00",
        ))
        conn.commit()

        result = odds_repo.get_all_for_fixtures([seeded_db["f1_id"], seeded_db["f2_id"]])
        assert len(result) == 2

    def test_empty_list_returns_empty(self, seeded_db):
        conn = seeded_db["conn"]
        odds_repo = OddsRepo(conn)
        result = odds_repo.get_all_for_fixtures([])
        assert result == {}

    def test_nonexistent_fixture_ids(self, seeded_db):
        conn = seeded_db["conn"]
        odds_repo = OddsRepo(conn)
        result = odds_repo.get_all_for_fixtures([9999, 8888])
        assert result == {}
