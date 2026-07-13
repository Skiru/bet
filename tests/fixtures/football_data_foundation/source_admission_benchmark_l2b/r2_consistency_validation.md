# Football Data Foundation - R2 Consistency Validation Report

This report audits the consistency of the L2B source admission scorecard, decision matrix, and implementation plan.

| Consistency Check | Status | Details |
| :--- | :--- | :--- |
| scorecard_completeness | **PASSED** | All 23 evaluated families are present in the scorecard. |
| scorecard_to_matrix_alignment | **PASSED** | All scorecard families have matching entries in the decision matrix. |
| plan_to_matrix_alignment | **PASSED** | All families in the implementation plan exist in the decision matrix. |
| real_value_facts_coherence | **PASSED** | Real value facts counts match perfectly across scorecard and evaluated results. |
| proof_level_to_decision_mapping | **PASSED** | Proof level matches decision type perfectly for all families. |
| no_synthetic_direct_admission | **PASSED** | No source supported solely by synthetic contract proof is directly admitted to implementation. |
| no_docs_only_direct_admission | **PASSED** | No source supported solely by docs capability is admitted to implementation. |
| no_credential_missing_admissions | **PASSED** | All credential-missing sources are deferred as DEFER_CREDENTIAL_REQUIRED. |
| no_dependency_missing_admissions | **PASSED** | All dependency-missing sources are blocked and excluded from the implementation plan. |
| programmatic_summary_consistency | **PASSED** | All markdown summary statistics and tables are programmatically derived from the same source of truth JSON objects. |

