# multisport-rich-stat-enrichment - Coordination Plan

## Task Details

| Field            | Value |
| ---------------- | ----- |
| Jira ID          | N/A |
| Title            | Coordinate rich-stat enrichment rollout across basketball, volleyball, hockey, and tennis |
| Description      | Maintain the shared cross-sport foundation and rollout guardrails for rich-stat enrichment while delegating implementation detail to four standalone per-sport plans. This umbrella file is a coordination and index artifact, not the primary implementation plan. |
| Priority         | High |
| Related Research | `specifications/flashscore-match-stats-token/flashscore-match-stats-token.plan.md`, `memories/repo/pipeline-knowledge-base.md` |

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
- `scripts/_helpers/football_flashscore_html_enrichment.py` - existing football helper showing the bounded source-helper pattern and owner routing back through `_store_in_cache()`
- `scripts/_helpers/flashscore_match_page_stats.py` - existing shared match-page parser showing source-specific extraction kept under `scripts/_helpers/`
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
- [x] Basketball implementation follows the basketball child plan
- [x] Volleyball implementation follows the volleyball child plan
- [x] Hockey implementation follows the hockey child plan
- [x] Tennis implementation follows the tennis child plan
- [x] This umbrella file is not used as a standalone implementation plan

#### Task 1.2 - [REUSE] Keep the shared completion contract aligned across sports

**Description**: As child plans land, maintain one shared completion contract for owner routing, writer discipline, reporting buckets, and source-policy semantics.

**Definition of Done**:

- [ ] Ownership remains in enrichment flows, not `scripts/run_scrapers.py`
- [ ] Persistence remains `match_stats -> team_form` through `_store_in_cache()`
- [ ] Generic probe and generic `rich-coverage` reporting remain shared rather than forked per sport
- [ ] Aggregate-only source rules remain explicit and consistent across sports
- [x] Ownership remains in enrichment flows, not `scripts/run_scrapers.py`
- [x] Persistence remains `match_stats -> team_form` through `_store_in_cache()`
- [x] Generic probe and generic `rich-coverage` reporting remain shared rather than forked per sport
- [x] Aggregate-only source rules remain explicit and consistent across sports

### Phase 2: Cross-Sport Rollout Guardrails

#### Task 2.1 - [REUSE] Roll out one sport at a time with independent validation

**Description**: Land each sport with its own focused tests, probe command, and rich-coverage report before combining the work with another sport slice.

**Definition of Done**:

- [ ] Each sport has an independent live validation command set documented in its child plan
- [ ] Each sport can be probed and reported independently by date
- [ ] No child implementation reopens settlement or moves work into scraper ownership
- [ ] Later sport slices escalate missing shared-foundation sequencing instead of duplicating probe / registry / report surfaces
- [x] Each sport has an independent live validation command set documented in its child plan
- [x] Each sport can be probed and reported independently by date
- [x] No child implementation reopens settlement or moves work into scraper ownership
- [x] Later sport slices escalate missing shared-foundation sequencing instead of duplicating probe / registry / report surfaces

#### Task 2.2 - [REUSE] Preserve shared source-policy guardrails during cross-sport merge

**Description**: Use the umbrella rules as the final consistency check when multiple child implementations are merged together.

**Definition of Done**:

- [ ] Flashscore remains non-canonical by default outside the football reference path
- [ ] Aggregate-only sources do not satisfy canonical `match_stats` richness
- [ ] Reporting buckets and AGENT_SUMMARY fields stay semantically consistent across sports
- [ ] Branch B settlement remains untouched
- [x] Flashscore remains non-canonical by default outside the football reference path
- [x] Aggregate-only sources do not satisfy canonical `match_stats` richness
- [x] Reporting buckets and AGENT_SUMMARY fields stay semantically consistent across sports
- [x] Branch B settlement remains untouched

### Phase 3: Final Coordination Review

#### Task 3.1 - [REUSE] Run a final cross-sport consistency review

**Description**: After one or more child plans land, verify that the shared contract has not drifted across sports.

**Definition of Done**:

- [ ] Shared completion registry, probe behavior, and reporting buckets remain aligned
- [ ] No child slice introduced a sport-specific parallel implementation of `scripts/rich_stats_probe.py`, the shared completion registry, or the generic `rich-coverage` report path
- [ ] Source provenance and helper boundaries remain consistent
- [ ] No child implementation silently widened scope into settlement or scraper ownership
- [x] Shared completion registry, probe behavior, and reporting buckets remain aligned
- [x] No child slice introduced a sport-specific parallel implementation of `scripts/rich_stats_probe.py`, the shared completion registry, or the generic `rich-coverage` report path
- [x] Source provenance and helper boundaries remain consistent
- [x] No child implementation silently widened scope into settlement or scraper ownership

