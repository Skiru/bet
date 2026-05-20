# Pipeline Data Flow Holes Review Pass - Implementation Plan

## Task Details

| Field            | Value                   |
| ---------------- | ----------------------- |
| Jira ID          | N/A |
| Title            | Manager-led deep review, fix, and improvement pass for branch `fix/pipeline-data-flow-holes` |
| Description      | Review the current dirty worktree on `fix/pipeline-data-flow-holes`, excluding the non-discovery SofaScore cleanup slice already owned by another agent, then land bug fixes and targeted improvements on the remaining branch state and prepare it for commit/push readiness without pulling generated betting artifacts into scope. |
| Priority         | High |
| Related Research | [sofascore-non-discovery-cleanup.plan.md](./sofascore-non-discovery-cleanup.plan.md), [flashscore-match-stats-token.plan.md](./flashscore-match-stats-token/flashscore-match-stats-token.plan.md), [post-refactor-alignment.plan.md](./post-refactor-alignment.plan.md), [pipeline-knowledge-base.md](../memories/repo/pipeline-knowledge-base.md) |

## Proposed Solution

Create a dedicated branch-review plan for the non-SofaScore slice of the branch instead of extending the active SofaScore cleanup plan.

The current dirty worktree is broader than the original feature cleanup, but the user clarified that `specifications/sofascore-non-discovery-cleanup.plan.md` is already being implemented in another agent. This plan therefore excludes that parallel-owned slice and focuses on the remaining review/fix work needed on this branch without racing or overwriting the other agent's implementation.

This plan therefore treats the existing feature plans as inputs, not as the execution container. The manager should use this document to run a review-first implementation pass in ordered slices:

```text
Current branch review pass
  -> freeze scope and capture findings
  -> review/fix remaining runtime data-flow, repository, and support-script surfaces
  -> review/fix remaining tests and documentation/spec/memory alignment
  -> run focused validation + tsh-code-reviewer gates
  -> finish with git readiness triage (no push in this task)
```

### In Scope

- Dirty code, test, and documentation surfaces under `.github/`, `scripts/`, `src/bet/`, `tests/`, `specifications/`, and `memories/repo/` that are not already owned by `specifications/sofascore-non-discovery-cleanup.plan.md`
- Remaining changed branch files currently visible outside the parallel-owned slice, including:
  - `.github/agents/bet-enricher.agent.md`
  - `.github/agents/bet-orchestrator.agent.md`
  - `.github/agents/bet-settler.agent.md`
  - `.github/copilot-instructions.md`
  - `.github/instructions/analysis-methodology.instructions.md`
  - `.github/internal-prompts/bet-enrich.prompt.md`
  - `.github/prompts/ask-betting.prompt.md`
  - `.github/prompts/orchestrate-betting-day.prompt.md`
  - `.github/skills/bet-settling-results/SKILL.md`
  - `memories/repo/pipeline-knowledge-base.md`
  - `scripts/analyze_betclic_learning.py`
  - `scripts/db_report.py`
  - `scripts/fetch_api_stats.py`
  - `scripts/flashscore_enricher.py`
  - `src/bet/api_clients/sofascore.py`
  - `src/bet/api_clients/unified.py`
  - `src/bet/db/repositories.py`
  - `tests/test_db_repositories.py`
  - `tests/test_fetch_api_stats.py`
  - operational/deleted script surfaces that are not already covered by the parallel feature plan: `scripts/_extract_legit.py`, `scripts/_tmp_db_check.py`, `scripts/_validate_coupon.py`, `scripts/deep_analysis_pool.py`, `scripts/verify_betclic_odds.py`
- `config/betting_config.json` only if review finds that a changed runtime surface depends on the modified config contract

### Explicitly Out Of Scope In This Pass

- `specifications/sofascore-non-discovery-cleanup.plan.md` and the implementation work already being done under that plan by another agent
- `scripts/data_enrichment_agent.py`
- `scripts/settle_on_finish.py`
- `src/bet/api_clients/volleyball_data.py`
- `src/bet/stats/fallback_chains.py`
- `src/bet/scrapers/__init__.py`
- `src/bet/scrapers/constants.py`
- `src/bet/scrapers/tennis/__init__.py`
- `src/bet/scrapers/tennis/sofascore_tennis.py`
- `src/bet/scrapers/volleyball/__init__.py`
- `src/bet/scrapers/volleyball/sofascore_volley.py`
- `tests/scrapers/test_integration.py`
- `tests/scrapers/tennis/test_sofascore_tennis.py`
- `tests/scrapers/volleyball/test_sofascore_volley.py`
- `specifications/post-refactor-alignment.plan.md`
- `specifications/scrapers-pipeline-integration.md`
- any new helper/test artifacts whose only purpose is to support the parallel SofaScore cleanup plan

