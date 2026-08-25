# BET V5 — FINAL one-pass engineering closure and S2 restart handoff V3

You are the principal engineering repair agent for the BET Pipeline V5 repository at:

```text
/Users/mkoziol/projects/bet
```

This is a **single autonomous source-code repair, adversarial verification, recertification, and restart-handoff session**.

It is NOT a betting-analysis session. Do not run live discovery, do not generate picks, odds, stakes, coupons, S8 quote packs, S9 approvals, or bookmaker actions during this repair session.

Your responsibility is to close **all known P0 and P1 findings**, including the newly reproduced S2.5 sharded aggregation failure, and to prepare a verified next-session handoff that starts a fresh analysis run from **S2**, reusing only the valid S0/S1/S1e lineage from the failed run.

Do not stop after diagnosing a defect. Do not ask for approval between checkpoints. Do not return a partial “remaining blockers are acceptable” result. Iterate internally through:

```text
reproduce -> repair -> focused tests -> integration tests -> adversarial audit -> repair again -> full gates
```

until every required acceptance criterion passes or a genuinely external, non-repository blocker makes completion impossible.

## 0. Output discipline

Do not emit chain-of-thought narration such as:

```text
I am currently examining...
I am now focusing on...
I am investigating...
```

Work silently between checkpoints. User-visible updates, if any, must be concise factual receipts containing only:

- checkpoint name;
- defects reproduced;
- files changed;
- commands executed;
- real exit codes;
- remaining blocker IDs.

The final response must use the machine-readable receipt defined in this prompt.

## 1. Immutable source and failed-run handoff

Expected reviewed source:

```text
REPO=/Users/mkoziol/projects/bet
BASE_SHA=fca79bfe9ca7690905f859a445a067d66b2b2520
REVIEWED_HEAD=0037b9faa63d069b668c70d48086d79bf7d94386
REVIEWED_TREE=c25545f101a1df8d8896a753db0cb188afdd5f09
REVIEWED_SOURCE_MANIFEST_SHA256=16f45227d15b41937a9f67104d302b0c22021173a02f45540a53e90ed1957e93
SOURCE_BUNDLE=/tmp/bet_pipeline_v5_final.bundle
SOURCE_BUNDLE_SHA256=63c0f2de60bf3cfba57449a680ae8e418a90c5ab8649df598137c7c98eb34681
```

Failed production-path analysis evidence:

```text
BETTING_DAY=2026-07-29
TIMEZONE=Europe/Warsaw
FAILED_RUN_ID=v5_analysis_20260729_002
FAILED_RUN_ROOT=/private/tmp/pipeline_runs/2026-07-29/v5_analysis_20260729_002
FAILED_REVIEW_PACKAGE=/tmp/bet_analysis_20260729_v5_analysis_20260729_002.tar.gz
FAILED_REVIEW_PACKAGE_SHA256=02f8a0e15f74849cf2f51b9063be620f9ddbe1966921dab30ee85fcf3497692c
FAILED_AT_STEP=S2.5
```

Correct event counts — do not repeat the previous inaccurate wording:

```text
S1_RAW_DISCOVERY_COUNT=998
S1_AFTER_PROVIDER_DEDUP_COUNT=914
S1_MARKET_MATRIX_COUNT=766
S1E_CANONICAL_UNIVERSE_COUNT=766
S2_EVENT_RECORD_COUNT=766
S2_3_EVENT_RECORD_COUNT=766
S2_5_SHARD_COUNT=52
```

`914` is not the S1e universe passed to the sharded agent steps. The actual S1e/S2 scope is `766` events.

Known source artifact hashes from the failed review package:

```text
FAILED_S0_ARTIFACT_SHA256=877d79cf3e973cae3e63abfc82c53579bf5f3da833cd22109c6bf99ff5e4232f
FAILED_S1_ARTIFACT_SHA256=e6cfa6b690857dc2d9909a91b2cd2c9e154b71a54f538f7f691e63222d722c97
FAILED_S1E_WRAPPER_ARTIFACT_SHA256=fc18b715aaf55b6daa26f88a2a72f59374995bf6b700a6e1584eec617c05222e
FAILED_S1E_DATA_SHA256=8ea10d69eaf9bd6b88adc99a3bae2b5416f76fd9c4731f4e8b0d86dedeb7c14a
FAILED_S2_ARTIFACT_SHA256=fdb5e93263addaf35a57f3d336cc2c79eda983d1cf0866d0160d6bd3ddebd8da
FAILED_S2_3_ARTIFACT_SHA256=3b154038e0af415ec4d52ae0d427b842631aceb75590bcb49302af54d7749a20
FAILED_S2_5_INVALID_ARTIFACT_SHA256=4549d72ff177672cf5c434b04f95372d129dc51b758c5e5027137b3ee0482e98
```

The old S2, S2.3, S2.5 work orders, chunks, ledgers and aggregates are evidence only. They are not reusable production inputs after the repair.

Create exactly this branch from the reviewed HEAD:

```text
fix/bet-v5-complete-closure-s2-restart-v3
```

Fail closed before editing if HEAD/tree or the reviewed source-manifest binding differs, or if the initial worktree contains unexplained source changes.

## 2. Non-negotiable safety rules

You MUST NOT:

- run `run_daily_pipeline.py` with `--allow-live-network` during this engineering session;
- resume or mutate `v5_analysis_20260729_002` in place;
- reuse the same run ID across a changed source HEAD/tree/manifest;
- rewrite original source-run artifacts to pretend they were produced by the repaired revision;
- reuse failed-run S2 or downstream outputs in the next analysis run;
- hardcode `PASS`, `READY`, `LOW`, `HOME`, `ACCEPTED`, default market, selection, probability, pricing readiness, empty unknowns, empty blockers or `source_bound=true` when evidence does not prove them;
- use synthetic provenance such as repeated `a`, `b`, `c`, hash-of-ID, `UNKNOWN`, or `/tmp/chunk.json` fallback paths;
- accept length-only hash validation as source binding;
- accept a chunk whose complete immutable binding differs from its work order, plan or run context;
- aggregate BLOCK, FAILED, UNKNOWN, incomplete, conflicted, source-unbound or requirement-unsatisfied input into parent PASS/READY;
- make S2.5 pass by merely adding an empty `provider_observations`, `observations`, or `source_observations` field;
- manually write the final chunk artifact or parent aggregate in the production-path E2E test;
- permit test/demo model packages to influence production resolution;
- approve pricing without a real fitted model artifact and verified package lineage;
- multiply correlated same-event marginal probabilities without an approved joint model or explicit approved independence protocol;
- mark a quality gate PASS without an immutable command receipt for the exact executed command;
- weaken pricing fail-closed, S9 human-only, event-accounting, source-binding or operator-manual boundaries;
- modify tests only to mirror an unsafe implementation;
- merge to `main` automatically.

Every behavior change must begin with a regression test that fails on `REVIEWED_HEAD` and passes after the fix. Save the red-test output before implementation.

## 3. Single-session completion contract

This prompt replaces both earlier prompts. Do not execute either the old analysis prompt or the focused reducer-only V2 prompt.

The session is successful only when all of the following are true in the same run:

```text
P0_FIXED=10/10
P1_FIXED=10/10
RUNTIME_S2_5_REGRESSION_FIXED=true
SAFE_S2_RESTART_PATH_IMPLEMENTED=true
INTERNAL_INDEPENDENT_AUDIT=PASS
UNRESOLVED_P0=0
UNRESOLVED_P1=0
READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION=YES
```

A focused repair with remaining audit findings is not a successful outcome.

Use an internal repair loop. After the first implementation pass, invoke a read-only independent verifier using `code-reviewer-local`, `bet-auditor`, or an equivalent separate verifier context. The verifier must attempt the old exploits. If it finds any issue, return to implementation within this same session, repair it, rerun affected gates, and audit again.

## 3A. Authoritative finding ledger

The following findings are individually mandatory. A category-level change does not count unless the exact finding has a red test, repair, green test and independent exploit attempt.

### P0 ledger

```text
P0-01  DummyStepModel remains in the production S0-S10 contract registry.
P0-02  Migration adapters fabricate market/selection/risk/status decisions.
P0-03  Chunk models auto-populate synthetic provenance and output paths.
P0-04  Chunk artifact validation omits immutable work-order/run bindings.
P0-05  Sharding lifecycle fabricates provenance when resolution fails.
P0-06  Generic shard aggregation hardcodes business PASS/source_bound/empty gaps.
P0-07  Chunk work-order schema is incompatible with the canonical agent executor.
P0-08  Ignored test model package without fitted model is pricing-eligible and can unlock S8.
P0-09  Quality receipt generator hardcodes gates as PASS and stores paths as hashes.
P0-10  Source provenance helpers return synthetic values instead of failing closed.
```

### P1 ledger

```text
P1-01  Acquisition plans are generic placeholders, not per event/sport/market.
P1-02  Tool-governance intersection is defined but not enforced in production execution.
P1-03  Strict step validation has identity fallbacks and optional S1e universe enforcement.
P1-04  Decision-bearing nested structures remain untyped dict[str, Any].
P1-05  Sport dossier readiness can rely on Home/Away/ALL placeholder identities.
P1-06  Unsupported market family can become ready for pricing.
P1-07  Model resolvers suppress distinct failures into unauditable None.
P1-08  Joint-model/builder scope and correlation binding is incomplete.
P1-09  S8 status semantics are inconsistent and promoted joint-model path is incomplete.
P1-10  Acceptance/mutation proof does not exercise the reproduced production exploits.
```

### Additional production-path closure items

```text
RUNTIME-01  S2.5 sharded parent artifact uses the S2.3 payload shape and fails validation.
RESTART-01  A changed revision cannot safely continue the old run; a lineage-preserving S2 fork is required.
```

The final finding matrix must contain exactly these 22 IDs. No ID may be marked fixed solely because another broader checkpoint passed.

## 4. R0 — provenance, baseline and evidence inventory

Before editing:

1. Verify:
   - `pwd`;
   - clean worktree;
   - exact HEAD and tree;
   - ancestry from `BASE_SHA`;
   - source-manifest hash;
   - source bundle SHA and `git bundle verify`;
   - failed review-package SHA and archive integrity.
2. Create the repair branch.
3. Record repository-defined commands for format, lint, typecheck, focused tests, pipeline tests, full suite, validators, offline E2E, acceptance, mutation and certification. Discover commands from project configuration; do not invent them.
4. Run a bounded baseline and save actual failures. Do not trust old `38/38` as proof of the missing exploit coverage.
5. Inventory ignored/untracked runtime-affecting state under:
   - `models/`;
   - run roots;
   - report roots;
   - `.kilo`;
   - caches and temporary registries.
