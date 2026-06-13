# FOOTBALL GOLDEN VERTICAL — Truthful Final Execution Closure

Use **GPT-5.4 with reasoning effort HIGH** in a fresh session on the current
worktree.

This is the final corrective execution run. Do not perform another broad audit,
provider survey or architecture redesign.

## Truthful starting state

Immediately restore and preserve:

`FOOTBALL_VERTICAL_STATE=PARTIAL`

until all gates below execute successfully.

The previous final output is invalid because its own `ALIGNMENT_CHECK.json`
records mandatory gates as `FAIL` or `NOT_EXECUTED`.

Do not use `FINAL_RESULT.json` as proof.

## Scope

Fix only these confirmed blockers:

1. production capability router is not actually wired;
2. downstream analysis does not receive normalized fixture-scoped snapshot data;
3. standings uses invalid scope IDs and non-replayable evidence;
4. H2H is P0 but lacks a typed evidence-linked route;
5. cross-provider proof is synthetic;
6. observation identity does not preserve changed evidence;
7. real offline replay and production double-run are absent;
8. certification ZIP is incomplete.

Do not add another provider or another sport.

## 1. Reproduce the defects

Add focused tests proving:

- no production callsite currently invokes `CapabilityResolution`;
- `get_fixture_scoped_form_snapshot()` returns `UNKNOWN` rather than normalized
  form values and ignores `stat_key`;
- standings fails with foreign keys enabled because scope IDs are zero;
- two competitions/cutoffs can collide in the current standings identity;
- changed evidence with the same current unique key is ignored;
- H2H has no typed evidence-linked production route;
- the current “E2E” test does not invoke production discovery or a real
  cross-provider mapping.

Do not continue until each defect is reproduced or directly disproved.

## 2. Wire the router into the real production path

Locate the actual football analysis/snapshot builder.

Make it call a typed capability orchestration service that:

- invokes provider adapters;
- creates immutable source observations;
- applies capability-specific fallback policy;
- persists the selected projection;
- returns attempted-source history and selected result.

The production path must use this service. A helper used only by tests does not
count.

Remove Boolean-only selection from the football critical path.

## 3. Return real snapshot values

Fixture-scoped snapshots must expose the normalized payload needed by analysis,
not only metadata and `value="UNKNOWN"`.

Requirements:

- payload or stable payload reference is persisted;
- form values are scoped by fixture, team, stat/capability and cutoff;
- `stat_key` is used or removed from the public contract;
- missing data remains explicit `UNKNOWN`;
- football never falls back to global `team_form` as historical snapshot truth;
- two fixtures for one team and two cutoffs return different snapshots;
- downstream analysis consumes and tests the resulting values.

## 4. Fix append-only observation identity

Create the next migration; do not rewrite migration 016.

An observation must distinguish materially different evidence. Its immutable
identity must include a stable combination containing:

- scope;
- capability;
- source;
- canonical request identity;
- evidence bundle ID or payload hash;
- valid/cutoff time.

`INSERT OR IGNORE` must not discard changed evidence.

On duplicate input, `save_observation()` must return the existing observation
ID deterministically; do not rely on ambiguous `lastrowid`.

Prove:

- identical evidence deduplicates;
- changed evidence creates a new observation;
- both versions remain queryable;
- projection may change without deleting observation history.

## 5. Model standings with a real scope

Do not use fixture ID 0 or team ID 0.

Choose the smallest generic production-safe identity, for example:

- target fixture + competition/season scope; or
- an explicit non-null scope type and scope ID.

The scope must distinguish competitions and seasons.

Use one verified standings provider route consistent with the capability
contract. If ESPN is selected, update the contract only after a real proof.

The typed standings client must use the canonical evidence transport:

- exact sanitized raw bytes;
- full SHA-256;
- request identity;
- bundle manifest;
- parser diagnostics;
- no-network replay.

A URL plus timestamp is not evidence.

Maximum one new standings live request when retained evidence is insufficient.

## 6. Implement typed P0 H2H

Because H2H is classified P0:

- add a typed result with evidence capture;
- use exact provider team/event IDs;
- apply target exclusion and strict cutoff before `last_n`;
- persist an immutable observation and selected projection;
- expose normalized H2H through the downstream snapshot;
- replay from raw bytes with network blocked.

If the betting contract does not truly require H2H, change the P0 contract only
with direct evidence from the analysis feature contract—not to obtain PASS.

