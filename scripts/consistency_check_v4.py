#!/usr/bin/env python3
"""
Consistency checker for V4 audit evidence.

Verifies that all reports align with manifest.
"""

import json
import re
import sys
from pathlib import Path


def load_manifest(manifest_path: Path) -> dict:
    with open(manifest_path) as f:
        return json.load(f)


def extract_count_from_file(filepath: Path, pattern: str, group: int = 1) -> int:
    """Extract count from markdown file using regex."""
    content = filepath.read_text()
    match = re.search(pattern, content)
    if match:
        return int(match.group(group))
    return -1


def check_consistency():
    base = Path(".")
    
    # Load V4 manifest
    manifest_path = base / "LIVE_TEST_EVIDENCE_V4" / "MANIFEST.json"
    if not manifest_path.exists():
        print("ERROR: MANIFEST.json not found")
        return False
    
    manifest = load_manifest(manifest_path)
    manifest_total = manifest["total_runs"]
    manifest_success = manifest["summary"]["LIVE_NETWORK_SUCCESS"]
    manifest_partial = manifest["summary"]["LIVE_NETWORK_PARTIAL"]
    
    print(f"Manifest: {manifest_total} runs, {manifest_success} SUCCESS, {manifest_partial} PARTIAL")
    
    # Check V4 reports
    errors = []
    
    # SOURCE_CAPABILITY_MATRIX_V4.md
    matrix_path = base / "SOURCE_CAPABILITY_MATRIX_V4.md"
    if matrix_path.exists():
        count = extract_count_from_file(matrix_path, r"\*\*Total Runs in V4 Manifest\*\*: (\d+)")
        if count != manifest_total:
            errors.append(f"SOURCE_CAPABILITY_MATRIX_V4.md: total_runs={count}, expected={manifest_total}")
    else:
        errors.append("SOURCE_CAPABILITY_MATRIX_V4.md not found")
    
    # INTEGRATION_DECISION_MATRIX_V4.md
    decision_path = base / "INTEGRATION_DECISION_MATRIX_V4.md"
    if decision_path.exists():
        count = extract_count_from_file(decision_path, r"\*\*Total Runs\*\*: (\d+)")
        if count != manifest_total:
            errors.append(f"INTEGRATION_DECISION_MATRIX_V4.md: total_runs={count}, expected={manifest_total}")
    else:
        errors.append("INTEGRATION_DECISION_MATRIX_V4.md not found")
    
    # AUDIT_REQUIREMENTS_TRACEABILITY_V4.md
    trace_path = base / "AUDIT_REQUIREMENTS_TRACEABILITY_V4.md"
    if trace_path.exists():
        count = extract_count_from_file(trace_path, r"\*\*Total Runs\*\*: (\d+)")
        if count != manifest_total:
            errors.append(f"TRACEABILITY_V4.md: total_runs={count}, expected={manifest_total}")
    else:
        errors.append("AUDIT_REQUIREMENTS_TRACEABILITY_V4.md not found")
    
    # EVENT_ENRICHMENT_COVERAGE_V4.md
    coverage_path = base / "EVENT_ENRICHMENT_COVERAGE_V4.md"
    if not coverage_path.exists():
        errors.append("EVENT_ENRICHMENT_COVERAGE_V4.md not found")
    
    if errors:
        print("\nCONSISTENCY ERRORS:")
        for e in errors:
            print(f"  - {e}")
        return False
    
    print("\nCONSISTENCY CHECK PASSED")
    return True


if __name__ == "__main__":
    if check_consistency():
        print("\nAll V4 reports consistent with manifest.")
        sys.exit(0)
    else:
        print("\nConsistency check FAILED.")
        sys.exit(1)