6. Detect and quarantine `models/store/test_pkg_t4`, `TEST_PROMOTED_001`, and any test/demo package that production resolution could see.
7. Verify the failed run root without modifying it. Recompute hashes of S0, S1, S1e and the transitive S1/S1e data dependencies.
8. Build `/tmp/bet_v5_closure_v3/finding_matrix.json` mapping every `P0-01..P0-10`, `P1-01..P1-10`, `RUNTIME-01`, and `RESTART-01` to:
   - source location;
   - red test;
   - intended repair;
   - post-fix test;
   - final status.

Do not proceed with an incomplete finding matrix.

## 5. R1 — authentic fail-closed provenance

Repair `src/bet/pipeline/receipts.py`, sharding lifecycle/model callers, work-order builders, artifact publishers and all dependent code.

Requirements:

- Git HEAD, tree and source-manifest resolution return authentic values or raise typed `ProvenanceResolutionError` with stable codes;
- exact lowercase-hex format and expected equality are required;
- no synthetic fallback is permitted;
- parent and chunk work-order hashes are SHA-256 of canonical persisted bytes;
- artifact hashes are recomputed from canonical bytes, not trusted from input fields;
- provenance resolution completes before any output is persisted;
- failure leaves no partial work order, plan, chunk, artifact, ledger transition or parent aggregate;
- errors preserve auditable cause classification without secrets;
- path normalization rejects symlinks, path escape and parent/output aliasing.

Required red/green tests:

- outside Git repository;
- Git binary/command failure;
- missing or malformed source manifest;
- permission/read failure;
- wrong expected HEAD/tree/manifest;
- invalid hex and uppercase/noncanonical hash;
- source file changes between hash and publish;
- no output after every failure;
- static guard proving magic provenance placeholders are absent from production paths.

## 6. R2 — real typed contracts S0–S10 and fail-closed migration

Remove `DummyStepModel` from the production registry.

Create concrete, versioned models for every registered contract from S0 through S10, including S1e, S2.3, S2.5, S2.7, S2.9 and S7b.

Requirements:

- decision-bearing nested records use explicit models, enums/Literal and constrained types;
- hashes, probabilities, odds, timestamps, IDs, status, market semantics, evidence refs, source refs and correlation classes are typed;
- `dict[str, Any]` is not permitted for decision-bearing structures;
- success-like status semantics are explicit per step;
- `READY` cannot bypass semantic validation because code checks only `status == "PASS"`;
- event membership is exact against a required S1e input; missing/unreadable S1e is BLOCK, not optional validation;
- top-level positive status cannot be inherited by an event record missing its own required status.

Migration rules:

- map only semantically equivalent values actually present in source input;
- missing decision-bearing data raises `MigrationAdapterError` or yields an explicit typed BLOCK/UNKNOWN object only where the contract allows it;
- never fabricate market, selection, side, probability, uncertainty, model ID, fair odds, minimum odds, motivation, risk, repeat decision or PASS/READY;
- document supported legacy aliases and reject all others;
- remove debug prints and silent coercions.

Required exploit regressions include:

- sparse S3 cannot become `result/1/PASS`;
- sparse S4 cannot become `RESULT/HOME/PASS`;
- sparse S5 cannot become `football/1.0/LOW/PASS`;
- sparse S6 cannot become `HOME/ACCEPTED/PASS`;
- missing S1e cannot disable exact event-universe validation;
- malformed nested evidence/market records fail with stable codes;
- every registry entry resolves to a real model class;
- valid representative production artifact for every step validates.

## 7. R3 — one executable work-order and chunk execution schema

Unify regular and chunk work orders under a canonical compatible execution schema, or provide a typed adapter that loses no binding information.

Every chunk execution contract must contain:

- pipeline ID, run ID, betting day, step ID, runtime mode;
- parent work-order ID and canonical SHA;
- chunk work-order ID and canonical SHA;
- plan ID and canonical SHA;
- producer agent ID;
- exact chunk index and total chunks;
- attempt number and attempt ID;
- immutable input refs and acquisition-plan refs with hashes;
- exact event IDs;
- exact unique normalized output path;
- exact artifact type and allowed statuses;
- source HEAD/tree/manifest;
- hard rules, forbidden outputs and instructions.

The canonical loader and renderer must consume the actual serialized schema. A valid `ChunkWorkOrderV1` must not be rejected for missing unrelated regular-work-order keys.

The executor must:

- render a real prompt/request through the same production interface;
- write atomically to `artifacts/chunks/<chunk_id>.json` or the canonical equivalent;
- validate the artifact before transitioning the ledger;
- never reuse the parent artifact path for a chunk;
- distinguish missing, malformed, foreign, blocked and stale chunk outputs.

Required real-path offline E2E:

```text
parent work order
-> acquisition plan
-> chunk plan
-> canonical chunk work order serialization
-> canonical prompt renderer
-> deterministic local agent adapter through production execution interface
-> atomic chunk artifact publish
-> complete binding validation
-> ledger transition
-> step-specific semantic reducer
-> parent contract validation
-> atomic parent publish
```

The test body may configure the deterministic local adapter, but may not directly write the expected final chunk JSON or parent aggregate.

## 8. R4 — complete chunk binding, ledger and resume correctness

