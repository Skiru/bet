# Pipeline Data Flow Fixes — Implementation Plan

**Date:** 2026-05-19  
**Scope:** Fix all 10 holes/inconsistencies found in pipeline audit  
**Affected files:** ~6 scripts + 1 orchestration prompt

---

## Technical Context

- DB: SQLite WAL at `betting/data/betting.db`, connection via `from bet.db.connection import get_db`
- Pipeline scripts emit `AGENT_SUMMARY:{json}` and use `--verbose`
- Enrichment uses `FALLBACK_CHAINS` per sport (ESPN → API → Flashscore)
- `scan_results` table stores discovered events (written by coordinator)
- `team_form` table stores enrichment results (stat_key, l10_avg, l5_avg)
- Orchestration prompt: `.github/prompts/orchestrate-betting-day.prompt.md`

---

## Tasks

### Phase 1: Fix Dead Data Loaders

- [x] **T1 [MODIFY]** `scripts/db_data_loader.py` — Implement `load_scan_summary_from_db()` to actually query `scan_results` table and return grouped data in format expected by `generate_market_matrix.py`
- [x] **T2 [MODIFY]** `scripts/data_enrichment_agent.py` — Fix `_detect_missing_from_shortlist()` to check DB `team_form` table for existing stats, not just cache file existence

### Phase 2: Wire Betclic Filtering Into Pipeline

- [x] **T3 [MODIFY]** `scripts/build_shortlist.py` — Add `--betclic-filter` flag that reads `betclic_market_validation_{date}.json` and excludes events not confirmed on Betclic
- [x] **T4 [MODIFY]** `scripts/filter_betclic_shortlist.py` — Output file name should be `{date}_s2_shortlist_bettable.json` (clearer) and script should also write to DB `pipeline_runs`

### Phase 3: Fix Pipeline Ordering in Orchestration

- [x] **T5 [MODIFY]** `.github/prompts/orchestrate-betting-day.prompt.md` — Add Betclic validation as S1.5; wire filter output (`_bettable.json`) to enrichment/analysis `--shortlist`; update S7.5 as moved; update run table; fix S3 deep_stats to use bettable shortlist

### Phase 4: Fix ESPN Odds Loader Gap

- [x] **T6 [MODIFY]** `scripts/generate_market_matrix.py` — `load_espn_odds_snapshot()` should fall back to DB `odds_history` table when file doesn't exist (consistent with other loaders)

---

## Changelog

| Time | Change |
|------|--------|
| 2026-05-19 14:30 | Plan created from pipeline audit findings |
