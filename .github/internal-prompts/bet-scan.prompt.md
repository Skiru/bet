---
agent: "bet-scanner"
description: "S1 handoff frame for discovery coverage and fixture quality analysis."
---

# S1 — Scan Handoff

Use the canonical execution protocol, source-navigation skill, and workflow handoff contract. This prompt owns only the handoff framing for the scanner specialist.

## Orchestrator Must Provide
- finished output from `discover_events.py`
- key metrics or `AGENT_SUMMARY`
- any obvious source failures, phantom fixtures, or date mismatches
- relevant DB or JSON artifacts if deeper verification is needed

## Specialist Focus
- coverage by sport, league, and tournament
- fixture validity and source reliability
- missing sports or protected competitions that should have appeared
- readiness to continue to ingestion or shortlist work

## Output Contract
Return the structured verdict required by `agent-execution-protocol.instructions.md` plus:
- scan coverage highlights
- anomalies that need operator attention
- next-step readiness for S1-ingest or shortlist work

## Guardrails
- analysis-only; do not run pipeline scripts
- flag gaps instead of inventing missing coverage

<!-- BET:internal-prompt:bet-scan:v2 -->
