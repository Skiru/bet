#!/usr/bin/env python3
"""Repeated tests with statistics for production certification."""
from __future__ import annotations

import json
import urllib.request
import time
import subprocess
from dataclasses import dataclass, asdict, field
from typing import Optional
from pathlib import Path
import statistics

BASE_URL = "http://127.0.0.1:8000/v1"
PID_FILE = Path(".kilo/runtime/rapid-mlx-8000.pid")


@dataclass
class SampleResult:
    attempt: int
    passed: bool
    latency_s: float
    error: Optional[str]
    finish_reason: Optional[str]
    malformed_tool: bool
    missing_tool: bool
    duplicated_tool: bool
    timeout: bool


@dataclass
class TestSummary:
    name: str
    attempts: int
    passed: int
    latency_p50: Optional[float]
    latency_p95: Optional[float]
    latency_max: Optional[float]
    malformed_tool_count: int
    missing_tool_count: int
    duplicated_tool_count: int
    timeout_count: int
    finish_reasons: dict


def request_json(payload: dict, timeout: int = 120) -> tuple[dict, float]:
    url = f"{BASE_URL}/chat/completions"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as response:
        result = json.loads(response.read())
    return result, time.perf_counter() - start


def request_stream_full(payload: dict, timeout: int = 120) -> tuple[str, dict, float]:
    url = f"{BASE_URL}/chat/completions"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    chunks = []
    finish_reason = None
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as response:
        for line in response:
            line = line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            chunks.append(line)
            if line.startswith("data: ") and line != "data: [DONE]":
                try:
                    obj = json.loads(line[6:])
                    finish_reason = obj.get("choices", [{}])[0].get("finish_reason") or finish_reason
                except:
                    pass
    return "\n".join(chunks), {"finish_reason": finish_reason}, time.perf_counter() - start


def run_repeated_chat(attempts: int = 20) -> TestSummary:
    results = []
    finish_reasons = {}
    for i in range(1, attempts + 1):
        marker = f"CHAT_OK_{i}"
        payload = {
            "model": "default",
            "messages": [{"role": "user", "content": f"Reply with exactly {marker}."}],
            "temperature": 0,
            "max_tokens": 64,
            "stream": False,
        }
        timeout_flag = False
        try:
            result, latency = request_json(payload, timeout=60)
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            passed = marker in content
            fr = result.get("choices", [{}])[0].get("finish_reason", "unknown")
            finish_reasons[fr] = finish_reasons.get(fr, 0) + 1
            error = None if passed else f"marker not in content: {content[:50]}"
        except Exception as exc:
            passed = False
            latency = 0
            fr = "error"
            error = str(exc)
            finish_reasons[fr] = finish_reasons.get(fr, 0) + 1
            timeout_flag = isinstance(exc, TimeoutError)
        results.append(SampleResult(i, passed, latency, error, fr, False, False, False, timeout_flag))
    return summarize("chat", results)


def run_repeated_tool(attempts: int = 30) -> TestSummary:
    results = []
    finish_reasons = {}
    for i in range(1, attempts + 1):
        tools = [{"type": "function", "function": {"name": "probe_status", "description": "Probe", "parameters": {"type": "object", "properties": {"seq": {"type": "integer"}}, "required": ["seq"]}}}]
        payload = {
            "model": "default",
            "messages": [{"role": "user", "content": f"Call probe_status with seq={i}. Do not answer directly."}],
            "tools": tools,
            "tool_choice": "required",
            "temperature": 0,
            "max_tokens": 256,
            "stream": False,
        }
        timeout_flag = False
        try:
            result, latency = request_json(payload, timeout=60)
            tool_calls = result.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
            names = [tc.get("function", {}).get("name") for tc in tool_calls]
            passed = "probe_status" in names
            malformed = len(tool_calls) > 0 and not names
            missing = "probe_status" not in names
            duplicated = names.count("probe_status") > 1
            fr = result.get("choices", [{}])[0].get("finish_reason", "unknown")
            finish_reasons[fr] = finish_reasons.get(fr, 0) + 1
            error = None if passed else f"tool_calls={names}"
        except Exception as exc:
            passed = False
            latency = 0
            fr = "error"
            error = str(exc)
            malformed = False
            missing = True
            duplicated = False
            finish_reasons[fr] = finish_reasons.get(fr, 0) + 1
            timeout_flag = isinstance(exc, TimeoutError)
        results.append(SampleResult(i, passed, latency, error, fr, malformed, missing, duplicated, timeout_flag))
    return summarize("tool", results)


