# tennis-rich-stat-enrichment - Implementation Plan

## Task Details

| Field            | Value |
| ---------------- | ----- |
| Jira ID          | N/A |
| Title            | Tennis rich-stat enrichment |
| Description      | Extend the shared rich-stat enrichment architecture already proven by the existing football implementation to tennis while preserving the stable `match_stats -> team_form` contract, keeping ownership in enrichment flows, preserving the existing scoreboard-based baseline handled by tennis enrichment scripts, and adding bounded serve/return richness from tennis-specific per-match sources rather than copying football or team-sport assumptions. |
| Priority         | High |
| Related Research | `specifications/multisport-rich-stat-enrichment/multisport-rich-stat-enrichment.plan.md`, `specifications/flashscore-match-stats-token/flashscore-match-stats-token.plan.md`, `memories/repo/pipeline-knowledge-base.md` |

## Proposed Solution

Implement tennis as a mixed-source completion path that preserves the current scoreboard baseline and adds bounded serve/return richness.

The implementation should keep the same shared architecture used by the existing football implementation:

- `scripts/data_enrichment_agent.py` remains the owner of rich completion inside the enrichment flow
- `scripts/enrich_tennis_stats.py` remains the baseline/backfill path for sets/games coverage rather than becoming a second rich-stat writer
- source-specific logic lives in a bounded helper under `scripts/_helpers/`
- persistence still flows through `fetch_api_stats._store_in_cache()` into `match_stats` and derived `team_form`

Tennis-specific source policy:

- baseline coverage stays on the existing scoreboard/ESPN-driven path already used by `scripts/enrich_tennis_stats.py`
- primary rich completion source: `tennis-abstract`
- bounded supporting source in this slice: `sackmann` via per-match `NormalizedMatchStats` paths only
- excluded from `supporting_sources`: Sackmann season aggregates and any other non-match-level summaries, which remain aggregate-only/advisory surfaces
- aggregate-only / advisory surfaces: season summaries or player-level aggregates that do not map cleanly to per-match `NormalizedMatchStats`

This plan must keep baseline and rich buckets distinct in reporting so tennis rollout does not blur scoreboard-derived completeness with serve/return richness.

When delegating implementation, use this child plan as the primary execution artifact and pass the multisport plan only as shared-guardrail context.
This plan is independently usable for tennis-specific logic, but it does not authorize a second shared probe / registry / report implementation path.
If the basketball-owned shared foundation is absent, record the blocker in this plan's Changelog and halt the slice; do not create `scripts/rich_stats_probe.py`, the shared completion registry, or the generic `rich-coverage` report path from scratch unless the manager explicitly reassigns that ownership.

**Branch B settlement remains out of scope and unchanged.** This plan does not modify `scripts/settle_on_finish.py` or the finalized DB-backed settlement path.

**Live validation commands**:

- `PYTHONPATH=src .venv/bin/python scripts/rich_stats_probe.py --date YYYY-MM-DD --sport tennis --limit 10 --verbose`
- `PYTHONPATH=src .venv/bin/python scripts/db_report.py --report rich-coverage --sport tennis --date YYYY-MM-DD`
- `PYTHONPATH=src .venv/bin/pytest -q tests/scrapers/tennis/test_sackmann.py tests/test_tennis_rich_completion.py`

These are post-implementation validation commands, not preflight checks against the current branch state.
They assume the basketball-owned shared foundation (`scripts/rich_stats_probe.py`, the shared completion registry, and the generic `rich-coverage` report path) is already present in the working branch or has been explicitly reassigned by the manager in the same slice. `tests/test_tennis_rich_completion.py` must exist before the final test run.

Use shared report-bucket vocabulary consistently: `rich`, `baseline_only`, `partial`, `no_data`.
For tennis, `baseline_only` specifically means scoreboard / ESPN baseline coverage exists, but serve/return rich keys are still missing. Keep AGENT_SUMMARY owner metrics separate: `eligible`, `completed`, `still_missing`.

