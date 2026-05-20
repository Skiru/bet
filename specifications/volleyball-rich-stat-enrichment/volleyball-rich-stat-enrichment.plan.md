# volleyball-rich-stat-enrichment - Implementation Plan

## Task Details

| Field            | Value |
| ---------------- | ----- |
| Jira ID          | N/A |
| Title            | Volleyball rich-stat enrichment |
| Description      | Extend the shared rich-stat enrichment architecture already proven by the existing football implementation to volleyball while preserving the stable `match_stats -> team_form` contract, keeping ownership in enrichment flows instead of `run_scrapers.py`, and aligning the current mixed provider policy around canonical provider-backed per-match completion rather than legacy Flashscore or Volleybox assumptions. |
| Priority         | High |
| Related Research | `specifications/multisport-rich-stat-enrichment/multisport-rich-stat-enrichment.plan.md`, `specifications/flashscore-match-stats-token/flashscore-match-stats-token.plan.md`, `memories/repo/pipeline-knowledge-base.md` |

## Proposed Solution

Implement volleyball rich completion around `api-volleyball`, not around historical Flashscore or Volleybox assumptions.

The implementation should keep the same shared architecture used by the existing football implementation:

- `scripts/data_enrichment_agent.py` remains the enrichment owner
- source-specific logic lives in a bounded helper under `scripts/_helpers/`
- `fetch_api_stats._store_in_cache()` remains the write boundary into `match_stats` and `team_form`
- generic probe and reporting surfaces should extend the basketball-owned shared foundation; if that foundation is missing in the working branch, escalate sequencing or obtain explicit manager reassignment instead of creating a volleyball-only fork

Volleyball-specific source policy:

- canonical per-match rich completion: `api-volleyball`
- bounded supporting source in this slice: `espn-volleyball` only when it returns clean per-match normalized stats
- `espn-volleyball` is registry-scoped to FIVB Men's fixtures (`CLIENT_REGISTRY["espn-volleyball"] = _espn_factory("volleyball", "fivb.m")`), so empty results outside that scope should be treated as unsupported-league skips rather than degraded-source failures
- excluded from `supporting_sources` in this slice: the generic `sofascore` client remains out until a volleyball-specific normalized match-stat contract is proven explicitly in a follow-up slice
- aggregate-only / advisory surfaces: Volleybox team-page aggregates and any non-match-level stat pages

This plan must resolve the current policy drift where comments and legacy helpers still imply Flashscore or Volleybox-centric behavior even though provider-backed `fetch_match_stats()` already exists.

When delegating implementation, use this child plan as the primary execution artifact and pass the multisport plan only as shared-guardrail context.
This plan is independently usable for volleyball-specific logic, but it does not authorize a second shared probe / registry / report implementation path.
If the basketball-owned shared foundation is absent, record the blocker in this plan's Changelog and halt the slice; do not create `scripts/rich_stats_probe.py`, the shared completion registry, or the generic `rich-coverage` report path from scratch unless the manager explicitly reassigns that ownership.

**Branch B settlement remains out of scope and unchanged.** This plan does not modify `scripts/settle_on_finish.py` or the DB-backed settlement policy.

**Live validation commands**:

- `PYTHONPATH=src .venv/bin/python scripts/rich_stats_probe.py --date YYYY-MM-DD --sport volleyball --limit 10 --verbose`
- `PYTHONPATH=src .venv/bin/python scripts/db_report.py --report rich-coverage --sport volleyball --date YYYY-MM-DD`
- `PYTHONPATH=src .venv/bin/pytest -q tests/test_flashscore_token_policy.py tests/test_api_season_fixtures.py tests/test_volleyball_rich_completion.py`

These are post-implementation validation commands, not preflight checks against the current branch state.
They assume the basketball-owned shared foundation (`scripts/rich_stats_probe.py`, the shared completion registry, and the generic `rich-coverage` report path) is already present in the working branch or has been explicitly reassigned by the manager in the same slice. `tests/test_volleyball_rich_completion.py` must exist before the final pytest run.

Use shared report-bucket vocabulary consistently: `rich`, `baseline_only`, `partial`, `no_data`.
For volleyball, `baseline_only` means usable match-level coverage exists in `match_stats` / `team_form`, but the required volleyball rich keys are still missing. Keep AGENT_SUMMARY owner metrics separate: `eligible`, `completed`, `still_missing`.

## Current Implementation Analysis

### Already Implemented

List of existing components, functions, utilities that will be reused (with file paths):

