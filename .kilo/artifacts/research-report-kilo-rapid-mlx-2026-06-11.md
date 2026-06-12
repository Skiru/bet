# Independent State-of-the-Art Research Report
## Kilo Code + Rapid-MLX for Production Betting Pipeline

**Research Date:** 2026-06-11  
**Target Environment:** MacBook Pro M4 Pro, 48 GB unified memory, macOS  
**Workload:** Multi-phase sports betting research and decision pipeline

---

## 1. Executive Verdict

**RECOMMENDATION:** Use Rapid-MLX v0.6.83+ with Qwen3.6-35B-A3B-4bit as the baseline local model, integrated with Kilo Code 7.3.41 via OpenAI-compatible localhost endpoint. Implement a **single-primary-agent architecture with phase-specific Skills and structured handoffs**, not a multi-agent orchestration. Reserve cloud models for final review only when evidence quality gates fail.

**Key Findings:**

1. **Rapid-MLX is production-ready** for Qwen3.6 tool calling with automatic parser detection and recovery [OFFICIAL FACT: Rapid-MLX README, 2026-06-09]
2. **Qwen3.6-35B-A3B-4bit fits 48 GB** with ~20 GB model + ~8-12 GB KV cache headroom [COMMUNITY EVIDENCE: Multiple M4 Pro 48 GB reports]
3. **Kilo Code 7.3.41 supports local OpenAI-compatible providers** with full context/input/output limit configuration [OFFICIAL FACT: Kilo documentation]
4. **Tool calling reliability is 100%** in Rapid-MLX benchmarks with auto-recovery for malformed outputs [OFFICIAL FACT: Rapid-MLX README]
5. **Prompt cache delivers 0.08s TTFT** for repeated system prompts [OFFICIAL FACT: Rapid-MLX README]

**Critical Constraints:**

- Practical context limit on 48 GB with concurrent apps: **~24,000-28,000 tokens** (not theoretical 256K)
- One local generation at a time (no proven safe concurrency for this workload)
- Sequential tool calls for baseline (parallel multi-tool not proven reliable for betting pipeline)
- Phase-specific Skills loaded on demand (not monolithic AGENTS.md)

---

## 2. Verified Current Capabilities of Rapid-MLX

### 2.1 Version and Features (OFFICIAL FACT)

**Current Stable:** v0.6.83 (as of 2026-06-09)

**Source:** https://github.com/raullenchai/Rapid-MLX

**Core Features:**
- 17 tool parsers with automatic detection and recovery
- 7 reasoning parsers (Qwen3, DeepSeek, MiniMax, etc.)
- Prompt/prefix cache with 0.08s cached TTFT
- KV cache trimming for standard transformers
- State snapshots for hybrid RNN models (Qwen3.5 DeltaNet)
- OpenAI-compatible `/v1/chat/completions` endpoint
- Anthropic-compatible `/v1/messages` endpoint
- Continuous batching (BatchedEngine)
- Cloud routing for hybrid local/remote execution

### 2.2 Qwen3.6 Support (OFFICIAL FACT)

**Model Aliases:**
- `qwen3.6-35b-a3b-4bit` (default for 48 GB systems)
- `qwen3.6-35b-a3b-8bit` (higher quality, more memory)
- `qwen3.6-27b-4bit` (dense alternative)

**Auto-Detection:**
- Tool parser: Auto-detected from model name
- Reasoning parser: Auto-detected for Qwen family
- Explicit flags override auto-detection

**Tool Calling:**
- 100% success rate in official benchmarks [OFFICIAL FACT]
- Auto-recovery for broken tool calls from quantized models
- Tested on Mac Studio M3 Ultra (256 GB), 2026-06-06

### 2.3 Reasoning Separation (OFFICIAL FACT)

**Configuration:**
```bash
# Enable thinking mode (default)
--reasoning-parser qwen3

# Disable thinking for faster responses
--reasoning-parser qwen3 --default-chat-template-kwargs '{"enable_thinking": false}'
```

**Behavior:**
- Thinking mode: Model generates `<think>...</think>` blocks before response
- Non-thinking mode: Direct response without reasoning tokens
- Both modes support tool calling

### 2.4 Prompt Cache (OFFICIAL FACT)

**Mechanism:**
- KV cache trimming for standard transformers (sub-100ms TTFT)
- State snapshots for Qwen3.5 DeltaNet (RNN state restoration in ~0.1ms)
- Cache persists across requests in same session

**Performance:**
- Cached TTFT: 0.08s
- Cold TTFT: ~277ms (warm cache)

### 2.5 Memory and Context (OFFICIAL + COMMUNITY)

**Model Memory (Qwen3.6-35B-A3B-4bit):**
- Model weights: ~20 GB [COMMUNITY EVIDENCE: Multiple sources]
- KV cache (FP16, 8K context): ~4-6 GB [INFERENCE]
- KV cache (FP16, 32K context): ~16-24 GB [INFERENCE]
- Total with 8K context: ~24-26 GB
- Total with 32K context: ~36-44 GB

**48 GB Practical Limit:**
- macOS overhead: 3-5 GB
- Development apps: 4-8 GB
- Available for model: ~35-40 GB
- **Safe operational context: 8K-16K tokens** with headroom
- **Maximum practical context: ~24K-28K tokens** (tight)

### 2.6 Advanced Features Status

| Feature | Qwen3.6-35B-A3B | Tool Calling | Reasoning | Status |
|---------|-----------------|--------------|-----------|--------|
| MTP | Not compatible | Yes | Yes | OFFICIAL: Requires specific MTP checkpoints |
| DFlash | Compatible | Yes | Yes | OFFICIAL: Supported in Rapid-MLX |
| TurboQuant KV | Compatible | Yes | Yes | COMMUNITY: Experimental, quality impact unclear |
| Continuous Batching | Compatible | Yes | Yes | OFFICIAL: Supported |
| Prefix Cache | Compatible | Yes | Yes | OFFICIAL: Supported |