## Current Implementation Analysis

### Already Implemented

List of existing components, functions, utilities that will be reused (with file paths):

- `scripts/data_enrichment_agent.py` - canonical enrichment owner; already supplements partial tennis results with Tennis Abstract for `hold_pct` and `break_pct`
- `scripts/enrich_tennis_stats.py` - existing aggressive baseline enrichment path that scans ESPN scoreboards and builds L10 baseline keys such as `sets_won`, `total_sets`, `games_won`, and `total_games`
- `scripts/fetch_api_stats.py::_store_in_cache()` - established writer into `match_stats` and derived `team_form`
- `src/bet/stats/fallback_chains.py` - shared fallback-chain module already listing tennis sources and expected stat keys
- `src/bet/api_clients/tennis_abstract.py` - existing tennis-specific source returning per-match serve/return stats and normalized fixtures
- `src/bet/api_clients/sackmann_adapter.py` - existing source for Sackmann-based tennis data, including match/history support and season aggregates

- `scripts/data_enrichment_agent.py` - expand the current partial Tennis Abstract supplementation into a full tennis rich-completion slice with explicit baseline-vs-rich reporting
- `scripts/enrich_tennis_stats.py` - keep baseline ownership clear and avoid duplicate persistence paths once rich completion is introduced; it currently persists baseline cache entries via `build_stats_cache._persist_to_db()`, so the rich slice must not convert it into a second rich-completion writer or overlap its baseline write surface
- `scripts/fetch_api_stats.py` - reuse or expose the minimal writer seams required by a tennis helper
- `src/bet/stats/fallback_chains.py` - encode explicit completion semantics and baseline/rich distinctions for tennis sources in `RICH_COMPLETION_POLICY` without inventing a second policy module
- `scripts/db_report.py` - extend the basketball-owned generic `rich-coverage` report to accept `--sport tennis` with explicit baseline-only vs rich-complete buckets; reuse the shared `--sport` CLI argument and `rich-coverage` argparse choice rather than adding a separate tennis-named report path

### To Be Created

List of new components, functions, utilities that need to be built from scratch:

- tennis-specific extensions to the basketball-owned shared completion registry / probe / report surfaces
- do not create `scripts/rich_stats_probe.py`, the shared completion registry, or the generic `rich-coverage` report path from scratch; if they are absent, record the blocker in this plan's Changelog and halt until basketball Task 1.1 is confirmed complete in the working branch or the manager explicitly reassigns ownership
- `scripts/_helpers/tennis_rich_completion.py` - bounded tennis helper that merges baseline and rich completion results without creating a second independent writer
- `tests/test_tennis_rich_completion.py` - focused merge, routing, baseline-vs-rich, and no-write probe tests

## Open Questions

| #   | Question | Answer | Status |
| --- | -------- | ------ | ------ |
| 1   | Should tennis rich completion rely on one source only? | No. Tennis needs a mixed-source design that keeps the existing scoreboard baseline while adding bounded rich completion from tennis-specific per-match sources. | ✅ Resolved |
| 2   | Should `scripts/enrich_tennis_stats.py` absorb the entire rich-completion orchestration? | No. It should remain the baseline/backfill tool, while the owner flow handles rich completion. | ✅ Resolved |
| 3   | Can season-aggregate Sackmann or other player-summary data satisfy canonical rich completion by itself? | No. Only per-match normalized stats can satisfy canonical `match_stats` richness. | ✅ Resolved |
| 4   | Does this plan change Branch B settlement? | No. Settlement remains unchanged. | ✅ Resolved |

## Technical Context

Project conventions, coding standards, and patterns discovered during planning. Downstream agents MUST read this section instead of re-discovering the same context.

### Project Instructions

- `.github/copilot-instructions.md` - DB-first, verify data flow before changes, keep implementation narrow and root-cause focused
- workspace memory - fish shell only for command examples; avoid inline Python or shell loops
- `memories/repo/pipeline-knowledge-base.md` - Branch B settlement is final and unchanged by this plan

