# Pipeline Overhaul — Implementation Plan

## Task Details

| Field            | Value                                                                 |
| ---------------- | --------------------------------------------------------------------- |
| Title            | Betting Pipeline Overhaul: Self-Healing Enrichment + Inclusive Coupons |
| Description      | Major pipeline overhaul to eliminate bottlenecks that reject most events. Add data enrichment agent, remove artificial caps, make gate advisory, include extended picks in coupons. |
| Priority         | Critical                                                              |

## Proposed Solution

The current pipeline funnels thousands of scanned events through progressively narrower filters — shortlist cap, smart filter in deep stats, 18-point gate check, approved-only coupon builder — resulting in only 5-8 events in final coupons. This overhaul transforms the pipeline from a rejection-first to an enrichment-first architecture:

1. **Data Enrichment Agent** — when team stats are missing, fetch them from internet sources (Flashscore, ESPN, Sofascore) using the existing Playwright infrastructure, persist to DB and stats cache, then re-analyze.
2. **Remove Smart Filter** — the `generate_deep_stats()` SMART FILTER at line 987 skips candidates without pre-existing data. Remove this filter so all candidates get analysis, relying on the enrichment agent to fill gaps.
3. **Advisory Gate** — gate checks become informational labels (STRONG/MODERATE/WEAK/FLAGGED) rather than binary pass/fail classification. Only hard rejects (phantoms, 48h repeat losses) remain blocking.
4. **Inclusive Coupon Builder** — all non-rejected picks feed into coupon construction, organized in tiers: CORE (STRONG gate), VALUE (MODERATE), DISCOVERY (WEAK/FLAGGED).
5. **Pipeline Step S2.5** — new enrichment step between shortlist (S1e) and deep stats (S3) that batch-enriches all candidates with missing data.

```
CURRENT:  Scan → Shortlist(cap) → SmartFilter → DeepStats → Gate(reject) → Coupon(approved-only)
                      ↓ drop              ↓ drop           ↓ drop           ↓ drop
                  ~17K → ~100          ~100 → ~30        ~30 → ~15        ~15 → ~8

PROPOSED: Scan → Shortlist(all) → S2.5:Enrich → DeepStats(all) → Gate(advisory) → Coupon(all tiers)
                  ~17K → ~17K*      fetch missing      analyze all       label only      tiered output
                  (*garbage filter only)
```

## Current Implementation Analysis

### Already Implemented

Components that will be reused as-is:

- `fetch_with_playwright.py` — `scripts/fetch_with_playwright.py` — Playwright fetcher with cookie handling, proxy rotation, storage state. Reused by enrichment agent.
- `db_data_loader.py` — `scripts/db_data_loader.py` — DB-first data loading with JSON fallback. Reused for reading/writing enriched data.
- `bet.db.repositories.StatsRepo` — `src/bet/db/repositories.py` — DB repository for team_form persistence.
- `bet.db.repositories.TeamRepo` — `src/bet/db/repositories.py` — Team resolution (name → ID) with fuzzy matching.
- `compute_safety_scores.py` — `scripts/compute_safety_scores.py` — Market ranking engine. No changes needed.
- `normalize_stats.py` — `scripts/normalize_stats.py` — Safety input builder from cache/DB data.
- `api_clients/espn_adapter.py` — ESPN multi-league client for basketball/hockey/baseball enrichment.
- `scanners/` — Per-sport Playwright scanner infrastructure with domain semaphores.
- `site_selectors.json` — Cookie/consent selectors per domain for Playwright.
- `utils.py` — `scripts/utils.py` — `normalize_team_name()`, `normalize_kickoff()`.
- `check_48h_repeats.py` — `scripts/check_48h_repeats.py` — 48h repeat loss detection.

### To Be Modified

