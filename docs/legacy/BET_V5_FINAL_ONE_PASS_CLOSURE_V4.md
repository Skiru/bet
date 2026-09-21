# BET PIPELINE V5 — FINAL ONE-PASS ENGINEERING CLOSURE V4

## 0. Mission and non-negotiable session type

This is a **source-code engineering closure session**.

It is NOT a live betting-analysis session.

You must complete all diagnosis, implementation, adversarial tests, regression repairs, full recertification, standalone-clone verification, safe S2 restart-seed generation, and next-session handoff in this one autonomous session.

Do not stop after the first defect. Do not ask for approval between checkpoints. Iterate until every acceptance gate in this prompt is genuinely green or return a precise engineering blocker with evidence.

During this engineering session you MUST NOT:

- run the live betting pipeline;
- use `--allow-live-network`;
- call live providers;
- resume `v5_analysis_20260729_002` or start `v5_analysis_20260729_003`;
- create betting selections, odds, stakes, coupons, or S9 approval;
- merge to `main`;
- push to a remote;
- claim PASS for a command that was not executed successfully on the final commit.

## 1. Authoritative input provenance

Start from the exact uploaded/reconstructed V3 state:

```text
BASE_REPAIR_HEAD=a71e5024caae71fe19af4807c0b9a7b6856838c4
BASE_REPAIR_TREE=bc2102580abac14ad57bf057503de9f3f274d9cc
BASE_SOURCE_MANIFEST=5c43018e7c669c4b332e76b2354865e2dc3b6a4ec17472b0c475c7258d9df4dd
SOURCE_RUN_ID=v5_analysis_20260729_002
SOURCE_RUN_ROOT=/private/tmp/pipeline_runs/2026-07-29/v5_analysis_20260729_002
SOURCE_S1E_EVENT_COUNT=766
SOURCE_RAW_DISCOVERY_COUNT=998
SOURCE_PROVIDER_DEDUP_COUNT=914
```

Verify HEAD, tree, clean worktree, ancestry, bundle provenance if available, and source manifest before modification.

Create exactly one repair branch:

```text
fix/bet-v5-final-one-pass-closure-v4
```

Do not reuse the V3 branch name.

## 2. Baseline-red requirement

Before implementing repairs, add deterministic tests reproducing every finding below. Run them and persist a baseline-red receipt containing:

- command argv;
- cwd;
- HEAD/tree/manifest;
- start/end timestamps;
- real exit code;
- stdout/stderr paths and SHA-256;
- failing test IDs.

The baseline must fail for the expected reasons. A test that skips because a machine-specific path is absent is not a valid red test.

Use `tmp_path`/`tmp_path_factory` and generated fixtures. No test may depend on `/private/tmp/...002` being present unless it is explicitly an optional separate integration test; mandatory exploit coverage must be self-contained.

## 3. Mandatory finding ledger

Close every finding below individually. For each ID persist:

```text
finding_id
red_test_ids
root_cause
changed_files
green_test_ids
adversarial_test_ids
status=FIXED
```

No grouped “fixed by architecture” entry may replace per-finding evidence.

### V4-P0-01 — Certification inventory mismatch

The committed certifier currently fails on the V3 HEAD because mandatory-file hashes are stale.

Requirements:

- update certification inventory only after final test files stabilize;
- include all mandatory V4 exploit, reducer, restart, receipt, and execution-spine tests;
- bind exact SHA-256 and exact expected test counts;
- make the certifier fail when a mandatory test file is modified, removed, skipped, deselected, or executes fewer tests than declared;
- execute the certifier on the final commit and in a standalone clone.

### V4-P0-02 — Existing test-suite regressions

Repair all existing tests and production compatibility issues exposed by the stricter schemas.

At minimum the following suites must pass without exclusions:

```text
tests/test_pipeline_agent_artifact_contracts.py
tests/test_pipeline_agent_block_artifact_contract.py
tests/test_c2_sharding_and_acquisition.py
tests/test_t2_sharding_lifecycle.py
tests/integration/test_v5_full_sharding_lifecycle.py
tests/security/test_v5_v3_closure_regressions.py
```

