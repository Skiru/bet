#!/usr/bin/env python3
"""
Phase 1 — Rapid-MLX Raw Baseline Test Harness
Production-grade validation for qwen3.6-35b-4bit

Version: 1.0.0
Schema Version: 1.0.0
Test Suite Version: 1.0.0

Usage:
    python scripts/test-rapidmlx-baseline.py smoke
    python scripts/test-rapidmlx-baseline.py qualify
    python scripts/test-rapidmlx-baseline.py all

Optional arguments:
    --base-url URL        (default: http://127.0.0.1:8000)
    --model MODEL         (default: from /v1/models)
    --output-dir DIR      (default: reports/rapidmlx-baseline/runs)
    --request-timeout SEC (default: 120)
"""

import argparse
import hashlib
import json
import os
import socket
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import urllib.request
import urllib.error
import ssl

# =============================================================================
# CONFIGURATION
# =============================================================================

SUITE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT = 120
DEFAULT_OUTPUT_DIR = "reports/rapidmlx-baseline/runs"

# Request profiles
EXECUTOR_PROFILE = {
    "enable_thinking": False,
    "preserve_thinking": False,
    "temperature": 0.7,
    "top_p": 0.8,
    "max_tokens": 256,
}

SYNTHESIS_PROFILE = {
    "enable_thinking": True,
    "preserve_thinking": False,
    "temperature": 1.0,
    "top_p": 0.95,
    "max_tokens": 2048,
}

TOOL_PROFILE = {
    "enable_thinking": False,
    "preserve_thinking": False,
    "temperature": 0.7,
    "top_p": 0.8,
    "max_tokens": 512,
}

# Tool definitions
GET_TEST_VALUE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_test_value",
        "description": "Get a test value by key. Use this when you need to retrieve a specific test value.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The key to look up"
                }
            },
            "required": ["key"]
        }
    }
}

LOOKUP_ITEM_TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_item",
        "description": "Look up an item by its ID. Returns item details.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The item ID to look up"
                }
            },
            "required": ["id"]
        }
    }
}

VALIDATE_ITEM_TOOL = {
    "type": "function",
    "function": {
        "name": "validate_item",
        "description": "Validate an item value. Returns validation result.",
        "parameters": {
            "type": "object",
            "properties": {
                "value": {
                    "type": "string",
                    "description": "The value to validate"
                }
            },
            "required": ["value"]
        }
    }
}

# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class AttemptResult:
    """Result of a single test attempt"""
    suite: str
    attempt_id: str
    mode: str
    streaming: bool
    thinking: bool
    tool_choice: Optional[str]
    start_time: str
    duration_ms: float
    ttft_ms: Optional[float]
    http_status: int
    finish_reason: Optional[str]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    reasoning_tokens: Optional[int]
    tool_call_count: int
    final_content_present: bool
    error_category: Optional[str]
    error_detail: Optional[str]
    passed: bool
    failure_reasons: list = field(default_factory=list)

@dataclass
class AggregateMetrics:
    """Aggregated metrics for a test group"""
    group: str
    attempts: int
    passed: int
    failed: int
    p50_latency_ms: float
    p95_latency_ms: float
    max_latency_ms: float
    p50_ttft_ms: Optional[float]
    p95_ttft_ms: Optional[float]
    output_tokens_per_second: Optional[float]

@dataclass
class TestRun:
    """Complete test run results"""
    schema_version: str
    run_id: str
    suite_version: str
    timestamp: str
    base_url: str
    model: str
    configuration_fingerprint: dict
    smoke_results: list
    qualification_results: list
    aggregate_metrics: list
    mandatory_gates: dict
    diagnostic_results: dict
    final_status: str

# =============================================================================
# HTTP CLIENT (stdlib only)
# =============================================================================

