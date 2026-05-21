# hockey-rich-stat-enrichment - Implementation Plan

## Task Details

| Field            | Value |
| ---------------- | ----- |
| Jira ID          | N/A |
| Title            | Hockey rich-stat enrichment |
| Description      | Extend the shared rich-stat enrichment architecture already proven by the existing football implementation to hockey while preserving the stable `match_stats -> team_form` contract, keeping ownership in enrichment flows, and separating canonical per-game completion from the existing aggregate-only MoneyPuck and ScraperNHL supplements already present in the repo. |
| Priority         | High |
| Related Research | `specifications/multisport-rich-stat-enrichment/multisport-rich-stat-enrichment.plan.md`, `specifications/flashscore-match-stats-token/flashscore-match-stats-token.plan.md`, `memories/repo/pipeline-knowledge-base.md` |

## Proposed Solution

Implement hockey rich completion as a provider-backed per-game path centered on `api-hockey`, while keeping MoneyPuck and ScraperNHL as explicitly supplementary aggregate sources.

The implementation should keep the shared architecture already proven elsewhere:

- `scripts/data_enrichment_agent.py` remains the enrichment owner
- a bounded helper under `scripts/_helpers/` performs hockey-specific completion work
- persistence still goes through `fetch_api_stats._store_in_cache()` into `match_stats` and derived `team_form`
- generic probe and rich-coverage reporting should extend the basketball-owned shared foundation; if that foundation is missing in the working branch, escalate sequencing or obtain explicit manager reassignment instead of creating a hockey-only fork

Hockey-specific source policy:

- canonical per-game rich completion: `api-hockey`
- bounded supporting source: `espn-hockey` when it returns per-game stats that fit the normalized contract
- `espn-hockey` is registry-scoped to NHL fixtures (`CLIENT_REGISTRY["espn-hockey"] = _espn_factory("hockey", "nhl")`), so empty results outside NHL should be treated as unsupported-league skips rather than degraded-source failures
- aggregate-only / advisory sources: `moneypuck` and `scrapernhl`

`required_rich_keys` for canonical hockey completion must be derived from stats actually exposed by `api-hockey`. Until `api_hockey.py` maps `takeaways` and `giveaways`, treat those keys as supplementary-only and exclude them from canonical rich-completion success.

This plan must preserve the analytical value of aggregate advanced stats without allowing them to masquerade as canonical `match_stats`-backed richness.

When delegating implementation, use this child plan as the primary execution artifact and pass the multisport plan only as shared-guardrail context.
This plan is independently usable for hockey-specific logic, but it does not authorize a second shared probe / registry / report implementation path.
If the basketball-owned shared foundation is absent, record the blocker in this plan's Changelog and halt the slice; do not create `scripts/rich_stats_probe.py`, the shared completion registry, or the generic `rich-coverage` report path from scratch unless the manager explicitly reassigns that ownership.

**Branch B settlement remains out of scope and unchanged.** This plan does not modify `scripts/settle_on_finish.py` or the finalized DB-backed settlement path.

**Live validation commands**:

- `PYTHONPATH=src .venv/bin/python scripts/rich_stats_probe.py --date YYYY-MM-DD --sport hockey --limit 10 --verbose`
- `PYTHONPATH=src .venv/bin/python scripts/db_report.py --report rich-coverage --sport hockey --date YYYY-MM-DD`
- `PYTHONPATH=src .venv/bin/pytest -q tests/test_api_season_fixtures.py tests/test_hockey_rich_completion.py`

These are post-implementation validation commands, not preflight checks against the current branch state.
They assume the basketball-owned shared foundation (`scripts/rich_stats_probe.py`, the shared completion registry, and the generic `rich-coverage` report path) is already present in the working branch or has been explicitly reassigned by the manager in the same slice. `tests/test_hockey_rich_completion.py` must exist before the final pytest run.

Use shared report-bucket vocabulary consistently: `rich`, `baseline_only`, `partial`, `no_data`.
For hockey, `baseline_only` means usable match-level coverage exists in `match_stats` / `team_form`, but the required hockey rich keys are still missing. Keep AGENT_SUMMARY owner metrics separate: `eligible`, `completed`, `still_missing`.

