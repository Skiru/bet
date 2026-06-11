# Sports Integrations Portfolio Audit Contract

**Version:** 2.0  
**Audit type:** read-only production-readiness baseline  
**Primary objective:** establish the current, real, evidence-backed state of every sports-data integration and every supported sport in this repository, then produce a deterministic remediation order.

The keywords **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT** and **MAY** are normative.

This contract governs an audit, not a repair. Production code, configuration, schemas and orchestration MUST NOT be changed during this run.

---

## 1. Definitions

### 1.1 Audit run

Create an `audit_run_id` before executing commands:

`SPORTS-AUDIT-<UTC-YYYYMMDDTHHMMSSZ>-<short-commit-sha>`

All timestamps MUST be ISO-8601 UTC. Record the repository's business timezone separately and test date discovery across timezone boundaries when applicable.

### 1.2 Integration unit

An integration is not merely a source name. Audit one atomic `integration_key` for each distinct combination:

`<source_key>::<sport_scope>::<role>::<implementation_variant>`

Examples:

- `api_football::football::EVENT_AND_ENRICHMENT::default`
- `vlr::valorant::EVENT_AND_ENRICHMENT::html`
- `open_meteo::multi_sport::WEATHER_OR_VENUE::forecast`
- `sackmann::tennis::HISTORICAL_DATASET::atp`

One provider supporting several sports or roles MUST produce separate integration rows when the code path, capability contract, configuration or readiness differs.

### 1.3 Integration roles

An integration MAY have several declared roles, but each matrix row MUST have one primary role:

- `EVENT_DISCOVERY`
- `EVENT_AND_ENRICHMENT`
- `ENRICHMENT_ONLY`
- `ODDS_ONLY`
- `WEATHER_OR_VENUE`
- `TIPSTER_OR_EDITORIAL`
- `HISTORICAL_DATASET`
- `IDENTITY_OR_REFERENCE_DATA`

### 1.4 Evidence grades

Use evidence grades instead of unsupported confidence scores:

- `E0_CLAIM_ONLY` — comment, README claim or unsupported inference;
- `E1_STATIC` — code/configuration/path inspection;
- `E2_DETERMINISTIC` — deterministic test, fixture, replay or isolated database proof;
- `E3_CURRENT_LIVE` — permitted source operation executed during this audit;
- `E4_CURRENT_REPLAY_RERUN` — current role-appropriate source proof (live network operation or pinned local-dataset revision) plus sanitized evidence, deterministic no-network replay and idempotent rerun where the role persists data.

A higher grade does not override a correctness defect.

---

## 2. Required audit outcome

The audit MUST answer:

1. Which sports, sources and integration variants actually exist?
2. Which integrations are registered, enabled and reachable through the real runtime path?
3. Which capabilities and normalized fields are implemented, missing, partial or falsely reported?
4. Which integrations currently work against the permitted live source or current pinned dataset revision?
5. Which observations are safe for analysis at a historical cutoff?
6. Which integrations preserve source identity, provenance and granularity?
7. Which integrations replay deterministically and persist idempotently?
8. Which failures belong to access, source availability, parsing, schema, matching, time, persistence, orchestration, testing or operations?
9. Which integrations are production-ready under the deterministic rules in this contract?
10. What repair sequence maximizes correctness and information gain while minimizing portfolio risk?

File names, old database rows, mocks, comments and fixture-only tests MUST NOT be treated as live readiness evidence.

---

## 3. Audit lock, safety and worktree integrity

During this audit the agent MUST NOT:

- repair or refactor production code;
- change adapters, schemas, migrations, queues, schedules, prompts, runtime configuration or orchestration;
- add providers or fallbacks;
- delete, rename or disable code;
- modify another branch or worktree;
- run destructive Git commands;
- commit, push or create tags;
- use production or shared development databases;
- bypass CAPTCHA, authentication, access controls, provider terms or rate limits;
- expose credentials, cookies, authorization headers or private payloads;
- fabricate or backfill live evidence.

Permitted writes are limited to:

1. the five audit artifacts defined in section 23;
2. temporary scripts, databases, raw evidence and traces under an OS temporary directory containing `audit_run_id`.

Temporary evidence MUST NOT be placed in tracked production paths. It MUST be sanitized before hashing or retention. At the end, remove temporary artifacts unless explicit retention is required for an unresolved finding; record retained paths and reasons without secrets.

Record `git status --short` before and after the audit. The final worktree delta MUST contain only the five permitted report files plus changes that existed in the baseline. Any other audit-created file is a failed integrity check.

