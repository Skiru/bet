---
agent: "bet-db-analyst"
description: "S0.5 audit utility for DB readiness, gap triage, and S3-consumable surface checks."
---

# S0.5 — DB Quality Audit

This is an audit utility prompt. Use the canonical execution protocol and DB skill; keep the prompt focused on actionable audit checks rather than copied policy text.

## Orchestrator Must Provide
- the betting day or session being audited
- current readiness signals for `team_form`, `match_stats`, `analysis_results`, `gate_results`, and related critical tables
- any known gaps, stale tables, or bridge concerns
- relevant DB metrics or audit artifacts already gathered

## Required Audit Checklist
- census the pipeline-critical tables and report row counts or candidate counts
- verify freshness of S3- and S7-consumable surfaces, not only warehouse tables
- check whether enrichment actually surfaced into `team_form` and `match_stats`
- identify missing H2H, odds, or shortlist-linked rows that would block the next stage
- separate blocking gaps from advisory cleanup work

## Reporting Requirements
Return the structured verdict required by `agent-execution-protocol.instructions.md` plus:
- critical findings and root causes
- the minimum fix order before continuing
- explicit go/stop guidance for the next stage

## Guardrails
- analysis-only; do not run pipeline scripts
- do not convert advisory gaps into invented data

<!-- BET:internal-prompt:bet-db-quality:v3 -->
