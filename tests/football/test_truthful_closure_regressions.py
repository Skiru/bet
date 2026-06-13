# ruff: noqa: E501

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime

import pytest

from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
from bet.db.models import Fixture
from bet.db.observation_models import create_observation, create_projection
from bet.db.repositories import FixtureCapabilityRepo, SportRepo
from bet.db.schema import init_db
from bet.enrichment.capability_router import Capability
from bet.stats import enrichment
from bet.stats.enrichment import (
    build_football_fixture_snapshot,
    enrich_fixtures,
    get_fixture_scoped_form_snapshot,
    get_standings_snapshot,
)


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    SportRepo(conn).seed_defaults()

    football = conn.execute("SELECT id FROM sports WHERE name = 'football'").fetchone()[0]
    conn.execute("INSERT INTO teams (id, name, sport_id) VALUES (1, 'Arsenal', ?)", (football,))
    conn.execute("INSERT INTO teams (id, name, sport_id) VALUES (2, 'Chelsea', ?)", (football,))
    conn.execute(
        "INSERT INTO competitions (id, sport_id, name, country, season) VALUES (1, ?, 'Premier League', 'England', '2026')",
        (football,),
    )
    kickoff = "2026-05-24T15:00:00+00:00"
    conn.execute(
        """INSERT INTO fixtures
           (id, sport_id, competition_id, home_team_id, away_team_id, kickoff, status, external_id, source, fetched_at)
           VALUES (1, ?, 1, 1, 2, ?, 'scheduled', 'api-1001', 'api-football', ?)""",
        (football, kickoff, datetime.now(UTC).isoformat()),
    )
    conn.execute(
        """INSERT INTO fixture_sources (fixture_id, source, external_id, confidence, raw_data, fetched_at)
           VALUES (1, 'api-football', '1001', 1.0, '{"provider_participant_ids":{"home":"501","away":"502"},"evidence_bundle_id":"api-bundle"}', ?)""",
        (datetime.now(UTC).isoformat(),),
    )
    conn.commit()
    yield conn
    conn.close()


def test_save_observation_is_append_only_for_changed_evidence(db_conn):
    repo = FixtureCapabilityRepo(db_conn)
    first = create_observation(
        canonical_fixture_id=1,
        team_id=1,
        capability=Capability.CURRENT_RECENT_FORM.value,
        source="espn-football",
        request_identity="GET https://example.test/form?team=1",
        status="SUCCESS",
        valid_at="2026-05-24T15:00:00+00:00",
        evidence_bundle_id="bundle-a",
        payload_sha256="hash-a",
        payload_json='{"stats":{"corners":{"l10_avg":6.2}}}',
    )
    duplicate = create_observation(
        canonical_fixture_id=1,
        team_id=1,
        capability=Capability.CURRENT_RECENT_FORM.value,
        source="espn-football",
        request_identity="GET https://example.test/form?team=1",
        status="SUCCESS",
        valid_at="2026-05-24T15:00:00+00:00",
        evidence_bundle_id="bundle-a",
        payload_sha256="hash-a",
        payload_json='{"stats":{"corners":{"l10_avg":6.2}}}',
    )
    changed = create_observation(
        canonical_fixture_id=1,
        team_id=1,
        capability=Capability.CURRENT_RECENT_FORM.value,
        source="espn-football",
        request_identity="GET https://example.test/form?team=1",
        status="SUCCESS",
        valid_at="2026-05-24T15:00:00+00:00",
        evidence_bundle_id="bundle-b",
        payload_sha256="hash-b",
        payload_json='{"stats":{"corners":{"l10_avg":7.1}}}',
    )

    first_id = repo.save_observation(first)
    duplicate_id = repo.save_observation(duplicate)
    changed_id = repo.save_observation(changed)

    assert first_id == duplicate_id
    assert changed_id != first_id
    assert len(repo.get_observations_for_fixture(1, Capability.CURRENT_RECENT_FORM.value)) == 2


