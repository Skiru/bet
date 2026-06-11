# Tool Registry — Names, Permissions & Output Protocol

> CRITICAL: Use ONLY these exact tool names. Do NOT invent tool names.
> EVERY invalid tool call = wasted turn = pipeline stall.

## Tool Registry

| Tool Name | Category | Purpose | Permission Level | Who Can Call | Wrong Names |
|-----------|----------|---------|-----------------|--------------|-------------|
| `sequentialthinking_sequentialthinking` | REASONING | Multi-step deduction, self-validation, hypothesis generation | READONLY (no side effects) | ALL agents | ~~sequentialthinking~~, ~~sequential_thinking~~ |
| `sqlite_read_query` | DATA_READ | SELECT queries against betting DB | READONLY (no mutations) | ALL agents | ~~sqlite_read~~, ~~read_query~~, ~~query~~ |
| `sqlite_write_query` | DATA_WRITE | INSERT/UPDATE/DELETE on betting DB | WRITE (data mutation) | bet-engineer only (script fixes) | ~~sqlite_write~~ |
| `sqlite_create_table` | DATA_WRITE | CREATE TABLE on betting DB | WRITE | bet-db-analyst only | |
| `sqlite_describe_table` | DATA_READ | Get table schema | READONLY | ALL agents | ~~describe_table~~ |
| `sqlite_list_tables` | DATA_READ | List all tables in DB | READONLY | ALL agents | ~~list_tables~~ |
| `sqlite_append_insight` | DATA_WRITE | Write business insight to memo | WRITE | ALL agents (append-only) | |
| `brave-search_brave_web_search` | WEB_READ | General web search for context | READONLY (external API) | ALL agents with brave need | ~~websearch~~, ~~brave_web_search~~ |
| `brave-search_brave_news_search` | WEB_READ | News search for recent events | READONLY (external API) | bet-challenger, bet-valuator, bet-statistician | ~~brave_news_search~~, ~~news_search~~ |
| `brave-search_brave_image_search` | WEB_READ | Image search | READONLY | Not used by pipeline agents | |
| `brave-search_brave_video_search` | WEB_READ | Video search | READONLY | Not used by pipeline agents | |
| `brave-search_brave_local_search` | WEB_READ | Local business search | READONLY | Not used by pipeline agents | |
| `webfetch` | WEB_READ | Fetch full web page content (rendered) | READONLY (external API) | bet-scout, bet-scanner (as fallback) | ~~fetch_webpage~~, ~~fetch_url~~ |
| `read` | FILE_READ | Read file contents from disk | READONLY (local filesystem) | ALL agents | ~~read_file~~, ~~open_file~~, ~~cat~~ |
| `write` | FILE_WRITE | Create/overwrite files | WRITE (filesystem mutation) | bet-builder (coupons), bet-engineer (fixes) | ~~write_file~~, ~~create_file~~, ~~save_file~~ |
| `edit` | FILE_WRITE | Edit existing files (patch) | WRITE (filesystem mutation) | bet-engineer, bet-orchestrator | ~~edit_file~~, ~~replace_in_file~~, ~~modify~~ |
| `bash` | EXECUTE | Run terminal commands | EXECUTE (full shell access) | ALL agents (pipeline scripts only) | ~~run_in_terminal~~, ~~execute~~, ~~shell~~ |
| `glob` | FILE_READ | Pattern-based file search | READONLY (local filesystem) | ALL agents | ~~file_search~~, ~~list_files~~, ~~find_files~~ |
| `grep` | FILE_READ | Content-based file search | READONLY (local filesystem) | ALL agents | ~~grep_search~~, ~~search~~ |
| `task` | ORCHESTRATION | Delegate work to subagent | ORCHESTRATION | bet-orchestrator only | ~~runSubagent~~, ~~delegate~~ |
| `todowrite` | INTERNAL | Manage task todo list | INTERNAL | ALL agents | ~~manage_todo~~, ~~todo~~ |
| `kilo_local_recall` | MEMORY | Recall past conversations | READONLY (memory) | ALL agents (rare) | |

## Permission Level Definitions

| Level | Meaning | Examples |
|-------|---------|---------|
| READONLY | No side effects. Safe to call any time. | `sqlite_read_query`, `read`, `brave-search_brave_web_search` |
| WRITE | Mutates state. Call only when explicitly authorized. | `sqlite_write_query`, `edit`, `write` |
| EXECUTE | Runs arbitrary code/shell. High risk. | `bash` |
| ORCHESTRATION | Delegates work to another agent. Orchestrator only. | `task` |
| INTERNAL | Session management, no external effect. | `todowrite` |

## Tool Output Protocol (ALL agents — MANDATORY)

Every tool call returns output. You MUST process it as follows:

1. **IF tool succeeds (data returned)**:
   - Extract specific numbers/strings relevant to your hypothesis
   - Store in working memory: `[TOOL: tool_name] result = value`
   - If data is empty (0 rows, empty string) → treat as ZERO, not ERROR
   - CITE the output in your verdict: `[source: tool_name, query: ...]`

2. **IF tool fails (timeout/error)**:
   - Note the failure in your verdict: `[FAILED: tool_name, reason]`
   - Try EXACTLY ONE alternative: different query (sqlite) or different search (brave)
   - If alternative also fails → mark as UNVERIFIED, continue
   - NEVER fabricate data to replace a failed query

3. **IF tool returns unexpected format**:
   - Parse what you can, flag the rest as PARTIAL
   - Never hallucinate schema or structure

4. **IF tool confirms your hypothesis**:
   - Strengthen confidence. Document: `[CONFIRMED: tool_name]`

5. **IF tool contradicts your hypothesis**:
   - Downgrade confidence. Document: `[CONTRADICTED: tool_name, delta: X→Y]`
   - Revise the hypothesis, do NOT double-down

## MCP Server Recovery Protocol

If an MCP tool call fails with timeout or server error:
1. **First failure**: Wait 3 seconds, retry the exact same call ONCE.
2. **Second failure**: Switch to fallback:
   - `sqlite` down → mark DB-dependent verdicts as UNAVAILABLE, proceed with web-only analysis
   - `brave-search` down → mark web-dependent verdicts as UNVERIFIED, proceed with DB-only analysis
   - `sequentialthinking` down → skip validate phase, cap confidence to LOW, note in verdict
3. **Never halt the pipeline for an MCP outage** — mark affected data as UNAVAILABLE/UNVERIFIED and continue.
