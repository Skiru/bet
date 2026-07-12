# Pipeline Contracts

`config/pipeline_manifest.json` is the machine-readable source of truth. `bet-executor` runs every script-mode step; domain ownership never grants shell access.

| Steps | Domain owner | Required result |
|---|---|---|
| S0, S10 | `bet-settler-postevent` | Settlement and post-event learning |
| S1-S2.9 | `bet-researcher` | Complete event coverage, enrichment, tipster labels, and factual reconciliation |
| S3-S4 | `bet-modeler` | Probabilities, fair prices, minimum acceptable quote, and quote-dependent EV |
| S5-S7 | `bet-risk-gatekeeper` | Context, portfolio risk, and hard gate verdicts |
| S7b | `bet-auditor` | Read-only Superbet market-name/line mapping verification |
| S8 | `bet-builder` | Manual quote packs and Bet Builder idea groups |
| S9 | Human operator | Real manual Superbet quote and placement decision |

Missing odds and tipsters do not block core analytical coverage. They must be labeled, every discovered event must receive a terminal status or reason, and missing real operator odds block EV, stakes, bettable status, and an executable coupon. Synthetic S9 approval is invalid. Zero approvals is valid `NO_ACTION_TERMINAL`.

Keep one worktree and `RUN_ID` through bounded continuation. A safe checkpoint precedes an unavoidable UI/context limit and never claims PASS.
