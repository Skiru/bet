# Pipeline Refactoring — Implementation Plan

**Date:** 2026-05-08  
**Input:** `pipeline-audit.research.md` (full codebase analysis of 60+ files, ~42,500 lines)  
**Goal:** Clean up dead code, consolidate definitions, extract God Object, enable agent-driven flow, improve pipeline reliability, add tests  
**Principle:** Each phase is independently deployable. No over-engineering. Practical changes only.

---

## Phase 1: Dead Code Cleanup

**Risk: LOW** — Removing files that are never imported or executed by the active pipeline.  
**Prerequisite:** None  
**Estimated scope:** ~20 file deletions, 0 logic changes to active code

### 1.1 Delete Dead Scripts

- [x] **[DELETE]** `scripts/build_s1s2_shortlist.py`
  - **Reason:** Hardcoded `DATE = '2026-05-07'` and absolute paths. One-time throwaway.
  - **Verification:** `grep -r "build_s1s2_shortlist" scripts/ src/ tests/` returns no imports.
  - **Definition of done:** File removed; no remaining references anywhere in repo.

- [x] **[DELETE]** `scripts/espn_deep_analysis.py`
  - **Reason:** Hardcoded team IDs and sport leagues. One-off debug script, not parameterized.
  - **Verification:** Not imported or called by any other file.
  - **Definition of done:** File removed; no remaining references.

- [x] **[DELETE]** `scripts/historical_learning.py`
  - **Reason:** CSV-based historical learning, fully superseded by `analyze_betclic_learning.py` + DB.
  - **Verification:** Not imported by any active script.
  - **Definition of done:** File removed; no remaining references.

- [x] **[DELETE]** `scripts/run_full_scan_and_prepare.sh`
  - **Reason:** Legacy bash orchestrator, fully superseded by `pipeline_orchestrator.py`.
  - **Verification:** Not referenced by any active code (only in `copilot-instructions.md` as historical context).
  - **Definition of done:** File removed; update `copilot-instructions.md` scripted workflow section to reference `pipeline_orchestrator.py` instead.

- [x] **[DELETE]** `scripts/run_session.sh`
  - **Reason:** Legacy session runner, fully superseded by `pipeline_orchestrator.py`.
  - **Verification:** Not referenced by any active code.
  - **Definition of done:** File removed.

### 1.2 Delete Unused `src/bet/` Package Modules

**Context:** `scripts/` is the active codebase. `src/bet/` contains a partial clean rewrite that was never activated. Active parts of `src/bet/` that MUST be kept:
- `src/bet/db/` — used by 15+ scripts (connection, repositories, models, schema, migrations)
- `src/bet/api_clients/` — used by `fetch_api_stats.py`, `fetch_espn_odds.py`, `seed_espn_data.py`
- `src/bet/stats/market_ranking.py` — will become canonical definition source (Phase 2)
- `src/bet/stats/enrichment.py` — used by tests; evaluate retention in Phase 6
- `src/bet/__init__.py` — package root

**Files to delete:**

- [x] **[DELETE]** `src/bet/pipeline/orchestrator.py`
  - **Reason:** 200-line unused rewrite. Real orchestrator is `scripts/pipeline_orchestrator.py` (2,500 lines).
  - **Definition of done:** File removed.

- [x] **[DELETE]** `src/bet/pipeline/progress.py`
  - **Reason:** Only used by the unused package orchestrator.
  - **Definition of done:** File removed.

- [x] **[DELETE]** `src/bet/pipeline/__init__.py`
  - **Reason:** Empty init for removed package.
  - **Definition of done:** Directory removed.

- [x] **[DELETE]** `src/bet/coupon/builder.py`
  - **Reason:** ~100-line duplicate of `scripts/coupon_builder.py` (~500 lines). Never called by pipeline.
  - **Definition of done:** File removed.

- [x] **[DELETE]** `src/bet/coupon/shopping_list.py`
  - **Reason:** Unused by pipeline.
  - **Definition of done:** File removed.

- [x] **[DELETE]** `src/bet/coupon/__init__.py`
  - **Reason:** Empty init for removed package.
  - **Definition of done:** Directory removed.

- [x] **[DELETE]** `src/bet/scanner/discovery.py`
  - **Reason:** Duplicates `scripts/discover_fixtures.py`. Not called by pipeline.
  - **Definition of done:** File removed.

- [x] **[DELETE]** `src/bet/scanner/odds_fetcher.py`
  - **Reason:** Only used by unused package orchestrator.
  - **Definition of done:** File removed.