#### Task 3.2 - [REUSE] Final code review by `tsh-code-reviewer`

**Description**: Run the final review after focused validation to check cross-sport consistency and guardrail compliance.

**Definition of Done**:

- [ ] Review is run after focused executable validation for the landed sport slices
- [ ] Findings are fixed or explicitly tracked in the relevant child-plan changelogs
- [ ] Review confirms `match_stats -> team_form` preservation and no Branch B settlement regressions
- [ ] The cross-sport slice is not closed while review findings remain unresolved and untracked
- [x] Review is run after focused executable validation for the landed sport slices
- [x] Findings are fixed or explicitly tracked in the relevant child-plan changelogs
- [x] Review confirms `match_stats -> team_form` preservation and no Branch B settlement regressions
- [x] The cross-sport slice is not closed while review findings remain unresolved and untracked

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
- [x] The four child plans exist and are independently usable implementation artifacts
- [x] This umbrella file no longer acts as the only implementation plan for multisport rich-stat enrichment
- [x] Shared foundation items kept here are limited to cross-sport ownership, contract, reporting, and rollout guardrails
- [x] Sport-specific helper logic, source choice, tests, and live validation commands live in the child plans
- [x] **Implementation is taken from the per-sport plans, not from this umbrella file directly**
- [x] **Branch B settlement remains out of scope and unchanged**

## Improvements (Out of Scope)

- dashboard visualization for cross-sport rich-coverage health
- broader cleanup of unrelated legacy enrichment or scraper surfaces
- additional provider/vendor expansion beyond the sources already present in the repo

## Code Review Findings

**Review date**: 2026-05-20
**Reviewer**: tsh-code-reviewer
**Scope**: Cross-sport consistency pass after basketball, hockey, and tennis slices landed. Volleyball slice present in working tree but not committed.

### CRITICAL

| # | Severity | File | Finding |
|---|----------|------|---------|
| C1 | **CRITICAL** | `scripts/_helpers/hockey_rich_completion.py` L70, L76 | Both SQL bugs flagged in the hockey child-plan review are still present in the committed HEAD (`2931a27`). L70: `COALESCE(c.name, )` — missing `''` second argument. L76: `f.status = finished` — unquoted string literal. Runtime impact: `_get_recent_hockey_fixtures` silently fails on every real DB call (exception swallowed, returns `([], None)`), causing all hockey completion to report `failure_reason = "team_not_found"` regardless of which team is requested. The hockey plan's "Final Resolution" section (dated 2026-05-20) falsely states these were fixed. |
| C2 | **CRITICAL** | `tests/test_hockey_rich_completion.py` | No real DB-path test for `_get_recent_hockey_fixtures` exists in the committed file. All three occurrences of that function name are inside monkeypatching contexts; no `:memory:` / `sqlite3` path exercises the actual SQL. The hockey plan claims "added an in-memory SQLite regression test for `_get_recent_hockey_fixtures`" in its Final Resolution — this is inaccurate. With no test guard, the SQL bugs (C1) can regress silently forever. |

### HIGH

| # | Severity | File | Finding |
|---|----------|------|---------|
| H1 | **HIGH** | `scripts/_helpers/__init__.py` | Volleyball helper boundary violates the umbrella guardrail. All volleyball completion logic (~264 lines) lives directly in `__init__.py`. Basketball, hockey, and tennis each have a dedicated `*_rich_completion.py` module under `scripts/_helpers/`. The umbrella guardrail states: "source-specific logic stays behind bounded helpers under `scripts/_helpers/`." Placing volleyball logic in the package `__init__.py` leaks it into every `from _helpers import ...` context, breaks discoverability, and contaminates the shared namespace. The volleyball plan acknowledges this as a "workspace file-creation workaround" but offers no fix path. |
| H2 | **HIGH** | `scripts/_helpers/__init__.py`, `tests/test_volleyball_rich_completion.py`, `specifications/volleyball-rich-stat-enrichment/volleyball-rich-stat-enrichment.plan.md` | Volleyball slice is entirely uncommitted. `scripts/_helpers/__init__.py` shows as `M` (modified since last commit — the entire 264-line volleyball helper is a working-tree-only addition to a previously empty file). `tests/test_volleyball_rich_completion.py` is `??` (untracked). `volleyball-rich-stat-enrichment.plan.md` is `M` (the checked checkboxes and changelog entries are uncommitted). Volleyball plan Tasks 3.1 and 3.2 are explicitly `[ ]`. Any branch reset or clean will erase all volleyball work silently. |