### Architecture & Patterns

- `scripts/data_enrichment_agent.py` already contains a narrow tennis supplementation path using Tennis Abstract when the result is partial; this plan should expand that into a first-class tennis completion slice rather than inventing another owner
- `scripts/enrich_tennis_stats.py` is the current scoreboard-heavy baseline path and should remain focused on baseline keys and backfill, not become an unrelated rich-stat orchestration surface
- `_store_in_cache()` remains the only intended persistence bridge for new per-match tennis richness
- `NormalizedMatchStats` is defined in `src/bet/models/normalized.py` (exported via `src/bet/models/__init__.py`) and is the required payload passed to `_store_in_cache()`: `fixture_id`, `source`, `sport`, `home_team`, `away_team`, `date`, and `stats` with per-stat `home` / `away` sub-keys
- `src/bet/stats/fallback_chains.py` already lists tennis sources, but reporting and completion semantics need to distinguish baseline-only from rich-complete coverage; leave `FALLBACK_CHAINS["tennis"]` ordering unchanged and express rich-completion semantics only in `RICH_COMPLETION_POLICY`

### Tech Stack

- Python `>=3.11`
- SQLite DB at `betting/data/betting.db`
- runtime libraries already used in this area: `requests`, `beautifulsoup4`, `sqlalchemy`, `pydantic`
- tests run with `pytest`

### Code Style & Standards

- Keep tennis-specific parsing and merge rules in a bounded helper under `scripts/_helpers/`
- Preserve explicit provenance such as `tennis-abstract`, `sackmann`, and scoreboard/ESPN baseline sources
- Do not let season aggregates silently satisfy canonical per-match richness
- Keep baseline and rich buckets explicit in metrics and reporting

### Testing Patterns

- Use narrow pytest modules with mocked provider payloads and source-merge assertions
- Mirror the football validation shape: helper/adapter test, owner-routing test, and no-write probe/report test
- Keep commands fish-safe and date-scoped

### Database Patterns

- `match_stats` remains the canonical per-fixture truth table
- `team_form` remains the denormalized analytics surface
- No second independent tennis writer should be introduced outside `_store_in_cache()`

### Additional Context

- `scripts/enrich_tennis_stats.py` already builds recent baseline match history from ESPN scoreboards across a 60-day lookback; that baseline should be preserved rather than duplicated
- `scripts/data_enrichment_agent.py` currently supplements `hold_pct` and `break_pct` via Tennis Abstract only when tennis results are partial; the plan should generalize that into explicit baseline-vs-rich semantics
- Pipeline ordering is explicit: `scripts/enrich_tennis_stats.py` remains an earlier standalone baseline/backfill step (see `scripts/agent_protocol.py` `tennis_enrichment` module entry), and `scripts/data_enrichment_agent.py` consumes its persisted baseline outputs; it must not invoke `enrich_tennis_stats.py` inline as part of the rich-completion helper.
- **Branch B settlement remains out of scope and unchanged throughout this plan**

## Implementation Plan

### Phase 1: Shared Completion Foundation for Tennis

#### Task 1.1 - [MODIFY] Extend shared completion registry and generic reporting for tennis

**Description**: Extend the shared completion policy, no-write probe, and generic rich-coverage reporting for tennis, with explicit baseline-only vs rich-complete buckets. If the basketball-owned shared foundation is missing in the working branch, record the blocker in this plan's Changelog and halt the slice rather than creating a tennis-only duplicate.

**Definition of Done**:

