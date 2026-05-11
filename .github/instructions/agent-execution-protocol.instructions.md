---
applyTo: ".github/agents/bet-*.agent.md"
---

# Agent Execution Protocol v4

## THE ONE RULE

> **If your response could be produced by piping terminal output to a file, you have FAILED.**
> Your response must contain YOUR ORIGINAL ANALYSIS — insights, patterns, anomalies, and reasoning that NO script could produce.
> A bash script can run commands and print output. YOU exist to THINK about what that output MEANS.

---

## The 4-Step Cycle (EVERY script execution, no exceptions)

### 1. RUN — Launch with `--verbose`, choose execution mode

Always `--verbose`. Choose mode by script duration:

| Tier | Timeout | Mode | Why |
|------|---------|------|-----|
| fast | ≤120000 | `mode=sync` | Quick — just wait for it |
| medium | 300000 | `mode=async` | 5 min — THINK while waiting |
| long | 600000 | `mode=async` | 10 min — THINK while waiting |

**FAST scripts (≤120s):** `mode=sync` — wait for completion, proceed to EXTRACT.

**MEDIUM/LONG scripts (≥300s):** `mode=async` — launch, then **THINK-WHILE-WAITING** (step 1b below). This is NOT fire-and-forget. You WILL check output.

### 1b. THINK-WHILE-WAITING (async scripts only)

While the script runs, use this time productively:
- `sequentialthinking` → analyze PREVIOUS step's output deeper
- Review data quality from earlier stages
- Read relevant data files, DB tables, or JSON for the upcoming analysis
- Plan your approach for the NEXT pipeline step
- Prepare the verdict template with what you already know

Then call `get_terminal_output(id)` to check if the script is done:
- **Done?** → proceed to step 2 (EXTRACT)
- **Still running?** → do more productive thinking, check again
- **Erroring?** → diagnose and decide: wait / kill+retry / escalate

#### Productive Async Work by Agent Role

| Agent | Script Running | THINK-WHILE-WAITING: Do This |
|-------|---------------|------------------------------|
| bet-scanner | `scan_events.py` (10 min) | Query DB for previous scan stats, review source health, check tournament schedules |
| bet-enricher | `data_enrichment_agent.py` (10 min) | Read shortlist JSON, check which teams already have form data in DB, identify gap candidates |
| bet-statistician | `deep_stats_report.py` (10 min) | Read enrichment output, assess data quality per candidate, pre-load sport protocols |
| bet-valuator | `odds_evaluator.py` (5 min) | Read S3 deep stats, pre-load safety scores and P(hit), identify strongest stat edges |
| bet-challenger | `context_checks.py` (5 min) | Review deep stats output, draft bear cases for borderline candidates |
| bet-scout | `tipster_aggregator.py` (5 min) | Read scan results, check pre-fetched HTML, identify tipster coverage gaps |
| bet-builder | `coupon_builder.py` (5 min) | Review gate results, check bankroll config, prepare portfolio intelligence |

#### ⛔ BAD vs ✅ GOOD Async Pattern

```
❌ BAD — brain-dead blocking:
run_in_terminal(command="python3 scripts/deep_stats_report.py ...", mode=sync, timeout=600000)
# Agent sits idle for 10 minutes doing NOTHING
# Then reads output

✅ GOOD — THINK-WHILE-WAITING:
terminal_id = run_in_terminal(command="python3 scripts/deep_stats_report.py ...", mode=async)
# Agent immediately starts productive work:
sequentialthinking("What did enrichment produce? 42/57 yield, hockey weak at 44%...")
read_file("betting/data/2026-05-11_s2_shortlist.json")  # understand candidates
run_in_terminal("SELECT COUNT(*) FROM team_form WHERE ...", mode=sync)  # fast DB check
# Then check if script is done:
get_terminal_output(terminal_id)  # read results → EXTRACT → THINK → RETURN
```

### 2. EXTRACT — Pull specific numbers

