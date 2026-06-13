# FOOTBALL GOLDEN VERTICAL — Provider-Decoupled Final Production Closure

## Model

Use **GPT-5.4 with reasoning effort HIGH** in a fresh session on the current worktree.

This is the final execution run. Do not perform another broad audit, redesign,
or provider survey.

## Starting state

Keep:

`FOOTBALL_VERTICAL_STATE=PARTIAL`

until all execution gates below pass.

The latest live proof established that API-Football access to the required 2026
target is `PLAN_RESTRICTED`. This is an external provider-plan limitation, not
a parser or request-construction defect.

Do not:

- substitute season 2024 for a 2026 target;
- weaken request identity;
- require API-Football to participate in the current-2026 workflow when the
  active key cannot access that season;
- treat provider-specific plan access as a blocker for the whole football
  vertical when another verified route closes the capability.

## Objective

Certify football in two independent scopes:

### A. Current operational scope

Execute one real current/upcoming 2026 football workflow using providers that
are actually available for the active credentials.

Expected current primary:

- ESPN for current discovery and enrichment.

API-Football current-season role:

- `PLAN_RESTRICTED`;
- non-retryable;
- observable;
- capability-specific negative cached;
- not called repeatedly after the restriction is known.

### B. Cross-provider mechanics scope

Prove real API-Football ↔ ESPN identity and crosswalk behavior using one
plan-accessible real historical event.

The event must have:

- a real API-Football fixture ID;
- real API-Football team IDs;
- an independently discovered real ESPN event ID;
- real ESPN participant IDs;
- mapped competition;
- identical canonical participant set;
- kickoff within the configured tolerance.

Do not use synthetic, shadow, or copied IDs.

The historical crosswalk proves provider-agnostic identity mechanics. It does
not claim that API-Football supports the current 2026 season for the active key.

## First action — validate the current worktree

Read only:

- current checkpoint;
- current diff;
- capability contract;
- capability router;
- fixture-scoped observation/projection repositories;
- downstream snapshot reader;
- latest live proof output;
- current audit artifacts.

Verify the latest claimed files actually exist, including:

- schema and migration 016/017 as applicable;
- `tests/e2e/test_football_truthful_live.py`;
- `tests/football/test_truthful_closure_regressions.py`.

The previously uploaded certification ZIP is stale and incomplete. Do not reuse
its `FINAL_RESULT.json`.

## Gate 1 — freeze provider roles

Update routing semantics before live execution:

### Current 2026

- ESPN: primary current discovery/enrichment route where capability-proven.
- API-Football: `PLAN_RESTRICTED` for inaccessible 2026 operations.
- Do not attempt API-Football repeatedly for a negatively cached
  capability/season restriction.

### Historical accessible scope

- API-Football: eligible discovery/enrichment source only for live-proven
  accessible seasons.
- ESPN: independent crosswalk/enrichment source.

Provider state must be capability- and temporal-scope-specific.

Do not label all of API-Football `PRODUCTION_READY`.

## Gate 2 — optional current redundancy probe

Current production readiness may use one verified source, but redundancy must
be reported explicitly.

Only when a rotated `SPORTDB_API_KEY` exists, allow a maximum of **four**
SportDB.dev calls to test a second current-2026 discovery route:

1. discover competition/season;
2. discover a current fixture and native IDs;
3. fetch that match by native SportDB ID;
4. one identity/participants verification call if needed.

Use current official endpoint shapes and native SportDB IDs.

If it passes identity, temporal and evidence gates, use SportDB as current
discovery fallback.

If it fails or credentials are absent, do not block certification. Report:

`CURRENT_REDUNDANCY=SINGLE_SOURCE`

Do not implement or probe TheSportsDB in this run.

## Gate 3 — execute current 2026 E2E

Using a real 2026 target, execute actual production entry points:

`current discovery
-> canonical fixture
-> capability router
-> immutable source observations
-> selected fixture-scoped projections
-> normalized snapshot
-> downstream football analysis read`

For every P0 capability record:

- attempted sources and typed statuses;
- selected source;
- native IDs;
- exact request identity;
- evidence bundle;
- analysis cutoff;
- observation and projection IDs;
- normalized downstream value or explicit transient `UNKNOWN`.

No manually inserted final observations or projections count as E2E proof.

## Gate 4 — execute historical real cross-provider proof

Select one plan-accessible historical football event.

Run actual API-Football discovery and independently resolve the ESPN event.

Persist two distinct source mappings to one canonical fixture.

Test:

- zero candidates -> `NOT_FOUND`;
- multiple candidates -> `AMBIGUOUS`;
- exact one candidate -> persisted mapping;
- wrong participants -> rejected;
- kickoff outside tolerance -> rejected.

