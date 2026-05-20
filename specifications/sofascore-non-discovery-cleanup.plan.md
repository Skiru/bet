# SofaScore Non-Discovery Cleanup - Implementation Plan

## Task Details

| Field | Value |
| --- | --- |
| Status | COMPLETED |
| Created | 2026-05-20 |
| Scope | Clean up remaining non-discovery SofaScore usage in the bet repo while keeping discovery intact |
| Primary Goal | Remove or demote low-value SofaScore surfaces that are stub-only, misleading, or no longer aligned with the active pipeline |
| Explicit Non-Goals | No discovery changes in Phase 1, no UI work, no broad refactor of generic basketball/hockey fallbacks |

## Proposed Solution

Keep SofaScore where it still has an active, distinct role:

- discovery adapter in `src/bet/discovery/sources/sofascore.py`
- discovery entrypoint in `scripts/discover_events.py`
- tennis-specific API client in `src/bet/api_clients/sofascore_tennis.py`
- generic `sofascore` client registration where it still supports discovery and the keep-for-now basketball/hockey fallback inventory

Clean up SofaScore where the current repo state shows low value or misleading ownership:

- remove football's generic SofaScore fallback from the shared stats chain, because the active football completion path has already pivoted to Flashscore HTML
- delete dormant football SofaScore helper residue and rename misleading football completion symbols that still mention SofaScore despite the Flashscore pivot
- remove the tennis SofaScore scraper from the scraper pipeline if it remains fixtures-only and adds no value in `run_scrapers.py`
- remove or demote volleyball SofaScore default usage in both the scraper pipeline and the shared volleyball fallback path
- treat settlement's SofaScore search helper as an optional final cleanup phase, because it is isolated and low-value but not a prerequisite for the earlier cleanup work

This plan intentionally separates active fallback inventory from scraper/runtime residue. The cleanup should prefer removing default execution paths and dead names first, while avoiding speculative pruning of generic capabilities that are still intentionally retained.

## Current Implementation Analysis

### Keep As-Is

- `src/bet/discovery/sources/sofascore.py` is the live discovery adapter and remains in scope only as a protected surface.
- `scripts/discover_events.py` remains the live discovery entrypoint and is not part of this cleanup.
- `src/bet/api_clients/sofascore_tennis.py` still provides dedicated tennis implementation value and stays in the active fallback chain.
- `src/bet/api_clients/sofascore.py` stays registered because discovery uses it and the generic basketball/hockey fallback inventory is still being kept for now.

### Active Cleanup Targets

- `src/bet/stats/fallback_chains.py` still routes football through generic `sofascore`, which is misaligned with the current Flashscore-based football completion plan.
- `scripts/data_enrichment_agent.py` still uses football helper function names that mention SofaScore even though the live football completion source is now `flashscore-html`.
- `scripts/_helpers/football_sofascore_enrichment.py` and `tests/test_football_sofascore_enrichment.py` remain as dormant residue.
- `src/bet/scrapers/__init__.py` and `src/bet/scrapers/constants.py` still register `sofascore-tennis` and `sofascore-volleyball` as scraper pipeline sources.
- `src/bet/scrapers/tennis/sofascore_tennis.py` and `src/bet/scrapers/volleyball/sofascore_volley.py` are documented as fixtures-only stubs in the current specs.
- `src/bet/api_clients/volleyball_data.py` still falls through to generic `sofascore` in the volleyball match-stats chain.
- `scripts/settle_on_finish.py` still performs a direct SofaScore search fallback before Flashscore request/search and Flashscore Playwright.

### Architectural Facts That Drive The Plan

- `scripts/fetch_api_stats.py` imports `FALLBACK_CHAINS` from `src/bet/stats/fallback_chains.py`, so fallback-chain edits flow into the shared enrichment path without duplicate changes.
- `scripts/run_scrapers.py` uses `SPORT_SOURCE_MAP` and the scraper registry as the default execution surface, so removing a low-value source there is the correct way to stop default pipeline usage.
- `tests/scrapers/test_integration.py` asserts registry and source-map consistency, so scraper cleanup is mechanically bounded.
- `tests/test_flashscore_token_policy.py` already covers both the settlement SofaScore helper and the volleyball fallback behavior, so optional cleanup remains low-risk if chosen.

## Scope Guardrails

### Mandatory Guardrails