- `deep_stats_report.py` — `scripts/deep_stats_report.py` — Remove SMART FILTER (lines 987-997), add enrichment retry loop in `extract_team_stats()` and `extract_h2h_stats()`, batch enrichment before analysis.
- `gate_checker.py` — `scripts/gate_checker.py` — Change classification logic in `run_gate()` (lines 1047-1064): replace approved/extended/rejected with advisory labels STRONG/MODERATE/WEAK/FLAGGED. Keep hard reject for phantoms and 48h repeats only.
- `coupon_builder.py` — `scripts/coupon_builder.py` — `build_coupons()` (line 1011): use all non-rejected picks organized in CORE/VALUE/DISCOVERY tiers. Add confidence_discount for weaker picks.
- `pipeline_orchestrator.py` — `scripts/pipeline_orchestrator.py` — Add S2.5 enrichment step to PIPELINE_STEPS list, update `_run_s3()` to not pass `top` limit, remove `--top` from S1e command.
- `build_shortlist.py` — `scripts/build_shortlist.py` — Remove `top_n` cap in `build_shortlist()` function, keep garbage filter, ensure all viable events pass through.
- `agent_protocol.py` — `scripts/agent_protocol.py` — Add enrichment agent (s2_5_enrich) to STEP_AGENT_CONFIG.

### To Be Created

- `scripts/data_enrichment_agent.py` — Self-healing enrichment agent that fetches missing team stats and H2H data from internet sources using Playwright. Accepts batch input, parallelizes fetching, persists to DB + stats cache JSON, returns enrichment report.

## Open Questions

| #   | Question                                                                 | Answer                                                                                   | Status       |
| --- | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- | ------------ |
| 1   | Should the enrichment agent have its own timeout or use STEP_TIMEOUTS?   | Use STEP_TIMEOUTS system with configurable per-sport timeouts                            | ✅ Resolved  |
| 2   | How many parallel enrichment workers?                                    | Default 4, configurable. Respect domain semaphores from existing scanner infrastructure   | ✅ Resolved  |
| 3   | Should stats-first mode change?                                          | No — stats-first mode remains. Enrichment adds data but user still verifies odds on Betclic | ✅ Resolved  |
| 4   | What minimum score threshold replaces top_n?                             | Score < 3 filtered (garbage only). All other events proceed                              | ✅ Resolved  |
| 5   | Should extended picks use Kelly 1/4 staking?                             | Yes, with confidence_discount multiplier (0.5 for VALUE, 0.25 for DISCOVERY)             | ✅ Resolved  |

## Implementation Plan

### Phase 1: Data Enrichment Agent

#### Task 1.1 — [CREATE] `scripts/data_enrichment_agent.py`

**Description**: Create a new self-healing data enrichment agent that fetches missing team statistics from internet sources using the existing Playwright infrastructure. The agent accepts a batch of `(team_name, sport, what_missing)` tuples, fetches data from sport-specific sources in parallel (respecting domain semaphores), parses HTML responses to extract L10 form data, and persists results to both the SQLite DB (`team_form` table via `StatsRepo`) and the JSON stats cache (`betting/data/stats_cache/{sport}/{slug}.json`).

**Key implementation details**:
- Import and reuse `fetch_with_playwright.fetch()` for Playwright page fetching
- Sport-to-sources mapping:
  - Football: `flashscore.com/team/{slug}/results/`, `sofascore.com/team/{slug}`
  - Tennis: `flashscore.com/player/{slug}/results/`, `tennisexplorer.com/player/{slug}/`
  - Basketball: `flashscore.com/team/{slug}/results/`, ESPN API via `api_clients/espn_adapter.py`
  - Hockey: `flashscore.com/team/{slug}/results/`, ESPN API
  - Baseball: ESPN API (primary), `flashscore.com/team/{slug}/results/`
  - All others: `flashscore.com` (universal fallback)
- HTML parsing: extract last 10 match results with stat breakdowns per `SPORT_STAT_KEYS`
- Fallback chain: try source A → on failure try source B → return partial data if available
- Persist to DB: use `TeamRepo.resolve()` to get/create team, then `StatsRepo` to write `team_form`
- Persist to stats cache JSON: write `betting/data/stats_cache/{sport}/{slug}.json` in the format expected by `extract_team_stats()`
- H2H enrichment: fetch H2H page from Flashscore, parse last 10 meetings
- ThreadPoolExecutor with `max_workers` (default 4), respect existing `DomainSemaphoreMap` from scanners
- Error handling: per-team try/except with retry (2 attempts per source), log failures, continue with remaining teams
- Return value: `{enriched: [...], failed: [...], stats: {fetched: int, cached: int, failed: int}}`

