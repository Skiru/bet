# REM-002B — API-Sports Family Production Rollout

## Agent and reasoning

Use **GPT-5.4 with reasoning effort HIGH**.

Act as the implementation owner and adversarial verifier for the API-Sports family only.

This run must maximize verified production progress while minimizing duplicated code, duplicated tests, live requests, documentation, and context growth.

## Objective

Apply the already-proven REM-002A identity, typed-result, content-addressed evidence, no-network replay, and idempotency foundation to these four atomic integrations:

1. `api-football::football::EVENT_AND_ENRICHMENT::default`
2. `api-basketball::basketball::EVENT_AND_ENRICHMENT::default`
3. `api-volleyball::volleyball::EVENT_AND_ENRICHMENT::default`
4. `api-hockey::hockey::EVENT_AND_ENRICHMENT::default`

Assign an independent final state to each integration. Do not require all four to share the same state.

## Binding sources of truth

Read completely before editing:

- `@/SPORTS_INTEGRATION_LIVE_REVIEW_CONTRACT.md`
- `@/docs/audits/sports-integrations/2026-06-11/AUDIT_RECONCILIATION.md`
- `@/docs/audits/sports-integrations/2026-06-11/INTEGRATION_MATRIX.md`
- `@/docs/audits/sports-integrations/2026-06-11/EVIDENCE_MANIFEST.json`
- `@/docs/audits/sports-integrations/2026-06-11/REMEDIATION_BACKLOG.md`
- `@/docs/audits/sports-integrations/2026-06-11/repairs/REM-002A_ESPN_FOUNDATION.md`
- the production and test files implementing the four registered clients, their discovery adapters, enrichment consumers, persistence paths, and the REM-002A evidence/result primitives.

Do not use `PORTFOLIO_AUDIT.md` as current readiness truth. It is historical and superseded by reconciliation plus the corrected matrix, manifest, and backlog.

## Current baseline

- ESPN Football is the only current `PRODUCTION_READY` integration.
- The four API-Sports integrations are currently `LIVE_PARTIAL`.
- Their main portfolio blockers are missing role-appropriate retained evidence, no-network replay, direct source-specific deterministic coverage, and idempotent rerun proof.
- API-Hockey has already demonstrated valid empty on one current date, non-empty results on nearby accessible dates, historical-date plan restrictions, and a working team/season parser path.
- Do not reclassify valid empty or plan restriction as parser failure.

## Non-goals

Do not modify or certify ESPN, Odds API, Odds-API-IO, Tennis Abstract, Sackmann, OpenDota, VLR, Flashscore, browser integrations, historical datasets, or any other provider family.

Do not build a universal sports schema, universal provider framework, new orchestration platform, feature store, or reporting system.

Do not rewrite stable REM-002A primitives unless a failing test proves a defect.

## Mandatory preflight

Before code changes:

1. Record branch, commit, worktree status, Python version, schema version, and the exact REM-002A baseline.
2. Require a clean worktree or preserve and list every unrelated pre-existing change.
3. Locate the registered client, discovery adapter, enrichment consumer, and persistence path for each integration.
4. Prove actual production wiring for client registry, discovery coordinator or scheduler, fallback/enrichment chain, persistence repository, and downstream consumer.
5. Do not trust the matrix role blindly. If an integration is not actually reachable for event discovery, do not certify `EVENT_AND_ENRICHMENT` from a direct client call. Either make the smallest intended wiring fix with tests, or correct the role and final state.
6. Inventory every production-reachable method and classify it as `CORE`, `OPTIONAL`, `UNSUPPORTED`, or `DEAD_OR_UNREACHABLE`.
7. Identify actual shared code. Share only transport, auth, quota telemetry, typed-result mapping, evidence capture, and contract-test mechanics when genuinely common.
8. Keep endpoint mapping, response schemas, parsers, capability rules, and temporal semantics sport-specific.

Write a compact execution checkpoint to `.kilo/artifacts/rem002b_api_sports/checkpoint.json`. It is not runtime evidence storage.

## Implementation order

Implement and verify:

1. API-Football.
2. API-Basketball.
3. API-Volleyball.
4. API-Hockey.

A failure in one sport must not block later sports unless the defect is in genuinely shared code.

After each sport, update the checkpoint with integration key, selected live event/date, gate states, evidence bundle ID, test result, and blocker.

Do not create a separate report per sport.

## Shared foundation requirements

Reuse REM-002A production primitives for typed source results, sanitized content-addressed evidence, deterministic bundles, no-network replay, stable evidence linkage, fail-closed identity, and duplicate-free persistence.

Do not copy ESPN-specific code into four clients.