- [x] Tennis declares baseline keys, rich keys, canonical rich source, supporting sources, and any aggregate-only sources in `src/bet/stats/fallback_chains.py::RICH_COMPLETION_POLICY`
- [x] Tennis `baseline_keys` are exactly `sets_won`, `total_sets`, `games_won`, and `total_games`
- [x] Tennis `required_rich_keys` are exactly `aces`, `double_faults`, `first_serve_pct`, `first_serve_win_pct`, `second_serve_win_pct`, `break_points_saved_pct`, `hold_pct`, and `break_pct`
- [x] Tennis `supporting_sources` are exactly `sackmann`, limited to per-match `NormalizedMatchStats` outputs only
- [x] The shared `scripts/rich_stats_probe.py` supports `--sport tennis` and reports baseline coverage, rich coverage, source choice, and failure reasons
- [x] `scripts/db_report.py` supports `--report rich-coverage --sport tennis --date <date>` with explicit `baseline_only`, `partial`, `rich`, and `no_data` buckets
- [x] The shared contract still persists only through `_store_in_cache()`

#### Task 1.2 - [CREATE] Build the bounded tennis rich-completion helper

**Description**: Add a tennis helper under `scripts/_helpers/` that merges baseline and rich completion results while preserving per-match provenance and writer discipline.

**Definition of Done**:

- [x] `tennis-abstract` is the primary rich-completion source
- [x] `sackmann` is the only supporting source in this slice, used only through per-match `NormalizedMatchStats` outputs
- [x] `sackmann_adapter.get_fixture_stats()` is the permitted Sackmann path; `sackmann_adapter.get_player_season_stats()` returns season aggregates wrapped in `NormalizedMatchStats` and is explicitly prohibited in this helper
- [x] Season-aggregate-only payloads cannot satisfy canonical rich completion by themselves
- [x] The `NormalizedMatchStats` payload passed to `_store_in_cache()` contains only rich-specific stat keys; baseline keys owned by `scripts/enrich_tennis_stats.py` are excluded so `save_team_form()` does not overwrite baseline rows via DELETE+INSERT
- [x] Calling `_store_in_cache()` with that rich-only payload may replace the JSON stats-cache `form` section for that player; this is acceptable because DB `team_form` rows remain the authoritative downstream source and the tennis rich slice keeps a single persistence bridge through `_store_in_cache()`
- [x] Pipeline ordering guarantees `scripts/enrich_tennis_stats.py` is not re-run after the tennis rich helper in the same session, so its `l10_matches` staleness gate cannot be satisfied by the rich-only JSON cache form
- [x] The helper returns the base 7-key contract used by the shared enrichment flow: `status` (`str`), `fixtures_scanned` (`int`), `matches_persisted` (`int`), `rich_keys_found` (`list[str]`), `missing_rich_keys` (`list[str]`), `error` (`str | None`), and `failure_reason` (`str | None`)

### Phase 2: Owner Wiring, Baseline Separation, and Tests

#### Task 2.1 - [MODIFY] Integrate tennis rich completion without duplicating the baseline writer

**Description**: Update `scripts/data_enrichment_agent.py` and related flows so the owner can trigger tennis rich completion when baseline exists but serve/return richness is still missing, while `scripts/enrich_tennis_stats.py` remains a separate earlier baseline/backfill step rather than an inline pre-hook inside the rich-completion helper.

**Definition of Done**:

- [x] `scripts/data_enrichment_agent.py` can trigger the tennis helper after baseline enrichment remains incomplete for rich keys
- [x] `scripts/enrich_tennis_stats.py` keeps baseline ownership and does not become a second independent rich-stat writer
- [x] `scripts/enrich_tennis_stats.py` is not invoked inline from `tennis_rich_completion.py` or from `data_enrichment_agent.py`'s tennis rich-completion branch
- [x] AGENT_SUMMARY reports tennis `eligible`, `completed`, and `still_missing` counts, with a `baseline_only` sub-field distinguishing matches where baseline coverage exists but serve/return rich keys are still absent
- [x] Branch B settlement code remains untouched

#### Task 2.2 - [CREATE] Add focused tennis merge, routing, and probe tests

**Description**: Lock down the tennis slice with narrow tests around source merge rules and baseline-vs-rich reporting semantics.

**Definition of Done**:

- [x] Tests cover helper persistence through `_store_in_cache()`
- [x] Tests cover owner routing from `scripts/data_enrichment_agent.py`
- [x] Tests verify that `sackmann_adapter.get_player_season_stats()` is never called by the helper (for example via a mock call-count assertion or a payload guard rejecting `season_aggregate` rows)
- [x] Tests cover baseline-vs-rich bucket semantics and no-write probes
- [x] Existing Sackmann tennis tests remain passing

### Phase 3: Live Validation and Review

#### Task 3.1 - [REUSE] Run the sport-specific live validation commands

**Description**: Validate tennis rollout with the planned probe, report, and narrow test commands only.

**Definition of Done**:

- [x] `scripts/rich_stats_probe.py --sport tennis` runs with no unintended DB/cache mutations
- [x] `scripts/db_report.py --report rich-coverage --sport tennis --date <date>` distinguishes `rich`, `baseline_only`, `partial`, and `no_data`
- [x] The tennis-focused pytest command passes

#### Task 3.2 - [REUSE] Final code review by `tsh-code-reviewer`

**Description**: After focused executable validation passes, run the final review to verify source-merge discipline and baseline/rich contract preservation.

**Definition of Done**:

- [x] Review is run after the focused validation suite
- [x] Findings are fixed or explicitly tracked in the Changelog (see Code Review Findings section)
- [x] Review confirms no duplicate tennis write path was introduced and no Branch B settlement regressions occurred
- [x] The slice is not closed while review findings remain unresolved and untracked — **M1/L1 fixed post-review; M2/L2/L3 fixed in the reopened follow-up slice; L4 became obsolete once SofaScore was removed from the tennis slice**

## Security Considerations

- Keep provider calls bounded to recent player matches and date-scoped probes
- Do not treat season aggregates as canonical per-match truth
- Preserve explicit provenance and failure reasons for baseline and rich paths
- Keep settlement logic untouched while implementing tennis enrichment

## Quality Assurance

Acceptance criteria checklist to verify the implementation meets the defined requirements:

- [x] Tennis rich completion remains owned by enrichment flows, not `scripts/run_scrapers.py`
- [x] Tennis preserves the existing baseline/backfill writer and adds rich completion without a second independent write path
- [x] `scripts/enrich_tennis_stats.py` is not invoked inline from the tennis rich-completion branch; baseline remains an earlier standalone step and rich `_store_in_cache()` payloads exclude baseline-owned keys
- [x] Baseline-only vs rich-complete reporting exists in the generic `rich-coverage` report
- [x] Season aggregates cannot satisfy canonical rich completion by themselves
- [x] Tennis helper, routing, merge, and probe tests pass
- [x] **Branch B settlement remains out of scope and unchanged**

## Code Review Findings

Reviewed 2026-05-20 against current branch state (`fix/pipeline-data-flow-holes`). All 9 tests pass.

### MEDIUM

**M1 — `_set_result_status` tennis branch uses `SPORT_STAT_KEYS` instead of `tennis_rich_complete`**
File: `scripts/data_enrichment_agent.py`, ~L211

Football and basketball both set `result["status"] = "enriched"` when their respective `*_rich_complete` flag is True.
The tennis branch introduced by this PR uses `found_keys >= set(SPORT_STAT_KEYS.get(sport, []))` which requires ALL keys in `SPORT_STAT_KEYS["tennis"]` — including `ranking`, which no enrichment path produces as part of rich completion.
Consequence: `result["status"]` is always `"partial"` for tennis even when all 8 rich keys are present; `_summarize_enrichment_results`'s top-level `enriched` counter is 0 for tennis regardless of completion outcome. The `tennis_rich_complete` flag and `tennis_completed` AGENT_SUMMARY metric are correct, but the shared `enriched` metric is misleading.
Fix: `result["status"] = "enriched" if result.get("tennis_rich_complete") else "partial"` — same pattern as football/basketball.

