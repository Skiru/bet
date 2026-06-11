#!/usr/bin/env python3
"""Comprehensive streaming tests for Qwen3.6 with thinking modes."""
from __future__ import annotations

import json
import urllib.request
import time
from dataclasses import dataclass, asdict
from typing import Optional

BASE_URL = "http://127.0.0.1:8000/v1"


@dataclass
class TestResult:
    name: str
    passed: bool
    marker_found: bool
    finish_reason: Optional[str]
    completion_tokens: Optional[int]
    has_reasoning_content: bool
    has_final_content: bool
    has_done: bool
    error: Optional[str]
    latency_s: float


def request_stream(payload: dict, timeout: int = 120) -> tuple[str, dict]:
    """Execute streaming request, return full text and metadata."""
    url = f"{BASE_URL}/chat/completions"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    chunks = []
    finish_reason = None
    completion_tokens = None
    has_reasoning = False
    has_content = False
    
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as response:
        for line in response:
            line = line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            if line == "data: [DONE]":
                chunks.append("[DONE]")
                break
            if line.startswith("data: "):
                try:
                    obj = json.loads(line[6:])
                    chunks.append(line)
                    delta = obj.get("choices", [{}])[0].get("delta", {})
                    if "reasoning_content" in delta:
                        has_reasoning = True
                    if "content" in delta:
                        has_content = True
                    finish = obj.get("choices", [{}])[0].get("finish_reason")
                    if finish:
                        finish_reason = finish
                    usage = obj.get("usage", {})
                    if usage:
                        completion_tokens = usage.get("completion_tokens")
                except json.JSONDecodeError:
                    pass
    return "\n".join(chunks), {
        "finish_reason": finish_reason,
        "completion_tokens": completion_tokens,
        "has_reasoning_content": has_reasoning,
        "has_final_content": has_content,
        "latency_s": round(time.perf_counter() - start, 3),
    }