- [x] **[DELETE]** `src/bet/scanner/playwright_pool.py`
  - **Reason:** Only used by unused package orchestrator.
  - **Definition of done:** File removed.

- [x] **[DELETE]** `src/bet/scanner/__init__.py`
  - **Reason:** Empty init for removed package.
  - **Definition of done:** Directory removed.

- [x] **[DELETE]** `src/bet/settlement/settler.py`
  - **Reason:** DB-based settler, never called. `scripts/settle_on_finish.py` is the active one.
  - **Definition of done:** File removed.

- [x] **[DELETE]** `src/bet/settlement/learning.py`
  - **Reason:** DB-based learning, never called.
  - **Definition of done:** File removed.

- [x] **[DELETE]** `src/bet/settlement/__init__.py`
  - **Reason:** Empty init for removed package.
  - **Definition of done:** Directory removed.

- [x] **[DELETE]** `src/bet/cli.py`
  - **Reason:** CLI entry point, never used. Pipeline uses `scripts/pipeline_orchestrator.py` directly.
  - **Definition of done:** File removed.

- [x] **[DELETE]** `src/bet/__main__.py`
  - **Reason:** Package runner, never used.
  - **Definition of done:** File removed.

- [x] **[DELETE]** `src/bet/adapters/betexplorer.py`, `src/bet/adapters/flashscore.py`, `src/bet/adapters/scores24.py`, `src/bet/adapters/__init__.py`
  - **Reason:** Duplicate of `scripts/adapters/`. Never called by pipeline.
  - **Definition of done:** Directory removed.

- [x] **[DELETE]** `src/bet/utils/odds.py`, `src/bet/utils/team_names.py`, `src/bet/utils/__init__.py`
  - **Reason:** `scripts/utils.py` has its own implementations. These are unused.
  - **Definition of done:** Directory removed.

- [x] **[DELETE]** `src/bet/stats/safety_scores.py`
  - **Reason:** DB-model implementation, never called. `scripts/compute_safety_scores.py` is the active one.
  - **Definition of done:** File removed.

- [ ] **[DELETE]** `src/bet/config.py`
  - **Reason:** Config loader only used by deleted package modules and some tests.
  - **Dependency:** Tests (`conftest.py`, `test_pipeline.py`, `test_data_gate.py`) import `BettingConfig` from here. These tests are testing the deleted package code and will be updated in Phase 6.
  - **Definition of done:** File removed. Tests that import it are temporarily broken (fixed in Phase 6).

> **Note on `src/bet/coupon/translations.py`:** Do NOT delete in Phase 1. It will be consolidated into `src/bet/stats/market_ranking.py` in Phase 2, then deleted.

### 1.3 Phase 1 Validation

- **Definition of done for Phase 1:**
  1. All listed files are deleted and committed.
  2. `python3 scripts/pipeline_orchestrator.py --status` runs without import errors.
  3. `python3 -c "from bet.db.connection import get_db; from bet.db.repositories import SportRepo"` succeeds.
  4. `python3 -c "from bet.api_clients.espn_stats import ESPNStatsClient"` succeeds.
  5. `grep -r "build_s1s2_shortlist\|espn_deep_analysis\|historical_learning\|run_full_scan\|run_session" scripts/ src/` returns no active imports (only potential references in docs/comments, which are acceptable).

---

## Phase 2: Consolidate Definitions

**Risk: MEDIUM** — Changing import paths across many files. Regression risk if any import is missed.  
**Prerequisite:** Phase 1 complete  
**Estimated scope:** 1 file modified as canonical source, ~8 files updated to import from it, 2 files removed

### 2.1 Establish Canonical Market Definitions

- [x] **[MODIFY]** `src/bet/stats/market_ranking.py` — **THE canonical source**
  - **Current state:** Already contains `SPORT_MARKETS`, `SPORT_STAT_KEYS`, `STANDARD_MARKET_LINES`.
  - **Action:** Add `MARKET_PL` dict (currently in `scripts/coupon_builder.py` and `src/bet/coupon/translations.py`). Ensure all entries are the union of both existing copies.
  - **Why this file:** It's in the installed `bet` package, already imported by `src/bet/db/repositories.py`. Scripts already import from `bet.*` for DB access, so importing from `bet.stats.market_ranking` requires no new infrastructure.
  - **Definition of done:** `market_ranking.py` contains `SPORT_MARKETS`, `SPORT_STAT_KEYS`, `STANDARD_MARKET_LINES`, and `MARKET_PL` — all as the single source of truth. No other file defines these dicts.

