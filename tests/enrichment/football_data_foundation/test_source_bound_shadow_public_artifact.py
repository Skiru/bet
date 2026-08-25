import ast
import json
import sqlite3
from pathlib import Path
import pytest

from bet.enrichment.football_data_foundation.source_bound_shadow.verifier import (
    check_public_raw_python,
    check_json_report,
    check_sqlite_blob_bytes,
    validate_artifact_proof_semantics,
    verify_public_python_source,
    verify_sqlite_blob,
    verify_public_json_report,
    verify_shadow_bundle,
)
from bet.enrichment.football_data_foundation.source_bound_shadow.runner import (
    run_source_bound_shadow_enrichment,
)
from bet.enrichment.football_data_foundation.source_bound_shadow.contracts import (
    NetworkProbeResult,
)

REQUIRED_TABLES = {"snapshot_metadata", "provider_ids", "facts", "conflicts"}
REQUIRED_PROVIDERS = {"api-football", "football-data-org", "espn-baseline", "sportdb", "highlightly"}


def test_req_test_001_public_raw_checker_fails_collapsed_one_line() -> None:
    # REQ-TEST-001 public raw checker fails collapsed one-line contracts.py-like source.
    raw = b"from dataclasses import dataclass class A: pass def f(): return 1\n"
    res = check_public_raw_python("contracts.py", raw)
    assert not res.passed
    assert "COLLAPSED_PUBLIC_RAW_SHAPE" in res.failures


def test_req_test_002_public_raw_checker_fails_13_line_source() -> None:
    # REQ-TEST-002 public raw checker fails 13-line verifier.py-like source.
    lines = ["# 13 lines of python code"]
    for i in range(12):
        lines.append(f"x_{i} = {i}")
    raw = "\n".join(lines).encode("utf-8")
    res = check_public_raw_python("verifier.py", raw)
    assert not res.passed
    assert any("TOO_FEW_LINES" in f for f in res.failures) or "COLLAPSED_PUBLIC_RAW_SHAPE" in res.failures


def test_req_test_003_public_raw_checker_fails_2_line_source() -> None:
    # REQ-TEST-003 public raw checker fails 2-line fuser.py-like source.
    raw = b"import json\nprint('hello')\n"
    res = check_public_raw_python("fuser.py", raw)
    assert not res.passed
    assert any("TOO_FEW_LINES" in f for f in res.failures) or "COLLAPSED_PUBLIC_RAW_SHAPE" in res.failures


def test_req_test_004_public_raw_checker_passes_normal_python() -> None:
    # REQ-TEST-004 public raw checker passes normal multi-line Python.
    lines = ["# normal python file", "import os", "class Normal:", "    def run(self):", "        return 42"]
    for i in range(45):
        lines.append(f"def f_{i}(): return {i}")
    raw = "\n".join(lines).encode("utf-8")
    res = check_public_raw_python("normal.py", raw)
    assert res.passed, res.failures


def test_req_test_005_json_report_checker_fails_one_line() -> None:
    # REQ-TEST-005 JSON report checker fails one-line public_artifact_proof.json.
    raw = b'{"verdict":"PASS","source_file_checks":{"verifier.py":true}}'
    res = check_json_report("public_artifact_proof.json", raw)
    assert not res.passed
    assert any("NOT_PRETTY_PRINTED" in f for f in res.failures)


def test_req_test_006_json_report_checker_passes_pretty() -> None:
    # REQ-TEST-006 JSON report checker passes pretty-printed multi-line JSON.
    raw = b"""{
  "failed_requirements": [],
  "line_1": true,
  "line_2": true,
  "line_3": true,
  "line_4": true,
  "line_5": true,
  "line_6": true,
  "line_7": true,
  "line_8": true,
  "verdict": "PASS"
}
"""
    res = check_json_report("public_artifact_proof.json", raw)
    assert res.passed, res.failures


def test_req_test_007_proof_semantics_fails_if_final_sha_missing() -> None:
    # REQ-TEST-007 proof semantics checker fails if final_public_proof_commit_sha is missing.
    proof = {
        "artifact_commit_sha": "abc123",
        "proof_commit_sha": "def456",
        "source_file_checks": {"verifier.py": True},
        "report_file_checks": {"public_artifact_proof.json": True},
        "committed_sqlite_header_ok": True,
        "public_raw_sqlite_header_ok": True,
        "verdict": "PASS",
    }
    res = validate_artifact_proof_semantics(proof, expected_final_commit_sha="def456")
    assert not res.passed
    assert any("FINAL_PROOF_COMMIT_MISMATCH" in f or "MISSING" in f for f in res.failures)


