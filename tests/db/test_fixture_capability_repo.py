"""Tests for FixtureCapabilityRepo - fixture-scoped observations and projections."""

from __future__ import annotations

import sqlite3

import pytest

from bet.db.observation_models import (
    create_observation,
    create_projection,
)
from bet.db.repositories import FixtureCapabilityRepo, SportRepo
from bet.db.schema import init_db, migrate


class TestFixtureCapabilityRepo:
    """Test fixture-scoped capability repository."""

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

    def test_save_observation(self, db_conn):
        """Save observation to database."""
        repo = FixtureCapabilityRepo(db_conn)
        obs = create_observation(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            source="espn",
            request_identity="GET https://example.com",
            status="SUCCESS",
            valid_at="2026-06-12T18:00:00+00:00",
        )
        obs_id = repo.save_observation(obs)
        assert obs_id > 0

    def test_get_observation(self, db_conn):
        """Get observation by identity key."""
        repo = FixtureCapabilityRepo(db_conn)
        obs = create_observation(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            source="espn",
            request_identity="GET https://example.com",
            status="SUCCESS",
            valid_at="2026-06-12T18:00:00+00:00",
            evidence_bundle_id="bundle123",
        )
        repo.save_observation(obs)

        retrieved = repo.get_observation(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            source="espn",
            valid_at="2026-06-12T18:00:00+00:00",
        )
        assert retrieved is not None
        assert retrieved.evidence_bundle_id == "bundle123"

    def test_save_projection(self, db_conn):
        """Save projection to database."""
        repo = FixtureCapabilityRepo(db_conn)
        proj = create_projection(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            analysis_cutoff_at="2026-06-12T18:00:00+00:00",
            selected_source="espn",
            selected_status="SUCCESS",
            selected_observation_id=1,
        )
        proj_id = repo.save_projection(proj)
        assert proj_id > 0

    def test_get_projection(self, db_conn):
        """Get projection by identity key."""
        repo = FixtureCapabilityRepo(db_conn)

        # First save an observation
        obs = create_observation(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            source="espn",
            request_identity="GET https://example.com",
            status="SUCCESS",
            valid_at="2026-06-12T18:00:00+00:00",
            evidence_bundle_id="bundle123",
        )
        obs_id = repo.save_observation(obs)

        # Then save a projection
        proj = create_projection(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            analysis_cutoff_at="2026-06-12T18:00:00+00:00",
            selected_source="espn",
            selected_status="SUCCESS",
            selected_observation_id=obs_id,
        )
        repo.save_projection(proj)

        retrieved = repo.get_projection(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            analysis_cutoff_at="2026-06-12T18:00:00+00:00",
        )
        assert retrieved is not None
        assert retrieved.selected_source == "espn"
        assert retrieved.selected_observation_id == obs_id

    def test_get_snapshot_for_analysis(self, db_conn):
        """Get fixture-scoped snapshot for downstream analysis."""
        repo = FixtureCapabilityRepo(db_conn)

        # Save observation
        obs = create_observation(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            source="espn",
            request_identity="GET https://example.com",
            status="SUCCESS",
            valid_at="2026-06-12T18:00:00+00:00",
            evidence_bundle_id="bundle123",
            native_fixture_id="ext123",
            native_team_id="team456",
        )
        obs_id = repo.save_observation(obs)

        # Save projection
        proj = create_projection(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            analysis_cutoff_at="2026-06-12T18:00:00+00:00",
            selected_source="espn",
            selected_status="SUCCESS",
            selected_observation_id=obs_id,
        )
        repo.save_projection(proj)

        # Get snapshot
        snapshot = repo.get_snapshot_for_analysis(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            analysis_cutoff_at="2026-06-12T18:00:00+00:00",
        )

        assert snapshot["status"] == "SUCCESS"
        assert snapshot["source"] == "espn"
        assert snapshot["observation_id"] == obs_id
        assert snapshot["evidence_bundle_id"] == "bundle123"
        assert snapshot["native_ids"]["fixture_id"] == "ext123"
        assert snapshot["native_ids"]["team_id"] == "team456"
        assert snapshot["staleness"] is False
        assert snapshot["value"] == "UNKNOWN"

    def test_get_snapshot_not_found(self, db_conn):
        """Get snapshot returns NOT_FOUND when no projection exists."""
        repo = FixtureCapabilityRepo(db_conn)

        snapshot = repo.get_snapshot_for_analysis(
            canonical_fixture_id=999,
            team_id=999,
            capability="current_recent_form",
            analysis_cutoff_at="2026-06-12T18:00:00+00:00",
        )

        assert snapshot["status"] == "NOT_FOUND"
        assert snapshot["value"] == "UNKNOWN"

    def test_two_fixtures_same_team_isolated(self, db_conn):
        """Two fixtures for same team with different cutoffs return isolated results."""
        repo = FixtureCapabilityRepo(db_conn)

        # Fixture 1, team 1, cutoff 1
        obs1 = create_observation(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            source="espn",
            request_identity="GET https://example.com/1",
            status="SUCCESS",
            valid_at="2026-06-12T18:00:00+00:00",
            evidence_bundle_id="bundle1",
        )
        obs1_id = repo.save_observation(obs1)

        proj1 = create_projection(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            analysis_cutoff_at="2026-06-12T18:00:00+00:00",
            selected_source="espn",
            selected_status="SUCCESS",
            selected_observation_id=obs1_id,
        )
        repo.save_projection(proj1)

        # Fixture 2, team 1, cutoff 2
        obs2 = create_observation(
            canonical_fixture_id=2,
            team_id=1,
            capability="current_recent_form",
            source="espn",
            request_identity="GET https://example.com/2",
            status="SUCCESS",
            valid_at="2026-06-12T20:00:00+00:00",
            evidence_bundle_id="bundle2",
        )
        obs2_id = repo.save_observation(obs2)

        proj2 = create_projection(
            canonical_fixture_id=2,
            team_id=1,
            capability="current_recent_form",
            analysis_cutoff_at="2026-06-12T20:00:00+00:00",
            selected_source="espn",
            selected_status="SUCCESS",
            selected_observation_id=obs2_id,
        )
        repo.save_projection(proj2)

        # Get snapshots - should be isolated
        snapshot1 = repo.get_snapshot_for_analysis(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            analysis_cutoff_at="2026-06-12T18:00:00+00:00",
        )
        snapshot2 = repo.get_snapshot_for_analysis(
            canonical_fixture_id=2,
            team_id=1,
            capability="current_recent_form",
            analysis_cutoff_at="2026-06-12T20:00:00+00:00",
        )

        assert snapshot1["evidence_bundle_id"] == "bundle1"
        assert snapshot2["evidence_bundle_id"] == "bundle2"
        assert snapshot1["observation_id"] != snapshot2["observation_id"]

    def test_projection_upsert(self, db_conn):
        """Projection upsert updates existing row."""
        repo = FixtureCapabilityRepo(db_conn)

        # First projection
        proj1 = create_projection(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            analysis_cutoff_at="2026-06-12T18:00:00+00:00",
            selected_source="espn",
            selected_status="SUCCESS",
        )
        repo.save_projection(proj1)

        # Second projection with same identity
        proj2 = create_projection(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            analysis_cutoff_at="2026-06-12T18:00:00+00:00",
            selected_source="api-football",
            selected_status="SUCCESS",
        )
        repo.save_projection(proj2)

        # Should have only one projection
        projections = repo.get_projections_for_fixture(1)
        assert len(projections) == 1
        assert projections[0].selected_source == "api-football"

    def test_fallback_metadata_preserved(self, db_conn):
        """Projection preserves fallback metadata."""
        repo = FixtureCapabilityRepo(db_conn)

        proj = create_projection(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            analysis_cutoff_at="2026-06-12T18:00:00+00:00",
            selected_source="espn",
            selected_status="SUCCESS",
            primary_source="api-football",
            primary_status="PLAN_RESTRICTED",
            fallback_reason="primary_plan_restricted",
        )
        repo.save_projection(proj)

        retrieved = repo.get_projection(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            analysis_cutoff_at="2026-06-12T18:00:00+00:00",
        )

        assert retrieved.primary_source == "api-football"
        assert retrieved.primary_status == "PLAN_RESTRICTED"
        assert retrieved.fallback_reason == "primary_plan_restricted"
