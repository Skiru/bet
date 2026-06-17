import json
import os
import sqlite3
import subprocess
import sys

from bet.integration.telemetry_wrapper import TransportResult
from scripts.enrichment.football_history import FrozenClock, RuntimeOverrides, run_cli


def test_source_scan_proves_mock_cli_acquisition_absent():
    with open("scripts/enrichment/football_history.py", encoding="utf-8") as f:
        src = f.read()
    assert "MOCK_CLI_ACQUISITION" not in src
    assert "is_mock" not in src
    assert "mock_scope" not in src


def create_test_bundle(evidence_root, fixture_id="1001"):
    import hashlib
    fixture_payload = {
        "response": [
            {
                "fixture": {"id": int(fixture_id), "status": {"short": "FT"}, "date": "2023-01-01T15:00:00Z"},
                "league": {"id": 39, "name": "Premier League", "season": 2023},
                "teams": {
                    "home": {"id": 33, "name": "Manchester United"},
                    "away": {"id": 34, "name": "Newcastle"}
                },
                "goals": {"home": 2, "away": 1},
                "score": {"penalty": {"home": None, "away": None}}
            }
        ]
    }

    stats_payload = {
        "response": [
            {
                "team": {"id": 33},
                "statistics": [
                    {"type": "Shots on Goal", "value": 5},
                    {"type": "Total Shots", "value": 10},
                    {"type": "Ball Possession", "value": "55%"},
                    {"type": "Fouls", "value": 12},
                    {"type": "Yellow Cards", "value": 2},
                    {"type": "Red Cards", "value": 0},
                    {"type": "Offsides", "value": 1},
                    {"type": "Corner Kicks", "value": 4},
                    {"type": "Goalkeeper Saves", "value": 3}
                ]
            },
            {
                "team": {"id": 34},
                "statistics": [
                    {"type": "Shots on Goal", "value": 3},
                    {"type": "Total Shots", "value": 8},
                    {"type": "Ball Possession", "value": "45%"},
                    {"type": "Fouls", "value": 10},
                    {"type": "Yellow Cards", "value": 1},
                    {"type": "Red Cards", "value": 0},
                    {"type": "Offsides", "value": 2},
                    {"type": "Corner Kicks", "value": 3},
                    {"type": "Goalkeeper Saves", "value": 4}
                ]
            }
        ]
    }

    fix_bytes = json.dumps(fixture_payload).encode("utf-8")
    fix_sha = hashlib.sha256(fix_bytes).hexdigest()
    fix_path = evidence_root / "objects" / fix_sha[:2] / fix_sha
    fix_path.parent.mkdir(parents=True, exist_ok=True)
    fix_path.write_bytes(fix_bytes)

    stats_bytes = json.dumps(stats_payload).encode("utf-8")
    stats_sha = hashlib.sha256(stats_bytes).hexdigest()
    stats_path = evidence_root / "objects" / stats_sha[:2] / stats_sha
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_bytes(stats_bytes)

    from bet.integration.evidence import EvidenceRef, write_bundle_manifest

    ref_fix = EvidenceRef(
        operation="history_discovery",
        request_identity="GET https://v3.football.api-sports.io/fixtures?league=39&season=2023",
        media_type="application/json",
        byte_size=len(fix_bytes),
        object_sha256=fix_sha,
        source_event_id=None,
        http_status=200,
        captured_at="2023-01-01T15:00:00Z"
    )

    ref_stats = EvidenceRef(
        operation="history_statistics",
        request_identity=f"GET https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}",
        media_type="application/json",
        byte_size=len(stats_bytes),
        object_sha256=stats_sha,
        source_event_id=fixture_id,
        http_status=200,
        captured_at="2023-01-01T15:01:00Z"
    )

    bundle_id, manifest_path = write_bundle_manifest(
        registered_source_key="api-football",
        projection_name="api-football-team-facts-v1",
        canonical_fixture_id=1,
        parser_version="api-football-team-facts-v1",
        source_event_refs=[f"api-football:{fixture_id}"],
        evidence_refs=[ref_fix, ref_stats],
        evidence_root=evidence_root
    )

    return bundle_id