**Definition of Done**:

- [ ] File `scripts/data_enrichment_agent.py` exists with functions `enrich_teams(missing, max_workers)`, `enrich_team(team_name, sport)`, `enrich_h2h(team_a, team_b, sport)`
- [ ] `enrich_team()` fetches from at least 2 sources per sport with fallback chain
- [ ] Successfully fetched data is written to both DB (team_form table) and stats cache JSON
- [ ] Stats cache JSON format matches what `deep_stats_report.extract_team_stats()` reads: `{form: {l10_avg: {stat: val}, l5_avg: {stat: val}, l10_matches: [...]}, sources: [...]}`
- [ ] `enrich_teams()` runs in parallel with ThreadPoolExecutor, max 4 concurrent fetches
- [ ] Each fetch has a 30-second timeout, 2 retry attempts per source
- [ ] Failed enrichments are logged but don't crash the batch
- [ ] Script can be run standalone: `python3 scripts/data_enrichment_agent.py --team "Real Madrid" --sport football`
- [ ] Unit tests in `tests/test_data_enrichment_agent.py` cover: source selection per sport, cache write format, batch parallel execution, error handling on fetch failure

#### Task 1.2 — [CREATE] `tests/test_data_enrichment_agent.py`

**Description**: Unit tests for the data enrichment agent. Mock Playwright fetches to avoid real network calls. Test source selection, HTML parsing stubs, DB persistence, cache format, batch execution, and error handling.

**Definition of Done**:

- [ ] Test file exists at `tests/test_data_enrichment_agent.py`
- [ ] Tests cover: source URL generation per sport, cache JSON format validation, batch enrichment with mixed success/failure, DB write verification (mocked), timeout handling
- [ ] All tests pass with `pytest tests/test_data_enrichment_agent.py`

---

### Phase 2: Remove Artificial Caps

#### Task 2.1 — [MODIFY] `scripts/build_shortlist.py` — Remove top_n cap

**Description**: Modify the `build_shortlist()` function to always pass all viable candidates. The `top_n` parameter should default to 0 (= no cap) and the CLI `--top` argument should default to 0. Add a minimum score threshold of 3 to filter only truly garbage events (currently the function already has garbage regex filtering; add a score threshold as well). The function already returns all events when `top_n=0`, but the CLI argument and orchestrator may pass non-zero values.

**Files**: `scripts/build_shortlist.py`

**Changes**:
- Ensure `--top` CLI argument defaults to `0`
- In `build_shortlist()`: when `top_n > 0`, still apply it (backward compatibility for manual runs), but add prominent log: `"Passing ALL {N} viable candidates (score ≥ 3) to deep analysis"`
- Add score threshold filter: `scored = [(s, e) for s, e in scored if s >= 3]` after garbage filtering
- Log count of filtered-by-score events

**Definition of Done**:

- [ ] `build_shortlist()` with `top_n=0` returns all events scoring ≥ 3
- [ ] Events with score < 3 are filtered with log message showing count
- [ ] CLI `--top 0` or omitted `--top` passes all viable candidates
- [ ] Existing scoring algorithm unchanged (sorting still works for priority)
- [ ] Log output shows: `"[shortlist] Passing ALL {N} viable candidates (score ≥ 3) to deep analysis"`

#### Task 2.2 — [MODIFY] `scripts/deep_stats_report.py` — Remove SMART FILTER

**Description**: Remove or replace the SMART FILTER (lines 987-997) that skips candidates without `safety_markets`, `n_odds_markets > 0`, or `fixture_verified`. This filter currently drops ~95% of candidates. Replace with a softer filter that only skips candidates with completely empty team names.