- Phase 1 explicitly excludes discovery changes.
- Do not modify `src/bet/discovery/sources/sofascore.py` in this cleanup.
- Do not modify `scripts/discover_events.py` in this cleanup.
- Do not remove `src/bet/api_clients/sofascore_tennis.py` from the tennis fallback chain.
- Do not remove generic `sofascore` from basketball or hockey fallback chains in this cleanup.
- Do not widen this task into a rewrite of archival specifications or old research folder names. Historical spec files may remain historical records.

### Success Criteria

- Football no longer uses generic SofaScore as an active stats fallback.
- Football completion naming no longer implies SofaScore when the active source is Flashscore HTML.
- `run_scrapers.py` no longer defaults to low-value SofaScore tennis or volleyball stub sources.
- Volleyball default stat fallback paths no longer silently route through generic SofaScore unless explicitly retained by an approved follow-up decision.
- Settlement cleanup, if taken, removes a fragile helper without disturbing DB-first or Flashscore-backed settlement behavior.

## Technical Context

### Source Ownership By Area

- Discovery ownership: `src/bet/discovery/` and `scripts/discover_events.py`
- Shared stats fallback ownership: `src/bet/stats/fallback_chains.py`
- Enrichment orchestration ownership: `scripts/data_enrichment_agent.py`
- Scraper pipeline ownership: `src/bet/scrapers/__init__.py`, `src/bet/scrapers/constants.py`, `scripts/run_scrapers.py`
- Volleyball dedicated helper ownership: `src/bet/api_clients/volleyball_data.py`
- Settlement ownership: `scripts/settle_on_finish.py`

### Important Existing Behavior

- The active football completion path already uses `scripts/_helpers/football_flashscore_html_enrichment.py` and surfaces `flashscore-html` in results.
- `scripts/_helpers/football_flashscore_html_enrichment.py` still exports a backward-compatible alias `complete_football_rich_stats`, which is useful for compatibility but misleading for cleanup.
- `tests/test_football_sofascore_enrichment.py` is already a deprecated placeholder and can be removed cleanly once the cleanup is implemented.
- `specifications/scrapers-pipeline-integration.md` already documents `sofascore-tennis` and `sofascore-volleyball` as `STUB (fixtures only)`.

## Implementation Plan

### Phase 1 - Protected Scope And No Discovery Changes

- [x] **Task 1.1** `[NO-CHANGE]` Protect discovery surfaces during cleanup
  - **Files explicitly excluded:** `src/bet/discovery/sources/sofascore.py`, `scripts/discover_events.py`
  - **Intent:** Make the cleanup implementation start from non-discovery surfaces only.
  - **Definition of Done:**
    - No discovery code paths are modified in the cleanup PR.
    - Discovery tests and discovery source ordering remain untouched.

- [x] **Task 1.2** `[NO-CHANGE]` Protect keep-for-now fallback inventory
  - **Files explicitly protected:** `src/bet/api_clients/sofascore.py`, `src/bet/api_clients/sofascore_tennis.py`, tennis/basketball/hockey entries that are intentionally retained
  - **Intent:** Prevent this cleanup from accidentally pruning still-approved fallback inventory.
  - **Definition of Done:**
    - Tennis API fallback via `sofascore-tennis` remains available.
    - Generic `sofascore` remains available for discovery and the keep-for-now basketball/hockey paths.

### Phase 2 - Football SofaScore Residue Removal And Naming Cleanup

- [x] **Task 2.1** `[MODIFY]` Remove football's generic SofaScore stats fallback from the shared chain
  - **Files:** `src/bet/stats/fallback_chains.py`
  - **Intent:** Align the football fallback policy with the already-landed Flashscore HTML pivot.
  - **Definition of Done:**
    - The football chain no longer contains `sofascore`.
    - Tennis, basketball, hockey, and discovery-related client registration remain unchanged.
    - No duplicate fallback-chain definitions are introduced elsewhere.

- [x] **Task 2.2** `[MODIFY]` Rename misleading football completion symbols to neutral or Flashscore-accurate names
  - **Files:** `scripts/data_enrichment_agent.py`, `scripts/_helpers/football_flashscore_html_enrichment.py`
  - **Recommended rename direction:**
    - `_needs_football_sofascore_completion` -> `_needs_football_rich_completion`
    - `_apply_football_sofascore_completion` -> `_apply_football_rich_completion`
    - remove the misleading backward-compatible alias `complete_football_rich_stats` once no live import needs it
  - **Intent:** Make the live football path read correctly without changing the downstream result contract.
  - **Definition of Done:**
    - No active football completion symbol in live code contains `sofascore`.
    - The existing `football_completion` output payload shape remains stable.
    - `flashscore-html` remains the surfaced active source for football completion.

