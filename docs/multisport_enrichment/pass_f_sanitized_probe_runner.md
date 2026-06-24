# Pass F: Bounded Sanitized Probe Runner

## 1. Why Pass F Exists After Pass E
While **Pass E** (`MULTISPORT_PASS_E_PROVIDER_MAPPING_CONTRACTS`) defined the mappings, required credentials, endpoint specifications, and structural contracts, it did not execute or attempt any provider access. **Pass F** introduces a **fail-closed, sanitized probe runner** to act as a diagnostic step. This allows testing connectivity and verifying schema/response fields in a secure, non-production sandbox without exposing raw credentials or violating terms.

---

## 2. Default: No Real Network Calls
By default, the probe runner is completely decoupled from the live internet.
* No real network calls are made.
* All checks map directly to deterministic blocked statuses or dry-run states depending on the mapping status and credentials.
* This ensures that developers can run the entire test suite and verify compliance locally/offline without risking unwanted charges, secret leakage, or scraping violations.

---

## 3. Real-Network Gating Conditions
Real network calls can be enabled *only* if all of the following conditions are strictly satisfied:
1. **Environment Variable:** `MULTISPORT_PASS_F_ALLOW_REAL_NETWORK=1` is set.
2. **Mapping Ready:** The source provider mapping status must be exactly `MAPPING_READY_FOR_SANITIZED_PROBE`.
3. **Credentials Present:** All required environment variables (e.g. `API_BASKETBALL_KEY`, `PANDASCORE_TOKEN`) must be non-empty and present in the environment.
4. **Policy Terms Review Approved:** The policy's `terms_review_approved` property must be set to `True`.
5. **Execution Caps:** `max_requests` is strictly `1` (or less).
6. **Sanitization Enforced:** `sanitized_probe_only` must be `True` to redact all raw values and payloads.

If even a single condition is unfulfilled, **no live network access is attempted**.

---

## 4. Expected Blocked Statuses (Standard Dry Run)
When credentials are not present or terms review has not been verified:
* **basketball, volleyball, hockey, tennis:** These are mapped to `SANITIZED_PROBE_BLOCKED_NO_CREDENTIALS` because they lack standard API-Sports family keys in the offline runner environment.
* **cs2, dota2, valorant:** These are mapped to `SANITIZED_PROBE_BLOCKED_PROVIDER_TERMS_OR_SCOPE` because they require an active terms and scope audit (the default policy has `terms_review_approved=False` for PandaScore).

---

## 5. Capturing Sanitized Response in Future Authorized Runs
When real network calls are safely permitted and succeed:
1. The response payload is requested using standard connection timeouts.
2. The payload is recursively parsed to extract *keys only* to identify which of the required proof fields are present.
3. A sanitized envelope is constructed (containing only response schema details, key presence list, and row counts).
4. `proof_fields_observed` is populated with the matching available fields.
5. **Absolutely no raw provider data or headers** are written to the artifact.
6. The status is set to `SANITIZED_PROBE_RESULT_CAPTURED_SANITIZED`.

---

## 6. Strict Guardrails: No Production or Betting Activation
For maximum safety and alignment with our compliance mandates:
* `production_selectable` is hard-locked to `False`.
* `betting_decisions_enabled` is hard-locked to `False`.
* No database writes are allowed.
* No picks, stakes, odds-derived proof fields, or recommendations can be produced or accepted.