### 2.2 Remove Duplicate Definitions

- [x] **[MODIFY]** `scripts/normalize_stats.py`
  - **Current state:** Defines its own `SPORT_MARKETS` (line 334) and `SPORT_STAT_KEYS`.
  - **Action:** Remove inline definitions. Add `from bet.stats.market_ranking import SPORT_MARKETS, SPORT_STAT_KEYS`.
  - **Affected files:** `scripts/generate_market_matrix.py`, `scripts/fetch_api_stats.py` (already import from `normalize_stats`; they'll get the re-exported symbols or import directly from canonical).
  - **Definition of done:** `normalize_stats.py` no longer defines `SPORT_MARKETS` or `SPORT_STAT_KEYS`; imports them from `bet.stats.market_ranking`.

- [x] **[MODIFY]** `scripts/generate_market_matrix.py`
  - **Current state:** Defines its own `STANDARD_MARKET_LINES` (line ~42 area) and imports `SPORT_MARKETS` from `normalize_stats`.
  - **Action:** Remove inline `STANDARD_MARKET_LINES`. Import `STANDARD_MARKET_LINES` and `SPORT_MARKETS` from `bet.stats.market_ranking`.
  - **Definition of done:** No local definition of `STANDARD_MARKET_LINES`; imports from canonical source.

- [x] **[MODIFY]** `scripts/coupon_builder.py`
  - **Current state:** Defines its own `MARKET_PL` dict (line 33).
  - **Action:** Remove inline `MARKET_PL`. Import from `bet.stats.market_ranking`.
  - **Definition of done:** No local definition of `MARKET_PL`; imports from canonical source.

- [x] **[DELETE]** `src/bet/coupon/translations.py`
  - **Reason:** `MARKET_PL` now lives in `bet.stats.market_ranking`. This file is redundant.
  - **Definition of done:** File removed. No imports reference it.

### 2.3 Standardize Field Names

- [x] **[MODIFY]** Standardize `home_team`/`away_team` across all scripts
  - **Current state:** Some scripts use `home_team`/`away_team`, others use `home`/`away`. This causes defensive `.get("home_team") or .get("home")` patterns.
  - **Action:** Audit and fix to consistently use `home_team`/`away_team` in all JSON structures. Specifically check:
    - `scripts/aggregate_and_select.py`
    - `scripts/build_shortlist.py`
    - `scripts/deep_analysis_pool.py`
    - `scripts/generate_market_matrix.py`
    - `scripts/deep_stats_report.py`
    - `scripts/pipeline_orchestrator.py` (inline S2, S4, S5, S6 code)
  - **Definition of done:** `grep -rn '\.get("home")' scripts/ | grep -v home_team` returns no results in pipeline-critical scripts. All JSON outputs use `home_team`/`away_team`.

### 2.4 Standardize Date Format

- [x] **[MODIFY]** `scripts/build_shortlist.py`
  - **Current state:** Writes `{YYYYMMDD}_s2_shortlist.json` (no dashes). Orchestrator has fallback code for both formats.
  - **Action:** Change output filename to `{YYYY-MM-DD}_s2_shortlist.json` to match all other dated files.
  - **Definition of done:** Shortlist file uses `YYYY-MM-DD` format. Remove the dash/no-dash fallback code from `pipeline_orchestrator.py`.

- [x] **[MODIFY]** `scripts/pipeline_orchestrator.py`
  - **Action:** Remove the shortlist filename fallback logic (try both date formats). After 2.4 above, only one format exists.
  - **Definition of done:** No fallback filename patterns for shortlist.

### 2.5 Phase 2 Validation

- **Definition of done for Phase 2:**
  1. `python3 -c "from bet.stats.market_ranking import SPORT_MARKETS, SPORT_STAT_KEYS, STANDARD_MARKET_LINES, MARKET_PL"` succeeds.
  2. `grep -rn "^SPORT_MARKETS\s*=" scripts/` returns 0 results (no local definitions).
  3. `grep -rn "^MARKET_PL\s*=" scripts/` returns 0 results.
  4. `grep -rn "^STANDARD_MARKET_LINES\s*=" scripts/` returns 0 results.
  5. Pipeline dry-run (`python3 scripts/pipeline_orchestrator.py --date 2026-05-08 --status`) succeeds.
  6. All dated output files use `YYYY-MM-DD` format consistently.

---

## Phase 3: Extract Orchestrator

**Risk: MEDIUM** — Extracting inline code into modules. Logic must be identical; only the location changes.  
**Prerequisite:** Phase 2 complete (consolidated imports are stable)  
**Estimated scope:** 5 new files created, `pipeline_orchestrator.py` reduced from ~2,500 to ~1,200 lines

### 3.1 Extract S4 Odds Evaluation

- [x] **[CREATE]** `scripts/odds_evaluator.py`
  - **Content:** Extract from `pipeline_orchestrator.py`:
    - `_convert_espn_odds_to_decimal()` (line 463, ~60 lines)
    - `_inject_ev_from_odds()` (line 521, ~250 lines)
    - `_run_odds_eval()` (line 944, ~70 lines)
  - **Interface:** `run_odds_eval(date: str, state: dict) -> tuple[bool, str]` — same signature as current inline function.
  - **Definition of done:** `odds_evaluator.py` passes `python3 -c "from odds_evaluator import run_odds_eval"`. Orchestrator imports and calls it. Pipeline output identical to before extraction.

- [x] **[MODIFY]** `scripts/pipeline_orchestrator.py`
  - **Action:** Remove `_convert_espn_odds_to_decimal`, `_inject_ev_from_odds`, `_run_odds_eval`. Add `from odds_evaluator import run_odds_eval as _run_odds_eval`.
  - **Definition of done:** No odds-related logic remains inline in orchestrator.

### 3.2 Extract S5/S6 Context and Upset Risk

- [x] **[CREATE]** `scripts/context_checks.py`
  - **Content:** Extract `_run_context_checks()` (line 1015, ~100 lines) from orchestrator.
  - **Interface:** `run_context_checks(date: str, state: dict) -> tuple[bool, str]`
  - **Definition of done:** Module importable, orchestrator calls it, output identical.

- [x] **[CREATE]** `scripts/upset_risk.py`
  - **Content:** Extract `_run_upset_risk()` (line 1117, ~100 lines) from orchestrator.
  - **Interface:** `run_upset_risk(date: str, state: dict) -> tuple[bool, str]`
  - **Definition of done:** Module importable, orchestrator calls it, output identical.

- [x] **[MODIFY]** `scripts/pipeline_orchestrator.py`
  - **Action:** Remove inline S5/S6 implementations. Import from new modules.
  - **Definition of done:** No context/upset logic remains inline.

### 3.3 Extract S2 Tipster Cross-Reference

- [x] **[CREATE]** `scripts/tipster_xref.py`
  - **Content:** Extract `_run_tipster_xref()` (line 867, ~75 lines) from orchestrator.
  - **Interface:** `run_tipster_xref(date: str, state: dict) -> tuple[bool, str]`
  - **Definition of done:** Module importable, orchestrator calls it, output identical.

- [x] **[MODIFY]** `scripts/pipeline_orchestrator.py`
  - **Action:** Remove inline S2. Import from new module.
  - **Definition of done:** No tipster logic remains inline.

### 3.4 Extract S10 Summary

- [x] **[CREATE]** `scripts/pipeline_summary.py`
  - **Content:** Extract `_run_s10()` (line 1866, ~110 lines) from orchestrator.
  - **Interface:** `run_s10(date: str, state: dict) -> tuple[bool, str]`
  - **Definition of done:** Module importable, orchestrator calls it, output identical.

- [x] **[MODIFY]** `scripts/pipeline_orchestrator.py`
  - **Action:** Remove inline S10. Import from new module.
  - **Definition of done:** No summary logic remains inline.

### 3.5 Slim Down Orchestrator

After all extractions, `pipeline_orchestrator.py` should contain ONLY:
- Step definitions (`PIPELINE_STEPS`, `STEP_TIMEOUTS`)
- State management (`load_state`, `save_state`, `load_config`)
- Step execution dispatch (`run_command`, `run_python_step`)
- Scan orchestration (`_run_parallel_scan`, `_run_scan_events`, `_run_parallel_enrichment`)
- S3 dispatch (`_run_s3`) — already imports from `deep_stats_report.py`
- S7 dispatch (`_run_s7`) — already imports from `gate_checker.py`
- S8 dispatch (`_run_s8`) — already imports from `coupon_builder.py`
- S9 dispatch (`_run_s9`) — already imports from `validate_coupons.py`
- CLI (`main`, argument parsing)
- Source health (`_run_source_health`)

- [x] **[MODIFY]** `scripts/pipeline_orchestrator.py`
  - **Action:** After all extractions, verify the file is purely orchestration. Add clear section headers.
  - **Definition of done:** File is ~1,200 lines (down from ~2,500). No inline analysis logic. All step implementations are either imported from dedicated modules or are thin dispatchers to subprocess commands.

### 3.6 Phase 3 Validation

- **Definition of done for Phase 3:**
  1. `pipeline_orchestrator.py` is ≤1,500 lines.
  2. New modules (`odds_evaluator.py`, `context_checks.py`, `upset_risk.py`, `tipster_xref.py`, `pipeline_summary.py`) each import cleanly.
  3. Full pipeline run (`--date <today>`) produces identical output artifacts as before extraction.
  4. Each extracted module can be tested independently (accepts `date` + `state` dict, returns `(bool, str)`).

---

## Phase 4: Agent Integration

**Risk: MEDIUM-HIGH** — Architectural change to how steps communicate with agents. Must preserve backward compatibility (pipeline still works without agents).  
**Prerequisite:** Phase 3 complete (clean module boundaries exist)  
**Estimated scope:** 1 new protocol file, ~6 module modifications, agent file updates

### 4.1 Define Agent Output Protocol

- [x] **[CREATE]** `scripts/agent_protocol.py`
  - **Purpose:** Define the structured JSON schemas for agent communication. Each pipeline step that requires agent review writes a structured output file that agents can consume, and agents write structured responses back.
  - **Content:**
    ```python
    # Step output schema: what each step writes for agent consumption
    STEP_OUTPUT_SCHEMAS = {
        "s1e_shortlist": {
            "type": "scan_review",
            "agent": "bet-scanner",
            "input_file": "{date}_s2_shortlist.json",
            "expected_action": "verify_scan_completeness",
            "output_file": "{date}_s1e_agent_review.json",
        },
        "s2_tipster": {
            "type": "tipster_enrichment",
            "agent": "bet-scout",
            "input_file": "{date}_s2_tipster_xref.json",
            "expected_action": "qualitative_tipster_assessment",
            "output_file": "{date}_s2_agent_review.json",
        },
        "s3_deep_stats": {
            "type": "stats_review",
            "agent": "bet-statistician",
            "input_file": "{date}_s3_deep_stats.json",
            "expected_action": "validate_statistical_analysis",
            "output_file": "{date}_s3_agent_review.json",
        },
        # ... etc for s4, s5, s6, s7, s8
    }
    
    # Agent review result schema
    AgentReviewResult = {
        "agent": str,           # agent name
        "step_id": str,         # pipeline step
        "status": str,          # "approved" | "flagged" | "enriched"
        "flags": list[str],     # issues found
        "enrichments": dict,    # additional data the agent added
        "timestamp": str,       # ISO timestamp
    }
    ```
  - **Definition of done:** Module importable. Schemas cover all steps with `agent_review_required`. Types are documented.

### 4.2 Write Structured Agent Input After Each Step

- [x] **[MODIFY]** `scripts/pipeline_orchestrator.py`
  - **Current state:** Prints `[AGENT-REVIEW-REQUIRED]` banners to stdout.
  - **Action:** After each step with `agent_review_required`, write a structured JSON file to `betting/data/agent_reviews/{date}_{step_id}_input.json` containing:
    - Step output summary (key metrics, counts, flags)
    - File paths to full artifacts
    - Expected agent action (from `STEP_OUTPUT_SCHEMAS`)
    - Context needed for the agent's analysis
  - **Backward compatible:** Banners are kept alongside structured output. Pipeline runs identically without agents reading the files.
  - **Definition of done:** After pipeline run, `betting/data/agent_reviews/` contains one `_input.json` per step that has `agent_review_required`. Each file is valid JSON matching the schema.

### 4.3 Agent Response Ingestion

- [x] **[MODIFY]** `scripts/pipeline_orchestrator.py`
  - **Action:** Before running step N+1, check if agent review file `{date}_{step_N}_review.json` exists for the previous step. If it does, load and merge enrichments into the step's state. If not, proceed without agent input (current behavior).
  - **This is opt-in:** If no agent writes a review file, the pipeline proceeds exactly as it does today. This makes the agent integration non-breaking.
  - **Definition of done:** Orchestrator checks for and loads agent review files. Pipeline works identically when no review files exist.

### 4.4 Update Agent Definitions

- [x] **[MODIFY]** `.github/agents/bet-orchestrator.agent.md`
  - **Action:** Add instructions for reading structured step outputs from `betting/data/agent_reviews/` and dispatching specialist agents based on the `expected_action` field. Add instructions for writing `_review.json` response files.
  - **Definition of done:** Agent instructions describe the structured input/output protocol.

- [x] **[MODIFY]** `.github/agents/bet-statistician.agent.md`, `bet-scout.agent.md`, `bet-valuator.agent.md`, `bet-challenger.agent.md`, `bet-builder.agent.md`
  - **Action:** Add instructions for each specialist agent to read its `_input.json` file and write a `_review.json` response with the `AgentReviewResult` schema.
  - **Definition of done:** Each agent file describes its structured I/O contract.

### 4.5 Phase 4 Validation

- **Definition of done for Phase 4:**
  1. Pipeline run generates `agent_reviews/` directory with structured JSON files.
  2. Pipeline works identically when no agent review files exist (backward compatible).
  3. Agent files document the input/output protocol.
  4. A manually created `_review.json` file is correctly loaded and merged by the orchestrator on the next step.

---

## Phase 5: Pipeline Improvements

**Risk: LOW-MEDIUM** — Targeted functional improvements.  
**Prerequisite:** Phase 3 complete (Phase 4 can be parallel)  
**Estimated scope:** ~5 file modifications, 1 new file

### 5.1 Add `evaluate_decisions.py` to S0

- [x] **[MODIFY]** `scripts/pipeline_orchestrator.py`
  - **Current state:** S0 runs `settle_on_finish.py` + `analyze_betclic_learning.py`. The `evaluate_decisions.py` script exists but is never called.
  - **Action:** Add `evaluate_decisions.py` as the third command in S0's `commands` list, after settlement and before analysis. It should run conditionally — only if settlement produced results.
  - **Definition of done:** S0 step definition includes `evaluate_decisions.py`. Post-settlement, `decision_outcomes` table is populated. Pipeline continues even if no previous day data exists (graceful no-op).

### 5.2 Add Data Rotation

- [x] **[CREATE]** `scripts/data_rotation.py`
  - **Purpose:** Clean up old dated files in `betting/data/` and old DB records.
  - **Behavior:**
    - Delete `*_{date}_*` files older than configurable retention period (default: 30 days)
    - Patterns to rotate: `*_s2_shortlist.json`, `*_s3_deep_stats.*`, `market_matrix_*`, `weather_*`, `tipster_aggregation_*`, `analysis_pool_*`, `odds_api_snapshot*`, `pipeline_state/pipeline_*.json`
    - Patterns to NEVER delete: `betclic_bets_history.json`, `picks-ledger*.csv`, `scan_urls.json`
    - DB cleanup: Delete `scan_results`, `match_stats`, `odds_history` records older than retention period
    - Dry-run mode by default (`--execute` flag to actually delete)
  - **Definition of done:** Script runs, reports what would be deleted. With `--execute`, removes old files. Protected files are never touched.

- [x] **[MODIFY]** `scripts/pipeline_orchestrator.py`
  - **Action:** Add data rotation as an optional post-S0 step (before scanning). Call `data_rotation.py --execute --days 30`.
  - **Definition of done:** Data rotation runs automatically at pipeline start. Old files are cleaned up.

### 5.3 Fix Dual-Import Pattern

- [x] **[MODIFY]** `scripts/pipeline_orchestrator.py`  
  - **Current state:** Has `sys.path.insert(0, str(SCRIPTS_DIR))` at the top, then `try: from scripts.X except: from X` for every import.
  - **Action:** Since `SCRIPTS_DIR` is already on `sys.path`, use bare imports directly: `from deep_stats_report import generate_deep_stats`. Remove all `try/except ImportError` wrappers.
  - **Definition of done:** Zero `try/except ImportError` import blocks in `pipeline_orchestrator.py`. All imports use bare module names (since `scripts/` is on `sys.path`).

- [x] **[MODIFY]** Other scripts that use the dual-import pattern
  - **Action:** For scripts that are run both standalone AND imported by the orchestrator, ensure `scripts/` is always on `sys.path`. The orchestrator already handles this. For scripts run directly via `subprocess`, they need their own `sys.path` setup at the top.
  - **Affected files:** `scripts/gate_checker.py`, `scripts/deep_stats_report.py`, `scripts/coupon_builder.py`, `scripts/validate_coupons.py`, `scripts/compute_safety_scores.py`, `scripts/normalize_stats.py`
  - **Strategy:** Add a standard 3-line preamble at the top of each script:
    ```python
    from pathlib import Path
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    ```
    Then use bare imports everywhere in that file.
  - **Definition of done:** `grep -rn "try:.*from scripts\." scripts/*.py` returns 0 results.

### 5.4 Add Step Retry Mechanism

- [x] **[MODIFY]** `scripts/pipeline_orchestrator.py`
  - **Current state:** Step failures are terminal (critical steps) or silently skipped (non-critical). No retry.
  - **Action:** Add configurable retry for non-critical steps. In `run_command()` and `run_python_step()`, if a step fails and `step.get("retries", 0) > 0`, retry with exponential backoff (5s, 15s, 45s). Add `"retries": 1` to steps that call external APIs (S1b parallel enrichment, S1a discover).
  - **Definition of done:** Failed non-critical steps retry once before marking as failed. Retry count and results are logged in state JSON.

### 5.5 Phase 5 Validation

- **Definition of done for Phase 5:**
  1. `evaluate_decisions.py` runs in S0 and populates `decision_outcomes` table.
  2. `data_rotation.py --days 7` in dry-run mode lists files older than 7 days.
  3. Zero `try/except ImportError` dual-import blocks in pipeline scripts.
  4. Retry mechanism triggers on simulated API failure (step retried once before marking failed).

---

## Phase 6: Testing

**Risk: LOW** — Adding tests doesn't change production code.  
**Prerequisite:** Phase 3 complete (extracted modules are testable), Phase 1 complete (dead tests cleaned up)  
**Estimated scope:** ~6 test files created/modified

### 6.1 Fix Broken Tests from Phase 1

- [x] **[MODIFY]** `tests/conftest.py`
  - **Current state:** Imports `from bet.config import BettingConfig`.
  - **Action:** `BettingConfig` was deleted with `src/bet/config.py` in Phase 1. Replace with a minimal inline fixture or create a lightweight `tests/helpers.py` with a test config builder.
  - **Definition of done:** `conftest.py` no longer imports from deleted modules. All shared fixtures work.
  - **Resolution:** `src/bet/config.py` was NOT deleted (still exists). Fixed root `conftest.py` to add `src/` to `sys.path` so `from bet.config import BettingConfig` works.

- [x] **[DELETE]** `tests/test_pipeline.py`
  - **Reason:** Tests the deleted `src/bet/pipeline/orchestrator.py`. Will be replaced by new orchestrator tests.
  - **Definition of done:** File removed.

- [x] **[DELETE]** `tests/test_data_gate.py`
  - **Current state:** Imports `from bet.config import BettingConfig` and `from bet.coupon.builder import build_coupons`.
  - **Action:** Deleted — `bet.coupon.builder` was removed in Phase 1 and `scripts/coupon_builder.py` has a completely different interface (dict-based, not MarketCandidate-based). Tests were not portable.
  - **Definition of done:** File removed.

- [x] **[DELETE]** `tests/test_settlement.py`
  - **Action:** Removed — imports from deleted `src/bet/settlement/settler.py`. No equivalent functions in scripts/.
  - **Definition of done:** File removed. Also deleted `test_coupon_builder.py` and `test_safety_scores.py` (same issue — imported deleted `bet.coupon.builder` and `bet.stats.safety_scores`/`bet.utils.odds`). Fixed `test_pipeline_modules.py` imports: `_inject_ev_from_odds` → `scripts.odds_evaluator`, removed `TestNormalizeStatus` class (historical_learning deleted).

### 6.2 Add Orchestrator Tests

- [x] **[CREATE]** `tests/test_orchestrator.py`
  - **Content:** Unit tests for `scripts/pipeline_orchestrator.py`:
    - `test_load_state_creates_fresh_state` — verifies new state has all step IDs
    - `test_save_and_load_state_roundtrip` — atomic write + read
    - `test_run_command_success` — subprocess execution with mock
    - `test_run_command_timeout` — timeout handling
    - `test_step_skip_on_resume` — completed steps are skipped
    - `test_critical_step_failure_aborts` — critical step failure stops pipeline
    - `test_non_critical_step_failure_continues` — non-critical failure continues
    - `test_python_step_dispatch` — `run_python_step` routes to correct function
  - **Definition of done:** All tests pass. Core orchestration logic (state management, step dispatch, failure handling) is covered.

### 6.3 Add Extracted Module Tests

- [x] **[CREATE]** `tests/test_odds_evaluator.py`
  - **Content:** Tests for `scripts/odds_evaluator.py`:
    - `test_convert_espn_odds_positive` — American +150 → 2.50
    - `test_convert_espn_odds_negative` — American -200 → 1.50
    - `test_inject_ev_from_odds_basic` — EV calculation with mock odds data
    - `test_inject_ev_no_odds_available` — graceful handling of missing odds
  - **Definition of done:** Tests pass. Odds evaluation logic has unit test coverage.

- [x] **[CREATE]** `tests/test_context_upset.py`
  - **Content:** Tests for `scripts/context_checks.py` and `scripts/upset_risk.py`:
    - `test_weather_flag_wind` — wind speed > threshold adds flag
    - `test_upset_risk_scoring` — upset risk heuristics produce expected scores
    - `test_context_no_weather_data` — graceful handling of missing weather
  - **Definition of done:** Tests pass. Context and upset risk logic has coverage.

### 6.4 Add Key Pipeline Module Tests

- [x] **[CREATE]** `tests/test_build_shortlist.py`
  - **Content:** Tests for `scripts/build_shortlist.py`:
    - `test_shortlist_ranking_order` — candidates ranked by score
    - `test_tournament_protection_boost` — tournament events get +15 score
    - `test_minor_league_value_boost` — non-top-5 leagues get +6 score
    - `test_shortlist_output_format` — output JSON has required fields
  - **Definition of done:** Tests pass. Shortlist builder ranking logic is covered.

- [ ] **[CREATE]** `tests/test_market_matrix.py` *(skipped — not in task scope)*
  - **Content:** Tests for `scripts/generate_market_matrix.py`:
    - `test_market_matrix_structure` — output has required columns
    - `test_stats_first_mode` — stats-first flag produces expected output
    - `test_major_competition_detection` — known tournaments detected
  - **Definition of done:** Tests pass. Market matrix generation has coverage.

### 6.5 Add Minimal E2E Pipeline Test

- [ ] **[MODIFY]** `tests/test_e2e_pipeline.py`
  - **Current state:** File exists but may test deleted package code.
  - **Action:** Create/update to test the actual `scripts/pipeline_orchestrator.py` with mock data:
    - Mock all external API calls and subprocess commands
    - Provide fixture files in `tests/fixtures/` (minimal scan_summary, shortlist, stats cache)
    - Run pipeline with `--date 2026-01-01` (safe test date)
    - Verify: state file created, steps marked completed, output files generated
  - **Scope:** This is a smoke test, not a full integration test. It verifies the pipeline wiring, not the analysis quality.
  - **Definition of done:** Test passes in CI. Pipeline runs end-to-end with mocked data in <10 seconds.

### 6.6 Phase 6 Validation

- **Definition of done for Phase 6:**
  1. [x] `pytest tests/ -x` passes with zero failures.
  2. [x] No test file imports from deleted `src/bet/` modules.
  3. [x] New test files exist for: orchestrator, odds_evaluator, context/upset, build_shortlist, data_rotation, agent_protocol.
  4. [x] Test count increased by ≥20 test functions. (Was 519 before; now 543 = +27 new tests, -3 deleted normalize_status tests.)

---

## Appendix: Files Affected Per Phase

| Phase | Creates | Modifies | Deletes |
|-------|---------|----------|---------|
| **1** | 0 | 0 | ~25 files |
| **2** | 0 | ~8 files | 1 file |
| **3** | 5 files | 1 file | 0 |
| **4** | 1 file | ~7 files | 0 |
| **5** | 1 file | ~10 files | 0 |
| **6** | 5-6 files | 3-4 files | 1 file |

## Appendix: Risk Matrix

| Risk | Phase | Mitigation |
|------|-------|------------|
| Missing import after Phase 1 deletion | 1 | Run `python3 -c "import ..."` checks for all active modules before committing |
| Market definition drift during migration | 2 | Diff both copies side-by-side before removing old one; take union of entries |
| Logic change during extraction | 3 | Exact copy-paste, then `diff` output artifacts before/after |
| Agent protocol over-engineering | 4 | Keep schemas minimal (JSON files, not classes). No framework. |
| Retry mechanism causing duplicate side effects | 5 | Only retry idempotent steps (API reads, not DB writes) |
| Test fixtures becoming stale | 6 | Use minimal fixtures with only required fields |

## Appendix: Dependency Graph Between Phases

```
Phase 1 (cleanup) ──→ Phase 2 (definitions) ──→ Phase 3 (extraction)
                                                       │
                                                       ├──→ Phase 4 (agents)     [can parallel with 5]
                                                       └──→ Phase 5 (improvements) [can parallel with 4]
                                                                    │
Phase 1 ─────────────────────────────────────────────────→ Phase 6 (testing)
                                                       [needs 3 complete, 1 complete]
```

Phases 4 and 5 are independent of each other and can be worked on in parallel after Phase 3.
Phase 6 needs Phases 1 and 3 complete (to fix broken tests and test extracted modules).