Resolved 2026-05-20: fixed in the current branch by switching tennis status to `tennis_rich_complete` and adding a regression test for the fully-rich owner path.

**M2 — `_store_in_cache` source attribution is inaccurate for multi-source batches**
File: `scripts/_helpers/tennis_rich_completion.py`, L366-367; `scripts/fetch_api_stats.py:_save_per_match_stat_arrays`

`_store_in_cache("tennis", team_name, persisted_matches, persisted_matches[0].source)` passes `persisted_matches[0].source` as the top-level `api_source` for all matches. `_save_per_match_stat_arrays` writes every `team_form` row with `source=api_source`, meaning sackmann-sourced keys on fixture 2 get attributed to `tennis-abstract` in `team_form`. Functionally harmless for classification (all sources are in `allowed_sources`), but per-key provenance is lost. No test covers a multi-fixture, multi-source scenario where sources differ by fixture.

Resolved 2026-05-20: shared persistence now preserves per-match provenance. `_persist_match_stats_to_db()` derives `match_source = getattr(match, "source", None) or api_source` inside the per-match loop, and `_save_per_match_stat_arrays()` tracks `stat_sources` (first contributing source per stat key) and uses that for `TeamForm.source`. Added `TestPerMatchSourceProvenance` coverage in `tests/test_fetch_api_stats.py`.

### LOW

**L1 — No-write probe test uses a weak mutation guard**
File: `tests/test_tennis_rich_completion.py`, ~L435

`if "FROM team_form" not in query: raise AssertionError` would pass a `DELETE FROM team_form` or `UPDATE team_form` statement. The guard should check `query.strip().upper().startswith("SELECT")`.

Resolved 2026-05-20: the probe test now rejects any non-`SELECT` query.

**L2 — Missing test: `rich` coverage team does not trigger completion**
The `_needs_tennis_rich_completion` logic is safe (empty `tennis_missing_rich_keys` short-circuits), but no test exercises the `bucket="rich"` → `needed=False` path.

Resolved 2026-05-20: added `test_apply_tennis_completion_skips_when_coverage_is_already_rich`.

**L3 — Missing test: `known_missing_team` skip path for tennis**
`_apply_tennis_rich_completion` has a `known missing team` early-return branch (consistent with football/basketball), but it is untested in the tennis suite.

Resolved 2026-05-20: added `test_apply_tennis_completion_skips_known_missing_team`.

**L4 — Obsolete after tennis SofaScore removal**
This gap applied only to the deleted `test_sofascore_tennis.py` path. Once `sofascore-tennis` was removed from the active tennis slice, the remaining partial-group and name-resolution coverage concerns stopped being part of the tennis implementation surface.

### INFORMATIONAL (no action required)

- **`settle_on_finish.py` modified on this branch**: Changes in commit `728593f` (SofaScore scraper removal) are unrelated to tennis enrichment. Settlement logic is intact. No tennis-enrichment regressions.
- **No hockey/volleyball helpers present**: `scripts/_helpers/hockey_rich_completion.py` and `scripts/_helpers/volleyball_rich_completion.py` do not exist on this branch — confirmed no spillover.
- **`ranking` in `SPORT_STAT_KEYS["tennis"]`**: Pre-existing; if `ranking` is present from ESPN enrichment, `result["status"]` can still reach `"enriched"` via the current logic. The inconsistency is a direct consequence of tennis needing the `ranking` key in the generic stat path while the policy-driven rich completion does not.
- **`_store_in_cache` JSON cache overwrite for baseline keys**: Already accepted in the plan (Task 1.2 DoD). Pipeline ordering prevents re-run of `enrich_tennis_stats.py` within the same session.

### Review Verdict

Core tennis enrichment contract is correctly implemented: policy declares correct buckets and sources, classification treats `espn-tennis-enriched` as baseline-only, helper persists only rich keys through `_store_in_cache`, `enrich_tennis_stats.py` is not invoked inline, AGENT_SUMMARY metrics are wired and correct, and no Branch B settlement regressions were introduced.