- [x] **Task 2.3** `[REMOVE]` Delete dormant football SofaScore helper and deprecated placeholder test
  - **Files:** `scripts/_helpers/football_sofascore_enrichment.py`, `tests/test_football_sofascore_enrichment.py`
  - **Intent:** Remove historical residue that no longer participates in runtime behavior.
  - **Definition of Done:**
    - The dormant helper file is removed.
    - The deprecated placeholder test file is removed.
    - No remaining runtime or test import references the removed helper.

### Phase 3 - Tennis SofaScore Scraper Stub Prune

- [x] **Task 3.1** `[REMOVE]` Remove the tennis SofaScore scraper from the active scraper registry and default sport source map
  - **Files:** `src/bet/scrapers/__init__.py`, `src/bet/scrapers/constants.py`
  - **Candidate removal target:** `("tennis", "sofascore-tennis")`
  - **Intent:** Stop `run_scrapers.py` from treating a fixtures-only stub as an active scraper pipeline source.
  - **Definition of Done:**
    - `available_scrapers()` no longer exposes the tennis SofaScore scraper.
    - `SPORT_SOURCE_MAP["tennis"]` no longer contains `sofascore-tennis`.
    - `scripts/run_scrapers.py --sport tennis` no longer includes this stub in default execution.

- [x] **Task 3.2** `[REMOVE]` Delete the tennis scraper module if Phase 3.1 leaves it orphaned
  - **Files:** `src/bet/scrapers/tennis/sofascore_tennis.py`, optionally `src/bet/scrapers/tennis/__init__.py` if export cleanup is needed
  - **Intent:** Finish the prune cleanly instead of keeping dead scraper code behind a removed registry entry.
  - **Definition of Done:**
    - No scraper registry or export path references the tennis SofaScore scraper module.
    - The tennis API client `src/bet/api_clients/sofascore_tennis.py` remains intact and unaffected.

- [x] **Task 3.3** `[MODIFY]` Sync scraper-facing docs and tests after the tennis prune
  - **Files:** `tests/scrapers/test_integration.py`, `specifications/scrapers-pipeline-integration.md`, `specifications/post-refactor-alignment.plan.md`
  - **Intent:** Keep the documented scraper inventory aligned with the live registry.
  - **Definition of Done:**
    - Scraper integration tests reflect the reduced registry.
    - Active documentation no longer presents the tennis SofaScore stub as part of the current scraper pipeline inventory.

### Phase 4 - Volleyball SofaScore Default Usage Rationalization

- [x] **Task 4.1** `[REMOVE]` Remove the volleyball SofaScore scraper from the active scraper registry and default sport source map
  - **Files:** `src/bet/scrapers/__init__.py`, `src/bet/scrapers/constants.py`
  - **Candidate removal target:** `("volleyball", "sofascore-volleyball")`
  - **Intent:** Discovery already covers fixtures; the scraper pipeline should not run a fixtures-only volleyball stub by default.
  - **Definition of Done:**
    - `available_scrapers()` no longer exposes the volleyball SofaScore scraper.
    - `SPORT_SOURCE_MAP["volleyball"]` no longer contains `sofascore-volleyball`.
    - `scripts/run_scrapers.py --sport volleyball` no longer includes this stub in default execution.

- [x] **Task 4.2** `[MODIFY]` Remove generic SofaScore from the default volleyball stats fallback path
  - **Files:** `src/bet/stats/fallback_chains.py`, `src/bet/api_clients/volleyball_data.py`
  - **Intent:** Keep volleyball defaults focused on the sources that are actually competitive in the current repo.
  - **Recommended direction:**
    - remove `sofascore` from `FALLBACK_CHAINS["volleyball"]`
    - remove `sofascore` from `VolleyballDataClient.fetch_match_stats()` provider order
  - **Definition of Done:**
    - Volleyball fallback defaults no longer route through generic `sofascore`.
    - ESPN and API-Volleyball remain the explicit default match-stats providers in `VolleyballDataClient`.
    - No basketball or hockey fallback behavior changes as part of this phase.

- [x] **Task 4.3** `[REMOVE]` Delete the volleyball scraper module if Phase 4.1 leaves it orphaned
  - **Files:** `src/bet/scrapers/volleyball/sofascore_volley.py`, optionally volleyball scraper package exports if cleanup is needed
  - **Intent:** Finish the prune rather than leaving a dead stub behind the removed registry entry.
  - **Definition of Done:**
    - No scraper registry or export path references the volleyball SofaScore scraper module.
    - Volleyball-specific helper paths outside the scraper registry are updated only if they depended on the removed module.

