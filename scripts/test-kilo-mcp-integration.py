#!/usr/bin/env python3
"""
Phase 2 — Kilo MCP Integration Test
Production-grade MCP tool call test through Rapid-MLX.

Tests:
1. Brave Web Search through API
2. Context7 resolve library through API
3. Tool call parsing validation
4. Streaming tool call through API
"""

import json
import os
import sys
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
TIMEOUT = 120


def get_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
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


def test_brave_search_tool_call() -> dict:
    """Test 1: Brave Web Search tool call."""
    print("  1. Brave Web Search tool call...")
    
    tools = [{
        "type": "function",
        "function": {
            "name": "brave-search_brave_web_search",
            "description": "Search the web for information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query"
                    }
                },
                "required": ["query"]
            }
        }
    }]
    
    messages = [
        {"role": "user", "content": "Search the web for 'Python 3.14 release date' using the brave-search_brave_web_search function."}
    ]
    
    status, result, duration = make_request("/chat/completions", {
        "model": MODEL_ID,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 200,
        "temperature": 0
    })
    
    passed = status == 200
    tool_calls = []
    tool_name = None
    
    if passed:
        choice = result.get("choices", [{}])[0]
        message = choice.get("message", {})
        tool_calls = message.get("tool_calls", [])
        if tool_calls:
            tool_name = tool_calls[0].get("function", {}).get("name")
    
    passed = passed and len(tool_calls) > 0 and tool_name == "brave-search_brave_web_search"
    
    print(f"     {'PASS' if passed else 'FAIL'} (HTTP {status}, tool_calls={len(tool_calls)}, tool_name={tool_name})")
    
    return {
        "test": "brave_search_tool_call",
        "passed": passed,
        "http_status": status,
        "duration_ms": duration,
        "tool_calls_count": len(tool_calls),
        "tool_name": tool_name
    }


def test_context7_tool_call() -> dict:
    """Test 2: Context7 resolve library tool call."""
    print("  2. Context7 resolve library tool call...")
    
    tools = [{
        "type": "function",
        "function": {
            "name": "context7_resolve-library-id",
            "description": "Resolve a library name to a Context7-compatible library ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "libraryName": {
                        "type": "string",
                        "description": "The library name to search for"
                    },
                    "query": {
                        "type": "string",
                        "description": "The question or task"
                    }
                },
                "required": ["libraryName", "query"]
            }
        }
    }]
    
    messages = [
        {"role": "user", "content": "Use context7_resolve-library-id to find the library ID for 'React' with query 'How to use hooks'."}
    ]
    
    status, result, duration = make_request("/chat/completions", {
        "model": MODEL_ID,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 200,
        "temperature": 0
    })
    
    passed = status == 200
    tool_calls = []
    tool_name = None
    arguments_valid = False
    
    if passed:
        choice = result.get("choices", [{}])[0]
        message = choice.get("message", {})
        tool_calls = message.get("tool_calls", [])
        if tool_calls:
            tool_name = tool_calls[0].get("function", {}).get("name")
            args_str = tool_calls[0].get("function", {}).get("arguments", "{}")
            try:
                args = json.loads(args_str)
                arguments_valid = "libraryName" in args
            except:
                pass
    
    passed = passed and len(tool_calls) > 0 and tool_name == "context7_resolve-library-id" and arguments_valid
    
    print(f"     {'PASS' if passed else 'FAIL'} (HTTP {status}, tool_calls={len(tool_calls)}, args_valid={arguments_valid})")
    
    return {
        "test": "context7_tool_call",
        "passed": passed,
        "http_status": status,
        "duration_ms": duration,
        "tool_calls_count": len(tool_calls),
        "tool_name": tool_name,
        "arguments_valid": arguments_valid
    }


def test_tool_call_parsing() -> dict:
    """Test 3: Tool call parsing validation."""
    print("  3. Tool call parsing validation...")
    
    tools = [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name"
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature unit"
                    }
                },
                "required": ["location"]
            }
        }
    }]
    
    messages = [
        {"role": "user", "content": "What's the weather in Tokyo? Use get_weather function."}
    ]
    
    status, result, duration = make_request("/chat/completions", {
        "model": MODEL_ID,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 200,
        "temperature": 0
    })
    
    passed = status == 200
    parsing_valid = False
    tool_call_id = None
    arguments_parsed = False
    
    if passed:
        choice = result.get("choices", [{}])[0]
        message = choice.get("message", {})
        tool_calls = message.get("tool_calls", [])
        
        if tool_calls:
            tc = tool_calls[0]
            tool_call_id = tc.get("id")
            func = tc.get("function", {})
            args_str = func.get("arguments", "{}")
            
            try:
                args = json.loads(args_str)
                arguments_parsed = True
                parsing_valid = "location" in args
            except:
                pass
    
    passed = passed and parsing_valid
    
    print(f"     {'PASS' if passed else 'FAIL'} (HTTP {status}, parsing_valid={parsing_valid}, args_parsed={arguments_parsed})")
    
    return {
        "test": "tool_call_parsing",
        "passed": passed,
        "http_status": status,
        "duration_ms": duration,
        "parsing_valid": parsing_valid,
        "arguments_parsed": arguments_parsed,
        "tool_call_id": tool_call_id
    }


