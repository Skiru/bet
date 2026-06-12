# REM-002B-CLOSURE — API-Sports Production Wiring and E4 Certification

## Model

Use **GPT-5.4 with reasoning effort HIGH**.

## Mission

Finish the existing REM-002B slice. Do not start another provider family and do
not redesign the whole integration architecture.

The previous run added a useful typed-result/evidence foundation, but it did
not complete role-appropriate live certification.

Certify independently:

1. `api-football::football::EVENT_AND_ENRICHMENT::default`
2. `api-basketball::basketball::EVENT_AND_ENRICHMENT::default`
3. `api-volleyball::volleyball::EVENT_AND_ENRICHMENT::default`
4. `api-hockey::hockey::EVENT_AND_ENRICHMENT::default`

A truthful partial result is acceptable. A false PASS is not.

## Read first

Read completely:

- `@/SPORTS_INTEGRATION_LIVE_REVIEW_CONTRACT.md`
- `@/docs/audits/sports-integrations/2026-06-11/AUDIT_RECONCILIATION.md`
- `@/docs/audits/sports-integrations/2026-06-11/INTEGRATION_MATRIX.md`
- `@/docs/audits/sports-integrations/2026-06-11/EVIDENCE_MANIFEST.json`
- `@/docs/audits/sports-integrations/2026-06-11/REMEDIATION_BACKLOG.md`
- `@/docs/audits/sports-integrations/2026-06-11/repairs/REM-002A_ESPN_FOUNDATION.md`
- `@/docs/audits/sports-integrations/2026-06-11/repairs/REM-002B_API_SPORTS_FAMILY.md`
- `@/src/bet/api_clients/base_client.py`
- all four API-Sports clients;
- their discovery adapters/coordinator wiring;
- production enrichment/fallback consumers;
- discovery and persistence repositories;
- `@/src/bet/integration/evidence.py`;
- the deterministic and live API-Sports tests.

Treat `PORTFOLIO_AUDIT.md` as historical and superseded.

## Known review findings

Assume these findings are real until disproved by code and tests:

1. `api_sports_live`/`live` marker is not registered.
2. The supposed live tests execute during the normal suite.
3. A live test passes on `RATE_LIMITED` or `AUTHENTICATION_ERROR`.
4. No successful REM-002B live certification output exists.
5. `get_fixtures_result()` is not used by production orchestration.
6. Provider participant IDs are not populated by the new result parsers.
7. Evidence persistence failure is swallowed.
8. HTTP 200 provider error payloads can become `SUCCESS`.
9. `response` schema is not validated.
10. No deterministic operation bundle ID reaches persistence.
11. No role-appropriate no-network replay or second-run persistence proof exists.
12. The review bundle omitted the family test file and untracked changes from its patch.
13. API-Basketball's real event-discovery wiring is still unproved.

## Scope restrictions

Do not:

- begin REM-003;
- modify ESPN behavior except when required to keep a shared primitive backward
  compatible;
- touch HTML, XHR, browser, odds, tennis, esports, or historical providers;
- create another result taxonomy when a canonical REM-002A type already exists;
- create ad-hoc evidence columns on multiple domain tables;
- write more than one short family report;
- repeatedly run the full suite;
- claim `PRODUCTION_READY` from a direct client call alone.

## Phase 0 — protect the worktree

Before editing:

1. Record current branch, commit, and `git status --short`.
2. Identify which REM-001/REM-002A files are accepted baseline and which changes
   belong to unfinished REM-002B.
3. Do not reset, delete, or overwrite unrelated changes.
4. Exclude `.DS_Store`, ZIP review bundles, prompt copies, and generated
   `.kilo/artifacts` from production commits.
5. Ensure the final patch contains every new test and audit file, not only
   tracked production files.
6. If a clean baseline cannot be established safely, stop with the exact
   blocker instead of mixing remediation slices.

## Phase 1 — fix the test boundary first

Before any new live request:

1. Register a dedicated marker:

   `api_sports_live: live API-Sports certification tests requiring explicit opt-in`

2. Add an explicit opt-in such as:

   `BET_RUN_LIVE_API_SPORTS=1`

3. Live tests must skip before client construction and before any network access
   when the opt-in is absent.
4. The normal suite must run with live tests excluded.
5. Run the targeted suite with strict marker validation.
6. Split deterministic family contracts and live certification tests if needed.
7. A certification live test must require the expected role-appropriate
   successful result.
8. `RATE_LIMITED`, missing credentials, plan restrictions, or access blocks are
   blockers/status evidence, not passing live proof.
9. Diagnostic error-classification tests remain deterministic and mocked.
10. Point all deterministic evidence writes to `tmp_path`.
11. Point a real certification run to the configured durable evidence store and
    record the exact root without committing raw payloads.

Acceptance:

- zero unknown-marker warnings;
- no network access in ordinary `pytest tests/`;
- live collection is selectable only through the dedicated marker;
- an auth/rate-limited response cannot produce a green certification.

## Phase 2 — one canonical typed-result implementation

Search the repository for result/status types introduced by REM-002A and the
current API-Sports patch.

