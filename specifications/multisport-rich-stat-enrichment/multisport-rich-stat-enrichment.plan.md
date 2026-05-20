# multisport-rich-stat-enrichment - Coordination Plan

## Task Details

| Field            | Value |
| ---------------- | ----- |
| Jira ID          | N/A |
| Title            | Coordinate rich-stat enrichment rollout across basketball, volleyball, hockey, and tennis |
| Description      | Maintain the shared cross-sport foundation and rollout guardrails for rich-stat enrichment while delegating implementation detail to four standalone per-sport plans. This umbrella file is a coordination and index artifact, not the primary implementation plan. |
| Priority         | High |
| Related Research | `specifications/football-sofascore-team-form-enrichment/football-sofascore-team-form-enrichment.plan.md`, `specifications/flashscore-match-stats-token/flashscore-match-stats-token.plan.md`, `memories/repo/pipeline-knowledge-base.md` |

## Proposed Solution

Use the per-sport plans as the implementation source of truth:

- [basketball-rich-stat-enrichment.plan.md](../basketball-rich-stat-enrichment/basketball-rich-stat-enrichment.plan.md)
- [volleyball-rich-stat-enrichment.plan.md](../volleyball-rich-stat-enrichment/volleyball-rich-stat-enrichment.plan.md)
- [hockey-rich-stat-enrichment.plan.md](../hockey-rich-stat-enrichment/hockey-rich-stat-enrichment.plan.md)
- [tennis-rich-stat-enrichment.plan.md](../tennis-rich-stat-enrichment/tennis-rich-stat-enrichment.plan.md)

**Implementation should be taken from the per-sport plans, not from this umbrella file directly.**

**Delegation / handoff rule**:

- Never delegate this umbrella file alone to an implementation agent.
- Always pair it with exactly one child plan; the child plan controls the implementation slice and this umbrella file supplies shared guardrails only.
- If a later-sport branch does not yet contain the basketball-owned shared foundation (`scripts/rich_stats_probe.py`, the shared completion registry, and the generic `scripts/db_report.py --report rich-coverage` path), treat that as a sequencing/escalation issue unless the manager explicitly reassigns shared-foundation ownership.
- Later sport slices must not create parallel sport-specific copies of shared probe / registry / report surfaces.

This coordination plan keeps only the shared foundation that must remain consistent across all four sport slices:

- ownership stays in `scripts/data_enrichment_agent.py` and focused enrichment/probe scripts, not `scripts/run_scrapers.py`
- persistence remains `NormalizedMatchStats -> fetch_api_stats._store_in_cache() -> match_stats -> team_form`
- source-specific logic stays behind bounded helpers under `scripts/_helpers/`
- generic no-write probe and generic `rich-coverage` reporting should be shared rather than reimplemented four times
- Flashscore remains non-canonical by default; do not copy the football Flashscore HTML path into other sports
- aggregate-only sources may supplement analytics but must not silently satisfy canonical `match_stats` richness
- rollout should happen sport by sport with independent validation and reporting

Required rollout order: basketball -> volleyball -> hockey -> tennis.
Basketball must ship the shared completion foundation before any later sport slice begins. Basketball is the canonical first rollout and owns the first implementation of the shared completion surfaces (`scripts/rich_stats_probe.py`, the shared completion registry, and generic `scripts/db_report.py --report rich-coverage`). Subsequent sports should extend those shared surfaces rather than re-create them.

Shared metric vocabulary for all child plans:

- reporting buckets: `rich`, `baseline_only`, `partial`, `no_data`
- `rich`: required rich keys are present from canonical or allowed supporting per-match sources
- `baseline_only`: usable match-level coverage exists, but required rich keys do not
- `partial`: some expected coverage exists, but it still fails the sport's rich-success contract
- `no_data`: no usable match-level coverage exists for the slice being reported
- owner-flow metrics stay separate from report buckets and should use `eligible`, `completed`, and `still_missing`

**Branch B settlement remains out of scope and unchanged** for all four child plans.

## Current Implementation Analysis

### Already Implemented

- `scripts/data_enrichment_agent.py` - canonical owner for enrichment flows and current AGENT_SUMMARY reporting
- `scripts/fetch_api_stats.py::_store_in_cache()` - canonical write boundary into `match_stats` and derived `team_form`
- `src/bet/stats/fallback_chains.py` - shared fallback-chain module for all core sports
- `scripts/db_report.py` - current reporting surface, including the football-only `football-rich-coverage` report that should evolve into generic `rich-coverage`
- `scripts/inspect_pipeline.py` - current coarse S2 coverage view that should stay compatible with richer reporting
- `specifications/football-sofascore-team-form-enrichment/football-sofascore-team-form-enrichment.plan.md` - completed reference for helper boundaries, owner routing, and writer discipline
- `specifications/flashscore-match-stats-token/flashscore-match-stats-token.plan.md` - finalized source-policy plan that retired tokenized Flashscore usage and locked in Branch B settlement
- the four child plans linked above - the primary implementation artifacts for basketball, volleyball, hockey, and tennis