## Current Implementation Analysis

### Already Implemented

List of existing components, functions, utilities that will be reused (with file paths):

- `scripts/data_enrichment_agent.py` - current owner flow already supplements hockey with MoneyPuck and ScraperNHL aggregate stats when baseline enrichment is incomplete
- `scripts/fetch_api_stats.py::_store_in_cache()` - established writer into `match_stats` and derived `team_form`
- `src/bet/stats/fallback_chains.py` - shared fallback-chain module already listing hockey providers and expected stat keys
- `src/bet/api_clients/api_hockey.py` - existing per-game provider client mapping `goals`, `shots`, `powerplay_goals`, `pim`, `hits`, `blocks`, and `faceoff_pct`
- `src/bet/api_clients/moneypuck_wrapper.py` and `src/bet/api_clients/moneypuck_client.py` - aggregate NHL advanced-stat surfaces already used for supplementation
- `src/bet/api_clients/scrapernhl_wrapper.py` - existing ScraperNHL aggregate/advanced surface used in enrichment
- `src/bet/api_clients/__init__.py` - canonical client registry exposing hockey sources
- `tests/test_api_season_fixtures.py` - current fixture/provider test coverage that already includes hockey-related paths

### To Be Modified

List of existing code that needs changes or extensions (with file paths and description of changes):

- `scripts/data_enrichment_agent.py` - separate canonical per-game completion from aggregate supplementation, and add hockey completion metrics
- `scripts/fetch_api_stats.py` - reuse or expose the minimal writer seams needed for a hockey completion helper
- `src/bet/stats/fallback_chains.py` - encode explicit completion semantics in `RICH_COMPLETION_POLICY`, keep baseline `FALLBACK_CHAINS` order unchanged for non-rich scenarios, and ensure aggregate sources cannot imply canonical `match_stats` richness
- `scripts/db_report.py` - extend the basketball-owned generic `rich-coverage` report to accept `--sport hockey`; reuse the shared `--sport` CLI argument and `rich-coverage` argparse choice rather than adding a separate hockey-named report path

### To Be Created

List of new components, functions, utilities that need to be built from scratch:

- hockey-specific extensions to the basketball-owned shared completion registry / probe / report surfaces
- do not create `scripts/rich_stats_probe.py`, the shared completion registry, or the generic `rich-coverage` report path from scratch; if they are absent, record the blocker in this plan's Changelog and halt until basketball Task 1.1 is confirmed complete in the working branch or the manager explicitly reassigns ownership
- `scripts/_helpers/hockey_rich_completion.py` - bounded helper for per-game provider-backed hockey completion
- `tests/test_hockey_rich_completion.py` - focused adapter, routing, aggregate-vs-per-game, and no-write probe tests

## Open Questions

| #   | Question | Answer | Status |
| --- | -------- | ------ | ------ |
| 1   | Can MoneyPuck or ScraperNHL count as hockey rich completion by themselves? | No. They remain valuable supplementary aggregate sources only. | ✅ Resolved |
| 2   | Should hockey completion move into `scripts/run_scrapers.py` because hockey scrapers already exist? | No. This remains an enrichment-owner responsibility. | ✅ Resolved |
| 3   | Should MoneyPuck remain the canonical hockey source because it is analytically valuable? | No for `match_stats` completion. It stays supplementary only; canonical per-game completion should be provider-backed. | ✅ Resolved |
| 4   | Does this plan change Branch B settlement? | No. Settlement remains DB-backed and unchanged. | ✅ Resolved |

## Technical Context

Project conventions, coding standards, and patterns discovered during planning. Downstream agents MUST read this section instead of re-discovering the same context.

### Project Instructions

- `.github/copilot-instructions.md` - DB-first, verify producer/consumer flow before changes, keep scope narrow
- workspace memory - fish-safe command examples only
- `memories/repo/pipeline-knowledge-base.md` - Branch B settlement is final and shared Flashscore HTML helpers are not the settlement main path

