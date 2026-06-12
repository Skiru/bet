# Football Golden Vertical — Deep Code and Evidence Review

## Final verdict

The submitted bundle does **not** support `FOOTBALL_VERTICAL_STATE=PRODUCTION_READY`.

Recommended current state:

- Football golden vertical: `LIVE_PARTIAL`
- Architecture direction: accepted
- Production certification: rejected
- Next action: one bounded final implementation-and-certification run

The bundle contains useful progress, but several critical defects mean the
running production path is not equivalent to the declared capability routing.

## Critical findings

### C1 — Two incompatible typed-result contracts exist

`src/bet/api_clients/base_client.py` defines:

- `SourceResultStatus`
- `SourceOperationResult`

`src/bet/api_clients/espn.py` independently defines different classes with the
same names.

`src/bet/stats/enrichment.py` imports the ESPN versions, while API-Football
returns the base-client versions.

The code then uses identity checks such as:

`last_fixtures_result.status is SourceResultStatus.SUCCESS`

Equal string values from different Enum classes are not the same enum member.
API-Football success and failure statuses can therefore be misclassified in the
real fallback path.

This invalidates the declared unified typed-result routing.

### C2 — PLAN_RESTRICTED is never actually produced by API-Sports

The canonical enum contains `PLAN_RESTRICTED`, but provider payload
classification maps free-plan/subscription/plan errors to:

- status: `AUTHENTICATION_ERROR`
- error code: `provider_plan_restricted`

The artifacts claim `PLAN_RESTRICTED`, while production code emits a different
status.

This breaks retry, negative-cache and fallback policy.

### C3 — The actual fallback logic contradicts the routing artifact

The production flow tries ESPN first.

For football, ESPN results including `NOT_FOUND`, `NOT_SUPPORTED`,
`PARSE_ERROR`, `SCHEMA_ERROR` and `PLAN_RESTRICTED` immediately stop processing
and prevent API-Football fallback.

The routing artifact claims API-Football is a fixture-statistics fallback, but
the real Boolean orchestration does not implement the declared
capability-specific policy.

A structured capability resolution is required; a Boolean result cannot retain
attempted source outcomes and fallback reasons.

### C4 — The end-to-end cross-provider proof is synthetic

The submitted proof uses:

- canonical fixture id: `1`
- external id: `api-football-shadow-740968`
- event id: `740968`

`740968` is an ESPN event ID. The test inserts an ESPN `fixture_sources`
mapping, while the canonical external ID is a synthetic shadow string.

No real API-Football event ID for that same event is proved.

The result does not demonstrate:

`real API-Football discovery event -> canonical fixture ->
real ESPN mapping for the same event -> enrichment`

The golden proof must use one real event with distinct, verified IDs from both
providers.

### C5 — team_form is a global mutable cache, not a point-in-time snapshot

`team_form` is logically keyed by team/stat/opponent.

It is not keyed by:

- target fixture;
- analysis cutoff;
- source observation;
- model/snapshot version.

A row calculated for one target match can be reused for another target match.
Historical analyses can therefore receive a projection calculated with a later
cutoff.

`team_form_evidence_history` preserves some evidence history but also lacks an
explicit target fixture and analysis cutoff.

For a betting analysis pipeline, fixture-scoped immutable enrichment snapshots
are mandatory. `team_form` may remain a latest cache, but it cannot be the
source of truth for point-in-time analysis.

## High findings

### H1 — Provider and audit states contradict each other

The matrix and backlog promote API-Football, but the evidence manifest still
reports:

- `LIVE_PARTIAL`
- `E3_CURRENT_LIVE`

The matrix also contains a narrative saying only ESPN Football reached
`PRODUCTION_READY`.

Audit truth is not atomic or internally consistent.

### H2 — Replay evidence is not independently reproducible from the bundle

The submitted bundle includes API-Football bundle manifests but omits the raw
content-addressed objects.

The full ESPN bundle manifest and objects are also absent.

Manifest hashes can be recomputed, but parser replay cannot be independently
executed from this review bundle.

### H3 — The SportDB.dev probe used IDs from other providers

The probe called SportDB match/team endpoints with:

- an ESPN event ID;
- an API-Football team ID.

A provider-native match or club ID was not first discovered from SportDB
fixtures/search.

The resulting 500 responses do not prove that SportDB match/team endpoints are
unstable.

The probe also used an older provider-specific endpoint shape instead of first
validating the current official REST contract.

### H4 — TheSportsDB proof is not auditable enough

The five submitted files are manually summarized response documents, not the
exact sanitized provider response bytes.

There are no bundle manifests or object hashes.

Cross-reference was called PASS after only one team and one event, although the
contract required three teams, two events and conflict checking.

The lineup contains only five entries and cannot be treated as a complete
lineup capability without completeness semantics.

The existing client defaults to an old key/path convention. Current official
documentation identifies `123` as the free V1 key.

### H5 — Golden capability requirements were defined circularly

H2H, standings, lineups, injuries and suspensions were marked optional because
no production consumer currently exists.

That does not establish whether the betting model requires them.

A golden vertical must derive required capabilities from the analysis contract
and feature usage, not only from already implemented consumers.

### H6 — Migration and evidence history are insufficiently tested

Schema v15 adds `team_form_evidence_history`, but the bundle does not contain a
complete focused proof for:

- populated v14 -> v15 upgrade;
- restart/re-entry;
- injected failure and rerun;
- fresh-vs-migrated schema equivalence;
- changed-evidence history;
- target-fixture/cutoff isolation.

### H7 — Final tests do not cover the claimed final architecture

The focused suite covers shared API-Sports and ESPN behavior.

It does not prove:

- a capability router;
- canonical result interoperability across ESPN and API-Football;
- a real cross-provider event;
- TheSportsDB/SportDB parsers;
- fixture-scoped snapshots;
- v15 migration and versioning.

An untracked request-identity test is listed in git status but absent from the
bundle and test collection.

### H8 — Changed files do not pass lint

The Ruff output includes import sorting, E501 and modernization errors in
modified code, including the duplicate ESPN result classes.

The claim that lint errors are only pre-existing is not supported.

### H9 — The worktree is not review-isolated

The diff contains approximately 4,818 insertions across multiple remediation
phases, plus many untracked ZIPs, prompts, artifacts and `.DS_Store`.

The provided base commit is descriptive text rather than a commit hash.

A final production commit cannot currently be attributed to one coherent
change set.

## Medium findings

- API-Football evidence uses sanitizer label `espn-http-v1`.
- Source-health persistence swallows exceptions.
- The legacy API-Football method still defaults to season 2024 and should not be
  reachable from production current-season enrichment.
- TheSportsDB client comments are outdated relative to observed endpoints.
- Provider role and complete vertical readiness are conflated.
- The vertical proof reports source-specific row counts, not router/snapshot
  idempotency.

## Positive findings

- All inspected JSON artifacts parse.
- Bundle manifest IDs recompute correctly from their manifest identity.
- Python files compile.
- Evidence objects are designed around deterministic request identity and full
  SHA-256.
- Mismatched replay requests fail closed.
- Temporal filtering and provider-ID side attribution have useful tests.
- The private SportDB credential was not found in the review bundle.
- The agent did not automatically register a new unverified provider.

## Correct target architecture

The final football vertical should contain:

1. one canonical result/status contract;
2. a capability-specific router preserving all attempted results;
3. real provider IDs and crosswalks for one real event;
4. typed `PLAN_RESTRICTED`;
5. immutable fixture-scoped enrichment snapshots;
6. append-only source observations and evidence history;
7. explicit current projection/cache separated from snapshot truth;
8. exact evidence replay with no network;
9. capability-level provider states;
10. one self-contained certification bundle.

## Required final state semantics

The football vertical may be `PRODUCTION_READY` even when API-Football current
enrichment is plan-restricted, provided every required capability has another
certified route.

Provider roles must remain explicit:

- ESPN Football: enrichment role and certified scope;
- API-Football: discovery scope plus plan-scoped enrichment;
- TheSportsDB: shadow/cross-reference candidate until raw-evidence gates pass;
- SportDB.dev: not correctly evaluated until native IDs and current endpoints
  are used.

Do not promote an entire provider because one role is ready.
