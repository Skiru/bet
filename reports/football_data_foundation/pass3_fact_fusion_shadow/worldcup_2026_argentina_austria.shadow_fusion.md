# Shadow Fusion Report

## Metadata
- Fixture Slug: worldcup_2026_argentina_austria
- Run ID: run_f07da4ff2404
- Manual Authorization Required: True
- Selectable for Production: False

## Fused Facts
- **FIXTURE_IDENTITY**
  - Sources: sportdb
  - Proofs: REAL_LIVE_API_PROOF
  - Value: `{"competition": "World Cup 2026", "home_team": "Argentina", "away_team": "Austria"}`
- **MATCH_STATUS**
  - Sources: sportdb
  - Proofs: REAL_LIVE_API_PROOF
  - Value: `{"status": "FT"}`
- **SCORE**
  - Sources: sportdb
  - Proofs: REAL_LIVE_API_PROOF
  - Value: `{"score_home": 2, "score_away": 1}`

## Conflicts
_No conflicts detected._

## Missing Fact Types
_No required fact types missing._

## Source Coverage
- **sportdb**: FIXTURE_IDENTITY, MATCH_STATUS, SCORE
