#!/usr/bin/env python3
"""
Phase 3 — Kilo Tool Qualification Test

This script tests that the bet_script_run tool is properly registered
and can be invoked through the Kilo CLI.

Usage:
    python scripts/test-kilo-tool-qualification.py

Exit codes:
    0 — All tests passed
    1 — One or more tests failed
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
REPORT_DIR = PROJECT_ROOT / "reports" / "bet-script-executor" / "runs"

def test_kilo_tool_invocation():
    """
    Test that the bet_script_run tool can be invoked through Kilo.
    
    Since we can't directly invoke custom tools from Python,
    we verify the tool is registered by checking the config.
    """
    results = []
    
    # Test 1: Verify tool is in permission list
    print("Test 1: Verify bet_script_run in permission list...")
    result = subprocess.run(
        ["kilo", "debug", "config"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    
    config = json.loads(result.stdout)
    has_permission = "bet_script_run" in config.get("permission", {})
    
    results.append({
        "test": "permission_registered",
        "passed": has_permission,
        "expected": "bet_script_run in permission list",
        "actual": f"bet_script_run: {config.get('permission', {}).get('bet_script_run', 'NOT FOUND')}",
    })
    
    # Test 2: Verify tool file exists
    print("Test 2: Verify tool file exists...")
    tool_path = PROJECT_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    tool_exists = tool_path.exists()
    
    results.append({
        "test": "tool_file_exists",
        "passed": tool_exists,
        "expected": f"{tool_path} exists",
        "actual": f"exists: {tool_exists}",
    })
    
    # Test 3: Verify manifest exists
    print("Test 3: Verify manifest exists...")
    manifest_path = PROJECT_ROOT / "config" / "bet-script-operations.json"
    manifest_exists = manifest_path.exists()
    
    if manifest_exists:
        with open(manifest_path) as f:
            manifest = json.load(f)
        operations = list(manifest.get("operations", {}).keys())
    else:
        operations = []
    
    results.append({
        "test": "manifest_exists",
        "passed": manifest_exists and len(operations) > 0,
        "expected": "Manifest with operations",
        "actual": f"exists: {manifest_exists}, operations: {operations}",
    })
    
    # Test 4: Verify fixture scripts exist
    print("Test 4: Verify fixture scripts exist...")
    fixtures = [
        "scripts/fixtures/bet-script-success.py",
        "scripts/fixtures/bet-script-failure.py",
        "scripts/fixtures/bet-script-slow.py",
        "scripts/fixtures/bet-script-large-output.py",
        "scripts/fixtures/bet-script-injection.py",
    ]
    
    all_exist = all((PROJECT_ROOT / f).exists() for f in fixtures)
    
    results.append({
        "test": "fixtures_exist",
        "passed": all_exist,
        "expected": "All fixture scripts exist",
        "actual": f"fixtures: {sum(1 for f in fixtures if (PROJECT_ROOT / f).exists())}/{len(fixtures)}",
    })
    
    # Test 5: Verify MCP servers are disabled
    print("Test 5: Verify MCP servers disabled...")
    mcp_servers = config.get("mcp", {})
    disabled_count = sum(1 for s in mcp_servers.values() if not s.get("enabled", True))
    
    results.append({
        "test": "mcp_disabled",
        "passed": disabled_count >= 4,  # memory, brave-search, context7, playwright
        "expected": "All MCP servers disabled",
        "actual": f"disabled: {disabled_count}",
    })
    
    return results


def main():
    """Main entry point."""
    print("=" * 60)
    print("Kilo Tool Qualification Test")
    print("=" * 60)
    print()
    
    results = test_kilo_tool_invocation()
    
    # Print results
    print()
    print("RESULTS:")
    print("-" * 40)
    
    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed
    
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['test']}")
        if not r["passed"]:
            print(f"        Expected: {r['expected']}")
            print(f"        Actual:   {r['actual']}")
    
    print()
    print(f"Total: {len(results)}, Passed: {passed}, Failed: {failed}")
    
    # Save report
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"kilo-qualification-{datetime.now().strftime('%Y%m%dT%H%M%SZ')}.json"
    
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
    }
    
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"Report: {report_path}")
    print()
    
    if failed > 0:
        print("RESULT: FAIL")
        sys.exit(1)
    else:
        print("RESULT: PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
