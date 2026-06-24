# Pass H Provider Access Gate

This document details the design, rationale, and implementation details for the transport-free **Pass H Provider Access Gate**.

## Why Pass H Exists after Pass E/F

* **Pass E (Provider Mapping)** established the sport-to-provider mappings and sanitized probe foundation, detailing which providers cover each target sport and defining status derivation based on credentials.
* **Pass F (Sanitized Probe Plan)** verified default probe policies, query parameter formats, and dry-run/live probe mechanics.
* **Pass H (Provider Access Gate)** serves as a strict, transport-free authorization barrier prior to performing actual network operations. It introduces explicit operational gates—terms review, data-scope, and operator approval—to ensure that all legal, architectural, and procedural validations are explicitly met before the system is allowed to initiate any live probes (Pass I).

## Why Credential Presence is Insufficient

Simply detecting that environment credentials (such as `API_SPORTS_KEY` or `PANDASCORE_TOKEN`) are set is insufficient for starting live network queries:
1. **Third-Party API Agreements:** Legal and pricing terms associated with API keys require conscious validation to avoid unintended financial costs or legal violations.
2. **Data Scope Restrictions:** API subscriptions must cover the intended data scopes (endpoints, sports, leagues, seasons). Probing without confirming scope leads to rate limit consumption or account suspensions.
3. **Operational Readiness:** System administrators/operators must formally enable the integration, confirming that down-stream systems are prepared to ingest, process, and store the retrieved data.

Pass H explicitly models these concerns as distinct gating environment flags.

## Operational Gates

### 1. Credentials Presence Detection
Checks if the required environment credentials are set (presence-only validation).
- **API-Sports Family:** `API_BASKETBALL_KEY`, `API_VOLLEYBALL_KEY`, `API_HOCKEY_KEY`, `API_TENNIS_KEY`, or `API_SPORTS_KEY`
- **PandaScore:** `PANDASCORE_TOKEN`

### 2. Terms Review Gate
Verifies that the provider terms and conditions have been explicitly reviewed and accepted.
- **API-Sports:** `MULTISPORT_API_SPORTS_TERMS_APPROVED=1`
- **PandaScore:** `MULTISPORT_PANDASCORE_TERMS_APPROVED=1`

### 3. Data-Scope Gate
Verifies that the requested sports and leagues are approved within the data scope.
- **API-Sports:** `MULTISPORT_API_SPORTS_DATA_SCOPE_APPROVED=1`
- **PandaScore:** `MULTISPORT_PANDASCORE_DATA_SCOPE_APPROVED=1`

### 4. Operator Approval Gate
Verifies that operators have cleared the integration for the single-flight probe.
- **API-Sports:** `MULTISPORT_API_SPORTS_OPERATOR_APPROVED=1`
- **PandaScore:** `MULTISPORT_PANDASCORE_OPERATOR_APPROVED=1`

## No Live Calls in this Pass

In accordance with strict safety invariants, Pass H **must never**:
- Initiate real network/HTTP requests.
- Initialize provider client libraries.
- Write data to the production databases or run destructive migrations.
- Output or write actual raw secret values or auth headers/cookies in the reports.

It is a pure metadata-based gate validating compliance before execution.

## Relationship to Future Pass I Sanitized Probe

Only when all four gates above are satisfied does a target sport move to the `AUTHORIZED_FOR_SANITIZED_LIVE_PROBE` status.

This status does **not** perform any live request. Instead, it transitions the sport's `next_allowed_phase` to `pass_i_authorized_single_flight_probe`, granting authorization for a future **Pass I single-flight sanitized live probe**.
