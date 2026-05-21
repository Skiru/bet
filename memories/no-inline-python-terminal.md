# PERMANENT RULE: No Inline Python in Terminal — ABSOLUTE BAN

## Established 2026-05-11 — Terminal garbles AND HANGS with multiline Python
## Updated 2026-05-11 — User FURIOUS after 3rd violation in same session
## Updated 2026-05-20 — Compound fish commands can kill the terminal session

- ⛔ NEVER run `python3 -c "..."` with multiline Python code in the terminal
- ⛔ NEVER let subagents run multiline Python in terminal either
- ⛔ NEVER run ANY command that has `\n` or literal newlines in the command string
- ⛔ NEVER chain multi-purpose fish commands with separators/pipes just to inspect state (for example `git ... && echo ... && pytest ... | tail -5`)
- Fish shell + terminal output capture GARBLES AND HANGS multiline commands
- Compound commands with `&&`, `echo` separators, and `tail`/redirection can also kill the terminal session or leave it unusable
- The output becomes unreadable — mixed command echo with actual output
- Commands with JOINs or complex SQL queries on large tables HANG (>60s timeout)

## What to do INSTEAD
- **For DB queries / data inspection:** Create a temporary script file (e.g., `scripts/_diag_*.py`), run it with `python3 scripts/_diag_foo.py`, then delete it after
- **For simple one-liners:** Single-line `python3 -c "print('hello')"` is OK (no newlines)
- **For terminal checks:** Run one simple command at a time; no combined status/test/output pipelines
- **For counting/searching:** Use `grep_search`, `file_search`, `read_file` tools — they're instant and never garble
- **For DB schema checks:** Write a small script, don't try to inline SQL queries in python -c
- **For subagents:** Include this rule in subagent prompts — they must also use script files

## Why this happens
- Fish shell processes quotes differently than bash
- Terminal output capture truncates/mangles long multiline commands
- The echo of the command itself mixes with stdout making output unreadable
- Large DB queries (JOINs on 12K+ rows) timeout and leave terminal hung
