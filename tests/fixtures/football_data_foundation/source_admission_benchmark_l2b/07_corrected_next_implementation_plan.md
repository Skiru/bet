# Football Data Foundation - Corrected L2B Next Implementation Plan

Strict sequence of subsequently scheduled implementation phases based solely on corrected L2B decisions.
The following schedule enforces proof-strength ordered progression, separating synthetic contract validation
and docs-only capabilities from actual implementation readiness.

| Sequence | Source Family | Decision | Next Phase Kind | Rationale |
| :---: | :--- | :--- | :--- | :--- |
| 1 | **espn_live_baseline** | ADMIT_NEXT_PHASE_CURRENT_SHADOW | current shadow fusion | Official live validation baseline. |
| 2 | **statsbomb_open_data** | ADMIT_NEXT_PHASE_HISTORICAL_ENRICHMENT | historical enrichment backfill | Measured offline open data values exist. |
| 3 | **kaggle_european_soccer** | ADMIT_NEXT_PHASE_HISTORICAL_ENRICHMENT | historical enrichment backfill | Measured offline open data values exist. |
| 4 | **openfootball** | ADMIT_NEXT_PHASE_REFERENCE | reference identity bridge | Measured offline reference datasets exist. |
| 5 | **sportdb** | DEFER_CREDENTIAL_REQUIRED | credential/live proof setup | Offline contract compatibility proven via synthetic fixture, but credentials are required for live integration. |
| 6 | **football-data.org** | DEFER_CREDENTIAL_REQUIRED | credential/live proof setup | Offline contract compatibility proven via synthetic fixture, but credentials are required for live integration. |
| 7 | **soccerdata_clubelo** | DEFER_CONNECTOR_REPLAY_CAPTURE | real replay capture phase | Synthetic contract proof validated, but requires real-world replay capture before implementation. |
| 8 | **soccerdata_espn** | DEFER_CONNECTOR_REPLAY_CAPTURE | real replay capture phase | Synthetic contract proof validated, but requires real-world replay capture before implementation. |
| 9 | **soccerdata_fbref** | DEFER_CONNECTOR_REPLAY_CAPTURE | real replay capture phase | Synthetic contract proof validated, but requires real-world replay capture before implementation. |
| 10 | **soccerdata_understat** | DEFER_CONNECTOR_REPLAY_CAPTURE | real replay capture phase | Synthetic contract proof validated, but requires real-world replay capture before implementation. |
| 11 | **fotmob_probe** | DEFER_REAL_PROOF_REQUIRED | parser repair | Available local offline fixtures exist but yield zero facts due to parsing gaps; requires parser repair. |
| 12 | **sofascore_rich_probe** | DEFER_REAL_PROOF_REQUIRED | parser repair | Available local offline fixtures exist but yield zero facts due to parsing gaps; requires parser repair. |

## Sequence Tradeoffs & Rationale
1. **Stage 1 (Maintenance)**: Keep ESPN Live Baseline active and monitored.
2. **Stage 2 (Real Open Data)**: StatsBomb, Kaggle and OpenFootball have local high-value evidence.
3. **Stage 3 (Credential/API Setup)**: football-data.org and SportDB need API keys and real live proof.
4. **Stage 4 (Replay Capture)**: Scraper connectors (ClubElo, ESPN, FBref, Understat) must do real replay capture before any implementation.
5. **Stage 5 (Parser Repairs)**: Fotmob and Sofascore require code fixes to resolve parsing gaps.

### Safety Constraints Check
- No scraper is run directly against live networks during execution.
- No uncredentialed live-api connectors are admitted as selectable.
