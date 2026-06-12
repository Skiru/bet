# FOOTBALL-GOLDEN-VERTICAL — Live-First Capability Routing and Production Closure

## Model and execution mode

Use **GPT-5.4 HIGH** or **GLM-5 HIGH** in a fresh session on the current worktree.

For GLM-5, keep maximum output at approximately **8192 tokens** and rely on repository checkpoints rather than chat history.

This is an implementation run, not another architecture discussion.

## Primary outcome

Finish football as the first complete, production-grade reference vertical that can later be propagated to basketball, volleyball and hockey.

The final result must answer two separate questions:

1. Is the **football vertical** production-ready?
2. What is the truthful state and role of each football provider?

Do not require every provider to be `PRODUCTION_READY` for the football vertical to be production-ready.

A provider may legitimately remain:

- discovery-only;
- historical enrichment only;
- metadata/cross-reference only;
- shadow-only;
- plan-restricted;
- rejected.

The football vertical is production-ready when every production-required football capability has at least one verified, auditable and temporally safe route.

## Non-negotiable strategy

Use:

`LIVE PROBE -> FAIL FAST -> CAPABILITY DECISION -> MINIMAL IMPLEMENTATION -> END-TO-END LIVE PROOF -> REPLAY -> RERUN -> STOP`

Do not spend the session repeatedly reviewing old reports.

Do not implement a provider before live data proves it can close a real capability gap.

Do not select a provider because it has a free tier.

## Security preflight

The SportDB.dev credential was previously exposed outside environment configuration.

Before any request:

1. require a newly rotated key in `SPORTDB_API_KEY`;
2. never print, persist, commit or include the key in evidence request identities;
3. use `THESPORTSDB_API_KEY` from environment;
4. treat the public TheSportsDB free V1 key only as configuration, not a secret;
5. scan changed files, logs and generated artifacts for credential leakage;
6. stop immediately if a private credential is found in tracked content.

Do not write literal keys into code, tests, prompts or Markdown.

## Read only current sources of truth

Read:

- the current football integration matrix;
- evidence manifest;
- remediation backlog;
- existing API-Sports family report;
- current football discovery and enrichment production code;
- ESPN Football client and tests;
- API-Football client and tests;
- the deprecated TheSportsDB client;
- client/scraper registries;
- fallback/routing logic;
- canonical identity and evidence-store primitives;
- relevant persistence repositories and schema;
- downstream football analysis readers.

Do not reread superseded portfolio reports.

Use targeted searches and line ranges.

## Accepted baseline

Treat as accepted unless a focused test disproves it:

- API-Football discovery works and preserves provider fixture/team identity;
- API-Football free access is limited by available seasons;
- passing the correct current event season is required;
- silently substituting season 2024 for a 2026 event is forbidden;
- ESPN Football is currently the verified primary enrichment path;
- API-Football enrichment may work for accessible historical seasons;
- typed source results, content-addressed evidence, request identity and fail-closed replay exist;
- canonical source crosswalks exist;
- target-event exclusion and provider-ID side attribution exist.

Do not reimplement accepted foundations.

## Phase 1 — define the football capability contract

Inspect actual downstream production consumers and classify every football capability as:

- `REQUIRED`;
- `OPTIONAL`;
- `UNUSED`;
- `OUT_OF_SCOPE`.

At minimum inspect:

1. event discovery and schedule/status;
2. canonical event/team identity;
3. current-season recent form;
4. H2H;
5. fixture/team statistics;
6. standings;
7. lineups, distinguishing predicted and confirmed;
8. injuries and suspensions;
9. venue/context fields used by analysis;
10. cross-provider ID mapping.

Do not add odds, tipster content, weather or browser scraping unless they are already part of the exact football enrichment consumer being closed.

Create one compact machine-readable capability table under:

`.kilo/artifacts/football_golden_vertical/capability_baseline.json`

Maximum 80 JSON lines.

Do not create a planning document.

## Phase 2 — classify the current API-Football limitation correctly

Perform at most **two** API-Football diagnostic requests, only when retained evidence is insufficient.

Prove:

- the source fixture season is passed into the enrichment request;
- a 2026 fixture does not silently become season 2024;
- the provider response represents season/data availability under the current plan.

Use the canonical typed status:

`PLAN_RESTRICTED`

with:

- `retryable=false`;
- `fallback_eligible=true`;
- a capability-specific negative TTL;
- provider error details retained without secrets.

Do not classify this as authentication failure, generic upstream error, not-found or parser failure when the provider response proves a plan/data-range restriction.

Do not hardcode “seasons <= 2024” globally. Record the exact live-observed available range and provider response because free-plan season availability may change.

## Phase 3 — immediate bounded live provider spike

Before implementing anything, run the following live spike.

