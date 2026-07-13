# Football Data Foundation - Admission Decision Matrix

Definitive admission statuses and role assignments for the subsequent integration phases.

| Source Family | Decision | Exact Reason | Next Phase Kind |
| :--- | :--- | :--- | :--- |
| **espn_live_baseline** | ADMIT_NEXT_PHASE_CURRENT_SHADOW | Official live production baseline platform. Extracted high-frequency live match metrics. | current shadow fusion |
| **sportdb** | DEFER_CREDENTIAL_REQUIRED | Metadata configuration exists, but lacks credentials and physical foundation integration module. | credential setup |
| **football-data.org** | DEFER_CREDENTIAL_REQUIRED | API client exists but remains deferred due to missing live credentials and validation. | credential setup |
| **soccerdata_clubelo** | ADMIT_OFFLINE_EVIDENCE_ONLY | Scraping-only blocks current live primary role. Preserved as offline evidence only. | rejection/no action |
| **soccerdata_espn** | ADMIT_OFFLINE_EVIDENCE_ONLY | Scraping-only blocks current live primary role. Preserved as offline evidence only. | rejection/no action |
| **soccerdata_fbref** | ADMIT_OFFLINE_EVIDENCE_ONLY | Scraping-only blocks current live primary role. Preserved as offline evidence only. | rejection/no action |
| **soccerdata_understat** | ADMIT_OFFLINE_EVIDENCE_ONLY | Scraping-only blocks current live primary role. Preserved as offline evidence only. | rejection/no action |
| **soccerdata_whoscored** | ADMIT_OFFLINE_EVIDENCE_ONLY | Scraping-only blocks current live primary role. Preserved as offline evidence only. | rejection/no action |
| **soccerdata_sofascore** | ADMIT_OFFLINE_EVIDENCE_ONLY | Scraping-only blocks current live primary role. Preserved as offline evidence only. | rejection/no action |
| **soccerdata_sofifa** | ADMIT_OFFLINE_EVIDENCE_ONLY | Scraping-only blocks current live primary role. Preserved as offline evidence only. | rejection/no action |
| **soccerdata_matchhistory** | ADMIT_OFFLINE_EVIDENCE_ONLY | Scraping-only blocks current live primary role. Preserved as offline evidence only. | rejection/no action |
| **soccerdata_fivethirtyeight** | REJECT_LOW_VALUE | No offline fixtures or usable dependency available, yielding zero canonical facts. | rejection/no action |
| **statsbomb_open_data** | ADMIT_NEXT_PHASE_HISTORICAL_ENRICHMENT | Offline parsing proof successfully yields rich event sequences, lineups, shot coordinates, and 360 freeze frames. | historical enrichment backfill |
| **statsbombpy** | DEFER_DEPENDENCY_REQUIRED | Optional dependencies statsbombpy are absent in test environment. | rejection/no action |
| **kaggle_european_soccer** | ADMIT_NEXT_PHASE_HISTORICAL_ENRICHMENT | Offline matches CSV parsing successfully yields historical scores and team API mapping data. | historical enrichment backfill |
| **openfootball** | ADMIT_NEXT_PHASE_REFERENCE | Offline World Cup JSON schedule successfully yields matchday schedule scheduling. | reference identity bridge |
| **fotmob_probe** | REJECT_LOW_VALUE | No offline fixtures or usable dependency available, yielding zero canonical facts. | rejection/no action |
| **sofascore_rich_probe** | REJECT_LOW_VALUE | No offline fixtures or usable dependency available, yielding zero canonical facts. | rejection/no action |
| **scraperfc_sofascore** | DEFER_DEPENDENCY_REQUIRED | Optional dependencies scraperfc_sofascore are absent in test environment. | rejection/no action |
| **socceraction** | DEFER_DEPENDENCY_REQUIRED | Optional dependencies socceraction are absent in test environment. | rejection/no action |
| **kloppy** | DEFER_DEPENDENCY_REQUIRED | Optional dependencies kloppy are absent in test environment. | rejection/no action |
| **floodlight** | DEFER_DEPENDENCY_REQUIRED | Optional dependencies floodlight are absent in test environment. | rejection/no action |
| **mplsoccer** | DEFER_DEPENDENCY_REQUIRED | Optional dependencies mplsoccer are absent in test environment. | rejection/no action |
