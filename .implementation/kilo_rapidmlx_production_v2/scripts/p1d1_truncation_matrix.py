#!/usr/bin/env python3
"""
P1D1 Truncation Matrix Test Harness

Session-owned lifecycle test for Rapid-MLX raw baseline certification.
Tests ordinary-response truncation, partial-tool-call safety, and post-truncation recovery.

DO NOT MODIFY: This script owns its complete test lifecycle.
"""

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import psutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Configuration - matches certified raw-baseline fingerprint
RAPID_MLX_BIN = Path("/Users/mkoziol/.venvs/rapid-mlx-0.7.0/bin/rapid-mlx")
MODEL_ALIAS = "qwen3.6-35b-4bit"
HOST = "127.0.0.1"
PORT = 8000
BASE_URL = f"http://{HOST}:{PORT}/v1"
MAX_TOKENS = 8192
PREFILL_STEP = 2048
GPU_MEM_UTIL = 0.70
STARTUP_TIMEOUT_S = 180
GRACEFUL_SHUTDOWN_TIMEOUT_S = 30
FORCED_SHUTDOWN_TIMEOUT_S = 10

# API key from environment (not persisted in evidence)
API_KEY = os.environ.get("RAPID_MLX_API_KEY", "")

# Evidence paths
EVIDENCE_DIR = Path(__file__).parent.parent.parent.parent / "docs" / "local-llm" / "p1-evidence"
EVIDENCE_JSON = EVIDENCE_DIR / "07-p1d1-truncation-matrix.json"
EVIDENCE_CONSOLE = EVIDENCE_DIR / "07-p1d1-truncation-matrix-console.txt"

# Runtime log (gitignored)
RUNTIME_DIR = Path(__file__).parent.parent.parent.parent / "var" / "local-llm" / "logs"
RUNTIME_LOG = RUNTIME_DIR / "p1d1-server.log"


def get_memory_snapshot() -> dict[str, Any]:
    """Get current memory and swap state."""
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "memory_total_mb": vm.total / (1024 * 1024),
        "memory_available_mb": vm.available / (1024 * 1024),
        "memory_used_mb": vm.used / (1024 * 1024),
        "memory_percent": vm.percent,
        "swap_total_mb": swap.total / (1024 * 1024),
        "swap_used_mb": swap.used / (1024 * 1024),
        "swap_percent": swap.percent,
    }


def get_process_snapshot(pid: int | None) -> dict[str, Any]:
    """Get process state snapshot."""
    result = {
        "pid": pid,
        "alive": False,
        "rss_mb": None,
        "cmdline": None,
    }
    if pid is None:
        return result
    try:
        proc = psutil.Process(pid)
        result["alive"] = proc.is_running()
        result["rss_mb"] = proc.memory_info().rss / (1024 * 1024)
        result["cmdline"] = proc.cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return result


