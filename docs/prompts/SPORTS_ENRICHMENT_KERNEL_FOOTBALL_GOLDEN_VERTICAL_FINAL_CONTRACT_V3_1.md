# SPORTS ENRICHMENT KERNEL + FOOTBALL GOLDEN VERTICAL
# FINAL IMPLEMENTATION CONTRACT V3.1

## 0. Authority and execution mode

This document is the binding implementation contract for the coding agent.

- Repository: `https://github.com/Skiru/bet`
- Reviewed public branch: `main`
- Reviewed public baseline: `ad9f6a8`
- Current scope: Football enrichment only
- Architectural output: reusable sports-enrichment kernel plus Football module
- Implementation reasoning: `HIGH`
- Final adversarial certification reasoning: `XHIGH`
- Agent role: implement, live-qualify, test, migrate, roll out, and certify
- Forbidden role: replacing this contract with another plan or architecture

The public `main` must be rechecked at the start. If local HEAD is newer, retain
already-correct code and implement only missing requirements. Do not weaken a
gate because later code differs from the reviewed baseline.

Execution order:

`BASELINE AND SECURITY
→ CALL GRAPH AND DEFECT PROOFS
→ GENERIC SPORTS KERNEL
→ FOOTBALL CONTRACTS
→ CANDIDATE ADAPTERS
→ BOUNDED LIVE QUALIFICATION
→ SELECTED PRODUCTION ADAPTERS
→ ROUTING AND SNAPSHOTS
→ SHADOW/CANARY
→ REAL E2E
→ OFFLINE REPLAY
→ CONCURRENCY/IDEMPOTENCY/VERSIONING
→ RESILIENCE/PERFORMANCE
→ FINAL CERTIFICATION`

Do not implement another sport. Reusability is proved by generic-kernel contract
tests, not by starting basketball, volleyball, hockey, or tennis.

---

# 1. Definition of done

The certified production path must be:

`provider transport response
→ exact durable evidence
→ canonical source result
→ provider-native entity identities
→ canonical entity reconciliation
→ versioned normalized DTO
→ temporal and lifecycle validation
→ append-only source observation
→ capability and metric selection
→ atomic immutable fixture snapshot
→ downstream Football analysis`

Final states:

- `PRODUCTION_READY_MULTI_SOURCE`
- `PRODUCTION_READY_SINGLE_SOURCE_RISK`
- `PARTIAL`

`PRODUCTION_READY_MULTI_SOURCE` requires all mandatory gates plus two genuinely
independent certified current routes for each critical current capability.

`PRODUCTION_READY_SINGLE_SOURCE_RISK` requires all mandatory gates except the
second independent route, an explicit degraded mode, reduced confidence,
provider-health alerting, and a documented external reason for missing
redundancy. Settlement-critical event identity/status still requires two
independent agreeing sources or one official source.

`PARTIAL` is mandatory when:

- any P0 capability lacks a safe route or truthful availability state;
- production bypasses the new service;
- downstream reads legacy mutable caches;
- a snapshot is not atomic and point-in-time safe;
- evidence or replay is incomplete;
- identity is synthetic, names-only, or ambiguous;
- concurrency/idempotency/versioning fails;
- certification cannot reproduce the result from the extracted bundle.

A provider never receives a global production-ready state. Every role is:

`provider + capability + competition/season scope + verification expiry`.

---

# 2. Architecture split required for reuse

## 2.1 Generic sports-enrichment kernel

The following must be sport-neutral:

- canonical source-result contract;
- request identity;
- evidence store;
- provider registry and usage policy;
- source entity references;
- enrichment runs and attempt history;
- append-only observations;
- current projections and projection history;
- immutable analysis snapshots;
- generic capability router;
- provider health, quota, circuit breaker, metrics, and tracing;
- replay transport;
- idempotency and concurrency controls.

Generic tables and APIs must not require `team_id`, `home`, `away`, football
metric names, or football-specific statuses.

Use generic subjects:

```text
EVENT
PARTICIPANT
COMPETITION
SEASON
ATHLETE
VENUE
OFFICIAL
```

Use generic participant roles:

```text
SIDE_A
SIDE_B
HOME
AWAY
NEUTRAL
```

Football maps its teams to `PARTICIPANT` with `HOME`/`AWAY`. A future tennis
adapter can map athletes to `PARTICIPANT` without schema redesign.

The generic kernel must remain minimal: implement only abstractions exercised
by Football or the mandatory fake-sport contract test. Do not build speculative
sport engines, generic UI, generic settlement, or unused plugin frameworks.

## 2.2 Football module

Football-specific code contains:

- Football capability contract;
- Football metric ontology;
- provider-specific Football adapters;
- Football identity rules;
- Football event lifecycle rules;
- Football routing configuration;
- `FootballEnrichmentService`;
- Football snapshot schema;
- downstream Football integration.

Add one fake-sport kernel contract test proving that the generic kernel accepts
an athlete-vs-athlete event and a non-football metric without schema or router
changes. This is a contract test only, not another sport implementation.

---

# 3. Non-negotiable invariants

1. Never invent, guess, or default missing provider data.
2. HTTP 2xx is not semantic success.
3. `VALID_EMPTY`, `NOT_FOUND`, `NOT_PUBLISHED_YET`, and technical errors are distinct.
4. `PLAN_RESTRICTED` is not authentication failure.
5. Never substitute a historical season for a current target.
6. Every provider identity uses native provider IDs.
7. Names are diagnostics only.
8. Never copy one provider's ID into another provider mapping.
9. Multiple identity candidates are `AMBIGUOUS`; never select the first.
10. Provider failures remain visible after fallback succeeds.
11. Null, blank, and malformed values never become zero.
12. Participant attribution uses native IDs, not list order.
13. Target and future events cannot enter form or H2H.
14. Post-match data cannot enter a pre-match snapshot.
15. Global `team_form` cannot be Football snapshot truth.
16. Every selected datum has exact durable evidence.
17. A manifest without raw evidence is not replay.
18. Mocked normalized or parsed output is not replay.
19. Equal counts alone are not idempotency proof.
20. Changed evidence creates a new observation and preserves the old one.
21. Non-live tests block all external network access.
22. Secrets never enter Git, evidence, request identities, logs, traces, or metrics.
23. Odds remain a separate pipeline.
24. Unofficial/crowd-sourced/scraped data cannot be sole settlement truth.
25. Two wrappers around the same upstream source do not count as independent.
26. An incomplete or partially committed snapshot is never visible downstream.
27. Concurrent identical runs must not duplicate provider calls or domain data.
28. All timestamps are timezone-aware UTC with microsecond-normalized serialization.
29. No acceptance gate may be weakened to obtain PASS.