Use one known canonical current-season 2026 football fixture/team and, when statistics require a completed match, one completed fixture.

### SportDB.dev

Maximum **six requests**:

1. resolve competition and available seasons;
2. retrieve current-season fixtures;
3. retrieve one match by stable match ID;
4. retrieve match statistics;
5. retrieve lineups;
6. one club/team lookup only if required for identity mapping.

### TheSportsDB

Maximum **five requests**:

1. resolve the selected team;
2. resolve/search the selected event;
3. fetch previous team events;
4. fetch event statistics;
5. fetch event lineup.

### Existing sources

- reuse retained ESPN evidence;
- reuse retained API-Football evidence;
- do not repeat existing successful calls merely for newer timestamps.

### Live spike requirements

For every response retain:

- exact sanitized raw bytes;
- full SHA-256;
- deterministic request identity;
- full evidence bundle ID;
- HTTP and provider semantic status;
- source event/team/competition IDs;
- event start and season;
- raw item count;
- accepted/rejected item count;
- latency;
- quota/rate-limit metadata when available.

No implementation is allowed until the live spike is complete.

## Phase 4 — fail-fast provider gates

Evaluate every candidate separately per capability.

### Current-season recent form gate

PASS only if:

- current-season events are available;
- both home and away matches are present;
- stable source event IDs exist;
- stable team IDs exist;
- target event can be excluded;
- every accepted event starts strictly before the target;
- postponed/rescheduled duplicates can be removed;
- enough matches exist for the configured sample;
- missing values remain missing;
- request is repeatable and permitted.

If TheSportsDB free returns a partial or home-only schedule, classify it:

`REJECT_INCOMPLETE_DATA`

for complete recent form, even if it remains useful for metadata.

### Fixture statistics gate

PASS only if:

- exact source event identity exists;
- both provider team IDs exist;
- side attribution uses IDs;
- neither-side/both-side cases fail closed;
- metric units and scales are interpretable;
- null differs from zero;
- raw/accepted/rejected metric counts are available.

### Lineup gate

PASS only if:

- lineup is attached to a stable event ID;
- team/player IDs are present where offered;
- missing/not-yet-published data is distinct from valid empty;
- predicted and confirmed states are not conflated.

### Cross-reference gate

TheSportsDB may be used for ID mapping only if live data actually exposes the expected external provider IDs and they are verified for at least:

- three teams;
- two events;
- no conflicting one-to-many mapping.

Do not assume `idAPIfootball` or `idESPN` fields exist or are correct merely because an old client expected them.

## Phase 5 — capability-specific provider decisions

For each provider and capability assign exactly one:

- `PRIMARY`;
- `FALLBACK`;
- `SHADOW_ONLY`;
- `METADATA_ONLY`;
- `CROSS_REFERENCE_ONLY`;
- `HISTORICAL_ONLY`;
- `PLAN_RESTRICTED`;
- `REJECT_INCOMPLETE_DATA`;
- `REJECT_UNSTABLE`;
- `NOT_SUPPORTED`.

Do not create one provider-wide priority list.

The routing table must be capability-specific, for example:

- discovery;
- current-season recent form;
- historical recent form;
- fixture statistics;
- lineups;
- standings;
- ID cross-reference.

The actual order must be derived from live evidence.

## Phase 6 — select the smallest production architecture

After live gates, select the minimal architecture that closes all `REQUIRED` football capabilities.

Preferred principle:

- retain already certified ESPN capabilities;
- retain API-Football discovery;
- retain API-Football historical enrichment where accessible;
- add at most **one** new provider implementation in this run;
- use the other candidate as shadow/metadata/rejected unless it closes a unique required gap.

Do not re-enable TheSportsDB simply by removing `_HOST_BROKEN`.

Do not register any client until direct live proof and deterministic parser tests pass.

Do not implement a generic multisport provider framework.

## Phase 7 — minimal implementation

Only for the selected provider and selected capability gaps:

1. use canonical typed results;
2. preserve provider event/team IDs;
3. use exact request identity;
4. create source crosswalks;
5. retain content-addressed evidence;
6. implement no-network replay;
7. preserve immutable `analysis_cutoff_at`;
8. preserve valid time and first-seen time;
9. apply temporal filtering before `last_n`;
10. distinguish null from zero;
11. propagate provider failure even if fallback succeeds;
12. implement capability-specific negative caching;
13. add source-specific metrics and bounded logging;
14. keep secrets out of evidence and telemetry.

Do not implement unused endpoints.

## Phase 8 — production football routing

Implement or correct a capability router that returns:

- selected source;
- selected typed result;
- attempted-source results;
- fallback reason;
- evidence bundle IDs;
- temporal eligibility;
- staleness;
- unresolved conflict when sources disagree.

