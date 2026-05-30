"""Deep reasoning quality testing — ROUND 2: max_tokens & top_k tuning."""
import requests, json, time, sys

def test(label, messages, max_tok=4096, temperature=0.6, top_k=20, top_p=0.95, verbose=True):
    t0 = time.time()
    resp = requests.post('http://localhost:8000/v1/chat/completions',
        json={'model': 'qwen3.6-35b', 'messages': messages, 'max_tokens': max_tok,
              'temperature': temperature, 'top_k': top_k, 'top_p': top_p, 'stream': True},
        stream=True)
    reasoning, content = [], []
    for line in resp.iter_lines():
        line = line.decode()
        if not line.startswith('data: {'): continue
        try:
            chunk = json.loads(line[6:])
            delta = chunk['choices'][0].get('delta', {})
            if 'reasoning_content' in delta and delta['reasoning_content']:
                reasoning.append(delta['reasoning_content'])
            if 'content' in delta and delta['content']:
                content.append(delta['content'])
        except: pass
    elapsed = time.time() - t0
    r = ''.join(reasoning)
    c = ''.join(content)
    if verbose:
        print(f"\n{'='*60}")
        print(f"TEST: {label} | temp={temperature} top_k={top_k} max_tok={max_tok}")
        print(f"{'='*60}")
        print(f"METRICS: reasoning={len(r)} chars | content={len(c)} chars | time={elapsed:.1f}s")
        if r:
            print(f"\nREASONING (first 1500 chars):")
            print(r[:1500])
            if len(r) > 1500: print(f"  ... [{len(r)-1500} more chars]")
        else:
            print(f"\nREASONING: (skipped)")
        print(f"\nCONTENT (first 800 chars):")
        print(c[:800])
    return {'reasoning_len': len(r), 'content_len': len(c), 'time': elapsed, 
            'reasoning': r, 'content': c}

# Same complex prompt from Round 1
CORNERS = [
    {'role': 'system', 'content': 'You are bet-statistician. Analyze using three-way cross-check (L10+H2H+L5). Identify ALL bear cases. Provide safety score 0-100.'},
    {'role': 'user', 'content': """Real analysis: Tottenham vs Crystal Palace — Over 9.5 Corners @ 1.72

DATA:
- Spurs L10 home corners: [7,9,6,11,8,7,10,5,8,9] avg=8.0
- Spurs L5 home corners: [7,10,5,8,9] avg=7.8  
- Palace L10 away corners: [3,5,4,2,6,3,4,5,3,4] avg=3.9
- Palace L5 away corners: [3,4,5,3,4] avg=3.8
- H2H last 5 total corners: [11,9,13,10,8] avg=10.2
- Combined L10 average: 8.0+3.9=11.9
- Combined L5 average: 7.8+3.8=11.6
- H2H suggests: 3/5 over 9.5 (60% hit rate)
- But Palace away corners are VERY low (3.9 avg). If Palace gets only 3, Spurs need 7+ alone.
- Spurs L10 shows 3/10 games with <7 corners at home.

Calculate: exact hit rate from available data, safety score, and whether odds 1.72 represent +EV."""}
]

# Real pipeline gate-checker scenario  
GATE_CHECKER = [
    {'role': 'system', 'content': """You are bet-challenger (Devil's Advocate). Your job is to DESTROY weak picks.
For each pick, you must find the STRONGEST bear case. If the bear case is stronger than the bull case, REJECT the pick.
Use this framework:
1. Identify the ONE stat that makes this pick fail
2. Calculate implied probability vs actual probability  
3. Check for recency bias (is L5 different from L10?)
4. Look for survivorship bias in the data
5. Final verdict: PASS (strong enough) or REJECT (bear wins)"""},
    {'role': 'user', 'content': """Gate-check these 3 picks from today's shortlist:

PICK 1: Wolves vs Brighton — Over 2.5 Goals @ 1.90
Bull: Combined L10 goals avg 3.1, H2H last 4 all O2.5, Brighton away scoring 2.0/game
Bear: Wolves home L5 goals scored only 0.8 avg (massive drop from L10=1.4), Wolves 3 clean sheets in last 5 home

PICK 2: Napoli vs Lecce — Napoli Over 1.5 Team Goals @ 1.55
Bull: Napoli L10 home goals avg 2.8, Lecce concede 2.1/game away, Napoli last 8 home all O1.5 team goals
Bear: Lecce last 2 away games: parked bus (0-0, 1-0 losses with 23% possession)

PICK 3: Djurgarden vs Hammarby — Over 2.5 Goals @ 1.85  
Bull: Stockholm derby always intense, H2H last 6 avg 3.5 goals, both teams scoring L5
Bear: Allsvenskan early season (round 8), cold weather, both teams cautious starts this year (combined L5 avg only 2.2)

For each: thinking, verdict, confidence 0-100."""}
]

print("=" * 60)
print("EXPERIMENT 2: OPTIMAL max_tokens AT temp=0.6")
print("Finding the sweet spot for full reasoning + full output")
print("=" * 60)

# Test with 8192 tokens — should be enough for reasoning + content
r1 = test("Corners @ 8192 tokens", CORNERS, max_tok=8192, temperature=0.6, top_k=20)

print("\n\n" + "=" * 60)
print("EXPERIMENT 3: REAL PIPELINE — GATE CHECKER (3 picks)")
print("=" * 60)

r2 = test("Gate checker (3 picks)", GATE_CHECKER, max_tok=8192, temperature=0.6, top_k=20)

print("\n\n" + "=" * 60)
print("EXPERIMENT 4: top_k COMPARISON (20 vs 40 vs 60)")
print("Does higher top_k improve reasoning diversity?")
print("=" * 60)

results_topk = {}
for k in [20, 40, 60]:
    results_topk[k] = test(f"Gate checker @ top_k={k}", GATE_CHECKER, max_tok=8192, temperature=0.6, top_k=k)

print(f"\n\n{'='*60}")
print("TOP_K COMPARISON RESULTS")
print(f"{'='*60}")
print(f"{'top_k':<8} {'Reasoning':<12} {'Content':<12} {'Time':<8}")
print(f"{'-'*8} {'-'*12} {'-'*12} {'-'*8}")
for k, r in results_topk.items():
    print(f"{k:<8} {r['reasoning_len']:<12} {r['content_len']:<12} {r['time']:<8.1f}")

print(f"\n\n{'='*60}")
print("FINAL SUMMARY")
print(f"{'='*60}")
print(f"Corners (8192 tok): reasoning={r1['reasoning_len']} | content={r1['content_len']} | time={r1['time']:.1f}s")
print(f"Gate checker (8192 tok): reasoning={r2['reasoning_len']} | content={r2['content_len']} | time={r2['time']:.1f}s")
print(f"\nOptimal top_k: {max(results_topk.keys(), key=lambda k: results_topk[k]['reasoning_len'])} (deepest reasoning)")
print(f"Runner up:     {sorted(results_topk.keys(), key=lambda k: results_topk[k]['reasoning_len'])[-2]} (2nd deepest)")