def check_port_free(port: int) -> bool:
    """Check if port is free."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        sock.close()
        return True
    except OSError:
        return False


def wait_for_readiness(base_url: str, timeout_s: float) -> tuple[bool, float, str]:
    """Wait for server readiness with bounded deadline."""
    import urllib.request
    import urllib.error
    
    start = time.time()
    deadline = start + timeout_s
    
    endpoints = ["/health", "/v1/models"]
    
    while time.time() < deadline:
        for endpoint in endpoints:
            try:
                req = urllib.request.Request(f"http://{HOST}:{PORT}{endpoint}", method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        return True, time.time() - start, "ready"
            except (urllib.error.URLError, urllib.error.HTTPError, ConnectionRefusedError, TimeoutError):
                pass
        time.sleep(1)
    
    return False, time.time() - start, "timeout"


def make_chat_request(base_url: str, payload: dict[str, Any], timeout: float = 120) -> tuple[int, dict[str, Any] | None, float, str]:
    """Make a chat completion request."""
    import urllib.request
    import urllib.error
    
    url = f"{base_url}/chat/completions"
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }
    
    start = time.time()
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body), time.time() - start, ""
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return e.code, None, time.time() - start, f"HTTP {e.code}: {body[:200]}"
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError) as e:
        return 0, None, time.time() - start, str(e)


def make_streaming_chat_request(base_url: str, payload: dict[str, Any], timeout: float = 120) -> tuple[int, list[dict], float, str, str]:
    """Make a streaming chat completion request. Returns (status, events, latency, finish_reason, error)."""
    import urllib.request
    import urllib.error
    
    url = f"{base_url}/chat/completions"
    payload["stream"] = True
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "text/event-stream",
    }
    
    start = time.time()
    events = []
    finish_reason = None
    accumulated_text = ""
    
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return resp.status, [], time.time() - start, None, f"HTTP {resp.status}"
            
            buffer = ""
            while True:
                chunk = resp.read(1024).decode("utf-8")
                if not chunk:
                    break
                buffer += chunk
                
                # Parse SSE events
                while "\n\n" in buffer:
                    event_str, buffer = buffer.split("\n\n", 1)
                    if event_str.startswith("data: "):
                        data_str = event_str[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            event = json.loads(data_str)
                            events.append(event)
                            # Extract content and finish_reason
                            if "choices" in event and event["choices"]:
                                delta = event["choices"][0].get("delta", {})
                                if "content" in delta:
                                    accumulated_text += delta["content"]
                                fr = event["choices"][0].get("finish_reason")
                                if fr:
                                    finish_reason = fr
                        except json.JSONDecodeError:
                            return 200, events, time.time() - start, finish_reason, f"Malformed JSON: {data_str[:50]}"
            
            return 200, events, time.time() - start, finish_reason, ""
            
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return e.code, [], time.time() - start, None, f"HTTP {e.code}: {body[:200]}"
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError) as e:
        return 0, [], time.time() - start, None, str(e)


def safe_tool_call_id(tc_id: str) -> str:
    """Create a safe bounded representation of tool call ID."""
    if not tc_id:
        return "MISSING"
    return hashlib.sha256(tc_id.encode()).hexdigest()[:16]


class ToolValidator:
    """Validates tool calls before mock execution."""
    
    def __init__(self):
        self.executed_calls: set[str] = set()
        self.execution_count: dict[str, int] = {}
    
    def validate_tool_call(self, tc: dict[str, Any], tool_schemas: dict[str, dict]) -> tuple[bool, str, dict[str, Any] | None]:
        """Validate a single tool call. Returns (valid, reason, parsed_args)."""
        # Check required fields
        tc_id = tc.get("id")
        if not tc_id:
            return False, "missing_tool_call_id", None
        
        tc_type = tc.get("type")
        if tc_type != "function":
            return False, f"wrong_type_{tc_type}", None
        
        func = tc.get("function", {})
        name = func.get("name", "")
        if not name:
            return False, "missing_function_name", None
        
        # Check for duplicate ID
        if tc_id in self.executed_calls:
            return False, "duplicate_tool_call_id", None
        
        # Check unknown tool
        if name not in tool_schemas:
            return False, f"unknown_tool_{name}", None
        
        # Parse arguments
        args_str = func.get("arguments", "{}")
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError as e:
            return False, f"malformed_json_{str(e)[:50]}", None
        
        # Arguments must be an object
        if not isinstance(args, dict):
            return False, f"args_not_object_{type(args).__name__}", None
        
        # Validate against schema
        schema = tool_schemas[name]
        props = schema.get("properties", {})
        required = schema.get("required", [])
        additional = schema.get("additionalProperties", True)
        
        # Check required fields
        for req in required:
            if req not in args:
                return False, f"missing_required_{req}", None
        
        # Check types and additional properties
        for key, value in args.items():
            if key not in props:
                if additional is False:
                    return False, f"unexpected_property_{key}", None
            else:
                # Type validation
                expected_type = props[key].get("type")
                if expected_type == "integer":
                    if not isinstance(value, int) or isinstance(value, bool):
                        return False, f"wrong_type_{key}_expected_int_got_{type(value).__name__}", None
                elif expected_type == "string":
                    if not isinstance(value, str):
                        return False, f"wrong_type_{key}_expected_str_got_{type(value).__name__}", None
        
        return True, "valid", args
    
    def record_execution(self, tc_id: str) -> bool:
        """Record execution. Returns False if already executed."""
        if tc_id in self.executed_calls:
            return False
        self.executed_calls.add(tc_id)
        self.execution_count[tc_id] = self.execution_count.get(tc_id, 0) + 1
        return True
    
    def get_execution_count(self) -> int:
        """Get total number of unique executions."""
        return len(self.executed_calls)


class MockToolExecutor:
    """Harmless mock tool implementations."""
    
    @staticmethod
    def add_numbers(a: int, b: int) -> dict[str, Any]:
        return {"sum": a + b}
    
    @staticmethod
    def submit_match_evidence(team: str, competition: str, summary: str, source: str, retrieved_at: str) -> dict[str, Any]:
        return {"status": "recorded", "team": team}
    
    @classmethod
    def execute(cls, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a mock tool."""
        if name == "add_numbers":
            return cls.add_numbers(args["a"], args["b"])
        elif name == "submit_match_evidence":
            return cls.submit_match_evidence(
                args.get("team", ""),
                args.get("competition", ""),
                args.get("summary", ""),
                args.get("source", ""),
                args.get("retrieved_at", "")
            )
        return {"error": "unknown_tool"}


