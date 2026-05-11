# V5 Agent Protocol — Implementation Plan

**Version:** 1.0  
**Date:** 2026-05-11  
**Status:** DRAFT  
**Scope:** 6 improvements, 8 files modified/created, 0 new dependencies

---

## Overview

Upgrade the agent execution protocol from v4 (4-step cycle) to v5 (5-step cycle with VALIDATE), adding structured validation, reaction patterns, concrete THINK-WHILE-WAITING queries, pipeline inspection tooling, and data flow contracts.

**Design principles:**
- All changes are additive — existing scripts keep working identically
- Pre-checks warn via AgentOutput, never block execution
- No new dependencies — uses stdlib only (json, pathlib, sqlite3 via bet.db)
- No business logic changes — only validation/observability layered on top

---

## Phase 1: Foundation (agent_output.py + agent_protocol.py)

### Task 1.1 [MODIFY] `scripts/agent_output.py` — Add `validate_summary()`

**What:** Add a `@staticmethod validate_summary(payload)` method that checks AGENT_SUMMARY structure, and auto-call it inside `summary()` before emitting.

**Changes:**
1. Add `validate_summary(payload: dict) -> list[str]` static method after `summary()`:
   - Check `verdict` ∈ `{"OK", "PARTIAL", "FAILED"}` — if missing/invalid, return warning
   - Check `metrics` is a dict with ≥1 entry — if empty, return warning
   - Check `issues` is a list — if wrong type, return warning
   - Check `step` is a non-empty string — if missing, return warning
   - Returns list of validation warning strings (empty = all good)
2. In `summary()`, call `validate_summary(payload)` BEFORE the `print(f"\nAGENT_SUMMARY:...")` line:
   - If warnings returned, append each as `{"level": "validation_warning", "message": msg}` to `all_issues`
   - Never block, never raise — just add warnings to the output
   - This gives FREE validation to all 15 scripts without touching them

**Lines affected:** ~15 new lines after line 175 (after current `summary()` method), ~5 lines inserted inside `summary()` before the print statement.

**Risk:** LOW — additive static method + non-blocking warning injection. All 15 scripts get validation for free.

**Definition of done:**
- [ ] `validate_summary()` exists as static method on `AgentOutput`
- [ ] `summary()` calls `validate_summary()` and appends any warnings to issues
- [ ] Calling `summary(verdict="OK", metrics={}, issues=[])` produces a validation warning about empty metrics
- [ ] Calling `summary(verdict="INVALID")` produces a validation warning about invalid verdict
- [ ] Existing `summary()` calls with valid data produce zero validation warnings
- [ ] All existing tests pass unchanged

---

### Task 1.2 [MODIFY] `scripts/agent_output.py` — Add `validate_input_contract()`

**What:** Add a `@classmethod validate_input_contract(cls, step_id, date, contracts=None)` that checks whether expected input files/DB tables exist for a pipeline step.

**Changes:**
1. Add `validate_input_contract(cls, step_id: str, date: str, contracts: dict | None = None) -> dict` classmethod:
   - If `contracts` is None, lazy-import `DATA_FLOW_CONTRACTS` from `agent_protocol` (avoids circular import at module level)
   - Look up the contract for `step_id` in contracts dict
   - For each expected file path (with `{date}` substitution): check `Path.exists()`
   - For each expected DB table: try `SELECT COUNT(*) FROM {table} WHERE betting_date='{date}'` via `get_db()`
   - Return `{"status": "OK"|"PARTIAL"|"MISSING", "found": [...], "missing": [...], "warnings": [...]}`
   - On any exception (DB connection, import error): return `{"status": "UNKNOWN", "warnings": ["..."]}`
2. This method is called BY agents (or by scripts that opt in) — not auto-called in `summary()`

**Lines affected:** ~40 new lines after `validate_summary()`.

**Risk:** MEDIUM — lazy import of `agent_protocol` could fail if file has syntax errors. Mitigated by try/except returning UNKNOWN status. DB access is read-only, wrapped in try/except.