**MTP Status (CRITICAL):**
- Qwen3.6-35B-A3B MTP checkpoints exist: `mlx-community/Qwen3.6-35B-A3B-MTP-4bit`
- **NOT compatible with Rapid-MLX baseline** - requires mlx-vlm or specialized runtime
- Community reports: MTP provides 1.4-2.2x speedup but adds complexity [COMMUNITY EVIDENCE]

**DFlash Status:**
- Supported in Rapid-MLX via `--draft-kind dflash`
- Provides speculative decoding without separate draft model
- Community reports: ~1.3-2.3% improvement on single-shot, more on concurrent [COMMUNITY EVIDENCE]

### 2.7 Known Issues and Fixes

**Issue: Tool parser not detected for Qwen3.6 non-Coder**
- Status: **FIXED** in Rapid-MLX (auto-detection works)
- Reference: mlx-lm issue #1293 (upstream, not Rapid-MLX)

**Issue: Multi-turn tool calling degradation**
- Status: **MITIGATED** by auto-recovery in Rapid-MLX
- Community reports: GGUF Q4_K_XL more stable than MLX 4-bit for some checkpoints

**Issue: OptiQ quantization breaks tool calling**
- Status: **CONFIRMED** - use standard MLX quantization instead
- Reference: mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit discussion

---

## 3. Verified Current Capabilities of Kilo Code

### 3.1 Version and Architecture (OFFICIAL FACT)

**Current Stable:** 7.3.41 (as of 2026-06-09)

**Source:** https://github.com/Kilo-Org/kilocode

**Architecture:**
- Core: OpenCode CLI backend (`packages/opencode/`)
- Frontend: VS Code extension (`packages/kilo-vscode/`)
- Config: Single `kilo.jsonc` file (v7 rebuild)
- Session: `kilo serve` backend process

### 3.2 Configuration System (OFFICIAL FACT)

**Config File:** `kilo.jsonc` (JSON with comments)

**Location Precedence:**
1. Project-level: `./kilo.jsonc` or `./opencode.jsonc`
2. Global: `~/.config/kilo/kilo.jsonc`

**Key Fields:**
```jsonc
{
  "agents": { ... },        // Custom agent definitions
  "commands": { ... },      // Slash commands
  "skills": { ... },        // Skill references
  "mcp": { ... },          // MCP server configurations
  "permissions": { ... },   // Action permissions
  "providers": { ... },     // Model provider configs
  "context": { ... }        // Context limits
}
```

### 3.3 Context Management (OFFICIAL FACT)

**Context Limits:**
- `context.maxTokens`: Total context window
- `context.maxInputTokens`: Maximum input tokens
- `context.maxOutputTokens`: Maximum output tokens

**Compaction:**
- Automatic when approaching context limit
- Threshold configurable via `autoCompactionThreshold`
- Quality degrades around 60% context fill [COMMUNITY EVIDENCE: Kilo engineers]
- Compaction at 95% is too late for quality

**Pruning:**
- Large tool outputs (>2000 chars) trimmed
- Protected tools preserved (e.g., skill tool)
- Payload limit: 1.25 MB before aggressive pruning

### 3.4 Agent System (OFFICIAL FACT)

**Built-in Agents:**
- `code`: Default coding agent
- `plan`: Architecture/planning
- `ask`: Read-only Q&A
- `debug`: Root-cause analysis

**Custom Agents:**
- Defined in `kilo.jsonc` under `agents`
- Per-agent model pinning supported
- Per-agent permissions supported
- Loaded from `.kilo/agent/*.md`

### 3.5 Skills System (OFFICIAL FACT)

**Purpose:** Load specialized instructions on demand

**Location:** `.kilo/skills/*/SKILL.md`

**Activation:** Via `skill` tool or automatic detection

**Benefits:**
- Progressive disclosure (not monolithic AGENTS.md)
- Phase-specific context loading
- Reusable across projects

### 3.6 MCP Integration (OFFICIAL FACT)

**Configuration:**
```jsonc
{
  "mcp": {
    "servers": {
      "server-name": {
        "command": "npx",
        "args": ["-y", "package-name"],
        "env": { "API_KEY": "..." }
      }
    }
  }
}
```

**Status:**
- Kilo Code supports MCP natively (v7+)
- Tool limit: ~40 tools before selection degradation [COMMUNITY EVIDENCE]
- Each MCP server adds tools to context

### 3.7 Agent Manager and Worktrees (OFFICIAL FACT)

**Agent Manager:**
- Multi-session orchestration panel
- Git worktree isolation per session
- Parallel agent execution
- Integrated terminals per worktree

**Worktree Isolation:**
- Each worktree: isolated repo copy on own branch
- State shared: Snapshot trackState
- State isolated: directory-keyed InstanceState

### 3.8 Local Provider Support (OFFICIAL FACT)

**OpenAI-Compatible Provider:**
```jsonc
{
  "providers": {
    "local-mlx": {
      "type": "openai-compatible",
      "baseUrl": "http://127.0.0.1:8000/v1",
      "apiKey": "not-needed",
      "modelId": "default"
    }
  }
}
```

**Context Limits:**
- Must match Rapid-MLX configuration
- Recommended: `maxInputTokens: 24576`, `maxOutputTokens: 4096`

---

## 4. Community Findings and Their Confidence

### 4.1 Performance Reports

| Finding | Hardware | Model | Confidence | Source |
|---------|----------|-------|------------|--------|
| 67 tok/s decode | M3 Ultra 256 GB | Qwen3.6-35B-A3B-4bit | HIGH | Rapid-MLX README |
| 70-80 tok/s | M4 Pro 48 GB | Qwen3.5-35B-A3B Q4 | HIGH | RunAIHome benchmark |
| 14-15 tok/s | M4 Pro 24 GB | Gemma 3 27B MLX | MEDIUM | Reddit r/LocalLLaMA |
| 18 tok/s with MTP | M4 Pro 48 GB | Qwen3.6-27B | MEDIUM | Medium article |
| 75-80 tok/s | M4 Pro 48 GB | Qwen3-Coder-30B-A3B | MEDIUM | PopularAI.org |

### 4.2 Quality Comparisons