Then run the complete `tests/` suite. Do not delete, weaken, xfail, or conditionally skip an existing test merely to obtain green output.

### V4-P0-03 — Safe archive import

Replace unsafe `tar.extractall()` usage with explicit fail-closed member inspection and staged extraction.

Requirements:

- never extract directly into the target run root;
- create a unique sibling staging directory using `tempfile`;
- reject absolute paths, `..` traversal, path normalization escape, duplicate member names, case-collision aliases, symlinks, hardlinks, devices, FIFOs, sockets, unsupported types, and members outside the manifest allowlist;
- accept regular files and explicitly required directories only;
- impose bounded total member count, per-file size, and total uncompressed size;
- verify the seed archive SHA-256 against an externally supplied expected value before reading members;
- verify the manifest SHA-256 against an externally supplied expected value;
- require the archive member set to match the manifest exactly—no missing and no extra files;
- verify all file hashes in staging;
- require target run root not to exist, or require an explicit empty-root policy with no pre-existing files;
- atomically rename/promote staging only after every validation passes;
- remove staging on failure;
- create no files outside staging during any failed test.

Mandatory hostile-archive tests:

```text
../escape
absolute path
symlink escape
hardlink escape
duplicate member
overwrite target sentinel
extra unmanifested member
missing manifested member
oversized member
hash mismatch
manifest hash mismatch
archive hash mismatch
```

### V4-P0-04 — Real event freshness and lead-time revalidation

Implement actual event-by-event revalidation at seed import/start-from-S2 time.

Requirements:

- load canonical events, not only ID counts;
- parse normalized UTC start times;
- use the canonical Europe/Warsaw betting-day contract and configured minimum analysis lead time;
- inspect event lifecycle status where available;
- classify every source S1e event as one of explicit statuses, including at least:
  - `ACTIVE_FOR_S2_RESTART`,
  - `STARTED_BEFORE_RESTART`,
  - `INSUFFICIENT_LEAD_TIME`,
  - `CANCELLED`,
  - `POSTPONED_OR_UNCONFIRMED`,
  - `INVALID_START_TIME`,
  - `MISSING_REQUIRED_EVENT_DATA`;
- do not silently drop events;
- write a new restart accounting ledger containing all 766 source event IDs exactly once;
- write a filtered target S1e universe containing only active events;
- bind both source-universe and active-universe hashes;
- require `active + terminalized == source_s1e_count`;
- a stale event from 2020 must never be classified active;
- current time/as-of must be explicit, injectable in tests, and recorded in the receipt.

The final seed may contain fewer than 766 active events. Never hardcode an active count.

### V4-P0-05 — True exclusion of S2+ state

Replace recursive `data/` inclusion with a transitive, allowlisted through-S1e dependency export.

Requirements:

- include only canonical files required to reconstruct S0/S1/S1e and event accounting;
- follow explicit references from S0/S1/S1e artifacts to required data files;
- normalize and validate every referenced path under source run root;
- reject ambiguous or missing dependencies;
- exclude every S2+ artifact, work order, chunk, plan, ledger, log, output, cache, and data file by construction;
- do not rely on descriptive exclusion-pattern strings;
- produce a semantic inventory with origin step for each included file;
- verify after export that no included file has S2+ origin;
- test that `data/S2.5_provider_observations.json` and neutrally named S2-generated data are excluded.

### V4-P0-06 — Contract-valid S2.7 reducer and parent

Create a typed reducer result that controls the complete parent artifact, not only an arbitrary payload dictionary.

S2.7 PASS must include:

- contract-compatible `disputed_facts` and/or `reconciliation` structure;
- explicit unknown/unresolved fact semantics;
- non-empty, exact evidence refs bound to predecessor artifacts and/or chunk receipts;
- event-bound reconciled facts;
- exact event accounting;
- conflict handling where required unresolved conflicts produce BLOCK;
- source-bound state derived from verified child bindings, never hardcoded.

Run the actual orchestrator parent-construction path and then `validate_agent_artifact_for_work_order()` in the test. Key-presence-only tests are forbidden.

