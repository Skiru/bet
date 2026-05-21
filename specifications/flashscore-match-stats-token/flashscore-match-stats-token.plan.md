# flashscore-match-stats-token - Implementation Plan

## Task Details

| Field            | Value                   |
| ---------------- | ----------------------- |
| Jira ID          | N/A |
| Title            | Flashscore match-stats token remediation |
| Description      | Remove the brittle dependency on Flashscore's tokenized `d.flashscore.com/x/feed/d_st_{event_id}` match-stat endpoint, preserve only the stable non-browser Flashscore search/results-page path where it still adds value, make already-implemented sport-specific providers the canonical source of per-match stats, and explicitly decide whether settlement keeps Flashscore HTML match pages or moves to non-Flashscore sources. |
| Priority         | High |
| Related Research | [flashscore-match-stats-token.research.md](./flashscore-match-stats-token.research.md) |

## Proposed Solution

Adopt the user-approved mixed strategy as a formal source policy.

The implementation should stop treating Flashscore as a deep match-stat provider and instead split responsibilities cleanly:

- Flashscore remains allowed only for stable non-browser search/results-page use cases such as entity resolution and lightweight form/results-page parsing.
- Canonical per-match stats come from the sport-specific provider inventory that already exists in the repo: ESPN, API-Sports clients, Tennis Abstract, Sackmann, Sofascore Tennis, Sofascore, ScraperNHL, MoneyPuck, and related source-specific clients where already implemented.
- Settlement becomes an explicit policy boundary instead of an accidental leftover. The implementation must record whether football stat-market settlement remains temporarily on Flashscore HTML match pages or moves now to non-Flashscore providers plus explicit manual fallback.

This avoids replacing one brittle Flashscore-only path with another brittle Flashscore-only path. It reuses the stable contracts that already matter downstream: `match_stats` as normalized per-fixture facts and `team_form` as a derived cache.

```text
Current state

flashscore_bulk_enrich.py
  -> flashscore_enricher.py::_fetch_match_statistics()
  -> d.flashscore.com/x/feed/d_st_{event_id}
  -> brittle token/x-fsign dependency

Target state

Flashscore search/results page
  -> entity resolution / lightweight form only

Canonical provider chains
  -> per-match stats
  -> match_stats
  -> team_form

Settlement policy gate
  -> either isolated Flashscore HTML adapter (temporary)
  -> or provider-backed settlement + explicit manual fallback
```

No UI changes are expected, so no UI verification tasks are needed.

## Current Implementation Analysis

### Already Implemented

List of existing components, functions, utilities that will be reused (with file paths):

- `src/bet/stats/enrichment.py::_try_api_fetch()` - `src/bet/stats/enrichment.py` - canonical API-first enrichment path that already prefers ESPN and API-Sports and computes `team_form` from normalized per-fixture stats.
- `scripts/fetch_api_stats.py` - `scripts/fetch_api_stats.py` - richer script-level per-sport provider chains already exist for football, basketball, hockey, tennis, and volleyball and already write through the shared stats/cache contracts.
- `src/bet/stats/fallback_chains.py` - `src/bet/stats/fallback_chains.py` - shared fallback-chain module exists and should become the single source of truth instead of creating another routing table.
- `src/bet/api_clients/__init__.py` - `src/bet/api_clients/__init__.py` - registry already exposes the non-Flashscore providers needed by the mixed strategy, including `api-football`, `api-basketball`, `api-hockey`, `api-volleyball`, `espn-*`, `tennis-abstract`, `sackmann`, `sofascore-tennis`, and `sofascore`.
- `src/bet/scrapers/flashscore.py::_get_flashscore_entity()` and `_try_flashscore()` - `src/bet/scrapers/flashscore.py` - stable non-browser Flashscore search/results-page path already exists and is covered by tests.
- `scripts/flashscore_enricher.py::_get_flashscore_entity()` and `_try_flashscore()` - `scripts/flashscore_enricher.py` - standalone Flashscore helper already supports the stable results-page/search flow needed by the mixed strategy.
- `scripts/data_enrichment_agent.py` - `scripts/data_enrichment_agent.py` - enrichment agent already treats Flashscore as a last-resort curl_cffi fallback rather than a primary canonical provider.
- `src/bet/db/repositories.py::StatsRepo` - `src/bet/db/repositories.py` - stable persistence contract for `match_stats` and `team_form`; downstream consumers already depend on these tables instead of caring about upstream source details.
- `scripts/settle_on_finish.py::settle_stat_market()` - `scripts/settle_on_finish.py` - stat-market settlement logic already exists and only needs its stat source boundary clarified.
- `tests/scrapers/test_flashscore.py` - `tests/scrapers/test_flashscore.py` - existing tests protect the working Flashscore results-page/search parser path.
- `tests/test_enrichment_budget.py` - `tests/test_enrichment_budget.py` - existing tests verify the repo's intended behavior of reusing cached `match_stats` data before making new provider calls.