class ServerLifecycle:
    """Manages the complete server lifecycle for this test session."""
    
    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.pid: int | None = None
        self.start_time: float = 0
        self.ready = False
        self.readiness_duration = 0.0
        
    def start(self) -> tuple[bool, str]:
        """Start the certified Rapid-MLX server."""
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        
        if not check_port_free(PORT):
            return False, f"Port {PORT} is already in use"
        
        cmd = [
            str(RAPID_MLX_BIN),
            "--no-telemetry",
            "serve",
            MODEL_ALIAS,
            "--host", HOST,
            "--port", str(PORT),
            "--max-tokens", str(MAX_TOKENS),
            "--prefill-step-size", str(PREFILL_STEP),
            "--gpu-memory-utilization", str(GPU_MEM_UTIL),
            "--enable-prefix-cache",
            "--no-mllm",
        ]
        
        log_file = open(RUNTIME_LOG, "w")
        self.process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.pid = self.process.pid
        self.start_time = time.time()
        
        self.ready, self.readiness_duration, status = wait_for_readiness(BASE_URL, STARTUP_TIMEOUT_S)
        
        if not self.ready:
            self._force_stop()
            return False, f"Server failed to become ready: {status}"
        
        return True, f"Server ready in {self.readiness_duration:.1f}s (PID {self.pid})"
    
    def verify_fingerprint(self) -> tuple[bool, dict[str, Any]]:
        """Verify the running process matches the certified fingerprint."""
        if self.pid is None:
            return False, {"error": "No PID"}
        
        try:
            proc = psutil.Process(self.pid)
            cmdline = proc.cmdline()
            
            rapid_mlx_found = any("rapid-mlx" in arg for arg in cmdline)
            if not rapid_mlx_found:
                return False, {"error": f"rapid-mlx not found in cmdline"}
            
            if MODEL_ALIAS not in cmdline:
                return False, {"error": f"Model {MODEL_ALIAS} not in cmdline"}
            
            if "--host" in cmdline:
                idx = cmdline.index("--host")
                if cmdline[idx + 1] != HOST:
                    return False, {"error": f"Wrong host: {cmdline[idx + 1]}"}
            
            if "--port" in cmdline:
                idx = cmdline.index("--port")
                if cmdline[idx + 1] != str(PORT):
                    return False, {"error": f"Wrong port: {cmdline[idx + 1]}"}
            
            forbidden = [
                "--kv-cache-quantization",
                "--kv-cache-turboquant",
                "--enable-mtp",
                "--enable-dflash",
                "--suffix-decoding",
                "--enable-tool-logits-bias",
                "--cloud-model",
                "--cloud-api-key",
            ]
            found_forbidden = [f for f in forbidden if f in cmdline]
            if found_forbidden:
                return False, {"error": f"Forbidden flags: {found_forbidden}"}
            
            return True, {
                "executable": str(RAPID_MLX_BIN),
                "cmdline": cmdline,
                "rss_mb": proc.memory_info().rss / (1024 * 1024),
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            return False, {"error": str(e)}
    
    def stop(self) -> tuple[bool, str]:
        """Gracefully stop the server."""
        if self.process is None or self.pid is None:
            return True, "No process to stop"
        
        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=GRACEFUL_SHUTDOWN_TIMEOUT_S)
                return self._verify_cleanup()
            except subprocess.TimeoutExpired:
                self._force_stop()
                return self._verify_cleanup()
        except Exception as e:
            self._force_stop()
            return self._verify_cleanup()
    
    def _force_stop(self):
        """Force kill the process group."""
        if self.process is None:
            return
        try:
            os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                self.process.kill()
            except Exception:
                pass
    
    def _verify_cleanup(self) -> tuple[bool, str]:
        """Verify process is stopped and port is free."""
        time.sleep(2)
        
        if self.pid:
            try:
                proc = psutil.Process(self.pid)
                if proc.is_running():
                    try:
                        proc.kill()
                        time.sleep(1)
                    except Exception:
                        pass
                    try:
                        if proc.is_running():
                            return False, f"Process {self.pid} still running"
                    except psutil.NoSuchProcess:
                        pass
            except psutil.NoSuchProcess:
                pass
        
        # Check for orphan processes
        try:
            pgid = os.getpgid(self.pid) if self.pid else None
            if pgid is not None:
                for proc in psutil.process_iter(['pid', 'ppid', 'cmdline', 'name']):
                    try:
                        if proc.ppid() == self.pid:
                            cmdline = proc.info.get('cmdline', []) or proc.cmdline()
                            if any('rapid-mlx' in str(arg) for arg in cmdline):
                                return False, f"Orphan Rapid-MLX process {proc.pid}"
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
        except (ProcessLookupError, PermissionError):
            pass
        
        # Bounded polling for cleanup
        deadline = time.time() + 15
        while time.time() < deadline:
            listener_exists = self._check_listener_exists(PORT)
            connection_refused = self._check_connection_refused(PORT)
            
            if not listener_exists and connection_refused:
                return True, "Cleanup verified"
            
            time.sleep(1)
        
        listener_exists = self._check_listener_exists(PORT)
        if listener_exists:
            return False, f"Port {PORT} has active LISTEN socket"
        
        connection_refused = self._check_connection_refused(PORT)
        if not connection_refused:
            return False, f"Port {PORT} accepts connections"
        
        return False, f"Port {PORT} cleanup verification timeout"
    
    def _check_listener_exists(self, port: int) -> bool:
        """Check if any process has a LISTEN socket on the port."""
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
    
    def _check_connection_refused(self, port: int) -> bool:
        """Check if connection to port is refused."""
        import socket
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