**Circular import mitigation:** `agent_output.py` does NOT import `agent_protocol` at module level. The import happens inside the method body only when `contracts=None`, making it a lazy/deferred import.

**Definition of done:**
- [ ] `validate_input_contract("s3_deep_stats", "2026-05-11")` returns status with found/missing lists
- [ ] Missing files produce `"MISSING"` or `"PARTIAL"` status
- [ ] DB connection failure produces `"UNKNOWN"` status (not crash)
- [ ] Method works without agent_protocol.py if `contracts` dict is passed explicitly
- [ ] No module-level import of agent_protocol in agent_output.py

---

### Task 1.3 [MODIFY] `scripts/agent_protocol.py` — Add `REACTION_PATTERNS`

**What:** Add `REACTION_PATTERNS` dict mapping failure scenarios to structured recovery actions.

**Changes:** Add after `ERROR_HANDLING_PROTOCOL` (around line 90):

```python
REACTION_PATTERNS = {
    "empty_output": {
        "trigger": "Script produces 0 candidates/events in output",
        "severity": "HIGH",
        "recovery": "Retry with alternative source or extended timeout. Check source_health DB.",
        "escalation": "If retry also empty → escalate to user with source health report",
    },
    "low_yield_below_40pct": {
        "trigger": "Enrichment/scan yield < 40% (enriched / attempted)",
        "severity": "MEDIUM",
        "recovery": "Trigger L3-L6 fallback enrichment for failed items. Try alternative sources.",
        "escalation": "If yield still < 20% after fallbacks → escalate to user",
    },
    "missing_sport": {
        "trigger": "Expected sport has 0 events in scan/shortlist",
        "severity": "HIGH",
        "recovery": "Re-scan that sport group only: scan_events.py --sport {sport}",
        "escalation": "If sport still missing after re-scan → check if season ended, inform user",
    },
    "exit_code_2": {
        "trigger": "Script exits with code 2 (critical failure)",
        "severity": "CRITICAL",
        "recovery": "STOP pipeline. Read error output. Do NOT retry blindly.",
        "escalation": "Immediate — show user the error and ask for guidance",
    },
    "agent_summary_missing": {
        "trigger": "Script output has no AGENT_SUMMARY: line",
        "severity": "HIGH",
        "recovery": "Script crashed before summary. Check exit code and last output lines.",
        "escalation": "If crash is in script logic → file bug. If data issue → fix data, retry.",
    },
    "data_quality_minimal_above_50pct": {
        "trigger": ">50% of candidates have MINIMAL data quality (<4/10)",
        "severity": "HIGH",
        "recovery": "Enrichment failure. Spawn web_research_agent (L7) for missing teams.",
        "escalation": "If still >50% minimal after L7 → inform user, proceed with warnings",
    },
    "odds_drift_above_8pct": {
        "trigger": "Odds drifted >8% between fetch and placement",
        "severity": "MEDIUM",
        "recovery": "Mandatory re-evaluation of EV. Recalculate with new odds.",
        "escalation": "If EV turns negative → move pick to extended pool, inform user",
    },
}
```

**Lines affected:** ~50 new lines.

**Risk:** LOW — pure data dict, no execution logic. Agents read this for guidance.

**Definition of done:**
- [ ] `REACTION_PATTERNS` dict exists in agent_protocol.py with 7 entries
- [ ] Each entry has: trigger, severity, recovery, escalation
- [ ] Severity values are: CRITICAL, HIGH, MEDIUM
- [ ] No code references `REACTION_PATTERNS` for automatic execution — it's advisory

---

### Task 1.4 [MODIFY] `scripts/agent_protocol.py` — Add `THINK_WHILE_WAITING_QUERIES`

**What:** Add per-agent concrete SQL queries and file reads for productive async work.

**Changes:** Add after `REACTION_PATTERNS`:

```python
THINK_WHILE_WAITING_QUERIES = {
    "bet-scanner": {
        "description": "While scan_events.py runs (~10 min), query previous scan data",
        "queries": [
            {
                "label": "Source health overview",
                "type": "sql",
                "query": "SELECT source_name, total_requests, total_failures, ROUND(total_failures*100.0/MAX(total_requests,1),1) as fail_pct FROM source_health ORDER BY total_requests DESC LIMIT 10",
            },
            {
                "label": "Previous scan sport distribution",
                "type": "sql",
                "query": "SELECT sport, COUNT(*) as cnt FROM scan_results WHERE betting_date='{date}' GROUP BY sport ORDER BY cnt DESC",
            },
            {
                "label": "Check scan errors from previous run",
                "type": "file",
                "path": "betting/data/scan_errors.json",
                "action": "Count entries, identify recurring blocked sources",
            },
        ],
    },
    "bet-enricher": { ... },  # 3-5 queries
    "bet-statistician": { ... },
    "bet-challenger": { ... },
    "bet-valuator": { ... },
    "bet-scout": { ... },
    "bet-builder": { ... },
}
```

(Full SQL queries as designed in thought 2 above — each agent gets 3-5 concrete tasks with actual SQL/file paths.)

**Lines affected:** ~120 new lines.

**Risk:** LOW — pure data dict. SQL queries use `{date}` placeholder that agents substitute. Queries are SELECT-only (read-only).

**Definition of done:**
- [ ] `THINK_WHILE_WAITING_QUERIES` dict exists with entries for all 7 specialist agents
- [ ] Each agent has 3-5 entries with label, type (sql/file), and query/path
- [ ] All SQL queries are SELECT-only (no INSERT/UPDATE/DELETE)
- [ ] SQL queries use `{date}` placeholder for date substitution
- [ ] File paths use `{date}` placeholder where needed

---

### Task 1.5 [MODIFY] `scripts/agent_protocol.py` — Add `DATA_FLOW_CONTRACTS`

**What:** Add step-to-step data flow contracts that define expected inputs and outputs.

**Changes:** Add after `THINK_WHILE_WAITING_QUERIES`:

```python
DATA_FLOW_CONTRACTS = {
    "s1_scan": {
        "produces": {
            "db": ["scan_results", "scan_run_stats", "source_health", "fixtures"],
            "files": ["betting/data/scan_summary.json", "betting/data/market_matrix_{date}.json"],
        },
        "required_keys": {
            "market_matrix_{date}.json": ["events"],
            "events[]": ["sport", "home_team", "away_team", "competition", "kickoff", "data_tier"],
        },
    },
    "s1e_shortlist": {
        "depends_on": "s1_scan",
        "requires": {
            "files": ["betting/data/market_matrix_{date}.json"],
            "db": [],  # reads market_matrix JSON, not DB
        },
        "produces": {
            "db": ["pipeline_runs"],
            "files": ["betting/data/{date}_s2_shortlist.json"],
        },
        "required_keys": {
            "{date}_s2_shortlist.json": ["candidates"],
            "candidates[]": ["sport", "home_team", "away_team", "competition", "kickoff"],
        },
    },
    "s2_5_enrich": {
        "depends_on": "s1e_shortlist",
        "requires": {
            "files": ["betting/data/{date}_s2_shortlist.json"],
            "db": [],
        },
        "produces": {
            "db": ["team_form"],
            "files": [],  # writes to stats_cache/{sport}/{slug}.json (dynamic paths)
        },
        "required_keys": {},
    },
    "s3_deep_stats": {
        "depends_on": "s2_5_enrich",
        "requires": {
            "files": ["betting/data/{date}_s2_shortlist.json"],
            "db": ["fixtures", "team_form"],
        },
        "produces": {
            "db": ["analysis_results", "analysis_raw_data"],
            "files": ["betting/data/{date}_s3_deep_stats.json"],
        },
        "required_keys": {
            "{date}_s3_deep_stats.json": ["analyses", "date", "total_candidates"],
            "analyses[]": ["home_team", "away_team", "sport", "has_data", "best_market_name", "best_safety_score", "ranking_result"],
        },
    },
    "s7_gate": {
        "depends_on": "s3_deep_stats",
        "requires": {
            "files": ["betting/data/{date}_s3_deep_stats.json"],
            "db": ["analysis_results"],
        },
        "produces": {
            "db": ["gate_results"],
            "files": ["betting/data/{date}_s7_gate_results.json"],
        },
        "required_keys": {
            "{date}_s7_gate_results.json": ["gate_results", "summary"],
            "gate_results": ["approved", "extended_pool", "rejected"],
        },
    },
    "s8_coupons": {
        "depends_on": "s7_gate",
        "requires": {
            "files": ["betting/data/{date}_s7_gate_results.json"],
            "db": ["gate_results"],
        },
        "produces": {
            "db": ["coupons", "bets", "decision_snapshots"],
            "files": [],  # writes to betting/coupons/{date}/ (dynamic)
        },
        "required_keys": {},
    },
}
```

