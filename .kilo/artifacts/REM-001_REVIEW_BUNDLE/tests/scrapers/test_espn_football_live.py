from __future__ import annotations

import asyncio
import hashlib
import json
import os
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


def _seed_fixture(
    conn, kickoff: str, home_name: str, away_name: str, competition_name: str
):
    sport_repo = SportRepo(conn)
    team_repo = TeamRepo(conn)
    competition_repo = CompetitionRepo(conn)
    fixture_repo = FixtureRepo(conn)

    football = sport_repo.get_by_name("football")
    home_team = team_repo.find_or_create(home_name, football.id)
    away_team = team_repo.find_or_create(away_name, football.id)
    competition_id = competition_repo.find_or_create(
        competition_name, football.id, season="2026"
    )
    fixture = Fixture(
        id=None,
        sport_id=football.id,
        competition_id=competition_id,
        home_team_id=home_team.id,
        away_team_id=away_team.id,
        kickoff=kickoff,
        status="scheduled",
        source="seed",
    )
    fixture.id = fixture_repo.upsert(fixture)
    conn.commit()
    return fixture, (home_team.id, away_team.id)


def test_espn_football_live_rem001(db_with_sports, tmp_path, monkeypatch):
    if os.getenv("BET_RUN_LIVE_ESPN") != "1":
        pytest.skip("Set BET_RUN_LIVE_ESPN=1 to run live ESPN proof")

    artifact_dir = Path(".kilo/artifacts/rem001_espn_football")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(base_client, "CACHE_DIR", tmp_path / "stats_cache_live")

    recorded: dict[str, dict] = {}
    real_get = requests.get

    def recording_get(url, *args, **kwargs):
        response = real_get(url, *args, **kwargs)
        params = kwargs.get("params")
        key = _request_key(url, params)
        body = response.text
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        record = {
            "status_code": response.status_code,
            "headers": {"Content-Type": response.headers.get("Content-Type", "")},
            "body": body,
            "sha256": sha,
        }
        recorded[key] = record
        safe_name = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        (artifact_dir / f"{safe_name}.json").write_text(body, encoding="utf-8")
        return response

    monkeypatch.setattr(requests, "get", recording_get)

    client = ESPNClient(sport="football", league="eng.1", rate_limiter=RateLimiter())
    fixtures = client.get_fixtures("2026-05-24")
    target = next((f for f in fixtures if f.external_id == "740968"), fixtures[0])

    fixture, team_ids = _seed_fixture(
        db_with_sports,
        target.kickoff.replace("Z", ":00"),
        "Arsenal",
        "Liverpool",
        "Premier League",
    )
    live_counts = asyncio.run(
        enrich_fixtures([fixture], db_with_sports, max_age_hours=0)
    )
    live_snapshot = _team_form_snapshot(db_with_sports, team_ids)

    assert fixtures
    assert target.external_id
    assert target.home_team_name and target.away_team_name
    assert live_counts["fetched"] >= 1
    assert any(row["source"] == "espn-football" for row in live_snapshot)

    summary = {
        "target_date": "2026-05-24",
        "league": "eng.1",
        "source_event_id": target.external_id,
        "participants": [target.home_team_name, target.away_team_name],
        "kickoff": target.kickoff,
        "competition": target.competition_name,
        "recorded_requests": {
            key: {
                "status_code": value["status_code"],
                "sha256": value["sha256"],
            }
            for key, value in recorded.items()
        },
        "live_counts": live_counts,
        "live_team_form_rows": len(live_snapshot),
        "replay": {},
    }

    replay_cache = tmp_path / "stats_cache_replay"
    replay_cache.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(base_client, "CACHE_DIR", replay_cache)

    def replay_get(url, *args, **kwargs):
        key = _request_key(url, kwargs.get("params"))
        if key not in recorded:
            raise AssertionError(f"Unexpected network access during replay: {key}")
        return _ReplayResponse(recorded[key])

    monkeypatch.setattr(requests, "get", replay_get)

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
        (f for f in replay_fixtures if f.external_id == target.external_id), None
    )
    assert replay_target is not None
    assert replay_target.home_team_name == target.home_team_name
    assert replay_target.away_team_name == target.away_team_name
    assert replay_target.kickoff == target.kickoff

    replay_fixture, replay_team_ids = _seed_fixture(
        replay_db,
        target.kickoff.replace("Z", ":00"),
        "Arsenal",
        "Liverpool",
        "Premier League",
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

    assert replay_counts_1["fetched"] >= 1
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