def test_req_test_008_proof_semantics_fails_if_final_sha_mismatch() -> None:
    # REQ-TEST-008 proof semantics checker fails if final_public_proof_commit_sha does not equal final pushed commit.
    proof = {
        "artifact_commit_sha": "abc123",
        "proof_commit_sha": "def456",
        "final_public_proof_commit_sha": "def456_wrong",
        "source_file_checks": {"verifier.py": True},
        "report_file_checks": {"public_artifact_proof.json": True},
        "committed_sqlite_header_ok": True,
        "public_raw_sqlite_header_ok": True,
        "verdict": "PASS",
    }
    res = validate_artifact_proof_semantics(proof, expected_final_commit_sha="def456")
    assert not res.passed
    assert any("FINAL_PROOF_COMMIT_MISMATCH" in f for f in res.failures)


def test_req_test_009_proof_semantics_permits_different_artifact_sha() -> None:
    # REQ-TEST-009 proof semantics checker permits artifact_commit_sha different from proof_commit_sha when both are explicit.
    proof = {
        "artifact_commit_sha": "abc123",
        "proof_commit_sha": "def456",
        "final_public_proof_commit_sha": "def456",
        "source_file_checks": {"verifier.py": True},
        "report_file_checks": {"public_artifact_proof.json": True},
        "committed_sqlite_header_ok": True,
        "public_raw_sqlite_header_ok": True,
        "verdict": "PASS",
    }
    res = validate_artifact_proof_semantics(proof, expected_final_commit_sha="def456", expected_artifact_commit_sha="abc123")
    assert res.passed, res.failures


def test_req_test_010_sqlite_checker_fails_zero_byte() -> None:
    # REQ-TEST-010 SQLite checker fails zero-byte blob.
    res = check_sqlite_blob_bytes("shadow.sqlite", b"", required_tables=REQUIRED_TABLES, required_providers=REQUIRED_PROVIDERS)
    assert not res.passed
    assert any("SQLITE_HEADER_INVALID" in f or "SQLITE_TOO_SMALL" in f for f in res.failures)


def test_req_test_011_sqlite_checker_fails_missing_tables(tmp_path: Path) -> None:
    # REQ-TEST-011 SQLite checker fails missing required tables.
    db_path = tmp_path / "missing_tables.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE dummy (val TEXT)")
    conn.commit()
    conn.close()
    blob = db_path.read_bytes()
    res = check_sqlite_blob_bytes("shadow.sqlite", blob, required_tables=REQUIRED_TABLES, required_providers=REQUIRED_PROVIDERS)
    assert not res.passed
    assert any("SQLITE_MISSING_TABLES" in f for f in res.failures)


def test_req_test_012_sqlite_checker_fails_missing_provider(tmp_path: Path) -> None:
    # REQ-TEST-012 SQLite checker fails facts table missing any required provider.
    db_path = tmp_path / "missing_provider.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE snapshot_metadata (k TEXT, v TEXT)")
    conn.execute("CREATE TABLE provider_ids (p TEXT)")
    conn.execute("CREATE TABLE facts (source TEXT, fact_type TEXT, key TEXT, value TEXT)")
    conn.execute("CREATE TABLE conflicts (c TEXT)")
    conn.execute("INSERT INTO facts VALUES ('api-football', 'score', 'score', '{}')")
    conn.commit()
    conn.close()
    blob = db_path.read_bytes()
    res = check_sqlite_blob_bytes("shadow.sqlite", blob, required_tables=REQUIRED_TABLES, required_providers=REQUIRED_PROVIDERS)
    assert not res.passed
    assert any("SQLITE_FACTS_MISSING_PROVIDERS" in f or "SQLITE_PROVIDER_ROWS_MISSING" in f for f in res.failures)