### Ignore During Review Unless A Runtime Contract Requires Read-Only Inspection

- `betting/coupons/**`
- `betting/coupons/pdf/**`
- `*.pre-rescan` coupon backups
- daily coupon markdown/json outputs
- `.DS_Store`

### Review Policy

- Treat deep code review findings as first-class implementation work, not a final polish step.
- Run `tsh-code-reviewer` twice: once after the main runtime/test slices, and once as the final gate.
- Do not reopen completed feature-plan items unless the review finds an active regression or a still-live stale reference.
- Do not revert unrelated user work or generated betting artifacts.

## Current Implementation Analysis

### Already Implemented

List of existing components, functions, utilities that will be reused (with file paths):

- `sofascore-non-discovery-cleanup.plan.md` - `specifications/sofascore-non-discovery-cleanup.plan.md` - active parallel-owned feature plan that defines the slice this review pass must not touch.
- `flashscore-match-stats-token.plan.md` - `specifications/flashscore-match-stats-token/flashscore-match-stats-token.plan.md` - finalized source-policy direction for retiring the tokenized Flashscore stats feed and keeping Branch B settlement.
- `pipeline-knowledge-base.md` - `memories/repo/pipeline-knowledge-base.md` - branch-level record of the current architecture decisions, including Branch B settlement and the orchestrator/model alignment.
- shared source-policy surfaces still in this pass - `scripts/fetch_api_stats.py`, `src/bet/api_clients/unified.py`, `src/bet/api_clients/sofascore.py` - current provider-routing surfaces outside the parallel-owned cleanup slice.
- remaining runtime/reporting surfaces - `scripts/flashscore_enricher.py`, `scripts/db_report.py`, `scripts/analyze_betclic_learning.py`, `src/bet/db/repositories.py` - active code paths still inside this review pass.
- current regression anchors in this pass - `tests/test_fetch_api_stats.py`, `tests/test_db_repositories.py` - focused tests that still directly cover the in-scope runtime surfaces.

### To Be Modified

List of existing code that needs changes or extensions (with file paths and description of changes):

- runtime data-flow and source-policy files in this pass - `scripts/fetch_api_stats.py`, `scripts/flashscore_enricher.py`, `scripts/db_report.py`, `scripts/analyze_betclic_learning.py`, `src/bet/api_clients/unified.py`, `src/bet/api_clients/sofascore.py`, `src/bet/db/repositories.py` - review and fix stale source routing, dead aliases/imports, repository contract drift, and reporting/documentation mismatches.
- temporary/deleted script surfaces - `scripts/_extract_legit.py`, `scripts/_tmp_db_check.py`, `scripts/_validate_coupon.py`, `scripts/deep_analysis_pool.py`, `scripts/verify_betclic_odds.py`, plus untracked operational scripts - decide whether each is a valid branch surface or should be removed/deferred and make sure no live references remain.
- documentation and orchestration surfaces still in this pass - `.github/agents/bet-enricher.agent.md`, `.github/agents/bet-orchestrator.agent.md`, `.github/agents/bet-settler.agent.md`, `.github/copilot-instructions.md`, `.github/instructions/analysis-methodology.instructions.md`, `.github/internal-prompts/bet-enrich.prompt.md`, `.github/prompts/ask-betting.prompt.md`, `.github/prompts/orchestrate-betting-day.prompt.md`, `.github/skills/bet-settling-results/SKILL.md`, `memories/repo/pipeline-knowledge-base.md` - align docs, prompts, and repo memory with the actual landed runtime behavior in the non-SofaScore slice.
- config boundary - `config/betting_config.json` - inspect only if branch review finds a runtime contract dependency tied to the modified config state.

### To Be Created

List of new components, functions, utilities that need to be built from scratch:

- additional targeted regression tests under `tests/` only where the review uncovers an unprotected contract that is not already covered by the current test suite.
- small follow-up notes or supersession markers in existing spec artifacts when the review closes a gap or invalidates an older assumption.
- no new production runtime modules by default; create a new runtime helper only if the review proves an existing contract cannot be fixed safely within the current owning file.