From the output, extract: total count, success/fail rates, per-category breakdown, error patterns, data quality signals. If you can't cite at least 3 specific numbers, you didn't read the output.

### 3. THINK — `sequentialthinking` is MANDATORY

Before forming ANY verdict, run `sequentialthinking` answering:
1. What did the script produce? (2-3 sentences)
2. Quality acceptable? (compare against baselines)
3. What anomalies exist? (numbers too high/low, missing categories)
4. Impact on next pipeline step?
5. My verdict and WHY?

### 4. RETURN — Fill in this MANDATORY template

```
## Verdict: {script_name}

**Result:** APPROVED / FLAGGED / REJECTED

| Metric | Value | Assessment |
|--------|-------|------------|
| (fill in ≥3 rows with REAL numbers from output) |

**Anomalies:** (specific anomalies with explanations, or "None")

**My Analysis:** (3-5 sentences of YOUR reasoning — what the numbers MEAN, not what they ARE)

**Impact on Next Step:** (what downstream step should know)

**Issues:** (actionable items, or "None")
```

---

## ⛔ BAD vs GOOD Output (learn this by heart)

### ❌ BAD — This is a script runner, not an analyst:
```
The enrichment script completed successfully. 57 candidates were processed.
Data was enriched from multiple sources including Flashscore and ESPN.
Some teams had missing data. The pipeline can proceed.
Verdict: APPROVED
```

### ✅ GOOD — This is an analyst who THOUGHT about the output:
```
## Verdict: data_enrichment_agent.py

**Result:** APPROVED

| Metric | Value | Assessment |
|--------|-------|------------|
| Yield | 73% (42/57) | OK (above 60% threshold) |
| Football | 24/28 (86%) | OK |
| Tennis | 8/12 (67%) | OK |
| Hockey | 4/9 (44%) | WARNING — below sport threshold |
| L10 form gaps | 15 candidates | WARNING — degraded S3 input |

**Anomalies:** Hockey enrichment at 44% — Flashscore returned stale data for KHL
teams (season ended). ESPN fallback provided standings but no team form.
This means hockey candidates will enter S3 with PARTIAL data quality.

**My Analysis:** Overall yield of 73% is healthy and above the 60% approval
threshold. The hockey weakness is structural (off-season) not a pipeline bug.
15 candidates with missing L10 form will get degraded analysis in S3 — they
should be flagged as PARTIAL data quality, not rejected. The football enrichment
at 86% is strong — our core sport has deep data for stat market analysis.

**Impact on Next Step:** S3 deep stats should expect 42 candidates with full
data and 15 with partial. Hockey candidates need extra caution in safety scores.

**Issues:** None blocking. Hockey gap is informational.
```

**The difference:** The GOOD output has specific numbers, per-category breakdown, anomaly explanation with ROOT CAUSE, impact assessment, and original reasoning. The BAD output has vague summaries that could apply to any script run ever.

---

## Anti-Patterns (doing ANY = pipeline failure)

| # | Pattern | Fix |
|---|---------|-----|
| 1 | Run script → return without reading output | Read FULL output first |
| 2 | Paste terminal output as "analysis" | Extract metrics, write YOUR conclusions |
| 3 | "Script completed successfully" | Say WHAT, HOW MUCH, WHAT QUALITY |
| 4 | Skip sequentialthinking | MANDATORY before every verdict |
| 5 | APPROVED/REJECTED without reasons | Cite specific metrics |
| 6 | Ignore errors in output | Triage every error: critical vs ignorable |
| 7 | Run script B without analyzing script A's output | Analyze BETWEEN scripts |
| 8 | Run without `--verbose` | Blind execution = failure |
| 9 | "Completed" without specific numbers | Cite ≥3 metrics from output |
| 10 | Summarize script's own summary as YOUR analysis | Add ORIGINAL INSIGHT the script didn't produce |
| 11 | "I analyzed the output" then just restate it | Analysis = WHY + IMPACT + ANOMALIES, not restating |
| 12 | Present script conclusions as your own | Your value is reasoning BEYOND what the script computed |
| 13 | Run `for` loops / batch loops in terminal | Run ONE command at a time, THINK about result, proceed |
| 14 | `sleep` / `ps -p` polling / idle waiting | Use `mode=async` + THINK-WHILE-WAITING. Get notified on completion |
| 15 | Fire-and-forget (`mode=async` then ignore output) | `mode=async` + THINK-WHILE-WAITING + `get_terminal_output` + EXTRACT |
| 16 | `python3 -c "..."` with complex nested quotes | Use `read_file` for JSON/data inspection. For complex Python, use heredoc: `python3 << 'EOF'` |
| 17 | Running terminal Python to read JSON files | Use `read_file` tool — instant, no quoting issues, no terminal waste |