---

## 4. Execution phases and resumability

Execute in this order:

- `P0_BASELINE`
- `P1_INVENTORY`
- `P2_RUNTIME_REACHABILITY`
- `P3_DETERMINISTIC_VERIFICATION`
- `P4_LIVE_VERIFICATION`
- `P5_CROSS_PORTFOLIO_ANALYSIS`
- `P6_ADVERSARIAL_SELF_REVIEW`
- `P7_WORKTREE_INTEGRITY`

Do not begin `P4` until inventory and role classification are complete.

After every audited `integration_key`:

1. atomically update `INTEGRATION_MATRIX.md`;
2. atomically update `EVIDENCE_MANIFEST.json`;
3. record the next integration and phase in the manifest's `resume_state`;
4. re-read this contract and the current matrix;
5. continue from persisted evidence rather than chat memory.

If context is condensed or the session is resumed, the manifest and matrix are the source of audit progress.

---

## 5. Repository and environment baseline

Before any source request:

1. Record repository root, worktree path, branch, commit SHA and baseline Git status.
2. Read every applicable `AGENTS.md`, `AGENT.md`, `CLAUDE.md`, `CONTEXT.md` and repository-specific rule file.
3. Detect language, framework, package manager, test runner, database, queue, cache, browser stack and observability stack from files and executable versions.
4. Record dependency lockfile checksums and relevant runtime versions.
5. Identify disposable database or isolated schema support.
6. Identify credentials only by environment-variable name and boolean presence. Never run commands that dump the whole environment.
7. Avoid shell tracing such as `set -x` around secret-bearing commands.
8. Run the smallest existing deterministic baseline that meaningfully covers integrations. Apply an explicit timeout.
9. If the full suite is too large or already failing, run targeted suites and record the omitted scope and reason.
10. Distinguish baseline failures from audit-discovered failures.

---

## 6. Inventory completeness proof

Explicitly search for support or attempted support for:

- football;
- basketball;
- volleyball;
- tennis;
- hockey;
- CS2;
- Dota 2;
- Valorant.

Also include every additional sport found in code, configuration, storage, tests or documentation. If one of the eight named sports is absent, record `NOT_FOUND_IN_REPOSITORY` with the searches used; do not invent an integration.

Build the inventory from at least five independent views:

1. implementations: adapters, clients, parsers, datasets;
2. registrations: dependency injection, registries, factories, feature flags;
3. execution: commands, jobs, queues, schedulers, workflows and public entry points;
4. persistence: models, repositories, migrations, read models and snapshots;
5. verification: tests, fixtures, evidence directories, docs and environment variables.

Search for:

- source and sport enums;
- capability enums or contracts;
- HTTP, XHR, HTML and browser clients;
- endpoint paths and hostnames;
- parser selectors and response schemas;
- provider credential names;
- source-event and participant identifiers;
- matching, alias and crosswalk logic;
- temporal filters and analysis cutoffs;
- persistence calls and unique constraints;
- live-test markers and replay fixtures;
- disabled, legacy, duplicate and unregistered implementations.

For every discovered reference, reconcile it to an `integration_key` or place it in an explicit `UNRESOLVED_REFERENCE` list.

Inventory completeness passes only when:

- every implementation has a classification;
- every registration points to a classified implementation or broken edge;
- every configured source key is reconciled;
- every integration-related persistence path is linked;
- every test/fixture source name is linked or marked orphaned;
- duplicate aliases and implementation variants are explicitly mapped.

Include the search commands and unresolved references in the audit artifacts.

---

## 7. Access method and external-contract verification

Classify the actual acquisition method:

- `LICENSED_OR_OFFICIAL_API`
- `DOCUMENTED_PUBLIC_API`
- `PUBLIC_XHR_OR_JSON`
- `STATIC_HTML`
- `BROWSER_AUTOMATION`
- `LOCAL_OR_OPEN_DATASET`
- `UNKNOWN_OR_REJECTED`

When web access is available, check current official provider documentation, access requirements, quota guidance and relevant terms before live execution. Record URL, check time and whether the conclusion is official documentation, repository evidence or inference.

Do not make a legal conclusion. Record whether a permitted basis for the planned request is known, unknown or blocked.

Flag:

- browser automation where static HTML or permitted JSON would suffice;
- undocumented endpoints treated as stable contracts;
- persistent browser identities without a legitimate need;
- disabled TLS verification;
- credential leakage in URLs, logs or fixtures;
- access-evasion mechanisms.

