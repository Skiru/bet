---
name: betting-pipeline-runtime
description: Runtime and safe-continuation contract for executing and resuming S0-S10 with one RUN_ID and no silent event omission.
---

# Betting Pipeline Runtime

## Runtime ownership

- Use `bet-executor` as the canonical full-day primary and script executor.
- Keep the same worktree and `RUN_ID` across bounded phases.
- Continue in the same session while context is safe. Use a fresh session in the same worktree only after a UI/context limit or explicit checkpoint.
- Use a new worktree only for Code/General engineering repair. Business agents never repair code or run shell.

## Per-phase loop

1. Verify prerequisite artifact paths and DB readiness.
2. Run the next bounded script/action.
3. Validate exit criteria mechanically.
4. Delegate only the analysis required by that phase.
5. Persist full evidence under `betting/` or `.kilo/artifacts/`.
6. Return only a compact decision record.
7. Audit every discovered event for an explicit terminal status or reason.

Tipster absence must be labeled but does not block core event analysis. Missing odds permit analysis but block EV, bettable status, stakes, and executable coupons. S9 is human-only and requires a real Superbet quote.

## Failure handling

- Retry the same operation at most twice.
- After two failures of the same operation, change strategy. If code repair is required, checkpoint and use Code/General in a fresh worktree.
- Never repeat a large web/browser/tool response in chat.
- Never silently omit an event, fabricate an S9 approval, or treat partial evidence as PASS.

## Safe checkpoint

Before an unavoidable UI/context limit, finish the current atomic operation and write compact JSON containing `status=CHECKPOINT`, `decision=SAFE_CONTINUATION_REQUIRED`, completed phases, branch, HEAD, changed files, tests passed, tests pending, risks, `safe_to_continue`, handoff path, `RUN_ID`, and the exact continuation prompt. A checkpoint never claims PASS. Never terminate with generic maximum-step-limit prose. Resume from the checkpoint without repeating completed phases.