---

# 4. Baseline defects to prove against actual HEAD

Create focused tests or direct proofs for every item. A newer fixed worktree may
make a test pass; do not force a failure.

- `F01`: source result metadata and enum compatibility are incomplete.
- `F02`: explicit provider-plan errors can be misclassified.
- `F03`: a legacy API-Football method has historical-season default risk.
- `F04`: the existing router is not proved as the production orchestration path.
- `F05`: observation uniqueness can discard changed evidence.
- `F06`: normalized payload is not durably available to downstream.
- `F07`: current snapshot reader may return only metadata/`UNKNOWN`.
- `F08`: standings can use invalid synthetic scope IDs.
- `F09`: global `team_form` remains on the production Football path.
- `F10`: prior E2E/replay/idempotency/certification proofs are incomplete.
- `F11`: repository root contains generated artifacts and credential-like files.
- `F12`: no atomic enrichment-run/snapshot publication boundary is proved.
- `F13`: no concurrency/duplicate-live-request protection is proved.
- `F14`: provider independence/provenance-family is not modeled.
- `F15`: normalized provider payload DTO versions are not explicitly governed.
- `F16`: freshness, negative-cache, and event-lifecycle policies are not explicit.
- `F17`: generic persistence currently assumes team-scoped subjects and is not
  reusable for athlete-based sports.
- `F18`: rollout/shadow/canary and rollback behavior are not certified.
- `F19`: evidence object retention and referenced-object garbage-collection
  safety are not defined.
- `F20`: metrics/tracing may permit high-cardinality fixture labels.
- `F21`: generic subject IDs may lack enforceable foreign-key integrity.
- `F22`: exactly-once upstream calls may be incorrectly assumed across crashes.
- `F23`: pagination/truncation completeness is not uniformly represented.
- `F24`: rate/circuit/quota state may be process-local rather than shared.
- `F25`: technical readiness and legal/usage authorization may be conflated.

P01 must cover `F01–F25`; no defect may be silently omitted.

---

# 5. Canonical source-result contract

Create or consolidate:

`src/bet/integration/source_result.py`

Exactly one production enum:

```python
class SourceResultStatus(StrEnum):
    SUCCESS = "SUCCESS"
    VALID_EMPTY = "VALID_EMPTY"
    NOT_FOUND = "NOT_FOUND"
    NOT_PUBLISHED_YET = "NOT_PUBLISHED_YET"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    AMBIGUOUS = "AMBIGUOUS"
    PLAN_RESTRICTED = "PLAN_RESTRICTED"
    LICENSE_BLOCKED = "LICENSE_BLOCKED"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    BLOCKED = "BLOCKED"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    PARSE_ERROR = "PARSE_ERROR"
    SCHEMA_ERROR = "SCHEMA_ERROR"
    EVIDENCE_ERROR = "EVIDENCE_ERROR"
```

Canonical immutable result:

```python
@dataclass(frozen=True)
class SourceOperationResult[T]:
    status: SourceResultStatus
    value: T | None
    provider: str
    operation: str
    request_identity: str
    evidence_refs: tuple[EvidenceRef, ...]
    bundle_id: str
    retrieved_at: datetime
    provider_updated_at: datetime | None
    valid_from: datetime | None
    valid_to: datetime | None
    http_status: int | None
    error_code: str
    retry_after_seconds: float | None
    retry_count: int
    quota_metadata: Mapping[str, JsonValue]
    parser_diagnostics: Mapping[str, JsonValue]
    schema_fingerprint: str
    parser_version: str
    normalization_version: str
```

Rules:

- all selected Football clients import this contract;
- provider-local duplicate enums/results are forbidden;
- list-returning compatibility methods may remain outside the new production
  path and are explicitly deprecated;
- provider result reports facts only;
- retry and fallback decisions belong to central policies, not provider clients;
- compatibility properties such as `retryable` or `fallback_eligible` may be
  derived, but the router must not trust provider-defined booleans.

Use immutable mapping values or defensive copies so frozen results cannot be
mutated through nested dictionaries.

---

# 6. Versioned normalized DTOs

Create:

`src/bet/enrichment/models.py`

Use validated frozen models or dataclasses with explicit schema versions.

Required normalized DTO families:

- `NormalizedEvent`
- `NormalizedEventStatus`
- `NormalizedParticipant`
- `NormalizedTeamMatch`
- `NormalizedStandingTable`
- `NormalizedStandingRow`
- `NormalizedMetricSet`
- `NormalizedLineupState`
- `NormalizedAvailabilityState`
- `NormalizedRoster`
- `NormalizedVenueContext`
- `NormalizedOfficialContext`
- `NormalizedPlayerMetricSet`

Every DTO includes:

- `schema_version`;
- canonical/native IDs;
- provider;
- source timestamps;
- explicit nullable fields;
- data-completeness metadata;
- validation diagnostics.

No provider adapter may return arbitrary dictionaries on the new production
path.

Create snapshot-schema compatibility tests. A DTO schema change requires a new
version and migration/parser compatibility, not in-place semantic mutation.

---

# 7. Canonical event lifecycle and temporal policy

Create:

`config/event_lifecycle.yaml`

Canonical Football statuses:

```text
SCHEDULED
POSTPONED
DELAYED
CANCELLED
ABANDONED
LIVE
HALFTIME
EXTRA_TIME
PENALTIES
FINAL
AWARDED
UNKNOWN
```

Provider mappings must be explicit and tested.

All source timestamps are parsed to timezone-aware UTC. Naive timestamps are a
schema error unless the provider contract defines an explicit timezone.

## Recent form

