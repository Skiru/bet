"""End-to-end football workflow test.

Tests the complete production path:
production discovery -> canonical fixture -> provider source mappings
-> typed capability router -> source observations -> point-in-time selected projections
-> fixture-scoped snapshot -> downstream football analysis read
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from bet.db.repositories import (
    FixtureCapabilityRepo,
    SportRepo,
)
from bet.db.schema import init_db, migrate
from bet.enrichment.capability_router import Capability
from bet.stats.enrichment import (
    enrich_standings,
    get_fixture_scoped_form_snapshot,
    get_standings_snapshot,
)


class TestEndToEndFootballWorkflow:
    """Test complete football enrichment workflow."""

    @pytest.fixture
    def db_conn(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        conn.execute("PRAGMA foreign_keys = OFF")
        migrate(conn, 15, 16)
        SportRepo(conn).seed_defaults()
        yield conn
        conn.close()

    @pytest.fixture
    def sample_fixture(self, db_conn):
        """Create a sample fixture for testing."""
        sport_repo = SportRepo(db_conn)

        # Get football sport
        sport = sport_repo.get_by_name("football")
        assert sport is not None

        # Create teams
        db_conn.execute(
            "INSERT INTO teams (id, name, sport_id) VALUES (1, 'Arsenal', ?)",
            (sport.id,),
        )
        db_conn.execute(
            "INSERT INTO teams (id, name, sport_id) VALUES (2, 'Chelsea', ?)",
            (sport.id,),
        )

        # Create competition
        db_conn.execute(
            "INSERT INTO competitions (id, sport_id, name, country) "
            "VALUES (1, ?, 'Premier League', 'England')",
            (sport.id,),
        )

        # Create fixture
        kickoff = "2026-06-12T18:00:00+00:00"
        db_conn.execute(
            "INSERT INTO fixtures (id, sport_id, competition_id, home_team_id, "
            "away_team_id, kickoff, status, fetched_at) "
            "VALUES (1, ?, 1, 1, 2, ?, 'scheduled', ?)",
            (sport.id, kickoff, datetime.now(UTC).isoformat()),
        )

        # Create fixture source mappings
        db_conn.execute(
            "INSERT INTO fixture_sources (id, fixture_id, source, external_id, "
            "confidence, fetched_at) VALUES (1, 1, 'espn', '740968', 1.0, ?)",
            (datetime.now(UTC).isoformat(),),
        )

        db_conn.commit()

        return {
            "fixture_id": 1,
            "home_team_id": 1,
            "away_team_id": 2,
            "kickoff": kickoff,
            "competition_name": "Premier League",
        }

    def test_fixture_scoped_snapshot_read(self, db_conn, sample_fixture):
        """Test reading fixture-scoped snapshot for downstream analysis."""
        cap_repo = FixtureCapabilityRepo(db_conn)

        # Create observation
        from bet.db.observation_models import create_observation, create_projection

        obs = create_observation(
            canonical_fixture_id=sample_fixture["fixture_id"],
            team_id=sample_fixture["home_team_id"],
            capability=Capability.CURRENT_RECENT_FORM.value,
            source="espn",
            request_identity="GET https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/teams/123",
            status="SUCCESS",
            valid_at=sample_fixture["kickoff"],
            evidence_bundle_id="bundle123",
            native_fixture_id="740968",
            native_team_id="123",
        )
        obs_id = cap_repo.save_observation(obs)

        # Verify observation was saved
        assert obs_id > 0, "Observation ID should be > 0"

        # Create projection
        proj = create_projection(
            canonical_fixture_id=sample_fixture["fixture_id"],
            team_id=sample_fixture["home_team_id"],
            capability=Capability.CURRENT_RECENT_FORM.value,
            analysis_cutoff_at=sample_fixture["kickoff"],
            selected_source="espn",
            selected_status="SUCCESS",
            selected_observation_id=obs_id,
        )
        proj_id = cap_repo.save_projection(proj)

        # Verify projection was saved
        assert proj_id > 0, "Projection ID should be > 0"

        # Read snapshot
        snapshot = get_fixture_scoped_form_snapshot(
            db_conn=db_conn,
            canonical_fixture_id=sample_fixture["fixture_id"],
            team_id=sample_fixture["home_team_id"],
            analysis_cutoff_at=sample_fixture["kickoff"],
            stat_key="corners",
        )

        assert snapshot is not None
        assert snapshot["status"] == "SUCCESS"
        assert snapshot["source"] == "espn"
        assert snapshot["evidence_bundle_id"] == "bundle123"
        assert snapshot["native_ids"]["fixture_id"] == "740968"
        assert snapshot["native_ids"]["team_id"] == "123"
        assert snapshot["staleness"] is False

    def test_two_fixtures_isolated_snapshots(self, db_conn, sample_fixture):
        """Test that two fixtures for same team return isolated snapshots."""
        cap_repo = FixtureCapabilityRepo(db_conn)

        from bet.db.observation_models import create_observation, create_projection

        # Fixture 1
        kickoff1 = "2026-06-12T18:00:00+00:00"
        obs1 = create_observation(
            canonical_fixture_id=1,
            team_id=1,
            capability=Capability.CURRENT_RECENT_FORM.value,
            source="espn",
            request_identity="GET https://example.com/1",
            status="SUCCESS",
            valid_at=kickoff1,
            evidence_bundle_id="bundle1",
        )
        obs1_id = cap_repo.save_observation(obs1)

        proj1 = create_projection(
            canonical_fixture_id=1,
            team_id=1,
            capability=Capability.CURRENT_RECENT_FORM.value,
            analysis_cutoff_at=kickoff1,
            selected_source="espn",
            selected_status="SUCCESS",
            selected_observation_id=obs1_id,
        )
        cap_repo.save_projection(proj1)

        # Fixture 2 (different kickoff)
        kickoff2 = "2026-06-19T18:00:00+00:00"
        db_conn.execute(
            "INSERT INTO fixtures (id, sport_id, competition_id, home_team_id, "
            "away_team_id, kickoff, status, fetched_at) "
            "VALUES (2, 1, 1, 1, 2, ?, 'scheduled', ?)",
            (kickoff2, datetime.now(UTC).isoformat()),
        )
        db_conn.commit()

        obs2 = create_observation(
            canonical_fixture_id=2,
            team_id=1,
            capability=Capability.CURRENT_RECENT_FORM.value,
            source="espn",
            request_identity="GET https://example.com/2",
            status="SUCCESS",
            valid_at=kickoff2,
            evidence_bundle_id="bundle2",
        )
        obs2_id = cap_repo.save_observation(obs2)

        proj2 = create_projection(
            canonical_fixture_id=2,
            team_id=1,
            capability=Capability.CURRENT_RECENT_FORM.value,
            analysis_cutoff_at=kickoff2,
            selected_source="espn",
            selected_status="SUCCESS",
            selected_observation_id=obs2_id,
        )
        cap_repo.save_projection(proj2)

        # Read snapshots - should be isolated
        snapshot1 = get_fixture_scoped_form_snapshot(
            db_conn=db_conn,
            canonical_fixture_id=1,
            team_id=1,
            analysis_cutoff_at=kickoff1,
            stat_key="corners",
        )
        snapshot2 = get_fixture_scoped_form_snapshot(
            db_conn=db_conn,
            canonical_fixture_id=2,
            team_id=1,
            analysis_cutoff_at=kickoff2,
            stat_key="corners",
        )

        assert snapshot1["evidence_bundle_id"] == "bundle1"
        assert snapshot2["evidence_bundle_id"] == "bundle2"
        assert snapshot1["observation_id"] != snapshot2["observation_id"]

    def test_standings_enrichment_mock(self, db_conn, sample_fixture, monkeypatch):
        """Test standings enrichment with mocked ESPN response."""
        # Mock ESPN client
        from bet.api_clients.base_client import (
            SourceOperationResult,
            SourceResultStatus,
        )

        def mock_get_standings_result(self):
            return SourceOperationResult(
                SourceResultStatus.SUCCESS,
                value=[
                    {"team_id": "123", "team_name": "Arsenal", "rank": 1, "points": 50},
                    {"team_id": "456", "team_name": "Chelsea", "rank": 2, "points": 45},
                ],
                bundle_id="standings_bundle_123",
            )

        def mock_is_available(self):
            return True

        def mock_init(self, *args, **kwargs):
            self.sport = "football"
            self.league = "eng.1"
            self.api_name = "espn-football"
            self._espn_sport = "soccer"

        # Patch ESPNClient methods
        from bet.api_clients import espn
        monkeypatch.setattr(espn.ESPNClient, "__init__", mock_init)
        monkeypatch.setattr(
            espn.ESPNClient, "get_standings_result", mock_get_standings_result
        )
        monkeypatch.setattr(espn.ESPNClient, "is_available", mock_is_available)

        # Run enrichment
        result = enrich_standings(
            db_conn=db_conn,
            sport="football",
            competition_name="Premier League",
            analysis_cutoff_at=sample_fixture["kickoff"],
        )

        assert result.status == SourceResultStatus.SUCCESS
        assert result.value is not None
        assert "standings" in result.value
        assert len(result.value["standings"]) == 2

    def test_standings_snapshot_read(self, db_conn, sample_fixture):
        """Test reading standings snapshot for downstream analysis."""
        cap_repo = FixtureCapabilityRepo(db_conn)

        from bet.db.observation_models import create_observation, create_projection

        # Create season-scoped observation (fixture_id=0, team_id=0)
        obs = create_observation(
            canonical_fixture_id=0,
            team_id=0,
            capability=Capability.STANDINGS_COMPETITION_CONTEXT.value,
            source="espn",
            request_identity="GET https://site.api.espn.com/apis/v2/sports/soccer/eng.1/standings",
            status="SUCCESS",
            valid_at=sample_fixture["kickoff"],
            evidence_bundle_id="standings_bundle",
        )
        cap_repo.save_observation(obs)

        proj = create_projection(
            canonical_fixture_id=0,
            team_id=0,
            capability=Capability.STANDINGS_COMPETITION_CONTEXT.value,
            analysis_cutoff_at=sample_fixture["kickoff"],
            selected_source="espn",
            selected_status="SUCCESS",
        )
        cap_repo.save_projection(proj)

        # Read snapshot
        snapshot = get_standings_snapshot(
            db_conn=db_conn,
            competition_name="Premier League",
            analysis_cutoff_at=sample_fixture["kickoff"],
        )

        assert snapshot is not None
        assert snapshot["status"] == "SUCCESS"
        assert snapshot["source"] == "espn"

    def test_missing_capability_returns_none(self, db_conn, sample_fixture):
        """Test that missing capability returns None, not stale data."""
        snapshot = get_fixture_scoped_form_snapshot(
            db_conn=db_conn,
            canonical_fixture_id=999,
            team_id=999,
            analysis_cutoff_at="2026-06-12T18:00:00+00:00",
            stat_key="corners",
        )

        assert snapshot is None

    def test_fallback_metadata_preserved(self, db_conn, sample_fixture):
        """Test that fallback metadata is preserved in snapshot."""
        cap_repo = FixtureCapabilityRepo(db_conn)

        from bet.db.observation_models import create_observation, create_projection

        # Primary failed
        obs1 = create_observation(
            canonical_fixture_id=sample_fixture["fixture_id"],
            team_id=sample_fixture["home_team_id"],
            capability=Capability.CURRENT_RECENT_FORM.value,
            source="api-football",
            request_identity="GET https://api-football/1",
            status="PLAN_RESTRICTED",
            valid_at=sample_fixture["kickoff"],
        )
        cap_repo.save_observation(obs1)

        # Fallback succeeded
        obs2 = create_observation(
            canonical_fixture_id=sample_fixture["fixture_id"],
            team_id=sample_fixture["home_team_id"],
            capability=Capability.CURRENT_RECENT_FORM.value,
            source="espn",
            request_identity="GET https://espn/1",
            status="SUCCESS",
            valid_at=sample_fixture["kickoff"],
            evidence_bundle_id="fallback_bundle",
        )
        obs2_id = cap_repo.save_observation(obs2)

        proj = create_projection(
            canonical_fixture_id=sample_fixture["fixture_id"],
            team_id=sample_fixture["home_team_id"],
            capability=Capability.CURRENT_RECENT_FORM.value,
            analysis_cutoff_at=sample_fixture["kickoff"],
            selected_source="espn",
            selected_status="SUCCESS",
            selected_observation_id=obs2_id,
            primary_source="api-football",
            primary_status="PLAN_RESTRICTED",
            fallback_reason="primary_plan_restricted",
        )
        cap_repo.save_projection(proj)

        # Read snapshot
        snapshot = get_fixture_scoped_form_snapshot(
            db_conn=db_conn,
            canonical_fixture_id=sample_fixture["fixture_id"],
            team_id=sample_fixture["home_team_id"],
            analysis_cutoff_at=sample_fixture["kickoff"],
            stat_key="corners",
        )

        assert snapshot is not None
        assert snapshot["primary_source"] == "api-football"
        assert snapshot["primary_status"] == "PLAN_RESTRICTED"
        assert snapshot["fallback_reason"] == "primary_plan_restricted"