Maximum one new H2H live request when required.

## 7. Prove one real cross-provider 2026 event

Use actual production discovery.

Persist distinct mappings for:

- real API-Football fixture and team IDs;
- independently discovered ESPN event and team IDs.

Match by sport, mapped competition, exact participant set and kickoff tolerance.

Forbidden:

- synthetic fixture IDs;
- `shadow-*`;
- copying one provider ID into another source;
- manually inserting only the ESPN mapping;
- names-only matching.

Maximum four discovery/crosswalk calls total.

## 8. Execute a real E2E workflow

Run through actual production entry points:

`discovery -> canonical fixture -> real source mappings -> capability router ->
observations -> projections -> normalized fixture snapshot -> downstream
analysis read`

For every P0 capability record:

- attempted sources/statuses;
- selected source;
- native IDs;
- exact bundle;
- cutoff;
- observation/projection IDs;
- downstream normalized value or explicit transient unknown.

Tests that manually insert final observations/projections are repository tests,
not E2E proof.

## 9. Offline replay and failure injection

Include exact raw objects for every selected P0 route.

Block network at the actual shared transport/socket boundary and replay:

- discovery;
- recent form;
- H2H;
- standings;
- fixture statistics;
- cross-provider identity where evidence-backed.

Prove an unexpected request fails.

Inject and verify:

- plan restriction;
- transport error;
- malformed payload;
- corrupt evidence;
- ambiguous mapping;
- source disagreement.

Mocking a final parsed result is not replay.

## 10. Real idempotency and versioning

Use a disposable database.

Execute the complete production vertical twice with identical retained evidence.

Compare counts and sorted logical identities for:

- fixtures;
- source mappings;
- observations;
- projections;
- normalized form/H2H/standings/stat data;
- evidence links;
- final snapshots.

All second-run logical deltas must be zero.

Then use modified evidence and prove the old and new observation versions remain
queryable and the projection follows policy.

“Tests passed twice” is not idempotency proof.

## 11. Final validation

Run:

1. focused defect/regression tests;
2. migration tests with foreign keys ON;
3. real E2E test;
4. no-network replay;
5. production double-run;
6. versioning/failure injection;
7. strict marker validation;
8. Ruff on every touched source/test file with zero errors;
9. compile/static checks;
10. secret scan;
11. full non-live suite once.

## 12. Atomic audit and certification bundle

Reconcile matrix, manifest, backlog and current football report only after
execution proof passes.

Create:

- `final_capability_routing.json`;
- `end_to_end_certification.json`;
- `CERTIFICATION_INDEX.json`;
- test/replay/idempotency/migration output files.

Create a new:

`FOOTBALL_GOLDEN_FINAL_CERTIFICATION_BUNDLE.zip`

It must include:

- real base/head commit hashes;
- scoped patch only;
- exact changed-file list;
- all changed code, schema, migration and tests;
- audit artifacts;
- all certification JSON;
- every cited manifest and raw evidence object;
- request identities;
- all validation outputs.

Exclude `.DS_Store`, prompts, unrelated providers, caches and unrelated ZIPs.

Extract it into a clean directory, set `EVIDENCE_ROOT` to extracted evidence,
recompute hashes and run offline replay with zero network.

## Final-state rule

`PRODUCTION_READY` is allowed only if every requirement above is executed and
`CERTIFICATION_INDEX.json` links each claim to code, test, evidence and
persistence identity.

Otherwise return `PARTIAL` with exactly one blocker.

## Final response

Return only:

RESULT: PASS | PARTIAL | FAIL
FOOTBALL_VERTICAL_STATE: <state>

PRODUCTION_ROUTER:
<entry point and PASS/FAIL>

SNAPSHOT:
<normalized payload, scope and downstream read>

REAL_TARGET:
<canonical/API-Football/ESPN IDs and crosswalk>

P0_CAPABILITIES:
<route, bundle and status per capability>

REPLAY:
<per capability, network blocked>

IDEMPOTENCY:
<first/second counts and logical deltas>

VERSIONING:
<old/new observation proof>

TESTS:
<focused/e2e/full/lint/static/secret>

AUDIT_CONSISTENCY:
<PASS/FAIL>

CERTIFICATION_BUNDLE:
<path and clean extraction/offline result>

REMAINING_BLOCKER:
<NONE or exactly one>

CHANGED_FILES:
<paths only>

Stop after football certification. Do not begin another sport.
