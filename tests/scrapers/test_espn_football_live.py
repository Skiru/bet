from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import sqlite3
from pathlib import Path
from urllib.parse import urlencode

import pytest
import requests

from bet.api_clients import base_client
from bet.api_clients.espn import ESPNClient
from bet.api_clients.rate_limiter import RateLimiter
from bet.db.models import Fixture
from bet.db.repositories import CompetitionRepo, FixtureRepo, SportRepo, TeamRepo
from bet.db.schema import init_db
from bet.stats.enrichment import enrich_fixtures

pytestmark = pytest.mark.espn_live


class _ReplayResponse:
    def __init__(self, record: dict):
        self.status_code = record["status_code"]
        self.headers = record["headers"]
        self.text = record["body"]
        self.content = record["body"].encode("utf-8")

    def json(self):
        return json.loads(self.text)


def _request_key(url: str, params: dict | None) -> str:
    if not params:
        return url
    return f"{url}?{urlencode(sorted((str(k), str(v)) for k, v in params.items()))}"


def _team_form_snapshot(conn, team_ids: tuple[int, int]) -> list[dict]:
    rows = conn.execute(
        "SELECT team_id, stat_key, l10_values, l5_values, "
        "l10_avg, l5_avg, trend, source "
        "FROM team_form WHERE team_id IN (?, ?) ORDER BY team_id, stat_key",
        team_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def _seed_fixture(conn, target_fixture):
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
        external_id=target_fixture.external_id,
        source="espn-football",
    )
    fixture.id = fixture_repo.upsert(fixture)
    conn.commit()
    return fixture, (home_team.id, away_team.id)


def _record_request(artifact_dir: Path, key: str, response) -> dict:
    body = response.text
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    safe_name = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    file_name = f"{safe_name}.json"
    (artifact_dir / file_name).write_text(body, encoding="utf-8")
    return {
        "status_code": response.status_code,
        "headers": {"Content-Type": response.headers.get("Content-Type", "")},
        "body": body,
        "sha256": sha,
        "artifact_file": file_name,
    }


def _load_replay_records(
    artifact_dir: Path, request_index: dict[str, dict]
) -> dict[str, dict]:
    replay_records: dict[str, dict] = {}
    for key, meta in request_index.items():
        replay_records[key] = {
            "status_code": meta["status_code"],
            "headers": meta["headers"],
            "body": (artifact_dir / meta["artifact_file"]).read_text(encoding="utf-8"),
            "sha256": meta["sha256"],
            "artifact_file": meta["artifact_file"],
        }
    return replay_records


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


def test_espn_football_live_rem001b(db_with_sports, tmp_path, monkeypatch):
    if os.getenv("BET_RUN_LIVE_ESPN") != "1":
        pytest.skip("Set BET_RUN_LIVE_ESPN=1 to run live ESPN proof")

    artifact_dir = Path(".kilo/artifacts/rem001b_espn_football")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(base_client, "CACHE_DIR", tmp_path / "stats_cache_live")

    recorded: dict[str, dict] = {}
    real_get = requests.get

    def recording_get(url, *args, **kwargs):
        response = real_get(url, *args, **kwargs)
        key = _request_key(url, kwargs.get("params"))
        recorded[key] = _record_request(artifact_dir, key, response)
        return response

    monkeypatch.setattr(requests, "get", recording_get)

    client = ESPNClient(sport="football", league="eng.1", rate_limiter=RateLimiter())
    fixtures = client.get_fixtures("2026-05-24")
    target = next(
        (fixture for fixture in fixtures if fixture.external_id == "740968"), None
    )
    assert target is not None
    assert target.home_participant_id == "384"
    assert target.away_participant_id == "359"

    fixture, team_ids = _seed_fixture(db_with_sports, target)
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

    request_index = {
        key: {
            "status_code": value["status_code"],
            "headers": value["headers"],
            "sha256": value["sha256"],
            "artifact_file": value["artifact_file"],
        }
        for key, value in recorded.items()
    }
    (artifact_dir / "request_index.json").write_text(
        json.dumps(request_index, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    summary = {
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
                {"event_id": event["id"], "start_at": event["date"]}
                for event in home_recent
            ],
            target.away_participant_id: [
                {"event_id": event["id"], "start_at": event["date"]}
                for event in away_recent
            ],
        },
        "target_event_absent_from_recent_form": all(
            event["id"] != target.external_id for event in home_recent + away_recent
        ),
        "all_recent_form_before_target": all(
            event["date"] < target.kickoff for event in home_recent + away_recent
        ),
        "side_selection": side_selection,
        "recorded_requests": request_index,
        "live_counts": live_counts,
        "live_team_form_rows": len(live_snapshot),
        "replay": {},
    }

    replay_cache = tmp_path / "stats_cache_replay"
    replay_cache.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(base_client, "CACHE_DIR", replay_cache)

    replay_records = _load_replay_records(artifact_dir, request_index)

    def replay_get(url, *args, **kwargs):
        key = _request_key(url, kwargs.get("params"))
        if key not in replay_records:
            raise AssertionError(f"Unexpected network access during replay: {key}")
        return _ReplayResponse(replay_records[key])

    monkeypatch.setattr(requests, "get", replay_get)
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
            fixture
            for fixture in replay_fixtures
            if fixture.external_id == target.external_id
        ),
        None,
    )
    assert replay_target is not None
    assert replay_target.home_team_name == target.home_team_name
    assert replay_target.away_team_name == target.away_team_name
    assert replay_target.home_participant_id == target.home_participant_id
    assert replay_target.away_participant_id == target.away_participant_id
    assert replay_target.kickoff == target.kickoff

    replay_fixture, replay_team_ids = _seed_fixture(replay_db, target)
    replay_counts_1 = asyncio.run(
        enrich_fixtures([replay_fixture], replay_db, max_age_hours=0)
    )
    replay_snapshot_1 = _team_form_snapshot(replay_db, replay_team_ids)
    replay_row_count_1 = len(replay_snapshot_1)

    replay_counts_2 = asyncio.run(
        enrich_fixtures([replay_fixture], replay_db, max_age_hours=0)
    )
    replay_snapshot_2 = _team_form_snapshot(replay_db, replay_team_ids)

    assert replay_counts_1["fetched"] == 2
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
