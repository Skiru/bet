# Kilo Code Setup Guide — Betting Pipeline

## Prerequisites

1. **VS Code** with Kilo Code extension installed (`kilocode.Kilo-Code` v7.3+)
2. **Rapid-MLX** installed: `pipx install rapid-mlx`
3. **Node.js 18+** (for MCP servers)
4. **Python 3.11+** with project virtualenv
5. **Fish shell** as default terminal

## Step 1: Install Kilo Code Extension

```
code --install-extension kilocode.Kilo-Code
```

Or search "Kilo Code" in VS Code Extensions marketplace.

## Step 2: Pull Model (First Time Only)

```fish
~/.local/bin/rapid-mlx pull qwen3.6-35b
```

Downloads `mlx-community/Qwen3.6-35B-A3B-4bit` (~18 GiB). Requires ~35GB free disk space.

## Step 3: Start Local Model Server

```fish
# Use the optimized start script:
./scripts/start_local_model.sh

# Or run manually with full flags:
~/.local/bin/rapid-mlx serve qwen3.6-35b --port 8000 \
  --no-mllm --max-num-seqs 1 --reasoning-parser qwen3 \
  --default-temperature 0.6 --default-top-p 0.95 --default-top-k 20 \
  --default-repetition-penalty 1.05 \
  --max-tokens 16384 --pin-system-prompt --enable-prefix-cache \
  --kv-cache-turboquant --kv-cache-turboquant-bits 3 \
  --cache-memory-mb 2000 --gpu-memory-utilization 0.9 \
  --prefill-step-size 4096 --gc-control \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder_xml
```

Wait for `Ready: http://localhost:8000/v1` before proceeding.

## Step 4: Configure OpenAI-Compatible Provider in Kilo Code

1. Open Kilo Code Settings
2. Go to **API Provider** → select **"OpenAI Compatible"**
3. Base URL: `http://localhost:8000/v1`
4. API Key: `not-needed` (any value works)
5. Model: `default` (auto-detected from kilo.jsonc)

### Model Details
- **openai-compatible/qwen3.6-35b-a3b** — all 10 agents use this model
- Qwen3.6-35B-A3B MoE, 4-bit quantization, hybrid attention/Mamba architecture
- MoE: 35B total knowledge, 3B active params per token
- 131K token context window (model maximum)
- ~45-70 tok/s on M4 Pro 48GB, ~19GB VRAM usage (21GB headroom for KV cache)
- Tool calling (qwen3_coder_xml parser), reasoning (qwen3 parser, `<think>` blocks)
- Thinking mode: ALWAYS ON — NEVER use --no-thinking
- No rate limits, no API costs, fully local

## Step 5: Configure MCP Servers

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

## Step 6: Verify Agent Discovery

1. Open Kilo Code chat
2. Type `@` — should show all 10 agents (bet-orchestrator, bet-statistician, etc.)
3. Select `bet-orchestrator` — should show "Pipeline coordinator" description
4. Start pipeline: `@bet-orchestrator Run today's betting pipeline`
5. All agents auto-use `openai-compatible/qwen3.6-35b-a3b` via the configured provider

## Step 7: Auto-Start (Optional)

Set up launchd to auto-start the server on login:

```fish
cp config/com.rapid-mlx.server.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.rapid-mlx.server.plist
```

To stop: `launchctl unload ~/Library/LaunchAgents/com.rapid-mlx.server.plist`

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Port 8000 in use | `lsof -ti :8000 \| xargs kill` then restart |
| Model not found | `~/.local/bin/rapid-mlx pull qwen3.6-35b` |
| OOM / Metal crash | Use `--safe` mode: `./scripts/start_local_model.sh --safe` |
| Slow TTFT | Expected ~15-30s for 20K+ token prompts (hybrid arch) |
| No tool calls | Verify `qwen3_coder_xml` in kilo.jsonc tool_format |
| Thinking not working | Check `--reasoning-parser qwen3` flag is set |
- **Autocomplete:** Codestral (default, free with Mistral BYOK via Continue.dev)

## Step 6: First Pipeline Run

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
│   │   ├── model-configuration.md  # Model specs and performance
│   │   ├── delegation-protocol.md  # Orchestrator delegation rules
│   │   └── terminal-environment.md # Fish shell + Python venv rules
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
3. Select: `gemini/gemini-2.5-flash`
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
- Models use `provider/model-id` format (e.g., `gemini/gemini-2.5-flash`)
- See `.kilocode/OPTIMAL-MODELS-GUIDE.md` for model configuration details
