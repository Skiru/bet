# Full Source Coverage Checklist — Pass 1

All 23 required football enrichment sources have been implemented with formal skeletons and contract descriptors under `src/bet/enrichment/football_data_foundation/`:

- [x] **ESPN accepted baseline** (`espn-accepted-baseline`) - Benchmark baseline with real accepted artifact proof.
- [x] **Highlightly** (`highlightly`) - Live/recent detailed shadow provider with credentials gate.
- [x] **SportDB** (`sportdb`) - Live current provider with API header and key requirements.
- [x] **football-data.org** (`football-data-org`) - Reference metadata current provider.
- [x] **API-Football** (`api-football`) - Deferred candidate provider.
- [x] **TheSportsDB** (`thesportsdb`) - Reference metadata shadow provider.
- [x] **StatsBomb Open Data** (`statsbomb-open-data`) - Historical local open-data with shot and event counting.
- [x] **statsbombpy** (`statsbombpy`) - Optional library bridge.
- [x] **OpenFootball** (`openfootball`) - Reference identity dataset.
- [x] **Kaggle European Soccer** (`kaggle-european-soccer`) - Deep historical dataset with temporal decay requirements.
- [x] **sport.db open-source tooling** (`sportdb-open-source-tooling`) - Optional text database tooling.
- [x] **soccerdata ClubElo** (`soccerdata-clubelo`) - Replay rating wrapper.
- [x] **soccerdata ESPN** (`soccerdata-espn`) - Replay reference wrapper.
- [x] **soccerdata FBref** (`soccerdata-fbref`) - Replay statistic wrapper.
- [x] **soccerdata FiveThirtyEight** (`soccerdata-fivethirtyeight`) - Replay legacy prior wrapper with staleness warning.
- [x] **soccerdata MatchHistory** (`soccerdata-matchhistory`) - Replay odds reference wrapper with odds reference marker.
- [x] **soccerdata Sofascore** (`soccerdata-sofascore`) - Replay statistic wrapper.
- [x] **soccerdata SoFIFA** (`soccerdata-sofifa`) - Replay player context wrapper.
- [x] **soccerdata Understat** (`soccerdata-understat`) - Replay xG wrapper.
- [x] **soccerdata WhoScored** (`soccerdata-whoscored`) - Replay statistic wrapper (docs-only).
- [x] **FotMob probe** (`fotmob-probe`) - Experimental unofficial probe.
- [x] **SofaScore rich probe** (`sofascore-rich-probe`) - Experimental rich unofficial probe.
- [x] **ScraperFC SofaScore bridge** (`scraperfc-sofascore-bridge`) - Experimental bridge probe.

## Verification Status

All sources have been validated against:
1. `test_kernel_contracts.py` - Core constraints on ProofLevel, SourceRole, FactType, and PayloadPolicy.
2. `test_provider_contract_catalog.py` - Uniqueness, shadow-only constraints, and absence of production selection.
3. `test_provider_contract_current.py` - Credentials checks and specific replay proofs.
4. `test_open_data_contract_adapters.py` - Local parsing, optional imports, and decay rules.
5. `test_soccerdata_replay_contracts.py` - Wrapper-specific capabilities and markers.
6. `test_probe_contracts.py` - Unofficial probe constraints and isolation.