- include only canonically completed/awarded events;
- exclude target event;
- include only kickoff `< analysis_cutoff_at`;
- remove postponed/rescheduled aliases that map to the same canonical event;
- deduplicate before sorting;
- sort by kickoff descending;
- apply `last_n` after filtering;
- include home and away events;
- fewer than `last_n` events is valid and reduces sample confidence;
- preserve opponent, competition, role, score, and selected metrics per event.

## H2H

Use the same temporal rules. Default scope is all verified competitions between
the exact canonical participants. Competition-specific H2H is a separate
configured policy, never implicit.

## Standings

Raw observation scope is `COMPETITION + SEASON`. Snapshot projections are made
for the target fixture and each actual participant at the analysis cutoff.
Competition/season identity is mandatory.

## Match statistics

Statistics are valid only for completed/awarded source events unless a
capability explicitly supports live stats. Pre-match snapshots use statistics
from prior events only.

## Lineups, injuries, roster

Publication state is explicit. `NOT_PUBLISHED_YET` must not be converted to
empty. Confirmed and predicted lineups are separate capabilities.

---

# 8. Generic canonical entities and source reconciliation

Create a canonical supertype table so generic subject references retain real
foreign-key integrity:

```text
sports_entity
- id
- sport
- entity_type
- domain_table
- domain_entity_id
- created_at
- UNIQUE(sport, entity_type, domain_table, domain_entity_id)
```

`domain_table` is restricted to an application allowlist. The application must
verify that the referenced domain row exists before creating the entity. All
generic observation, projection, snapshot-item, and source-reference rows use
`sports_entity.id` as a foreign key; an unconstrained polymorphic integer ID is
forbidden.

Create or extend a generic source reference model:

```text
source_entity_reference
- sport
- entity_type
- canonical_entity_id
- provider
- provider_entity_id
- valid_from
- valid_to
- verification_status
- verification_method
- evidence_bundle_id
```

Supported entity types include:

- competition;
- season;
- event;
- participant;
- athlete;
- venue;
- official.

A source reference must point to a valid `sports_entity` row. Deleting a domain
entity with referenced evidence is restricted; use lifecycle/validity changes
instead of destructive deletion.

Existing `fixture_sources` may remain as a compatibility projection but cannot
be the only identity model.

Initial event reconciliation requires:

- sport and event granularity;
- verified competition mapping;
- exact canonical participant set;
- provider-native participant IDs;
- kickoff difference within configured tolerance, default 10 minutes;
- no conflicting active source mapping.

Result:

- zero candidates: `NOT_FOUND`;
- exactly one: verified mapping;
- more than one: `AMBIGUOUS`;
- wrong/missing/duplicated participants: reject;
- conflicting existing mapping: reject and persist conflict.

Already-mapped events may receive kickoff/status corrections without creating a
new canonical event. Preserve every correction version and link it to evidence.

Provider names remain diagnostics only.

---

# 9. Provider trust, legal use, and independence

Create:

`config/provider_governance.yaml`

Trust classes:

```text
OFFICIAL
LICENSED_COMMERCIAL
COMMERCIAL_AGGREGATOR
MEDIA_UNOFFICIAL
CROWDSOURCED
SCRAPED
OPEN_DATASET
```

Usage policies:

```text
PRODUCTION_ALLOWED
PRODUCTION_WITH_ATTRIBUTION
SHADOW_ONLY
RESEARCH_ONLY
LICENSE_RESTRICTED
UNKNOWN_BLOCKED
```

Provenance family identifies likely shared upstream origin.

Two providers count as independent only when:

- their provenance families differ; and
- neither is merely a wrapper/cache of the other; and
- live evidence shows independently retrieved source IDs/timestamps.

Unknown terms or unknown provenance cannot be promoted beyond SHADOW until
resolved.

The implementation agent does not make legal conclusions. It records the
governance state. `UNKNOWN_BLOCKED` and `LICENSE_RESTRICTED` cannot be selected
in production.

---

# 10. Durable evidence contract

Reuse or extend the existing evidence store.

Transport safety defaults:

- maximum compressed response body: provider-configured, default 10 MiB;
- maximum decompressed response body: default 50 MiB;
- reject unsupported content types;
- reject decompression bombs and invalid encodings;
- stream large responses to temporary storage instead of unbounded memory;
- disk-full, fsync, rename, or hash failures become `EVIDENCE_ERROR` and the
  result is never selectable.

For every request retain:

- provider and operation;
- canonical request identity;
- sanitized request metadata;
- exact response body bytes as delivered to the parser;
- status code;
- allowlisted non-secret response headers;
- content type and content encoding;
- retrieval timestamp;
- response-body SHA-256;
- sanitizer version;
- manifest version;
- parser version;
- schema fingerprint.

If the response body itself contains a secret, apply a deterministic,
versioned sanitizer and mark that the stored body is sanitized.

Evidence writes use:

1. temporary file;
2. flush/fsync when supported;
3. atomic rename;
4. manifest written only after every object exists;
5. post-write hash verification.

Schema fingerprint algorithm:

- parse JSON when applicable;
- enumerate sorted JSON paths and value types;
- ignore scalar values and list ordering;
- include optional/required presence counts;
- SHA-256 the canonical shape document.

Garbage collection may delete only unreferenced objects. Evidence referenced by
an observation, snapshot, bet decision, audit, or certification bundle is
retained. Add a reachability test before any GC implementation.

Unreferenced evidence retention is configuration-driven, default 30 days.
Evidence may be compressed after hashing the canonical stored bytes; manifests
record compression. Storage usage, write failures, and GC deletions are
observable. No GC implementation is required in this Football slice unless one
already exists; the mandatory work is retention metadata and reachability
safety.

---

# 11. Atomic enrichment runs and immutable snapshots

Create generic tables/models:

```text
sports_enrichment_run
source_operation_attempt
capability_observation
metric_observation
capability_projection
metric_projection
projection_selection_history
analysis_snapshot
analysis_snapshot_item
```

## 11.1 Enrichment run

Run identity:

`SHA256(sport | canonical_event_id | analysis_cutoff_at |
routing_policy_hash | capability_contract_hash | metric_contract_hash)`

Run states:

```text
RUNNING
COMPLETE
DEGRADED
FAILED
ABANDONED
```

Store:

- started/completed timestamps;
- lease owner and lease expiry;
- policy/config hashes;
- requested capabilities;
- completion summary;
- failure reason.

Only one active run with the same run identity is allowed.

Source operation attempts use:

```text
PENDING
IN_FLIGHT
SUCCEEDED
FAILED
ABANDONED
```

Attempt identity is:

`SHA256(run_id | provider | operation | request_identity)`

and is unique. Each attempt has a short lease.

The system guarantees at-most-one concurrent request for the same attempt.
Exactly-once external HTTP delivery across process crashes is impossible and
must not be claimed. If a process crashes after the upstream accepted a request
but before durable evidence was committed, recovery may repeat the idempotent
GET. Domain ingest and evidence linking must still remain deterministic and
duplicate-free.

A crashed expired `RUNNING` or `IN_FLIGHT` lease becomes `ABANDONED`; a later
run may resume from durable attempts/evidence and safely repeat only an
uncommitted idempotent read request.

## 11.2 Generic observation scope

Observations use:

- target event ID;
- subject type;
- subject canonical ID;
- capability;
- provider;
- operation;
- request identity;
- evidence bundle;
- normalized payload hash;
- valid interval;
- dedupe key.

No generic table requires a team FK.

Dedupe key:

`SHA256(target_event | subject_type | subject_id | capability | provider |
operation | request_identity | evidence_bundle | payload_hash |
valid_from | valid_to)`

An identical dedupe key returns the existing observation ID deterministically.
Changed evidence or payload creates a new observation.

## 11.3 Current projection and history

Projection identity:

`target_event | subject_type | subject_id | capability | analysis_cutoff_at`

Use `ON CONFLICT DO UPDATE`, never delete+insert.

Every selection/change inserts append-only history in the same transaction:

- selected observation ID;
- routing policy version;
- reason;
- confidence;
- conflict flags;
- created time.

## 11.4 Immutable snapshot publication

A snapshot is immutable and references selected observations/metrics through
snapshot items.

Snapshot states:

```text
COMPLETE
DEGRADED
BLOCKED
```

Snapshot publication is one transaction after all P0 decisions are known.

Downstream may read only a fully committed snapshot whose run state is COMPLETE
or policy-approved DEGRADED. It may never assemble data from mutable current
projections during an active run.

The snapshot stores:

- schema version;
- run ID;
- target event;
- cutoff;
- selected observation IDs;
- selected metric observation IDs;
- attempt summary;
- hard/soft missing capabilities;
- confidence;
- provider health flags;
- evidence bundle IDs;
- config/policy hashes.

---

# 12. Concurrency and crash consistency

Use a per-run unique constraint and lease.

For SQLite:

- acquire run creation/lease with a short `BEGIN IMMEDIATE` transaction;
- release DB lock before provider network calls;
- renew lease between provider operations;
- persist each attempt/evidence before selection;
- publish snapshot atomically at the end.

Concurrency tests must prove:

- two simultaneous identical calls create one logical run;
- at most one provider call is concurrently in flight for a unique attempt;
- expired lease recovery works;
- crash after evidence but before projection resumes safely;
- crash during snapshot publication exposes no partial snapshot;
- concurrent different cutoffs create independent runs/snapshots.

---

# 13. Football service and snapshot API

Create:

`src/bet/enrichment/football_service.py`

```python
class FootballEnrichmentService:
    def enrich_fixture(
        self,
        canonical_fixture_id: int,
        analysis_cutoff_at: datetime,
        *,
        force_refresh: bool = False,
    ) -> FootballEnrichmentSnapshot:
        ...
```

Create:

`src/bet/enrichment/football_snapshot.py`

The returned immutable versioned snapshot contains:

- canonical fixture/competition/season;
- home and away participants;
- kickoff and event status;
- cutoff and snapshot state;
- current and historical form records;
- H2H records;
- standings rows/context;
- selected fixture/team metrics;
- lineup/availability states;
- venue/referee context;
- selected advanced metrics;
- all selected provider/native IDs;
- attempt summaries;
- bundle IDs;
- freshness/staleness;
- confidence components;
- hard/soft missing fields.

The actual S3/statistical-analysis production entry point must consume this
snapshot. No Football production read from `team_form` is permitted after
cutover.

Legacy `team_form` may be updated as a compatibility cache, but its values
cannot influence snapshot selection or downstream Football decisions.

---

# 14. Capability and metric contracts

Create:

- `config/football_capabilities.yaml`
- `config/football_metrics.yaml`
- `config/football_routing.yaml`
- `config/football_freshness.yaml`

## 14.1 P0 data capabilities

- discovery/kickoff;
- event status/score;
- canonical competition/event/participant identity;
- current recent form;
- historical recent form;
- H2H;
- standings/competition context;
- detailed historical team match statistics;
- venue/referee context;
- cross-provider identity.

## 14.2 P0 availability-state capabilities

Routes and semantics are mandatory; a particular event may truthfully be
unknown/not published:

- confirmed lineups;
- injuries/suspensions;
- roster availability;
- referee/official assignment.

## 14.3 Scoped advanced capabilities

- xG;
- shot-level data;
- player match statistics;
- advanced passing/defending;
- predicted lineups.

## 14.4 Separate pipelines

- odds;
- weather;
- news/editorial;
- tipsters;
- settlement.

## 14.5 Core Football metrics

Required for the certified detailed-stat capability:

```text
goals
corners
shots_total
shots_on_target
possession_pct
fouls
yellow_cards
red_cards
offsides
```

Additional metrics:

```text
shots_off_target
shots_blocked
goalkeeper_saves
passes_total
passes_accurate
pass_accuracy_pct
expected_goals
big_chances
tackles
interceptions
```

Every metric defines:

- canonical type and unit;
- valid range;
- provider aliases;
- scale conversion;
- null/zero behavior;
- participant-side rule;
- publication phase;
- disagreement tolerance;
- required/scoped status.

Default conflict tolerances:

- discrete counts: exact;
- score/status: exact and settlement-critical;
- possession/pass accuracy: 2 percentage points;
- xG: 0.10;
- timestamps: identity tolerance configured separately.

These defaults may be tightened by metric configuration, never silently
widened.

---

# 15. Freshness, cache, retry, and circuit policies

