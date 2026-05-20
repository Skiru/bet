# Post-Refactor Pipeline Alignment — Implementation Plan

**Status:** NOT STARTED
**Created:** 2026-05-14
**Scope:** Fix all misalignments between actual codebase and documentation/agent/prompt layer after 3 major refactoring efforts (discovery module, scrapers module, odds pipeline cleanup).

---

## §1. Technical Context

### Current Architecture

**Event Discovery (S1):** `src/bet/discovery/` module with 3 structured API sources (SofaScore, The-Odds-API, API-Football). Entrypoint: `scripts/discover_events.py`. Old `scan_events.py` deleted. ~30s, 1500-2000 events.

**Scrapers (S2.3):** `src/bet/scrapers/` — 17 scrapers (lazy registry in `__init__.py`) across 5 sports via SQLAlchemy 2.0 ORM. Sources: FBref, NBA API, Basketball-Reference, Sackmann, NHL API, Hockey-Reference, Volleybox (blocked), ESPN (5 sports), Flashscore (5 sports). CLI: `scripts/run_scrapers.py`. Writes to `league_profiles` + `player_season_stats` + `athletes`.

**Scraper-to-Pipeline Bridge (S2.4):** `scripts/scraper_to_team_form.py` — **NOT YET BUILT.** Documented as "TO BE BUILT" in `pipeline-knowledge-base.md` and `specifications/scrapers-pipeline-integration.md`. Currently referenced as if it exists in 7+ agent/prompt/doc files.

**Enrichment (S2.5):** `scripts/data_enrichment_agent.py` — fills gaps after scrapers. ESPN API, Flashscore HTTP/Playwright. DB-first via `get_db()`.

**Odds Pipeline (S4):** 3 automated sources — the-odds-api, odds-api.io, api-football-odds. Scripts: `fetch_odds_api.py`, `fetch_odds_api_io.py`, `fetch_odds_multi.py`. OddsPortal/BetExplorer removed from automated pipeline (kept for manual/fixture discovery). DB: `odds_history` table.

**Execution Model (Model A — Run-Then-Delegate):** Orchestrator runs ALL scripts, monitors output, extracts AGENT_SUMMARY. Specialist agents receive finished output for analysis-only. Specialists NEVER run scripts.

**DB Access:** `from bet.db.connection import get_db` + repository classes (`SportRepo`, `TeamRepo`, `FixtureRepo`, etc.). Never raw `sqlite3.connect()`. Schema column: `fixtures.kickoff` (NOT `kickoff_utc`).

**5 Core Sports:** Football, Volleyball, Basketball, Tennis, Hockey.

---

## §2. Verification Summary

### Issues verified as ALREADY CLEAN (no action needed):
- `bet-valuator.agent.md` — no OddsPortal/BetExplorer references ✅
- `tests/test_odds_sources.py` — no stale source references ✅
- `tests/test_fetch_odds_multi.py` — no stale source references ✅
- `scripts/fetch_odds_multi.py` — no stale oddsportal/betexplorer references ✅
- `.github/agents/` — no raw `sqlite3.connect()` references ✅
- `.github/instructions/analysis-methodology.instructions.md` — no `scan_events.py` references ✅

---

## Phase 1: Critical Fixes (phantom scripts, broken code)

These issues cause runtime failures or incorrect pipeline diagnostics.

### Scripts

