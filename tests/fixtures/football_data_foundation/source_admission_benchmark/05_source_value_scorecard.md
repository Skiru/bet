# Football Data Foundation - Source Value Scorecard

Calculated dynamic capabilities scores and checked gate compliance across all families.

| Source Family | Recommended Role | Can Participate | Hard Gates Failed |
| :--- | :--- | :--- | :--- |
| **espn_live_baseline** | ACCEPTED_BASELINE | True | None |
| **sportdb** | METADATA_ONLY | False | missing_credential_blocks_live_api_proof, no_identity_fields, no_temporal_fields |
| **football-data.org** | CURRENT_SHADOW_CANDIDATE | False | missing_credential_blocks_live_api_proof, no_identity_fields, no_temporal_fields |
| **soccerdata_clubelo** | OFFLINE_EVIDENCE_ONLY | False | historical_dataset_cannot_confirm_current_live_score, no_identity_fields, scraping_only_blocks_current_primary |
| **soccerdata_espn** | OFFLINE_EVIDENCE_ONLY | False | no_identity_fields, no_temporal_fields, scraping_only_blocks_current_primary |
| **soccerdata_fbref** | OFFLINE_EVIDENCE_ONLY | False | no_identity_fields, no_temporal_fields, scraping_only_blocks_current_primary |
| **soccerdata_understat** | OFFLINE_EVIDENCE_ONLY | False | no_identity_fields, no_temporal_fields, scraping_only_blocks_current_primary |
| **soccerdata_whoscored** | OFFLINE_EVIDENCE_ONLY | False | no_identity_fields, no_temporal_fields, scraping_only_blocks_current_primary |
| **soccerdata_sofascore** | OFFLINE_EVIDENCE_ONLY | False | no_identity_fields, no_temporal_fields, scraping_only_blocks_current_primary |
| **soccerdata_sofifa** | OFFLINE_EVIDENCE_ONLY | False | historical_dataset_cannot_confirm_current_live_score, no_identity_fields, scraping_only_blocks_current_primary |
| **soccerdata_matchhistory** | OFFLINE_EVIDENCE_ONLY | False | historical_dataset_cannot_confirm_current_live_score, no_identity_fields, scraping_only_blocks_current_primary |
| **soccerdata_fivethirtyeight** | OFFLINE_EVIDENCE_ONLY | False | None |
| **statsbomb_open_data** | HISTORICAL_ENRICHMENT_CANDIDATE | True | historical_dataset_cannot_confirm_current_live_score |
| **statsbombpy** | DEPENDENCY_BLOCKED | False | dependency_missing, no_facts_extracted, no_identity_fields, no_temporal_fields |
| **kaggle_european_soccer** | HISTORICAL_ENRICHMENT_CANDIDATE | True | historical_dataset_cannot_confirm_current_live_score |
| **openfootball** | REFERENCE_CANDIDATE | True | historical_dataset_cannot_confirm_current_live_score |
| **fotmob_probe** | OFFLINE_EVIDENCE_ONLY | False | no_facts_extracted |
| **sofascore_rich_probe** | OFFLINE_EVIDENCE_ONLY | False | no_facts_extracted |
| **scraperfc_sofascore** | DEPENDENCY_BLOCKED | False | dependency_missing, no_facts_extracted, no_identity_fields, no_temporal_fields |
| **socceraction** | DEPENDENCY_BLOCKED | False | dependency_missing, no_facts_extracted, no_identity_fields, no_temporal_fields |
| **kloppy** | DEPENDENCY_BLOCKED | False | dependency_missing, no_facts_extracted, no_identity_fields, no_temporal_fields |
| **floodlight** | DEPENDENCY_BLOCKED | False | dependency_missing, no_facts_extracted, no_identity_fields, no_temporal_fields |
| **mplsoccer** | DEPENDENCY_BLOCKED | False | dependency_missing, no_facts_extracted, no_identity_fields, no_temporal_fields |
