# API-Football Hydration Probe Report

This probe verifies the configuration, budget compliance, and connectivity of the API-Football client for the targeted candidates.

---

## 1. Environment & API Key Verification
* **API Key Status:** `NOT_CONFIGURED`
* **API Key Safe Redaction:** Verified. No raw keys or secret values are loaded or printed.
* **Database Connection Status:** `PASS` (Reads from `betting/data/betting.db` 482MB).

---

## 2. Probe Run Details
* **Endpoints Attempted:** 
  * `/teams` (Resolve Team IDs)
  * `/fixtures` (Get Team Last Fixtures)
  * `/fixtures/statistics` (Get Fixture Stats)
* **Total Request Count:** `0` (Since API Key is `NOT_CONFIGURED`, live requests were safely bypassed to avoid rate limit or auth errors).
* **Quota / Rate-Limit Status:** `DATA_UNAVAILABLE`
* **Provider Errors:** `AUTHENTICATION_ERROR` (API key missing or empty).

---

## 3. Candidate Hydration Summary

| Candidate ID | Status | Blocker Category | Provider Error / Details |
|---|---|---|---|
| `football|Kazma|Al-Salmiya|2026-06-29` | `BLOCKED` | `PROVIDER_DATA_UNAVAILABLE` | Live API query bypassed (no key) |
| `football|Melgar|CD Moquegua|2026-06-29` | `BLOCKED` | `PROVIDER_DATA_UNAVAILABLE` | Live API query bypassed (no key) |
| `football|B68 Toftir|Argir|2026-06-29` | `BLOCKED` | `PROVIDER_DATA_UNAVAILABLE` | Live API query bypassed (no key) |
| `football|HB Torshavn|Skala|2026-06-29` | `BLOCKED` | `PROVIDER_DATA_UNAVAILABLE` | Live API query bypassed (no key) |
| `football|Brazil|Japan|2026-06-29` | `BLOCKED` | `PROVIDER_DATA_UNAVAILABLE` | Live API query bypassed (no key) |
| `football|Germany|Paraguay|2026-06-29` | `BLOCKED` | `PROVIDER_DATA_UNAVAILABLE` | Live API query bypassed (no key) |
| `football|Deportivo Garcilaso|Deportivo Binacional|2026-06-29` | `BLOCKED` | `PROVIDER_DATA_UNAVAILABLE` | Live API query bypassed (no key) |
| `football|Vikingur|Runavik|2026-06-29` | `BLOCKED` | `PROVIDER_DATA_UNAVAILABLE` | Live API query bypassed (no key) |

---

## 4. Verdict
* **API_FOOTBALL_HYDRATION_VERDICT:** `NOT_CONFIGURED`
* **Action Plan:** In the absence of live API keys, candidates must remain blocked as `RESEARCH_GAP_L10_MISSING` or `RESEARCH_GAP_STATS_MISSING` in strict compliance with anti-hallucination policies. No placeholder statistics have been or will be injected.
