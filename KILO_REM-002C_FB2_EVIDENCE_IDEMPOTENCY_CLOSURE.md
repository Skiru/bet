# REM-002C-FB2 — API-Football Enrichment Evidence and Idempotency Closure

## Model

Use **GPT-5.4 with reasoning effort MEDIUM**.

Escalate to HIGH only if the canonical evidence-store contract or persistence
model is genuinely defective.

## Mission

Close exactly the two remaining blockers for:

`api-football::football::EVENT_AND_ENRICHMENT::default`

1. replayable retained evidence for API-Football enrichment;
2. direct idempotency proof for the real API-Football enrichment production path.

Do not redesign discovery, typed statuses, crosswalks, temporal filtering,
ESPN, or the wider provider architecture.

Do not work on another sport or provider.

## Accepted proof

Treat these as accepted unless a focused test disproves them:

- API-Football discovery bundle:
  `de648d03aaffe6b3707f6804e5eeb9e73e1d9c95a92d0a084a0bc684d31f2bdd`
- discovery no-network replay;
- discovery duplicate-free rerun;
- production entry:
  `bet.stats.enrichment._try_api_sports_fetch()`;
- API-Sports identity resolution:
  `_resolve_api_sports_fixture_identity()`;
- target-event exclusion and strict cutoff filtering;
- provider-ID side attribution;
- actual fallback order:
  `ESPN Football primary -> API-Football fallback`;
- test inventory: 662 non-live tests with zero unintended removals.

Do not repeat those audits.

## Read only necessary files

Read:

- `@/docs/audits/sports-integrations/2026-06-11/INTEGRATION_MATRIX.md`
- `@/docs/audits/sports-integrations/2026-06-11/EVIDENCE_MANIFEST.json`
- `@/docs/audits/sports-integrations/2026-06-11/REMEDIATION_BACKLOG.md`
- `@/docs/audits/sports-integrations/2026-06-11/repairs/REM-002B_API_SPORTS_FAMILY.md`
- API-Football client;
- shared evidence implementation and configuration;
- football enrichment production consumer;
- `StatsRepo` and relevant persistence models;
- focused API-Sports/football tests.

Use targeted searches and line ranges. Do not load superseded portfolio reports.

## Known unresolved claims

The audit currently references:

- fixture-statistics bundle:
  `2b0ed4ba3c4a80b2ebff7670c1645d0dd89a8c9c8e887f71f9284bb71691a0af`
- team-fixtures bundle:
  `b01f22fbb05326dc37de3230fe1accacd83c54586f3c2d17bdceb6fb76359e16`

Their raw objects were not found in `.kilo/artifacts`.

Do not assume `.kilo/artifacts` is the canonical runtime evidence store.

## Phase 1 — locate evidence before making live calls

1. Determine the configured runtime evidence root from code and configuration.
2. Resolve each claimed bundle ID through the canonical evidence-store API.
3. Locate its manifest and every referenced object.
4. Recompute:
   - each full object SHA-256;
   - the deterministic bundle SHA-256.
5. Verify sanitization metadata, operation identity, parser version and
   namespaced source references.
6. Check cache-backed evidence locations and content-addressed object paths.
7. Do not treat an audit summary or bundle ID string as retained evidence.
8. Do not perform a live call while a valid retained object may exist elsewhere.

Classify each bundle:

- `VERIFIED`;
- `MANIFEST_MISSING`;
- `OBJECT_MISSING`;
- `HASH_MISMATCH`;
- `NOT_A_REAL_BUNDLE`.

## Phase 2 — reconcile the CORE operation list

The earlier output listed:

- `get_fixtures_result`;
- `get_fixture_stats_result`;
- `get_team_last_fixtures_result`;
- `get_event_fixture_result`.

Determine which are truly production-reachable `CORE` operations.

For `get_event_fixture_result`:

- identify whether it performs a distinct network operation;
- identify whether it is only a helper/lookup over already retained fixture data;
- either provide its evidence/replay path or reclassify it truthfully as
  `OPTIONAL`, `INTERNAL_HELPER`, or `DEAD_OR_UNREACHABLE`.

Do not leave the audit claiming a CORE operation with no evidence requirement.

## Phase 3 — minimal recapture only when required

If enrichment evidence is genuinely absent or corrupt, execute the minimum
permitted live recapture:

- at most one fixture-statistics request;
- at most one team-fixtures/recent-form request;
- at most one additional request only if a genuinely distinct CORE operation
  cannot be represented by the first two.

Maximum: **3 API-Football live requests total**.

Before calling:

- inspect daily/minute quota;
- reuse the already verified fixture/team identity;
- use the same canonical workflow where possible;
- ensure the durable runtime evidence root is configured;
- never write runtime evidence only to `.kilo/artifacts`.

For each response:

1. sanitize exact raw bytes;
2. atomically retain the content-addressed object;
3. compute full SHA-256;
4. build a deterministic operation bundle;
5. exclude volatile metadata from bundle identity;
6. link bundle to the corresponding production enrichment operation/observation;
7. record no secret headers or URLs.

Do not preserve the old claimed bundle ID if the underlying object never
existed. Replace the claim with the newly verified full bundle ID.

## Phase 4 — no-network enrichment replay

For every production-reachable CORE enrichment network operation:

1. load the bundle using the public evidence-store API;
2. verify manifest and all object hashes;
3. block outbound network at transport/socket level;
4. execute the same typed parser and production consumer path;
5. compare live/captured and replay:
   - semantic payload;
   - provider identities;
   - status;
   - parser diagnostics;
   - normalized output;
6. fail closed on missing/corrupt object or unexpected network request.

Add focused deterministic tests equivalent to:

- fixture-stat replay;
- team-fixtures replay;
- missing object fails closed;
- corrupt object fails closed.

Do not mock the parser output. Replay the retained provider bytes.

## Phase 5 — direct API-Football enrichment idempotency

Use a disposable database.

Invoke the real API-Football enrichment production path, not the ESPN path and
not a directly constructed repository row.

Use retained evidence for both runs.

Capture first-run and second-run counts/identities for all applicable outputs:

- canonical fixture;
- `fixture_sources`;
- team-form/recent-form rows;
- fixture-stat or normalized-stat observations if persisted;
- source observations/runs if persisted;
- evidence links.

Requirements:

- second run creates zero new logical domain rows;
- source-event references are stable and deduplicated;
- evidence links are stable and deduplicated;
- missing values remain missing;
- changed input evidence would produce a new observation/version rather than
  silently overwrite historical evidence.

If fixture statistics are intentionally transient and not persisted:

- prove that from the production design and consumer;
- mark fixture-stat persistence idempotency `NOT_APPLICABLE`;
- still prove deterministic replay and downstream semantic equality;
- do not invent a new persistence table solely to satisfy this task.

Add a dedicated focused test for the API-Football path. Reusing an ESPN
idempotency test is forbidden.

## Phase 6 — audit consistency

After proof:

- remove unsupported claimed bundle IDs;
- add only verified full bundle IDs;
- ensure matrix, manifest, backlog and family report agree;
- retain `LIVE_PARTIAL` until both blockers pass;
- promote to `PRODUCTION_READY` only after direct proof.

Update only:

- `INTEGRATION_MATRIX.md`;
- `EVIDENCE_MANIFEST.json`;
- `REMEDIATION_BACKLOG.md`;
- existing `REM-002B_API_SPORTS_FAMILY.md`.

Add no more than 25 lines to the existing report.

Do not create a new report.

## Tests and token budget

Run:

1. focused evidence-store tests;
2. focused API-Football enrichment replay tests;
3. focused API-Football idempotency test;
4. Ruff/static/compile checks on changed files;
5. full non-live suite exactly once only if production or shared test code changed.

Do not rerun discovery live proof.
Do not rerun other sports.
Do not generate architecture documentation or copied command logs.

## Final-state rule

Set API-Football to `PRODUCTION_READY` only when:

- every production-reachable CORE enrichment operation has retained verified
  evidence;
- no-network replay succeeds from exact raw objects;
- the real production consumer is exercised;
- direct API-Football enrichment idempotency is proved;
- audit artifacts contain no unsupported bundle claim;
- no critical/high blocker remains.

Otherwise retain `LIVE_PARTIAL` and name exactly one blocker.

## Required final response

Return only:

RESULT: PASS | PARTIAL | FAIL
FINAL_STATE: <state>

CORE_OPERATIONS:
<operation=CORE/OPTIONAL/HELPER/UNREACHABLE>

EVIDENCE:
fixture_stats=<old status, final full bundle ID or missing>
team_fixtures=<old status, final full bundle ID or missing>
other_core=<bundle IDs or none>
canonical_store_root=<redacted safe path>

LIVE_REQUESTS:
<count 0-3, operation and quota only>

REPLAY:
<one line per CORE operation, network_blocked and hash verification>

IDEMPOTENCY:
fixtures=<first/second>
fixture_sources=<first/second>
team_form=<first/second>
normalized_stats=<first/second or NOT_APPLICABLE>
evidence_links=<first/second>

TESTS:
focused=<result>
full_non_live=<result or NOT_RUN_WITH_REASON>
lint_static=<result>

GATE_DELTA:
<concise>

REMAINING_BLOCKER:
<NONE or exactly one>

CHANGED_FILES:
<paths only>

## Stop

Stop after the API-Football evidence/idempotency gate.

Do not start basketball, volleyball, hockey, Odds-API-IO, SportDB.dev,
TheSportsDB, HTML/XHR, browser automation or another provider family.
