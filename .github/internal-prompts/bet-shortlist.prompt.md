---
agent: "bet-scanner"
description: "S1e handoff frame for shortlist quality and stats-first candidate review."
---

# S1e — Shortlist Handoff

Use the canonical execution protocol and scanner/domain skills. This prompt is the thin frame for analyzing finished shortlist output.

## Orchestrator Must Provide
- finished output from `build_shortlist.py`
- shortlist artifacts and summary metrics
- any flagged phantom fixtures, missing sports, or source anomalies
- current date and session context

## Specialist Focus
- shortlist size and sport distribution
- stats-first market quality and candidate shape
- missing major leagues, tournaments, or protected contexts
- issues that should block enrichment or downstream analysis

## Output Contract
Return the structured verdict required by `agent-execution-protocol.instructions.md` plus:
- shortlist strengths and weaknesses
- candidates or sports requiring follow-up
- next-step readiness for S2 and enrichment

## Guardrails
- analysis-only; do not run pipeline scripts
- write only short ranking insights to `/memories/session/` when something is new and reusable

<!-- BET:internal-prompt:bet-shortlist:v2 -->