| Finding | Evidence | Confidence |
|---------|----------|------------|
| Qwen3.6-27B > 35B-A3B for coding | SWE-bench 77.2 vs 73.4 | HIGH |
| Qwen3.6-35B-A3B > 27B for math | AIME 92.7 vs 87.8 | HIGH |
| Q4 to Q6 significant quality gain for coding | Reddit reports | MEDIUM |
| OptiQ breaks tool calling | HuggingFace discussion | HIGH |
| KV cache quantization impacts quality | Community reports | MEDIUM |

### 4.3 Stability Reports

| Finding | Confidence | Notes |
|---------|------------|-------|
| Rapid-MLX stable for single-user | HIGH | Official benchmarks |
| Concurrent requests need BatchedEngine | HIGH | Official docs |
| Long context (>32K) causes memory pressure | HIGH | Multiple reports |
| Thinking loops in Qwen3.6 | MEDIUM | Reddit reports, mitigated by disable |
| Multi-turn tool calling stable in Rapid-MLX | HIGH | Official tests |

---

## 5. Model and Quantization Comparison

### 5.1 Candidates for 48 GB Unified Memory

| Model | Quant | Memory | Speed (est.) | Tool Calling | Reasoning | Quality |
|-------|-------|--------|--------------|--------------|-----------|---------|
| Qwen3.6-35B-A3B | 4-bit | ~20 GB | 60-70 tok/s | Excellent | Excellent | Good |
| Qwen3.6-35B-A3B | 8-bit | ~40 GB | 40-50 tok/s | Excellent | Excellent | Better |
| Qwen3.6-27B | 4-bit | ~17 GB | 50-60 tok/s | Excellent | Excellent | Best coding |
| Qwen3.6-27B | 6-bit | ~25 GB | 40-50 tok/s | Excellent | Excellent | Better |
| Qwen3.6-27B | 8-bit | ~34 GB | 30-40 tok/s | Excellent | Excellent | Best |

### 5.2 Quality vs Speed Trade-offs

**Qwen3.6-35B-A3B-4bit (RECOMMENDED BASELINE):**
- Pros: Fast (MoE, ~3B active), good tool calling, fits comfortably
- Cons: Slightly lower coding quality than 27B dense
- Best for: Speed-critical agent loops, tool-heavy workflows

**Qwen3.6-27B-4bit (ALTERNATIVE):**
- Pros: Best coding quality, dense model consistency
- Cons: Slower (all 27B active), less context headroom
- Best for: Quality-critical reasoning, complex code generation

**Qwen3.6-35B-A3B-8bit (A/B CANDIDATE):**
- Pros: Higher quality, better for final decisions
- Cons: Tight memory fit, slower, less context headroom
- Best for: Final review phase, quality gates

### 5.3 Hybrid Architecture Evaluation

**Hypothesis: Fast 35B-A3B executor + slower dense reviewer**

| Aspect | Assessment | Evidence |
|--------|------------|----------|
| Quality benefit | MARGINAL | 27B only slightly better on coding |
| Complexity cost | HIGH | Two model loads, context transfer |
| Memory impact | HIGH | Cannot fit both simultaneously |
| Latency impact | HIGH | Model switching overhead |
| **Verdict** | NOT RECOMMENDED | Single model + cloud fallback better |

**Hypothesis: Local executor + cloud final reviewer**

| Aspect | Assessment | Evidence |
|--------|------------|----------|
| Quality benefit | SIGNIFICANT | Cloud models exceed local on reasoning |
| Complexity cost | MEDIUM | One handoff, structured artifact |
| Memory impact | NONE | Cloud runs separately |
| Latency impact | LOW | Only for final review |
| **Verdict** | RECOMMENDED | Use for quality gates only |

---

## 6. Recommended Target Architecture

### 6.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     KILO CODE 7.3.41                            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    PRIMARY AGENT                           │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │  │
│  │  │   AGENTS.md │  │   Skills    │  │  Commands   │       │  │
│  │  │  (minimal)  │  │ (on-demand) │  │ (slash)     │       │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘       │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│  ┌───────────────────────────┼───────────────────────────────┐  │
│  │                      TOOLS                                  │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────────┐  │  │
│  │  │  Bash   │ │  Read   │ │  Write  │ │ Custom Tools    │  │  │
│  │  │(scripts)│ │ (files) │ │(artifacts)│ │(DB, Web)       │  │  │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────────────┘  │  │
│  └───────────────────────────┼───────────────────────────────┘  │
│                              │                                   │
│  ┌───────────────────────────┼───────────────────────────────┐  │
│  │                    MCP SERVERS                             │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │  │
│  │  │ Brave Search│  │   SQLite    │  │  (minimal set)  │   │  │
│  │  │  (web)      │  │  (read-only)│  │                 │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RAPID-MLX v0.6.83+                           │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Qwen3.6-35B-A3B-4bit                                     │  │
│  │  - Tool parser: auto (qwen3_coder)                        │  │
│  │  - Reasoning parser: qwen3                                │  │
│  │  - Thinking: disabled for tools, enabled for synthesis    │  │
│  │  - Context: 24K input / 4K output                         │  │
│  │  - Cache: prefix cache enabled                            │  │
│  └───────────────────────────────────────────────────────────┘  │
│  Endpoint: http://127.0.0.1:8000/v1                             │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Key Design Decisions

1. **Single Primary Agent:** One Qwen agent handles all phases with Skills loaded on demand
2. **Sequential Tools:** One tool call at a time for reliability
3. **Phase Handoffs:** Structured artifacts between phases, not subagent delegation
4. **Minimal MCP:** Only Brave Search and read-only SQLite MCP enabled by default
5. **Script-First:** Deterministic scripts for computation, LLM for decisions
6. **Cloud Fallback:** Optional cloud model for final review quality gate

---

## 7. Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         BETTING PIPELINE FLOW                              │
└────────────────────────────────────────────────────────────────────────────┘

Phase A: Settlement (S0)
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Script:    │───▶│   Script:    │───▶│   Artifact:  │
│   Settle     │    │   Validate   │    │   phase-A-   │
│   Bets       │    │   Results    │    │   handoff.md │
└──────────────┘    └──────────────┘    └──────────────┘
       │                   │                    │
       ▼                   ▼                    ▼
  [Deterministic]    [Deterministic]      [Structured]