- `scripts/data_enrichment_agent.py` - canonical enrichment owner and current source-health / AGENT_SUMMARY surface
- `scripts/fetch_api_stats.py::_store_in_cache()` - established writer into `match_stats` and derived `team_form`
- `src/bet/stats/fallback_chains.py` - current fallback-chain source of truth; already lists volleyball providers and expected stat keys
- `src/bet/api_clients/api_volleyball.py` - existing provider-backed per-match stats client
- `src/bet/api_clients/volleyball_data.py` - existing secondary volleyball client; `fetch_match_stats()` already prefers provider-backed match-level stats, while `fetch_team_stats()` still scrapes aggregate Volleybox team pages
- `src/bet/api_clients/__init__.py` - canonical client registry exposing volleyball and ESPN clients
- `tests/test_flashscore_token_policy.py` - existing source-policy regression surface already covering volleyball Flashscore assumptions
- `tests/test_api_season_fixtures.py` - current focused fixture/provider tests that include volleyball coverage

### To Be Modified

List of existing code that needs changes or extensions (with file paths and description of changes):

- `scripts/data_enrichment_agent.py` - add volleyball rich-completion routing and summary metrics
- `scripts/fetch_api_stats.py` - reuse or expose the minimal writer seams required by a volleyball helper
- `src/bet/stats/fallback_chains.py` - encode explicit completion semantics in `RICH_COMPLETION_POLICY`, keep baseline `FALLBACK_CHAINS` order unchanged for non-rich scenarios, and normalize required volleyball rich keys
- `src/bet/api_clients/api_volleyball.py` - extend `STAT_TYPE_MAP` for `kills`, `digs`, and `assists` if the provider exposes them, and normalize `attack_pct` to the canonical `hitting_pct` key at the client boundary; if the provider does not expose one of these stats, revise `required_rich_keys` before the adapter is built
- `src/bet/api_clients/volleyball_data.py` - align class-level comments and fallback messaging with the actual canonical source policy
- `scripts/db_report.py` - extend the basketball-owned generic `rich-coverage` report to accept `--sport volleyball`; reuse the shared `--sport` CLI argument and `rich-coverage` argparse choice rather than adding a separate volleyball-named report path

### To Be Created

List of new components, functions, utilities that need to be built from scratch:

- volleyball-specific extensions to the basketball-owned shared completion registry / probe / report surfaces
- do not create `scripts/rich_stats_probe.py`, the shared completion registry, or the generic `rich-coverage` report path from scratch; if they are absent, record the blocker in this plan's Changelog and halt until basketball Task 1.1 is confirmed complete in the working branch or the manager explicitly reassigns ownership
- `scripts/_helpers/volleyball_rich_completion.py` - bounded volleyball adapter for provider-backed per-match completion
- `tests/test_volleyball_rich_completion.py` - focused adapter, key-normalization, routing, and no-write probe tests

## Open Questions

| #   | Question | Answer | Status |
| --- | -------- | ------ | ------ |
| 1   | Should volleyball completion move into `scripts/run_scrapers.py` because scrapers already operate by sport? | No. Rich completion still belongs to enrichment-owner flows that populate `team_form`. | ✅ Resolved |
| 2   | Should ESPN remain the canonical volleyball completion source because it is first in the current fallback chain? | No. The plan keeps `api-volleyball` as canonical completion and treats ESPN as bounded support only. | ✅ Resolved |
| 3   | Can Volleybox aggregate team-page stats satisfy rich completion by themselves? | No. Aggregate-only surfaces may inform analysis, but they cannot satisfy canonical `match_stats` richness. | ✅ Resolved |
| 4   | Does this work reopen Branch B settlement? | No. Settlement remains untouched. | ✅ Resolved |

## Technical Context

Project conventions, coding standards, and patterns discovered during planning. Downstream agents MUST read this section instead of re-discovering the same context.

### Project Instructions

- `.github/copilot-instructions.md` - DB-first, data-flow verification required, keep changes narrow and root-cause focused
- workspace memory - fish shell only for command examples; avoid inline Python or shell loops
- `memories/repo/pipeline-knowledge-base.md` - Branch B settlement is final and stays isolated from this work

### Architecture & Patterns

- `scripts/data_enrichment_agent.py` remains the owner; `scripts/run_scrapers.py` is not the enrichment completion surface
- `_store_in_cache()` remains the only intended persistence bridge for new rich completion
- `NormalizedMatchStats` is defined in `src/bet/models/normalized.py` (exported via `src/bet/models/__init__.py`) and is the required payload passed to `_store_in_cache()`: `fixture_id`, `source`, `sport`, `home_team`, `away_team`, `date`, and `stats` with per-stat `home` / `away` sub-keys
- `src/bet/api_clients/volleyball_data.py` currently mixes aggregate Volleybox scraping with provider-backed match-stat lookup; this plan should separate those semantics rather than blur them
- `src/bet/stats/fallback_chains.py` currently lists `espn-volleyball` before `api-volleyball`; leave that baseline ordering unchanged and express canonical rich completion in `RICH_COMPLETION_POLICY` instead of changing non-rich fallback behavior

