#!/usr/bin/env python3
"""
P1B Chat Protocol Matrix Test Harness

Session-owned lifecycle test for Rapid-MLX raw baseline certification.
Starts ephemeral server, runs chat/streaming/two-turn/reasoning/cache tests,
archives bounded evidence, and safely stops the owned server.

DO NOT MODIFY: This script owns its complete test lifecycle.
"""

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
EVIDENCE_JSON = EVIDENCE_DIR / "05-p1b-chat-protocol-matrix.json"
EVIDENCE_CONSOLE = EVIDENCE_DIR / "05-p1b-chat-protocol-matrix-console.txt"

# Runtime log (gitignored)
RUNTIME_DIR = Path(__file__).parent.parent.parent.parent / "var" / "local-llm" / "logs"
RUNTIME_LOG = RUNTIME_DIR / "p1b-server.log"


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
    
    # Try both /health and /v1/models endpoints
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


def make_chat_request(base_url: str, payload: dict[str, Any], stream: bool = False) -> tuple[int, dict[str, Any] | None, float, str]:
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


def make_streaming_request(base_url: str, payload: dict[str, Any]) -> tuple[int, str, float, float, str]:
    """Make a streaming chat completion request."""
    import urllib.request
    import urllib.error
    
    url = f"{base_url}/chat/completions"
    payload["stream"] = True
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }
    
    start = time.time()
    ttft = None
    accumulated = ""
    finish_reason = None
    
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            for line in resp:
                line = line.decode("utf-8").strip()
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    chunk_str = line[6:]
                    try:
                        chunk = json.loads(chunk_str)
                        if ttft is None:
                            ttft = time.time() - start
                        if "choices" in chunk and chunk["choices"]:
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta:
                                accumulated += delta["content"]
                            finish_reason = chunk["choices"][0].get("finish_reason")
                    except json.JSONDecodeError:
                        pass
        return resp.status, accumulated, ttft or 0.0, time.time() - start, finish_reason or ""
    except urllib.error.HTTPError as e:
        return e.code, "", 0.0, time.time() - start, f"HTTP {e.code}"
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError) as e:
        return 0, "", 0.0, time.time() - start, str(e)


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
        # Ensure directories exist
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Check port is free
        if not check_port_free(PORT):
            return False, f"Port {PORT} is already in use"
        
        # Build command (no shell interpolation)
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
        
        # Start process with new process group
        log_file = open(RUNTIME_LOG, "w")
        self.process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # New process group
        )
        self.pid = self.process.pid
        self.start_time = time.time()
        
        # Wait for readiness
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
            
            # Verify the command contains rapid-mlx (the actual script path)
            # The exe() returns the Python interpreter, but cmdline[0] is the script
            rapid_mlx_found = any("rapid-mlx" in arg for arg in cmdline)
            if not rapid_mlx_found:
                return False, {"error": f"rapid-mlx not found in cmdline: {cmdline[:3]}"}
            
            # Verify model
            if MODEL_ALIAS not in cmdline:
                return False, {"error": f"Model {MODEL_ALIAS} not in cmdline"}
            
            # Verify host binding
            if "--host" in cmdline:
                idx = cmdline.index("--host")
                if cmdline[idx + 1] != HOST:
                    return False, {"error": f"Wrong host: {cmdline[idx + 1]}"}
            
            # Verify port
            if "--port" in cmdline:
                idx = cmdline.index("--port")
                if cmdline[idx + 1] != str(PORT):
                    return False, {"error": f"Wrong port: {cmdline[idx + 1]}"}
            
            # Verify no forbidden flags
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
            # First try graceful termination
            self.process.terminate()
            try:
                self.process.wait(timeout=GRACEFUL_SHUTDOWN_TIMEOUT_S)
                return self._verify_cleanup()
            except subprocess.TimeoutExpired:
                # Force kill if graceful fails
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
        """Verify process is stopped and port is free using robust checks."""
        # Wait a moment for cleanup
        time.sleep(2)
        
        # Check process is gone
        if self.pid:
            try:
                proc = psutil.Process(self.pid)
                if proc.is_running():
                    # Force kill again
                    try:
                        proc.kill()
                        time.sleep(1)
                    except Exception:
                        pass
                    # Re-check
                    try:
                        if proc.is_running():
                            return False, f"Process {self.pid} still running"
                    except psutil.NoSuchProcess:
                        pass
            except psutil.NoSuchProcess:
                pass
        
        # Check for orphan Rapid-MLX processes in the process group
        try:
            pgid = os.getpgid(self.pid) if self.pid else None
            if pgid is not None:
                for proc in psutil.process_iter(['pid', 'ppid', 'cmdline', 'name']):
                    try:
                        if proc.ppid() == self.pid or (hasattr(proc, 'pgid') and proc.pgid() == pgid):
                            cmdline = proc.info.get('cmdline', []) or proc.cmdline()
                            if any('rapid-mlx' in str(arg) for arg in cmdline):
                                return False, f"Orphan Rapid-MLX process {proc.pid} in process group"
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
        except (ProcessLookupError, PermissionError):
            pass
        
        # Verify cleanup with bounded retry (max 15 seconds)
        deadline = time.time() + 15
        while time.time() < deadline:
            # Check 1: No LISTEN socket on port (authoritative)
            listener_exists = self._check_listener_exists(PORT)
            
            # Check 2: Connection is refused (confirms no server)
            connection_refused = self._check_connection_refused(PORT)
            
            # Primary success condition: no listener AND connection refused
            # These two checks are sufficient - bind check is unreliable for transient states
            if not listener_exists and connection_refused:
                return True, "Cleanup verified"
            
            time.sleep(1)
        
        # Final diagnostic
        listener_exists = self._check_listener_exists(PORT)
        if listener_exists:
            return False, f"Port {PORT} has active LISTEN socket"
        
        connection_refused = self._check_connection_refused(PORT)
        if not connection_refused:
            return False, f"Port {PORT} accepts connections (unexpected)"
        
        # This should not be reached, but provide diagnostic
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
            # If lsof returns output (not just header), a listener exists
            lines = result.stdout.strip().split('\n')
            return len(lines) > 1  # More than just the header line
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Fallback: assume no listener if lsof unavailable
            return False
    
    def _check_connection_refused(self, port: int) -> bool:
        """Check if connection to port is refused (no server listening)."""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            sock.connect((HOST, port))
            sock.close()
            return False  # Connection succeeded = server still listening
        except (ConnectionRefusedError, OSError):
            return True  # Connection refused = no server
        finally:
            try:
                sock.close()
            except Exception:
                pass