**Lines affected:** ~80 new lines.

**Risk:** LOW — pure data dict. Must accurately reflect the actual data shapes verified from reading the 5 scripts. Inaccuracies would produce false warnings in inspect_pipeline.py, but never block execution.

**Definition of done:**
- [ ] `DATA_FLOW_CONTRACTS` dict exists with entries for: s1_scan, s1e_shortlist, s2_5_enrich, s3_deep_stats, s7_gate, s8_coupons
- [ ] Each entry has `produces` (db tables + files) and `requires` (db tables + files)
- [ ] File paths use `{date}` placeholder
- [ ] `required_keys` match actual JSON structures verified from code reading
- [ ] `depends_on` field links steps sequentially

---

## Phase 2: Tooling

### Task 2.1 [CREATE] `scripts/inspect_pipeline.py` — Pipeline Inspector CLI

**What:** New read-only CLI script that inspects pipeline state for a given step and date.

**Purpose:** Replaces complex `python3 -c "..."` one-liners that garble in fish terminal. Provides a clean, agent-friendly inspection tool.

**CLI interface:**
```
python3 scripts/inspect_pipeline.py --step s1|s1e|s2|s3|s7|s8 --date YYYY-MM-DD [--verbose]
```

**Design:**
1. Imports: `argparse`, `json`, `pathlib`, `sys`, `from bet.db.connection import get_db`, `from agent_output import AgentOutput, add_agent_args`, `from agent_protocol import DATA_FLOW_CONTRACTS`
2. Step handler dispatch: `STEP_HANDLERS = {"s1": inspect_s1, "s1e": inspect_s1e, ...}`
3. Each handler:
   - Reads the contract from `DATA_FLOW_CONTRACTS`
   - Checks input status (files exist? DB rows present?)
   - Checks output status (files exist? DB rows present?)
   - Prints key metrics (counts, quality indicators)
   - Emits AGENT_SUMMARY via AgentOutput

**Step handlers:**

| Step | Handler | Key metrics |
|------|---------|-------------|
| s1 | `inspect_s1()` | scan_results count by sport, source_health failures, fixture count |
| s1e | `inspect_s1e()` | shortlist candidate count, sport distribution, data tier breakdown |
| s2 | `inspect_s2()` | enrichment yield (team_form rows vs shortlist teams), per-sport coverage |
| s3 | `inspect_s3()` | analysis_results count, avg safety score, has_data ratio, data quality distribution |
| s7 | `inspect_s7()` | gate distribution (STRONG/MODERATE/WEAK/FLAGGED), approval rate, sport diversity |
| s8 | `inspect_s8()` | coupon count, total legs, stake allocation, risk tier distribution |

**Each handler pattern:**
```python
def inspect_s3(date: str, out: AgentOutput):
    contract = DATA_FLOW_CONTRACTS["s3_deep_stats"]
    
    # Check inputs
    input_status = AgentOutput.validate_input_contract("s3_deep_stats", date)
    
    # Check outputs
    metrics = {}
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM analysis_results WHERE betting_date=?", (date,)
        ).fetchone()
        metrics["analysis_count"] = row[0]
        # ... more queries
    
    # Check file output
    path = Path(f"betting/data/{date}_s3_deep_stats.json")
    metrics["output_file_exists"] = path.exists()
    
    out.summary(verdict=..., metrics=metrics)
```