### To Be Modified

List of existing code that needs changes or extensions (with file paths and description of changes):

- `_fetch_match_statistics()` - `scripts/flashscore_enricher.py` - remove the tokenized `d_st_` runtime path or reduce it to a deprecated no-op surface that cannot be invoked accidentally.
- `_try_flashscore_deep()` and CLI messaging - `scripts/flashscore_bulk_enrich.py` - stop promising or attempting deep match-stat enrichment through Flashscore; either downgrade the script to shallow results-page enrichment only or route deep stats through canonical provider-backed logic.
- `FALLBACK_CHAINS` and expected stat coverage - `src/bet/stats/fallback_chains.py` - update the shared chain to reflect already-implemented providers so canonical per-match stats do not depend on Flashscore.
- script-level duplicated fallback chains - `scripts/fetch_api_stats.py` - stop owning a divergent provider policy; import the shared fallback definitions instead.
- stale Flashscore-centric stats routing - `src/bet/api_clients/unified.py` - remove or neutralize the default `totalcorner -> flashscore` / `flashscore` match-stat routing so shared factory code cannot silently reintroduce Flashscore as canonical stats source.
- stale Flashscore delegation - `src/bet/api_clients/volleyball_data.py` - replace the nonexistent `bet.scrapers.flashscore.FlashscoreClient` dependency with an explicit canonical provider or mark the method unsupported.
- Flashscore registry exposure and comments - `src/bet/api_clients/__init__.py` - keep registry support where needed, but align comments and downstream usage so Flashscore is not treated as the default deep stats source.
- settlement stat source - `scripts/settle_on_finish.py` - isolate the current Flashscore HTML path behind an explicit settlement-only source decision or migrate to non-Flashscore sources now.

### To Be Created

List of new components, functions, utilities that need to be built from scratch:

- focused regression tests for the removed tokenized path - new test module(s) under `tests/` validating that no runtime path still constructs or calls `d.flashscore.com/x/feed/d_st_`.
- focused routing tests for canonical per-match provider selection - new test module(s) under `tests/` validating that shared routing prefers sport-specific providers over Flashscore.
- settlement source tests - new test module(s) under `tests/` validating the chosen settlement policy branch: isolated Flashscore HTML adapter or non-Flashscore settlement source plus explicit manual fallback.
- optional narrow settlement source helper - new helper module under `scripts/_helpers/` only if needed to pull network source selection out of `scripts/settle_on_finish.py` cleanly without expanding scope.

### Root Cause

The failure is caused by a brittle assumption in `scripts/flashscore_enricher.py::_fetch_match_statistics()`: it constructs `https://d.flashscore.com/x/feed/d_st_{match_id}` and sends a static `x-fsign: SW9D1eZo` header as though that were sufficient for long-term access. Research and current code comments already show this assumption is no longer reliable. The endpoint now behaves like a rotating-token/session-dependent internal feed, which makes a static non-browser caller fragile.

The blast radius is narrow but important:

- `scripts/flashscore_bulk_enrich.py::_try_flashscore_deep()` is the direct caller.
- that path silently degrades because failed tokenized requests are swallowed and the script can still return shallow score-derived stats from the results page.
- stale shared code still suggests Flashscore is a valid canonical match-stat source in `src/bet/api_clients/unified.py` and `src/bet/api_clients/volleyball_data.py`, increasing the risk that future work routes back into Flashscore-centric behavior.
- settlement is a separate issue: `scripts/settle_on_finish.py` does not use `d_st_`, but it still depends on Flashscore HTML match pages for football stat-market settlement.

### Steps to Reproduce

