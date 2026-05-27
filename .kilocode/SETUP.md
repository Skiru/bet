# Kilo Code Setup Guide — Betting Pipeline

## Prerequisites

1. **VS Code** with Kilo Code extension installed (`kilocode.Kilo-Code`)
2. **Google AI Studio API key** (free, no credit card): https://aistudio.google.com/apikey
3. **Node.js 18+** (for MCP servers)
4. **Python 3.11+** with project virtualenv
5. **Fish shell** as default terminal

## Step 1: Install Kilo Code Extension

```
code --install-extension kilocode.Kilo-Code
```

Or search "Kilo Code" in VS Code Extensions marketplace.

## Step 2: Configure Gemini 2.5 Flash

1. Open VS Code Settings (`Cmd+,`)
2. Search "Kilo Code"
3. Set API Provider: **Google AI Studio** (Gemini)
4. Enter your API key from https://aistudio.google.com/apikey
5. Select model: **gemini-2.5-flash**
6. Verify: Open Kilo Code chat, type "hello" — should respond.

### Rate Limits (Free Tier)
- 1,500 requests/day, 15 requests/minute, 250K tokens/minute
- 1,000,000 token context window
- See `.kilocode/rules/gemini-rate-limits.md` for pipeline implications

## Step 3: Configure MCP Servers

MCP configuration is in `.kilocode/mcp.json`. Set up:

```fish
# Add BRAVE_API_KEY to your fish profile (persists across sessions)
set -U BRAVE_API_KEY your_brave_api_key_here
# Or add to ~/.config/fish/config.fish:
# set -x BRAVE_API_KEY your_key
```

Verify MCP servers work:

```fish
# Test sequentialthinking
npx -y @modelcontextprotocol/server-sequential-thinking

# Test sqlite (should connect to betting.db)
uvx mcp-server-sqlite --db-path ./betting/data/betting.db

# Test brave-search
npx -y brave-search-mcp
```

## Step 4: Verify Agent Discovery

1. Open Kilo Code chat
2. Type `@` — should show all 10 agents (bet-orchestrator, bet-statistician, etc.)
3. Select `bet-orchestrator` — should show "Pipeline coordinator" description

## Step 5: First Pipeline Run

```
@bet-orchestrator settle and run today's pipeline
```

The orchestrator will:
1. Check session-state.md (empty = fresh start)
2. Run S0 settlement
3. Delegate to bet-settler for analysis
4. Continue S1→S8 with specialist delegations

## File Structure

```
bet/
├── AGENTS.md              # Global rules (read by ALL agents)
├── kilo.jsonc             # Agent definitions (10 agents)
├── .kilocode/
│   ├── mcp.json           # MCP server configuration
│   ├── rules/             # Detailed methodology (loaded on demand)
│   │   ├── execution-protocol.md
│   │   ├── analysis-methodology.md
│   │   ├── betting-mistakes-rules.md
│   │   ├── sport-protocols.md
│   │   ├── artifacts-format.md
│   │   └── gemini-rate-limits.md
│   └── memory/            # Persistent memory (survives across sessions)
│       ├── session-state.md
│       ├── pipeline-knowledge-base.md
│       ├── coupon-risk-lessons.md
│       └── betting-preferences.md
├── config/
│   ├── api_keys.json      # API keys (brave, odds-api, serpapi, etc.)
│   └── betting_config.json
├── betting/data/
│   └── betting.db         # SQLite database (primary data store)
└── scripts/               # Pipeline scripts (data producers)
```

## Fallback: DeepSeek V3

If Gemini quota exhausted (1500 RPD):
1. Open Kilo Code Settings
2. Change API Provider to **DeepSeek**
3. Enter DeepSeek API key
4. Select model: **deepseek-chat** (DeepSeek V3)
5. Cost: ~$0.27/1M input ($1.10/1M output, ~$3-5/month)

## Migration Notes

- Old `.github/` Copilot artifacts remain for reference but are NOT read by Kilo Code
- Old `config/lmstudio_config.json` is for OPTIONAL local LM Studio enrichment scripts (not the agent system)
- Kilo Code auto-reads `AGENTS.md` and `kilo.jsonc` from project root
- `.kilocode/rules/` files are loaded on-demand by agents when needed
