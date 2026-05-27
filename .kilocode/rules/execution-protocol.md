# Agent Execution Protocol (Kilo Code)

## Terminal: Fish Shell ONLY

No inline Python (`python3 -c "..."`), no bash loops, no heredocs, no `export`.
Use `set -x VAR value` for env vars. Run scripts via terminal one at a time.

---

## BOOT SEQUENCE (first action of every delegation)

Use `sequentialthinking` MCP tool answering:
1. What are MY 3 critical rules? (from my agent definition in kilo.jsonc)
2. What is my analytical value — what can I produce that a script cannot?
3. What lessons from `.kilocode/memory/pipeline-knowledge-base.md` apply today?
4. Apply HARD REJECT rules from `betting-mistakes-rules.md` to EVERY candidate.

## SELF-AUDIT (last action before returning verdict)

Use `sequentialthinking` verifying:
1. Did I follow my 3 rules? Evidence for each.
2. Does my output contain ≥3 specific metrics?
3. Does my output contain ORIGINAL ANALYSIS?

---

## Execution Pattern

```
INSPECT → RUN → THINK → EXTRACT → VALIDATE → RETURN
```

1. Verify inputs exist (check files/DB)
2. Run script (with `--verbose` if supported)
3. `sequentialthinking` — what does output MEAN?
4. Parse `AGENT_SUMMARY:{json}` or extract key metrics
5. Verify outputs exist (check files/DB)
6. Return structured verdict

---

## Structured Verdict Template

```markdown
## Verdict: {script_name}

verdict: APPROVED | FLAGGED | REJECTED
quality_score: 1-10
script: {script_name}
exit_code: {0|1|2}

### Metrics
| Metric | Value | Assessment |
|--------|-------|------------|
| (≥3 rows with REAL numbers from actual output) |

### Anomalies
- (specific anomaly + root cause, or None)

### Analysis
(3-5 sentences — what numbers MEAN, not what they ARE)

### Impact
- (what downstream step should know)

### Issues
- (actionable items, or None)

### Data For Orchestrator
- next_step_ready: (required)
- quality_flags: (required)
- focus_points: (required)
```

---

## BAD vs GOOD Output

❌ BAD: `"The enrichment script completed successfully. 57 candidates. Pipeline can proceed. APPROVED."`

✅ GOOD:
```
Metrics: Yield 73% (42/57). Football 24/28 (86%) Strong. Hockey 4/9 (44%) WARNING.
Analysis: Hockey weakness is structural (off-season), not a bug. 15 PARTIAL
candidates need conservative safety scoring. Football keeps core strong at 86%.
Data: next_step_ready: 42 FULL + 15 PARTIAL. quality_flags: hockey=PARTIAL.
```

---

## Data Flow Verification (R18)

Before running script B after script A:
1. READ script A's output format (JSON keys, DB tables written)
2. READ script B's input expectations (what it reads)
3. VERIFY they match — check real data, not assumptions
4. If mismatch → STOP and fix before proceeding

---

## Anti-Patterns (ANY = failure)

1. Return without reading full output
2. Paste terminal output as "analysis"
3. Skip `sequentialthinking`
4. APPROVED without citing ≥3 metrics
5. Ignore errors (404, 403, 0 results)
6. Skip verifying script flags before running (use `--verbose` if available)
7. Skip INSPECT/VALIDATE steps
8. "Looks good" without specific evidence
9. Proceed when candidate count < expected (≥20% of shortlist for S3)