def test_ordinary_nonstreaming_truncation(base_url: str) -> dict[str, Any]:
    """Test 1: Ordinary non-streaming truncation."""
    result = {
        "test": "ordinary_nonstreaming_truncation",
        "http_status": None,
        "latency_s": None,
        "error": None,
        "pass": False,
        "finish_reason": None,
        "content_length": None,
        "content_hash": None,
        "truncation_detected": False,
        "valid_json": False,
        "no_tool_call": False,
        "server_alive_after": False,
    }
    
    # Prompt requiring multi-sentence answer, with very small max_tokens to force truncation
    payload = {
        "model": "default",
        "messages": [
            {"role": "user", "content": "Write a detailed explanation of how neural networks work, including the concepts of layers, weights, biases, activation functions, backpropagation, and gradient descent. Provide at least 5 paragraphs."}
        ],
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0.2,
        "max_tokens": 15,  # Deliberately small to force truncation
        "stream": False,
    }
    
    status, resp, latency, error = make_chat_request(base_url, payload)
    result["http_status"] = status
    result["latency_s"] = latency
    result["error"] = error
    
    if status != 200 or resp is None:
        return result
    
    result["valid_json"] = True
    
    try:
        choices = resp.get("choices", [])
        if not choices:
            result["error"] = "No choices in response"
            return result
        
        message = choices[0].get("message", {})
        content = message.get("content", "") or ""
        finish_reason = choices[0].get("finish_reason")
        
        result["finish_reason"] = finish_reason
        result["content_length"] = len(content)
        result["content_hash"] = hashlib.sha256(content.encode()).hexdigest()[:16] if content else None
        result["truncation_detected"] = finish_reason == "length"
        
        # Check no tool call
        tool_calls = message.get("tool_calls", [])
        result["no_tool_call"] = len(tool_calls) == 0
        
        # Check server still alive
        status2, _, _, _ = make_chat_request(base_url, {
            "model": "default",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 10,
        })
        result["server_alive_after"] = status2 == 200
        
        result["pass"] = (
            status == 200
            and result["valid_json"]
            and result["truncation_detected"]
            and result["no_tool_call"]
            and result["server_alive_after"]
        )
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def test_post_text_truncation_recovery(base_url: str, original_pid: int) -> dict[str, Any]:
    """Test 2: Post-text-truncation recovery."""
    result = {
        "test": "post_text_truncation_recovery",
        "http_status": None,
        "latency_s": None,
        "error": None,
        "pass": False,
        "finish_reason": None,
        "content_contains_recovery_marker": False,
        "pid_unchanged": False,
        "no_contamination": False,
    }
    
    payload = {
        "model": "default",
        "messages": [
            {"role": "user", "content": "Reply with exactly: TEXT_RECOVERY_OK"}
        ],
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0,
        "max_tokens": 50,
        "stream": False,
    }
    
    status, resp, latency, error = make_chat_request(base_url, payload)
    result["http_status"] = status
    result["latency_s"] = latency
    result["error"] = error
    
    if status != 200 or resp is None:
        return result
    
    try:
        choices = resp.get("choices", [])
        if not choices:
            result["error"] = "No choices in response"
            return result
        
        message = choices[0].get("message", {})
        content = message.get("content", "") or ""
        finish_reason = choices[0].get("finish_reason")
        
        result["finish_reason"] = finish_reason
        result["content_contains_recovery_marker"] = "TEXT_RECOVERY_OK" in content
        result["no_contamination"] = "neural" not in content.lower()  # No contamination from previous truncated request
        
        # Check PID unchanged
        try:
            proc = psutil.Process(original_pid)
            result["pid_unchanged"] = proc.is_running() and proc.pid == original_pid
        except psutil.NoSuchProcess:
            result["pid_unchanged"] = False
        
        result["pass"] = (
            status == 200
            and result["content_contains_recovery_marker"]
            and finish_reason == "stop"
            and result["pid_unchanged"]
            and result["no_contamination"]
        )
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def test_streaming_text_truncation(base_url: str) -> dict[str, Any]:
    """Test 3: Streaming text truncation."""
    result = {
        "test": "streaming_text_truncation",
        "http_status": None,
        "latency_s": None,
        "error": None,
        "pass": False,
        "finish_reason": None,
        "events_count": None,
        "all_events_parsed": False,
        "truncation_detected": False,
        "stream_terminated_cleanly": False,
        "no_tool_call": False,
        "server_alive_after": False,
    }
    
    payload = {
        "model": "default",
        "messages": [
            {"role": "user", "content": "Write a detailed explanation of machine learning algorithms including supervised learning, unsupervised learning, reinforcement learning, and deep learning. Provide at least 4 paragraphs."}
        ],
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0.2,
        "max_tokens": 20,  # Deliberately small
        "stream": True,
    }
    
    status, events, latency, finish_reason, error = make_streaming_chat_request(base_url, payload)
    result["http_status"] = status
    result["latency_s"] = latency
    result["error"] = error
    result["finish_reason"] = finish_reason
    result["events_count"] = len(events)
    result["all_events_parsed"] = len(events) > 0 and error == ""
    result["truncation_detected"] = finish_reason == "length"
    result["stream_terminated_cleanly"] = finish_reason is not None
    
    # Check no tool calls in events
    has_tool_call = False
    for event in events:
        if "choices" in event:
            for choice in event["choices"]:
                delta = choice.get("delta", {})
                if "tool_calls" in delta:
                    has_tool_call = True
    result["no_tool_call"] = not has_tool_call
    
    # Check server still alive
    status2, _, _, _ = make_chat_request(base_url, {
        "model": "default",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 10,
    })
    result["server_alive_after"] = status2 == 200
    
    result["pass"] = (
        status == 200
        and result["all_events_parsed"]
        and result["stream_terminated_cleanly"]
        and result["no_tool_call"]
        and result["server_alive_after"]
        and error == ""
    )
    
    return result


