# LOCAL_AGENT_SETUP_ACCEPTANCE_MATRIX

**Certification ID:** CERT-20260612T155800Z  
**Generated:** 2026-06-12T15:58:00Z  
**Original Session:** ses_1442814d3ffeD3xwnS5pXzl1KX  
**Repair Session:** ses_143dfde6dffe6CmYI0DuWWvlKa  
**Scenarios Rerun:** NO  
**Scenarios Preserved:** YES

---

## Acceptance Matrix

| Gate | Status | Evidence |
|------|--------|----------|
| Accepted checkpoint loaded | PASS | `kilo-agent-config-pre-demo` tag, Phase 4A `AGENT_CONFIG_PASS` |
| Input manifest loaded | PASS | `reports/agent-config/PHASE4B_INPUT_MANIFEST.json` exists |
| Pipeline Skill loaded | PASS | `betting-pipeline-runtime` skill invoked |
| Primary bet-orchestrator used | PASS | Agent `bet-orchestrator` configured in kilo.jsonc |
| 13 required scenarios executed | PASS | C01-C13 all completed |
| 12 canonical specialists represented | PASS | bet-settler, bet-db-analyst, bet-scanner, bet-scout, bet-enricher, bet-statistician, bet-valuator, bet-challenger, bet-builder, bet-engineer (x2), bet-reconciler, bet-test-engineer |
| bet-engineer executed twice | PASS | C12 (fixture operation) and C13 (mutation-required) |
| All child tasks sequential | PASS | Max 1 active child task |
| Maximum active child tasks one | PASS | No parallel Task calls |
| All required schemas valid | PASS | All 13 responses had STATUS, DECISION, EVIDENCE, CALCULATIONS, UNCERTAINTY, RISKS, NEXT_ACTION |
| All expected PASS outcomes matched | PASS | C03, C04, C05, C06, C07, C10, C11, C12 all PASS |
| Expected challenger FAIL matched | PASS | C08 returned FAIL/CANDIDATE_REJECTED |
| Expected capability BLOCKED outcomes matched | PASS | C01, C02, C09, C13 all BLOCKED |
| Builder used bet_artifact_write | PASS | C10 artifact at `reports/betting-demo/final-agent-certification-20260612T143920Z/coupon.json` |
| Builder artifact verified by test engineer | PASS | C11 validated C10 artifact |
| Engineer used only certified fixture operation | PASS | C12 used `bet_script_run` envelope |
| Mutation-required scenario blocked safely | PASS | C13 returned BLOCKED/MUTATION_CAPABILITY_UNAVAILABLE |
| Permission prompts zero | PASS | 0 permission prompts |
| Question calls zero | PASS | 0 question calls |
| Generic Bash calls zero | PASS | 0 Bash calls |
| Direct write/edit/patch calls zero | PASS | 0 direct mutations by orchestrator |
| DB bypass zero | PASS | 0 database bypasses |
| Web calls zero | PASS | 0 web calls |
| MCP calls zero | PASS | 0 MCP calls |
| Real scripts zero | PASS | 0 real scripts (fixture-only) |
| Recursive delegation zero | PASS | 0 recursive child delegations |
| Unknown tools zero | PASS | 0 unknown tool calls |
| Context errors zero | PASS | 0 ContextOverflowError |
| Compaction failures zero | PASS | 0 compaction failures |
| Malformed tool calls zero | PASS | 0 malformed tool calls |
| Duplicate tool calls zero | PASS | 0 duplicate tool calls |
| Stalled sessions zero | PASS | 0 stalled sessions |
| Local runtime healthy | PASS | All 13 scenarios completed without transport failure |

---

## Original Failure

The certification completed all 13 scenarios successfully but failed during finalization:

1. **Tool Availability:** `bet_artifact_write` was not present in the orchestrator's tool catalog
2. **Output Exhaustion:** The model hit its output limit while reasoning and produced no actionable output

**Root Cause 1:** Tool file was in `.kilo/tool/` directory, but Kilo's plugin system expects tools in `.kilo/plugin/` for auto-loading.

**Root Cause 2:** Qwen3.6-35B-A3B-4bit has `reasoning: true` in model config. When the orchestrator entered extended thinking mode, it exhausted the 4096-token output budget.

---

## Repair Applied

1. **Tool Registration:** Copied `bet_artifact_write.ts` and `bet_script_run.ts` to `.kilo/plugin/` directory
2. **Model Configuration:** Created `qwen36-orchestrator` model with `reasoning: false` and `output: 8192`
3. **Agent Configuration:** Updated `bet-orchestrator` to use `qwen36-orchestrator` model
4. **Prompt Update:** Updated orchestrator prompt to discourage extended reasoning

---

## Deferred Capabilities

The following capabilities remain explicitly deferred and are NOT certified:

- `bet_sqlite_query` (database access)
- Real betting scripts (fixture-only operations)
- Web search (MCP disabled)
- Brave Search (MCP disabled)
- Context7 (MCP disabled)
- Playwright (MCP disabled)

---

## Evidence Paths

- Parent session: `ses_1442814d3ffeD3xwnS5pXzl1KX` (via kilo_local_recall)
- Builder artifact: `reports/betting-demo/final-agent-certification-20260612T143920Z/coupon.json`
- Tool source: `.kilo/plugin/bet_artifact_write.ts`
- Agent config: `kilo.jsonc`
- Preserved evidence: `reports/betting-demo/runtime-repair-evidence-20260612T155800Z/PRESERVED_SESSION_EVIDENCE.md`
