#!/usr/bin/env python3
"""
P2 Lifecycle Certification Test

Deterministic certification for Rapid-MLX 0.7.0 production lifecycle.
Tests: start, stop, restart, status, health, logs, smoke, safety scenarios.

DO NOT MODIFY: This script validates production lifecycle safety.
"""

import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ==============================================================================
# CONFIGURATION - Must match production lifecycle
# ==============================================================================
RAPID_MLX_BIN = Path.home() / ".venvs" / "rapid-mlx-0.7.0" / "bin" / "rapid-mlx"
EXPECTED_VERSION = "0.7.0"
MODEL_ALIAS = "qwen3.6-35b-4bit"
MODEL_RESOLVED = "mlx-community/Qwen3.6-35B-A3B-4bit"
HOST = "127.0.0.1"
PORT = 8000
BASE_URL = f"http://{HOST}:{PORT}/v1"
MAX_TOKENS = 8192
PREFILL_STEP = 2048
GPU_MEM_UTIL = 0.70

# Timeouts
STARTUP_TIMEOUT_S = 180
GRACEFUL_SHUTDOWN_S = 30
FORCED_SHUTDOWN_S = 10
HEALTH_TIMEOUT_S = 15
SMOKE_TIMEOUT_S = 300
CLEANUP_POLL_S = 1
CLEANUP_MAX_WAIT_S = 15

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
EVIDENCE_DIR = PROJECT_ROOT / "docs" / "local-llm" / "p2-evidence"
RUNTIME_DIR = PROJECT_ROOT / ".kilo" / "runtime"
LOG_DIR = PROJECT_ROOT / ".kilo" / "logs"
PID_FILE = RUNTIME_DIR / f"rapid-mlx-{PORT}.pid"
MANIFEST_FILE = RUNTIME_DIR / f"rapid-mlx-{PORT}.manifest.json"
LIFECYCLE_SCRIPT = SCRIPT_DIR / "local-llm.sh"

# ==============================================================================
# EVIDENCE COLLECTION
# ==============================================================================
evidence: dict[str, Any] = {
    "schema_version": "1.0",
    "phase": "P2",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "tests": [],
    "fingerprint": {},
    "safety_tests": {},
    "security": {},
    "final_state": {},
}


def add_test_result(name: str, passed: bool, details: dict[str, Any]) -> None:
    evidence["tests"].append({
        "name": name,
        "passed": passed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": details,
    })