---

## 8. Pipeline reachability

A class existing in the repository is not an active integration.

Trace the real path according to role.

### Event discovery

`public entry/scheduler -> orchestration -> adapter -> source event -> source identity -> canonical matching -> persistence -> downstream snapshot/read model`

### Event enrichment

`canonical event/participant -> source lookup identity -> source observation -> temporal eligibility -> persistence -> downstream snapshot/read model`

### Odds

`canonical event -> source market/event identity -> bookmaker/market/selection observation -> snapshot persistence -> downstream read model`

### Weather or venue

`canonical event + venue/time -> source location/forecast identity -> issue/valid times -> observation -> snapshot`

### Tipster/editorial

`canonical event/topic -> article/post identity -> publication/first-seen time -> sanitized untrusted record -> read-only downstream use`

### Historical dataset

`pinned revision/checksum -> loader -> normalization -> temporal semantics -> persistence/read model`

### Identity/reference data

`source participant/competition identity -> crosswalk/alias observation -> effective dates -> consumer`

Classify reachability:

- `ACTIVE_REACHABLE`
- `REGISTERED_BUT_UNREACHABLE`
- `IMPLEMENTED_NOT_REGISTERED`
- `CONFIGURED_DISABLED`
- `LEGACY_OR_DEAD`
- `UNKNOWN`

Record the first broken edge with file and symbol evidence.

---

## 9. Role-specific proof selection

Do not require event discovery from roles that do not discover events.

Select proof using a deterministic rule and record that rule to prevent cherry-picking.

### Event-capable integrations

Use one primary real event selected from a declared date/window by deterministic ordering. It MUST have a source event ID, participants, competition/stage when applicable and parseable start time.

A single supporting event MAY be used only for a capability unavailable due to event state, such as confirmed lineups, final statistics or a completed esports draft. It cannot replace the primary identity, persistence or temporal tests.

### Enrichment-only integrations

Start from one canonical event selected by deterministic rule and prove the exact source lookup identity and source observation identity.

### Odds-only integrations

Prove source event/market identity plus at least one bookmaker, market, selection, line where applicable, price and observation timestamp.

### Weather/venue integrations

Prove normalized venue/location identity, forecast issue time, forecast-valid time and event-time alignment.

### Tipster/editorial integrations

Prove stable article/post identity, author when available, publication time or first-seen fallback, event/market linkage and untrusted-content isolation.

### Historical datasets

No network request is required for readiness when runtime use is local. Prove current pinned revision, checksum, licence/provenance metadata, loader determinism, row counts and temporal semantics using representative records.

### Identity/reference integrations

Prove stable source entity identity, canonical crosswalk behaviour, effective dates and ambiguity handling.

All date-based discovery tests MUST record request timezone, source timezone assumptions, canonical UTC time and DST/date-boundary observations.

---

## 10. Live request budget and stop conditions

Before live execution, declare per source:

- operation purpose;
- maximum requests;
- maximum concurrency;
- connect/read/write/pool timeout or equivalent;
- operation deadline;
- retryable failure classes;
- maximum retries;
- quota/rate constraint;
- positive and negative cache assumptions.

When official limits are unknown, use the safe default:

- concurrency `1`;
- one request per distinct operation needed to prove declared core capabilities, plus one identity/discovery request;
- hard cap `10` source requests, excluding at most one transient retry;
- at most `1` retry, only for a transient idempotent read;
- coalesce or reuse identical requests and cached evidence;
- no retry for authentication, blocking, parser, schema or semantic failures;
- operation deadline `30 seconds` for HTTP and `45 seconds` for browser automation unless repository/provider constraints are stricter.

Stop source execution immediately when:

- access is blocked or challenged;
- credentials are rejected;
- the declared budget is exhausted;
- a response indicates the method is not permitted;
- repeated structural/schema failure makes further requests non-diagnostic.

Never hedge third-party requests during the audit.

Credential/access classification:

- required credential absent before execution: live gate `NOT_EXECUTED`;
- credential present but rejected: live gate `FAIL`;
- explicit provider block/challenge: reachability/access gate `FAIL` and no further requests;
- source legitimately has no credential requirement: do not penalize it.

---

## 11. Capability contract and states

Determine each integration's **declared core capabilities** from active code, configuration and runtime consumers. Do not redefine core capabilities from an aspirational sport wishlist.

Record separately:

- `DECLARED_CORE`
- `IMPLEMENTED_OPTIONAL`
- `SOURCE_AVAILABLE_NOT_IMPLEMENTED`
- `PORTFOLIO_GAP`

Capability evidence states:

- `IMPLEMENTED_AND_LIVE_VERIFIED`
- `IMPLEMENTED_REPLAY_VERIFIED`
- `IMPLEMENTED_UNVERIFIED`
- `PARTIAL`
- `VALID_EMPTY`
- `NOT_PUBLISHED_YET`
- `NOT_SUPPORTED`
- `NOT_IMPLEMENTED`
- `STALE`
- `AMBIGUOUS`
- `BLOCKED`
- `PARSE_ERROR`
- `SCHEMA_ERROR`
- `AUTH_OR_CONFIG_MISSING`

Definitions:

- `VALID_EMPTY` means the source and parser were valid and the domain truth was empty.
- `NOT_PUBLISHED_YET` requires evidence that publication is expected later.
- `NOT_SUPPORTED` requires coverage or source-contract evidence.
- `PARTIAL` identifies exactly which expected subset is missing; it is not a generic success label.

Universal capability families include discovery, source status, competition/stage, participant identity, H2H, recent form, standings/rankings, statistics, availability, predicted/confirmed lineups, event-effective rosters, venue/surface/weather, odds, tactical context, results reconciliation and editorial opinion.

Use sport-specific depth expectations from repository consumers and the domain profile below, but do not fail an individual source for portfolio capabilities assigned to another source.

- **Football:** form, H2H, standings, team/player statistics, injuries, suspensions, predicted/confirmed XI, venue, weather, cards/corners when relevant, odds.
- **Basketball:** team/player box statistics, pace/efficiency when consumed, availability, starters, roster, rest context, venue, odds.
- **Volleyball:** set-level results/form, standings, team/player statistics, roster, availability.
- **Tennis:** ranking at cutoff, surface, H2H, recent overall/surface form, serve/return statistics, withdrawals, venue/weather.
- **Hockey:** form, standings, availability, goalies/lines when consumed, special teams, roster, venue, odds.
- **CS2:** series/maps, map history/pool, veto, ranking, event-effective roster, LAN/online, patch/version, odds.
- **Dota 2:** series/games, patch, stage, event-effective roster, draft/heroes, side context, recent matches, odds.
- **Valorant:** series/maps, map pool, patch, event-effective roster, agents, map statistics, side splits, stage, odds.

---

## 12. Statistical field and semantic fidelity

Endpoint presence does not prove statistical correctness.

Create a complete inventory of every normalized or derived field emitted by each integration. For every field record at least:

- source path or extraction rule;
- normalized field;
- entity and granularity;
- unit and scale;
- total, average, rate, percentage, rank, snapshot or categorical semantics;
- denominator and sample window where applicable;
- season/stage/map/set/surface/patch scope;
- null, unknown, unavailable and real-zero semantics;
- whether copied, normalized or derived;
- derivation formula and version when derived.

Deep-verify with live or replay evidence:

1. **100% of derived fields**;
2. **100% of identity, time, status and betting-critical fields**;
3. at least one representative field from every remaining semantic class and granularity;
4. any field with suspicious naming, scaling or aggregation.

For each inspected observation compare raw, parsed and persisted item counts and values.

Flag:

- `0.53` versus `53%` confusion;
- total versus average/rate confusion;
- incorrect denominator;
- mixed seasons, stages, surfaces, patches, maps or sample windows;
- double aggregation;
- silent truncation or pagination loss;
- map/set/game data flattened to event level;
- missing values converted to zero;
- stale/current data represented as point-in-time history.

Store field-semantic evidence in `EVIDENCE_MANIFEST.json` and summarize critical findings in the report.

---

## 13. Source identity and canonical matching

Verify matching order:

1. existing source crosswalk;
2. exact provider event/entity IDs;
3. approved aliases/crosswalks;
4. hard candidate blocking;
5. soft/fuzzy scoring only within the blocked set;
6. fail-closed `AMBIGUOUS` or `NOT_FOUND`.

Hard constraints MUST use every trustworthy available dimension, including sport, granularity, competition/season/stage, participant set, scheduled-start window, round, series format, venue, map or bracket context.

Audit adversarial cases:

- aliases, diacritics and transliteration;
- sponsor prefixes;
- youth, academy, women and reserve variants;
- same participants meeting more than once;
- postponed/rescheduled events;
- organisation versus active esports roster;
- duplicate player handles/names;
- series versus game/map/set granularity;
- one source event matching several canonical candidates.