def run_repeated_multitool(attempts: int = 30) -> TestSummary:
    results = []
    finish_reasons = {}
    for i in range(1, attempts + 1):
        tools = [
            {"type": "function", "function": {"name": "probe_alpha", "description": "Alpha", "parameters": {"type": "object", "properties": {"val": {"type": "integer"}}, "required": ["val"]}}},
            {"type": "function", "function": {"name": "probe_beta", "description": "Beta", "parameters": {"type": "object", "properties": {"val": {"type": "integer"}}, "required": ["val"]}}},
        ]
        payload = {
            "model": "default",
            "messages": [{"role": "user", "content": f"Call probe_alpha with val={i} and probe_beta with val={i*2}. Use both tools."}],
            "tools": tools,
            "tool_choice": "required",
            "temperature": 0,
            "max_tokens": 512,
            "stream": False,
        }
        timeout_flag = False
        try:
            result, latency = request_json(payload, timeout=60)
            tool_calls = result.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
            names = [tc.get("function", {}).get("name") for tc in tool_calls]
            passed = "probe_alpha" in names and "probe_beta" in names
            malformed = len(tool_calls) > 0 and not names
            missing = "probe_alpha" not in names or "probe_beta" not in names
            duplicated = names.count("probe_alpha") > 1 or names.count("probe_beta") > 1
            fr = result.get("choices", [{}])[0].get("finish_reason", "unknown")
            finish_reasons[fr] = finish_reasons.get(fr, 0) + 1
            error = None if passed else f"tool_calls={names}"
        except Exception as exc:
            passed = False
            latency = 0
            fr = "error"
            error = str(exc)
            malformed = False
            missing = True
            duplicated = False
            finish_reasons[fr] = finish_reasons.get(fr, 0) + 1
            timeout_flag = isinstance(exc, TimeoutError)
        results.append(SampleResult(i, passed, latency, error, fr, malformed, missing, duplicated, timeout_flag))
    return summarize("multitool", results)


def run_repeated_stream_nonthinking(attempts: int = 20) -> TestSummary:
    results = []
    finish_reasons = {}
    for i in range(1, attempts + 1):
        marker = f"STREAM_OK"
        payload = {
            "model": "default",
            "messages": [{"role": "user", "content": f"Reply with exactly {marker}."}],
            "temperature": 0,
            "max_tokens": 128,
            "stream": True,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        timeout_flag = False
        try:
            text, meta, latency = request_stream_full(payload, timeout=60)
            content_parts = []
            for line in text.split("\n"):
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        obj = json.loads(line[6:])
                        delta = obj.get("choices", [{}])[0].get("delta", {})
                        if "content" in delta:
                            content_parts.append(delta["content"])
                    except:
                        pass
            full_content = "".join(content_parts)
            marker_found = marker in full_content
            has_done = "[DONE]" in text
            passed = marker_found and has_done and meta["finish_reason"] == "stop"
            fr = meta["finish_reason"] or "unknown"
            finish_reasons[fr] = finish_reasons.get(fr, 0) + 1
            error = None if passed else f"finish={fr}, marker_found={marker_found}, has_done={has_done}"
        except Exception as exc:
            passed = False
            latency = 0
            fr = "error"
            error = str(exc)
            finish_reasons[fr] = finish_reasons.get(fr, 0) + 1
            timeout_flag = isinstance(exc, TimeoutError)
        results.append(SampleResult(i, passed, latency, error, fr, False, False, False, timeout_flag))
    return summarize("stream_nonthinking", results)


def summarize(name: str, results: list[SampleResult]) -> TestSummary:
    latencies = [r.latency_s for r in results if r.passed]
    return TestSummary(
        name=name,
        attempts=len(results),
        passed=sum(1 for r in results if r.passed),
        latency_p50=statistics.median(latencies) if latencies else None,
        latency_p95=statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies) if latencies else None,
        latency_max=max(latencies) if latencies else None,
        malformed_tool_count=sum(1 for r in results if r.malformed_tool),
        missing_tool_count=sum(1 for r in results if r.missing_tool),
        duplicated_tool_count=sum(1 for r in results if r.duplicated_tool),
        timeout_count=sum(1 for r in results if r.timeout),
        finish_reasons={r.finish_reason: sum(1 for x in results if x.finish_reason == r.finish_reason) for r in results},
    )


if __name__ == "__main__":
    import sys
    reports = []
    
    print("Running chat tests (20 attempts)...")
    s1 = run_repeated_chat(20)
    print(f"  {s1.passed}/{s1.attempts} passed")
    reports.append(asdict(s1))
    
    print("Running tool tests (30 attempts)...")
    s2 = run_repeated_tool(30)
    print(f"  {s2.passed}/{s2.attempts} passed")
    reports.append(asdict(s2))
    
    print("Running multitool tests (30 attempts)...")
    s3 = run_repeated_multitool(30)
    print(f"  {s3.passed}/{s3.attempts} passed")
    reports.append(asdict(s3))
    
    print("Running non-thinking stream tests (20 attempts)...")
    s4 = run_repeated_stream_nonthinking(20)
    print(f"  {s4.passed}/{s4.attempts} passed")
    reports.append(asdict(s4))
    
    report_path = Path("reports/implementation/2026-06-10T15-22-failed-baseline/repeated-tests.json")
    report_path.write_text(json.dumps({"tests": reports}, indent=2) + "\n")
    
    print("\n=== SUMMARY ===")
    for r in reports:
        print(f"{r['name']}: {r['passed']}/{r['attempts']} ({100*r['passed']/r['attempts']:.1f}%)")
    
    all_pass = all(r["passed"] == r["attempts"] for r in reports)
    sys.exit(0 if all_pass else 1)
