# Sports Integration Live Review Contract

**Purpose:** review and repair exactly one sports-data source integration per run, using real live evidence, deterministic replay, point-in-time correctness, and idempotent persistence.

This is an execution contract, not an architecture essay. Follow the existing repository architecture unless a change is required to pass a measurable gate.

---

## 1. Run parameters

The launching prompt must provide:

- `SOURCE`: integration/provider to review;
- `SPORT`: one supported sport;
- `TARGET_DATE`: `YYYY-MM-DD` or `AUTO`;
- optional `TARGET_EVENT_ID`: known provider event ID;
- optional `ANALYSIS_CUTOFF`: ISO-8601 timestamp or `AUTO_PRE_EVENT`.

If `TARGET_DATE=AUTO`, prefer one upcoming event that:

1. has a real provider event ID;
2. has identifiable participants and competition;
3. exposes enough data to test discovery plus at least three enrichment capabilities;
4. does not require bypassing access controls.

A recently completed primary event is acceptable only for a post-match/historical adapter. When one primary event cannot expose a state-dependent capability such as confirmed lineups or final statistics, use at most one additional supporting event from the same source. The supporting event may prove that capability parser, but it cannot replace the primary event's identity, temporal, replay, and idempotency gates.

Record all selected values and the reason for any supporting event before editing code.

---

## 2. Non-negotiable scope lock

During this run:

- review and modify only the selected integration and the smallest shared code required for correctness;
- use exactly one primary live event for the acceptance gate and at most one justified supporting event for state-dependent data;
- do not repair another source;
- do not introduce a universal framework after observing only one adapter;
- do not redesign unrelated orchestration, agents, prompts, schemas, or infrastructure;
- do not replace existing architecture merely because another style is preferred;
- do not declare success from mocks, cached database rows, synthetic traces, or empty output.

When a wider defect is discovered, document it as a follow-up unless it blocks the selected vertical slice.

---

## 3. Safety and repository preparation

Before implementation:

1. Confirm the worktree and branch.
2. Show `git status --short` and preserve unrelated changes.
3. Do not run destructive Git commands, delete untracked files, rewrite history, or reset the worktree.
4. Locate and read applicable `AGENTS.md`, repository instructions, tests, migrations, source adapters, and domain contracts.
5. Identify the disposable test database mechanism.
6. Identify required credentials only by environment-variable name. Never print, log, persist, or commit secrets.
7. Record the baseline test commands and results.

Use a temporary/disposable database for all live-review persistence tests. Never use production data and do not depend on old development rows as evidence.

---

## 4. Source-access rule

Prefer, in order:

1. licensed or official API;
2. documented public API;
3. permitted stable JSON/XHR endpoint;
4. static HTML;
5. browser automation only when rendering is genuinely required;
6. pinned local/open dataset for historical data;
7. quarantine or reject the source.

Do not implement CAPTCHA bypass, fingerprint evasion, credential sharing, session hijacking, paywall bypass, identity/IP rotation, or aggressive traffic.

For every live request record:

- source and operation;
- final URL or endpoint name with secrets removed;
- HTTP status;
- start/end time and duration;
- retry count;
- cache outcome;
- response content hash;
- adapter/parser/schema version.

Raw evidence must be sanitized before storage.

---

## 5. Required vertical slice

Prove the complete path:

`target date/event -> live discovery -> source event identity -> canonical match -> deep enrichment -> temporal filtering -> persistence -> analysis snapshot -> offline replay -> identical rerun`

The integration is not accepted when only a participant/team profile works. Event retrieval must produce or resolve a real source event identity.

### Mandatory event-discovery output

- source event ID;
- sport and event granularity;
- competition/tournament and season/stage when available;
- scheduled source start time and timezone semantics;
- source status;
- source participant IDs and original names;
- evidence reference;
- parser/schema version.

If the source supplies event IDs, absence of the ID is a hard failure.

---

## 6. Event and participant matching

Resolve identity in this order:

1. existing source-ID crosswalk;
2. exact provider participant IDs;
3. manually approved alias/crosswalk;
4. deterministic candidate generation using hard constraints;
5. fuzzy scoring only inside the blocked candidate set;
6. `AMBIGUOUS` or `NOT_FOUND`.

Hard constraints should use all applicable fields:

- sport;
- event granularity;
- competition/season/stage;
- participant set;
- kickoff/start-time window;
- round, best-of format, venue, or map/series context.

Never auto-link from names alone. Store matching features, matcher version, threshold version, competing candidates, and final decision. A false positive is more damaging than a missing enrichment.

Adversarial matching tests must include aliases, diacritics, sponsor prefixes, academy/youth/women variants, same participants playing twice, rescheduled events, and historical organisation/roster changes where relevant.

---

## 7. Capability inventory and deep-stat coverage

First inspect what the source actually supports. Build a capability matrix with one semantic result for every applicable capability.

### Universal capability families