Required rules:

- `PLAN_RESTRICTED` may trigger fallback;
- `NOT_PUBLISHED_YET` may trigger scheduled retry or fallback according to capability;
- `RATE_LIMITED` remains observable;
- parser/schema failures remain observable;
- fallback success does not erase primary failure;
- names-only source matching is forbidden;
- source observations are not overwritten by the selected projection.

Do not route all capabilities through the same provider order.

## Phase 9 — one real end-to-end football proof

Run one complete production workflow.

Use:

- one current/upcoming 2026 fixture for discovery and pre-event enrichment;
- one completed fixture only if final match statistics are required.

Prove:

`live discovery
-> canonical event
-> provider crosswalks
-> capability router
-> current-season form/H2H/stats/lineups as applicable
-> point-in-time filtering
-> normalized persistence
-> downstream football analysis snapshot`

For every `REQUIRED` capability report:

- selected source;
- source event/team IDs;
- semantic status;
- bundle ID;
- temporal eligibility;
- persisted record or explicit transient result.

## Phase 10 — replay, idempotency and failure injection

Using retained evidence:

1. block all outbound network;
2. replay every selected `REQUIRED` capability through the real parser and production consumer;
3. assert semantic equality;
4. run the full football workflow twice in a disposable database;
5. assert zero new logical duplicates on the second run;
6. assert evidence links remain stable;
7. assert changed evidence creates a new auditable version or preserves old history;
8. inject:
   - API-Football `PLAN_RESTRICTED`;
   - selected-provider transport error;
   - malformed provider payload;
   - ambiguous ID mapping;
9. verify fallback and fail-closed behavior.

## Phase 11 — tests

During implementation run focused tests only.

Final sequence:

1. provider live-spike validation;
2. source-specific parser tests;
3. capability-router tests;
4. temporal and side-attribution tests;
5. no-network replay;
6. duplicate-free second run;
7. changed-evidence history test;
8. strict marker and secret scan;
9. Ruff/static/compile checks;
10. full non-live suite exactly once.

Do not repeatedly run the full suite.

## Production-ready gates

Set:

`FOOTBALL_VERTICAL_STATE=PRODUCTION_READY`

only when every `REQUIRED` capability has:

- a verified source route;
- stable source identity;
- typed status propagation;
- point-in-time correctness;
- retained evidence;
- no-network replay;
- failure isolation;
- deterministic persistence or explicit transient semantics;
- direct source-specific tests;
- no unresolved critical/high blocker.

Assign provider integration states independently.

API-Football may remain partially plan-restricted while the football vertical is production-ready through verified capability fallbacks.

## Documentation limit

Update only:

- `INTEGRATION_MATRIX.md`;
- `EVIDENCE_MANIFEST.json`;
- `REMEDIATION_BACKLOG.md`;
- the existing football/API-Sports family report.

Add one compact routing artifact:

`.kilo/artifacts/football_golden_vertical/final_capability_routing.json`

Do not create another long Markdown report.

Maximum new Markdown: **60 lines total**.

## Final response

Return only:

RESULT: PASS | PARTIAL | FAIL
FOOTBALL_VERTICAL_STATE: <state>

LIVE_SPIKE:
api_football=<requests, observed plan range/status>
espn=<reused evidence/live status>
sportdb=<requests, bundle IDs, capability decisions>
thesportsdb=<requests, bundle IDs, capability decisions>

CAPABILITY_ROUTING:
discovery=<ordered sources>
recent_form_current=<ordered sources>
recent_form_historical=<ordered sources>
h2h=<ordered sources>
fixture_stats=<ordered sources>
lineups=<ordered sources>
standings=<ordered sources>
cross_reference=<ordered sources>

SELECTED_NEW_PROVIDER:
<provider or NONE>

PROVIDER_STATES:
espn-football=<state/role>
api-football=<state/role>
sportdb=<state/role>
thesportsdb=<state/role>

END_TO_END:
target_fixture=<IDs>
required_capabilities=<PASS/PARTIAL per capability>
snapshot=<PASS/FAIL>

REPLAY:
<per selected capability>

IDEMPOTENCY:
<first/second logical counts and deltas>

FAILURE_INJECTION:
plan_restricted=<result>
transport_error=<result>
malformed_payload=<result>
ambiguous_mapping=<result>

TESTS:
focused=<result>
full_non_live=<result>
lint_static=<result>
secret_scan=<result>

REMAINING_BLOCKER:
<NONE or exactly one>

CHANGED_FILES:
<paths only>

## Stop rule

Stop after the football golden vertical gate.

Do not begin propagation to basketball, volleyball or hockey.
Do not begin Odds-API-IO or browser integrations.
Do not produce another architecture proposal without executing the live spike.