Remove every model validator that auto-populates provenance.

`validate_chunk_against_work_order` must compare and independently test mutations for:

- chunk ID;
- parent work-order ID and SHA;
- chunk work-order ID and SHA;
- parent plan ID and SHA;
- producer agent ID;
- betting day;
- run ID;
- runtime mode;
- source HEAD;
- source tree;
- source manifest;
- chunk index;
- total chunks;
- attempt number;
- attempt ID;
- artifact type;
- exact normalized expected path;
- allowed status;
- exact event set;
- input refs and acquisition-plan bindings;
- recomputed artifact SHA;
- point-in-time/retrieval timestamp where contractually required.

The exact former exploit must fail:

```text
producer_agent_id=evil-agent
betting_day=2099-01-01
run_id=foreign-run
chunk_index=999
total_chunks=99
```

Each mismatch requires a stable distinct error code.

Ledger requirements:

- explicit legal state machine;
- atomic compare-and-set or equivalent single-writer safety;
- immutable attempt history;
- successful chunks are not rerun;
- only retryable failed/incomplete states can resume;
- corrupt ledger blocks instead of resetting;
- unresolved command requests cannot be bypassed by starting a downstream step;
- a changed source HEAD/tree/manifest cannot resume the same run ID;
- failed or incomplete chunk can never be hidden by aggregate success.

## 9. R5 — contract-aware reducers for every sharded step

Replace the generic aggregate in `_handle_sharded_agent_step` with a typed reducer registry. The orchestrator coordinates; it does not invent business semantics.

The registry must cover every current manifest step that can shard:

```text
S2.3 enrichment_gap_detection
S2.5 provider_enrichment
S2.7 source_reconciliation
S2.9 data_readiness_gate
S5 context_motivation_risk
```

Universal reducer rules:

- validate every chunk before reduction;
- exact disjoint event cover is mandatory but not sufficient;
- preserve all event records and explicit terminal statuses;
- preserve source refs, evidence refs, retrieval timestamps, receipts, warnings, unknowns, conflicts and blocked reasons;
- derive source binding and status;
- use an explicit fail-closed status lattice;
- a required BLOCK/FAILED/UNKNOWN/incomplete/conflict/unbound input prevents PASS/READY;
- verify acquisition requirement satisfaction;
- deduplicate evidence without treating mirrors/copied claims as independent;
- bind parent artifact to exact plan/work-order/chunk hashes and source/run provenance;
- validate the final parent artifact before atomic publication;
- leave no partial parent artifact after failure;
- emit stable reduction error codes.

Step-specific requirements:

### S2.3

- aggregate actual gap/enrichment-gap records;
- derive bounded/blocking state from chunk evidence;
- preserve unknowns and blockers;
- required blocking gaps prevent PASS.

### S2.5

- aggregate actual provider/source observations;
- preserve provider, event, retrieval time, evidence/source binding, normalized facts and success/degraded/failure status;
- missing required provider evidence prevents PASS;
- empty required observation arrays do not satisfy the contract;
- structurally support 766 events split into 52 chunks;
- reproduce and close `S2_5_SHARD_AGGREGATION_PAYLOAD_SCHEMA_MISMATCH` through the real orchestrator path.

### S2.7

- preserve disputed facts and reconciliation records;
- preserve non-empty evidence refs for positive status;
- conflicting claims remain visible;
- unresolved required conflict prevents PASS.

### S2.9

- derive readiness from exact bound S2.3/S2.5/S2.7 artifacts;
- make PASS/READY vocabulary consistent across manifest, typed contract, validator and orchestrator;
- run semantic validation for every success-like status;
- derive `s3_may_proceed` from predecessor completeness;
- any predecessor BLOCK/UNKNOWN/conflict/binding failure prevents READY;
- add a regression proving `status=READY` cannot bypass validation.

### S5

- preserve evidence-bound injury/lineup, motivation/tournament, travel/fatigue, morale/form and upset/volatility context;
- preserve candidate and rejected-candidate accounting;
- any unaccounted required candidate prevents PASS;
- never reuse S2.3 payload fields.

Required reducer tests:

- success and blocking cases for every reducer;
- one failed chunk blocks each reducer;
- one source-unbound chunk blocks;
- duplicate or foreign event blocks;
- corrupt existing chunk reports corruption, not waiting;
- parent file absent after validation failure;
- deterministic replay is byte-identical for identical inputs;
- `>15` events activates sharding and `<=15` keeps non-sharded execution;
- a generated 766-event scope creates 52 chunks and a valid deterministic aggregate without live network;
- resume does not rerun valid completed chunks;
- real orchestrator output validates for every supported sharded step.

## 10. R6 — semantic acquisition plans, tool governance and sport dossiers

Repair acquisition planning so it is per canonical event, sport and requested market family.

Requirements:

- no default event ID, default football sport, generic `ALL`, `Home`, `Away` or all-market requirement;
- exact S1e identity, competition, participants and start time are required;
- requirements derive from sport protocol and market family;
- allowed tools equal the intersection of agent profile, manifest policy and requirement policy on the production path, not only in tests;
- query/retrieval budgets are bounded and auditable;
- source independence, freshness and conflict policy are explicit;
- missing required facts produce BLOCK/UNKNOWN;
- unsupported sport/market is `NOT_SUPPORTED/BLOCK`, never pricing-ready;
- sport dossier readiness cannot be based on placeholder identities;
- every discovered event has explicit accounting and terminal status/reason.

