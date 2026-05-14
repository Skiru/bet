---
applyTo: ".github/agents/bet-*.agent.md"
---

# Agent Execution Protocol v6

## ⛔ FISH SHELL — ABSOLUTE TERMINAL RULES (VIOLATION = PIPELINE FAILURE)

This project uses **fish shell** (NOT bash/zsh). The following are **ABSOLUTELY FORBIDDEN** and WILL HANG/GARBLE:

### 🚫 NEVER DO (INSTANT FAILURE):

1. **`python3 -c "..."`** — ANY inline Python in terminal. Multi-line = GARBLES. Single-line with quotes = GARBLES. **ZERO EXCEPTIONS.** This has caused DOZENS of pipeline failures. The terminal output becomes gibberish and the command hangs indefinitely.
2. **`for f in ...; do ...; done`** — bash loop syntax. INVALID in fish.
3. **`while ...; do ...; done`** — bash loop syntax. INVALID in fish.
4. **`$(command)`** — bash command substitution. Use explicit values (e.g., `2026-05-11` not `$(date +%Y-%m-%d)`).
5. **Heredocs (`<< EOF`)** — Not supported in fish.
6. **`[[ ]]` conditionals** — bash-only. Fish uses `test` or `[ ]`.

### ✅ ALWAYS DO INSTEAD:

| Need | Solution |
|------|----------|
| Set up Python env | `ms-python.python/configurePythonEnvironment` → `ms-python.python/getPythonExecutableCommand` (once per session) |
| Run a scanner | `python3 scripts/run_scanner.py --sport football --date 2026-05-11` |
| Verify scan results | `python3 scripts/verify_scan.py --sport football --date 2026-05-11` |
| Check DB state | `python3 scripts/db_report.py --report quality` |
| Check scan data | `python3 scripts/db_report.py --report scan --date 2026-05-11` |
| Check source health | `python3 scripts/db_report.py --report source-health` |
| Validate pipeline | `python3 scripts/validate_phase.py --date 2026-05-11 --phase data` |
| Run scrapers | `PYTHONPATH=src .venv/bin/python scripts/run_scrapers.py --sport all --season 2425 --verbose` |
| Warm up odds cache | `python3 scripts/daily_odds_warmup.py --date 2026-05-11 --verbose` (stealth Playwright → html_cache/) |
| Any other logic | Create a `.py` file in `scripts/`, run it, then delete if temporary |
| Read data files | Use `read_file` tool (instant, no terminal needed) |

**WHY:** Fish shell handles multi-line strings and nested quotes differently from bash. Every `python3 -c "..."` attempt gets split into fragments by fish's parser, producing garbage output like `")` repeated hundreds of times, or hanging indefinitely. This is NOT fixable with escaping — it's a fundamental incompatibility.

---

## THE ONE RULE

> **If your response could be produced by piping terminal output to a file, you have FAILED.**
> Your response must contain YOUR ORIGINAL ANALYSIS — insights, patterns, anomalies, and reasoning that NO script could produce.
> A bash script can run commands and print output. YOU exist to THINK about what that output MEANS.

---

## 🔑 BOOT SEQUENCE (execute BEFORE any work — no exceptions)

**Your FIRST action** in every session must be a `sequentialthinking` call that answers:

```
0. Python env: Have I configured the Python environment via ms-python.python/configurePythonEnvironment?
1. What are MY 3 critical rules? (read from "MY RULES" section in your agent.md)
2. For each rule: what must I DO? What must I NEVER do?
3. What is my analytical value — what can I produce that a script cannot?
```

**WHY:** Rules buried in long documents get skipped. This forces conscious acknowledgment at the ONE moment you're most attentive — the start. If you skip this step, everything downstream is suspect.

**FORMAT:** Your sequentialthinking boot call must explicitly name each rule (e.g., "R5: I must evaluate stat markets BEFORE outcome markets") and state the concrete action (e.g., "For every football match, I will check corners/fouls/shots BEFORE checking ML/winner").

---

## 🔒 SELF-AUDIT (execute BEFORE returning — no exceptions)

**Your LAST action** before returning ANY response must be a `sequentialthinking` call that verifies:

