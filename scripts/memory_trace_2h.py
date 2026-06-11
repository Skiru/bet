#!/usr/bin/env python3
"""Genuine 2-hour memory trace with workload and health checks."""
import subprocess
import json
import time
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
import os
import sys

DURATION_SECONDS = 7200
INTERVAL_SECONDS = 5
BASE_URL = "http://127.0.0.1:8000/v1"


def get_process_info(pid: int) -> dict:
    """Get process tree info."""
    result = {"pid": pid, "rss_kb": 0, "vsz_kb": 0, "children": []}
    try:
        # Get parent process info
        output = subprocess.check_output(["ps", "-o", "pid,ppid,rss,vsz,comm", "-p", str(pid)], text=True)
        lines = output.strip().split("\n")
        if len(lines) > 1:
            parts = lines[1].split()
            result["rss_kb"] = int(parts[2])
            result["vsz_kb"] = int(parts[3])
        
        # Get children
        output = subprocess.check_output(["pgrep", "-P", str(pid)], text=True)
        for child_pid in output.strip().split():
            if child_pid:
                child_info = get_process_info(int(child_pid))
                result["children"].append(child_info)
                result["rss_kb"] += child_info["rss_kb"]
    except:
        pass
    return result


def get_vm_stats() -> dict:
    """Get VM statistics."""
    result = {}
    try:
        output = subprocess.check_output(["vm_stat"], text=True)
        for line in output.split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                result[key.strip()] = val.strip().rstrip(".")
    except:
        pass
    return result


def get_swap_mb() -> float:
    """Get swap used in MB."""
    try:
        output = subprocess.check_output(["sysctl", "-n", "vm.swapusage"], text=True)
        for part in output.split("used"):
            if "=" in part:
                return float(part.split("=")[1].strip().split("M")[0])
    except:
        pass
    return 0.0


def get_memory_pressure() -> str:
    """Get memory pressure level."""
    try:
        return subprocess.check_output(["memory_pressure"], text=True).strip()
    except:
        return "unknown"


def make_health_request() -> tuple[bool, float]:
    """Make health request and return status and latency."""
    try:
        start = time.perf_counter()
        with urllib.request.urlopen(f"{BASE_URL}/models", timeout=10) as response:
            latency = time.perf_counter() - start
            return response.status == 200, latency
    except:
        return False, 0.0


def make_workload_request() -> tuple[bool, float, str]:
    """Make a minimal workload request."""
    try:
        payload = {
            "model": "default",
            "messages": [{"role": "user", "content": "Count from 1 to 5."}],
            "temperature": 0,
            "max_tokens": 32,
            "stream": False,
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        start = time.perf_counter()
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read())
            latency = time.perf_counter() - start
            finish_reason = result.get("choices", [{}])[0].get("finish_reason", "unknown")
            return True, latency, finish_reason
    except Exception as e:
        return False, 0.0, str(e)


def main():
    if len(sys.argv) < 2:
        print("Usage: memory_trace_2h.py <output.json> [--dry-run]")
        sys.exit(1)
    
    output_path = Path(sys.argv[1])
    dry_run = "--dry-run" in sys.argv
    duration = 60 if dry_run else DURATION_SECONDS
    
    # Get PID
    try:
        pid_file = Path(".kilo/runtime/rapid-mlx-8000.pid")
        pid = int(pid_file.read_text().strip())
    except:
        print("ERROR: Cannot read PID file")
        sys.exit(1)
    
    started_at = datetime.now(timezone.utc)
    samples = []
    request_count = 0
    success_count = 0
    
    print(f"Starting {duration}s trace at {started_at.isoformat()}")
    print(f"PID: {pid}, Output: {output_path}")
    
    end_time = time.time() + duration
    
    while time.time() < end_time:
        now = time.time()
        
        # Collect sample
        process_info = get_process_info(pid)
        vm_stats = get_vm_stats()
        swap_mb = get_swap_mb()
        pressure = get_memory_pressure()
        health_ok, health_latency = make_health_request()
        
        # Make workload request every 5 samples
        workload_ok, workload_latency, workload_result = False, 0.0, "skipped"
        if len(samples) % 5 == 0:
            workload_ok, workload_latency, workload_result = make_workload_request()
            request_count += 1
            if workload_ok:
                success_count += 1
        
        sample = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": round(now - started_at.timestamp(), 1),
            "process": process_info,
            "swap_used_mb": swap_mb,
            "memory_pressure": pressure,
            "pages_active": vm_stats.get("Pages active"),
            "pages_wired": vm_stats.get("Pages wired down"),
            "pages_free": vm_stats.get("Pages free"),
            "health_ok": health_ok,
            "health_latency_s": health_latency,
            "workload_ok": workload_ok,
            "workload_latency_s": workload_latency,
            "workload_result": workload_result,
        }
        samples.append(sample)
        
        # Save intermediate results every 60 samples
        if len(samples) % 60 == 0:
            elapsed = time.time() - started_at.timestamp()
            print(f"Sample {len(samples)}, elapsed {elapsed:.0f}s, swap {swap_mb:.0f}MB, requests {success_count}/{request_count}")
        
        time.sleep(INTERVAL_SECONDS)
    
    ended_at = datetime.now(timezone.utc)
    actual_duration = (ended_at - started_at).total_seconds()
    
    report = {
        "started_at_utc": started_at.isoformat(),
        "ended_at_utc": ended_at.isoformat(),
        "duration_requested_s": duration,
        "duration_actual_s": round(actual_duration, 1),
        "sample_count": len(samples),
        "interval_s": INTERVAL_SECONDS,
        "request_count": request_count,
        "request_success_count": success_count,
        "samples": samples if len(samples) <= 1000 else samples[::2],  # Compress if too large
        "summary": {
            "rss_peak_kb": max(s["process"]["rss_kb"] for s in samples),
            "swap_peak_mb": max(s["swap_used_mb"] for s in samples),
            "swap_start_mb": samples[0]["swap_used_mb"],
            "swap_end_mb": samples[-1]["swap_used_mb"],
        }
    }
    
    # Validation
    if actual_duration < 7200 and not dry_run:
        report["VALIDATION"] = "FAILED: duration < 7200 seconds"
        print(f"ERROR: Duration {actual_duration}s < 7200s required")
        output_path.write_text(json.dumps(report, indent=2))
        sys.exit(1)
    
    output_path.write_text(json.dumps(report, indent=2))
    print(f"Wrote {len(samples)} samples to {output_path}")
    print(f"Duration: {actual_duration:.0f}s, Requests: {success_count}/{request_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
