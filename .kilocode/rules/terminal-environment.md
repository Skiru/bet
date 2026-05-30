# Terminal & Python Environment Rules

## Shell
- This machine uses **fish shell**. Do NOT use bash/zsh syntax.
- No `export VAR=value` → use `set -x VAR value`
- No `$()` → use `(command)`
- No heredocs, no `if [ ]; then; fi`

## Python
- All Python scripts MUST use the project virtualenv: `.venv/bin/python3`
- All pip commands MUST use: `.venv/bin/pip`
- NEVER use bare `python3` or `pip` — they won't have project dependencies
- Dependencies are ALREADY INSTALLED in `.venv/`. Do NOT reinstall them.
- Working directory: `/Users/mkoziol/projects/bet`
- Source code path: `src/` (add to sys.path if running standalone scripts)

## Running Pipeline Scripts
```fish
cd /Users/mkoziol/projects/bet
.venv/bin/python3 scripts/<script_name>.py [args]
```

## NEVER DO
- `pip install` anything (deps already in .venv)
- Use `python` or `python3` without `.venv/bin/` prefix
- Use bash syntax (`export`, `$(...)`, heredocs)
- Use zsh syntax
- **Run scripts with `--help`** — the orchestrator prompt has the EXACT commands table. Use it.
- **Run scripts "to see what happens"** — know the expected output BEFORE running
- **Chain multiple scripts** in one command — run them ONE AT A TIME, delegate between each

## When Scripts CRASH — Fix Them (MANDATORY)

You are an engineer. When a Python script throws an error:
1. Read the traceback — find the exact file and line
2. Read the code — understand why it crashed (None value? missing key? type error?)
3. Edit the file — apply a defensive fix (add `or default`, None guard, try/except)
4. Re-run — verify the fix works
5. Continue — proceed with the pipeline

**NEVER report an error and stop. NEVER ask the user to fix it. ALWAYS fix it yourself.**
