# REM-002A — Lean Crosswalk, Evidence, Status, and Migration Foundation (V2)

Use **GPT-5.4 with reasoning effort HIGH**.

## Mission

Close the remaining ESPN Football foundation defects with the **smallest reusable implementation** that will later accelerate provider-family repairs.

Validate it on `espn-football` only. Do not migrate another provider in this run.

The required outcome is not “tests pass”. The required outcome is:

1. ESPN enrichment resolves the ESPN event through the canonical fixture-source crosswalk, never by assuming the canonical fixture external ID belongs to ESPN.
2. Persisted projections reference a complete, replayable, content-addressed evidence bundle.
3. The critical ESPN orchestration path receives an explicit typed result and can distinguish valid empty data from source failures.
4. Schema migration is safe for fresh, populated, restarted, and partially migrated SQLite databases.
5. The audit files contain one consistent final state supported by direct evidence.

## Efficiency constraints

- Work in one clean worktree and preserve unrelated changes.
- Do not perform broad web research or write a new architecture document.
- Before creating anything, search for and reuse existing fixture-source, cache/evidence, transport, result, migration, and repository abstractions.
- Add no dependency unless the repository cannot meet an acceptance criterion without it.
- Do not create a universal integration framework.
- While implementing, run only focused tests. Run the shared ESPN suite once after focused tests pass and the complete suite once at the end.
- Do not repeatedly run the full suite.
- Keep the final repair report at **80 lines or fewer**.
- Do not start the next remediation item automatically.

## Read first

Read completely:

- `@/SPORTS_INTEGRATION_LIVE_REVIEW_CONTRACT.md`
- `@/docs/audits/sports-integrations/2026-06-11/INTEGRATION_MATRIX.md`
- `@/docs/audits/sports-integrations/2026-06-11/EVIDENCE_MANIFEST.json`
- `@/docs/audits/sports-integrations/2026-06-11/REMEDIATION_BACKLOG.md`
- `@/docs/audits/sports-integrations/2026-06-11/repairs/REM-001_FINAL_RECERTIFICATION.md`
- `@/src/bet/api_clients/espn.py`
- `@/src/bet/stats/enrichment.py`
- `@/src/bet/db/models.py`
- `@/src/bet/db/repositories.py`
- `@/src/bet/db/schema.py`
- `@/src/bet/db/schema.sql`
- `@/src/bet/db/migrations/014_team_form_evidence.sql`
- the actual `fixture_sources`, transport, cache, telemetry, and migration code reached by these paths
- all repository instructions applicable to the changed files

## Binding baseline

Verify these facts against code and evidence; do not trust older prose claims:

- `espn-football` is at most `PRODUCTION_CANDIDATE`.
- The previous migration verification terminated before proving restart, partial migration, equivalence, and round-trip claims.
- The current `evidence_hash` is a truncated hash of event IDs, not a content-addressed evidence reference.
- `source_event_ids` are not source-namespaced.
- The prior review bundle did not contain every response referenced by its live summary.
- `fixtures.external_id` is not guaranteed to be ESPN-owned.
- Valid empty data, malformed JSON, HTTP failures, and timeouts still collapse to the same list/empty-list interface.
- Audit files disagree about G11, status taxonomy, “all gates pass”, and production readiness.

## Preflight — no code changes yet

Record in the final report, without creating a separate plan file:

- baseline commit and `git status --short`;
- exact atomic integration key and registered source key;
- the current ESPN fallback call path;
- where `fixture_sources` is written and queried;
- whether migration 014 may already have been applied to any local/shared database;
- existing evidence/cache abstraction that can be reused;
- existing transport result/error classification;
- intended changed production files.

If migration 014 may already have been applied, **do not rewrite its meaning as if it were new**. Keep applied migrations immutable. Add a new migration version only if the database schema must change. A code-only repair of the migration runner does not require a schema-version bump.

## A. Exact ESPN source-event resolution

Implement the narrowest safe resolver used by the ESPN Football enrichment path.

### Required lookup order

