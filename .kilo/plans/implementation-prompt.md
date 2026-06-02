# IMPLEMENTATION PROMPT — Betting Pipeline Kilo Code Refactoring

You are an IMPLEMENTATION AGENT. Your job is to execute the plan exactly as specified at:

**PLAN:** `.kilo/plans/final-comprehensive-plan.md`  
**READ THE PLAN FIRST.** Every phase, every fix, every test is documented there. This prompt summarizes the execution order and critical rules — but the PLAN is authoritative.

---

## ⛔ CRITICAL RULES (break any = restart)

1. **Phase 0 (BACKUP) is MANDATORY.** Do NOT proceed past Phase 0 without verifying backup exists.
2. **Follow M0→M1→M2→...→M10 in order.** Never reorder phases.
3. **After EVERY phase, write a CHECKPOINT line.** If you get interrupted, resume from the last CHECKPOINT.
4. **Before ANY `rm` (Phase D), run D0 verification.** D0 is your safety net.
5. **Use FISH SHELL only.** No bash. `set -x VAR value`, `env VAR=val cmd`, NOT `VAR=val cmd`.
6. **All Python: `.venv/bin/python3`** — NEVER bare `python3`.
7. **After every script/tool call: <think> what you learned, then proceed.**
8. **If a file is MISSING (grep returns null, cp fails) → STOP, report, do NOT proceed.**
9. **Token budget target: system prompt < 10,000 tokens total.**

---

## EXECUTION ORDER (summary — plan has details)

```
🟢 M0:  PRE-FLIGHT — verify scripts/ exist + .venv/bin/python3 exists
🔴 M1:  BACKUP     — git commit + cp -r /tmp/  [CHECKPOINT]
🟢 M2:  COPY RULES — 8 agent-rule files → .kilo/docs/agent-rules/
🟢 M3:  COPY COMPACT — 4 compact files → .kilo/docs/
🟡 M4:  FIX RUNBOOK — copy execution-spine.md, THEN fix: 37 PYTHONPATH→env, new_task→task, add date vars, remove python3 -c
🟡 M5:  CREATE execution-core.md, execution-protocol.md
🟡 M6:  ADD hallucination prevention to analysis-methodology.md
🟡 M7:  COPY memory files + merge betting-preferences
🟡 M8:  REFERENCE INTEGRITY CHECK — grep all paths in kilo.jsonc, verify they exist [CRITICAL GATE]
🟡 M9:  UPDATE KILOJSONC — 12 fixes + steps + browser + instructions per agent [CHECKPOINT]
🟡 M10: FIX server script — --max-tokens 16384
🟡 M11: FIX global config — model name
🟢 M12: REMOVE .kilocode/mcp.json (MCP dedup)
🟡 M13: VERIFY no .github/ refs in kilo.jsonc
🟡 M14: TRIM 11 PROMPTS — -40/55% each, fix orchestrator sequentialthinking policy [CHECKPOINT]
🔴 M15: D0 PRE-DELETION CHECK — verify ALL new files exist, verify backup [CRITICAL GATE]
🔴 M16: DELETE — rm -rf .github/ .roo/ .roomodes .clinerules .vscode/mcp.json .continuerc.json [CHECKPOINT]
🟢 M17: CONSISTENCY — fix AGENTS.md (3 lines), fix anti-drift-protocol.md (3 lines), grep for deprecated refs [CHECKPOINT]
🟢 M18: TEST SUITE — T1 through T8 [CHECKPOINT]
🟢 M19: MONITOR — 2-3 pipeline runs
```

---

## PER-PHASE GUIDANCE

### M4 — Fixing execution-spine (37 occurrences!)

Use `edit` tool with `replaceAll: true` for these replacements in `.kilo/docs/orchestrator-runbook.md`:

```
replaceAll: "PYTHONPATH=src .venv/bin/python3" → "env PYTHONPATH=src .venv/bin/python3"
replaceAll: "PYTHONPATH=src python3" → "env PYTHONPATH=src .venv/bin/python3"
replace: "new_task" → "task" (line ~347)
replace: the python3 -c verify block → sqlite_read_query call
```

Then INSERT date variables header after `## HOW TO READ THIS FILE`.

### M9 — Updating kilo.jsonc (12 fixes across 428 lines!)

Be VERY careful with JSONC structure. Key changes:
- `mcp.sequentialthinking.enabled`: false→true
- `mcp.sequentialthinking.timeout`: 120000→300000
- brave-search timeout: 25000→45000
- model.limit: 8192→16384
- compaction.reserved: 14000→18432
- experimental.mcp_timeout: 30000→60000
- tool_output max_lines: 100→200, max_bytes: 16384→32768
- model names: "qwen3.6-35b-a3b"→"qwen3.6-35b"
- ALL agent `steps` values
- ALL agent `instructions` arrays
- ALL agent `browser` permissions
- ALL agent `.github/instructions/` → `.kilo/docs/...` paths

### M14 — Trimming prompts

For EACH of the 11 .kilo/prompts/*.md files:
1. Read the file
2. Identify what to KEEP (use target sizes from plan)
3. Remove everything else
4. Write trimmed version
5. **For bet-orchestrator.md: change sequentialthinking policy from BANNED to ALLOWED (see plan C3)**

### 🔴 M15-M16 — DELETION (most dangerous phase)

DO NOT SKIP D0. Run ALL 9 file existence checks + grep for .github/ refs FIRST.
ONLY if ALL pass → proceed to rm commands.
After each rm, verify with `test -e`.

---

## WHAT SUCCESS LOOKS LIKE

After M18, you will have:
- ✅ All 8 tests (T1-T8) passing
- ✅ No .github/ .roo/ .roomodes .clinerules .continuerc.json on disk
- ✅ Sequentialthinking MCP enabled and responding
- ✅ Model output limit = 16384 (matches server)
- ✅ Compaction math correct (reserved=18432)
- ✅ All prompts trimmed 40-55%
- ✅ Token budget < 10,000
- ✅ Default agent = bet-orchestrator
- ✅ All references in kilo.jsonc resolve to existing files
- ✅ Fish syntax in all runbook commands
- ✅ Delegation uses `task` (not `runSubagent` or `new_task`)

---

## RECOVERY

If you get stuck or interrupted:
1. Find the last CHECKPOINT
2. Resume from the phase AFTER that checkpoint
3. If Phase D was interrupted MID-DELETION → check what was already deleted, what remains. Re-run D0 before continuing.

---

## START

Begin by reading `.kilo/plans/final-comprehensive-plan.md` fully. Then execute M0.
