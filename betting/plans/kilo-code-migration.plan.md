# Migration Plan: GitHub Copilot → Kilo Code + Gemini Free Tier

**Created:** 2026-05-27  
**Supersedes:** `roo-code-migration.plan.md` (INVALID — Roo Code archived May 15, 2026)  
**Status:** READY TO EXECUTE  
**Hardware:** MacBook Pro M4 Pro, 48GB RAM, macOS  

---

## CRITICAL FINDINGS FROM RESEARCH

### ⛔ Why the Previous Plan FAILED:

| Problem | Impact | Fix |
|---------|--------|-----|
| **Roo Code was ARCHIVED May 15, 2026** | Entire plan targets dead software | Use **Kilo Code** (official successor, v5.x fork) |
| **Local LM Studio + Gemma 31B = 20GB RAM** | MLX kills laptop, crashes, swaps | Use **Google Gemini 2.5 Flash API** (free, cloud, 0 local RAM) |
| **Qwen 7B for autocomplete = 5GB extra RAM** | 25GB+ total = M4 Pro memory pressure | Kilo Code has **built-in autocomplete** (same Gemini key) |
| **32K context window (Gemma local)** | Pipeline needs large context for analysis | Gemini 2.5 Flash = **1M token context** window |
| **Continue.dev as separate extension** | Extra complexity, extra config | Not needed — Kilo has autocomplete built-in |
| **Dual model serving** | LM Studio instability, model swapping | Single cloud API, zero local compute |

### ✅ New Stack (Zero Local AI Compute):

```
BEFORE (failed plan):                    AFTER (this plan):
─────────────────────────────────────────────────────────────
Roo Code (DEAD May 15)              →  Kilo Code (active, 3M+ users)
LM Studio local (kills RAM)         →  Google Gemini API (free cloud)
Gemma 31B Q4 (20GB RAM)            →  Gemini 2.5 Flash (free, 1M ctx)
Qwen 7B (5GB RAM)                  →  Kilo built-in autocomplete
Continue.dev (extra extension)      →  Not needed
32K context                         →  1,000,000 token context
~25GB RAM consumed by AI            →  0 GB RAM consumed by AI
Crashes, swaps, instability         →  Always available, fast
```

---

## 1. Provider Decision Matrix (Free Tiers Compared)

| Provider | Free Limits | Best Model | Context | Tool Use | Speed | Verdict |
|----------|-------------|------------|---------|----------|-------|---------|
| **Google Gemini** | 1,500 RPD, 15 RPM, 250K TPM | Gemini 2.5 Flash | 1M | ✅ Excellent | Fast | **🏆 PRIMARY** |
| Groq | 1,000 RPD, 30 RPM, 500K TPD | Llama 3.3 70B | 128K | ⚠️ Limited | Ultra-fast (315 TPS) | Backup for quick tasks |
| OpenRouter Free | 50 RPD (no credits) | Gemma 4 26B / Llama 4 | Varies | ⚠️ Varies | Medium | Too limited |
| DeepSeek | 5M tokens signup then $0.14/M | DeepSeek V4 Flash | 128K | ✅ Good | Medium | Cheap paid fallback (~$2/mo) |
| Kilo Gateway | Free auto-router | MiniMax M2.5 | Varies | ⚠️ Basic | Fast | Quick start, less capable |
| Cerebras | 60K tokens/min | Llama 3.3 70B | 8K | ❌ No | Ultra-fast | No tool use = unusable |

### Winner: **Google Gemini 2.5 Flash (Free Tier)**

- **1,500 requests/day** — more than enough for full pipeline (typical session = 100-300 requests)
- **1M token context** — fits entire codebase context, long analysis outputs
- **Excellent tool use** — native function calling, MCP support via Kilo
- **No credit card** — truly free, no trial, no expiry
- **Native Kilo Code support** — first-class provider integration
- **Thinking mode** — can enable step-by-step reasoning for complex analysis

### Fallback: **DeepSeek V4 Flash ($0.14/1M input)**

- When Gemini rate-limits you (>15 RPM burst)
- For heavy sessions that exceed 1,500 RPD (unlikely but possible)
- ~$2/month for unlimited heavy use
- Also supports tool use and coding

---

## 2. Architecture: Kilo Code Configuration

### 2.1 Kilo Code vs Roo Code Mapping

