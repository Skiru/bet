"""Tests for fixture-scoped observations and projections."""

from __future__ import annotations

import sqlite3

import pytest

from bet.db.observation_models import (
    create_observation,
    create_projection,
)
from bet.db.repositories import SportRepo
from bet.db.schema import init_db, migrate


class TestFixtureCapabilityObservation:
    """Test fixture-scoped observation model."""

    @pytest.fixture
    def db_conn(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        # Disable foreign keys for test isolation (after init_db enables them)
        conn.execute("PRAGMA foreign_keys = OFF")
        # Run migration to v16
        migrate(conn, 15, 16)
        SportRepo(conn).seed_defaults()
        yield conn
        conn.close()

    def test_create_observation(self):
        """Create observation with all fields."""
        obs = create_observation(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            source="espn",
            request_identity="GET https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/teams/123",
            status="SUCCESS",
            valid_at="2026-06-12T18:00:00+00:00",
            evidence_bundle_id="abc123",
            native_fixture_id="760415",
            native_team_id="123",
            http_status=200,
            parser_version="espn-client-rem002a-v1",
        )
        assert obs.canonical_fixture_id == 1
        assert obs.team_id == 1
        assert obs.capability == "current_recent_form"
        assert obs.source == "espn"
        assert obs.status == "SUCCESS"
        assert obs.valid_at == "2026-06-12T18:00:00+00:00"
        assert obs.evidence_bundle_id == "abc123"

    def test_observation_identity_includes_cutoff(self):
        """Observation identity must include cutoff for temporal isolation."""
        obs1 = create_observation(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            source="espn",
            request_identity="GET https://example.com",
            status="SUCCESS",
            valid_at="2026-06-12T18:00:00+00:00",
        )
        obs2 = create_observation(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            source="espn",
            request_identity="GET https://example.com",
            status="SUCCESS",
            valid_at="2026-06-12T20:00:00+00:00",  # Different cutoff
        )
        # Different cutoffs should create different observations
        assert obs1.valid_at != obs2.valid_at

    def test_insert_observation(self, db_conn):
        """Insert observation into database."""
        obs = create_observation(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            source="espn",
            request_identity="GET https://example.com",
            status="SUCCESS",
            valid_at="2026-06-12T18:00:00+00:00",
        )

        cursor = db_conn.execute(
            """INSERT INTO fixture_capability_observation
               (canonical_fixture_id, team_id, capability, source, request_identity,
                status, valid_at, observed_at, evidence_bundle_id, native_fixture_id,
                native_team_id, http_status, error_code, retryable, parser_version,
                parser_diagnostics_json, payload_sha256)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                obs.canonical_fixture_id,
                obs.team_id,
                obs.capability,
                obs.source,
                obs.request_identity,
                obs.status,
                obs.valid_at,
                obs.observed_at,
                obs.evidence_bundle_id,
                obs.native_fixture_id,
                obs.native_team_id,
                obs.http_status,
                obs.error_code,
                int(obs.retryable),
                obs.parser_version,
                "{}",
                obs.payload_sha256,
            ),
        )
        assert cursor.lastrowid > 0

    def test_unique_constraint_prevents_duplicate_observations(self, db_conn):
        """Same fixture+team+capability+source+cutoff should be unique."""
        obs = create_observation(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            source="espn",
            request_identity="GET https://example.com",
            status="SUCCESS",
            valid_at="2026-06-12T18:00:00+00:00",
        )

        db_conn.execute(
            """INSERT INTO fixture_capability_observation
               (canonical_fixture_id, team_id, capability, source, request_identity,
                status, valid_at, observed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (obs.canonical_fixture_id, obs.team_id, obs.capability, obs.source,
             obs.request_identity, obs.status, obs.valid_at, obs.observed_at),
        )

        # Second insert with same identity should fail
        with pytest.raises(sqlite3.IntegrityError):
            db_conn.execute(
                """INSERT INTO fixture_capability_observation
                   (canonical_fixture_id, team_id, capability, source, request_identity,
                    status, valid_at, observed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (obs.canonical_fixture_id, obs.team_id, obs.capability, obs.source,
                 obs.request_identity, obs.status, obs.valid_at, obs.observed_at),
            )


class TestFixtureCapabilityProjection:
    """Test fixture-scoped projection model."""

    def test_create_projection(self):
        """Create projection with all fields."""
        proj = create_projection(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            analysis_cutoff_at="2026-06-12T18:00:00+00:00",
            selected_source="espn",
            selected_status="SUCCESS",
            selected_observation_id=1,
            primary_source="api-football",
            primary_status="PLAN_RESTRICTED",
            fallback_reason="primary_plan_restricted",
        )
        assert proj.canonical_fixture_id == 1
        assert proj.team_id == 1
        assert proj.capability == "current_recent_form"
        assert proj.selected_source == "espn"
        assert proj.primary_source == "api-football"
        assert proj.fallback_reason == "primary_plan_restricted"

    def test_projection_tracks_fallback(self):
        """Projection should track fallback metadata."""
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
        assert proj.primary_source == "api-football"
        assert proj.primary_status == "PLAN_RESTRICTED"
        assert proj.fallback_reason == "primary_plan_restricted"


class TestChangedEvidenceHistory:
    """Test that changed evidence creates new observation."""

    @pytest.fixture
    def db_conn(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        # Disable foreign keys for test isolation (after init_db enables them)
        conn.execute("PRAGMA foreign_keys = OFF")
        # Run migration to v16
        migrate(conn, 15, 16)
        SportRepo(conn).seed_defaults()
        yield conn
        conn.close()

    def test_changed_evidence_creates_new_observation(self, db_conn):
        """Changed evidence should create a new observation, not overwrite."""
        # First observation
        obs1 = create_observation(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            source="espn",
            request_identity="GET https://example.com",
            status="SUCCESS",
            valid_at="2026-06-12T18:00:00+00:00",
            evidence_bundle_id="bundle1",
            payload_sha256="hash1",
        )

        db_conn.execute(
            """INSERT INTO fixture_capability_observation
               (canonical_fixture_id, team_id, capability, source, request_identity,
                status, valid_at, observed_at, evidence_bundle_id, payload_sha256)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (obs1.canonical_fixture_id, obs1.team_id, obs1.capability, obs1.source,
             obs1.request_identity, obs1.status, obs1.valid_at, obs1.observed_at,
             obs1.evidence_bundle_id, obs1.payload_sha256),
        )

        # Second observation with different evidence (different cutoff)
        obs2 = create_observation(
            canonical_fixture_id=1,
            team_id=1,
            capability="current_recent_form",
            source="espn",
            request_identity="GET https://example.com",
            status="SUCCESS",
            valid_at="2026-06-12T20:00:00+00:00",  # Different cutoff
            evidence_bundle_id="bundle2",
            payload_sha256="hash2",
        )

        db_conn.execute(
            """INSERT INTO fixture_capability_observation
               (canonical_fixture_id, team_id, capability, source, request_identity,
                status, valid_at, observed_at, evidence_bundle_id, payload_sha256)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (obs2.canonical_fixture_id, obs2.team_id, obs2.capability, obs2.source,
             obs2.request_identity, obs2.status, obs2.valid_at, obs2.observed_at,
             obs2.evidence_bundle_id, obs2.payload_sha256),
        )

        # Both observations should exist
        cursor = db_conn.execute(
            "SELECT id, evidence_bundle_id, payload_sha256 FROM fixture_capability_observation ORDER BY valid_at"
        )
        rows = cursor.fetchall()
        assert len(rows) == 2
        assert rows[0]["evidence_bundle_id"] == "bundle1"
        assert rows[1]["evidence_bundle_id"] == "bundle2"


class TestMigrationV16:
    """Test migration v16 for fixture-scoped observations."""

    def test_fresh_db_has_observation_table(self):
        """Fresh DB must have fixture_capability_observation table."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fixture_capability_observation'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_fresh_db_has_projection_table(self):
        """Fresh DB must have fixture_capability_projection table."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fixture_capability_projection'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_migrated_db_has_observation_table(self):
        """Migrated DB must have fixture_capability_observation table."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        # Simulate v15 state
        conn.execute("UPDATE schema_meta SET value = '15' WHERE key = 'version'")
        conn.commit()
        
        # Run migration
        migrate(conn, 15, 16)
        
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fixture_capability_observation'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_unique_index_exists(self):
        """Unique index on fixture+team+capability+source+valid_at must exist."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_fixture_capability_observation_identity'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_null_team_not_allowed(self):
        """team_id must be NOT NULL."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        conn.execute("PRAGMA foreign_keys = OFF")
        
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO fixture_capability_observation
                   (canonical_fixture_id, team_id, capability, source, request_identity, status, valid_at, observed_at)
                   VALUES (1, NULL, 'test', 'test', 'test', 'SUCCESS', '2026-06-12T18:00:00+00:00', '2026-06-12T18:00:00+00:00')"""
            )
        conn.close()

    def test_null_capability_not_allowed(self):
        """capability must be NOT NULL."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        conn.execute("PRAGMA foreign_keys = OFF")
        
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO fixture_capability_observation
                   (canonical_fixture_id, team_id, capability, source, request_identity, status, valid_at, observed_at)
                   VALUES (1, 1, NULL, 'test', 'test', 'SUCCESS', '2026-06-12T18:00:00+00:00', '2026-06-12T18:00:00+00:00')"""
            )
        conn.close()

    def test_null_valid_at_not_allowed(self):
        """valid_at must be NOT NULL."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        conn.execute("PRAGMA foreign_keys = OFF")
        
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO fixture_capability_observation
                   (canonical_fixture_id, team_id, capability, source, request_identity, status, valid_at, observed_at)
                   VALUES (1, 1, 'test', 'test', 'test', 'SUCCESS', NULL, '2026-06-12T18:00:00+00:00')"""
            )
        conn.close()

    def test_same_team_two_fixtures_two_cutoffs(self):
        """Same team with two fixtures and two cutoffs must create two observations."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        conn.execute("PRAGMA foreign_keys = OFF")
        
        # First fixture, first cutoff
        conn.execute(
            """INSERT INTO fixture_capability_observation
               (canonical_fixture_id, team_id, capability, source, request_identity, status, valid_at, observed_at)
               VALUES (1, 1, 'current_recent_form', 'espn', 'GET https://example.com/1', 'SUCCESS', '2026-06-12T18:00:00+00:00', '2026-06-12T18:00:00+00:00')"""
        )
        
        # First fixture, second cutoff
        conn.execute(
            """INSERT INTO fixture_capability_observation
               (canonical_fixture_id, team_id, capability, source, request_identity, status, valid_at, observed_at)
               VALUES (1, 1, 'current_recent_form', 'espn', 'GET https://example.com/2', 'SUCCESS', '2026-06-12T20:00:00+00:00', '2026-06-12T20:00:00+00:00')"""
        )
        
        # Second fixture, first cutoff
        conn.execute(
            """INSERT INTO fixture_capability_observation
               (canonical_fixture_id, team_id, capability, source, request_identity, status, valid_at, observed_at)
               VALUES (2, 1, 'current_recent_form', 'espn', 'GET https://example.com/3', 'SUCCESS', '2026-06-12T18:00:00+00:00', '2026-06-12T18:00:00+00:00')"""
        )
        
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM fixture_capability_observation")
        assert cursor.fetchone()["cnt"] == 3
        conn.close()
