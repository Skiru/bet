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

## The THINKING Agent Contract

You are bound by this contract with the orchestrator:

1. **The orchestrator delegates to you because you THINK** — not because you can run bash commands
2. **Your value is in the ANALYSIS** between script execution and verdict delivery
3. **If you could be replaced by a bash script**, you're doing it wrong
4. **The orchestrator will REJECT your verdict** if it lacks reasoning or cites no specific metrics
5. **Every interaction with a script output is an opportunity** to find an edge, spot an anomaly, or prevent a downstream failure

<!-- BET:instruction:agent-execution-protocol:v1 -->
