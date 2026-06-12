# REM-002C — API-Sports Enrichment E4 Closure + Multisport Provider Inventory

## Model

Use **GPT-5.4 with reasoning effort HIGH**.

## Objective

Complete the remaining enrichment-path E4 proof for these four integrations:

1. `api-football::football::EVENT_AND_ENRICHMENT::default`
2. `api-basketball::basketball::EVENT_AND_ENRICHMENT::default`
3. `api-volleyball::volleyball::EVENT_AND_ENRICHMENT::default`
4. `api-hockey::hockey::EVENT_AND_ENRICHMENT::default`

The discovery path is already proved. Do not rebuild it.

Secondary read-only objective: determine whether working, registered clients already exist for:

- `sportdb.dev`
- `TheSportsDB`

Do not implement either provider in this run. Record only verified repository facts and one concise backlog decision.

## Read first

Read completely:

- `@/SPORTS_INTEGRATION_LIVE_REVIEW_CONTRACT.md`
- `@/docs/audits/sports-integrations/2026-06-11/INTEGRATION_MATRIX.md`
- `@/docs/audits/sports-integrations/2026-06-11/EVIDENCE_MANIFEST.json`
- `@/docs/audits/sports-integrations/2026-06-11/REMEDIATION_BACKLOG.md`
- `@/docs/audits/sports-integrations/2026-06-11/repairs/REM-002A_ESPN_FOUNDATION.md`
- `@/docs/audits/sports-integrations/2026-06-11/repairs/REM-002B_API_SPORTS_FAMILY.md`
- the four API-Sports clients;
- API-Sports discovery adapters;
- `StatFetcher`, fallback chains, enrichment services, repositories, evidence primitives, and all API-Sports tests.

Treat the original `PORTFOLIO_AUDIT.md` as historical and superseded.

## Accepted baseline

Accept unless a focused regression proves otherwise:

- typed fixture-result propagation;
- production discovery wiring for all four clients;
- API-Basketball discovery registration;
- provider event and participant identity in discovery;
- deterministic source-operation bundles;
- discovery no-network replay;
- discovery duplicate-free rerun;
- fail-closed same-source duplicate protection;
- dedicated live test boundary;
- four integrations remain `LIVE_PARTIAL`.

Do not rewrite accepted discovery code merely for style.

## Mandatory preflight

Before editing:

1. Record branch, commit and worktree status.
2. Preserve unrelated changes.
3. Identify the exact commit/diff belonging to REM-002B closure.
4. Reconcile test collection:
   - collect all test nodeids from the accepted pre-REM-002B baseline when available;
   - collect current nodeids;
   - explain the difference between the previously reported `700 passed, 5 skipped`
     and the current `657 passed, 4 skipped, 6 deselected`;
   - fail the gate if non-live tests disappeared unintentionally.
5. Confirm strict marker registration and prove the ordinary suite performs zero
   API-Sports network calls.
6. Read the current retained discovery bundle IDs and reuse their selected
   provider event and participant IDs where valid.
7. Inventory production-reachable enrichment methods per client and mark each:
   - `CORE`;
   - `OPTIONAL`;
   - `UNSUPPORTED`;
   - `DEAD_OR_UNREACHABLE`.

Do not certify methods that are not called by production consumers.

## Scope

Implement typed, evidence-linked production paths only for enrichment methods
that are genuinely `CORE`.

Expected candidates include:

- `get_fixture_stats`;
- `get_team_last_fixtures`;
- `get_h2h` only if a production consumer actually uses it;
- volleyball-specific aliases such as `get_match_stats` or `get_team_l10_stats`
  only if they are production-reachable.

Do not expand into standings, injuries, lineups, odds, or new endpoints unless
they are already declared and production-reachable CORE capabilities.

## One canonical result path

Use the existing canonical `SourceOperationResult` and evidence primitives.

For each CORE operation, provide a typed result method or internal typed
operation that preserves:

- semantic status;
- typed payload;
- HTTP status;
- retry metadata;
- bounded quota metadata;
- parser diagnostics;
- evidence object refs;
- deterministic bundle ID;
- namespaced provider event/team refs.

Legacy list/dict methods may remain for compatibility, but production
orchestration must consume typed results.

