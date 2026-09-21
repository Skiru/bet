# P01 V2 — FOOTBALL REALITY MAP, REFERENCE-PATTERN FIT, AND MINIMAL P02

Use GPT-5.4 with reasoning effort HIGH.

Binding architecture:

`@/docs/prompts/SPORTS_ENRICHMENT_KERNEL_FOOTBALL_GOLDEN_VERTICAL_FINAL_CONTRACT_V3_1.md`

Accepted P00 commit:

`94962f2a46bc3d5c45535769adfd48aea2f2efeb`

Execute P01 only. Do not implement P02 or call any live provider.

## Goal

Produce one accurate map of the current Football production flow and one small,
mechanical P02 foundation slice.

This phase must eliminate uncertainty and reduce implementation size. It must
not create another broad architecture plan.

## External architecture decisions already made

The following patterns were reviewed from mature open-source projects and are
binding implementation clarifications:

1. **Ingestify pattern:** raw provider files/evidence are retained first;
   multi-response provider packages are atomic, complete, versioned, and not
   visible partially.
2. **Kloppy pattern:** request transport, deserialization, and canonical
   normalization are separate layers.
3. **socceraction pattern:** provider-native IDs remain present after
   normalization; provider loaders feed a unified capability model.
4. **Singer/Airbyte pattern:** connector access, capability discovery,
   pagination, truncation, and extraction state are explicit.
5. **dlt pattern:** additive compatible schema drift differs from breaking
   schema drift.
6. **soccerdata boundary:** scraping/cache libraries are research or shadow
   inputs unless they independently pass production gates.
7. **Public-ESPN-API boundary:** reuse health/scheduled-ingestion ideas but do
   not create a new Django/Celery microservice.

Do not add Ingestify, Kloppy, Singer, Airbyte, dlt, or another connector
framework as a runtime dependency.

## Constraints

- No live requests.
- No production implementation.
- No migration.
- No provider modifications.
- No full test suite.
- No Markdown report.
- At most eight new focused tests.
- One JSON artifact plus checkpoint only.
- Use direct code proof where reliable.
- Do not inspect another sport except shared infrastructure callsites.

## 1. Map the executable production flow

Trace real callers from executable/scheduler/command entry to downstream
Football analysis.

Map exact path and symbol for:

- event discovery;
- enrichment scheduling/invocation;
- Football recent form;
- H2H;
- standings;
- fixture/team statistics;
- lineup/injury/roster state;
- provider construction;
- router invocation;
- identity/crosswalk;
- request identity;
- evidence write/read;
- observation/projection persistence;
- snapshot construction;
- final betting/statistical consumer;
- odds boundary;
- schema initialization and migrations.

For each node record:

- caller and callee;
- production/test/dead/compatibility classification;
- Football-specific/shared classification;
- whether it performs HTTP, parsing, normalization, selection, persistence, or
  downstream reading.

Do not treat an uncalled helper as production.

## 2. Map current provider operation layering

For every Football provider currently reachable in production, identify whether
these stages are separate or mixed:

1. request specification;
2. HTTP/shared transport;
3. raw evidence capture;
4. deserialization from bytes;
5. canonical normalization;
6. identity reconciliation;
7. persistence;
8. selection.

Record exact functions where stages are mixed.

Flag as `REPLAY_BLOCKER` when retained evidence cannot be passed through the
actual deserializer and normalizer without HTTP.

## 3. Evaluate evidence package completeness

Determine whether current evidence supports:

- exact parser input bytes;
- request identity;
- content hash;
- parser/schema versions;
- atomic manifest publication;
- multi-response package completeness;
- version/revision identity;
- missing/corrupt-object failure;
- replay lookup by exact request rather than latest operation.

For each capability identify whether one provider result is:

- single-response;
- paginated;
- multi-response package.

A multi-response package is incomplete if one required member is missing or
belongs to a different revision.

## 4. Evaluate connector lifecycle and pagination

For each reachable provider operation prove whether code supports:

- access/auth check without consuming excessive quota;
- declared capability/scope;
- request construction;
- pagination/cursor;
- total/has-more/truncation metadata;
- per-operation extraction state;
- bounded retry/backoff;
- quota metadata;
- negative cache;
- deterministic contract test from raw evidence.

Do not propose Singer or Airbyte integration. Identify only the smallest
internal Python protocol needed later.

## 5. Evaluate schema drift correctly

Classify current schema handling as:

- `COMPATIBLE_ADDITIVE`: optional new fields while canonical DTO still validates;
- `BREAKING_REQUIRED_FIELD`;
- `BREAKING_TYPE`;
- `BREAKING_IDENTITY_OR_SIDE`;
- `BREAKING_TEMPORAL`;
- `BREAKING_PAGINATION`;
- `UNKNOWN`.

Do not require provider demotion for every fingerprint change.

Breaking drift must later quarantine only the affected
provider-operation-capability scope, not the whole provider.

## 6. Verify current downstream truth

Prove:

- every caller of `get_fixture_scoped_form_snapshot()`;
- whether final analysis consumes its normalized value;
- every Football read/write of global `team_form`;
- whether missing projection silently falls back;
- whether stat keys select distinct data;
- whether standings use real competition/season/event/participant scope;
- whether source, native IDs, valid time, and evidence survive into the final
  downstream object.

## 7. Verify persistence and temporal correctness

Record:

- schema version and relevant migrations;
- observation and projection unique constraints;
- dedupe behavior and returned ID;
- changed-evidence version behavior;
- projection upsert/delete-insert behavior;
- selection history;
- foreign-key state in production and tests;
- atomic snapshot/run boundary;
- concurrent-run protection;
- target/future exclusion;
- `last_n` ordering after filtering;
- current-season historical-default reachability.

## 8. Compactly classify F01–F25

For every binding defect assign:

- `BLOCKING_P02`;
- `BLOCKING_FOOTBALL_FLOW`;
- `LATER_PROVIDER_PHASE`;
- `LATER_CERTIFICATION`;
- `ALREADY_FIXED`;
- `NOT_APPLICABLE`.

Each entry contains:

- file and symbol;
- direct proof;
- concise finding;
- target phase;
- dependencies;
- one acceptance assertion.

Do not repeat contract prose.

## 9. Compare current code with reviewed reference patterns

Add `reference_pattern_fit` entries for:

- Ingestify atomic raw package/revision;
- Kloppy loader/deserializer separation;
- socceraction native-ID/unified-model pattern;
- Singer/Airbyte connector state/pagination pattern;
- dlt schema-contract/evolution pattern;
- soccerdata research-only scraper boundary;
- Public-ESPN-API scheduled health pattern.

Classify each:

- `ADOPT_P02`;
- `ADOPT_LATER`;
- `ALREADY_PRESENT`;
- `REJECT_OVERENGINEERING`.

Include exact local files affected and no external dependency proposal.

## 10. Produce no more than six workstreams

Required groups:

1. canonical result, request identity, evidence package;
2. persistence, versioning, atomic snapshot;
3. Football service, temporal rules, downstream cutover;
4. provider adapter protocol, qualification, selected adapters;
5. concurrency, resilience, observability, rollout;
6. replay, idempotency, certification.

For each record current reusable code, exact changes, tests, migration need,
dependencies, and non-goals.

## 11. Produce one minimal P02 slice

P02 may contain only foundation shared by every later phase:

- canonical source result compatibility;
- canonical request identity;
- atomic evidence package/revision using existing evidence code where possible;
- minimum generic subject reference required by actual current schema;
- append-only capability observation with deterministic changed-evidence
  versioning;
- current projection plus selection history;
- immutable snapshot publication boundary;
- additive migration and focused repository/migration tests.

P02 must not include:

- SportDB.dev or Highlightly;
- provider live probes;
- provider ranking or final routing;
- complete Football metric ontology;
- Prometheus/OpenTelemetry;
- feature rollout;
- performance soak;
- certification ZIP;
- a general data lake or external connector framework.

For the proposed P02 provide:

- exact files to create/modify;
- exact next migration number;
- exact tables/columns/indexes;
- compatibility behavior for current Football code;
- exact focused test node IDs to add;
- exit gate;
- size estimate;
- rollback risk.

Do not implement it.

## 12. Validation

Run only:

- focused existing tests touching mapped paths;
- at most eight new behavior tests;
- disposable-DB schema inspection;
- JSON validation;
- import and callsite searches.

No live tests. No full suite.

## 13. Artifacts

Create only:

`.kilo/artifacts/football_golden_v3/p01_call_graph_and_defects.json`

and update:

`.kilo/artifacts/football_golden_v3/checkpoint.json`

The P01 JSON must include:

```json
{
  "baseline_commit": "",
  "production_entrypoints": [],
  "call_graph": [],
  "provider_layering": [],
  "evidence_package_analysis": [],
  "connector_lifecycle": [],
  "schema_drift": [],
  "downstream_truth": {},
  "schema_and_temporal": {},
  "f01_f25": [],
  "reference_pattern_fit": [],
  "workstreams": [],
  "p02_minimal_slice": {},
  "focused_tests": [],
  "gate": {}
}
```

Maximum 600 JSON lines.

## 14. Exit gate

P01 passes only when:

- the executable-to-consumer call graph is complete;
- production, test-only, dead, and compatibility code are distinct;
- provider stages and replay blockers are explicit;
- evidence package completeness is known;
- pagination/truncation/state behavior is known;
- schema drift is classified compatibly rather than by fingerprint alone;
- every Football `team_form` access is classified;
- F01–F25 have direct proof;
- reference patterns have adopt/reject decisions;
- there are at most six workstreams;
- P02 is small, deterministic, and does not include provider work;
- no live request or production implementation occurred.

## 15. Commit and stop

Stage only:

- P01 JSON;
- checkpoint;
- focused P01 tests, when added.

Create and push:

`phase(P01): map football flow and minimal evidence-snapshot foundation`

Do not start P02.

Return only:

```text
PHASE: P01
RESULT: PASS | FAIL
REASONING_USED: HIGH
COMMIT_SHA:
PARENT_SHA:
COMMIT_URL:
ENTRYPOINT:
DOWNSTREAM_CONSUMER:
REPLAY_BLOCKERS:
EVIDENCE_PACKAGE_STATE:
SCHEMA_DRIFT_STATE:
LEGACY_BYPASSES:
DEFECT_CLASSIFICATION:
REFERENCE_PATTERN_DECISIONS:
P02_MINIMAL_SLICE:
TESTS:
CHANGED_FILES:
GATE:
NEXT_PHASE: BLOCKED_PENDING_EXTERNAL_REVIEW
BLOCKER:
```
