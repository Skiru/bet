# Football Data Foundation - Corrected L2B Admission Decision Matrix

| Source Family | Corrected Decision | Exact Reason | Next Phase Kind |
| :--- | :--- | :--- | :--- |
| **espn_live_baseline** | ADMIT_NEXT_PHASE_CURRENT_SHADOW | Official live validation baseline. | current shadow fusion |
| **sportdb** | DEFER_CREDENTIAL_REQUIRED | Offline contract compatibility proven via synthetic fixture, but credentials are required for live integration. | credential/live proof setup |
| **football-data.org** | DEFER_CREDENTIAL_REQUIRED | Offline contract compatibility proven via synthetic fixture, but credentials are required for live integration. | credential/live proof setup |
| **soccerdata_clubelo** | DEFER_CONNECTOR_REPLAY_CAPTURE | Synthetic contract proof validated, but requires real-world replay capture before implementation. | real replay capture phase |
| **soccerdata_espn** | DEFER_CONNECTOR_REPLAY_CAPTURE | Synthetic contract proof validated, but requires real-world replay capture before implementation. | real replay capture phase |
| **soccerdata_fbref** | DEFER_CONNECTOR_REPLAY_CAPTURE | Synthetic contract proof validated, but requires real-world replay capture before implementation. | real replay capture phase |
| **soccerdata_understat** | DEFER_CONNECTOR_REPLAY_CAPTURE | Synthetic contract proof validated, but requires real-world replay capture before implementation. | real replay capture phase |
| **soccerdata_whoscored** | DEFER_REAL_PROOF_REQUIRED | Scraping blocks current live. Lacks local offline replay fixtures for contract safety validation. | offline contract fixture |
| **soccerdata_sofascore** | DEFER_REAL_PROOF_REQUIRED | Scraping blocks current live. Lacks local offline replay fixtures for contract safety validation. | offline contract fixture |
| **soccerdata_sofifa** | DEFER_REAL_PROOF_REQUIRED | Scraping blocks current live. Lacks local offline replay fixtures for contract safety validation. | offline contract fixture |
| **soccerdata_matchhistory** | DEFER_REAL_PROOF_REQUIRED | Scraping blocks current live. Lacks local offline replay fixtures for contract safety validation. | offline contract fixture |
| **soccerdata_fivethirtyeight** | REJECT_LOW_VALUE | Retired predication platform. | none |
| **statsbomb_open_data** | ADMIT_NEXT_PHASE_HISTORICAL_ENRICHMENT | Measured offline open data values exist. | historical enrichment backfill |
| **statsbombpy** | DEFER_REAL_PROOF_REQUIRED | Optional library dependencies are absent in current environment. | dependency setup |
| **kaggle_european_soccer** | ADMIT_NEXT_PHASE_HISTORICAL_ENRICHMENT | Measured offline open data values exist. | historical enrichment backfill |
| **openfootball** | ADMIT_NEXT_PHASE_REFERENCE | Measured offline reference datasets exist. | reference identity bridge |
| **fotmob_probe** | DEFER_REAL_PROOF_REQUIRED | Available local offline fixtures exist but yield zero facts due to parsing gaps; requires parser repair. | parser repair |
| **sofascore_rich_probe** | DEFER_REAL_PROOF_REQUIRED | Available local offline fixtures exist but yield zero facts due to parsing gaps; requires parser repair. | parser repair |
| **scraperfc_sofascore** | DEFER_REAL_PROOF_REQUIRED | Optional library dependencies are absent in current environment. | dependency setup |
| **socceraction** | DEFER_REAL_PROOF_REQUIRED | Optional library dependencies are absent in current environment. | dependency setup |
| **kloppy** | DEFER_REAL_PROOF_REQUIRED | Optional library dependencies are absent in current environment. | dependency setup |
| **floodlight** | DEFER_REAL_PROOF_REQUIRED | Optional library dependencies are absent in current environment. | dependency setup |
| **mplsoccer** | DEFER_REAL_PROOF_REQUIRED | Optional library dependencies are absent in current environment. | dependency setup |
