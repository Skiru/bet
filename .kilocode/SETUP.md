# Kilo Code Setup Guide — Betting Pipeline

## Prerequisites

1. **VS Code** with Kilo Code extension installed (`kilocode.Kilo-Code` v7.3+)
2. **Google AI Studio API key** (free, no credit card): https://aistudio.google.com/apikey
3. **Node.js 18+** (for MCP servers)
4. **Python 3.11+** with project virtualenv
5. **Fish shell** as default terminal

## Step 1: Install Kilo Code Extension

```
code --install-extension kilocode.Kilo-Code
```

Or search "Kilo Code" in VS Code Extensions marketplace.

## Step 2: Configure Google Gemini API Provider

1. Open Kilo Code Settings
2. Go to **API Provider** → select **"Google Gemini"**
3. Paste your API key from https://aistudio.google.com/apikey
4. Model: `gemini-3.5-flash` (auto-detected from kilo.jsonc)

### Model Details
- **google/gemini-3.5-flash** — all 10 agents use this model
- 1M token context window
- Free tier: 1,500 requests/day, 15 requests/minute
- Highest coding index of all free models
- Designed for agentic workflows

### CRITICAL: Use "Google Gemini" Provider Directly
Do NOT use "Kilo Gateway" — it charges per token.
The free tier is accessed only through the direct Google Gemini provider.

## Step 3: Configure MCP Servers

MCP configuration is in `.kilocode/mcp.json`. Set up:

```fish
# Add BRAVE_API_KEY to your fish profile (persists across sessions)
set -U BRAVE_API_KEY your_brave_api_key_here
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
4. Start pipeline: `@bet-orchestrator Run today's betting pipeline`
5. All agents auto-use `google/gemini-3.5-flash` via the configured provider

## Step 5: Verify Model Settings

The model is set per-agent in `kilo.jsonc` (`google/gemini-3.5-flash` for all 10 agents).
No manual model selection needed in the UI — agents auto-use their configured model.
- **Autocomplete:** Codestral (default, free with Mistral BYOK via Continue.dev)

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
│   ├── rules/             # Auto-loaded by all agents
│   │   ├── tool-names.md  # Correct MCP tool name mappings
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

## Fallback: DeepSeek V3 / Google AI Studio

If free models are unavailable or too throttled:

### Option A: DeepSeek V4 Flash (Budget)
1. Sign up at https://platform.deepseek.com
2. Add API key as BYOK in Kilo Gateway (Settings → Providers)
3. Select model: `deepseek/deepseek-v4-flash`
4. Cost: ~$0.13/1M tokens (~$0.50-1/day)

### Option B: Google AI Studio (Original Setup)
1. Get API key from https://aistudio.google.com/apikey
2. Add as BYOK in Kilo Gateway
3. Select: `google/gemini-3.5-flash`
4. Limits: 1,500 RPD, 15 RPM, 250K TPM, 1M context

### Option C: VS Code LM API (Use Your Copilot Subscription!)
1. Settings → Providers → VS Code LM API
2. Use GitHub Copilot's models (Claude Sonnet 4.6, GPT-5.4)
3. Subject to Copilot rate limits
4. Good for critical gate decisions

## Migration Notes

- Old `.github/` Copilot artifacts remain for reference but are NOT read by Kilo Code
- Old `config/lmstudio_config.json` is for OPTIONAL local LM Studio enrichment scripts (not the agent system)
- Kilo Code auto-reads `AGENTS.md` and `kilo.jsonc` from project root
- `.kilocode/rules/` files are loaded on-demand by agents when needed
- Permission key is `bash` (not `command`) in the new CLI-based extension
- Models use `provider/model-id` format (e.g., `google/gemini-3.5-flash`)
- See `.kilocode/OPTIMAL-MODELS-GUIDE.md` for model configuration details
