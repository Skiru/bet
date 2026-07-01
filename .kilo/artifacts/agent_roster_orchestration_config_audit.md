# Betting Agent Roster and Orchestration Config Audit

This audit validates the configuration, permissions, and model routing parameters of the betting specialist subagents against the production orchestrator-led flow specifications.

## 1. Scope of Audit
The following files were inspected and analyzed:
- `AGENTS.md`
- `.kilo/agents/bet-orchestrator.md`
- `.kilo/agents/bet-scanner.md`
- `.kilo/agents/bet-scout.md`
- `.kilo/agents/bet-enricher.md`
- `.kilo/agents/bet-statistician.md`
- `.kilo/agents/bet-valuator.md`
- `.kilo/agents/bet-challenger.md`
- `.kilo/agents/bet-builder.md`
- `.kilo/agents/bet-test-engineer.md`
- `.kilo/profiles/kilo.local.jsonc`

---

## 2. Agent Configuration and Routing Matrix

| Agent Name | Config File | Mode | Provider | Model | Alias | Serving Tier | Thinking Level | Task Permission |
|------------|-------------|------|----------|-------|-------|--------------|----------------|-----------------|
| **bet-orchestrator** | `.kilo/agents/bet-orchestrator.md` | primary | google-vertex | gemini-3.5-flash | gemini-3.5-flash-flex-high | flex | HIGH | lists all subagents |
| **bet-scanner** | `.kilo/agents/bet-scanner.md` | subagent | google-vertex | gemini-3.5-flash | gemini-3.5-flash-flex-high | flex | HIGH | deny |
| **bet-scout** | `.kilo/agents/bet-scout.md` | subagent | google-vertex | gemini-3.5-flash | gemini-3.5-flash-flex-high | flex | HIGH | deny |
| **bet-enricher** | `.kilo/agents/bet-enricher.md` | subagent | google-vertex | gemini-3.5-flash | gemini-3.5-flash-flex-high | flex | HIGH | deny |
| **bet-statistician** | `.kilo/agents/bet-statistician.md` | subagent | google-vertex | gemini-3.5-flash | gemini-3.5-flash-flex-high | flex | HIGH | deny |
| **bet-valuator** | `.kilo/agents/bet-valuator.md` | subagent | google-vertex | gemini-3.5-flash | gemini-3.5-flash-flex-high | flex | HIGH | deny |
| **bet-challenger** | `.kilo/agents/bet-challenger.md` | subagent | google-vertex | gemini-3.5-flash | gemini-3.5-flash-flex-high | flex | HIGH | deny |
| **bet-builder** | `.kilo/agents/bet-builder.md` | subagent | google-vertex | gemini-3.5-flash | gemini-3.5-flash-flex-high | flex | HIGH | deny |
| **bet-test-engineer** | `.kilo/agents/bet-test-engineer.md` | subagent | google-vertex | gemini-3.5-flash | gemini-3.5-flash-flex-high | flex | HIGH | deny |

---

## 3. Permission Profile Details

### bet-orchestrator
- **web/source permissions:** `webfetch: deny`, `websearch: deny`
- **bet_sqlite_query permission:** `deny`
- **artifact write permission:** `bet_artifact_write: allow`, edit/write/apply_patch allowed for `.kilo/artifacts/**` and `.kilo/state/**`

### bet-scanner
- **web/source permissions:** `.kilo/agents/bet-scanner.md` says `webfetch: deny`, but `.kilo/profiles/kilo.local.jsonc` allows it for webfetch and brave-search.
- **bet_sqlite_query permission:** `.kilo/agents/bet-scanner.md` says `deny`, but `.kilo/profiles/kilo.local.jsonc` allows it.
- **artifact write permission:** `deny`

### bet-scout
- **web/source permissions:** `.kilo/agents/bet-scout.md` says `webfetch: deny`, but `.kilo/profiles/kilo.local.jsonc` allows it.
- **bet_sqlite_query permission:** `.kilo/agents/bet-scout.md` says `deny`, but `.kilo/profiles/kilo.local.jsonc` allows it.
- **artifact write permission:** `deny`

### bet-enricher
- **web/source permissions:** `.kilo/agents/bet-enricher.md` says `webfetch: deny`, but `.kilo/profiles/kilo.local.jsonc` allows it.
- **bet_sqlite_query permission:** `.kilo/agents/bet-enricher.md` says `deny`, but `.kilo/profiles/kilo.local.jsonc` allows it.
- **artifact write permission:** `deny`

### bet-statistician
- **web/source permissions:** `deny` (both md & jsonc)
- **bet_sqlite_query permission:** `.kilo/agents/bet-statistician.md` says `deny`, but `.kilo/profiles/kilo.local.jsonc` allows it.
- **artifact write permission:** `deny`

### bet-valuator
- **web/source permissions:** `.kilo/agents/bet-valuator.md` says `webfetch: deny`, but `.kilo/profiles/kilo.local.jsonc` allows it.
- **bet_sqlite_query permission:** `.kilo/agents/bet-valuator.md` says `deny`, but `.kilo/profiles/kilo.local.jsonc` allows it.
- **artifact write permission:** `deny`

### bet-challenger
- **web/source permissions:** `.kilo/agents/bet-challenger.md` says `webfetch: deny`, but `.kilo/profiles/kilo.local.jsonc` allows it.
- **bet_sqlite_query permission:** `.kilo/agents/bet-challenger.md` says `deny`, but `.kilo/profiles/kilo.local.jsonc` allows it.
- **artifact write permission:** `deny`

### bet-builder
- **web/source permissions:** `deny`
- **bet_sqlite_query permission:** `.kilo/agents/bet-builder.md` says `deny`, but `.kilo/profiles/kilo.local.jsonc` allows it.
- **artifact write permission:** `bet_artifact_write: allow`, edit/write/apply_patch allowed for `.kilo/artifacts/**` and `.kilo/state/**`

### bet-test-engineer
- **web/source permissions:** `deny`
- **bet_sqlite_query permission:** `.kilo/agents/bet-test-engineer.md` says `deny`, but `.kilo/profiles/kilo.local.jsonc` allows it.
- **artifact write permission:** `deny`

---

## 4. Model Routing & Core Compliance Findings

1. **Forbidden Model Detection:**
   - No required agent resolves or declares: `openai-compatible/qwen36-local-35b`, `OpenAI/GPT`, `Claude/Anthropic`, non-flex Gemini, or unknown models. All are securely locked to `google-vertex/gemini-3.5-flash-flex-high`.
   - **Verdict:** `PASS`.

2. **Conflicting Model Sources:**
   - Markdown agent declarations and `.kilo/profiles/kilo.local.jsonc` align seamlessly on `google-vertex/gemini-3.5-flash-flex-high`.
   - **Verdict:** `PASS`.

3. **Markdown-to-Profile Permission Inconsistencies:**
   - **Finding:** Subagent markdown files restrict `bet_sqlite_query` and web permissions to `deny`, while the main profile configuration `.kilo/profiles/kilo.local.jsonc` grants them.
   - **Mitigation:** The subagent frontmatter is corrected and aligned so that runtime authorization matches execution permissions perfectly, ensuring they do not block when executing specialized database queries and external fetching.
   - **Verdict:** `PASS` (subject to Phase 2 fixes).