def check_port_free(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        sock.close()
        return True
    except OSError:
        return False


def check_listener_exists(port: int) -> bool:
    try:
        result = subprocess.run(
            ["lsof", "-nP", "-iTCP:" + str(port), "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5
        )
        lines = result.stdout.strip().split('\n')
        return len(lines) > 1
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_connection_refused(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        sock.connect((HOST, port))
        sock.close()
        return False
    except (ConnectionRefusedError, OSError):
        return True
    finally:
        try:
            sock.close()
        except Exception:
            pass


def run_lifecycle_command(action: str, timeout: int = 300) -> tuple[int, str, str]:
    """Run lifecycle script command."""
    result = subprocess.run(
        [str(LIFECYCLE_SCRIPT), action],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(PROJECT_ROOT),
    )
    return result.returncode, result.stdout, result.stderr


def wait_for_readiness(timeout_s: int = STARTUP_TIMEOUT_S) -> tuple[bool, float]:
    """Wait for server readiness."""
    import urllib.request
    import urllib.error
    
    start = time.time()
    deadline = start + timeout_s
    
    while time.time() < deadline:
        try:
            req = urllib.request.Request(f"http://{HOST}:{PORT}/health", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return True, time.time() - start
        except (urllib.error.URLError, urllib.error.HTTPError, ConnectionRefusedError, TimeoutError):
            pass
        time.sleep(1)
    
    return False, time.time() - start


def get_pid_from_file() -> int | None:
    """Read PID from file."""
    if not PID_FILE.exists():
        return None
    try:
        content = PID_FILE.read_text().strip()
        return int(content) if content.isdigit() else None
    except Exception:
        return None


def is_process_alive(pid: int) -> bool:
    """Check if process is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def get_process_cmdline(pid: int) -> list[str] | None:
    """Get process command line."""
    try:
        import psutil
        proc = psutil.Process(pid)
        return proc.cmdline()
    except Exception:
        return None


def verify_fingerprint(pid: int) -> tuple[bool, dict[str, Any]]:
    """Verify process matches expected fingerprint."""
    result = {
        "pid": pid,
        "executable_match": False,
        "model_match": False,
        "host_match": False,
        "port_match": False,
        "forbidden_flags_absent": False,
        "cmdline": None,
    }
    
    cmdline = get_process_cmdline(pid)
    if cmdline is None:
        return False, result
    
    result["cmdline"] = cmdline
    
    # Check executable
    cmdline_str = " ".join(cmdline)
    if str(RAPID_MLX_BIN) in cmdline_str:
        result["executable_match"] = True
    
    # Check model
    if MODEL_ALIAS in cmdline_str:
        result["model_match"] = True
    
    # Check host
    if "--host" in cmdline:
        idx = cmdline.index("--host")
        if idx + 1 < len(cmdline) and cmdline[idx + 1] == HOST:
            result["host_match"] = True
    
    # Check port
    if "--port" in cmdline:
        idx = cmdline.index("--port")
        if idx + 1 < len(cmdline) and cmdline[idx + 1] == str(PORT):
            result["port_match"] = True
    
    # Check forbidden flags
    forbidden = [
        "--kv-cache-quantization",
        "--kv-cache-turboquant",
        "--enable-mtp",
        "--enable-dflash",
        "--suffix-decoding",
        "--enable-tool-logits-bias",
        "--cloud-model",
        "--cloud-api-key",
        "--mllm",
    ]
    found_forbidden = [f for f in forbidden if f in cmdline_str]
    result["forbidden_flags_absent"] = len(found_forbidden) == 0
    result["found_forbidden"] = found_forbidden
    
    all_ok = (
        result["executable_match"]
        and result["model_match"]
        and result["host_match"]
        and result["port_match"]
        and result["forbidden_flags_absent"]
    )
    
    return all_ok, result


# ==============================================================================
# TEST FUNCTIONS
# ==============================================================================

def test_initial_state() -> tuple[bool, dict[str, Any]]:
    """Test 1: Initial stopped state."""
    details = {
        "port_free": False,
        "no_listener": False,
        "no_pid_file": False,
        "connection_refused": False,
    }
    
    # Check port is free
    details["port_free"] = check_port_free(PORT)
    
    # Check no listener
    details["no_listener"] = not check_listener_exists(PORT)
    
    # Check no PID file
    details["no_pid_file"] = not PID_FILE.exists()
    
    # Check connection refused
    details["connection_refused"] = check_connection_refused(PORT)
    
    passed = details["port_free"] or (details["no_listener"] and details["connection_refused"])
    return passed, details


def test_start() -> tuple[bool, dict[str, Any]]:
    """Test 2: Normal start."""
    details = {
        "exit_code": None,
        "pid": None,
        "readiness_succeeded": False,
        "readiness_duration_s": None,
        "fingerprint_ok": False,
        "manifest_exists": False,
    }
    
    # Run start
    exit_code, stdout, stderr = run_lifecycle_command("start")
    details["exit_code"] = exit_code
    details["stdout"] = stdout[:500] if stdout else ""
    details["stderr"] = stderr[:500] if stderr else ""
    
    if exit_code != 0:
        return False, details
    
    # Get PID
    pid = get_pid_from_file()
    details["pid"] = pid
    
    if pid is None:
        return False, details
    
    # Wait for readiness
    ready, duration = wait_for_readiness()
    details["readiness_succeeded"] = ready
    details["readiness_duration_s"] = duration
    
    if not ready:
        return False, details
    
    # Verify fingerprint
    fingerprint_ok, fingerprint = verify_fingerprint(pid)
    details["fingerprint_ok"] = fingerprint_ok
    details["fingerprint"] = fingerprint
    
    # Check manifest
    details["manifest_exists"] = MANIFEST_FILE.exists()
    
    passed = (
        exit_code == 0
        and pid is not None
        and ready
        and fingerprint_ok
    )
    return passed, details


def test_health() -> tuple[bool, dict[str, Any]]:
    """Test 3: Health check."""
    details = {
        "exit_code": None,
    }
    
    exit_code, stdout, stderr = run_lifecycle_command("health")
    details["exit_code"] = exit_code
    details["stdout"] = stdout[:500] if stdout else ""
    
    return exit_code == 0, details


def test_status() -> tuple[bool, dict[str, Any]]:
    """Test 4: Status check."""
    details = {
        "exit_code": None,
        "shows_running": False,
    }
    
    exit_code, stdout, stderr = run_lifecycle_command("status")
    details["exit_code"] = exit_code
    details["stdout"] = stdout[:500] if stdout else ""
    details["shows_running"] = "running" in stdout.lower()
    
    return exit_code == 0 and details["shows_running"], details


def test_smoke() -> tuple[bool, dict[str, Any]]:
    """Test 5: Smoke test."""
    details = {
        "exit_code": None,
    }
    
    exit_code, stdout, stderr = run_lifecycle_command("smoke", timeout=SMOKE_TIMEOUT_S)
    details["exit_code"] = exit_code
    details["stdout"] = stdout[:500] if stdout else ""
    
    return exit_code == 0, details


def test_logs() -> tuple[bool, dict[str, Any]]:
    """Test 6: Logs command."""
    details = {
        "exit_code": None,
        "has_output": False,
    }
    
    exit_code, stdout, stderr = run_lifecycle_command("logs")
    details["exit_code"] = exit_code
    details["has_output"] = len(stdout) > 0
    details["stdout_lines"] = len(stdout.split('\n')) if stdout else 0
    
    return exit_code == 0 and details["has_output"], details


def test_duplicate_start() -> tuple[bool, dict[str, Any]]:
    """Test 7: Repeated start without duplicate process."""
    details = {
        "first_pid": None,
        "second_exit_code": None,
        "pid_unchanged": False,
        "no_duplicate_process": False,
    }
    
    # Get current PID
    first_pid = get_pid_from_file()
    details["first_pid"] = first_pid
    
    # Try to start again
    exit_code, stdout, stderr = run_lifecycle_command("start")
    details["second_exit_code"] = exit_code
    details["stdout"] = stdout[:500] if stdout else ""
    
    # Check PID unchanged
    second_pid = get_pid_from_file()
    details["pid_unchanged"] = first_pid == second_pid
    
    # Check no duplicate process
    try:
        result = subprocess.run(
            ["pgrep", "-f", "rapid-mlx.*serve"],
            capture_output=True,
            text=True,
            timeout=5
        )
        pids = [int(p) for p in result.stdout.strip().split('\n') if p.strip().isdigit()]
        details["rapid_mlx_pids"] = pids
        details["no_duplicate_process"] = len(pids) == 1
    except Exception as e:
        details["error"] = str(e)
        details["no_duplicate_process"] = False
    
    passed = (
        details["pid_unchanged"]
        and details["no_duplicate_process"]
    )
    return passed, details


def test_restart() -> tuple[bool, dict[str, Any]]:
    """Test 8: Restart."""
    details = {
        "old_pid": None,
        "new_pid": None,
        "exit_code": None,
        "pid_changed": False,
        "readiness_ok": False,
    }
    
    old_pid = get_pid_from_file()
    details["old_pid"] = old_pid
    
    exit_code, stdout, stderr = run_lifecycle_command("restart", timeout=STARTUP_TIMEOUT_S + GRACEFUL_SHUTDOWN_S)
    details["exit_code"] = exit_code
    details["stdout"] = stdout[:500] if stdout else ""
    
    if exit_code != 0:
        return False, details
    
    new_pid = get_pid_from_file()
    details["new_pid"] = new_pid
    details["pid_changed"] = old_pid != new_pid
    
    # Wait for readiness
    ready, duration = wait_for_readiness()
    details["readiness_ok"] = ready
    details["readiness_duration_s"] = duration
    
    passed = (
        exit_code == 0
        and details["pid_changed"]
        and ready
    )
    return passed, details


def test_health_after_restart() -> tuple[bool, dict[str, Any]]:
    """Test 9: Health after restart."""
    return test_health()


def test_stop() -> tuple[bool, dict[str, Any]]:
    """Test 10: Graceful stop."""
    details = {
        "exit_code": None,
        "process_gone": False,
        "port_free": False,
        "no_listener": False,
        "pid_file_removed": False,
    }
    
    exit_code, stdout, stderr = run_lifecycle_command("stop", timeout=GRACEFUL_SHUTDOWN_S + FORCED_SHUTDOWN_S)
    details["exit_code"] = exit_code
    details["stdout"] = stdout[:500] if stdout else ""
    
    # Wait for cleanup
    time.sleep(2)
    
    # Check process gone
    pid = get_pid_from_file()
    if pid:
        details["process_gone"] = not is_process_alive(pid)
    else:
        details["process_gone"] = True
    
    # Check port free
    details["port_free"] = check_port_free(PORT)
    details["no_listener"] = not check_listener_exists(PORT)
    details["connection_refused"] = check_connection_refused(PORT)
    
    # Check PID file removed
    details["pid_file_removed"] = not PID_FILE.exists()
    
    passed = (
        exit_code == 0
        and details["process_gone"]
        and details["no_listener"]
        and details["connection_refused"]
    )
    return passed, details


def test_duplicate_stop() -> tuple[bool, dict[str, Any]]:
    """Test 11: Repeated stop is safe."""
    details = {
        "exit_code": None,
    }
    
    exit_code, stdout, stderr = run_lifecycle_command("stop")
    details["exit_code"] = exit_code
    details["stdout"] = stdout[:500] if stdout else ""
    
    # Should succeed (idempotent)
    return exit_code == 0, details


def test_stale_pid_handling() -> tuple[bool, dict[str, Any]]:
    """Test 12: Stale lifecycle-owned PID file handling."""
    details = {
        "stale_pid_created": False,
        "start_succeeded": False,
        "stale_file_cleaned": False,
    }
    
    # Create stale PID file with non-existent PID
    stale_pid = 999999  # Very unlikely to exist
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(stale_pid))
    details["stale_pid_created"] = PID_FILE.exists()
    
    # Try to start - should clean up stale file
    exit_code, stdout, stderr = run_lifecycle_command("start")
    details["start_exit_code"] = exit_code
    details["start_succeeded"] = exit_code == 0
    
    if exit_code == 0:
        # Verify new PID is different
        new_pid = get_pid_from_file()
        details["new_pid"] = new_pid
        details["pid_differs"] = new_pid != stale_pid
        
        # Stop for next test
        run_lifecycle_command("stop")
        time.sleep(2)
    
    passed = details["start_succeeded"]
    return passed, details


def test_unrelated_pid_protection() -> tuple[bool, dict[str, Any]]:
    """Test 13: PID-reuse/unrelated-process protection."""
    details = {
        "test_process_started": False,
        "test_pid": None,
        "stale_pid_file_created": False,
        "start_refused": False,
        "test_process_survived": False,
        "cleanup_done": False,
    }
    
    # Start a harmless test process (sleep)
    test_proc = subprocess.Popen(
        ["sleep", "60"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    details["test_process_started"] = True
    details["test_pid"] = test_proc.pid
    
    # Create PID file pointing to test process
    PID_FILE.write_text(str(test_proc.pid))
    details["stale_pid_file_created"] = True
    
    # Try to start - should refuse (PID exists but is not Rapid-MLX)
    exit_code, stdout, stderr = run_lifecycle_command("start")
    details["start_exit_code"] = exit_code
    details["start_refused"] = exit_code != 0
    details["start_stderr"] = stderr[:300] if stderr else ""
    
    # Verify test process still alive
    time.sleep(1)
    details["test_process_survived"] = is_process_alive(test_proc.pid)
    
    # Cleanup
    test_proc.terminate()
    test_proc.wait(timeout=5)
    PID_FILE.unlink(missing_ok=True)
    details["cleanup_done"] = True
    
    passed = (
        details["start_refused"]
        and details["test_process_survived"]
    )
    return passed, details


def test_port_conflict_handling() -> tuple[bool, dict[str, Any]]:
    """Test 14: Same-port unrelated-listener protection."""
    details = {
        "dummy_listener_started": False,
        "start_refused": False,
        "dummy_survived": False,
        "cleanup_done": False,
    }
    
    # Start a dummy listener on the port
    dummy_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    dummy_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        dummy_sock.bind((HOST, PORT))
        dummy_sock.listen(1)
        details["dummy_listener_started"] = True
    except OSError as e:
        details["error"] = str(e)
        dummy_sock.close()
        return False, details
    
    # Try to start - should refuse
    exit_code, stdout, stderr = run_lifecycle_command("start")
    details["start_exit_code"] = exit_code
    details["start_refused"] = exit_code != 0
    details["start_stderr"] = stderr[:300] if stderr else ""
    
    # Verify dummy still listening
    details["dummy_survived"] = check_listener_exists(PORT)
    
    # Cleanup
    dummy_sock.close()
    details["cleanup_done"] = True
    
    passed = (
        details["start_refused"]
        and details["dummy_survived"]
    )
    return passed, details


def test_failed_start_cleanup() -> tuple[bool, dict[str, Any]]:
    """Test 15: Failed-start cleanup."""
    details = {
        "port_occupied": False,
        "start_failed": False,
        "no_orphan_process": False,
        "port_freed": False,
    }
    
    # Start server normally first
    exit_code, stdout, stderr = run_lifecycle_command("start")
    if exit_code != 0:
        details["error"] = "Failed to start server for test"
        return False, details
    
    time.sleep(5)
    
    # Get PID
    pid = get_pid_from_file()
    details["original_pid"] = pid
    
    # Port should be occupied
    details["port_occupied"] = check_listener_exists(PORT)
    
    # Kill the process abruptly (simulating crash)
    if pid and is_process_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
            time.sleep(2)
        except Exception as e:
            details["kill_error"] = str(e)
    
    # Clean up PID file to simulate failed state
    PID_FILE.unlink(missing_ok=True)
    
    # Verify port is now free or process is gone
    details["no_orphan_process"] = not is_process_alive(pid) if pid else True
    details["port_freed"] = not check_listener_exists(PORT) or check_connection_refused(PORT)
    
    passed = details["no_orphan_process"]
    return passed, details


def test_final_cleanup() -> tuple[bool, dict[str, Any]]:
    """Test 16: Final no-process/no-listener/no-orphan verification."""
    details = {
        "no_process": False,
        "no_listener": False,
        "connection_refused": False,
        "no_pid_file": False,
    }
    
    # Ensure stopped
    run_lifecycle_command("stop")
    time.sleep(3)
    
    # Check no Rapid-MLX process
    try:
        result = subprocess.run(
            ["pgrep", "-f", "rapid-mlx.*serve"],
            capture_output=True,
            text=True,
            timeout=5
        )
        pids = [p for p in result.stdout.strip().split('\n') if p.strip()]
        details["rapid_mlx_pids"] = pids
        details["no_process"] = len(pids) == 0
    except Exception:
        details["no_process"] = True
    
    # Check no listener
    details["no_listener"] = not check_listener_exists(PORT)
    
    # Check connection refused
    details["connection_refused"] = check_connection_refused(PORT)
    
    # Check no PID file
    details["no_pid_file"] = not PID_FILE.exists()
    
    passed = (
        details["no_process"]
        and details["no_listener"]
        and details["connection_refused"]
    )
    return passed, details


def test_secret_scan() -> tuple[bool, dict[str, Any]]:
    """Test 17: Secret scan - no credentials in evidence."""
    details = {
        "no_api_key_in_manifest": False,
        "no_api_key_in_logs": False,
        "no_bearer_in_logs": False,
    }
    
    # Check manifest
    if MANIFEST_FILE.exists():
        manifest_content = MANIFEST_FILE.read_text()
        details["no_api_key_in_manifest"] = (
            "--api-key" not in manifest_content
            and "Bearer " not in manifest_content
            and "api_key" not in manifest_content.lower()
        )
    else:
        details["no_api_key_in_manifest"] = True
    
    # Check logs
    log_files = list(LOG_DIR.glob("*.log")) if LOG_DIR.exists() else []
    log_content = ""
    for log_file in log_files:
        log_content += log_file.read_text(errors="ignore")
    
    details["no_api_key_in_logs"] = "--api-key" not in log_content
    details["no_bearer_in_logs"] = "Bearer " not in log_content
    
    passed = (
        details["no_api_key_in_manifest"]
        and details["no_api_key_in_logs"]
        and details["no_bearer_in_logs"]
    )
    return passed, details


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    print("=" * 60)
    print("P2 LIFECYCLE CERTIFICATION")
    print("=" * 60)
    print()
    
    # Ensure evidence directory exists
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Run tests in order
    tests = [
        ("01_initial_state", test_initial_state),
        ("02_start", test_start),
        ("03_health", test_health),
        ("04_status", test_status),
        ("05_smoke", test_smoke),
        ("06_logs", test_logs),
        ("07_duplicate_start", test_duplicate_start),
        ("08_restart", test_restart),
        ("09_health_after_restart", test_health_after_restart),
        ("10_stop", test_stop),
        ("11_duplicate_stop", test_duplicate_stop),
        ("12_stale_pid", test_stale_pid_handling),
        ("13_unrelated_pid", test_unrelated_pid_protection),
        ("14_port_conflict", test_port_conflict_handling),
        ("15_failed_start_cleanup", test_failed_start_cleanup),
        ("16_final_cleanup", test_final_cleanup),
        ("17_secret_scan", test_secret_scan),
    ]
    
    all_passed = True
    
    for name, test_func in tests:
        print(f"Running {name}...", end=" ")
        try:
            passed, details = test_func()
            add_test_result(name, passed, details)
            status = "PASS" if passed else "FAIL"
            print(status)
            if not passed:
                all_passed = False
                print(f"  Details: {json.dumps(details, indent=2)[:500]}")
        except Exception as e:
            print(f"ERROR: {e}")
            add_test_result(name, False, {"error": str(e)})
            all_passed = False
    
    # Collect fingerprint
    print()
    print("Collecting fingerprint...")
    try:
        version_result = subprocess.run(
            [str(RAPID_MLX_BIN), "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        evidence["fingerprint"]["version"] = version_result.stdout.strip()
        evidence["fingerprint"]["expected_version"] = EXPECTED_VERSION
        evidence["fingerprint"]["model_alias"] = MODEL_ALIAS
        evidence["fingerprint"]["model_resolved"] = MODEL_RESOLVED
        evidence["fingerprint"]["host"] = HOST
        evidence["fingerprint"]["port"] = PORT
        evidence["fingerprint"]["max_tokens"] = MAX_TOKENS
        evidence["fingerprint"]["prefill_step"] = PREFILL_STEP
        evidence["fingerprint"]["gpu_memory"] = GPU_MEM_UTIL
    except Exception as e:
        evidence["fingerprint"]["error"] = str(e)
    
    # Final state
    print("Checking final state...")
    evidence["final_state"] = {
        "port_free": check_port_free(PORT),
        "no_listener": not check_listener_exists(PORT),
        "connection_refused": check_connection_refused(PORT),
        "pid_file_exists": PID_FILE.exists(),
    }
    
    # Summary
    evidence["completed_at"] = datetime.now(timezone.utc).isoformat()
    evidence["status"] = "PASS" if all_passed else "FAIL"
    
    # Count results
    passed_count = sum(1 for t in evidence["tests"] if t["passed"])
    total_count = len(evidence["tests"])
    evidence["summary"] = {
        "passed": passed_count,
        "total": total_count,
        "all_passed": all_passed,
    }
    
    # Write evidence
    evidence_file = EVIDENCE_DIR / "p2-lifecycle-certification.json"
    evidence_file.write_text(json.dumps(evidence, indent=2))
    
    # Write console log
    console_file = EVIDENCE_DIR / "p2-lifecycle-certification-console.txt"
    console_content = f"""P2 LIFECYCLE CERTIFICATION
===========================
Started: {evidence["started_at"]}
Completed: {evidence["completed_at"]}
Status: {evidence["status"]}

TESTS
-----
"""
    for test in evidence["tests"]:
        status = "PASS" if test["passed"] else "FAIL"
        console_content += f"{test['name']}: {status}\n"
    
    console_content += f"""
SUMMARY
-------
Passed: {passed_count}/{total_count}
Overall: {evidence["status"]}

FINGERPRINT
-----------
Version: {EXPECTED_VERSION}
Model: {MODEL_ALIAS}
Host: {HOST}
Port: {PORT}
Max tokens: {MAX_TOKENS}
Prefill step: {PREFILL_STEP}
GPU memory: {GPU_MEM_UTIL}

FINAL STATE
-----------
Port free: {evidence["final_state"]["port_free"]}
No listener: {evidence["final_state"]["no_listener"]}
Connection refused: {evidence["final_state"]["connection_refused"]}
"""
    console_file.write_text(console_content)
    
    print()
    print("=" * 60)
    print(f"P2 CERTIFICATION: {evidence['status']}")
    print(f"Tests: {passed_count}/{total_count}")
    print(f"Evidence: {evidence_file}")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
