# Kilo Code — Model Configuration (May 2026)

## Active Model: Google Gemini 3.5 Flash

All 10 agents use: `google/gemini-3.5-flash`

| Property | Value |
|----------|-------|
| Provider | Google Gemini (direct API key) |
| Context | 1,000,000 tokens |
| Free tier | 1,500 req/day, 15 RPM |
| Coding index | Highest among free models |
| Design | Native agentic (tool calling, multi-step) |

## Why NOT Kilo Gateway / "Auto Free"

| Issue | Impact |
|-------|--------|
| Routes to random models (Laguna, Nemotron) | Inconsistent quality |
| 128K context max | Loses methodology mid-pipeline |
| Poor tool calling | MCP tools fail silently |
| No guaranteed model | Different model each call |

## Setup

1. Settings → API Provider → **"Google Gemini"**
2. Paste key from https://aistudio.google.com/apikey
3. Model auto-reads from `kilo.jsonc` → `google/gemini-3.5-flash`

## Fallback

If rate-limited (>1500 calls/day), change in kilo.jsonc:
```jsonc
"model": "google/gemini-2.5-flash"  // also free, also 1M context
```

## Budget (if upgrading later)

| Tier | Model | Cost/day |
|------|-------|----------|
| Free | gemini-3.5-flash | $0 |
| Budget | gemini-2.5-pro | ~$0.50 |
| Premium | claude-sonnet-4.6 | ~$3-5 |
