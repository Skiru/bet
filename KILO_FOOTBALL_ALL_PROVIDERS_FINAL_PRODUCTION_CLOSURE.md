# FOOTBALL GOLDEN VERTICAL — ALL-PROVIDERS FINAL PRODUCTION CLOSURE

## Model and execution mode

Use **GPT-5.4 with reasoning effort HIGH** in a fresh Kilo session on the
existing worktree.

This is the final football enrichment implementation and certification run.

It is not another provider research report, architecture essay, or portfolio
audit. Every investigation must lead immediately to one of:

- production implementation;
- shadow-only implementation;
- explicit rejection with retained evidence;
- a truthful external blocker.

Required execution order:

`RECOVER STATE
-> INVENTORY ALL PROVIDERS
-> FREEZE CAPABILITY CONTRACT
-> RUN BOUNDED LIVE MATRIX
-> FAIL FAST
-> SELECT ROUTES
-> IMPLEMENT MINIMAL COMPLETE ARCHITECTURE
-> CURRENT 2026 E2E
-> HISTORICAL CROSS-PROVIDER PROOF
-> OFFLINE REPLAY
-> SECOND RUN
-> FAILURE INJECTION
-> CERTIFY
-> STOP`

The final result must be exactly:

- `PRODUCTION_READY`; or
- `PARTIAL` with exactly one highest-priority blocker.

Do not preserve any existing `PRODUCTION_READY` claim without direct execution
proof.

---

# 0. Context, worktree, and recovery discipline

Before editing:

1. record the real HEAD commit;
2. record `git status --short`;
3. save a binary backup patch;
4. list tracked and untracked task files;
5. preserve unrelated changes;
6. never run `git reset`, `git clean`, or destructive checkout;
7. exclude ZIP files, `.DS_Store`, caches, prompt copies, and old generated
   review directories from production staging.

Use targeted searches, exact paths, and narrow line ranges. Do not dump large
files into the conversation.

After every phase update:

`.kilo/artifacts/football_all_providers_final/checkpoint.json`

The checkpoint must contain only:

- current phase;
- completed gates;
- changed files;
- focused test results;
- live request counts and remaining quota;
- retained bundle IDs;
- current blocker;
- one next command.

If context is compacted or the run is resumed, continue from checkpoint plus
`git diff`. Never repeat passed live probes.

---

# 1. Security gate

Credentials must be read only from environment/configuration abstractions.

Expected variables may include:

- `API_FOOTBALL_KEY`;
- `SPORTDB_API_KEY`;
- `FOOTBALL_DATA_API_KEY`;
- `THESPORTSDB_API_KEY`;
- existing odds-provider variables.

Requirements:

- require a rotated SportDB.dev key;
- never print, log, persist, or commit private keys;
- exclude credentials from request identities and evidence;
- sanitize URLs when credentials can appear in their path;
- scan tracked files, current diff, logs, evidence, and final ZIP;
- stop immediately if a private credential is found in tracked content.

Do not bypass authentication, anti-bot controls, or access restrictions.

---

# 2. Inventory every available football provider

Perform a repository-wide inventory before changing routing.

Inspect:

- client and scraper registries;
- discovery sources;
- enrichment clients;
- fallback chains;
- environment/configuration;
- deterministic and live tests;
- source-health telemetry;
- audit integration keys.

The mandatory initial candidate list is:

## Licensed or official API candidates

- API-Football / API-Sports;
- SportDB.dev;
- football-data.org;
- TheSportsDB.

## Public or unofficial data candidates already present in the repository

- ESPN Football;
- Flashscore Football;
- Understat;
- FBref.

## Discovery or odds sources that must remain separate unless they expose a
## verified enrichment capability

- Odds-API-IO;
- The Odds API / `odds-api`;
- Betclic;
- any other registered football source discovered in the repository.

Also discover any additional football provider not listed above.

For each provider record:

- exact integration key;
- registration path;
- credential availability, without value;
- access method;
- implemented operations;
- production callsites;
- deterministic tests;
- current live evidence;
- legal/operational restrictions;
- current truthful state.

