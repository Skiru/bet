---
agent: "bet-builder"
description: "S8 handoff frame for coupon, portfolio, and extended-pool construction."
---

# S8 — Portfolio Handoff

Use the canonical execution protocol, coupon-building skill, and formatting instruction. This prompt owns only the handoff framing for finished build output.

## Orchestrator Must Provide
- finished output from `coupon_builder.py` and any validation summaries
- approved, extended, and flagged candidate groups
- bankroll or staking context when relevant
- any placement constraints or duplicate-event concerns

## Specialist Focus
- core portfolio quality, event uniqueness, and portfolio balance
- extended-pool separation versus core coupon eligibility
- correlation, duplicate-event, or formatting issues that block delivery
- whether the current build is ready for user presentation

## Output Contract
Return the structured verdict required by `agent-execution-protocol.instructions.md` plus:
- core versus extended-pool summary
- issues that require rebuild or placement caution
- next-step readiness for final validation or presentation

## Guardrails
- analysis-only; do not run pipeline scripts
- write only short portfolio observations to `/memories/session/` when they are reusable

<!-- BET:internal-prompt:bet-portfolio:v2 -->
