---
agent: "bet-enricher"
description: "S2.3/S2.5 handoff frame for enrichment coverage, bridge visibility, and gap triage."
---

# S2.3 / S2.5 — Enrichment Handoff

Use the canonical execution protocol, source-navigation skill, and enrichment agent role. This prompt owns only the handoff framing for finished enrichment output.

## Orchestrator Must Provide
- finished output from `run_scrapers.py`, `data_enrichment_agent.py`, or sport-specific enrichment steps
- the pre-handoff stage context pack for this stage when required by `stage-context-packs.md`
- yield metrics, source-health metrics, and gap counts
- affected sports, competitions, or candidate sets
- any known stale or blocked sources

## Specialist Focus
- S3 readiness of `team_form`, `match_stats`, and critical caches
- per-sport yield, freshness, and bridge visibility
- recoverable versus non-recoverable gaps
- whether the pipeline should continue, pause, or re-run a narrower enrichment slice

## Output Contract
Return the structured verdict required by `agent-execution-protocol.instructions.md` plus:
- readiness summary by sport
- unresolved data gaps or source-health alarms
- next-step readiness for S3

## Guardrails
- analysis-only; do not run pipeline scripts
- write only short source-health observations to `/memories/session/` when they are new and reusable

<!-- BET:internal-prompt:bet-enrich:v2 -->