**Files**: `scripts/deep_stats_report.py`

**Changes**:
- Remove the SMART FILTER block (lines 987-997 of `generate_deep_stats()`)
- Remove the `top` parameter cap (line 985: `candidates = candidates[:top]`)
- Add log: `"[deep_stats] Processing ALL {N} candidates (no smart filter)"`
- Keep the team-name validity filter (line 999-1000) that skips empty names

**Definition of Done**:

- [ ] `generate_deep_stats()` no longer applies the SMART FILTER that requires `safety_markets` or `n_odds_markets > 0`
- [ ] `top` parameter still accepted for backward compatibility but ignored when value is 0 or None
- [ ] All candidates with valid team names are analyzed
- [ ] Log output confirms: `"Processing ALL {N} candidates"`
- [ ] Performance is acceptable (ThreadPoolExecutor with 8 workers handles large candidate lists)

#### Task 2.3 — [MODIFY] `scripts/pipeline_orchestrator.py` — Remove --top from S1e and S3

**Description**: Update the orchestrator to not pass `--top` limit to the shortlist builder or deep stats report. The S1e step command already uses `--stats-first` without `--top`. Ensure `_run_s3()` does not pass the `top` parameter to `generate_deep_stats()`.

**Files**: `scripts/pipeline_orchestrator.py`

**Changes**:
- In `_run_s3()` (around line 802): change `result = generate_deep_stats(date, shortlist_path=shortlist_path, top=top)` to `result = generate_deep_stats(date, shortlist_path=shortlist_path)` — remove the `top` parameter pass
- Verify S1e step command in PIPELINE_STEPS doesn't include `--top`

**Definition of Done**:

- [ ] `_run_s3()` calls `generate_deep_stats()` without `top` parameter
- [ ] S1e pipeline step command does not include `--top` flag
- [ ] Pipeline state `cli_args` still stores `top` for debug purposes but doesn't use it

---

### Phase 3: Advisory Gate Checker

#### Task 3.1 — [MODIFY] `scripts/gate_checker.py` — Advisory classification

**Description**: Change the classification logic in `run_gate()` (lines 1047-1064) from binary approved/extended/rejected to advisory labels. All non-hard-rejected candidates pass through. The existing 18 gate checks remain unchanged — they provide valuable signal. Only the classification at the end changes.

**Files**: `scripts/gate_checker.py`

**Changes**:
- Add new constants at module level:
  ```python
  ADVISORY_LABELS = {
      "STRONG": (0, 2),    # 0-2 failures
      "MODERATE": (3, 5),  # 3-5 failures
      "WEAK": (6, 9),      # 6-9 failures
      "FLAGGED": (10, 18), # 10+ failures
  }
  ```
- In `run_gate()`, replace classification block (lines 1047-1064):
  - Hard reject: unchanged (only for "HARD REJECT" in gate detail messages)
  - All other candidates: assign advisory label based on `n_failed` count
  - ALL non-rejected candidates go into `approved` list (renamed conceptually to `all_candidates`)
  - `extended_pool` becomes empty (backward compat: kept as empty list)
  - Each candidate gets `advisory_label` field: STRONG/MODERATE/WEAK/FLAGGED
  - Each candidate gets `gate_failures` count
- Keep `risk_tier` computation unchanged (LR/MS/HR/N)
- Gate output JSON structure remains compatible: `gate_results.approved` contains ALL non-rejected candidates (coupon builder reads this)
- Add `advisory_label` to the entry dict returned per candidate

**Definition of Done**:

- [ ] `run_gate()` returns all non-hard-rejected candidates in `gate_results.approved`
- [ ] Each candidate has `advisory_label` field: STRONG, MODERATE, WEAK, or FLAGGED
- [ ] `gate_results.extended_pool` is empty list (backward compat preserved)
- [ ] `gate_results.rejected` contains only hard-rejected candidates (phantoms, 48h repeat losses with "HARD REJECT")
- [ ] All 18 gate checks still execute and their results are stored in `gate_details`
- [ ] `gate_score`, `risk_tier`, `final_confidence` computations unchanged
- [ ] Summary includes: `strong_count`, `moderate_count`, `weak_count`, `flagged_count` alongside existing `approved_count`
- [ ] Unit tests verify: candidate with 1 failure → STRONG label; candidate with 7 failures → WEAK label; candidate with "HARD REJECT" → rejected

