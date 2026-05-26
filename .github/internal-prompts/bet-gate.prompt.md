---
agent: "bet-challenger"
description: "S7 handoff frame for final gate reasoning, bear cases, and advisory tiers."
---

# S7 — Gate Handoff

This is a thin handoff prompt. The execution protocol, sport rules, and analytical methodology stay in the canonical instructions and skills.

## Orchestrator Must Provide
- finished output from `gate_checker.py`
- `AGENT_SUMMARY` or tier metrics, warnings, and any repeat-loss findings
- upstream S3-S6 artifacts needed to verify the final thesis
- the candidate set or the subset that needs the final judgment

## Specialist Focus
- build a specific mechanism, bull case, and bear case for the important picks
- keep every candidate in the matrix while assigning advisory strength
- flag any missing evidence or upstream defect that should stop S8
- decide which picks stay core, move to extended pool, or need escalation

## Output Contract
Return the structured verdict required by `agent-execution-protocol.instructions.md` plus:
- decisive advisory tier and mechanism for the key picks
- bear-case summary for anything borderline
- next-step readiness for coupon building

## Guardrails
- analysis-only; do not run pipeline scripts
- write only short new risk patterns to `/memories/session/` when they are reusable

<!-- BET:internal-prompt:bet-gate:v2 -->
