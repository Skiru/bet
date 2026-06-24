# Shadow Fusion Report

## Metadata
- Fixture Slug: generic_club_shadow_canary
- Run ID: run_a936a3fa0df3
- Manual Authorization Required: True
- Selectable for Production: False

## Fused Facts
- **FIXTURE_IDENTITY**
  - Identity Key: generic-club-match
  - Primary Source: sportdb
  - Supporting Sources: 
  - Confidence: 0.95
  - Proofs: REAL_LIVE_API_PROOF
  - Value: `{"competition_name": "UEFA Champions League", "home_team": "Manchester City", "away_team": "Real Madrid"}`
- **MATCH_STATUS**
  - Identity Key: generic-club-match
  - Primary Source: sportdb
  - Supporting Sources: 
  - Confidence: 0.95
  - Proofs: REAL_LIVE_API_PROOF
  - Value: `{"status": "FT"}`
- **SCORE**
  - Identity Key: generic-club-match
  - Primary Source: sportdb
  - Supporting Sources: 
  - Confidence: 0.95
  - Proofs: REAL_LIVE_API_PROOF
  - Value: `{"score_home": 3, "score_away": 2}`

## Conflicts
_No conflicts detected._

## Missing Fact Types
_No required fact types missing._

## Source Coverage
- **sportdb**: FIXTURE_IDENTITY, MATCH_STATUS, SCORE