Do not allow a production consumer to convert:

- transport failure;
- rate limiting;
- provider error;
- malformed JSON;
- schema error;
- evidence error

into `[]`, `{}`, `None`, or zero.

## Status semantics

Required distinctions:

- `SUCCESS` with data;
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
- `SCHEMA_ERROR`;
- the existing explicit evidence/internal failure status.

HTTP 200 with a provider `errors` payload is not success.

If an endpoint is not available for the selected event, preserve the exact
semantic status; do not substitute stale data.

## Identity and side attribution

For every enrichment response:

1. Use provider event ID from the persisted source crosswalk.
2. Use provider team/participant IDs, not canonical names.
3. Verify the requested event/team belongs to the expected canonical fixture.
4. Attribute home/away statistics only by exact provider participant ID.
5. Reject neither-side or both-side matches.
6. Reject blank IDs, `"None"`, unknown participants, and missing start times.
7. Do not infer side from array order.
8. Preserve competition/league and season context when supplied.
9. Names may be diagnostics only, never the identity proof.

## Point-in-time rules

For every proof use immutable:

- `target_start_at`;
- `analysis_cutoff_at`;
- `target_source_event_id`.

For recent form/H2H:

- target event is excluded;
- every included event starts strictly before target;
- missing ID/date is rejected;
- postponed duplicates are not double-counted;
- fetch time is not historical availability;
- `last_n` is applied only after temporal filtering;
- participant side is resolved by provider ID.

For fixture statistics:

- completed-event statistics may prove parser correctness;
- do not claim they were available before kickoff;
- persist valid-time and first-seen/fetched timing;
- pre-event snapshots must exclude post-event statistics.

## Statistical semantic validation

For each accepted metric retain or test:

- source field/path;
- normalized field;
- unit and scale;
- total/average/rate/percentage meaning;
- sample window;
- event/team granularity;
- null versus true zero;
- side attribution;
- raw, accepted and rejected counts.

Mandatory adversarial cases:

- blank numeric value;
- non-numeric value;
- percentage represented as `0.53` versus `53`;
- missing team side;
- duplicated metric;
- unknown metric;
- wrong event or team ID;
- partial provider payload.

Never invent zero for missing/unparseable data.

## Evidence and replay

For each CORE live operation:

1. retain exact sanitized response bytes;
2. verify full SHA-256 object hash;
3. build deterministic operation bundle;
4. link bundle to persisted enrichment observation/row/run;
5. verify all object hashes during replay;
6. block all outbound network;
7. fail closed on missing/corrupt evidence;
8. compare live and replay semantic outputs;
9. ensure bundle identity excludes volatile metadata.

Reuse the accepted discovery event/bundle where applicable, but enrichment
endpoint responses require their own evidence objects and bundle.

## Production-consumer proof

For each sport prove the actual path:

`canonical fixture -> fixture_sources provider ID -> typed enrichment method ->
temporal filter -> normalized metrics/form -> persistence -> downstream reader`

A direct client call is insufficient.

Fallback behavior must be explicit:

- valid empty / not published / unsupported may continue according to policy;
- auth, blocked, rate-limited, transport, parse and schema failures must remain
  observable even if another source is attempted;
- one source failure must not erase successful capabilities;
- no fallback may silently reinterpret failure as zero or empty success.

## Live proof budget

Use retained discovery evidence; do not rediscover repeatedly.

Per sport:

- one completed event for fixture-stat proof;
- one target event/team for recent-form proof;
- reuse the same event when possible;
- at most one extra event when publication/state requires it;
- maximum 8 new live requests per sport;
- maximum 24 new live requests total.

Stop earlier when quota is low. Capture once, debug by replay.

API-Hockey must preserve the already-proved distinction among valid empty,
nearby non-empty, and historical plan limitation.

## Idempotency

Use a disposable database.

For each sport:

1. run the full production enrichment path;
2. record relevant row/source/evidence-link counts;
3. run the identical path again;
4. assert zero new logical enrichment rows;
5. assert zero duplicate source links;
6. assert zero duplicate evidence links;
7. allow only intentionally append-only run telemetry;
8. replay offline and assert the same persistence outcome.

## Tests

