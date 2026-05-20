# basketball-rich-stat-enrichment - Implementation Plan

## Task Details

| Field            | Value |
| ---------------- | ----- |
| Jira ID          | N/A |
| Title            | Basketball rich-stat enrichment |
| Description      | Extend the shared rich-stat enrichment pattern already proven by the existing football implementation to basketball while keeping ownership in enrichment flows, preserving the stable `match_stats -> team_form` contract, routing all persistence through `fetch_api_stats._store_in_cache()`, and using provider-backed per-game completion instead of any Flashscore HTML carryover. |
| Priority         | High |
| Related Research | `specifications/multisport-rich-stat-enrichment/multisport-rich-stat-enrichment.plan.md`, `specifications/flashscore-match-stats-token/flashscore-match-stats-token.plan.md`, `memories/repo/pipeline-knowledge-base.md` |

## Proposed Solution

Implement basketball as a provider-backed rich-completion slice, not as a copy of football's Flashscore HTML path.

The implementation should keep the already-proven architecture:

- `scripts/data_enrichment_agent.py` remains the owning enrichment flow
- source-specific logic stays behind a bounded helper under `scripts/_helpers/`
- persistence still hands normalized per-match data to `fetch_api_stats._store_in_cache()`
- downstream consumers continue to read the stable `match_stats -> team_form` contract

Basketball-specific source policy:

- canonical per-match rich completion: `api-basketball`
- supporting sources: `nba-api` for NBA-only coverage, `espn-basketball` where it returns usable per-game stats
- `espn-basketball` is registry-scoped to NBA fixtures (`CLIENT_REGISTRY["espn-basketball"] = _espn_factory("basketball", "nba")`), so empty results outside NBA should be treated as unsupported-league skips rather than degraded-source failures
- non-canonical by default: Flashscore HTML and other shallow surfaces

If shared registry/probe/report surfaces from the umbrella plan are not present yet, introduce the minimal fully generic versions in the same change set: sport-agnostic in interface, reusable by volleyball, hockey, and tennis without redesign, and explicitly not basketball-scoped shared surfaces.

This is the required first non-football rollout. Basketball owns the first implementation of the shared completion surfaces so later sport slices can extend them instead of creating duplicates.

Shared completion policy shape for the first rollout:

```python
RICH_COMPLETION_POLICY = {
	"basketball": {
		"required_rich_keys": [
			"rebounds", "assists", "steals", "blocks", "turnovers",
			"fouls", "fg_pct", "three_pct", "ft_pct",
			"points_in_paint", "fast_break_points",
		],
		"canonical_source": "api-basketball",
		"supporting_sources": ["nba-api", "espn-basketball"],
		"aggregate_only_sources": [],
	},
}
```

Store this shared policy in `src/bet/stats/fallback_chains.py` beside `FALLBACK_CHAINS` and `EXPECTED_STATS_PER_SPORT`. Only the `basketball` key should be committed in this slice; later sport plans add their own key to the existing dict rather than pre-seeding placeholder entries or inventing a second schema/module.

When delegating implementation, use this child plan as the primary execution artifact and pass the multisport plan only as shared-guardrail context.
Basketball is the only child plan authorized to introduce the first shared registry / probe / generic report surfaces; later sport plans extend them rather than recreate them.

**Branch B settlement remains out of scope and unchanged.** This plan does not reopen `scripts/settle_on_finish.py` or the finalized DB-backed settlement policy.

**Live validation commands**:

- `PYTHONPATH=src .venv/bin/python scripts/rich_stats_probe.py --date YYYY-MM-DD --sport basketball --limit 10 --verbose`
- `PYTHONPATH=src .venv/bin/python scripts/db_report.py --report rich-coverage --sport basketball --date YYYY-MM-DD`
- `PYTHONPATH=src .venv/bin/pytest -q tests/test_api_basketball.py tests/test_api_season_fixtures.py tests/test_basketball_rich_completion.py`

These are post-implementation validation commands, not preflight checks against the current branch state.
This basketball slice is expected to create `scripts/rich_stats_probe.py`, the generic `rich-coverage` path in `scripts/db_report.py`, and `tests/test_basketball_rich_completion.py` before the full validation command is expected to pass.

Use shared report-bucket vocabulary consistently: `rich`, `baseline_only`, `partial`, `no_data`.
For basketball, `baseline_only` means usable match-level coverage exists in `match_stats` / `team_form`, but the required basketball rich keys are still missing. Keep AGENT_SUMMARY owner metrics separate: `eligible`, `completed`, `still_missing`.

## Current Implementation Analysis

### Already Implemented