```
1. Did I follow my 3 boot rules? Evidence for EACH:
   - Rule 1: [specific action I took that proves compliance]
   - Rule 2: [specific action I took that proves compliance]
   - Rule 3: [specific action I took that proves compliance]
2. Does my output contain ≥3 specific metrics from script output?
3. Does my output contain ORIGINAL ANALYSIS (not just restated numbers)?
4. If ANY rule was violated → I must FIX before returning.
```

**If you cannot cite evidence for a rule → you violated it.** Go back and fix.

---

## 🐍 Python Environment Setup (BEFORE first script execution)

Before running ANY Python script, use the `ms-python.python/configurePythonEnvironment` tool to ensure the correct virtual environment is active. Then use `ms-python.python/getPythonExecutableCommand` to get the proper Python executable path. This ensures scripts run in the project's `.venv` with all dependencies available — not the system Python.

**Do this ONCE per session**, before your first script execution. Cache the executable command and reuse it for all subsequent `run_in_terminal` calls.

If a script fails with `ModuleNotFoundError`, use `ms-python.python/installPythonPackage` to install the missing dependency, then retry.

---

## 🛠️ R21: PYLANCE-FIRST — Tool Selection Matrix (DECIDE BEFORE EVERY ACTION)

You have THREE execution tools. Choosing the WRONG one wastes time and blocks thinking.
**`pylanceRunCodeSnippet` is the PRIMARY tool for ALL data inspection.** NEVER use `python3 -c` or `python3 <<` in terminal — fish shell garbles it. Terminal is ONLY for running pipeline scripts via `python3 scripts/X.py`.

| Need | Tool | Why |
|------|------|-----|
| Check JSON structure, read data, count records | `pylanceRunCodeSnippet` | Instant — no terminal overhead, returns Python output directly |
| Query DB (SELECT COUNT, verify tables) | `pylanceRunCodeSnippet` | Fast — runs in Pylance runtime, no shell quoting issues |
| Validate input/output formats (R18) | `pylanceRunCodeSnippet` | Perfect for format checks before/after scripts |
| Quick calculations (EV, safety scores) | `pylanceRunCodeSnippet` | No fish shell issues, pure Python |
| Run ANY pipeline script | `run_in_terminal` + `mode=async` | ALWAYS async — agent THINKS while waiting, reacts to output |
| NEVER | `python3 -c "..."` in terminal | Fish shell GARBLES inline Python — ZERO exceptions |

### `pylanceRunCodeSnippet` — Your PRIMARY inspection tool

Use this for ALL data checks instead of terminal Python. It runs Python code directly through Pylance — no fish shell issues, instant results, perfect for:

```python
# Check shortlist format before running enrichment (R18):
import json
with open("betting/data/2026-05-13_s2_shortlist.json") as f:
    data = json.load(f)
print(f"Candidates: {len(data)}")
print(f"Keys: {list(data[0].keys()) if data else 'EMPTY'}")

# Verify DB state:
import sqlite3
conn = sqlite3.connect("betting/data/betting.db")
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM team_form WHERE date >= '2026-05-13'")
print(f"team_form rows today: {cur.fetchone()[0]}")
conn.close()

# Validate enrichment output matches S3 expectations:
import json, os
path = "betting/data/2026-05-13_enrichment_results.json"
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
    print(f"Enriched: {len(data)} | Keys: {list(data[0].keys()) if data else 'EMPTY'}")
else:
    print(f"MISSING: {path}")
```

**Rule:** If you can answer the question with <10 lines of Python → use `pylanceRunCodeSnippet`. If you need a full pipeline script → use `run_in_terminal`.

---

## Execution Models: RUN-THEN-DELEGATE vs AGENT-RUNS

There are **two execution models** for pipeline scripts. Choose based on WHO runs the script:

### Model A: RUN-THEN-DELEGATE (PREFERRED — orchestrator runs script, subagent analyzes)