If REM-002A evidence linkage is tied only to one model, do not add equivalent ad-hoc columns to multiple tables. Use the smallest existing generic observation/evidence boundary. If none exists and persistence cannot be linked otherwise, introduce one minimal reusable relation with focused migration tests.

Any new migration must prove fresh creation, populated previous-schema upgrade, restart/idempotent re-entry, legacy-row readability, injected failure and rerun, repository round-trip, and schema equivalence where applicable.

## Typed result semantics

Critical production paths must not collapse failures into `[]`, `{}`, `None`, or zero.

Use the existing project result type and extend it only when required.

Required distinctions:

- `SUCCESS` with non-empty payload;
- `SUCCESS` with valid empty collection;
- `NOT_FOUND`;
- `NOT_PUBLISHED_YET`;
- `NOT_SUPPORTED`;
- `AMBIGUOUS`;
- `AUTHENTICATION_ERROR`;
- `BLOCKED`;
- `RATE_LIMITED`;
- `TRANSPORT_ERROR`;
- `UPSTREAM_ERROR`;
- `PARSE_ERROR`;
- `SCHEMA_ERROR`.

Classify both HTTP status and provider payload errors. HTTP success with a provider error object is not `SUCCESS`.

Preserve the status through discovery and enrichment orchestration. Do not convert it back to list/empty-list semantics.

## Provider identity and canonical matching

For each selected event:

1. Retain provider event/game ID.
2. Retain provider participant/team IDs.
3. Retain competition/league and season IDs when supplied.
4. Persist the source reference under the exact atomic source key.
5. Link canonical events through `fixture_sources` or the audited crosswalk.
6. Never assume canonical `external_id` belongs to the active provider.
7. Never auto-link from names alone.
8. Hard-block by sport, granularity, competition/season, participant set, and time window before soft scoring.
9. Persist `AMBIGUOUS` without selecting a candidate.
10. Verify an existing crosswalk cannot point to an event with different participants or implausible start time.

Duplicate identical source-reference rows are one logical mapping. Multiple distinct provider IDs are ambiguous unless an explicit supersession rule exists.

## Point-in-time rules

Every enrichment proof must carry immutable `analysis_cutoff_at`.

For H2H, recent form, or prior games:

- every included event starts strictly before the target;
- target provider event ID is excluded;
- missing event ID or start time is rejected;
- postponed duplicates are not counted twice;
- wall-clock now is not a historical cutoff.

For standings, injuries, lineups, rosters, or odds:

- use only observations provably available at or before cutoff;
- do not backdate data fetched now;
- distinguish predicted and confirmed lineups;
- retain effective roster dates;
- retain odds observation time and market identity.

If data is not published, return `NOT_PUBLISHED_YET`; do not substitute stale historical data.

## Live-proof selection

Use one primary representative event per sport. A second event is allowed only for phase-dependent capability proof.

The event must have provider event ID, provider participant IDs, start time, competition/league, season when supplied, non-ambiguous canonical link, and strongest available coverage for production-reachable CORE methods.

Prefer current or upcoming events for pre-event capabilities. Completed events may prove result/stat parsing but not pre-event availability.

If today's date is valid empty:

1. retain it as valid-empty proof;
2. search the nearest provider-accessible non-empty date within budget;
3. do not label the integration broken.

For API-Hockey explicitly prove valid empty, nearby non-empty current-window response, historical plan limitation classification, and no confusion among those states.

## Live request and quota budget

Before live calls, read provider status/quota information or response headers and record daily and minute remaining values when available.

Hard budget:

- maximum 10 live requests per sport;
- maximum 32 total;
- stop if fewer than 15 daily requests or fewer than 3 minute-level requests remain.

Do not spend live quota on debugging. Capture once and replay locally.

Do not retry authentication errors, blocked responses, schema/parse errors, or valid empty. Honor `Retry-After`. Allow at most one bounded retry for an idempotent transient read.

Never log keys, auth headers, credential-bearing URLs, or secret config.

## Evidence requirements

For every proof request:

1. sanitize exact response bytes;
2. compute full SHA-256;
3. atomically store in the configured content-addressed evidence store;
4. record MIME type, byte size, source, operation, capture time, parser/schema version, sanitization version, and secret-free request identity;
5. create a deterministic bundle manifest excluding volatile values from identity;
6. compute full SHA-256 bundle ID;
7. link persisted observations or source runs to bundle ID;
8. verify object hashes during replay;
9. fail closed on missing/corrupt objects;
10. prohibit live fallback during replay.

A cache hit is certifiable only if it resolves to retained sanitized bytes and the same content hash.

## Role-appropriate proof

For discovery:

- real date query;
- provider event and participant IDs;
- source-reference persistence;
- deterministic dedup/matching;
- second identical run creates zero new logical events or source references;
- replay reproduces the same semantic candidates.