Phase B: Discovery (S1-S1e)
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Script:    │───▶│   LLM:       │───▶│   Artifact:  │
│   Fetch      │    │   Analyze    │    │   phase-B-   │
│   Fixtures   │    │   Shortlist  │    │   handoff.md │
└──────────────┘    └──────────────┘    └──────────────┘
       │                   │                    │
       ▼                   ▼                    ▼
  [Deterministic]    [Skill: discovery]   [Structured]

Phase C: Tipster Aggregation (S2)
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Script:    │───▶│   LLM:       │───▶│   Artifact:  │
│   Aggregate  │    │   Validate   │    │   phase-C-   │
│   Tips       │    │   Tips       │    │   handoff.md │
└──────────────┘    └──────────────┘    └──────────────┘

Phase D: Enrichment & Modelling (S2.3-S7)
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   MCP:       │───▶│   LLM:       │───▶│   Artifact:  │
│   Web Search │    │   Enrich     │    │   phase-D-   │
│   + Fetch    │    │   + Model    │    │   handoff.md │
└──────────────┘    └──────────────┘    └──────────────┘

Phase E: Construction & Validation (S8-S10)
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   LLM:       │───▶│   Reviewer:  │───▶│   Artifact:  │
│   Build      │    │   (local or  │    │   final-     │
│   Coupon     │    │   cloud)     │    │   decision.md│
└──────────────┘    └──────────────┘    └──────────────┘

Legend:
[Deterministic] = Script execution, no LLM
[Skill: X] = Skill loaded on demand
[Structured] = JSON/Markdown artifact
[LLM] = Rapid-MLX inference
[MCP] = MCP server call
```

---

## 8. Agent-Role Matrix

| Role | Agent | Model | Thinking | Tools | Skill |
|------|-------|-------|----------|-------|-------|
| Phase Controller | Primary | Qwen3.6-35B-A3B | Off | Bash, Read, Write | betting-pipeline-runtime |
| Script Executor | Primary | Qwen3.6-35B-A3B | Off | Bash | (none) |
| DB Analyst | Primary | Qwen3.6-35B-A3B | Off | sqlite_read_query | (none) |
| Web Researcher | Primary | Qwen3.6-35B-A3B | Off | brave_search, webfetch | (none) |
| Evidence Synthesizer | Primary | Qwen3.6-35B-A3B | On | Read, Write | (none) |
| Skeptic/Reviewer | Primary (or Cloud) | Qwen3.6-35B-A3B or Claude | On | Read | (none) |
| Final Decision | Primary | Qwen3.6-35B-A3B | On | Write | (none) |

**Key Insight:** All roles use the **same primary agent** with different thinking modes and tool access. Skills are loaded on demand for pipeline orchestration, not for each role.

---

## 9. Model/Reasoning-Mode Matrix

| Phase | Thinking Mode | Reasoning Parser | Tool Parser | Rationale |
|-------|---------------|------------------|-------------|-----------|
| S0 (Settlement) | Off | qwen3 | qwen3_coder | Deterministic scripts only |
| S1 (Discovery) | Off | qwen3 | qwen3_coder | Tool-heavy, speed priority |
| S2 (Aggregation) | Off | qwen3 | qwen3_coder | Structured validation |
| S2.3-S5 (Enrichment) | Off | qwen3 | qwen3_coder | Web research, tool calls |
| S6-S7 (Modelling) | On | qwen3 | qwen3_coder | Deep reasoning required |
| S8 (Construction) | On | qwen3 | qwen3_coder | Synthesis and decision |
| S9-S10 (Validation) | On | qwen3 | qwen3_coder | Final review, quality gate |

**Configuration:**
```bash
# Non-thinking mode (default for tools)
--reasoning-parser qwen3 --default-chat-template-kwargs '{"enable_thinking": false}'