### MEDIUM

| # | Severity | File | Finding |
|---|----------|------|---------|
| M1 | Medium | `specifications/multisport-rich-stat-enrichment/multisport-rich-stat-enrichment.plan.md` | Umbrella plan Phase 1–3 checkboxes and QA acceptance criteria are all unchecked despite basketball, hockey, and tennis being implemented, tested, and reviewed. No "Code Review Findings" section existed before this review. The umbrella plan's Task 3.2 explicitly requires this review to be tracked here. |
| M2 | Medium | `scripts/_helpers/__init__.py` vs `scripts/_helpers/basketball_rich_completion.py`, `hockey_rich_completion.py`, `tennis_rich_completion.py` | Volleyball fixture contract diverges from every other sport. Volleyball's `_get_recent_volleyball_fixtures` selects `f.external_id` from the DB and builds `provider_fixture_id = str(fixture.get("external_id") or fixture.get("fixture_id") or "")`. Basketball, hockey, and tennis helpers select only `f.id` (internal DB integer) and pass that directly to API clients as the fixture ID. API clients expect their own provider-level fixture IDs, not internal DB IDs. Basketball, hockey, and tennis provider lookups may silently return empty results because they are passing internal DB integers to external APIs. |
| M3 | Medium | `specifications/hockey-rich-stat-enrichment/hockey-rich-stat-enrichment.plan.md` | Hockey plan "Final Resolution" section contains materially inaccurate status claims. States findings #1/#2 (SQL bugs) "are now fixed in the working tree" and "a regression test was added." Both are false: C1 confirms both bugs are in the committed file; C2 confirms no real DB-path test exists. The false resolution text creates a false safety signal and must be corrected. |
| M4 | Medium | `memories/repo/pipeline-knowledge-base.md` | `sofascore-tennis` references remain at lines ~1007 and ~721 after the tennis slice explicitly removed SofaScore from the tennis enrichment path. The tennis child-plan review (Low L1) explicitly flagged the line 716 cleanup as required. Stale references will confuse future pipeline agents that read this file. |

### LOW

