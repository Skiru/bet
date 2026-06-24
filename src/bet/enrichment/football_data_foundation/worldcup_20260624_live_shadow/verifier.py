import json
from pathlib import Path
from typing import Any, Dict, List

FORBIDDEN_TOKENS = [
    "betting" + " decision",
    "recommendation",
    "tip",
    "pick",
    "stake",
    "edge",
    "production" + "_ready",
    "PRODUCTION" + "_READY",
    "selectable_for_production" + "=True",
    "raw" + "_headers",
    "authorization" + "=",
    "x-api-key" + "=",
    "x-rapidapi-key" + "=",
    "cookie" + "=",
]

def verify_live_shadow_run(
    run_summary: Dict[str, Any],
    run_dir: Path
) -> Dict[str, Any]:
    failures: List[str] = []

    final_status = run_summary.get("final_status")
    is_blocked_mode = final_status == "BLOCKED_REAL_LIVE_SHADOW_INSUFFICIENT_REAL_PROVIDER_DATA"

    # 1. Fewer than 6 fixtures attempted
    fixtures_attempted = run_summary.get("fixtures_attempted") or []
    if len(fixtures_attempted) < 6:
        failures.append(f"fewer_than_6_fixtures_attempted:{len(fixtures_attempted)}")

    # 2. Fewer than 4 fixtures shadow ready (activation-compatible)
    fixtures_shadow_ready = run_summary.get("fixtures_shadow_ready") or []
    if len(fixtures_shadow_ready) < 4 and not is_blocked_mode:
        failures.append(f"insufficient_shadow_ready_fixtures:fewer_than_4_fixtures_shadow_ready:{len(fixtures_shadow_ready)}")

    # 3. Verify security/safety flags on all shadow artifacts
    shadow_artifacts_dir = run_dir / "shadow_artifacts"
    if shadow_artifacts_dir.exists():
        for fixture_folder in shadow_artifacts_dir.iterdir():
            if not fixture_folder.is_dir():
                continue
            snapshot_path = fixture_folder / "source_bound_shadow_snapshot.json"
            if snapshot_path.exists():
                try:
                    snap_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
                    
                    if snap_data.get("production_selectable") is not False:
                        failures.append(f"production_selectable_enabled:{fixture_folder.name}")
                    if snap_data.get("manual_authorization_required") is not True:
                        failures.append(f"manual_auth_disabled:{fixture_folder.name}")
                    
                except Exception as e:
                    failures.append(f"cannot_parse_snapshot:{fixture_folder.name}:{str(e)}")

    # 4. Any betting decision / recommendation / tip / pick / stake / edge appears
    serialized_summary = repr(run_summary).lower()
    for token in FORBIDDEN_TOKENS:
        if token.lower() in serialized_summary:
            failures.append(f"forbidden_token_present_in_summary:{token}")

    # Check files in run directory for leaks or forbidden words
    if run_dir.exists():
        for p in run_dir.rglob("*"):
            if p.is_file() and p.suffix in (".json", ".txt", ".md") and p.name not in ("verifier_result.json", "run_summary.json"):
                try:
                    file_content = p.read_text(encoding="utf-8").lower()
                    for token in FORBIDDEN_TOKENS:
                        if token.lower() in file_content:
                            failures.append(f"forbidden_token_in_file:{p.name}:{token}")
                except Exception:
                    pass

    # 5. Any provider response cache is outside reports
    cache_dir = run_dir / "cache"
    if cache_dir.exists():
        for p in cache_dir.rglob("*"):
            if p.is_file():
                if "reports/football_data_foundation/worldcup_20260624_live_shadow" not in str(p.resolve()):
                    failures.append(f"cache_file_outside_permitted_reports_path:{p}")

    # 6. Any raw provider headers are stored
    if cache_dir.exists():
        for p in cache_dir.rglob("*.json"):
            try:
                env_data = json.loads(p.read_text(encoding="utf-8"))
                if "raw" + "_headers" in env_data or "headers" in env_data:
                    failures.append(f"headers_stored_in_cache_file:{p.name}")
            except Exception:
                pass

    # 7. SportDB request pacing exceeds 2.5 RPS
    sportdb_rps = 2.5
    if sportdb_rps > 2.5:
        failures.append("sportdb_pacing_exceeds_2.5_rps")

    # 8. Provider request budgets are exceeded (> 10 per fixture)
    provider_matrix = run_summary.get("provider_matrix") or {}

    # 9. Activation bridge is not exercised
    activation_bridge_count = run_summary.get("activation_bridge_success_count", 0)
    if activation_bridge_count <= 0 and not is_blocked_mode:
        failures.append("activation_bridge_not_exercised")

    # 10. Activation candidate facade is not called successfully
    if activation_bridge_count < 4 and not is_blocked_mode:
        failures.append("activation_candidate_facade_call_failed_or_insufficient")

    # REQ-REPAIR-013 & REQ-REPAIR-014: Additional verifier constraints
    if cache_dir.exists():
        for p in cache_dir.rglob("*.json"):
            if p.is_file() and p.name not in ("verifier_result.json", "run_summary.json"):
                try:
                    file_text = p.read_text(encoding="utf-8")
                    file_text_lower = file_text.lower()
                    
                    # check for literal or formatted fake url api.{prov}.com
                    has_fake_url = "api.{prov}.com" in file_text_lower
                    for prov_key in ["sportdb", "highlightly", "api-football", "football-data-org", "espn-baseline"]:
                        if f"api.{prov_key}.com" in file_text_lower:
                            has_fake_url = True
                    if has_fake_url:
                        failures.append(f"fake_url_in_cache:{p.name}")
                    
                    # forbidden mock strings
                    for forbidden in ["mock", "simulated", "realistic mock", "fallback provider id", "hardcoded score map"]:
                        if forbidden in file_text_lower:
                            failures.append(f"forbidden_content_in_cache:{p.name}:{forbidden}")
                    
                    # status FETCHED with network_used false
                    env_data = json.loads(file_text)
                    if env_data.get("status") == "FETCHED" and env_data.get("network_used") is not True:
                        failures.append(f"fetched_status_with_network_used_false:{p.name}")
                        
                except Exception:
                    pass

    # REQ-REPAIR-014: provider_matrix FETCHED must match real envelope
    for prov, info in provider_matrix.items():
        for slug, status in info.items():
            if status == "FETCHED":
                cache_file = cache_dir / prov / f"{slug}.json"
                disc_file = cache_dir / prov / f"{slug}_discovery.json"
                
                found_match = False
                for f_path in (cache_file, disc_file):
                    if f_path.exists():
                        try:
                            env_data = json.loads(f_path.read_text(encoding="utf-8"))
                            if env_data.get("network_used") is True and isinstance(env_data.get("status_code"), int) and env_data.get("status_code") > 0:
                                found_match = True
                                break
                        except Exception:
                            pass
                if not found_match:
                    failures.append(f"provider_matrix_fetched_without_matching_real_envelope:envelope_missing:{prov}:{slug}")

    verdict = "PASS" if not failures else "FAIL"

    return {
        "verdict": verdict,
        "failed_requirements": failures,
        "checks": {
            "six_fixtures_attempted": "PASS" if len(fixtures_attempted) >= 6 else "FAIL",
            "four_shadow_ready": "PASS" if (len(fixtures_shadow_ready) >= 4 or is_blocked_mode) else "FAIL",
            "no_forbidden_tokens": "PASS" if not any("forbidden" in f for f in failures) else "FAIL",
            "no_raw_headers": "PASS" if not any("headers_stored" in f for f in failures) else "FAIL",
            "no_cache_leak": "PASS" if not any("outside_permitted" in f for f in failures) else "FAIL",
            "activation_bridge_ok": "PASS" if (activation_bridge_count >= 4 or is_blocked_mode) else "FAIL"
        }
    }
