# Pipeline Truth Contract

## Why the Manifest Exists

The pipeline manifest (`config/pipeline_manifest.json`) serves as the single canonical, machine-readable, and fail-closed source of truth for the sports betting pipeline. Prior to introducing the manifest, the pipeline's operational definitions were scattered across multiple disjoint files, state trackers, documentation maps, and script wrappers. 

By centralizing the steps, associated agents, execution modes, outputs, permitted step-to-step transitions, and hard rules in a single validated file, the pipeline enforces strict operational consistency, branch hygiene, and architectural safety boundaries without modifying any underlying betting logic.

## Canonical Step Order

The pipeline progresses sequentially through 17 explicit steps in this exact order:

1. **S0**: Settler (Phase: `DATA`, Agent: `bet-settler-postevent`) — The first DATA step of the daily pipeline, which may settle prior events before current-day discovery.
2. **S1**: Discover (Phase: `DATA`, Agent: `bet-researcher`)
3. **S1e**: Events Discovery (Phase: `DATA`, Agent: `bet-researcher`)
4. **S2**: Tipsters Discovery (Phase: `DATA`, Agent: `bet-researcher`)
5. **S2.3**: Enrichment Gap Detection (Phase: `DATA`, Agent: `bet-researcher`)
6. **S2.5**: Provider Enrichment (Phase: `DATA`, Agent: `bet-researcher`)
7. **S2.7**: Source Reconciliation (Phase: `DATA`, Agent: `bet-researcher`)
8. **S2.9**: Data Readiness Gate (Phase: `DATA`, Agent: `bet-researcher`)
9. **S3**: Stats & Probability (Phase: `ANALYSIS_BUILD`, Agent: `bet-modeler`)
10. **S4**: Valuator & CLV (Phase: `ANALYSIS_BUILD`, Agent: `bet-modeler`)
11. **S5**: Context/Motivation/Risk (Phase: `ANALYSIS_BUILD`, Agent: `bet-risk-gatekeeper`)
12. **S6**: Portfolio/Repeat Guard (Phase: `ANALYSIS_BUILD`, Agent: `bet-risk-gatekeeper`)
13. **S7**: Hard Approval Gate (Phase: `ANALYSIS_BUILD`, Agent: `bet-risk-gatekeeper`)
14. **S7b**: Market Availability Validation (Phase: `ANALYSIS_BUILD`, Agent: `bet-auditor`)
15. **S8**: Coupon Construction (Phase: `ANALYSIS_BUILD`, Agent: `bet-builder`)
16. **S9**: Human Execution Gate (Phase: `EXECUTION`, Agent: `bet-risk-gatekeeper`)
17. **S10**: Settlement Handoff (Phase: `POST_EVENT`, Agent: `bet-settler-postevent`) — The POST_EVENT settlement/learning handoff.

## Execution Modes

Every pipeline step is bound to one of four validated execution modes:

* **script**: Governed and run via a canonical script wrapper (e.g., Python wrapper under `scripts/pipeline_steps/`).
* **agent_artifact**: Executes using isolated LLM/agent-generated file artifacts, adhering strictly to progressive disclosure and point-in-time constraints.
* **human_gate**: Requires explicit manual user interaction, review, and consensus verification before advancing state.
* **state_only**: Serves as a logical placeholder or transition state that tracks step progress without independent execution wrappers.

## Enrichment Boundary (S2.3 - S2.9)

Steps **S2.3**, **S2.5**, **S2.7**, and **S2.9** define the isolated **Enrichment Boundary**. These steps enrich available fixture metadata but are strictly prohibited from making any predictive or staking modifications. They are subject to these immutable validation constraints:

* **no_pick**: Must not emit, suggest, or modify betting picks.
* **no_edge**: Must not compute, imply, or register betting edges.
* **no_stake**: Must not compute, scale, or suggest Kelly staking/amounts.
* **no_coupon**: Must not construct or manipulate betting coupons.
* **source_bound_only**: Must rely strictly on authorized provider data inputs.
* **unknown_or_blocked_for_missing_data**: Must fail closed if any required input data is missing or corrupted.
* **no_production_db_write**: Must never mutate the production SQLite database.
* **no_betting_data_write**: Must not store betting artifacts outside of standard isolated caches.
* **point_in_time_required**: Every operation must strictly adhere to the designated point-in-time historical constraints.

## Gate Semantics (S7 vs. S7b)

* **S7 (Hard Approval Gate)**: Serves as the ultimate mathematical, statistical, and risk-management filtering gate. It outputs the finalized list of `approved_picks` based on evidentiary validation.
* **S7b (Market Availability Validation)**: A downstream safety gate that verifies whether the approved picks from S7 are actively available and mapped in Betclic. It sits explicitly between the S7 gate and the S8 coupon construction step, ensuring no invalid coupon is created.

## Hard Rules & Global Guarantees

* **No Picks Before S7**: No step prior to S7 can establish, record, or imply a selected pick.
* **No Coupons Before S8**: Staking and coupon composition can only occur in S8, downstream of both S7 and S7b.
* **All Picks Conditional Until User Betclic Verification**: All generated picks remain conditional and unplaced until a human operator physically validates the exact market existence and odds in Betclic at S9.
* **Contract Pass Integrity**: This pass establishes the machine-readable truth layer. It does not activate new live providers, alter provider routing, write to production databases, modify odds valuation models, or change gate score calculations.
