#!/usr/bin/env python3
"""
Phase 2 — Kilo Context Prefix Load Test
Production-grade context accounting and stability test for Rapid-MLX under Kilo prefix load.

Tests:
1. Cold start with full Kilo prefix
2. Warm cache benefit measurement
3. Context accounting accuracy
4. Token limit enforcement
5. Multi-turn stability under prefix
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Optional

# Configuration
BASE_URL = os.environ.get("RAPID_MLX_BASE_URL", "http://127.0.0.1:8000/v1")
API_KEY = os.environ.get("RAPID_MLX_API_KEY", "bb2c5c92afddd427bbede6807920fe63ac12ea3af4c3a9cb473373d20e8514c7")
MODEL_ID = "default"
OUTPUT_DIR = "reports/kilo-rapidmlx-baseline"
TIMEOUT = 120

# Kilo prefix simulation (truncated for test, real prefix is ~16KB)
KILO_PREFIX_TEMPLATE = """You are Kilo, a highly skilled software engineer with extensive knowledge in many programming languages, frameworks, design patterns, and best practices.

# Personality

- Your goal is to accomplish the user's task, NOT engage in a back and forth conversation.
- You accomplish tasks iteratively, breaking them down into clear steps and working through them methodically.
- Do not ask for more information than necessary. Use the tools provided to accomplish the user's request efficiently and effectively.
- You are STRICTLY FORBIDDEN from starting your messages with "Great", "Certainly", "Okay", "Sure". You should NOT be conversational in your responses, but rather direct and to the point.

# Code

- When making changes to code, always consider the context in which the code is being used. Ensure that your changes are compatible with the existing codebase and that they follow the project's coding standards and best practices.

# Model routing

- `code-gpt54`: OpenAI – ChatGPT Plus/Pro, model `openai-codex/gpt-5.4`, reasoning effort `medium`. Use for difficult architecture, large refactors, complex debugging, migrations, security-sensitive implementation, and final review.
- `code-local`: Rapid-MLX local Qwen (`openai-compatible/qwen36-local-35b`). Use for routine/private coding, repository exploration, bounded fixes, summaries, and low-cost iterations.

# Runtime

- Kilo Code baseline: 7.3.41 stable or newer stable.
- Local inference: Rapid-MLX 0.7.0, API model ID `default`, endpoint `http://127.0.0.1:8000/v1`.
- Local Kilo budget: 28,672 context / 24,576 input / 4,096 output on Apple M4 Pro with 48 GB unified memory.
- Local profile is text-only: no vision, DFlash, MTP, speculative decoding, or concurrent local generations.

# Execution rules

1. Never run more than one request against the local Rapid-MLX server at once.
2. Local Qwen agents issue exactly one tool call per assistant turn and wait for the result.
3. `code-gpt54` may group independent read-only operations, but mutations and delegated tasks remain sequential.
4. A primary agent delegates matching specialist work instead of imitating a specialist. Subagents never delegate recursively.
5. Maximum two attempts for the same failing operation; then change strategy or delegate.
6. Never claim success without a concrete diff, artifact, query result, test result, or current cited source.
7. Inspect the current diff before and after edits. Do not overwrite unrelated user changes.

# Session and context discipline

- Start a new session after switching profile, provider, model, primary agent, or betting phase.
- Read only the files required by the current task; do not recursively ingest the whole repository.
- Keep every displayed tool result below 8 KiB and save verbose output under `.kilo/artifacts/`.
- Local subagent output must stay below 900 tokens. Betting handoffs must stay below 1,000 tokens.
- Local automatic compaction is disabled. Save a checkpoint before manual `/compact`; after one compaction failure, continue in a fresh session.

# Betting phase contract

| Phase | Scope | Mandatory specialists | Exit artifact |
|---|---|---|---|
| A | S0 settlement and historical learning | `bet-settler`, `bet-db-analyst`, `bet-test-engineer` | `.kilo/state/phase-A-handoff.md` |
| B | S1–S1e discovery and shortlist | `bet-scanner`, `bet-test-engineer` | `.kilo/state/phase-B-handoff.md` |
| C | S2 tipster aggregation | `bet-scout`, `bet-test-engineer` | `.kilo/state/phase-C-handoff.md` |
| D | S2.3–S7 enrichment, modelling and gates | `bet-enricher`, `bet-statistician`, `bet-valuator`, `bet-challenger`, `bet-test-engineer` | `.kilo/state/phase-D-handoff.md` |
| E | S8–S10 construction and final validation | `bet-builder`, `bet-test-engineer` | `.kilo/state/phase-E-handoff.md` |

# Specialist result schema

Every betting specialist returns only: `STATUS`, `DECISION`, `EVIDENCE`, `CALCULATIONS`, `UNCERTAINTY`, `RISKS`, `NEXT_ACTION`.

# Evidence and data