Do not assume a provider is active because a client class or credential exists.

Do not require every provider to be used. Every provider must be evaluated and
assigned a truthful capability-specific role or rejection.

Persist:

`.kilo/artifacts/football_all_providers_final/provider_inventory.json`

---

# 3. Freeze the football capability and metric contract

Derive capability requirements from the actual betting-analysis feature
contract, model inputs, and downstream readers.

Classify every capability as:

- `P0_REQUIRED`;
- `P1_ENHANCEMENT`;
- `SEPARATE_PIPELINE`;
- `OUT_OF_SCOPE`.

At minimum evaluate:

1. event discovery, status, and kickoff;
2. canonical competition/event/team identity;
3. current-season recent form;
4. H2H;
5. standings and competition context;
6. historical fixture results;
7. fixture/team match statistics;
8. event timeline;
9. injuries and suspensions;
10. roster availability;
11. predicted lineups;
12. confirmed lineups;
13. player match statistics;
14. venue and referee context;
15. cross-provider identity;
16. advanced metrics such as xG when available.

Odds, weather, news, and tipster/editorial data may be `SEPARATE_PIPELINE` only
when an actual subsystem owns them.

## Required football match-statistics schema

For completed-match enrichment evaluate at least:

- goals;
- corners;
- total shots;
- shots on target;
- shots off target or blocked when available;
- possession;
- fouls;
- yellow cards;
- red cards;
- offsides;
- saves;
- passes and pass accuracy when available;
- expected goals;
- big chances or equivalent advanced chance metrics when available.

For every normalized metric define:

- canonical name;
- provider source path;
- unit;
- scale;
- team/event/player granularity;
- total, average, percentage, or rate semantics;
- null versus true zero;
- temporal availability;
- aggregation rules;
- provider coverage.

Never require a provider to fabricate an unsupported metric.

A provider lacking corners or another required metric cannot be the sole
primary source for the complete fixture-statistics capability.

Persist:

`.kilo/artifacts/football_all_providers_final/capability_contract.json`

and:

`.kilo/artifacts/football_all_providers_final/metric_contract.json`

---

# 4. Canonical architecture gate

Before provider integration, verify or implement these shared foundations.

## One canonical source-result contract

Exactly one production definition of:

- `SourceResultStatus`;
- `SourceOperationResult`;
- evidence references;
- parser diagnostics;
- retry and quota metadata.

Required statuses include:

- `SUCCESS`;
- explicit valid empty;
- `NOT_FOUND`;
- `NOT_PUBLISHED_YET`;
- `NOT_SUPPORTED`;
- `AMBIGUOUS`;
- `PLAN_RESTRICTED`;
- `AUTHENTICATION_ERROR`;
- `BLOCKED`;
- `RATE_LIMITED`;
- `TRANSPORT_ERROR`;
- `UPSTREAM_ERROR`;
- `PARSE_ERROR`;
- `SCHEMA_ERROR`;
- `EVIDENCE_ERROR`.

All provider clients, adapters, and orchestration import the same types.

## Typed capability router

The production router must return:

- capability;
- canonical target and cutoff;
- attempted sources in order;
- every source status and error code;
- source-native IDs;
- request identities;
- evidence bundles;
- freshness and temporal eligibility;
- conflicts;
- selected source and result;
- fallback reason.

Fallback success must never erase primary-source failure.

## Fixture-scoped point-in-time model

The production source of truth must preserve:

- canonical fixture;
- non-null team/scope key;
- capability;
- source;
- request identity;
- evidence bundle or payload hash;
- semantic status;
- source-native references;
- observed, first-seen, valid, and cutoff times;
- parser/schema version;
- normalized payload.

Source observations are append-only.

Selected projections are keyed by fixture, scope, capability, and cutoff.

Global `team_form` may be a latest cache only, never historical snapshot truth.

Changed evidence creates a new observation while preserving the previous one.

Downstream football analysis must read the fixture-scoped projection.

---

# 5. Live-test dataset

Use one controlled dataset across providers.

## Current operational target