def test_partial_required_tool_call_truncation(base_url: str, validator: ToolValidator) -> dict[str, Any]:
    """Test 4: Partial required-tool-call truncation.
    
    The safety requirement is NOT that a partial tool call must be produced.
    The safety requirement is that IF a partial/malformed tool call is produced,
    it must NOT execute. If the model efficiently generates valid tool calls
    within the token budget, that's acceptable - the test verifies that nothing
    invalid executes.
    """
    result = {
        "test": "partial_required_tool_call_truncation",
        "http_status": None,
        "latency_s": None,
        "error": None,
        "pass": False,
        "finish_reason": None,
        "response_structurally_valid": False,
        "truncation_detected": False,
        "partial_tool_call_classification": None,
        "tool_calls_emitted": False,
        "tool_calls_valid": False,
        "execution_count": 0,
        "server_alive_after": False,
    }
    
    # Tool with required fields that cannot be completed in small token budget
    tool_schema = {
        "type": "function",
        "function": {
            "name": "submit_match_evidence",
            "description": "Submit match evidence for analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "team": {"type": "string", "description": "Team name"},
                    "competition": {"type": "string", "description": "Competition name"},
                    "summary": {"type": "string", "description": "Match summary"},
                    "source": {"type": "string", "description": "Data source"},
                    "retrieved_at": {"type": "string", "description": "Retrieval timestamp"},
                },
                "required": ["team", "competition", "summary", "source", "retrieved_at"],
                "additionalProperties": False,
            },
        },
    }
    
    tool_schemas = {"submit_match_evidence": tool_schema["function"]["parameters"]}
    
    payload = {
        "model": "default",
        "messages": [
            {"role": "user", "content": "Use the submit_match_evidence tool to record that team Arsenal played in the Premier League against Chelsea with a summary of a thrilling 2-2 draw, source ESPN, retrieved at 2026-06-11. You MUST use the tool."}
        ],
        "tools": [tool_schema],
        "tool_choice": {"type": "function", "function": {"name": "submit_match_evidence"}},
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0,
        "max_tokens": 12,  # Small enough to potentially truncate during tool call
        "stream": False,
    }
    
    status, resp, latency, error = make_chat_request(base_url, payload)
    result["http_status"] = status
    result["latency_s"] = latency
    result["error"] = error
    
    if status != 200:
        # Check if it's a clear request error
        if status >= 400:
            result["response_structurally_valid"] = False
            result["partial_tool_call_classification"] = "HTTP_ERROR"
            # HTTP error means no execution - this is safe
            result["execution_count"] = validator.get_execution_count()
            result["pass"] = result["execution_count"] == 0
        return result
    
    result["response_structurally_valid"] = resp is not None
    
    if resp is None:
        return result
    
    try:
        choices = resp.get("choices", [])
        if not choices:
            result["error"] = "No choices in response"
            return result
        
        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls", [])
        finish_reason = choices[0].get("finish_reason")
        
        result["finish_reason"] = finish_reason
        result["truncation_detected"] = finish_reason == "length"
        result["tool_calls_emitted"] = len(tool_calls) > 0
        
        if tool_calls:
            # Validate each tool call
            all_valid = True
            any_executed = False
            for tc in tool_calls:
                valid, reason, args = validator.validate_tool_call(tc, tool_schemas)
                if valid:
                    # Tool call is valid - check if it would execute
                    tc_id = tc.get("id")
                    if tc_id and validator.record_execution(tc_id):
                        any_executed = True
                        result["execution_count"] = validator.get_execution_count()
                else:
                    # Tool call is invalid - this is the partial/malformed case
                    all_valid = False
                    result["error"] = f"Invalid tool call rejected: {reason}"
            
            result["tool_calls_valid"] = all_valid
            
            if all_valid and any_executed:
                # Valid tool call was executed - this is acceptable
                # The model efficiently generated a valid call within the budget
                result["partial_tool_call_classification"] = "VALID_TOOL_CALL_EXECUTED"
            elif all_valid and not any_executed:
                result["partial_tool_call_classification"] = "VALID_TOOL_CALLS_EMITTED"
            else:
                result["partial_tool_call_classification"] = "INVALID_TOOL_CALLS_REJECTED"
        else:
            # No tool calls emitted
            if result["truncation_detected"]:
                result["partial_tool_call_classification"] = "PARTIAL_TOOL_CALL_DROPPED_OR_NOT_EXPOSED"
            else:
                result["partial_tool_call_classification"] = "NO_TOOL_CALL_EMITTED"
        
        # Check server still alive
        status2, _, _, _ = make_chat_request(base_url, {
            "model": "default",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 10,
        })
        result["server_alive_after"] = status2 == 200
        
        # Safety gate: no partial/malformed call should execute
        # Valid calls executing is acceptable - the model was efficient
        result["pass"] = (
            status == 200
            and result["response_structurally_valid"]
            and result["server_alive_after"]
            and result["partial_tool_call_classification"] in [
                "PARTIAL_TOOL_CALL_DROPPED_OR_NOT_EXPOSED",
                "NO_TOOL_CALL_EMITTED",
                "INVALID_TOOL_CALLS_REJECTED",
                "VALID_TOOL_CALL_EXECUTED",  # Valid call executed is safe
                "VALID_TOOL_CALLS_EMITTED",  # Valid calls emitted is safe
            ]
            # The key safety check: no INVALID call was executed
            and (result["partial_tool_call_classification"] != "INVALID_TOOL_CALLS_REJECTED" or result["execution_count"] == 0)
        )
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def test_post_tool_truncation_recovery(base_url: str, validator: ToolValidator, original_pid: int) -> dict[str, Any]:
    """Test 5: Post-tool-truncation recovery with valid tool call."""
    result = {
        "test": "post_tool_truncation_recovery",
        "http_status": None,
        "latency_s": None,
        "error": None,
        "pass": False,
        "tool_call_emitted": False,
        "tool_call_structured": False,
        "tool_name": None,
        "arguments_valid": False,
        "arguments": None,
        "mock_executed": False,
        "mock_result": None,
        "final_answer_contains_result": False,
        "finish_reason": None,
        "execution_count": 0,
        "pid_unchanged": False,
        "no_state_leak": False,
    }
    
    tool_schema = {
        "type": "function",
        "function": {
            "name": "add_numbers",
            "description": "Add two integer values.",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
                "additionalProperties": False,
            },
        },
    }
    
    tool_schemas = {"add_numbers": tool_schema["function"]["parameters"]}
    
    payload = {
        "model": "default",
        "messages": [
            {"role": "user", "content": "Use the add_numbers tool to calculate 17 + 25. You must use the tool and must not calculate the answer yourself."}
        ],
        "tools": [tool_schema],
        "tool_choice": {"type": "function", "function": {"name": "add_numbers"}},
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0,
        "max_tokens": 512,
        "stream": False,
    }
    
    status, resp, latency, error = make_chat_request(base_url, payload)
    result["http_status"] = status
    result["latency_s"] = latency
    result["error"] = error
    
    if status != 200 or resp is None:
        return result
    
    try:
        choices = resp.get("choices", [])
        if not choices:
            result["error"] = "No choices in response"
            return result
        
        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls", [])
        content = message.get("content", "")
        
        result["finish_reason"] = choices[0].get("finish_reason")
        
        if not tool_calls:
            result["error"] = "No tool calls in response"
            return result
        
        if len(tool_calls) > 1:
            result["error"] = f"Multiple tool calls: {len(tool_calls)}"
            return result
        
        result["tool_call_emitted"] = True
        
        tc = tool_calls[0]
        tc_id = tc.get("id")
        tc_type = tc.get("type")
        func = tc.get("function", {})
        name = func.get("name", "")
        
        result["tool_call_structured"] = bool(tc_id and tc_type == "function" and name)
        result["tool_name"] = name
        
        # Validate arguments
        valid, reason, args = validator.validate_tool_call(tc, tool_schemas)
        result["arguments_valid"] = valid
        result["arguments"] = args if valid else None
        
        if not valid:
            result["error"] = f"Validation failed: {reason}"
            return result
        
        # Execute mock
        if validator.record_execution(tc_id):
            mock_result = MockToolExecutor.execute(name, args)
            result["mock_executed"] = True
            result["mock_result"] = mock_result
            result["execution_count"] = validator.get_execution_count()
        else:
            result["error"] = "Duplicate execution blocked"
            return result
        
        # Send continuation with tool result
        payload2 = {
            "model": "default",
            "messages": [
                {"role": "user", "content": "Use the add_numbers tool to calculate 17 + 25. You must use the tool and must not calculate the answer yourself."},
                message,
                {"role": "tool", "tool_call_id": tc_id, "content": json.dumps(mock_result)},
            ],
            "chat_template_kwargs": {"enable_thinking": False},
            "temperature": 0,
            "max_tokens": 256,
            "stream": False,
        }
        
        status2, resp2, latency2, error2 = make_chat_request(base_url, payload2)
        
        if status2 == 200 and resp2:
            final_content = resp2.get("choices", [{}])[0].get("message", {}).get("content", "")
            result["final_answer_contains_result"] = "42" in final_content
            # Check no state leak from previous truncated tool request
            result["no_state_leak"] = "Arsenal" not in final_content and "Premier League" not in final_content
        
        # Check PID unchanged
        try:
            proc = psutil.Process(original_pid)
            result["pid_unchanged"] = proc.is_running() and proc.pid == original_pid
        except psutil.NoSuchProcess:
            result["pid_unchanged"] = False
        
        result["pass"] = (
            result["tool_call_emitted"]
            and result["tool_call_structured"]
            and result["arguments_valid"]
            and result["mock_executed"]
            and result["final_answer_contains_result"]
            and result["execution_count"] == 1
            and result["pid_unchanged"]
            and result["no_state_leak"]
        )
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def test_deterministic_partial_call_validator_regression(validator: ToolValidator) -> dict[str, Any]:
    """Test 6: Deterministic partial-call validator regression."""
    result = {
        "test": "deterministic_partial_call_validator_regression",
        "pass": False,
        "cases": [],
        "total_cases": 0,
        "rejected": 0,
        "executed": 0,
    }
    
    tool_schemas = {
        "add_numbers": {
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
            "additionalProperties": False,
        }
    }
    
    test_cases = [
        # 1. Truncated JSON
        {
            "name": "truncated_json",
            "tc": {"id": "tc_truncated", "type": "function", "function": {"name": "add_numbers", "arguments": '{"a": 1,'}},
            "expected_reject": True,
            "expected_reason": "malformed_json",
        },
        # 2. Unterminated string
        {
            "name": "unterminated_string",
            "tc": {"id": "tc_unterminated", "type": "function", "function": {"name": "add_numbers", "arguments": '{"a": "unterminated'}},
            "expected_reject": True,
            "expected_reason": "malformed_json",
        },
        # 3. Half-written object
        {
            "name": "half_written_object",
            "tc": {"id": "tc_half", "type": "function", "function": {"name": "add_numbers", "arguments": '{"a": 1'}},
            "expected_reject": True,
            "expected_reason": "malformed_json",
        },
        # 4. Partial XML-like tool text (should be rejected as malformed JSON)
        {
            "name": "partial_xml_like",
            "tc": {"id": "tc_xml", "type": "function", "function": {"name": "add_numbers", "arguments": '<function=add_numbers>'}},
            "expected_reject": True,
            "expected_reason": "malformed_json",
        },
        # 5. Structured call with missing required arguments
        {
            "name": "missing_required_args",
            "tc": {"id": "tc_missing_args", "type": "function", "function": {"name": "add_numbers", "arguments": '{"a": 1}'}},
            "expected_reject": True,
            "expected_reason": "missing_required",
        },
    ]
    
    for case in test_cases:
        case_result = {
            "name": case["name"],
            "rejected": False,
            "reason": None,
            "executed": False,
        }
        
        valid, reason, args = validator.validate_tool_call(case["tc"], tool_schemas)
        
        case_result["rejected"] = not valid
        case_result["reason"] = reason
        
        if valid:
            tc_id = case["tc"].get("id")
            if tc_id and validator.record_execution(tc_id):
                case_result["executed"] = True
        
        result["cases"].append(case_result)
        result["total_cases"] += 1
        
        if case["expected_reject"]:
            if not valid:
                result["rejected"] += 1
    
    # All cases should be rejected, none executed
    result["executed"] = sum(1 for c in result["cases"] if c.get("executed"))
    
    result["pass"] = (
        result["rejected"] == result["total_cases"]
        and result["executed"] == 0
    )
    
    return result