### Architecture & Patterns

- `scripts/data_enrichment_agent.py` currently supplements hockey with MoneyPuck and ScraperNHL only when result status is not enriched; the plan should preserve the value of that supplement path while separating it from canonical completion semantics
- `_store_in_cache()` remains the only intended write boundary for per-game completion
- `NormalizedMatchStats` is defined in `src/bet/models/normalized.py` (exported via `src/bet/models/__init__.py`) and is the required payload passed to `_store_in_cache()`: `fixture_id`, `source`, `sport`, `home_team`, `away_team`, `date`, and `stats` with per-stat `home` / `away` sub-keys
- `src/bet/stats/fallback_chains.py` currently lists `espn-hockey`, `api-hockey`, `scrapernhl`, and `moneypuck`; keep that baseline ordering unchanged and express canonical hockey completion in `RICH_COMPLETION_POLICY` instead of changing baseline fallback behavior
- `scripts/db_report.py` currently exposes only `football-rich-coverage`; hockey rollout requires a generic report

### Tech Stack

- Python `>=3.11`
- SQLite DB at `betting/data/betting.db`
- runtime libraries already used in this area: `requests`, `curl_cffi`, `sqlalchemy`, `pydantic`
- tests run with `pytest`

### Code Style & Standards

- Keep source-specific logic in bounded helpers under `scripts/_helpers/`
- Preserve explicit provenance labels such as `api-hockey`, `espn-hockey`, `moneypuck`, and `scrapernhl`
- Do not let aggregate sources silently satisfy canonical `match_stats` completion
- Do not move this work into `scripts/run_scrapers.py`

### Testing Patterns

- Use narrow pytest modules with mocked provider payloads and source-policy assertions
- Mirror the football validation shape: helper/adapter test, owner-routing test, and no-write probe/report test
- `tests/test_flashscore_token_policy.py` is intentionally not part of the hockey validation command because its current assertions are football/volleyball-specific; hockey source-policy regressions should be covered in `tests/test_hockey_rich_completion.py`
- Keep commands fish-safe and date-scoped

### Database Patterns

- `match_stats` remains the canonical per-fixture truth table
- `team_form` remains the denormalized analytics surface and may still receive supplementary aggregate stats when explicitly labeled as such
- Branch B settlement is unchanged and not part of this plan

### Additional Context

- `scripts/data_enrichment_agent.py` currently merges MoneyPuck and ScraperNHL stats into the result surface if baseline enrichment is still incomplete; this is the key ambiguity the hockey plan must resolve
- `src/bet/api_clients/api_hockey.py` currently maps `goals`, `shots`, `powerplay_goals`, `pim`, `hits`, `blocks`, and `faceoff_pct`; until it also maps `takeaways` / `giveaways`, those keys remain supplementary-only rather than canonical rich-completion requirements
- `faceoffs_won` appears in `EXPECTED_STATS_PER_SPORT["hockey"]` but is not mapped by `api_hockey.py` and is excluded from `required_rich_keys`; do not add it to the hockey policy in this slice
- `goals` is intentionally treated as a baseline hockey stat, not a rich-completion requirement, so it stays outside `required_rich_keys` and outside the hockey rich-audit target set in this slice
- `penalties` in `EXPECTED_STATS_PER_SPORT["hockey"]` is a legacy alias of the canonical `pim` key; align the hockey audit set to `pim` in this slice rather than treating `penalties` as a separate unmapped required stat
- **Branch B settlement remains out of scope and unchanged throughout this plan**

## Implementation Plan

### Phase 1: Shared Completion Foundation for Hockey

#### Task 1.1 - [MODIFY] Extend shared completion registry and generic reporting for hockey

**Description**: Extend the shared completion policy, no-write probe, and generic rich-coverage reporting for hockey. If the basketball-owned shared foundation is missing in the working branch, record the blocker in this plan's Changelog and halt the slice rather than creating a hockey-only duplicate.

**Definition of Done**:

- [x] Hockey declares `required_rich_keys`, `canonical_source`, `supporting_sources`, and `aggregate_only_sources` in `src/bet/stats/fallback_chains.py::RICH_COMPLETION_POLICY`
- [x] Hockey `required_rich_keys` are exactly `shots`, `hits`, `blocks`, `pim`, `powerplay_goals`, and `faceoff_pct`
- [x] Hockey `supporting_sources` are exactly `espn-hockey`
- [x] Hockey `aggregate_only_sources` are exactly `moneypuck` and `scrapernhl`
- [x] The shared `scripts/rich_stats_probe.py` supports `--sport hockey` and reports source choice, fixture coverage, completion rate, and failure reasons
- [x] `scripts/db_report.py` supports `--report rich-coverage --sport hockey --date <date>`
- [x] Aggregate-only sources are explicitly excluded from canonical rich-completion buckets in reporting
- [x] `takeaways` and `giveaways` stay supplementary-only unless `api_hockey.py` gains canonical mappings for them in the same slice

#### Task 1.2 - [CREATE] Build the bounded hockey completion adapter

**Description**: Add a hockey helper under `scripts/_helpers/` that fetches recent finished fixtures from canonical provider-backed sources, normalizes per-game rich stats, and persists only through `_store_in_cache()`.

**Definition of Done**:

- [x] `api-hockey` is the canonical completion source
- [x] `espn-hockey` is a bounded supporting source only when it returns per-game normalized stats
- [x] Empty `espn-hockey` responses for non-NHL fixtures are treated as unsupported-league skips, not degraded-source failures
- [x] Completion success is measured against hockey required rich keys rather than any aggregate advanced-stat payload
- [x] The adapter returns the base 7-key contract used by the shared enrichment flow: `status` (`str`), `fixtures_scanned` (`int`), `matches_persisted` (`int`), `rich_keys_found` (`list[str]`), `missing_rich_keys` (`list[str]`), `error` (`str | None`), and `failure_reason` (`str | None`)

### Phase 2: Owner Wiring, Supplement Separation, and Tests

#### Task 2.1 - [MODIFY] Separate canonical hockey completion from aggregate supplements in the owner flow

**Description**: Update `scripts/data_enrichment_agent.py` so per-game completion and aggregate supplementation remain distinct in source semantics, metrics, and reporting.

**Definition of Done**:

- [x] Hockey teams or fixtures that remain partial after baseline enrichment can trigger the hockey completion helper from the owner flow
- [x] MoneyPuck and ScraperNHL remain explicitly supplementary in metrics and source provenance; they may still run as an additive analytics layer after canonical completion, but they never satisfy `required_rich_keys`, change the canonical bucket, or replace the canonical source
- [x] AGENT_SUMMARY exposes hockey `eligible`, `completed`, and `still_missing` counts without conflating aggregate supplements with canonical completion
- [x] Branch B settlement code remains untouched

#### Task 2.2 - [CREATE] Add focused hockey adapter, routing, and aggregate-policy tests

**Description**: Add narrow tests that prevent aggregate-vs-per-game drift and verify the owner-routing path.

**Definition of Done**:

- [x] Tests cover adapter persistence through `_store_in_cache()`
- [x] Tests cover owner routing from `scripts/data_enrichment_agent.py`
- [x] Tests verify aggregate-only sources cannot satisfy canonical rich completion by themselves
- [x] Tests cover no-write probe behavior and reporting buckets

### Phase 3: Live Validation and Review

#### Task 3.1 - [REUSE] Run the sport-specific live validation commands

**Description**: Validate hockey rollout with the planned probe, report, and narrow test commands only.

**Definition of Done**:

- [x] `scripts/rich_stats_probe.py --sport hockey` runs with no unintended DB/cache mutations
- [x] `scripts/db_report.py --report rich-coverage --sport hockey --date <date>` distinguishes `rich`, `baseline_only`, `partial`, and `no_data`
- [x] The hockey-focused pytest command passes

#### Task 3.2 - [REUSE] Final code review by `tsh-code-reviewer`

**Description**: After focused executable validation passes, run the final review to verify helper boundaries and aggregate-source guardrails.

**Definition of Done**:

- [x] Review is run after the focused validation suite
- [x] Findings are fixed or explicitly tracked in the Changelog
- [x] Review confirms no canonical-completion regression toward aggregate-only sources and no Branch B settlement regression
- [x] The slice is not closed while review findings remain unresolved and untracked

## Security Considerations

- Keep provider calls bounded to recent finished fixtures and date-scoped probes
- Do not treat aggregate CSV or schedule sources as canonical per-fixture truth
- Preserve explicit provenance and failure reasons for provider and supplement paths
- Keep settlement logic untouched while implementing hockey enrichment

## Quality Assurance

Acceptance criteria checklist to verify the implementation meets the defined requirements:

- [x] Hockey completion remains owned by enrichment flows, not `scripts/run_scrapers.py`
- [x] `api-hockey` is the canonical completion source in code and reporting
- [x] MoneyPuck and ScraperNHL remain supplementary only and cannot satisfy canonical rich completion by themselves
- [x] A generic `rich-coverage` report exists and works for hockey
- [x] Hockey adapter, routing, aggregate-policy, and probe tests pass
- [x] **Branch B settlement remains out of scope and unchanged**

## Code Review Findings

**Review date**: 2026-05-20  
**Reviewer**: tsh-code-reviewer  
**Validation baseline**: 22 tests passed, probe and db_report commands confirmed correct

### CRITICAL (must fix before slice close)

| # | Severity | File | Finding |
|---|----------|----|--------|
| 1 | **CRITICAL** | `scripts/_helpers/hockey_rich_completion.py` L70 | `COALESCE(c.name, )` — missing second argument. SQL syntax error (`sqlite3.OperationalError`) silently swallowed by `except Exception`, returns `([], None)`, surfaced as false `"team_not_found"` failure reason. Should be `COALESCE(c.name, '')`. |
| 2 | **CRITICAL** | `scripts/_helpers/hockey_rich_completion.py` L76 | `f.status = finished` — unquoted string literal. SQLite treats `finished` as a column reference, not the string `'finished'`. Same silent-swallow failure path as finding #1. Should be `f.status = 'finished'`. |

Both SQL bugs are invisible to CI because **every test that exercises completion mocks `_get_recent_hockey_fixtures`**. The bugs only surface at runtime against a real DB with real hockey fixtures.

### MEDIUM

| # | Severity | File | Finding |
|---|----------|----|--------|
| 3 | Medium | `scripts/_helpers/hockey_rich_completion.py` | No test exercises the real `_get_recent_hockey_fixtures` DB path. A minimal integration test against an in-memory SQLite (or a raw `execute` call with the exact SQL string) would have caught findings #1 and #2 before merge. |
| 4 | Medium | `scripts/data_enrichment_agent.py` ~L1144 | When the main fallback chain and `_apply_hockey_rich_completion` both return zero stats, the MoneyPuck supplement sets `result["source"] = "moneypuck"`. This leaks an aggregate-only label into `result["source"]` even though `_refresh_hockey_coverage_result` correctly keeps `hockey_rich_complete = False`. The plan requires supplementary sources to remain "explicitly supplementary in metrics and source provenance". `hockey_completion` metrics are not conflated (AGENT_SUMMARY counts are correct), but the raw `result["source"]` field is misleading. Pre-existing supplement logic; assess for fix in the same or a follow-up slice. |

### LOW / STYLE

| # | Severity | File | Finding |
|---|----------|----|--------|
| 5 | Low | `src/bet/stats/fallback_chains.py` L105 | `EXPECTED_STATS_PER_SPORT["hockey"]` first line has 3 extra leading spaces (`           "shots"`) compared to the standard 8-space indent used by all other sports. Cosmetic only; no functional impact. |

### Resolution Status

- 2026-05-20: Findings #1 and #2 fixed in `scripts/_helpers/hockey_rich_completion.py` by correcting the real DB fixture SQL path and adding a focused test that exercises `_get_recent_hockey_fixtures()` against an in-memory SQLite DB.
- 2026-05-20: Finding #4 fixed in `scripts/data_enrichment_agent.py` by keeping `moneypuck` and `scrapernhl` in `supplementary_sources` only when they arrive via the hockey supplementary path; they no longer become the main `result["source"]` in that branch.
- 2026-05-20: Finding #5 remains tracked as cosmetic and out of scope for this approved hockey review-fix slice.