M1, L1, M2, L2, and L3 are fixed in the current branch. The prior SofaScore-only L4 gap is obsolete because the tennis slice no longer includes SofaScore support.

## Improvements (Out of Scope)

Potential improvements identified during planning that are not part of the current task:

- wider cleanup of tennis player-name resolution and season-aggregate helpers outside the touched slice
- dashboard visualization for tennis rich-coverage health
- broader cross-sport fallback-chain cleanup beyond tennis

## Changelog

| Date   | Change Description |
| ------ | ------------------ |
| 2026-05-20 | Plan split out of the former multisport umbrella artifact so tennis can be implemented independently |
| 2026-05-20 | Hardened shared-foundation sequencing, validation preconditions, shared metric vocabulary, and downstream-agent handoff guidance |
| 2026-05-20 | Implemented tennis rich completion via shared policy/report extensions, bounded helper wiring in `data_enrichment_agent.py`, focused tennis tests, and live probe/report/pytest validation |
| 2026-05-20 | Code review complete. M1: `_set_result_status` uses `SPORT_STAT_KEYS` instead of `tennis_rich_complete` for status — fix required before merge. M2: multi-source batch source attribution inaccurate in `team_form` — tracked, low operational risk. L1–L4: test hygiene gaps tracked for follow-up. No duplicate write path; no settlement regressions. |
| 2026-05-20 | Fixed post-review findings M1 and L1 by aligning tennis status with `tennis_rich_complete`, adding a regression test for the fully-rich owner path, and tightening the no-write probe test guard to reject any non-`SELECT` query. |
| 2026-05-20 | Fixed M2: per-match source provenance in shared persistence. `_persist_match_stats_to_db` now derives `match_source = getattr(match, "source", None) or api_source` inside the per-match loop; `_save_per_match_stat_arrays` now tracks `stat_sources` (first contributing source per stat_key) and uses it in `TeamForm.source` instead of the batch `api_source`. No change to `rich_coverage.py` required — all tennis sources are already in `allowed_sources`. Added `TestPerMatchSourceProvenance` (2 tests) in `tests/test_fetch_api_stats.py`. All 11 tennis + provenance tests pass; full test_fetch_api_stats suite 19/19 pass. |
| 2026-05-20 | Reopened tennis follow-up slice completed: added owner-flow regression tests for the already-rich and known-missing branches, added SofaScore tennis `get_team_last_fixtures` coverage, and minimally repaired shared `fallback_chains.py` structure to unblock validation after unrelated in-progress multisport edits. Follow-up review found no new high/medium issues; only L4 remains tracked. |
| 2026-05-20 | Removed `sofascore-tennis` from the tennis slice entirely (user correction: SofaScore removed from project). `FALLBACK_CHAINS["tennis"]` and `RICH_COMPLETION_POLICY["tennis"]["supporting_sources"]` now list `sackmann` only. Deleted `src/bet/api_clients/sofascore_tennis.py` and `tests/scrapers/tennis/test_sofascore_tennis.py`. Removed `_normalize_sofascore_match_for_player` and its call site from `scripts/_helpers/tennis_rich_completion.py`. Removed `sofascore-tennis` registration block from `src/bet/api_clients/__init__.py`. Updated test mocks. 14/14 tennis tests pass. |
| 2026-05-20 | Final code review of SofaScore-removal change. No HIGH or MEDIUM findings. L1 (low): stale `sofascore-tennis` row in `memories/repo/pipeline-knowledge-base.md` line 716 — should be removed to prevent agent confusion. All five expected outcomes confirmed clean: `FALLBACK_CHAINS["tennis"]` and `supporting_sources` contain no sofascore-tennis; helper has no sofascore branch; `__init__.py` has no sofascore-tennis key; both deleted files confirmed absent; 14/14 tests pass; `test_tennis_policy_declares_baseline_and_rich_contract` provides permanent regression guard. |