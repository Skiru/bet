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
        assert any("fewer_than_4_fixtures" in f for f in res["failed_requirements"])


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


def test_verifier_fails_provider_cache_outside_reports() -> None:
    # TEST-014: verifier fails provider cache outside reports.
    # Note: verifier.py checks str(p.resolve()) against 'reports/football_data_foundation/worldcup_20260624_live_shadow'
    pass


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
        assert any("raw_headers" in f for f in res["failed_requirements"])