**Lines:** ~250 lines.

**Risk:** MEDIUM — new script touching DB (read-only). Must handle missing tables gracefully (DB might not have all 28 tables populated). Mitigated by try/except per query.

**Definition of done:**
- [ ] `scripts/inspect_pipeline.py` exists and is executable
- [ ] `--step s1 --date 2026-05-11` produces structured output with scan metrics
- [ ] `--step s3 --date 2026-05-11` produces structured output with analysis metrics
- [ ] All 6 step handlers work (s1, s1e, s2, s3, s7, s8)
- [ ] Missing data produces informative output (not crashes)
- [ ] Emits `AGENT_SUMMARY:{json}` when `--verbose` is used
- [ ] Uses `from bet.db.connection import get_db` (R2 DB-FIRST)
- [ ] Exit code 0 for healthy state, 1 for partial/warnings, 2 for critical gaps

---

## Phase 3: Script Pre-checks (5 scripts)

All pre-checks follow the same pattern:
1. After `AgentOutput` is initialized and date is parsed
2. Before any business logic runs
3. Call `AgentOutput.validate_input_contract(step_id, date)`
4. If status is `"MISSING"`: emit `out.warning(...)` with details
5. Never block — script continues to its existing input loading logic

### Task 3.1 [MODIFY] `scripts/build_shortlist.py` — Pre-check for scan results

**What:** After line ~798 (after `out = AgentOutput(...)` and date parsing), add input contract validation.

**Pre-check logic:**
```python
# V5 input contract pre-check
_contract = AgentOutput.validate_input_contract("s1e_shortlist", date)
if _contract["status"] != "OK":
    for w in _contract.get("warnings", []):
        out.warning(f"Input contract: {w}")
    for m in _contract.get("missing", []):
        out.warning(f"Missing input: {m}")
```

**Lines affected:** ~6 new lines inserted after date validation (around line 800).

**Risk:** LOW — warning-only, never blocks. Existing `sys.exit(1)` on missing `market_matrix_{date}.json` (line 423) still handles the hard failure.

**Definition of done:**
- [ ] Running `build_shortlist.py --date 2026-05-11` when market_matrix exists: no extra warnings
- [ ] Running with missing market_matrix: pre-check warning emitted BEFORE the existing error
- [ ] Script still exits with existing error handling after pre-check

---

### Task 3.2 [MODIFY] `scripts/deep_stats_report.py` — Pre-check for shortlist/enrichment data

**What:** After `out = AgentOutput("s3_deep", ...)` (line ~1651), add input contract validation.

**Pre-check logic:** Same pattern as Task 3.1, using step_id `"s3_deep_stats"`.

**Lines affected:** ~6 new lines after line 1651.

**Risk:** LOW — warning-only. Existing logic in `generate_deep_stats()` already handles missing data gracefully (falls back to empty candidates list).

**Definition of done:**
- [ ] Running with valid shortlist and team_form data: no extra warnings
- [ ] Running with missing shortlist: pre-check warning emitted, script continues to its own fallback logic
- [ ] Pre-check reports missing team_form DB entries when relevant

---

### Task 3.3 [MODIFY] `scripts/gate_checker.py` — Pre-check for S3 deep stats output

**What:** After `out = AgentOutput("s7_gate", ...)` (line ~1608), add input contract validation.

**Pre-check logic:** Same pattern, using step_id `"s7_gate"`.

**Lines affected:** ~6 new lines after line 1608.

**Risk:** LOW — warning-only. Existing `_load_s3_output()` already handles missing data with `sys.exit(1)`.

**Definition of done:**
- [ ] Running with valid S3 output: no extra warnings
- [ ] Running with missing S3 output (no DB data, no JSON): pre-check warning, then existing exit
- [ ] Pre-check correctly reports both DB and file availability

---

### Task 3.4 [MODIFY] `scripts/coupon_builder.py` — Pre-check for S7 gate results

**What:** After `out = AgentOutput("s8_coupon", ...)` (line ~1928), add input contract validation.

**Pre-check logic:** Same pattern, using step_id `"s8_coupons"`.

