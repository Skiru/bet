#!/usr/bin/env python3
"""
P1C Tool Calling Matrix Test Harness

Session-owned lifecycle test for Rapid-MLX raw baseline certification.
Tests structured tool calling: single required tool, sequential three-tool chain,
and deterministic invalid-call rejection.

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

# Configuration
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
EVIDENCE_JSON = EVIDENCE_DIR / "06-p1c-tool-calling-matrix.json"
EVIDENCE_CONSOLE = EVIDENCE_DIR / "06-p1c-tool-calling-matrix-console.txt"

# Runtime log (gitignored)
RUNTIME_DIR = Path(__file__).parent.parent.parent.parent / "var" / "local-llm" / "logs"
RUNTIME_LOG = RUNTIME_DIR / "p1c-server.log"


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


def make_chat_request(base_url: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | None, float, str]:
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
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body), time.time() - start, ""
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return e.code, None, time.time() - start, f"HTTP {e.code}: {body[:200]}"
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError) as e:
        return 0, None, time.time() - start, str(e)


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
    def get_seed(name: str) -> dict[str, Any]:
        if name == "alpha":
            return {"value": 7}
        return {"value": 0, "error": "unknown_seed"}
    
    @staticmethod
    def multiply(value: int, factor: int) -> dict[str, Any]:
        return {"value": value * factor}
    
    @staticmethod
    def format_result(value: int, label: str) -> dict[str, Any]:
        return {"formatted": f"{label}={value}"}
    
    @classmethod
    def execute(cls, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a mock tool."""
        if name == "add_numbers":
            return cls.add_numbers(args["a"], args["b"])
        elif name == "get_seed":
            return cls.get_seed(args["name"])
        elif name == "multiply":
            return cls.multiply(args["value"], args["factor"])
        elif name == "format_result":
            return cls.format_result(args["value"], args["label"])
        return {"error": "unknown_tool"}


class ServerLifecycle:
    """Manages the complete server lifecycle for this test session."""
    
    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.pid: int | None = None
        self.start_time: float = 0
        self.ready = False
        self.readiness_duration = 0.0
        self.parser_selection: str | None = None
        
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
        
        # Try to detect parser selection from logs
        self._detect_parser()
        
        return True, f"Server ready in {self.readiness_duration:.1f}s (PID {self.pid})"
    
    def _detect_parser(self):
        """Try to detect parser selection from server logs."""
        try:
            if RUNTIME_LOG.exists():
                with open(RUNTIME_LOG, "r") as f:
                    content = f.read()
                    # Look for parser-related log lines
                    if "qwen3" in content.lower() and "parser" in content.lower():
                        self.parser_selection = "qwen3"
                    elif "tool" in content.lower() and "parser" in content.lower():
                        # Extract parser name if visible
                        import re
                        match = re.search(r"parser[:\s]+(\w+)", content, re.IGNORECASE)
                        if match:
                            self.parser_selection = match.group(1).lower()
        except Exception:
            pass
    
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