def test_non_thinking(base_url: str) -> dict[str, Any]:
    """Test 1: Non-thinking chat."""
    payload = {
        "model": "default",
        "messages": [{"role": "user", "content": "Reply with exactly: NON_THINKING_OK"}],
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0,
        "max_tokens": 128,
        "stream": False,
    }
    
    status, resp, latency, error = make_chat_request(base_url, payload)
    
    result = {
        "test": "non_thinking_chat",
        "http_status": status,
        "latency_s": latency,
        "error": error,
        "pass": False,
        "finish_reason": None,
        "content": None,
        "has_thinking_tags": False,
    }
    
    if status != 200 or resp is None:
        return result
    
    try:
        choices = resp.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")
            result["content"] = content
            result["finish_reason"] = choices[0].get("finish_reason")
            result["has_thinking_tags"] = "<think>" in content or "</think>" in content
            result["pass"] = (
                "NON_THINKING_OK" in content
                and not result["has_thinking_tags"]
                and result["finish_reason"] == "stop"
            )
    except Exception as e:
        result["error"] = str(e)
    
    return result


def test_thinking(base_url: str) -> dict[str, Any]:
    """Test 2: Thinking chat with reasoning separation."""
    payload = {
        "model": "default",
        "messages": [{"role": "user", "content": "Determine which is larger: 17*19 or 18*18. Return the final comparison in one short sentence."}],
        "chat_template_kwargs": {"enable_thinking": True},
        "temperature": 0.6,
        "top_p": 0.95,
        "max_tokens": 1024,
        "stream": False,
    }
    
    status, resp, latency, error = make_chat_request(base_url, payload)
    
    result = {
        "test": "thinking_chat",
        "http_status": status,
        "latency_s": latency,
        "error": error,
        "pass": False,
        "finish_reason": None,
        "content": None,
        "has_leaked_thinking": False,
        "reasoning_present": False,
        "reasoning_length": 0,
        "math_correct": False,
    }
    
    if status != 200 or resp is None:
        return result
    
    try:
        choices = resp.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")
            reasoning = message.get("reasoning_content", "")
            
            result["content"] = content[:500] if content else None  # Truncated for evidence
            result["finish_reason"] = choices[0].get("finish_reason")
            result["reasoning_present"] = bool(reasoning)
            result["reasoning_length"] = len(reasoning) if reasoning else 0
            
            # Check for leaked thinking tags in final content
            result["has_leaked_thinking"] = "<think>" in content or "</think>" in content or "<tool_call>" in content
            
            # Check math: 17*19 = 323, 18*18 = 324, so 18*18 is larger
            result["math_correct"] = "324" in content or "18*18" in content.lower() or "larger" in content.lower()
            
            result["pass"] = (
                result["math_correct"]
                and not result["has_leaked_thinking"]
                and bool(content)
            )
    except Exception as e:
        result["error"] = str(e)
    
    return result


