# FOOTBALL GOLDEN VERTICAL V3 — Final Production Closure

## Execution

Use **GPT-5.4 HIGH** in a fresh Kilo session on the current worktree.

Goal: finish one production-grade football enrichment vertical that becomes the
reference pattern for later sports.

This is not another audit or design exercise.

Required order:

`VERIFY -> FIX FOUNDATIONS -> FREEZE P0 -> MEASURE EXISTING COVERAGE ->
PROBE ONLY GAPS -> ROUTE -> REAL LIVE RUN -> REPLAY -> RERUN -> CERTIFY -> STOP`

Final state must be exactly:

- `PRODUCTION_READY`; or
- `PARTIAL` with one blocker.

## Context control

Use exact paths, `rg`, narrow line ranges and focused tests. Do not dump large
files.

After every phase update:

`.kilo/artifacts/football_golden_final/checkpoint.json`

Include only phase, passed gates, changed files, tests, live-call counts/quota,
bundle IDs, blocker and next command.

If the session is compacted or resumed, continue from checkpoint plus `git
diff`; never repeat passed phases.

## Security and worktree

Before editing:

- record HEAD hash and `git status`;
- save a binary backup patch;
- preserve unrelated changes;
- never use `git reset`, `git clean` or destructive checkout;
- exclude ZIPs, `.DS_Store`, prompt copies and generated review folders from
  production staging;
- require a rotated SportDB key via `SPORTDB_API_KEY`;
- use `THESPORTSDB_API_KEY` from environment;
- scan tracked files, diff, logs and artifacts for leaked credentials;
- never persist credentials in code, evidence or request identity.

Read only current matrix, manifest, backlog, football/API-Sports report,
football production code, ESPN/API-Football clients, result types, evidence
store, crosswalks, schema/repositories and focused tests.

Do not read superseded reports or old prompts.

---

## PHASE 0 — Verify known defects

Create focused tests or direct proofs for:

1. ESPN and API-Football use the same result/status classes.
2. API-Football statuses are interpreted correctly by football enrichment.
3. plan/data-range responses become `PLAN_RESTRICTED`.
4. fallback decisions are capability-policy driven, not hidden in Boolean
   returns.
5. two fixtures for one team and different cutoffs cannot share one unscoped
   snapshot.
6. audit artifacts currently disagree and must only be reconciled after
   execution.

A defect test may already pass if current code is fixed; do not force failure.

---

## PHASE 1 — Canonical result contract

Use one canonical module for:

- `SourceResultStatus`;
- `SourceOperationResult`;
- evidence refs;
- diagnostics;
- retry/quota metadata.

All clients and orchestration import it.

Required statuses:

`SUCCESS`, explicit valid empty, `NOT_FOUND`, `NOT_PUBLISHED_YET`,
`NOT_SUPPORTED`, `AMBIGUOUS`, `PLAN_RESTRICTED`,
`AUTHENTICATION_ERROR`, `BLOCKED`, `RATE_LIMITED`, `TRANSPORT_ERROR`,
`UPSTREAM_ERROR`, `PARSE_ERROR`, `SCHEMA_ERROR`, `EVIDENCE_ERROR`.

Requirements:

- remove duplicate ESPN types;
- no string coercion between enums;
- no cross-module enum identity bug;
- compatibility wrappers only where still used;
- cross-provider interoperability tests.

`PLAN_RESTRICTED` must be non-retryable, fallback-eligible, observable after
fallback and negatively cached per capability.

Never silently substitute season 2024 for a 2026 target.

---

## PHASE 2 — Freeze the P0 contract

Classify each capability as:

- `P0_REQUIRED`;
- `P1_ENHANCEMENT`;
- `SEPARATE_PIPELINE`;
- `OUT_OF_SCOPE`.

Evaluate:

- discovery/status;
- canonical event/team identity;
- current recent form;
- H2H;
- standings/competition context;
- fixture/team statistics;
- injuries/suspensions;
- roster availability;
- predicted lineup;
- confirmed lineup;
- venue/context;
- cross-provider identity.

Odds, weather, news and tipster data may be `SEPARATE_PIPELINE` only when an
existing subsystem owns them.

Write:

`.kilo/artifacts/football_golden_final/capability_contract.json`

A P0 route may return transient `NOT_PUBLISHED_YET` or verified valid empty if
the snapshot preserves `UNKNOWN` and confidence impact.

P0 does not pass when no route exists, all routes are permanently unsupported
or plan-restricted, evidence/identity/temporal gates fail, or stale data is
substituted.

Do not implement P1 in this run.

---

## PHASE 3 — Measure existing providers first