- [ ] **Task 1.1** `[MODIFY]` `scripts/inspect_pipeline.py`
  - **File:** `scripts/inspect_pipeline.py`
  - **Changes:**
    - L137-142: Replace `kickoff_utc` → `kickoff` in the fixtures date-specific count query. Currently tries `date(kickoff_utc)` as fallback — fixture schema uses `kickoff`.
      ```python
      # L137-142 CURRENT:
      count = _safe_fetchone(conn,
          f"SELECT COUNT(*) FROM {t} WHERE date(kickoff_utc) = ?", (date,), default=0)
      # CHANGE TO:
      count = _safe_fetchone(conn,
          f"SELECT COUNT(*) FROM {t} WHERE date(kickoff) = ?", (date,), default=0)
      ```
    - L189: Same fix — `date(kickoff_utc)` → `date(kickoff)` in `inspect_s1()` fixtures count.
      ```python
      # L189 CURRENT:
      "SELECT COUNT(*) FROM fixtures WHERE date(kickoff_utc) = ?",
      # CHANGE TO:
      "SELECT COUNT(*) FROM fixtures WHERE date(kickoff) = ?",
      ```
    - L176/L222: Align metric key — `inspect_s1()` builds `total_discovery_events` (L176) but verdict check at L222 reads `total_scan_events`. Change L222 to read `total_discovery_events` for consistency.
      ```python
      # L222 CURRENT:
      if metrics["total_scan_events"] == 0:
      # CHANGE TO:
      if metrics["total_discovery_events"] == 0:
      ```
  - **Acceptance criteria:** `python3 scripts/inspect_pipeline.py --step s1 --date 2026-05-14` runs without SQL errors. Metric keys consistent throughout the file.

- [ ] **Task 1.2** `[MODIFY]` `scripts/validate_phase.py`
  - **File:** `scripts/validate_phase.py`
  - **Changes:**
    - L173: Recovery message references `discover_fixtures.py` which doesn't exist. Change to `discover_events.py`.
      ```python
      # L173 CURRENT:
      recovery=f"Run: PYTHONPATH=src python3 scripts/discover_fixtures.py --date {date} --verbose"))
      # CHANGE TO:
      recovery=f"Run: PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date {date} --verbose"))
      ```
  - **Acceptance criteria:** `python3 scripts/validate_phase.py --date 2026-05-14 --phase data` shows correct recovery command for D4 check.

- [ ] **Task 1.3** `[MODIFY]` `scripts/agent_protocol.py`
  - **File:** `scripts/agent_protocol.py`
  - **Changes:**
    - L697: SQL query uses `date(kickoff_utc)` — change to `date(kickoff)`.
      ```python
      # L697 CURRENT:
      "query": "SELECT DISTINCT competition FROM fixtures WHERE date(kickoff_utc)='{date}' ...
      # CHANGE TO:
      "query": "SELECT DISTINCT competition FROM fixtures WHERE date(kickoff)='{date}' ...
      ```
  - **Acceptance criteria:** Tournament protection query in STEP_AGENT_CONFIG uses correct column name.

---

## Phase 2: Execution Model Alignment (Model A enforcement)

Three specialist agents still instruct themselves to run scripts, contradicting the Run-Then-Delegate model where the orchestrator runs ALL scripts.

- [ ] **Task 2.1** `[MODIFY]` `.github/agents/bet-scanner.agent.md`
  - **File:** `.github/agents/bet-scanner.agent.md`
  - **Changes:**
    - R17 in MY RULES table: Change from "LIVE SCRIPT MONITORING" with "Run ALL scripts with `mode=async`..." to "ANALYSIS-ONLY" matching bet-valuator/bet-enricher pattern:
      ```
      | R17 | ANALYSIS-ONLY | You do NOT run scripts. The orchestrator runs scan scripts and passes you AGENT_SUMMARY + log excerpts. Analyze coverage, fixture quality, sport diversity. Cite ≥3 specific metrics. Return Model A verdict. | Run any pipeline script. Use run_in_terminal. Return "scan completed" without specific numbers. |
      ```
    - ORCHESTRATION PROTOCOL section (around L100-140): Remove the bash command blocks that instruct the agent to run `discover_events.py`, `ingest_scan_stats.py`, etc. Replace with analysis-focused instructions explaining what output to expect from the orchestrator.
    - Script Execution Rules table: Remove or retitle to "Expected Script Output" (reference only, not execution instructions).
  - **Acceptance criteria:** No `run_in_terminal`, `mode=async`, or bash command references remain. R17 says "ANALYSIS-ONLY". Agent description reflects analysis role.

