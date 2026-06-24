import tempfile
import json
from pathlib import Path
from bet.enrichment.football_data_foundation.worldcup_20260624_live_shadow.verifier import verify_live_shadow_run

def test_verifier_fails_fewer_than_4_shadow_ready() -> None:
    # TEST-011: verifier fails if fewer than 4 activation-compatible fixtures.
    run_summary = {
        "run_id": "run_test",
        "fixtures_attempted": ["f1", "f2", "f3", "f4", "f5", "f6"],
        "fixtures_shadow_ready": ["f1", "f2", "f3"], # only 3 ready, should fail
        "fixtures_blocked": ["f4", "f5", "f6"],
        "provider_matrix": {},
        "secret_leak_check": "PASS",
        "production_guardrail_check": "PASS",
        "betting_decision_check": "PASS",
        "final_status": "WORLD_CUP_2026_24_JUNE_LIVE_SHADOW_COMPLETE"
    }
    
    with tempfile.TemporaryDirectory() as tmp:
        res = verify_live_shadow_run(run_summary, Path(tmp))
        assert res["verdict"] == "FAIL"
        assert any("insufficient_shadow_ready_fixtures" in f for f in res["failed_requirements"])


def test_verifier_fails_betting_decision() -> None:
    # TEST-012: verifier fails betting decision text.
    run_summary = {
        "run_id": "run_test",
        "fixtures_attempted": ["f1", "f2", "f3", "f4", "f5", "f6"],
        "fixtures_shadow_ready": ["f1", "f2", "f3", "f4", "f5", "f6"],
        "fixtures_blocked": [],
        "provider_matrix": {},
        "secret_leak_check": "PASS",
        "production_guardrail_check": "PASS",
        "betting_decision_check": "PASS",
        "final_status": "WORLD_CUP_2026_24_JUNE_LIVE_SHADOW_COMPLETE",
        "notes": "We recommend placing a stake on Switzerland" # forbidden betting decision text
    }
    
    with tempfile.TemporaryDirectory() as tmp:
        res = verify_live_shadow_run(run_summary, Path(tmp))
        assert res["verdict"] == "FAIL"
        assert any("forbidden_token" in f for f in res["failed_requirements"])


def test_verifier_fails_production_selectable() -> None:
    # TEST-013: verifier fails production selectable.
    run_summary = {
        "run_id": "run_test",
        "fixtures_attempted": ["f1", "f2", "f3", "f4", "f5", "f6"],
        "fixtures_shadow_ready": ["f1", "f2", "f3", "f4", "f5", "f6"],
        "fixtures_blocked": [],
        "provider_matrix": {},
        "secret_leak_check": "PASS",
        "production_guardrail_check": "PASS",
        "betting_decision_check": "PASS",
        "final_status": "WORLD_CUP_2026_24_JUNE_LIVE_SHADOW_COMPLETE"
    }
    
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        artifacts_dir = run_dir / "shadow_artifacts" / "worldcup2026_switzerland_canada"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        # Write snapshot with production_selectable = True
        snap_data = {
            "fixture_slug": "worldcup2026-switzerland-canada",
            "production_selectable": True, # Should fail
            "manual_authorization_required": True
        }
        (artifacts_dir / "source_bound_shadow_snapshot.json").write_text(json.dumps(snap_data))
        
        res = verify_live_shadow_run(run_summary, run_dir)
        assert res["verdict"] == "FAIL"
        assert any("production_selectable_enabled" in f for f in res["failed_requirements"])


def test_verifier_fails_raw_headers() -> None:
    # TEST-015: verifier fails raw headers.
    run_summary = {
        "run_id": "run_test",
        "fixtures_attempted": ["f1", "f2", "f3", "f4", "f5", "f6"],
        "fixtures_shadow_ready": ["f1", "f2", "f3", "f4", "f5", "f6"],
        "fixtures_blocked": [],
        "provider_matrix": {},
        "secret_leak_check": "PASS",
        "production_guardrail_check": "PASS",
        "betting_decision_check": "PASS",
        "final_status": "WORLD_CUP_2026_24_JUNE_LIVE_SHADOW_COMPLETE"
    }
    
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        cache_dir = run_dir / "cache" / "sportdb"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Write envelope containing raw_headers
        env_data = {
            "fixture_slug": "switzerland",
            "raw_headers": {"Authorization": "bearer xyz"} # should fail
        }
        (cache_dir / "switzerland.json").write_text(json.dumps(env_data))
        
        res = verify_live_shadow_run(run_summary, run_dir)
        assert res["verdict"] == "FAIL"
        assert any("raw_headers" in f for f in res["failed_requirements"]) or any("headers_stored" in f for f in res["failed_requirements"])