Record score components, thresholds and matcher version where scoring exists. Hardcoded confidence without calibration or feature evidence is a defect.

Any automatic ambiguous or wrong link is `CRITICAL`.

---

## 14. Point-in-time and bitemporal correctness

Determine whether each observation records and correctly uses:

- raw source timestamp, timezone/offset and parsing assumption;
- normalized source event time in UTC;
- source publication time and trust level;
- source update time and trust level;
- system first-seen time;
- fetch and ingestion times;
- valid-from and valid-to where applicable;
- immutable analysis cutoff;
- temporal eligibility and rejection reason.

Earliest-provable-availability rule:

- use source publication time only when it applies to the exact item/version;
- otherwise use immutable system first-seen time;
- never backdate from event date, URL, page order, current page contents or current database state.

Verify:

- current event excluded from its own H2H/recent form;
- all included form events occur strictly before the target event;
- future and postponed duplicates excluded;
- historical rankings/standings are not reconstructed from current values;
- historical rosters are event-effective;
- predicted and confirmed lineups remain distinct;
- post-event corrections do not alter earlier pre-event snapshots;
- odds remain append-only timestamped observations;
- weather retains issue time and valid time;
- event status transitions, postponement and rescheduling preserve observation history.

Any future leakage is `CRITICAL`.

---

## 15. Data quality and semantic outcomes

The values in this section are runtime/domain outcomes. They are distinct from the audit evidence states in section 11. Verify distinct handling of:

- `SUCCESS`
- `PARTIAL`
- `VALID_EMPTY`
- `NOT_FOUND`
- `NOT_PUBLISHED_YET`
- `NOT_SUPPORTED`
- `STALE`
- `AMBIGUOUS`
- `BLOCKED`
- `PARSE_ERROR`
- `SCHEMA_ERROR`
- `AUTH_OR_CONFIG_MISSING`

For every capability evaluate:

- correctness;
- completeness with an explicit denominator where measurable;
- freshness;
- uniqueness;
- consistency;
- provenance;
- source/entity-match safety;
- temporal eligibility.

Audit misleading behaviour, including empty-as-success, stale canonical status, hardcoded confidence, opinion-as-fact and missing-as-zero.

---

## 16. Cross-source reconciliation and conflicts

Where several sources provide the same capability, verify that the system:

- preserves source-level observations;
- derives canonical values separately;
- records capability-specific source priority rather than one universal source rank;
- considers publication/first-seen time and freshness;
- retains conflicts instead of silently overwriting;
- identifies syndicated or duplicated editorial content;
- records derivation/reconciliation policy version;
- can explain which observation produced the canonical value.

A source disagreement is not automatically a parser error. Record the conflicting values and temporal context.

---

## 17. Tipster and untrusted-text security

For `TIPSTER_OR_EDITORIAL` integrations verify:

- stable author/article/post identity where available;
- publication time or first-seen fallback;
- event, market, selection and quoted odds extraction;
- distinction between fact, claim, argument and prediction;
- near-duplicate/syndication detection before consensus;
- historical author evaluation without look-ahead bias;
- HTML sanitization and hidden-content handling;
- external text stored and presented as untrusted data, never executable instructions;
- downstream agent access is read-only and least-privileged;
- raw external instructions cannot trigger tools, credentials or writes.

Counting syndicated articles as independent consensus is a `HIGH` defect. Letting scraped text control a privileged agent is `CRITICAL`.

---

## 18. Raw evidence, replay and parser resilience

For every network integration verify raw evidence is retained before normalization, or identify the exact absence.

Evidence metadata MUST include:

- evidence ID;
- source and operation;
- sanitized endpoint identity;
- capture time;
- HTTP/result status;
- MIME type;
- sanitized content hash;
- byte size and compression;
- parser/schema version;
- redaction policy version;
- temporary storage path or retained evidence reference.

Do not store secrets or full sensitive payloads in repository reports.

Replay proof MUST:

- deny or fail all outbound network access;
- use the exact retained sanitized evidence;
- reproduce semantically equivalent normalized observations;
- compare semantic payload hashes while excluding declared volatile metadata;
- report every difference.

For HTML/browser sources additionally verify:

- semantic selectors;
- DOM/schema signature;
- cardinality and cross-field assertions;
- fallback path semantics;
- minimized golden fixtures;
- mutated/adversarial fixtures;
- structural-drift quarantine;
- no silent success from empty selectors;
- Playwright only when static HTML or permitted XHR is insufficient;
- HAR/trace redaction and Service Worker implications where relevant.

