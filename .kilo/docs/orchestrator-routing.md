# Power-Agent Routing

`bet-executor` is the canonical full-day betting primary. It delegates only to the six partner agents in its YAML task allowlist.

| Scope | Partner |
|---|---|
| S0/S10 settlement | `bet-settler-postevent` |
| S1-S2.9 research and factual conflicts | `bet-researcher` |
| S3/S4 probability and pricing | `bet-modeler` |
| S5-S7 context, risk, and approval | `bet-risk-gatekeeper` |
| S7b and final verification | `bet-auditor` |
| S8 quote-pack packaging | `bet-builder` |
| S9 quote and placement decision | Human only; never delegated |

Code/General in a fresh worktree handles engineering repairs and is only an emergency execution fallback. Business agents do not run shell or repair code.