def test_single_required_tool(base_url: str, validator: ToolValidator) -> dict[str, Any]:
    """Test 1: Required single tool call."""
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
    
    result = {
        "test": "single_required_tool",
        "http_status": None,
        "latency_s": None,
        "error": None,
        "pass": False,
        "tool_call_emitted": False,
        "tool_call_structured": False,
        "tool_name": None,
        "arguments_valid": False,
        "arguments": None,
        "tool_call_id": None,
        "tool_call_id_hash": None,
        "mock_executed": False,
        "mock_result": None,
        "final_answer_contains_result": False,
        "finish_reason": None,
        "raw_xml_leaked": False,
        "execution_count": 0,
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
        
        # Check for raw XML leakage
        result["raw_xml_leaked"] = "<function=" in content or "<tool_call>" in content
        
        if not tool_calls:
            result["error"] = "No tool calls in response"
            return result
        
        if len(tool_calls) > 1:
            result["error"] = f"Multiple tool calls: {len(tool_calls)}"
            return result
        
        result["tool_call_emitted"] = True
        
        tc = tool_calls[0]
        
        # Validate structure
        tc_id = tc.get("id")
        tc_type = tc.get("type")
        func = tc.get("function", {})
        name = func.get("name", "")
        args_str = func.get("arguments", "{}")
        
        result["tool_call_structured"] = bool(tc_id and tc_type == "function" and name)
        result["tool_name"] = name
        result["tool_call_id"] = tc_id
        result["tool_call_id_hash"] = safe_tool_call_id(tc_id) if tc_id else None
        
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
        
        result["pass"] = (
            result["tool_call_emitted"]
            and result["tool_call_structured"]
            and result["arguments_valid"]
            and result["mock_executed"]
            and result["final_answer_contains_result"]
            and not result["raw_xml_leaked"]
            and result["execution_count"] == 1
        )
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def test_sequential_three_tool_chain(base_url: str, validator: ToolValidator) -> dict[str, Any]:
    """Test 2: Sequential three-tool chain."""
    tool_schemas_raw = {
        "get_seed": {
            "type": "function",
            "function": {
                "name": "get_seed",
                "description": "Get a seed value by name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
            },
        },
        "multiply": {
            "type": "function",
            "function": {
                "name": "multiply",
                "description": "Multiply a value by a factor.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "integer"},
                        "factor": {"type": "integer"},
                    },
                    "required": ["value", "factor"],
                    "additionalProperties": False,
                },
            },
        },
        "format_result": {
            "type": "function",
            "function": {
                "name": "format_result",
                "description": "Format a result with a label.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "integer"},
                        "label": {"type": "string"},
                    },
                    "required": ["value", "label"],
                    "additionalProperties": False,
                },
            },
        },
    }
    
    tool_schemas = {name: spec["function"]["parameters"] for name, spec in tool_schemas_raw.items()}
    
    result = {
        "test": "sequential_three_tool_chain",
        "pass": False,
        "error": None,
        "expected_order": ["get_seed", "multiply", "format_result"],
        "observed_order": [],
        "state_transitions": [],
        "argument_propagation_correct": False,
        "execution_counts": {},
        "final_answer_correct": False,
        "raw_xml_leaked": False,
        "duplicate_calls_blocked": 0,
        "wrong_order_blocked": 0,
    }
    
    messages = [
        {"role": "user", "content": "Complete this operation using exactly one tool call per assistant turn. First call get_seed with name alpha. After receiving its result, call multiply with the returned value and factor 3. After receiving that result, call format_result with the returned value and label VERIFIED. Do not answer until all three tool results have been received."}
    ]
    
    expected_sequence = [
        ("get_seed", {"name": "alpha"}),
        ("multiply", {"value": 7, "factor": 3}),
        ("format_result", {"value": 21, "label": "VERIFIED"}),
    ]
    
    state = 0
    max_turns = 10
    
    while state < 3 and len(messages) < 20 and max_turns > 0:
        max_turns -= 1
        
        payload = {
            "model": "default",
            "messages": messages,
            "tools": list(tool_schemas_raw.values()),
            "chat_template_kwargs": {"enable_thinking": False},
            "temperature": 0,
            "max_tokens": 512,
            "stream": False,
        }
        
        status, resp, latency, error = make_chat_request(base_url, payload)
        
        if status != 200 or resp is None:
            result["error"] = f"HTTP {status}: {error}"
            break
        
        choices = resp.get("choices", [])
        if not choices:
            result["error"] = "No choices"
            break
        
        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls", [])
        content = message.get("content", "")
        
        # Check for raw XML leakage
        if "<function=" in content or "<tool_call>" in content:
            result["raw_xml_leaked"] = True
        
        # If no tools and we're done, check final answer
        if not tool_calls and state == 3:
            result["final_answer_correct"] = "VERIFIED=21" in content
            break
        
        if not tool_calls:
            # No tool call when expected
            if state < 3:
                result["error"] = f"No tool call at state {state}"
            break
        
        if len(tool_calls) > 1:
            result["error"] = f"Multiple tool calls at state {state}: {len(tool_calls)}"
            break
        
        tc = tool_calls[0]
        expected_name, expected_args = expected_sequence[state]
        
        valid, reason, args = validator.validate_tool_call(tc, tool_schemas)
        
        if not valid:
            result["error"] = f"Validation failed at state {state}: {reason}"
            break
        
        actual_name = tc.get("function", {}).get("name", "")
        
        # Check order
        if actual_name != expected_name:
            result["wrong_order_blocked"] += 1
            result["error"] = f"Wrong order at state {state}: expected {expected_name}, got {actual_name}"
            break
        
        # Check argument propagation
        if state == 0:
            # get_seed
            if args.get("name") != "alpha":
                result["error"] = f"Wrong get_seed args: {args}"
                break
        elif state == 1:
            # multiply - value should come from previous result
            if args.get("value") != 7 or args.get("factor") != 3:
                result["error"] = f"Wrong multiply args: {args}"
                break
        elif state == 2:
            # format_result - value should come from previous result
            if args.get("value") != 21 or args.get("label") != "VERIFIED":
                result["error"] = f"Wrong format_result args: {args}"
                break
        
        tc_id = tc.get("id")
        
        # Execute mock
        if not validator.record_execution(tc_id):
            result["duplicate_calls_blocked"] += 1
            result["error"] = f"Duplicate call blocked at state {state}"
            break
        
        mock_result = MockToolExecutor.execute(actual_name, args)
        
        result["observed_order"].append(actual_name)
        result["state_transitions"].append({
            "state": state,
            "tool": actual_name,
            "args": args,
            "result": mock_result,
            "tc_id_hash": safe_tool_call_id(tc_id) if tc_id else None,
        })
        
        # Append to messages
        messages.append(message)
        messages.append({"role": "tool", "tool_call_id": tc_id, "content": json.dumps(mock_result)})
        
        state += 1
    
    # Final request without tools
    if state == 3:
        payload_final = {
            "model": "default",
            "messages": messages,
            "chat_template_kwargs": {"enable_thinking": False},
            "temperature": 0,
            "max_tokens": 256,
            "stream": False,
        }
        
        status, resp, _, _ = make_chat_request(base_url, payload_final)
        if status == 200 and resp:
            final_content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            result["final_answer_correct"] = "VERIFIED=21" in final_content
    
    result["execution_counts"] = {
        "get_seed": 1 if "get_seed" in result["observed_order"] else 0,
        "multiply": 1 if "multiply" in result["observed_order"] else 0,
        "format_result": 1 if "format_result" in result["observed_order"] else 0,
    }
    
    result["argument_propagation_correct"] = (
        len(result["observed_order"]) == 3
        and result["state_transitions"][0]["args"].get("name") == "alpha"
        and result["state_transitions"][1]["args"].get("value") == 7
        and result["state_transitions"][2]["args"].get("value") == 21
    )
    
    result["pass"] = (
        result["observed_order"] == result["expected_order"]
        and result["argument_propagation_correct"]
        and result["final_answer_correct"]
        and not result["raw_xml_leaked"]
        and result["duplicate_calls_blocked"] == 0
        and result["wrong_order_blocked"] == 0
        and sum(result["execution_counts"].values()) == 3
    )
    
    return result