1. Run the direct caller on a football sample, for example `PYTHONPATH=src .venv/bin/python3 scripts/flashscore_bulk_enrich.py --date 2026-05-20 --sport football --limit 1 --verbose`.
2. Observe that `scripts/flashscore_bulk_enrich.py::_try_flashscore_deep()` resolves a team, fetches its `/results/` page, extracts recent match IDs, and then calls `scripts/flashscore_enricher.py::_fetch_match_statistics()`.
3. Observe that `_fetch_match_statistics()` requests `https://d.flashscore.com/x/feed/d_st_{match_id}` with a static `x-fsign` header.
4. When the feed no longer accepts the static token/header combination, the helper returns no deep stats and the caller falls back to shallow results-page output only, so corners/cards/shots coverage silently disappears or becomes partial.
5. Equivalent function-level reproduction: call `_fetch_match_statistics(["<known_recent_event_id>"], "football")` directly and verify that the returned dict is empty or incomplete even when the caller expected deep stats.

## Open Questions

| #   | Question   | Answer   | Status                |
| --- | ---------- | -------- | --------------------- |
| 1   | What planning baseline should drive the solution? | Use the mixed strategy approved by the user: keep only the stable non-browser Flashscore search/results-page path where it still helps, and make already-implemented sport-specific providers the canonical source of per-match stats. | ✅ Resolved |
| 2   | Do we need new third-party providers to replace the broken tokenized feed? | No. The repo already contains enough provider coverage to execute the mixed strategy without adding a new vendor in this task. | ✅ Resolved |
| 3   | Should `UnifiedAPIClient` be treated as active core architecture? | No direct `UnifiedAPIClient(...)` caller was found in the current workspace, but it is still imported into `bet.api_clients`, so it remains a stale shared surface that must be aligned or explicitly de-risked. | ✅ Resolved |
| 4   | Should Flashscore remain a canonical match-stat source after this change? | No. Flashscore should remain only for stable non-browser search/results-page use cases and any temporary settlement-only exception that is explicitly approved. | ✅ Resolved |
| 5   | Should settlement keep Flashscore HTML match pages for football stat-market settlement or move in the same change set to non-Flashscore sources plus explicit manual fallback? | Branch B was selected after live validation. Football stat-market settlement now uses canonical DB `match_stats` with explicit manual fallback for uncovered stats. | ✅ Resolved |

## Technical Context

Project conventions, coding standards, and patterns discovered during planning. Downstream agents MUST read this section instead of re-discovering the same context.

### Project Instructions

- `.github/copilot-instructions.md` in the `bet` workspace defines the repo as a disciplined betting pipeline with DB-first expectations. Relevant implementation rules for this task: fix the root cause instead of adding another brittle Flashscore workaround; keep changes narrow; preserve stable downstream contracts; and avoid broad cleanup outside the issue.
- Repo/user memory adds two critical workflow rules relevant here: verify data flow before changing producer/consumer scripts, and treat Flashscore results-page curl_cffi access as the currently viable non-browser Flashscore path while avoiding speculative browser/token workarounds.
- The user works in fish shell. Any validation commands in implementation should use simple fish-compatible syntax and avoid inline Python one-liners, bash loops, or heredocs.
- This is a planning-only task. No implementation should be done during planning, but the plan should assume future implementation follows the same repo rules: `apply_patch` for edits, targeted validation after each change, and no unrelated refactors.

### Architecture & Patterns

- The `bet` repo is a Python monorepo with reusable application code under `src/bet/` and orchestration/CLI scripts under `scripts/`. There is also a separate `dashboard/` Next.js app, but this issue is backend/script only.
- Reusable runtime logic lives under `src/bet/` in domain-oriented packages such as `api_clients`, `db`, `scrapers`, and `stats`. Script files often wrap these modules and still contain some legacy duplication.
- Stats flow is contract-driven:
  - `match_stats` stores normalized per-fixture stat rows.
  - `team_form` stores denormalized L10/L5 and H2H caches derived from match stats or fallback enrichment.
  - downstream consumers such as reports, league profiling, and decision evaluation care about those tables, not about which upstream provider produced them.
- `src/bet/db/repositories.py::StatsRepo.save_team_form()` uses DELETE+INSERT wrapped in a savepoint, validates stat ranges before writes, and warns about concurrent write hazards. Future implementation should respect that instead of introducing parallel write paths casually.
- `src/bet/stats/enrichment.py` is the clearest canonical enrichment shape in `src/`: it prefers sport-specific APIs first, computes form from `match_stats`, and writes via `StatsRepo`.
- `scripts/fetch_api_stats.py` contains a richer provider matrix than `src/bet/stats/fallback_chains.py`. The same source policy is currently duplicated in two places and should be consolidated rather than expanded further.
- Flashscore support is currently split across three distinct patterns:
  - `src/bet/scrapers/flashscore.py` and `scripts/flashscore_enricher.py` for stable curl_cffi search/results-page parsing.
  - `scripts/flashscore_enricher.py::_fetch_match_statistics()` for the brittle tokenized `d_st_` feed.
  - `src/bet/api_clients/flashscore.py` and `scripts/settle_on_finish.py` for match-page HTML/Playwright-derived detail access.
