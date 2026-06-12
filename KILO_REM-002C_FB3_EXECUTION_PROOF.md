# REM-002C-FB3 — Execute Missing Enrichment Replay and Idempotency Proof

## Model
Use **GPT-5.4 with reasoning effort MEDIUM**.
Escalate to HIGH only if a real defect is found in the evidence-store API,
repository uniqueness constraints, or production enrichment path.

## Objective
Close exactly two remaining gates for:

`api-football::football::EVENT_AND_ENRICHMENT::default`

1. executable no-network replay of retained enrichment evidence;
2. observed duplicate-free persistence from two executions of the real
   API-Football enrichment production path.

Do not add capabilities, perform broad refactoring, make live requests, or work
on another provider.

## Accepted baseline
Accept unless a focused test disproves it:

- discovery bundle and discovery replay are valid;
- discovery idempotency is valid;
- provider event/team identity is valid;
- temporal filtering and target-event exclusion are valid;
- provider-ID side attribution is valid;
- fallback order is ESPN Football primary -> API-Football fallback;
- retained enrichment bundles exist:
  - fixture stats:
    `2b0ed4ba3c4a80b2ebff7670c1645d0dd89a8c9c8e887f71f9284bb71691a0af`
  - team fixtures:
    `b01f22fbb05326dc37de3230fe1accacd83c54586f3c2d17bdceb6fb76359e16`
- canonical evidence root is `betting/data/evidence`;
- `get_event_fixture_result` is an internal helper.

Not accepted:

- `network_blocked=N/A` is not replay proof;
- hash verification alone is not semantic replay;
- describing repository methods as upserts is not executed idempotency proof;
- stable content-addressed references are not evidence-link count proof.

Keep API-Football `LIVE_PARTIAL` until both gates pass.

## Read only necessary files
Read:

- current `INTEGRATION_MATRIX.md`;
- current `EVIDENCE_MANIFEST.json`;
- current `REMEDIATION_BACKLOG.md`;
- existing `REM-002B_API_SPORTS_FAMILY.md`;
- canonical evidence-store implementation;
- API-Football typed enrichment methods;
- `_try_api_sports_fetch()` and the production persistence/downstream path;
- `StatsRepo`, relevant schema constraints and focused tests.

Use targeted searches and line ranges. Do not load superseded audit reports.

## Phase 1 — public evidence-store verification
For each enrichment bundle:

1. load the manifest through the production evidence-store API;
2. verify the bundle ID;
3. load every referenced raw object;
4. recompute every object SHA-256;
5. record source, operation, provider IDs, parser version and object count;
6. fail on missing or mismatched objects.

Do not read arbitrary files directly as a substitute for exercising the public
evidence-store API.

No live calls are allowed.

## Phase 2 — executable no-network replay
Add or execute dedicated replay tests for:

- `get_fixture_stats_result`;
- `get_team_last_fixtures_result`.

Each test must:

1. use the retained provider bytes;
2. invoke the same typed parser used by production;
3. invoke the real production consumer;
4. block outbound networking at the shared transport/socket boundary;
5. fail immediately on any unexpected network attempt;
6. compare status, provider identities, parser diagnostics, normalized payload
   and downstream result with the retained live result;
7. fail closed when an object is missing or corrupt.

Add one negative test that deliberately causes an unexpected request and proves
the blocking boundary is actually used.

Report exact test nodeids.

## Phase 3 — verify real uniqueness constraints
Inspect actual schema constraints and repository conflict targets for:

- `fixture_sources`;
- `team_form` or the real recent-form table;
- source observations/runs;
- evidence links.

Do not infer idempotency from the word `upsert`.

Verify every `ON CONFLICT` target corresponds to an actual `UNIQUE` or
`PRIMARY KEY` constraint. Check whether nullable key fields can bypass logical
deduplication.

Add focused schema/repository assertions when needed.

## Phase 4 — execute the API-Football enrichment path twice
Use a disposable database and retained evidence.

Invoke the real production path twice:

`canonical fixture -> fixture_sources -> _try_api_sports_fetch() ->
typed enrichment -> temporal filtering -> persistence -> downstream read`

Do not invoke ESPN and do not manually construct repository rows.

Capture first-run and second-run logical identities and counts for:

- canonical fixtures;
- `fixture_sources`;
- recent/team-form rows;
- persisted stat/source observations, when applicable;
- evidence links;
- downstream returned records.

Required:

- second-run logical delta is zero for every domain table/reference;
- stable provider source IDs and bundle IDs;
- no `"None"` source IDs or empty evidence links;
- downstream semantic result is identical.

If fixture stats are intentionally transient:

- report `normalized_stats=NOT_APPLICABLE`;
- prove replay/downstream equality;
- do not add a new table solely for this task.

Add a dedicated API-Football idempotency test. Reusing an ESPN test is
forbidden.

## Phase 5 — changed-evidence history proof
Using a deterministic modified copy of retained evidence, prove one of:

- a materially changed payload creates a new append-only observation/version; or
- the current projection changes while the underlying evidence history remains
  preserved and addressable.

Do not make a live request.

The only audit trail must never be silently overwritten.

## Phase 6 — efficient validation
Run only:

1. focused evidence-store tests;
2. focused enrichment replay tests;
3. focused API-Football double-run test;
4. focused changed-evidence/versioning test;
5. Ruff/static/compile checks on changed files;
6. full non-live suite exactly once only if production/shared code changed.

No live tests and no other sports.

## Audit updates
After proof, update only:

- `INTEGRATION_MATRIX.md`;
- `EVIDENCE_MANIFEST.json`;
- `REMEDIATION_BACKLOG.md`;
- existing `REM-002B_API_SPORTS_FAMILY.md`.

Add no more than 20 lines to the existing report.

Correct prior G7/G8 claims if they were based only on hash verification or
repository design.

## Final-state rule
Set `PRODUCTION_READY` only when:

- both enrichment bundles replay through the actual parser and consumer with
  networking blocked;
- all raw hashes are verified;
- the real API-Football production path executes twice;
- second-run logical deltas are zero;
- uniqueness constraints are directly verified;
- changed evidence preserves auditable history;
- no critical/high blocker remains.

Otherwise retain `LIVE_PARTIAL` and name exactly one blocker.

## Required final response
Return only:

RESULT: PASS | PARTIAL | FAIL
FINAL_STATE: <state>

REPLAY:
fixture_stats=<bundle, network_blocked, semantic_match, test_nodeid>
team_fixtures=<bundle, network_blocked, semantic_match, test_nodeid>
negative_network_test=<result>

CONSTRAINTS:
fixture_sources=<constraint/conflict target>
team_form=<constraint/conflict target>
evidence_links=<constraint/conflict target>
nullable_key_risk=<PASS/FAIL>

IDEMPOTENCY:
fixtures=<first/second/logical_delta>
fixture_sources=<first/second/logical_delta>
team_form=<first/second/logical_delta>
normalized_stats=<first/second/logical_delta or NOT_APPLICABLE>
evidence_links=<first/second/logical_delta>
downstream_semantic_match=<PASS/FAIL>

VERSIONING:
changed_evidence=<append-only version or preserved evidence history proof>

TESTS:
focused=<result>
full_non_live=<result or NOT_RUN_WITH_REASON>
lint_static=<result>

GATE_DELTA:
G7=<state>
G8=<state>

REMAINING_BLOCKER:
<NONE or exactly one>

CHANGED_FILES:
<paths only>

## Stop
Stop after this API-Football execution gate.

Do not start basketball, volleyball, hockey, Odds-API-IO, SportDB.dev,
TheSportsDB, HTML/XHR, browser automation or another provider family.