def test_req_test_013_sqlite_checker_passes_valid(tmp_path: Path) -> None:
    # REQ-TEST-013 SQLite checker passes valid SQLite with all five provider rows.
    db_path = tmp_path / "valid.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE snapshot_metadata (k TEXT, v TEXT)")
    conn.execute("CREATE TABLE provider_ids (source TEXT, provider_id TEXT)")
    conn.execute("CREATE TABLE facts (source TEXT, fact_type TEXT, key TEXT, value TEXT)")
    conn.execute("CREATE TABLE conflicts (c TEXT)")
    for provider in REQUIRED_PROVIDERS:
        conn.execute("INSERT INTO facts VALUES (?, 'score', 'score', '{}')", (provider,))
    conn.commit()
    conn.close()
    blob = db_path.read_bytes()
    res = check_sqlite_blob_bytes("shadow.sqlite", blob, required_tables=REQUIRED_TABLES, required_providers=REQUIRED_PROVIDERS, min_size=128)
    assert res.passed, res.failures


def test_req_test_014_verifier_result_includes_final_public_truth_fields(tmp_path: Path) -> None:
    # REQ-TEST-014 verifier result includes final public truth fields.
    sqlite_path = tmp_path / "reports/football_data_foundation/source_bound_shadow/db.sqlite"
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(sqlite_path)
    conn.execute("CREATE TABLE snapshot_metadata (key TEXT, value TEXT)")
    conn.execute("CREATE TABLE provider_ids (provider TEXT, provider_id TEXT)")
    conn.execute("CREATE TABLE facts (source TEXT, fact_type TEXT, key TEXT, value_json TEXT)")
    conn.execute("CREATE TABLE conflicts (value TEXT)")
    conn.execute("INSERT INTO snapshot_metadata VALUES ('shadow_status', 'SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW')")
    conn.execute("INSERT INTO snapshot_metadata VALUES ('fixture_slug', 'worldcup2026-norway-senegal')")
    for prov in REQUIRED_PROVIDERS:
        conn.execute("INSERT INTO provider_ids VALUES (?, 'id')", (prov,))
        conn.execute("INSERT INTO facts VALUES (?, 'score', 'full_time_score', '{}')", (prov,))
    conn.commit()
    conn.close()

    snapshot_data = {
        "fixture_slug": "worldcup2026-norway-senegal",
        "provider_ids": {p: "id" for p in REQUIRED_PROVIDERS},
        "score": {"home": 3, "away": 2},
        "status": "FINISHED",
        "kickoff_utc": "2026-06-23T00:00:00Z",
        "teams": {"home": "Norway", "away": "Senegal"},
        "competition": "FIFA World Cup",
        "venue": "MetLife Stadium",
        "referee": "Sampaio W.",
        "facts": [
            {"source": p, "source_role": "source_bound_flashscore_replay" if p != "api-football" else "primary_detailed_replay", "fact_type": "odds_reference" if p == "sportdb" else "match_event_summary", "key": "odds_reference_available" if p == "sportdb" else "event_summary", "value": {}, "body_sha256": "sha", "source_file": "file"}
            for p in REQUIRED_PROVIDERS
        ],
        "conflicts": [],
        "source_priority": ["api-football", "sportdb", "highlightly", "football-data-org", "espn-baseline"],
        "production_selectable": False,
        "manual_authorization_required": True,
        "shadow_status": "SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW"
    }
    json_path = tmp_path / "reports/football_data_foundation/source_bound_shadow/snapshot.json"
    json_path.write_text(json.dumps(snapshot_data, indent=2, sort_keys=True), encoding="utf-8")

    probe = NetworkProbeResult(True, 0, "monkeypatch", "tmp")
    res = verify_shadow_bundle(json_path, sqlite_path, Path("d"), Path("c"), network_probe=probe)

    assert "public_raw_reviewability_check" in res
    assert "public_raw_report_format_check" in res
    assert "committed_blob_sqlite_check" in res
    assert "public_raw_sqlite_check" in res
    assert "artifact_commit_sha" in res
    assert "proof_commit_sha" in res
    assert "final_public_proof_commit_sha" in res


def test_req_test_015_network_blocked_runner(tmp_path: Path) -> None:
    # REQ-TEST-015 network-blocked runner test still passes.
    result = run_source_bound_shadow_enrichment(
        project_root=Path("tests/fixtures"),
        output_root=tmp_path / "reports/football_data_foundation/source_bound_shadow/worldcup2026_norway_senegal",
        fixture_slug="worldcup2026-norway-senegal",
    )
    assert result["verdict"] == "PASS"
    assert result["network_probe_check"] == "PASS"


def test_req_test_016_no_committed_test_report_dir() -> None:
    # REQ-TEST-016 no committed test report artifact directory exists.
    test_report_dir = Path("reports/football_data_foundation/source_bound_shadow/worldcup2026_norway_senegal_test")
    assert not test_report_dir.exists()
