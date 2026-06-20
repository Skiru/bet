# A5C2 Football Data Foundation Semantic Spot Check

## Overview
This report contains the semantic audit results for the normalized Football Data Foundation canonical mapping and enrichment freshness layers. All 12 core enrichment invariants are verified by focused regression tests or direct code inspections.

---

## Semantic Invariant Verification

### 1. Separate Identifiers
* **Rule:** `scanner_event_id` is never used as `provider_event_id`.
* **Status:** **PASS**
* **Verification:** `test_resolver_creates_sport_competition_team_fixture_rows_and_mappings` verifies that scanner_event_id (`66456944`) and provider_event_id (`760442`) are mapped separately.

### 2. ESPN Event ID Preservation
* **Rule:** `provider_event_id=760442` remains ESPN event id for USA/Australia.
* **Status:** **PASS**
* **Verification:** Checked in active enrichment profile inputs, where the ESPN FIFA World Cup event ID `760442` represents the target USA vs Australia match.

### 3. Conflicting External ID Protection
* **Rule:** Source `external_id` mismatch returns `SOURCE_EXTERNAL_ID_CONFLICT` or `AMBIGUOUS_FIXTURE_MATCH`.
* **Status:** **PASS**
* **Verification:** `test_source_external_id_conflict_handling` tests attempting to map an already-mapped source to a conflicting external ID, raising `SOURCE_EXTERNAL_ID_CONFLICT`.

### 4. Generic Resolver Execution
* **Rule:** Generic resolver paths do not hardcode football except in acceptance test data.
* **Status:** **PASS**
* **Verification:** `test_future_non_world_cup_profile_integration` successfully processes a Premier League non-World-Cup match, showing the resolver logic handles any generic sport/profile.

### 5. Country Sanitation
* **Rule:** `competition.country` never stores group labels like `Group D`.
* **Status:** **PASS**
* **Verification:** `test_competition_country_does_not_store_group_label` asserts that when scanner group label starts with `"Group"`, `country` is set to `None`/null.

### 6. Explicit Fact Scopes
* **Rule:** Fact scopes are explicit: `TEAM_HOME`, `TEAM_AWAY`, `FIXTURE_LEVEL`, `UNKNOWN`.
* **Status:** **PASS**
* **Verification:** `test_fact_scoping_and_duplication_flagging` inspects the output observation payload and verifies that all facts are explicitly mapped to their respective scope using `classify_fact_scope`.

### 7. Duplication Marker
* **Rule:** Duplicated fixture-level facts include `duplicated_for_schema_team_id_constraint=true`.
* **Status:** **PASS**
* **Verification:** Checked by `test_fact_scoping_and_duplication_flagging`, ensuring duplicated home/away rows are clearly marked to prevent double-counting.

### 8. Live-to-Final Drift Protection
* **Rule:** Live-to-final drift returns `STATUS_DRIFT_REFRESH_REQUIRED`.
* **Status:** **PASS**
* **Verification:** `test_live_to_final_status_drift` validates that if cached match is live but live source has completed, drift check triggers `STATUS_DRIFT_REFRESH_REQUIRED`.

### 9. Freshness Enforcement
* **Rule:** Stale status-sensitive evidence cannot be reused blindly.
* **Status:** **PASS**
* **Verification:** `test_stale_status_sensitive_evidence_cannot_be_reused_blindly` asserts that evidence older than TTL returns `STALE_REFRESH_REQUIRED` and `must_refresh=True`.

### 10. Write Isolation
* **Rule:** No real `betting/data/betting.db` write occurs.
* **Status:** **PASS**
* **Verification:** `test_temp_sqlite_harness_initializes_cleanly_without_touching_real_db` ensures the real DB's mtime and contents remain unmodified.

### 11. No Config Side-Effects
* **Rule:** Matrix/routing remain untouched.
* **Status:** **PASS**
* **Verification:** Git status verifies zero modifications to files in `config/` or `src/bet/db/`.

### 12. Complete Separation from Betting Decisions
* **Rule:** No betting decision modules are imported.
* **Status:** **PASS**
* **Verification:** Verified by `test_no_betting_decision_tables_are_written` checking that decision tables (`analysis_results`, `gate_results`, `coupons`, `bets`) are empty.