---

## ⛔ BANNED TERMINAL PATTERNS

These patterns are **ABSOLUTELY FORBIDDEN**. Violation = pipeline failure.

### ❌ NEVER DO:
```bash
# Batch loops — user CANNOT tell if hung or running
for f in betting/data/*.json; do python3 scripts/process.py "$f"; done

# Sleep/poll loops — wasted time, no analysis
while ps -p $PID > /dev/null; do sleep 5; done

# Fire-and-forget async — launch then IGNORE output
run_in_terminal(mode=async)  # then never check output or think

# Blocking sync for long scripts — agent sits idle 10 min doing NOTHING
run_in_terminal(mode=sync, timeout=600000)  # brain-dead waiting

# Multiple scripts chained blindly
python3 scripts/A.py && python3 scripts/B.py && python3 scripts/C.py

# Complex inline Python with nested quotes — GARBLES in terminal
python3 -c "d = json.load(open('file.json')); print(f'{d[\"key\"]}')"  # quoting hell
```

### ✅ INSTEAD DO:
```
FOR DATA INSPECTION (JSON files, DB queries):
→ Use read_file tool — instant, no quoting issues
→ For JSON summary: read_file + grep_search, NOT terminal Python

FOR RUNNING SCRIPTS:
→ Use the script's CLI (python3 scripts/X.py --args)
→ NEVER write inline Python in terminal to analyze script output

FOR FAST SCRIPTS (≤120s):
1. Run script: mode=sync, timeout=120000, --verbose
2. Read output → EXTRACT → THINK → RETURN

FOR MEDIUM/LONG SCRIPTS (≥300s):
1. Run script: mode=async, --verbose
2. THINK-WHILE-WAITING: sequentialthinking on PREVIOUS step, review data, plan next
3. get_terminal_output → check if done
4. If done: EXTRACT → THINK → RETURN
5. If still running: more thinking, check again
6. THEN run next script
```

**The rule:** ONE command → THINK → NEXT command. Never batch. Never loop. For long scripts: launch async → think productively → check output → analyze.

---

## Data Flow Verification (R18)

Before running script B after script A: verify A's output keys/tables match B's input expectations.
READ producer code → READ consumer code → COMPARE keys → VERIFY with actual data → FIX mismatches before running.

**Real example of what goes wrong:** `tipster_aggregator.py` saved picks under `"all_picks"` → `tipster_xref.py` read `"tips"` → got 0 matches → pipeline ran for DAYS with zero tipster data. Nobody noticed because nobody READ THE CODE.

After every script: verify output file exists, check DB row counts, spot-check for garbage entries.

---

## The THINKING Agent Contract

1. **You exist to THINK** — not to run bash commands. A bash script can do that.
2. **Your value = the ANALYSIS** between script execution and verdict delivery.
3. **If you could be replaced by `cat output.log | grep -c`**, you're doing it wrong.
4. **The orchestrator will REJECT your verdict** if it lacks reasoning or cites <3 specific metrics.
5. **Before connecting scripts**, verify data format compatibility — you are the integration layer.
6. **TEST: Read your response. Remove all numbers and metrics. Is anything left? If not, you just reformatted the output — you didn't analyze it.**

<!-- BET:instruction:agent-execution-protocol:v3 -->
