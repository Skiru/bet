# FOOTBALL GOLDEN VERTICAL — Final Execution Closure

Use **GPT-5.4 with reasoning effort HIGH**.

Continue in the current worktree from the existing V3 instruction and checkpoint.

This is not another audit or architecture phase. Execute only the remaining
mandatory gates and stop.

## Binding sources

Re-read:

- the original V3 instruction provided at the beginning of this session;
- `.kilo/artifacts/football_golden_final/checkpoint.json`;
- `.kilo/artifacts/football_golden_final/capability_contract.json`;
- the current git diff;
- the fixture-scoped observation/snapshot models and migration;
- the downstream football analysis reader;
- the capability router and focused tests.

Do not reread superseded reports or old prompts.

## Accepted baseline

Treat as accepted unless a focused regression disproves it:

- canonical result contract work;
- `PLAN_RESTRICTED` classification work;
- capability router implementation;
- fixture-scoped observation schema and migration;
- cross-provider matching tests;
- 171 focused tests passing;
- 807 full non-live tests passing;
- touched new files lint-clean;
- no hardcoded secrets.

Do not refactor accepted code for style.

## Step 1 — resolve the real blocker

The primary blocker is:

`downstream football analysis does not read the fixture-scoped snapshot`

Wire the actual production analysis path to read the selected fixture-scoped,
point-in-time projection.

Requirements:

- lookup is scoped by canonical fixture, non-null team scope, capability and
  `analysis_cutoff_at`;
- no fallback to global mutable `team_form` as snapshot truth;
- `team_form` may remain a latest cache only;
- missing capability data remains explicit `UNKNOWN`, never zero or stale data;
- source status, selected provider, evidence bundle and staleness remain
  observable downstream;
- two fixtures for the same team and different cutoffs return isolated results.

Add focused production-consumer tests.

## Step 2 — decide standings from the binding P0 contract

Read the current capability contract.

If standings is `P0_REQUIRED`:

- wire the smallest existing typed standings route through the capability
  router, fixture-scoped observation and downstream snapshot;
- use an already verified provider where possible;
- make at most two live requests only when retained evidence is insufficient;
- retain raw evidence and support no-network replay.

If standings is `P1_ENHANCEMENT`, `SEPARATE_PIPELINE` or `OUT_OF_SCOPE`:

- do not implement it;
- remove it from the current production blocker;
- preserve the truthful classification and rationale.

Do not change the capability classification merely to obtain PASS. Change it
only if the betting-analysis contract proves the prior classification wrong.

## Step 3 — run one real end-to-end football workflow

Use the real cross-provider 2026 fixture already selected by V3, or select one
only if the existing target is invalid.

Execute through production entry points:

`production discovery
-> canonical fixture
-> provider source mappings
-> typed capability router
-> source observations
-> point-in-time selected projections
-> fixture-scoped snapshot
-> downstream football analysis read`

For every P0 capability record:

- attempted sources and statuses;
- selected provider;
- native source IDs;
- exact evidence bundle;
- cutoff and temporal eligibility;
- persisted observation/projection identity;
- downstream value or explicit transient `UNKNOWN`.

Synthetic IDs, names-only matching and manually constructed final repository
rows are forbidden.

## Step 4 — offline replay

Using retained evidence:

- block all outbound network at the actual shared transport/socket boundary;
- replay every selected P0 capability through parser, router, persistence and
  downstream snapshot;
- prove exact request-identity matching;
- compare semantic output and diagnostics;
- prove an unexpected request fails;
- prove missing or corrupt evidence fails closed.

Manifest or hash verification alone is not replay proof.

## Step 5 — duplicate-free second run and versioning

Use a disposable database.

Run the complete production football workflow twice with identical retained
evidence.

Compare counts and sorted logical identities for:

- canonical fixtures;
- source mappings;
- source observations;
- selected projections;
- form/stat rows;
- evidence links;
- final snapshots.

Every second-run logical delta must be zero.

Then use deterministically modified evidence and prove:

- a new append-only observation/version is created;
- the previous observation remains queryable;
- the selected projection follows policy;
- no historical evidence relation is overwritten.

SQLite upsert behavior must be backed by actual `UNIQUE`, `PRIMARY KEY`, or
unique-index constraints; do not infer idempotency merely from repository method
names.

## Step 6 — failure injection

Execute focused deterministic cases for:

- `PLAN_RESTRICTED`;
- transport failure;
- malformed payload;
- corrupt evidence;
- ambiguous provider mapping;
- source disagreement.

Verify:

- attempted-source history is preserved;
- fallback policy is capability-specific;
- fallback success does not erase the primary failure;
- ambiguity and corrupt evidence fail closed;
- downstream snapshot exposes truthful status.

## Step 7 — final quality and certification

Run:

1. focused changed-area tests;
2. strict marker validation;
3. no-network replay;
4. duplicate-free complete rerun;
5. versioning tests;
6. Ruff on every touched production/test file with zero errors;
7. static/compile checks;
8. secret scan;
9. full non-live suite exactly once after final code state.

Then create and validate:

`FOOTBALL_GOLDEN_FINAL_CERTIFICATION_BUNDLE.zip`

It must contain the scoped patch, changed files, capability/routing/certification
JSON, audit artifacts, every cited manifest and raw object, request identities,
test outputs, migration proof, replay proof and idempotency identities.

Extract it into a clean temporary directory, point `EVIDENCE_ROOT` to the
extracted evidence, recompute hashes and run offline replay with zero network
access.

## Documentation limit

Update only the authoritative existing audit files and V3 machine-readable
artifacts.

Do not create another design or audit report.

## Final-state rule

Set `PRODUCTION_READY` only when:

- downstream analysis reads fixture-scoped point-in-time snapshots;
- every P0 capability has a verified route or policy-approved transient state;
- standings is implemented only if genuinely P0;
- the real E2E workflow passes;
- offline replay passes;
- second-run logical deltas are zero;
- changed evidence preserves history;
- failure injection passes;
- touched-file lint is clean;
- audit truth agrees;
- the extracted certification bundle validates.

Otherwise return `PARTIAL` with exactly one highest-priority blocker.

## Final response

Return only:

RESULT: PASS | PARTIAL | FAIL
FOOTBALL_VERTICAL_STATE: <state>

DOWNSTREAM_SNAPSHOT:
<production path, fixture/cutoff isolation, result>

STANDINGS:
<classification and route or NOT_REQUIRED>

END_TO_END:
<target fixture and per-P0 results>

REPLAY:
<per-P0 result, network blocked>

IDEMPOTENCY:
<first/second counts and logical deltas>

VERSIONING:
<old/new observation history>

FAILURE_INJECTION:
<results>

TESTS:
<focused/full/lint/static/secret>

CERTIFICATION_BUNDLE:
<path and extraction/offline validation>

REMAINING_BLOCKER:
<NONE or exactly one>

CHANGED_FILES:
<paths only>

Stop immediately after this football certification gate.
Do not begin another sport or provider family.