**Lines affected:** ~6 new lines after line 1928.

**Risk:** LOW — warning-only. Existing code already has DB-first + JSON fallback + error handling for missing gate results.

**Definition of done:**
- [ ] Running with valid gate results: no extra warnings
- [ ] Running with missing gate results: pre-check warning before existing error handling

---

### Task 3.5 [MODIFY] `scripts/data_enrichment_agent.py` — Pre-check for shortlist (--date mode)

**What:** In the `elif args.date:` branch (line ~1908), add input contract validation before calling `_detect_missing_from_shortlist()`.

**Pre-check logic:** Same pattern, using step_id `"s2_5_enrich"`.

**Lines affected:** ~6 new lines after line 1908, before `missing = _detect_missing_from_shortlist(args.date)`.

**Risk:** LOW — warning-only. Existing `_detect_missing_from_shortlist()` already handles missing shortlist gracefully (returns empty list).

**Definition of done:**
- [ ] Running with valid shortlist: no extra warnings
- [ ] Running with missing shortlist: pre-check warning, then existing empty-list behavior

---

## Phase 4: Documentation

### Task 4.1 [MODIFY] `agent-execution-protocol.instructions.md` — Protocol v4 → v5

**What:** Update the protocol document to reflect all V5 changes.

**Changes:**

1. **Title:** `# Agent Execution Protocol v5` (already says v5 from header — verify and update version marker at bottom)

2. **4-step → 5-step cycle:** Rename section to "The 5-Step Cycle" and insert VALIDATE between EXTRACT and THINK:

   ```
   ### 2b. VALIDATE — Check output structure (NEW in v5)
   
   After extracting numbers, validate:
   1. AGENT_SUMMARY structure: `validate_summary()` auto-checks in every script (v5)
   2. Input contract: call `AgentOutput.validate_input_contract(step_id, date)` 
      before running the NEXT script to verify data handoff
   3. If validation warnings exist: note them in your THINK step
   
   Validation is ADVISORY — it adds warnings, never blocks the pipeline.
   The scripts themselves handle hard failures (exit codes, sys.exit).
   ```

3. **REACTION section:** Add after the 5-step cycle, before anti-patterns:

   ```
   ## Reaction Patterns
   
   When a script produces unexpected results, consult `REACTION_PATTERNS` in 
   `agent_protocol.py` for structured recovery guidance. Key patterns:
   
   | Trigger | Severity | Action |
   |---------|----------|--------|
   | Empty output (0 events) | HIGH | Retry with alt source, check source_health |
   | Yield < 40% | MEDIUM | Trigger L3-L6 fallback enrichment |
   | Missing sport | HIGH | Re-scan that sport: `--sport {sport}` |
   | Exit code 2 | CRITICAL | STOP pipeline, escalate to user |
   | No AGENT_SUMMARY line | HIGH | Script crashed — check exit code |
   | >50% MINIMAL quality | HIGH | Spawn web_research_agent (L7) |
   | Odds drift >8% | MEDIUM | Mandatory EV re-evaluation |
   ```

4. **THINK-WHILE-WAITING concrete queries:** In the existing per-agent table, add a note:

   ```
   For concrete SQL queries and file reads per agent, see 
   `THINK_WHILE_WAITING_QUERIES` in `scripts/agent_protocol.py`.
   ```

5. **Data Flow Verification section:** Expand existing R18 section with:

   ```
   V5 adds programmatic enforcement via `DATA_FLOW_CONTRACTS` in `agent_protocol.py` 
   and `validate_input_contract()` in `agent_output.py`. Use `inspect_pipeline.py` 
   for quick state checks instead of complex inline Python.
   ```

6. **Version marker:** Update bottom marker from `v3` to `v5`:
   ```
   <!-- BET:instruction:agent-execution-protocol:v5 -->
   ```

**Lines affected:** ~40 lines modified/added across the document.

**Risk:** LOW — documentation only. No runtime impact.

