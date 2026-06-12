# REM-002C-FB — API-Football Vertical Production Closure

## Model
Use **GPT-5.4 with reasoning effort HIGH**.

## Mission
Close exactly one vertical:

`api-football::football::EVENT_AND_ENRICHMENT::default`

Accepted baseline:
- API-Sports discovery is wired and live-proved.
- API-Football discovery preserves provider fixture/team IDs.
- Discovery evidence, no-network replay, and duplicate-free rerun are proved.
- ESPN Football is a certified fallback.
- API-Football enrichment returned live SUCCESS for fixture stats and team fixtures.
- Full bundle IDs must be read from existing artifacts; do not use only the prefixes shown in chat.

Do not work on basketball, volleyball, hockey, Odds-API-IO, SportDB.dev, TheSportsDB, HTML/XHR, browser integrations, or another provider family.

## Required outcome
Assign one truthful final state to API-Football.

`PRODUCTION_READY` requires this real production flow:

`discovery -> canonical fixture -> fixture_sources -> typed enrichment ->
temporal filtering -> normalization -> persistence -> evidence linkage ->
no-network replay -> identical rerun -> downstream read`

A direct client call is not enough.

## Read only necessary context
Read completely:
- `@/SPORTS_INTEGRATION_LIVE_REVIEW_CONTRACT.md`
- `@/docs/audits/sports-integrations/2026-06-11/INTEGRATION_MATRIX.md`
- `@/docs/audits/sports-integrations/2026-06-11/EVIDENCE_MANIFEST.json`
- `@/docs/audits/sports-integrations/2026-06-11/REMEDIATION_BACKLOG.md`
- `@/docs/audits/sports-integrations/2026-06-11/repairs/REM-002B_API_SPORTS_FAMILY.md`
- API-Football client and discovery adapter
- production football enrichment/fallback consumers
- relevant repositories and downstream readers
- shared typed-result/evidence primitives
- focused API-Football and ESPN Football tests

Do not reread historical superseded portfolio reports. Use targeted searches and line ranges.

## Preserve accepted work
Do not rebuild or refactor for style:
- discovery wiring
- participant identity
- canonical source-reference persistence
- discovery evidence/replay
- live-test isolation
- ESPN fallback certification

Only change accepted code when a focused failing test proves a defect.

## Preflight
1. Record branch, commit and `git status --short`.
2. Preserve unrelated work.
3. Locate the full fixture-stats and team-fixtures bundle IDs and their raw objects.
4. Verify every object exists and matches full SHA-256.
5. Identify target canonical fixture, API-Football fixture ID, home/away team IDs, kickoff, league and season.
6. Inventory only production-reachable football enrichment methods.
7. Classify each as `CORE`, `OPTIONAL`, `UNSUPPORTED`, or `DEAD_OR_UNREACHABLE`.
8. Collect current non-live test nodeids. At closure require zero unintended removals; new tests may increase the count.
9. Write at most one small JSON checkpoint under `.kilo/artifacts/rem002c_fb/`. Do not create a recovery report.

## One coherent workflow
Prefer one canonical fixture for discovery, recent form and persistence.
Use a second completed fixture only when final statistics cannot legitimately be proved on the primary fixture.

Do not combine unrelated direct-client calls and describe them as end-to-end proof.

## Typed enrichment
For every production-reachable `CORE` operation:
- use the canonical typed result
- preserve status, typed payload, provider IDs, HTTP status, retry/quota metadata, parser diagnostics, evidence refs and full bundle ID
- route the typed result through the real production consumer
- never collapse failures to `[]`, `{}`, `None`, or zero
- treat provider errors inside HTTP 200 as failures
- preserve valid empty, `NOT_PUBLISHED_YET`, and `NOT_SUPPORTED`
- fail closed on evidence-store failure

Legacy compatibility methods may remain, but the production path must use typed results.

## Identity and side attribution
Use exact API-Football IDs:
- fixture
- home team
- away team
- league
- season when supplied

Requirements:
- requested fixture matches the persisted API-Football source reference
- requested team belongs to the expected canonical participant
- home/away attribution uses exact provider team ID only
- neither-side and both-side cases fail closed
- names and array order are never identity proof
- blank IDs, `"None"`, unknown participants, and missing kickoff are rejected
- conflicting source mappings fail closed

## Point-in-time rules
Use immutable:
- `target_start_at`
- `analysis_cutoff_at`
- `target_source_event_id`