def test_invalid_call_rejection(validator: ToolValidator) -> dict[str, Any]:
    """Test 3: Deterministic invalid-call rejection (client-side validation)."""
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
    
    result = {
        "test": "invalid_call_rejection",
        "pass": False,
        "cases": [],
        "total_cases": 0,
        "rejected": 0,
        "executed": 0,
        "valid_control_executed": False,
    }
    
    # Synthetic test cases
    test_cases = [
        # 1. Missing required argument
        {
            "name": "missing_required_arg",
            "tc": {"id": "tc_missing", "type": "function", "function": {"name": "add_numbers", "arguments": '{"a": 1}'}},
            "expected_reject": True,
            "expected_reason": "missing_required",
        },
        # 2. Wrong primitive type
        {
            "name": "wrong_type_integer",
            "tc": {"id": "tc_wrongtype", "type": "function", "function": {"name": "add_numbers", "arguments": '{"a": "not_int", "b": 2}'}},
            "expected_reject": True,
            "expected_reason": "wrong_type",
        },
        # 3. Unexpected additional property
        {
            "name": "unexpected_property",
            "tc": {"id": "tc_extra", "type": "function", "function": {"name": "add_numbers", "arguments": '{"a": 1, "b": 2, "c": 3}'}},
            "expected_reject": True,
            "expected_reason": "unexpected_property",
        },
        # 4. Unknown tool name
        {
            "name": "unknown_tool",
            "tc": {"id": "tc_unknown", "type": "function", "function": {"name": "unknown_tool", "arguments": '{}'}},
            "expected_reject": True,
            "expected_reason": "unknown_tool",
        },
        # 5. Malformed JSON arguments
        {
            "name": "malformed_json",
            "tc": {"id": "tc_malformed", "type": "function", "function": {"name": "add_numbers", "arguments": 'not json'}},
            "expected_reject": True,
            "expected_reason": "malformed_json",
        },
        # 6. Arguments not an object
        {
            "name": "args_not_object",
            "tc": {"id": "tc_notobj", "type": "function", "function": {"name": "add_numbers", "arguments": '[1, 2]'}},
            "expected_reject": True,
            "expected_reason": "args_not_object",
        },
        # 7. Missing tool-call ID
        {
            "name": "missing_id",
            "tc": {"type": "function", "function": {"name": "add_numbers", "arguments": '{"a": 1, "b": 2}'}},
            "expected_reject": True,
            "expected_reason": "missing_tool_call_id",
        },
        # 8. Duplicate tool-call ID
        {
            "name": "duplicate_id",
            "tc": {"id": "tc_duplicate", "type": "function", "function": {"name": "add_numbers", "arguments": '{"a": 1, "b": 2}'}},
            "setup": lambda v: v.executed_calls.add("tc_duplicate"),
            "expected_reject": True,
            "expected_reason": "duplicate_tool_call_id",
        },
        # 9. Duplicate idempotency key (same as duplicate ID)
        {
            "name": "duplicate_idempotency",
            "tc": {"id": "tc_idempotency", "type": "function", "function": {"name": "add_numbers", "arguments": '{"a": 5, "b": 5}'}},
            "setup": lambda v: v.executed_calls.add("tc_idempotency"),
            "expected_reject": True,
            "expected_reason": "duplicate_tool_call_id",
        },
        # 10. Partial/truncated argument string
        {
            "name": "truncated_args",
            "tc": {"id": "tc_truncated", "type": "function", "function": {"name": "add_numbers", "arguments": '{"a": 1,'}},
            "expected_reject": True,
            "expected_reason": "malformed_json",
        },
        # 11. Valid control call
        {
            "name": "valid_control",
            "tc": {"id": "tc_valid_control", "type": "function", "function": {"name": "add_numbers", "arguments": '{"a": 10, "b": 20}'}},
            "expected_reject": False,
            "expected_result": {"sum": 30},
        },
    ]
    
    for case in test_cases:
        case_result = {
            "name": case["name"],
            "rejected": False,
            "reason": None,
            "executed": False,
        }
        
        # Setup if needed
        if "setup" in case:
            case["setup"](validator)
        
        valid, reason, args = validator.validate_tool_call(case["tc"], tool_schemas)
        
        case_result["rejected"] = not valid
        case_result["reason"] = reason
        
        if valid:
            tc_id = case["tc"].get("id")
            if tc_id and validator.record_execution(tc_id):
                mock_result = MockToolExecutor.execute("add_numbers", args)
                case_result["executed"] = True
                case_result["result"] = mock_result
                
                if case["name"] == "valid_control":
                    result["valid_control_executed"] = True
        
        result["cases"].append(case_result)
        result["total_cases"] += 1
        
        if case["expected_reject"]:
            if not valid:
                result["rejected"] += 1
        else:
            if valid and case_result["executed"]:
                result["executed"] += 1
    
    # Verify no invalid call was executed
    invalid_executed = sum(1 for c in result["cases"] if c["rejected"] is False and c.get("executed") and c["name"] != "valid_control")
    
    result["pass"] = (
        result["rejected"] == 10  # All 10 invalid cases rejected
        and result["valid_control_executed"]  # Valid control executed
        and invalid_executed == 0  # No invalid call executed
    )
    
    return result