def test_verifier_fails_fake_url_term() -> None:
    # TEST-004: cache envelope with source_url api.{prov}.com fails verifier.
    run_summary = {
        "run_id": "run_test",
        "fixtures_attempted": ["f1", "f2", "f3", "f4", "f5", "f6"],
        "fixtures_shadow_ready": ["f1", "f2", "f3", "f4", "f5", "f6"],
        "fixtures_blocked": [],
        "provider_matrix": {},
        "secret_leak_check": "PASS",
        "production_guardrail_check": "PASS",
        "betting_decision_check": "PASS",
        "final_status": "WORLD_CUP_2026_24_JUNE_LIVE_SHADOW_COMPLETE"
    }
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        cache_dir = run_dir / "cache" / "sportdb"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        env_data = {
            "fixture_slug": "switzerland",
            "source_url": "https://api.sportdb.com/v4/matches/switzerland" # fake url, should fail
        }
        (cache_dir / "switzerland.json").write_text(json.dumps(env_data))
        
        res = verify_live_shadow_run(run_summary, run_dir)
        assert res["verdict"] == "FAIL"
        assert any("fake_url" in f for f in res["failed_requirements"])


def test_verifier_fails_fetched_status_with_network_used_false() -> None:
    # TEST-005: status FETCHED with network_used=false fails verifier.
    run_summary = {
        "run_id": "run_test",
        "fixtures_attempted": ["f1", "f2", "f3", "f4", "f5", "f6"],
        "fixtures_shadow_ready": ["f1", "f2", "f3", "f4", "f5", "f6"],
        "fixtures_blocked": [],
        "provider_matrix": {},
        "secret_leak_check": "PASS",
        "production_guardrail_check": "PASS",
        "betting_decision_check": "PASS",
        "final_status": "WORLD_CUP_2026_24_JUNE_LIVE_SHADOW_COMPLETE"
    }
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        cache_dir = run_dir / "cache" / "sportdb"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        env_data = {
            "fixture_slug": "switzerland",
            "status": "FETCHED",
            "network_used": False # FETCHED with network_used False should fail
        }
        (cache_dir / "switzerland.json").write_text(json.dumps(env_data))
        
        res = verify_live_shadow_run(run_summary, run_dir)
        assert res["verdict"] == "FAIL"
        assert any("network_used_false" in f or "network_used" in f for f in res["failed_requirements"])


def test_verifier_fails_provider_matrix_fetched_without_matching_real_envelope() -> None:
    # TEST-006: provider_matrix FETCHED without matching real envelope fails verifier.
    run_summary = {
        "run_id": "run_test",
        "fixtures_attempted": ["f1", "f2", "f3", "f4", "f5", "f6"],
        "fixtures_shadow_ready": ["f1", "f2", "f3", "f4", "f5", "f6"],
        "fixtures_blocked": [],
        "provider_matrix": {
            "sportdb": {"f1": "FETCHED"} # says FETCHED but envelope missing or not matching real
        },
        "secret_leak_check": "PASS",
        "production_guardrail_check": "PASS",
        "betting_decision_check": "PASS",
        "final_status": "WORLD_CUP_2026_24_JUNE_LIVE_SHADOW_COMPLETE"
    }
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        # envelope completely missing
        res = verify_live_shadow_run(run_summary, run_dir)
        assert res["verdict"] == "FAIL"
        assert any("envelope_missing" in f or "fetched" in f for f in res["failed_requirements"])


def test_verifier_allows_blocked_status_when_real_provider_fails() -> None:
    # TEST-008: verifier allows BLOCKED status when real provider access fails.
    run_summary = {
        "run_id": "run_test",
        "fixtures_attempted": ["f1", "f2", "f3", "f4", "f5", "f6"],
        "fixtures_shadow_ready": [],
        "fixtures_blocked": ["f1", "f2", "f3", "f4", "f5", "f6"],
        "provider_matrix": {},
        "secret_leak_check": "PASS",
        "production_guardrail_check": "PASS",
        "betting_decision_check": "PASS",
        "final_status": "BLOCKED_REAL_LIVE_SHADOW_INSUFFICIENT_REAL_PROVIDER_DATA" # allowed blocked status
    }
    with tempfile.TemporaryDirectory() as tmp:
        res = verify_live_shadow_run(run_summary, Path(tmp))
        assert res["verdict"] == "PASS" # should allow BLOCKED status!