- `src/bet/api_clients/unified.py` is stale relative to the current canonical enrichment flow. It still exposes Flashscore-centric match-stat routing even though current enrichment already prefers non-Flashscore providers.

### Tech Stack

- Language/runtime: Python 3.11+.
- Persistence: SQLite database at `betting/data/betting.db`.
- Core libraries in this area from `pyproject.toml`: `requests`, `beautifulsoup4`, `playwright`, `lxml`, `pydantic`, `sqlalchemy`, `rapidfuzz`, and optional `pytest` / `pytest-asyncio` for tests.
- Flashscore non-browser access currently relies on `curl_cffi` in the relevant runtime modules.
- The repo contains a separate Next.js dashboard, but no frontend stack changes are needed for this task.

### Code Style & Standards

- `src/bet/` code generally uses typed function signatures, repository abstractions, and explicit logging. Script files are more mixed and include some legacy direct `sqlite3` usage.
- New shared runtime logic should prefer `get_db()` and repository classes instead of introducing more raw `sqlite3.connect()` paths.
- Existing stats writes should continue to flow through `StatsRepo.save_team_form()` or equivalent established helpers so value-range validation and source provenance are preserved.
- Logging is already the standard way to make degraded provider behavior observable. The fix should favor explicit degraded modes over silent fallback.
- Scope control matters in this repo. Do not use this issue to rewrite all Flashscore code, delete all legacy modules, or refactor unrelated pipeline surfaces.

### Testing Patterns

- Tests live under `tests/` and primarily use `pytest` with in-memory SQLite fixtures or mocked provider calls.
- Relevant existing tests and patterns:
  - `tests/scrapers/test_flashscore.py` validates the working Flashscore search/results-page parser path.
  - `tests/test_enrichment_budget.py` verifies that enrichment reuses cached `match_stats` before calling providers.
  - `tests/test_enrichment_thread_safety.py` checks lock usage in `scripts/data_enrichment_agent.py` by inspecting source text, which shows this repo sometimes uses source-level tests for script behavior.
  - `tests/test_db_integration_fixes.py` validates DB integration contracts around settlement and fixtures.
- There are no direct tests today for the brittle `_fetch_match_statistics()` tokenized path, for `src/bet/api_clients/unified.py` canonical provider routing, or for the stat-source branch in `scripts/settle_on_finish.py`. Those tests should be added as part of the implementation.
- Default fast validation command is `pytest`. For implementation, the first validation pass should use narrow test modules only, for example targeted `pytest tests/...` invocations around the touched slice.

### Database Patterns

- DB-first is the preferred pattern. `get_db()` plus repositories under `src/bet/db/repositories.py` are the intended access layer.
- `match_stats` is the normalized historical truth table for per-fixture stats. `StatsRepo.save_match_stats()` writes one row per stat key.
- `team_form` is a denormalized cache keyed by `(team_id, stat_key, h2h_opponent_id)` semantics. `StatsRepo.is_stale()` and `StatsRepo.get_form()` are already used to avoid unnecessary provider calls.
- `team_form.source` and `match_stats.source` are meaningful provenance fields. The implementation should keep source values accurate when moving away from Flashscore.
- `StatsRepo.save_team_form()` warns that concurrent writes from multiple scripts are hazardous. The plan should avoid adding new parallel writers unless the implementation also adds proper serialization/retry handling.

### Additional Context

- `scripts/flashscore_bulk_enrich.py` is the only direct caller of the broken `d_st_` helper and is therefore the narrowest runtime remediation point.
- `scripts/run_scrapers.py` still exposes Flashscore scrapers in the registry, but it does not hit the tokenized `d_st_` path. It is not part of the direct failure unless implementation changes the scraper registry semantics.
- `scripts/settle_on_finish.py` now uses canonical DB `match_stats` for semi-automated football stat-market settlement, with explicit manual fallback when coverage is missing.
- The stable non-browser Flashscore results-page/search path is already tested and should be preserved only where it provides unique value. Tennis remains weaker on this path, which is another reason not to expand Flashscore responsibilities.