- [ ] **Task 2.2** `[MODIFY]` `.github/agents/bet-settler.agent.md`
  - **File:** `.github/agents/bet-settler.agent.md`
  - **Changes:**
    - R17 in MY RULES table: Change from "LIVE SCRIPT MONITORING" with "Run ALL scripts..." to "ANALYSIS-ONLY":
      ```
      | R17 | ANALYSIS-ONLY | You do NOT run scripts. The orchestrator runs settlement scripts and passes you output. Analyze PnL patterns, learning insights, bankroll health. Cite ≥3 specific metrics. Return Model A verdict. | Run any pipeline script. Use run_in_terminal. Return PnL numbers without analysis. |
      ```
    - Tool Usage → `execute/runInTerminal` section (around L96-100): Remove "MUST use for: `python3 scripts/settle_on_finish.py`..." and `fetch_odds_api.py --scores` and `analyze_betclic_learning.py`. Keep browser tool usage for result verification (OddsPortal CLV — manual, which is fine).
    - Remove `--verbose`, `mode=async`, timeout references from tool usage.
  - **Acceptance criteria:** No script execution instructions remain. R17 says "ANALYSIS-ONLY". Tool usage focuses on browser verification + sequential-thinking.

- [ ] **Task 2.3** `[MODIFY]` `.github/agents/bet-db-analyst.agent.md`
  - **File:** `.github/agents/bet-db-analyst.agent.md`
  - **Changes:**
    - R17 in MY RULES table: Change from "LIVE SCRIPT MONITORING" with "Run ALL scripts..." to "ANALYSIS-ONLY":
      ```
      | R17 | ANALYSIS-ONLY | You do NOT run scripts. You analyze data via pylanceRunCodeSnippet and DB queries passed by the orchestrator. Cite ≥3 specific metrics (row counts, gap counts, freshness dates). Return Model A verdict. | Run any pipeline script. Use run_in_terminal. Say "data looks good" without numbers. |
      ```
  - **Acceptance criteria:** R17 says "ANALYSIS-ONLY". No references to running pipeline scripts.

---

## Phase 3: Documentation Alignment (agents, prompts, skills, instructions)

Remove phantom `scraper_to_team_form.py` references, fix stale entrypoints, update scraper counts.

### Orchestrator & Prompts

- [ ] **Task 3.1** `[MODIFY]` `.github/agents/bet-orchestrator.agent.md`
  - **File:** `.github/agents/bet-orchestrator.agent.md`
  - **Changes:**
    - L82: Remove `scraper_to_team_form.py — **NEW (S2.4):** bridge adapter → team_form from scraper data` from the "ALL pipeline scripts are run by YOU" list.
    - L317: Remove `scraper_to_team_form.py` row from the Script Execution Rules command table.
    - Add a comment/note that S2.4 is a planned future step (TO BE BUILT), not current pipeline.
  - **Acceptance criteria:** No `scraper_to_team_form.py` in script execution lists. S2.4 noted as planned.

- [ ] **Task 3.2** `[MODIFY]` `.github/prompts/orchestrate-betting-day.prompt.md`
  - **File:** `.github/prompts/orchestrate-betting-day.prompt.md`
  - **Changes:**
    - L234: Remove `S2.4 adapter | scraper_to_team_form.py | 120000 | ...` row from the Pre-filled Run-Then-Delegate table.
    - L247: Remove `scraper_to_team_form.py` from the AGENT_SUMMARY emitting scripts list. Update count from "15 analytical scripts" to "14 analytical scripts".
    - L576-592: Remove the entire STEP S2.4 execution block (bash command + EXTRACT + delegate section referencing `scraper_to_team_form.py`).
  - **Acceptance criteria:** No `scraper_to_team_form.py` references. Script count accurate. S2.3 flows directly into gap analysis for S2.5.

### Enricher Agent & Internal Prompt

- [ ] **Task 3.3** `[MODIFY]` `.github/agents/bet-enricher.agent.md`
  - **File:** `.github/agents/bet-enricher.agent.md`
  - **Changes:**
    - L62: Remove "2. **S2.4** — `scraper_to_team_form.py` converts scraper data → `team_form` rows" from data flow. Renumber S2.5 → S2.4 (or keep S2.5 label).
    - L95: Remove "Receives output from: `scraper_to_team_form.py`..." line.
    - Update description in frontmatter: remove "(S2.3/S2.4)" → "(S2.3/S2.5)" since S2.4 doesn't exist yet.
  - **Acceptance criteria:** No `scraper_to_team_form.py` references. Data flow accurately shows S2.3 (scrapers) → S2.5 (gap-fill enrichment).