One real current/upcoming 2026 football event for:

- discovery;
- current recent form;
- standings;
- lineups/publication status;
- downstream pre-match snapshot.

## Completed-match statistics sample

Use at least:

- three completed matches;
- from at least two competitions;
- one match with complete statistics;
- one match from a different competition;
- one match with sparse, partial, or empty statistics.

Where possible, query the same completed match from multiple providers.

## Historical cross-provider identity target

Use one real event in a season accessible to API-Football for:

- real API-Football fixture/team IDs;
- independently discovered ESPN event/team IDs;
- optional mappings to SportDB.dev, football-data.org, and TheSportsDB;
- exact competition, participants, and kickoff matching.

No synthetic or copied provider IDs are permitted.

---

# 6. Mandatory bounded live provider matrix

Live probes occur before new provider implementation.

Capture once and debug through replay.

Global hard limit: **50 new provider requests**.

Stop earlier when rate limits or quota become unsafe.

## ESPN Football

Maximum eight new requests, preferably fewer through retained evidence.

Evaluate:

- current event discovery;
- recent form;
- H2H;
- standings;
- fixture statistics;
- lineups;
- event status/timeline where implemented;
- competition coverage.

Because ESPN is an unofficial/public endpoint integration, record operational
stability, schema drift risk, and failure semantics explicitly.

## SportDB.dev — mandatory deep evaluation

Maximum twelve requests.

SportDB.dev must be evaluated as a full enrichment candidate, not merely as
discovery redundancy.

Use native SportDB competition, fixture, match, club, and player IDs.

Evaluate:

- current-season fixtures;
- current discovery;
- recent-form source completeness;
- match lookup;
- match statistics;
- corners;
- shots and shots on target;
- possession;
- fouls;
- cards;
- offsides;
- advanced metrics when supplied;
- standings;
- lineups;
- event/player identity.

Do not send IDs from another provider unless an explicit cross-reference proves
equivalence.

Test the three completed matches and two competitions from the common dataset.

## API-Football

Maximum six new requests.

Evaluate:

- current key season availability;
- historical discovery;
- historical recent form;
- H2H;
- standings;
- fixture statistics;
- events;
- lineups;
- injuries;
- player statistics.

A provider response reporting an unavailable season or subscription range must
be `PLAN_RESTRICTED`, non-retryable, fallback-eligible, observable, and
negative-cached.

Never silently substitute an older season.

## football-data.org

Maximum six requests.

Evaluate:

- competition/match discovery;
- current standings;
- team match history/recent form;
- H2H;
- canonical competition/team/match identity;
- current-season coverage and rate limits.

Do not expect detailed corners or full fixture statistics unless live payloads
prove them.

## TheSportsDB

Maximum six requests.

Evaluate:

- three teams;
- two events;
- league/season identity;
- event lookup;
- event statistics;
- lineups;
- standings;
- external provider ID fields;
- mapping conflicts;
- schedule completeness.

Explicitly verify free-tier limitations, including whether team previous/next
events are home-only and whether fixture statistics omit betting-critical
metrics such as corners.

TheSportsDB must not be the sole primary recent-form or complete
fixture-statistics provider when data is incomplete.

## Understat

Maximum four requests when the selected competitions are covered.

Evaluate as a specialized advanced-statistics source:

- event identity;
- team identity;
- xG;
- shot-level data;
- competition coverage;
- historical/current freshness;
- replay stability.

Do not use it as a general football provider outside verified covered leagues.

## FBref

Maximum four requests when existing repository access remains permitted and
stable.

Evaluate as a historical/advanced dataset:

- team and match identity;
- shooting;
- passing;
- possession;
- defense;
- player/team statistics;
- update latency;
- competition coverage;
- parsing stability.

Respect access limits and do not circumvent blocking.

FBref must not become a current live primary without explicit live proof.

## Flashscore

Maximum four requests through the existing registered integration only.

Evaluate:

- live/current match stats;
- corners and team stats;
- native IDs;
- schema stability;
- temporal semantics;
- access reliability.

Do not bypass anti-bot protections.