#### Task 3.2 — [CREATE] `tests/test_gate_checker_advisory.py`

**Description**: Unit tests for the advisory gate classification. Test that candidates are correctly labeled and that hard rejects still work.

**Definition of Done**:

- [ ] Test file exists at `tests/test_gate_checker_advisory.py`
- [ ] Tests cover: STRONG (0-2 failures), MODERATE (3-5), WEAK (6-9), FLAGGED (10+), hard reject preserved
- [ ] Tests verify backward compatibility: `gate_results` dict structure unchanged
- [ ] All tests pass

---

### Phase 4: Inclusive Coupon Builder

#### Task 4.1 — [MODIFY] `scripts/coupon_builder.py` — Tiered coupon construction

**Description**: Modify `build_coupons()` to use all non-rejected picks for coupon construction, organized in tiers. Currently the function only uses `approved` picks (line 1022). After Phase 3, all non-rejected picks are in `approved`, but they have different `advisory_label` values. The coupon builder should create tiered coupons:

- **CORE** tier: picks with `advisory_label` STRONG — full Kelly 1/4 stake
- **VALUE** tier: picks with `advisory_label` MODERATE — Kelly 1/4 × 0.5 confidence discount
- **DISCOVERY** tier: picks with `advisory_label` WEAK or FLAGGED — Kelly 1/4 × 0.25 confidence discount

**Files**: `scripts/coupon_builder.py`

**Changes**:
- In `build_coupons()`:
  - All picks from `approved` list are used (this now includes what was previously `extended_pool`)
  - Split picks by `advisory_label` into CORE/VALUE/DISCOVERY buckets
  - `assign_picks_to_core()` uses CORE picks (STRONG label)
  - New function `assign_picks_to_value()` builds VALUE tier coupons from MODERATE picks with 0.5× stake multiplier
  - New function `assign_picks_to_discovery()` builds DISCOVERY tier coupons from WEAK/FLAGGED picks with 0.25× stake multiplier
  - `generate_combos()` uses ALL picks (allows cross-tier combos)
  - Result dict adds: `value_coupons`, `discovery_coupons` keys
  - Singles generated for ALL picks (with tier label)
- In markdown/JSON output writers: separate sections for CORE/VALUE/DISCOVERY
- Daily cap enforcement: CORE first → VALUE → DISCOVERY → combos → singles

**Definition of Done**:

- [ ] `build_coupons()` creates CORE, VALUE, and DISCOVERY tier coupons
- [ ] CORE coupons use STRONG-labeled picks with full Kelly 1/4 stakes
- [ ] VALUE coupons use MODERATE-labeled picks with 0.5× stake multiplier
- [ ] DISCOVERY coupons use WEAK/FLAGGED-labeled picks with 0.25× stake multiplier
- [ ] Combo menu uses all picks (cross-tier combinations allowed)
- [ ] Singles generated for all non-rejected picks with appropriate tier labels
- [ ] Daily cap enforcement prioritizes: CORE → VALUE → DISCOVERY → combos → singles
- [ ] Output JSON has `core_coupons`, `value_coupons`, `discovery_coupons`, `combos`, `singles` keys
- [ ] Markdown output has separate sections per tier
- [ ] Backward compatibility: if no `advisory_label` field exists on picks, all treated as CORE (legacy behavior)

#### Task 4.2 — [MODIFY] `scripts/coupon_builder.py` — Update markdown/JSON writers

**Description**: Update `write_coupon_markdown()` and `write_coupon_json()` to include VALUE and DISCOVERY tier sections in the output files.

**Definition of Done**:

- [ ] Markdown output includes `## KUPON VALUE` and `## KUPON DISCOVERY` sections after core coupons
- [ ] JSON output includes `value_coupons` and `discovery_coupons` arrays
- [ ] Each coupon in VALUE/DISCOVERY tier clearly labeled with tier name and confidence discount
- [ ] Summary section shows total spend per tier

---

### Phase 5: Self-Healing Deep Stats

#### Task 5.1 — [MODIFY] `scripts/deep_stats_report.py` — Enrichment retry in extract functions

**Description**: Add enrichment retry logic to `extract_team_stats()` and `extract_h2h_stats()`. When data is missing (returns `has_data=False`), call the enrichment agent to fetch from internet, then retry extraction. This makes the deep stats report self-healing — it tries to fill gaps rather than accepting missing data.

**Files**: `scripts/deep_stats_report.py`

**Changes**:
- In `generate_deep_stats()`, before the analysis loop:
  1. First pass: collect all teams that need enrichment (run `extract_team_stats()` for each, note which return `has_data=False`)
  2. Batch enrich: call `data_enrichment_agent.enrich_teams(missing_list)` with all missing teams
  3. Second pass: run the full analysis (which will now find data in cache/DB for enriched teams)
- In `analyze_candidate()`:
  - When `extract_team_stats()` returns `has_data=False`, mark as `"ENRICHMENT_ATTEMPTED"` (enrichment was already done in batch)
  - Continue with partial data — don't skip the candidate
- Enrichment is optional: if `data_enrichment_agent` import fails, log warning and proceed without enrichment (backward compat)

**Definition of Done**:

- [ ] `generate_deep_stats()` collects all teams with missing data before analysis loop
- [ ] Calls `data_enrichment_agent.enrich_teams()` with batch of missing teams
- [ ] After enrichment, analysis loop re-reads from cache/DB (which now has enriched data)
- [ ] Candidates where enrichment also failed are marked `ENRICHMENT_FAILED` but still analyzed with partial data
- [ ] If `data_enrichment_agent` is not importable, pipeline proceeds without enrichment (graceful degradation)
- [ ] Log output shows: `"[deep_stats] Enrichment batch: {N} teams to enrich, {M} succeeded, {K} failed"`
- [ ] Performance: enrichment runs with ThreadPoolExecutor (4 workers), total timeout capped at 300s

#### Task 5.2 — [CREATE] `tests/test_deep_stats_enrichment.py`

**Description**: Unit tests for the enrichment integration in deep_stats_report. Mock the enrichment agent to verify the batch-enrich-then-analyze flow.

**Definition of Done**:

- [ ] Tests verify batch collection of missing teams
- [ ] Tests verify enrichment agent is called with correct team list
- [ ] Tests verify re-analysis after enrichment finds data
- [ ] Tests verify graceful degradation when enrichment agent unavailable
- [ ] All tests pass

---

### Phase 6: Pipeline Integration

#### Task 6.1 — [MODIFY] `scripts/pipeline_orchestrator.py` — Add S2.5 enrichment step

**Description**: Add a new pipeline step `s2_5_enrich` between S1e (shortlist) and S2 (tipster xref). This step reads the shortlist, identifies all candidates with missing data, and runs the enrichment agent to fetch it. The enrichment is a standalone step so it can be skipped/resumed independently.

**Files**: `scripts/pipeline_orchestrator.py`

**Changes**:
- Add new step to `PIPELINE_STEPS` list after `s1e_shortlist`:
  ```python
  {
      "id": "s2_5_enrich",
      "name": "S2.5: Data Enrichment",
      "description": "Fetch missing team stats from internet sources (Flashscore, ESPN, Sofascore)",
      "python_step": "data_enrichment",
      "critical": False,
      "retries": 1,
      "agent_review_required": "bet-enricher",
      "agent_task": "Review enrichment results: coverage by sport, failed teams, data quality of fetched stats",
  }
  ```