### Tech Stack

- Python `>=3.11`
- SQLite DB at `betting/data/betting.db`
- runtime libraries already used in this area: `curl_cffi`, `requests`, `sqlalchemy`, `pydantic`
- tests run with `pytest`

### Code Style & Standards

- Keep source-specific parsing in helper modules under `scripts/_helpers/`
- Preserve explicit source provenance such as `api-volleyball`, `espn-volleyball`, and any advisory aggregate source labels
- Do not reintroduce Flashscore as a canonical volleyball match-stat path
- Keep stat-key normalization explicit instead of hiding it in implicit aliases

### Testing Patterns

- Use narrow pytest modules with mocked provider payloads
- Mirror the football validation shape: adapter/persistence test, owner-routing test, and no-write probe/report test
- Keep commands fish-safe and date-scoped

### Database Patterns

- `match_stats` remains the canonical per-fixture truth table
- `team_form` remains the denormalized downstream analytics surface
- New volleyball completion code should not create an alternate write path outside `_store_in_cache()`

### Additional Context

- `src/bet/api_clients/volleyball_data.py` still contains a class docstring and helper naming that overstate Flashscore / Volleybox centrality even though `fetch_match_stats()` already tries provider-backed clients first
- Volleyball key naming is currently at risk of drift between `attack_pct` and `hitting_pct`; `hitting_pct` is the canonical persisted key, and any incoming `attack_pct` must be normalized to `hitting_pct` before persistence
- The generic `sofascore` client key already exists in `src/bet/api_clients/__init__.py`, but it is not part of `FALLBACK_CHAINS["volleyball"]`; this plan excludes it from `supporting_sources` until a volleyball-specific normalized match-stat contract is proven in a separate slice rather than inventing a new client key or silently adding it to baseline fallback behavior
- **Branch B settlement remains out of scope and unchanged throughout this plan**

## Implementation Plan

### Phase 1: Shared Completion Foundation for Volleyball

#### Task 1.1 - [MODIFY] Extend shared completion registry and generic reporting for volleyball

**Description**: Extend the shared completion policy, no-write probe, and generic rich-coverage report for volleyball. If the basketball-owned shared foundation is missing in the working branch, record the blocker in this plan's Changelog and halt the slice rather than creating a volleyball-only duplicate.

**Definition of Done**:

- [ ] Volleyball declares `required_rich_keys`, `canonical_source`, `supporting_sources`, and `aggregate_only_sources` in `src/bet/stats/fallback_chains.py::RICH_COMPLETION_POLICY`
- [ ] Volleyball candidate rich-key set for provider verification is `kills`, `aces`, `blocks`, `digs`, `assists`, `hitting_pct`, and `points`
- [ ] Task 1.1 is not complete until `RICH_COMPLETION_POLICY["volleyball"]["required_rich_keys"]` is finalized to the exact provider-confirmed subset after `api_volleyball.py` verification of `kills`, `digs`, and `assists`; do not ship an aspirational list
- [ ] If `kills`, `digs`, or `assists` are not exposed by the provider, the minimum viable fallback `required_rich_keys` for this slice is `aces`, `blocks`, `hitting_pct`, and `points`; unsupported candidate keys are downgraded to supplementary-only and recorded in the Changelog
- [ ] Volleyball `supporting_sources` are exactly `espn-volleyball` for this slice
- [ ] Volleyball `aggregate_only_sources` are exactly `volleybox`
- [ ] The shared `scripts/rich_stats_probe.py` supports `--sport volleyball` and reports source choice, fixture coverage, key completeness, and failure reasons
- [ ] `scripts/db_report.py` supports `--report rich-coverage --sport volleyball --date <date>`
- [ ] The shared contract still persists only through `_store_in_cache()`

#### Task 1.2 - [CREATE] Build the bounded volleyball completion adapter

**Description**: Add a volleyball helper under `scripts/_helpers/` that fetches recent finished matches from canonical provider-backed sources, normalizes rich stats, and persists only through the established writer contract.

**Definition of Done**:

- [ ] `api-volleyball` is the canonical completion source
- [ ] `espn-volleyball` is the only supporting source in this slice, and it is used only through per-match normalized stats
- [ ] Empty `espn-volleyball` responses for non-FIVB-Men's fixtures are treated as unsupported-league skips, not degraded-source failures
- [ ] Volleybox aggregate team-page data cannot satisfy completion success
- [ ] The adapter returns the base 7-key contract used by the shared enrichment flow: `status` (`str`), `fixtures_scanned` (`int`), `matches_persisted` (`int`), `rich_keys_found` (`list[str]`), `missing_rich_keys` (`list[str]`), `error` (`str | None`), and `failure_reason` (`str | None`)

### Phase 2: Policy Alignment, Owner Wiring, and Tests

#### Task 2.1 - [MODIFY] Align `volleyball_data.py` and owner routing with the canonical source policy

**Description**: Update owner flow and legacy helper messaging so code, comments, and tests all reflect the same volleyball source policy.

**Definition of Done**:

- [ ] `scripts/data_enrichment_agent.py` can trigger the volleyball completion helper after baseline enrichment remains partial
- [ ] AGENT_SUMMARY reports volleyball `eligible`, `completed`, and `still_missing` counts
- [ ] `src/bet/api_clients/volleyball_data.py` no longer presents Flashscore or Volleybox as the canonical rich-match solution
- [ ] Remove the unused `FLASHSCORE_SPORT_ID = 12` constant and update the `VolleyballDataClient` class docstring so it no longer describes the client as "using Flashscore + volleybox.net"
- [ ] Key normalization for `attack_pct` / `hitting_pct` is explicit and test-covered in `src/bet/api_clients/api_volleyball.py::STAT_TYPE_MAP`, with `hitting_pct` as the canonical persisted key and any incoming `attack_pct` normalized before persistence
- [ ] No ownership is moved into `scripts/run_scrapers.py`

#### Task 2.2 - [CREATE] Add focused volleyball adapter, normalization, and probe tests

**Description**: Lock down the volleyball slice with narrow tests around completion semantics and source policy.

**Definition of Done**:

- [ ] Tests cover adapter persistence through `_store_in_cache()`
- [ ] Tests cover owner routing from `scripts/data_enrichment_agent.py`
- [ ] Tests cover `attack_pct` / `hitting_pct` normalization and no-write probe behavior
- [ ] Existing source-policy tests remain passing

### Phase 3: Live Validation and Review

#### Task 3.1 - [REUSE] Run the sport-specific live validation commands

**Description**: Validate volleyball rollout with the planned probe, report, and narrow test commands only.

**Definition of Done**:

- [ ] `scripts/rich_stats_probe.py --sport volleyball` runs with no unintended DB/cache mutations
- [ ] `scripts/db_report.py --report rich-coverage --sport volleyball --date <date>` distinguishes `rich`, `baseline_only`, `partial`, and `no_data`
- [ ] The volleyball-focused pytest command passes

#### Task 3.2 - [REUSE] Final code review by `tsh-code-reviewer`

**Description**: After focused executable validation passes, run the final review to verify source-policy discipline and contract preservation.

**Definition of Done**:

- [ ] Review is run after the focused validation suite
- [ ] Findings are fixed or explicitly tracked in the Changelog
- [ ] Review confirms no Branch B settlement regressions and no Flashscore policy backsliding
- [ ] The slice is not closed while review findings remain unresolved and untracked

## Security Considerations

- Keep provider calls bounded to recent finished fixtures and date-scoped probes
- Do not expand Flashscore or Volleybox beyond bounded supporting/advisory use
- Preserve explicit source provenance and missing-key reporting for degraded provider behavior
- Keep settlement logic untouched while implementing volleyball enrichment

## Quality Assurance

Acceptance criteria checklist to verify the implementation meets the defined requirements:

- [ ] Volleyball completion remains owned by enrichment flows, not `scripts/run_scrapers.py`
- [ ] `api-volleyball` is the canonical completion source in code and reporting
- [ ] Aggregate-only Volleybox data cannot satisfy canonical rich completion by itself
- [ ] A generic `rich-coverage` report exists and works for volleyball
- [ ] Volleyball adapter, normalization, routing, and probe tests pass
- [ ] **Branch B settlement remains out of scope and unchanged**

## Improvements (Out of Scope)

Potential improvements identified during planning that are not part of the current task:

- broader cleanup of legacy volleyball helper comments and naming outside the touched slice
- dashboard visualization for volleyball rich-coverage health
- wider cleanup of fallback-chain ordering beyond volleyball

## Changelog

| Date   | Change Description |
| ------ | ------------------ |
| 2026-05-20 | Plan split out of the former multisport umbrella artifact so volleyball can be implemented independently |
| 2026-05-20 | Hardened shared-foundation sequencing, validation preconditions, shared metric vocabulary, and downstream-agent handoff guidance |