**Definition of done:**
- [ ] Title confirms "v5"
- [ ] 5-step cycle documented with VALIDATE step between EXTRACT and THINK
- [ ] REACTION section exists with table referencing REACTION_PATTERNS
- [ ] THINK-WHILE-WAITING references THINK_WHILE_WAITING_QUERIES
- [ ] R18 section references DATA_FLOW_CONTRACTS and inspect_pipeline.py
- [ ] Version marker at bottom reads `v5`

---

## Dependency Graph

```
Phase 1 (Foundation) ─── all tasks parallelizable within phase
  ├── Task 1.1: agent_output.py validate_summary()
  ├── Task 1.2: agent_output.py validate_input_contract()  ←── needs Task 1.5 (DATA_FLOW_CONTRACTS)
  ├── Task 1.3: agent_protocol.py REACTION_PATTERNS
  ├── Task 1.4: agent_protocol.py THINK_WHILE_WAITING_QUERIES
  └── Task 1.5: agent_protocol.py DATA_FLOW_CONTRACTS

Phase 2 (Tooling) ─── depends on Phase 1
  └── Task 2.1: inspect_pipeline.py  ←── imports DATA_FLOW_CONTRACTS + validate_input_contract()

Phase 3 (Script Pre-checks) ─── depends on Task 1.2
  ├── Task 3.1: build_shortlist.py
  ├── Task 3.2: deep_stats_report.py
  ├── Task 3.3: gate_checker.py       ←── all 5 parallelizable
  ├── Task 3.4: coupon_builder.py
  └── Task 3.5: data_enrichment_agent.py

Phase 4 (Documentation) ─── depends on all above
  └── Task 4.1: agent-execution-protocol.instructions.md
```

**Recommended execution order:**
1. Task 1.5 → Task 1.1 → Task 1.2 (agent_output depends on contracts for lazy import)
2. Tasks 1.3 + 1.4 (can run in parallel with above)
3. Task 2.1 (depends on 1.2 + 1.5)
4. Tasks 3.1–3.5 (all parallel, depend on 1.2)
5. Task 4.1 (last — documents everything)

---

## Risk Assessment Summary

| Task | Risk | Rationale |
|------|------|-----------|
| 1.1 validate_summary() | LOW | Additive static method, non-blocking warnings |
| 1.2 validate_input_contract() | MEDIUM | Lazy import of agent_protocol, DB access — mitigated by try/except |
| 1.3 REACTION_PATTERNS | LOW | Pure data dict, advisory only |
| 1.4 THINK_WHILE_WAITING_QUERIES | LOW | Pure data dict, SELECT-only SQL |
| 1.5 DATA_FLOW_CONTRACTS | LOW | Pure data dict, must match actual code (verified) |
| 2.1 inspect_pipeline.py | MEDIUM | New script with DB access — mitigated by read-only, per-query try/except |
| 3.1–3.5 Script pre-checks | LOW | Warning-only, 6 lines each, never block execution |
| 4.1 Protocol docs | LOW | Documentation only |

**Overall risk:** LOW-MEDIUM. All changes are additive. No existing behavior modified. Pre-checks are warning-only. DB access is read-only. Worst case: a validation warning is incorrect (false positive), which agents can ignore.

---

## Files Changed Summary

| File | Action | Phase | Lines ±  |
|------|--------|-------|----------|
| `scripts/agent_output.py` | MODIFY | 1 | +60 |
| `scripts/agent_protocol.py` | MODIFY | 1 | +250 |
| `scripts/inspect_pipeline.py` | CREATE | 2 | +250 |
| `scripts/build_shortlist.py` | MODIFY | 3 | +6 |
| `scripts/deep_stats_report.py` | MODIFY | 3 | +6 |
| `scripts/gate_checker.py` | MODIFY | 3 | +6 |
| `scripts/coupon_builder.py` | MODIFY | 3 | +6 |
| `scripts/data_enrichment_agent.py` | MODIFY | 3 | +6 |
| `.github/instructions/agent-execution-protocol.instructions.md` | MODIFY | 4 | +40 |

**Total:** 9 files, ~630 lines added, 0 lines removed, 0 new dependencies.