## Open Questions

| #   | Question   | Answer   | Status                |
| --- | ---------- | -------- | --------------------- |
| 1   | Should this work be anchored on `sofascore-non-discovery-cleanup.plan.md` with one more phase, or split into a separate plan? | Split into a separate plan and explicitly exclude that feature slice, because the user confirmed it is already being implemented in another agent. | ✅ Resolved |
| 2   | Are generated coupon markdown/json/pdf files part of the manager-led review scope? | No. Treat them as generated/live output and ignore them unless a changed runtime contract requires read-only inspection for debugging. | ✅ Resolved |
| 3   | Should `config/betting_config.json` be reviewed as part of this pass? | Only if a changed script or test now depends on its modified schema/keys. Otherwise leave it out of the implementation slice. | ✅ Resolved |
| 4   | Should `tsh-code-reviewer` be used only at the end? | No. Use it mid-pass after the main runtime/test slices and again as the final gate. | ✅ Resolved |

## Technical Context

Project conventions, coding standards, and patterns discovered during planning. Downstream agents MUST read this section instead of re-discovering the same context.

### Project Instructions

- `.github/copilot-instructions.md` defines the bet repo as an agent-driven betting pipeline. Relevant rules for this plan: DB-first where possible, never use `pipeline_orchestrator.py`, avoid broad unrelated refactors, fix root causes instead of surface-only patches, and keep Betclic handling conditional.
- Workspace/user memory adds critical execution constraints: fish shell only, no inline Python terminal one-liners, no batch loops, read code before rerunning scripts, and treat Betclic learning as advisory only.
- This task is planning-only. No runtime implementation or git push is allowed in this session, but the plan must be concrete enough for a manager to delegate to `tsh-software-engineer` and `tsh-code-reviewer` in Full Implementation Flow.

### Architecture & Patterns

- The repo is a Python monorepo with reusable code in `src/bet/` and orchestration/CLI scripts in `scripts/`.
- The active branch already combines multiple related efforts, but this plan covers only the non-SofaScore slice because the non-discovery SofaScore cleanup is parallel-owned by another agent.
- Shared routing policy should converge on the owning abstractions that already exist:
  - `scripts/fetch_api_stats.py` and `src/bet/api_clients/unified.py` for provider routing in this pass
  - `scripts/flashscore_enricher.py`, `scripts/db_report.py`, and `src/bet/db/repositories.py` for the remaining runtime/reporting contracts in this pass
- Existing feature plans are implementation inputs, but `sofascore-non-discovery-cleanup.plan.md` is explicitly parallel-owned and excluded from this review pass.

### Tech Stack

- Python `>=3.11` from `pyproject.toml`
- Runtime libraries in the touched slice: `requests`, `beautifulsoup4`, `playwright`, `lxml`, `pydantic`, `sqlalchemy`, `rapidfuzz`
- Test stack: `pytest`, `pytest-asyncio`
- Persistence: SQLite-backed pipeline data, primarily under `betting/data/`

### Code Style & Standards

- Prefer existing owning abstractions over introducing new ones. If a routing, persistence, or helper boundary already exists, fix it there.
- Preserve stable output contracts unless the review explicitly changes them and updates the owning tests/docs in the same slice.
- Keep changes fish-safe when documenting validation commands.
- Do not pull generated betting outputs into code review, and do not revert unrelated dirty files.

### Testing Patterns

- The repo uses `pytest` from the workspace root, with `testpaths = ["tests"]` in `pyproject.toml`.
- Focused validation should prefer narrow commands over a broad repo-wide test run.
- Relevant validation anchors for this branch are expected to include:
  - `PYTHONPATH=src .venv/bin/pytest -q tests/test_fetch_api_stats.py tests/test_db_repositories.py`
  - `PYTHONPATH=src .venv/bin/python -m py_compile ...` for touched runtime files
- Documentation-only slices should be validated with targeted stale-reference searches and file-existence checks rather than broad test runs.

### Database Patterns

- DB-first remains the preferred runtime pattern. `get_db()` and repository classes under `src/bet/db/` are the intended persistence layer where applicable.
- The touched branch surfaces rely heavily on `fixtures`, `match_stats`, `team_form`, and settlement-related repository/query behavior.
- The branch review must preserve the current Branch B settlement boundary described in repo memory and must not modify settlement-owned files that are part of the parallel SofaScore cleanup slice.

### Additional Context

