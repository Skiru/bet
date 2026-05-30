#!/usr/bin/env python3
"""Benchmark rapid-mlx server under realistic pipeline workloads."""
import time
import json
import urllib.request
import sys

BASE = "http://localhost:8000/v1/chat/completions"

def api_call(messages, max_tokens=50, stream=False):
    data = json.dumps({
        "model": "qwen3.6-35b",
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": stream,
        "temperature": 0.6,
    }).encode()
    req = urllib.request.Request(BASE, data=data, headers={"Content-Type": "application/json"})
    start = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        body = r.read()
    elapsed = time.time() - start
    d = json.loads(body)
    return d, elapsed


def stream_call(messages, max_tokens=100):
    """Measure time-to-first-token (TTFT) with streaming."""
    data = json.dumps({
        "model": "qwen3.6-35b",
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True,
        "temperature": 0.6,
    }).encode()
    req = urllib.request.Request(BASE, data=data, headers={"Content-Type": "application/json"})
    start = time.time()
    ttft = None
    total_chunks = 0
    with urllib.request.urlopen(req, timeout=300) as r:
        for line in r:
            line = line.decode().strip()
            if line.startswith("data: ") and line != "data: [DONE]":
                if ttft is None:
                    ttft = time.time() - start
                total_chunks += 1
    total = time.time() - start
    return ttft, total, total_chunks


def make_messages(prompt_tokens_target):
    """Build messages that approximate a target token count."""
    # ~4 chars per token average
    system = "You are a betting pipeline analyst. " * max(1, prompt_tokens_target // 20)
    user = "Summarize in one sentence."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def make_tool_messages(prompt_tokens_target):
    """Simulate a pipeline conversation with tool calls."""
    msgs = [
        {"role": "system", "content": "You are a betting pipeline agent. " * (prompt_tokens_target // 40)},
        {"role": "user", "content": "Run the S3 deep stats analysis for today's shortlist."},
        {"role": "assistant", "content": "I'll query the database for today's fixtures."},
        {"role": "tool", "content": json.dumps({"fixtures": [{"id": i, "home": f"Team{i}", "away": f"Team{i+50}", "sport": "football"} for i in range(20)]})},
        {"role": "assistant", "content": "Found 20 fixtures. Now analyzing form data."},
        {"role": "tool", "content": json.dumps({"form": {"goals_l10": [2.1, 1.8, 2.3], "corners_l10": [5.2, 4.8, 6.1]}}) * 5},
        {"role": "user", "content": "What's the verdict?"},
    ]
    return msgs


print("=" * 60)
print("RAPID-MLX PIPELINE BENCHMARK")
print("=" * 60)

# Test 1: Short prompt (typical subagent quick response)
print("\n[1] Short prompt (12 tokens in, 20 out) — baseline")
d, t = api_call([{"role": "user", "content": "Say hello in 3 words"}], 20)
tin = d["usage"]["prompt_tokens"]
tout = d["usage"]["completion_tokens"]
print(f"    {tin} in → {tout} out in {t:.2f}s | gen speed: {tout/t:.1f} tok/s")

# Test 2: Medium prompt (~2K tokens - early pipeline turn)
print("\n[2] Medium prompt (~2K tokens in) — early pipeline turn")
msgs = make_messages(2000)
d, t = api_call(msgs, 100)
tin = d["usage"]["prompt_tokens"]
tout = d["usage"]["completion_tokens"]
prefill_est = t - tout / 50  # assume ~50 tok/s generation
print(f"    {tin} in → {tout} out in {t:.2f}s | prefill ~{prefill_est:.1f}s | gen: {tout/t:.1f} tok/s")

# Test 3: Large prompt (~10K tokens - mid pipeline)
print("\n[3] Large prompt (~10K tokens in) — mid-pipeline")
msgs = make_messages(10000)
d, t = api_call(msgs, 50)
tin = d["usage"]["prompt_tokens"]
tout = d["usage"]["completion_tokens"]
prefill_est = t - tout / 50
print(f"    {tin} in → {tout} out in {t:.2f}s | prefill ~{prefill_est:.1f}s | gen: {tout/t:.1f} tok/s")

# Test 4: Very large prompt (~30K tokens - late pipeline with history)
print("\n[4] Very large prompt (~30K tokens in) — late pipeline")
msgs = make_messages(30000)
d, t = api_call(msgs, 50)
tin = d["usage"]["prompt_tokens"]
tout = d["usage"]["completion_tokens"]
prefill_est = t - tout / 50
print(f"    {tin} in → {tout} out in {t:.2f}s | prefill ~{prefill_est:.1f}s | gen: {tout/t:.1f} tok/s")

# Test 5: Streaming TTFT at different sizes
print("\n[5] Streaming TTFT (time-to-first-token)")
for label, target in [("2K", 2000), ("10K", 10000), ("30K", 30000)]:
    msgs = make_messages(target)
    ttft, total, chunks = stream_call(msgs, 30)
    print(f"    {label}: TTFT={ttft:.2f}s, total={total:.2f}s, chunks={chunks}")

# Test 6: Tool call conversation (realistic pipeline pattern)
print("\n[6] Tool-call conversation (~5K mixed)")
msgs = make_tool_messages(5000)
d, t = api_call(msgs, 200)
tin = d["usage"]["prompt_tokens"]
tout = d["usage"]["completion_tokens"]
print(f"    {tin} in → {tout} out in {t:.2f}s | gen: {tout/t:.1f} tok/s")

# Test 7: Repeated prompt (prefix cache hit)
print("\n[7] Prefix cache test (same 10K prompt, 2nd call)")
msgs = make_messages(10000)
# First call (cold)
_, t1 = api_call(msgs, 30)
# Second call (warm — should hit prefix cache)
_, t2 = api_call(msgs, 30)
print(f"    Cold: {t1:.2f}s | Warm: {t2:.2f}s | Speedup: {t1/max(t2,0.01):.1f}x")

print("\n" + "=" * 60)
print("DONE")