- [ ] **Task 3.4** `[MODIFY]` `.github/internal-prompts/bet-enrich.prompt.md`
  - **File:** `.github/internal-prompts/bet-enrich.prompt.md`
  - **Changes:**
    - L12-15: Remove "2. **S2.4** — `scraper_to_team_form.py` converts scraper data → `team_form` rows" from data flow.
    - L12: Change "14 scrapers" → "19 scrapers" in scraper coverage description.
    - Title: Update "S2.3/S2.4/S2.5" → "S2.3/S2.5" since S2.4 doesn't exist.
  - **Acceptance criteria:** No `scraper_to_team_form.py` references. Scraper count = 19. Steps reflect actual pipeline.

### Skills

- [ ] **Task 3.5** `[MODIFY]` `.github/skills/bet-navigating-sources/SKILL.md`
  - **File:** `.github/skills/bet-navigating-sources/SKILL.md`
  - **Changes:**
    - L45-46: Replace stale Flashscore/scan_events.py reference:
      ```markdown
      # CURRENT:
      **PRIMARY SCAN SOURCE: Flashscore** (via `UnifiedAPIClient` in `scan_events.py`)
      - Used by `scan_events.py` to discover ALL events for all 5 sports
      
      # CHANGE TO:
      **PRIMARY DISCOVERY SOURCE: SofaScore + Odds API + API-Football** (via `src/bet/discovery/` module)
      - Used by `discover_events.py` to discover ALL events for all 5 sports (~30s, 1500-2000 events)
      ```
    - L47-49: Update enrichment description to mention discovery module provides fixtures, enrichment provides form/H2H.
    - Market Sources table (L25-area): Add a note clarifying OddsPortal/BetExplorer are manual/fixture-discovery only, not automated odds pipeline sources.
  - **Acceptance criteria:** No `scan_events.py` references. Discovery source accurately described. Market sources table has automated vs manual distinction.

- [ ] **Task 3.6** `[MODIFY]` `.github/skills/bet-evaluating-odds/SKILL.md`
  - **File:** `.github/skills/bet-evaluating-odds/SKILL.md`
  - **Changes:**
    - Verify the multi-source protocol reflects 3 automated sources (the-odds-api, odds-api.io, api-football-odds). If stale references to 5 sources exist, update to 3.
    - This file is already mostly clean based on review — may be NO-OP. Verify during implementation.
  - **Acceptance criteria:** Odds source list matches actual 3-source architecture.

### Memory

- [ ] **Task 3.7** `[MODIFY]` `memories/repo/pipeline-knowledge-base.md`
  - **File:** `memories/repo/pipeline-knowledge-base.md`
  - **Changes:**
    - L61: Change "Need: `scripts/scraper_to_team_form.py` adapter" → clarify it's a TODO, not referenced as existing pipeline step.
    - L75: Change "S2.4: `scraper_to_team_form.py` — bridge adapter (TO BE BUILT)" — already marked TO BE BUILT, but update surrounding text that implies it's part of the active pipeline execution sequence.
    - L348: Update gap note to reflect this is a known backlog item.
    - Scraper section header: "14 scrapers" → "19 scrapers" (matches actual `_SCRAPER_REGISTRY`).
  - **Acceptance criteria:** Knowledge base clearly marks S2.4 as backlog, not active. Scraper count = 19.

### ask-betting prompt

