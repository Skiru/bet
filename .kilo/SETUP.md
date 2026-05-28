# Kilo Code Setup: Gemini 3.5 Flash

## One-Time Setup (3 minutes)

### 1. Get Google Gemini API Key (FREE)

1. Go to https://aistudio.google.com/apikey
2. Sign in with Google account
3. Click "Create API key"
4. Copy the key

### 2. Configure Kilo Code Extension

1. Open Kilo Code panel → click gear icon (⚙️)
2. **API Provider:** select **"Google Gemini"** (NOT "Kilo Gateway"!)
3. **API Key:** paste your Google AI Studio key
4. **Model:** auto-reads from `kilo.jsonc` → `google/gemini-3.5-flash`
5. Done!

### 3. Verify

Switch to `bet-orchestrator` agent and ask: "What model are you?"
Should respond as Gemini 3.5 Flash with 1M context.

---

## What Changed

| Before (broken) | After (fixed) |
|-----------------|---------------|
| Kilo Gateway "Auto Free" (random models) | Google Gemini direct (deterministic) |
| 128K context (loses methodology mid-pipeline) | 1M context (full methodology always loaded) |
| Poor tool calling | Native agentic design |
| Inline prompts truncated at ~2000 chars | External files via `{file:...}` (unlimited) |

## Free Tier Limits

- **1,500 requests/day** — pipeline uses ~80-120 per full run
- **15 requests/minute** — sequential pipeline is fine
- **1M tokens context** — agents NEVER lose methodology
- Can run 10+ full pipeline sessions/day at $0

## Fallback

If rate-limited, change ONE line in `kilo.jsonc`:
```jsonc
"model": "google/gemini-2.5-flash"   // also free, also 1M context
```

## Context Budget

| Component | Tokens | % of 1M |
|-----------|:---:|:---:|
| Instructions (6 files) | ~34K | 3.4% |
| Agent prompt (per agent) | ~1.5K | 0.15% |
| AGENTS.md + .kilocode/rules/ | ~0.8K | 0.08% |
| **System total** | **~36K** | **3.6%** |
| **Remaining for work** | **~964K** | **96.4%** |