List of existing components, functions, utilities that will be reused (with file paths):

- `scripts/data_enrichment_agent.py` - canonical enrichment owner and current source-health / AGENT_SUMMARY surface
- `scripts/fetch_api_stats.py::_store_in_cache()` - established writer into `match_stats` and derived `team_form`
- `src/bet/stats/fallback_chains.py` - single fallback-chain module already listing basketball providers and expected stat keys
- `src/bet/api_clients/api_basketball.py` - existing per-game client already maps `points`, `rebounds`, `assists`, `steals`, `blocks`, `turnovers`, `fg_pct`, `three_pct`, `ft_pct`, and extra keys such as `offensive_rebounds`, `defensive_rebounds`, `points_in_paint`, `fast_break_points`, and `fouls`
- `src/bet/api_clients/nba_api_client.py` - NBA-only support client already available in the registry
- `src/bet/api_clients/__init__.py` - canonical client registry exposing `api-basketball`, `nba-api`, and ESPN clients
- `scripts/inspect_pipeline.py` - existing coarse S2 enrichment visibility that should remain compatible with richer reporting
- `tests/test_api_basketball.py` and `tests/test_api_season_fixtures.py` - focused current tests around basketball provider behavior
- `scripts/_helpers/football_flashscore_html_enrichment.py` - existing football helper that demonstrates the bounded helper boundary, owner routing, and `_store_in_cache()` persistence discipline these sport plans should preserve

### To Be Modified

List of existing code that needs changes or extensions (with file paths and description of changes):

- `scripts/data_enrichment_agent.py` - add basketball rich-completion routing and per-sport completion metrics without disturbing current football fields
- `scripts/fetch_api_stats.py` - expose or reuse the minimal seams needed for a basketball completion helper while keeping `_store_in_cache()` as the only persistence bridge
- `src/bet/stats/fallback_chains.py` - add explicit completion semantics for basketball in `RICH_COMPLETION_POLICY` while leaving baseline `FALLBACK_CHAINS` order unchanged for non-rich scenarios
- `scripts/db_report.py` - extend the current football-only richness reporting to a generic `rich-coverage` report usable for basketball, add a `--sport` CLI argument, extend argparse `choices=` to include `rich-coverage`, and keep `football-rich-coverage` as a backward-compatible alias until callers migrate
- `scripts/inspect_pipeline.py` - keep the coarse S2 report aligned with any new rich-coverage reporting fields

### To Be Created

List of new components, functions, utilities that need to be built from scratch:

- `scripts/rich_stats_probe.py` - shared generic no-write probe created in this first rollout and reused by all later sport slices
- shared completion registry / probe / report surfaces required by the first rollout, including the generic `rich-coverage` report path
- `scripts/_helpers/basketball_rich_completion.py` - bounded basketball adapter that fetches recent finished fixtures, normalizes rich stats, and persists only through `_store_in_cache()`
- `tests/test_basketball_rich_completion.py` - focused adapter, routing, and no-write probe tests

## Open Questions

| #   | Question | Answer | Status |
| --- | -------- | ------ | ------ |
| 1   | Should basketball rich completion move into `scripts/run_scrapers.py` because that file already orchestrates sport scrapers? | No. `run_scrapers.py` owns scraper outputs such as `league_profiles` and player-stat artifacts, not `team_form` enrichment completion. | ✅ Resolved |
| 2   | Should basketball copy the football Flashscore HTML pattern because it is already proven for football enrichment? | No. Reuse the helper boundary and writer contract, not the football source choice. Basketball should stay provider-backed. | ✅ Resolved |
| 3   | Can `nba-api` be treated as universal basketball completion coverage? | No. It is useful support for NBA fixtures only and cannot define universal basketball coverage semantics. | ✅ Resolved |
| 4   | Does this plan change Branch B settlement behavior? | No. Settlement remains DB-backed and unchanged. | ✅ Resolved |

## Technical Context

Project conventions, coding standards, and patterns discovered during planning. Downstream agents MUST read this section instead of re-discovering the same context.

### Project Instructions

- `.github/copilot-instructions.md` - DB-first, root-cause-oriented, narrow changes only; verify producer/consumer data flow before changing pipeline steps
- workspace memory - fish shell only for terminal commands; do not rely on inline Python or shell loops in validation instructions
- `memories/repo/pipeline-knowledge-base.md` - Branch B settlement is final; Flashscore HTML remains available only for shared enrichment/search/results-page use cases, not as a generic deep-source policy

### Architecture & Patterns

