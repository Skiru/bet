from __future__ import annotations

import asyncio
import json
import os
import socket
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests

from bet.api_clients import base_client
from bet.api_clients.espn import ESPNClient
from bet.api_clients.rate_limiter import RateLimiter
from bet.db.models import Fixture
from bet.db.repositories import CompetitionRepo, FixtureRepo, SportRepo, TeamRepo
from bet.db.schema import init_db
from bet.integration import telemetry_wrapper
from bet.integration.evidence import build_replay_transport, load_bundle_manifest
from bet.stats.enrichment import enrich_fixtures

pytestmark = pytest.mark.espn_live


def _team_form_snapshot(conn, team_ids: tuple[int, int]) -> list[dict]:
    rows = conn.execute(
        "SELECT team_id, stat_key, l10_values, l5_values, "
        "l10_avg, l5_avg, trend, source, source_event_ids, evidence_hash "
        "FROM team_form WHERE team_id IN (?, ?) ORDER BY team_id, stat_key",
        team_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def _seed_fixture(conn, target_fixture, canonical_external_id: str):
    sport_repo = SportRepo(conn)
    team_repo = TeamRepo(conn)
    competition_repo = CompetitionRepo(conn)
    fixture_repo = FixtureRepo(conn)

    football = sport_repo.get_by_name("football")
    home_team = team_repo.find_or_create(target_fixture.home_team_name, football.id)
    away_team = team_repo.find_or_create(target_fixture.away_team_name, football.id)
    competition_id = competition_repo.find_or_create(
        target_fixture.competition_name or "Premier League",
        football.id,
        season="2026",
    )
    fixture = Fixture(
        id=None,
        sport_id=football.id,
        competition_id=competition_id,
        home_team_id=home_team.id,
        away_team_id=away_team.id,
        kickoff=target_fixture.kickoff.replace("Z", "+00:00"),
        status="scheduled",
        external_id=canonical_external_id,
        source="api-football",
    )
    fixture.id = fixture_repo.upsert(fixture)
    conn.execute(
        "INSERT INTO fixture_sources (fixture_id, source, external_id, confidence, fetched_at) VALUES (?, ?, ?, ?, ?)",
        (fixture.id, "espn-football", target_fixture.external_id, 1.0, datetime.now(UTC).isoformat()),
    )
    conn.commit()
    return fixture, (home_team.id, away_team.id)


def _select_side(provider_team_id: str, stats) -> str | None:
    home_id = str(getattr(stats, "home_participant_id", "") or "")
    away_id = str(getattr(stats, "away_participant_id", "") or "")
    if not provider_team_id or not home_id or not away_id:
        return None
    home_match = provider_team_id == home_id
    away_match = provider_team_id == away_id
    if home_match == away_match:
        return None
    return "home" if home_match else "away"


def _block_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Unexpected outbound network access during replay")

    monkeypatch.setattr(socket, "create_connection", blocked)

    def blocked_connect(self, address):
        raise AssertionError(f"Unexpected socket connection during replay: {address}")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect, raising=True)
    try:
        import urllib3.util.connection

        monkeypatch.setattr(urllib3.util.connection, "create_connection", blocked)
    except Exception:
        pass