Use exactly one canonical public operation result contract.

Required fields or equivalent:

- status;
- typed value;
- HTTP status;
- retryable;
- error code;
- retry-after;
- evidence refs;
- deterministic evidence bundle ID;
- retry count;
- bounded response/quota metadata;
- parser diagnostics such as raw count, accepted count, rejected count.

Do not expose secrets or complete response headers.

Type `evidence_refs`; avoid an unbounded raw `list`.

If evidence is mandatory for the called audited operation, an evidence write
failure must not return `SUCCESS`. Use an existing internal failure status or
add one precise status such as `EVIDENCE_ERROR`; do not mislabel it as a source
parse error.

Keep compatibility for ESPN's already-certified behavior.

## Phase 3 — make transport classification correct

Repair `_request_with_evidence()` or its canonical equivalent.

Requirements:

1. Maximum two total attempts: initial request plus at most one retry.
2. Retry only idempotent transient transport failures and selected 502/503/504.
3. Add bounded jitter or reuse the project's existing jitter helper.
4. Do not retry 400/401/403/404, provider schema errors, parse errors, valid
   empty, or evidence-store errors.
5. On 429, preserve `Retry-After`; do not immediately retry unless the existing
   policy explicitly permits it within the request budget.
6. Count every actual HTTP attempt in telemetry/local request accounting.
7. Capture API-Sports daily and minute quota headers in bounded metadata.
8. Set retry count correctly on evidence refs and the final result.
9. Inspect a successful HTTP payload for provider-level `errors`.
10. A non-empty provider error object/list/string is not `SUCCESS`.
11. Require a top-level object and a list-valued `response` for collection
    operations.
12. Map malformed JSON to `PARSE_ERROR`.
13. Map missing/wrong `response` shape to `SCHEMA_ERROR`.
14. Preserve valid `response: []` as `SUCCESS` with an empty collection.
15. Preserve historical plan restriction separately from valid empty.

Add deterministic tests for all mappings.

## Phase 4 — validate source identity in all four parsers

For every fixture returned by a typed result:

- provider event ID is non-empty;
- home participant ID is non-empty;
- away participant ID is non-empty;
- participant IDs differ;
- participant names are non-empty;
- kickoff is parseable and timezone-aware or normalized consistently;
- competition/league identity is retained;
- season identity is retained when the provider supplies it;
- source equals the exact atomic registered source key.

Populate `home_participant_id` and `away_participant_id`; do not merely test
those fields on manually constructed fixtures.

Do not emit `"None"`, empty IDs, or `"Unknown"` participants under `SUCCESS`.

If the raw response contains records but none pass identity/schema validation,
return `SCHEMA_ERROR`.

If some records are accepted and some rejected, return `SUCCESS` with bounded
diagnostics and retain rejected-count evidence. Never silently treat bad rows as
valid.

## Phase 5 — wire typed operations into the real application

Repository-wide search must show production use of the typed operations.

For each sport prove:

`registered client -> discovery adapter/coordinator -> source candidate ->
fixture_sources/canonical matching -> persistence -> downstream consumer`

Requirements:

1. The production discovery adapter calls the typed operation, not only legacy
   `get_fixtures()`.
2. The operation status reaches the discovery run/result and is not converted
   to `[]`.
3. Evidence bundle ID and source identity reach the persisted source
   observation/run/reference.
4. Canonical matching uses provider event/participant identities and hard
   constraints, not names alone.
5. Existing crosswalks are validated against participants and time.
6. Multiple distinct provider IDs fail closed as `AMBIGUOUS`.
7. A missing provider mapping does not fall back to a canonical `external_id`
   owned by another source.
8. One sport's failure does not abort independent sports.

For API-Basketball specifically:

- prove it is reachable through intended event discovery;
- if no intended discovery adapter exists, either implement the minimal
  registered adapter with tests or correct the role to `ENRICHMENT_ONLY`;
- do not retain `EVENT_AND_ENRICHMENT` based only on a direct client method.

Legacy list-returning methods may remain for compatibility, but the
production-critical coordinator path must use the typed operation.

## Phase 6 — deterministic bundles and replay

A single response object reference is not enough.

For every role-appropriate proof:

1. retain sanitized response object(s);
2. build a deterministic operation bundle;
3. include stable source, operation, request identity, parser version, response
   object hashes, and namespaced source-event refs;
4. exclude timestamps, latency, retry count, run ID, and local paths from bundle
   identity;
5. return and persist the full 64-character bundle ID;
6. support discovery operations that have no canonical fixture yet without
   inventing fixture ID `0`;
7. verify every object hash before replay;
8. block all outbound network during replay;
9. fail closed for missing/corrupt objects or unexpected requests;
10. compare replayed semantic candidates/results with live output.

Do not break existing ESPN bundle IDs. Add a compatible source-operation bundle
helper if the existing canonical-fixture manifest cannot represent discovery.

## Phase 7 — role-appropriate persistence and idempotency

Use a disposable database.

For each sport:

1. Run the real discovery path using one representative provider date/event.
2. Persist provider source event/reference and evidence linkage.
3. Run the identical flow again.
4. Assert zero new logical canonical events.
5. Assert zero new logical source-reference rows.
6. Assert no duplicate evidence linkage.
7. Allow append-only run metadata only when it is intentionally keyed as a new
   run and is not counted as duplicated domain information.
8. Replay the same bundle with all network blocked.
9. Assert the same semantic source candidates and persistence outcome.

Do not add four sets of provider-specific provenance columns. Reuse a generic
source observation/run/evidence relation where available.

## Phase 8 — cover actual CORE enrichment or correct the role

Inventory the real production-reachable methods for each client.

For every method currently used as a CORE enrichment capability, such as fixture
statistics, H2H, or recent form:

- add/use a typed result;
- retain source identity;
- capture and bundle evidence;
- enforce point-in-time rules;
- add deterministic parser replay;
- prove one representative live shape when quota/publication permits;
- link persistence to evidence when stored.

Rules:

- target event must be excluded from form/H2H;
- every prior event must start strictly before target start;
- missing ID/date is rejected;
- `analysis_cutoff_at` is immutable;
- current fetch time is not historical availability;
- null is not zero;
- side attribution uses provider participant IDs, not response order.

If the integration does not actually provide/use enrichment in production,
correct its role instead of faking proof.

Do not assign `PRODUCTION_READY` to `EVENT_AND_ENRICHMENT` after proving only
fixture discovery.

## Phase 9 — efficient live certification

Run only after deterministic focused tests pass and quota is available.

Use:

- one primary event/date per sport;
- one additional event/date only for phase-dependent or valid-empty proof;
- at most 10 live calls per sport and 32 total;
- capture once, debug through replay.

For API-Hockey independently prove:

- valid-empty accessible date;
- nearby non-empty accessible date;
- historical plan limitation;
- no confusion among these statuses.

For API-Football, if daily quota is unavailable:

- do not treat it as a pass;
- retain the blocker;
- continue independently with other sports;
- leave Football `LIVE_PARTIAL` or `DETERMINISTIC_ONLY` as dictated by evidence.

Certification output must contain actual event IDs, participant IDs, request
counts, quota metadata, bundle IDs, and evidence object counts without secrets.

## Phase 10 — tests and audit closure

Required test sequence:

1. focused deterministic tests during implementation;
2. family deterministic suite once;
3. live certification once per sport;
4. no-network replay once per sport;
5. identical persistence rerun once per sport;
6. lint, compile/static checks on all changed production and test files;
7. full project suite exactly once at the end with live tests excluded;
8. strict marker validation.

The final patch/bundle must include all new tracked and untracked task files,
including the family test suite, live tests, marker config, audit updates, and
short report.

Reconcile conflicting counts and claims in:

- `INTEGRATION_MATRIX.md`;
- `EVIDENCE_MANIFEST.json`;
- `REMEDIATION_BACKLOG.md`;
- `REM-002B_API_SPORTS_FAMILY.md`.

Keep all four states `LIVE_PARTIAL` until their independent gate is actually
proved.

## Final-state algorithm

Assign each integration independently.

`PRODUCTION_READY` requires:

- actual production role wiring;
- successful current role proof;
- source event and participant identity;
- safe canonical matching;
- typed status propagation;
- point-in-time correctness for CORE enrichment;
- retained deterministic evidence bundle;
- no-network replay;
- duplicate-free persistence rerun;
- direct source-specific deterministic tests;
- failure isolation;
- quota/secret safety;
- no unresolved critical/high blocker.

`PRODUCTION_CANDIDATE` is allowed only when implementation, evidence, replay,
idempotency, wiring, and temporal safety pass but exactly one non-critical
publication/plan/current-proof limitation remains.

Otherwise use the truthful lower state.

## Documentation limit

Update only the existing matrix, manifest, backlog, and the single existing
REM-002B family report.

Maximum report length: 120 lines.

Do not create per-sport reports or copy full command logs into Markdown.

## Required final response

Return only:

RESULT: PASS | PARTIAL | FAIL

FAMILY:
api-football=<state>
api-basketball=<state>
api-volleyball=<state>
api-hockey=<state>

ROLE_CORRECTIONS:
<none or concise list>

TEST_BOUNDARY:
marker=<registered>
normal_suite_network_calls=0
live_opt_in=<flag>
strict_markers=<result>

PRODUCTION_WIRING:
<one concise line per sport>

LIVE:
<one concise line per sport with date/event IDs/request count/quota/bundle>

REPLAY:
<one concise line per sport>

IDEMPOTENCY:
<one concise line per sport>

TESTS:
focused=<result>
family=<result>
full_without_live=<result>
lint_static=<result>

GATE_DELTA:
<one line per sport>

REMAINING_BLOCKERS:
<none or one line per affected sport>

CHANGED_FILES:
<paths only>

REPORT:
<path>

## Stop rule

Stop after independent REM-002B closure for these four keys.

Do not begin Odds-API-IO, REM-003, HTML/XHR, browser automation, another
provider family, or framework-wide cleanup.
