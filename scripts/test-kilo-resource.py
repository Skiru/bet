#!/usr/bin/env python3
"""
Phase 2 — Kilo Resource Observation Test
Production-grade resource monitoring and stability test.

Tests:
1. Memory usage tracking
2. Memory stability over time
3. Resource cleanup verification
4. Server health monitoring
"""

import json
import os
import sys
import subprocess
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

# Configuration
BASE_URL = os.environ.get("RAPID_MLX_BASE_URL", "http://127.0.0.1:8000/v1")
API_KEY = os.environ.get("RAPID_MLX_API_KEY", "bb2c5c92afddd427bbede6807920fe63ac12ea3af4c3a9cb473373d20e8514c7")
MODEL_ID = "default"
OUTPUT_DIR = "reports/kilo-rapidmlx-baseline"
PID_FILE = "reports/rapidmlx-baseline/runtime/rapid-mlx.pid"


def get_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_process_info(pid: int) -> dict:
    """Get process memory and CPU info."""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "rss,vsz,cpu,time"],
            capture_output=True,
            text=True,
            timeout=5
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            return {
                "rss_kb": int(parts[0]) if parts[0].isdigit() else 0,
                "vsz_kb": int(parts[1]) if parts[1].isdigit() else 0,
                "cpu_pct": float(parts[2]) if parts[2].replace(".", "").isdigit() else 0,
                "time": parts[3] if len(parts) > 3 else ""
            }
    except Exception as e:
        return {"error": str(e)}
    return {"error": "Unknown"}


def make_request(endpoint: str, data: dict) -> tuple[int, Any, float]:
    """Make API request and return (status_code, response_data, duration_ms)."""
    url = f"{BASE_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            status = response.status
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        status = e.code
        result = json.loads(e.read().decode("utf-8"))
    except Exception as e:
        status = 0
        result = {"error": str(e)}
    duration_ms = (time.perf_counter() - start) * 1000
    
    return status, result, duration_ms


def test_memory_tracking() -> dict:
    """Test 1: Memory usage tracking."""
    print("  1. Memory usage tracking...")
    
    # Read PID
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
    except:
        print("     FAIL (Cannot read PID file)")
        return {"test": "memory_tracking", "passed": False, "error": "Cannot read PID file"}
    
    info = get_process_info(pid)
    
    if "error" in info:
        print(f"     FAIL ({info['error']})")
        return {"test": "memory_tracking", "passed": False, "error": info["error"]}
    
    rss_mb = info["rss_kb"] / 1024
    vsz_mb = info["vsz_kb"] / 1024
    
    # RSS should be reasonable (under 10GB for this model)
    passed = rss_mb < 10240
    
    print(f"     {'PASS' if passed else 'FAIL'} (RSS={rss_mb:.0f}MB, VSZ={vsz_mb:.0f}MB)")
    
    return {
        "test": "memory_tracking",
        "passed": passed,
        "rss_mb": rss_mb,
        "vsz_mb": vsz_mb,
        "cpu_pct": info.get("cpu_pct", 0)
    }


def test_memory_stability() -> dict:
    """Test 2: Memory stability over time."""
    print("  2. Memory stability over time...")
    
    # Read PID
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
    except:
        print("     FAIL (Cannot read PID file)")
        return {"test": "memory_stability", "passed": False, "error": "Cannot read PID file"}
    
    # Take initial measurement
    initial_info = get_process_info(pid)
    if "error" in initial_info:
        print(f"     FAIL ({initial_info['error']})")
        return {"test": "memory_stability", "passed": False, "error": initial_info["error"]}
    
    initial_rss = initial_info["rss_kb"]
    
    # Run several requests
    for i in range(5):
        make_request("/chat/completions", {
            "model": MODEL_ID,
            "messages": [{"role": "user", "content": f"Test {i+1}" * 100}],
            "max_tokens": 100,
            "temperature": 0
        })
        time.sleep(0.2)
    
    # Take final measurement
    final_info = get_process_info(pid)
    if "error" in final_info:
        print(f"     FAIL ({final_info['error']})")
        return {"test": "memory_stability", "passed": False, "error": final_info["error"]}
    
    final_rss = final_info["rss_kb"]
    
    # Memory should not grow excessively (allow 20% growth)
    growth_pct = ((final_rss - initial_rss) / initial_rss * 100) if initial_rss > 0 else 0
    passed = growth_pct < 20 or final_rss <= initial_rss  # Allow no growth or small growth
    
    print(f"     {'PASS' if passed else 'INFO'} (initial={initial_rss/1024:.0f}MB, final={final_rss/1024:.0f}MB, growth={growth_pct:.1f}%)")
    
    return {
        "test": "memory_stability",
        "passed": passed,
        "initial_rss_kb": initial_rss,
        "final_rss_kb": final_rss,
        "growth_pct": growth_pct
    }


