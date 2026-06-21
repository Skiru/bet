# Football Data Foundation - Corrected L2B Source Value Scorecard

| Source Family | Proof Level | Real Facts | Contract Facts | Docs Summary | Recommended Role | Confidence | Next Action |
| :--- | :--- | :---: | :---: | :--- | :--- | :---: | :--- |
| **espn_live_baseline** | REAL_ACCEPTED_ARTIFACT_PROOF | 156 | 0 | Official high-frequency live match scorecard. | ACCEPTED_BASELINE | high | MAINTAIN |
| **sportdb** | SYNTHETIC_CONTRACT_PROOF | 0 | 1 | Provides leagues, matches, standings, and matchday live scoring capability. | REFERENCE_CANDIDATE | medium | OFFLINE_CONTRACT_WORK |
| **football-data.org** | SYNTHETIC_CONTRACT_PROOF | 0 | 2 | Provides leagues, matches, standings, and matchday live scoring capability. | CURRENT_SHADOW_CANDIDATE | medium | CREDENTIAL_SETUP |
| **soccerdata_clubelo** | SYNTHETIC_CONTRACT_PROOF | 0 | 2 | ClubElo historical team ratings. | CONNECTOR_REPLAY_CANDIDATE | medium | IMPLEMENT_CONNECTOR_REPLAY |
| **soccerdata_espn** | SYNTHETIC_CONTRACT_PROOF | 0 | 1 | ESPN lineups and statistics scraper. | CONNECTOR_REPLAY_CANDIDATE | medium | IMPLEMENT_CONNECTOR_REPLAY |
| **soccerdata_fbref** | SYNTHETIC_CONTRACT_PROOF | 0 | 1 | FBref team and player match/season statistics. | CONNECTOR_REPLAY_CANDIDATE | medium | IMPLEMENT_CONNECTOR_REPLAY |
| **soccerdata_understat** | SYNTHETIC_CONTRACT_PROOF | 0 | 1 | Understat team match statistics and shot-event coordinates. | CONNECTOR_REPLAY_CANDIDATE | medium | IMPLEMENT_CONNECTOR_REPLAY |
| **soccerdata_whoscored** | DOCS_CAPABILITY_ONLY | 0 | 0 | Scrapers for schedules, injuries, standings, and historical results. | OFFLINE_EVIDENCE_ONLY | low | DEFER_REAL_PROOF_REQUIRED |
| **soccerdata_sofascore** | DOCS_CAPABILITY_ONLY | 0 | 0 | Scrapers for schedules, injuries, standings, and historical results. | OFFLINE_EVIDENCE_ONLY | low | DEFER_REAL_PROOF_REQUIRED |
| **soccerdata_sofifa** | DOCS_CAPABILITY_ONLY | 0 | 0 | Scrapers for schedules, injuries, standings, and historical results. | OFFLINE_EVIDENCE_ONLY | low | DEFER_REAL_PROOF_REQUIRED |
| **soccerdata_matchhistory** | DOCS_CAPABILITY_ONLY | 0 | 0 | Scrapers for schedules, injuries, standings, and historical results. | OFFLINE_EVIDENCE_ONLY | low | DEFER_REAL_PROOF_REQUIRED |
| **soccerdata_fivethirtyeight** | DOCS_CAPABILITY_ONLY | 0 | 0 | Retired soccer predictions. | REJECT_LOW_VALUE | low | NONE |
| **statsbomb_open_data** | REAL_LOCAL_OPEN_DATA_PROOF | 5 | 0 | StatsBomb events, lineups, and threesixty metadata. | HISTORICAL_ENRICHMENT_CANDIDATE | high | ADMIT_HISTORICAL |
| **statsbombpy** | DOCS_CAPABILITY_ONLY | 0 | 0 | Advanced open event/tracking libraries. | DEPENDENCY_BLOCKED | low | DEFER_DEPENDENCY_REQUIRED |
| **kaggle_european_soccer** | REAL_LOCAL_OPEN_DATA_PROOF | 2 | 0 | Kaggle European matches database. | HISTORICAL_ENRICHMENT_CANDIDATE | high | ADMIT_HISTORICAL |
| **openfootball** | REAL_LOCAL_OPEN_DATA_PROOF | 1 | 0 | OpenFootball World Cup schedule schemas. | REFERENCE_CANDIDATE | high | ADMIT_REFERENCE |
| **fotmob_probe** | DOCS_CAPABILITY_ONLY | 0 | 0 | Unofficial web API match events and statistics. | OFFLINE_EVIDENCE_ONLY | low | DEFER_PARSER_REPAIR_REQUIRED |
| **sofascore_rich_probe** | DOCS_CAPABILITY_ONLY | 0 | 0 | Unofficial web API match events and statistics. | OFFLINE_EVIDENCE_ONLY | low | DEFER_PARSER_REPAIR_REQUIRED |
| **scraperfc_sofascore** | DOCS_CAPABILITY_ONLY | 0 | 0 | Advanced open event/tracking libraries. | DEPENDENCY_BLOCKED | low | DEFER_DEPENDENCY_REQUIRED |
| **socceraction** | DOCS_CAPABILITY_ONLY | 0 | 0 | Advanced open event/tracking libraries. | DEPENDENCY_BLOCKED | low | DEFER_DEPENDENCY_REQUIRED |
| **kloppy** | DOCS_CAPABILITY_ONLY | 0 | 0 | Advanced open event/tracking libraries. | DEPENDENCY_BLOCKED | low | DEFER_DEPENDENCY_REQUIRED |
| **floodlight** | DOCS_CAPABILITY_ONLY | 0 | 0 | Advanced open event/tracking libraries. | DEPENDENCY_BLOCKED | low | DEFER_DEPENDENCY_REQUIRED |
| **mplsoccer** | DOCS_CAPABILITY_ONLY | 0 | 0 | Advanced open event/tracking libraries. | DEPENDENCY_BLOCKED | low | DEFER_DEPENDENCY_REQUIRED |