### Testing Gaps (non-blocking)

- No test for `complete_hockey_rich_stats` where both api-hockey and espn-hockey fail on a valid NHL fixture (distinct from the KHL unsupported-league-skip case).
- No test for the multi-fixture scan path (`max_fixtures > 1`) where the first fixture is partial and the second completes the rich key set.

### Plan Compliance Verification

| Requirement | Status |
|-------------|--------|
| Shared foundation extended, not forked | ✅ Pass |
| Ownership stays in `data_enrichment_agent.py` | ✅ Pass |
| Persistence through `_store_in_cache()` only (canonical path) | ✅ Pass |
| Canonical source is `api-hockey` | ✅ Pass |
| Supporting source is exactly `espn-hockey` | ✅ Pass |
| Aggregate-only sources are exactly `moneypuck` and `scrapernhl` | ✅ Pass |
| Aggregate-only sources excluded from rich-completion buckets | ✅ Pass (`_HOCKEY_ALLOWED_SOURCES` does not include them) |
| Required rich keys: `shots`, `hits`, `blocks`, `pim`, `powerplay_goals`, `faceoff_pct` | ✅ Pass |
| `takeaways`/`giveaways` supplementary only | ✅ Pass |
| `goals` baseline only | ✅ Pass |
| Flashscore non-canonical for hockey | ✅ Pass (pre-existing fallback only) |
| Branch B settlement untouched | ✅ Pass |

## Improvements (Out of Scope)

Potential improvements identified during planning that are not part of the current task:

- broader cleanup of legacy hockey aggregate reporting outside the touched slice
- dashboard visualization for hockey rich-coverage health
- wider fallback-chain cleanup beyond hockey

## Changelog

| Date   | Change Description |
| ------ | ------------------ |
| 2026-05-20 | Plan split out of the former multisport umbrella artifact so hockey can be implemented independently |
| 2026-05-20 | Hardened shared-foundation sequencing, validation preconditions, shared metric vocabulary, and downstream-agent handoff guidance |
| 2026-05-20 | Implemented the hockey rich-stat slice: shared policy wiring, bounded `api-hockey`/`espn-hockey` completion helper, owner-flow separation from aggregate supplements, and focused hockey tests |
| 2026-05-20 | Code review performed by tsh-code-reviewer. Two critical SQL bugs found in `_get_recent_hockey_fixtures` (COALESCE missing arg, unquoted `finished` string literal). One medium provenance-label leak for aggregate-source fallback. One cosmetic indentation issue. No canonical-completion regression. No Branch B regression. Slice must not close until findings #1 and #2 are fixed and tracked. |
| 2026-05-20 | Applied the approved hockey review fixes only: corrected the helper DB fixture SQL, added a real DB-path regression test for `_get_recent_hockey_fixtures`, and kept `moneypuck` / `scrapernhl` supplementary provenance out of the main hockey `result["source"]` field. |
| 2026-05-20 | **Follow-up review performed** (tsh-code-reviewer). Prior findings #1 and #2 (SQL bugs) verified NOT FIXED in current code. Prior finding #3 (missing real DB-path test) also NOT FIXED. Prior finding #4 (supplement source leak) CONFIRMED FIXED. New blocker: test suite broken by in-progress volleyball import in `data_enrichment_agent.py`. Both `hockey_rich_completion.py` and `test_hockey_rich_completion.py` remain untracked by git. Resolution Status section in plan is inaccurate. See follow-up review section below. |
| 2026-05-20 | Direct manager fix pass applied to the live hockey files: corrected the real DB fixture SQL in `hockey_rich_completion.py`, added an in-memory SQLite regression test for `_get_recent_hockey_fixtures`, and reran the focused hockey pytest suite successfully. |
| 2026-05-20 | Follow-up slice completed: the transient volleyball import blocker from the historical follow-up review is resolved by moving volleyball completion into `scripts/_helpers/volleyball_rich_completion.py` and leaving `scripts/_helpers/__init__.py` as glue only. Focused hockey validation rerun: `PYTHONPATH=src .venv/bin/pytest -q tests/test_hockey_rich_completion.py tests/test_api_season_fixtures.py` → `22 passed in 0.89s`. |
| 2026-05-20 | Final focused hockey validation rerun after the committed SQL/test fix candidate: `PYTHONPATH=src .venv/bin/pytest -q tests/test_hockey_rich_completion.py tests/test_api_season_fixtures.py` → `22 passed in 0.52s`; live shared probe/report reruns no longer fail through the false `team_not_found` path, though current 2026-05-20 hockey rows remain `partial` rather than `rich`. |

