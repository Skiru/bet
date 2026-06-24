# Run Readiness Implementation Bundle v1

## Purpose

This bundle defines the contract layer required before implementing the manifest-driven daily pipeline orchestrator.

## Base

* Branch: main
* Expected main prefix: 0f8d082
* Pipeline source of truth: `config/pipeline_manifest.json`
* Enrichment source of truth: `src/bet/enrichment/multisport_foundation`

## Invariants

* `fail_closed=true`
* `point_in_time_required=true`
* `no_pick_before_s7=true`
* `no_coupon_before_s8=true`
* `s2_9_required_before_s3=true`
* no production DB writes in readiness pass
* no live provider calls in readiness pass

## Bundle Components

* `readiness_contracts.py`: Dataclasses, Enums, and status helpers representing pipeline and artifact statuses.
* `artifact_gate.py`: Logic to locate, parse, recursively scan, and validate step artifacts against the Gate Matrix.
* `run_evidence.py`: Helpers for system hash calculation, atomic JSON writes, and building run evidence summaries.
* `wrapper_contracts.py`: Manifest wrapper validation, path matching, ordering checks, and compilation tests.
* runner/write-safety hardening: Safe write conditions requiring `--allow-write`, custom env verification, and dry-run exclusion.
* wrapper compile/naming fixes: Aligning `s4_valuator.py` and `s7_validate.py` to compiled execution conventions.
* tests: Direct test assertions verifying each of the readiness contracts, gate logic, runner safety, and wrappers.

## Artifact Contract

The artifact JSON schema requires:
* `schema_version`: integer (must be >= 1)
* `artifact_type`: string representing the category of the artifact (e.g., AGENT_ARTIFACT, HUMAN_GATE, STATE_MARKER, SCRIPT_EVIDENCE, RUN_SUMMARY)
* `step_id`: string identifying the pipeline step that produced the artifact (must match the expected step_id)
* `status`: string indicating the step completion status (PASS, WARN, BLOCK, UNKNOWN, SKIPPED, HUMAN_APPROVED, HUMAN_REJECTED)
* `betting_day`: string (YYYY-MM-DD format)
* `run_id`: string uniquely identifying the execution run
* `sport`: optional string
* `fixture_id`: optional string
* `fixture_key`: optional string
* `point_in_time_as_of`: YYYY-MM-DDTHH:MM:SS format ISO timestamp representing when the source data was captured (required for agent artifacts)
* `source_bound`: boolean indicating if the data is bound to real sources rather than model inferences (must be true for enrichment artifacts)
* `no_pick_edge_stake_coupon_emitted`: boolean proving no forbidden signals were written (must be true for enrichment steps S2.3-S2.9)
* `production_selectable`: boolean (must be false for enrichment artifacts)
* `betting_decisions_enabled`: boolean (must be false for enrichment artifacts)
* `sources`: tuple/list of strings listing physical sources (required for agent artifacts)
* `unknowns`: optional tuple/list of strings listing unverified values or missing sources
* `blocked_reasons`: optional tuple/list of strings explaining why an item was blocked
* `evidence_refs`: tuple/list of strings representing references or data hashes
* `payload`: dictionary of raw step data containing nested metrics, mappings, or status structures (recursively checked for forbidden decision signals)

## Gate Matrix

The validation gate evaluates pre-requisite artifacts before any step may execute:
* S3 execution requires a validated S2.9 PASS artifact.
* S6 execution requires a validated S5 PASS artifact.
* S8 execution requires both S7 PASS and S7b PASS artifacts.
* S10 execution requires a validated S9 HUMAN_APPROVED artifact.
* S2.3, S2.5, S2.7, and S2.9 (enrichment steps) must never contain any pick, edge, stake, or coupon fields, either at the top-level or nested.
* UNKNOWN status never passes.
* WARN status never passes into betting execution without an explicit policy override.

## Future Passes

* Pass 2: manifest-driven orchestrator
* Pass 3: provider readiness matrix
* Pass 4: daily dry-run certification
