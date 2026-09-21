# Pass C: Multi-Sport Activation Candidate & Fail-Closed Observation

This document defines and describes the implementation, behavior, and design invariants of Pass C within the multi-sport data foundation.

## Architectural Flow

Pass C operates directly on top of the accepted Pass B outputs (source inventory and source-bound shadow status by sport). It processes seven target sports:
*   Basketball
*   Volleyball
*   Hockey
*   Tennis
*   CS2
*   Dota 2
*   Valorant

### 1. Status Derivation from Pass B

For each target sport, the Pass C status is strictly derived from the corresponding Pass B source-bound shadow status as follows:

*   **SOURCE_BOUND_SHADOW_READY** (with non-empty `source_keys` and `corpus_ids`):
    *   **Pass C Status**: `ACTIVATION_CANDIDATE_SHADOW_ONLY`
    *   This represents a shadow-only activation candidate, meaning the provider data is parsed, mapped, and structured under shadow execution, but not promoted to production routes.
*   **REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT**:
    *   **Pass C Status**: `REAL_PROVIDER_ACCESS_OBSERVED_BUT_LIVE_SHADOW_BLOCKED_INSUFFICIENT_MAPPING`
*   **BLOCKED_PROVIDER_TERMS_OR_SCOPE**:
    *   **Pass C Status**: `BLOCKED_PROVIDER_TERMS_OR_SCOPE`
*   **BLOCKED_PROVIDER_MAPPING_NOT_FOUND**, **BLOCKED_NO_CREDENTIALS**, **BLOCKED_PROVIDER_ACCESS**, or any missing/malformed status:
    *   **Pass C Status**: `BLOCKED_NO_REAL_PROVIDER_ACCESS`

### 2. Design Invariants and Safety Guardrails

To prevent accidental production route promotion, data pollution, or uncontrolled operations, Pass C enforces the following strict invariants across both the Activation Candidate model and the Live Observation model:

*   **No Production Activation / Selectable Routes**: The field `production_selectable` must always be `false`.
*   **No Betting Decisions**: The field `betting_decisions_enabled` must always be `false`. No picks, stakes, odds-derived edges, recommendations, or tips are produced or enabled.
*   **Manual Authorization Required**: The field `manual_authorization_required` must always be `true` for all models and sports.
*   **Zero Live Network Calls**: The field `live_call_made` and `provider_access_attempted` are hardcoded to `false` in this pass. No active provider queries are made.
*   **Observation Mode**: The field `observation_mode` is locked to `fail_closed_no_live_call`.

## Current State of the Target Sports

At the current revision (`START_SHA`), all seven target sports are in the `BLOCKED_PROVIDER_MAPPING_NOT_FOUND` state in Pass B because no sport-specific endpoint mappings or provider corpora have been registered.

Consequently, Pass C correctly and safely derives **`BLOCKED_NO_REAL_PROVIDER_ACCESS`** for all seven sports. This is a fully expected and valid outcome that ensures the system fails closed until real provider credentials, mappings, and verified corpora are supplied.

## Generated Artifacts

Pass C automatically produces three audited JSON report files under `reports/multisport_foundation/pass_c/`:
*   `activation_candidate_by_sport.json`: Audit log of the shadow activation candidates.
*   `live_fail_closed_observation_by_sport.json`: Audit log of live observations (operating under fail-closed mode).
*   `pass_c_summary.json`: Summary overview of the metrics, counts, and statuses.

All reports are pretty-printed, sorted, multi-line, and strictly contain no raw secrets, headers, tokens, cookies, or API keys.