1. Load the canonical fixture by internal `fixture_id`.
2. Query `fixture_sources` using the exact registered ESPN Football source key and internal fixture ID.
3. Require exactly one distinct, non-empty ESPN external event ID.
4. Zero mappings → explicit `NOT_FOUND`; do not fall back to `fixtures.external_id`.
5. More than one distinct mapping → explicit `AMBIGUOUS`; do not pick the first and do not persist enrichment.
6. Fetch/validate the mapped ESPN event before using it.

### Validation invariants

- Returned ESPN event ID equals the crosswalk ID.
- Sport and league/competition are compatible with the target fixture.
- Kickoff obeys the existing configured matching policy; do not invent an unreviewed tolerance.
- Provider participant IDs are present.
- Home and away are selected only from explicit provider side markers and exact provider participant identity.
- Missing, duplicated, neither-side, or both-side identities fail closed.
- Names may be diagnostic features only. They cannot be the final automatic identity proof.

Do **not** build a new fuzzy crosswalk-creation engine in this slice. If the mapping is absent, return `NOT_FOUND` and record a future discovery/crosswalk-population task. The live test may insert an already verified mapping into its disposable database.

Required deterministic cases:

- canonical `fixtures.external_id` belongs to a different provider while the ESPN ID exists only in `fixture_sources`;
- zero ESPN mappings;
- duplicate identical rows normalize to one logical mapping or are rejected according to existing repository policy;
- two distinct ESPN mappings fail as `AMBIGUOUS`;
- mapped response has wrong event ID;
- missing/duplicated provider sides fail closed.

## B. Truthful content-addressed evidence

Reuse an existing evidence abstraction if it satisfies every invariant below. Otherwise add one small shared module; do not add a lineage platform.

### Evidence object

For every ESPN response actually used to produce the persisted TeamForm projection:

- sanitize before persistence using a deterministic, versioned policy;
- retain the exact sanitized response bytes used by the parser;
- compute the **full 64-character SHA-256** over those exact bytes;
- store the object content-addressed by that hash in the application evidence store; `.kilo/artifacts` may contain audit copies but must not be the runtime source of truth;
- make the evidence root configurable and use a temporary root in tests;
- write atomically using a temporary file and rename/replace; concurrent writers of the same hash must converge on one verified object;
- never include authorization values, cookies, API keys, secret query parameters, or user-specific identifiers;
- store only an allowlisted subset of response metadata.

The content hash must change when sanitized response bytes change. It must not depend on local path, run ID, or capture time. Cache hits must retain or resolve the original evidence bytes and object hash; hashing only a parsed/normalized cache value is insufficient.

### Stable evidence bundle

Create a canonical manifest for the complete set of evidence objects used by one persisted projection.

The **hashed identity section** must contain only stable fields:

- manifest schema version;
- registered source key;
- capability/projection name;
- canonical fixture ID;
- namespaced source event references;
- parser version;
- sanitization-policy version;
- ordered evidence entries containing operation, normalized secret-free request identity, source event ID when applicable, media type, byte size, and full object SHA-256.

Exclude volatile fields such as `captured_at`, run ID, local path, latency, and retry count from the bundle identity. Store them as non-identity metadata if useful.

Canonical serialization must be deterministic UTF-8 JSON using sorted keys, compact separators, and a stable entry ordering. Compute the full SHA-256 of the canonical identity section; this is the bundle ID persisted in `TeamForm.evidence_hash`.

### Stored source references

Keep the existing `source_event_ids` field unless a schema change is unavoidable. Store canonical, deduplicated, sorted namespaced strings for all new writes:

```text
espn-football:<event_id>
```

Never store bare IDs, `None`, empty strings, duplicates, or unstable input order. Existing rows containing bare IDs or 16-character hashes are legacy/unverified evidence: keep them readable, do not invent a namespace or raw-evidence link, and do not backfill them without provable source provenance.

### Retrieval and replay

The runtime evidence-bundle manifest is distinct from the audit file `docs/.../EVIDENCE_MANIFEST.json`. Given `TeamForm.evidence_hash`, application code must be able to:

1. locate the evidence bundle manifest;
2. recompute and verify the bundle ID;
3. locate every referenced object;
4. recompute and verify every object SHA-256;
5. feed the retained bytes to the same parser with outbound network unavailable.

Missing, corrupted, or mismatched objects must fail closed. They must never silently fall back to live network.

