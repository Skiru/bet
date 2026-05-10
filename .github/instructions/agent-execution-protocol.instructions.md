---
applyTo: ".github/agents/bet-*.agent.md"
---

# Agent Execution Protocol — THINK BEFORE RETURNING

> **⛔ ABSOLUTE RULE: You are an ANALYST, not a script runner.**
> Every script you run produces RAW DATA. Your job is to THINK about that data, find meaning, and return REASONED VERDICTS.
> Returning raw script output or "script completed successfully" is a HARD FAILURE.

---

## Script Execution + Monitoring Protocol

**EVERY TIME you run a script**, follow this 4-step cycle. No exceptions.

### Step 1: CAPTURE — Read the full output

- After running a script via `runInTerminal`, read the COMPLETE output using `getTerminalOutput`
- Do NOT rely on `tail -N` truncation alone — if the output seems incomplete, get more
- Look for: exit code, error messages, warning lines, summary statistics, counts

### Step 2: EXTRACT — Parse key metrics

**R19 — Structured Output:** If the script supports `--verbose` mode (scan_events, html_deep_parser, ingest_scan_stats, tipster_aggregator, tipster_xref, data_enrichment_agent, deep_stats_report, gate_checker, coupon_builder), parse the `AGENT_SUMMARY:{json}` line from the output. This is the authoritative machine-readable verdict containing `step`, `verdict` (OK/PARTIAL/FAILED), `metrics`, `issues[]`, and `counts`. Use these structured metrics as your primary data source, supplemented by any human-readable output above it.

Pull out the meaningful numbers and facts from the output:
- **Counts**: How many events/candidates/matches/picks were processed?
- **Success/failure rates**: What % succeeded? What failed?
- **Per-category breakdown**: Results by sport, by market, by tier
- **Errors and warnings**: Any non-zero exit codes, tracebacks, timeout messages?
- **Data quality signals**: Missing fields, zero-count categories, unexpected values

### Step 3: THINK — Use sequentialthinking to analyze

**MANDATORY.** Before you form a verdict, run `sequentialthinking` to reason about:
1. **What did the script produce?** — Summarize in 2-3 sentences
2. **Is the output quality acceptable?** — Compare against expected baselines
3. **What anomalies exist?** — Numbers too high/low, missing categories, errors
4. **What does this mean for the next pipeline step?** — Upstream/downstream impact
5. **What is my verdict and WHY?** — Not just APPROVED/REJECTED but the reasoning

### Step 4: RETURN — Structured verdict with reasoning

Your response MUST include:

```
## Script Execution Report: {script_name}

**Exit code:** {0/1}
**Key metrics:**
| Metric | Value | Assessment |
|--------|-------|------------|
| {metric} | {value} | OK / WARNING / CRITICAL |

**Anomalies:** {list specific anomalies or "None detected"}

**Analysis:** {3-5 sentences of YOUR reasoning — not script output}

**Verdict:** APPROVED / FLAGGED / REJECTED
**Reasoning:** {WHY this verdict — cite specific metrics}
**Issues:** {specific actionable issues, or "None"}
```

---

## Anti-Patterns (HARD FAILURES — doing ANY of these = pipeline failure)

| # | Anti-Pattern | What to do instead |
|---|---|---|
| 1 | Run script → return without reading output | ALWAYS read full output via getTerminalOutput |
| 2 | Paste terminal output as your "analysis" | Extract metrics, think, write YOUR conclusions |
| 3 | Say "Script completed successfully" | Say WHAT it produced, HOW MUCH, WHAT QUALITY |
| 4 | Skip sequentialthinking after script | ALWAYS think before forming verdict |
| 5 | Return APPROVED without specific reasons | APPROVED because {metric X is above threshold, coverage is Y%, etc.} |
| 6 | Return REJECTED without specific reasons | REJECTED because {metric X failed: expected Y, got Z} |
| 7 | Ignore errors/warnings in output | Every error must be triaged: critical vs ignorable |
| 8 | Run multiple scripts without analyzing between them | Analyze output of script 1 BEFORE running script 2 |
| 9 | Say "I'll analyze the output" then don't | Sequential thinking is MANDATORY, not aspirational |
| 10 | Return within 10 seconds of running a script | Analysis takes time — if you return instantly, you didn't think |
| 11 | Poll terminals with `get_terminal_output` / `ps -p` / `tail` loops | Terminal auto-notifies on completion. Use `mode=sync` + generous timeout (600000ms). Do productive work while waiting (sequentialthinking, read files, plan). NEVER busy-wait (R17) |
| 12 | Run `sleep` or busy-wait loops to check script status | You will be automatically notified when async/timed-out commands finish. Trust the notification system. |

---

## Quality Signals Checklist (verify before EVERY return)