- The repository is a Python monorepo with reusable code under `src/bet/` and owner/orchestration scripts under `scripts/`
- `scripts/data_enrichment_agent.py` is the owning enrichment path; do not move basketball completion into `scripts/run_scrapers.py`
- `_store_in_cache()` is the write boundary; new basketball completion logic should hand it `NormalizedMatchStats` rather than invent another DB writer
- `NormalizedMatchStats` is defined in `src/bet/models/normalized.py` (exported via `src/bet/models/__init__.py`) and is the required payload passed to `_store_in_cache()`: `fixture_id`, `source`, `sport`, `home_team`, `away_team`, `date`, and `stats` with per-stat `home` / `away` sub-keys
- `src/bet/stats/fallback_chains.py` is already the fallback-chain source of truth, but basketball rich completion should be defined in `RICH_COMPLETION_POLICY` rather than by reordering baseline `FALLBACK_CHAINS`; the current ESPN / NBA-first ordering remains the baseline fallback path for non-rich scenarios
- `scripts/db_report.py` currently exposes only `football-rich-coverage`; basketball rollout requires a generic report rather than another football-specific copy

### Tech Stack

- Python `>=3.11`
- SQLite DB at `betting/data/betting.db`
- runtime dependencies already used in this slice: `requests`, `curl_cffi`, `sqlalchemy`, `pydantic`, `rapidfuzz`
- tests run with `pytest`

### Code Style & Standards

- Keep the implementation local to enrichment-owner paths and helper modules under `scripts/_helpers/`
- Preserve accurate source provenance such as `api-basketball`, `nba-api`, and `espn-basketball`
- Do not introduce Flashscore as a canonical basketball completion source
- Reuse the touched area's existing import patterns; do not widen unrelated refactors

### Testing Patterns

- Prefer narrow `pytest` modules with mocks over wide end-to-end runs
- Mirror the football testing pattern: helper/adapter test, owner-routing test, and no-write probe / report coverage
- `tests/test_flashscore_token_policy.py` is intentionally not part of the basketball validation command because its current assertions are football/volleyball-specific; basketball source-policy regressions should be covered in `tests/test_basketball_rich_completion.py`
- Keep validation commands fish-safe and date-scoped

### Database Patterns

- Use `from bet.db.connection import get_db` and repository-backed writes where new DB access is required
- Preserve the stable `match_stats -> team_form` flow; `match_stats` remains the canonical per-fixture store and `team_form` remains the denormalized analytics layer
- No settlement DB contract changes are part of this plan

### Additional Context

- `src/bet/api_clients/api_basketball.py` already exposes the stat families needed for basketball richness; the missing work is owner routing, reporting, and explicit completion semantics
- `scripts/db_report.py` is still football-only for rich coverage, so basketball needs generic richness reporting rather than another isolated report name
- **Branch B settlement remains out of scope and unchanged throughout this plan**

## Implementation Plan

### Phase 1: Shared Completion Foundation for Basketball

#### Task 1.1 - [MODIFY] Extend the shared completion registry, probe, and report surfaces for basketball

**Description**: If the shared rich-completion contract from the multisport coordination plan is not already present, introduce the minimal fully generic registry / no-write probe / generic rich-coverage report required for the first rollout. Those surfaces must be sport-agnostic in interface and extensible by later sports without redesign. If the shared contract already exists, extend it without creating a parallel basketball-only mechanism.

**Definition of Done**:

- [ ] Basketball declares `required_rich_keys`, `canonical_source`, `supporting_sources`, and any `aggregate_only_sources` in `src/bet/stats/fallback_chains.py::RICH_COMPLETION_POLICY`
- [ ] Basketball `required_rich_keys` are exactly `rebounds`, `assists`, `steals`, `blocks`, `turnovers`, `fouls`, `fg_pct`, `three_pct`, `ft_pct`, `points_in_paint`, and `fast_break_points`
- [ ] The shared `scripts/rich_stats_probe.py` supports `--sport basketball` and reports source choice, fixtures scanned, `rich`, `baseline_only`, `partial`, and `no_data` bucket counts, completion rate, and failure reasons
- [ ] `scripts/db_report.py` supports `--report rich-coverage --sport basketball --date <date>`
- [ ] The shared contract still writes only through `_store_in_cache()`
- [ ] Basketball is the first and only child plan that introduces the initial shared registry / probe / generic report surfaces
- [ ] `football-rich-coverage` remains available as a thin backward-compatible alias to the new generic rich-coverage implementation until callers are migrated

#### Task 1.2 - [CREATE] Build the bounded basketball completion adapter

**Description**: Create a basketball helper under `scripts/_helpers/` that loads recent finished fixtures, fetches per-game stats from the canonical provider path, normalizes them, and persists through the existing writer.

