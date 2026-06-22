# Shadow Fusion Report

## Metadata
- Fixture Slug: generic_club_match
- Run ID: run_b5092975f1e9
- Manual Authorization Required: True
- Selectable for Production: False

## Fused Facts
- **FIXTURE_IDENTITY**
  - Sources: sportdb
  - Proofs: REAL_LIVE_API_PROOF
  - Value: `{"competition": "Premier League", "home_team": "Arsenal", "away_team": "Chelsea"}`
- **MATCH_STATUS**
  - Sources: sportdb
  - Proofs: REAL_LIVE_API_PROOF
  - Value: `{"status": "HT"}`
- **SCORE**
  - Sources: sportdb
  - Proofs: REAL_LIVE_API_PROOF
  - Value: `{"score_home": 1, "score_away": 0}`

## Conflicts
_No conflicts detected._

## Missing Fact Types
_No required fact types missing._

## Source Coverage
- **sportdb**: FIXTURE_IDENTITY, MATCH_STATUS, SCORE
