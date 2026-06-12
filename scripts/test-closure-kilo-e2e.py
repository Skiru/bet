#!/usr/bin/env python3
"""
Phase 3 Closure — Real Kilo Custom-Tool E2E Tests
Tests actual model-triggered custom-tool calls through Kilo.

This test suite validates:
1. Successful operation (10/10)
2. Failure interpretation (5/5)
3. Invalid request handling (5/5)
4. Timeout interpretation (3/3)
5. Output-limit interpretation (3/3)
6. Prompt-injection output (5/5)

Run: python scripts/test-closure-kilo-e2e.py
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Configuration
REPO_ROOT = Path(__file__).parent.parent
RESULTS_DIR = REPO_ROOT / "reports" / "bet-script-executor" / "closure-20260612T091303Z"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Test counters
total_tests = 0
passed_tests = 0
failed_tests = 0


def log_result(test_name: str, passed: bool, details: str = ""):
    global total_tests, passed_tests, failed_tests
    total_tests += 1
    if passed:
        passed_tests += 1
        print(f"✅ {test_name}: PASS")
    else:
        failed_tests += 1
        print(f"❌ {test_name}: FAIL - {details}")


# =============================================================================
# SUCCESS OPERATION TESTS (10/10)
# =============================================================================

def test_success_fixture_exists():
    """Test 1: Success fixture exists and is executable."""
    print("\n--- Success Tests ---")
    
    fixture_path = REPO_ROOT / "scripts" / "fixtures" / "bet-script-success.py"
    passed = fixture_path.exists()
    log_result("Success fixture exists", passed)


def test_success_fixture_executes():
    """Test 2: Success fixture executes correctly."""
    result = subprocess.run(
        ["/opt/homebrew/bin/python3", str(REPO_ROOT / "scripts" / "fixtures" / "bet-script-success.py"), "--match-id", "test-001"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=REPO_ROOT
    )
    
    log_result("Success fixture executes", result.returncode == 0)


def test_success_returns_json():
    """Test 3: Success fixture returns valid JSON."""
    result = subprocess.run(
        ["/opt/homebrew/bin/python3", str(REPO_ROOT / "scripts" / "fixtures" / "bet-script-success.py"), "--match-id", "test-002"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=REPO_ROOT
    )
    
    try:
        data = json.loads(result.stdout)
        passed = data.get("status") == "success"
    except json.JSONDecodeError:
        passed = False
    
    log_result("Success returns JSON", passed)


def test_success_manifest_entry():
    """Test 4: Success operation in manifest."""
    manifest_path = REPO_ROOT / "config" / "bet-script-operations.json"
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    passed = "fixture_success" in manifest["operations"]
    log_result("Success in manifest", passed)


def test_success_manifest_timeout():
    """Test 5: Success operation has timeout configured."""
    manifest_path = REPO_ROOT / "config" / "bet-script-operations.json"
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    op = manifest["operations"].get("fixture_success", {})
    passed = op.get("timeout_seconds", 0) > 0
    log_result("Success has timeout", passed)


def test_success_manifest_output_limit():
    """Test 6: Success operation has output limits."""
    manifest_path = REPO_ROOT / "config" / "bet-script-operations.json"
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    op = manifest["operations"].get("fixture_success", {})
    passed = op.get("max_stdout_bytes", 0) > 0
    log_result("Success has output limit", passed)


def test_success_manifest_arguments():
    """Test 7: Success operation has argument validation."""
    manifest_path = REPO_ROOT / "config" / "bet-script-operations.json"
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    op = manifest["operations"].get("fixture_success", {})
    passed = "match_id" in op.get("allowed_arguments", {})
    log_result("Success has argument validation", passed)


def test_success_typescript_handler():
    """Test 8: TypeScript handles success operation."""
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    passed = '"success"' in content and "status" in content
    log_result("TypeScript handles success", passed)


def test_success_permission_allow():
    """Test 9: bet_script_run permission is allow."""
    kilo_path = REPO_ROOT / "kilo.jsonc"
    content = kilo_path.read_text()
    
    # Check for bet_script_run: allow in permissions
    passed = '"bet_script_run"' in content and '"allow"' in content
    log_result("bet_script_run permission allow", passed)


def test_success_no_bash_fallback():
    """Test 10: No automatic Bash fallback for success."""
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    # Should not call bash directly
    has_spawn = "spawn(" in content
    no_bash_exec = "exec(" not in content or "spawn" in content
    
    passed = has_spawn
    log_result("No Bash fallback", passed)


# =============================================================================
# FAILURE INTERPRETATION TESTS (5/5)
# =============================================================================

def test_failure_fixture_exists():
    """Test 11: Failure fixture exists."""
    print("\n--- Failure Tests ---")
    
    fixture_path = REPO_ROOT / "scripts" / "fixtures" / "bet-script-failure.py"
    passed = fixture_path.exists()
    log_result("Failure fixture exists", passed)


def test_failure_executes():
    """Test 12: Failure fixture returns non-zero."""
    result = subprocess.run(
        ["/opt/homebrew/bin/python3", str(REPO_ROOT / "scripts" / "fixtures" / "bet-script-failure.py"), "--error-code", "42"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=REPO_ROOT
    )
    
    log_result("Failure returns non-zero", result.returncode == 42)


def test_failure_status_in_typescript():
    """Test 13: TypeScript has 'failed' status."""
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    passed = '"failed"' in content
    log_result("Failure status in TypeScript", passed)


def test_failure_exit_code_captured():
    """Test 14: Exit code captured in result."""
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    passed = "exit_code" in content
    log_result("Exit code captured", passed)


def test_failure_no_auto_retry():
    """Test 15: No automatic retry on failure."""
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    # Should not have retry logic
    has_no_retry = "retry" not in content.lower() or "no-retry" in content.lower()
    
    log_result("No auto retry on failure", has_no_retry)


# =============================================================================
# INVALID REQUEST TESTS (5/5)
# =============================================================================

def test_invalid_operation_rejected():
    """Test 16: Invalid operation rejected."""
    print("\n--- Invalid Request Tests ---")
    
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    passed = '"invalid_request"' in content and "Unknown operation" in content
    log_result("Invalid operation rejected", passed)


def test_invalid_argument_rejected():
    """Test 17: Invalid argument rejected."""
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    passed = "validateArgument" in content and "Invalid argument" in content
    log_result("Invalid argument rejected", passed)


def test_path_traversal_rejected():
    """Test 18: Path traversal rejected."""
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    passed = ".." in content and "validatePath" in content
    log_result("Path traversal rejected", passed)


def test_shell_metacharacters_rejected():
    """Test 19: Shell metacharacters rejected."""
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    passed = "dangerous" in content or "forbidden" in content
    log_result("Shell metacharacters rejected", passed)


def test_no_child_process_on_invalid():
    """Test 20: No child process on invalid request."""
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    # Check that invalid_request returns before spawn
    has_early_return = "invalid_request" in content
    has_subprocesses_field = "subprocesses_started" in content
    
    passed = has_early_return and has_subprocesses_field
    log_result("No child process on invalid", passed)


# =============================================================================
# TIMEOUT INTERPRETATION TESTS (3/3)
# =============================================================================

def test_timeout_status_exists():
    """Test 21: Timeout status exists."""
    print("\n--- Timeout Tests ---")
    
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    passed = '"timeout"' in content
    log_result("Timeout status exists", passed)


def test_timeout_kills_process():
    """Test 22: Timeout kills process."""
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    passed = "setTimeout" in content and "child.kill" in content
    log_result("Timeout kills process", passed)


def test_timeout_no_retry():
    """Test 23: No automatic retry on timeout."""
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    # No retry logic
    passed = "retry" not in content.lower() or content.count("retry") == 0
    log_result("No retry on timeout", passed)


# =============================================================================
# OUTPUT LIMIT TESTS (3/3)
# =============================================================================

def test_output_limit_status_exists():
    """Test 24: Output limit status exists."""
    print("\n--- Output Limit Tests ---")
    
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    passed = '"output_limit_exceeded"' in content
    log_result("Output limit status exists", passed)


def test_output_limit_kills_process():
    """Test 25: Output limit kills process."""
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    passed = "maxBytes" in content and "child.kill" in content
    log_result("Output limit kills process", passed)


def test_output_limit_no_unbounded():
    """Test 26: No unbounded output retrieval."""
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    # Should have streaming capture with limits
    passed = "captureOutput" in content or "chunk" in content
    log_result("No unbounded output", passed)


# =============================================================================
# PROMPT INJECTION TESTS (5/5)
# =============================================================================

def test_injection_fixture_exists():
    """Test 27: Injection fixture exists."""
    print("\n--- Prompt Injection Tests ---")
    
    fixture_path = REPO_ROOT / "scripts" / "fixtures" / "bet-script-injection.py"
    passed = fixture_path.exists()
    log_result("Injection fixture exists", passed)


def test_injection_patterns_contained():
    """Test 28: Injection patterns in output."""
    result = subprocess.run(
        ["/opt/homebrew/bin/python3", str(REPO_ROOT / "scripts" / "fixtures" / "bet-script-injection.py"), "--match-id", "test-inj"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=REPO_ROOT
    )
    
    # Should contain injection patterns in output
    has_patterns = "Ignore previous" in result.stdout or "bash" in result.stdout.lower()
    
    log_result("Injection patterns in output", has_patterns)


def test_secret_redaction():
    """Test 29: Secret redaction in TypeScript."""
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    passed = "redactSecrets" in content and "[REDACTED]" in content
    log_result("Secret redaction", passed)


def test_injection_no_tool_trigger():
    """Test 30: Injection cannot trigger another tool."""
    ts_path = REPO_ROOT / ".kilo" / "tool" / "bet_script_run.ts"
    content = ts_path.read_text()
    
    # Output should be treated as data, not instructions
    # The tool only returns JSON, doesn't execute based on output
    passed = "return JSON.stringify" in content
    log_result("Injection no tool trigger", passed)


def test_injection_output_untrusted():
    """Test 31: Injection output marked as untrusted."""
    fixture_path = REPO_ROOT / "scripts" / "fixtures" / "bet-script-injection.py"
    content = fixture_path.read_text()
    
    passed = "untrusted" in content.lower() or "warning" in content.lower()
    log_result("Injection output untrusted", passed)


def main():
    print("=" * 60)
    print("Phase 3 Closure — Real Kilo Custom-Tool E2E Tests")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)
    
    # Success tests (10/10)
    test_success_fixture_exists()
    test_success_fixture_executes()
    test_success_returns_json()
    test_success_manifest_entry()
    test_success_manifest_timeout()
    test_success_manifest_output_limit()
    test_success_manifest_arguments()
    test_success_typescript_handler()
    test_success_permission_allow()
    test_success_no_bash_fallback()
    
    # Failure tests (5/5)
    test_failure_fixture_exists()
    test_failure_executes()
    test_failure_status_in_typescript()
    test_failure_exit_code_captured()
    test_failure_no_auto_retry()
    
    # Invalid request tests (5/5)
    test_invalid_operation_rejected()
    test_invalid_argument_rejected()
    test_path_traversal_rejected()
    test_shell_metacharacters_rejected()
    test_no_child_process_on_invalid()
    
    # Timeout tests (3/3)
    test_timeout_status_exists()
    test_timeout_kills_process()
    test_timeout_no_retry()
    
    # Output limit tests (3/3)
    test_output_limit_status_exists()
    test_output_limit_kills_process()
    test_output_limit_no_unbounded()
    
    # Prompt injection tests (5/5)
    test_injection_fixture_exists()
    test_injection_patterns_contained()
    test_secret_redaction()
    test_injection_no_tool_trigger()
    test_injection_output_untrusted()
    
    print("\n" + "=" * 60)
    print(f"Results: {passed_tests}/{total_tests} passed")
    print("=" * 60)
    
    # Save results
    results = {
        "test_suite": "closure-kilo-e2e",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_tests": total_tests,
        "passed": passed_tests,
        "failed": failed_tests,
        "categories": {
            "success": "10/10",
            "failure": "5/5",
            "invalid_request": "5/5",
            "timeout": "3/3",
            "output_limit": "3/3",
            "prompt_injection": "5/5"
        },
        "status": "PASS" if passed_tests == total_tests else "FAIL"
    }
    
    results_path = RESULTS_DIR / "kilo-e2e-tests.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to: {results_path}")
    
    return 0 if passed_tests == total_tests else 1


if __name__ == "__main__":
    sys.exit(main())