# Thinking mode (for synthesis)
# Pass enable_thinking: true in request body
```

---

## 10. Tool and MCP Matrix

### 10.1 Built-in Tools (Always Enabled)

| Tool | Purpose | Permission | Output Limit |
|------|---------|------------|---------------|
| `read` | Read files | Allow | 2000 lines |
| `write` | Write artifacts | Ask | - |
| `edit` | Edit files | Ask | - |
| `glob` | Find files | Allow | 100 results |
| `grep` | Search content | Allow | 50 results |
| `bash` | Run scripts | Ask (auto for allowlist) | 8 KB |

### 10.2 MCP Servers (Minimal Set)

| Server | Purpose | Tools | Enabled For |
|--------|---------|-------|-------------|
| Brave Search | Web search | `brave_web_search`, `brave_news_search` | All phases |
| SQLite (read-only) | DB queries | `sqlite_read_query`, `sqlite_describe_table` | All phases |

### 10.3 Custom Tools (Project-Level)

| Tool | Purpose | Implementation |
|------|---------|----------------|
| `bet_sqlite_query` | Betting DB queries | Python script with allowlist |
| `bet_script_run` | Pipeline scripts | Bash wrapper with validation |

### 10.4 Disabled by Default

| Tool | Reason |
|------|--------|
| Playwright MCP | Last resort only, high token cost |
| Sequential Thinking MCP | Qwen3.6 has native reasoning |
| Memory MCP | Use structured artifacts instead |

---

## 11. Script-Execution Design

### 11.1 Execution Model

**Approach:** Built-in Bash tool with project-level allowlist and validation

**Rationale:**
- Kilo's Bash tool is sufficient for script execution
- Custom tool adds complexity without clear benefit
- Allowlist provides safety without MCP overhead

### 11.2 Safety Measures

| Measure | Implementation |
|---------|----------------|
| Command allowlist | Regex patterns in kilo.jsonc |
| Working directory | Fixed to project root |
| Timeout | 120 seconds default |
| Output limit | 8 KB, truncate with tail |
| Exit code | Required in result envelope |
| Stderr | Preserved in result |
| Environment | Isolated, no secrets |

### 11.3 Result Envelope

```json
{
  "status": "success" | "error" | "timeout",
  "command_id": "uuid",
  "started_at": "ISO-8601",
  "duration_ms": 1234,
  "exit_code": 0,
  "summary": "First 500 chars of stdout",
  "metrics": { "rows_processed": 100 },
  "warnings": ["Large output truncated"],
  "artifact_path": "/tmp/command_id.txt",
  "truncated": false
}
```

### 11.4 Auto-Approval Rules

| Category | Commands | Auto-Approve |
|----------|----------|--------------|
| Read-only scripts | `scripts/s0-*.fish`, `scripts/query-*.fish` | Yes |
| Data fetch | `scripts/fetch-*.fish` | Yes |
| Validation | `scripts/validate-*.fish` | Yes |
| Mutation | `scripts/update-*.fish` | No (Ask) |
| Database write | Any | No (Ask) |
| Arbitrary | Outside allowlist | No (Deny) |

---

## 12. Database-Access Design

### 12.1 Approach

**Recommendation:** Custom read-only Kilo tool (`bet_sqlite_query`)

**Rationale:**
- MCP SQLite servers add context overhead
- Custom tool provides tighter control
- Read-only enforcement at Python level
- Query validation before execution

### 12.2 Safety Measures

| Measure | Implementation |
|---------|----------------|
| Read-only | SQLite connection with `uri?mode=ro` |
| Database allowlist | Path validation against known DBs |
| Statement validation | Regex reject: `INSERT`, `UPDATE`, `DELETE`, `PRAGMA`, `ATTACH` |
| Query timeout | 30 seconds |
| Row limit | 1000 rows |
| Byte limit | 64 KB |
| Parameter binding | Required for user input |

### 12.3 Query Templates vs Natural Language

**Recommendation:** Query templates selected by LLM

**Rationale:**
- Natural language to SQL is unreliable
- Templates provide deterministic results
- LLM selects template + parameters
- Provenance tracked in artifact

### 12.4 Output Format

```json
{
  "status": "success",
  "query_id": "uuid",
  "template": "get_match_stats",
  "params": { "match_id": 12345 },
  "rows": 50,
  "columns": ["team", "goals", "xG"],
  "data": [...],
  "truncated": false,
  "query_time_ms": 45
}
```

---

## 13. Internet-Research Design

### 13.1 Layered Strategy

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Structured Sports API (future)                     │
│ - Direct API calls via scripts                              │
│ - Deterministic data retrieval                              │
│ - No LLM interpretation needed                              │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Brave Search MCP (current)                        │
│ - `brave_web_search` for discovery                         │
│ - `brave_news_search` for recent events                    │
│ - Citations included                                       │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: WebFetch (current)                                │
│ - `webfetch` for full page content                         │
│ - Markdown conversion                                      │
│ - Bounded output (first 2000 lines)                        │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: Playwright MCP (fallback only)                    │
│ - JavaScript rendering                                      │
│ - Login-required pages                                     │
│ - High token cost (~114K tokens per task)                  │
│ - Requires explicit approval                               │
└─────────────────────────────────────────────────────────────┘
```

### 13.2 Source Handling

| Aspect | Implementation |
|--------|----------------|
| Provenance | URL + retrieval timestamp in artifact |
| Conflicts | Both sources recorded, confidence adjusted |
| Freshness | `freshness: "pw"` for last 7 days |
| Injection | Sanitize HTML, strip scripts |

### 13.3 Provider Comparison

| Provider | Latency | Quality | Cost | MCP Support |
|----------|---------|---------|------|-------------|
| Brave Search | 669ms | High | Free tier | Yes |
| Exa | ~1s | High | Paid | Yes |
| Tavily | 998ms | Medium | Free tier | Yes |
| Firecrawl | ~1.3s | High | Paid | Yes |

**Recommendation:** Brave Search MCP for baseline (privacy, independent index, low latency)

---

## 14. Reasoning and Review Workflow

### 14.1 Reasoning Modes

| Mode | When | Output |
|------|------|--------|
| Non-thinking | Tool execution, scripts | Direct response |
| Thinking | Synthesis, decisions | `<think>` blocks preserved |
| Preserved | Multi-turn reasoning | Thinking context retained |

### 14.2 Structured Artifacts (Instead of Hidden CoT)

```markdown
# Evidence Table

| Source | Claim | Confidence | Verified |
|--------|-------|------------|----------|
| DB: matches/12345 | Home team: Arsenal | HIGH | Yes |
| Web: bbc.co.uk/... | Injury: Saka doubtful | MEDIUM | Yes |

# Assumptions

1. Lineups announced 1 hour before kickoff
2. Weather conditions stable

# Unresolved Conflicts

- Source A: xG 1.2
- Source B: xG 1.5
- Resolution: Use Source A (official stats)

# Candidate Hypotheses

1. Arsenal win (confidence: 0.72)
2. Draw (confidence: 0.18)
3. Arsenal loss (confidence: 0.10)

# Final Decision

**Pick:** Arsenal -1.5 Asian Handicap
**Confidence:** 0.68
**Reasoning:** [structured reasoning]
**Risks:** [list of risks]
**Abstention Threshold:** < 0.60 confidence
```

### 14.3 Review Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ Local Review (Primary Agent)                               │
│ - Self-consistency check                                   │
│ - Evidence validation                                      │
│ - Confidence calibration                                    │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │ Confidence >= 0.80?   │
              └───────────────────────┘
                    │           │
                   Yes          No
                    │           │
                    ▼           ▼
            ┌───────────┐  ┌─────────────────────┐
            │ Proceed   │  │ Cloud Review         │
            │ to output │  │ (Claude/GPT)         │
            └───────────┘  │ - Independent check  │
                           │ - Quality gate      │
                           │ - Final decision    │
                           └─────────────────────┘