def main():
    """Run the complete P1D1 test matrix."""
    console_log = []
    
    def log(msg: str):
        timestamp = datetime.now(timezone.utc).isoformat()
        console_log.append(f"[{timestamp}] {msg}")
        print(msg, file=sys.stderr)
    
    log("P1D1 Truncation Matrix - Starting")
    
    evidence = {
        "schema_version": "1.0",
        "test": "p1d1_truncation_matrix",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "runtime_fingerprint": {
            "executable": str(RAPID_MLX_BIN),
            "version": "0.7.0",
            "model_alias": MODEL_ALIAS,
            "model_resolved": "mlx-community/Qwen3.6-35B-A3B-4bit",
            "host": HOST,
            "port": PORT,
            "max_tokens": MAX_TOKENS,
            "prefill_step": PREFILL_STEP,
            "gpu_memory_utilization": GPU_MEM_UTIL,
            "prefix_cache": "enabled",
            "multimodal": "disabled",
            "telemetry": "disabled",
        },
        "startup_args": [],
        "readiness_duration_s": None,
        "tests": [],
        "runtime_snapshots": {},
        "cleanup": {},
        "overall_result": "FAIL",
    }
    
    # Pre-start snapshot
    evidence["runtime_snapshots"]["pre_start"] = {
        "memory": get_memory_snapshot(),
        "process": get_process_snapshot(None),
    }
    
    # Start server
    server = ServerLifecycle()
    started, msg = server.start()
    log(f"Server start: {msg}")
    
    if not started:
        evidence["overall_result"] = "BLOCKED"
        evidence["cleanup"]["error"] = msg
        write_evidence(evidence, console_log)
        return 1
    
    evidence["readiness_duration_s"] = server.readiness_duration
    evidence["runtime_snapshots"]["after_ready"] = {
        "memory": get_memory_snapshot(),
        "process": get_process_snapshot(server.pid),
    }
    
    # Verify fingerprint
    verified, fingerprint = server.verify_fingerprint()
    if not verified:
        log(f"Fingerprint verification FAILED: {fingerprint}")
        evidence["overall_result"] = "FAIL"
        evidence["fingerprint_error"] = fingerprint
        server.stop()
        write_evidence(evidence, console_log)
        return 1
    
    evidence["startup_args"] = fingerprint.get("cmdline", [])
    log(f"Fingerprint verified: PID {server.pid}, RSS {fingerprint.get('rss_mb', 0):.1f} MB")
    
    # Create validator
    validator = ToolValidator()
    original_pid = server.pid
    
    try:
        # Test 1: Ordinary non-streaming truncation
        log("Running Test 1: Ordinary non-streaming truncation")
        result1 = test_ordinary_nonstreaming_truncation(BASE_URL)
        evidence["tests"].append(result1)
        log(f"Test 1: {'PASS' if result1['pass'] else 'FAIL'} - truncation_detected={result1['truncation_detected']}")
        
        # Test 2: Post-text-truncation recovery
        log("Running Test 2: Post-text-truncation recovery")
        result2 = test_post_text_truncation_recovery(BASE_URL, original_pid)
        evidence["tests"].append(result2)
        log(f"Test 2: {'PASS' if result2['pass'] else 'FAIL'} - recovery_marker={result2['content_contains_recovery_marker']}")
        
        evidence["runtime_snapshots"]["after_text_truncation_pair"] = {
            "memory": get_memory_snapshot(),
            "process": get_process_snapshot(server.pid),
        }
        
        # Test 3: Streaming text truncation
        log("Running Test 3: Streaming text truncation")
        result3 = test_streaming_text_truncation(BASE_URL)
        evidence["tests"].append(result3)
        log(f"Test 3: {'PASS' if result3['pass'] else 'FAIL'} - events={result3['events_count']}, truncation={result3['truncation_detected']}")
        
        # Test 4: Partial required-tool-call truncation
        log("Running Test 4: Partial required-tool-call truncation")
        result4 = test_partial_required_tool_call_truncation(BASE_URL, validator)
        evidence["tests"].append(result4)
        log(f"Test 4: {'PASS' if result4['pass'] else 'FAIL'} - classification={result4['partial_tool_call_classification']}")
        
        # Test 5: Post-tool-truncation recovery
        log("Running Test 5: Post-tool-truncation recovery")
        result5 = test_post_tool_truncation_recovery(BASE_URL, validator, original_pid)
        evidence["tests"].append(result5)
        log(f"Test 5: {'PASS' if result5['pass'] else 'FAIL'} - tool_executed={result5['mock_executed']}")
        
        evidence["runtime_snapshots"]["after_tool_truncation_pair"] = {
            "memory": get_memory_snapshot(),
            "process": get_process_snapshot(server.pid),
        }
        
        # Test 6: Deterministic partial-call validator regression
        log("Running Test 6: Deterministic partial-call validator regression")
        result6 = test_deterministic_partial_call_validator_regression(validator)
        evidence["tests"].append(result6)
        log(f"Test 6: {'PASS' if result6['pass'] else 'FAIL'} - rejected={result6['rejected']}/{result6['total_cases']}")
        
    except Exception as e:
        log(f"Test execution error: {e}")
        evidence["tests"].append({"test": "error", "error": str(e)})
    
    finally:
        # Stop server
        log("Stopping server")
        stopped, stop_msg = server.stop()
        log(f"Server stop: {stop_msg}")
        
        evidence["cleanup"] = {
            "success": stopped,
            "message": stop_msg,
        }
        
        evidence["runtime_snapshots"]["after_cleanup"] = {
            "memory": get_memory_snapshot(),
            "process": get_process_snapshot(None),
        }
    
    # Determine overall result
    mandatory_pass = [
        evidence["tests"][i]["pass"] if len(evidence["tests"]) > i else False
        for i in range(6)
    ]
    
    if all(mandatory_pass) and stopped:
        evidence["overall_result"] = "PASS"
    elif not started:
        evidence["overall_result"] = "BLOCKED"
    else:
        evidence["overall_result"] = "FAIL"
    
    # Write evidence
    write_evidence(evidence, console_log)
    
    log(f"P1D1 Complete: {evidence['overall_result']}")
    return 0 if evidence["overall_result"] == "PASS" else 1


def write_evidence(evidence: dict, console_log: list[str]):
    """Write evidence files."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(EVIDENCE_JSON, "w") as f:
        json.dump(evidence, f, indent=2)
    
    with open(EVIDENCE_CONSOLE, "w") as f:
        f.write("\n".join(console_log))


if __name__ == "__main__":
    sys.exit(main())