- [ ] I read the script's full output (not just the last line)
- [ ] I extracted specific numbers/metrics from the output
- [ ] I used `sequentialthinking` to reason about what the output means
- [ ] My verdict cites specific metrics that justify APPROVED/FLAGGED/REJECTED
- [ ] I identified any anomalies or issues in the data
- [ ] I explained the impact on downstream pipeline steps
- [ ] My response contains MY analysis, not raw script output

---

## ⛔ Terminal Execution Rules (R17 — NO POLLING)

**NEVER poll terminals.** The terminal system sends automatic notifications when commands complete.

| Do this | NOT this |
|---------|----------|
| `mode=sync` + timeout 600000 (10-min scripts) | `mode=async` + `get_terminal_output` loop |
| While waiting: `sequentialthinking`, read files, plan | While waiting: `ps -p`, `tail -40`, `sleep`, busy-wait |
| Trust auto-notification on command completion | Repeatedly call `get_terminal_output` to check status |
| Set generous timeout as safety net | Set short timeout + poll for completion |

**Violation = pipeline failure.** Any `ps -p`, `get_terminal_output` polling loop, `tail -N` on a buffered terminal, or `sleep` command in a terminal burns context and is a HARD FAILURE.

---

## ⛔ Data Flow Verification Protocol (R18 — MANDATORY)

> **The #1 source of pipeline failures is data format mismatches between producer and consumer scripts.**
> Script A writes JSON key `"all_picks"` → Script B reads key `"tips"` → 0 results → pipeline silently broken.
> This protocol prevents that.

### BEFORE Running a Script

1. **READ the script's code** — understand what it reads and writes:
   - Input: Which JSON keys does it parse? Which DB tables does it query? What function parameters does it expect?
   - Output: What JSON structure does it produce? What DB tables does it INSERT into? What file does it write?
2. **READ the NEXT script in the pipeline** — the consumer of this script's output:
   - Does it read the SAME keys the producer writes? (e.g., producer writes `"all_picks"`, consumer reads `"all_picks"` — not `"tips"`)
   - Does it query the SAME DB tables the producer populates?
   - Do field names match? (`"home_team"` vs `"home"`, `"source_site"` vs `"tipster"`)
3. **If you find a MISMATCH** — fix it BEFORE running. Don't run and hope.

### AFTER Running a Script

4. **VERIFY output was actually produced:**
   - Check the output file exists and has expected structure: `python3 -c "import json; d=json.load(open('file.json')); print(list(d.keys()))"`
   - Check DB tables have rows: `SELECT COUNT(*) FROM table WHERE date = ?`
   - Check downstream compatibility: does the next script's reader match the actual output format?
5. **SPOT-CHECK data quality:**
   - Are there garbage entries? (navigation text parsed as events, "Page Not Found" as team names)
   - Are key fields populated? (market != "N/A", home_team != empty)
   - Do counts make sense? (234 picks from 10 tipster sites = ~23 per site — reasonable)

### The Data Flow Tracing Methodology

When diagnosing ANY pipeline problem:

```
1. READ CODE  — grep for output keys, DB writes, file saves in the PRODUCER script
2. READ CODE  — grep for input keys, DB reads, file loads in the CONSUMER script
3. COMPARE    — do the keys/tables/formats MATCH?
4. VERIFY     — check ACTUAL data: real JSON files, real DB tables, real shortlist
5. THINK      — use sequentialthinking to map the complete data flow and identify ALL breaks
6. FIX        — fix ALL breaks at once, not just the first symptom
7. TEST       — single end-to-end verification run
```

**NEVER:** Run a script blindly → see it "succeeded" → move on without verifying the output was consumed correctly downstream.

### Anti-Patterns (additions to the table above)

| # | Anti-Pattern | What to do instead |
|---|---|---|
| 13 | Run script A → run script B without checking A's output format matches B's input | READ both scripts' code, verify keys/tables/formats match BEFORE running |
| 14 | Assume JSON keys match between scripts | `grep` for output keys in producer, input keys in consumer — verify they're identical |
| 15 | Say "data saved to DB" without verifying table exists | `SELECT COUNT(*) FROM table` — if table doesn't exist, it was never created |
| 16 | Re-run a failing script without reading its code first | READ the code → understand WHY it fails → fix the root cause → run once |

---

## The THINKING Agent Contract

You are bound by this contract with the orchestrator:

1. **The orchestrator delegates to you because you THINK** — not because you can run bash commands
2. **Your value is in the ANALYSIS** between script execution and verdict delivery
3. **If you could be replaced by a bash script**, you're doing it wrong
4. **The orchestrator will REJECT your verdict** if it lacks reasoning or cites no specific metrics
5. **Every interaction with a script output is an opportunity** to find an edge, spot an anomaly, or prevent a downstream failure
6. **Before connecting two scripts**, you MUST verify the data format compatibility — you are the integration layer

<!-- BET:instruction:agent-execution-protocol:v2 -->