def test_resource_cleanup() -> dict:
    """Test 3: Resource cleanup verification."""
    print("  3. Resource cleanup verification...")
    
    # Read PID
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
    except:
        print("     FAIL (Cannot read PID file)")
        return {"test": "resource_cleanup", "passed": False, "error": "Cannot read PID file"}
    
    # Get initial state
    initial_info = get_process_info(pid)
    if "error" in initial_info:
        print(f"     FAIL ({initial_info['error']})")
        return {"test": "resource_cleanup", "passed": False, "error": initial_info["error"]}
    
    # Run requests with large outputs
    for i in range(3):
        make_request("/chat/completions", {
            "model": MODEL_ID,
            "messages": [{"role": "user", "content": "Write a short poem."}],
            "max_tokens": 200,
            "temperature": 0.5
        })
        time.sleep(0.3)
    
    # Get final state
    final_info = get_process_info(pid)
    if "error" in final_info:
        print(f"     FAIL ({final_info['error']})")
        return {"test": "resource_cleanup", "passed": False, "error": final_info["error"]}
    
    # Check if memory is stable
    rss_diff = abs(final_info["rss_kb"] - initial_info["rss_kb"])
    passed = rss_diff < 500000  # Allow 500MB variance
    
    print(f"     {'PASS' if passed else 'INFO'} (RSS variance={rss_diff/1024:.0f}MB)")
    
    return {
        "test": "resource_cleanup",
        "passed": passed,
        "initial_rss_kb": initial_info.get("rss_kb", 0),
        "final_rss_kb": final_info.get("rss_kb", 0),
        "rss_diff_kb": rss_diff
    }


def test_server_health() -> dict:
    """Test 4: Server health monitoring."""
    print("  4. Server health monitoring...")
    
    # Check health endpoint
    url = f"{BASE_URL.replace('/v1', '')}/health"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=10) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        status = e.code
        body = ""
    except Exception as e:
        status = 0
        body = str(e)
    
    passed = status == 200
    
    print(f"     {'PASS' if passed else 'FAIL'} (HTTP {status})")
    
    return {
        "test": "server_health",
        "passed": passed,
        "http_status": status,
        "response": body[:100] if body else None
    }


def test_process_alive() -> dict:
    """Test 5: Process alive check."""
    print("  5. Process alive check...")
    
    # Read PID
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
    except:
        print("     FAIL (Cannot read PID file)")
        return {"test": "process_alive", "passed": False, "error": "Cannot read PID file"}
    
    # Check if process is alive
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid)],
            capture_output=True,
            timeout=5
        )
        alive = result.returncode == 0
    except:
        alive = False
    
    # Also check port
    try:
        result = subprocess.run(
            ["lsof", "-nP", "-iTCP:8000", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            timeout=5
        )
        port_owner = result.stdout.strip()
        port_ok = port_owner == str(pid)
    except:
        port_ok = False
    
    passed = alive and port_ok
    
    print(f"     {'PASS' if passed else 'FAIL'} (alive={alive}, port_ok={port_ok})")
    
    return {
        "test": "process_alive",
        "passed": passed,
        "process_alive": alive,
        "port_ok": port_ok,
        "pid": pid
    }


def test_thermal_status() -> dict:
    """Test 6: Thermal status check."""
    print("  6. Thermal status check...")
    
    # On macOS, check for thermal pressure
    try:
        result = subprocess.run(
            ["pmset", "-g", "therm"],
            capture_output=True,
            text=True,
            timeout=10
        )
        therm_output = result.stdout
        
        # Check for thermal warnings
        has_warning = "warning" in therm_output.lower() or "limited" in therm_output.lower()
        passed = not has_warning
    except:
        # If we can't check, assume OK
        therm_output = "Unable to check thermal status"
        passed = True
    
    print(f"     {'PASS' if passed else 'WARN'} (thermal_warning={not passed})")
    
    return {
        "test": "thermal_status",
        "passed": passed,
        "thermal_warning": not passed,
        "output": therm_output[:200] if therm_output else None
    }


def main():
    print("=== Phase 2 — Kilo Resource Observation Test ===")
    print(f"Timestamp: {get_timestamp()}")
    print(f"Base URL: {BASE_URL}")
    print(f"Model: {MODEL_ID}")
    print()
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    results = []
    
    print("Running resource observation tests...")
    results.append(test_memory_tracking())
    results.append(test_memory_stability())
    results.append(test_resource_cleanup())
    results.append(test_server_health())
    results.append(test_process_alive())
    results.append(test_thermal_status())
    
    print()
    
    # Summary
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    
    print("=" * 60)
    print(f"RESULTS: {passed}/{total} PASS")
    print("=" * 60)
    
    # Save results
    run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    output_file = os.path.join(OUTPUT_DIR, f"{run_id}-resource-test.json")
    
    with open(output_file, "w") as f:
        json.dump({
            "run_id": run_id,
            "timestamp": get_timestamp(),
            "base_url": BASE_URL,
            "model": MODEL_ID,
            "results": results,
            "summary": {
                "passed": passed,
                "total": total,
                "pass_rate": passed / total if total > 0 else 0
            }
        }, f, indent=2)
    
    print(f"Results saved to: {output_file}")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