- Add step timeout: `"s2_5_enrich": 600` (10 minutes)
- Add `_run_s2_5_enrich()` function:
  1. Load shortlist from `{date}_s2_shortlist.json`
  2. For each candidate, check if team stats exist in DB/cache
  3. Collect list of `(team_name, sport)` pairs with missing data
  4. Call `data_enrichment_agent.enrich_teams(missing_list)`
  5. Store enrichment results in pipeline state
  6. Log: `"S2.5 completed: {enriched}/{total} teams enriched ({failed} failed)"`
- Add `"data_enrichment"` case to `run_python_step()` dispatcher
- Add `s2_5_enrich` to `PHASE_STEPS["data"]` set
- Add `s2_5_enrich` to `SCAN_STEP_IDS` so it's skipped with `--skip-scan`

**Definition of Done**:

- [ ] New step `s2_5_enrich` appears in `PIPELINE_STEPS` between S1e and S2
- [ ] `_run_s2_5_enrich()` function reads shortlist, identifies missing data, calls enrichment agent
- [ ] Pipeline state records enrichment metrics: `s2_5_enriched`, `s2_5_failed`, `s2_5_total`
- [ ] `run_python_step()` dispatches `"data_enrichment"` to `_run_s2_5_enrich()`
- [ ] Step has `retries: 1` for transient network failures
- [ ] Step is non-critical (pipeline continues even if enrichment fails)
- [ ] `--skip-scan` also skips this step
- [ ] `--list-steps` shows the new step

#### Task 6.2 — [MODIFY] `scripts/pipeline_orchestrator.py` — Update S3 and S8 calls

**Description**: Update `_run_s3()` to not pass `top` parameter (covered in Phase 2 Task 2.3). Update `_run_s8()` to handle the new gate result structure where all non-rejected candidates are in `approved` and have `advisory_label`.

**Files**: `scripts/pipeline_orchestrator.py`

**Changes**:
- In `_run_s8()`: Log advisory label distribution before building coupons
- Print per-tier summary: `"CORE: {N} STRONG picks, VALUE: {M} MODERATE picks, DISCOVERY: {K} WEAK/FLAGGED picks"`

**Definition of Done**:

- [ ] `_run_s8()` logs advisory label distribution
- [ ] Pipeline step output includes tier breakdown in verbose mode

---

### Phase 7: Agent Protocol Enhancement

#### Task 7.1 — [MODIFY] `scripts/agent_protocol.py` — Add enrichment agent config

**Description**: Add the enrichment agent to `STEP_AGENT_CONFIG` so the pipeline writes structured input for agent review after enrichment completes.

**Files**: `scripts/agent_protocol.py`

**Changes**:
- Add `s2_5_enrich` entry to `STEP_AGENT_CONFIG`:
  ```python
  "s2_5_enrich": {
      "agent": "bet-enricher",
      "task": "Review enrichment results: coverage by sport, failed teams, data quality of fetched stats, identify teams that need manual data entry",
      "required_input": ["{date}_enrichment_results.json"],
      "output_metrics": ["total_teams", "enriched_count", "failed_count", "sport_coverage"],
  }
  ```

**Definition of Done**:

- [ ] `STEP_AGENT_CONFIG` contains `s2_5_enrich` entry
- [ ] Agent input file written after enrichment step completes
- [ ] Agent task description is clear and actionable

---

### Phase 8: Integration Testing & Verification

#### Task 8.1 — [CREATE] `tests/test_pipeline_integration.py`

**Description**: Integration tests that verify the full pipeline flow with the new enrichment step, advisory gate, and tiered coupon builder. Tests use fixture data (no real network calls).

**Definition of Done**:

- [ ] Test verifies: shortlist → enrichment → deep stats → advisory gate → tiered coupons flow
- [ ] Test verifies: enrichment failure doesn't crash pipeline
- [ ] Test verifies: all non-rejected candidates appear in coupon builder input
- [ ] Test verifies: CORE/VALUE/DISCOVERY tier assignment matches advisory labels
- [ ] Test verifies: backward compatibility with old gate result format (no advisory_label)
- [ ] All tests pass with `pytest tests/test_pipeline_integration.py`

#### Task 8.2 — [MODIFY] Verify pipeline step listing