A parser without reproducible evidence cannot exceed `IMPLEMENTED_UNVERIFIED` or `LIVE_FUNCTIONAL_NOT_SAFE`, depending on live behaviour. A browser trace or HAR is debugging evidence, not sufficient replay proof unless sanitized and replayed with network fallback disabled.

---

## 19. Persistence and idempotency

Use a disposable database or isolated schema. Never use production or shared development data.

For integrations that persist data, execute the same verified logical flow twice when safely possible and compare logical identities and row counts.

Audit:

- source-event/entity uniqueness;
- participant crosswalk uniqueness and correction history;
- deterministic observation idempotency keys;
- append-only source observations;
- canonical materialization separated from evidence;
- odds snapshot identity;
- effective-dated roster membership;
- transaction boundaries;
- correction/tombstone semantics;
- replay safety;
- duplicate H2H, form, lineup, injury, statistics and market rows;
- null/unknown preservation.

Idempotency keys MUST NOT depend on run ID, retry count or fetch time when those values do not define logical identity.

A second identical run creating logical duplicates is `CRITICAL`.

For read-only integrations, mark persistence gates `NOT_APPLICABLE` only after proving they truly have no write path.

---

## 20. Reliability, scheduling and source isolation

Verify per source:

- bounded connect/read/write/pool timeouts or equivalent;
- full-operation deadline;
- bounded retries and retryable classes;
- `Retry-After` handling;
- exponential backoff with jitter;
- retry budget;
- per-host concurrency and provider quota control;
- circuit breaker or quarantine semantics;
- queue/worker bulkhead isolation;
- partial-result behaviour;
- stale-if-error policy restricted by capability;
- positive and negative TTL per capability;
- delayed-publication state;
- event-state-driven refresh rules;
- postponement/rescheduling behaviour;
- backfill isolated from live priority;
- one slow source unable to consume the complete event deadline.

Do not accept one universal polling interval or one global retry loop as production grade.

---

## 21. Tests and observability

### Tests

Inventory and execute applicable:

- unit;
- adapter contract;
- parser/golden replay;
- temporary-database integration;
- controlled failure injection;
- adversarial identity;
- temporal leakage;
- idempotent rerun;
- live canary;
- end-to-end;
- shadow or soak tests when present.

Live tests MUST be explicitly marked/tagged and excluded from normal deterministic CI. Record command, count, pass/fail/skip/xfail, duration and timeout.

A live source outage MUST NOT be reported as a deterministic parser regression. Tests that only assert absence of exceptions or mock the adapter do not prove semantic correctness.

### Observability

Verify bounded telemetry for:

- trace correlation;
- source, operation and capability;
- semantic result status;
- latency and deadline;
- retry count;
- cache result;
- parser/schema version;
- evidence reference;
- freshness;
- ambiguous matches;
- temporal rejections;
- persistence conflicts;
- circuit/quarantine state.

Event IDs, URLs, participant names, run IDs and evidence hashes MUST NOT be unbounded metric labels. They MAY appear in structured logs or traces under the repository's privacy and retention policy.

Verify alerts/runbooks distinguish outage, access block, rate limit, parser/schema drift, temporal violation, ambiguity and duplication.

---

## 22. Gates, severity and deterministic final states

### 22.1 Gate statuses

Each applicable gate is exactly one of:

- `PASS` — all mandatory criteria pass with required evidence;
- `PARTIAL` — a documented non-critical subset passes, no critical defect is hidden;
- `FAIL` — mandatory criterion failed or a critical/high safety defect exists;
- `NOT_APPLICABLE` — role has no such responsibility and no code path;
- `NOT_EXECUTED` — evidence could not be obtained; this never proves safety.

### 22.2 Portfolio gate

- `PG0_INVENTORY_RECONCILED` — evaluated once for the complete inventory; it must pass before claiming the portfolio audit is complete.

### 22.3 Integration gates

- `G1_RUNTIME_REACHABLE`
- `G2_SOURCE_IDENTITY`
- `G3_CANONICAL_OR_ENTITY_MATCH_SAFE`
- `G4_DECLARED_CORE_CAPABILITIES`
- `G5_STATISTICAL_SEMANTIC_FIDELITY`
- `G6_POINT_IN_TIME_SAFE`
- `G7_EVIDENCE_AND_NO_NETWORK_REPLAY`
- `G8_IDEMPOTENT_PERSISTENCE`
- `G9_FAILURE_ISOLATION_AND_BUDGETS`
- `G10_TEST_SEPARATION`
- `G11_OBSERVABILITY_AND_OPERATIONS`
- `G12_ACCESS_SECRET_AND_UNTRUSTED_DATA_SAFETY`