| Roo Code (DEAD) | Kilo Code (ACTIVE) | Notes |
|------------------|-------------------|-------|
| `.roomodes` | `kilo.jsonc` → `agent` key | Auto-migrated on first run |
| `.roorules` / `.clinerules` | `AGENTS.md` (project root) | Project-wide rules |
| `.roo/rules/` | `.kilocode/rules/` | Per-mode overflow rules |
| `.roo/rules-{slug}/` | `.kilocode/rules/` (flat) or per-agent `.md` | Simpler structure |
| `.roo/mcp.json` | `.kilocode/mcp.json` | Same format |
| `.roo/memory-bank/` | `.kilocode/memory/` or project files | Kilo reads project files directly |
| Tool groups (`read`, `edit`, etc.) | Permission system (`allow`, `deny`, `ask`) | More granular |
| `new_task(mode, message)` | `/newtask` + subagent config | Similar but improved |
| `attempt_completion` | Task completion built-in | Same concept |

### 2.2 File Structure After Migration

```
/Users/mkoziol/projects/bet/
├── AGENTS.md                            ← Global rules (replaces .clinerules)
├── kilo.jsonc                           ← Agent definitions + model config
├── .kilocode/
│   ├── mcp.json                         ← MCP servers (sqlite, brave, seq-thinking)
│   ├── rules/                           ← Overflow rule files loaded per-agent
│   │   ├── analysis-methodology.md
│   │   ├── sport-protocols.md
│   │   ├── mistakes-rules.md
│   │   ├── artifacts-format.md
│   │   └── source-navigation.md
│   └── memory/                          ← Persistent memory
│       ├── pipeline-knowledge-base.md
│       ├── coupon-risk-lessons.md
│       └── betting-preferences.md
├── (existing project files unchanged)
└── .github/_archived-copilot/           ← Phase 4 archive
```

### 2.3 Kilo Agent Permission Model

```jsonc
// Permission examples in kilo.jsonc
"permission": {
  "read": "allow",           // Always allowed
  "edit": "allow",           // Can modify files
  "bash": "allow",           // Can run terminal commands
  "browser": "allow",        // Can browse web
  "mcp": "allow",           // Can use MCP servers
  "task": {                  // Can spawn sub-tasks
    "bet-statistician": "allow",
    "bet-challenger": "allow",
    "bet-builder": "allow"
  }
}
```

---

## 3. Phase Plan

### Phase 1: Install & Configure (15 minutes)

**Task 1.1 — Install Kilo Code extension**
```
VS Code → Extensions → Search "Kilo Code" → Install (kilocode.Kilo-Code)
```

**Task 1.2 — Get Gemini API key (free)**
1. Go to https://aistudio.google.com/apikey
2. Sign in with Google account
3. Click "Create API key"
4. Copy the key

**Task 1.3 — Configure Kilo Code provider**
In Kilo Code settings (sidebar):
- API Provider: `Google Gemini`
- API Key: (paste Gemini key)
- Model: `gemini-2.5-flash`

**Task 1.4 — Verify connection**
Open Kilo Code chat, ask: "What model are you using?"
Expected: responds using Gemini 2.5 Flash.

**Definition of done:** Kilo Code installed, responds to prompts using Gemini 2.5 Flash, zero RAM consumed by AI models.

---

### Phase 2: Project Configuration (30 minutes)

**Task 2.1 — Create `AGENTS.md`** (project-wide rules)

Condensed from `copilot-instructions.md` — 40 lines max. Global rules for all agents.

**Task 2.2 — Create `kilo.jsonc`** (agent definitions)

10 agents defined with roles, permissions, and model config.

**Task 2.3 — Create `.kilocode/mcp.json`** (MCP servers)

```json
{
  "mcpServers": {
    "sequentialthinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    },
    "sqlite": {
      "command": "uvx",
      "args": ["mcp-server-sqlite", "--db-path", "/Users/mkoziol/projects/bet/betting/data/betting.db"]
    },
    "brave-search": {
      "command": "npx",
      "args": ["-y", "brave-search-mcp"],
      "env": {
        "BRAVE_API_KEY": "BSAn2VjXZWHXBQ4qygvaLbT1xXINw5u"
      }
    }
  }
}
```

**Task 2.4 — Create `.kilocode/rules/`** (overflow files)