def test_non_thinking_stream() -> TestResult:
    """Test streaming with thinking disabled."""
    marker = "STREAM_OK"
    payload = {
        "model": "default",
        "messages": [{"role": "user", "content": f"Reply with exactly {marker}. No other text."}],
        "temperature": 0,
        "max_tokens": 128,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    
    text, meta = request_stream(payload)
    
    # Check for marker in content (not reasoning_content)
    content_parts = []
    for line in text.split("\n"):
        if line.startswith("data: ") and line != "data: [DONE]":
            try:
                obj = json.loads(line[6:])
                content = obj.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if content:
                    content_parts.append(content)
            except:
                pass
    
    full_content = "".join(content_parts)
    marker_found = marker in full_content
    has_done = "[DONE]" in text
    passed = (
        marker_found
        and has_done
        and meta["finish_reason"] == "stop"
        and meta["has_final_content"]
    )
    
    return TestResult(
        name="non_thinking_stream",
        passed=passed,
        marker_found=marker_found,
        finish_reason=meta["finish_reason"],
        completion_tokens=meta["completion_tokens"],
        has_reasoning_content=meta["has_reasoning_content"],
        has_final_content=meta["has_final_content"],
        has_done=has_done,
        error=None if passed else f"finish_reason={meta['finish_reason']}, marker_in_content={marker_found}",
        latency_s=meta["latency_s"],
    )


def test_reasoning_aware_stream() -> TestResult:
    """Test streaming with thinking enabled, expect reasoning + content."""
    marker = "STREAM_REASONING_OK"
    payload = {
        "model": "default",
        "messages": [{"role": "user", "content": f"After thinking, reply with exactly {marker}."}],
        "temperature": 0,
        "max_tokens": 512,
        "stream": True,
    }
    
    text, meta = request_stream(payload)
    
    # Collect all content
    content_parts = []
    reasoning_parts = []
    for line in text.split("\n"):
        if line.startswith("data: ") and line != "data: [DONE]":
            try:
                obj = json.loads(line[6:])
                delta = obj.get("choices", [{}])[0].get("delta", {})
                if "content" in delta:
                    content_parts.append(delta["content"])
                if "reasoning_content" in delta:
                    reasoning_parts.append(delta["reasoning_content"])
            except:
                pass
    
    full_content = "".join(content_parts)
    marker_found = marker in full_content
    has_done = "[DONE]" in text
    passed = (
        marker_found
        and has_done
        and meta["finish_reason"] == "stop"
        and meta["has_reasoning_content"]
        and meta["has_final_content"]
    )
    
    return TestResult(
        name="reasoning_aware_stream",
        passed=passed,
        marker_found=marker_found,
        finish_reason=meta["finish_reason"],
        completion_tokens=meta["completion_tokens"],
        has_reasoning_content=meta["has_reasoning_content"],
        has_final_content=meta["has_final_content"],
        has_done=has_done,
        error=None if passed else f"finish_reason={meta['finish_reason']}, marker_found={marker_found}, has_reasoning={meta['has_reasoning_content']}, has_content={meta['has_final_content']}",
        latency_s=meta["latency_s"],
    )


def test_cancellation_recovery() -> dict:
    """Test stream cancellation and immediate recovery."""
    import socket
    import ssl
    
    results = {"cancellation": None, "recovery_health": None, "recovery_chat": None, "recovery_stream": None}
    
    # Start a long streaming request
    url = f"{BASE_URL}/chat/completions"
    payload = {
        "model": "default",
        "messages": [{"role": "user", "content": "Count from 1 to 1000 slowly, one number per line."}],
        "temperature": 0,
        "max_tokens": 4096,
        "stream": True,
    }
    
    # Open connection but don't read all
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as response:
            # Read first few chunks then break connection
            for i, line in enumerate(response):
                if i > 5:
                    break
            # Connection will be closed when we return
        results["cancellation"] = {"ok": True, "chunks_read": i + 1}
    except Exception as e:
        results["cancellation"] = {"ok": False, "error": str(e)}
    
    time.sleep(1)
    
    # Recovery test 1: health check
    try:
        with urllib.request.urlopen(f"{BASE_URL}/models", timeout=10) as response:
            results["recovery_health"] = {"ok": response.status == 200}
    except Exception as e:
        results["recovery_health"] = {"ok": False, "error": str(e)}
    
    # Recovery test 2: non-streaming completion
    try:
        payload = {
            "model": "default",
            "messages": [{"role": "user", "content": "Reply with exactly RECOVERY_OK."}],
            "temperature": 0,
            "max_tokens": 32,
            "stream": False,
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read())
            content = result["choices"][0]["message"].get("content", "")
            results["recovery_chat"] = {"ok": "RECOVERY_OK" in content, "content": content[:50]}
    except Exception as e:
        results["recovery_chat"] = {"ok": False, "error": str(e)}
    
    # Recovery test 3: post-cancel streaming
    try:
        payload = {
            "model": "default",
            "messages": [{"role": "user", "content": "Reply with exactly POST_CANCEL_STREAM_OK."}],
            "temperature": 0,
            "max_tokens": 128,
            "stream": True,
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        full_text = ""
        with urllib.request.urlopen(req, timeout=60) as response:
            for line in response:
                full_text += line.decode("utf-8", errors="replace")
        results["recovery_stream"] = {"ok": "POST_CANCEL_STREAM_OK" in full_text and "[DONE]" in full_text}
    except Exception as e:
        results["recovery_stream"] = {"ok": False, "error": str(e)}
    
    return results


if __name__ == "__main__":
    import sys
    
    print("=== Non-Thinking Stream Test ===")
    r1 = test_non_thinking_stream()
    print(json.dumps(asdict(r1), indent=2))
    
    print("\n=== Reasoning-Aware Stream Test ===")
    r2 = test_reasoning_aware_stream()
    print(json.dumps(asdict(r2), indent=2))
    
    print("\n=== Cancellation Recovery Test ===")
    r3 = test_cancellation_recovery()
    print(json.dumps(r3, indent=2))
    
    all_passed = r1.passed and r2.passed and all(r3.get(k, {}).get("ok", False) for k in ["recovery_health", "recovery_chat", "recovery_stream"])
    
    print(f"\n=== OVERALL: {'PASS' if all_passed else 'FAIL'} ===")
    sys.exit(0 if all_passed else 1)
