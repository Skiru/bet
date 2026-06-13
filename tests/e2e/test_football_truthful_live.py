# ruff: noqa: E501, I001

from __future__ import annotations

import json
import os
import socket
import sqlite3
from pathlib import Path

import pytest
import requests
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from bet.api_clients import base_client
from bet.db.schema import init_db
from bet.discovery.coordinator import EventDiscoveryCoordinator
from bet.discovery.sources.api_football import APIFootballAdapter
from bet.integration import telemetry_wrapper
from bet.integration.evidence import build_replay_transport
from bet.scrapers.engine import Base
from bet.stats.enrichment import build_football_fixture_snapshot
def _block_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Unexpected outbound network access during replay")

    monkeypatch.setattr(socket, "create_connection", blocked)

    def blocked_connect(self, address):
        raise AssertionError(f"Unexpected socket connection during replay: {address}")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect, raising=True)
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Unexpected requests.get during replay")
        ),
    )
    try:
        import urllib3.util.connection

        monkeypatch.setattr(urllib3.util.connection, "create_connection", blocked)
    except Exception:
        pass


def _build_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    raw_conn = engine.raw_connection()
    try:
        raw_conn.row_factory = sqlite3.Row
        init_db(raw_conn)
    finally:
        raw_conn.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, factory()


def _select_target_fixture(conn) -> int:
    row = conn.execute(
        text(
            """SELECT f.id
               FROM fixtures f
               JOIN teams ht ON ht.id = f.home_team_id
               JOIN teams at ON at.id = f.away_team_id
               WHERE ht.name = 'Crystal Palace' AND at.name = 'Arsenal'
               ORDER BY f.id ASC
               LIMIT 1"""
        )
    ).fetchone()
    assert row is not None, "Real API-Football discovery did not persist Crystal Palace vs Arsenal"
    return int(row[0])


def _bundle_ids(conn) -> list[str]:
    bundle_ids = {
        row[0]
        for row in conn.execute(
            text("SELECT DISTINCT evidence_bundle_id FROM fixture_capability_observation WHERE evidence_bundle_id != ''")
        )
        if row[0]
    }
    for row in conn.execute(text("SELECT raw_data FROM fixture_sources WHERE raw_data IS NOT NULL AND raw_data != ''")):
        payload = json.loads(row[0])
        bundle_id = str(payload.get("evidence_bundle_id", "") or "")
        if bundle_id:
            bundle_ids.add(bundle_id)
    return sorted(bundle_ids)


def _domain_state(conn) -> dict:
    return {
        "fixtures": sorted(
            tuple(row)
            for row in conn.execute(
                text("SELECT id, external_id, home_team_id, away_team_id, kickoff FROM fixtures ORDER BY id")
            )
        ),
        "source_mappings": sorted(
            tuple(row)
            for row in conn.execute(
                text("SELECT fixture_id, source, external_id FROM fixture_sources ORDER BY fixture_id, source")
            )
        ),
        "observations": sorted(
            tuple(row)
            for row in conn.execute(
                text(
                    "SELECT canonical_fixture_id, team_id, capability, source, request_identity, evidence_bundle_id, valid_at, payload_sha256 "
                    "FROM fixture_capability_observation ORDER BY canonical_fixture_id, team_id, capability, source, valid_at, evidence_bundle_id"
                )
            )
        ),
        "projections": sorted(
            tuple(row)
            for row in conn.execute(
                text(
                    "SELECT canonical_fixture_id, team_id, capability, analysis_cutoff_at, selected_source, selected_status, selected_observation_id "
                    "FROM fixture_capability_projection ORDER BY canonical_fixture_id, team_id, capability, analysis_cutoff_at"
                )
            )
        ),
    }


def test_real_football_vertical_live_replay_and_idempotency(tmp_path, monkeypatch):
    if os.getenv("BET_RUN_TRUTHFUL_FOOTBALL") != "1":
        pytest.skip("Set BET_RUN_TRUTHFUL_FOOTBALL=1 to run the real football vertical proof")

    artifact_dir = Path(".kilo/artifacts/football_truthful_live")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    evidence_root = tmp_path / "evidence"
    monkeypatch.setenv("BET_EVIDENCE_ROOT", str(evidence_root))
    monkeypatch.setattr(base_client, "CACHE_DIR", tmp_path / "live_cache")

    import bet.discovery.coordinator as coordinator_module

    monkeypatch.setattr(coordinator_module, "DATA_DIR", tmp_path / "discovery_data")

    engine, live_session = _build_session()
    coordinator = EventDiscoveryCoordinator(session=live_session, sources=[APIFootballAdapter()])
    discovery = coordinator.discover("2026-05-24", sports=["football"])
    assert discovery.total_discovered > 0

    fixture_id = _select_target_fixture(live_session)
    live_snapshot_1 = build_football_fixture_snapshot(live_session.connection(), fixture_id)
    state_1 = _domain_state(live_session)
    build_football_fixture_snapshot(live_session.connection(), fixture_id)
    state_2 = _domain_state(live_session)

    assert live_snapshot_1["cross_provider_identity"]["payload"]["espn"]["fixture_id"] == "740968"
    assert live_snapshot_1["cross_provider_identity"]["payload"]["api_football"]["fixture_id"]
    assert state_1 == state_2

    bundle_ids = _bundle_ids(live_session)
    assert bundle_ids, "No retained evidence bundles were persisted"

    replay_transports = [build_replay_transport(bundle_id, evidence_root) for bundle_id in bundle_ids]

    def replay_wrap_request(**kwargs):
        last_error = None
        for transport in replay_transports:
            try:
                return transport(**kwargs)
            except AssertionError as exc:
                last_error = exc
        raise last_error or AssertionError("No replay transport matched the request")

    monkeypatch.setattr(telemetry_wrapper, "wrap_request", replay_wrap_request)
    _block_network(monkeypatch)

    _, replay_session = _build_session()
    replay_coordinator = EventDiscoveryCoordinator(session=replay_session, sources=[APIFootballAdapter()])
    replay_discovery = replay_coordinator.discover("2026-05-24", sports=["football"])
    assert replay_discovery.total_discovered > 0

    replay_fixture_id = _select_target_fixture(replay_session)
    replay_snapshot_1 = build_football_fixture_snapshot(replay_session.connection(), replay_fixture_id)
    replay_state_1 = _domain_state(replay_session)
    replay_snapshot_2 = build_football_fixture_snapshot(replay_session.connection(), replay_fixture_id)
    replay_state_2 = _domain_state(replay_session)

    assert replay_snapshot_1 == live_snapshot_1
    assert replay_snapshot_2 == replay_snapshot_1
    assert replay_state_1 == replay_state_2

    with pytest.raises(AssertionError):
        replay_transports[0](
            provider="unexpected",
            request_fn=requests.get,
            url="https://site.api.espn.com/apis/v2/sports/soccer/eng.1/unexpected",
            params=None,
        )

    summary = {
        "fixture_id": fixture_id,
        "cross_provider_identity": live_snapshot_1["cross_provider_identity"],
        "capability_statuses": live_snapshot_1["capability_statuses"],
        "bundle_ids": bundle_ids,
        "live_state_counts": {key: len(value) for key, value in state_1.items()},
        "replay_state_counts": {key: len(value) for key, value in replay_state_1.items()},
        "idempotent_second_run": state_1 == state_2,
        "replay_idempotent_second_run": replay_state_1 == replay_state_2,
    }
    (artifact_dir / "truthful_live_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    live_session.close()
    replay_session.close()
    engine.dispose()