Add positive and unsupported-market cases for:

```text
football
tennis
basketball
volleyball
hockey
CS2
Dota 2
Valorant
```

Add a production-path test proving tool governance is enforced when building and executing work orders.

## 11. R7 — model-package governance and S8 pricing fail-closed

Repair `ModelPackageResolver`, joint resolver, model registry and S8 binding.

A pricing-eligible package must include and validate:

- typed package metadata;
- real fitted model file;
- exact fitted model SHA-256;
- dataset receipt schema/hash;
- feature schema schema/hash;
- code receipt schema/hash and source HEAD/tree binding;
- temporal split schema/hash;
- backtest schema/hash with sample-size and temporal-order policy;
- calibration schema/hash;
- uncertainty-method schema/hash;
- model card schema/hash;
- promotion decision schema/hash;
- immutable promotion authority/registry entry;
- consistent package ID, sport, competition, market and scope across files;
- approved immutable store;
- no symlink/path escape;
- explicit contamination classification excluding test/demo packages.

Define a canonical package manifest hash without trusting an arbitrary self-hash field.

Resolver behavior:

- return a typed status and stable rejection reason;
- do not collapse malformed JSON, IO error, provenance conflict and scope mismatch into silent `None`;
- production resolution cannot inspect repository-local ignored test state;
- tests use `tmp_path`/isolated stores and leave no production-visible state.

Required exploit tests:

- former `TEST_PROMOTED_001` package is blocked;
- text files with matching hashes are rejected;
- missing fitted file is rejected;
- fake fitted hash is rejected;
- altered file is rejected;
- foreign/stale scope is rejected;
- package outside approved store is rejected;
- running tests leaves no production-visible package;
- startup contamination scan blocks test/demo packages.

S8 requirements:

- consume the already-resolved typed package bound to the exact estimate/card;
- reverify scope, hashes and prediction timestamp;
- no arbitrary path-string re-resolution;
- no verified fitted package means analysis-only blocked/manual-research status, not pricing-ready;
- `UNPRICED` cannot simultaneously mean ready for priced coupon execution;
- no current manual operator quote means no EV, stake, combined operator odds or executable coupon;
- S9 remains external human-only.

## 12. R8 — joint-model and Bet Builder correctness

Requirements:

- correlated same-event legs require a promoted calibrated scope-bound joint model;
- marginal probabilities cannot be multiplied merely because metadata says `assumes_independence=true`;
- an approved independence protocol, where supported, must be separate, versioned and scope-bound;
- type all legs, event scopes, market periods, regulation/overtime semantics, correlation classes and model bindings;
- reject duplicate legs, contradictory lines, mixed event scope, mixed competition scope, stale quote scope and same-market double counting;
- candidate groups remain non-executable and unpriced until current human-entered operator quotes are supplied;
- resolve S8 status vocabulary into explicit analysis-only, awaiting-quote, priced-review and blocked states.

Test correlated markets, duplicates, contradictions, regulation/overtime mismatch, missing joint model and foreign scope.

## 13. R9 — truthful receipts, certification and mutation coverage

Replace hardcoded quality statuses with immutable command receipts.

Every required gate receipt contains:

```text
gate_id
head_sha
tree_sha
source_manifest_sha256
command_argv
cwd
environment_fingerprint_without_secrets
started_at
finished_at
exit_code
stdout_path
stdout_sha256
stderr_path
stderr_sha256
artifact_paths_and_sha256
status
```

Rules:

- missing receipt is `NOT_RUN/BLOCK`;
- a file path is never a SHA-256;
- final report recomputes receipt and artifact hashes;
- mixed HEAD/tree/manifest receipts are rejected;
- no PASS field is accepted as an unverified literal;
- command exit status must be the real process/pipeline status, not merely `tee`;
- each mutation has a bounded timeout and independent logs;
- the external acceptance harness is copied outside the target worktree or pinned by an independently recorded hash before execution.

Expand acceptance and mutation coverage to include every P0 exploit, all P1 behaviors, the concrete S2.5 runtime regression and the safe S2 restart mechanism.

## 14. R10 — safe forked restart from S2 using the failed run

The repaired code will have a different HEAD/tree/manifest. Therefore, do not resume `v5_analysis_20260729_002` in place.

Implement a canonical **forked run seed/import** mechanism for a new run ID. Use repository conventions, but the user-facing CLI must support an equivalent of:

```text
--source-run-root <absolute source run root>
--reuse-through-step S1e
--start-step S2
```

A separate preparation command is acceptable, but the final handoff must provide one exact copy-ready sequence.

The source seed may reuse only validated information through S1e:

- S0 artifact where relevant;
- S1 artifact;
- S1 market matrix and shortlist inputs required to reconstruct S2 state;
- S1e wrapper artifact;
- S1e event-universe data;
- event-accounting initialization required by downstream gates;
- deterministic normalized data needed to reconstruct run-scoped DB state.

Do not blindly copy a mutable SQLite database when a deterministic artifact-based reconstruction is possible. When a DB snapshot is unavoidable, bind schema version and file hash and validate it before import.

Do not reuse:

- S2 artifact;
- S2.3/S2.5 artifacts;
- any old chunk work order/artifact;
- old acquisition plans;
- old shard ledger;
- old resume ledger entries for S2+;
- any S3+ output.