For every P0 capability test current ESPN/API-Football production paths and
retained evidence.

Record:

- entry point;
- source order;
- native IDs;
- status;
- temporal eligibility;
- bundle;
- replay;
- snapshot/persistence;
- missing gate.

If existing providers close all P0 capabilities, skip all new-provider work.

Otherwise create exact gap records:

`capability + missing semantics + required proof`

Only these gaps may trigger Phase 7.

---

## PHASE 4 — Typed capability router

Replace Boolean orchestration with a typed resolution containing:

- capability;
- target fixture/team;
- cutoff;
- attempted sources and statuses;
- native IDs;
- evidence bundles;
- temporal/staleness flags;
- conflicts;
- selected result;
- fallback reason.

Rules:

- primary success stops fallback;
- `PLAN_RESTRICTED` may fall back;
- `NOT_FOUND`, `NOT_SUPPORTED`, `NOT_PUBLISHED_YET` follow explicit per-capability
  policy;
- auth/rate/transport/parse/schema errors remain visible;
- fallback success never erases primary failure;
- ambiguity fails closed;
- source observations are immutable;
- selected projection is separate.

Add parameterized policy tests for every status.

---

## PHASE 5 — Fixture-scoped observations and snapshot

Reuse an existing generic observation/snapshot model if it satisfies all
invariants; otherwise add the smallest generic migration.

Observation identity must include:

- canonical fixture;
- non-null team scope;
- capability;
- source;
- canonical request identity;
- evidence bundle;
- status;
- source event/team refs;
- observed and valid times;
- parser/schema version;
- normalized payload/hash.

Selected projection identity must include:

- canonical fixture;
- non-null team scope;
- capability;
- `analysis_cutoff_at`.

Requirements:

- nullable fields cannot bypass uniqueness;
- use `NOT NULL`, sentinel or expression index;
- observations are append-only;
- changed evidence creates a new observation;
- projection changes do not delete history;
- `team_form` may be latest cache only;
- downstream analysis reads fixture-scoped snapshot.

Migration tests:

- fresh DB;
- populated previous version;
- restart;
- injected failure/rerun;
- legacy readability;
- fresh-vs-migrated equivalence;
- null-key safety;
- same team/two fixtures/two cutoffs;
- changed-evidence history.

---

## PHASE 6 — One real cross-provider 2026 event

Select one event from actual production discovery.

Require real API-Football fixture/team IDs, competition, season and kickoff.

Independently find the ESPN event.

Crosswalk rules:

1. same sport/granularity;
2. mapped competition;
3. exact canonical participant set;
4. kickoff difference <= 10 minutes;
5. zero candidates -> `NOT_FOUND`;
6. multiple candidates -> `AMBIGUOUS`;
7. exactly one -> persist distinct provider mappings.

Forbidden:

- `shadow-*` IDs;
- copying one provider ID into another source;
- names-only matching;
- selecting first candidate without ambiguity checks.

One completed secondary event is allowed only for post-match stats.

---

## PHASE 7 — Probe only unresolved P0 gaps

Stop probing once gaps are closed. Implement at most one new provider.

### SportDB.dev

Probe first when it matches the gap. Maximum six calls.

Use rotated key and current official REST contract. Discover native SportDB
competition, fixture, club and match IDs before match/stats/lineup calls.

Never send ESPN/API-Football IDs unless a cross-reference field proves them.

### TheSportsDB

Probe only for remaining gaps. Maximum five calls.

Use free V1 credential from environment.

Verify exact raw responses for three teams and two events, external-ID fields,
mapping conflicts, schedule completeness, stats semantics and lineup
publication/completeness.

For every probe retain exact sanitized bytes, request identity, SHA-256, bundle,
native IDs, status, counts and quota metadata.

Do not register a provider before parser, identity, temporal, evidence and
offline replay gates pass.

Assign capability-specific roles only:
`PRIMARY`, `FALLBACK`, `SHADOW_ONLY`, `CROSS_REFERENCE_ONLY`,
`METADATA_ONLY`, `HISTORICAL_ONLY`, `PLAN_RESTRICTED`,
`REJECT_INCOMPLETE_DATA`, `REJECT_UNSTABLE`, `NOT_SUPPORTED`.

---

## PHASE 8 — Real end-to-end run

Execute:

`production discovery -> canonical fixture -> real source mappings ->
capability router -> P0 observations -> point-in-time selection ->
fixture-scoped snapshot -> downstream analysis read`

For every P0 capability record attempted sources, selected route, native IDs,
bundle, cutoff, temporal state, observation identity and projection identity.

Missing values remain explicit unknowns; never convert them to zero or stale
values.

---

