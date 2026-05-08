"""Tests for previously untested DB repositories (M9 gap fix).

Covers: AnalysisResultRepo, GateResultRepo, AnalysisRawDataRepo,
        DecisionSnapshotRepo, DecisionOutcomeRepo, ScanResultRepo,
        AthleteRepo, PlayerGamelogRepo, PlayerSplitRepo, StandingRepo,
        TeamATSRepo, TeamOURepo, ESPNPredictionRepo, TeamRosterRepo,
        TransactionRepo, PowerIndexRepo.
"""

import json
import sqlite3
from pathlib import Path

import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bet.db.models import (
    AnalysisRawData,
    AnalysisResult,
    Athlete,
    Bet,
    Coupon,
    DecisionOutcome,
    DecisionSnapshot,
    ESPNPrediction,
    Fixture,
    GateResult,
    PlayerGamelog,
    PlayerSplit,
    PowerIndex,
    ScanResult,
    ScanRunStats,
    Standing,
    TeamATSRecord,
    TeamOURecord,
    TeamRoster,
    Transaction,
)
from bet.db.repositories import (
    AnalysisRawDataRepo,
    AnalysisResultRepo,
    AthleteRepo,
    CompetitionRepo,
    CouponRepo,
    DecisionOutcomeRepo,
    DecisionSnapshotRepo,
    ESPNPredictionRepo,
    FixtureRepo,
    GateResultRepo,
    PlayerGamelogRepo,
    PlayerSplitRepo,
    PowerIndexRepo,
    ScanResultRepo,
    SportRepo,
    StandingRepo,
    TeamATSRepo,
    TeamOURepo,
    TeamRepo,
    TeamRosterRepo,
    TransactionRepo,
)

SCHEMA_PATH = Path(__file__).parent.parent / "src" / "bet" / "db" / "schema.sql"
MIGRATION_005 = Path(__file__).parent.parent / "src" / "bet" / "db" / "migrations" / "005_espn_deep_tables.sql"