- [x] **Task 4.4** `[MODIFY]` Sync volleyball docs and tests after fallback demotion/removal
  - **Files:** `tests/scrapers/test_integration.py`, `tests/test_flashscore_token_policy.py`, `specifications/scrapers-pipeline-integration.md`, `specifications/post-refactor-alignment.plan.md`
  - **Intent:** Keep test expectations and active docs aligned with the new default policy.
  - **Definition of Done:**
    - Volleyball fallback tests assert the new provider order or absence of SofaScore, depending on the final implementation.
    - Scraper inventory docs no longer present volleyball SofaScore as an active default path.

### Phase 5 - Optional Settlement SofaScore Search Cleanup

- [x] **Task 5.1** `[OPTIONAL][MODIFY]` Remove direct SofaScore search from settlement result lookup order
  - **Files:** `scripts/settle_on_finish.py`
  - **Current order:** odds snapshot -> cached HTML -> `search_sofascore` -> `search_flashscore` -> Flashscore Playwright
  - **Recommended direction:** remove `search_sofascore` entirely rather than merely reordering it
  - **Intent:** Settlement should rely on DB-first sources and the already-maintained Flashscore-backed fallbacks, not a fragile extra SofaScore search step.
  - **Definition of Done:**
    - Settlement no longer calls `search_sofascore()` in the normal lookup path.
    - DB-backed and Flashscore-backed settlement behavior remains intact.

- [x] **Task 5.2** `[OPTIONAL][REMOVE]` Delete the settlement SofaScore helper and shrink the dedicated tests accordingly
  - **Files:** `scripts/settle_on_finish.py`, `tests/test_flashscore_token_policy.py`
  - **Intent:** Finish the optional cleanup cleanly if Phase 5.1 is accepted.
  - **Definition of Done:**
    - `search_sofascore()` is removed if it has no callers.
    - The URL quoting test and settlement-order tests are updated to match the new flow.

## Test Plan

### Mandatory Automated Validation

- Scraper registry and source-map regression tests
  - `PYTHONPATH=src .venv/bin/pytest -q tests/scrapers/test_integration.py`
- Football completion regression tests
  - `PYTHONPATH=src .venv/bin/pytest -q tests/test_football_flashscore_html_enrichment.py`
- Settlement and volleyball fallback regression tests when Phase 4 or Phase 5 is implemented
  - `PYTHONPATH=src .venv/bin/pytest -q tests/test_flashscore_token_policy.py`

### Narrow Static Validation

- `PYTHONPATH=src .venv/bin/python -m py_compile scripts/data_enrichment_agent.py src/bet/stats/fallback_chains.py src/bet/api_clients/volleyball_data.py scripts/settle_on_finish.py`

### Validation Expectations By Phase

- After Phase 2: football cleanup passes without touching discovery tests.
- After Phase 3: scraper integration tests reflect removal of the tennis SofaScore scraper.
- After Phase 4: scraper integration and volleyball fallback tests reflect the new default policy.
- After Phase 5: settlement lookup tests reflect the absence of the SofaScore search helper.

## Security Considerations

- This cleanup reduces reliance on fragile third-party scraping/search surfaces rather than adding new ones.
- No credential, API key, or bookmaker handling changes are required.
- The cleanup must not reintroduce any Betclic scraping behavior.
- Removing unnecessary fallback paths lowers the chance of silent source drift and blocked-request churn.

## Quality Assurance

- Keep changes source-local and avoid rewriting unrelated provider logic.
- Prefer deleting dead registry entries and dead modules over keeping undocumented dormant paths.
- Preserve stable output contracts where downstream scripts depend on them, especially `football_completion` and existing AGENT_SUMMARY shapes.
- Update active documentation only where it describes current live behavior. Historical specs may remain as historical records.

## Recommendation

**Ready for direct implementation:** Yes.

The mandatory cleanup phases are sufficiently specified and low-risk:

- Phase 1 is a scope lock, not a design unknown.
- Phase 2 is a straightforward alignment with the football Flashscore pivot already present in live code.
- Phase 3 and Phase 4 are bounded scraper/fallback removals with explicit test anchors.

The only phase that should remain optional is Phase 5. Settlement SofaScore search cleanup is isolated and safe to split out if the user wants the first implementation pass to stay strictly focused on enrichment and scraper surfaces.

## Changelog

