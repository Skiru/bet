# Plan Review: orchestrator-brave-search-optimization.plan.md

- Reviewed plan path: [orchestrator-brave-search-optimization.plan.md](./orchestrator-brave-search-optimization.plan.md)
- Research file path: [orchestrator-brave-search-optimization.research.md](./orchestrator-brave-search-optimization.research.md)
- Review date: 2026-05-26
- Verdict: `APPROVED`

Summary:

- Blockers: 0
- Warnings: 2
- Suggestions: 2

## Challenge Domains

### Ownership Placement

- **No issue**: The revised plan makes `async-wait-overlap.md` the sole canonical owner and limits shared resources to generic baselines or backlink-only mentions.

### Concurrency Safety

- **No issue**: The revised plan defines explicit, testable control knobs for trigger threshold, active-stage scope, and Brave query budget.

### Validation Realism

- **No issue**: The revised plan upgrades validation to a two-layer touched-file gate derived from the existing customization suite while keeping global drift out of scope.

### Scope Control

- **No issue**: The plan stays out of runtime pipeline code and avoids drifting into betting methodology or script changes.

### Repo Reality

- **Finding**: Broader customization drift still exists in the live `.github` tree, but the revised plan now treats it as an explicit out-of-scope baseline condition rather than ignoring it.

## Decision And Revision History

| Date | Iteration | Decision / Topic | Problem / Challenge | Plan Decision / Change | Status |
| --- | --- | --- | --- | --- | --- |
| 2026-05-26 | 1 | Workflow-layer ownership | Good direction, but shared resources may be too broad for orchestrator-only behavior | Needs tighter scoping or explicit consumer impact analysis | open |
| 2026-05-26 | 1 | Aggressive Brave overlap policy | Trigger threshold, search scope, and query budget remain unspecified | Needs explicit policy fields in plan and acceptance | open |
| 2026-05-26 | 1 | Validation strategy | Narrow regex test can miss contradictory customization baseline | Needs stronger validation story or documented boundary | open |
| 2026-05-26 | 2 | Workflow-layer ownership | Canonical owner narrowed to `async-wait-overlap.md`; shared resources stay generic/backlink-only | Opt-in wiring through prompt and skill only | resolved |
| 2026-05-26 | 2 | Aggressive Brave overlap policy | Explicit `>120s` trigger, active-stage-frontier scope, and two-pack/three-query budget added | Policy became testable and bounded | resolved |
| 2026-05-26 | 2 | Validation strategy | Two-layer touched-file acceptance added using feature assertions plus touched-file integrity checks | Scoped validation now credible for touched artifacts | resolved |

## Top Failure Modes

- Shared baseline files drift from backlink-only mentions into second policy owners during implementation.
- The targeted test module misses one of the touched-file integrity invariants and gives a weaker signal than the revised plan expects.
- The prompt or skill body starts duplicating the canonical trigger/scope/budget table instead of referencing the resource.

## Unproven Assumptions

- Implementers will keep any shared-file edits backlink-only and resist the temptation to restate policy text in multiple places.
- The targeted pytest module will mirror the relevant touched-file integrity checks precisely enough to catch drift in the modified artifacts.
- The active-stage-frontier rule is sufficient to keep the aggressive policy bounded without needing broader session-level orchestration changes.

## Most Likely Rework Triggers

- Discovering during implementation that a shared resource was edited beyond a backlink and now duplicates the canonical policy.
- Discovering that the targeted test module does not fully cover the touched prompt/skill/resource invariants promised by the plan.
- Discovering that touched-file validation relies on assumptions from the global customization suite that were not actually mirrored locally.

## Questions The Architect Must Answer Before Coding

- No execution-critical open questions remain for planning. The remaining risk is implementation discipline against the approved ownership and validation boundaries.

## BLOCKERS

- None after iteration 2. The prior blockers were resolved by explicit policy knobs, opt-in ownership placement, and a stronger touched-file validation story.

## WARNINGS

### 1. Source-of-truth drift is acknowledged but not absorbed into the execution strategy

Broader customization drift still exists outside this task. The revised plan handles it acceptably by scoping acceptance to touched artifacts, but implementers must not quietly expand this work into a repo-wide cleanup.

### 2. Handoff-contract changes can become duplication magnets

The approved plan keeps the async-wait addendum in the canonical resource. If implementation touches shared handoff files anyway, those edits must remain backlink-only.

## SUGGESTIONS

### 1. Treat the aggressive policy as a bounded default

Keep the explicit trigger/scope/budget table together in the canonical resource and avoid splitting pieces of it across prompt or skill prose.

### 2. Prefer the narrowest ownership surface that still avoids duplication

If a shared baseline file truly needs a mention, use one backlink sentence to the canonical resource and let the dedicated test assert that the file did not become a second owner.

## Verdict

`APPROVED`