Defaults live in configuration and are included in routing-policy hash.

## 15.1 Freshness defaults

- scheduled discovery more than 24h before kickoff: 30 minutes;
- scheduled discovery within 24h: 5 minutes;
- within 2h: 2 minutes;
- live status: 30 seconds when live polling is enabled;
- recent form/H2H: 6 hours;
- standings: 30 minutes;
- injuries/roster: 30 minutes;
- confirmed lineup within 2h of kickoff: 5 minutes;
- `NOT_PUBLISHED_YET` lineup: 5-minute negative cache;
- final match statistics: first refresh 10 minutes after final, then one
  correction refresh after 6 hours;
- `PLAN_RESTRICTED`: 24 hours per provider/capability/scope;
- `NOT_SUPPORTED`: 7 days per provider/capability/scope;
- authentication failure: until credential/config changes.

Provider-specific documented rules may override defaults in configuration and
tests.

## 15.2 Retry defaults

- transport timeout/connection and 5xx: maximum two retries after initial call;
- delays: 1s, 2s with ±25% jitter;
- 429: respect `Retry-After`; do not retry if it exceeds run deadline;
- auth, plan restriction, unsupported, parse, schema, evidence, ambiguity: no
  immediate retry;
- request timeout default 15 seconds;
- fixture enrichment deadline default 75 seconds;
- maximum four concurrent provider calls;
- maximum one concurrent call per host unless provider policy allows more.

## 15.3 Circuit defaults

- 3 operational failures in 5 minutes: open 5 minutes;
- schema/evidence failure: open 30 minutes;
- half-open permits one probe;
- success closes circuit;
- circuit state is provider + operation scoped.

## 15.4 Quota reserve

Do not spend the final configured reserve on noncritical shadow requests.
Reserve is provider-configured and defaults to 20% of daily credits for current
P0 operations.

## 15.5 Shared rate and circuit state

Rate-limit, quota, negative-cache, and circuit state must be shared across
processes using the database or another existing shared store. Per-process-only
limiters are insufficient when multiple workers can call the same provider.

## 15.6 Pagination and truncation

Every paginated operation must report:

- requested page/cursor;
- received page count;
- total/items metadata when supplied;
- `has_more`/next cursor;
- truncation/completeness state.

A result with unconsumed required pages or provider-imposed truncation cannot be
selected as a complete recent-form, H2H, standings, roster, or history result.
It may be `VALID_EMPTY`, partial/shadow, or rejected according to the capability
contract.

## 15.7 Deterministic time and jitter dependencies

The enrichment service, cache policies, retry scheduler, and tests must use
injected `Clock` and randomness/jitter abstractions. Direct production calls to
`datetime.now()` or global randomness inside selection/TTL logic are forbidden.

---

# 16. Deterministic confidence and conflict policy

Hard-gate failure makes an observation unselectable regardless of confidence.

For hard-gate survivors compute confidence:

- identity quality: 30%;
- temporal validity: 25%;
- capability/metric completeness: 20%;
- independent-source agreement: 15%;
- provider health/freshness: 10%.

Each component is stored separately.

Independent agreement values:

- 1.0: independent sources agree within configured tolerance;
- 0.5: no independent comparison exists;
- 0.0: unresolved disagreement.

Conflict handling:

- identity disagreement: BLOCKED/fail closed;
- score/final-status disagreement: unresolved until two independent sources
  agree or an official source resolves it;
- discrete metric disagreement: retain all values, select highest-ranked
  qualified source only for non-settlement analysis, mark conflict and reduce
  confidence;
- unit/scale mismatch: reject incompatible observation;
- stale/current disagreement: select only temporally eligible value.

Provider ranking never overrides identity, temporal, legal, evidence, or schema
hard gates.

---

# 17. Provider governance and required qualification

Every provider in the repository is inventoried. Missing credentials are
`CREDENTIAL_UNAVAILABLE` and do not pause unrelated work.

Inventory does not imply implementation. Only provider-capability pairs that
close a P0 gap, add genuine independent redundancy, or add a required metric are
implemented beyond a bounded candidate adapter.

## Tier A: mandatory when accessible

### ESPN Football

Candidate: current discovery/status, form, H2H, standings, stats, lineup state.

- trust: `MEDIA_UNOFFICIAL`;
- conservative default 1 request/second;
- schema drift monitoring mandatory;
- never sole settlement truth.

### SportDB.dev

Candidate: current discovery fallback, current form, standings, detailed stats,
lineups, metadata.

- REST is production path;
- MCP is diagnostics only;
- native SportDB IDs must be discovered first;
- test three completed matches, two competitions, and one sparse payload;
- explicitly verify corners and every core metric.

### Highlightly

Candidate: discovery, form, H2H, standings, stats, lineups, future multi-sport
template.

- odds fields are routed away from enrichment;
- free daily quota must be tracked.

### API-Football

Candidate: accessible-scope discovery and historical/current capabilities
allowed by the active plan.

- explicit plan restriction;
- no historical default for current target;
- minute/day quota capture;
- negative cache by provider/capability/competition/season.

### football-data.org

Candidate: discovery/status cross-check, standings, competition/team identity,
match history, H2H if proven.

Not a complete detailed-stat source without live proof.

## Tier B: bounded/restricted roles

### TheSportsDB

Do not enable the deprecated client by flipping a flag. Build a current V1
candidate adapter only after a successful probe.

Default maximum roles: metadata, cross-reference, event lookup, lineup shadow,
reference discovery.

### Understat

Specialized xG/shot source for verified covered competitions only.

### Sportmonks Free

Contract benchmark and optional route only inside live-proved free competitions.

### FBref/soccerdata/open datasets

Historical/research lane unless governance explicitly permits production.

### Flashscore/Sofascore/Soccerway

Shadow/canary only; never bypass anti-bot protections.

## Tier C: conditional/deferred

### BALLDONTLIE Football

Do not reactivate the deprecated client. Probe only if Tier A leaves a specific
P0 gap and current credential/scope exists.

### Odds providers

Strictly separate.

---

# 18. Probe lifecycle without circular dependency

The previous plan had a circular risk: probes required production adapters, but
adapters were selected only after probes.

Use this fixed lifecycle:

1. `INVENTORIED`
2. `CANDIDATE_SHADOW_ADAPTER`
3. `LIVE_PROBED`
4. `QUALIFIED` or `REJECTED`
5. `PRODUCTION_WIRED`

A candidate shadow adapter must already use:

- shared transport;
- exact evidence;
- canonical request identity;
- versioned normalized DTO;
- schema validation;
- no production registry role.

Live qualification uses the shadow adapter.

Only qualified provider-capability pairs are promoted into production routing.
Rejected candidates remain unwired.

---

# 19. Common qualification dataset

Use:

- one current/upcoming event in the execution-time current season;
- three completed matches;
- at least two competitions;
- one sparse/partial response;
- one historical event accessible to API-Football for identity proof.

Use the same event across providers when coverage permits. When a provider does
not cover the common event, use a provider-specific replacement and explicitly
mark the result as non-comparable; do not count it as cross-provider agreement.

Target selection is persisted before probing and includes canonical and native
IDs as they become known.

---

# 20. Hard qualification gates and roles

A provider-capability pair fails qualification if any applicable gate fails:

- access/governance;
- stable native IDs;
- exact participant attribution;
- lifecycle/status semantics;
- temporal cutoff;
- target/future exclusion;
- valid-empty semantics;
- null/zero semantics;
- exact evidence;
- request identity;
- DTO/schema validation;
- offline parser replay;
- bounded retry/rate behavior;
- correction/version behavior.

Roles:

- `PRIMARY`: all gates, complete capability, live-proved scope, replay and
  idempotency.
- `FALLBACK`: all gates, independent of primary, safe minimum fields, live proof.
- `CROSSCHECK`: reliable identity/status but insufficient enrichment.
- `SPECIALIZED`: qualified scoped metric.
- `SHADOW`: useful but not production-selectable.
- `REFERENCE`: metadata/cross-reference only.
- `REJECTED`: intended role fails a hard gate.

Tie-breakers among qualified providers:

1. core completeness;
2. certified current scope;
3. identity/temporal quality;
4. evidence/replay stability;
5. operational reliability;
6. quota/cost;
7. latency.

---

# 21. Fixed Football routing precedence

Use only qualified routes.

- current discovery: ESPN → SportDB.dev → Highlightly → football-data.org;
- current form: ESPN → SportDB.dev → Highlightly → football-data.org;
- historical form/H2H: API-Football accessible scope → ESPN → Highlightly →
  football-data.org;
- standings: SportDB.dev → football-data.org → Highlightly → ESPN →
  API-Football accessible scope;
- detailed metrics: per-metric qualified selection from SportDB.dev,
  Highlightly, ESPN, API-Football accessible scope;
- lineups: SportDB.dev → Highlightly → API-Football → ESPN;
- injuries/roster: qualified API-Football/Highlightly/ESPN route;
- advanced xG: Understat for certified scope, then other qualified sources.

Precedence is a starting order. A provider with expired qualification, open
circuit, insufficient scope, stale data, or failed hard gate is skipped with an
attempt record.

---

# 22. Performance, indexing, and observability

## 22.1 Performance gates

- every network call has timeout;
- run deadline enforced;
- no provider request occurs while holding a long SQLite write transaction;
- observation/projection/snapshot lookup uses indexes;
- `EXPLAIN QUERY PLAN` tests show no full-table scan for primary lookup paths;
- snapshot read target: p95 under 100 ms on a representative local database;
- offline replay of 20 retained fixtures completes without memory growth or
  unbounded DB growth;
- concurrent-run tests show no duplicate network work.

If hardware variation prevents an absolute timing assertion, record baseline
and fail only on more than 50% regression within the same test environment.

## 22.2 Metrics

Prometheus labels may include provider, operation, capability, competition, and
status. Do not use fixture/event/team/player IDs as metric labels.

Required metrics:

```text
sports_provider_requests_total
sports_provider_request_duration_seconds
sports_provider_quota_remaining
sports_provider_circuit_state
sports_provider_schema_changes_total
sports_provider_evidence_failures_total
sports_provider_fallback_total
sports_provider_selected_total
sports_provider_coverage_ratio
sports_snapshot_unknown_fields_total
sports_crosswalk_conflicts_total
sports_enrichment_runs_total
sports_enrichment_run_duration_seconds
```

Fixture and native IDs belong in structured logs and tracing attributes, not
Prometheus labels.

## 22.3 Tracing

Add OpenTelemetry spans for:

- enrichment run;
- provider request;
- parser;
- reconciliation;
- observation persistence;
- selection;
- snapshot publication.

Never record credentials or raw response bodies in spans.

---

# 23. Qualification expiry and drift

Provider qualification is not permanent.

Registry stores:

- `verified_at`;
- `verification_expires_at`;
- parser version;
- schema fingerprint;
- certified scope.

Default expiry:

- unofficial/scraped/media source: 7 days;
- commercial/API source: 30 days;
- official source: 30 days unless documented otherwise.

A schema fingerprint change immediately sets the affected provider-operation
qualification state to `PENDING_REQUALIFICATION`, forces its capability role to
`SHADOW`, and prevents production selection until contract tests and one live
probe pass.

Qualification states are exactly:

```text
UNVERIFIED
QUALIFIED
PENDING_REQUALIFICATION
EXPIRED
REJECTED
```

---

# 24. Rollout, feature flags, and rollback

Add:

```text
FOOTBALL_ENRICHMENT_MODE=off|shadow|canary|on
```

## Shadow

- new pipeline runs from retained evidence or within quota;
- does not affect downstream decisions;
- compares normalized outputs with legacy path;
- records differences.

## Canary

- enabled only for configured certified competitions;
- downstream reads new immutable snapshot;
- legacy path remains available as emergency rollback but is not blended.

## On

- all certified scope uses new service;
- legacy `team_form` read path disabled for Football;
- emergency rollback requires explicit mode change and creates an operational
  alert.

Migrations are additive and rollback-safe. Rollback must not delete new
observations or snapshots.

Production-ready certification requires `canary` and then `on` proof. A shadow
comparison alone is insufficient.

---

# 25. Execution phases

After each phase write:

`.kilo/artifacts/football_golden_v3/checkpoint.json`

