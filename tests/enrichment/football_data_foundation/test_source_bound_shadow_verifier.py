import json
from pathlib import Path
from bet.enrichment.football_data_foundation.source_bound_shadow.verifier import verify_shadow_bundle

def _write_file(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path

def _valid_bundle_data() -> dict:
    return {
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
            {"source": "api-football", "source_role": "primary_detailed_replay", "fact_type": "match_event_summary", "key": "event_summary", "value": {"event_count": 10, "goals": [], "cards_count": 0, "substitutions_count": 0, "provider_event_categories": []}, "body_sha256": "sha", "source_file": "file"},
            {"source": "football-data-org", "source_role": "current_reference_replay", "fact_type": "score", "key": "full_time_score", "value": {"home": 3, "away": 2}, "body_sha256": "sha", "source_file": "file"},
            {"source": "espn-baseline", "source_role": "unofficial_shadow_cross_check", "fact_type": "fixture_identity", "key": "fixture_slug", "value": "x", "body_sha256": "sha", "source_file": "file"},
            {"source": "sportdb", "source_role": "source_bound_flashscore_replay", "fact_type": "odds_reference", "key": "odds_reference_available", "value": {"odds_reference_available": True, "bookmaker_count": 1, "market_count": 1, "decision_use": "forbidden_reference_only"}, "body_sha256": "sha", "source_file": "file"},
            {"source": "sportdb", "source_role": "source_bound_flashscore_replay", "fact_type": "match_event_summary", "key": "event_summary", "value": {"event_count": 5, "goals": [], "cards_count": 0, "substitutions_count": 0, "provider_event_categories": []}, "body_sha256": "sha", "source_file": "file"},
            {"source": "highlightly", "source_role": "source_bound_detailed_replay", "fact_type": "match_event_summary", "key": "event_summary", "value": {"event_count": 8, "goals": [], "cards_count": 0, "substitutions_count": 0, "provider_event_categories": []}, "body_sha256": "sha", "source_file": "file"}
        ],
        "conflicts": [],
        "source_priority": ["api-football", "sportdb", "highlightly", "football-data-org", "espn-baseline"],
        "production_selectable": False,
        "manual_authorization_required": True,
        "shadow_status": "SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW"
    }

def test_verifier_passes_valid_snapshot(tmp_path):
    # Ensure SQLite exists to pass sqlite content check
    sqlite_path = tmp_path / "reports/football_data_foundation/source_bound_shadow/db.sqlite"
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    import sqlite3
    conn = sqlite3.connect(sqlite_path)
    conn.execute("CREATE TABLE IF NOT EXISTS test (val TEXT)")
    conn.execute("INSERT INTO test VALUES ('ok')")
    conn.commit()
    conn.close()

    json_path = _write_file(tmp_path / "reports/football_data_foundation/source_bound_shadow/valid.json", _valid_bundle_data())
    res = verify_shadow_bundle(json_path, sqlite_path, Path("d"), Path("c"))
    assert res["verdict"] == "PASS"
    assert not res["failed_requirements"]

def test_verifier_fails_raw_payload_leakage(tmp_path):
    data = _valid_bundle_data()
    data["raw_payload"] = {"nested": "value"}
    json_path = _write_file(tmp_path / "reports/football_data_foundation/source_bound_shadow/leak.json", data)
    res = verify_shadow_bundle(json_path, json_path.parent / "db.sqlite", Path("d"), Path("c"))
    assert res["verdict"] == "FAIL"
    assert any("raw_payload" in f for f in res["failed_requirements"])

def test_verifier_fails_secret_header_leakage(tmp_path):
    data = _valid_bundle_data()
    data["facts"][0]["value"] = "Bearer secret_token_123"
    json_path = _write_file(tmp_path / "reports/football_data_foundation/source_bound_shadow/secret.json", data)
    res = verify_shadow_bundle(json_path, json_path.parent / "db.sqlite", Path("d"), Path("c"))
    assert res["verdict"] == "FAIL"
    assert any("secret" in f.lower() for f in res["failed_requirements"])