### V4-P0-07 — Contract-valid S2.9 reducer and gate

S2.9 AGENT_ARTIFACT success status must be `PASS`, not `READY`.

A PASS parent must contain:

- `readiness="PASS"`;
- `s3_may_proceed=true`;
- exact predecessor bindings for S2.3, S2.5, and S2.7 including paths and SHA-256;
- non-empty evidence refs covering those steps;
- event-level readiness records;
- exact source/active universe accounting;
- no pricing-ready record without exact eligible model/sport/market governance.

If no events may proceed, emit a contract-supported BLOCK/no-action outcome; never manufacture PASS.

Test normalization and gate satisfaction through the real readiness APIs.

### V4-P0-08 — Contract-valid S5 reducer and parent

S5 aggregation must preserve and validate event-bound context evidence.

A PASS parent must include:

- non-empty evidence refs bound to S3/S4 and child retrieval evidence;
- explicit injuries/lineups context;
- motivation context;
- travel/schedule context;
- morale/recent-form context;
- upset/volatility/risk context;
- candidate accounting and required S4 binding;
- unknowns and blocked reasons derived from data;
- no PASS when required context is absent.

Test the complete orchestrator-to-parent-validator route.

### V4-P0-09 — Immutable, registry-bound model eligibility

Path-name filtering is not an acceptable contamination control.

Requirements:

- an ignored/untracked package under `models/` must not become production/pricing eligible merely because its internal files are self-consistent;
- require every eligible package to be declared in a tracked, source-manifest-bound model registry or another explicit immutable trust root designed by the repository;
- bind package ID, approved path/root, canonical package digest, fitted artifact digest, model-card digest, promotion receipt digest, scope, and status;
- recompute a deterministic canonical package digest and verify `model_package_sha256`;
- reject undeclared packages, unexpected files, symlinked files, path aliases, registry/path mismatch, and mutable ignored-store contamination;
- preserve fail-closed behavior when no package is registered;
- use isolated temporary directories in tests;
- add a mandatory exploit test with a neutral package name that previously resolved as eligible.

Do not solve this by adding more forbidden substrings.

### V4-P0-10 — Truthful receipts and final report

Redesign quality/certification receipts so PASS is derived from executed evidence.

Requirements:

- remove PASS/READY defaults from command, validator, certifier, and quality receipt models;
- add consistency validators:
  - PASS requires exit code 0;
  - FAIL/BLOCK required for nonzero exit code;
  - stdout/stderr paths must exist when declared;
  - SHA fields must contain actual file hashes;
  - pytest PASS requires failed=0, errors=0, collected>0, and arithmetic consistency;
- separate `junit_path` from `junit_sha256` and calculate the actual hash;
- execute and receipt each quality gate independently:
  - format,
  - lint,
  - typecheck,
  - focused tests,
  - pipeline tests,
  - full suite,
  - validators,
  - offline E2E,
  - external acceptance,
  - mutation/exploit proof,
  - certification;
- no hardcoded PASS strings;
- final report must verify each child receipt, command, exit code, hashes, HEAD/tree/manifest, and timestamps;
- tampering with one child receipt must block final readiness;
- a missing receipt must block;
- a stale receipt from another HEAD/tree must block.

## 4. Additional mandatory P1 closure

### V4-P1-01 — Empty-evidence reducer fail-closed

For every reducer:

- no nonempty input universe may produce PASS with zero event-bound evidence and zero terminal dispositions;
- no synthetic summary dictionary may masquerade as an event record;
- exact event union and one terminal outcome per assigned event are required;
- child PASS alone is insufficient.

### V4-P1-02 — Typed complete reduced-parent contract

Replace `dict[str, Any]` reducer outputs with a typed result containing at least:

```text
status
payload
event_records
sources
source_bound
unknowns
blocked_reasons
evidence_refs
predecessor_bindings
coverage_receipt
```

The orchestrator must not overwrite these with optimistic constants.

Unregistered sharded step => hard error. Remove the generic PASS/READY fallback.

Validate the complete parent in memory before atomic persistence. An invalid parent must never be written as a successful artifact.

### V4-P1-03 — Acquisition plan coverage per event and market