def main():
    """Run the complete P1C test matrix."""
    console_log = []
    
    def log(msg: str):
        timestamp = datetime.now(timezone.utc).isoformat()
        console_log.append(f"[{timestamp}] {msg}")
        print(msg, file=sys.stderr)
    
    log("P1C Tool Calling Matrix - Starting")
    
    evidence = {
        "schema_version": "1.0",
        "test": "p1c_tool_calling_matrix",
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
        "parser_selection": None,
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
    evidence["parser_selection"] = server.parser_selection
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
    
    try:
        # Test 1: Single required tool
        log("Running Test 1: Single required tool call")
        result1 = test_single_required_tool(BASE_URL, validator)
        evidence["tests"].append(result1)
        log(f"Test 1: {'PASS' if result1['pass'] else 'FAIL'}")
        
        evidence["runtime_snapshots"]["after_single_tool"] = {
            "memory": get_memory_snapshot(),
            "process": get_process_snapshot(server.pid),
        }
        
        # Test 2: Sequential three-tool chain
        log("Running Test 2: Sequential three-tool chain")
        result2 = test_sequential_three_tool_chain(BASE_URL, validator)
        evidence["tests"].append(result2)
        log(f"Test 2: {'PASS' if result2['pass'] else 'FAIL'}")
        
        evidence["runtime_snapshots"]["after_chain"] = {
            "memory": get_memory_snapshot(),
            "process": get_process_snapshot(server.pid),
        }
        
        # Test 3: Invalid call rejection (client-side, no server needed)
        log("Running Test 3: Invalid call rejection matrix")
        result3 = test_invalid_call_rejection(validator)
        evidence["tests"].append(result3)
        log(f"Test 3: {'PASS' if result3['pass'] else 'FAIL'}")
        
        evidence["runtime_snapshots"]["after_validation"] = {
            "memory": get_memory_snapshot(),
            "process": get_process_snapshot(server.pid),
        }
        
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
        evidence["tests"][0]["pass"] if len(evidence["tests"]) > 0 else False,
        evidence["tests"][1]["pass"] if len(evidence["tests"]) > 1 else False,
        evidence["tests"][2]["pass"] if len(evidence["tests"]) > 2 else False,
    ]
    
    if all(mandatory_pass) and stopped:
        evidence["overall_result"] = "PASS"
    elif not started:
        evidence["overall_result"] = "BLOCKED"
    else:
        evidence["overall_result"] = "FAIL"
    
    # Write evidence
    write_evidence(evidence, console_log)
    
    log(f"P1C Complete: {evidence['overall_result']}")
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