Create typed import/seed receipts that preserve both:

```text
source_run_id/source_head/source_tree/source_manifest/source_artifact_hashes
and
target_run_id/target_head/target_tree/target_manifest/import_receipt_hash
```

Do not rewrite old artifact provenance. A target artifact derived from source evidence must explicitly identify itself as imported/derived evidence and retain exact source hashes.

The seed exporter must traverse the transitive file/input references required by S2 rather than packaging only wrapper JSONs. This is necessary because the failed review archive does not by itself prove inclusion of every referenced S1/S1e data file.

Create and verify:

```text
/tmp/bet_v5_20260729_s2_restart_seed_v3.tar.gz
/tmp/bet_v5_20260729_s2_restart_seed_v3_manifest.json
```

The seed manifest must include:

- source run root and run ID;
- source HEAD/tree/manifest;
- source run-as-of time;
- all included relative paths and SHA-256 hashes;
- exact event counts at each stage;
- S1e event IDs hash;
- explicit exclusion list for S2+;
- schema versions;
- import compatibility version;
- verification result.

### Freshness and event-time revalidation

Because the next session starts later than discovery, S2 entry must revalidate each of the 766 S1e events against the new target `run_as_of_utc` and repository lead-time policy.

Events that already started, were cancelled/postponed, changed identity, or no longer have sufficient lead time must receive explicit terminal statuses/reasons. They must not be silently dropped.

At minimum support stable reasons equivalent to:

```text
STARTED_BEFORE_RESTART
INSUFFICIENT_LEAD_TIME
FIXTURE_CANCELLED_OR_POSTPONED
FIXTURE_IDENTITY_CHANGED
SOURCE_EVENT_STALE
```

The exact repository vocabulary may differ, but semantics must be explicit and typed.

S2 and all downstream acquisition/enrichment/reconciliation/context evidence must run fresh in the next live session.

### Restart tests

Add deterministic offline tests proving:

1. same run ID cannot resume after source revision changes;
2. source run remains byte-identical after seed export;
3. seed import verifies every hash and rejects tampering/missing transitive input;
4. target run receives explicit source lineage without rewritten provenance;
5. only through-S1e state is reusable;
6. old S2+ artifacts/chunks/ledgers are ignored or rejected;
7. target `--start-step S2` passes prerequisite gates using the imported seed;
8. stale/started events are terminalized, not dropped;
9. exact event accounting remains complete;
10. offline execution from imported S1e through at least S2.9 succeeds through the real orchestration path;
11. a 766-event structural replay creates 52 S2.x chunks where applicable;
12. repeated seed import is idempotent or fails with a stable conflict code, never partially overwrites.

Do not run live network as part of these tests.

## 15. R11 — complete gates in the repaired worktree

Install/synchronize dependencies using the repository lockfile and declared package manager. Do not edit dependency declarations merely to bypass a missing local package.

Run and record the exact repository-defined commands for:

1. `git diff --check`;
2. format check;
3. lint;
4. typecheck;
5. focused tests for every finding;
6. all V5 contract tests;
7. sharding/reducer tests;
8. acquisition/sport dossier tests;
9. model governance and S8 tests;
10. restart-seed tests;
11. all pipeline tests;
12. full test suite;
13. validators;
14. offline end-to-end;
15. external acceptance;
16. expanded mutation/exploit proof;
17. certification;
18. compile/build checks.

No live betting-day pipeline is allowed during repair certification.

After tests, verify:

```text
NO_IGNORED_MODEL_CONTAMINATION=true
NO_MAGIC_PROVENANCE_PLACEHOLDERS=true
NO_DUMMY_PRODUCTION_CONTRACTS=true
NO_HARDCODED_QUALITY_PASS=true
NO_GENERIC_SHARDED_PARENT_PAYLOAD=true
NO_MANUAL_CHUNK_ARTIFACT_IN_REAL_PATH_E2E=true
NO_REUSED_S2_PLUS_STATE_IN_RESTART_SEED=true
```

## 16. R12 — standalone clone and internal independent adversarial audit

Commit the implementation in logically reviewable commits.

Create a fresh standalone clone from the repair branch without repo-local ignored state. In that clone:

- install/synchronize dependencies from the lockfile;
- verify exact HEAD/tree/source manifest;
- rerun all required tests and certification;
- import a copy of the S2 restart seed into an isolated temporary run root;
- run the deterministic offline start-from-S2 proof;
- execute the complete exploit matrix.

Delegate a read-only audit to a separate verifier context. It must inspect the diff and independently attempt, at minimum:

- sparse migration fabrication;
- synthetic provenance fallback;
- foreign chunk producer/run/day/index/total;
- work-order schema incompatibility;
- BLOCK/UNKNOWN chunk aggregated to PASS;
- S2.5 generic S2.3 payload regression;
- S2.9 READY validation bypass;
- test model package without fitted model;
- ignored model contamination;
- hardcoded quality PASS;
- unsupported market pricing readiness;
- joint-model/independence bypass;
- changed-revision same-run resume;
- tampered S2 restart seed;
- accidental reuse of old S2+ artifacts.

If the verifier finds any issue, do not finish. Repair it in the original branch, rerun affected and full gates, update the standalone clone, and audit again in this same session.

Only the final read-only audit iteration may set `INTERNAL_INDEPENDENT_AUDIT=PASS`.

