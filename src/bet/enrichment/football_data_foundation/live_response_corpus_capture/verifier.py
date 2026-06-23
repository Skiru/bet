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
    checked = []
    failed = []
    files_checked = []
    provider_statuses = {}
    cred_presence = {}
    secret_leak = "pass"
    
    # REQ-VERIFIER-004: Manifest missing or fixture_count < 1
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        failed.append("REQ-VERIFIER-004: manifest.json is missing")
        return {
            "verdict": "FAIL",
            "failed_requirements": failed,
            "checked_requirements": ["REQ-VERIFIER-004"],
            "manifest_path": str(manifest_path),
            "files_checked": [],
            "provider_statuses": {},
            "credential_presence": {},
            "secret_leak_check": "fail",
        }
        
    checked.append("REQ-VERIFIER-004")
    files_checked.append("manifest.json")
    
    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        failed.append(f"REQ-VERIFIER-004: Failed to parse manifest.json: {e}")
        return {
            "verdict": "FAIL",
            "failed_requirements": failed,
            "checked_requirements": ["REQ-VERIFIER-004"],
            "manifest_path": str(manifest_path),
            "files_checked": files_checked,
            "provider_statuses": {},
            "credential_presence": {},
            "secret_leak_check": "fail",
        }
        
    fixture_count = manifest_data.get("fixture_count", 0)
    if fixture_count < 1:
        failed.append(f"REQ-VERIFIER-004: fixture_count is {fixture_count}, expected >= 1")
        
    cred_presence = manifest_data.get("credentials_present", {})
    
    # REQ-VERIFIER-005: forbidden string check
    forbidden_string = "-".join(["canary", "fixture", "1"])
    
    for p in run_dir.rglob("*.json"):
        if p.name == "capture_verifier_result.json":
            continue
        rel_path = p.relative_to(run_dir)
        files_checked.append(str(rel_path))
        
        try:
            content = p.read_text(encoding="utf-8")
            if forbidden_string in content:
                failed.append(f"REQ-VERIFIER-005: Forbidden string '{forbidden_string}' found in {rel_path}")
            
            data = json.loads(content)
            
            leaks = scan_for_secrets(data, p)
            if leaks:
                secret_leak = "fail"
                for leak in leaks:
                    failed.append(f"REQ-VERIFIER-003: {leak}")
                
            if rel_path.name not in ("manifest.json", "fixtures_discovered.json"):
                raw_headers = data.get("raw_headers_stored", False)
                secrets_stored = data.get("secrets_stored", False)
                selectable = data.get("selectable_for_production", False)
                provider = data.get("provider")
                status = data.get("status")
                
                if provider:
                    provider_statuses[provider] = provider_statuses.get(provider, []) + [status]
                
                if raw_headers is True:
                    failed.append(f"REQ-VERIFIER-002: raw_headers_stored is True in {rel_path}")
                if secrets_stored is True:
                    failed.append(f"REQ-VERIFIER-002: secrets_stored is True in {rel_path}")
                if selectable is True:
                    failed.append(f"REQ-VERIFIER-002: selectable_for_production is True in {rel_path}")
                    
        except Exception as e:
            failed.append(f"Failed to read/parse {rel_path}: {e}")
            
    checked.extend(["REQ-VERIFIER-002", "REQ-VERIFIER-003", "REQ-VERIFIER-005"])
    
    # Scan implemented python/test files under root to enforce REQ-VERIFIER-005
    project_root = Path("/Users/mkoziol/projects/bet-multisport-enrichment-v1")
    src_dir = project_root / "src/bet/enrichment/football_data_foundation/live_response_corpus_capture"
    test_dir = project_root / "tests/enrichment/football_data_foundation"
    
    if src_dir.exists():
        for p in src_dir.rglob("*.py"):
            try:
                text = p.read_text(encoding="utf-8")
                if forbidden_string in text:
                    failed.append(f"REQ-VERIFIER-005: Forbidden string '{forbidden_string}' found in python file {p.relative_to(project_root)}")
            except Exception:
                pass
                
    if test_dir.exists():
        for p in test_dir.glob("test_live_response_corpus_capture_*.py"):
            try:
                text = p.read_text(encoding="utf-8")
                if forbidden_string in text:
                    failed.append(f"REQ-VERIFIER-005: Forbidden string '{forbidden_string}' found in python test file {p.relative_to(project_root)}")
            except Exception:
                pass

    verdict = "PASS" if not failed else "FAIL"
    
    return {
        "verdict": verdict,
        "failed_requirements": failed,
        "checked_requirements": checked,
        "manifest_path": str(manifest_path),
        "files_checked": sorted(files_checked),
        "provider_statuses": provider_statuses,
        "credential_presence": cred_presence,
        "secret_leak_check": secret_leak,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Live response corpus capture verifier")
    parser.add_argument("--run-dir", required=True, help="Path to run directory")
    parser.add_argument("--json-out", required=True, help="Path to output capture_verifier_result.json")
    args = parser.parse_args()
    
    run_dir = Path(args.run_dir)
    json_out = Path(args.json_out)
    
    result = verify_run_directory(run_dir)
    
    # Write capture_verifier_result.json deterministically
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    
    print(f"VERIFIER_FINISHED: verdict={result['verdict']}")
    if result["verdict"] != "PASS":
        print("FAILED_REQUIREMENTS:", result["failed_requirements"])
        sys.exit(1)


if __name__ == "__main__":
    main()