For recent form/H2H:
- exclude target fixture
- include only fixtures strictly before target start
- reject missing ID/start time
- deduplicate postponed/rescheduled copies
- apply `last_n` after temporal filtering
- resolve team side by provider ID
- never use wall-clock now as a historical cutoff

For completed-match statistics:
- retain first-seen/fetched and valid-time metadata
- never include post-match stats in a pre-match snapshot

## Statistical semantics
For each persisted normalized metric verify:
- source JSON path
- normalized field
- unit and scale
- total/average/rate/percentage meaning
- team/event granularity
- sample window
- null versus true zero
- side attribution
- raw/accepted/rejected counts

Adversarial tests must cover:
- blank value
- non-numeric value
- `0.53` versus `53`
- duplicate metric
- unknown metric
- missing side
- wrong provider team ID
- partial payload

Never convert missing or invalid values to zero.

## Evidence and replay
Reuse retained live objects whenever sufficient. Do not repeat live requests just to obtain new timestamps.

For every `CORE` operation:
1. verify sanitized raw bytes and full object SHA-256
2. verify deterministic bundle identity
3. link bundle to persisted enrichment observation/run
4. replay with all outbound network blocked
5. verify every object hash
6. fail closed on missing/corrupt objects or unexpected requests
7. compare live and replay semantic outputs and diagnostics
8. prove the production consumer receives the replayed typed result

If evidence is incomplete, allow at most **4 new API-Football requests** in the entire run. Check quota first.

## Fallback
Prove the real football fallback chain:
- API-Football is attempted according to configured priority
- successful API-Football data avoids unnecessary fallback
- a deterministic typed failure can trigger ESPN Football
- the API-Football failure remains observable
- ESPN success does not rewrite primary failure as empty success
- one capability failure does not erase successful capabilities
- missing values remain missing

Use injected deterministic failures; do not waste live quota to manufacture failures.

## Persistence and idempotency
Use a disposable database.

Run the full production football workflow twice with identical inputs and retained evidence.

Second run must create:
- zero duplicate canonical fixtures
- zero duplicate `fixture_sources`
- zero duplicate enrichment observations
- zero duplicate recent/team-form rows
- zero duplicate evidence links

Append-only run telemetry may add a run record only when intentionally designed.

Read persisted output through the actual downstream reader and compare it with live and replay output.

## Efficient test order
During implementation run focused tests only.

Final sequence:
1. focused API-Football parser/enrichment/consumer tests
2. deterministic API-Football -> ESPN fallback tests
3. one no-network enrichment replay
4. one identical persistence rerun
5. strict marker validation
6. Ruff/static/compile checks on changed files
7. full non-live suite exactly once

Do not run live basketball, volleyball, or hockey tests.
Do not require the historical count `662`; require zero unintended non-live nodeid removals.

## Documentation limit
Update only:
- `INTEGRATION_MATRIX.md`
- `EVIDENCE_MANIFEST.json`
- `REMEDIATION_BACKLOG.md`
- existing `REM-002B_API_SPORTS_FAMILY.md`

Add at most 40 lines to the existing family report.
Do not create another report, architecture document, or test transcript.

## Final state
Set API-Football to `PRODUCTION_READY` only when accepted discovery plus every production-reachable `CORE` enrichment path passes:
- production wiring
- provider identity
- side attribution
- temporal correctness
- statistical semantics
- typed status propagation
- evidence linkage
- no-network replay
- duplicate-free rerun
- downstream read
- fallback observability
- direct deterministic tests
- no unresolved critical/high blocker

Otherwise retain `LIVE_PARTIAL`, or use `PRODUCTION_CANDIDATE` only when exactly one non-critical external limitation remains.

Name exactly one blocker.

## Required final response
Return only:

RESULT: PASS | PARTIAL | FAIL
FINAL_STATE: <state>
TARGET_FIXTURES: <canonical/provider IDs and purpose>
CORE_CAPABILITIES: <concise list>
LIVE_REQUESTS: <0-4, quota and new bundle IDs>
REPLAY: <result and bundle IDs>
IDEMPOTENCY: <first/second domain row deltas>
FALLBACK: <typed primary failure + ESPN outcome>
TEST_INVENTORY: <baseline/current/unintended removals>
TESTS: <focused/full non-live/lint-static>
GATE_DELTA: <concise>
REMAINING_BLOCKER: <NONE or exactly one>
CHANGED_FILES: <paths only>

## Stop rule
Stop immediately after the API-Football gate.

Do not start basketball, volleyball, hockey, Odds-API-IO, SportDB.dev, TheSportsDB, HTML/XHR, browser automation, or another provider family.