```
ORCHESTRATOR                              SUBAGENT (specialist)
    │                                          │
    ├── pylanceRunCodeSnippet (INSPECT inputs)  │
    ├── run_in_terminal(mode=async, --verbose)  │
    ├── sequentialthinking (THINK-WHILE-WAITING)│
    ├── get_terminal_output → AGENT_SUMMARY     │
    ├── pylanceRunCodeSnippet (VALIDATE outputs) │
    │                                          │
    ├── runSubagent(specialist, {              │
    │     script_output: AGENT_SUMMARY,        │
    │     raw_metrics: extracted_numbers,      │
    │     input_context: upstream_data         │
    │   })                                     │──► ANALYZE ONLY
    │                                          │    (no script execution)
    │◄── structured verdict ───────────────────│
    │                                          │
    ├── 6-question quality gate                │
    ├── present to user                        │
```

**WHY this is preferred:** The orchestrator has DIRECT terminal control — it sees 404 errors, timeout signals, and script failures IN REAL TIME. Subagents focus on what they do best: specialist analysis with a fresh context window. Eliminates the entire class of R17 violations where subagents launch scripts and then sit idle.

**When to use:** ALL analytical steps (S2-S8) where the script is a standard run-once-and-analyze.

### Model B: AGENT-RUNS (legacy — subagent runs script + analyzes)

Use ONLY when the subagent needs iterative script execution (multiple runs, gap analysis, retargeting):
- Targeted re-enrichment after identifying specific gaps
- Multiple validation cycles (coupon V1-V10 → fix → re-validate)
- Interactive data exploration that requires multiple script invocations

**In Model B**, the subagent MUST follow the full 6-Step Cycle below.

---

## The 6-Step Cycle (for Model B — when subagent runs scripts)

### 0. INSPECT — Verify inputs BEFORE running (pylanceRunCodeSnippet)

Before launching ANY pipeline script, use `pylanceRunCodeSnippet` to verify:
1. Input files exist and have expected format (R18)
2. DB tables have data the script will read
3. Previous step's output matches this step's input expectations

```
❌ BAD: Just run the script and hope inputs are correct
✅ GOOD: pylanceRunCodeSnippet → check input JSON keys match script expectations → THEN run
```

**This catches R18 violations BEFORE they waste 10 minutes of script time.**

### 1. RUN — Launch with `--verbose`, choose execution mode

Always `--verbose`. Choose mode by script duration:

| Tier | Timeout | Mode | Why |
|------|---------|------|-----|
| fast | 120000 | `mode=async` | Even short scripts — THINK while waiting |
| medium | 300000 | `mode=async` | 5 min — THINK while waiting |
| long | 600000 | `mode=async` | 10 min — THINK while waiting |

**ALL scripts: `mode=async`** — launch, then **THINK-WHILE-WAITING** (step 1b below). No exceptions. Even a 30-second script gives you time to review previous data, plan next analysis, or verify assumptions. This is NOT fire-and-forget. You WILL check output.

### 1b. THINK-WHILE-WAITING (EVERY script — no exceptions)

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
| bet-scanner | `discover_events.py` (~30s) | Query DB for previous scan stats, review source health, check tournament schedules |
| bet-enricher | `data_enrichment_agent.py` (10 min) | Read shortlist JSON, check which teams already have form data in DB, identify gap candidates |
| bet-statistician | `deep_stats_report.py` (10 min) | Read enrichment output, assess data quality per candidate, pre-load sport protocols |
| bet-valuator | `odds_evaluator.py` (5 min) | Read S3 deep stats, pre-load safety scores and P(hit), identify strongest stat edges |
| bet-challenger | `context_checks.py` (5 min) | Review deep stats output, draft bear cases for borderline candidates |
| bet-scout | `tipster_aggregator.py` (5 min) | Read scan results, check pre-fetched HTML, identify tipster coverage gaps |
| bet-builder | `coupon_builder.py` (5 min) | Review gate results, check bankroll config, prepare portfolio intelligence |

#### ⛔ BAD vs ✅ GOOD Async Pattern