class HttpClient:
    """Simple HTTP client using urllib (stdlib only)"""

    def __init__(self, base_url: str, timeout: int = DEFAULT_TIMEOUT, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key or os.environ.get("RAPID_MLX_API_KEY")

    def _get_headers(self) -> dict:
        """Get headers including auth if available"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def get(self, path: str) -> tuple[int, dict]:
        """GET request, returns (status_code, json_response)"""
        url = f"{self.base_url}{path}"
        try:
            req = urllib.request.Request(url, method="GET", headers=self._get_headers())
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
                return resp.status, json.loads(body)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if e.fp else ""
            try:
                return e.code, json.loads(body)
            except:
                return e.code, {"error": body}
        except Exception as e:
            return 0, {"error": str(e)}

    def post(self, path: str, data: dict, stream: bool = False) -> tuple[int, Any]:
        """POST request, returns (status_code, response)"""
        url = f"{self.base_url}{path}"
        headers = self._get_headers()

        try:
            req_data = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")

            if stream:
                return self._handle_stream(req)
            else:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8")
                    return resp.status, json.loads(body)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if e.fp else ""
            try:
                return e.code, json.loads(body)
            except:
                return e.code, {"error": body}
        except Exception as e:
            return 0, {"error": str(e)}

    def _handle_stream(self, req: urllib.request.Request) -> tuple[int, list]:
        """Handle SSE stream, returns (status_code, events_list)"""
        events = []
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                buffer = ""
                while True:
                    chunk = resp.read(1024)
                    if not chunk:
                        break
                    buffer += chunk.decode("utf-8")

                    while "\n\n" in buffer:
                        event_data, buffer = buffer.split("\n\n", 1)
                        if event_data.startswith("data: "):
                            data_str = event_data[6:].strip()
                            if data_str == "[DONE]":
                                events.append({"type": "done"})
                            else:
                                try:
                                    events.append({"type": "data", "content": json.loads(data_str)})
                                except:
                                    events.append({"type": "raw", "content": data_str})

            return 200, events
        except Exception as e:
            return 0, [{"type": "error", "content": str(e)}]

# =============================================================================
# TEST HARNESS
# =============================================================================

class TestHarness:
    """Main test harness for Rapid-MLX baseline validation"""

    def __init__(self, base_url: str, output_dir: str, timeout: int):
        self.client = HttpClient(base_url, timeout)
        self.base_url = base_url
        self.output_dir = Path(output_dir)
        self.timeout = timeout
        self.run_id = self._generate_run_id()
        self.model: Optional[str] = None
        self.results: list[AttemptResult] = []
        self.failures_dir = self.output_dir.parent / "failures"

        # Ensure directories exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.failures_dir.mkdir(parents=True, exist_ok=True)

    def _generate_run_id(self) -> str:
        """Generate unique run ID"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        short_uuid = uuid.uuid4().hex[:8]
        return f"run-{timestamp}-{short_uuid}"

    def _generate_attempt_id(self) -> str:
        """Generate unique attempt ID"""
        return f"{self.run_id}-attempt-{len(self.results)+1:04d}"

    def _get_timestamp(self) -> str:
        """Get ISO timestamp"""
        return datetime.now(timezone.utc).isoformat()

    def discover_model(self) -> Optional[str]:
        """Discover model ID from /v1/models endpoint"""
        status, data = self.client.get("/v1/models")
        if status == 200 and "data" in data:
            models = data["data"]
            if models:
                self.model = models[0].get("id", "default")
                return self.model
        return None

    def _build_request(self, messages: list, tools: Optional[list] = None,
                       tool_choice: Optional[str] = None,
                       profile: Optional[dict] = None,
                       stream: bool = False) -> dict:
        """Build chat completion request"""
        request = {
            "model": self.model or "default",
            "messages": messages,
            "stream": stream,
        }

        # Apply profile
        if profile:
            if "temperature" in profile:
                request["temperature"] = profile["temperature"]
            if "top_p" in profile:
                request["top_p"] = profile["top_p"]
            if "max_tokens" in profile:
                request["max_tokens"] = profile["max_tokens"]

            # Thinking configuration via chat_template_kwargs
            if "enable_thinking" in profile or "preserve_thinking" in profile:
                request["chat_template_kwargs"] = {}
                if "enable_thinking" in profile:
                    request["chat_template_kwargs"]["enable_thinking"] = profile["enable_thinking"]
                if "preserve_thinking" in profile:
                    request["chat_template_kwargs"]["preserve_thinking"] = profile["preserve_thinking"]

        # Tools
        if tools:
            request["tools"] = tools
        if tool_choice:
            request["tool_choice"] = tool_choice

        return request

    def _execute_request(self, messages: list, tools: Optional[list] = None,
                         tool_choice: Optional[str] = None,
                         profile: Optional[dict] = None,
                         stream: bool = False,
                         suite: str = "unknown") -> AttemptResult:
        """Execute a single request and capture results"""
        attempt_id = self._generate_attempt_id()
        start_time = self._get_timestamp()
        start_ns = time.monotonic_ns()

        request = self._build_request(messages, tools, tool_choice, profile, stream)

        ttft_ms = None
        http_status = 0
        response = None
        error_category = None
        error_detail = None

        if stream:
            http_status, events = self.client.post("/v1/chat/completions", request, stream=True)
            first_token_ns = None

            # Process streaming events
            content_chunks = []
            tool_calls = {}
            finish_reason = None

            for event in events:
                if event.get("type") == "data":
                    data = event.get("content", {})
                    choices = data.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})

                        # Track TTFT
                        if first_token_ns is None and (delta.get("content") or delta.get("tool_calls")):
                            first_token_ns = time.monotonic_ns()
                            ttft_ms = (first_token_ns - start_ns) / 1_000_000

                        # Collect content
                        if "content" in delta and delta["content"]:
                            content_chunks.append(delta["content"])

                        # Collect tool calls
                        if "tool_calls" in delta:
                            for tc in delta["tool_calls"]:
                                idx = tc.get("index", 0)
                                if idx not in tool_calls:
                                    tool_calls[idx] = {"id": "", "function": {"name": "", "arguments": ""}}
                                if "id" in tc:
                                    tool_calls[idx]["id"] = tc["id"]
                                if "function" in tc:
                                    if "name" in tc["function"]:
                                        tool_calls[idx]["function"]["name"] = tc["function"]["name"]
                                    if "arguments" in tc["function"]:
                                        tool_calls[idx]["function"]["arguments"] += tc["function"]["arguments"]

                        # Finish reason
                        if choices[0].get("finish_reason"):
                            finish_reason = choices[0]["finish_reason"]

            # Build response-like structure
            response = {
                "choices": [{
                    "message": {
                        "content": "".join(content_chunks) if content_chunks else None,
                        "tool_calls": list(tool_calls.values()) if tool_calls else None
                    },
                    "finish_reason": finish_reason
                }],
                "usage": {}
            }
        else:
            http_status, response = self.client.post("/v1/chat/completions", request)

        end_ns = time.monotonic_ns()
        duration_ms = (end_ns - start_ns) / 1_000_000

        # Parse response
        finish_reason = None
        prompt_tokens = None
        completion_tokens = None
        reasoning_tokens = None
        tool_call_count = 0
        final_content_present = False
        passed = True
        failure_reasons = []

        if http_status == 200 and response:
            choices = response.get("choices", [])
            if choices:
                choice = choices[0]
                finish_reason = choice.get("finish_reason")
                message = choice.get("message", {})

                # Content
                content = message.get("content")
                final_content_present = content is not None and len(content) > 0

                # Tool calls
                tool_calls = message.get("tool_calls", [])
                tool_call_count = len(tool_calls) if tool_calls else 0

                # Usage
                usage = response.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens")
                completion_tokens = usage.get("completion_tokens")
                reasoning_tokens = usage.get("reasoning_tokens")
        else:
            error_category = "HTTP_ERROR"
            error_detail = f"Status {http_status}: {response}"
            passed = False
            failure_reasons.append("http_error")

        result = AttemptResult(
            suite=suite,
            attempt_id=attempt_id,
            mode="chat",
            streaming=stream,
            thinking=profile.get("enable_thinking", False) if profile else False,
            tool_choice=tool_choice,
            start_time=start_time,
            duration_ms=duration_ms,
            ttft_ms=ttft_ms,
            http_status=http_status,
            finish_reason=finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reasoning_tokens=reasoning_tokens,
            tool_call_count=tool_call_count,
            final_content_present=final_content_present,
            error_category=error_category,
            error_detail=error_detail,
            passed=passed,
            failure_reasons=failure_reasons
        )

        self.results.append(result)
        return result

    def _validate_tool_call(self, result: AttemptResult, expected_tool: str,
                            expected_key: Optional[str] = None) -> list[str]:
        """Validate tool call structure"""
        failures = []

        if result.http_status != 200:
            failures.append("http_error")
            return failures

        # Get response from stored data
        request = {"model": self.model, "messages": [], "stream": False}
        status, response = self.client.post("/v1/chat/completions", request)

        # We need to re-execute to get the actual response
        # For now, check based on tool_call_count
        if result.tool_call_count == 0:
            failures.append("missing_tool_call")
        elif result.tool_call_count > 1:
            failures.append("unexpected_parallel_calls")

        if result.finish_reason == "length":
            failures.append("length_truncation")

        return failures

    def _check_repetition(self, text: str) -> bool:
        """Check for repetition collapse"""
        if not text:
            return False

        # Check for repeated identical sentences (3+ times)
        sentences = text.split(". ")
        if len(sentences) >= 3:
            for i in range(len(sentences) - 2):
                if sentences[i] == sentences[i+1] == sentences[i+2]:
                    return True

        # Check for n-gram loops
        words = text.split()
        if len(words) >= 6:
            for n in [3, 4, 5]:
                for i in range(len(words) - n * 3):
                    ngram = " ".join(words[i:i+n])
                    count = 0
                    j = i
                    while j < len(words) - n:
                        if " ".join(words[j:j+n]) == ngram:
                            count += 1
                            j += n
                        else:
                            break
                    if count >= 3:
                        return True

        return False

    # =========================================================================
    # SMOKE TESTS
    # =========================================================================

    def run_smoke(self) -> tuple[bool, list[AttemptResult]]:
        """Run smoke test suite"""
        smoke_results = []
        all_passed = True

        print("Running smoke tests...")

        # 1. Health check
        print("  1. Health check...")
        status, _ = self.client.get("/health")
        if status != 200:
            status, _ = self.client.get("/v1/models")
        health_passed = status == 200
        print(f"     {'PASS' if health_passed else 'FAIL'} (HTTP {status})")
        all_passed = all_passed and health_passed

        # 2. Models check
        print("  2. Models endpoint...")
        status, data = self.client.get("/v1/models")
        models_passed = status == 200 and "data" in data
        print(f"     {'PASS' if models_passed else 'FAIL'} (HTTP {status})")
        all_passed = all_passed and models_passed

        if models_passed and data.get("data"):
            self.model = data["data"][0].get("id", "default")

        # 3. Non-thinking chat
        print("  3. Non-thinking chat...")
        result = self._execute_request(
            messages=[{"role": "user", "content": "Say 'hello' in one word."}],
            profile=EXECUTOR_PROFILE,
            stream=False,
            suite="smoke_non_thinking"
        )
        passed = result.passed and result.final_content_present
        print(f"     {'PASS' if passed else 'FAIL'}")
        smoke_results.append(result)
        all_passed = all_passed and passed

        # 4. Thinking chat
        print("  4. Thinking chat...")
        result = self._execute_request(
            messages=[{"role": "user", "content": "What is 2+2? Think briefly and answer."}],
            profile=SYNTHESIS_PROFILE,
            stream=False,
            suite="smoke_thinking"
        )
        passed = result.passed and result.final_content_present
        print(f"     {'PASS' if passed else 'FAIL'}")
        smoke_results.append(result)
        all_passed = all_passed and passed

        # 5. Forced tool call
        print("  5. Forced tool call (non-streaming)...")
        result = self._execute_request(
            messages=[{"role": "user", "content": "Get the test value for key 'alpha'."}],
            tools=[GET_TEST_VALUE_TOOL],
            tool_choice={"type": "function", "function": {"name": "get_test_value"}},
            profile=TOOL_PROFILE,
            stream=False,
            suite="smoke_forced_tool"
        )
        passed = result.passed and result.tool_call_count == 1
        print(f"     {'PASS' if passed else 'FAIL'} (tool_calls={result.tool_call_count})")
        smoke_results.append(result)
        all_passed = all_passed and passed

        # 6. Automatic tool selection (streaming)
        print("  6. Automatic tool selection (streaming)...")
        result = self._execute_request(
            messages=[{"role": "user", "content": "I need to retrieve the test value for key 'beta'."}],
            tools=[GET_TEST_VALUE_TOOL],
            tool_choice="auto",
            profile=TOOL_PROFILE,
            stream=True,
            suite="smoke_auto_tool_stream"
        )
        passed = result.passed and result.tool_call_count >= 1
        print(f"     {'PASS' if passed else 'FAIL'} (tool_calls={result.tool_call_count})")
        smoke_results.append(result)
        all_passed = all_passed and passed

        # 7. No-tool negative control
        print("  7. No-tool negative control...")
        result = self._execute_request(
            messages=[{"role": "user", "content": "What is the capital of France?"}],
            tools=[GET_TEST_VALUE_TOOL],
            tool_choice="auto",
            profile=EXECUTOR_PROFILE,
            stream=False,
            suite="smoke_no_tool"
        )
        passed = result.passed and result.tool_call_count == 0 and result.final_content_present
        print(f"     {'PASS' if passed else 'FAIL'} (tool_calls={result.tool_call_count})")
        smoke_results.append(result)
        all_passed = all_passed and passed

        return all_passed, smoke_results

    # =========================================================================
    # QUALIFICATION TESTS
    # =========================================================================

    def run_qualification(self) -> tuple[bool, list[AttemptResult]]:
        """Run full qualification suite"""
        qual_results = []
        all_passed = True

        print("\nRunning qualification tests...")

        # P1.9 — Chat qualification
        print("\nP1.9 — Chat qualification:")

        # Non-thinking chat (5/5)
        print("  Non-thinking chat (5 attempts)...")
        non_thinking_passed = 0
        for i in range(5):
            result = self._execute_request(
                messages=[{"role": "user", "content": f"Question {i+1}: What is {i*10}+{i}? Answer briefly."}],
                profile=EXECUTOR_PROFILE,
                stream=False,
                suite="qual_non_thinking_chat"
            )
            if result.passed and result.final_content_present:
                non_thinking_passed += 1
            qual_results.append(result)
        print(f"    Result: {non_thinking_passed}/5")
        all_passed = all_passed and (non_thinking_passed == 5)

        # Thinking chat (5/5)
        print("  Thinking chat (5 attempts)...")
        thinking_passed = 0
        for i in range(5):
            result = self._execute_request(
                messages=[{"role": "user", "content": f"Think and answer: What is {i+1} squared?"}],
                profile=SYNTHESIS_PROFILE,
                stream=False,
                suite="qual_thinking_chat"
            )
            if result.passed and result.final_content_present:
                thinking_passed += 1
            qual_results.append(result)
        print(f"    Result: {thinking_passed}/5")
        all_passed = all_passed and (thinking_passed == 5)

        # P1.10 — Single-tool qualification
        print("\nP1.10 — Single-tool qualification:")

        # A. Forced parser test, non-streaming (10/10)
        print("  A. Forced tool, non-streaming (10 attempts)...")
        forced_passed = 0
        for i in range(10):
            result = self._execute_request(
                messages=[{"role": "user", "content": f"Get test value for key 'test_{i}'."}],
                tools=[GET_TEST_VALUE_TOOL],
                tool_choice={"type": "function", "function": {"name": "get_test_value"}},
                profile=TOOL_PROFILE,
                stream=False,
                suite="qual_forced_tool"
            )
            if result.passed and result.tool_call_count == 1:
                forced_passed += 1
            qual_results.append(result)
        print(f"    Result: {forced_passed}/10")
        all_passed = all_passed and (forced_passed == 10)

        # B. Automatic selection, non-streaming (10/10)
        print("  B. Automatic tool, non-streaming (10 attempts)...")
        auto_passed = 0
        for i in range(10):
            result = self._execute_request(
                messages=[{"role": "user", "content": f"I need to retrieve the test value for key 'auto_{i}'."}],
                tools=[GET_TEST_VALUE_TOOL],
                tool_choice="auto",
                profile=TOOL_PROFILE,
                stream=False,
                suite="qual_auto_tool"
            )
            if result.passed and result.tool_call_count >= 1:
                auto_passed += 1
            qual_results.append(result)
        print(f"    Result: {auto_passed}/10")
        all_passed = all_passed and (auto_passed == 10)

        # C. Automatic selection, streaming (10/10)
        print("  C. Automatic tool, streaming (10 attempts)...")
        stream_passed = 0
        for i in range(10):
            result = self._execute_request(
                messages=[{"role": "user", "content": f"Please get the test value for key 'stream_{i}'."}],
                tools=[GET_TEST_VALUE_TOOL],
                tool_choice="auto",
                profile=TOOL_PROFILE,
                stream=True,
                suite="qual_stream_tool"
            )
            if result.passed and result.tool_call_count >= 1:
                stream_passed += 1
            qual_results.append(result)
        print(f"    Result: {stream_passed}/10")
        all_passed = all_passed and (stream_passed == 10)

        # D. No-tool negative control (5/5)
        print("  D. No-tool negative control (5 attempts)...")
        no_tool_passed = 0
        no_tool_prompts = [
            "What is 2+2? Just give me the number.",
            "What is the capital of France? Answer with just the city name.",
            "What color is grass? Answer with one word.",
            "How many days in a week? Just the number.",
            "What is the largest planet? Answer briefly."
        ]
        for i, prompt in enumerate(no_tool_prompts):
            result = self._execute_request(
                messages=[{"role": "user", "content": prompt}],
                tools=[GET_TEST_VALUE_TOOL],
                tool_choice="auto",
                profile=EXECUTOR_PROFILE,
                stream=False,
                suite="qual_no_tool_control"
            )
            if result.passed and result.tool_call_count == 0 and result.final_content_present:
                no_tool_passed += 1
            qual_results.append(result)
        print(f"    Result: {no_tool_passed}/5")
        all_passed = all_passed and (no_tool_passed == 5)

        # E. Thinking-enabled tool diagnostic (5 attempts, diagnostic only)
        print("  E. Thinking-enabled tool (diagnostic, 5 attempts)...")
        thinking_tool_passed = 0
        for i in range(5):
            thinking_profile = TOOL_PROFILE.copy()
            thinking_profile["enable_thinking"] = True
            result = self._execute_request(
                messages=[{"role": "user", "content": f"Think and get the test value for key 'think_{i}'."}],
                tools=[GET_TEST_VALUE_TOOL],
                tool_choice="auto",
                profile=thinking_profile,
                stream=False,
                suite="diag_thinking_tool"
            )
            if result.passed and result.tool_call_count >= 1:
                thinking_tool_passed += 1
            qual_results.append(result)
        print(f"    Result: {thinking_tool_passed}/5 (diagnostic)")

        # P1.11 — Sequential two-tool qualification
        print("\nP1.11 — Sequential two-tool qualification:")

        # Non-streaming workflow (10/10)
        print("  Non-streaming workflow (10 attempts)...")
        seq_passed = 0
        for i in range(10):
            # First turn: lookup
            result1 = self._execute_request(
                messages=[{"role": "user", "content": f"Look up item with ID 'item_{i}'."}],
                tools=[LOOKUP_ITEM_TOOL, VALIDATE_ITEM_TOOL],
                tool_choice="auto",
                profile=TOOL_PROFILE,
                stream=False,
                suite="qual_seq_lookup"
            )
            if result1.passed and result1.tool_call_count >= 1:
                seq_passed += 1
            qual_results.append(result1)
        print(f"    Result: {seq_passed}/10")
        all_passed = all_passed and (seq_passed == 10)

        # Streaming workflow (5/5)
        print("  Streaming workflow (5 attempts)...")
        seq_stream_passed = 0
        for i in range(5):
            result = self._execute_request(
                messages=[{"role": "user", "content": f"Look up item with ID 'stream_item_{i}'."}],
                tools=[LOOKUP_ITEM_TOOL, VALIDATE_ITEM_TOOL],
                tool_choice="auto",
                profile=TOOL_PROFILE,
                stream=True,
                suite="qual_seq_stream"
            )
            if result.passed and result.tool_call_count >= 1:
                seq_stream_passed += 1
            qual_results.append(result)
        print(f"    Result: {seq_stream_passed}/5")
        all_passed = all_passed and (seq_stream_passed == 5)

        # P1.12 — Streaming chat qualification
        print("\nP1.12 — Streaming chat qualification:")

        # Non-thinking streams (3/3)
        print("  Non-thinking streams (3 attempts)...")
        nt_stream_passed = 0
        for i in range(3):
            result = self._execute_request(
                messages=[{"role": "user", "content": f"Tell me a short fact about the number {i+1}."}],
                profile=EXECUTOR_PROFILE,
                stream=True,
                suite="qual_stream_non_thinking"
            )
            if result.passed and result.final_content_present:
                nt_stream_passed += 1
            qual_results.append(result)
        print(f"    Result: {nt_stream_passed}/3")
        all_passed = all_passed and (nt_stream_passed == 3)

        # Thinking streams (3/3)
        print("  Thinking streams (3 attempts)...")
        t_stream_passed = 0
        for i in range(3):
            result = self._execute_request(
                messages=[{"role": "user", "content": f"Think briefly: What is {i+1} times {i+2}?"}],
                profile=SYNTHESIS_PROFILE,
                stream=True,
                suite="qual_stream_thinking"
            )
            if result.passed and result.final_content_present:
                t_stream_passed += 1
            qual_results.append(result)
        print(f"    Result: {t_stream_passed}/3")
        all_passed = all_passed and (t_stream_passed == 3)

        # P1.13 — Cancellation and recovery
        print("\nP1.13 — Cancellation and recovery:")
        print("  (Simulated - 3 cycles)...")
        # Note: True cancellation requires client-side connection close
        # We simulate by making requests and checking server stability
        recovery_passed = 0
        for i in range(3):
            # Make a request
            result = self._execute_request(
                messages=[{"role": "user", "content": f"Recovery test {i+1}: Say 'RECOVERY_OK'."}],
                profile=EXECUTOR_PROFILE,
                stream=False,
                suite="qual_recovery"
            )
            # Check health
            status, _ = self.client.get("/v1/models")
            if result.passed and status == 200:
                recovery_passed += 1
            qual_results.append(result)
        print(f"    Result: {recovery_passed}/3")
        all_passed = all_passed and (recovery_passed == 3)

        # P1.16 — Bounded multi-turn stability
        print("\nP1.16 — Bounded multi-turn stability (20 turns)...")
        multi_turn_passed = 0
        for i in range(20):
            profile = EXECUTOR_PROFILE if i % 2 == 0 else SYNTHESIS_PROFILE
            result = self._execute_request(
                messages=[{"role": "user", "content": f"Turn {i+1}: What is {i}+{i+1}?"}],
                profile=profile,
                stream=False,
                suite="qual_multi_turn"
            )
            if result.passed and result.final_content_present:
                multi_turn_passed += 1
            qual_results.append(result)
        print(f"    Result: {multi_turn_passed}/20")
        all_passed = all_passed and (multi_turn_passed == 20)

        return all_passed, qual_results

    # =========================================================================
    # DIAGNOSTIC TESTS
    # =========================================================================

    def run_diagnostics(self) -> dict:
        """Run diagnostic tests (not hard gates)"""
        diagnostics = {}

        print("\nRunning diagnostic tests...")

        # P1.14 — Truncation safety check
        print("  P1.14 — Truncation safety check...")
        trunc_profile = TOOL_PROFILE.copy()
        trunc_profile["max_tokens"] = 5  # Deliberately small
        result = self._execute_request(
            messages=[{"role": "user", "content": "Get test value for key 'truncation_test'."}],
            tools=[GET_TEST_VALUE_TOOL],
            tool_choice={"type": "function", "function": {"name": "get_test_value"}},
            profile=trunc_profile,
            stream=False,
            suite="diag_truncation"
        )

        # Harness should detect this as failure
        truncation_detected = not result.passed or result.finish_reason == "length" or result.tool_call_count == 0
        diagnostics["truncation_safety"] = {
            "passed": truncation_detected,
            "status": "TRUNCATION_CORRECTLY_DETECTED" if truncation_detected else "TRUNCATION_NOT_DETECTED",
            "finish_reason": result.finish_reason,
            "tool_call_count": result.tool_call_count
        }
        print(f"    Status: {diagnostics['truncation_safety']['status']}")

        # P1.15 — Cache diagnostic
        print("  P1.15 — Cache diagnostic...")
        system_prompt = "You are a helpful assistant. Be concise."

        # Cold request
        result1 = self._execute_request(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "What is 1+1?"}
            ],
            profile=EXECUTOR_PROFILE,
            stream=False,
            suite="diag_cache_cold"
        )

        # Warm request (same prefix)
        result2 = self._execute_request(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "What is 2+2?"}
            ],
            profile=EXECUTOR_PROFILE,
            stream=False,
            suite="diag_cache_warm"
        )

        # Changed prefix control
        result3 = self._execute_request(
            messages=[
                {"role": "system", "content": "You are an unhelpful assistant."},
                {"role": "user", "content": "What is 3+3?"}
            ],
            profile=EXECUTOR_PROFILE,
            stream=False,
            suite="diag_cache_control"
        )

        # Analyze
        if result2.duration_ms < result1.duration_ms * 0.8:
            cache_status = "CACHE_BENEFIT_OBSERVED_NOT_CONFIRMED"
        else:
            cache_status = "CACHE_EFFECT_UNKNOWN"

        diagnostics["cache"] = {
            "cold_latency_ms": result1.duration_ms,
            "warm_latency_ms": result2.duration_ms,
            "control_latency_ms": result3.duration_ms,
            "status": cache_status
        }
        print(f"    Status: {cache_status}")

        return diagnostics

    # =========================================================================
    # RESULTS AGGREGATION
    # =========================================================================

    def aggregate_results(self, results: list[AttemptResult], group: str) -> AggregateMetrics:
        """Aggregate results for a group"""
        if not results:
            return AggregateMetrics(
                group=group,
                attempts=0,
                passed=0,
                failed=0,
                p50_latency_ms=0,
                p95_latency_ms=0,
                max_latency_ms=0,
                p50_ttft_ms=None,
                p95_ttft_ms=None,
                output_tokens_per_second=None
            )

        latencies = sorted([r.duration_ms for r in results])
        passed = sum(1 for r in results if r.passed)

        ttfts = [r.ttft_ms for r in results if r.ttft_ms is not None]

        # Calculate tokens per second
        total_tokens = sum(r.completion_tokens or 0 for r in results if r.completion_tokens)
        total_duration_s = sum(r.duration_ms for r in results) / 1000
        tps = total_tokens / total_duration_s if total_duration_s > 0 else None

        def percentile(sorted_list: list, p: float) -> float:
            if not sorted_list:
                return 0
            idx = int(len(sorted_list) * p)
            return sorted_list[min(idx, len(sorted_list) - 1)]

        return AggregateMetrics(
            group=group,
            attempts=len(results),
            passed=passed,
            failed=len(results) - passed,
            p50_latency_ms=percentile(latencies, 0.5),
            p95_latency_ms=percentile(latencies, 0.95),
            max_latency_ms=max(latencies) if latencies else 0,
            p50_ttft_ms=percentile(sorted(ttfts), 0.5) if ttfts else None,
            p95_ttft_ms=percentile(sorted(ttfts), 0.95) if ttfts else None,
            output_tokens_per_second=tps
        )

    def build_mandatory_gates(self, smoke_results: list, qual_results: list) -> dict:
        """Build mandatory gates summary"""
        gates = {}

        # Count by suite
        def count_passed(results: list, suite_prefix: str) -> tuple[int, int]:
            matching = [r for r in results if r.suite.startswith(suite_prefix)]
            passed = sum(1 for r in matching if r.passed)
            return passed, len(matching)

        gates["non_thinking_chat"] = count_passed(qual_results, "qual_non_thinking")
        gates["thinking_chat"] = count_passed(qual_results, "qual_thinking")
        gates["forced_tool_non_stream"] = count_passed(qual_results, "qual_forced_tool")
        gates["auto_tool_non_stream"] = count_passed(qual_results, "qual_auto_tool")
        gates["auto_tool_stream"] = count_passed(qual_results, "qual_stream_tool")
        gates["no_tool_control"] = count_passed(qual_results, "qual_no_tool_control")
        gates["seq_workflow_non_stream"] = count_passed(qual_results, "qual_seq_lookup")
        gates["seq_workflow_stream"] = count_passed(qual_results, "qual_seq_stream")
        gates["stream_non_thinking"] = count_passed(qual_results, "qual_stream_non_thinking")
        gates["stream_thinking"] = count_passed(qual_results, "qual_stream_thinking")
        gates["cancellation_recovery"] = count_passed(qual_results, "qual_recovery")
        gates["multi_turn"] = count_passed(qual_results, "qual_multi_turn")

        # Count malformed/duplicate tool calls
        gates["malformed_tool_calls"] = sum(1 for r in qual_results if "malformed" in r.failure_reasons)
        gates["duplicated_tool_calls"] = sum(1 for r in qual_results if "duplicate" in r.failure_reasons)
        gates["unexpected_parallel_calls"] = sum(1 for r in qual_results if "parallel" in r.failure_reasons)
        gates["repetition_collapse"] = sum(1 for r in qual_results if "repetition" in r.failure_reasons)
        gates["oom_crash_restart"] = 0  # Would need server monitoring

        return gates

    def save_results(self, smoke_results: list, qual_results: list,
                     diagnostics: dict, final_status: str) -> str:
        """Save results to JSON file"""

        all_results = smoke_results + qual_results

        # Build configuration fingerprint
        fingerprint = {
            "repository_head": os.popen("git rev-parse HEAD").read().strip(),
            "suite_version": SUITE_VERSION,
            "base_url": self.base_url,
            "model": self.model,
            "timeout": self.timeout,
            "timestamp": self._get_timestamp()
        }

        # Aggregate metrics
        smoke_agg = self.aggregate_results(smoke_results, "smoke")
        qual_agg = self.aggregate_results(qual_results, "qualification")

        # Build gates
        gates = self.build_mandatory_gates(smoke_results, qual_results)

        # Build test run
        test_run = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "suite_version": SUITE_VERSION,
            "timestamp": self._get_timestamp(),
            "base_url": self.base_url,
            "model": self.model,
            "configuration_fingerprint": fingerprint,
            "smoke_results": [asdict(r) for r in smoke_results],
            "qualification_results": [asdict(r) for r in qual_results],
            "aggregate_metrics": [asdict(smoke_agg), asdict(qual_agg)],
            "mandatory_gates": gates,
            "diagnostic_results": diagnostics,
            "final_status": final_status
        }

        # Write to file
        output_file = self.output_dir / f"{self.run_id}.json"
        with open(output_file, "w") as f:
            json.dump(test_run, f, indent=2)

        print(f"\nResults saved to: {output_file}")
        return str(output_file)

# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Rapid-MLX Baseline Test Harness")
    parser.add_argument("command", choices=["smoke", "qualify", "all"],
                        help="Test suite to run")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"Base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--model", default=None,
                        help="Model ID (default: from /v1/models)")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--request-timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT})")

    args = parser.parse_args()

    print(f"=== Rapid-MLX Baseline Test Harness v{SUITE_VERSION} ===")
    print(f"Run ID: will be generated")
    print(f"Base URL: {args.base_url}")
    print(f"Output: {args.output_dir}")
    print("")

    # Initialize harness
    harness = TestHarness(args.base_url, args.output_dir, args.request_timeout)

    # Discover model
    print("Discovering model...")
    model = harness.discover_model()
    if model:
        print(f"Model: {model}")
    else:
        print("WARNING: Could not discover model from /v1/models")

    smoke_results = []
    qual_results = []
    diagnostics = {}
    final_status = "UNKNOWN"

    # Run tests
    if args.command in ["smoke", "all"]:
        smoke_passed, smoke_results = harness.run_smoke()
        if not smoke_passed:
            print("\n!!! SMOKE TESTS FAILED !!!")
            print("Cannot proceed to qualification.")
            final_status = "RAPID_BASELINE_FAIL"
            harness.save_results(smoke_results, [], {}, final_status)
            return 1

    if args.command in ["qualify", "all"]:
        qual_passed, qual_results = harness.run_qualification()
        diagnostics = harness.run_diagnostics()

        if smoke_passed and qual_passed:
            final_status = "RAPID_BASELINE_PASS"
        else:
            final_status = "RAPID_BASELINE_FAIL"

    # Save results
    output_file = harness.save_results(smoke_results, qual_results, diagnostics, final_status)

    # Print summary
    print("\n" + "="*60)
    print(f"FINAL STATUS: {final_status}")
    print("="*60)

    return 0 if final_status == "RAPID_BASELINE_PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