- [ ] **Task 3.8** `[MODIFY]` `.github/prompts/ask-betting.prompt.md`
  - **File:** `.github/prompts/ask-betting.prompt.md`
  - **Changes:**
    - Memory section (around L53): Change `pipeline-lessons-learned.md` → `pipeline-knowledge-base.md` (files were consolidated).
    - Agent Delegation Map — Required Context column:
      - Scanning row: `scan_errors.json` → remove (not reliably produced). Keep `scan_results` DB + `scan_run_stats` DB.
      - Statistics row: `analysis_pool_{date}.json` → `analysis_results` DB table (actual primary source).
      - Enrichment row: `stats_cache_{date}.json` → `team_form` DB table (actual primary source).
  - **Acceptance criteria:** All context file references point to files/tables that actually exist. Memory file reference is current.

---

## Phase 4: Test Fixes and New Tests

- [x] **Task 4.1** `[CREATE]` `tests/test_inspect_pipeline.py`
  - **File:** `tests/test_inspect_pipeline.py`
  - **Changes:** Create basic test coverage:
    - Test that `inspect_s0` returns valid metrics dict with `_verdict` key.
    - Test that `inspect_s1` handles missing DB gracefully (PARTIAL verdict).
    - Test SQL queries use `kickoff` (not `kickoff_utc`) — grep test on source.
    - Test metric key consistency (`total_discovery_events` used in verdict).
  - **Acceptance criteria:** Tests pass. SQL column references verified programmatically.

- [x] **Task 4.2** `[CREATE]` `tests/test_validate_phase.py`
  - **File:** `tests/test_validate_phase.py`
  - **Changes:** Create basic test coverage:
    - Test that recovery messages reference existing scripts (no `discover_fixtures.py`).
    - Test that `validate_data_phase` returns Check objects with correct structure.
    - Test that `_get_db()` uses project connection layer.
  - **Acceptance criteria:** Tests pass. Recovery commands reference valid scripts.

---

## Phase 5: README Rewrite