```

---

## 15. Context and State-Management Strategy

### 15.1 Context Budget

| Component | Tokens | Notes |
|-----------|--------|-------|
| System prompt (AGENTS.md) | ~2,000 | Minimal, load Skills on demand |
| Skill (when loaded) | ~1,500 | One at a time |
| Tool definitions | ~3,000 | Minimal MCP set |
| Conversation history | ~8,000 | Preserve recent |
| Tool outputs | ~8,000 | Pruned aggressively |
| Working context | ~2,000 | Current task |
| **Total** | ~24,500 | Safe operational limit |

### 15.2 Thresholds

| Threshold | Value | Action |
|-----------|-------|--------|
| Checkpoint | 20,000 tokens | Write artifact, clear history |
| No-new-research | 22,000 tokens | Complete with existing evidence |
| Mandatory handoff | 24,000 tokens | End phase, start new session |
| Compaction | 26,000 tokens | Auto-compact (quality risk) |

### 15.3 State Persistence

| State | Storage | Format |
|-------|---------|--------|
| Phase progress | `.kilo/state/phase-X-handoff.md` | Markdown |
| Evidence | `.kilo/artifacts/evidence-table.json` | JSON |
| Decisions | `.kilo/artifacts/decision-log.json` | JSON |
| Session | `.kilo/memory/session-state.md` | Markdown |

### 15.4 Session Boundaries

| Trigger | Action |
|---------|--------|
| Phase complete | New session for next phase |
| Context > 24K | Mandatory handoff |
| Compaction failure | Fresh session |
| Model switch | Fresh session |

---

## 16. Observability and Security Model

### 16.1 Observability Fields

| Field | Source | Purpose |
|-------|--------|---------|
| request_id | Kilo | Trace correlation |
| phase_id | Pipeline | Phase tracking |
| session_id | Kilo | Session correlation |
| model | Rapid-MLX | Model identification |
| thinking_mode | Request | Reasoning mode |
| prompt_tokens | Rapid-MLX | Context usage |
| completion_tokens | Rapid-MLX | Output size |
| tool_name | Kilo | Tool invocation |
| tool_duration_ms | Kilo | Tool performance |
| tool_exit_code | Kilo | Tool success/failure |
| latency_ms | Kilo | End-to-end latency |
| ttft_ms | Rapid-MLX | Time to first token |
| cache_hit | Rapid-MLX | Cache effectiveness |
| finish_reason | Rapid-MLX | Completion status |
| memory_pressure | macOS | System health |

### 16.2 Apple Silicon Monitoring

| Metric | Method | Limitation |
|--------|--------|-------------|
| Process RSS | `ps` or `top` | Approximate |
| Memory pressure | `memory_pressure` | System-level |
| Swap usage | `vm_stat` | System-level |
| Thermal state | `pmset -g therm` | System-level |
| MLX memory | Not available externally | Cannot measure from separate process |

**Recommendation:** Monitor system-level metrics, accept that MLX internal memory is opaque.

### 16.3 Security and Redaction

| Category | Policy |
|----------|--------|
| Secrets | Never log, never pass to LLM |
| API keys | Environment variables only |
| Credentials | `.env` excluded from all tools |
| PII | Redact in logs |
| Betting stakes | Never in artifacts |

---

## 17. Rapid-MLX Baseline Profile

### 17.1 Startup Command

```bash
rapid-mlx serve qwen3.6-35b-a3b-4bit \
  --port 8000 \
  --reasoning-parser qwen3 \
  --default-chat-template-kwargs '{"enable_thinking": false}'
```

### 17.2 Configuration

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Model | qwen3.6-35b-a3b-4bit | Fits 48 GB, fast MoE |
| Port | 8000 | Standard localhost |
| Reasoning parser | qwen3 | Required for Qwen3.6 |
| Default thinking | false | Speed for tool calls |
| Max output tokens | 4096 | Per request limit |
| Context limit | 24576 input | Safe operational limit |

### 17.3 Expected Performance

| Metric | Value | Source |
|--------|-------|--------|
| Decode speed | 60-70 tok/s | Official benchmark (M3 Ultra) |
| TTFT (cached) | 0.08s | Official benchmark |
| TTFT (cold) | ~277ms | Official benchmark |
| Tool calling | 100% | Official benchmark |
| Memory usage | ~20-24 GB | Community reports |

---

## 18. Rapid-MLX A/B Tuning Candidates

### 18.1 A/B Test Matrix

| Candidate | Change | Hypothesis | Test |
|-----------|--------|------------|------|
| 8-bit quantization | `qwen3.6-35b-a3b-8bit` | Higher quality | Quality benchmark |
| DFlash | `--draft-kind dflash` | Faster decode | Speed benchmark |
| KV cache 8-bit | `--kv-bits 8` | More context | Memory benchmark |
| Prefill step | `--prefill-step-size 8192` | Faster prefill | TTFT benchmark |
| Thinking preserved | `enable_thinking: true` | Better reasoning | Quality benchmark |

### 18.2 Test Protocol

1. **Baseline:** Run benchmark with default config
2. **Variant:** Run same benchmark with one change
3. **Metrics:** Compare quality, speed, memory
4. **Decision:** Adopt if quality >= baseline AND speed/memory improves

### 18.3 Not Recommended for Baseline

| Feature | Reason |
|---------|--------|
| MTP | Requires different runtime, complexity |
| TurboQuant KV | Quality impact uncertain |
| Continuous batching | Single-user workload |
| OptiQ quantization | Breaks tool calling |

---

## 19. Kilo Configuration Strategy

### 19.1 Config File Structure

```
.kilo/
├── config/
│   └── kilo.jsonc          # Main config
├── agent/
│   └── betting-agent.md    # Minimal agent definition
├── skills/
│   ├── betting-pipeline-runtime/
│   │   └── SKILL.md        # Pipeline orchestration
│   └── context-safe-agentics/
│       └── SKILL.md        # Context management
├── commands/
│   ├── phase-A.md          # Phase A command
│   ├── phase-B.md          # Phase B command
│   └── ...
└── rules/
    ├── betting-anti-hallucination.md
    ├── tool-names.md
    └── ...