def test_verifier_fails_production_selectable_true(tmp_path):
    data = _valid_bundle_data()
    data["production_selectable"] = True
    json_path = _write_file(tmp_path / "reports/football_data_foundation/source_bound_shadow/prod_sel.json", data)
    res = verify_shadow_bundle(json_path, json_path.parent / "db.sqlite", Path("d"), Path("c"))
    assert res["verdict"] == "FAIL"
    assert "PRODUCTION_SELECTABLE_IS_TRUE" in res["failed_requirements"]

def test_verifier_fails_manual_authorization_required_false(tmp_path):
    data = _valid_bundle_data()
    data["manual_authorization_required"] = False
    json_path = _write_file(tmp_path / "reports/football_data_foundation/source_bound_shadow/manual_auth.json", data)
    res = verify_shadow_bundle(json_path, json_path.parent / "db.sqlite", Path("d"), Path("c"))
    assert res["verdict"] == "FAIL"
    assert "MANUAL_AUTHORIZATION_REQUIRED_IS_FALSE" in res["failed_requirements"]

def test_verifier_fails_betting_decisions(tmp_path):
    data = _valid_bundle_data()
    data["facts"][0]["value"] = "This is a betting recommendation tip"
    json_path = _write_file(tmp_path / "reports/football_data_foundation/source_bound_shadow/bet_dec.json", data)
    res = verify_shadow_bundle(json_path, json_path.parent / "db.sqlite", Path("d"), Path("c"))
    assert res["verdict"] == "FAIL"
    assert any("tip" in f or "decision" in f for f in res["failed_requirements"])

def test_verifier_fails_fewer_than_five_providers(tmp_path):
    data = _valid_bundle_data()
    data["facts"] = [f for f in data["facts"] if f["source"] != "espn-baseline"]
    json_path = _write_file(tmp_path / "reports/football_data_foundation/source_bound_shadow/few_prov.json", data)
    res = verify_shadow_bundle(json_path, json_path.parent / "db.sqlite", Path("d"), Path("c"))
    assert res["verdict"] == "FAIL"
    assert "FEWER_THAN_FIVE_PROVIDERS_CONTRIBUTE_FACTS" in res["failed_requirements"]

def test_verifier_fails_sportdb_odds_as_betting_decision(tmp_path):
    data = _valid_bundle_data()
    for f in data["facts"]:
        if f["source"] == "sportdb" and f["fact_type"] == "odds_reference":
            f["value"] = "recommending a betting tip"
    json_path = _write_file(tmp_path / "reports/football_data_foundation/source_bound_shadow/odds_dec.json", data)
    res = verify_shadow_bundle(json_path, json_path.parent / "db.sqlite", Path("d"), Path("c"))
    assert res["verdict"] == "FAIL"
    assert "SPORTDB_ODDS_CLASSIFIED_AS_BETTING_DECISION" in res["failed_requirements"]

def test_verifier_fails_raw_like_fact_types(tmp_path):
    data = _valid_bundle_data()
    data["facts"].append({"source": "api-football", "source_role": "primary_detailed_replay", "fact_type": "match_event", "key": "events", "value": "raw", "body_sha256": "sha", "source_file": "file"})
    json_path = _write_file(tmp_path / "reports/football_data_foundation/source_bound_shadow/raw_like.json", data)
    res = verify_shadow_bundle(json_path, json_path.parent / "db.sqlite", Path("d"), Path("c"))
    assert res["verdict"] == "FAIL"
    assert any("RAW_LIKE_FACT_TYPE_PRESENT" in f for f in res["failed_requirements"])

def test_verifier_fails_oversized_fact_value(tmp_path):
    data = _valid_bundle_data()
    data["facts"][0]["value"] = "x" * 13000
    json_path = _write_file(tmp_path / "reports/football_data_foundation/source_bound_shadow/oversized.json", data)
    res = verify_shadow_bundle(json_path, json_path.parent / "db.sqlite", Path("d"), Path("c"))
    assert res["verdict"] == "FAIL"
    assert any("FACT_VALUE_TOO_LARGE" in f for f in res["failed_requirements"])