Unless access and replay are stable, classify it as `SHADOW_ONLY` or
`REJECT_UNSTABLE`.

## Odds providers and Betclic

Do not include odds in the enrichment snapshot.

Verify that they remain in the separate odds pipeline and do not contaminate
football provider scoring.

---

# 7. Hard provider gates and scoring

For each provider and capability assign:

- `PRIMARY`;
- `FALLBACK`;
- `SHADOW_ONLY`;
- `CROSS_REFERENCE_ONLY`;
- `METADATA_ONLY`;
- `HISTORICAL_ONLY`;
- `PLAN_RESTRICTED`;
- `REJECT_INCOMPLETE_DATA`;
- `REJECT_UNSTABLE`;
- `NOT_SUPPORTED`.

## Hard gates

A capability route passes only when:

- source-native identity is stable;
- participant sides use IDs;
- temporal eligibility is correct;
- target event is excluded where required;
- null is distinct from zero;
- exact raw evidence is retained;
- no-network replay passes;
- parser fails closed;
- current access is repeatable;
- provider usage is operationally permissible.

Hard-gate failure cannot be overridden by a numerical score.

## Comparative score

For hard-gate survivors score each capability:

- data completeness: 20;
- identity quality: 15;
- temporal correctness: 15;
- competition/current-season coverage: 10;
- freshness/publication semantics: 10;
- schema stability: 10;
- replay/evidence quality: 10;
- quota/cost efficiency: 5;
- operational reliability: 5.

Use score only to rank providers that have passed all hard gates.

Persist:

`.kilo/artifacts/football_all_providers_final/provider_capability_matrix.json`

---

# 8. Select the minimal complete production routing

Do not use a single provider-wide priority order.

Build routing per capability.

Expected hypotheses to verify, not assumptions:

- current discovery: ESPN and/or SportDB.dev;
- detailed fixture stats: SportDB.dev, ESPN, accessible API-Football;
- current recent form: ESPN, SportDB.dev, football-data.org;
- historical recent form: API-Football, football-data.org, ESPN;
- H2H: ESPN, football-data.org, accessible API-Football;
- standings: SportDB.dev, football-data.org, ESPN, accessible API-Football;
- xG/advanced metrics: Understat or FBref for covered competitions;
- lineups: SportDB.dev, ESPN, API-Football, TheSportsDB shadow;
- metadata/cross-reference: internal crosswalk, TheSportsDB shadow;
- fragile XHR/HTML sources: shadow or specialized fallback only after hard
  gates.

## Critical redundancy rule

For these critical current capabilities prefer two independent verified routes:

- discovery;
- current recent form;
- standings;
- required detailed fixture statistics.

If only one route exists, the vertical may be certified only with:

`CURRENT_REDUNDANCY=SINGLE_SOURCE_CURRENT`

and an explicit operational risk.

If SportDB.dev passes detailed-statistics gates, implement it as a production
route. Do not leave a proven rich P0 provider as an unused experiment.

Do not implement providers that add no unique capability, redundancy, or
quality improvement.

---

# 9. Provider implementations

For every selected production or shadow provider:

- use the canonical typed result;
- preserve native IDs;
- use canonical request identity;
- retain exact sanitized raw bytes;
- create deterministic evidence bundles;
- normalize metrics through the metric contract;
- preserve raw/accepted/rejected counts;
- propagate status through the router;
- enforce analysis cutoff;
- use append-only observations;
- persist selected fixture-scoped projections;
- add source-specific health metrics;
- apply bounded retries, jitter, quota handling, circuit breaking, and
  capability-specific negative caching;
- keep private credentials out of telemetry.

No provider-specific columns should be added to shared domain tables when a
generic observation/reference model is sufficient.

---

# 10. Real current-2026 end-to-end proof

Execute actual production entry points:

`live discovery
-> canonical fixture
-> source mappings
-> capability router
-> provider attempts
-> immutable observations
-> selected projections
-> normalized point-in-time snapshot
-> downstream football analysis read`

For every P0 capability record:

- attempted providers and statuses;
- selected provider;
- native IDs;
- request identity;
- evidence bundle;
- cutoff and valid time;
- observation/projection IDs;
- normalized value or explicit `UNKNOWN`;
- provider confidence/coverage warning.

Do not manually insert final observations or projections as E2E proof.

---

# 11. Historical real cross-provider proof

Use the plan-accessible historical event.

Persist distinct real mappings for all providers that resolve it.

At minimum require real API-Football and ESPN mappings.

Test:

- exact participant set;
- competition mapping;
- kickoff tolerance;
- zero candidates -> `NOT_FOUND`;
- multiple candidates -> `AMBIGUOUS`;
- wrong participant -> rejected;
- wrong kickoff -> rejected;
- provider disagreement -> preserved conflict.

The historical proof validates cross-provider mechanics without falsely
claiming API-Football current-2026 access.

---

# 12. Offline replay

For every selected P0 route and every provider used in the final snapshot:

1. load exact retained bytes;
2. verify full object hashes and manifest;
3. block network at shared transport/socket level;
4. execute parser;
5. execute router;
6. persist observations/projections;
7. build downstream snapshot;
8. compare semantic output and diagnostics.

Required negative tests:

- unexpected network request;
- missing evidence;
- corrupt evidence;
- mismatched request identity.

Mocks of already-parsed values are not replay.

---

# 13. Idempotency and evidence versioning

Use a disposable database with foreign keys enabled.

Run the complete current-2026 vertical twice using identical evidence.

Compare counts and sorted logical identities for:

- canonical fixtures;
- provider source mappings;
- source observations;
- selected projections;
- normalized capability data;
- evidence links;
- final snapshots.

All second-run logical deltas must be zero.

Then change retained evidence deterministically and prove:

- a new observation/version is created;
- old and new observations remain queryable;
- projection policy selects the correct version;
- no previous evidence link is overwritten.

Counts alone do not prove idempotency.

---

# 14. Failure, resilience, and operational tests

Inject:

- `PLAN_RESTRICTED`;
- authentication error;
- rate limit;
- transport timeout;
- 5xx upstream failure;
- malformed JSON;
- schema drift;
- partial statistics;
- corrupt evidence;
- ambiguous crosswalk;
- provider disagreement;
- stale observation;
- lineup not yet published.

Verify:

- attempted-source history is retained;
- fallback is capability-specific;
- primary failure remains visible;
- circuit breaker and negative cache work;
- retry budget is bounded;
- fallback success does not erase uncertainty;
- downstream snapshot remains truthful.

Add source-health metrics for:

- success/error/status counts;
- latency;
- quota remaining;
- freshness;
- coverage;
- fallback selection;
- schema rejections;
- evidence failures.

---

# 15. Final validation

Run in this order:

1. canonical result tests;
2. provider parser tests;
3. metric normalization tests;
4. provider capability matrix tests;
5. router policy tests;
6. temporal and identity tests;
7. migration tests with foreign keys enabled;
8. real current-2026 E2E;
9. historical cross-provider E2E;
10. offline replay;
11. duplicate-free second run;
12. versioning;
13. failure injection;
14. strict live-marker validation;
15. secret scan;
16. Ruff on every touched source/test file with zero errors;
17. compile/static checks;
18. full non-live suite exactly once.

Normal non-live tests must perform zero external provider calls.

---

# 16. Atomic audit truth

Update atomically:

- integration matrix;
- evidence manifest;
- remediation backlog;
- existing football/API-Sports report.

Create only:

- `provider_inventory.json`;
- `capability_contract.json`;
- `metric_contract.json`;
- `provider_capability_matrix.json`;
- `final_capability_routing.json`;
- `end_to_end_certification.json`;
- `CERTIFICATION_INDEX.json`;
- `checkpoint.json`.

Maximum new Markdown: 60 lines.

`CERTIFICATION_INDEX.json` must link every final claim to:

- capability/provider;
- source-native IDs;
- request identity;
- evidence manifests/raw hashes;
- test node IDs;
- observation/projection identities;
- audit entries.