def test_fixture_scoped_form_snapshot_returns_normalized_values_and_uses_stat_key(db_conn):
    repo = FixtureCapabilityRepo(db_conn)
    obs = create_observation(
        canonical_fixture_id=1,
        team_id=1,
        capability=Capability.CURRENT_RECENT_FORM.value,
        source="espn-football",
        request_identity="GET https://example.test/form?team=1",
        status="SUCCESS",
        valid_at="2026-05-24T15:00:00+00:00",
        evidence_bundle_id="bundle-form",
        payload_sha256="hash-form",
        payload_json='{"stats":{"corners":{"l10_values":[8,7,6],"l5_values":[8,7,6],"l10_avg":7.0,"l5_avg":7.0,"trend":"up"},"shots":{"l10_values":[14,12,10],"l5_values":[14,12,10],"l10_avg":12.0,"l5_avg":12.0,"trend":"stable"}}}',
    )
    obs_id = repo.save_observation(obs)
    repo.save_projection(
        create_projection(
            canonical_fixture_id=1,
            team_id=1,
            capability=Capability.CURRENT_RECENT_FORM.value,
            analysis_cutoff_at="2026-05-24T15:00:00+00:00",
            selected_source="espn-football",
            selected_status="SUCCESS",
            selected_observation_id=obs_id,
        )
    )

    corners = get_fixture_scoped_form_snapshot(db_conn, 1, 1, "2026-05-24T15:00:00+00:00", "corners")
    shots = get_fixture_scoped_form_snapshot(db_conn, 1, 1, "2026-05-24T15:00:00+00:00", "shots")
    missing = get_fixture_scoped_form_snapshot(db_conn, 1, 1, "2026-05-24T15:00:00+00:00", "fouls")

    assert corners["l10_avg"] == 7.0
    assert shots["l10_avg"] == 12.0
    assert missing["value"] == "UNKNOWN"


def test_enrich_fixtures_wires_capability_router_into_production_path(db_conn, monkeypatch):
    def fake_try_espn_fetch(team, sport, stat_keys, db_conn, fixture_contexts=None):
        del sport, stat_keys, db_conn, fixture_contexts
        return SourceOperationResult(
            SourceResultStatus.SUCCESS,
            value={
                "payload": {
                    "team_id": team.id,
                    "source": "espn-football",
                    "source_event_ids": ["espn-football:740968"],
                    "stats": {
                        "corners": {
                            "l10_values": [8, 7, 6],
                            "l5_values": [8, 7, 6],
                            "l10_avg": 7.0,
                            "l5_avg": 7.0,
                            "trend": "stable",
                        }
                    },
                },
                "native_ids": {"fixture_id": "740968", "team_id": f"espn-{team.id}"},
            },
            bundle_id=f"bundle-{team.id}",
        )

    monkeypatch.setattr(enrichment, "_try_espn_fetch", fake_try_espn_fetch)
    monkeypatch.setattr(
        enrichment,
        "_try_api_sports_fetch",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fallback should not run")),
    )

    fixture = Fixture(
        id=1,
        sport_id=1,
        competition_id=1,
        home_team_id=1,
        away_team_id=2,
        kickoff="2026-05-24T15:00:00+00:00",
        status="scheduled",
        external_id="api-1001",
        source="api-football",
        fetched_at=datetime.now(UTC).isoformat(),
    )
    result = asyncio.run(enrich_fixtures([fixture], db_conn, max_age_hours=0))
    repo = FixtureCapabilityRepo(db_conn)
    snapshot = repo.get_snapshot_for_analysis(1, 1, Capability.CURRENT_RECENT_FORM.value, "2026-05-24T15:00:00+00:00")

    assert result["fetched"] == 2
    assert snapshot["source"] == "espn-football"
    assert snapshot["payload"]["stats"]["corners"]["l10_avg"] == 7.0


def test_standings_snapshot_uses_fixture_team_scope_and_linked_observation(db_conn):
    repo = FixtureCapabilityRepo(db_conn)
    obs = create_observation(
        canonical_fixture_id=1,
        team_id=1,
        capability=Capability.STANDINGS_COMPETITION_CONTEXT.value,
        source="espn-football",
        request_identity="GET https://example.test/standings",
        status="SUCCESS",
        valid_at="2026-05-24T15:00:00+00:00",
        evidence_bundle_id="bundle-standings",
        payload_sha256="hash-standings",
        payload_json='{"competition_name":"Premier League","selected_team":{"team_id":"101","rank":1},"standings":[{"team_id":"101","rank":1}]}',
    )
    obs_id = repo.save_observation(obs)
    repo.save_projection(
        create_projection(
            canonical_fixture_id=1,
            team_id=1,
            capability=Capability.STANDINGS_COMPETITION_CONTEXT.value,
            analysis_cutoff_at="2026-05-24T15:00:00+00:00",
            selected_source="espn-football",
            selected_status="SUCCESS",
            selected_observation_id=obs_id,
        )
    )

    snapshot = get_standings_snapshot(
        db_conn,
        analysis_cutoff_at="2026-05-24T15:00:00+00:00",
        canonical_fixture_id=1,
        team_id=1,
    )

    assert snapshot is not None
    assert snapshot["observation_id"] == obs_id
    assert snapshot["payload"]["selected_team"]["rank"] == 1


