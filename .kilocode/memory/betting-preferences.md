# Betting Preferences

## Bankroll & Staking
- Bookmaker: Betclic (Polish interface)
- All picks CONDITIONAL until user verifies in Betclic app
- Kelly 1/4 criterion for stake sizing
- Max 5% bankroll per single bet
- 20% drawdown = MANDATORY stop

## Analysis Preferences
- Statistical markets > outcome markets (ALWAYS)
- UNDER picks historically 74% hit rate
- Statistical markets 63% > outcomes 45%
- 2-3 leg coupons preferred (AKO5/7 = 0 wins historically)
- team_corners 87%, cards 75%, fouls 67% historical hit rates

## Communication
- Polish language for coupon descriptions and market names
- Europe/Warsaw timezone
- Dot decimals for odds/PLN
- Full team/player names (never abbreviate)

## Pipeline
- Agent-driven (NEVER run pipeline_orchestrator.py)
- DB-first architecture (betting.db via get_db())
- Fish shell terminal (no bash syntax)
- Scripts produce data, agents analyze
- Deep source fusion: tipsters + DB stats + web search

## Model Configuration
- Primary: Gemini 2.5 Flash (Google AI Studio free tier)
- 1,500 RPD, 15 RPM, 250K TPM, 1M context
- Fallback: DeepSeek V3 (~$0.27/1M input)
- MCP: sequentialthinking, sqlite, brave-search