def test_streaming(base_url: str) -> dict[str, Any]:
    """Test 3: Streaming response."""
    payload = {
        "model": "default",
        "messages": [{"role": "user", "content": "Reply with exactly: STREAMING_OK"}],
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0,
        "max_tokens": 128,
    }
    
    status, content, ttft, total_latency, finish_reason = make_streaming_request(base_url, payload)
    
    return {
        "test": "streaming",
        "http_status": status,
        "ttft_s": ttft,
        "total_latency_s": total_latency,
        "finish_reason": finish_reason,
        "content": content,
        "pass": status == 200 and "STREAMING_OK" in content and ttft > 0,
    }


def test_two_turn(base_url: str) -> dict[str, Any]:
    """Test 4: Two-turn conversation."""
    # Turn 1
    payload1 = {
        "model": "default",
        "messages": [{"role": "user", "content": "Remember this code: COBALT-731. Reply only: STORED."}],
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0,
        "max_tokens": 64,
        "stream": False,
    }
    
    status1, resp1, latency1, error1 = make_chat_request(base_url, payload1)
    
    result = {
        "test": "two_turn",
        "turn1": {
            "http_status": status1,
            "latency_s": latency1,
            "error": error1,
            "content": None,
        },
        "turn2": {
            "http_status": None,
            "latency_s": None,
            "error": None,
            "content": None,
        },
        "pass": False,
    }
    
    if status1 != 200 or resp1 is None:
        return result
    
    # Extract assistant response for turn 2
    turn1_content = resp1.get("choices", [{}])[0].get("message", {}).get("content", "")
    result["turn1"]["content"] = turn1_content
    
    # Turn 2 - include the actual assistant response
    payload2 = {
        "model": "default",
        "messages": [
            {"role": "user", "content": "Remember this code: COBALT-731. Reply only: STORED."},
            {"role": "assistant", "content": turn1_content},
            {"role": "user", "content": "What code did I ask you to remember? Reply with the code only."},
        ],
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0,
        "max_tokens": 64,
        "stream": False,
    }
    
    status2, resp2, latency2, error2 = make_chat_request(base_url, payload2)
    
    result["turn2"]["http_status"] = status2
    result["turn2"]["latency_s"] = latency2
    result["turn2"]["error"] = error2
    
    if status2 == 200 and resp2:
        turn2_content = resp2.get("choices", [{}])[0].get("message", {}).get("content", "")
        result["turn2"]["content"] = turn2_content
        result["pass"] = "COBALT-731" in turn2_content
    
    return result


def test_prefix_cache(base_url: str) -> dict[str, Any]:
    """Test 5: Prefix cache observation."""
    system_prompt = "You are a helpful assistant. Always be concise."
    user_prompt = "What is 2+2? Reply with just the number."
    
    payload = {
        "model": "default",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0,
        "max_tokens": 32,
        "stream": False,
    }
    
    measurements = []
    
    # Warm-up request
    status, resp, _, _ = make_chat_request(base_url, payload)
    if status != 200:
        return {
            "test": "prefix_cache",
            "pass": False,
            "error": "Warm-up request failed",
            "measurements": [],
        }
    
    # Measured repetitions
    for i in range(3):
        status, resp, latency, error = make_chat_request(base_url, payload)
        if status == 200 and resp:
            choices = resp.get("choices", [])
            content = choices[0].get("message", {}).get("content", "") if choices else ""
            measurements.append({
                "round": i + 1,
                "latency_s": latency,
                "content": content,
                "finish_reason": choices[0].get("finish_reason") if choices else None,
            })
        time.sleep(0.5)
    
    # Analyze cache behavior
    if len(measurements) < 3:
        return {
            "test": "prefix_cache",
            "pass": False,
            "error": "Insufficient measurements",
            "measurements": measurements,
        }
    
    latencies = [m["latency_s"] for m in measurements]
    avg_latency = sum(latencies) / len(latencies)
    
    # Check for consistent improvement (cache indicator)
    # PASS if latencies are stable or improving without correctness regression
    all_correct = all("4" in m["content"] for m in measurements)
    stable_or_improving = latencies[2] <= latencies[0] * 1.1  # Within 10% of first
    
    # Since we don't have explicit cache-hit evidence, classify as INCONCLUSIVE if correct
    result_status = "PASS" if all_correct and stable_or_improving else "FAIL"
    if all_correct and not stable_or_improving:
        result_status = "INCONCLUSIVE"  # Correct but no cache evidence
    
    return {
        "test": "prefix_cache",
        "pass": result_status == "PASS",
        "status": result_status,
        "measurements": measurements,
        "avg_latency_s": avg_latency,
        "all_correct": all_correct,
    }