Maximum 120 lines: phase, baseline, changed files, tests, live calls, quotas,
bundle IDs, gate, blocker, next command.

## P00 — baseline, security, governance

Reasoning: MEDIUM.

- verify local/remote HEAD;
- save backup patch;
- record tracked/untracked files;
- scan current tree and Git history for active credential material;
- remove current-tree secrets/generated archives from scoped change;
- verify rotation of any exposed active credential before using it;
- if rotation cannot be verified, stop live calls with
  `CREDENTIAL_ROTATION_REQUIRED`;
- record baseline test inventory, Ruff, compile, and non-live suite;
- build scoped file allowlist.

Gate: exact base, no active secret, safe worktree, baseline captured.

## P01 — production call graph and F01–F25 proofs

Reasoning: HIGH.

Map:

- discovery entry;
- statistical-analysis entry;
- every provider callsite;
- router callsites;
- legacy cache reads/writes;
- evidence paths;
- current migration/version;
- current feature flags.

Add deterministic tests/proofs for every F01–F25 item.

Gate: complete call graph and all defects proved/disproved.

## P02 — generic kernel and migrations

Reasoning: HIGH.

Implement Sections 5–12:

- source result;
- DTO base/versioning;
- generic entity refs;
- evidence contract;
- run/attempt/observation/projection/snapshot models;
- concurrency lease;
- additive migration;
- generic router interfaces.

Run fresh/upgrade/restart/failure/FK/concurrency/versioning migration tests.

Gate: sport-neutral kernel passes including fake athlete-vs-athlete contract test.

## P03 — Football contracts and service skeleton

Reasoning: HIGH.

Implement Sections 7, 13–16:

- lifecycle;
- Football DTOs;
- capability/metric/freshness/routing configs;
- Football service;
- snapshot model;
- downstream interface;
- confidence/conflict policies.

Wire service in `shadow` mode only.

Gate: no arbitrary provider data yet; deterministic Football contract tests pass.

## P04 — inventory and candidate shadow adapters

Reasoning: HIGH.

Inventory every provider.

Create candidate shadow adapters only for accessible mandatory candidates.

Create probe runner using candidate adapters, shared transport, evidence, and
request budgets.

Persist common dataset before live calls.

Gate: no circular dependency; every candidate is probe-ready or truthfully
credential/governance blocked.

## P05 — bounded live qualification

Reasoning: HIGH.

Two-stage fail-fast budget.

Stage A: identity/access probe, maximum 2 calls per candidate.

Stage B: only Stage-A survivors.

Maximum totals:

- ESPN 7;
- SportDB.dev 10;
- Highlightly 8;
- API-Football 6;
- football-data.org 5;
- TheSportsDB 4;
- Understat 3 when scoped;
- Sportmonks 3 when credentialed;
- shadow browser sources 2 total only for a remaining P0 gap;
- BALLDONTLIE 3 only for a remaining P0 gap.

Global maximum 45.

No repeated debugging calls. Use retained evidence. Missing credential continues
as `CREDENTIAL_UNAVAILABLE`.

Gate: every accessible candidate gets capability roles; SportDB core metrics and
Highlightly capabilities are explicitly evaluated.

## P06 — selected production adapters

Reasoning: HIGH.

Promote only qualified provider-capability pairs.

Each selected adapter includes canonical DTOs, evidence, native IDs, schema
validation, quota, retry/circuit policy, and replay fixtures.

Gate: selected contract tests pass; no rejected provider is production-wired.

## P07 — routing, metric selection, and downstream cutover preparation

Reasoning: HIGH.

Build configuration-driven routes and per-metric selection.

Wire actual statistical-analysis entry to consume immutable snapshot behind
feature flag.

Run shadow comparisons and resolve only proven normalization/cutoff differences.

Gate: attempt history, source provenance, and snapshot payload are complete; no
unexplained parity difference.

## P08 — real current-season shadow and canary E2E

Reasoning: HIGH.

Execute real production call graph:

`live discovery → reconciliation → provider attempts → observations →
projections → immutable snapshot → downstream reader`

No manual final-row inserts.

Run first in shadow, then canary for certified competitions.

Gate: real native IDs, every P0 route/state, no legacy blending, canary PASS.

## P09 — historical cross-provider and completed-stat proof

Reasoning: HIGH.

Use a real API-Football-accessible historical event independently resolved in
ESPN. Add other qualified mappings where possible.

Use completed-match sample for metric coverage/conflicts.

Gate: zero/one/multiple candidate behavior; real crosswalk; core metrics covered.

## P10 — full offline replay

Reasoning: HIGH.

Block socket/HTTP access at shared boundary.

Replay selected current and historical routes:

`raw body → parser → DTO → router → persistence → immutable snapshot →
downstream`

Negative cases: unexpected network, missing/corrupt object, request mismatch,
schema mismatch.

Gate: zero network and semantic equality.

## P11 — concurrency, idempotency, crash, correction, temporal

Reasoning: HIGH.

With foreign keys ON:

- two identical concurrent runs;
- two sequential identical runs;
- expired lease recovery;
- crash after evidence;
- crash before snapshot publication;
- two different cutoffs;
- changed evidence;
- target/future exclusion;
- post-match/pre-match isolation;
- reschedule correction/dedupe.

Compare counts, logical IDs, hashes, run IDs, observation IDs, projection
history, snapshot IDs, and downstream serialization.

Gate: zero logical duplicates, no partial snapshots, full history preserved.

## P12 — resilience, performance, observability

Reasoning: HIGH.

Inject plan/auth/rate/timeout/5xx/JSON/schema/valid-empty/partial/not-published/
corrupt/ambiguous/disagreement/stale cases.

Verify retry, circuit, negative cache, quotas, confidence, logs, metrics, traces,
index plans, snapshot-read benchmark, and 20-fixture replay soak.

Gate: no retry storm, no high-cardinality metrics, SLO/non-regression PASS.

## P13 — production rollout and final certification

Reasoning: XHIGH when supported, otherwise HIGH.

- final canary;
- mode `on` for certified scope;
- restart and replay;
- full non-live suite once;
- opt-in live suite;
- touched-file Ruff/static;
- markers;
- secret/history scan;
- audit consistency.

Create only the required runtime/certification artifacts:

- provider inventory;
- governance matrix;
- capability/metric contracts;
- provider qualification;
- final routes;
- E2E proof;
- replay proof;
- concurrency/idempotency proof;
- resilience/performance proof;
- certification index;
- implementation report <=80 lines.

Create `FOOTBALL_GOLDEN_V3_CERTIFICATION_BUNDLE.zip` containing exact base/head,
scoped patch, changed files, code/migrations/tests/configs, every cited evidence
object/manifest, and all validation outputs.

Extract to a clean directory, recompute hashes, point evidence root to extracted
objects, block network, and rerun complete replay.

Gate: extracted bundle independently reproduces certification; no critical/high
blocker.

---

# 26. Test architecture

## Unit

- source-status classification;
- DTO validation/versioning;
- request identity;
- lifecycle mapping;
- metric normalization/tolerances;
- confidence components;
- retry/fallback policy;
- reconciliation rules.

## Provider contract

- retained raw response per selected provider operation;
- actual parser/DTO validation;
- no parsed-output mocks.

## Migration/repository

- fresh/upgrade/restart/failure;
- FK ON;
- dedupe ID;
- changed evidence;
- projection history;
- snapshot atomicity;
- lease/concurrency.

## Integration

- adapter → router → observation → projection → snapshot;
- per-metric selection;
- conflict behavior;
- downstream serialization.

## E2E

- replay-backed full production call graph;
- opt-in live current E2E;
- real historical cross-provider E2E;
- shadow/canary/on modes.

## Network isolation

Autouse guard blocks all non-live sockets/HTTP. A negative control must prove
the guard catches an attempted request.

---

# 27. Certification scope and acceptance

Certification is competition/season/capability scoped.

Technical certification and production-use authorization are separate:

- `TECHNICAL_CERTIFICATION`: code, data quality, replay, resilience, and
  operational gates;
- `USAGE_AUTHORIZATION`: governance policy permits production use.

A provider with technical PASS but `UNKNOWN_BLOCKED`,
`LICENSE_RESTRICTED`, or expired authorization remains non-selectable. The final
Football state can be production-ready only when every selected route has both
technical certification and usage authorization.

`PRODUCTION_READY_MULTI_SOURCE` requires:

1. every P0 data capability has a certified current route;
2. P0 availability capabilities have certified state semantics;
3. critical current capabilities have independent primary/fallback or official source;
4. core detailed metrics are covered with per-metric provenance;
5. current canary/on E2E uses real production callsites;
6. historical real cross-provider proof passes;
7. snapshot is atomic, immutable, fixture/cutoff scoped;
8. downstream uses only the new snapshot;
9. evidence is complete and durable;
10. full offline replay passes;
11. concurrency/crash/idempotency/versioning pass;
12. temporal/lifecycle correction tests pass;
13. resilience/performance/observability pass;
14. selected providers have valid governance and unexpired qualification;
15. no active secret exists in current tree/artifacts;
16. all touched code and tests pass;
17. authoritative audit artifacts agree;
18. extracted certification bundle reproduces the result;
19. certified scope is explicit;
20. no unresolved critical/high issue remains.

`PRODUCTION_READY_SINGLE_SOURCE_RISK` permits only missing independent fallback,
subject to the constraints in Section 1.

Otherwise state is `PARTIAL` with exactly one highest-priority blocker.

---

# 28. Agent operating constraints and documentation budget

The implementation must remain code-first.

Allowed authored documentation:

- this binding contract;
- configuration files required by runtime behavior;
- one checkpoint JSON;
- one provider qualification JSON;
- one final certification index JSON;
- one implementation report, maximum 80 lines.

Tests, command output, evidence manifests, and benchmark results are artifacts,
not narrative reports. Do not create phase reports, architecture essays,
duplicate matrices, or additional master prompts.

- Act autonomously for routine safe work.
- Do not perform destructive Git operations.
- Stop before a live call when credential rotation is unverified.
- Missing credential: classify and continue.
- Do not create a replacement architecture document.
- Do not implement other sports.
- Do not re-run passed live probes.
- Do not repeatedly run the full suite.
- Store large outputs as artifacts, not Markdown.
- Stop at a failed phase gate.
- Never call a provider outside its configured budget.

After each phase return only:

```text
PHASE:
RESULT:
REASONING_USED:
CHANGED_FILES:
TESTS:
LIVE_REQUESTS:
QUOTA:
BUNDLE_IDS:
GATE:
NEXT_PHASE:
BLOCKER:
```

---

# 29. Final response contract

Return only:

```text
RESULT: PASS | PARTIAL | FAIL

FOOTBALL_VERTICAL_STATE:
  PRODUCTION_READY_MULTI_SOURCE |
  PRODUCTION_READY_SINGLE_SOURCE_RISK |
  PARTIAL

CERTIFIED_SCOPE:
<competitions, seasons, capabilities, verification expiry>

GENERIC_KERNEL:
<contract-test and reuse result>

PROVIDER_ROLES:
<provider -> trust, provenance family, capability/scope role>

CURRENT_TARGET:
<canonical and native IDs>

P0_CAPABILITIES:
<attempts, selected observation, bundle, state>

METRIC_COVERAGE:
<metric, selected provider, normalization, conflict, bundle>

SNAPSHOT:
<run ID, snapshot ID/state, cutoff, downstream schema version>

CROSS_PROVIDER:
<real historical proof>

REPLAY:
<current/historical routes, zero-network proof>

CONCURRENCY_IDEMPOTENCY:
<run/attempt/observation/projection/snapshot identities and deltas>

VERSIONING_CORRECTIONS:
<old/new evidence and event corrections>

RESILIENCE_PERFORMANCE:
<failure matrix, SLO, indexes, soak>

OBSERVABILITY:
<metrics, tracing, quota, circuit>

ROLLOUT:
<shadow, canary, on, rollback proof>

TESTS:
<unit, contracts, integration, live, full, lint, static, secret>

AUDIT_CONSISTENCY:
<PASS/FAIL>

CERTIFICATION_BUNDLE:
<path, SHA-256, extraction, offline replay>

REMAINING_BLOCKER:
<NONE or exactly one>

CHANGED_FILES:
<paths only>
```