Write evidence objects and the complete bundle before committing the TeamForm row that references them. A row must never reference an incomplete bundle.

Required deterministic cases:

- same evidence with different capture times produces the same bundle ID;
- input ordering and duplicate references do not change the bundle ID;
- changed response bytes change the object and bundle hashes;
- missing/corrupted object fails replay;
- secrets are absent from stored request identity and evidence metadata;
- a cache hit and an equivalent live response resolve to the same object/bundle identity when the sanitized bytes are identical;
- legacy 16-character hashes and bare event IDs remain readable but are not falsely certified as replayable evidence;
- identical second persistence run creates no logical duplicate or spurious evidence identity.

## C. Minimal explicit source-result boundary

Introduce or reuse a small typed generic result only at the ESPN operations used by this flow. Do not migrate every adapter.

Minimum fields:

- `status`;
- typed `value`;
- `http_status` when available;
- `retryable`;
- stable error code/class without secrets;
- `retry_after_seconds` when available;
- evidence object references when a response was received.

Required statuses:

- `SUCCESS`
- `NOT_FOUND`
- `NOT_PUBLISHED_YET`
- `NOT_SUPPORTED`
- `AMBIGUOUS`
- `AUTHENTICATION_ERROR`
- `RATE_LIMITED`
- `BLOCKED`
- `TRANSPORT_ERROR`
- `UPSTREAM_ERROR`
- `PARSE_ERROR`
- `SCHEMA_ERROR`

### Exact classification

- HTTP 2xx + valid expected schema + collection with zero items → `SUCCESS` with an empty typed value.
- Singular lookup genuinely absent → `NOT_FOUND`.
- Expected source publication delay → `NOT_PUBLISHED_YET` only when domain evidence supports that interpretation.
- HTTP 401 → `AUTHENTICATION_ERROR`, non-retryable.
- HTTP 403/challenge/access block → `BLOCKED`, non-retryable.
- HTTP 429 → `RATE_LIMITED`, retryability and delay derived from `Retry-After`/policy.
- Connect/read timeout or connection failure → `TRANSPORT_ERROR`, bounded-retryable.
- HTTP 5xx → `UPSTREAM_ERROR`, bounded-retryable.
- Invalid JSON → `PARSE_ERROR`, non-retryable for the same response.
- Valid JSON with incompatible required shape → `SCHEMA_ERROR`, non-retryable.
- Multiple valid source-event mappings → `AMBIGUOUS`, non-retryable.

The actual fallback orchestration must consume the typed result. A legacy list-returning convenience wrapper may delegate to it for compatibility, but the critical ESPN fallback path must not call a wrapper that erases status.

Do not add retries here if the repository already has a retry layer. Preserve one retry authority and avoid nested retry amplification.

Required deterministic cases cover every classification above, including headers for `Retry-After` and a valid empty collection.

## D. Safe SQLite migration handling

The objective is safe real-world behavior, not merely a green fresh-schema test.

- Never execute unconditional `ALTER TABLE ... ADD COLUMN` for a column that may already exist.
- Inspect actual columns before each addition. Use the repository’s row-factory conventions correctly.
- Add each missing column independently.
- Use the current migration transaction model or an explicit savepoint. Do not swallow arbitrary `sqlite3.OperationalError`.
- Update `schema_meta.version` only after the migration and all required indexes complete successfully.
- On failure, keep the previous schema version and leave the database rerunnable.
- Do not create a plain B-tree index on JSON-array text unless an actual query and test justify it.
- Preserve legacy rows as “no evidence”, not fabricated evidence.

If no schema shape changes are needed, keep schema version 14 and repair the migration runner/tests only. If new tables/columns/indexes are required, create the next migration; do not mutate an already applied migration contract.

Prove with disposable databases:

1. fresh schema;
2. populated v13 → current;
3. restart after successful migration;
4. partial migration with only one evidence column present;
5. legacy rows remain readable;
6. fresh and migrated schemas are equivalent by columns, nullability/defaults, and relevant indexes;
7. injected failure before version update leaves the old version and succeeds on rerun;
8. repository write/read round-trip preserves namespaced refs and full bundle hash.

## E. Shared-client blast-radius control