- 2026-05-20 11:30 Europe/Warsaw - Completed Phases 1-2 scope lock and football cleanup: removed football generic `sofascore` fallback, renamed live football completion helpers to neutral rich-completion names, deleted dormant football SofaScore helper/test, and validated with `tests/test_football_flashscore_html_enrichment.py` plus narrow `py_compile`.
- 2026-05-20 11:38 Europe/Warsaw - Completed Phases 3-4 scraper and volleyball cleanup: removed tennis/volleyball SofaScore scrapers from the active registry and source map, deleted orphaned scraper modules/tests, removed volleyball fallback through generic `sofascore`, updated active inventory docs, and validated with `tests/scrapers/test_integration.py`, `tests/test_flashscore_token_policy.py`, and narrow `py_compile`.
- 2026-05-20 12:43 CEST - Completed Phase 5 settlement cleanup: removed the direct `search_sofascore()` settlement fallback, deleted the orphaned helper from `scripts/settle_on_finish.py`, updated the settlement regression tests to Flashscore-only quoting and lookup assertions, and validated the touched slice with `tests/test_flashscore_token_policy.py` plus narrow `py_compile`.
- 2026-05-20 Code review performed. All Phase 5 DoD criteria verified. 17/17 settlement+policy tests pass, 54/54 total (scraper integration + policy) pass. Two minor observations noted in Code Review Findings.
- 2026-05-20 12:58 CEST - Review follow-up: removed generic `sofascore` from `FALLBACK_CHAINS["volleyball"]`, added a regression assertion for the shared volleyball fallback policy, and revalidated with `tests/test_flashscore_token_policy.py` plus narrow `py_compile`.

## Code Review Findings

**Reviewer verdict: APPROVED — no blocking issues.**

All Phase 5 definition-of-done criteria are satisfied. Both files compile cleanly, 17 new tests pass, and the broader scraper+policy suite (54 tests) shows no regressions.

### Observations

**[LOW] `_mark_manual_settlement_source` receives a stale list reference**
- File: [scripts/settle_on_finish.py](../scripts/settle_on_finish.py#L857)
- `still_unsettled` is computed before the DB-stats settlement loop and passed directly into `_mark_manual_settlement_source` after that loop. Picks settled in-place by `settle_stat_market` have their `status` mutated, so the function's internal guard (`pick.get("status") in ("pending", "placed")`) correctly skips them. The behavior is correct, but the variable name `still_unsettled` is misleading at the call site — it may actually contain fully-settled picks after the loop. No code change needed; a comment clarifying the intent would remove ambiguity for the next reader.

**[LOW] Dynamic re-import of `bet.db.connection.get_db` inside `_fetch_settlement_db_match_stats`**
- File: [scripts/settle_on_finish.py](../scripts/settle_on_finish.py#L468)
- The function performs a late `from bet.db.connection import get_db` at call time (consistent with the rest of the script's late-import pattern to avoid hard deps). The test patch `@patch("bet.db.connection.get_db")` works correctly because Python returns the patched attribute from the already-cached module. This is safe in the current test environment but would silently bypass the mock if the function were called before `bet.db.connection` is first imported (edge case only, not a concern in normal operation).

**[INFO] Missing explicit test for `betting_day=None` flow**
- The path where `event_picks[0].get("betting_day")` returns `None` is not directly tested. `_settlement_date_candidates(None)` returns `[]`, which causes `_fetch_settlement_db_match_stats` to return `None` silently — correct graceful degradation. The gap is acceptable given the existing coverage depth.

**[INFO] `_mark_manual_settlement_source` applies to all sports, not only football**
- This is broader than the pre-change behavior (where only football stat markets were attempted via DB stats). For non-football picks with stat-market keywords in the market name, the new code also tags them `manual_verification_required`. This is additive and correct, but is a behavioral change not explicitly described in the plan's Phase 5 DoD. No concern, but worth noting if volleyball/basketball stat market settlement is added in a follow-up.

**[SECURITY / FIXED] `search_flashscore` URL encoding**
- The replacement of `.replace(" ", "%20")` with `urllib.parse.quote(...)` is a correct security improvement — it encodes all reserved characters (e.g., `&`, Unicode) rather than only spaces. The test `test_settlement_search_helper_quotes_flashscore_query` explicitly validates the multi-byte Unicode and special-character case. ✅

### Review Follow-up

- 2026-05-20 12:58 CEST - Resolved the only code-review gap by removing generic `sofascore` from the shared volleyball fallback chain in `src/bet/stats/fallback_chains.py` and adding a regression assertion in `tests/test_flashscore_token_policy.py`.