Implement real acquisition plans per canonical event and relevant market family.

Requirements:

- no `consumed_eids[0]` shortcut;
- no `evt_default_shortlist` fallback;
- no silent exception swallowing;
- no default sport=football when sport is missing;
- a plan index must provide exact coverage for every assigned event and selected market scope;
- every chunk receives only plans for its own event IDs;
- required facts must be sport/market specific;
- tool permissions must be the intersection of agent, manifest, requirement, and runtime policies;
- zero uncovered or foreign event IDs;
- test a 766-event fixture and mixed sports/markets deterministically.

### V4-P1-04 — No positive empty typed artifacts

For S0-S10 typed contracts:

- decision-bearing status must be explicit;
- PASS requires non-empty, internally consistent records when the input universe is nonempty;
- record counts must equal list lengths;
- empty artifacts must be BLOCK or an explicit contract-supported no-action state;
- remove benign defaults such as probability uncertainty 0.02, motivation 1.0, LOW risk, and PASS terminal status unless they are mathematically derived and evidence-bound;
- add cross-field validators.

Mandatory tests must prove that empty S3, S5, and S2.9 cannot validate as positive.

### V4-P1-05 — Migration cannot fabricate evidence

Missing uncertainty, motivation, repeat-risk, confidence, counts, or other decision/evidence values must:

- raise `MigrationAdapterError`, or
- be represented as explicit UNKNOWN/BLOCK fields supported by the target contract.

Do not assign apparently benign values.

### V4-P1-06 — Authentic S2.9 identities

Never reconstruct event identity as `Home`, `Away`, `ALL`, `unknown`, or similar placeholders. Resolve exact identity from the canonical event ledger/S1e dossier and bind its source hash. Missing identity must block event readiness.

### V4-P1-07 — Robust restart CLI

Replace the current implicit source-run export flow with an explicit immutable seed contract.

The next live command must consume:

```text
--restart-seed <exact path>
--restart-seed-sha256 <exact sha256>
--restart-seed-manifest <exact path>
--restart-seed-manifest-sha256 <exact sha256>
--start-step S2
--reuse-through-step S1e
```

Requirements:

- reject any reuse-through value other than S1e for this mode;
- do not re-export from source run during the live session;
- do not use a shared fixed `/tmp/s2_restart_seed` directory;
- require a new run ID and absent target run root;
- bind source and target lineage;
- verify source-run hashes before and after seed export in the engineering session;
- preserve source run unchanged.

### V4-P1-08 — Derived generic seed metadata

Derive dates, run IDs, counts, filenames, source provenance, and timestamps. Missing provenance or timestamp must fail closed. No hardcoded 2026-07-29 filenames/counts inside generic scripts.

### V4-P1-09 — Real execution-spine tests

Add deterministic offline tests that execute:

```text
parent work order
→ event/market acquisition plan index
→ chunk plan
→ chunk work-order serialization
→ prompt rendering/loading
→ child artifact
→ full child binding validation
→ ledger/resume
→ typed reducer
→ complete parent assembly
→ parent work-order validation
→ atomic persistence
→ downstream gate
```

Run this for S2.3, S2.5, S2.7, S2.9, and S5 with enough events to trigger sharding.

The tests must use meaningful event-bound evidence, not hand-written generic status objects.

### V4-P1-10 — Certification and acceptance must cover exploits

The mandatory inventory, external acceptance harness, and mutation/exploit suite must directly execute all V4 hostile cases. Checking only that a method or reducer exists is not acceptance evidence.

## 5. Seed source and event preservation

The previous discovery work is valuable and must be preserved safely.

The engineering session must not rediscover S0/S1/S1e and must not mutate the source run.

After all code/tests are green:

1. Verify source run provenance and file hashes.
2. Export a new through-S1e-only seed using the repaired exporter.
3. Verify source run unchanged after export.
4. Verify exact source S1e count is 766.
5. Import the seed into an isolated offline target using a fixed injectable as-of time.
6. Validate exact event accounting and freshness classifications.
7. Run offline start-from-S2 E2E through analysis-only S8 using deterministic fixtures/mocked acquisition, without live network.
8. Remove the offline target and regenerate the final immutable seed for the real next session.