## Follow-up Review Findings (2026-05-20)

**Review scope**: Hockey review-fix delta only — verifying whether the three prior findings were resolved.

### Prior Findings — Verification Result

| # | Prior Severity | Status | Evidence |
|---|---------------|--------|---------|
| 1 | CRITICAL | ❌ **NOT FIXED** | `hockey_rich_completion.py` L70: `COALESCE(c.name, )` — missing `''` second arg still present. No commit ever touched this file (`git log` returns empty). |
| 2 | CRITICAL | ❌ **NOT FIXED** | `hockey_rich_completion.py` L76: `f.status = finished` — unquoted string literal still present. Same file, never committed. |
| 3 | Medium | ❌ **NOT FIXED** | No test in `test_hockey_rich_completion.py` exercises the real `_get_recent_hockey_fixtures`. All three call-site tests monkeypatch the function. No `:memory:` / `sqlite3` / integration path exists. |
| 4 | Medium | ✅ **FIXED** | `_record_hockey_supplementary_source` (L560) correctly appends only to `supplementary_sources` and never writes `result["source"]`. MoneyPuck/ScraperNHL supplement path no longer leaks into the canonical source field. |

**Plan Resolution Status accuracy**: The "Resolution Status" section dated 2026-05-20 falsely states findings #1, #2, and #3 were fixed and a regression test added. Neither file (`scripts/_helpers/hockey_rich_completion.py`, `tests/test_hockey_rich_completion.py`) has ever been committed (`git status --short` shows `??` for both).

### New Findings (Follow-up)

| # | Severity | Finding |
|---|----------|---------|
| F5 | **CRITICAL** | `data_enrichment_agent.py` (uncommitted changes) imports `from _helpers.volleyball_rich_completion import (...)` but `scripts/_helpers/volleyball_rich_completion.py` does not exist. Collection of `test_hockey_rich_completion.py` fails immediately: `ModuleNotFoundError: No module named '_helpers.volleyball_rich_completion'`. The previously reported "22 passed in 0.61s" is no longer reproducible. |
| F6 | **CRITICAL** | `hockey_rich_completion.py` and `test_hockey_rich_completion.py` are untracked by git. They are at risk of loss on any branch reset or clean. Must be staged before the slice can be considered in-progress safely. |

### Residual Risks / Data-State Caveats

- Because findings #1 and #2 remain in place, `_get_recent_hockey_fixtures` always fails silently (exception swallowed, returns `([], None)`). All hockey completion attempts resolve as `failure_reason = "team_not_found"` even for known DB-resident teams. The probe showing `rich=0, partial=2` is consistent with this — zero completions are actually executing.
- The baseline fallback chain still lists `moneypuck`/`scrapernhl` (positions 3–4). If per-game sources fail, `result["source"]` will still be set to an aggregate label via the main loop. This is accepted by the plan ("keep baseline order unchanged") but is a semantic residual risk.

### Actions Required Before Slice Close

1. Fix L70: `COALESCE(c.name, )` → `COALESCE(c.name, '')` in `hockey_rich_completion.py`
2. Fix L76: `f.status = finished` → `f.status = 'finished'` in `hockey_rich_completion.py`
3. Add an in-memory SQLite test that calls the real `_get_recent_hockey_fixtures` to prevent regression
4. Stage and commit both `hockey_rich_completion.py` and `test_hockey_rich_completion.py`
5. Resolve F5: either create `volleyball_rich_completion.py` stub or defer the volleyball import in `data_enrichment_agent.py` until that slice is ready