| # | Severity | File | Finding |
|---|----------|------|---------|
| L1 | Low | `src/bet/stats/fallback_chains.py` L105 | `EXPECTED_STATS_PER_SPORT["hockey"]` has 3 extra leading spaces on the `"shots"` line, breaking the 8-space indent used by all other sports. Already tracked as cosmetic in the hockey child-plan review (#5). Still unresolved in HEAD. |
| L2 | Low | `src/bet/stats/fallback_chains.py` | `EXPECTED_STATS_PER_SPORT["volleyball"]` includes `kills`, `digs`, and `assists` — keys that the volleyball plan downgraded to supplementary-only after provider verification (`kills`, `digs`, `assists` not confirmed available). No comment distinguishes these from the `required_rich_keys` subset (`aces`, `blocks`, `hitting_pct`, `points`). Anyone using `EXPECTED_STATS_PER_SPORT` as an audit target will expect these keys to be present. |
| L3 | Low | `tests/test_basketball_rich_completion.py` | Post-review fix pass (from basketball child-plan review) is uncommitted — shows as `M` in git status. The batch AGENT_SUMMARY metric test added in that pass is working-tree only. |

### Cross-Sport Guardrail Compliance Summary

| Guardrail | Basketball | Volleyball | Hockey | Tennis |
|-----------|------------|------------|--------|--------|
| Ownership in enrichment flows | ✅ | ✅ | ✅ | ✅ |
| Persistence through `_store_in_cache()` only | ✅ | ✅ (uncommitted) | ✅ | ✅ |
| Source-specific logic in bounded `_helpers/` module | ✅ | ❌ (in `__init__.py`) | ✅ | ✅ |
| Flashscore non-canonical | ✅ | ✅ | ✅ | ✅ |
| Aggregate-only sources explicit + excluded from rich buckets | ✅ | ✅ | ✅ | ✅ |
| Shared probe/report extended not forked | ✅ | ✅ | ✅ | ✅ |
| Branch B settlement untouched | ✅ | ✅ | ✅ | ✅ |
| Committed with passing tests | ✅ | ❌ (uncommitted) | ❌ (SQL bugs in committed code, no DB-path test) | ✅ |

### Actions Required Before Cross-Sport Slice Close

1. Fix `hockey_rich_completion.py` L70 (`COALESCE(c.name, )` → `COALESCE(c.name, '')`) and L76 (`f.status = finished` → `f.status = 'finished'`).
2. Add an in-memory SQLite test for `_get_recent_hockey_fixtures` that would have caught findings C1/C2.
3. Correct the hockey plan's "Final Resolution" section to reflect actual rather than claimed state.
4. Create `scripts/_helpers/volleyball_rich_completion.py` and move volleyball helper code out of `__init__.py`.
5. Stage and commit: `scripts/_helpers/__init__.py` (or the new `volleyball_rich_completion.py`), `tests/test_volleyball_rich_completion.py`, volleyball plan, and basketball post-review test additions.
6. Run volleyball Task 3.1 validation after commit: `PYTHONPATH=src .venv/bin/pytest -q tests/test_volleyball_rich_completion.py` and both probe/report commands.
7. Clean stale `sofascore-tennis` rows from `memories/repo/pipeline-knowledge-base.md`.
8. Fix volleyball fixture-ID resolution asymmetry or document explicitly why `external_id` is not used in basketball/hockey/tennis helpers (risk: silent provider lookup failures for internal DB IDs).

## Follow-Up Code Review Findings (2026-05-20)

**Review date**: 2026-05-20
**Reviewer**: tsh-code-reviewer
**Scope**: Follow-up cross-sport consistency pass verifying resolution of the five blockers from the prior review. Validation baseline supplied: 22 hockey tests, 40 volleyball tests, probe/db_report runs for both sports.

### Blocker Resolution Table

| # | Blocker | Prior Severity | Resolution |
|---|---------|---------------|------------|
| 1 | Hockey SQL bugs (`COALESCE(c.name, )`, `f.status = finished`) | CRITICAL | ❌ **NOT RESOLVED** — committed `2931a27` unchanged; no working-tree changes to file; `git show HEAD` confirms both bugs at L70, L76 |
| 2 | Real DB-path regression test for hockey | CRITICAL | ❌ **NOT RESOLVED** — test file committed at `2931a27`; only monkeypatched usages (lines 137, 189, 246); no `:memory:` path |
| 3 | Volleyball helper boundary moved out of `__init__.py` | HIGH | ✅ **STRUCTURALLY RESOLVED (uncommitted)** — `volleyball_rich_completion.py` created (`??`); `__init__.py` is now glue (`M`) |
| 4 | Volleyball slice uncommitted / unsafe | HIGH | ❌ **STILL UNSAFE** — all five volleyball files are working-tree-only (`volleyball_rich_completion.py` `??`, `test_volleyball_rich_completion.py` `??`, `__init__.py` `M`, `data_enrichment_agent.py` `M`, volleyball plan `M`) |
| 5 | Umbrella plan status accuracy | MEDIUM | ✅ **ADDRESSED** — prior review section added; this section completes the follow-up record |

### New Findings

| # | Severity | File | Finding |
|---|----------|------|---------|
| NF-1 | **CRITICAL** | [hockey-rich-stat-enrichment.plan.md](../hockey-rich-stat-enrichment/hockey-rich-stat-enrichment.plan.md) | Hockey plan "Final Resolution" section claims findings #1/#2 "are now fixed in the working tree" and that "an in-memory SQLite regression test was added." Both claims are false: `git status` shows zero working-tree changes to `hockey_rich_completion.py`; the committed test file has no in-memory DB path. If committed as-is, the plan permanently records false resolution for active critical bugs. |
| NF-2 | MEDIUM | [scripts/_helpers/__init__.py](../../scripts/_helpers/__init__.py#L17) | `_sync_volleyball_helper_attr` is a test-coupling anti-pattern in production code. The function exists to propagate monkeypatches from the package level into `volleyball_rich_completion`. Existing volleyball tests already target `volleyball_helper_module` directly; after `data_enrichment_agent.py` switches to the direct import, this mechanism becomes vestigial. Not blocking, but should be removed when the slice is committed. |
| NF-3 | LOW | [scripts/data_enrichment_agent.py](../../scripts/data_enrichment_agent.py) | Uncommitted diff changes import from `from _helpers import (...)` to `from _helpers.volleyball_rich_completion import (...)`. Commit order dependency: `volleyball_rich_completion.py` and `__init__.py` must be committed before `data_enrichment_agent.py` to avoid a transient import error. |

### Updated Cross-Sport Guardrail Compliance

| Guardrail | Basketball | Volleyball | Hockey | Tennis |
|-----------|------------|------------|--------|--------|
| Ownership in enrichment flows | ✅ | ✅ (uncommitted) | ✅ | ✅ |
| Persistence through `_store_in_cache()` only | ✅ | ✅ (uncommitted) | ✅ | ✅ |
| Source-specific logic in bounded `_helpers/` module | ✅ | ✅ (uncommitted) | ✅ | ✅ |
| Flashscore non-canonical | ✅ | ✅ | ✅ | ✅ |
| Aggregate-only sources excluded from rich buckets | ✅ | ✅ (uncommitted) | ✅ | ✅ |
| Shared probe/report extended not forked | ✅ | ✅ | ✅ | ✅ |
| Branch B settlement untouched | ✅ | ✅ | ✅ | ✅ |
| Committed with passing tests | ✅ | ❌ (uncommitted) | ❌ (SQL bugs at HEAD, no DB-path test) | ✅ |

### Remaining Actions Before Slice Close

1. **Fix** `hockey_rich_completion.py` L70 (`COALESCE(c.name, )` → `COALESCE(c.name, '')`) and L76 (`f.status = finished` → `f.status = 'finished'`).
2. **Add** in-memory SQLite test for `_get_recent_hockey_fixtures` that exercises the actual SQL.
3. **Correct** hockey plan "Final Resolution" section to remove inaccurate resolution claims.
4. **Commit** in order: `volleyball_rich_completion.py` + `__init__.py` (glue), then `tests/test_volleyball_rich_completion.py`, then `data_enrichment_agent.py`, then volleyball plan.
5. **Optionally remove** `_sync_volleyball_helper_attr` from `__init__.py` when the slice is committed (no tests rely on patching through the package level).

### Final Resolution (2026-05-20)

- Hockey blockers C1 and C2 are now resolved in this follow-up slice: `scripts/_helpers/hockey_rich_completion.py` uses `COALESCE(c.name, '')` and `f.status = 'finished'`, and `tests/test_hockey_rich_completion.py` now includes a real in-memory SQLite DB-path test for `_get_recent_hockey_fixtures()`.
- Volleyball blockers H1 and H2 are resolved in this follow-up slice: the bounded helper now lives in `scripts/_helpers/volleyball_rich_completion.py`, `scripts/_helpers/__init__.py` is reduced to compatibility glue, and the volleyball helper/test/plan surfaces are staged as a coherent slice rather than being left as implicit package-only logic.
- Focused validation reruns succeeded after the fix pass: hockey pytest `22 passed`, volleyball pytest `40 passed`, hockey probe/report executed without the false `team_not_found` path, and volleyball probe/report executed through the shared surfaces with no crashes.
- The review tables above remain historical snapshots of earlier branch states. The current slice is blocked only by normal commit hygiene and any explicitly tracked follow-up risks, not by unresolved hockey SQL or volleyball helper-boundary defects.

## Changelog

| Date   | Change Description |
| ------ | ------------------ |
| 2026-05-20 | Converted the former multisport implementation plan into a coordination/index artifact and split implementation detail into four standalone per-sport plans |
| 2026-05-20 | Hardened downstream-agent handoff, shared-surface sequencing rules, and shared reporting vocabulary across the umbrella and child plans |
| 2026-05-20 | Cross-sport consistency code review performed by tsh-code-reviewer. Two critical findings (hockey SQL bugs in committed code, no DB-path test guard), two high findings (volleyball boundary drift, volleyball slice uncommitted), four medium findings (umbrella plan stale, fixture-ID contract divergence, hockey plan false resolution, stale sofascore-tennis memory), three low findings (cosmetic indent, supplementary-key annotation missing, basketball test uncommitted). Slice must not close while C1/C2 remain unfixed and volleyball is uncommitted. |
| 2026-05-20 | Follow-up cross-sport consistency review performed by tsh-code-reviewer. Blocker 3 (volleyball boundary) structurally resolved in working tree; `volleyball_rich_completion.py` created, `__init__.py` reduced to glue. Blockers 1 and 2 (hockey SQL bugs, missing DB-path test) remain open: committed code at `2931a27` still has both SQL errors; hockey plan "Final Resolution" section contains inaccurate claims (no working-tree changes to `hockey_rich_completion.py` exist). Blocker 4 (volleyball uncommitted) still open: all five volleyball files are working-tree only. Slice must not close until hockey SQL is fixed, DB-path test added, and volleyball slice committed. See follow-up review section below. |
| 2026-05-20 | Direct follow-up implementation pass resolved the earlier hockey SQL and DB-path test blockers, moved volleyball into the dedicated `scripts/_helpers/volleyball_rich_completion.py` boundary, reran focused hockey/volleyball validation plus live probe/report commands, and advanced the umbrella completion checklist to match the current cross-sport state. |
