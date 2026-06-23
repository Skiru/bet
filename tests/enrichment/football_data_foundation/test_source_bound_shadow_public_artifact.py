import ast
import json
import sqlite3
from pathlib import Path
import pytest

from bet.enrichment.football_data_foundation.source_bound_shadow.verifier import (
    verify_public_python_source,
    verify_sqlite_blob,
    verify_public_json_report,
    verify_shadow_bundle,
)
from bet.enrichment.football_data_foundation.source_bound_shadow.runner import (
    run_source_bound_shadow_enrichment,
)
from bet.enrichment.football_data_foundation.source_bound_shadow.writer import (
    write_shadow_json,
)
from bet.enrichment.football_data_foundation.source_bound_shadow.contracts import (
    NormalizedMatchSnapshot,
    NetworkProbeResult,
)


def test_public_raw_checker_fails_collapsed() -> None:
    # REQ-TEST-001 public raw checker fails collapsed one-line Python.
    text = "import ast; import json; def f(): return 1"
    res = verify_public_python_source("verifier.py", text)
    assert not res.passed
    assert "PUBLIC_RAW_COLLAPSED" in res.failures


def test_public_raw_checker_passes_normal() -> None:
    # REQ-TEST-002 public raw checker passes normal multi-line Python.
    lines = ["# normal multi-line python code", "def test_func():", "    x = 10", "    return x"]
    for i in range(50):
        lines.append(f"y_{i} = {i}")
    text = "\n".join(lines)
    res = verify_public_python_source("verifier.py", text)
    assert res.passed
    assert res.line_count >= 40


def test_sqlite_verifier_fails_zero_byte() -> None:
    # REQ-TEST-003 SQLite verifier fails zero-byte blob.
    res = verify_sqlite_blob("source_bound_shadow.sqlite", b"")
    assert not res.passed
    assert "SQLITE_BLOB_TOO_SMALL:0" in res.failures


def test_sqlite_verifier_fails_missing_tables(tmp_path: Path) -> None:
    # REQ-TEST-004 SQLite verifier fails missing required tables.
    db_path = tmp_path / "missing.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE dummy (col TEXT)")
    conn.commit()
    conn.close()
    
    blob = db_path.read_bytes()
    res = verify_sqlite_blob("source_bound_shadow.sqlite", blob)
    assert not res.passed
    assert any("SQLITE_MISSING_TABLES" in f for f in res.failures)


def test_sqlite_verifier_fails_missing_provider_rows(tmp_path: Path) -> None:
    # REQ-TEST-005 SQLite verifier fails facts table with missing provider rows.
    db_path = tmp_path / "missing_providers.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE snapshot_metadata (key TEXT, value TEXT)")
    conn.execute("CREATE TABLE provider_ids (provider TEXT, provider_id TEXT)")
    conn.execute("CREATE TABLE facts (source TEXT, fact_type TEXT, key TEXT, value_json TEXT)")
    conn.execute("CREATE TABLE conflicts (value TEXT)")
    conn.execute("INSERT INTO facts VALUES ('api-football', 'fact', 'key', '{}')")
    conn.commit()
    conn.close()

    blob = db_path.read_bytes()
    res = verify_sqlite_blob("source_bound_shadow.sqlite", blob)
    assert not res.passed
    assert any("SQLITE_FACTS_MISSING_PROVIDERS" in f for f in res.failures)


def test_sqlite_verifier_passes_valid(tmp_path: Path) -> None:
    # REQ-TEST-006 SQLite verifier passes valid SQLite with all five provider rows.
    db_path = tmp_path / "valid.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE snapshot_metadata (key TEXT, value TEXT)")
    conn.execute("CREATE TABLE provider_ids (provider TEXT, provider_id TEXT)")
    conn.execute("CREATE TABLE facts (source TEXT, fact_type TEXT, key TEXT, value_json TEXT)")
    conn.execute("CREATE TABLE conflicts (value TEXT)")
    
    for prov in ["api-football", "football-data-org", "espn-baseline", "sportdb", "highlightly"]:
        conn.execute("INSERT INTO facts VALUES (?, 'fact', 'key', '{}')", (prov,))
    conn.commit()
    conn.close()

    blob = db_path.read_bytes()
    res = verify_sqlite_blob("source_bound_shadow.sqlite", blob)
    assert res.passed
    assert res.provider_count == 5