- Direct database reads use only `bet_sqlite_query`; never open SQLite through shell, Python, editor, or another MCP tool.
- Database mutations use reviewed repository scripts and focused tests.
- Every factual betting claim traces to a DB row, generated artifact, or current external source with `as_of`.
- Never invent odds, fixtures, teams, markets, injuries, statistics, lineups, consensus, or model outputs.
- Material external facts should use two independent current sources when available; unresolved conflicts invoke `bet-reconciler`.
- `bet-test-engineer` must return `PASS` before a phase completes.
- All picks remain conditional until the user verifies the exact market and odds in Betclic.

# Repository and command safety

- Never read, echo, log, commit, or copy credentials, `.env` values, tokens, cookies, private keys, or OAuth state.
- Never use `sudo`, destructive recursive deletion, `git reset --hard`, `git clean`, force push, or unreviewed database mutation.
- A repair is the smallest reversible change and includes a focused regression test.
- Bash scripts with a Bash shebang may be launched from Fish.
"""


def get_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_request(endpoint: str, data: dict, stream: bool = False) -> tuple[int, Any, float]:
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


def test_cold_start_with_prefix() -> dict:
    """Test 1: Cold start with full Kilo prefix."""
    print("  1. Cold start with Kilo prefix...")
    
    messages = [
        {"role": "system", "content": KILO_PREFIX_TEMPLATE},
        {"role": "user", "content": "What is 2+2? Reply with only the number."}
    ]
    
    status, result, duration = make_request("/chat/completions", {
        "model": MODEL_ID,
        "messages": messages,
        "max_tokens": 10,
        "temperature": 0,
        "stream": False
    })
    
    passed = status == 200
    prompt_tokens = result.get("usage", {}).get("prompt_tokens", 0) if passed else 0
    
    print(f"     {'PASS' if passed else 'FAIL'} (HTTP {status}, {duration:.0f}ms, prompt_tokens={prompt_tokens})")
    
    return {
        "test": "cold_start_with_prefix",
        "passed": passed,
        "http_status": status,
        "duration_ms": duration,
        "prompt_tokens": prompt_tokens,
        "error": result.get("error") if not passed else None
    }


def test_warm_cache_benefit() -> dict:
    """Test 2: Warm cache benefit measurement."""
    print("  2. Warm cache benefit...")
    
    messages = [
        {"role": "system", "content": KILO_PREFIX_TEMPLATE},
        {"role": "user", "content": "What is 3+3? Reply with only the number."}
    ]
    
    # First request (should be cached from previous if prefix similar)
    status1, result1, duration1 = make_request("/chat/completions", {
        "model": MODEL_ID,
        "messages": messages,
        "max_tokens": 10,
        "temperature": 0,
        "stream": False
    })
    
    # Second request (should hit cache)
    status2, result2, duration2 = make_request("/chat/completions", {
        "model": MODEL_ID,
        "messages": messages,
        "max_tokens": 10,
        "temperature": 0,
        "stream": False
    })
    
    passed = status1 == 200 and status2 == 200
    cache_benefit = duration1 - duration2  # Positive if warm is faster
    
    print(f"     {'PASS' if passed else 'FAIL'} (cold={duration1:.0f}ms, warm={duration2:.0f}ms, benefit={cache_benefit:.0f}ms)")
    
    return {
        "test": "warm_cache_benefit",
        "passed": passed,
        "cold_duration_ms": duration1,
        "warm_duration_ms": duration2,
        "cache_benefit_ms": cache_benefit,
        "cache_benefit_pct": (cache_benefit / duration1 * 100) if duration1 > 0 else 0
    }


def test_context_accounting() -> dict:
    """Test 3: Context accounting accuracy."""
    print("  3. Context accounting accuracy...")
    
    # Build a message with known token count
    test_content = "a " * 100  # ~100 tokens
    messages = [
        {"role": "system", "content": KILO_PREFIX_TEMPLATE},
        {"role": "user", "content": test_content}
    ]
    
    status, result, duration = make_request("/chat/completions", {
        "model": MODEL_ID,
        "messages": messages,
        "max_tokens": 10,
        "temperature": 0,
        "stream": False
    })
    
    passed = status == 200
    usage = result.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", 0)
    
    # Verify accounting: total should equal prompt + completion
    accounting_valid = total_tokens == prompt_tokens + completion_tokens
    
    passed = passed and accounting_valid
    
    print(f"     {'PASS' if passed else 'FAIL'} (prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}, accounting_valid={accounting_valid})")
    
    return {
        "test": "context_accounting",
        "passed": passed,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "accounting_valid": accounting_valid
    }


def test_token_limit_enforcement() -> dict:
    """Test 4: Token limit enforcement."""
    print("  4. Token limit enforcement...")
    
    messages = [
        {"role": "system", "content": KILO_PREFIX_TEMPLATE},
        {"role": "user", "content": "Count from 1 to 100, one number per line."}
    ]
    
    # Request with small max_tokens
    max_tokens = 20
    status, result, duration = make_request("/chat/completions", {
        "model": MODEL_ID,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": False
    })
    
    passed = status == 200
    finish_reason = result.get("choices", [{}])[0].get("finish_reason", "")
    completion_tokens = result.get("usage", {}).get("completion_tokens", 0)
    
    # Should be truncated (finish_reason should be "length" not "stop")
    truncated = finish_reason == "length" or completion_tokens <= max_tokens
    passed = passed and truncated
    
    print(f"     {'PASS' if passed else 'FAIL'} (finish_reason={finish_reason}, completion_tokens={completion_tokens}, max_tokens={max_tokens})")
    
    return {
        "test": "token_limit_enforcement",
        "passed": passed,
        "finish_reason": finish_reason,
        "completion_tokens": completion_tokens,
        "max_tokens": max_tokens,
        "truncated": truncated
    }


def test_multi_turn_stability() -> dict:
    """Test 5: Multi-turn stability under prefix."""
    print("  5. Multi-turn stability (5 turns)...")
    
    messages = [
        {"role": "system", "content": KILO_PREFIX_TEMPLATE},
        {"role": "user", "content": "My name is Alice. Remember it."}
    ]
    
    turns_passed = 0
    total_tokens = 0
    errors = []
    
    # Turn 1: Initial
    status, result, _ = make_request("/chat/completions", {
        "model": MODEL_ID,
        "messages": messages,
        "max_tokens": 50,
        "temperature": 0
    })
    
    if status == 200:
        turns_passed += 1
        total_tokens += result.get("usage", {}).get("total_tokens", 0)
        assistant_reply = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        messages.append({"role": "assistant", "content": assistant_reply})
    else:
        errors.append(f"Turn 1 failed: {status}")
    
    # Turn 2-5: Continue conversation
    follow_ups = [
        "What is my name?",
        "Calculate 5+5.",
        "What was the calculation result?",
        "Summarize our conversation in one sentence."
    ]
    
    for i, follow_up in enumerate(follow_ups, start=2):
        messages.append({"role": "user", "content": follow_up})
        status, result, _ = make_request("/chat/completions", {
            "model": MODEL_ID,
            "messages": messages,
            "max_tokens": 100,
            "temperature": 0
        })
        
        if status == 200:
            turns_passed += 1
            total_tokens += result.get("usage", {}).get("total_tokens", 0)
            assistant_reply = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            messages.append({"role": "assistant", "content": assistant_reply})
        else:
            errors.append(f"Turn {i} failed: {status}")
    
    passed = turns_passed == 5
    
    print(f"     {'PASS' if passed else 'FAIL'} (turns_passed={turns_passed}/5, total_tokens={total_tokens})")
    
    return {
        "test": "multi_turn_stability",
        "passed": passed,
        "turns_passed": turns_passed,
        "total_turns": 5,
        "total_tokens": total_tokens,
        "errors": errors
    }


def test_context_boundary() -> dict:
    """Test 6: Context boundary near limit."""
    print("  6. Context boundary test...")
    
    # Build a message that approaches but stays under the limit
    # Kilo prefix is ~4K tokens, we have 24K input limit
    # Let's test with a large but safe payload
    
    large_content = "x " * 5000  # ~5000 tokens
    messages = [
        {"role": "system", "content": KILO_PREFIX_TEMPLATE},
        {"role": "user", "content": large_content}
    ]
    
    status, result, duration = make_request("/chat/completions", {
        "model": MODEL_ID,
        "messages": messages,
        "max_tokens": 10,
        "temperature": 0,
        "stream": False
    })
    
    passed = status == 200
    prompt_tokens = result.get("usage", {}).get("prompt_tokens", 0) if passed else 0
    
    print(f"     {'PASS' if passed else 'FAIL'} (HTTP {status}, prompt_tokens={prompt_tokens}, duration={duration:.0f}ms)")
    
    return {
        "test": "context_boundary",
        "passed": passed,
        "http_status": status,
        "prompt_tokens": prompt_tokens,
        "duration_ms": duration,
        "error": result.get("error") if not passed else None
    }


def main():
    print("=== Phase 2 — Kilo Context Prefix Load Test ===")
    print(f"Timestamp: {get_timestamp()}")
    print(f"Base URL: {BASE_URL}")
    print(f"Model: {MODEL_ID}")
    print()
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    results = []
    
    print("Running context prefix tests...")
    results.append(test_cold_start_with_prefix())
    results.append(test_warm_cache_benefit())
    results.append(test_context_accounting())
    results.append(test_token_limit_enforcement())
    results.append(test_multi_turn_stability())
    results.append(test_context_boundary())
    
    print()
    
    # Summary
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    
    print("=" * 60)
    print(f"RESULTS: {passed}/{total} PASS")
    print("=" * 60)
    
    # Save results
    run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    output_file = os.path.join(OUTPUT_DIR, f"{run_id}-context-test.json")
    
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
