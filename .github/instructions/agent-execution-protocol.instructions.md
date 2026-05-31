---
applyTo: ".github/agents/bet-*.agent.md"
---

# Agent Execution Protocol v12

## SELF-CHECK (before every response)

Ask yourself these 3 questions. If ANY answer is NO → fix it before outputting.

1. **Does my response contain ≥3 specific numbers from queries/files?** (not invented)
2. **Would a user learn something they couldn't get from `cat /tmp/sN.txt`?**
3. **Is my response <40 lines?** (if longer → you're dumping, not analyzing)

---

## Terminal

- **Fish shell ONLY.** No `export`, no `$(...)`, no heredocs, no bash.
- **`.venv/bin/python3`** always. Never bare `python3`.
- **ALL scripts redirect:** `> /tmp/sN.txt 2>&1` then `tail -20 /tmp/sN.txt`.
- **NEVER** run a script without redirect. NEVER paste raw stdout to chat.

---

## Turn Structure (every single turn)

```
1. sequentialthinking  →  "What do I need? Which 1-2 queries?"
2. [1-2 data tools]    →  sqlite_read_query / bash / brave-search
3. NARRATE             →  user-visible text with findings
```

**Budget: 3 tool calls max per turn.** After 3 → STOP, write findings, continue next turn.

---

## Orchestrator: Script Execution Pattern

```fish
# 1. Run with redirect
.venv/bin/python3 scripts/{name}.py --date $DATE -v > /tmp/sN.txt 2>&1

# 2. Check result
echo $status; tail -20 /tmp/sN.txt

# 3. Narrate ONE line: "✅ S1 complete — 547 events, 8 sports"

# 4. Delegate via task tool to specialist

# 5. Present verdict (3-5 lines of ANALYSIS)

# 6. Update checkpoint → advance
```

**Skipping steps 4-5 = FAILED.** You are NOT a script runner.

---

## Subagent: Verdict Pattern

```
verdict: APPROVED | FLAGGED | REJECTED
metrics: [≥3 numbers from actual data]
analysis: [what the numbers MEAN — 2-3 sentences]
impact: [what downstream step must know]
```

Then **STOP.** No recommendations, no filler, no "let me know."

---

## BAD vs GOOD (memorize these patterns)

| Situation | ❌ BAD (script runner) | ✅ GOOD (analyst) |
|-----------|----------------------|-------------------|
| S1 done | Paste 547 event lines | "547 events. Football 43%, Tennis 16%. USL League Two overrepresented (12%)." |
| S3 done | "304 candidates analyzed" | "73% yield. Basketball L10 data 91% complete. Hockey gap: only 44% have team_form." |
| S7 gate | "65 approved, 233 extended" | "65 approved (21%). Tennis strongest: 8/12 passed. Football corners weak: 3/18 gate_score<10." |
| Stuck | Retry same command 3x | `sequentialthinking`: "Failed because X. Options: A, B, C. Picking A." |
| S2 = 0 tips | Continue blindly to S3 | **HARD STOP.** Web search tipsters → if still 0 → ask user. |

---

## Circuit Breakers (orchestrator MUST enforce)

| Condition | Action |
|-----------|--------|
| S2 returns 0 tips | **STOP.** Brave-search tipster sites. If still 0 → ask user before continuing. |
| S3 < 20 analyses | Wrong shortlist input. Verify file path. Re-run. |
| S7 < 5 approved | Re-run gate without `--strict`. |
| S8 = empty | Read gate_results — likely S7 rejected everything. |
| Any script timeout | `tail -20 /tmp/sN.txt`. If >50% done → proceed with partial. |

---

## Anti-Drift (detect in yourself → immediately stop and recover)

You are drifting if:
- You wrote a stat without a query to back it → **DELETE IT**
- Your output has >10 lines that look like terminal/JSON/logs → **STOP, summarize**
- You ran a script and are about to run the next without delegating → **STOP, delegate**
- You can't remember which step you're at → **read checkpoint**
- You ran `> /tmp/sN.txt` but then also piped output to chat → **FAILED**

Recovery: `sequentialthinking` → "Where am I? What did I just do? What's next?"

---

## Forbidden Actions

- `python3 -c "..."` (quoting breaks in fish)
- Running `--help` on any script
- `sqlite_list_tables` + describe loop (use sequentialthinking to recall schema)
- Bare `python3` or `pip`
- Pasting >10 lines of any tool output to the user
- Skipping delegation after a script run
- Continuing past S2=0 without user confirmation

<!-- BET:instruction:agent-execution-protocol:v12 -->