```

### 19.2 kilo.jsonc Template

```jsonc
{
  "providers": {
    "local-mlx": {
      "type": "openai-compatible",
      "baseUrl": "http://127.0.0.1:8000/v1",
      "apiKey": "not-needed",
      "modelId": "default",
      "context": {
        "maxTokens": 32768,
        "maxInputTokens": 24576,
        "maxOutputTokens": 4096
      }
    }
  },
  
  "agents": {
    "betting-agent": {
      "model": "local-mlx",
      "systemPrompt": ".kilo/agent/betting-agent.md",
      "permissions": {
        "read": "allow",
        "write": "ask",
        "edit": "ask",
        "bash": "ask",
        "glob": "allow",
        "grep": "allow"
      }
    }
  },
  
  "mcp": {
    "servers": {
      "brave-search": {
        "command": "npx",
        "args": ["-y", "@brave/brave-search-mcp-server"],
        "env": {
          "BRAVE_API_KEY": "${BRAVE_API_KEY}"
        }
      }
    }
  },
  
  "autoCompactionThreshold": 0.75,
  
  "tools": {
    "bash": {
      "allowlist": [
        "scripts/s0-*.fish",
        "scripts/query-*.fish",
        "scripts/fetch-*.fish",
        "scripts/validate-*.fish"
      ],
      "timeout": 120000,
      "outputLimit": 8192
    }
  }
}
```

### 19.3 Minimal AGENTS.md

```markdown
# Betting Pipeline Agent

## Role
Execute multi-phase sports betting research and decision pipeline.

## Core Principles
1. Script-first: Use deterministic scripts for computation
2. Evidence-based: Every claim must have a source
3. Structured artifacts: Output JSON/Markdown, not prose
4. Phase isolation: Complete one phase before starting next

## Tools
- Bash: Execute pipeline scripts
- Read/Write: Manage artifacts
- MCP: Brave Search, SQLite (read-only)

## Skills
Load `betting-pipeline-runtime` for phase orchestration.

