# Football Data Foundation - Corrected L2B Next Implementation Plan

Strict sequence of subsequently scheduled implementation phases based solely on corrected L2B decisions.

| Sequence | Source Family | Decision | Next Phase Kind | Rationale |
| :---: | :--- | :--- | :--- | :--- |
| 1 | **espn_live_baseline** | ADMIT_NEXT_PHASE_CURRENT_SHADOW | current shadow fusion | Official live validation baseline. |
| 2 | **soccerdata_clubelo** | ADMIT_NEXT_PHASE_CONNECTOR_REPLAY | connector replay | Synthetic replay proof validates offline parser contract shapes safely. |
| 3 | **soccerdata_espn** | ADMIT_NEXT_PHASE_CONNECTOR_REPLAY | connector replay | Synthetic replay proof validates offline parser contract shapes safely. |
| 4 | **soccerdata_fbref** | ADMIT_NEXT_PHASE_CONNECTOR_REPLAY | connector replay | Synthetic replay proof validates offline parser contract shapes safely. |
| 5 | **soccerdata_understat** | ADMIT_NEXT_PHASE_CONNECTOR_REPLAY | connector replay | Synthetic replay proof validates offline parser contract shapes safely. |
| 6 | **statsbomb_open_data** | ADMIT_NEXT_PHASE_HISTORICAL_ENRICHMENT | historical enrichment backfill | Measured offline open data values exist. |
| 7 | **kaggle_european_soccer** | ADMIT_NEXT_PHASE_HISTORICAL_ENRICHMENT | historical enrichment backfill | Measured offline open data values exist. |
| 8 | **openfootball** | ADMIT_NEXT_PHASE_REFERENCE | reference identity bridge | Measured offline reference datasets exist. |

## Sequence Tradeoffs & Rationale
1. **ESPN Live Baseline** remains active baseline platform.
2. **Open Data (StatsBomb/Kaggle/OpenFootball)** admitted directly due to high real value open-data proof.
3. **Scraper Connectors (ClubElo/ESPN/FBref/Understat)** admitted strictly for offline connector replay verification, preventing unsafe live network queries.
