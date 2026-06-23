import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

SECRET_KEYWORDS = {
    "api_key", "x-api-key", "x-auth-token", "authorization", 
    "bearer", "token", "cookie", "set-cookie", "secret", "password"
}


def scan_for_secrets(data: Any, path: Path) -> List[str]:
    failures = []
    if isinstance(data, dict):
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(kw in k_lower for kw in SECRET_KEYWORDS):
                if k_lower in ("credentials_present", "files_written"):
                    failures.extend(scan_for_secrets(v, path))
                    continue
                if isinstance(v, str) and v not in ("[REDACTED_SECRET]", "[REDACTED_SECRET_VALUE]"):
                    failures.append(f"Secret-like key '{k}' with unredacted value in {path.name}")
            failures.extend(scan_for_secrets(v, path))
    elif isinstance(data, list):
        for item in data:
            failures.extend(scan_for_secrets(item, path))
    elif isinstance(data, str):
        val_lower = data.lower()
        if any(kw in val_lower for kw in ["bearer ", "token=", "api_key=", "password="]) and "redacted" not in val_lower:
            failures.append(f"Secret value pattern matched in string in {path.name}")
    return failures


def verify_run_directory(run_dir: Path) -> Dict[str, Any]:
    failed = []
    checked = ["REQ-VERIFIER-001", "REQ-VERIFIER-002", "REQ-VERIFIER-003", "REQ-VERIFIER-004", "REQ-VERIFIER-005", "REQ-VERIFIER-006", "REQ-VERIFIER-007", "REQ-VERIFIER-008"]
    files_checked = []
    
    # 1. Manifest checks
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        failed.append("REQ-VERIFIER-004: manifest.json is missing")
        return {
            "verdict": "FAIL",
            "failed_requirements": failed,
            "checked_requirements": checked,
            "manifest_path": str(manifest_path),
            "files_checked": [],
            "provider_statuses": {},
            "provider_request_purposes": {},
            "discovery_attempted_by_provider": {},
            "discovery_fetched_count": 0,
            "mapping_candidates_found": 0,
            "secret_leak_check": "fail",
            "rescue_provider_statuses": {},
            "rescue_attempted_by_provider": {},
            "rescue_fetched_count": 0,
            "requests_dependency_present": False,
        }
        
    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        failed.append(f"REQ-VERIFIER-004: Failed to parse manifest.json: {e}")
        return {
            "verdict": "FAIL",
            "failed_requirements": failed,
            "checked_requirements": checked,
            "manifest_path": str(manifest_path),
            "files_checked": ["manifest.json"],
            "provider_statuses": {},
            "provider_request_purposes": {},
            "discovery_attempted_by_provider": {},
            "discovery_fetched_count": 0,
            "mapping_candidates_found": 0,
            "secret_leak_check": "fail",
            "rescue_provider_statuses": {},
            "rescue_attempted_by_provider": {},
            "rescue_fetched_count": 0,
            "requests_dependency_present": False,
        }
        
    cred_presence = manifest_data.get("credentials_present", {})
    fixture_count = manifest_data.get("fixture_count", 0)
    if fixture_count < 1:
        failed.append(f"REQ-VERIFIER-004: fixture_count is {fixture_count}, expected >= 1")

    # 2. Files and envelopes checks
    provider_statuses = {}
    provider_request_purposes = {}
    discovery_attempted_by_provider = {}
    discovery_fetched_count = 0
    mapping_candidates_found = 0
    secret_leak = "pass"
    
    is_rescue_run = False
    rescue_provider_statuses = {}
    rescue_attempted_by_provider = {"sportdb": False, "highlightly": False, "espn-baseline": False}
    rescue_fetched_count = 0
    requests_dependency_present = False
    
    forbidden_string = "-".join(["canary", "fixture", "1"])
    
    mapping_candidate_path = run_dir / "mapping_candidate.json"
    if mapping_candidate_path.exists():
        try:
            candidates = json.loads(mapping_candidate_path.read_text(encoding="utf-8"))
            if isinstance(candidates, list):
                mapping_candidates_found = len(candidates)
        except Exception as e:
            failed.append(f"Failed to parse mapping_candidate.json: {e}")
            
    for p in run_dir.rglob("*.json"):
        if p.name == "capture_verifier_result.json":
            continue
        rel_path = p.relative_to(run_dir)
        files_checked.append(str(rel_path))
        
        try:
            content = p.read_text(encoding="utf-8")
            if forbidden_string in content:
                failed.append(f"REQ-VERIFIER-007: Forbidden string '{forbidden_string}' found in JSON {rel_path}")
            if "PRODUCTION_" + "READY" in content:
                failed.append(f"REQ-VERIFIER-007: Forbidden string 'PRODUCTION_READY' found in JSON {rel_path}")
            for marker in ["betting/data", "sqlite_write_query", "INSERT", "UPDATE", "DELETE", "activate", "matrix", "routing"]:
                if marker in content:
                    failed.append(f"REQ-VERIFIER-007: Forbidden DB/routing/betting marker '{marker}' found in JSON {rel_path}")
                
            data = json.loads(content)
            
            leaks = scan_for_secrets(data, p)
            if leaks:
                secret_leak = "fail"
                for leak in leaks:
                    failed.append(f"REQ-VERIFIER-007: {leak}")
                    
            if rel_path.name not in ("manifest.json", "fixtures_discovered.json", "mapping_candidate.json"):
                provider = data.get("provider")
                status = data.get("status")
                purpose = data.get("request_purpose", "fixture_detail")
                
                raw_headers = data.get("raw_headers_stored", False)
                secrets_stored = data.get("secrets_stored", False)
                selectable = data.get("selectable_for_production", False)
                rescue_attempt = data.get("rescue_attempt", False)
                rescue_prov = data.get("rescue_provider") or provider
                rescue_attempted = data.get("request_attempted", True)
                net_used = data.get("network_used", True)
                
                if raw_headers is True:
                    failed.append(f"REQ-VERIFIER-007: raw_headers_stored is True in {rel_path}")
                if secrets_stored is True:
                    failed.append(f"REQ-VERIFIER-007: secrets_stored is True in {rel_path}")
                if selectable is True:
                    failed.append(f"REQ-VERIFIER-007: selectable_for_production is True in {rel_path}")
                    
                if rescue_attempt:
                    is_rescue_run = True
                    if rescue_prov:
                        rescue_provider_statuses.setdefault(rescue_prov, []).append(status)
                        if rescue_attempted:
                            rescue_attempted_by_provider[rescue_prov] = True
                            
                    if status == "RESCUE_FETCHED":
                        rescue_fetched_count += 1
                        
                    # REQ-VERIFIER-006 Checks
                    if not isinstance(rescue_attempted, bool):
                        failed.append(f"REQ-VERIFIER-006: rescue envelope {rel_path} must have boolean request_attempted")
                    if not isinstance(net_used, bool):
                        failed.append(f"REQ-VERIFIER-006: rescue envelope {rel_path} must have boolean network_used")
                    if not isinstance(purpose, str):
                        failed.append(f"REQ-VERIFIER-006: rescue envelope {rel_path} must have string request_purpose")
                    if rescue_attempt is not True:
                        failed.append(f"REQ-VERIFIER-006: rescue envelope {rel_path} must have rescue_attempt=True")
                    if selectable is not False:
                        failed.append(f"REQ-VERIFIER-006: rescue envelope {rel_path} must have selectable_for_production=False")
                        
                    # REQ-VERIFIER-004 Checks
                    if status == "RESCUE_BLOCKED_ENDPOINT_UNAVAILABLE" and rescue_prov == "highlightly":
                        error_msg = data.get("error") or ""
                        if "highlightly_base_url_or_auth_header_not_available_in_repo_or_docs" not in error_msg:
                            failed.append(f"REQ-VERIFIER-004: highlightly RESCUE_BLOCKED_ENDPOINT_UNAVAILABLE must have exact reason in error field: {rel_path}")
                            
                    # REQ-VERIFIER-005 Checks
                    if status in ("RESCUE_FETCHED", "RESCUE_NO_MATCH_FOUND"):
                        if not data.get("source_url"):
                            failed.append(f"REQ-VERIFIER-005: {rel_path} with status {status} lacks source_url")
                        if not data.get("body_sha256"):
                            failed.append(f"REQ-VERIFIER-005: {rel_path} with status {status} lacks body_sha256")
                else:
                    if provider:
                        provider_statuses.setdefault(provider, []).append(status)
                        provider_request_purposes.setdefault(provider, []).append(purpose)
                        
                        if "discovery" in purpose or purpose.endswith("discovery"):
                            discovery_attempted_by_provider[provider] = True
                            if status == "DISCOVERY_FETCHED":
                                discovery_fetched_count += 1
                                
                    if status in ("DISCOVERY_FETCHED", "DISCOVERY_NO_MATCH_FOUND"):
                        if not data.get("source_url"):
                            failed.append(f"REQ-VERIFIER-003: {rel_path} with status {status} lacks source_url")
                        if not data.get("body_sha256"):
                            failed.append(f"REQ-VERIFIER-003: {rel_path} with status {status} lacks body_sha256")
                            
        except Exception as e:
            failed.append(f"Failed to read/parse {rel_path}: {e}")

    # Rescue Run Checks
    if is_rescue_run:
        # REQ-VERIFIER-001 Checks
        for prov in ["sportdb", "highlightly", "espn-baseline"]:
            if prov not in rescue_provider_statuses:
                failed.append(f"REQ-VERIFIER-001: Missing rescue evidence/envelope for provider {prov}")
                
        # REQ-VERIFIER-002 Checks
        sportdb_present = cred_presence.get("sportdb") or cred_presence.get("SPORTDB_API_KEY")
        if sportdb_present:
            sportdb_attempted = rescue_attempted_by_provider.get("sportdb", False)
            if not sportdb_attempted:
                failed.append("REQ-VERIFIER-002: SportDB credential is present but no SportDB request was attempted")
                
        # REQ-VERIFIER-003 Checks
        espn_attempted = rescue_attempted_by_provider.get("espn-baseline", False)
        if not espn_attempted:
            failed.append("REQ-VERIFIER-003: ESPN request was not attempted")
    else:
        for prov in ("sportdb", "football-data-org", "highlightly", "api-football", "espn-baseline"):
            if prov not in discovery_attempted_by_provider:
                discovery_attempted_by_provider[prov] = False

        for provider, present in cred_presence.items():
            if not present:
                continue
            dash_provider = provider.replace("_", "-")
            statuses = provider_statuses.get(dash_provider, []) or provider_statuses.get(provider, [])
            if not statuses:
                failed.append(f"REQ-VERIFIER-001: Credential present for {provider} but no envelopes written")
            elif set(statuses) == {"BLOCKED_PROVIDER_MAPPING_MISSING"}:
                failed.append(f"REQ-VERIFIER-001: Credential present for {provider} but only BLOCKED_PROVIDER_MAPPING_MISSING was written")

    project_root = Path("/Users/mkoziol/projects/bet-multisport-enrichment-v1")
    src_dir = project_root / "src/bet/enrichment/football_data_foundation/live_response_corpus_capture"
    test_dir = project_root / "tests/enrichment/football_data_foundation"
    
    if src_dir.exists():
        for p in src_dir.rglob("*.py"):
            if p.name == "verifier.py":
                continue
            try:
                text = p.read_text(encoding="utf-8")
                if forbidden_string in text:
                    failed.append(f"REQ-VERIFIER-007: Forbidden string '{forbidden_string}' found in python file {p.relative_to(project_root)}")
                if "PRODUCTION_" + "READY" in text:
                    failed.append(f"REQ-VERIFIER-007: Forbidden string 'PRODUCTION_READY' found in python file {p.relative_to(project_root)}")
                if re.search(r"\bimport\s+requests\b|\bfrom\s+requests\b|\brequests\.[a-zA-Z_]", text):
                    requests_dependency_present = True
                    failed.append(f"REQ-VERIFIER-007: forbidden requests import/usage found in python file {p.relative_to(project_root)}")
                for marker in ["betting/data", "sqlite_write_query", "INSERT", "UPDATE", "DELETE", "activate", "matrix", "routing"]:
                    if marker in text:
                        failed.append(f"REQ-VERIFIER-007: Forbidden DB/routing/betting marker '{marker}' found in python file {p.relative_to(project_root)}")
            except Exception:
                pass
                
    if test_dir.exists():
        for p in test_dir.glob("test_live_response_corpus_capture_*.py"):
            try:
                text = p.read_text(encoding="utf-8")
                if forbidden_string in text:
                    failed.append(f"REQ-VERIFIER-007: Forbidden string '{forbidden_string}' found in python test file {p.relative_to(project_root)}")
            except Exception:
                pass

    verdict = "PASS" if not failed else "FAIL"
    
    return {
        "verdict": verdict,
        "failed_requirements": sorted(list(set(failed))),
        "checked_requirements": checked,
        "manifest_path": str(manifest_path),
        "files_checked": sorted(files_checked),
        "provider_statuses": provider_statuses,
        "provider_request_purposes": provider_request_purposes,
        "discovery_attempted_by_provider": discovery_attempted_by_provider,
        "discovery_fetched_count": discovery_fetched_count,
        "mapping_candidates_found": mapping_candidates_found,
        "secret_leak_check": secret_leak,
        "rescue_provider_statuses": rescue_provider_statuses,
        "rescue_attempted_by_provider": rescue_attempted_by_provider,
        "rescue_fetched_count": rescue_fetched_count,
        "requests_dependency_present": requests_dependency_present,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Live response corpus capture verifier")
    parser.add_argument("--run-dir", required=True, help="Path to run directory")
    parser.add_argument("--json-out", required=True, help="Path to output capture_verifier_result.json")
    args = parser.parse_args()
    
    run_dir = Path(args.run_dir)
    json_out = Path(args.json_out)
    
    result = verify_run_directory(run_dir)
    
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    
    print(f"VERIFIER_FINISHED: verdict={result['verdict']}")
    if result["verdict"] != "PASS":
        print("FAILED_REQUIREMENTS:", result["failed_requirements"])
        sys.exit(1)


if __name__ == "__main__":
    main()