All audit states, evidence grades, bundle IDs, provider roles, and blockers must
agree.

---

# 17. Self-contained certification bundle

Create:

`FOOTBALL_ALL_PROVIDERS_FINAL_CERTIFICATION_BUNDLE.zip`

Include:

- real base and head commit hashes;
- scoped binary patch;
- exact changed-file list;
- all changed production/schema/migration/test files;
- all machine-readable certification artifacts;
- current audit files;
- every cited manifest and sanitized raw object;
- redacted request identities;
- live outputs;
- replay outputs;
- migration outputs;
- idempotency identities;
- resilience/failure outputs;
- lint/static/full-suite/secret outputs.

Exclude:

- secrets;
- prompt files;
- unrelated ZIPs;
- caches;
- `.DS_Store`;
- unrelated sports/provider changes.

Validate by:

1. extracting to a clean temporary directory;
2. verifying `CERTIFICATION_INDEX.json`;
3. recomputing every hash;
4. pointing `EVIDENCE_ROOT` to extracted evidence;
5. running offline replay;
6. proving zero network calls;
7. verifying the scoped patch contains every required changed file.

---

# Production-ready rule

Set:

`FOOTBALL_VERTICAL_STATE=PRODUCTION_READY`

only when:

- every P0 capability has a verified current route or a policy-approved
  transient unavailable state;
- no P0 capability is permanently unsupported across all routes;
- the detailed-statistics contract, including corners when required, is
  satisfied by at least one production provider;
- every available provider has a truthful capability-specific role or rejection;
- current-2026 E2E passes;
- historical cross-provider identity proof passes;
- fixture-scoped point-in-time downstream snapshots pass;
- exact raw evidence is retained;
- offline replay passes;
- second-run logical deltas are zero;
- changed evidence preserves history;
- failure/resilience tests pass;
- touched-file lint is clean;
- audit truth is consistent;
- extracted certification bundle validates;
- no critical/high blocker remains.

Provider states remain independent and capability-specific.

Do not claim universal competition coverage beyond tested competitions.

If current critical capabilities have only one provider, report:

`CURRENT_REDUNDANCY=SINGLE_SOURCE_CURRENT`

without hiding the risk.

Otherwise report:

`CURRENT_REDUNDANCY=MULTI_SOURCE_CURRENT`.

If any mandatory gate fails, return `PARTIAL` with exactly one highest-priority
blocker.

---

# Required final response

Return only:

RESULT: PASS | PARTIAL | FAIL
FOOTBALL_VERTICAL_STATE: <state>
CURRENT_REDUNDANCY: MULTI_SOURCE_CURRENT | SINGLE_SOURCE_CURRENT
CERTIFIED_SCOPE: <competitions, capabilities, temporal scope>

PROVIDER_INVENTORY:
<one concise role/state line per discovered provider>

REAL_TARGET_2026:
<canonical ID and native provider IDs>

P0_CAPABILITIES:
<one line per capability: attempted routes, selected route, status, bundle>

DETAILED_STATS:
<provider comparison and required metric coverage including corners>

HISTORICAL_CROSS_PROVIDER:
<real source IDs and crosswalk result>

ROUTER:
<attempt history, typed fallback, conflicts, negative cache>

SNAPSHOT:
<fixture scope, cutoff, normalized payload, downstream read>

REPLAY:
<one line per selected P0 route>

IDEMPOTENCY:
<first/second counts, sorted identity deltas, semantic equality>

VERSIONING:
<old/new observation history>

RESILIENCE:
<plan, auth, rate, timeout, 5xx, schema, corruption, ambiguity results>

TESTS:
<focused/live/full/lint/static/secret>

AUDIT_CONSISTENCY:
<PASS/FAIL>

CERTIFICATION_BUNDLE:
<path, index/hash validation, clean extraction, offline replay>

REMAINING_BLOCKER:
<NONE or exactly one>

CHANGED_FILES:
<paths only>

## Stop rule

Stop immediately after football certification.

Do not propagate to basketball, volleyball, hockey, or another sport in this
run.