def test_verifier_json_contains_proof_fields(tmp_path: Path) -> None:
    # REQ-TEST-007 verifier JSON contains public artifact proof fields.
    sqlite_path = tmp_path / "db.sqlite"
    conn = sqlite3.connect(sqlite_path)
    conn.execute("CREATE TABLE snapshot_metadata (key TEXT, value TEXT)")
    conn.execute("CREATE TABLE provider_ids (provider TEXT, provider_id TEXT)")
    conn.execute("CREATE TABLE facts (source TEXT, fact_type TEXT, key TEXT, value_json TEXT)")
    conn.execute("CREATE TABLE conflicts (value TEXT)")
    conn.execute("INSERT INTO snapshot_metadata VALUES ('shadow_status', 'SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW')")
    conn.execute("INSERT INTO snapshot_metadata VALUES ('fixture_slug', 'worldcup2026-norway-senegal')")
    for prov in ["api-football", "football-data-org", "espn-baseline", "sportdb", "highlightly"]:
        conn.execute("INSERT INTO provider_ids VALUES (?, 'id')", (prov,))
        conn.execute("INSERT INTO facts VALUES (?, 'score', 'full_time_score', '{}')", (prov,))
    conn.commit()
    conn.close()

    snapshot_data = {
        "fixture_slug": "worldcup2026-norway-senegal",
        "provider_ids": {
            "sportdb": "xSUJLPV8",
            "highlightly": "1267481035",
            "api-football": "1489401",
            "football-data-org": "537394",
            "espn-baseline": "760454"
        },
        "score": {"home": 3, "away": 2},
        "status": "FINISHED",
        "kickoff_utc": "2026-06-23T00:00:00Z",
        "teams": {"home": "Norway", "away": "Senegal"},
        "competition": "FIFA World Cup",
        "venue": "MetLife Stadium",
        "referee": "Sampaio W.",
        "facts": [
            {"source": "sportdb", "source_role": "source_bound_flashscore_replay", "fact_type": "fixture_identity", "key": "fixture_slug", "value": "x", "body_sha256": "sha", "source_file": "file"},
            {"source": "highlightly", "source_role": "source_bound_detailed_replay", "fact_type": "fixture_identity", "key": "fixture_slug", "value": "x", "body_sha256": "sha", "source_file": "file"},
            {"source": "api-football", "source_role": "primary_detailed_replay", "fact_type": "match_event_summary", "key": "event_summary", "value": {}, "body_sha256": "sha", "source_file": "file"},
            {"source": "football-data-org", "source_role": "current_reference_replay", "fact_type": "score", "key": "full_time_score", "value": {"home": 3, "away": 2}, "body_sha256": "sha", "source_file": "file"},
            {"source": "espn-baseline", "source_role": "unofficial_shadow_cross_check", "fact_type": "fixture_identity", "key": "fixture_slug", "value": "x", "body_sha256": "sha", "source_file": "file"},
            {"source": "sportdb", "source_role": "source_bound_flashscore_replay", "fact_type": "odds_reference", "key": "odds_reference_available", "value": {"odds_reference_available": True}, "body_sha256": "sha", "source_file": "file"},
            {"source": "highlightly", "source_role": "source_bound_detailed_replay", "fact_type": "match_event_summary", "key": "event_summary", "value": {}, "body_sha256": "sha", "source_file": "file"},
            {"source": "api-football", "source_role": "primary_detailed_replay", "fact_type": "lineup_summary", "key": "lineup_summary", "value": {}, "body_sha256": "sha", "source_file": "file"},
            {"source": "sportdb", "source_role": "source_bound_flashscore_replay", "fact_type": "lineup_summary", "key": "lineup_summary", "value": {}, "body_sha256": "sha", "source_file": "file"},
            {"source": "highlightly", "source_role": "source_bound_detailed_replay", "fact_type": "lineup_summary", "key": "lineup_summary", "value": {}, "body_sha256": "sha", "source_file": "file"},
            {"source": "api-football", "source_role": "primary_detailed_replay", "fact_type": "statistics_summary", "key": "statistics_summary", "value": {}, "body_sha256": "sha", "source_file": "file"},
            {"source": "sportdb", "source_role": "source_bound_flashscore_replay", "fact_type": "statistics_summary", "key": "statistics_summary", "value": {}, "body_sha256": "sha", "source_file": "file"},
            {"source": "highlightly", "source_role": "source_bound_detailed_replay", "fact_type": "statistics_summary", "key": "statistics_summary", "value": {}, "body_sha256": "sha", "source_file": "file"}
        ],
        "conflicts": [],
        "source_priority": ["api-football", "sportdb", "highlightly", "football-data-org", "espn-baseline"],
        "production_selectable": False,
        "manual_authorization_required": True,
        "shadow_status": "SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW"
    }
    json_path = tmp_path / "snapshot.json"
    json_path.write_text(json.dumps(snapshot_data, indent=2, sort_keys=True), encoding="utf-8")

    probe = NetworkProbeResult(True, 0, "monkeypatch", "tmp")
    res = verify_shadow_bundle(json_path, sqlite_path, Path("d"), Path("c"), network_probe=probe)
    
    assert "public_raw_reviewability_check" in res
    assert "committed_blob_sqlite_check" in res
    assert "public_raw_sqlite_check" in res
    assert "public_artifact_proof_path" in res


