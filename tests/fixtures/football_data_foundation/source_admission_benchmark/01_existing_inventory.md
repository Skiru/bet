# Football Data Foundation - Existing Source Inventory

This inventory documents all 23 football data source integrations identified across 5 key categories within the repository structure.

## 1. Summary of Source Families

| Source Family | Category | Local Module Path | Status | Prior Claimed Capabilities |
| :--- | :--- | :--- | :--- | :--- |
| **espn_live_baseline** | Baseline | `src/bet/enrichment/football_data_foundation/active_enrichment.py` | ACCEPTED_BASELINE | Live score, form, lineup, metrics |
| **sportdb** | Shadow | `src/bet/api_clients/sportdb_mcp.py` | STRATEGIC_P2E | Detailed metrics (shadow only) |
| **football-data.org** | API Bridge | `open_reference_sources/football_data_org_bridge.py` | IMPLEMENTED_ACTIVE | Current fixtures and standings |
| **soccerdata_clubelo** | Scraper Wrapper | `soccerdata_sources/clubelo.py` | IMPLEMENTED_ACTIVE | Historical ELO ratings |
| **soccerdata_espn** | Scraper Wrapper | `soccerdata_sources/espn.py` | IMPLEMENTED_ACTIVE | Duplicated ESPN scheduler and lineups |
| **soccerdata_fbref** | Scraper Wrapper | `soccerdata_sources/fbref.py` | IMPLEMENTED_ACTIVE | Fragile league and player stats |
| **soccerdata_understat** | Scraper Wrapper | `soccerdata_sources/understat.py` | IMPLEMENTED_ACTIVE | Shot xG and match stats |
| **soccerdata_whoscored** | Scraper Wrapper | `soccerdata_sources/whoscored.py` | IMPLEMENTED_ACTIVE | Highly volatile match center statistics |
| **soccerdata_sofascore** | Scraper Wrapper | `soccerdata_sources/sofascore.py` | IMPLEMENTED_ACTIVE | Standings and schedules |
| **soccerdata_sofifa** | Scraper Wrapper | `soccerdata_sources/sofifa.py` | IMPLEMENTED_ACTIVE | Player and team FIFA rating cards |
| **soccerdata_matchhistory** | Scraper Wrapper | `soccerdata_sources/matchhistory.py` | IMPLEMENTED_ACTIVE | Head to head result rows |
| **soccerdata_fivethirtyeight** | Scraper Wrapper | `soccerdata_sources/fivethirtyeight.py` | NOT_SUPPORTED | Unavailable due to absent package classes |
| **statsbomb_open_data** | Local Parser | `open_reference_sources/statsbomb_open_data.py` | EVIDENCE_READY | Historical xG, event sequences, lineups |
| **statsbombpy** | API Wrapper | `open_reference_sources/statsbombpy_bridge.py` | NOT_SUPPORTED | Absent dependency |
| **kaggle_european_soccer** | Local Parser | `open_reference_sources/kaggle_european_soccer.py` | EVIDENCE_READY | Historical match result rows |
| **openfootball** | Local Parser | `open_reference_sources/openfootball.py` | EVIDENCE_READY | Historical world cup fixture scheduling |
| **fotmob_probe** | Scraper | `rich_unofficial_sources/fotmob_probe.py` | NOT_SUPPORTED | Missing live selectable evidence |
| **sofascore_rich_probe** | Scraper | `rich_unofficial_sources/sofascore_rich_probe.py` | NOT_SUPPORTED | Missing live selectable evidence |
| **scraperfc_sofascore** | Scraper Wrapper | `rich_unofficial_sources/scraperfc_sofascore_bridge.py` | NOT_SUPPORTED | Absent dependency |
| **socceraction** | Converter | `event_model_bridges/socceraction_bridge.py` | NOT_SUPPORTED | Absent dependency |
| **kloppy** | Loader | `event_model_bridges/kloppy_bridge.py` | NOT_SUPPORTED | Absent dependency |
| **floodlight** | Loader | `event_model_bridges/floodlight_bridge.py` | NOT_SUPPORTED | Absent dependency |
| **mplsoccer** | Visualizer | `event_model_bridges/mplsoccer_bridge.py` | NOT_SUPPORTED | Absent dependency |

## 2. Cannot Admit Yet Analysis

Every source family, except the accepted ESPN live baseline, is constrained by one or more hard blockers preventing production routing:
1. **Missing Offline Fixtures / Evidence:** All `soccerdata` wrappers and `football-data.org` lack local test fixtures to verify parser reliability without initiating network connections.
2. **Missing Dependencies:** `statsbombpy`, `scraperfc_sofascore`, `socceraction`, `kloppy`, `floodlight`, and `mplsoccer` have import blocks because their optional external libraries are not present in this runtime.
3. **Volatility & Fragility:** Browser-scraping wrappers like `soccerdata_whoscored` cannot be admitted as primary routes due to compliance and selector volatility risks.
4. **Offline Limitation:** Excellent historical parsers (`statsbomb_open_data`, `kaggle_european_soccer`) have zero current live coverage capability.
