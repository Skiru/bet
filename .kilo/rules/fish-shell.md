# Fish Shell Only

This project uses Fish shell only.
- Use `set -x VAR value`, never `export VAR=value`.
- Use `(cmd)` command substitution, never `$(cmd)`.
- Do not use bash heredocs.
- All long command output must be redirected to `/tmp/*.txt` and summarized with `tail -20`.