def test_cli_e2e_scenarios(tmp_path):
    db_path = tmp_path / "test.db"
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()

    discovery_call_count = 0
    details_call_count = 0

    def mock_wrap_request(provider, request_fn, url, method="GET", scope_id="", **kwargs):
        nonlocal discovery_call_count, details_call_count
        params = kwargs.get("params") or {}

        if "/fixtures" in url and "league" in params:
            discovery_call_count += 1
            body = {
                "response": [
                    {
                        "fixture": {"id": 1001, "status": {"short": "FT"}, "date": "2023-01-01T15:00:00Z"},
                        "league": {"id": 39, "name": "Premier League", "season": 2023},
                        "teams": {
                            "home": {"id": 33, "name": "Manchester United"},
                            "away": {"id": 34, "name": "Newcastle"}
                        },
                        "goals": {"home": 2, "away": 1},
                        "score": {"penalty": {"home": None, "away": None}}
                    }
                ]
            }
            return TransportResult(
                success=True,
                status_code=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps(body).encode("utf-8")
            )

        elif "/fixtures" in url and "ids" in params:
            details_call_count += 1
            body = {
                "response": [
                    {
                        "fixture": {"id": 1001, "status": {"short": "FT"}, "date": "2023-01-01T15:00:00Z"},
                        "statistics": [
                            {
                                "team": {"id": 33},
                                "statistics": [
                                    {"type": "Shots on Goal", "value": 5},
                                    {"type": "Total Shots", "value": 10},
                                    {"type": "Ball Possession", "value": "55%"},
                                    {"type": "Fouls", "value": 12},
                                    {"type": "Yellow Cards", "value": 2},
                                    {"type": "Red Cards", "value": 0},
                                    {"type": "Offsides", "value": 1},
                                    {"type": "Corner Kicks", "value": 4},
                                    {"type": "Goalkeeper Saves", "value": 3}
                                ]
                            },
                            {
                                "team": {"id": 34},
                                "statistics": [
                                    {"type": "Shots on Goal", "value": 3},
                                    {"type": "Total Shots", "value": 8},
                                    {"type": "Ball Possession", "value": "45%"},
                                    {"type": "Fouls", "value": 10},
                                    {"type": "Yellow Cards", "value": 1},
                                    {"type": "Red Cards", "value": 0},
                                    {"type": "Offsides", "value": 2},
                                    {"type": "Corner Kicks", "value": 3},
                                    {"type": "Goalkeeper Saves", "value": 4}
                                ]
                            }
                        ]
                    }
                ]
            }
            return TransportResult(
                success=True,
                status_code=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps(body).encode("utf-8")
            )

        return TransportResult(
            success=False,
            status_code=404,
            body=b"{}"
        )

    overrides = RuntimeOverrides(
        wrap_request=mock_wrap_request,
        clock=FrozenClock("2023-01-03T12:00:00Z"),
        evidence_root=evidence_root
    )

    bootstrap_args = [
        "bootstrap",
        "--db", str(db_path),
        "--competition-id", "39",
        "--season", "2023",
        "--from", "2023-01-01",
        "--to", "2023-01-02"
    ]
    ret = run_cli(bootstrap_args, overrides=overrides)
    assert ret == 0
    assert discovery_call_count == 1
    assert details_call_count == 1

    conn = sqlite3.connect(db_path)
    try:
        fixtures = conn.execute("SELECT id, status, score_home, score_away FROM fixtures").fetchall()
        assert len(fixtures) == 1
        assert fixtures[0][1] == "finished"
        assert fixtures[0][2] == 2
        assert fixtures[0][3] == 1
        fixture_id = fixtures[0][0]

        teams = conn.execute("SELECT id, name FROM teams").fetchall()
        assert len(teams) == 2

        obs = conn.execute("SELECT id, team_id, capability, status, evidence_bundle_id FROM fixture_capability_observation").fetchall()
        assert len(obs) == 2
        for row in obs:
            assert row[2] == "TEAM_MATCH_FACTS"
            assert row[3] == "SUCCESS"
            bundle_id = row[4]
            assert bundle_id is not None

    finally:
        conn.close()

    # Now we write a real bundle manifest under evidence_root for Replay to load
    real_replay_bundle_id = create_test_bundle(evidence_root, fixture_id="1001")

    discovery_call_count = 0
    details_call_count = 0
    inc_args = [
        "incremental-sync",
        "--db", str(db_path),
        "--competition-id", "39",
        "--season", "2023",
        "--correction-lookback-days", "0"
    ]
    ret_inc = run_cli(inc_args, overrides=overrides)
    assert ret_inc == 0
    assert discovery_call_count == 1
    assert details_call_count == 0

    discovery_call_count = 0
    details_call_count = 0
    replay_args = [
        "replay",
        "--db", str(db_path),
        "--evidence-bundle", real_replay_bundle_id
    ]
    ret_replay = run_cli(replay_args, overrides=overrides)
    assert ret_replay == 0
    assert discovery_call_count == 0
    assert details_call_count == 0

    snap_args = [
        "build-snapshot",
        "--db", str(db_path),
        "--canonical-target-fixture-id", str(fixture_id),
        "--analysis-cutoff-at", "2023-01-02T12:00:00Z",
        "--policy-version", "1"
    ]
    ret_snap = run_cli(snap_args, overrides=overrides)
    assert ret_snap == 0

    conn = sqlite3.connect(db_path)
    try:
        snapshots = conn.execute("SELECT id, run_id, canonical_fixture_id, snapshot_hash FROM analysis_snapshot").fetchall()
        assert len(snapshots) == 1
        assert snapshots[0][2] == fixture_id
    finally:
        conn.close()

    inspect_args = [
        "inspect",
        "--db", str(db_path),
        "--fixture-id", str(fixture_id)
    ]
    ret_inspect = run_cli(inspect_args, overrides=overrides)
    assert ret_inspect == 0

    inspect_args_not_found = [
        "inspect",
        "--db", str(db_path),
        "--fixture-id", "99999"
    ]
    ret_inspect_not_found = run_cli(inspect_args_not_found, overrides=overrides)
    assert ret_inspect_not_found == 2


def test_cli_subprocess_execution(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = "src"

    res = subprocess.run(
        [sys.executable, "-m", "scripts.enrichment.football_history", "--help"],
        capture_output=True,
        text=True,
        env=env
    )
    assert res.returncode == 0
    assert "bootstrap" in res.stdout