## Implementation Plan

### Phase 1: Canonical Source Policy

#### Task 1.1 - [REUSE] Ratify the match-stat source ownership matrix

**Description**: Use the existing research and current provider inventory to record one canonical owner per workflow: per-match stats enrichment, lightweight Flashscore results-page fallback, H2H/form fallback, and settlement. This task turns the approved mixed strategy into an explicit implementation contract before code changes begin.

**Definition of Done**:

- [x] The implementation branch records a single source policy that states Flashscore is not a canonical per-match stats provider anymore.
- [x] The policy explicitly lists which sport-specific providers are canonical for football, basketball, hockey, tennis, and volleyball.
- [x] The policy explicitly states whether settlement keeps a temporary Flashscore HTML exception or moves in the same change set.
- [x] Unsupported markets and degraded flows are documented as explicit manual fallback, not silent runtime behavior.

#### Task 1.2 - [MODIFY] Consolidate fallback-chain configuration into one authoritative module

**Description**: Align `src/bet/stats/fallback_chains.py` with the richer provider inventory already present in `scripts/fetch_api_stats.py`, then update runtime callers to import the shared definitions instead of maintaining divergent copies.

**Definition of Done**:

- [x] `src/bet/stats/fallback_chains.py` reflects the actual provider inventory already implemented in the repo.
- [x] `scripts/fetch_api_stats.py` stops owning an independent authoritative `FALLBACK_CHAINS` copy.
- [x] Canonical per-match chains do not include Flashscore as a normal deep-stat provider.
- [x] No new provider-routing table is introduced elsewhere for the same concern.

### Phase 2: Remove the Tokenized Runtime Dependency

#### Task 2.1 - [MODIFY] Retire the tokenized Flashscore match-stat helper

**Description**: Remove the live `d.flashscore.com/x/feed/d_st_{event_id}` path from `scripts/flashscore_enricher.py` so the runtime can no longer depend on a static-token assumption. Preserve only the stable results-page/search helpers that remain part of the mixed strategy.

**Definition of Done**:

- [x] No runtime code in `scripts/flashscore_enricher.py` constructs or calls `d.flashscore.com/x/feed/d_st_`.
- [x] Comments, docstrings, and exported behavior no longer claim that Flashscore deep match-stat API access is supported.
- [x] Stable helpers for entity resolution and results-page parsing remain intact.
- [x] Existing tests for stable Flashscore scraping still describe valid behavior after the change.

#### Task 2.2 - [MODIFY] Rework `scripts/flashscore_bulk_enrich.py` around the mixed strategy

**Description**: Stop using `_try_flashscore_deep()` as a pseudo-deep Flashscore source. Either downgrade this script to shallow results-page enrichment only or route its deep-stat responsibility through the canonical provider chain and then aggregate results into the existing persistence contract.

**Definition of Done**:

- [x] `scripts/flashscore_bulk_enrich.py` no longer attempts to fetch deep stats from Flashscore tokenized feeds.
- [x] The script's CLI flags, logging, and docstrings accurately describe its new responsibility.
- [x] If the script remains in use, its writes to `team_form` continue to preserve correct source provenance.
- [x] If the script is reduced to shallow-only behavior, the deep-stat responsibility is clearly handed to an already-existing provider-backed path.

#### Task 2.3 - [REUSE] Route deep stats through existing provider-backed enrichment paths

**Description**: Reuse `src/bet/stats/enrichment.py`, `scripts/fetch_api_stats.py`, and `scripts/data_enrichment_agent.py` as the canonical deep-stat producers instead of inventing a new Flashscore replacement flow.

**Definition of Done**:

- [x] Deep per-match stats for supported sports are sourced from existing sport-specific providers.
- [x] No new custom deep-stat orchestration path is introduced for this issue.
- [x] Any necessary wiring changes reuse existing normalized `match_stats` / `team_form` contracts.
- [x] Flashscore remains, at most, a last-resort results-page fallback rather than a deep-stat owner.

### Phase 3: Clean Stale Shared Routing and Resolve Settlement

#### Task 3.1 - [MODIFY] Align or de-risk `src/bet/api_clients/unified.py`

**Description**: Remove the stale Flashscore-centric match-stat routing from `UnifiedAPIClient` or explicitly constrain the class so future callers cannot silently get Flashscore as the default deep-stat source.

**Definition of Done**:

- [x] `STATS_PRIORITY` no longer points football stats to `totalcorner -> flashscore` as the canonical chain.
- [x] Default match-stat routing in `UnifiedAPIClient` reflects the canonical provider policy or is explicitly marked legacy/non-canonical.
- [x] `get_deep_data()` no longer assumes Flashscore match stats are the default deep-data source.
- [x] The change does not expand scope into unrelated `UnifiedAPIClient` cleanup beyond what is needed to remove stale Flashscore routing risk.

#### Task 3.2 - [MODIFY] Remove stale Flashscore match-stat assumptions from secondary clients

**Description**: Fix modules such as `src/bet/api_clients/volleyball_data.py` that still assume a Flashscore match-stat client shape that no longer exists or should no longer be canonical.

**Definition of Done**:

- [x] `src/bet/api_clients/volleyball_data.py` no longer imports or expects a nonexistent `bet.scrapers.flashscore.FlashscoreClient`.
- [x] Any retained volleyball match-stat path points to an actual supported provider or fails explicitly.
- [x] Comments in secondary clients no longer suggest Flashscore deep match stats are the default solution.

#### Task 3.3 - [REUSE] Resolve the settlement source policy before touching `scripts/settle_on_finish.py`

**Description**: Use the Phase 1 source matrix to choose exactly one of the two implementation branches below before changing settlement code.

**Definition of Done**:

- [x] The user-approved settlement choice is recorded in the implementation branch or issue notes.
- [x] The selected branch is scoped to football stat-market settlement only unless an expanded scope is explicitly approved.
- [x] The non-selected branch is not partially implemented.

#### Task 3.4 - [MODIFY] Branch A: keep Flashscore HTML for settlement as a temporary isolated exception

**Description**: If the user approves keeping Flashscore HTML settlement for now, isolate the existing HTML/search logic as a settlement-only adapter and make the exception explicit instead of leaving the code path embedded as a hidden repo-wide Flashscore assumption.

Status: superseded by Branch B after intermediate live validation.

These unchecked DoD items are historical only. They are not remaining implementation work because Branch A was explicitly abandoned in favor of Branch B.

**Definition of Done**:

- [ ] `scripts/settle_on_finish.py` calls an explicit settlement-only stat source helper or clearly isolated internal function for Flashscore HTML.
- [ ] The helper is documented as a temporary exception, not a canonical match-stat provider.
- [ ] Manual fallback behavior is explicit when Flashscore HTML settlement cannot provide stats.
- [ ] No other runtime path reuses that settlement-only helper for enrichment.

#### Task 3.5 - [MODIFY] Branch B: move settlement off Flashscore in the same change set

**Description**: If the user approves a full move now, replace Flashscore HTML settlement for football stat markets with the canonical provider chain wherever coverage exists, and preserve manual fallback for unsupported markets or competitions.

Branch status: selected and implemented.

**Definition of Done**:

- [x] `scripts/settle_on_finish.py` no longer fetches Flashscore HTML match-stat pages for settlement.
- [x] Settlement source order is consistent with the canonical provider matrix defined earlier in the plan.
- [x] Unsupported or low-confidence markets degrade explicitly to manual settlement.
- [x] Settlement source provenance is visible in the resulting pick status metadata.

### Phase 4: Focused Validation and Guardrails

#### Task 4.1 - [CREATE] Add regression tests for the removed tokenized path

**Description**: Add narrow tests that fail if runtime code still constructs or depends on `d.flashscore.com/x/feed/d_st_`.

**Definition of Done**:

- [x] A focused test covers the direct caller surface that previously used `_fetch_match_statistics()`.
- [x] The test fails if tokenized Flashscore deep-stat routing is reintroduced.
- [x] The test remains narrow to this issue and does not require network access.

#### Task 4.2 - [CREATE] Add focused routing tests for canonical provider selection

**Description**: Add tests around the shared provider policy so future changes cannot silently route match stats back to Flashscore.

**Definition of Done**:

- [x] Tests cover the updated fallback-chain ownership and at least one stale shared surface such as `UnifiedAPIClient`.
- [x] Tests verify that supported sports prefer their canonical non-Flashscore providers for per-match stats.
- [x] Tests verify explicit degraded behavior where coverage is not available.

#### Task 4.3 - [CREATE] Add settlement-source tests for the chosen branch

**Description**: Add tests that verify the selected settlement policy branch and prevent accidental cross-contamination between enrichment and settlement source rules.

**Definition of Done**:

- [ ] If Branch A is chosen, tests verify Flashscore HTML is isolated to settlement only.
- [x] If Branch B is chosen, tests verify settlement no longer hits Flashscore HTML match pages.
- [x] Tests cover explicit manual fallback behavior for unsupported markets.

#### Task 4.4 - [REUSE] Run targeted quality checks

**Description**: Validate the touched slice with existing fast-running checks only. Do not widen into unrelated suites unless the touched tests require it.

**Definition of Done**:

- [x] Targeted `pytest` runs cover the touched Flashscore, enrichment, routing, and settlement test modules.
- [x] Existing relevant tests such as `tests/scrapers/test_flashscore.py` and `tests/test_enrichment_budget.py` continue to pass.
- [x] Any new targeted tests added for this issue pass without relying on live network responses.

## Security Considerations

- Do not attempt to solve the issue by harvesting, caching, or replaying rotating Flashscore session/token material from a browser. That would increase fragility and create a hidden session-management dependency.
- Keep third-party requests rate-limited and explicit. The fix should reduce hidden dependency on blocked or anti-bot-protected internal endpoints rather than add more of it.
- Preserve source provenance in `match_stats`, `team_form`, and settlement metadata so debugging degraded provider behavior remains possible.
- If settlement temporarily keeps Flashscore HTML, isolate it as a clearly bounded exception so future contributors do not generalize it into enrichment paths.
- Avoid expanding API-key usage beyond already-implemented providers for this issue. Reordering existing providers is in scope; adding a new vendor is not.

## Quality Assurance

Acceptance criteria checklist to verify the implementation meets the defined requirements:

- [x] No runtime code path depends on `https://d.flashscore.com/x/feed/d_st_{event_id}`.
- [x] The stable Flashscore non-browser search/results-page path remains available only for approved lightweight use cases.
- [x] Already-implemented sport-specific providers are the canonical per-match stats sources after the change.
- [x] Shared routing/configuration surfaces no longer default back to Flashscore for deep match stats.
- [x] The directly affected runtime slice (`scripts/flashscore_enricher.py` and `scripts/flashscore_bulk_enrich.py`) reflects the mixed strategy accurately in code and logging.
- [x] Settlement behavior is explicit, documented, and tested according to the chosen policy branch.
- [x] Focused regression tests cover the removed tokenized path, canonical provider routing, and settlement-source behavior.

## Improvements (Out of Scope)

Potential improvements identified during planning that are not part of the current task:

- Full retirement or deletion of all legacy Flashscore Playwright clients if they remain unused after this issue.
- Wider cleanup of script-level raw `sqlite3` usage that predates this task.
- General provider-health telemetry and automated coverage scoring across all enrichment sources.
- Broader refactoring of unrelated legacy modules that import `UnifiedAPIClient` only indirectly.

## Changelog

