# Shadow Fusion Report

## Metadata
- Fixture Slug: worldcup_2026_shadow_canary
- Run ID: run_c59f7378ecb0
- Manual Authorization Required: True
- Selectable for Production: False

## Fused Facts
- **FIXTURE_IDENTITY**
  - Identity Key: wc-2026-arg-aus
  - Primary Source: sportdb
  - Supporting Sources: 
  - Confidence: 0.95
  - Proofs: REAL_LIVE_API_PROOF
  - Value: `{"competition_name": "FIFA World Cup 2026", "home_team": "Argentina", "away_team": "Austria"}`
- **MATCH_STATUS**
  - Identity Key: wc-2026-arg-aus
  - Primary Source: sportdb
  - Supporting Sources: 
  - Confidence: 0.95
  - Proofs: REAL_LIVE_API_PROOF
  - Value: `{"status": "FT"}`
- **SCORE**
  - Identity Key: wc-2026-arg-aus
  - Primary Source: sportdb
  - Supporting Sources: 
  - Confidence: 0.95
  - Proofs: REAL_LIVE_API_PROOF
  - Value: `{"score_home": 2, "score_away": 1}`

## Conflicts
_No conflicts detected._

## Missing Fact Types
_No required fact types missing._

## Source Coverage
- **sportdb**: FIXTURE_IDENTITY, MATCH_STATUS, SCORE