This gate validates the reusable cross-provider identity pattern for later
sports without falsely claiming current API-Football 2026 access.

## Gate 5 — offline replay

Retain exact sanitized raw objects and deterministic bundles for:

- current 2026 discovery;
- every selected current P0 enrichment route;
- historical API-Football discovery;
- historical ESPN event resolution/crosswalk.

Block all network at the shared transport/socket boundary and replay through:

`parser -> router -> observation persistence -> projection -> snapshot ->
downstream reader`

Prove:

- exact request identity;
- semantic equality;
- unexpected request fails;
- missing/corrupt evidence fails closed.

Mocked parsed values are not replay proof.

## Gate 6 — production double-run and versioning

Use a disposable database.

Execute the full current-2026 workflow twice with identical evidence.

Compare counts and sorted logical identities for:

- canonical fixtures;
- source mappings;
- source observations;
- selected projections;
- normalized P0 data;
- evidence links;
- final snapshot.

Every second-run logical delta must be zero.

Then modify retained evidence deterministically and prove:

- a new append-only observation is created;
- the old observation remains queryable;
- the projection follows selection policy;
- no historical evidence link is overwritten.

## Gate 7 — failure injection

Execute:

- API-Football `PLAN_RESTRICTED`;
- current-primary transport failure;
- malformed payload;
- corrupt evidence;
- ambiguous historical crosswalk;
- source disagreement.

Verify attempted-source history, fail-closed behavior and truthful downstream
status.

## Gate 8 — final validation

Run:

1. focused current-routing and historical-crosswalk tests;
2. real current-2026 E2E;
3. historical real cross-provider proof;
4. no-network replay;
5. complete production double-run;
6. versioning and failure injection;
7. migration tests with foreign keys enabled;
8. strict marker validation;
9. Ruff on every touched source/test file with zero errors;
10. compile/static checks;
11. secret scan;
12. full non-live suite exactly once.

## Final state semantics

Set:

`FOOTBALL_VERTICAL_STATE=PRODUCTION_READY`

when:

- every current P0 capability has a verified current route or policy-approved
  transient state;
- current 2026 E2E passes;
- historical real API-Football/ESPN crosswalk proof passes;
- API-Football plan restriction remains explicit;
- offline replay passes;
- second-run logical deltas are zero;
- changed-evidence history is preserved;
- failure injection passes;
- audit artifacts are consistent;
- certification bundle validates.

Current multi-source redundancy is **not** a hard blocker. Report it separately:

- `MULTI_SOURCE_CURRENT`, or
- `SINGLE_SOURCE_CURRENT`.

Do not claim current API-Football coverage when it is plan-restricted.

## Certification bundle

Create a fresh:

`FOOTBALL_GOLDEN_FINAL_CERTIFICATION_BUNDLE.zip`

Include:

- real base/head commit hashes;
- scoped patch and exact changed-file list;
- all changed code/schema/migrations/tests;
- audit files;
- capability/routing/end-to-end/certification index JSON;
- every cited manifest and raw object;
- request identities;
- current E2E output;
- historical crosswalk output;
- replay output;
- idempotency/versioning/failure outputs;
- lint/static/full-suite/secret outputs.

Exclude prompts, stale bundles, `.DS_Store`, caches and unrelated changes.

Extract to a clean directory, set `EVIDENCE_ROOT` to extracted evidence,
recompute hashes and run offline replay with zero network.

## Final response

Return only:

RESULT: PASS | PARTIAL | FAIL
FOOTBALL_VERTICAL_STATE: <state>
CURRENT_REDUNDANCY: MULTI_SOURCE_CURRENT | SINGLE_SOURCE_CURRENT

CURRENT_2026:
target=<real IDs>
p0_routes=<capability -> source/status/bundle>
e2e=<PASS/FAIL>

API_FOOTBALL_CURRENT:
status=PLAN_RESTRICTED
negative_cache=<PASS/FAIL>
repeated_calls_suppressed=<PASS/FAIL>

HISTORICAL_CROSS_PROVIDER:
api_football=<real IDs>
espn=<real IDs>
crosswalk=<PASS/FAIL>

REPLAY:
<current and historical results>

IDEMPOTENCY:
<first/second counts and logical deltas>

VERSIONING:
<old/new observation proof>

FAILURE_INJECTION:
<results>

TESTS:
<focused/live/full/lint/static/secret>

AUDIT_CONSISTENCY:
<PASS/FAIL>

CERTIFICATION_BUNDLE:
<path and clean extraction/offline validation>

REMAINING_BLOCKER:
<NONE or exactly one>

CHANGED_FILES:
<paths only>

Stop after football certification.
Do not begin another sport.
