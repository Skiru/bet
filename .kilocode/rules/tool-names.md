# Kilo Code — Correct Tool Names

> CRITICAL: Use ONLY these exact tool names. Do NOT invent tool names.

## Available Tools

| Purpose | Correct Tool Name | WRONG (do NOT use) |
|---------|------------------|--------------------|
| Web search | `websearch` | ~~brave_search_brave_web_search~~, ~~brave_web_search~~ |
| Sequential thinking | `sequentialthinking_sequentialthinking` | ~~sequentialthinking~~ |
| SQLite read | `sqlite_read_query` | ~~sqlite_read~~, ~~read_query~~ |
| SQLite write | `sqlite_write_query` | ~~sqlite_write~~ |
| SQLite list tables | `sqlite_list_tables` | ~~list_tables~~ |
| SQLite describe | `sqlite_describe_table` | ~~describe_table~~ |
| SQLite create table | `sqlite_create_table` | |
| SQLite append insight | `sqlite_append_insight` | |
| Read file | `read` | ~~read_file~~ |
| Write file | `write` | ~~write_file~~, ~~create_file~~ |
| Edit file | `edit` | ~~edit_file~~, ~~replace_in_file~~ |
| Run terminal | `bash` | ~~run_in_terminal~~, ~~execute~~ |
| Search files | `glob` | ~~file_search~~ |
| Text search | `grep` | ~~grep_search~~ |
| Fetch URL | `webfetch` | ~~fetch_webpage~~ |
| Delegate to agent | `task` | ~~runSubagent~~ |
| Write todo | `todowrite` | ~~manage_todo~~ |
| Recall memory | `kilo_local_recall` | |

## Rules

1. When prompts say "use brave-search MCP" → use `websearch`
2. When prompts say "use sequentialthinking" → use `sequentialthinking_sequentialthinking`
3. When prompts say "query sqlite MCP" → use `sqlite_read_query`
4. NEVER prefix tool names with `mcp_` or `brave_search_`
5. If unsure about a tool name → use `websearch` for web, `sqlite_read_query` for DB
