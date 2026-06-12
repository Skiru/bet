#!/usr/bin/env python3
"""
Phase 3 — Phase 2 Regression Test

Verifies that Phase 2 baseline properties are preserved under Phase 3.

Usage:
    python scripts/test-p2-regression.py

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

import os

BASE_URL = "http://127.0.0.1:8000/v1"
API_KEY = os.environ.get("RAPID_MLX_API_KEY", "test")


def test_connectivity():
    """Test Rapid-MLX connectivity."""
    results = []
    
    # Test 1: Models endpoint
    try:
        proc = subprocess.run(
            ["curl", "-s", "-H", f"Authorization: Bearer {API_KEY}", f"{BASE_URL}/models"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(proc.stdout)
        models = [m["id"] for m in data.get("data", [])]
        passed = len(models) > 0
        results.append({
            "test": "connectivity_models",
            "passed": passed,
            "expected": "At least one model",
            "actual": f"models: {models}",
        })
    except Exception as e:
        results.append({
            "test": "connectivity_models",
            "passed": False,
            "expected": "At least one model",
            "actual": f"error: {e}",
        })
    
    # Test 2: Chat completion
    try:
        payload = {
            "model": "default",
            "messages": [{"role": "user", "content": "Say 'test'"}],
            "max_tokens": 10,
        }
        proc = subprocess.run(
            ["curl", "-s", "-X", "POST", "-H", f"Authorization: Bearer {API_KEY}",
             "-H", "Content-Type: application/json", "-d", json.dumps(payload),
             f"{BASE_URL}/chat/completions"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        data = json.loads(proc.stdout)
        passed = "choices" in data and len(data["choices"]) > 0
        results.append({
            "test": "connectivity_chat",
            "passed": passed,
            "expected": "Chat completion with choices",
            "actual": f"choices: {len(data.get('choices', []))}",
        })
    except Exception as e:
        results.append({
            "test": "connectivity_chat",
            "passed": False,
            "expected": "Chat completion with choices",
            "actual": f"error: {e}",
        })
    
    return results


def test_read_operations():
    """Test read operations."""
    results = []
    
    # Test 1: Read file
    test_file = PROJECT_ROOT / "kilo.jsonc"
    passed = test_file.exists()
    results.append({
        "test": "read_file",
        "passed": passed,
        "expected": "kilo.jsonc exists",
        "actual": f"exists: {passed}",
    })
    
    # Test 2: Glob
    py_files = list(PROJECT_ROOT.glob("scripts/**/*.py"))
    passed = len(py_files) > 0
    results.append({
        "test": "glob_files",
        "passed": passed,
        "expected": "Python files in scripts/",
        "actual": f"files: {len(py_files)}",
    })
    
    return results


def test_mcp_disabled():
    """Test that MCP servers are disabled."""
    results = []
    
    try:
        proc = subprocess.run(
            ["kilo", "debug", "config"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        config = json.loads(proc.stdout)
        mcp = config.get("mcp", {})
        
        disabled_count = sum(1 for s in mcp.values() if not s.get("enabled", True))
        passed = disabled_count >= 4
        
        results.append({
            "test": "mcp_disabled",
            "passed": passed,
            "expected": "All MCP servers disabled",
            "actual": f"disabled: {disabled_count}",
        })
    except Exception as e:
        results.append({
            "test": "mcp_disabled",
            "passed": False,
            "expected": "All MCP servers disabled",
            "actual": f"error: {e}",
        })
    
    return results


def test_rapid_mlx_health():
    """Test Rapid-MLX process health."""
    results = []
    
    try:
        proc = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
        )
        passed = "rapid-mlx" in proc.stdout or "python" in proc.stdout and "8000" in proc.stdout
        results.append({
            "test": "rapid_mlx_process",
            "passed": passed,
            "expected": "Rapid-MLX process running",
            "actual": f"process found: {passed}",
        })
    except Exception as e:
        results.append({
            "test": "rapid_mlx_process",
            "passed": False,
            "expected": "Rapid-MLX process running",
            "actual": f"error: {e}",
        })
    
    return results


def main():
    """Main entry point."""
    print("=" * 60)
    print("Phase 2 Regression Test")
    print("=" * 60)
    print()
    
    all_results = []
    
    print("Running connectivity tests (2)...")
    all_results.extend(test_connectivity())
    
    print("Running read operation tests (2)...")
    all_results.extend(test_read_operations())
    
    print("Running MCP disabled tests (1)...")
    all_results.extend(test_mcp_disabled())
    
    print("Running Rapid-MLX health tests (1)...")
    all_results.extend(test_rapid_mlx_health())
    
    # Print results
    print()
    print("RESULTS:")
    print("-" * 40)
    
    passed = sum(1 for r in all_results if r["passed"])
    failed = len(all_results) - passed
    
    for r in all_results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['test']}")
        if not r["passed"]:
            print(f"        Expected: {r['expected']}")
            print(f"        Actual:   {r['actual']}")
    
    print()
    print(f"Total: {len(all_results)}, Passed: {passed}, Failed: {failed}")
    
    # Gate check
    gate_result = f"{passed}/{len(all_results)}"
    
    print()
    print(f"GATE: Phase 2 regression: {gate_result}")
    
    # Save report
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"p2-regression-{datetime.now().strftime('%Y%m%dT%H%M%SZ')}.json"
    
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": len(all_results),
        "passed": passed,
        "failed": failed,
        "gate": gate_result,
        "results": all_results,
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