## PHASE 9 — Replay, rerun and versioning

Using retained evidence and a disposable DB:

1. block all outbound network;
2. replay every selected P0 route through parser, router and downstream snapshot;
3. compare semantic outputs;
4. run the complete vertical twice;
5. compare counts **and sorted logical identities**;
6. require zero second-run delta for fixture, mappings, observations,
   projections, form/stat rows, evidence links and snapshot;
7. inject modified evidence;
8. prove old and new observations remain queryable;
9. prove projection policy without deleting history.

Inject:

- plan restriction;
- transport error;
- malformed payload;
- evidence corruption;
- ambiguous mapping;
- source disagreement.

---

## PHASE 10 — Final quality gate

Run in this order:

1. result interoperability;
2. plan restriction;
3. P0 contract validation;
4. router policy matrix;
5. real cross-provider mapping;
6. temporal snapshot isolation;
7. migration/constraints;
8. provider parsers;
9. no-network replay;
10. duplicate-free rerun;
11. versioning;
12. failure injection;
13. strict markers;
14. secret scan;
15. Ruff on every touched production/test file with zero errors;
16. static/compile checks;
17. full non-live suite once.

Normal tests must make zero external provider calls.

---

## PHASE 11 — Atomic truth and certification bundle

Atomically update matrix, manifest, backlog and existing football/API-Sports
report. Maximum 50 new Markdown lines.

Create:

- `capability_contract.json`;
- `final_capability_routing.json`;
- `end_to_end_certification.json`;
- `checkpoint.json`;
- `CERTIFICATION_INDEX.json`.

`CERTIFICATION_INDEX.json` maps every final claim to provider/capability, source
IDs, bundle/raw hashes, test node IDs, persistence identities and audit entries.

Create:

`FOOTBALL_GOLDEN_FINAL_CERTIFICATION_BUNDLE.zip`

Include real base/head hashes, scoped patch, changed files, changed code/tests,
all five JSON artifacts, audit files, every cited manifest/raw object, redacted
request identities, test/lint/static/secret outputs, migration proof and
idempotency identities.

Exclude secrets, unrelated ZIPs, caches, prompts and `.DS_Store`.

Validate by extracting to a clean temp directory, recomputing hashes and running
offline replay with `EVIDENCE_ROOT` pointing to extracted evidence. Prove zero
network access.

---

## Final-state rule

Set `FOOTBALL_VERTICAL_STATE=PRODUCTION_READY` only when:

- every P0 capability has a verified route;
- transient unavailable states are explicit;
- no P0 is permanently unsupported or plan-restricted across all routes;
- one real cross-provider event passes;
- one canonical result contract is used;
- router preserves attempted outcomes;
- downstream uses fixture-scoped snapshot;
- raw evidence is included;
- offline replay passes;
- second run has zero logical delta;
- changed evidence preserves history;
- touched-file lint is clean;
- audit truth is consistent;
- extracted certification bundle validates;
- no critical/high blocker remains.

Provider states remain independent and capability-scoped.

Otherwise return `PARTIAL` with exactly one blocker.

State the certified competitions/sample, P0 capabilities, temporal scope,
provider-plan limitations and separate pipelines. Do not claim broader coverage.

## Final response

Return only:

RESULT: PASS | PARTIAL | FAIL
FOOTBALL_VERTICAL_STATE: <state>
CERTIFIED_SCOPE: <concise>

REAL_TARGET:
canonical_fixture=<id>
api_football=<fixture/team IDs>
espn=<event/team IDs>
crosswalk=<PASS/FAIL>

P0_CAPABILITIES:
<one line per capability: route, status, bundle>

PROVIDER_ROLE_STATES:
<one line per provider/role>

ROUTER:
attempt_history=<PASS/FAIL>
typed_fallback=<PASS/FAIL>
plan_restricted=<PASS/FAIL>
conflict_handling=<PASS/FAIL>

SNAPSHOT:
fixture_scoped=<PASS/FAIL>
cutoff_safe=<PASS/FAIL>
downstream_read=<PASS/FAIL>

REPLAY:
<one line per P0>

IDEMPOTENCY:
<counts, logical identity deltas, semantic match>

VERSIONING:
<old/new evidence history>

TESTS:
focused=<result>
full_non_live=<result>
lint_static=<result>
secret_scan=<result>

AUDIT_CONSISTENCY:
<PASS/FAIL>

CERTIFICATION_BUNDLE:
<path, index/hash validation, offline replay>

REMAINING_BLOCKER:
<NONE or exactly one>

CHANGED_FILES:
<paths only>

## Stop

Stop after football certification. Do not propagate to another sport.
