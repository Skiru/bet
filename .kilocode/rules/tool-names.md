# Kilo Code — Correct Tool Names

> CRITICAL: Use ONLY these exact tool names. Do NOT invent tool names.
> EVERY invalid tool call = wasted turn = pipeline stall. You have been CAUGHT using wrong names before.

## Available Tools

| Purpose | Correct Tool Name | WRONG (do NOT use) |
|---------|------------------|--------------------|
| Web search | `brave-search_brave_web_search` | ~~websearch~~, ~~brave_web_search~~, ~~web_search~~ |
| News search | `brave-search_brave_news_search` | ~~brave_news_search~~, ~~news_search~~ |
| Sequential thinking | `sequentialthinking_sequentialthinking` | ~~sequentialthinking~~, ~~sequential_thinking~~ |
| SQLite read | `sqlite_read_query` | ~~sqlite_read~~, ~~read_query~~, ~~query~~ |
| SQLite write | `sqlite_write_query` | ~~sqlite_write~~ |
| SQLite list tables | `sqlite_list_tables` | ~~list_tables~~ |
| SQLite describe | `sqlite_describe_table` | ~~describe_table~~ |
| SQLite create table | `sqlite_create_table` | |
| SQLite append insight | `sqlite_append_insight` | |
| Read file | `read` | ~~read_file~~, ~~open_file~~, ~~cat~~ |
| Write file | `write` | ~~write_file~~, ~~create_file~~, ~~save_file~~ |
| Edit file | `edit` | ~~edit_file~~, ~~replace_in_file~~, ~~modify~~ |
| Run terminal | `bash` | ~~run_in_terminal~~, ~~execute~~, ~~shell~~ |
| Search files | `glob` | ~~file_search~~, ~~list_files~~, ~~find_files~~ |
| Text search | `grep` | ~~grep_search~~, ~~search~~ |
| Fetch URL | `webfetch` | ~~fetch_webpage~~, ~~fetch_url~~ |
| Delegate to agent | `task` | ~~runSubagent~~, ~~delegate~~ |
| Write todo | `todowrite` | ~~manage_todo~~, ~~todo~~ |
| Recall memory | `kilo_local_recall` | |

## Rules

1. When prompts say "use brave-search MCP" → use `brave-search_brave_web_search`
2. When prompts say "use sequentialthinking" → use `sequentialthinking_sequentialthinking`
3. When prompts say "query sqlite MCP" → use `sqlite_read_query`
4. NEVER prefix tool names with `mcp_` (that's Copilot syntax, not Kilo)
5. If unsure about a tool name → use `brave-search_brave_web_search` for web, `sqlite_read_query` for DB
