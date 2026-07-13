# Football Data Foundation - Proposed Next Implementation Plan

Strict scheduling and sequence of subsequent implementation phases based solely on admitted sources.

| Sequence | Source Family | Role | Next Phase Kind | Verification Tests Needed |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **statsbomb_open_data** | HISTORICAL_ENRICHMENT_CANDIDATE | historical enrichment backfill | tests/enrichment/football_data_foundation/test_statsbomb_open_data.py |
| 2 | **kaggle_european_soccer** | HISTORICAL_ENRICHMENT_CANDIDATE | historical enrichment backfill | tests/enrichment/football_data_foundation/test_kaggle_european_soccer.py |
| 3 | **openfootball** | REFERENCE_CANDIDATE | reference identity bridge | tests/enrichment/football_data_foundation/test_openfootball.py |

## Verification Gates
- All subsequent integrations remain shadow-only/offline evidence only.
- No production routing activation or certification is permitted.
