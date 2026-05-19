# Pipeline Remediation Plan

**Version:** 1.0  
**Date:** 2026-05-19  
**Scope:** 30 issues across architecture, data quality, execution, methodology, operations  
**System size:** ~48K LoC, 153 files, 62 scripts, 21 agents, 28+ DB tables  

---

## Technical Context — Current Architecture Patterns

### Data Flow
```
S1 discover_events.py → DB: fixtures, fixture_sources, scan_results, teams, competitions, sports
S2 data_enrichment_agent.py → DB: team_form, injuries + JSON stats_cache
S2.5 build_shortlist.py → JSON: {date}_s2_shortlist.json
S3 deep_stats_report.py → DB: analysis_results, analysis_raw_data
S4 odds_evaluator.py → DB: odds evaluation overlay
S5 context_checks.py → context signals
S6 upset_risk.py → upset risk signals
S7 gate_checker.py → DB: gate_results
S8 coupon_builder.py → DB: coupons, bets + MD: coupon file
```

### Key Architectural Facts
1. **DB-first with JSON fallback** — All scripts dual-write (DB + JSON). Scripts try DB first via `get_db()`, fall back to JSON.
2. **Dual api_clients/** — `scripts/api_clients/` (20 files, runtime) vs `src/bet/api_clients/` (21 files, importable). Overlapping: ESPN, rate_limiter, base_client.
3. **Agent-driven pipeline** — Orchestrator agent calls individual scripts; specialist sub-agents analyze output.
4. **Validation gap** — `SPORT_VALUE_RANGES` enforcement exists only in `data_enrichment_agent._save_to_db()`. Other writers bypass.
5. **Shortlist JSON is the single non-DB handoff** — `build_shortlist.py` → JSON → `deep_stats_report.py`.
6. **Betclic market scraper** — Fully operational (2026-05-18). Uses curl_cffi, Angular SSR extraction, 38 competitions registered.
7. **SQLite concurrency** — `busy_timeout=30s`, `_db_write_lock` in enrichment, `retry_on_lock()` utility.
8. **Bankroll state** — 57.235 PLN, daily cap 5-15 PLN, max stake 2 PLN.

### DB Schema (key tables for this plan)
- `team_form` (207K rows): L10/L5/H2H per-match stats — the contamination target
- `fixtures` (1406): canonical event identity
- `analysis_results` / `analysis_raw_data`: S3 output
- `gate_results`: S7 verdicts (APPROVED/EXTENDED/REJECTED)
- `coupons` / `bets`: placed bet history
- `betclic_markets` / `betclic_competition_profiles`: market availability (v10)
- `source_health`: enrichment source tracking

---

## Architecture Decision Records

### ADR-1: Consolidate `api_clients/` into `src/bet/api_clients/`

**Context:** Two directories with overlapping modules cause import confusion. `data_enrichment_agent.py` imports from both (`from api_clients import...` uses `scripts/api_clients/` via PYTHONPATH, `from bet.api_clients...` uses `src/bet/`).

**Decision:** Make `src/bet/api_clients/` the canonical location. Create thin shim modules in `scripts/api_clients/` that re-export from `src/bet/api_clients/` for backward compatibility during transition.

**Rationale:**
- `src/bet/` is the proper Python package (importable, testable, typed)
- `scripts/api_clients/` has 20 files but many are sport-API wrappers unique to that location
- Breaking all imports at once is high risk; shim approach is incremental
- Final state: `scripts/api_clients/` contains only `__init__.py` with re-exports

**Consequences:** All new API clients go in `src/bet/api_clients/`. Shims allow existing scripts to work unchanged during migration.

---

### ADR-2: Centralize stat validation at repository write layer

**Context:** Garbage values (corners=989, goals=211) entered `team_form` because validation only existed in one code path. Multiple writers bypass it: `build_stats_cache.py`, `ingest_scan_stats.py`, Google Sports client.

**Decision:** Move `SPORT_VALUE_RANGES` validation into `StatsRepo.save_team_form()` as the single enforcement point. All code paths writing to `team_form` must go through the repository.

**Rationale:**
- Repository pattern is already established (`src/bet/db/repositories.py`)
- Defense-in-depth: even if upstream code changes, invalid data cannot persist
- Existing `src/bet/stats/value_ranges.py` module already provides the ranges
- No performance concern (simple dict lookup per write)

**Consequences:** Any write that bypasses `StatsRepo` is a bug. Direct `INSERT INTO team_form` becomes forbidden (enforceable via grep in CI).

---

### ADR-3: Betclic market validation becomes pipeline step S7.5

**Context:** `validate_betclic_markets.py` exists and works (tested 2026-05-18, 43 events scanned) but is NOT in the numbered pipeline. Result: 17 picks flagged UNAVAILABLE only after coupon was built.

**Decision:** Insert Betclic validation as mandatory step S7.5 — after gate checker (S7), before coupon builder (S8). Gate-fail any pick whose market is confirmed UNAVAILABLE.

**Rationale:**
- Cannot run earlier (Betclic Statystyki tab appears only ≤48h before kickoff)
- Must run before coupon build (no point building coupon legs that can't be placed)
- Fits naturally: gate produces candidates, market validation removes unbettable ones, coupon builds from remainder
- Script already outputs JSON that `coupon_builder.py` already reads

**Consequences:** Pipeline gains one additional mandatory script call. Coupon size may shrink when markets are unavailable — Extended Pool must absorb them.

---

## Phase 0: Quick Wins (1 session)

Fixes that require only config changes, small code edits, or documentation updates.

### Task 0.1: Delete dual key storage
- **Tag:** `[DELETE]` + `[MODIFY]`
- **Files:** `config/odds_api_key.txt`, `config/api_keys.json`
- **Change:** Delete `odds_api_key.txt`. Verify `fetch_odds_api.py` reads from `api_keys.json` only (it already does — the adapter tries JSON first).
- **Acceptance criteria:** `odds_api_key.txt` does not exist. `fetch_odds_api.py` still loads the key successfully from `api_keys.json`. Tests pass.
- **Dependencies:** None
- **Issue:** #27

### Task 0.2: Remove thesportsdb placeholder
- **Tag:** `[MODIFY]`
- **Files:** `config/api_keys.json`
- **Change:** Remove `thesportsdb` entry or set to `null` with a comment. Add a log WARNING in any code that references it.
- **Acceptance criteria:** No code path attempts to use a 3-char placeholder key for real API calls.
- **Dependencies:** None
- **Issue:** #28

### Task 0.3: Add Gemini startup warning
- **Tag:** `[MODIFY]`
- **Files:** `scripts/deep_stats_report.py` (and any script with `--gemini` flag)
- **Change:** At startup, if `--gemini` flag is passed but `config/gemini_config.json` has empty `api_key`, log `WARNING: --gemini flag passed but Gemini API key is empty. Gemini features disabled.` and continue without Gemini (current silent no-op behavior preserved but now visible).
- **Acceptance criteria:** Running with `--gemini` and empty key prints warning. No crash. Behavior otherwise unchanged.
- **Dependencies:** None
- **Issue:** #23

### Task 0.4: Add `odds_source` field to coupon output
- **Tag:** `[MODIFY]`
- **Files:** `scripts/coupon_builder.py`, `scripts/odds_evaluator.py`
- **Change:** Add `odds_source` field to each pick dict. Values: `"api"` (from odds_history DB), `"estimated"` (generated/rounded), `"betclic"` (from validation scrape). When all picks have `odds_source=estimated`, render warning banner in coupon markdown: `⚠️ WSZYSTKIE KURSY SĄ SZACUNKOWE — zweryfikuj w aplikacji Betclic przed postawieniem.`
- **Acceptance criteria:** Coupon markdown shows odds source per pick. Warning banner appears when 100% estimated. No existing test regression.
- **Dependencies:** None
- **Issue:** #14

### Task 0.5: Document S7→S8 Extended Pool contract
- **Tag:** `[MODIFY]`
- **Files:** `scripts/agent_protocol.py`, `scripts/coupon_builder.py` (docstring)
- **Change:** Add docstring/comment clarifying: Extended Pool = `gate_results WHERE status='EXTENDED'` (candidates that passed some gate checks but not all). Add to `STEP_AGENT_CONFIG["s8_coupon"]` detailed instructions.
- **Acceptance criteria:** `grep -r "Extended Pool" scripts/` returns clear definition. No code change needed — documentation only.
- **Dependencies:** None
- **Issue:** #29

### Task 0.6: Create canonical PIPELINE_STEPS registry
- **Tag:** `[MODIFY]`
- **Files:** `scripts/agent_protocol.py`
- **Change:** Add `PIPELINE_STEPS` dict at module level:
  ```python
  PIPELINE_STEPS = {
      "S0": {"script": "analyze_betclic_learning.py", "agent": None, "description": "Historical learning"},
      "S1": {"script": "discover_events.py", "agent": "bet-scanner", "description": "Event discovery"},
      "S1.5": {"script": "build_shortlist.py", "agent": "bet-scanner", "description": "Shortlist build"},
      "S2": {"script": "data_enrichment_agent.py", "agent": "bet-enricher", "description": "Data enrichment"},
      "S2T": {"script": "tipster_aggregator.py", "agent": "bet-scout", "description": "Tipster aggregation"},
      "S3": {"script": "deep_stats_report.py", "agent": "bet-statistician", "description": "Deep stats analysis"},
      "S4": {"script": "odds_evaluator.py", "agent": "bet-valuator", "description": "Odds & EV evaluation"},
      "S5": {"script": "context_checks.py", "agent": "bet-challenger", "description": "Context checks"},
      "S6": {"script": "upset_risk.py", "agent": "bet-challenger", "description": "Upset risk assessment"},
      "S7": {"script": "gate_checker.py", "agent": "bet-gatekeeper", "description": "Gate check"},
      "S7.5": {"script": "validate_betclic_markets.py", "agent": None, "description": "Betclic market validation"},
      "S8": {"script": "coupon_builder.py", "agent": "bet-portfolio", "description": "Coupon construction"},
  }
  ```
- **Acceptance criteria:** `PIPELINE_STEPS` is importable. Each entry maps unambiguously to one script and one agent. `STEP_AGENT_CONFIG` keys align with `PIPELINE_STEPS` keys.
- **Dependencies:** None
- **Issue:** #11

---

## Phase 1: Data Quality Gates (1-2 sessions)

Validation enforcement, dedup fix, budget enforcement, diversity constraints.

### Task 1.1: Centralize stat validation in StatsRepo
- **Tag:** `[MODIFY]`
- **Files:** `src/bet/db/repositories.py`, `src/bet/stats/value_ranges.py`
- **Change:**
  1. Import `SPORT_VALUE_RANGES` from `src/bet/stats/value_ranges.py` into `repositories.py`
  2. In `StatsRepo.save_team_form()` (or equivalent upsert method), add validation BEFORE the INSERT/UPDATE:
     ```python
     def save_team_form(self, team_id, sport_id, stat_key, l10_values, ...):
         sport_name = self._get_sport_name(sport_id)
         ranges = SPORT_VALUE_RANGES.get(sport_name, {}).get(stat_key)
         if ranges:
             l10_values = [v for v in l10_values if ranges[0] <= v <= ranges[1]]
             if not l10_values:
                 logger.warning(f"All values out of range for {sport_name}/{stat_key}: rejected")
                 return None
         # proceed with write
     ```
  3. Add same validation to `save_h2h()` method
  4. Ensure `data_enrichment_agent._save_to_db()`, `build_stats_cache.py`, `ingest_scan_stats.py`, and `google_sports_client.py` all route through `StatsRepo`
- **Acceptance criteria:** 
  - Writing `corners=989` to football `team_form` via ANY code path is rejected
  - Unit test: `test_stats_repo_rejects_out_of_range()` passes
  - Existing pipeline run produces identical output (no false rejections of valid data)
- **Dependencies:** None
- **Issue:** #3

### Task 1.2: Fix duplicate fixture detection with fuzzy matching
- **Tag:** `[MODIFY]`
- **Files:** `src/bet/discovery/deduplication.py` (or equivalent), `scripts/coupon_builder.py`
- **Change:**
  1. Create `normalize_team_name(name: str) -> str` in `src/bet/utils/text.py`:
     - Strip suffixes: "FC", "SC", "CF", "W" (women), "U21", "U19", "II", "B"
     - Normalize: "São Paulo" → "Sao Paulo", "Ñ" → "N"
     - Strip punctuation/hyphens: "Botafogo-PB" → "Botafogo PB"
  2. In dedup logic, replace exact `min(home,away)|max(home,away)|date` with:
     ```python
     from rapidfuzz import fuzz
     key_a = normalize_team_name(home) + "|" + normalize_team_name(away)
     # Compare against existing keys with fuzz.ratio threshold >= 80
     ```
  3. In `coupon_builder.py` coupon stress test, add duplicate event check using same normalization
- **Acceptance criteria:**
  - "Botafogo FC PB vs AA Internacional Limeira SP" matches "Botafogo-PB vs Inter de Limeira" (ratio ≥80)
  - Unit test with 10 known variant pairs all detected
  - No false positives on distinct teams (e.g., "Inter Miami" ≠ "Inter Milan")
- **Dependencies:** `rapidfuzz` already installed
- **Issue:** #5

### Task 1.3: Enforce data quality gate in coupon builder
- **Tag:** `[MODIFY]`
- **Files:** `scripts/coupon_builder.py`
- **Change:**
  1. When selecting picks for core coupons, filter: only `data_quality_score >= 4` (PARTIAL or FULL)
  2. Candidates with `data_quality_score < 4` (MINIMAL) go to Extended Pool section only
  3. Log: `INFO: {n} candidates moved to Extended Pool (MINIMAL data quality)`
  4. Keep all candidates visible in the market matrix (R3 compliance) — just don't auto-include MINIMAL in core coupons
- **Acceptance criteria:**
  - Core coupon legs all have `data_quality >= PARTIAL`
  - MINIMAL candidates appear in Extended Pool section of coupon markdown
  - No R3 violation (nothing auto-rejected from the matrix)
- **Dependencies:** `data_quality_score` already computed in S3
- **Issue:** #6

### Task 1.4: Add market diversity constraint
- **Tag:** `[MODIFY]`
- **Files:** `scripts/coupon_builder.py`
- **Change:**
  1. After singles list is built, add diversity check:
     ```python
     MAX_IDENTICAL_THESIS = 3  # max picks with same market+direction+line
     from collections import Counter
     thesis_counts = Counter((p["market"], p["direction"], p["line"]) for p in singles)
     for thesis, count in thesis_counts.items():
         if count > MAX_IDENTICAL_THESIS:
             excess = [p for p in singles if (p["market"], p["direction"], p["line"]) == thesis]
             # Keep top 3 by safety_score, move rest to Extended Pool
     ```
  2. Add config param `max_identical_thesis` to `betting_config.json` (default 3)
  3. Log: `WARNING: {n} singles with identical thesis '{market} {direction} {line}' — trimmed to 3`
- **Acceptance criteria:**
  - 11 "Total Points UNDER 205.5" singles → trimmed to 3 in core, 8 in Extended Pool
  - Config overridable. Unit test verifies trim logic.
- **Dependencies:** None
- **Issue:** #7

### Task 1.5: Enforce budget hard cap
- **Tag:** `[MODIFY]`
- **Files:** `scripts/coupon_builder.py`
- **Change:**
  1. After all coupons + singles built, compute `total_exposure = sum(c["stake"] for c in all_coupons + singles)`
  2. If `total_exposure > config["daily_exposure_range"][1]`:
     ```python
     # Trim lowest-priority items (lowest safety_score singles, then lowest combined-odds combos)
     while total_exposure > max_daily and trimmable_items:
         worst = min(trimmable_items, key=lambda x: x["priority_score"])
         trimmable_items.remove(worst)
         extended_pool.append(worst)
         total_exposure -= worst["stake"]
     ```
  3. Log: `WARNING: Budget cap {max_daily} PLN exceeded ({total}). Trimmed {n} items to Extended Pool.`
  4. Current code at line 1424 already has a section "ENFORCE DAILY CAP" — enhance it to actually trim, not just note
- **Acceptance criteria:**
  - 58 PLN portfolio → trimmed to ≤15 PLN (daily_exposure_range[1])
  - Trimmed items appear in Extended Pool with reason "budget cap"
  - Unit test: given 20 items totaling 30 PLN with cap 15, output ≤15 PLN
- **Dependencies:** None
- **Issue:** #12

### Task 1.6: Enforce event concentration limit
- **Tag:** `[MODIFY]`
- **Files:** `scripts/coupon_builder.py`, `config/betting_config.json`
- **Change:**
  1. Add `"max_event_reuse_across_coupons": 5` to `betting_config.json`
  2. After building all coupons, count event appearances:
     ```python
     from collections import Counter
     event_usage = Counter()
     for coupon in all_coupons:
         for leg in coupon["legs"]:
             event_usage[leg["event_key"]] += 1
     over_exposed = {k: v for k, v in event_usage.items() if v > max_reuse}
     ```
  3. If over-exposed events found: drop excess coupon legs (lowest safety_score ones)
  4. Render warning in coupon: `⚠️ KONCENTRACJA: {event} pojawia się w {n} kuponach`
- **Acceptance criteria:**
  - No single event appears in >5 coupons in final output
  - Warning rendered for any event appearing in >3 coupons
  - Unit test with mock coupons verifies enforcement
- **Dependencies:** None
- **Issue:** #13

### Task 1.7: Improve gate scoring for H2H presence
- **Tag:** `[MODIFY]`
- **Files:** `scripts/gate_checker.py`
- **Change:**
  1. In the 18-point gate logic, increase weight of H2H presence from 1 → 3 points:
     ```python
     # Current: has_h2h → +1 point
     # New: has_h2h_with_data → +3 points (must have ≥3 meetings)
     #       has_h2h_sparse → +1 point (1-2 meetings)
     #       no_h2h → +0 points
     ```
  2. Add gate detail field: `"h2h_depth": "FULL|SPARSE|NONE"`
  3. Candidates with gate_score ≥12 but `h2h_depth=NONE` get flagged: `warning: "No H2H data — statistical inference only"`
- **Acceptance criteria:**
  - Candidate with safety=0.50 and zero H2H gets gate_score ≤10 (previously 12)
  - Candidate with ≥5 H2H meetings gets +3 gate points
  - Gate results JSON includes `h2h_depth` field
- **Dependencies:** None
- **Issue:** #8

### Task 1.8: Add same-competition correlation check in coupon stress test
- **Tag:** `[MODIFY]`
- **Files:** `scripts/coupon_builder.py`
- **Change:**
  1. In `compute_concentration_warnings()` or coupon stress test section, add:
     ```python
     # Detect same-competition pairs in a single coupon
     for coupon in coupons:
         comps = [leg["competition"] for leg in coupon["legs"]]
         comp_counts = Counter(comps)
         for comp, count in comp_counts.items():
             if count >= 2:
                 warnings.append({
                     "type": "same_competition_correlation",
                     "competition": comp,
                     "count": count,
                     "coupon_id": coupon["id"],
                     "flagged": True,
                 })
     ```
  2. Render in markdown: `⚠️ KORELACJA: {count} mecze z {competition} w jednym kuponie`
- **Acceptance criteria:**
  - Two Venezuela Liga matches in one coupon → warning flagged
  - Unit test verifies detection
- **Dependencies:** None
- **Issue:** #30

---

## Phase 2: Architecture Consolidation (2-3 sessions)

Structural fixes: api_clients merge, scraper bridge, dead code removal, enrichment targeting.

### Task 2.1: Consolidate api_clients — Phase A (shim layer)
- **Tag:** `[MODIFY]` + `[CREATE]`
- **Files:** `scripts/api_clients/__init__.py`, `src/bet/api_clients/` (multiple)
- **Change:**
  1. Move unique modules from `scripts/api_clients/` to `src/bet/api_clients/`:
     - `api_basketball.py`, `api_football.py`, `api_football_odds.py`, `api_hockey.py`, `api_tennis.py`, `api_volleyball.py`
     - `balldontlie.py`, `espn_adapter.py`, `football_data_org.py`, `gemini_client.py`, `google_sports_client.py`
     - `moneypuck_client.py`, `nba_api_client.py`, `odds_api_io.py`, `serpapi_client.py`, `thesportsdb.py`, `understat_client.py`
  2. For modules that exist in BOTH directories (base_client, rate_limiter, espn):
     - Keep `src/bet/api_clients/` version as canonical
     - Merge any unique functionality from `scripts/api_clients/` version
  3. Rewrite `scripts/api_clients/__init__.py` as shim:
     ```python
     """Backward-compatibility shim. Canonical location: src/bet/api_clients/"""
     from bet.api_clients import *  # noqa: F401,F403
     from bet.api_clients import get_client, CLIENT_REGISTRY, RateLimiter
     ```
  4. Update `scripts/api_clients/base_client.py` to re-export from `src/bet/api_clients/base_client`
- **Acceptance criteria:**
  - `from api_clients import get_client` still works (via shim)
  - `from bet.api_clients import get_client` also works
  - All pipeline scripts run without import errors
  - Tests pass (637+)
- **Dependencies:** None
- **Issue:** #1

### Task 2.2: Consolidate api_clients — Phase B (update imports)
- **Tag:** `[MODIFY]`
- **Files:** All scripts importing from `api_clients` (grep for `from api_clients`)
- **Change:**
  1. Update all `from api_clients import X` to `from bet.api_clients import X`
  2. Update all `from api_clients.module import X` to `from bet.api_clients.module import X`
  3. After all imports updated, reduce `scripts/api_clients/__init__.py` to deprecation warning shim
- **Acceptance criteria:**
  - Zero `from api_clients import` in any script (only `from bet.api_clients`)
  - Shim still present but unused
  - All tests pass
- **Dependencies:** Task 2.1

### Task 2.3: Consolidate api_clients — Phase C (cleanup)
- **Tag:** `[DELETE]`
- **Files:** `scripts/api_clients/` (all files except `__init__.py`)
- **Change:** Delete all module files. Keep only `__init__.py` with deprecation shim (in case external tools reference it).
- **Acceptance criteria:**
  - `scripts/api_clients/` contains only `__init__.py` and `__pycache__/`
  - All pipeline scripts work
  - Tests pass
- **Dependencies:** Task 2.2

### Task 2.4: Build scraper-to-team_form bridge
- **Tag:** `[CREATE]`
- **Files:** `scripts/scraper_to_team_form.py`
- **Change:**
  1. Read from `league_profiles` and `player_season_stats` tables
  2. Transform scraper data into `team_form` format:
     - `league_profiles.avg_corners_per_match` → `team_form(stat_key='corners', l10_values=[...])`
     - `player_season_stats.goals` → team aggregate per match
  3. Use `StatsRepo.save_team_form()` (benefits from Task 1.1 validation)
  4. Support `--sport`, `--league`, `--dry-run`, `--verbose` flags
  5. Emit `AGENT_SUMMARY:{json}` (R19 compliance)
- **Acceptance criteria:**
  - Running the script populates `team_form` with scraper-sourced data
  - Data passes SPORT_VALUE_RANGES validation
  - `deep_stats_report.py` can read the bridged data (same table, same schema)
  - `--dry-run` shows what would be written without writing
- **Dependencies:** Task 1.1 (validation in StatsRepo)
- **Issue:** #2

### Task 2.5: Decompose `fetch_api_stats.py`
- **Tag:** `[MODIFY]` + `[CREATE]`
- **Files:** `scripts/fetch_api_stats.py`, `src/bet/stats/fetcher.py` (new), `src/bet/stats/fallback_chains.py` (new)
- **Change:**
  1. Extract `fetch_team_stats()`, `fetch_h2h_stats()`, `FALLBACK_CHAINS` into `src/bet/stats/`
  2. `src/bet/stats/fetcher.py`: stateless functions for fetching team/H2H stats via client chain
  3. `src/bet/stats/fallback_chains.py`: `FALLBACK_CHAINS` dict (per-sport ordered source lists)
  4. Update `data_enrichment_agent.py` imports: `from bet.stats.fetcher import fetch_team_stats, fetch_h2h_stats`
  5. Keep `scripts/fetch_api_stats.py` as thin CLI wrapper calling into `src/bet/stats/`
  6. Remove "LEGACY" label from docs — it's now properly decomposed
- **Acceptance criteria:**
  - `from bet.stats.fetcher import fetch_team_stats` works
  - `data_enrichment_agent.py` no longer imports from `fetch_api_stats`
  - CLI `python scripts/fetch_api_stats.py --team "Man City" --sport football` still works
  - Tests pass
- **Dependencies:** Task 2.1 (api_clients consolidated first)
- **Issue:** #16

### Task 2.6: Delete `unified.py` dead code
- **Tag:** `[DELETE]`
- **Files:** `src/bet/api_clients/unified.py`
- **Change:** Delete the file. Remove from `__init__.py` exports. Grep for any import and remove.
- **Acceptance criteria:** Zero `import unified` or `from.*unified` in codebase. Tests pass.
- **Dependencies:** Task 2.1
- **Issue:** #20

### Task 2.7: Make enrichment shortlist-aware by default
- **Tag:** `[MODIFY]`
- **Files:** `scripts/data_enrichment_agent.py`
- **Change:**
  1. Default behavior: enrich only teams from today's shortlist (read `{date}_s2_shortlist.json` or fixtures from today's scan)
  2. Add `--all` flag for full DB enrichment (current behavior)
  3. Logic:
     ```python
     if args.all:
         teams = load_all_teams_from_db()
     else:
         shortlist = load_shortlist(args.date)
         teams = extract_teams_from_shortlist(shortlist)
     ```
  4. Log: `INFO: Enriching {len(teams)} teams from shortlist (use --all for full DB)`
- **Acceptance criteria:**
  - Default run enriches only shortlisted teams (typically 50-200, not 6000+)
  - `--all` preserves old behavior
  - Enrichment completes in <2 min for shortlist mode (vs 8+ min for all)
  - `--shortlist path/to/shortlist.json` accepted as explicit override
- **Dependencies:** None
- **Issue:** #4

---

## Phase 3: Methodology Enforcement (1-2 sessions)

Gate improvements, Betclic validation insertion, settlement expansion, H2H enforcement.

### Task 3.1: Insert Betclic market validation as S7.5
- **Tag:** `[MODIFY]`
- **Files:** `scripts/validate_betclic_markets.py`, `scripts/gate_checker.py`, `scripts/agent_protocol.py`
- **Change:**
  1. In `PIPELINE_STEPS` (from Task 0.6), add S7.5 entry
  2. In `gate_checker.py` or as post-gate step: load `betclic_market_validation_{date}.json` and mark any UNAVAILABLE picks as `status='REJECTED'` with reason `"betclic_market_unavailable"`
  3. Alternative approach: `validate_betclic_markets.py` reads `gate_results` and updates status directly:
     ```python
     # After scanning Betclic:
     for pick in gate_approved:
         if pick["market"] in unavailable_markets[pick["event"]]:
             update_gate_status(pick, "REJECTED", reason="betclic_market_unavailable")
     ```
  4. Rejected picks move to Extended Pool with note: "Rynek niedostępny na Betclic — szukaj alternatywy"
- **Acceptance criteria:**
  - Running S7.5 after S7 removes unavailable markets from APPROVED status
  - Coupon builder never receives UNAVAILABLE picks
  - Extended Pool shows rejected-by-Betclic picks with alternative market suggestions
  - Orchestrator protocol documents S7.5 as mandatory between S7 and S8
- **Dependencies:** Task 0.6 (PIPELINE_STEPS)
- **Issue:** #9

### Task 3.2: Enforce H2H validation in deep stats
- **Tag:** `[MODIFY]`
- **Files:** `scripts/deep_stats_report.py`
- **Change:**
  1. When computing `data_quality_score`, add H2H-specific component:
     - Has ≥5 H2H meetings with stat data → +2 DQ points
     - Has 1-4 H2H meetings → +1 DQ point
     - Has 0 H2H meetings → +0, add warning `"H2H-STAT-BLIND"`
  2. In per-candidate output, add explicit field: `"h2h_status": "FULL|SPARSE|BLIND"`
  3. Add warning to market ranking when H2H is blind: safety score gets `* 0.85` multiplier (15% penalty for missing cross-check)
  4. Do NOT auto-reject (R3 compliance) — but the DQ score reduction naturally pushes BLIND candidates toward Extended Pool via Task 1.3
- **Acceptance criteria:**
  - Candidates with 0 H2H meetings show `h2h_status: BLIND` and lower DQ scores
  - League-level generalizations explicitly marked as such (not presented as H2H data)
  - Market safety scores reflect reduced confidence from missing H2H
- **Dependencies:** None
- **Issue:** #10

### Task 3.3: Expand settlement for statistical markets
- **Tag:** `[MODIFY]`
- **Files:** `scripts/settle_on_finish.py`
- **Change:**
  1. Add Flashscore match statistics fetching via `curl_cffi`:
     ```python
     # After match finishes, fetch stats page:
     # https://www.flashscore.com/match/{match_id}/#/match-summary/match-statistics
     # Extract: corners, yellow cards, red cards, shots on target
     ```
  2. Auto-settle statistical markets: corners O/U, cards O/U, shots O/U
  3. Still manual: HC (handicap), MyCombi (complex combos)
  4. Add `--fetch-stats` flag (default ON for football, OFF for others until stats pages confirmed)
  5. Use `flashscore_enricher.py` patterns for curl_cffi access
- **Acceptance criteria:**
  - Football match with corners O/U 9.5 → auto-settled when Flashscore shows total corners
  - Settlement adds `settlement_source: "flashscore_stats"` to settled bets
  - Manual markets still prompt for manual input
  - Rate limiting: max 30 Flashscore requests per settlement run
- **Dependencies:** None (Flashscore curl_cffi already working)
- **Issue:** #15

### Task 3.4: Reduce NON-NEGOTIABLE rules from 21 to 10
- **Tag:** `[MODIFY]`
- **Files:** `.github/copilot-instructions.md`
- **Change:**
  Merge related rules:
  | New Rule | Merges Old Rules | Core Statement |
  |----------|-----------------|----------------|
  | R1 | R1 + R17 + R19 | Agent-driven pipeline: run scripts async+verbose, parse AGENT_SUMMARY, delegate to specialists |
  | R2 | R2 | DB-first: always `get_db()`, never raw sqlite3 |
  | R3 | R3 + R4 + R6 | No auto-rejection: all candidates in matrix, user decides. Betclic history = advisory. |
  | R4 | R5 + R10 | Stats-first: statistical markets before outcomes, events without odds still analyzed |
  | R5 | R7 + R8 + R13 | League protection: tournaments +15, protected domestics +10, minor leagues +6 |
  | R6 | R9 + R15 | Self-healing data: 7 fallback layers including web research agent |
  | R7 | R11 | Sequential thinking: mandatory per pipeline step and per candidate |
  | R8 | R12 + R16 | Conditional picks: user verifies on Betclic, live betting valid |
  | R9 | R14 + R18 | Data quality: DQ score mandatory, verify data flow before scripts |
  | R10 | R20 + R21 | Fish shell: no inline Python, pylance-first for inspection |

  Move detailed specifics to `agent-execution-protocol.instructions.md` (where they already partially live).
- **Acceptance criteria:**
  - `copilot-instructions.md` NON-NEGOTIABLE section has exactly 10 rules
  - Each rule is ≤4 lines (one statement + one clarification)
  - All original rule content preserved in referenced instruction files
  - No behavioral change — same rules, less text
- **Dependencies:** None
- **Issue:** #18

### Task 3.5: Add source health tracking to non-enrichment scripts
- **Tag:** `[MODIFY]`
- **Files:** `scripts/fetch_odds_api.py`, `scripts/tipster_aggregator.py`, `scripts/discover_events.py`
- **Change:**
  1. After each external API call, log to `source_health` table:
     ```python
     from bet.db.repositories import SourceHealthRepo
     repo = SourceHealthRepo(db)
     repo.record_success("odds-api", response_ms=elapsed)
     # or
     repo.record_failure("odds-api", error_type="timeout")
     ```
  2. Add `SourceHealthRepo` if not existing (or verify it exists in repositories.py)
  3. Each script logs source health for its primary sources:
     - `fetch_odds_api.py`: "odds-api", "odds-api-io"
     - `tipster_aggregator.py`: per-site ("zawodtyper", "feedinco", etc.)
     - `discover_events.py`: "sofascore", "odds-api", "api-football"
- **Acceptance criteria:**
  - `source_health` table updated by all 3 scripts
  - `bet-scanner` agent can query source reliability across all pipeline steps
  - No performance impact (async write or batched at end)
- **Dependencies:** None
- **Issue:** #17

---

## Phase 4: Operations & Learning (1 session)

Pre-flight check, learning loop automation, H2H expansion, agent invocation clarity.

### Task 4.1: Create pre-flight check script
- **Tag:** `[CREATE]`
- **Files:** `scripts/preflight_check.py`
- **Change:**
  Create script that validates all pipeline dependencies before S1:
  ```python
  checks = [
      ("API Keys", check_api_keys),        # odds-api, serpapi present & non-empty
      ("Database", check_db_health),        # betting.db exists, schema version correct
      ("Imports", check_critical_imports),   # curl_cffi, rapidfuzz, playwright importable
      ("Config", check_config_valid),       # betting_config.json parseable, bankroll > 0
      ("Disk Space", check_disk_space),     # >100MB free
      ("Stale Data", check_stale_fixtures), # no fixtures from >7 days ago in "pending" status
  ]
  ```
  Exit codes: 0=all pass, 1=warnings only, 2=blocking failure.
  Emit `AGENT_SUMMARY:{json}` with check results.
- **Acceptance criteria:**
  - Running with valid config → exit 0
  - Running with missing API key → exit 2 with clear error message
  - Running with empty Gemini key → exit 1 (warning, not blocking)
  - All checks complete in <5s
- **Dependencies:** None
- **Issue:** #25

### Task 4.2: Auto-append learning log after settlement
- **Tag:** `[MODIFY]`
- **Files:** `scripts/settle_on_finish.py`, `betting/journal/learning-log.md`
- **Change:**
  1. After successful settlement, auto-append structured entry to `learning-log.md`:
     ```markdown
     ## {date} — Settlement Summary
     - **Settled:** {n} bets ({wins}W / {losses}L / {voids}V)
     - **Day PnL:** {pnl} PLN ({pct}% of bankroll)
     - **Best market:** {market} ({hit_rate}% hit rate today)
     - **Worst market:** {market} ({hit_rate}% hit rate today)
     - **CLV avg:** {clv}%
     - **Rule changes:** None (auto-generated, review manually)
     ```
  2. Include per-sport breakdown if ≥3 bets settled
  3. Flag: if `day_pnl < -20%_bankroll` → append `⚠️ DRAWDOWN ALERT`
  4. Never overwrite existing entries (append-only)
- **Acceptance criteria:**
  - After `settle_on_finish.py` completes, `learning-log.md` has new dated entry
  - Entry contains actual PnL, hit rates, CLV from that day's settlements
  - Running settlement twice doesn't duplicate the entry (idempotent check by date)
- **Dependencies:** None
- **Issue:** #19

### Task 4.3: Add BetExplorer H2H as fallback source
- **Tag:** `[CREATE]`
- **Files:** `src/bet/api_clients/betexplorer_h2h.py`
- **Change:**
  1. Implement BetExplorer H2H scraper using curl_cffi:
     ```python
     # URL pattern: https://www.betexplorer.com/h2h/{team-a-slug}/{team-b-slug}/
     # Extract: last 10 meetings, scores, dates, competition
     ```
  2. Add to `FALLBACK_CHAINS` for all 5 sports as position after Google Sports
  3. Write to `h2h_stats` table via existing schema
  4. Respect rate limiting (max 20 req/min)
- **Acceptance criteria:**
  - `fetch_h2h("Barcelona", "Real Madrid", "football")` returns ≥5 meetings from BetExplorer
  - Data written to `h2h_stats` table
  - Graceful degradation on 403/timeout
- **Dependencies:** Task 2.5 (fallback chains in proper location)
- **Issue:** #26

### Task 4.4: Add agent invocation map
- **Tag:** `[MODIFY]`
- **Files:** `scripts/agent_protocol.py`
- **Change:**
  1. Add `AGENT_INVOCATION_MAP` dict:
     ```python
     AGENT_INVOCATION_MAP = {
         "bet-scanner": {"trigger": "S1 complete", "receives": "s1_events.json", "produces": "scan verdict"},
         "bet-enricher": {"trigger": "S2 complete", "receives": "enrichment logs", "produces": "data quality verdict"},
         "bet-scout": {"trigger": "S2T complete", "receives": "tipster data", "produces": "tipster analysis"},
         "bet-statistician": {"trigger": "S3 complete", "receives": "deep_stats.json", "produces": "market rankings review"},
         "bet-valuator": {"trigger": "S4 complete", "receives": "odds evaluation", "produces": "EV/drift verdict"},
         "bet-challenger": {"trigger": "S5+S6 complete", "receives": "context+upset data", "produces": "bear cases"},
         "bet-gatekeeper": {"trigger": "S7 complete", "receives": "gate_results", "produces": "gate audit"},
         "bet-portfolio": {"trigger": "S8 complete", "receives": "coupon data", "produces": "portfolio quality"},
     }
     ```
  2. This codifies what was previously spread across multiple agent .md files
- **Acceptance criteria:**
  - Every agent has exactly one trigger point and clear I/O
  - `AGENT_INVOCATION_MAP` is importable and used by orchestrator for delegation decisions
- **Dependencies:** Task 0.6 (PIPELINE_STEPS)
- **Issue:** #24

### Task 4.5: Add volleyball alternative source
- **Tag:** `[CREATE]`
- **Files:** `src/bet/api_clients/volleyball_data.py`
- **Change:**
  1. Implement CEV statistics or Data.Volleyball API client
  2. Target data: set scores, points per set, aces, blocks, attack efficiency
  3. Add to volleyball `FALLBACK_CHAINS` as primary after Flashscore
  4. Rate limited, curl_cffi based
- **Acceptance criteria:**
  - Volleyball team enrichment returns ≥5 stat keys for top European leagues
  - Integration test with PlusLiga team
  - Graceful fallback when source unavailable
- **Dependencies:** Task 2.5
- **Issue:** #22

### Task 4.6: Add tennis serve stats from sackmann data
- **Tag:** `[CREATE]`
- **Files:** `src/bet/api_clients/tennis_sackmann.py`
- **Change:**
  1. Jeff Sackmann's tennis_atp GitHub repo has match-level CSV data (public domain)
  2. Implement parser for: aces, double_faults, first_serve_pct, break_points_saved
  3. Cache parsed CSVs locally (update weekly)
  4. Write to `team_form` with `source='sackmann'`
- **Acceptance criteria:**
  - Top 100 ATP players have serve stats available
  - Data refreshed from GitHub CSV at most once per day
  - `deep_stats_report.py` can read serve stats for tennis candidates
- **Dependencies:** None
- **Issue:** #21

---

## Dependency Graph

```
Phase 0 (no dependencies, all parallel):
  0.1, 0.2, 0.3, 0.4, 0.5, 0.6

Phase 1 (mostly parallel, some sequencing):
  1.1 → 2.4 (scraper bridge needs validated repo)
  1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8 (all independent)

Phase 2 (sequential chain for api_clients):
  2.1 → 2.2 → 2.3
  2.1 → 2.5, 2.6
  1.1 → 2.4
  2.7 (independent)

Phase 3 (mostly independent):
  0.6 → 3.1
  3.2, 3.3, 3.4, 3.5 (all independent)

Phase 4 (mostly independent):
  2.5 → 4.3, 4.5
  0.6 → 4.4
  4.1, 4.2, 4.6 (independent)
```

---

## Verification Plan

After all phases complete, run a full pipeline day (S0→S8) and verify:

| Metric | Expected | Verification |
|--------|----------|--------------|
| Garbage values in team_form | 0 | `SELECT COUNT(*) FROM team_form WHERE l10_avg > range_max` |
| Duplicate fixtures in coupon | 0 | Fuzzy match check on coupon output |
| Core coupon data quality | All ≥ PARTIAL | `grep "data_quality" coupon.json \| grep MINIMAL` = 0 |
| Budget compliance | ≤ 15 PLN total | Sum stakes in coupon JSON |
| Event concentration | ≤ 5 per event | Count event appearances across coupons |
| Identical thesis limit | ≤ 3 | Count same market+direction+line in singles |
| Betclic unavailable in coupon | 0 | Cross-check with validation JSON |
| H2H depth tracked | All candidates | `h2h_status` field present in S3 output |
| Pre-flight passes | Exit 0 | Run `preflight_check.py` before pipeline |
| Learning log updated | Entry for today | Check `learning-log.md` after settlement |
| Import path canonical | 0 `from api_clients` | `grep -r "from api_clients" scripts/ \| grep -v __pycache__` |
| Source health logged | All scripts | `SELECT DISTINCT source_name FROM source_health` includes odds/tipster/discovery |

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| StatsRepo validation rejects valid edge-case data | Log rejected values for 1 week before hard-reject. Start with `WARNING` mode. |
| api_clients consolidation breaks imports | Shim layer ensures backward compat. Run full test suite after each sub-task. |
| Fuzzy dedup creates false positives | Threshold tuning (80 ratio) + explicit exception list for known distinct teams with similar names |
| Budget cap trims good picks | Trim by priority (lowest safety_score first). User can override via config. |
| Betclic validation delays pipeline | Cache results (48h valid). Only scan sport/competition pages, not individual events unless in coupon. |
| Rule reduction (21→10) loses specifics | All detail preserved in referenced instruction files. Grep verification that no rule content is lost. |
