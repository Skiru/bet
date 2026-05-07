"""Unit tests for ScanResultRepo."""

import json
import sqlite3
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from bet.db.models import ScanResult, ScanRunStats
from bet.db.repositories import ScanResultRepo

SCHEMA_PATH = Path(__file__).parent.parent.parent / "src" / "bet" / "db" / "schema.sql"


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
def repo(db):
    return ScanResultRepo(db)


def _make_scan_result(sport="football", event_key="arsenal|chelsea", **kwargs):
    defaults = dict(
        id=None,
        betting_date="2026-05-07",
        sport=sport,
        source_domain="flashscore.com",
        event_key=event_key,
        home_team="Arsenal",
        away_team="Chelsea",
        competition="Premier League",
        kickoff="2026-05-07T15:00:00",
        raw_data={"odds": {"1": 1.85, "X": 3.40, "2": 4.20}},
        scan_timestamp="2026-05-07T08:00:00Z",
    )
    defaults.update(kwargs)
    return ScanResult(**defaults)


class TestBulkInsert:
    def test_inserts_multiple_results(self, repo, db):
        results = [
            _make_scan_result(event_key=f"team_a_{i}|team_b_{i}")
            for i in range(10)
        ]
        count = repo.bulk_insert(results)
        assert count == 10

        all_rows = repo.get_all_by_date("2026-05-07")
        assert len(all_rows) == 10

    def test_ignores_duplicates(self, repo, db):
        results = [_make_scan_result(), _make_scan_result()]
        count = repo.bulk_insert(results)
        assert count == 1

    def test_empty_list(self, repo):
        count = repo.bulk_insert([])
        assert count == 0


class TestUpsert:
    def test_inserts_new(self, repo, db):
        result = _make_scan_result()
        row_id = repo.upsert(result)
        assert row_id > 0

        fetched = repo.get_all_by_date("2026-05-07")
        assert len(fetched) == 1
        assert fetched[0].home_team == "Arsenal"

    def test_replaces_existing(self, repo, db):
        result = _make_scan_result()
        repo.upsert(result)

        updated = _make_scan_result(home_team="Arsenal FC")
        repo.upsert(updated)

        fetched = repo.get_all_by_date("2026-05-07")
        assert len(fetched) == 1
        assert fetched[0].home_team == "Arsenal FC"

    def test_preserves_raw_data(self, repo, db):
        data = {"corners": 11, "fouls": 22, "nested": {"key": "val"}}
        result = _make_scan_result(raw_data=data)
        repo.upsert(result)

        fetched = repo.get_all_by_date("2026-05-07")
        assert fetched[0].raw_data == data


class TestGetByDateAndSport:
    def test_filters_by_sport(self, repo, db):
        repo.upsert(_make_scan_result(sport="football", event_key="a|b"))
        repo.upsert(_make_scan_result(sport="tennis", event_key="c|d"))
        repo.upsert(_make_scan_result(sport="football", event_key="e|f"))

        football = repo.get_by_date_and_sport("2026-05-07", "football")
        assert len(football) == 2

        tennis = repo.get_by_date_and_sport("2026-05-07", "tennis")
        assert len(tennis) == 1

    def test_filters_by_date(self, repo, db):
        repo.upsert(_make_scan_result(betting_date="2026-05-07"))
        repo.upsert(_make_scan_result(betting_date="2026-05-06", event_key="x|y"))

        results = repo.get_by_date_and_sport("2026-05-07", "football")
        assert len(results) == 1


class TestDeleteByDate:
    def test_deletes_target_date_only(self, repo, db):
        repo.upsert(_make_scan_result(betting_date="2026-05-07", event_key="a|b"))
        repo.upsert(_make_scan_result(betting_date="2026-05-07", event_key="c|d"))
        repo.upsert(_make_scan_result(betting_date="2026-05-06", event_key="e|f"))

        deleted = repo.delete_by_date("2026-05-07")
        assert deleted == 2

        remaining = repo.get_all_by_date("2026-05-06")
        assert len(remaining) == 1


class TestRunStats:
    def test_record_and_retrieve(self, repo, db):
        stats = ScanRunStats(
            id=None,
            betting_date="2026-05-07",
            sport="football",
            scanner_group="football",
            events_found=45,
            sources_ok=8,
            sources_failed=2,
            deep_links_found=120,
            duration_seconds=185.3,
            validation_passed=True,
            gaps_description=["missing sofascore", "hltv timeout"],
            scan_timestamp="2026-05-07T08:05:00Z",
        )
        repo.record_run_stats(stats)

        fetched = repo.get_run_stats("2026-05-07")
        assert len(fetched) == 1
        assert fetched[0].sport == "football"
        assert fetched[0].events_found == 45
        assert fetched[0].sources_failed == 2
        assert fetched[0].duration_seconds == 185.3
        assert fetched[0].validation_passed is True
        assert fetched[0].gaps_description == ["missing sofascore", "hltv timeout"]

    def test_upsert_replaces(self, repo, db):
        stats1 = ScanRunStats(
            id=None,
            betting_date="2026-05-07",
            sport="tennis",
            scanner_group="tennis",
            events_found=10,
            scan_timestamp="2026-05-07T08:00:00Z",
        )
        repo.record_run_stats(stats1)

        stats2 = ScanRunStats(
            id=None,
            betting_date="2026-05-07",
            sport="tennis",
            scanner_group="tennis",
            events_found=15,
            sources_ok=4,
            scan_timestamp="2026-05-07T08:10:00Z",
        )
        repo.record_run_stats(stats2)

        fetched = repo.get_run_stats("2026-05-07")
        tennis = [s for s in fetched if s.sport == "tennis"]
        assert len(tennis) == 1
        assert tennis[0].events_found == 15
        assert tennis[0].sources_ok == 4
