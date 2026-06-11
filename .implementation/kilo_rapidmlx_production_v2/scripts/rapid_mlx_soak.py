#!/usr/bin/env python3
"""Sequential Rapid-MLX stability harness: chat, required tools, streaming and recovery."""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class Sample:
    round: int
    kind: str
    ok: bool
    latency_s: float
    error: str | None
    rss_mb: float | None
    swap_used_mb: float | None


def request_json(url: str, payload: dict[str, Any] | None = None, timeout: int = 900) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read())


def request_stream(url: str, payload: dict[str, Any], timeout: int = 900) -> str:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    chunks: list[str] = []
    with urllib.request.urlopen(req, timeout=timeout) as response:
        for raw in response:
            chunks.append(raw.decode("utf-8", errors="replace"))
    return "".join(chunks)


def rss_mb(pid: int | None) -> float | None:
    if not pid:
        return None
    try:
        raw = subprocess.check_output(["ps", "-o", "rss=", "-p", str(pid)], text=True).strip()
        return round(int(raw) / 1024, 2) if raw else None
    except Exception:
        return None


def swap_used_mb() -> float | None:
    try:
        raw = subprocess.check_output(["sysctl", "-n", "vm.swapusage"], text=True)
        return float(raw.split("used =", 1)[1].split("M", 1)[0].strip())
    except Exception:
        return None


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * q))
    return round(ordered[index], 3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--rounds", type=int, default=60)
    parser.add_argument("--pause", type=float, default=1.0)
    parser.add_argument("--pid-file", default=".kilo/runtime/rapid-mlx-8000.pid")
    parser.add_argument("--report", default="reports/rapid-mlx-soak.json")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    request_json(f"{base}/models", timeout=20)
    try:
        pid = int(Path(args.pid_file).read_text().strip())
    except Exception:
        pid = None

    samples: list[Sample] = []
    conversation: list[dict[str, Any]] = [
        {"role": "system", "content": "You are a deterministic reliability probe."}
    ]

    for n in range(1, args.rounds + 1):
        kind = {0: "stream", 1: "chat", 2: "tool", 3: "multitool"}[n % 4]
        marker = f"ROUND-{n}-OK"

        if kind == "chat":
            conversation.append({"role": "user", "content": f"Return exactly {marker}."})
            conversation = [conversation[0], *conversation[-10:]]
            payload: dict[str, Any] = {
                "model": "default",
                "messages": conversation,
                "temperature": 0,
                "max_tokens": 128,
                "stream": False,
            }
        elif kind == "stream":
            payload = {
                "model": "default",
                "messages": [{"role": "user", "content": f"Return exactly {marker}."}],
                "temperature": 0,
                "max_tokens": 128,
                "stream": True,
            }
        else:
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "probe_alpha",
                        "description": "Probe",
                        "parameters": {
                            "type": "object",
                            "properties": {"sequence": {"type": "integer"}},
                            "required": ["sequence"],
                            "additionalProperties": False,
                        },
                    },
                }
            ]
            if kind == "multitool":
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": "probe_beta",
                            "description": "Second probe",
                            "parameters": {
                                "type": "object",
                                "properties": {"sequence": {"type": "integer"}},
                                "required": ["sequence"],
                                "additionalProperties": False,
                            },
                        },
                    }
                )
            instruction = "both tools" if kind == "multitool" else "probe_alpha"
            payload = {
                "model": "default",
                "messages": [
                    {
                        "role": "user",
                        "content": f"Call {instruction} with sequence {n}; do not answer directly.",
                    }
                ],
                "tools": tools,
                "tool_choice": "required",
                "temperature": 0,
                "max_tokens": 768,
                "stream": False,
            }

        started = time.perf_counter()
        ok = False
        error = None
        try:
            if kind == "stream":
                body = request_stream(f"{base}/chat/completions", payload)
                ok = marker in body and "[DONE]" in body
            else:
                result = request_json(f"{base}/chat/completions", payload)
                message = result["choices"][0]["message"]
                if kind == "chat":
                    content = message.get("content") or ""
                    ok = marker in content
                    conversation.append({"role": "assistant", "content": content})
                else:
                    names = [
                        item.get("function", {}).get("name")
                        for item in message.get("tool_calls", [])
                    ]
                    ok = "probe_alpha" in names and (
                        kind != "multitool" or "probe_beta" in names
                    )
            if not ok:
                error = "unexpected response"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

        sample = Sample(
            n,
            kind,
            ok,
            round(time.perf_counter() - started, 3),
            error,
            rss_mb(pid),
            swap_used_mb(),
        )
        samples.append(sample)
        print(json.dumps(asdict(sample)), flush=True)
        time.sleep(args.pause)

    successful_latencies = [sample.latency_s for sample in samples if sample.ok]
    report = {
        "base_url": base,
        "rounds": args.rounds,
        "passed": sum(sample.ok for sample in samples),
        "failed": sum(not sample.ok for sample in samples),
        "success_rate": round(
            sum(sample.ok for sample in samples) / max(1, len(samples)), 4
        ),
        "latency_s": {
            "mean": round(statistics.mean(successful_latencies), 3)
            if successful_latencies
            else None,
            "p50": percentile(successful_latencies, 0.5),
            "p95": percentile(successful_latencies, 0.95),
            "max": round(max(successful_latencies), 3)
            if successful_latencies
            else None,
        },
        "rss_mb": {
            "first": next(
                (sample.rss_mb for sample in samples if sample.rss_mb is not None),
                None,
            ),
            "last": next(
                (
                    sample.rss_mb
                    for sample in reversed(samples)
                    if sample.rss_mb is not None
                ),
                None,
            ),
            "max": max(
                (sample.rss_mb for sample in samples if sample.rss_mb is not None),
                default=None,
            ),
        },
        "swap_used_mb": {
            "first": next(
                (
                    sample.swap_used_mb
                    for sample in samples
                    if sample.swap_used_mb is not None
                ),
                None,
            ),
            "last": next(
                (
                    sample.swap_used_mb
                    for sample in reversed(samples)
                    if sample.swap_used_mb is not None
                ),
                None,
            ),
            "max": max(
                (
                    sample.swap_used_mb
                    for sample in samples
                    if sample.swap_used_mb is not None
                ),
                default=None,
            ),
        },
        "samples": [asdict(sample) for sample in samples],
    }

    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Report: {output}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