```
❌ BAD — brain-dead blocking (even for short scripts!):
run_in_terminal(command="python3 scripts/build_shortlist.py ...", mode=sync, timeout=120000)
# Agent sits idle doing NOTHING — not even reviewing previous data
# Then reads output without context

✅ GOOD — INSPECT → RUN ASYNC → THINK → VALIDATE:
# Step 0: INSPECT inputs first
pylanceRunCodeSnippet("""
import json, os
path = "betting/data/2026-05-13_enrichment_results.json"
data = json.load(open(path))
print(f"Input: {len(data)} candidates, keys: {list(data[0].keys())[:5]}")
# Verify format matches what deep_stats_report.py expects
assert 'team_home' in data[0], "MISSING team_home key — R18 VIOLATION"
""")

# Step 1: RUN async — don't block
terminal_id = run_in_terminal(command="python3 scripts/deep_stats_report.py ...", mode=async, timeout=600000)

# Step 1b: THINK while script runs
sequentialthinking("Enrichment produced 42/57 yield. Hockey at 44% — those candidates need PARTIAL flags...")
read_file("betting/data/2026-05-13_s2_shortlist.json")  # understand candidates
pylanceRunCodeSnippet("import sqlite3; conn = sqlite3.connect('betting/data/betting.db'); ...")  # quick DB check

# Step 2-3: Script done → EXTRACT + THINK
get_terminal_output(terminal_id)  # read full results
sequentialthinking("Script produced X candidates, Y anomalies...")

# Step 5: VALIDATE outputs before returning
pylanceRunCodeSnippet("""
import json, os
output = json.load(open("betting/data/2026-05-13_s3_deep_stats.json"))
print(f"Output: {len(output)} candidates analyzed")
print(f"Safety scores present: {sum(1 for c in output if 'safety_score' in c)}")
""")
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

### 4. RETURN — Fill in this MANDATORY template (Model B only — Model A subagents receive output, not run scripts)

- `subagent_verdict`, `Metrics`, `Anomalies`, `Issues`, and `Data For Orchestrator` = facts grounded in script output or `pylanceRunCodeSnippet` validation.
- `Analysis`, `Impact`, and `User Summary` = YOUR reasoning. `User Summary` MUST be plain-language and different from `Analysis`.

````markdown
## Verdict: {script_name}

```subagent_verdict
verdict: APPROVED | FLAGGED | REJECTED
quality_score: 1-10
script: {script_name}
exit_code: {0|1|2}
think_while_waiting: (required — what you did DURING script execution: sequentialthinking topics, pylanceRunCodeSnippet checks, data reviewed. If blank → R17 violation.)
```

### Metrics
| Metric | Value | Assessment |
|--------|-------|------------|
| (fill in ≥3 rows with REAL numbers from output) |

### Anomalies
- (specific anomaly + root cause, or `None`)

### Analysis
(3-5 sentences of YOUR reasoning — explain what the numbers MEAN, not what they ARE)

### Impact
- (what downstream step should know)

### Issues
- (actionable items, or `None`)

### User Summary
(2-3 plain-language sentences the orchestrator can present directly to the user)

### Data For Orchestrator
- next_step_ready: (required — e.g., `42 candidates ready for S3`)
- quality_flags: (required — e.g., `hockey=PARTIAL, football=FULL`)
- focus_points: (required — e.g., `re-price 6 partial-data candidates in S4`)
- (add extra keys only if essential)
````

### 5. VALIDATE — Verify outputs with `pylanceRunCodeSnippet` BEFORE returning

After forming your verdict, use `pylanceRunCodeSnippet` to verify the script's outputs are correct and ready for the next step:
1. Output files exist and have expected structure (R18)
2. DB tables were updated with expected row counts
3. Output format matches what the NEXT pipeline step will read

---

## Model A: Analysis-Only Verdict Template (when orchestrator ran the script)

When the orchestrator passes you script output for analysis, you DO NOT run any script. You receive:
- `script_output`: The AGENT_SUMMARY JSON + key metrics the orchestrator extracted
- `raw_log_excerpt`: Relevant warnings/errors from script verbose output
- `input_context`: Upstream step data and quality flags

Your job: **ANALYZE the output with specialist knowledge** and return the same structured verdict format.

````markdown
## Verdict: {script_name} (analysis-only)

```subagent_verdict
verdict: APPROVED | FLAGGED | REJECTED
quality_score: 1-10
script: {script_name}
exit_code: {from orchestrator context}
execution_model: analysis-only
```

### Metrics
| Metric | Value | Assessment |
|--------|-------|------------|
| (fill in ≥3 rows from the provided script output) |

### Anomalies
- (specific anomaly + root cause, or `None`)

### Analysis
(3-5 sentences of YOUR specialist reasoning — explain what the numbers MEAN for this domain)

### Impact
- (what downstream step should know)

### Issues
- (actionable items, or `None`)

### User Summary
(2-3 plain-language sentences the orchestrator can present directly to the user)

### Data For Orchestrator
- next_step_ready: (required)
- quality_flags: (required)
- focus_points: (required)
````

**Key difference from Model B:** No `think_while_waiting` field (you didn't run a script). No INSPECT/VALIDATE steps (orchestrator did those). Your ENTIRE value is specialist analysis.

```python
# Example: After enrichment, verify outputs before returning verdict
import json, os, sqlite3