## Constraints
- Never invent odds, lineups, or statistics
- Never execute betting actions
- Always cite sources with timestamps
```

---

## 20. Benchmark and Acceptance Gates

### 20.1 Runtime Tests

| Test | Pass Criteria |
|------|---------------|
| Model startup | < 30 seconds to ready |
| Chat completion | < 5 seconds for 100 tokens |
| Tool call (single) | < 10 seconds end-to-end |
| Tool chain (5 sequential) | < 60 seconds total |
| Cancellation recovery | Clean abort, no hang |
| Long session (50 turns) | No memory leak, no crash |

### 20.2 Script Tests

| Test | Pass Criteria |
|------|---------------|
| Successful script | Exit code 0, valid JSON |
| Failed script | Exit code non-zero, error captured |
| Timeout | Graceful termination after 120s |
| Large output | Truncation with artifact path |
| Malformed JSON | Error reported, no crash |

### 20.3 Database Tests

| Test | Pass Criteria |
|------|---------------|
| Bounded aggregation | < 1000 rows, < 64 KB |
| Forbidden write | Rejected with error |
| SQL injection attempt | Sanitized, rejected |
| Timeout | Graceful termination after 30s |

### 20.4 Internet Tests

| Test | Pass Criteria |
|------|---------------|
| Current information | Results from last 7 days |
| Source disagreement | Both recorded, confidence adjusted |
| Inaccessible page | Error reported, fallback used |
| Prompt injection | Sanitized, no execution |

### 20.5 Reasoning Tests

| Test | Pass Criteria |
|------|---------------|
| Multi-source synthesis | All sources cited |
| Conflict resolution | Resolution documented |
| Missing data | Abstention when evidence insufficient |
| Final decision | Confidence >= 0.60 or abstain |

### 20.6 Scoring Weights

| Category | Weight |
|----------|--------|
| Tool and script reliability | 25% |
| Decision correctness | 25% |
| Evidence quality and provenance | 20% |
| Context stability | 10% |
| Memory stability | 10% |
| Latency | 7% |
| Tokens per second | 3% |

---

## 21. Incremental Implementation Roadmap

### Phase 1: Rapid-MLX Raw Baseline
- Install Rapid-MLX v0.6.83+
- Download Qwen3.6-35B-A3B-4bit
- Verify startup and basic chat
- Measure baseline performance
- **Gate:** 60+ tok/s, 100% tool calling in isolation

### Phase 2: Minimal Kilo Integration
- Configure local OpenAI-compatible provider
- Set context limits (24K/4K)
- Test single tool call from Kilo
- Verify cache behavior
- **Gate:** Tool call success, cache hit on repeat

### Phase 3: Script Executor
- Implement Bash allowlist
- Add result envelope parsing
- Test timeout handling
- Test large output handling
- **Gate:** All script tests pass

### Phase 4: Read-Only Database Access
- Implement custom SQLite tool
- Add query validation
- Test row/byte limits
- Test forbidden operations
- **Gate:** All database tests pass

### Phase 5: Internet Research
- Configure Brave Search MCP
- Test web search
- Test webfetch
- Test source provenance
- **Gate:** All internet tests pass

### Phase 6: Reasoning and Reviewer
- Implement thinking mode toggle
- Create evidence artifact format
- Test multi-source synthesis
- Test conflict resolution
- **Gate:** All reasoning tests pass

### Phase 7: Context Hardening
- Implement phase handoffs
- Add checkpoint thresholds
- Test long sessions
- Test compaction recovery
- **Gate:** No context overflow in 50-turn test

### Phase 8: Tuning
- A/B test 8-bit quantization
- A/B test DFlash
- A/B test KV cache options
- Select optimal configuration
- **Gate:** Quality >= baseline, speed improved

### Phase 9: Soak
- Run full pipeline 10 times
- Monitor memory stability
- Monitor context growth
- Identify failure modes
- **Gate:** 0 crashes, < 5% quality variance

### Phase 10: Production Canary
- Deploy to single user
- Monitor for 1 week
- Collect metrics
- Iterate on issues
- **Gate:** User satisfaction, no critical bugs

---

## 22. Risks, Unknowns, and Rejected Alternatives

### 22.1 Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Context overflow | Medium | High | Strict thresholds, phase handoffs |
| Memory pressure | Medium | High | Monitor system metrics, restart on threshold |
| Tool calling degradation | Low | High | Auto-recovery, fallback to non-thinking |
| Web source unreliability | High | Medium | Multiple sources, confidence adjustment |
| Model quality insufficient | Low | Medium | Cloud fallback for final review |

### 22.2 Unknowns

| Unknown | Status | Resolution |
|---------|--------|------------|
| Actual tok/s on M4 Pro 48 GB | Requires test | Benchmark in Phase 1 |
| KV cache memory at 16K context | Requires test | Measure in Phase 1 |
| Multi-turn tool calling stability | Requires test | Test in Phase 2 |
| Optimal thinking mode toggle | Requires test | A/B test in Phase 8 |

### 22.3 Rejected Alternatives

| Alternative | Reason Rejected |
|-------------|-----------------|
| Multi-agent orchestration | Complexity > benefit, context fragmentation |
| MTP speculative decoding | Requires different runtime, not proven for tools |
| TurboQuant KV cache | Quality impact uncertain, experimental |
| OptiQ quantization | Breaks tool calling (confirmed) |
| Sequential-thinking MCP | Qwen3.6 has native reasoning |
| Playwright for every request | High token cost, last resort only |
| Natural language to SQL | Unreliable, use templates instead |
| Monolithic AGENTS.md | Context bloat, use Skills instead |

---

## 23. Definition of Production-Ready

A configuration is **production-ready** when:

1. **Reliability:** 99%+ tool call success rate over 1000 calls
2. **Stability:** Zero crashes in 10-hour soak test
3. **Quality:** Decision correctness >= 80% on benchmark scenarios
4. **Evidence:** 100% of claims have cited sources
5. **Context:** Zero context overflow errors in normal operation
6. **Memory:** No memory leaks, stable RSS over long sessions
7. **Latency:** P95 tool call latency < 15 seconds
8. **Recovery:** Graceful handling of all failure modes
9. **Observability:** All critical metrics logged and queryable
10. **Security:** No secrets in logs, read-only DB enforced

---

## 24. Final Concise Recommendation

**Use Rapid-MLX v0.6.83+ with Qwen3.6-35B-A3B-4bit as the single local model for all pipeline phases. Configure Kilo Code 7.3.41 with minimal AGENTS.md, phase-specific Skills loaded on demand, and sequential tool calls. Implement strict context limits (24K input, 4K output), phase handoffs with structured artifacts, and optional cloud review for quality gates.**

**Do not implement multi-agent orchestration, MTP, or TurboQuant for the baseline. Do not use Playwright except as a last resort. Do not enable natural language to SQL.**

**Start with Phase 1 (Rapid-MLX baseline) and progress through the 10-phase roadmap, passing all acceptance gates before proceeding.**

---

## 25. Implementation Prompt Outline

The implementation will be divided into **10 certified phases**, each with:
- Clear objectives
- Specific commands and configurations
- Acceptance gates
- Rollback procedures

### Phase Structure

1. **Phase 1: Rapid-MLX Raw Baseline**
   - Install and verify Rapid-MLX
   - Download and test Qwen3.6-35B-A3B-4bit
   - Benchmark performance
   - Gate: 60+ tok/s, tool calling works

2. **Phase 2: Minimal Kilo Integration**
   - Configure kilo.jsonc for local provider
   - Set context limits
   - Test single tool call
   - Gate: Tool call from Kilo succeeds

3. **Phase 3: Script Executor**
   - Implement Bash allowlist
   - Add result envelope
   - Test error handling
   - Gate: All script tests pass

4. **Phase 4: Read-Only Database Access**
   - Implement custom SQLite tool
   - Add validation and limits
   - Test forbidden operations
   - Gate: All database tests pass

5. **Phase 5: Internet Research**
   - Configure Brave Search MCP
   - Test search and fetch
   - Verify provenance
   - Gate: All internet tests pass

6. **Phase 6: Reasoning and Reviewer**
   - Implement thinking toggle
   - Create evidence artifacts
   - Test synthesis
   - Gate: All reasoning tests pass

7. **Phase 7: Context Hardening**
   - Implement handoffs
   - Add thresholds
   - Test long sessions
   - Gate: No overflow in 50-turn test

8. **Phase 8: Tuning**
   - A/B test configurations
   - Select optimal settings
   - Document results
   - Gate: Quality >= baseline

9. **Phase 9: Soak**
   - Run full pipeline repeatedly
   - Monitor stability
   - Identify issues
   - Gate: 0 crashes, stable quality

10. **Phase 10: Production Canary**
    - Deploy to single user
    - Monitor for 1 week
    - Iterate on feedback
    - Gate: User satisfaction

### Implementation Approach

Each phase will be implemented in a **separate Kilo session** with:
- Clear starting state (clean branch or previous phase artifact)
- Specific implementation steps
- Verification commands
- Acceptance criteria
- Rollback instructions

The implementation prompt for each phase will be generated after the previous phase passes its acceptance gate.

---

## References

### Official Sources
1. Rapid-MLX GitHub: https://github.com/raullenchai/Rapid-MLX
2. Kilo Code GitHub: https://github.com/Kilo-Org/kilocode
3. Qwen3.6 GitHub: https://github.com/QwenLM/Qwen3.6
4. MLX Community: https://huggingface.co/mlx-community
5. Unsloth Qwen3.6: https://unsloth.ai/docs/models/qwen3.6

### Community Sources
1. Reddit r/LocalLLaMA: Multiple threads on Qwen3.6 performance
2. RunAIHome: Ollama MLX benchmarks
3. Local AI Master: Apple Silicon buying guide
4. Codersera: Qwen 3.6 local guide

### Benchmark Sources
1. Rapid-MLX README: Official throughput numbers
2. AIMultiple: Search API comparison
3. LLMReference: Qwen3.6-27B vs 35B-A3B comparison

---

**Report Compiled:** 2026-06-11  
**Research Method:** Web search (Brave), official documentation, community reports  
**Confidence Level:** HIGH for official facts, MEDIUM for community evidence, LOW for unverified claims
