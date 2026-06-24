# Football Enrichment Pass 1: Evidence Kernel & Source Contracts

This report defines the structural contracts, source roles, proof levels, and adapter specifications implemented in Pass 1 of the football enrichment pipeline.

## Architectural Overview

The Evidence Kernel is a typed and validated foundation that standardizes how various football data sources (current APIs, deep historical datasets, replay tools, libraries, and experimental probes) are ingested and represented as claims. It prevents common integration risks such as:
- Silently mixing historical or synthetic data with live current truth.
- Storing unverified or raw payloads inside the repository.
- Committing live access credentials or API tokens.

## Files Generated in Pass 1

- `reports/football_data_foundation/pass1_evidence_kernel/README.md` (this file)
- `reports/football_data_foundation/pass1_evidence_kernel/source_role_matrix.json`
- `reports/football_data_foundation/pass1_evidence_kernel/proof_level_contract.json`
- `reports/football_data_foundation/pass1_evidence_kernel/adapter_contract_summary.json`
- `reports/football_data_foundation/pass1_evidence_kernel/full_source_coverage_checklist.md`

## Complete Source Catalog

All 23 sources have been configured with formal source descriptors, provider identities, freshness policies, and payload rules:

1. **ESPN accepted baseline** (`espn-accepted-baseline`) - Benchmark anchor.
2. **Highlightly** (`highlightly`) - Detailed current live/recent shadow.
3. **SportDB** (`sportdb`) - Current live provider.
4. **football-data.org** (`football-data-org`) - Current reference metadata.
5. **API-Football** (`api-football`) - Deferred provider candidate.
6. **TheSportsDB** (`thesportsdb`) - Reference metadata shadow.
7. **StatsBomb Open Data** (`statsbomb-open-data`) - Local open-data deep historical.
8. **statsbombpy** (`statsbombpy`) - Optional library bridge.
9. **OpenFootball** (`openfootball`) - Reference identity dataset.
10. **Kaggle European Soccer** (`kaggle-european-soccer`) - Historical deep backfill.
11. **sport.db open-source tooling** (`sportdb-open-source-tooling`) - Optional text tooling.
12. **soccerdata ClubElo** (`soccerdata-clubelo`) - Replay rating.
13. **soccerdata ESPN** (`soccerdata-espn`) - Replay reference result.
14. **soccerdata FBref** (`soccerdata-fbref`) - Replay statistics.
15. **soccerdata FiveThirtyEight** (`soccerdata-fivethirtyeight`) - Replay legacy prior.
16. **soccerdata MatchHistory** (`soccerdata-matchhistory`) - Replay odds reference.
17. **soccerdata Sofascore** (`soccerdata-sofascore`) - Replay statistics.
18. **soccerdata SoFIFA** (`soccerdata-sofifa`) - Replay player context.
19. **soccerdata Understat** (`soccerdata-understat`) - Replay xG.
20. **soccerdata WhoScored** (`soccerdata-whoscored`) - Replay statistics (docs-only).
21. **FotMob probe** (`fotmob-probe`) - Unofficial experimental probe.
22. **SofaScore rich probe** (`sofascore-rich-probe`) - Unofficial experimental probe.
23. **ScraperFC SofaScore bridge** (`scraperfc-sofascore-bridge`) - Experimental wrapper probe.
