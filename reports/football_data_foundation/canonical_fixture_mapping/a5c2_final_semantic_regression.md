# A5C2 Final Semantic Regression Lock Report

## Overview
This report lists and locks the 16 crucial semantic invariants verified across the football data foundation canonical fixture mapping layer. All assertions are backed by concrete tests in `tests/enrichment/football_data_foundation/test_canonical_fixture_mapping.py` or explicit checks in `src/bet/enrichment/football_data_foundation/`.

---

## Verified Semantic Invariants

### 1. `scanner_event_id` Separate from `provider_event_id`
* **Status:** **PASS**
* **Evidence:** `test_resolver_creates_sport_competition_team_fixture_rows_and_mappings` asserts that scanner ID `'66456944'` remains separate and distinct from provider event ID `'760442'`.

### 2. ESPN `provider_event_id` remains 760442
* **Status:** **PASS**
* **Evidence:** World Cup USA vs Australia fixture uses the permanent ESPN event ID `'760442'` for verification.

### 3. Source `external_id` Conflict Fails Closed
* **Status:** **PASS**
* **Evidence:** `test_source_external_id_conflict_handling` verifies that mapping a source with conflicting external ID returns status `SOURCE_EXTERNAL_ID_CONFLICT` and prevents corruption.

### 4. No Hardcoded 'football' in Generic Resolver Paths
* **Status:** **PASS**
* **Evidence:** `test_future_non_world_cup_profile_integration` validates mapping EPL soccer datasets under non-World Cup profiles successfully.

### 5. `competition.country` Avoids Group Stage Labels
* **Status:** **PASS**
* **Evidence:** `test_competition_country_does_not_store_group_label` asserts that when scanner group label is `'Group D'`, the destination country stores null/None.

### 6. Team Alias Ambiguity Fails Closed
* **Status:** **PASS**
* **Evidence:** `test_team_alias_ambiguity_fails_closed` ensures that resolving an alias that matches multiple teams fails closed.

### 7. Natural Fixture Conflict Fails Closed
* **Status:** **PASS**
* **Evidence:** `test_natural_fixture_conflict_across_competition_returns_ambiguity` guarantees that resolving fixtures matching multiple competitions returns failure status.

### 8. Explicit Fact Scopes
* **Status:** **PASS**
* **Evidence:** `test_fact_scoping_and_duplication_flagging` confirms fact scopes map exclusively to `TEAM_HOME`, `TEAM_AWAY`, `FIXTURE_LEVEL`, or `UNKNOWN`.

### 9. Duplicated Fixture-level Facts Marked
* **Status:** **PASS**
* **Evidence:** `test_fact_scoping_and_duplication_flagging` asserts `duplicated_for_schema_team_id_constraint=true` is attached to duplicated fixture-level facts.

### 10. `source_operation_attempt` Integrity
* **Status:** **PASS**
* **Evidence:** `test_evidence_package_revision_member_count` confirms attempt state and operation status carry actual logs/responses rather than defaulting blindly to 200/COMPLETED.

### 11. Live-to-Final Drift Control
* **Status:** **PASS**
* **Evidence:** `test_live_to_final_status_drift` validates transition of match states returns `STATUS_DRIFT_REFRESH_REQUIRED`.

### 12. No Blind Reuse of Stale Status-Sensitive Evidence
* **Status:** **PASS**
* **Evidence:** `test_stale_status_sensitive_evidence_cannot_be_reused_blindly` handles expired TTL as `STALE_REFRESH_REQUIRED` requiring fresh retrieval.

### 13. Schema-only Stale Proof Requires Explicit Flag
* **Status:** **PASS**
* **Evidence:** Refresh parameters fail closed unless the CLI `--allow-stale-proof` flag is explicitly set.

### 14. No Real DB Writes
* **Status:** **PASS**
* **Evidence:** `test_temp_sqlite_harness_initializes_cleanly_without_touching_real_db` ensures `betting/data/betting.db` is completely untouched.

### 15. No Matrix/Routing/Config Activation
* **Status:** **PASS**
* **Evidence:** Source code analysis shows `config/provider_capability_matrix.json` and `config/football_routing.yaml` are unimported and unchanged.

### 16. No Imports of Betting Decision Modules
* **Status:** **PASS**
* **Evidence:** `test_no_betting_decision_tables_are_written` verifies that zero records are created in decision tables and zero imports from those modules exist.