- event schedule, status, result and competition context;
- H2H;
- recent form;
- standings or rankings;
- team/player/participant statistics;
- injuries, suspensions, withdrawals or availability;
- predicted lineup;
- confirmed lineup or starters;
- historical and event-effective roster;
- venue, surface and weather where relevant;
- odds and market snapshots;
- sport-specific tactical context;
- tipster/editorial opinions as an isolated untrusted-data capability.

### Sport-specific depth examples

- **Football:** team/player splits, injuries, suspensions, predicted/confirmed XI, venue, weather, odds.
- **Basketball:** pace/efficiency splits, player availability, starters, roster, venue, odds.
- **Volleyball:** set-level form, team/player statistics, roster and availability.
- **Tennis:** ranking at cutoff, surface, H2H, recent matches, serve/return statistics, withdrawals, venue/weather.
- **Hockey:** goalie/line context, injuries, roster, special-teams statistics, venue and odds.
- **CS2:** series and map history, map pool, veto when available, rankings, roster, patch/version and odds.
- **Dota 2:** tournament stage, patch, event-effective roster, hero/draft context, recent matches and odds.
- **Valorant:** series/maps, patch, map pool, event-effective roster, agent/map statistics and odds.

Do not fabricate unsupported fields. Use `NOT_SUPPORTED`, `NOT_PUBLISHED_YET`, or `NOT_FOUND` accurately.

For each capability also declare a source-specific refresh profile: positive TTL, negative TTL, event-state trigger, provider update limitation and maximum request budget. Do not introduce one universal polling interval.

Every capability must return exactly one status:

- `SUCCESS`
- `PARTIAL`
- `NOT_FOUND`
- `NOT_PUBLISHED_YET`
- `NOT_SUPPORTED`
- `STALE`
- `AMBIGUOUS`
- `BLOCKED`
- `PARSE_ERROR`
- `SCHEMA_ERROR`

An empty collection is not automatically `SUCCESS`. Missing data is never stored as numeric zero.

---

## 8. Point-in-time correctness

Create one immutable `analysis_cutoff_at` for the acceptance event.

Every persisted observation must retain, where available:

- source event time;
- trustworthy source publication time;
- trustworthy source update time;
- system first-seen time;
- fetch time;
- ingestion time;
- real-world valid-from/valid-to interval;
- temporal eligibility and rejection reason.

### Earliest provable availability

Use a source publication timestamp only when it clearly describes the exact item/version. Otherwise, use the system first-seen timestamp. Never backdate current data based on the event date, URL, page order, current database contents, or a guessed publication time.

Only observations whose earliest provable availability is at or before the cutoff may enter the analysis snapshot.

### Required temporal invariants

- the analyzed event cannot appear in its own recent form or H2H;
- every recent-form/H2H event included for prediction must occur strictly before the analyzed event;
- future events and postponed duplicates are excluded;
- current rosters cannot represent historical esports events unless membership is effective at the event time;
- predicted and confirmed lineups are distinct states;
- current standings/rankings fetched after an old event do not become historical standings/rankings;
- post-event corrections may be stored but cannot alter the original pre-event snapshot;
- odds remain append-only snapshots, not a mutable current value;
- weather must preserve forecast issue time as well as forecast-valid time.

---

## 9. Raw evidence and deterministic replay

Persist or reference immutable sanitized evidence before normalization:

- JSON response;
- HTML response;
- relevant XHR body;
- minimized DOM fixture;
- HAR or browser trace only when needed for diagnosis.

Use content hashing and compression. Redact authorization headers, cookies, API keys and unnecessary personal data.

Every observation must reference real evidence and record the adapter/parser/schema version.

Create an offline replay test that:

1. performs no network requests;
2. reads retained evidence;
3. executes the real parser and normalizer;
4. produces the same semantic observations and snapshot as the live run, excluding explicitly volatile operational metadata.

For HTML sources add:

- semantic selectors rather than absolute paths;
- DOM/schema signature;
- cardinality and cross-field assertions;
- mutated fixtures for missing, reordered, duplicated and renamed sections;
- fail-closed quarantine on structural drift;
- no `SUCCESS` from a selector that silently returns empty data.

---

## 10. Reliability and source isolation

Use separate connect/read/pool or equivalent timeouts and an overall operation deadline.

Retry only idempotent reads for transient conditions such as connection reset, timeout, `408`, `429`, `502`, `503`, and `504`. Respect `Retry-After`. Use bounded exponential backoff with jitter and a source retry budget.

Do not retry authentication failures, access blocks, parser failures, schema failures, valid empty responses, or unsupported capabilities.

Enforce:

- bounded per-host concurrency;
- provider/source rate budget;
- request coalescing for identical in-flight operations where practical;
- isolated capability execution;
- partial results when one capability fails;
- no single source/capability consuming the complete event deadline;
- source quarantine after repeated parser/schema/access failures.

Do not hedge third-party or rate-limited requests.

---

## 11. Persistence and idempotency

Source observations are append-only. Canonical/current state is a separate derived projection.

At minimum enforce logical uniqueness for:

- `(source, source_event_id)`;
- `(source, source_participant_id)`;
- analysis snapshot `(canonical_event_id, analysis_cutoff_at, policy_version)`;
- content-addressed raw evidence;
- capability observation identity;
- lineup/roster/odds child identities.