For every production-reachable CORE enrichment capability:

- deterministic parser test from retained evidence;
- typed result;
- provider identity preservation;
- temporal eligibility;
- persistence/evidence linkage where stored.

Live proof must cover one representative response shape for each distinct CORE endpoint family. If legitimately unavailable, use the permitted second event or retain an explicit non-success status.

Do not assign `PRODUCTION_READY` to `EVENT_AND_ENRICHMENT` if only discovery was proved.

## Deterministic tests

Add one parameterized family contract suite for shared behavior and small sport-specific tests for distinct schemas.

Shared contract coverage:

- auth without secret logging;
- timeout and bounded retry;
- provider error payload classification;
- 401, 403, 429, 5xx, timeout, malformed JSON, wrong schema, valid empty;
- rate-limit header capture;
- evidence object and bundle hashing;
- no-network replay;
- missing/corrupt evidence fail-closed;
- stable semantic replay;
- source identity;
- duplicate-free rerun.

Sport-specific coverage:

- event and participant IDs;
- competition/season mapping;
- status mapping;
- null versus zero;
- timestamp/timezone conversion;
- representative CORE enrichment payload;
- sport-specific temporal invariants.

Generic value-range tests do not count as direct source-specific parser proof.

## Test execution budget

During implementation run focused tests only.

After deterministic implementation:

1. run the family-focused suite once;
2. run one controlled live pass per sport;
3. run one no-network replay per sport;
4. run one identical persistence rerun per sport;
5. run lint/static checks on changed files;
6. run the full suite exactly once.

Do not rerun the full suite after every sport.

Live tests must remain separately marked and excluded from normal deterministic CI.

## Independent final-state algorithm

`PRODUCTION_READY` requires all role-applicable mandatory gates: current proof, direct source-specific deterministic coverage, safe identity/matching, temporal correctness, typed status propagation, evidence/replay, idempotency where applicable, failure isolation, secret/rate-limit safety, and no unresolved critical/high blocker.

Use `PRODUCTION_CANDIDATE` when deterministic safety, evidence, replay, and wiring pass but exactly one non-critical live, plan, or publication limitation remains.

Use `LIVE_PARTIAL` when live access works but evidence, replay, persistence, temporal, or core capability proof is incomplete.

Use `DETERMINISTIC_ONLY` when deterministic source proof passes but current proof was not executed.

Use `IMPLEMENTED_UNVERIFIED` when direct deterministic and current proof remain insufficient.

Never promote one sport because another sport passed.

## Failure isolation

One sport's failure produces a sport-specific blocker.

Do not allow valid empty to fail the family, one schema drift to consume all quota, one retry loop to block other clients, shared changes to alter unrelated providers, or partial success to be reported as four certifications.

If shared code fails, repair once and rerun focused shared tests.

## Documentation and token budget

Update only:

- `INTEGRATION_MATRIX.md`
- `EVIDENCE_MANIFEST.json`
- `REMEDIATION_BACKLOG.md`

Create one report:

`docs/audits/sports-integrations/2026-06-11/repairs/REM-002B_API_SPORTS_FAMILY.md`

Maximum 120 lines.

Do not create per-sport/per-test reports, architecture essays, command transcripts, or duplicate summaries.

The report contains only scope/role corrections, changed files, one row per sport with event/date/live result/bundle/replay/rerun/gate delta/final state/blocker, shared tests, quota usage, and unresolved family risks.

## Final response format

Return only:

RESULT: PASS | PARTIAL | FAIL

FAMILY:
api-football=<state>
api-basketball=<state>
api-volleyball=<state>
api-hockey=<state>

ROLE_CORRECTIONS:
<none or concise list>

CHANGED_FILES:
<paths only>

TESTS:
focused=<result>
family=<result>
full=<result>
lint_static=<result>

LIVE:
api-football=<event/date, requests, bundle>
api-basketball=<event/date, requests, bundle>
api-volleyball=<event/date, requests, bundle>
api-hockey=<valid-empty + non-empty proof, requests, bundles>

REPLAY:
<one line per sport>

IDEMPOTENCY:
<one line per sport>

GATE_DELTA:
<one line per sport>

REMAINING_BLOCKERS:
<none or one line per affected sport>

REPORT:
<path>

## Stop rule

Stop after the four API-Sports keys have independent final states and the three authoritative audit artifacts agree.

Do not begin REM-003, Odds-API-IO, another current-live integration, HTML/XHR, browser automation, another provider family, or framework-wide cleanup.

If credentials, quota, publication timing, or plan prevents proof, preserve the exact blocker, assign the truthful state, continue with independent sports when safe, and stop without inventing success.