# Check output file
path = "betting/data/2026-05-13_enrichment_results.json"
exists = os.path.exists(path)
if exists:
    with open(path) as f:
        data = json.load(f)
    print(f"Output: {len(data)} records, keys: {list(data[0].keys())[:5]}")

# Verify DB writes
conn = sqlite3.connect("betting/data/betting.db")
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM team_form WHERE updated_at >= date('now')")
print(f"DB writes today: {cur.fetchone()[0]}")
conn.close()
```

**If validation fails → FIX the issue before returning. Don't pass broken data downstream.**

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
````markdown
## Verdict: data_enrichment_agent.py

```subagent_verdict
verdict: APPROVED
quality_score: 8
script: data_enrichment_agent.py
exit_code: 0
think_while_waiting: sequentialthinking on shortlist data quality (88% FIXTURE_ONLY), pylanceRunCodeSnippet to check team_form baseline (12,847 rows), identified 9 hockey teams likely to gap
```

### Metrics
| Metric | Value | Assessment |
|--------|-------|------------|
| Yield | 73% (42/57) | OK (above 60% threshold) |
| Football | 24/28 (86%) | OK |
| Tennis | 8/12 (67%) | OK |
| Hockey | 4/9 (44%) | WARNING — below sport threshold |
| L10 form gaps | 15 candidates | WARNING — degraded S3 input |

### Anomalies
- Hockey enrichment yield: 4/9 (44%). Root cause: Flashscore returned stale KHL pages and ESPN fallback had standings only.
- L10 form gaps: 15 candidates. Root cause: off-season datasets left recent-fixture coverage incomplete.

### Analysis
Overall yield of 73% is healthy and above the 60% approval threshold. The hockey weakness is structural (off-season), not a pipeline bug. The 15 candidates with missing L10 form will get degraded analysis in S3, so they should be flagged as PARTIAL data quality rather than rejected. Football enrichment at 86% is strong, which keeps our core sport well supplied for stat-market analysis.

### Impact
- S3 should expect 42 candidates with FULL data and 15 with PARTIAL data.
- Hockey candidates need extra caution in safety scores.

### Issues
- None blocking. Hockey gap is informational.

### User Summary
Enrichment cleared most of the shortlist with strong football coverage and manageable partial-data risk. Hockey remains the weak spot because off-season sources returned incomplete form data, so those candidates need caution rather than rejection.

### Data For Orchestrator
- next_step_ready: 42 FULL candidates, 15 PARTIAL candidates
- quality_flags: hockey=PARTIAL, football=FULL, tennis=FULL
- focus_points: highlight hockey caution in S3 and preserve all candidates in stats-first mode
````

**The difference:** The GOOD output separates script-grounded facts (`subagent_verdict`, `Metrics`, `Anomalies`, `Data For Orchestrator`) from agent reasoning (`Analysis`, `Impact`, `User Summary`). The BAD output is vague prose that the orchestrator cannot reliably parse or present.

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
| 16 | `python3 -c "..."` in terminal | Use `pylanceRunCodeSnippet` for ALL inline Python — instant, no fish issues |
| 17 | Terminal Python for data inspection | Use `pylanceRunCodeSnippet` (PRIMARY) or `read_file` (JSON). NEVER terminal Python |
| 18 | Skip INSPECT step (run script without checking inputs) | Use `pylanceRunCodeSnippet` to verify inputs BEFORE launching script (R18) |
| 19 | Skip VALIDATE step (return without checking outputs) | Use `pylanceRunCodeSnippet` to verify outputs BEFORE returning verdict |
| 20 | `mode=sync` for ANY pipeline script | MUST use `mode=async` + THINK-WHILE-WAITING for ALL scripts — brain-dead blocking = FAILURE |

---

## ⛔ BANNED TERMINAL PATTERNS

These patterns are **ABSOLUTELY FORBIDDEN**. Violation = pipeline failure.

### ❌ NEVER DO:
```bash
# ANY inline python — GARBLES in fish shell, HANGS terminal
python3 -c "anything"
python3 -c 'anything'
PYTHONPATH=src python3 -c "anything"