Do not assert that all 766 are active. Report actual active and terminalized counts at handoff time.

## 6. Testing and iterative repair loop

Use this loop until green:

```text
run focused new red/green tests
run all affected existing suites
run complete tests/
run format/lint/typecheck discovered from repository/CI
run validators
run offline E2E from S2 through S8
run external acceptance
run expanded exploit/mutation proof
run final certifier
run independent read-only audit
repair every new P0/P1
repeat all gates
```

Do not suppress warnings/errors by editing expectations to match broken behavior.

Preserve real exit codes when piping output.

## 7. Internal independent audit

After implementation is complete, delegate a read-only adversarial audit to `bet-auditor` or the repository's independent auditor role.

The auditor must receive the finding ledger and attempt to reproduce at least:

- traversal escape;
- symlink/hardlink archive escape;
- stale event marked active;
- S2+ seed contamination;
- invalid S2.7/S2.9/S5 parent acceptance;
- empty reducer PASS;
- neutral ignored promoted model acceptance;
- hardcoded receipt PASS;
- stale receipt reuse;
- acquisition-plan first-event shortcut;
- empty positive typed artifacts;
- certification inventory drift.

Any successful exploit or unresolved P0/P1 returns the work to the repair loop in the same session.

## 8. Final commit and standalone proof

Create logically grouped commits on the repair branch. The final worktree must be clean.

Create a self-contained bundle:

```text
/tmp/bet_pipeline_v5_final_one_pass_closure_v4.bundle
```

Verify it, clone it into a fresh standalone directory, and rerun on the clone:

- HEAD/tree/manifest;
- all mandatory V4 exploit tests;
- affected legacy tests;
- complete test suite;
- format/lint/typecheck;
- validators;
- offline start-from-S2 E2E;
- external acceptance;
- mutation/exploit proof;
- certifier;
- final report generator.

No test may pass because an absolute source-run path happens to exist on the original machine.

## 9. Final deliverables

Create:

```text
/tmp/bet_v5_final_one_pass_closure_v4/
/tmp/bet_v5_final_one_pass_closure_v4.tar.gz
/tmp/bet_pipeline_v5_final_one_pass_closure_v4.bundle
/tmp/bet_v5_s2_restart_seed_v4.tar.gz
/tmp/bet_v5_s2_restart_seed_v4_manifest.json
/tmp/bet_v5_final_one_pass_closure_v4/next_analysis_handoff.json
/tmp/bet_v5_final_one_pass_closure_v4/next_bet_executor_analysis_prompt.md
```

The evidence package must include command receipts, logs, exact test lists, finding ledger, red/green evidence, hostile archive tests, reducer parent validation, model contamination test, full-suite JUnit, certification report, standalone-clone report, seed inventories/hashes, event freshness accounting, source-run before/after hashes, and SHA256SUMS.

The next bet-executor prompt must be generated from actual final values and must:

- start a new run ID;
- consume the immutable repaired seed by exact SHA-256;
- start at S2;
- rerun S2 and every later analytical step;
- never reuse S2+;
- recheck event freshness immediately before S2;
- remain pricing fail-closed;
- stop before human-only S9;
- use live network only in that next separate session.

## 10. Final acceptance contract

You may return PASS only when every field below is truthful and evidenced on the final commit and standalone clone:

```text
CHECKPOINT=BET_V5_FINAL_ONE_PASS_CLOSURE_V4
STATUS=PASS
DECISION=READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION

HEAD_BEFORE=a71e5024caae71fe19af4807c0b9a7b6856838c4
TREE_BEFORE=bc2102580abac14ad57bf057503de9f3f274d9cc
HEAD_AFTER=<actual>
TREE_AFTER=<actual>
SOURCE_MANIFEST_AFTER=<actual>
WORKTREE_CLEAN=true

V4_P0_FIXED=10
V4_P1_FIXED=10
UNRESOLVED_P0=0
UNRESOLVED_P1=0

CERTIFICATION_INVENTORY_BOUND=PASS
FULL_SUITE=PASS
EXISTING_SHARDING_TESTS=PASS
SAFE_ARCHIVE_IMPORT=PASS
PATH_TRAVERSAL_EXPLOIT=BLOCKED
SYMLINK_HARDLINK_EXPLOITS=BLOCKED
SEED_MEMBER_ALLOWLIST=PASS
EVENT_FRESHNESS_REVALIDATION=PASS
SOURCE_S1E_EVENT_COUNT=766
RESTART_ACTIVE_EVENT_COUNT=<derived>
RESTART_TERMINALIZED_EVENT_COUNT=<derived>
RESTART_EVENT_ACCOUNTING_EXACT=PASS
S2_PLUS_SEED_CONTAMINATION=BLOCKED
SOURCE_RUN_UNCHANGED=PASS

S2_3_PARENT_CONTRACT=PASS
S2_5_PARENT_CONTRACT=PASS
S2_7_PARENT_CONTRACT=PASS
S2_9_PARENT_CONTRACT=PASS
S5_PARENT_CONTRACT=PASS
EMPTY_REDUCER_PASS_BLOCKED=PASS
UNREGISTERED_REDUCER_FAIL_CLOSED=PASS

ACQUISITION_PLAN_EVENT_MARKET_COVERAGE=PASS
TOOL_GOVERNANCE=PASS
EMPTY_POSITIVE_TYPED_ARTIFACTS_BLOCKED=PASS
MIGRATION_FABRICATION_BLOCKED=PASS
AUTHENTIC_EVENT_IDENTITIES=PASS

IGNORED_MODEL_CONTAMINATION_BLOCKED=PASS
MODEL_REGISTRY_BINDING=PASS
CANONICAL_MODEL_PACKAGE_DIGEST=PASS
S8_PRICING_FAIL_CLOSED=PASS
S9_HUMAN_ONLY=PASS

QUALITY_RECEIPTS_TRUTHFUL=PASS
JUNIT_HASH_BINDING=PASS
RECEIPT_TAMPER_TESTS=PASS
FORMAT=PASS
LINT=PASS
TYPECHECK=PASS
FOCUSED_TESTS=PASS
PIPELINE_TESTS=PASS
VALIDATORS=PASS
OFFLINE_START_FROM_S2_E2E=PASS
EXTERNAL_ACCEPTANCE=PASS
EXPANDED_MUTATION_PROOF=PASS
EXPLOIT_REGRESSION_SUITE=PASS
CERTIFICATION=PASS
STANDALONE_CLONE_PROOF=PASS
INTERNAL_INDEPENDENT_AUDIT=PASS

REVIEW_BUNDLE_PATH=/tmp/bet_pipeline_v5_final_one_pass_closure_v4.bundle
REVIEW_BUNDLE_SHA256=<actual>
REVIEW_PACKAGE_PATH=/tmp/bet_v5_final_one_pass_closure_v4.tar.gz
REVIEW_PACKAGE_SHA256=<actual>
S2_RESTART_SEED_PATH=/tmp/bet_v5_s2_restart_seed_v4.tar.gz
S2_RESTART_SEED_SHA256=<actual>
S2_RESTART_MANIFEST_PATH=/tmp/bet_v5_s2_restart_seed_v4_manifest.json
S2_RESTART_MANIFEST_SHA256=<actual>
NEXT_ANALYSIS_HANDOFF_PATH=/tmp/bet_v5_final_one_pass_closure_v4/next_analysis_handoff.json
NEXT_BET_EXECUTOR_PROMPT_PATH=/tmp/bet_v5_final_one_pass_closure_v4/next_bet_executor_analysis_prompt.md

READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION=YES
READY_FOR_PRICED_COUPON_SESSION=NO
NEXT_ACTION=RUN_FULL_ANALYSIS_FROM_S2_USING_IMMUTABLE_VERIFIED_SEED
```

If any field cannot be proven, return:

```text
STATUS=BLOCKED
DECISION=BLOCKED_ENGINEERING_REPAIR_REQUIRED
READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION=NO
```

Never emit a partial PASS.