- [ ] **Task 5.1** `[MODIFY]` `README.md`
  - **File:** `README.md`
  - **Changes — complete content rewrite:**
    - Remove fake CLI section (`bet run/settle/status/history/health/migrate` — none exist).
    - Remove stale module references (`src/bet/scanner/`, `src/bet/pipeline/`, `src/bet/settlement/` — don't exist).
    - Remove "scripts/ are deprecated" claim — scripts ARE the active pipeline.
    - Fix sport count: "14 sports" → "5 core sports (football, volleyball, basketball, tennis, hockey)".
    - Remove `pipeline_orchestrator.py` reference.
    - Add accurate architecture section:
      - Discovery: `src/bet/discovery/` (3 API sources)
      - Scrapers: `src/bet/scrapers/` (19 scrapers, 5 sports)
      - DB: `src/bet/db/` (SQLite WAL, 28 tables, get_db() pattern)
      - Stats: `src/bet/stats/` (normalization, safety scores)
      - Pipeline: Agent-driven via `.github/agents/bet-orchestrator.agent.md` (Model A)
    - Keep Polish language (user preference) but fix all factual content.
    - Keep installation instructions (`pip install -e .`).
    - Update directory structure to match reality.
    - Keep "Najwazniejsze Zasady" section but update to reflect current rules.
  - **Acceptance criteria:** Every file/module/script referenced in README actually exists. Sport count = 5. No CLI commands that don't work. No "deprecated" claims about active code.

---

## Phase 6: Cleanup (delete stale files, clean source registry)

- [ ] **Task 6.1** `[DELETE]` `.github/prompts/_archive_integrate-discovery-module.prompt.md`
  - **File:** `.github/prompts/_archive_integrate-discovery-module.prompt.md`
  - **Rationale:** Completed migration prompt (marked "STATUS: COMPLETED"). Contains 20+ stale `scan_events.py` references that could confuse agents if accidentally loaded.
  - **Acceptance criteria:** File deleted. No references to it from other files.

- [ ] **Task 6.2** `[MODIFY]` `betting/sources/source-registry.md`
  - **File:** `betting/sources/source-registry.md`
  - **Changes:**
    - Add clear section headers segmenting sources:
      - **Automated Pipeline Sources** — the-odds-api, odds-api.io, api-football-odds, SofaScore API, API-Football (used by scripts programmatically)
      - **Manual/Browser Sources** — OddsPortal, BetExplorer, SBR, ESPN Odds, ScoresAndOdds (used by agents via Playwright/browser for manual checks)
      - **Tipster Sources** — ZawodTyper, Typersi, OLBG, PicksWise, etc.
      - **Archived/Blocked Sources** — Forebet, FootySupertips, etc.
    - OddsPortal entry already has "NOTE: Removed from automated odds pipeline" — good. Ensure BetExplorer has same note.
    - Add scraper module as a source category (19 scrapers, `src/bet/scrapers/`).
  - **Acceptance criteria:** Clear segmentation between automated/manual/archived. Reader can immediately tell which sources are programmatic vs manual.

---

## Phase 7: Cross-Validation

After all phases complete, run these verification checks:

- [ ] **Task 7.1** Grep verification: `grep -r "scraper_to_team_form" .github/ memories/repo/` returns 0 matches in active pipeline references (OK if in specifications/ or plans/ as "TO BE BUILT").
- [ ] **Task 7.2** Grep verification: `grep -r "kickoff_utc" scripts/` returns 0 matches (only `deep_stats_report.py` L1367 fallback is acceptable).
- [ ] **Task 7.3** Grep verification: `grep -r "scan_events.py" .github/` returns 0 matches (only `_archive_*` files acceptable, but those should be deleted in 6.1).
- [ ] **Task 7.4** Grep verification: `grep -r "discover_fixtures.py" scripts/` returns 0 matches.
- [ ] **Task 7.5** Run full test suite: `PYTHONPATH=src .venv/bin/python -m pytest tests/ --ignore=tests/scrapers -v --tb=short` — all pass.
- [ ] **Task 7.6** Run `python3 scripts/inspect_pipeline.py --step all --date 2026-05-14` — no SQL errors.
- [ ] **Task 7.7** Run `python3 scripts/validate_phase.py --date 2026-05-14 --phase all` — no stale script references in recovery messages.

---

## §3. Implementation Order & Dependencies

```
Phase 1 (Critical fixes) ─── no dependencies, do first
  │
Phase 2 (Model A alignment) ─── independent of Phase 1
  │
Phase 3 (Doc alignment) ─── depends on Phase 1 decisions (re: S2.4 status)
  │
Phase 4 (Tests) ─── depends on Phase 1 (test the fixed code)
  │
Phase 5 (README) ─── depends on Phase 3 (reference accurate architecture)
  │
Phase 6 (Cleanup) ─── independent, can run in parallel with Phase 3-5
  │
Phase 7 (Cross-validation) ─── depends on ALL above
```

Phases 1 and 2 can be done in parallel. Phase 6 can be done in parallel with 3-5. Phase 7 is the final gate.

---

## §4. Risk Notes

1. **scraper_to_team_form.py is a real planned feature.** The fix is to REMOVE it from current execution references (it doesn't exist yet), not to delete the specifications describing how to build it. `specifications/scrapers-pipeline-integration.md` and `betting/plans/scrapers-integration-handoff.md` should keep their S2.4 design docs intact.

2. **bet-scanner has dual identity.** It's listed as both `user-invokable: true` AND as a specialist agent under the orchestrator. As a user-invokable agent, it may legitimately need to run scripts when invoked directly (not via orchestrator). Consider keeping script execution capability but gating it: "When invoked by orchestrator (Model A) → analysis-only. When invoked directly by user → can run scan scripts." This requires a conditional in the agent, not a blanket removal.

3. **bet-settler edge case.** Settlement involves interactive verification (checking Flashscore, Betclic). When called via orchestrator → analysis-only. When called via `ask-betting` for ad-hoc settlement → may need to run scripts. Same conditional pattern as bet-scanner.

4. **Scraper count will grow.** Currently 17. Using "17 scrapers" is accurate today but will drift. Consider referencing the registry dynamically: "see `src/bet/scrapers/__init__.py` `_SCRAPER_REGISTRY` for current count."

---

## §5. Changelog

| Date | Phase | Tasks | Notes |
|------|-------|-------|-------|
| — | — | — | Implementation not started |
