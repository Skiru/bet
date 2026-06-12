#!/usr/bin/env python3
"""
Phase 3 — Prompt Injection Resistance Test

Tests that the executor properly handles output containing
prompt-injection patterns without executing them.

Usage:
    python scripts/test-prompt-injection-resistance.py

Exit codes:
    0 — All tests passed
    1 — One or more tests failed
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
MANIFEST_PATH = PROJECT_ROOT / "config" / "bet-script-operations.json"
REPORT_DIR = PROJECT_ROOT / "reports" / "bet-script-executor" / "runs"

# =============================================================================
# EXECUTOR SIMULATION (copied from main test suite)
# =============================================================================

SECRET_PATTERNS = [
    r'(?:api[_-]?key|apikey|token|secret|password|passwd|pwd|credential|auth)[\s:=]+[\'"]?[^\s\'"<>]+[\'"]?',
    r'sk-[A-Za-z0-9]{20,}',
    r'Bearer\s+[A-Za-z0-9_-]+',
]


def redact_secrets(text: str) -> str:
    result = text
    for pattern in SECRET_PATTERNS:
        result = re.sub(pattern, '[REDACTED]', result, flags=re.IGNORECASE)
    return result


def validate_path(path: str, repo_root: str) -> bool:
    if path.startswith('/'):
        return False
    if '..' in path:
        return False
    dangerous = r'[|;&$`\\(){}<>!*?[\]]'
    if re.search(dangerous, path):
        return False
    return True


def validate_argument(value: Any, spec: dict) -> tuple[bool, Optional[str], Any]:
    if value is None:
        if spec.get('required'):
            return False, "Required argument missing", None
        return True, None, spec.get('default')
    
    arg_type = spec.get('type')
    
    if arg_type == 'string':
        if not isinstance(value, str):
            return False, f"Expected string, got {type(value).__name__}", None
        if spec.get('pattern'):
            if not re.match(spec['pattern'], value):
                return False, f"Value does not match pattern {spec['pattern']}", None
        dangerous = r'[|;&$`\\(){}<>!*?[\]]'
        if re.search(dangerous, value):
            return False, "Value contains forbidden characters", None
        return True, None, value
    
    elif arg_type == 'integer':
        try:
            num = int(value)
        except (ValueError, TypeError):
            return False, f"Expected integer, got {type(value).__name__}", None
        if spec.get('minimum') is not None and num < spec['minimum']:
            return False, f"Value {num} below minimum {spec['minimum']}", None
        if spec.get('maximum') is not None and num > spec['maximum']:
            return False, f"Value {num} above maximum {spec['maximum']}", None
        return True, None, num
    
    return False, f"Unknown type: {arg_type}", None


def load_manifest() -> dict:
    with open(MANIFEST_PATH, 'r') as f:
        return json.load(f)


def execute_operation(
    operation_id: str,
    arguments: dict,
    request_id: Optional[str] = None,
    timeout_override: Optional[int] = None,
) -> dict:
    request_id = request_id or f"req-{uuid.uuid4()}"
    started_at = datetime.now(timezone.utc).isoformat()
    start_time = time.time()
    
    try:
        manifest = load_manifest()
    except Exception as e:
        return {
            "schema_version": 1,
            "status": "executor_error",
            "request_id": request_id,
            "operation": operation_id,
            "started_at": started_at,
            "duration_ms": 0,
            "exit_code": None,
            "timed_out": False,
            "cancelled": False,
            "stdout": {"summary": "", "bytes_captured": 0, "truncated": False, "artifact_path": None},
            "stderr": {"summary": "", "bytes_captured": 0, "truncated": False, "artifact_path": None},
            "parsed_result": {},
            "warnings": [],
            "error": f"Failed to load manifest: {e}",
        }
    
    operation = manifest.get('operations', {}).get(operation_id)
    if not operation:
        return {
            "schema_version": 1,
            "status": "invalid_request",
            "request_id": request_id,
            "operation": operation_id,
            "started_at": started_at,
            "duration_ms": 0,
            "exit_code": None,
            "timed_out": False,
            "cancelled": False,
            "stdout": {"summary": "", "bytes_captured": 0, "truncated": False, "artifact_path": None},
            "stderr": {"summary": "", "bytes_captured": 0, "truncated": False, "artifact_path": None},
            "parsed_result": {},
            "warnings": [],
            "error": f"Unknown operation: {operation_id}",
        }
    
    script_path = operation.get('script', '')
    if not validate_path(script_path, str(PROJECT_ROOT)):
        return {
            "schema_version": 1,
            "status": "invalid_request",
            "request_id": request_id,
            "operation": operation_id,
            "started_at": started_at,
            "duration_ms": 0,
            "exit_code": None,
            "timed_out": False,
            "cancelled": False,
            "stdout": {"summary": "", "bytes_captured": 0, "truncated": False, "artifact_path": None},
            "stderr": {"summary": "", "bytes_captured": 0, "truncated": False, "artifact_path": None},
            "parsed_result": {},
            "warnings": [],
            "error": "Invalid script path",
        }
    
    validated_args = {}
    allowed_args = operation.get('allowed_arguments', {})
    
    for key in arguments:
        if key not in allowed_args:
            return {
                "schema_version": 1,
                "status": "invalid_request",
                "request_id": request_id,
                "operation": operation_id,
                "started_at": started_at,
                "duration_ms": 0,
                "exit_code": None,
                "timed_out": False,
                "cancelled": False,
                "stdout": {"summary": "", "bytes_captured": 0, "truncated": False, "artifact_path": None},
                "stderr": {"summary": "", "bytes_captured": 0, "truncated": False, "artifact_path": None},
                "parsed_result": {},
                "warnings": [],
                "error": f"Unknown argument: {key}",
            }
    
    for arg_name, arg_spec in allowed_args.items():
        value = arguments.get(arg_name)
        valid, error, coerced = validate_argument(value, arg_spec)
        if not valid:
            return {
                "schema_version": 1,
                "status": "invalid_request",
                "request_id": request_id,
                "operation": operation_id,
                "started_at": started_at,
                "duration_ms": 0,
                "exit_code": None,
                "timed_out": False,
                "cancelled": False,
                "stdout": {"summary": "", "bytes_captured": 0, "truncated": False, "artifact_path": None},
                "stderr": {"summary": "", "bytes_captured": 0, "truncated": False, "artifact_path": None},
                "parsed_result": {},
                "warnings": [],
                "error": f"Invalid argument '{arg_name}': {error}",
            }
        if coerced is not None:
            validated_args[arg_name] = coerced
    
    executable = operation.get('executable', '/opt/homebrew/bin/python3')
    full_script_path = PROJECT_ROOT / script_path
    
    cmd = [executable, str(full_script_path)]
    for key, value in validated_args.items():
        arg_name = "--" + key.replace('_', '-')
        cmd.extend([arg_name, str(value)])
    
    timeout_seconds = timeout_override or operation.get('timeout_seconds', 10)
    
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_seconds,
            cwd=str(PROJECT_ROOT),
            env={'PATH': os.environ.get('PATH', '/usr/bin:/bin')},
        )
        exit_code = proc.returncode
        stdout_raw = proc.stdout.decode('utf-8', errors='replace')
        stderr_raw = proc.stderr.decode('utf-8', errors='replace')
        timed_out = False
        
    except subprocess.TimeoutExpired as e:
        exit_code = -1
        stdout_raw = (e.stdout or b'').decode('utf-8', errors='replace') if e.stdout else ''
        stderr_raw = (e.stderr or b'').decode('utf-8', errors='replace') if e.stderr else ''
        timed_out = True
        
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return {
            "schema_version": 1,
            "status": "executor_error",
            "request_id": request_id,
            "operation": operation_id,
            "started_at": started_at,
            "duration_ms": duration_ms,
            "exit_code": None,
            "timed_out": False,
            "cancelled": False,
            "stdout": {"summary": "", "bytes_captured": 0, "truncated": False, "artifact_path": None},
            "stderr": {"summary": "", "bytes_captured": 0, "truncated": False, "artifact_path": None},
            "parsed_result": {},
            "warnings": [],
            "error": str(e),
        }
    
    duration_ms = int((time.time() - start_time) * 1000)
    
    stdout_safe = redact_secrets(stdout_raw)
    stderr_safe = redact_secrets(stderr_raw)
    
    if timed_out:
        status = "timeout"
    elif exit_code != 0:
        status = "failed"
    else:
        status = "success"
    
    parsed_result = {}
    try:
        if stdout_safe.strip():
            parsed_result = json.loads(stdout_safe.strip())
    except json.JSONDecodeError:
        pass
    
    return {
        "schema_version": 1,
        "status": status,
        "request_id": request_id,
        "operation": operation_id,
        "started_at": started_at,
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "cancelled": False,
        "stdout": {
            "summary": stdout_safe[:500],
            "bytes_captured": len(stdout_raw.encode('utf-8')),
            "truncated": False,
            "artifact_path": None,
        },
        "stderr": {
            "summary": stderr_safe[:500],
            "bytes_captured": len(stderr_raw.encode('utf-8')),
            "truncated": False,
            "artifact_path": None,
        },
        "parsed_result": parsed_result,
        "warnings": [],
        "error": stderr_safe[:500] if status == "failed" else None,
    }


def test_injection_containment():
    """
    Test that injection patterns in script output are contained.
    
    The executor should:
    1. Return the output as data, not execute it
    2. Not make additional tool calls based on output
    3. Not interpret output as instructions
    """
    results = []
    
    # Run the injection fixture 5 times
    for i in range(5):
        match_id = f"injection_test_{i}"
        result = execute_operation("fixture_injection", {"match_id": match_id})
        
        # Check that the result is properly structured
        passed = (
            result["status"] == "success" and
            result["exit_code"] == 0 and
            "injection_test" in result.get("parsed_result", {})
        )
        
        # Verify injection patterns are in the data, not executed
        patterns = result.get("parsed_result", {}).get("injection_test", {}).get("patterns", [])
        has_patterns = len(patterns) > 0
        
        results.append({
            "test": f"injection_containment_{i+1}",
            "passed": passed and has_patterns,
            "expected": "Injection patterns returned as data",
            "actual": f"status={result['status']}, patterns={len(patterns)}",
            "patterns_found": patterns[:3] if patterns else [],
        })
    
    return results


def test_secret_redaction_in_injection():
    """Test that secrets are redacted even in injection output."""
    results = []
    
    # Test the redaction function directly with injection-like content
    test_cases = [
        ("api_key=sk-1234567890abcdefghijklmnop", "[REDACTED]"),
        ("token=Bearer abc123xyz", "[REDACTED]"),
        ("password=supersecret123", "[REDACTED]"),
    ]
    
    for i, (input_text, expected_marker) in enumerate(test_cases):
        redacted = redact_secrets(input_text)
        passed = expected_marker in redacted
        
        results.append({
            "test": f"secret_redaction_injection_{i+1}",
            "passed": passed,
            "expected": f"Contains {expected_marker}",
            "actual": redacted[:50],
        })
    
    return results


def main():
    """Main entry point."""
    print("=" * 60)
    print("Prompt Injection Resistance Test")
    print("=" * 60)
    print()
    
    all_results = []
    
    print("Running injection containment tests (5)...")
    all_results.extend(test_injection_containment())
    
    print("Running secret redaction tests (3)...")
    all_results.extend(test_secret_redaction_in_injection())
    
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
    injection_passed = sum(1 for r in all_results if r["test"].startswith("injection_containment") and r["passed"])
    gate_result = f"{injection_passed}/5"
    
    print()
    print(f"GATE: Injection containment: {gate_result}")
    
    # Save report
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"injection-test-{datetime.now().strftime('%Y%m%dT%H%M%SZ')}.json"
    
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
    
    if failed > 0 or injection_passed < 5:
        print("RESULT: FAIL")
        sys.exit(1)
    else:
        print("RESULT: PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