def test_espn_football_live_rem002a(db_with_sports, tmp_path, monkeypatch):
    if os.getenv("BET_RUN_LIVE_ESPN") != "1":
        pytest.skip("Set BET_RUN_LIVE_ESPN=1 to run live ESPN proof")

    artifact_dir = Path(".kilo/artifacts/rem002a_espn_football")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(base_client, "CACHE_DIR", tmp_path / "stats_cache_live")
    evidence_root = tmp_path / "runtime_evidence"
    monkeypatch.setenv("BET_EVIDENCE_ROOT", str(evidence_root))

    client = ESPNClient(sport="football", league="eng.1", rate_limiter=RateLimiter())
    fixtures = client.get_fixtures("2026-05-24")
    target = next(
        (fixture for fixture in fixtures if fixture.external_id == "740968"), None
    )
    assert target is not None
    assert target.home_participant_id == "384"
    assert target.away_participant_id == "359"

    canonical_external_id = f"api-football-shadow-{target.external_id}"
    fixture, team_ids = _seed_fixture(db_with_sports, target, canonical_external_id)
    live_counts = asyncio.run(
        enrich_fixtures([fixture], db_with_sports, max_age_hours=0)
    )
    live_snapshot = _team_form_snapshot(db_with_sports, team_ids)

    home_recent = client.get_team_last_fixtures(
        target.home_participant_id,
        last_n=10,
        analysis_cutoff_at=target.kickoff,
        exclude_event_ids={target.external_id},
    )
    away_recent = client.get_team_last_fixtures(
        target.away_participant_id,
        last_n=10,
        analysis_cutoff_at=target.kickoff,
        exclude_event_ids={target.external_id},
    )

    assert live_counts["fetched"] == 2
    assert live_counts["failed"] == 0
    assert any(row["source"] == "espn-football" for row in live_snapshot)
    assert all(event["id"] != target.external_id for event in home_recent + away_recent)
    assert all(event["date"] < target.kickoff for event in home_recent + away_recent)

    bundle_ids = sorted({row["evidence_hash"] for row in live_snapshot if row["evidence_hash"]})
    assert bundle_ids
    bundle_id = bundle_ids[0]
    manifests = [load_bundle_manifest(current_bundle_id, evidence_root) for current_bundle_id in bundle_ids]

    side_selection = []
    for team_name, provider_team_id, recent in (
        (target.home_team_name, target.home_participant_id, home_recent),
        (target.away_team_name, target.away_participant_id, away_recent),
    ):
        assert recent
        stats = client.get_fixture_stats(recent[0]["id"])
        assert stats
        selected_side = _select_side(provider_team_id, stats[0])
        side_selection.append(
            {
                "team_name": team_name,
                "provider_team_id": provider_team_id,
                "fixture_id": recent[0]["id"],
                "home_participant_id": stats[0].home_participant_id,
                "away_participant_id": stats[0].away_participant_id,
                "selected_side": selected_side,
            }
        )
        assert selected_side in {"home", "away"}

    request_index = {}
    for manifest in manifests:
        for entry in manifest["entries"]:
            request_index[entry.request_identity] = {
                "status_code": entry.http_status,
                "object_sha256": entry.object_sha256,
                "operation": entry.operation,
                "source_event_id": entry.source_event_id,
            }

    summary = {
        "canonical_fixture_id": fixture.id,
        "canonical_external_id": canonical_external_id,
        "target_source_event_id": target.external_id,
        "target_start_at": target.kickoff,
        "analysis_cutoff_at": target.kickoff,
        "competition": target.competition_name,
        "target_participants": {
            "home": {
                "provider_team_id": target.home_participant_id,
                "name": target.home_team_name,
            },
            "away": {
                "provider_team_id": target.away_participant_id,
                "name": target.away_team_name,
            },
        },
        "recent_form": {
            target.home_participant_id: [
                {"event_id": event["id"], "start_at": event["date"], "reason": "accepted_pre_cutoff_finished"}
                for event in home_recent
            ],
            target.away_participant_id: [
                {"event_id": event["id"], "start_at": event["date"], "reason": "accepted_pre_cutoff_finished"}
                for event in away_recent
            ],
        },
        "recent_form_rejections": [
            {"event_id": target.external_id, "reason": "excluded_target_event"}
        ],
        "target_event_absent_from_recent_form": all(
            event["id"] != target.external_id for event in home_recent + away_recent
        ),
        "all_recent_form_before_target": all(
            event["date"] < target.kickoff for event in home_recent + away_recent
        ),
        "side_selection": side_selection,
        "recorded_requests": request_index,
        "object_hashes": sorted(
            {
                entry.object_sha256
                for manifest in manifests
                for entry in manifest["entries"]
            }
        ),
        "bundle_id": bundle_id,
        "bundle_ids": bundle_ids,
        "live_counts": live_counts,
        "live_team_form_rows": len(live_snapshot),
        "replay": {},
    }

    replay_cache = tmp_path / "stats_cache_replay"
    replay_cache.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(base_client, "CACHE_DIR", replay_cache)
    replay_transports = [
        build_replay_transport(current_bundle_id, evidence_root)
        for current_bundle_id in bundle_ids
    ]

    def replay_wrap_request(**kwargs):
        last_error = None
        for transport in replay_transports:
            try:
                return transport(**kwargs)
            except AssertionError as exc:
                last_error = exc
        raise last_error or AssertionError("No replay transport matched the request")

    monkeypatch.setattr(telemetry_wrapper, "wrap_request", replay_wrap_request)
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Unexpected requests.get during replay")
        ),
    )
    _block_network(monkeypatch)

    replay_db = sqlite3.connect(":memory:")
    replay_db.row_factory = sqlite3.Row
    replay_db.execute("PRAGMA foreign_keys = ON")
    init_db(replay_db)
    SportRepo(replay_db).seed_defaults()

    replay_client = ESPNClient(
        sport="football", league="eng.1", rate_limiter=RateLimiter()
    )
    replay_fixtures = replay_client.get_fixtures("2026-05-24")
    replay_target = next(
        (
            replay_fixture
            for replay_fixture in replay_fixtures
            if replay_fixture.external_id == target.external_id
        ),
        None,
    )
    assert replay_target is not None
    assert replay_target.home_team_name == target.home_team_name
    assert replay_target.away_team_name == target.away_team_name
    assert replay_target.home_participant_id == target.home_participant_id
    assert replay_target.away_participant_id == target.away_participant_id
    assert replay_target.kickoff == target.kickoff

    replay_fixture, replay_team_ids = _seed_fixture(
        replay_db,
        target,
        canonical_external_id,
    )
    replay_counts_1 = asyncio.run(
        enrich_fixtures([replay_fixture], replay_db, max_age_hours=0)
    )
    replay_snapshot_1 = _team_form_snapshot(replay_db, replay_team_ids)
    replay_row_count_1 = len(replay_snapshot_1)

    replay_counts_2 = asyncio.run(
        enrich_fixtures([replay_fixture], replay_db, max_age_hours=0)
    )
    replay_snapshot_2 = _team_form_snapshot(replay_db, replay_team_ids)

    assert replay_counts_1["failed"] == 0
    assert replay_snapshot_1 == live_snapshot
    assert len(replay_snapshot_2) == replay_row_count_1
    assert replay_snapshot_2 == replay_snapshot_1

    summary["replay"] = {
        "first_run_counts": replay_counts_1,
        "first_run_team_form_rows": replay_row_count_1,
        "second_run_counts": replay_counts_2,
        "second_run_team_form_rows": len(replay_snapshot_2),
        "semantic_match_live": replay_snapshot_1 == live_snapshot,
        "idempotent_second_run": len(replay_snapshot_2) == replay_row_count_1,
    }
    (artifact_dir / "live_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    replay_db.close()