- Branch context at planning time: `fix/pipeline-data-flow-holes`, with `origin/fix/pipeline-data-flow-holes` already present. The task is to review and harden the current dirty worktree on top of that branch state, not to design a new branch.
- The active worktree contains modified, deleted, and untracked files across runtime, tests, docs, and specs. The manager should treat untracked helper/test/spec files as potentially intentional branch content and review them explicitly instead of ignoring them as noise.
- The largest non-code dirty surfaces are coupon outputs and PDFs. These should not be allowed to expand the implementation or review scope.

## Implementation Plan

### Phase 1: Scope Freeze and Findings Baseline

#### Task 1.1 - [CREATE] Build the branch review ledger and scope fence

**Description**: Use this plan as the manager-owned ledger for the review pass. Before any fixes, map every dirty file into one of four buckets: runtime code, tests, docs/specs/memory, or generated artifacts to ignore.

**Definition of Done**:

- [ ] The manager has a written list of in-scope dirty files grouped by runtime, tests, docs/specs, and config.
- [ ] Coupon markdown/json/pdf outputs, backup files, and `.DS_Store` are explicitly marked as ignored artifacts.
- [ ] The active Flashscore feature plans are recorded as context inputs, and the non-discovery SofaScore cleanup plan is explicitly recorded as parallel-owned and out of scope for this pass.

#### Task 1.2 - [REUSE] Run the first `tsh-code-reviewer` pass on the in-scope branch slice

**Description**: Ask `tsh-code-reviewer` to review only the in-scope code, test, doc, and spec files from Task 1.1. Capture findings by severity and map them into the implementation phases below.

**Definition of Done**:

- [ ] The initial review findings are captured in manager notes or the plan changelog.
- [ ] Critical and high-severity findings are grouped by owning slice instead of treated as one mixed backlog.
- [ ] No generated coupon artifacts or unrelated live data files are reviewed as code.

### Phase 2: Remaining Runtime and Support-Script Review/Fix

#### Task 2.1 - [MODIFY] Review and fix the remaining provider routing, repository, and reporting contracts

**Description**: Audit the current branch changes in `scripts/fetch_api_stats.py`, `scripts/flashscore_enricher.py`, `scripts/db_report.py`, `scripts/analyze_betclic_learning.py`, `src/bet/api_clients/unified.py`, `src/bet/api_clients/sofascore.py`, and `src/bet/db/repositories.py` to ensure provider-routing, repository writes, and reporting behavior remain consistent in the non-SofaScore slice.

**Definition of Done**:

- [ ] Provider-routing and repository/reporting decisions are consistent across `src/bet/` and `scripts/` surfaces still in scope.
- [ ] Any remaining SofaScore or Flashscore usage in these files is intentional, justified, and documented by the code/tests/docs changed in the same slice.
- [ ] No stale alias, dead import, or divergent contract remains after the fix.

#### Task 2.2 - [MODIFY] Review deleted utility scripts and still-in-scope operational entrypoints

**Description**: Review deleted utility scripts (`scripts/_extract_legit.py`, `scripts/_tmp_db_check.py`, `scripts/_validate_coupon.py`, `scripts/deep_analysis_pool.py`, `scripts/verify_betclic_odds.py`) and any still-in-scope operational additions to ensure the branch does not leave orphan entrypoints, undocumented support scripts, or stale references.

**Definition of Done**:

- [ ] No live code, tests, prompts, or docs reference a deleted script that is no longer part of the branch.
- [ ] Each remaining operational script is either accepted as part of the branch with clear purpose and validation coverage or explicitly deferred out of scope.
- [ ] The final branch state does not contain mystery CLI entrypoints with no owner, no spec, and no validation story.

### Phase 3: Tests, Docs, Memory, and Prompt Alignment

#### Task 3.1 - [MODIFY] Review current regression tests and add missing branch-level coverage only where needed

**Description**: Audit `tests/test_fetch_api_stats.py` and `tests/test_db_repositories.py` first, then add new coverage only if the initial code review finds an unprotected contract in the remaining non-SofaScore branch slice.

**Definition of Done**:

- [ ] Existing tests reflect the current in-scope branch behavior instead of pre-review assumptions.
- [ ] New regression tests are added only for uncovered contracts discovered during the review.
- [ ] Test changes do not overlap the parallel-owned SofaScore cleanup slice.

#### Task 3.2 - [MODIFY] Review agent, prompt, instruction, and repo-memory surfaces against the landed runtime behavior