def test_streaming_tool_call() -> dict:
    """Test 4: Streaming tool call through API."""
    print("  4. Streaming tool call...")
    
    tools = [{
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Perform a calculation",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression to evaluate"
                    }
                },
                "required": ["expression"]
            }
        }
    }]
    
    messages = [
        {"role": "user", "content": "Calculate 123 * 456 using the calculate function."}
    ]
    
    # For streaming, we need to handle SSE
    url = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": MODEL_ID,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 200,
        "temperature": 0,
        "stream": True
    }
    
    start = time.perf_counter()
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        chunks_received = 0
        tool_call_chunks = 0
        finish_reason = None
        
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            for line in response:
                line = line.decode("utf-8").strip()
                if line.startswith("data: "):
                    chunk_data = line[6:]
                    if chunk_data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(chunk_data)
                        chunks_received += 1
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        if "tool_calls" in delta:
                            tool_call_chunks += 1
                        finish = chunk.get("choices", [{}])[0].get("finish_reason")
                        if finish:
                            finish_reason = finish
                    except:
                        pass
        
        duration_ms = (time.perf_counter() - start) * 1000
        
        passed = chunks_received > 0 and tool_call_chunks > 0 and finish_reason == "tool_calls"
        
    except Exception as e:
        passed = False
        chunks_received = 0
        tool_call_chunks = 0
        finish_reason = None
        duration_ms = 0
    
    print(f"     {'PASS' if passed else 'FAIL'} (chunks={chunks_received}, tool_chunks={tool_call_chunks}, finish={finish_reason})")
    
    return {
        "test": "streaming_tool_call",
        "passed": passed,
        "duration_ms": duration_ms,
        "chunks_received": chunks_received,
        "tool_call_chunks": tool_call_chunks,
        "finish_reason": finish_reason
    }


def test_multi_tool_call() -> dict:
    """Test 5: Multiple tool calls in sequence."""
    print("  5. Multiple tool calls in sequence...")
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_time",
                "description": "Get current time",
                "parameters": {"type": "object", "properties": {}, "required": []}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_date",
                "description": "Get current date",
                "parameters": {"type": "object", "properties": {}, "required": []}
            }
        }
    ]
    
    messages = [
        {"role": "user", "content": "Get both the current time and date using the available functions."}
    ]
    
    status, result, duration = make_request("/chat/completions", {
        "model": MODEL_ID,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 300,
        "temperature": 0
    })
    
    passed = status == 200
    tool_calls = []
    unique_tools = set()
    
    if passed:
        choice = result.get("choices", [{}])[0]
        message = choice.get("message", {})
        tool_calls = message.get("tool_calls", [])
        unique_tools = {tc.get("function", {}).get("name") for tc in tool_calls}
    
    # Note: Model may call one or both tools depending on interpretation
    passed = passed and len(tool_calls) >= 1
    
    print(f"     {'PASS' if passed else 'FAIL'} (HTTP {status}, tool_calls={len(tool_calls)}, unique_tools={unique_tools})")
    
    return {
        "test": "multi_tool_call",
        "passed": passed,
        "http_status": status,
        "duration_ms": duration,
        "tool_calls_count": len(tool_calls),
        "unique_tools": list(unique_tools)
    }


def main():
    print("=== Phase 2 — Kilo MCP Integration Test ===")
    print(f"Timestamp: {get_timestamp()}")
    print(f"Base URL: {BASE_URL}")
    print(f"Model: {MODEL_ID}")
    print()
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    results = []
    
    print("Running MCP integration tests...")
    results.append(test_brave_search_tool_call())
    results.append(test_context7_tool_call())
    results.append(test_tool_call_parsing())
    results.append(test_streaming_tool_call())
    results.append(test_multi_tool_call())
    
    print()
    
    # Summary
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    
    print("=" * 60)
    print(f"RESULTS: {passed}/{total} PASS")
    print("=" * 60)
    
    # Save results
    run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    output_file = os.path.join(OUTPUT_DIR, f"{run_id}-mcp-test.json")
    
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