### To Be Modified

- `src/bet/stats/fallback_chains.py` - shared completion semantics, required rich keys, and explicit aggregate-only source policy must remain aligned across sports
- `scripts/db_report.py` - generic `rich-coverage` reporting should stay shared across sports instead of splintering into separate report names; `football-rich-coverage` remains as a backward-compatible alias until callers migrate to `--report rich-coverage --sport football`
- `scripts/data_enrichment_agent.py` - per-sport completion routing and summary fields should remain consistent with the shared contract as each child plan lands

### To Be Created

- none at the umbrella level beyond the child plans already created; implementation details now live in the four per-sport plan files

## Open Questions

| #   | Question | Answer | Status |
| --- | -------- | ------ | ------ |
| 1   | Where should implementation detail come from after the split? | From the four per-sport plans linked in this file, not from the umbrella plan. | ✅ Resolved |
| 2   | Should this umbrella plan continue to carry sport-specific helper logic and live commands? | No. Those details now belong in the per-sport plans so each can be used independently. | ✅ Resolved |
| 3   | What remains only in this umbrella plan? | Cross-sport shared foundation, rollout guardrails, and coordination expectations. | ✅ Resolved |
| 4   | Does any part of this split reopen Branch B settlement? | No. Branch B remains unchanged and out of scope. | ✅ Resolved |

## Technical Context

### Project Instructions

- `.github/copilot-instructions.md` - DB-first, verify producer/consumer data flow before changes, keep changes narrow and root-cause focused
- workspace memory - fish-safe commands only; do not rely on inline Python or shell loops in validation guidance
- `memories/repo/pipeline-knowledge-base.md` - Branch B settlement is final and remains isolated from enrichment rollout work

### Architecture & Patterns

- `scripts/data_enrichment_agent.py` is the canonical owner for self-healing enrichment and remains the preferred integration point for all four sports
- `scripts/run_scrapers.py` is a scraper registry for season/team/player/fixture scraping and does not own `team_form` completion
- `_store_in_cache()` remains the only intended persistence bridge for new per-match rich completion
- shared completion semantics should live in `src/bet/stats/fallback_chains.py` as a single sport-keyed `RICH_COMPLETION_POLICY` structure adjacent to `FALLBACK_CHAINS` and `EXPECTED_STATS_PER_SPORT`; later sports extend that structure rather than inventing another module or schema
- baseline fallback ordering in `FALLBACK_CHAINS` stays unchanged unless a child plan explicitly re-scopes baseline behavior; canonical rich-completion semantics live in `RICH_COMPLETION_POLICY`, not in chain order
- helper modules under `scripts/_helpers/` are the accepted boundary for source-specific parsing or completion logic
- generic probe and report surfaces should be shared across sports rather than duplicated

### Cross-Sport Source Policy Guardrails

- basketball: provider-backed per-match completion centered on `api-basketball`
- volleyball: provider-backed per-match completion centered on `api-volleyball`
- hockey: provider-backed per-game completion centered on `api-hockey`; aggregate advanced sources remain supplementary only
- tennis: mixed-source completion that preserves the scoreboard baseline, uses `tennis-abstract` as the canonical rich-completion source, and adds bounded supporting serve/return richness
- Flashscore is non-canonical by default outside the already-completed football reference path

### Testing Patterns

- each sport should land with narrow pytest coverage for helper logic, owner routing, and no-write probe/report behavior
- validation should use fish-safe, date-scoped commands only
- rollout should remain sport-by-sport so failures are easy to isolate

### Additional Context

- `scripts/db_report.py` still has only `football-rich-coverage` today, so generic reporting remains a shared gap across all four sports
- `scripts/data_enrichment_agent.py` already contains asymmetric supplementary logic for hockey and tennis, which is why the child plans explicitly separate canonical completion from supplementary or baseline behavior
- **Branch B settlement remains out of scope and unchanged across the full multisport rollout**

## Implementation Plan

### Phase 1: Treat the Child Plans as the Primary Implementation Artifacts

#### Task 1.1 - [REUSE] Implement each sport from its dedicated child plan

**Description**: Engineering work for basketball, volleyball, hockey, and tennis should start from the linked child plan for that sport rather than from this umbrella file.