**Description**: Audit `.github/agents/bet-enricher.agent.md`, `.github/agents/bet-orchestrator.agent.md`, `.github/agents/bet-settler.agent.md`, `.github/copilot-instructions.md`, `.github/instructions/analysis-methodology.instructions.md`, `.github/internal-prompts/bet-enrich.prompt.md`, `.github/prompts/ask-betting.prompt.md`, `.github/prompts/orchestrate-betting-day.prompt.md`, `.github/skills/bet-settling-results/SKILL.md`, and `memories/repo/pipeline-knowledge-base.md`.

**Definition of Done**:

- [ ] No deleted script names, stale source-policy descriptions, or wrong pipeline-step counts remain in the in-scope documentation surfaces.
- [ ] Orchestrator and specialist documentation match the current run-then-delegate model and the reviewed non-SofaScore runtime behavior.
- [ ] Repo memory accurately documents the current branch truth without claiming ownership of the parallel SofaScore cleanup slice.

#### Task 3.3 - [REUSE] Reconcile the config/data boundary without widening scope

**Description**: Inspect `config/betting_config.json` and any read-only data artifact only if a reviewed runtime slice depends on it. Keep generated betting outputs outside the code review unless a concrete contract check requires them.

**Definition of Done**:

- [ ] Config changes are either confirmed as intentional and compatible with the reviewed code or explicitly removed from this review slice.
- [ ] No generated coupon or PDF artifact becomes a blocker for closing the code review.
- [ ] The manager can explain exactly why any config or data artifact was included in the final branch scope.

### Phase 4: Focused Validation and Review Gates

#### Task 4.1 - [REUSE] Run focused executable validation after each implementation slice

**Description**: After every runtime/test slice, run the narrowest commands that can falsify the current fix before moving on. Keep commands fish-safe and scoped to the touched files.

**Definition of Done**:

- [ ] Runtime slices use narrow validation such as `PYTHONPATH=src .venv/bin/python -m py_compile ...` on the touched files.
- [ ] Test slices use narrow `pytest` commands against the owning test modules instead of a broad repo-wide run.
- [ ] Documentation-only slices are validated with targeted stale-reference/file-existence checks.
- [ ] Validation results are captured in manager notes before the next slice begins.

#### Task 4.2 - [REUSE] Run the mid-pass `tsh-code-reviewer` gate after Phases 2-3

**Description**: Once the main runtime and test fixes are in place and focused validation is green, run `tsh-code-reviewer` again before widening into the final documentation/spec cleanup.

**Definition of Done**:

- [ ] The mid-pass review runs after focused validation, not before it.
- [ ] Critical and high findings from the mid-pass review are resolved or explicitly triaged before Phase 4 closes.
- [ ] The manager does not open a fresh implementation slice without rerunning the relevant focused validation after each fix.

#### Task 4.3 - [REUSE] Run the final `tsh-code-reviewer` gate

**Description**: After all branch slices are aligned and focused validation passes, run the final review gate to confirm the branch is ready for commit/push preparation.

**Definition of Done**:

- [ ] The final review runs after the final focused validation pass.
- [ ] No unresolved critical or high-severity review findings remain.
- [ ] Remaining medium/low issues are either fixed or explicitly documented as follow-up items.

### Phase 5: Final Git Readiness and Manager Handoff

#### Task 5.1 - [REUSE] Triage the final dirty worktree into commit candidates versus ignored artifacts

**Description**: Use git status and diff views to classify the remaining dirty files. Keep the commit-ready set limited to the reviewed code/test/doc/spec surfaces and exclude generated coupon artifacts and other ignored files.

**Definition of Done**:

- [ ] The final `git status --short` output is grouped into commit candidates and ignored artifacts.
- [ ] Generated coupon/json/pdf outputs, backup files, and `.DS_Store` are excluded from the commit-ready set.
- [ ] Reviewed spec and memory updates stay paired with the runtime behavior they document.

#### Task 5.2 - [REUSE] Produce the manager handoff summary for Full Implementation Flow

**Description**: Summarize the ordered implementation slices, resolved review findings, validation evidence, remaining optional follow-ups, and the final commit-ready file set. This is the handoff artifact the manager uses before manual commit/push.

**Definition of Done**:

- [ ] The manager has an ordered list of completed slices and any remaining optional follow-ups.
- [ ] Validation evidence and final review outcomes are summarized in one place.
- [ ] The branch is ready for manual commit/push decisions, but no push is performed as part of this task.

