import json
import sqlite3
from pathlib import Path

import pytest

import bet.api_clients.api_football  # noqa: F401
from bet.db.models import TeamForm
from bet.db.repositories import SportRepo, StatsRepo, TeamRepo
from bet.db.schema import init_db
from bet.integration.evidence import (
    build_replay_transport,
    normalize_request_identity,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = REPO_ROOT / "betting" / "data" / "evidence"
OLD_TEAM_BUNDLE = "b01f22fbb05326dc37de3230fe1accacd83c54586f3c2d17bdceb6fb76359e16"


def _memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    SportRepo(conn).seed_defaults()
    return conn


def _create_v14_like_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    SportRepo(conn).seed_defaults()
    conn.execute("UPDATE schema_meta SET value = '14' WHERE key = 'version'")
    conn.execute("DROP INDEX IF EXISTS idx_team_form_evidence_history_dedup")
    conn.execute("DROP INDEX IF EXISTS idx_team_form_evidence_history_lookup")
    conn.execute("DROP TABLE IF EXISTS team_form_evidence_history")
    conn.commit()
    return conn


def _seed_team_form(
    conn: sqlite3.Connection,
    evidence_hash: str,
    source_event_ids: list[str],
) -> TeamForm:
    football = SportRepo(conn).get_by_name("football")
    team = TeamRepo(conn).find_or_create("Sport Recife", football.id)
    return TeamForm(
        id=None,
        team_id=team.id,
        sport_id=football.id,
        stat_key="corners",
        l10_values=[5.0, 6.0],
        l5_values=[5.0, 6.0],
        l10_avg=5.5,
        l5_avg=5.5,
        trend="stable",
        updated_at="2026-06-12T08:00:00+00:00",
        source="api-football",
        source_event_ids=source_event_ids,
        evidence_hash=evidence_hash,
    )


def test_normalize_request_identity_sorts_query_params():
    left = normalize_request_identity(
        "get",
        "https://v3.football.api-sports.io/fixtures",
        {"team": "123", "season": "2026", "league": "72"},
    )
    right = normalize_request_identity(
        "GET",
        "https://v3.football.api-sports.io/fixtures?season=2026&league=72",
        {"team": "123"},
    )

    assert left == right
    assert (
        left
        == "GET https://v3.football.api-sports.io/fixtures?league=72&season=2026&team=123"
    )


def test_replay_transport_rejects_semantic_identity_mismatch():
    transport = build_replay_transport(OLD_TEAM_BUNDLE, EVIDENCE_ROOT)

    with pytest.raises(AssertionError, match="Unexpected replay request"):
        transport(
            provider="api-football",
            request_fn=None,
            url="https://v3.football.api-sports.io/fixtures",
            params={"team": "123", "season": "2026", "league": "72"},
            headers={},
            timeout=30,
            scope_id="/fixtures",
        )


def test_replay_transport_accepts_query_order_variation():
    transport = build_replay_transport(OLD_TEAM_BUNDLE, EVIDENCE_ROOT)

    result = transport(
        provider="api-football",
        request_fn=None,
        url="https://v3.football.api-sports.io/fixtures?team=123",
        params={"season": "2024"},
        headers={},
        timeout=30,
        scope_id="/fixtures",
    )

    assert (
        result.telemetry["request_identity"]
        == "GET https://v3.football.api-sports.io/fixtures?season=2024&team=123"
    )
    assert result.status_code == 200


def test_team_form_evidence_history_migration_backfills_existing_links():
    conn = _create_v14_like_db()
    old_hash = "a" * 64
    form = _seed_team_form(
        conn,
        old_hash,
        ["api-football:1183398", "api-football:1520718"],
    )
    conn.execute(
        "INSERT INTO team_form ("
        "team_id, sport_id, stat_key, l10_values, l5_values, l10_avg, l5_avg, "
        "h2h_values, h2h_opponent_id, trend, updated_at, source, "
        "source_event_ids, evidence_hash"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            form.team_id,
            form.sport_id,
            form.stat_key,
            json.dumps(form.l10_values),
            json.dumps(form.l5_values),
            form.l10_avg,
            form.l5_avg,
            json.dumps(form.h2h_values),
            form.h2h_opponent_id,
            form.trend,
            form.updated_at,
            form.source,
            json.dumps(form.source_event_ids),
            form.evidence_hash,
        ),
    )
    conn.commit()

    init_db(conn)

    rows = conn.execute(
        "SELECT team_id, stat_key, source, source_event_ids, evidence_hash "
        "FROM team_form_evidence_history"
    ).fetchall()

    assert len(rows) == 1
    assert rows[0][2] == "api-football"
    assert rows[0][4] == old_hash
    assert json.loads(rows[0][3]) == [
        "api-football:1183398",
        "api-football:1520718",
    ]
    conn.close()


def test_team_form_evidence_history_preserves_versions_and_is_idempotent():
    conn = _memory_db()
    repo = StatsRepo(conn)

    old_hash = "1" * 64
    new_hash = "2" * 64
    old_form = _seed_team_form(
        conn,
        old_hash,
        ["api-football:1183398", "api-football:1520718"],
    )
    repo.save_team_form(old_form)
    repo.save_team_form(old_form)

    new_form = _seed_team_form(
        conn,
        new_hash,
        ["api-football:1183398", "api-football:1520718"],
    )
    new_form.l10_values = [7.0, 6.0]
    new_form.l5_values = [7.0, 6.0]
    new_form.l10_avg = 6.5
    new_form.l5_avg = 6.5
    new_form.trend = "up"
    new_form.updated_at = "2026-06-12T09:00:00+00:00"
    repo.save_team_form(new_form)

    history_rows = conn.execute(
        "SELECT evidence_hash, observed_at FROM team_form_evidence_history "
        "ORDER BY observed_at, evidence_hash"
    ).fetchall()
    current_row = conn.execute(
        "SELECT evidence_hash, source_event_ids FROM team_form "
        "WHERE stat_key = 'corners'"
    ).fetchone()

    assert [(row[0], row[1]) for row in history_rows] == [
        (old_hash, "2026-06-12T08:00:00+00:00"),
        (new_hash, "2026-06-12T09:00:00+00:00"),
    ]
    assert current_row[0] == new_hash
    assert json.loads(current_row[1]) == [
        "api-football:1183398",
        "api-football:1520718",
    ]
    conn.close()