Copy and condense from current `.github/instructions/` and `.github/skills/`:
- `analysis-methodology.md` (60 lines)
- `sport-protocols.md` (80 lines)
- `mistakes-rules.md` (full — already short)
- `artifacts-format.md` (50 lines)
- `source-navigation.md` (40 lines)

---

### Phase 3: Agent Definitions (1 hour)

All 10 agents defined in `kilo.jsonc`:

| Agent | Role | Key Permissions |
|-------|------|-----------------|
| `bet-orchestrator` | Pipeline coordinator | All (read, edit, bash, browser, mcp, task) |
| `bet-scanner` | Event discovery | read, edit, bash, mcp, browser |
| `bet-settler` | Settlement + PnL | read, edit, bash, mcp, browser |
| `bet-statistician` | Deep stats analysis | read, bash, mcp, browser |
| `bet-scout` | Tipster intelligence | read, bash, mcp, browser |
| `bet-enricher` | Data quality | read, edit, bash, mcp, browser |
| `bet-valuator` | Odds + EV analysis | read, bash, mcp |
| `bet-challenger` | Gate + bear cases | read, bash, mcp, browser |
| `bet-builder` | Coupon construction | read, edit, bash, mcp |
| `bet-db-analyst` | DB quality audit | read, bash, mcp |

---

### Phase 4: Testing & Validation (30 minutes)

**Test 1:** MCP server connectivity (sqlite query, brave search, sequential thinking)
**Test 2:** Agent switching — ask orchestrator to delegate to statistician
**Test 3:** Full command execution — run a pipeline script
**Test 4:** Rate limit test — make 20 rapid requests to check Gemini limits
**Test 5:** Context window test — send large analysis prompt

---

### Phase 5: Cleanup (15 minutes)

- Archive `.github/` Copilot artifacts → `.github/_archived-copilot/`
- Disable/uninstall GitHub Copilot extension
- Remove Continue.dev if installed
- Remove LM Studio (or keep for occasional local experiments)
- Update README.md references

---

## 4. Gemini Free Tier Rate Management

### Daily Budget: 1,500 requests

Typical pipeline session breakdown:
```
S0 Settlement:           ~10 requests
S1 Scan + Discovery:     ~20 requests  
S1e Shortlist:           ~15 requests
S2 Tipster xref:         ~30 requests
S2.3-S2.9 Enrichment:   ~40 requests
S3 Deep Stats:           ~80 requests (heaviest step)
S4 Odds Evaluation:      ~30 requests
S5+S6 Context + Upset:   ~40 requests
S7 Gate:                 ~30 requests
S8 Coupons:              ~50 requests
S9-S10 Validation:       ~20 requests
─────────────────────────────────────
TOTAL:                   ~365 requests
```

**Conclusion:** Full pipeline uses ~25% of daily budget. Even 3-4 complete reruns fit within free limits.

### Rate Limit Strategy:
- Gemini 2.5 Flash: 15 RPM (one request every 4 seconds)
- For burst needs: Kilo handles retries automatically
- If rate-limited: wait 60s and retry (Kilo does this automatically)
- Emergency fallback: switch to DeepSeek V4 Flash for remainder of session

---

## 5. DeepSeek Fallback Configuration

If Gemini is insufficient for some reason, add DeepSeek as a secondary provider:

1. Sign up at https://platform.deepseek.com
2. Get API key (5M free tokens on signup)
3. In Kilo Code, add as secondary provider
4. Model: `deepseek-v4-flash` (best cost/quality ratio)
5. Cost: ~$0.14/1M input, $0.28/1M output
6. Typical daily pipeline cost: $0.10 - $0.50 (if Gemini free tier exhausted)

---

## 6. Comparison: Current (Copilot) vs Target (Kilo + Gemini)

| Dimension | GitHub Copilot | Kilo Code + Gemini Free |
|-----------|---------------|------------------------|
| **Monthly cost** | $19/month ($228/year) | $0 |
| **Model quality** | Claude 4.6 (excellent) | Gemini 2.5 Flash (very good) |
| **Context window** | ~200K (varies) | 1,000,000 tokens |
| **Custom agents** | .agent.md (10 agents) | kilo.jsonc + .md agents |
| **Tool use** | Built-in tools | MCP + permissions |
| **Orchestration** | runSubagent | /newtask + subagents |
| **Autocomplete** | Built-in | Kilo built-in |
| **Local RAM** | ~500MB (extension only) | ~500MB (extension only) |
| **Rate limits** | Generous (paid) | 1,500 RPD / 15 RPM |
| **Offline** | No | No (both need internet) |
| **Open source** | No | Yes (Apache 2.0) |
| **Vendor lock-in** | GitHub/Microsoft | None (switch providers freely) |