Add one parameterized shared contract for common typed/evidence behavior and
small sport-specific parser/consumer tests.

Required coverage:

- successful fixture stats;
- successful recent form;
- valid empty;
- not published;
- provider error in HTTP 200;
- 401, 403, 429, 5xx, timeout;
- malformed JSON and wrong schema;
- evidence failure;
- missing/corrupt replay object;
- provider IDs and side attribution;
- temporal exclusion/cutoff;
- null versus zero;
- production fallback propagation;
- duplicate-free second run.

Do not count generic value-range tests as direct source parser proof.

Execution order:

1. focused tests during implementation;
2. API-Sports enrichment family suite once;
3. controlled live enrichment proof once per sport;
4. no-network replay once per sport;
5. identical persistence rerun once per sport;
6. strict marker/static/lint checks;
7. full non-live suite exactly once.

## Read-only inventory: SportDB.dev and TheSportsDB

Perform a repository-only inventory after API-Sports work is complete.

Run an equivalent of:

`rg -n -i "sportdb\\.dev|api\\.sportdb\\.dev|thesportsdb|THESPORTSDB|SPORTDB" src tests config pyproject.toml`

Also inspect:

- `CLIENT_REGISTRY`;
- `SCRAPER_REGISTRY`;
- discovery sources;
- fallback chains;
- API-key configuration;
- tests;
- persistence consumers.

For each provider report exactly:

- client class/path, or `ABSENT`;
- registry key(s);
- credential configured: yes/no, without value;
- supported sports declared in code;
- production role/wiring;
- direct deterministic tests;
- live proof;
- current truthful state.

Important:

- A configured API key is not proof of a client.
- A class not registered or called is not an active integration.
- Do not use the superseded old portfolio report as proof.
- Do not add new atomic integration keys unless code and registration actually
  exist.
- Do not implement either provider in this run.

If absent or unverified, add one concise backlog item:

`REM-006 — Multisport provider onboarding assessment`

Split later implementation by provider, not by sport, and require a capability
coverage comparison before coding.

## Final states

Assign the four API-Sports integrations independently.

`PRODUCTION_READY` requires both discovery and all production-reachable CORE
enrichment paths to pass identity, temporal, typed-status, evidence/replay,
idempotency, live proof, failure isolation, and direct deterministic gates.

Use `PRODUCTION_CANDIDATE` only when all safety and replay gates pass and exactly
one non-critical publication/plan limitation remains.

Otherwise retain the truthful lower state.

## Documentation limit

Update only:

- `INTEGRATION_MATRIX.md`;
- `EVIDENCE_MANIFEST.json`;
- `REMEDIATION_BACKLOG.md`;
- existing `REM-002B_API_SPORTS_FAMILY.md`.

Do not create a new long report. Add at most 50 lines to the existing family
report.

Add at most one backlog item for SportDB.dev/TheSportsDB inventory.

## Required final response

Return only:

RESULT: PASS | PARTIAL | FAIL

TEST_INVENTORY:
baseline=<count>
current_non_live=<count>
intentional_difference=<explanation>
missing_unintentional=<count>

FAMILY:
api-football=<state>
api-basketball=<state>
api-volleyball=<state>
api-hockey=<state>

CORE_CAPABILITIES:
<one concise line per sport>

LIVE_ENRICHMENT:
<event/team IDs, request count, bundle IDs per sport>

REPLAY:
<one line per sport>

IDEMPOTENCY:
<one line per sport>

GATE_DELTA:
<one line per sport>

MULTISPORT_PROVIDER_INVENTORY:
sportdb.dev=<client/registry/credential/wiring/tests/state>
thesportsdb=<client/registry/credential/wiring/tests/state>

REMAINING_BLOCKERS:
<none or concise lines>

CHANGED_FILES:
<paths only>

REPORT:
<existing report path>

## Stop rule

Stop after:

- enrichment E4 has been independently evaluated for the four API-Sports keys;
- test inventory is reconciled;
- SportDB.dev and TheSportsDB have a read-only repository verdict;
- matrix, manifest and backlog agree.

Do not implement SportDB.dev or TheSportsDB.
Do not start Odds-API-IO, HTML/XHR, browser automation, or another provider
family.