| Date   | Change Description   |
| ------ | -------------------- |
| 2026-05-20 | Initial plan created |
| 2026-05-20 | Branch A selected for settlement: keep Flashscore HTML as an explicit settlement-only exception |
| 2026-05-20 | Implemented tokenized-feed retirement, canonical provider routing alignment, settlement isolation, and focused regression tests |
| 2026-05-20 | Live smoke tests uncovered a fixture/stats payload shape mismatch in `scripts/fetch_api_stats.py`; fixed and covered with focused regression tests |
| 2026-05-20 | Review follow-up: fixed settlement URL encoding, numeric sport-id handling, transient retry behavior, and consistent volleyball fallback returns |
| 2026-05-20 | Live settlement smoke test uncovered list-shaped `livesport` search payload handling gap; fixed and covered with regression test |
| 2026-05-20 16:10 CEST | Branch A live fix: settlement helper now recognizes object-typed Livesport event results, extracts match ids from event URLs when needed, and adds a focused regression test |
| 2026-05-20 10:15 CEST | Branch A live fix: when Livesport search yields no event row, settlement now falls back to Flashscore team `/results/` page event-id resolution before fetching match statistics |
| 2026-05-20 10:33 CEST | Branch B live fix: football stat-market settlement now reads canonical DB `match_stats` and passed on real ledger pick `PK-20260507-02` (`Crystal Palace vs Shakhtar Donetsk`) with `db_match_stats_settlement` provenance |
| 2026-05-20 10:46 CEST | Review follow-up: DB match_stats provenance is now the default, dead Flashscore fallback duplication removed, settlement reads go through `StatsRepo`, manual fallback markers are centralized, and live recheck on `PK-20260507-02` still passed |
| 2026-05-20 10:50 CEST | Review follow-up 2: fixed stale Flashscore fallback test patch targets after helper extraction, added ±1-day DB fallback coverage plus a main-path isolation test, marked Branch A as superseded in the final plan, and revalidated the live DB settlement on `PK-20260507-02` |
| 2026-05-20 11:00 CEST | Final code review performed — 42 tests passing, all Branch B acceptance criteria met; the three low-severity findings were later cleaned up in the focused 2026-05-20 11:40 CEST pass |
| 2026-05-20 11:40 CEST | Focused cleanup pass: removed superseded Branch A settlement wrappers and Flashscore HTML helper state from `settle_on_finish.py`, moved shared Flashscore HTML regressions to `tests/test_flashscore_match_page_stats.py`, fixed stale `.github` prompt/session-memory references, and updated Branch B final-state docs |
| 2026-05-20 11:21 CEST | Review-fix pass: corrected stale Branch B knowledge-base anchors (including `_fetch_settlement_db_match_stats`) and clarified in-plan that Branch A unchecked DoD items are historical superseded artifacts rather than pending work |
| 2026-05-20 | Final post-cleanup code review performed by `tsh-code-reviewer`. Findings: (F1-info) module docstring was stale — fixed in same pass; (F2-low) `_sync_settlement_to_db` fallback LIMIT 1 without ORDER BY — pre-existing, tracked; (F3-info) intermediate changelog entry noted 42 tests vs final 47 — no action; no blocking findings. All acceptance criteria confirmed met. |
| 2026-05-20 11:49 CEST | Final foundation validation: reran the focused regression suite (`47 passed`), reran the non-mutating live Branch B probe on `PK-20260507-02` (`stats_found=true`, `settled=true`, `status=win`, `settlement_source=db_match_stats_settlement`), and created the follow-up multisport rich-stat enrichment plan for future implementation |

## Code Review Findings

Review performed 2026-05-20 against the final implementation after all follow-up fixes, the focused cleanup pass, the final review-fix pass, and the final foundation validation.

### Test results

`PYTHONPATH=src .venv/bin/pytest -q tests/test_flashscore_token_policy.py tests/test_flashscore_match_page_stats.py tests/test_db_repositories.py` → **47 passed in 0.91s** ✅

Non-mutating live Branch B probe on real ledger pick `PK-20260507-02` → **stats_found=true, settled=true, status=win, settlement_source=db_match_stats_settlement** ✅

### Acceptance criteria verdict

All 7 Branch B acceptance criteria are met (see checkboxes above). Branch A DoD items and the first Task 4.3 bullet are intentionally left unchecked because Branch A was superseded; they are historical branch markers, not pending work.

### Findings

**F1 — INFO — Module docstring stale (fixed)**

`scripts/settle_on_finish.py` header notes were updated to reflect Branch B DB-backed stat settlement plus explicit manual fallback semantics.

**F2 — LOW — `_sync_settlement_to_db` fallback query non-deterministic**

`scripts/settle_on_finish.py` event-only fallback still uses `LIMIT 1` without `ORDER BY`. This is pre-existing and only applies when the primary `event+market` DB sync path does not match. Low practical risk; tracked, not part of this task.

**F3 — INFO — Earlier cleanup findings resolved**

The earlier low-severity cleanup findings were resolved in the 2026-05-20 11:40 CEST cleanup pass:

- dead Branch A settlement wrapper delegates were removed from `scripts/settle_on_finish.py`
- dead settlement-only Flashscore helper state/constants were removed from `scripts/settle_on_finish.py`
- legacy Flashscore HTML regression coverage was moved to `tests/test_flashscore_match_page_stats.py`, removing the misleading settlement-specific test naming

**F4 — INFO — Documentation anchors now aligned to final validation**

The 2026-05-20 11:21 CEST review-fix pass and the 2026-05-20 11:49 CEST final validation pass aligned repository memory and plan artifacts to the final `47 passed` focused suite result.

No blocking findings remain.

### Residual risk

- Shared Flashscore HTML parsing and match-id resolution still exist in `scripts/_helpers/flashscore_match_page_stats.py` for enrichment/shared helper use. Any future policy change that reintroduces it into settlement would need new explicit tests because the main settlement path no longer owns that code.
- `_sync_settlement_to_db` retains its pre-existing low-risk event-only fallback query ambiguity when market matching fails in DB.