def test_final_json_writer_pretty_prints(tmp_path: Path) -> None:
    # REQ-TEST-008 final JSON writer pretty-prints with indent=2 and sorted keys.
    snapshot = NormalizedMatchSnapshot(
        fixture_slug="slug",
        provider_ids={"api-football": "1"},
        teams={"home": "A", "away": "B"},
        status="FINISHED",
        score={"home": 1, "away": 0},
        kickoff_utc="utc",
        competition="comp",
        venue="venue",
        referee="ref",
    )
    json_path = tmp_path / "snapshot.json"
    write_shadow_json(snapshot, json_path)
    
    content = json_path.read_text(encoding="utf-8")
    expected = json.dumps(snapshot.to_json(), indent=2, sort_keys=True) + "\n"
    assert content == expected


def test_snapshot_json_not_collapsed() -> None:
    # REQ-TEST-009 snapshot JSON is not collapsed.
    local_snapshot_path = Path("reports/football_data_foundation/source_bound_shadow/worldcup2026_norway_senegal/source_bound_shadow_snapshot.json")
    if local_snapshot_path.exists():
        text = local_snapshot_path.read_text(encoding="utf-8")
        res = verify_public_json_report(str(local_snapshot_path), text)
        assert res["passed"]
        assert "JSON_REPORT_COLLAPSED" not in res["failures"]


def test_source_files_remain_ast_parseable_and_multiline() -> None:
    # REQ-TEST-010 source files remain ast-parseable and multi-line.
    src_dir = Path("src/bet/enrichment/football_data_foundation/source_bound_shadow")
    for f in src_dir.glob("*.py"):
        if f.name == "__init__.py":
            continue
        text = f.read_text(encoding="utf-8")
        ast.parse(text)
        assert len(text.splitlines()) >= 40


def test_network_blocked_runner(tmp_path: Path) -> None:
    # REQ-TEST-011 network-blocked runner test still passes.
    result = run_source_bound_shadow_enrichment(
        project_root=Path("."),
        output_root=tmp_path / "reports/football_data_foundation/source_bound_shadow/worldcup2026_norway_senegal",
        fixture_slug="worldcup2026-norway-senegal",
    )
    assert result["verdict"] == "PASS"
    assert result["network_probe_check"] == "PASS"


def test_no_committed_test_report_dir() -> None:
    # REQ-TEST-012 no committed test report artifact directory exists.
    test_report_dir = Path("reports/football_data_foundation/source_bound_shadow/worldcup2026_norway_senegal_test")
    assert not test_report_dir.exists()
