# Power-Agent Execution Core

## Control Flow

1. Read the manifest step, prerequisite artifacts, and current checkpoint.
2. `bet-executor` runs the canonical wrapper and captures Fish `$pipestatus`.
3. Delegate only the step's domain interpretation to its power-agent owner.
4. Persist source-bound evidence and explicit UNKNOWN values.
5. `bet-auditor` verifies complete artifacts and returns PASS only from complete evidence.
6. Record every discovered event's terminal status or reason and advance the same `RUN_ID`.

## Boundaries

- Business agents deny shell and repository mutation.
- Factual conflicts route to `bet-researcher`; risk conflicts route to `bet-risk-gatekeeper`.
- Real operator odds are mandatory before EV, stakes, bettable status, or executable coupons.
- S9 is a manual human Superbet gate. No agent substitutes for the quote or placement decision.
- Code/General in a fresh worktree is the repair path after bounded failures.

## Continuation

Chat is a control plane, not a data store. Persist verbose evidence. Before an unavoidable UI/context limit, finish the atomic operation and write a safe checkpoint with branch, HEAD, changed files, completed phases, tests passed/pending, risks, handoff path, `RUN_ID`, and exact continuation prompt. A checkpoint never claims PASS.