**Definition of Done**:

- [ ] Basketball implementation follows the basketball child plan
- [ ] Volleyball implementation follows the volleyball child plan
- [ ] Hockey implementation follows the hockey child plan
- [ ] Tennis implementation follows the tennis child plan
- [ ] This umbrella file is not used as a standalone implementation plan

#### Task 1.2 - [REUSE] Keep the shared completion contract aligned across sports

**Description**: As child plans land, maintain one shared completion contract for owner routing, writer discipline, reporting buckets, and source-policy semantics.

**Definition of Done**:

- [ ] Ownership remains in enrichment flows, not `scripts/run_scrapers.py`
- [ ] Persistence remains `match_stats -> team_form` through `_store_in_cache()`
- [ ] Generic probe and generic `rich-coverage` reporting remain shared rather than forked per sport
- [ ] Aggregate-only source rules remain explicit and consistent across sports

### Phase 2: Cross-Sport Rollout Guardrails

#### Task 2.1 - [REUSE] Roll out one sport at a time with independent validation

**Description**: Land each sport with its own focused tests, probe command, and rich-coverage report before combining the work with another sport slice.

**Definition of Done**:

- [ ] Each sport has an independent live validation command set documented in its child plan
- [ ] Each sport can be probed and reported independently by date
- [ ] No child implementation reopens settlement or moves work into scraper ownership
- [ ] Later sport slices escalate missing shared-foundation sequencing instead of duplicating probe / registry / report surfaces

#### Task 2.2 - [REUSE] Preserve shared source-policy guardrails during cross-sport merge

**Description**: Use the umbrella rules as the final consistency check when multiple child implementations are merged together.

**Definition of Done**:

- [ ] Flashscore remains non-canonical by default outside the football reference path
- [ ] Aggregate-only sources do not satisfy canonical `match_stats` richness
- [ ] Reporting buckets and AGENT_SUMMARY fields stay semantically consistent across sports
- [ ] Branch B settlement remains untouched

### Phase 3: Final Coordination Review

#### Task 3.1 - [REUSE] Run a final cross-sport consistency review

**Description**: After one or more child plans land, verify that the shared contract has not drifted across sports.

**Definition of Done**:

- [ ] Shared completion registry, probe behavior, and reporting buckets remain aligned
- [ ] No child slice introduced a sport-specific parallel implementation of `scripts/rich_stats_probe.py`, the shared completion registry, or the generic `rich-coverage` report path
- [ ] Source provenance and helper boundaries remain consistent
- [ ] No child implementation silently widened scope into settlement or scraper ownership

#### Task 3.2 - [REUSE] Final code review by `tsh-code-reviewer`

**Description**: Run the final review after focused validation to check cross-sport consistency and guardrail compliance.

**Definition of Done**:

- [ ] Review is run after focused executable validation for the landed sport slices
- [ ] Findings are fixed or explicitly tracked in the relevant child-plan changelogs
- [ ] Review confirms `match_stats -> team_form` preservation and no Branch B settlement regressions
- [ ] The cross-sport slice is not closed while review findings remain unresolved and untracked

## Security Considerations

- Keep all new source calls bounded by recent fixtures, rate limiters, and date-scoped probes
- Do not expand Flashscore or any speculative scraping path across sports unless a sport-specific child plan explicitly proves it
- Preserve explicit source provenance and failure reasons in shared reporting and metrics
- Keep settlement logic isolated from this enrichment rollout

## Quality Assurance

- [ ] The four child plans exist and are independently usable implementation artifacts
- [ ] This umbrella file no longer acts as the only implementation plan for multisport rich-stat enrichment
- [ ] Shared foundation items kept here are limited to cross-sport ownership, contract, reporting, and rollout guardrails
- [ ] Sport-specific helper logic, source choice, tests, and live validation commands live in the child plans
- [ ] **Implementation is taken from the per-sport plans, not from this umbrella file directly**
- [ ] **Branch B settlement remains out of scope and unchanged**

## Improvements (Out of Scope)

- dashboard visualization for cross-sport rich-coverage health
- broader cleanup of unrelated legacy enrichment or scraper surfaces
- additional provider/vendor expansion beyond the sources already present in the repo

## Changelog

| Date   | Change Description |
| ------ | ------------------ |
| 2026-05-20 | Converted the former multisport implementation plan into a coordination/index artifact and split implementation detail into four standalone per-sport plans |
| 2026-05-20 | Hardened downstream-agent handoff, shared-surface sequencing rules, and shared reporting vocabulary across the umbrella and child plans |