Review the REM-001 changes to the shared ESPN client.

- Revert unrelated behavior changes not required by the accepted ESPN Football invariants.
- In particular, do not retain competition-name or side-order behavior changes merely because the full suite is green.
- Do not infer home/away from array position for the football critical path.
- Add focused deterministic coverage for shared parsing behavior affected across basketball, hockey, volleyball, and tennis, or keep the change football-specific.
- Do not claim football proof certifies another ESPN sport.

## Execution order and test budget

1. Add focused failing regression tests for the confirmed defects before implementation where practical.
2. Implement the smallest coherent changes.
3. Run only the new/focused tests until green.
4. Run the existing ESPN deterministic suite once.
5. Run one permitted ESPN Football live proof.
6. Run replay with the project transport replaced by a fail-on-call transport and a socket-level sentinel as defense in depth.
7. Run the identical persistence flow a second time.
8. Run lint/static checks on every changed production and test file.
9. Run the complete repository test suite exactly once.
10. Review the final diff for scope leakage, hidden fallbacks, secret exposure, and contradictory audit claims.

Do not report mocked transport as live evidence. Do not make a live test pass by falling back to an arbitrary event.

## Live proof

Use one coherent ESPN Football event end to end in a disposable database.

- Give the canonical fixture a non-ESPN external ID and a different source owner.
- Insert one verified ESPN mapping into `fixture_sources`.
- Resolve the ESPN ID only through that mapping.
- Capture every ESPN response used by the projection.
- Record canonical fixture ID, ESPN event ID, provider participant IDs, cutoff, accepted and rejected recent-event IDs with reasons, object hashes, bundle ID, first-run counts, and second-run counts.
- Replay only from the stored bundle with network blocked.
- Prove malformed JSON, valid empty, 401, 403, 429, 5xx, and timeout statuses using deterministic tests, not repeated live traffic.

## Audit updates — minimal and authoritative

Only after code and verification are complete:

- update the single `espn-football` row in `INTEGRATION_MATRIX.md`;
- update only related records in `EVIDENCE_MANIFEST.json`;
- update only the relevant remediation entries in `REMEDIATION_BACKLOG.md`;
- create `docs/audits/sports-integrations/2026-06-11/repairs/REM-002A_ESPN_FOUNDATION.md`, maximum 80 lines.

The report contains only:

- exact scope and changed files;
- focused, ESPN, lint, live, replay, migration, and full-suite command results;
- live identifiers and bundle ID;
- migration matrix;
- gate delta;
- exactly one final state;
- exactly one remaining blocker, or `NONE`.

Do not repeat code diffs or historical narrative. Do not claim `all gates pass` when any mandatory gate is partial, failed, or not executed. Matrix, manifest, backlog, and report must agree exactly.

## Acceptance gate

Assign `PRODUCTION_READY` only when all are directly proved:

- exact ESPN crosswalk resolution with no canonical-ID ownership assumption;
- fail-closed duplicate/ambiguous identity handling;
- provider-side identity and point-in-time invariants remain green;
- full replayable content-addressed evidence linkage;
- explicit statuses reach the fallback orchestrator without collapsing to `[]`;
- migration scenarios all pass;
- no-network replay passes;
- identical rerun creates zero logical duplicates;
- changed-file lint/static checks and full suite pass;
- all audit artifacts agree.

Otherwise retain `PRODUCTION_CANDIDATE` and name one exact blocker. Do not create a vague blocker list.

## Final response format

Return only:

```text
RESULT: PASS | PARTIAL | FAIL
FINAL_STATE: <one state>
CHANGED_FILES: <compact list>
TESTS: focused=<...>; espn=<...>; live=<...>; migration=<...>; full=<...>
LIVE: canonical_fixture=<id>; espn_event=<id>; bundle_sha256=<64 hex>
GATE_DELTA: <only changed gates>
REMAINING_BLOCKER: NONE | <one exact blocker>
REPORT: <path>
```

## Stop

Stop after REM-002A validation on `espn-football`.

Do not migrate API-Sports, Odds API, Flashscore, VLR, HLTV, BO3.gg, Betclic, or another ESPN sport. Do not create a provider framework, additional reports, or the next backlog task.