# Batch loops — user CANNOT tell if hung or running
for f in betting/data/*.json; do python3 scripts/process.py "$f"; done

# Sleep/poll loops — wasted time, no analysis
while ps -p $PID > /dev/null; do sleep 5; done

# Bash command substitution — INVALID in fish
python3 scripts/X.py --date $(date +%Y-%m-%d)

# Fire-and-forget async — launch then IGNORE output
run_in_terminal(mode=async)  # then never check output or think

# Multiple scripts chained blindly
python3 scripts/A.py && python3 scripts/B.py && python3 scripts/C.py
```

### ✅ INSTEAD DO:
```
FOR DATA INSPECTION — USE pylanceRunCodeSnippet (PRIMARY):
→ BEST: pylanceRunCodeSnippet with Python code (DB queries, JSON reads, format checks)
→ GOOD: python3 scripts/db_report.py --report quality|gaps|scan|source-health
→ GOOD: read_file on JSON output files — instant, no quoting issues
→ NEVER: python3 -c in terminal — ALWAYS use pylanceRunCodeSnippet instead

FOR INPUT/OUTPUT VALIDATION (R18):
→ BEFORE script: pylanceRunCodeSnippet to check input format/existence
→ AFTER script: pylanceRunCodeSnippet to verify output format/counts
→ NEVER: Skip validation. Never assume scripts "just work".

FOR DATES:
→ Always use explicit date: --date 2026-05-13
→ NEVER: $(date +%Y-%m-%d) or `date +%Y-%m-%d`

FOR ALL PIPELINE SCRIPTS (no sync exceptions):
1. INSPECT: pylanceRunCodeSnippet → verify inputs
2. RUN: mode=async, --verbose (timeout: 120000 fast, 300000 medium, 600000 long)
3. THINK-WHILE-WAITING: sequentialthinking + pylanceRunCodeSnippet for data review
4. get_terminal_output → check if done
5. EXTRACT+THINK: Read output → sequentialthinking → verdict + DECIDE next action
6. VALIDATE: pylanceRunCodeSnippet → verify outputs
7. ACT: If issues found → FIX them before proceeding
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

<!-- BET:instruction:agent-execution-protocol:v6 -->


## ⚡️ V6: UNIFIED API & BEAST MODE FALLBACK (2026-05-12)
- **UnifiedAPIClient**: Always refer to `bet.api_clients.unified.UnifiedAPIClient`. It wraps Flashscore, ESPN.
- **Playwright Fallback**: If 403 Forbidden is hit, the Unified API automatically triggers `StealthPlaywright` (Fallback). Do not assume 403 means dead end.
- **Gemini 3.1 Pro**: Execution, reasoning, and context analysis is driven by `Gemini 3.1 Pro (Preview)`. Use asynchronous parsing and `sequentialthinking` aggressively.

## ⚡️ V7: ACTIVE AGENT PATTERN (2026-05-13)
- **pylanceRunCodeSnippet = PRIMARY** for all data inspection (DB queries, JSON validation, format checks). Replaces `python3 -c` and simple terminal commands.
- **6-Step Cycle**: INSPECT → RUN → THINK → EXTRACT+THINK → RETURN → VALIDATE. Steps 0 and 5 use `pylanceRunCodeSnippet`.
- **Tool Selection Matrix**: Added clear decision rules — pylanceRunCodeSnippet for <10 lines Python, run_in_terminal(sync) for ≤120s scripts, run_in_terminal(async) for >120s scripts.
- **ZERO blocking allowed**: Scripts >120s MUST use `mode=async`. Agent MUST use `sequentialthinking` + `pylanceRunCodeSnippet` while waiting. Brain-dead sync blocking = PIPELINE FAILURE.
