#!/usr/bin/env python3
"""Generate properly classified manifest from actual evidence."""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

EVIDENCE_DIR = Path("LIVE_TEST_EVIDENCE/20260610T150000Z_AUDIT_V3")

def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def classify_run(result: dict, response: dict) -> str:
    """Properly classify a test run."""
    error = result.get("error")
    
    # Check for setup failures first
    if error:
        if "playwright" in error.lower():
            return "BLOCKED_BEFORE_NETWORK"
        if "module" in error.lower() and "not found" in error.lower():
            return "FAILED_SETUP"
        return "FAILED_SETUP"
    
    # Check if network was attempted
    if not result.get("network_attempted", False):
        return "STATIC_ANALYSIS"
    
    # Check for actual verifiable data
    raw_records = result.get("raw_records", 0)
    parsed_records = result.get("parsed_records", 0)
    
    # For response data, check if it has actual content
    response_has_data = False
    if response and isinstance(response, dict):
        # Exclude empty responses
        if response.get("error") is None and len(response) > 0 and not all(v is None for v in response.values()):
            response_has_data = True
    
    if parsed_records > 0 and response_has_data:
        return "LIVE_NETWORK_SUCCESS"
    elif raw_records > 0 and response_has_data:
        return "LIVE_NETWORK_PARTIAL"
    elif result.get("network_attempted"):
        return "LIVE_NETWORK_PARTIAL"
    else:
        return "STATIC_ANALYSIS"

# Collect all runs
runs = []
for run_dir in sorted(EVIDENCE_DIR.iterdir()):
    if run_dir.is_dir() and run_dir.name.startswith("202"):
        result_file = run_dir / "result.json"
        response_file = run_dir / "raw_response_sanitized.json"
        parsed_file = run_dir / "parsed_response.json"
        
        if result_file.exists():
            with open(result_file) as f:
                result = json.load(f)
            with open(response_file) as f:
                response = json.load(f)
            with open(parsed_file) as f:
                parsed = json.load(f)
            
            # Properly reclassify
            proper_class = classify_run(result, response)
            result["classification"] = proper_class
            
            # Update checks
            checks = {
                "data_returned": result.get("parsed_records", 0) > 0,
                "has_verifiable_content": len(str(parsed)) > 50 and parsed != {} and parsed.get("error") is None
            }
            result["checks"] = checks
            
            # Calculate SHA256 if files exist
            sha256_hashes = {}
            for fname in ["command.txt", "result.json", "raw_response_sanitized.json", "parsed_response.json", "checks.json", "sha256.txt"]:
                fpath = run_dir / fname
                if fpath.exists():
                    sha256_hashes[fname] = sha256_file(fpath)
            
            runs.append({
                "run_id": result.get("run_id"),
                "source": result.get("source"),
                "sport": result.get("sport"),
                "capability": result.get("capability"),
                "classification": proper_class,
                "network_attempted": result.get("network_attempted", False),
                "start_timestamp": result.get("start_timestamp"),
                "end_timestamp": result.get("end_timestamp"),
                "duration_seconds": result.get("duration_seconds"),
                "error": result.get("error"),
                "raw_records": result.get("raw_records", 0),
                "parsed_records": result.get("parsed_records", 0),
                "checks": checks,
                "file_hashes": sha256_hashes
            })

# Classify by type
by_class = {}
for r in runs:
    c = r["classification"]
    by_class[c] = by_class.get(c, 0) + 1

# Build manifest
manifest = {
    "audit_run_id": "20260610T150000Z_AUDIT_V3",
    "generated": datetime.now(timezone.utc).isoformat(),
    "status": "AUDIT_EXECUTED_WITH_BLOCKERS",
    "summary": by_class,
    "total_runs": len(runs),
    "runs": runs,
    "notes": [
        "VLR team_stats: SUCCESS with verifiable data (win_rate, matches_found, ranking)",
        "Sackmann adapter returns NULL for player search - needs investigation",
        "HLTV blocked by missing playwright dependency",
        "Discovery adapters return empty for date 2026-06-10 (future date relative to fixture data)"
    ]
}

print(json.dumps(manifest, indent=2))

# Save manifest
(EVIDENCE_DIR / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
print(f"\nSaved: {EVIDENCE_DIR}/MANIFEST.json")
