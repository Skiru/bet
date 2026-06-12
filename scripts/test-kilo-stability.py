#!/usr/bin/env python3
"""
Phase 2 — Kilo Multi-Turn Stability Test
Production-grade extended conversation stability test.

Tests:
1. 10-turn conversation stability
2. Context accumulation tracking
3. Memory stability under load
4. Response quality consistency
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


def test_extended_conversation() -> dict:
    """Test 1: 10-turn conversation stability."""
    print("  1. Extended conversation (10 turns)...")
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Keep responses brief."}
    ]
    
    turns = [
        "Hello, my name is TestBot. Remember it.",
        "What is my name?",
        "Calculate 10 + 20.",
        "What was the result of the calculation?",
        "Name three colors.",
        "What was the second color I mentioned?",
        "Tell me a short joke.",
        "Summarize our conversation so far.",
        "What day comes after Wednesday?",
        "Goodbye, summarize everything in one sentence."
    ]
    
    turns_passed = 0
    total_tokens = 0
    durations = []
    errors = []
    token_counts = []
    
    for i, user_input in enumerate(turns, start=1):
        messages.append({"role": "user", "content": user_input})
        
        status, result, duration = make_request("/chat/completions", {
            "model": MODEL_ID,
            "messages": messages,
            "max_tokens": 150,
            "temperature": 0.3
        })
        
        if status == 200:
            turns_passed += 1
            usage = result.get("usage", {})
            total_tokens += usage.get("total_tokens", 0)
            token_counts.append(usage.get("total_tokens", 0))
            durations.append(duration)
            
            assistant_reply = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            messages.append({"role": "assistant", "content": assistant_reply})
        else:
            errors.append(f"Turn {i}: HTTP {status}")
            durations.append(duration)
        
        # Brief pause between requests
        time.sleep(0.1)
    
    passed = turns_passed == len(turns)
    avg_duration = sum(durations) / len(durations) if durations else 0
    
    print(f"     {'PASS' if passed else 'FAIL'} (turns={turns_passed}/{len(turns)}, tokens={total_tokens}, avg_duration={avg_duration:.0f}ms)")
    
    return {
        "test": "extended_conversation",
        "passed": passed,
        "turns_passed": turns_passed,
        "total_turns": len(turns),
        "total_tokens": total_tokens,
        "avg_duration_ms": avg_duration,
        "token_counts": token_counts,
        "errors": errors
    }


def test_context_accumulation() -> dict:
    """Test 2: Context accumulation tracking."""
    print("  2. Context accumulation tracking...")
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."}
    ]
    
    # Build up context with numbered items
    items = []
    for i in range(5):
        items.append(f"Item {i+1}")
        messages.append({"role": "user", "content": f"Remember: {items[-1]}"})
        
        status, result, _ = make_request("/chat/completions", {
            "model": MODEL_ID,
            "messages": messages,
            "max_tokens": 50,
            "temperature": 0
        })
        
        if status == 200:
            assistant_reply = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            messages.append({"role": "assistant", "content": assistant_reply})
    
    # Now ask to recall all items
    messages.append({"role": "user", "content": "List all items I asked you to remember."})
    
    status, result, duration = make_request("/chat/completions", {
        "model": MODEL_ID,
        "messages": messages,
        "max_tokens": 100,
        "temperature": 0
    })
    
    passed = status == 200
    recall_count = 0
    
    if passed:
        response = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        # Count how many items were recalled
        for i in range(1, 6):
            if f"Item {i}" in response or f"item {i}" in response.lower() or str(i) in response:
                recall_count += 1
    
    # Accept if at least 3 items recalled (model may not recall all perfectly)
    passed = passed and recall_count >= 3
    
    print(f"     {'PASS' if passed else 'FAIL'} (HTTP {status}, items_recalled={recall_count}/5)")
    
    return {
        "test": "context_accumulation",
        "passed": passed,
        "http_status": status,
        "items_recalled": recall_count,
        "total_items": 5
    }


def test_memory_stability() -> dict:
    """Test 3: Memory stability under load."""
    print("  3. Memory stability under load...")
    
    # Run multiple requests and check for memory-related errors
    errors_count = 0
    success_count = 0
    total_duration = 0
    
    for i in range(10):
        status, result, duration = make_request("/chat/completions", {
            "model": MODEL_ID,
            "messages": [{"role": "user", "content": f"Test request {i+1}. Reply with 'OK'."}],
            "max_tokens": 10,
            "temperature": 0
        })
        
        total_duration += duration
        
        if status == 200:
            success_count += 1
        else:
            errors_count += 1
        
        time.sleep(0.05)
    
    passed = success_count == 10 and errors_count == 0
    avg_duration = total_duration / 10
    
    print(f"     {'PASS' if passed else 'FAIL'} (success={success_count}/10, errors={errors_count}, avg_duration={avg_duration:.0f}ms)")
    
    return {
        "test": "memory_stability",
        "passed": passed,
        "success_count": success_count,
        "errors_count": errors_count,
        "avg_duration_ms": avg_duration
    }


def test_response_consistency() -> dict:
    """Test 4: Response quality consistency."""
    print("  4. Response quality consistency...")
    
    # Same prompt multiple times with temperature 0 should give similar responses
    prompt = "What is 2 + 2? Reply with only the number."
    responses = []
    
    for i in range(5):
        status, result, _ = make_request("/chat/completions", {
            "model": MODEL_ID,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 10,
            "temperature": 0
        })
        
        if status == 200:
            response = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            responses.append(response.strip())
    
    # Check if responses contain "4" (the correct answer)
    correct_count = sum(1 for r in responses if "4" in r)
    passed = correct_count >= 4  # Allow 1 variation
    
    print(f"     {'PASS' if passed else 'FAIL'} (correct_responses={correct_count}/5)")
    
    return {
        "test": "response_consistency",
        "passed": passed,
        "correct_count": correct_count,
        "total_requests": 5,
        "responses": responses
    }


def test_long_context_handling() -> dict:
    """Test 5: Long context handling."""
    print("  5. Long context handling...")
    
    # Build a conversation with accumulating context
    messages = [{"role": "system", "content": "You are a helpful assistant."}]
    
    # Add 20 turns
    for i in range(20):
        messages.append({"role": "user", "content": f"Turn {i+1}: What is {i+1} + {i+1}?"})
        
        status, result, _ = make_request("/chat/completions", {
            "model": MODEL_ID,
            "messages": messages,
            "max_tokens": 30,
            "temperature": 0
        })
        
        if status == 200:
            assistant_reply = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            messages.append({"role": "assistant", "content": assistant_reply})
    
    # Final request should still work
    messages.append({"role": "user", "content": "What was the first question I asked?"})
    
    status, result, duration = make_request("/chat/completions", {
        "model": MODEL_ID,
        "messages": messages,
        "max_tokens": 50,
        "temperature": 0
    })
    
    passed = status == 200
    prompt_tokens = result.get("usage", {}).get("prompt_tokens", 0) if passed else 0
    
    print(f"     {'PASS' if passed else 'FAIL'} (HTTP {status}, prompt_tokens={prompt_tokens})")
    
    return {
        "test": "long_context_handling",
        "passed": passed,
        "http_status": status,
        "prompt_tokens": prompt_tokens,
        "total_turns": 21,
        "duration_ms": duration
    }


def main():
    print("=== Phase 2 — Kilo Multi-Turn Stability Test ===")
    print(f"Timestamp: {get_timestamp()}")
    print(f"Base URL: {BASE_URL}")
    print(f"Model: {MODEL_ID}")
    print()
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    results = []
    
    print("Running multi-turn stability tests...")
    results.append(test_extended_conversation())
    results.append(test_context_accumulation())
    results.append(test_memory_stability())
    results.append(test_response_consistency())
    results.append(test_long_context_handling())
    
    print()
    
    # Summary
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    
    print("=" * 60)
    print(f"RESULTS: {passed}/{total} PASS")
    print("=" * 60)
    
    # Save results
    run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    output_file = os.path.join(OUTPUT_DIR, f"{run_id}-stability-test.json")
    
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
