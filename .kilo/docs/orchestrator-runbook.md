# Full-Day Betting Runbook

1. Select `bet-executor`; stop with `WRONG_KILO_AGENT_MODE_NO_BASH` if Bash is unavailable.
2. Create one `RUN_ID`, verify the source tree, and execute canonical wrappers from `config/pipeline_manifest.json`.
3. Delegate domain interpretation only to the manifest owner. Capture Fish `$pipestatus` for piped commands.
4. Preserve all discovered events through S1-S7 with an explicit terminal status or reason. Label absent tipster evidence without dropping the event.
5. Permit analysis without odds, but do not calculate EV, Kelly/stakes, bettable status, or an executable coupon until a real human-entered Superbet quote exists.
6. Require `bet-auditor` to verify S7b and final artifacts from complete evidence. Missing quote means `MANUAL_QUOTE_REQUIRED`, not operator availability.
7. Let `bet-builder` produce quote cards and idea groups only. S9 is a human-only quote and placement decision; generated approval is invalid.
8. Accept zero approved candidates as `NO_ACTION_TERMINAL`.

Continue bounded phases in the same session, worktree, and `RUN_ID` while context is safe. Before an unavoidable UI/context limit, finish the atomic operation and persist a safe checkpoint with completed phases, branch, HEAD, changed files, passed/pending tests, risks, handoff path, and exact continuation prompt. Resume without repeating completed phases. Use a new worktree only for Code/General engineering repair.
