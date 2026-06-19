# Football Data Foundation and Connector Kernel

This document provides a comprehensive report of the newly implemented production-grade Football Data Foundation and its shared Connector Kernel.

## 1. Unified Connector Kernel Summary
The shared Connector Kernel establishes strict architectural boundaries between data discovery, transport, parsing, and normalization. By channeling all providers through a single protocol, we eliminate loose, hard-to-maintain adapters.

- **Access Declarations (`access.py` / `capabilities.py`):** Explicitly defines required packages, environment variables, credentials, and scopes before any execution.
- **Transport Layer (`transport.py`):** Handles safe, test-friendly reading of filesystem objects and API endpoints.
- **Deserializer (`deserialization.py`):** Safely parses raw JSON, CSV, or SQLite streams into native python data frames/dictionaries.
- **Normalizer (`normalization.py`):** Flattens multi-index columns deterministically, preserves original IDs/names, and treats missing values as `UNKNOWN` rather than coercing them to `0`.
- **Evidence Packaging (`evidence.py`):** Every successful/partial operation generates a deterministic atomic evidence identity verifying the integrity of the data.
- **State Tracker (`state.py` / `pagination.py`):** Enforces explicit pagination and tracking models (`NO_PAGINATION`, `PAGE_NUMBER`, `CURSOR`, `DATE_WINDOW`, `SEASON_SCOPE`, `FILE_TREE`).
- **Drift Classification (`drift.py`):** Classifies schema updates into `ADDITIVE_SCHEMA_DRIFT` (safe; preserves execution status) or `BREAKING_SCHEMA_DRIFT` (quarantines affected elements).

---

## 2. Integrated Source Coverage Matrix
All 21 sources listed below have been successfully implemented and integrated:

| Source ID | Group | Access Model | Transport Type | Pagination Model | Dependencies | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ClubElo** | SoccerData | Public URL | Official API | `NO_PAGINATION` | `soccerdata` | `IMPLEMENTED_ACTIVE` |
| **ESPN** | SoccerData | Public URL | Unofficial API | `SEASON_SCOPE` | `soccerdata` | `IMPLEMENTED_ACTIVE` |
| **FBref** | SoccerData | Public URL | Metadata API | `SEASON_SCOPE` | `soccerdata` | `IMPLEMENTED_ACTIVE` |
| **FiveThirtyEight** | SoccerData | None (Retired) | Official API | `NO_PAGINATION` | `soccerdata` | `NOT_SUPPORTED` |
| **MatchHistory** | SoccerData | Public URL | Metadata API | `SEASON_SCOPE` | `soccerdata` | `IMPLEMENTED_ACTIVE` |
| **Sofascore** | SoccerData | Public URL | Metadata API | `SEASON_SCOPE` | `soccerdata` | `IMPLEMENTED_ACTIVE` |
| **SoFIFA** | SoccerData | Public URL | Metadata API | `SEASON_SCOPE` | `soccerdata` | `IMPLEMENTED_ACTIVE` |
| **Understat** | SoccerData | Public URL | Unofficial API | `SEASON_SCOPE` | `soccerdata` | `IMPLEMENTED_ACTIVE` |
| **WhoScored** | SoccerData | Public URL | Browser Scraper | `SEASON_SCOPE` | `soccerdata` | `IMPLEMENTED_ACTIVE` |
| **StatsBombOpenData** | Open/Reference | Local JSON | File System | `FILE_TREE` | None | `EVIDENCE_READY` |
| **StatsBombPy** | Open/Reference | API Key | Official API | `NO_PAGINATION` | `statsbombpy` | `SELECTABLE_CANDIDATE` |
| **KaggleEuropeanSoccer** | Open/Reference | Local SQLite | File System | `NO_PAGINATION` | `sqlite3` | `EVIDENCE_READY` |
| **FootballDataOrg** | Open/Reference | API Key | Official API | `NO_PAGINATION` | None | `CERTIFIED_SELECTABLE` |
| **OpenFootball** | Open/Reference | Local JSON | File System | `NO_PAGINATION` | None | `EVIDENCE_READY` |
| **FotMobProbe** | Rich Unofficial | Public URL | Unofficial API | `NO_PAGINATION` | None | `SELECTABLE_CANDIDATE` |
| **SofaScoreRichProbe** | Rich Unofficial | Public URL | Browser Scraper | `NO_PAGINATION` | None | `SELECTABLE_CANDIDATE` |
| **ScraperFCSofascore** | Rich Unofficial | Public URL | Browser Scraper | `NO_PAGINATION` | `ScraperFC` | `NOT_SUPPORTED` |
| **SoccerAction** | Event Bridge | Computation | Computation | `NO_PAGINATION` | `socceraction` | `NOT_SUPPORTED` |
| **Kloppy** | Event Bridge | Computation | Computation | `NO_PAGINATION` | `kloppy` | `NOT_SUPPORTED` |
| **Floodlight** | Event Bridge | Computation | Computation | `NO_PAGINATION` | `floodlight` | `NOT_SUPPORTED` |
| **MplSoccer** | Event Bridge | Computation | Computation | `NO_PAGINATION` | `mplsoccer` | `NOT_SUPPORTED` |

---

## 3. Drift Classification & Recovery Protocol
The kernel incorporates a strict anti-fragility strategy:
1. **Schema Check:** Compares execution columns against registered golden schema.
2. **Additive Schema Drift:** If new columns are introduced, the operation remains active and logs warnings.
3. **Breaking Schema Drift:** If expected columns disappear, the operation is immediately quarantined to protect downstream calculations.
4. **Offline Replay Recovery:** Enables test execution without live network dependencies, protecting our budget and ensuring safety.

---

## 4. Comparison & Integration with Existing Configs
The capability matrix in `provider_capability_matrix.json` was updated in a strictly additive manner. No existing production routes (`espn` or `football-data` scopes) were modified or replaced. This preserves current orchestration stability while unlocking a rich pipeline of candidate and shadow data.

---

## 5. Value Addition & Predictive Sanity
- **Immediate Enrichment Value:** Standardizes MultiIndex flattening, enables robust offline test coverage via deterministic atomic evidence, and offers complete diagnostic tracing for over 20 external football source APIs.
- **Betting Predictor Safety:** **NO BETTING PREDICTION OR DECISION LOGIC HAS BEEN CHANGED.** All modifications are strictly confined to data access, contracts, and schema normalization.