**Definition of Done**:

- [ ] `api-basketball` is the canonical completion source
- [ ] `nba-api` and `espn-basketball` are bounded supporting sources only where the policy allows
- [ ] Empty `espn-basketball` responses for non-NBA fixtures are treated as unsupported-league skips, not degraded-source failures
- [ ] Completion success is based on basketball required rich keys rather than any non-empty payload
- [ ] The adapter returns the base 7-key contract used by the shared enrichment flow: `status` (`str`), `fixtures_scanned` (`int`), `matches_persisted` (`int`), `rich_keys_found` (`list[str]`), `missing_rich_keys` (`list[str]`), `error` (`str | None`), and `failure_reason` (`str | None`)

### Phase 2: Owner Wiring and Focused Tests

#### Task 2.1 - [MODIFY] Route basketball completion through the owning enrichment flow

**Description**: Wire the new basketball completion adapter into `scripts/data_enrichment_agent.py` and keep the current baseline fallback-chain behavior intact for non-rich scenarios.

**Definition of Done**:

- [ ] Basketball teams or fixtures that remain partial after baseline enrichment can trigger the rich-completion helper from the owner flow
- [ ] AGENT_SUMMARY reports basketball `eligible`, `completed`, and `still_missing` counts
- [ ] Source provenance remains explicit and no new ownership is introduced in `scripts/run_scrapers.py`
- [ ] Branch B settlement code paths remain untouched

#### Task 2.2 - [CREATE] Add focused basketball adapter, routing, and probe tests

**Description**: Add narrow tests for the basketball completion slice and extend existing basketball provider tests where useful.

**Definition of Done**:

- [ ] Tests cover adapter persistence through `_store_in_cache()`
- [ ] Tests cover owner routing from `scripts/data_enrichment_agent.py`
- [ ] Tests cover no-write probe behavior and completion semantics
- [ ] Existing basketball provider tests remain passing

### Phase 3: Live Validation and Review

#### Task 3.1 - [REUSE] Run the sport-specific live validation commands

**Description**: Validate basketball rollout with the planned probe, report, and narrow test commands only.

**Definition of Done**:

- [ ] `scripts/rich_stats_probe.py --sport basketball` runs without mutating DB or cache outside its intended contract
- [ ] `scripts/db_report.py --report rich-coverage --sport basketball --date <date>` distinguishes `rich`, `baseline_only`, `partial`, and `no_data`
- [ ] The basketball-focused pytest command passes

#### Task 3.2 - [REUSE] Final code review by `tsh-code-reviewer`

**Description**: After focused executable validation passes, run the final review to check source-policy discipline, helper boundaries, and contract preservation.

**Definition of Done**:

- [ ] Review is run after the focused validation suite
- [ ] Findings are fixed or explicitly tracked in the Changelog
- [ ] Review confirms `match_stats -> team_form` preservation and no Branch B settlement regressions
- [ ] Review confirms `scripts/rich_stats_probe.py`, the shared completion registry, and `scripts/db_report.py --report rich-coverage` are sport-agnostic and not hardcoded to basketball
- [ ] The slice is not closed while review findings remain unresolved and untracked

## Security Considerations

- Keep provider calls bounded to recent finished fixtures and date-scoped probes
- Do not introduce Flashscore HTML or other speculative scraping as a basketball deep-stat default
- Preserve source provenance and explicit failure reasons for degraded provider behavior
- Do not reopen settlement logic while implementing basketball enrichment

## Quality Assurance

Acceptance criteria checklist to verify the implementation meets the defined requirements:

- [ ] Basketball rich completion stays owned by enrichment flows, not `scripts/run_scrapers.py`
- [ ] Persistence still flows through `_store_in_cache()` into `match_stats` and derived `team_form`
- [ ] Basketball has explicit canonical and supporting source policy in code and reporting
- [ ] A generic `rich-coverage` report exists and works for basketball
- [ ] Basketball-specific probe, adapter, and routing tests pass
- [ ] **Branch B settlement remains out of scope and unchanged**

## Improvements (Out of Scope)

Potential improvements identified during planning that are not part of the current task:

- wider cleanup of legacy provider ordering outside basketball
- dashboard or UI visualization of cross-sport rich coverage
- broader normalization cleanup between `normalize_stats` and `bet.models.normalized`

## Changelog

| Date   | Change Description |
| ------ | ------------------ |
| 2026-05-20 | Plan split out of the former multisport umbrella artifact so basketball can be implemented independently |
| 2026-05-20 | Hardened first-rollout ownership, validation preconditions, shared metric vocabulary, and downstream-agent handoff guidance |