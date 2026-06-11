#!/usr/bin/env python3
"""Low-overhead macOS process/RAM/swap monitor that writes CSV during a soak run."""
from __future__ import annotations

import argparse
import csv
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def command(*args: str) -> str:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def process_stats(pid: int) -> tuple[str, str]:
    raw = command("ps", "-o", "rss=,%cpu=", "-p", str(pid))
    fields = raw.split()
    return (fields[0], fields[1]) if len(fields) >= 2 else ("", "")


def swap_mb() -> str:
    raw = command("sysctl", "-n", "vm.swapusage")
    try:
        return raw.split("used =", 1)[1].split("M", 1)[0].strip()
    except Exception:
        return ""


def pressure() -> str:
    raw = command("memory_pressure", "-Q")
    for line in raw.splitlines():
        if "System-wide memory free percentage" in line:
            return line.rsplit(":", 1)[-1].strip().rstrip("%")
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid-file", default=".kilo/runtime/rapid-mlx-8000.pid")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--duration", type=int, default=3600)
    parser.add_argument("--output", default="reports/mac-resources.csv")
    args = parser.parse_args()

    pid = int(Path(args.pid_file).read_text().strip())
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.duration
    with output.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp_utc", "pid", "rss_mb", "cpu_percent", "swap_used_mb", "memory_free_percent"])
        while time.monotonic() < deadline:
            rss_kb, cpu = process_stats(pid)
            if not rss_kb:
                writer.writerow([datetime.now(timezone.utc).isoformat(), pid, "", "", swap_mb(), pressure()])
                handle.flush()
                return 2
            writer.writerow([
                datetime.now(timezone.utc).isoformat(),
                pid,
                round(int(rss_kb) / 1024, 2),
                cpu,
                swap_mb(),
                pressure(),
            ])
            handle.flush()
            time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