Role applicability MUST be recorded, not assumed. Examples:

- historical datasets can pass `G2` using pinned revision/checksum identity and do not require a live network call;
- read-only sources may mark `G8` not applicable only when no write path exists;
- discovery-only sources are evaluated only for declared enrichment capabilities;
- identity/reference sources may use entity matching rather than event matching in `G3`.

### 22.4 Role-applicability baseline

Use this baseline and document every deviation:

| Role | Required gates unless code proves not applicable |
|---|---|
| `EVENT_DISCOVERY` | G1–G7, G8 when writing, G9–G12 |
| `EVENT_AND_ENRICHMENT` | G1–G7, G8 when writing, G9–G12 |
| `ENRICHMENT_ONLY` | G1–G7 except discovery-specific subcriteria, G8 when writing, G9–G12 |
| `ODDS_ONLY` | G1–G7, G8 when writing, G9–G12 |
| `WEATHER_OR_VENUE` | G1–G7, G8 when writing, G9–G12 |
| `TIPSTER_OR_EDITORIAL` | G1–G7, G8 when writing, G9–G12 |
| `HISTORICAL_DATASET` | G1 loader reachability, G2 revision identity, G3 when canonical joins occur, G4–G7, G8 when writing, G9–G10, G11 when operationally active, G12 |
| `IDENTITY_OR_REFERENCE_DATA` | G1–G7 with entity-match semantics, G8 when writing, G9 when networked or orchestrated, G10–G12 |

`NOT_APPLICABLE` requires an explicit role and code-path reason.

### 22.5 Severity

- `CRITICAL` — wrong/ambiguous automatic identity, future leakage, fabricated evidence, secret exposure, privileged prompt injection, destructive or duplicate persistence;
- `HIGH` — broken active core capability, no reproducible evidence, unsafe failure coupling, silent parser/schema drift, materially wrong statistics;
- `MEDIUM` — incomplete optional coverage, operational or observability gap with safe failure;
- `LOW` — documentation, naming or maintainability issue with no current correctness impact.

### 22.6 Final state precedence

Apply the first matching rule below. A rule matches only when its stated evidence condition is satisfied:

1. `ABSENT_OR_STUB` — no substantive implementation or runtime contract exists.
2. `INTENTIONALLY_DISABLED` — substantive implementation exists and an explicit configuration/feature flag intentionally disables the runtime path; do not mislabel it dead or ready.
3. `LEGACY_OR_RETIRED` — evidence shows the implementation is intentionally retired and has no active consumer.
4. `DEAD_OR_UNREACHABLE` — substantive implementation is intended to be active, but the configured real runtime path cannot reach it.
5. `LIVE_FUNCTIONAL_NOT_SAFE` — current role-appropriate source proof returns usable data, but any critical gate fails.
6. `LIVE_BROKEN` — current permitted live attempt was executed but produced no usable role-appropriate result because of access, source, parser, schema or declared-core failure.
7. `PRODUCTION_READY` — `E4_CURRENT_REPLAY_RERUN` role-appropriate proof exists and all applicable gates pass.
8. `PRODUCTION_CANDIDATE` — current role-appropriate proof exists; all safety and declared-core gates pass; only non-critical operational or optional gaps remain.
9. `LIVE_PARTIAL` — current proof works for a safe subset, with no critical defect, but at least one declared-core gate is `PARTIAL` or `NOT_EXECUTED`.
10. `DETERMINISTIC_ONLY` — meaningful `E2_DETERMINISTIC` proof exists, but required current-source proof was not executed. For a purely local historical dataset, a current pinned-revision proof is current-source proof and may qualify for a higher state.
11. `IMPLEMENTED_UNVERIFIED` — substantive implementation exists but only `E0_CLAIM_ONLY` or `E1_STATIC` evidence exists.

`NOT_EXECUTED` on any applicable safety or core gate prevents `PRODUCTION_READY`.

---

## 23. Mandatory output artifacts

Create exactly this directory using the UTC audit date:

`docs/audits/sports-integrations/YYYY-MM-DD/`

Create exactly five tracked files:

1. `PORTFOLIO_AUDIT.md`
2. `INTEGRATION_MATRIX.md`
3. `EVIDENCE_MANIFEST.json`
4. `REMEDIATION_BACKLOG.md`
5. `AUDIT_COMMANDS.md`

### 23.1 `PORTFOLIO_AUDIT.md`

Required sections:

- executive verdict;
- audit run and repository baseline;
- inventory completeness proof and unresolved references;
- runtime pipeline map;
- per-sport portfolio coverage;
- per-integration evidence summaries;
- statistical semantic findings;
- temporal and identity findings;
- cross-source reconciliation findings;
- systemic critical/high findings;
- readiness verdicts;
- recommended first repair;
- uncertainties and unexecuted checks;
- final adversarial validation and worktree-integrity result.

Every load-bearing claim MUST cite an `evidence_id`, command ID, test-run ID or live-operation ID from the manifest.

### 23.2 `INTEGRATION_MATRIX.md`

One row per `integration_key`, including:

- source, sport, primary role and variant;
- intended portfolio role;
- access method;
- activation and reachability;
- role-specific source identity;
- current proof grade;
- declared core capability result;
- statistical fidelity;
- temporal safety;
- replay;
- persistence/idempotency;
- reliability;
- tests;
- observability;
- gate summary;
- final state;
- top blocker.

### 23.3 `EVIDENCE_MANIFEST.json`

The file MUST be valid strict JSON with no comments or trailing commas and this top-level structure:

```json
{
  "schema_version": "2.0",
  "audit_run_id": "...",
  "started_at": "...Z",
  "completed_at": null,
  "resume_state": {},
  "repository": {},
  "environment": {},
  "integrations": [],
  "commands": [],
  "test_runs": [],
  "live_operations": [],
  "evidence": [],
  "field_semantics": [],
  "gate_results": [],
  "blockers": [],
  "worktree_integrity": {}
}
```

Every record MUST have a unique ID and `integration_key` where applicable. Do not include secrets or full sensitive payloads. Validate JSON parsing before completion.

### 23.4 `REMEDIATION_BACKLOG.md`

Create a dependency-aware order. Each item MUST include:

- item ID;
- source/sport/integration key;
- severity;
- exact defect and evidence IDs;
- affected capabilities and consumers;
- smallest safe repair slice;
- required live proof type;
- acceptance gates;
- dependencies;
- complexity `S/M/L/XL`;
- recommended reasoning `medium/high/xhigh`.

Prioritize:

1. future leakage and wrong identity;
2. fabricated/unverifiable evidence and secret/security defects;
3. destructive/duplicate persistence;
4. broken active discovery/core paths;
5. material statistical semantic errors;
6. source isolation and retry-storm risk;
7. replay/parser resilience;
8. missing high-value portfolio capabilities;
9. observability and operations;
10. later abstraction.

Select one first repair based on risk reduction and information gain, not ease alone.

### 23.5 `AUDIT_COMMANDS.md`

Record:

- command ID;
- UTC time;
- working directory;
- exact sanitized command;
- relevant environment-variable names only;
- timeout;
- exit code;
- concise result;
- produced evidence IDs.

---

## 24. Adversarial final validation

Before completing the audit, perform a separate review pass. A read-only subagent MAY assist, but the primary agent MUST verify every correction.

The validation MUST prove:

- every inventoried integration key has exactly one matrix row;
- every matrix row has gate results and a deterministic final state;
- intentionally disabled and retired integrations are not mislabeled dead or production-ready;
- every report claim has evidence linkage;
- every live claim was executed during this audit;
- every historical-dataset readiness claim has pinned revision/checksum evidence;
- `NOT_APPLICABLE` has a role-based reason;
- `NOT_EXECUTED` is not presented as success;
- no critical defect is hidden by `PARTIAL`;
- no ambiguous match or future leakage is accepted;
- manifest JSON parses and IDs are unique/referentially valid;
- no secret-like value is present in tracked reports;
- the five reports do not contradict one another;
- final Git status matches the allowed worktree delta.

Fix report inconsistencies only. Do not repair production code.

---

## 25. Final response format

Return only:

1. overall portfolio verdict;
2. counts of sports, integration keys and role-appropriate current proofs;
3. counts by final state;
4. critical and high findings;
5. recommended first repair and reasoning level;
6. the five audit output paths;
7. blockers that prevented proof;
8. worktree-integrity result.

Do not paste the reports into chat. Do not claim production readiness unless the deterministic state rule permits it. Stop after the audit and validation are complete.