### Quality Trade-off:
- Copilot with Claude 4.6 = top-tier reasoning
- Gemini 2.5 Flash = excellent for agents/coding, slightly below Claude for complex reasoning
- For the betting pipeline specifically: Gemini's 1M context + tool use is MORE important than marginal reasoning quality difference
- If reasoning quality is critical: DeepSeek V4 Pro ($0.56/1M) or Gemini 2.5 Pro (50 RPD free) for complex analysis steps

---

## 7. Risk Register (Updated)

| Risk | Probability | Mitigation |
|------|-------------|-----------|
| Gemini free tier gets reduced | Low (Google committed through 2026) | DeepSeek fallback ready ($2/mo) |
| 15 RPM rate limit slows pipeline | Medium | Kilo auto-retries; pipeline is not latency-critical |
| Gemini quality insufficient for complex analysis | Low-Medium | Use Gemini 2.5 Pro for S3 heavy analysis (50 RPD free) |
| Kilo Code bugs (newer project) | Low | Active community, weekly releases, 3M+ users |
| Google AI Studio account issues | Very Low | DeepSeek or Groq as immediate fallback |
| MCP servers incompatible | Very Low | Same MCP protocol, already tested with Copilot |

---

## 8. Execution Checklist

```markdown
### Phase 1: Install & Configure (15 min)
- [ ] 1.1 Install Kilo Code extension from VS Code Marketplace
- [ ] 1.2 Get Gemini API key from aistudio.google.com/apikey
- [ ] 1.3 Configure Kilo Code → Gemini provider + model
- [ ] 1.4 Verify: Kilo responds using Gemini 2.5 Flash

### Phase 2: Project Configuration (30 min)
- [ ] 2.1 Create AGENTS.md (project-wide rules, 40 lines)
- [ ] 2.2 Create kilo.jsonc (10 agent definitions)
- [ ] 2.3 Create .kilocode/mcp.json (3 servers)
- [ ] 2.4 Create .kilocode/rules/ (5 overflow files)

### Phase 3: Agent Definitions (1 hour)
- [ ] 3.1 bet-orchestrator agent definition
- [ ] 3.2 bet-statistician agent definition
- [ ] 3.3 bet-challenger agent definition
- [ ] 3.4 bet-builder agent definition
- [ ] 3.5 bet-scanner agent definition
- [ ] 3.6 bet-settler agent definition
- [ ] 3.7 bet-scout agent definition
- [ ] 3.8 bet-enricher agent definition
- [ ] 3.9 bet-valuator agent definition
- [ ] 3.10 bet-db-analyst agent definition

### Phase 4: Testing (30 min)
- [ ] 4.1 MCP servers connect (sqlite, brave, seq-thinking)
- [ ] 4.2 Agent switching works
- [ ] 4.3 Script execution works
- [ ] 4.4 Rate limit acceptable
- [ ] 4.5 Context window handles large prompts

### Phase 5: Cleanup (15 min)
- [ ] 5.1 Archive .github/ Copilot artifacts
- [ ] 5.2 Disable GitHub Copilot extension
- [ ] 5.3 Update README.md
- [ ] 5.4 Remove LM Studio (optional)
```

---

## 9. Quick Start (Do This NOW)

```bash
# 1. Install Kilo Code
# VS Code → Cmd+Shift+X → search "Kilo Code" → Install

# 2. Get Gemini key
# Open: https://aistudio.google.com/apikey
# Click "Create API key" → copy

# 3. Configure in Kilo Code sidebar:
#    Provider: Google Gemini
#    API Key: (paste)
#    Model: gemini-2.5-flash

# 4. Test it:
#    Open Kilo Code chat → "Hello, what model are you using?"

# 5. Create project config:
#    See Phase 2 tasks below for AGENTS.md and kilo.jsonc
```

**Total time to working system: ~2.5 hours (vs 8+ hours in old plan)**  
**Total cost: $0/month (vs $19/month Copilot)**  
**Local RAM for AI: 0 GB (vs 25GB in old plan)**