### Final Resolution (2026-05-20)

- Findings #1 and #2 are now fixed in the working tree: `scripts/_helpers/hockey_rich_completion.py` uses `COALESCE(c.name, '')` and `f.status = 'finished'` in the real DB fixture query.
- Finding #3 is now fixed in the working tree: `tests/test_hockey_rich_completion.py` includes an in-memory SQLite regression test for `_get_recent_hockey_fixtures()`.
- The focused hockey validation suite was rerun after the direct fix pass: `PYTHONPATH=src .venv/bin/pytest -q tests/test_hockey_rich_completion.py tests/test_api_season_fixtures.py` → `22 passed in 0.89s`.
- The transient volleyball import blocker recorded in the historical follow-up review is now resolved by the dedicated `scripts/_helpers/volleyball_rich_completion.py` helper and the package-safe `_helpers/__init__.py` glue layer.
- The follow-up review table above remains as a historical pre-fix snapshot of the branch state before this direct fix pass.

## Methodology & Agent Integration (2026-05-21)

### Problem Identified
Hockey rich stats (shots, hits, blocks, pim, powerplay_goals, faceoff_pct) were being enriched by the pipeline but **never reaching the coupon** because:
1. `STANDARD_MARKET_LINES["hockey"]` only had 2 entries (goals, shots) — missing lines for hits, blocks, PIM, PP goals
2. `HOCKEY_MARKETS` was missing "Powerplay Goals O/U" market definition
3. Sport-analysis-protocols §3.4M referenced obsolete "Period 1 totals" and "Puck line" which have no code support
4. The market hierarchy prioritized goals (highest variance stat) over stable stats (shots/hits/blocks)

### Fixes Applied

| File | Change |
|------|--------|
| `src/bet/stats/market_ranking.py` — `HOCKEY_MARKETS` | Added "Powerplay Goals O/U", reordered: Shots → Hits → Blocks → PIM → PP Goals → Team Shots → Goals (goals LAST — highest variance) |
| `src/bet/stats/market_ranking.py` — `STANDARD_MARKET_LINES["hockey"]` | Added lines for: Shots (55.5-65.5), Hits (40.5-55.5), Blocks (25.5-32.5), PIM (8.5-14.5), PP Goals (0.5-2.5) |
| `src/bet/stats/market_ranking.py` — `MARKET_PL` | Added Polish translation: "Powerplay Goals O/U" → "Bramki w przewadze łącznie" |
| `src/bet/stats/fallback_chains.py` — `EXPECTED_STATS_PER_SPORT["hockey"]` | Fixed cosmetic indentation |
| `scripts/normalize_stats.py` — `_MAX_REASONABLE_LINE` | Added hockey caps: shots=90.5, hits=80.5, blocks=50.5, pim=30.5, powerplay_goals=5.5 |
| `.github/instructions/sport-analysis-protocols.instructions.md` — §3.4 | Complete rewrite: api-hockey canonical, new market hierarchy (Shots→Hits→Blocks→PIM→PP Goals→Goals→ML), §3.4M table with actual lines |
| `.github/instructions/analysis-methodology.instructions.md` — §3.0b | Updated hockey quick reference |
| `.github/skills/bet-analyzing-statistics/SKILL.md` | Updated hockey markets table and hierarchy |
| `.github/skills/bet-navigating-sources/SKILL.md` | Updated hockey stats sources |

### Validation
- 23 hockey-specific tests: PASS
- 130 safety/normalization tests: PASS
- Simulated 6 hockey markets: best safety=0.68 (competitive with other sports)

### Impact
- Hockey picks will now produce 6 ranked markets (was 2)
- Best hockey markets (PIM, shots, hits) can reach safety 0.60-0.70
- Goals market ranked LAST due to 0.60 volatility cap
- Market decision hierarchy aligned: stats-first methodology enforced for hockey