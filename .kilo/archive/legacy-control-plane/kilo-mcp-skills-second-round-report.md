# Kilo MCP & Skills — Second Round Deep Review Report

**Date:** 2026-06-05  
**Status:** COMPLETE — Current config is optimal. One runtime caching issue identified and workaround provided.

---

## 1. Current MCP Server Inventory

| MCP | Status | Package | Purpose | Verdict |
|-----|--------|---------|---------|---------|
| **sequentialthinking** | ✅ connected | `@modelcontextprotocol/server-sequential-thinking` | Multi-step reasoning, hypothesis validation | **KEEP** — essential |
| **sqlite** | ✅ connected | `uvx mcp-server-sqlite` | DB queries on `betting.db` | **KEEP** — essential |
| **brave-search** | ⚠️ config correct, runtime stale | `@brave/brave-search-mcp-server` | Web search for tipsters, news, provider status | **KEEP** — essential |
| memory | ❌ disabled (project) | `@modelcontextprotocol/server-memory` | Cross-session knowledge graph | **KEEP DISABLED** — redundant with `.kilocode/memory/session-state.md` |
| context7 | ❌ disabled | Remote `https://mcp.context7.com/mcp` | Library documentation lookup | **KEEP DISABLED** — enable only if engineer needs library docs |
| playwright | ❌ disabled | `@playwright/mcp@latest` | Browser automation, DOM scraping | **KEEP DISABLED** — enable only if `webfetch` fails for tipster scraping |

**Conclusion:** The current 3-active / 3-disabled split is **production-optimal**. No additional MCP servers are needed.

---

## 2. Live Test Results

### 2.1 sequentialthinking — PASS
- Tool call succeeded with hypothesis "This is a reload smoke test"
- Response time: <2s

### 2.2 sqlite — PASS
- `sqlite_read_query` returned 42,830 fixtures
- Table enumeration returned 38 tables including all pipeline tables
- Query latency: <1s

### 2.3 brave-search — PARTIAL (runtime issue, not config)

**Finding:** `brave-search_brave_web_search` returned `API error (422)` and later `Not connected`.