@pytest.fixture
def db():
    """In-memory SQLite with full schema + ESPN tables."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text())
    if MIGRATION_005.exists():
        conn.executescript(MIGRATION_005.read_text())
    yield conn
    conn.close()


@pytest.fixture
def seeded(db):
    """DB with sport, teams, competition, fixture, coupon+bet."""
    sport_repo = SportRepo(db)
    sport_repo.seed_defaults()
    football = sport_repo.get_by_name("football")

    team_repo = TeamRepo(db)
    home = team_repo.find_or_create("Arsenal", football.id)
    away = team_repo.find_or_create("Chelsea", football.id)

    comp_id = CompetitionRepo(db).find_or_create("Premier League", football.id, country="England")

    fid = FixtureRepo(db).upsert(Fixture(
        id=None, sport_id=football.id, competition_id=comp_id,
        home_team_id=home.id, away_team_id=away.id,
        kickoff="2026-05-08T15:00:00", source="test", fetched_at="2026-05-08T10:00:00",
    ))

    coupon_repo = CouponRepo(db)
    cid = coupon_repo.create_coupon(Coupon(
        id=None, coupon_id="C-20260508-001", coupon_type="AKO",
        total_odds=3.5, stake_pln=2.0, status="pending",
        created_at="2026-05-08T10:00:00",
    ))
    bid = coupon_repo.add_bet(Bet(
        id=None, coupon_id=cid, fixture_id=fid, sport="football",
        event_name="Arsenal vs Chelsea", market="corners_total",
        selection="Over 9.5", odds=1.85, safety_score=0.72, hit_rate=0.80,
    ))

    db.commit()
    return {
        "conn": db, "football": football, "home": home, "away": away,
        "comp_id": comp_id, "fid": fid, "cid": cid, "bid": bid,
    }


# ── AnalysisResultRepo ──────────────────────────────────────────────


class TestAnalysisResultRepo:
    def test_save_and_get_by_date(self, seeded):
        repo = AnalysisResultRepo(seeded["conn"])
        ar = AnalysisResult(
            id=None, fixture_id=seeded["fid"], betting_date="2026-05-08",
            has_data=True, best_market_name="corners_total",
            best_market_line=9.5, best_market_direction="OVER",
            best_safety_score=0.72, markets_evaluated=5,
            ranking_json=[{"market": "corners", "score": 0.72}],
            warnings_json=[], source="test",
        )
        repo.save(ar)
        seeded["conn"].commit()

        results = repo.get_by_date("2026-05-08")
        assert len(results) == 1
        assert results[0].best_market_name == "corners_total"
        assert results[0].has_data is True
        assert results[0].ranking_json == [{"market": "corners", "score": 0.72}]

    def test_get_with_data_filters(self, seeded):
        repo = AnalysisResultRepo(seeded["conn"])
        repo.save(AnalysisResult(
            id=None, fixture_id=seeded["fid"], betting_date="2026-05-08",
            has_data=False, source="test",
        ))
        seeded["conn"].commit()
        assert repo.get_with_data("2026-05-08") == []

    def test_bulk_save(self, seeded):
        repo = AnalysisResultRepo(seeded["conn"])
        results = [
            AnalysisResult(
                id=None, fixture_id=seeded["fid"], betting_date="2026-05-08",
                has_data=True, best_market_name="corners", source="test",
            ),
        ]
        repo.bulk_save(results)
        seeded["conn"].commit()
        assert len(repo.get_by_date("2026-05-08")) == 1

    def test_delete_by_date(self, seeded):
        repo = AnalysisResultRepo(seeded["conn"])
        repo.save(AnalysisResult(
            id=None, fixture_id=seeded["fid"], betting_date="2026-05-08",
            has_data=True, source="test",
        ))
        seeded["conn"].commit()
        deleted = repo.delete_by_date("2026-05-08")
        assert deleted == 1
        assert repo.get_by_date("2026-05-08") == []

    def test_update_stats_summary(self, seeded):
        repo = AnalysisResultRepo(seeded["conn"])
        repo.save(AnalysisResult(
            id=None, fixture_id=seeded["fid"], betting_date="2026-05-08",
            has_data=True, source="test",
        ))
        seeded["conn"].commit()
        updated = repo.update_stats_summary(seeded["fid"], "2026-05-08", {"key": "val"})
        assert updated == 1
        result = repo.get_by_fixture(seeded["fid"], "2026-05-08")
        assert result.stats_summary_json == {"key": "val"}


# ── GateResultRepo ──────────────────────────────────────────────────


class TestGateResultRepo:
    def test_save_and_get_approved(self, seeded):
        repo = GateResultRepo(seeded["conn"])
        repo.save(GateResult(
            id=None, fixture_id=seeded["fid"], betting_date="2026-05-08",
            status="APPROVED", gate_score=14, best_market_name="corners_total",
            best_safety_score=0.72, ev=0.15, risk_tier="LR", source="test",
        ))
        seeded["conn"].commit()

        approved = repo.get_approved("2026-05-08")
        assert len(approved) == 1
        assert approved[0].status == "APPROVED"
        assert approved[0].gate_score == 14

    def test_get_extended(self, seeded):
        repo = GateResultRepo(seeded["conn"])
        repo.save(GateResult(
            id=None, fixture_id=seeded["fid"], betting_date="2026-05-08",
            status="EXTENDED", gate_score=10, source="test",
        ))
        seeded["conn"].commit()
        extended = repo.get_extended("2026-05-08")
        assert len(extended) == 1

    def test_bulk_save(self, seeded):
        repo = GateResultRepo(seeded["conn"])
        repo.bulk_save([
            GateResult(
                id=None, fixture_id=seeded["fid"], betting_date="2026-05-08",
                status="APPROVED", gate_score=14, source="test",
            ),
        ])
        seeded["conn"].commit()
        assert len(repo.get_by_date("2026-05-08")) == 1

    def test_delete_by_date(self, seeded):
        repo = GateResultRepo(seeded["conn"])
        repo.save(GateResult(
            id=None, fixture_id=seeded["fid"], betting_date="2026-05-08",
            status="APPROVED", gate_score=14, source="test",
        ))
        seeded["conn"].commit()
        deleted = repo.delete_by_date("2026-05-08")
        assert deleted == 1


# ── AnalysisRawDataRepo ─────────────────────────────────────────────


class TestAnalysisRawDataRepo:
    def test_save_and_get(self, seeded):
        repo = AnalysisRawDataRepo(seeded["conn"])
        repo.save(AnalysisRawData(
            id=None, fixture_id=seeded["fid"], betting_date="2026-05-08",
            team_a_l10_json={"corners": [10, 11]},
            team_b_l10_json={"corners": [8, 9]},
            h2h_meetings_json={"count": 3},
            per_market_details_json=[{"m": "corners", "s": 0.7}],
        ))
        seeded["conn"].commit()

        result = repo.get_by_fixture(seeded["fid"], "2026-05-08")
        assert result is not None
        assert result.team_a_l10_json == {"corners": [10, 11]}

    def test_get_by_date(self, seeded):
        repo = AnalysisRawDataRepo(seeded["conn"])
        repo.save(AnalysisRawData(
            id=None, fixture_id=seeded["fid"], betting_date="2026-05-08",
        ))
        seeded["conn"].commit()
        results = repo.get_by_date("2026-05-08")
        assert len(results) == 1


# ── DecisionSnapshotRepo ────────────────────────────────────────────


class TestDecisionSnapshotRepo:
    def test_save_and_get_by_bet(self, seeded):
        repo = DecisionSnapshotRepo(seeded["conn"])
        repo.save(DecisionSnapshot(
            id=None, bet_id=seeded["bid"], fixture_id=seeded["fid"],
            betting_date="2026-05-08", chosen_market="corners_total",
            chosen_line=9.5, chosen_direction="OVER", safety_score=0.72,
            reasoning_json={"reason": "strong L10"},
        ))
        seeded["conn"].commit()

        snap = repo.get_by_bet(seeded["bid"])
        assert snap is not None
        assert snap.chosen_market == "corners_total"
        assert snap.reasoning_json == {"reason": "strong L10"}

    def test_get_by_fixture(self, seeded):
        repo = DecisionSnapshotRepo(seeded["conn"])
        repo.save(DecisionSnapshot(
            id=None, bet_id=seeded["bid"], fixture_id=seeded["fid"],
            betting_date="2026-05-08", chosen_market="corners_total",
            chosen_direction="OVER",
        ))
        seeded["conn"].commit()
        snaps = repo.get_by_fixture(seeded["fid"])
        assert len(snaps) == 1

    def test_get_by_date(self, seeded):
        repo = DecisionSnapshotRepo(seeded["conn"])
        repo.save(DecisionSnapshot(
            id=None, bet_id=seeded["bid"], fixture_id=seeded["fid"],
            betting_date="2026-05-08", chosen_market="corners_total",
            chosen_direction="OVER",
        ))
        seeded["conn"].commit()
        assert len(repo.get_by_date("2026-05-08")) == 1


# ── DecisionOutcomeRepo ─────────────────────────────────────────────


class TestDecisionOutcomeRepo:
    def test_save_and_get_by_bet(self, seeded):
        repo = DecisionOutcomeRepo(seeded["conn"])
        repo.save(DecisionOutcome(
            id=None, bet_id=seeded["bid"], fixture_id=seeded["fid"],
            betting_date="2026-05-08", sport="football", market="corners_total",
            line=9.5, direction="OVER", predicted_value=11.2, actual_value=10.0,
            deviation=1.2, deviation_pct=10.7, result="won",
        ))
        seeded["conn"].commit()

        outcome = repo.get_by_bet(seeded["bid"])
        assert outcome is not None
        assert outcome.result == "won"
        assert outcome.deviation == 1.2

    def test_get_by_sport_and_market(self, seeded):
        repo = DecisionOutcomeRepo(seeded["conn"])
        repo.save(DecisionOutcome(
            id=None, bet_id=seeded["bid"], fixture_id=seeded["fid"],
            betting_date="2026-05-08", sport="football", market="corners_total",
            direction="OVER", result="won",
        ))
        seeded["conn"].commit()
        results = repo.get_by_sport_and_market("football", "corners_total")
        assert len(results) == 1

    def test_get_deviation_stats(self, seeded):
        repo = DecisionOutcomeRepo(seeded["conn"])
        repo.save(DecisionOutcome(
            id=None, bet_id=seeded["bid"], fixture_id=seeded["fid"],
            betting_date="2026-05-08", sport="football", market="corners_total",
            direction="OVER", predicted_value=11.0, actual_value=10.0,
            deviation=1.0, deviation_pct=9.1, result="won",
        ))
        seeded["conn"].commit()

        stats = repo.get_deviation_stats(sport="football")
        assert stats["count"] == 1
        assert stats["won_count"] == 1
        assert stats["avg_deviation"] == 1.0

    def test_get_deviation_stats_no_filter(self, seeded):
        repo = DecisionOutcomeRepo(seeded["conn"])
        repo.save(DecisionOutcome(
            id=None, bet_id=seeded["bid"], fixture_id=seeded["fid"],
            betting_date="2026-05-08", sport="football", market="corners",
            direction="OVER", predicted_value=10.0, actual_value=9.0,
            deviation=1.0, result="lost",
        ))
        seeded["conn"].commit()
        stats = repo.get_deviation_stats()
        assert stats["count"] == 1
        assert stats["lost_count"] == 1


# ── ScanResultRepo ──────────────────────────────────────────────────


class TestScanResultRepo:
    def test_bulk_insert_and_get(self, seeded):
        repo = ScanResultRepo(seeded["conn"])
        count = repo.bulk_insert([
            ScanResult(
                id=None, betting_date="2026-05-08", sport="football",
                source_domain="flashscore.com", event_key="arsenal-chelsea",
                home_team="Arsenal", away_team="Chelsea",
                competition="Premier League", kickoff="2026-05-08T15:00:00",
            ),
        ])
        seeded["conn"].commit()
        assert count == 1

        results = repo.get_all_by_date("2026-05-08")
        assert len(results) == 1
        assert results[0].home_team == "Arsenal"

    def test_get_by_date_and_sport(self, seeded):
        repo = ScanResultRepo(seeded["conn"])
        repo.bulk_insert([
            ScanResult(
                id=None, betting_date="2026-05-08", sport="football",
                source_domain="test", event_key="a-b",
            ),
            ScanResult(
                id=None, betting_date="2026-05-08", sport="tennis",
                source_domain="test", event_key="c-d",
            ),
        ])
        seeded["conn"].commit()
        football_results = repo.get_by_date_and_sport("2026-05-08", "football")
        assert len(football_results) == 1

    def test_delete_by_date(self, seeded):
        repo = ScanResultRepo(seeded["conn"])
        repo.bulk_insert([
            ScanResult(
                id=None, betting_date="2026-05-08", sport="football",
                source_domain="test", event_key="a-b",
            ),
        ])
        seeded["conn"].commit()
        deleted = repo.delete_by_date("2026-05-08")
        assert deleted == 1

    def test_record_run_stats(self, seeded):
        repo = ScanResultRepo(seeded["conn"])
        repo.record_run_stats(ScanRunStats(
            id=None, betting_date="2026-05-08", sport="football",
            scanner_group="eu_football", events_found=42, sources_ok=5,
            sources_failed=1, deep_links_found=30,
        ))
        seeded["conn"].commit()
        stats = repo.get_run_stats("2026-05-08")
        assert len(stats) == 1
        assert stats[0].events_found == 42


# ── AthleteRepo ─────────────────────────────────────────────────────


class TestAthleteRepo:
    def test_upsert_and_get(self, seeded):
        repo = AthleteRepo(seeded["conn"])
        athlete = Athlete(
            id=None, external_id="espn-12345", sport_id=seeded["football"].id,
            team_id=seeded["home"].id, name="Bukayo Saka",
            position="RW", jersey="7", age=24,
        )
        aid = repo.upsert(athlete)
        seeded["conn"].commit()
        assert aid > 0

        result = repo.get_by_external_id("espn-12345", seeded["football"].id)
        assert result is not None
        assert result.name == "Bukayo Saka"

    def test_get_by_team(self, seeded):
        repo = AthleteRepo(seeded["conn"])
        repo.upsert(Athlete(
            id=None, external_id="espn-001", sport_id=seeded["football"].id,
            team_id=seeded["home"].id, name="Player A",
        ))
        repo.upsert(Athlete(
            id=None, external_id="espn-002", sport_id=seeded["football"].id,
            team_id=seeded["home"].id, name="Player B",
        ))
        seeded["conn"].commit()
        athletes = repo.get_by_team(seeded["home"].id)
        assert len(athletes) == 2


# ── PlayerGamelogRepo ───────────────────────────────────────────────


class TestPlayerGamelogRepo:
    def test_upsert_and_get_last_n(self, seeded):
        repo = PlayerGamelogRepo(seeded["conn"])
        athlete_repo = AthleteRepo(seeded["conn"])
        aid = athlete_repo.upsert(Athlete(
            id=None, external_id="espn-100", sport_id=seeded["football"].id,
            team_id=seeded["home"].id, name="Test Player",
        ))

        repo.upsert(PlayerGamelog(
            id=None, athlete_id=aid, fixture_id=seeded["fid"],
            game_date="2026-05-01", opponent="Chelsea", result="W",
            stats_json='{"goals": 1}',
        ))
        repo.upsert(PlayerGamelog(
            id=None, athlete_id=aid, fixture_id=None,
            game_date="2026-04-28", opponent="Liverpool", result="L",
        ))
        seeded["conn"].commit()

        logs = repo.get_last_n(aid, n=5)
        assert len(logs) == 2
        assert logs[0].game_date == "2026-05-01"  # most recent first


# ── PlayerSplitRepo ─────────────────────────────────────────────────


class TestPlayerSplitRepo:
    def test_upsert_and_get(self, seeded):
        athlete_repo = AthleteRepo(seeded["conn"])
        aid = athlete_repo.upsert(Athlete(
            id=None, external_id="espn-200", sport_id=seeded["football"].id,
            team_id=seeded["home"].id, name="Split Player",
        ))

        repo = PlayerSplitRepo(seeded["conn"])
        repo.upsert(PlayerSplit(
            id=None, athlete_id=aid, split_type="home",
            stats_json='{"goals_avg": 0.8}', season="2025-26",
        ))
        seeded["conn"].commit()

        splits = repo.get_for_athlete(aid)
        assert len(splits) == 1
        assert splits[0].split_type == "home"


# ── StandingRepo ────────────────────────────────────────────────────


class TestStandingRepo:
    def test_upsert_and_get_by_competition(self, seeded):
        repo = StandingRepo(seeded["conn"])
        repo.upsert(Standing(
            id=None, competition_id=seeded["comp_id"], team_id=seeded["home"].id,
            season="2025-26", rank=1, wins=25, draws=5, losses=3, points=80,
            form="WWWDW",
        ))
        repo.upsert(Standing(
            id=None, competition_id=seeded["comp_id"], team_id=seeded["away"].id,
            season="2025-26", rank=2, wins=22, draws=8, losses=3, points=74,
        ))
        seeded["conn"].commit()

        standings = repo.get_by_competition(seeded["comp_id"], "2025-26")
        assert len(standings) == 2
        assert standings[0].rank == 1

    def test_get_team_standing(self, seeded):
        repo = StandingRepo(seeded["conn"])
        repo.upsert(Standing(
            id=None, competition_id=seeded["comp_id"], team_id=seeded["home"].id,
            season="2025-26", rank=1, wins=25, points=80,
        ))
        seeded["conn"].commit()

        standing = repo.get_team_standing(seeded["home"].id, seeded["comp_id"], "2025-26")
        assert standing is not None
        assert standing.wins == 25


# ── TeamATSRepo ─────────────────────────────────────────────────────


class TestTeamATSRepo:
    def test_upsert_and_get(self, seeded):
        repo = TeamATSRepo(seeded["conn"])
        repo.upsert(TeamATSRecord(
            id=None, team_id=seeded["home"].id, sport_id=seeded["football"].id,
            season="2025-26", wins=15, losses=10, pushes=3,
        ))
        seeded["conn"].commit()

        records = repo.get_for_team(seeded["home"].id, "2025-26")
        assert len(records) == 1
        assert records[0].wins == 15


# ── TeamOURepo ──────────────────────────────────────────────────────


class TestTeamOURepo:
    def test_upsert_and_get(self, seeded):
        repo = TeamOURepo(seeded["conn"])
        repo.upsert(TeamOURecord(
            id=None, team_id=seeded["home"].id, sport_id=seeded["football"].id,
            season="2025-26", overs=18, unders=10, pushes=2,
        ))
        seeded["conn"].commit()

        records = repo.get_for_team(seeded["home"].id, "2025-26")
        assert len(records) == 1
        assert records[0].overs == 18


# ── ESPNPredictionRepo ──────────────────────────────────────────────


class TestESPNPredictionRepo:
    def test_upsert_and_get(self, seeded):
        repo = ESPNPredictionRepo(seeded["conn"])
        repo.upsert(ESPNPrediction(
            id=None, fixture_id=seeded["fid"],
            home_win_pct=65.0, away_win_pct=25.0, tie_pct=10.0,
        ))
        seeded["conn"].commit()

        pred = repo.get_for_fixture(seeded["fid"])
        assert pred is not None
        assert pred.home_win_pct == 65.0
        assert pred.tie_pct == 10.0


# ── TeamRosterRepo ──────────────────────────────────────────────────


class TestTeamRosterRepo:
    def test_upsert_and_get(self, seeded):
        athlete_repo = AthleteRepo(seeded["conn"])
        aid = athlete_repo.upsert(Athlete(
            id=None, external_id="espn-300", sport_id=seeded["football"].id,
            team_id=seeded["home"].id, name="Roster Player",
        ))

        repo = TeamRosterRepo(seeded["conn"])
        repo.upsert(TeamRoster(
            id=None, team_id=seeded["home"].id, athlete_id=aid,
            position="GK", jersey="1", status="active", depth_rank=1,
            season="2025-26",
        ))
        seeded["conn"].commit()

        roster = repo.get_team_roster(seeded["home"].id, "2025-26")
        assert len(roster) == 1
        assert roster[0].position == "GK"


# ── TransactionRepo ─────────────────────────────────────────────────


class TestTransactionRepo:
    def test_insert_and_get(self, seeded):
        repo = TransactionRepo(seeded["conn"])
        repo.insert(Transaction(
            id=None, team_id=seeded["home"].id, athlete_id=None,
            transaction_type="sign", description="Signed new forward",
            transaction_date="2026-01-15",
        ))
        seeded["conn"].commit()

        txns = repo.get_for_team(seeded["home"].id)
        assert len(txns) == 1
        assert txns[0].transaction_type == "sign"

    def test_get_recent(self, seeded):
        repo = TransactionRepo(seeded["conn"])
        repo.insert(Transaction(
            id=None, team_id=seeded["home"].id, athlete_id=None,
            transaction_type="injury", description="Hamstring",
            transaction_date="2026-05-07",
        ))
        seeded["conn"].commit()
        recent = repo.get_recent(days=7)
        assert len(recent) == 1


# ── PowerIndexRepo ──────────────────────────────────────────────────


class TestPowerIndexRepo:
    def test_upsert_and_get(self, seeded):
        repo = PowerIndexRepo(seeded["conn"])
        repo.upsert(PowerIndex(
            id=None, team_id=seeded["home"].id, sport_id=seeded["football"].id,
            season="2025-26", rating=82.5, offensive_rating=85.0,
            defensive_rating=80.0, rank=3,
        ))
        seeded["conn"].commit()

        entries = repo.get_for_team(seeded["home"].id)
        assert len(entries) == 1
        assert entries[0].rating == 82.5

    def test_get_sport_rankings(self, seeded):
        repo = PowerIndexRepo(seeded["conn"])
        repo.upsert(PowerIndex(
            id=None, team_id=seeded["home"].id, sport_id=seeded["football"].id,
            season="2025-26", rating=82.5, rank=1,
        ))
        repo.upsert(PowerIndex(
            id=None, team_id=seeded["away"].id, sport_id=seeded["football"].id,
            season="2025-26", rating=78.0, rank=2,
        ))
        seeded["conn"].commit()

        rankings = repo.get_sport_rankings(seeded["football"].id, "2025-26")
        assert len(rankings) == 2
        assert rankings[0].rank == 1