## 17. Git, bundle and deliverables

Do not merge to main.

Push the branch if remote permission is available. If push is denied, preserve a complete standalone bundle; remote denial alone does not invalidate local engineering readiness when all local proofs pass.

Create:

```text
/tmp/bet_v5_complete_closure_v3/
  provenance_before.txt
  provenance_after.txt
  finding_matrix.json
  changed_files.txt
  full_diff.patch
  red_tests/
  green_tests/
  command_receipts/
  contract_registry_inventory.json
  migration_matrix.json
  chunk_binding_matrix.json
  reducer_matrix.json
  acquisition_plan_matrix.json
  sport_dossier_matrix.json
  model_package_matrix.json
  s8_joint_builder_matrix.json
  restart_seed_manifest.json
  restart_seed_verification.json
  standalone_clone_receipt.json
  independent_audit.md
  next_analysis_handoff.json
  next_bet_executor_analysis_prompt.md
  final_report.json
  SHA256SUMS
```

Create and verify the Git bundle:

```text
/tmp/bet_pipeline_v5_complete_closure_v3.bundle
```

The bundle must include the repair branch and all prerequisite refs required for standalone clone.

Verify:

- `git bundle verify`;
- exact branch ref;
- standalone clone from the bundle;
- complete test/certification rerun in standalone clone;
- bundle SHA-256;
- review-package archive SHA-256;
- restart-seed archive SHA-256.

Also archive the review directory:

```text
/tmp/bet_v5_complete_closure_v3.tar.gz
```

## 18. Exact next full-analysis handoff

When and only when all code, gates, standalone proof and internal independent audit pass, create a unique target run ID that does not already exist. Prefer:

```text
v5_analysis_20260729_003
```

only when that run ID is unused; otherwise increment safely.

Generate `/tmp/bet_v5_complete_closure_v3/next_analysis_handoff.json` containing:

```text
BETTING_DAY=2026-07-29
TIMEZONE=Europe/Warsaw
SOURCE_RUN_ID=v5_analysis_20260729_002
SOURCE_RUN_ROOT=/private/tmp/pipeline_runs/2026-07-29/v5_analysis_20260729_002
REUSE_THROUGH_STEP=S1e
START_STEP=S2
TARGET_RUN_ID=<unique>
TARGET_HEAD=<HEAD_AFTER>
TARGET_TREE=<TREE_AFTER>
TARGET_SOURCE_MANIFEST=<manifest after repair>
S1_RAW_DISCOVERY_COUNT=998
S1_AFTER_PROVIDER_DEDUP_COUNT=914
S1E_IMPORTED_EVENT_COUNT=766
S2_PLUS_REUSED=false
FRESHNESS_REVALIDATION_REQUIRED=true
PRICING_FAIL_CLOSED=true
S9_HUMAN_ONLY=true
```

Include an exact copy-ready command sequence that first checks out/verifies `HEAD_AFTER`, verifies a clean worktree, prepares/imports the seed into the new target run, and then invokes the canonical runner. The sequence must not depend on an implicit current branch or current working directory.

Also generate:

```text
/tmp/bet_v5_complete_closure_v3/next_bet_executor_analysis_prompt.md
```

That generated prompt must be fully concrete: exact repaired HEAD/tree/manifest, source and target run IDs, seed path/hash, import command, start-at-S2 command, model/runtime smoke proof, analysis-only S8, pricing fail-closed, S9 human-only, freshness revalidation and final manual-pricing handoff. It must not contain unresolved placeholders other than live operator quotes that are intentionally unavailable.

Before generating the live command, check whether the betting-day window `2026-07-29 06:00:00` through `2026-07-30 05:59:59 Europe/Warsaw` is still active. When it is no longer active, do not generate or recommend a stale S2 live run. Preserve the seed as evidence, set `BETTING_DAY_WINDOW_ACTIVE_AT_HANDOFF=false`, and make the next action a new-day discovery run instead. Code readiness may still be PASS, but the stale betting-day command must be `NONE`.

When the window is active, include an exact copy-ready command sequence using the implemented canonical seed/import interface and then:

```text
scripts/pipeline_steps/run_daily_pipeline.py
--date 2026-07-29
--run-id <TARGET_RUN_ID>
--runtime-mode LIVE_SHADOW
--start-step S2
--base-run-dir /private/tmp/pipeline_runs
--allow-live-network
--verbose
```

Do not execute the live command in this engineering session.

The next session must rerun S2, S2.3, S2.5, S2.7, S2.9 and all downstream steps fresh. It may reuse only the verified through-S1e seed.

## 19. Final machine-readable receipt

Return exactly one final receipt followed by a concise human summary:

```text
CHECKPOINT=BET_V5_COMPLETE_CLOSURE_AND_S2_RESTART_V3
STATUS=PASS|BLOCKED
DECISION=READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION|BLOCKED_ENGINEERING_REPAIR_REQUIRED

BRANCH=fix/bet-v5-complete-closure-s2-restart-v3
HEAD_BEFORE=0037b9faa63d069b668c70d48086d79bf7d94386
TREE_BEFORE=c25545f101a1df8d8896a753db0cb188afdd5f09
HEAD_AFTER=<sha>
TREE_AFTER=<sha>
SOURCE_MANIFEST_AFTER=<sha256>
WORKTREE_CLEAN=<true|false>

P0_FIXED=<0..10>
P1_FIXED=<0..10>
UNRESOLVED_P0=<count>
UNRESOLVED_P1=<count>
RUNTIME_S2_5_REGRESSION=<PASS|FAIL>

PROVENANCE_FAIL_CLOSED=<PASS|FAIL>
REAL_TYPED_CONTRACTS_S0_S10=<PASS|FAIL>
MIGRATION_NO_DECISION_DEFAULTS=<PASS|FAIL>
CHUNK_EXECUTION_SCHEMA=<PASS|FAIL>
CHUNK_FULL_BINDING=<PASS|FAIL>
CHUNK_LEDGER_RESUME=<PASS|FAIL>
S2_3_REDUCER=<PASS|FAIL>
S2_5_REDUCER=<PASS|FAIL>
S2_7_REDUCER=<PASS|FAIL>
S2_9_REDUCER=<PASS|FAIL>
S5_REDUCER=<PASS|FAIL>
SUCCESS_STATUS_SEMANTICS=<PASS|FAIL>
ACQUISITION_PLANS_PER_EVENT_MARKET=<PASS|FAIL>
TOOL_GOVERNANCE_RUNTIME_ENFORCED=<PASS|FAIL>
SPORT_DOSSIER_IDENTITY=<PASS|FAIL>
UNSUPPORTED_MARKET_FAIL_CLOSED=<PASS|FAIL>
MODEL_PACKAGE_FITTED_ARTIFACT_REQUIRED=<PASS|FAIL>
IGNORED_MODEL_CONTAMINATION_BLOCKED=<PASS|FAIL>
S8_PRICING_FAIL_CLOSED=<PASS|FAIL>
JOINT_MODEL_CORRELATION_GOVERNANCE=<PASS|FAIL>
S9_HUMAN_ONLY=<PASS|FAIL>
QUALITY_RECEIPTS_TRUTHFUL=<PASS|FAIL>

SAFE_FORKED_RUN_IMPORT=<PASS|FAIL>
SOURCE_RUN_UNCHANGED=<PASS|FAIL>
RESTART_SEED_VERIFY=<PASS|FAIL>
RESTART_SEED_EVENT_COUNT=<count>
RESTART_REUSES_THROUGH_STEP=S1e|NONE
RESTART_REUSES_S2_PLUS=false
EVENT_FRESHNESS_REVALIDATION=<PASS|FAIL>
OFFLINE_START_FROM_S2_E2E=<PASS|FAIL>

FORMAT=<PASS|FAIL>
LINT=<PASS|FAIL>
TYPECHECK=<PASS|FAIL>
FOCUSED_TESTS=<PASS|FAIL>
PIPELINE_TESTS=<PASS|FAIL>
FULL_SUITE=<PASS|FAIL>
VALIDATORS=<PASS|FAIL>
OFFLINE_E2E=<PASS|FAIL>
EXTERNAL_ACCEPTANCE=<PASS|FAIL>
EXPANDED_MUTATION_PROOF=<PASS|FAIL>
EXPLOIT_REGRESSION_SUITE=<PASS|FAIL>
CERTIFICATION=<PASS|FAIL>
STANDALONE_CLONE_PROOF=<PASS|FAIL>
INTERNAL_INDEPENDENT_AUDIT=<PASS|FAIL>

REMOTE_BRANCH_HEAD=<sha|NOT_PUSHED>
PR_NUMBER=<number|NONE>
PR_URL=<url|NONE>
REVIEW_BUNDLE_PATH=/tmp/bet_pipeline_v5_complete_closure_v3.bundle
REVIEW_BUNDLE_SHA256=<sha256>
REVIEW_PACKAGE_PATH=/tmp/bet_v5_complete_closure_v3.tar.gz
REVIEW_PACKAGE_SHA256=<sha256>
S2_RESTART_SEED_PATH=/tmp/bet_v5_20260729_s2_restart_seed_v3.tar.gz
S2_RESTART_SEED_SHA256=<sha256>
NEXT_ANALYSIS_HANDOFF_PATH=/tmp/bet_v5_complete_closure_v3/next_analysis_handoff.json
NEXT_BET_EXECUTOR_PROMPT_PATH=/tmp/bet_v5_complete_closure_v3/next_bet_executor_analysis_prompt.md
BETTING_DAY_WINDOW_ACTIVE_AT_HANDOFF=<true|false>
NEXT_ANALYSIS_COMMAND=<exact copy-ready command or NONE>

READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION=<YES|NO>
READY_FOR_PRICED_COUPON_SESSION=NO
NEXT_ACTION=RUN_FULL_ANALYSIS_FROM_S2|RUN_NEW_BETTING_DAY_FROM_S1|ENGINEERING_REPAIR_REMAINS_BLOCKED
```

`READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION=YES` is permitted only when:

```text
STATUS=PASS
P0_FIXED=10
P1_FIXED=10
UNRESOLVED_P0=0
UNRESOLVED_P1=0
all required gates=PASS
STANDALONE_CLONE_PROOF=PASS
INTERNAL_INDEPENDENT_AUDIT=PASS
SAFE_FORKED_RUN_IMPORT=PASS
RESTART_SEED_VERIFY=PASS
OFFLINE_START_FROM_S2_E2E=PASS
```

Otherwise return `NO` and list the exact blocker IDs. Do not present partial completion as readiness.