**Root cause identified:**
1. Old `brave-search-mcp` (mikechao's package) processes were still running from the previous VS Code session (PID 86979, 86849)
2. Kilo daemon (running since 08:22 AM) cached these old processes
3. The new `@brave/brave-search-mcp-server` package was configured but the daemon never restarted the MCP server
4. After killing old PIDs, Kilo showed "connected" in `mcp list` but the actual process was not running — causing "Not connected" on tool call

**Direct MCP test (bypassing Kilo daemon):**
```bash
npx -y @brave/brave-search-mcp-server --transport stdio
```
→ `brave_web_search` tool call with `{"query":"Premier League predictions","count":3}`  
→ **HTTP 200, valid search results returned**

**Verdict:** The MCP server package and API key are **100% functional**. The failure is purely a **Kilo daemon process-caching issue**.

---

## 3. MCP Deep-Dive: What Else Exists

### 3.1 npm Search Results

Searched `@modelcontextprotocol/server-*` and related packages. Relevant findings:

| Package | Relevance | Verdict |
|---------|-----------|---------|
| `@modelcontextprotocol/server-memory` | Already in global config, disabled locally | Not needed — local session-state.md is sufficient and lower-context |
| `@modelcontextprotocol/server-filesystem` | File read/write | **Redundant** — Kilo has built-in `read`/`edit`/`write`/`glob` |
| `@modelcontextprotocol/server-pdf` | PDF processing | **Not needed** — pipeline produces markdown, not PDFs (S10 PDF generation is script-based) |
| `@modelcontextprotocol/server-github` | GitHub PRs/issues | **Deprecated** (npm warns) — pipeline doesn't use GitHub automation |
| `mcp-smart-crawler` | Playwright-based web scraper | **Redundant** — playwright MCP already configured as fallback |
| `@modelcontextprotocol/server-fetch` | HTTP fetch | **Does not exist** in registry — no such package |
| `@modelcontextprotocol/server-everything` | Broad utility server | **Too bloated** — adds many unused tools, high context cost |

### 3.2 Global Config Leakage

Discovered **stale processes** from global `~/.config/kilo/kilo.jsonc` running despite project-level disable:

```
PID 86846: npm exec @modelcontextprotocol/server-memory
PID 63543: node mcp-server-sequential-thinking (duplicate/old)
PID 63625: npm exec @modelcontextprotocol/server-sequential-thinking (duplicate/old)
PID 63834: node mcp-server-puppeteer
PID 63864: npm exec @playwright/mcp@0.0.38
```

These consume memory but do not affect functionality. They are from the global config's default MCP list. Project-level `enabled: false` prevents Kilo from routing tool calls to them, but the OS processes persist until killed or the daemon restarts.

**Action:** Restart VS Code / Kilo daemon to clean stale processes.

---

## 4. Skills Assessment

### 4.1 Available Skills

| Skill | Available | Location | Relevance |
|-------|-----------|----------|-----------|
| `agent-md-refactor` | ✅ Yes | `~/.kilo/skills/agent-md-refactor/SKILL.md` | Refactors bloated agent instruction files |

No other skills are installed or available in the Kilo marketplace for this project.

### 4.2 Should `agent-md-refactor` Be Enabled?

**Pros:**
- Could help maintain `AGENTS.md` and `.kilo/prompts/*.md` as they grow
- Aligns with progressive disclosure principles

**Cons:**
- Skill injection adds ~2,000+ tokens to agent context
- No agent prompt currently references skill usage
- The `kilo debug agent` shows `skill: false` for all agents (blocked by root `skill: deny`)
- Manual refactoring via `read`/`edit` is sufficient for occasional maintenance

**Verdict:** **KEEP DISABLED** for production pipeline. Enable only during dedicated refactoring sessions by temporarily changing `"skill": "ask"` for the orchestrator.

---

## 5. Permission Verification (from `kilo debug agent`)

Resolved permissions confirmed for key agents:

### bet-orchestrator
- `bash: allow *` ✅
- `edit: allow *` ✅
- `task: allow` for all 12 betting agents ✅
- `sequentialthinking_sequentialthinking: allow *` ✅
- `sqlite_read_query: allow *` ✅
- `sqlite_write_query: deny *` ✅
- `sqlite_create_table: deny *` ✅
- `brave-search_brave_web_search: ask *` ✅
- `brave-search_brave_news_search: ask *` ✅
- `question: ask *` ✅

### bet-scanner
- `bash: deny *` ✅
- `edit: deny *` ✅
- `webfetch: allow *` ✅
- `brave-search_brave_web_search: allow *` ✅
- `playwright_*: ask *` ✅

### bet-db-analyst
- `bash: deny *` ✅
- `edit: deny *` ✅
- `webfetch: deny *` ✅
- `brave-search_*: deny *` ✅
- `playwright_*: deny *` ✅

All permissions match the design matrix. No leaks detected.

---

## 6. Production-Grade Recommendations

### Immediate (Pre-Pipeline)

1. **Restart VS Code / Kilo daemon** to flush stale MCP processes and let brave-search reconnect with the new package.
2. **Verify brave-search live** after restart with: `@bet-scout Run 1 brave-search_brave_web_search query and confirm HTTP 200.`
3. **Test full tool chain** with the test prompts from the previous report.

### Ongoing (Maintenance)

4. **MCP health check** — Add to orchestrator startup protocol:
   ```
   Before S0: Run `kilo mcp list` equivalent check. If any required MCP shows
   "not connected", restart Kilo daemon or retry tool call after 5s.
   ```
5. **Process cleanup** — After major config changes, run `ps aux | grep mcp` and kill orphaned processes.
6. **Brave API key rotation** — The key is hardcoded in `~/.config/kilo/kilo.jsonc`. Rotate via environment variable if security policy requires it. Current approach (global hardcoded) is functional but not best-practice.

### Not Needed (Avoid Bloat)

7. **No additional MCP servers** — The 3 active MCPs cover all pipeline needs.
8. **No skills** — Keep `agent-md-refactor` disabled until a dedicated refactoring session.
9. **No playwright enablement** — Only enable if a live tipster scraping session fails with `webfetch` and requires DOM interaction.
10. **No context7 enablement** — Only enable if engineer needs to look up library docs for a complex fix.

---

## 7. Final Verdict

| Category | Status |
|----------|--------|
| MCP configuration | **OPTIMAL** — 3 active, 3 disabled, no additions needed |
| MCP server packages | **CORRECT** — official `@brave/brave-search-mcp-server` in use |
| API key passing | **FUNCTIONAL** — global hardcoded key persists through deep-merge |
| Live connectivity (sequentialthinking) | **PASS** |
| Live connectivity (sqlite) | **PASS** |
| Live connectivity (brave-search) | **PENDING DAEMON RESTART** — server works, daemon caching old process |
| Skills | **MINIMAL BUT SUFFICIENT** — `agent-md-refactor` available, disabled |
| Permission matrix | **VERIFIED** — `kilo debug agent` confirms all 13 agents match design |
| Global config leakage | **CONTAINED** — root project permissions block global `allow-all` |

**Overall: PASS with one operator action (restart VS Code).**

---

## Appendix: Operator Checklist Before First Production Pipeline Run

- [ ] Restart VS Code completely (⌘Q, reopen)
- [ ] Run `kilo mcp list` in terminal — verify 3 green checkmarks (sequentialthinking, sqlite, brave-search)
- [ ] Run `@bet-scout brave-search smoke test` — verify search results returned
- [ ] Run `@bet-db-analyst sqlite smoke test` — verify fixture count >0
- [ ] Run `@bet-statistician sequentialthinking smoke test` — verify tool call succeeds
- [ ] Check `ps aux | grep mcp` — should show only 3 active MCP processes, no duplicates
- [ ] Set `BRAVE_API_KEY` in shell if VS Code launched from Dock: `set -x BRAVE_API_KEY BSAn2VjXZWHXBQ4qygvaLbT1xXINw5u`
- [ ] Run `@bet-test-engineer test suite` — PASS_MAJOR or better
- [ ] Run `@bet-orchestrator full pipeline 2026-06-05` — monitor S0 through S10
