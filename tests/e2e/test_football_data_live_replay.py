# ruff: noqa: E501, I001

from __future__ import annotations

import os
import json
import hashlib
import socket
import pytest
import requests
from pathlib import Path
from datetime import UTC, datetime

from bet.api_clients import base_client
from bet.api_clients.football_data_org import FootballDataOrgClient
from bet.discovery.sources.football_data_org import FootballDataOrgDiscoveryAdapter
from bet.enrichment.football_service import FootballDataStandingsAdapter
from bet.api_clients.rate_limiter import RateLimiter
from bet.integration import telemetry_wrapper
from bet.integration.evidence import build_replay_transport
from bet.api_clients.base_client import SourceResultStatus
from pydantic import BaseModel
from dataclasses import is_dataclass, asdict


def to_canonical_json(obj) -> str:
    def simplify(o):
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, BaseModel):
            return simplify(o.model_dump())
        if is_dataclass(o):
            return simplify(asdict(o))
        if isinstance(o, dict):
            return {k: simplify(v) for k, v in o.items()}
        if isinstance(o, (list, tuple, set)):
            return [simplify(v) for v in o]
        return o

    simplified = simplify(obj)
    return json.dumps(simplified, sort_keys=True, separators=(",", ":"))


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


def test_football_data_live_and_replay(tmp_path, monkeypatch):
    from dotenv import load_dotenv
    load_dotenv()

    key = os.getenv("FOOTBALL_DATA_ORG_KEY")
    if not key:
        pytest.skip("FOOTBALL_DATA_ORG_KEY not found in environment or .env")

    # Setup temporary evidence root and cache
    evidence_root = tmp_path / "evidence"
    monkeypatch.setenv("BET_EVIDENCE_ROOT", str(evidence_root))
    monkeypatch.setattr(base_client, "CACHE_DIR", tmp_path / "live_cache")

    # 1. Live Run
    limiter = RateLimiter()
    client = FootballDataOrgClient(rate_limiter=limiter)
    client.api_key = key

    # Live Discovery Proof
    discovery_adapter = FootballDataOrgDiscoveryAdapter(competition="PL", rate_limiter=limiter)
    discovery_adapter._client.api_key = key

    # Call get_fixtures_result directly to get the SourceOperationResult
    discovery_res = discovery_adapter._client.get_fixtures_result("2026-05-24", competition="PL")
    assert discovery_res.status is SourceResultStatus.SUCCESS

    # Call fetch_events to get the parsed events
    discovered_events = discovery_adapter.fetch_events("2026-05-24", "football")
    assert len(discovered_events) > 0

    # Live Standings Proof
    cutoff = datetime.now(UTC)
    standings_adapter = FootballDataStandingsAdapter(client)
    standings_res = standings_adapter.fetch_capability(
        capability="standings_competition_context",
        canonical_fixture_id=1,
        analysis_cutoff_at=cutoff,
        native_competition_id="eng.1",
    )
    assert standings_res.status is SourceResultStatus.SUCCESS
    assert standings_res.value is not None

    # Capture metadata
    key_sha256_prefix = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]

    # Discovery metadata
    disc_ref = discovery_res.evidence_refs[0]
    disc_raw_body = evidence_root / "objects" / disc_ref.object_sha256[:2] / disc_ref.object_sha256
    disc_raw_bytes = disc_raw_body.read_bytes()
    disc_raw_sha256 = hashlib.sha256(disc_raw_bytes).hexdigest()
    disc_norm_json = to_canonical_json(discovered_events)
    disc_norm_sha256 = hashlib.sha256(disc_norm_json.encode("utf-8")).hexdigest()

    discovery_metadata = {
        "provider": "football-data",
        "capability": "current_discovery",
        "competition_scope": "football:eng.1",
        "season_scope": "current",
        "mode": "shadow",
        "request_path_without_secrets": "/competitions/PL/matches",
        "params": {"dateFrom": "2026-05-24", "dateTo": "2026-05-24"},
        "response_status": discovery_res.http_status,
        "bundle_id": discovery_res.bundle_id,
        "raw_response_sha256": disc_raw_sha256,
        "parser_version": "football-data-org-fixtures-v1",
        "normalized_payload_sha256": disc_norm_sha256,
        "accepted_count": len(discovered_events),
        "rejected_count": discovery_res.parser_diagnostics.get("rejected_count", 0),
        "source_operation_status": discovery_res.status.value,
        "env_key_name": "FOOTBALL_DATA_ORG_KEY",
        "env_key_source": ".env",
        "env_key_sha256_prefix": key_sha256_prefix,
    }

    # Standings metadata
    stand_ref = standings_res.evidence_refs[0]
    stand_raw_body = evidence_root / "objects" / stand_ref.object_sha256[:2] / stand_ref.object_sha256
    stand_raw_bytes = stand_raw_body.read_bytes()
    stand_raw_sha256 = hashlib.sha256(stand_raw_bytes).hexdigest()
    stand_norm_json = to_canonical_json(standings_res.value)
    stand_norm_sha256 = hashlib.sha256(stand_norm_json.encode("utf-8")).hexdigest()

    standings_metadata = {
        "provider": "football-data",
        "capability": "standings",
        "competition_scope": "football:eng.1",
        "season_scope": "current",
        "mode": "shadow",
        "request_path_without_secrets": "/competitions/PL/standings",
        "params": None,
        "response_status": standings_res.http_status,
        "bundle_id": standings_res.bundle_id,
        "raw_response_sha256": stand_raw_sha256,
        "parser_version": "football-data-org-standings-v1",
        "normalized_payload_sha256": stand_norm_sha256,
        "accepted_count": len(standings_res.value.rows),
        "rejected_count": 0,
        "source_operation_status": standings_res.status.value,
        "env_key_name": "FOOTBALL_DATA_ORG_KEY",
        "env_key_source": ".env",
        "env_key_sha256_prefix": key_sha256_prefix,
    }

    # 2. Replay Run
    # Setup replay transport
    bundle_ids = [discovery_res.bundle_id, standings_res.bundle_id]
    replay_transports = [build_replay_transport(bid, evidence_root) for bid in bundle_ids]

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

    # Replay Discovery
    replay_limiter = RateLimiter()
    replay_client = FootballDataOrgClient(rate_limiter=replay_limiter)
    replay_client.api_key = key
    replay_discovery_adapter = FootballDataOrgDiscoveryAdapter(competition="PL", rate_limiter=replay_limiter)
    replay_discovery_adapter._client.api_key = key

    replay_discovery_res = replay_discovery_adapter._client.get_fixtures_result("2026-05-24", competition="PL")
    assert replay_discovery_res.status is SourceResultStatus.SUCCESS

    replay_discovered_events = replay_discovery_adapter.fetch_events("2026-05-24", "football")
    assert len(replay_discovered_events) > 0

    # Replay Standings
    replay_standings_adapter = FootballDataStandingsAdapter(replay_client)
    replay_standings_res = replay_standings_adapter.fetch_capability(
        capability="standings_competition_context",
        canonical_fixture_id=1,
        analysis_cutoff_at=cutoff,
        native_competition_id="eng.1",
    )
    assert replay_standings_res.status is SourceResultStatus.SUCCESS
    assert replay_standings_res.value is not None

    # Verify Replay matches Live exactly
    # Raw response sha256
    rep_disc_ref = replay_discovery_res.evidence_refs[0]
    rep_disc_raw_body = evidence_root / "objects" / rep_disc_ref.object_sha256[:2] / rep_disc_ref.object_sha256
    rep_disc_raw_sha256 = hashlib.sha256(rep_disc_raw_body.read_bytes()).hexdigest()
    assert rep_disc_raw_sha256 == disc_raw_sha256

    rep_stand_ref = replay_standings_res.evidence_refs[0]
    rep_stand_raw_body = evidence_root / "objects" / rep_stand_ref.object_sha256[:2] / rep_stand_ref.object_sha256
    rep_stand_raw_sha256 = hashlib.sha256(rep_stand_raw_body.read_bytes()).hexdigest()
    assert rep_stand_raw_sha256 == stand_raw_sha256

    # Normalized payload sha256
    rep_disc_norm_json = to_canonical_json(replay_discovered_events)
    rep_disc_norm_sha256 = hashlib.sha256(rep_disc_norm_json.encode("utf-8")).hexdigest()
    assert rep_disc_norm_sha256 == disc_norm_sha256

    rep_stand_norm_json = to_canonical_json(replay_standings_res.value)
    rep_stand_norm_sha256 = hashlib.sha256(rep_stand_norm_json.encode("utf-8")).hexdigest()
    assert rep_stand_norm_sha256 == stand_norm_sha256

    # Accepted/rejected counts
    assert len(replay_discovered_events) == len(discovered_events)
    assert replay_discovery_res.parser_diagnostics.get("rejected_count", 0) == discovery_res.parser_diagnostics.get("rejected_count", 0)
    assert len(replay_standings_res.value.rows) == len(standings_res.value.rows)

    # Source operation status
    assert replay_discovery_res.status.value == discovery_res.status.value
    assert replay_standings_res.status.value == standings_res.status.value

    # Canonical discovery identities
    live_identities = sorted([e.external_id for e in discovered_events])
    replay_identities = sorted([e.external_id for e in replay_discovered_events])
    assert live_identities == replay_identities

    # Normalized standings table
    assert replay_standings_res.value.competition_canonical_id == standings_res.value.competition_canonical_id
    assert replay_standings_res.value.competition_native_id == standings_res.value.competition_native_id
    assert replay_standings_res.value.provider == standings_res.value.provider
    assert len(replay_standings_res.value.rows) == len(standings_res.value.rows)
    for r_row, l_row in zip(replay_standings_res.value.rows, standings_res.value.rows):
        assert r_row.team_native_id == l_row.team_native_id
        assert r_row.rank == l_row.rank
        assert r_row.points == l_row.points
        assert r_row.played == l_row.played
        assert r_row.wins == l_row.wins
        assert r_row.draws == l_row.draws
        assert r_row.losses == l_row.losses
        assert r_row.goals_for == l_row.goals_for
        assert r_row.goals_against == l_row.goals_against
        assert r_row.goal_diff == l_row.goal_diff
        assert r_row.form == l_row.form

    # Write compact artifact summary
    artifact_dir = Path(".kilo/artifacts/football_truthful_live")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Generate a unique replay proof ID derived from the proof artifact
    proof_id = hashlib.sha256(to_canonical_json([discovery_metadata, standings_metadata]).encode("utf-8")).hexdigest()

    summary = {
        "proof_id": proof_id,
        "discovery_proof": discovery_metadata,
        "standings_proof": standings_metadata,
        "replay_verification": "PASS",
    }

    summary_file = artifact_dir / "football_data_proof_summary.json"
    summary_file.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Proof summary written to {summary_file}")
