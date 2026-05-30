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
- Primary: Qwen3.6-35B-A3B MoE 4-bit (local via Rapid-MLX on localhost:8000)
- Architecture: MoE 35B total, 3B active per token, hybrid attention/Mamba, 131K context, 4-bit quantization
- Thinking mode: ALWAYS ON (<think> blocks, qwen3 parser). NEVER --no-thinking.
- Tool calling: qwen3_coder_xml parser
- ~45-70 tok/s on M4 Pro 48GB, ~19GB VRAM (21GB headroom for KV cache)
- No rate limits, no API costs, fully local
- MCP: sequentialthinking, sqlite, brave-search
