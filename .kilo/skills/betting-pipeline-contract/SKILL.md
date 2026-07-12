---
name: betting-pipeline-contract
description: Canonical S0-S10 ownership, execution, verification, continuation, and human-gate contract for the seven betting power agents.
---

# Betting Pipeline Contract

## Ownership

| Steps | Domain owner | Contract |
|---|---|---|
| S0, S10 | `bet-settler-postevent` | Settlement, accounting, and post-event learning only |
| S1, S1e, S2, S2.3, S2.5, S2.7, S2.9 | `bet-researcher` | Event identity, tipsters, enrichment, and factual reconciliation |
| S3, S4 | `bet-modeler` | Probabilities, fair price, minimum acceptable quote, and EV only with real odds |
| S5, S6, S7 | `bet-risk-gatekeeper` | Current context, portfolio risk, and hard approval gates |
| S7b | `bet-auditor` | Independent market-mapping and artifact verification |
| S8 | `bet-builder` | Manual quote cards and Bet Builder idea groups |
| S9 | Human operator | Manual Superbet quote and placement decision; no agent substitute |

`bet-executor` is the canonical script executor for all script-mode steps. Domain ownership never grants shell access. `bet-auditor` independently verifies and never repairs. Code/General in a fresh worktree is the engineering repair path and emergency fallback, not the normal betting orchestrator.

## Gates

- Missing odds do not block analytical coverage, but they block EV, bettable status, stakes, and an executable final coupon.
- Tipster absence must be explicitly labeled and cannot silently drop an event or block core analysis.
- Every discovered event must receive an explicit terminal status or reason.
- Zero S7 approvals is valid `NO_ACTION_TERMINAL`.
- S9 requires a real human-entered Superbet quote. Synthetic or generated S9 evidence is invalid.
- Missing or partial evidence cannot produce PASS.

## Continuation

Use the same worktree and `RUN_ID` across bounded phases. Continue in the same session while context is safe. If the UI/context limit approaches, finish the current atomic operation, persist a safe checkpoint, and continue in a fresh session in the same worktree without repeating completed phases. Use a new worktree only for engineering repair.