def test_build_football_fixture_snapshot_reads_normalized_downstream_payloads(db_conn, monkeypatch):
    monkeypatch.setattr(
        enrichment,
        "_resolve_cross_provider_identity",
        lambda *args, **kwargs: type("Resolution", (), {"selected_status": SourceResultStatus.SUCCESS, "selected_value": {}})(),
    )
    monkeypatch.setattr(
        enrichment,
        "_resolve_football_recent_form",
        lambda team, **kwargs: type("Resolution", (), {"selected_status": SourceResultStatus.SUCCESS, "selected_value": {"stats": {"corners": {"l10_avg": float(team.id)}}}})(),
    )
    monkeypatch.setattr(
        enrichment,
        "_resolve_standings_for_fixture",
        lambda db_conn, canonical_fixture_id, team_id, analysis_cutoff_at: SourceOperationResult(SourceResultStatus.SUCCESS, value={"team_id": team_id}),
    )
    monkeypatch.setattr(
        enrichment,
        "_resolve_h2h_for_fixture",
        lambda *args, **kwargs: SourceOperationResult(SourceResultStatus.SUCCESS, value={"meeting_count": 3}),
    )
    monkeypatch.setattr(
        enrichment,
        "_resolve_fixture_statistics_for_fixture",
        lambda *args, **kwargs: SourceOperationResult(SourceResultStatus.NOT_PUBLISHED_YET, value=None),
    )

    repo = FixtureCapabilityRepo(db_conn)
    for capability, team_id, payload in (
        (Capability.CROSS_PROVIDER_IDENTITY.value, 1, {"espn": {"fixture_id": "740968"}}),
        (Capability.CURRENT_RECENT_FORM.value, 1, {"stats": {"corners": {"l10_avg": 1.0}}}),
        (Capability.CURRENT_RECENT_FORM.value, 2, {"stats": {"corners": {"l10_avg": 2.0}}}),
        (Capability.STANDINGS_COMPETITION_CONTEXT.value, 1, {"selected_team": {"rank": 1}}),
        (Capability.STANDINGS_COMPETITION_CONTEXT.value, 2, {"selected_team": {"rank": 2}}),
        (Capability.H2H_HEAD_TO_HEAD.value, 1, {"meeting_count": 3}),
    ):
        obs = create_observation(
            canonical_fixture_id=1,
            team_id=team_id,
            capability=capability,
            source="test-source",
            request_identity=f"GET https://example.test/{capability}/{team_id}",
            status="SUCCESS",
            valid_at="2026-05-24T15:00:00+00:00",
            evidence_bundle_id=f"bundle-{capability}-{team_id}",
            payload_sha256=f"hash-{capability}-{team_id}",
            payload_json=str(payload).replace("'", '"'),
        )
        obs_id = repo.save_observation(obs)
        repo.save_projection(
            create_projection(
                canonical_fixture_id=1,
                team_id=team_id,
                capability=capability,
                analysis_cutoff_at="2026-05-24T15:00:00+00:00",
                selected_source="test-source",
                selected_status="SUCCESS",
                selected_observation_id=obs_id,
            )
        )

    snapshot = build_football_fixture_snapshot(db_conn, 1, "2026-05-24T15:00:00+00:00")

    assert snapshot["teams"]["home"]["recent_form"]["stats"]["corners"]["l10_avg"] == 1.0
    assert snapshot["teams"]["away"]["standings"]["selected_team"]["rank"] == 2
    assert snapshot["cross_provider_identity"]["payload"]["espn"]["fixture_id"] == "740968"
