# Pass I Single Flight Probe

This document outlines the architecture, constraints, and operational guidelines for the **Pass I Single Flight Probe** in the Multisport Enrichment pipeline.

## Why Pass I Exists After Pass H

Pass H (Provider Access Gate) manages and authorizes provider access on a per-sport basis. However, Pass H does not make active provider requests; it is a passive structural gate checking credentials and terms. Pass I serves as the first active stage representing a real single-flight probe request to verify the physical transport capability of the routes under strict authorization.

## Exact Gates Before Any Real Request

No network call or real request is allowed unless all of the following gates evaluate to `True`:

1. **Pass H Access Authorization**: The Pass H access status for that sport and provider must be exactly `AUTHORIZED_FOR_SANITIZED_LIVE_PROBE`.
2. **Pass E Mapping Status**: The Pass E provider mapping status must be exactly `MAPPING_READY_FOR_SANITIZED_PROBE`.
3. **Pass F Policy**: The Pass F policy must permit the sanitized probe boundary.
4. **Operator network flag**: The environment variable `MULTISPORT_PASS_I_ALLOW_REAL_NETWORK=1` must be explicitly set, and `operator_network_flag` must be passed as `True`.
5. **Injected Transport Boundary**: A valid transport boundary (`ProbeTransport` protocol implementation) must be explicitly injected.
6. **Max Requests Constraint**: `max_requests` in the policy must be exactly `1`.
7. **HTTP Method**: The request method must be exactly `GET`.
8. **Active Response Sanitizer**: Response sanitization must be active before the report is written.
9. **Forbidden Fields Absence**: No forbidden fields (such as odds or predictions) can be accepted as proof.

## Why Default Report Makes No Network Calls

By default, Pass H has all seven sports blocked with `BLOCKED_NO_CREDENTIALS`. Consequently, the default Pass I run derives the status `SINGLE_FLIGHT_BLOCKED_ACCESS_GATE` for all sports. No transport or network access is attempted under the default configurations.

## How Fake Transport Tests Prove Sanitizer Behavior

Unit tests inject a `FakeTransport` implementing the `ProbeTransport` protocol to supply mock provider payloads. These tests verify:
1. That only minimum fact fields are collected as proof names.
2. That raw values of the payload are discarded.
3. That exceptions raised by the transport are sanitized to their error class and never leak internal strings or raw URLs.
4. That presence of any forbidden domain fields (e.g. odds, predictions) blocks result capture.

## How Future Real Provider Probes Should Be Run

To execute real single-flight probes in the future:
1. Ensure credentials are set and Pass H/E gates are fully authorized.
2. Set the environment variable `MULTISPORT_PASS_I_ALLOW_REAL_NETWORK=1`.
3. Inject a concrete HTTP client transport mapping to the actual API endpoint.
4. Verify the output report contains `SINGLE_FLIGHT_RESULT_CAPTURED_SANITIZED` and has logged the observed facts.

## Why Raw Provider Payloads Are Never Persisted

To prevent logging secrets, sensitive metadata, or raw response states, raw provider payloads are never written to any report or persisted on disk. The sanitized envelope contains only a redacted summary of observed/missing minimum facts.

## Why Odds/Predictions Are Forbidden As Proof

This pass is strictly focused on verification of basic data mapping and physical transport boundaries. To eliminate any compliance or domain coupling risk, odds, predictions, picks, stakes, edges, recommendations, and bookmaker-related elements are strictly forbidden from appearing in proof fields.

## Why Production Activation and Betting Decisions Remain False

In alignment with the fail-closed pipeline principles, production activation and betting decision capabilities are hardcoded to `False` in this pass. Single-flight probes are diagnostic tools and must never influence active betting decisions or production states.