## Security Considerations

- Review for stale third-party source paths, dead helper aliases, and documentation drift that could silently reintroduce blocked or brittle runtime behavior.
- Do not widen scope into credential handling or Betclic scraping beyond the already-approved branch surfaces.
- Excluding generated coupon artifacts from the commit-ready set reduces the risk of accidentally publishing live betting data or noisy outputs.

## Quality Assurance

Acceptance criteria checklist to verify the implementation meets the defined requirements:

- [ ] The manager can point to a clear in-scope file set and a clear ignore list before implementation starts.
- [ ] Runtime source-policy, repository, reporting, and support-script changes in the non-SofaScore slice are validated by focused automated checks.
- [ ] Deleted scripts and remaining support-script surfaces are either reviewed into the branch or explicitly deferred.
- [ ] `tsh-code-reviewer` is used both mid-pass and as the final gate.
- [ ] The final dirty worktree is triaged into commit-ready branch content versus generated/live artifacts to ignore.

## Improvements (Out of Scope)

Potential improvements identified during planning that are not part of the current task:

- Rebuilding or regenerating coupon markdown/json/pdf outputs for historical betting days.
- Reopening discovery architecture or unrelated pipeline redesign beyond the current dirty branch surfaces.
- Broad cleanup of unrelated config or live data files that are not required by the reviewed runtime contracts.
- New enrichment features or source additions that are not justified by current branch review findings.

## Execution Progress

### Completed In This Review Pass

- Initial and final `tsh-code-reviewer` gates were run for the narrowed non-SofaScore slice, ending with explicit zero remaining findings.
- Obsolete tests for the removed `scripts.deep_analysis_pool` surface were deleted, and repo-wide test collection recovered successfully.
- `scripts/analyze_betclic_learning.py` was corrected to keep DB-first behavior authoritative, use JSON only as fallback, avoid false missing-file warnings for empty JSON, and preserve DB data when JSON is unreadable.
- `src/bet/db/repositories.py` was corrected to keep the sport-name cache instance-scoped, seed hockey as Tier 1, clear stale `l5_avg` / `l10_avg` values when all filtered inputs are rejected, and clarify `FixtureRepo.bulk_upsert()` transaction ownership.
- `src/bet/api_clients/api_basketball.py` was improved with a reusable dynamic season helper, fixture-side lookup via `/games`, and an explicit warning when home/away assignment falls back to response order.
- Regression coverage was added or tightened in `tests/test_analyze_betclic_learning.py`, `tests/test_db_repositories.py`, and `tests/test_api_basketball.py` to protect the fixed contracts.
- `.github/agents/bet-enricher.agent.md` and `.github/internal-prompts/bet-enrich.prompt.md` were aligned with the current enrichment flow, fallback-layer count, validation commands, and markdown/code-block correctness.
- `memories/repo/pipeline-lessons-learned.md` was added to restore a missing repo-memory reference used by the reviewed agent/prompt surfaces.

### Validation Evidence

- Focused validation passed: `PYTHONPATH=src .venv/bin/pytest -q tests/test_analyze_betclic_learning.py tests/test_db_repositories.py tests/test_api_basketball.py`
- Compilation validation passed: `PYTHONPATH=src .venv/bin/python -m py_compile scripts/analyze_betclic_learning.py src/bet/db/repositories.py src/bet/api_clients/api_basketball.py`
- Collection validation passed earlier in the review pass: `PYTHONPATH=src .venv/bin/pytest -q --collect-only tests`

### Still Pending

- Final git-worktree triage into commit candidates, ignored generated artifacts, and parallel-owned SofaScore cleanup files left untouched.
- Final manager handoff for manual commit/push decision once git triage confirms a safe commit set.

## Changelog

| Date   | Change Description   |
| ------ | -------------------- |
| 2026-05-20 | Initial plan created for manager-led branch review pass on `fix/pipeline-data-flow-holes` |
| 2026-05-20 | Plan narrowed to exclude `specifications/sofascore-non-discovery-cleanup.plan.md` and its owned file slice after the user clarified that work is being done in another agent |
| 2026-05-20 | Review/fix execution recorded for the narrowed non-SofaScore slice, including DB-first Betclic-learning repair, repository fixes, basketball API hardening, prompt/agent alignment, and regression coverage updates |
| 2026-05-20 | Final review gate reached zero remaining findings; git-worktree triage left as the final pending step before any manual commit/push decision |