An observation idempotency key should derive from stable source identity, capability, schema version, normalized payload identity and applicable source/valid-time identity. It must not contain run ID, retry count or fetch timestamp.

Execute the complete live flow twice against the disposable database. The second run must create zero duplicate logical records.

Network access must occur outside long database transactions. Persist each capability result, its evidence and normalized children atomically where the current architecture permits.

---

## 12. Required tests

Use the repository's current test stack. Add only tests required for this integration.

### Deterministic suite

- parser/normalizer unit tests;
- adapter contract tests;
- event-matching positive, negative and ambiguous tests;
- temporal leakage tests;
- current-event exclusion tests;
- predicted-versus-confirmed lineup tests where applicable;
- temporary-database integration tests;
- identical-rerun/idempotency test;
- offline evidence replay test;
- controlled failures: timeout, `429`, malformed payload, valid empty, unsupported capability, delayed publication and one capability failure.

### Live suite

Live tests must be separately marked/tagged and excluded from normal unit CI. A source outage or access block must not be reported as a deterministic parser regression.

The live test must prove:

- a real response was fetched during this run;
- a real source event ID was obtained or validated;
- parsed observations reference the new evidence hash;
- the disposable database contains the expected logical records;
- replay of the same evidence passes offline.

---

## 13. Review-and-repair workflow

### Phase A — Inspect

- Map the current source path end to end.
- Identify concrete defects with file/line references and evidence.
- Run baseline deterministic tests.
- Do not edit yet.

### Phase B — Plan

Write a short implementation plan containing only changes needed to pass this contract. Explicitly list deferred issues.

### Phase C — Live proof before broad refactoring

- Run one real discovery/read request.
- Save sanitized evidence.
- Verify source event identity and capability availability.
- Record actual failures.

### Phase D — Minimal repair

Implement the smallest coherent change. Follow existing code style and architecture. Do not create abstractions without at least two concrete consumers or a correctness requirement.

### Phase E — Deterministic verification

Run unit, contract, replay, database, matching, temporal and failure tests.

### Phase F — Live verification

Run the separately marked live test, then the identical second run.

### Phase G — Adversarial review

Review the final diff for:

- false matches;
- future leakage;
- empty-data false positives;
- stale data presented as current;
- duplicate persistence;
- unbounded retry or timeout behavior;
- leaked secrets;
- source-specific assumptions incorrectly moved into shared code;
- tipster/untrusted text reaching privileged agent instructions.

Fix critical/high issues and rerun affected tests.

---

## 14. Acceptance gate

The run is `PASS` only when every applicable gate passes:

1. A real live response was fetched during the run.
2. The real source event ID is persisted or validated.
3. Event matching is deterministic and not ambiguous.
4. Discovery is not implemented through participant-profile lookup.
5. Capability statuses distinguish unsupported, not published, not found, stale and parser/schema failures.
6. No missing value is converted to zero.
7. The current event and future events are absent from recent form/H2H.
8. No post-cutoff observation enters the analysis snapshot.
9. Predicted and confirmed lineups cannot be confused.
10. Historical roster/participant membership is event-effective where applicable.
11. Every persisted observation references real retained evidence.
12. Offline replay is deterministic.
13. The identical second run creates zero logical duplicates.
14. One capability failure yields `PARTIAL` rather than destroying successful capabilities.
15. Live tests remain separate from deterministic CI.
16. Secrets are absent from logs, evidence, fixtures and Git diff.
17. All changed deterministic tests pass.
18. The final diff contains no unrelated refactoring.

A correctly classified `NOT_SUPPORTED`, `NOT_PUBLISHED_YET`, or valid empty result does not fail the run. Use `PARTIAL PASS` only when the integration remains safe and correct but a non-core capability could not be fully live-proven because of source state, quota, or availability. Any ambiguity, temporal leakage, fabricated evidence, duplicate persistence, false `SUCCESS`, or unproven core event identity is an automatic `FAIL`.

---

## 15. Mandatory final report

Return a concise execution report:

### Target
- source, sport, primary date/event and analysis cutoff;
- real source event ID and canonical event ID;
- optional supporting event and its narrowly stated purpose.

### Baseline findings
- verified defects, each with evidence;
- root cause, not speculation.

### Changes
- changed files and purpose;
- migrations/constraints added;
- intentionally deferred work.

### Live evidence
- command or test used;
- HTTP outcome without secrets;
- evidence hashes;
- capability statuses;
- temporal rejections.

### Verification
- deterministic test commands/results;
- live test command/result;
- first-run versus second-run insert counts;
- replay result;
- database assertions.

### Gate table
For each acceptance gate: `PASS`, `PARTIAL`, `FAIL`, or `N/A`, with one-line evidence.

### Verdict
- `PASS`, `PARTIAL PASS`, or `FAIL`;
- exact next integration or local repair recommendation;
- no broad roadmap.

---

## 16. Stop rule

Stop immediately after the selected integration gate is evaluated.

Do not start another source, extract a universal framework, or continue with unrelated improvements in the same run.
