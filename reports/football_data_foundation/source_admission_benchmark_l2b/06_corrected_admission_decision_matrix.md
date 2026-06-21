# Football Data Foundation - Corrected L2B Admission Decision Matrix

| Source Family | Corrected Decision | Exact Reason | Next Phase Kind |
| :--- | :--- | :--- | :--- |
| **espn_live_baseline** | ADMIT_NEXT_PHASE_CURRENT_SHADOW | Official live validation baseline. | current shadow fusion |
| **sportdb** | DEFER_CREDENTIAL_REQUIRED | Offline contract compatibility proven via synthetic fixture, but credentials are required for live integration. | credential setup |
| **football-data.org** | DEFER_CREDENTIAL_REQUIRED | Offline contract compatibility proven via synthetic fixture, but credentials are required for live integration. | credential setup |
| **soccerdata_clubelo** | ADMIT_NEXT_PHASE_CONNECTOR_REPLAY | Synthetic replay proof validates offline parser contract shapes safely. | connector replay |
| **soccerdata_espn** | ADMIT_NEXT_PHASE_CONNECTOR_REPLAY | Synthetic replay proof validates offline parser contract shapes safely. | connector replay |
| **soccerdata_fbref** | ADMIT_NEXT_PHASE_CONNECTOR_REPLAY | Synthetic replay proof validates offline parser contract shapes safely. | connector replay |
| **soccerdata_understat** | ADMIT_NEXT_PHASE_CONNECTOR_REPLAY | Synthetic replay proof validates offline parser contract shapes safely. | connector replay |
| **soccerdata_whoscored** | DEFER_REAL_PROOF_REQUIRED | Scraping blocks current live. Lacks local offline replay fixtures for contract safety validation. | offline contract fixture |
| **soccerdata_sofascore** | DEFER_REAL_PROOF_REQUIRED | Scraping blocks current live. Lacks local offline replay fixtures for contract safety validation. | offline contract fixture |
| **soccerdata_sofifa** | DEFER_REAL_PROOF_REQUIRED | Scraping blocks current live. Lacks local offline replay fixtures for contract safety validation. | offline contract fixture |
| **soccerdata_matchhistory** | DEFER_REAL_PROOF_REQUIRED | Scraping blocks current live. Lacks local offline replay fixtures for contract safety validation. | offline contract fixture |
| **soccerdata_fivethirtyeight** | REJECT_LOW_VALUE | Retired predication platform. | none |
| **statsbomb_open_data** | ADMIT_NEXT_PHASE_HISTORICAL_ENRICHMENT | Measured offline open data values exist. | historical enrichment backfill |
| **statsbombpy** | DEFER_DEPENDENCY_REQUIRED | Optional library dependencies are absent in current test environment. | dependency setup |
| **kaggle_european_soccer** | ADMIT_NEXT_PHASE_HISTORICAL_ENRICHMENT | Measured offline open data values exist. | historical enrichment backfill |
| **openfootball** | ADMIT_NEXT_PHASE_REFERENCE | Measured offline reference datasets exist. | reference identity bridge |
| **fotmob_probe** | DEFER_PARSER_REPAIR_REQUIRED | Available local offline fixtures exist but yield zero facts due to parsing gaps. | parser repair |
| **sofascore_rich_probe** | DEFER_PARSER_REPAIR_REQUIRED | Available local offline fixtures exist but yield zero facts due to parsing gaps. | parser repair |
| **scraperfc_sofascore** | DEFER_DEPENDENCY_REQUIRED | Optional library dependencies are absent in current test environment. | dependency setup |
| **socceraction** | DEFER_DEPENDENCY_REQUIRED | Optional library dependencies are absent in current test environment. | dependency setup |
| **kloppy** | DEFER_DEPENDENCY_REQUIRED | Optional library dependencies are absent in current test environment. | dependency setup |
| **floodlight** | DEFER_DEPENDENCY_REQUIRED | Optional library dependencies are absent in current test environment. | dependency setup |
| **mplsoccer** | DEFER_DEPENDENCY_REQUIRED | Optional library dependencies are absent in current test environment. | dependency setup |
