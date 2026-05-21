# Pipeline Errors — 2026-05-21

## Error #1: Orchestrator skipped subagent delegation after enrichment (and possibly other steps)

**Symptom:** After running `data_enrichment_agent.py`, the orchestrator summarized the output itself and moved directly to S3 without calling `runSubagent("bet-enricher")`. Same pattern may have occurred for other steps.

**Root Cause:** No mechanical enforcement existed to prevent the orchestrator from skipping delegation. Rules said "MUST delegate" but there was no hard gate preventing the next step from launching.

**Fix Applied:**
1. Added **R20 — NO STEP WITHOUT VERDICT** to `bet-orchestrator.agent.md`:
   - New rule in MY RULES table (boot sequence)
   - New rule in Rules (R1-R20) table
   - New §MANDATORY DELEGATION MAP — explicit script→agent mapping table
   - New Behavioral Mandate #5
   - New Anti-Pattern #11 ("Run script → summarize → move on")
   - Updated Self-Audit to explicitly check R20 per-script
2. Added **8 inline `⛔ DELEGATION GATE (R20)` markers** in `orchestrate-betting-day.prompt.md`:
   - After S2 (bet-scout)
   - After S2.3 (bet-enricher for scrapers)
   - After S2.5 (bet-enricher for enrichment)
   - After S3 (bet-statistician)
   - After S4 (bet-valuator)
   - After S5+S6 (bet-challenger)
   - After S7 (bet-challenger)
   - After S8+S9 (bet-builder)
3. Updated **§DELEGATION COMPLIANCE GATE** rules in the prompt:
   - Added rule #5: "Before launching ANY new script, check if previous row has ☑ Agent Delegated"
   - Added explicit R20 violation example: "The enrichment output looks straightforward, I'll just note it and move on to S3" — NO.

**NEVER REPEAT:**
- Running any analytical script and proceeding without `runSubagent` call to the mapped specialist agent
- Self-summarizing script output instead of delegating
- Saying "looks good, moving on" without specialist verdict