**Description**: Run the pipeline with `--list-steps` (or `--status`) to verify the new S2.5 step is registered and ordered correctly. Verify step dependencies and phase membership.

**Definition of Done**:

- [ ] `python3 scripts/pipeline_orchestrator.py --status` shows S2.5 in correct position
- [ ] Step order: ...S1e → S2.5 → S2 → S3...
- [ ] `--skip-scan` skips S2.5

---

### Phase 9: Code Review

#### Task 9.1 — [REUSE] Code Review by `tsh-code-reviewer`

**Description**: Run `tsh-code-reviewer` agent via `tsh-review.prompt.md` to review all changes. Pass the following scope:
- New file: `scripts/data_enrichment_agent.py`
- Modified files: `scripts/deep_stats_report.py`, `scripts/gate_checker.py`, `scripts/coupon_builder.py`, `scripts/pipeline_orchestrator.py`, `scripts/build_shortlist.py`, `scripts/agent_protocol.py`
- Test files: `tests/test_data_enrichment_agent.py`, `tests/test_gate_checker_advisory.py`, `tests/test_deep_stats_enrichment.py`, `tests/test_pipeline_integration.py`
- Run all tests: `pytest tests/ -v`

**Definition of Done**:

- [ ] Code review passes or issues are resolved
- [ ] All tests pass
- [ ] No security issues (OWASP compliance)
- [ ] Review report documented in Changelog

## Security Considerations

- **Playwright fetching**: The enrichment agent fetches external web pages. All URLs are constructed from known patterns (flashscore.com, sofascore.com, ESPN API), not from user input. No arbitrary URL fetching.
- **SQL injection**: All DB operations use parameterized queries via existing repository classes (`StatsRepo`, `TeamRepo`). No raw SQL string interpolation.
- **HTML parsing**: Parsed HTML is used only to extract statistical values. No HTML is rendered or passed to eval/exec. Extracted values are validated as numbers before persisting.
- **Rate limiting**: Enrichment agent respects existing domain semaphores and adds per-domain rate limiting (max 1 request/second per domain) to avoid IP bans.
- **Data validation**: Enriched data is validated against expected stat key schemas (`SPORT_STAT_KEYS`) before persisting. Unexpected keys are logged and dropped.
- **Timeout protection**: Each enrichment fetch has a 30-second timeout. Batch enrichment has a 300-second total cap. Prevents hung Playwright browsers.

## Quality Assurance

Acceptance criteria checklist to verify the implementation meets requirements:

- [ ] All scanned events with valid team names reach deep analysis (no artificial caps)
- [ ] Enrichment agent successfully fetches data for at least one sport (e.g., football from Flashscore)
- [ ] Gate checker labels all candidates with advisory labels (STRONG/MODERATE/WEAK/FLAGGED)
- [ ] Only hard reject conditions cause actual rejection (phantoms, 48h repeat losses)
- [ ] Coupon builder creates CORE, VALUE, and DISCOVERY tier coupons
- [ ] Extended picks appear in coupon output with appropriate confidence discounts
- [ ] Pipeline runs end-to-end without crashes (enrichment failures are non-blocking)
- [ ] All unit tests pass: `pytest tests/ -v`
- [ ] Pipeline state JSON correctly records enrichment step metrics
- [ ] Backward compatibility: pipeline works even if enrichment agent is not available

## Improvements (Out of Scope)

- **Real-time odds monitoring**: Continuously poll Betclic/Odds API for line movement alerts during the betting day
- **ML probability engine**: Replace safety_score with trained ML model for hit probability estimation
- **Flashscore scraper library**: Build a dedicated Flashscore parsing library with structured selectors per page type (team page, match page, H2H page)
- **WebSocket live data**: Stream live match data for in-play betting decisions
- **Distributed enrichment**: Run enrichment across multiple machines for faster data collection
- **Historical backfill**: Batch-enrich historical data for all teams in DB to improve future pipeline runs

## Changelog

| Date       | Change Description       |
| ---------- | ------------------------ |
| 2026-05-08 | Initial plan created     |