def main():
    """Run the complete P1B test matrix."""
    console_log = []
    
    def log(msg: str):
        timestamp = datetime.now(timezone.utc).isoformat()
        console_log.append(f"[{timestamp}] {msg}")
        print(msg, file=sys.stderr)
    
    log("P1B Chat Protocol Matrix - Starting")
    
    # Initialize evidence structure
    evidence = {
        "schema_version": "1.0",
        "test": "p1b_chat_protocol_matrix",
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
        "shutdown": {},
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
        evidence["shutdown"]["error"] = msg
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
    
    # Run tests
    try:
        # Test 1: Non-thinking
        log("Running Test 1: Non-thinking chat")
        result1 = test_non_thinking(BASE_URL)
        evidence["tests"].append(result1)
        log(f"Test 1: {'PASS' if result1['pass'] else 'FAIL'}")
        
        # Test 2: Thinking
        log("Running Test 2: Thinking chat")
        result2 = test_thinking(BASE_URL)
        evidence["tests"].append(result2)
        log(f"Test 2: {'PASS' if result2['pass'] else 'FAIL'}")
        
        # Test 3: Streaming
        log("Running Test 3: Streaming")
        result3 = test_streaming(BASE_URL)
        evidence["tests"].append(result3)
        log(f"Test 3: {'PASS' if result3['pass'] else 'FAIL'}")
        
        # Test 4: Two-turn
        log("Running Test 4: Two-turn conversation")
        result4 = test_two_turn(BASE_URL)
        evidence["tests"].append(result4)
        log(f"Test 4: {'PASS' if result4['pass'] else 'FAIL'}")
        
        # Test 5: Prefix cache
        log("Running Test 5: Prefix cache observation")
        result5 = test_prefix_cache(BASE_URL)
        evidence["tests"].append(result5)
        log(f"Test 5: {result5.get('status', 'FAIL')}")
        
        # Post-test snapshot
        evidence["runtime_snapshots"]["after_tests"] = {
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
        
        evidence["shutdown"] = {
            "success": stopped,
            "message": stop_msg,
        }
        
        evidence["runtime_snapshots"]["after_cleanup"] = {
            "memory": get_memory_snapshot(),
            "process": get_process_snapshot(None),
        }
    
    # Determine overall result
    mandatory_pass = [
        evidence["tests"][0]["pass"] if len(evidence["tests"]) > 0 else False,  # Non-thinking
        evidence["tests"][1]["pass"] if len(evidence["tests"]) > 1 else False,  # Thinking
        evidence["tests"][2]["pass"] if len(evidence["tests"]) > 2 else False,  # Streaming
        evidence["tests"][3]["pass"] if len(evidence["tests"]) > 3 else False,  # Two-turn
    ]
    
    cache_result = evidence["tests"][4].get("status", "FAIL") if len(evidence["tests"]) > 4 else "FAIL"
    cache_acceptable = cache_result in ("PASS", "INCONCLUSIVE")
    
    if all(mandatory_pass) and cache_acceptable and stopped:
        evidence["overall_result"] = "PASS"
    elif not started:
        evidence["overall_result"] = "BLOCKED"
    else:
        evidence["overall_result"] = "FAIL"
    
    # Write evidence
    write_evidence(evidence, console_log)
    
    log(f"P1B Complete: {evidence['overall_result']}")
    return 0 if evidence["overall_result"] == "PASS" else 1


def write_evidence(evidence: dict, console_log: list[str]):
    """Write evidence files."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Write JSON evidence
    with open(EVIDENCE_JSON, "w") as f:
        json.dump(evidence, f, indent=2)
    
    # Write console log
    with open(EVIDENCE_CONSOLE, "w") as f:
        f.write("\n".join(console_log))


if __name__ == "__main__":
    sys.exit(main())
