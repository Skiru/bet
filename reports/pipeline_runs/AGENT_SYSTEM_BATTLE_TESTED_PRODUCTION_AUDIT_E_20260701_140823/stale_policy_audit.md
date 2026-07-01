# Stale Policy Audit

Run ID: `AGENT_SYSTEM_BATTLE_TESTED_PRODUCTION_AUDIT_E_20260701_140823`

## Pre-Repair Findings

- `AGENTS.md` still says picks remain conditional until the user verifies the exact market and odds in Betclic. This conflicts with the current manual Superbet quote boundary.
- `.kilo/agents/bet-reconciler.md` contains stale Gemini-only routing text.
- `.kilo/agents/bet-db-analyst.md` contains stale Gemini-only routing text.
- `.kilo/agents/bet-settler.md` contains stale Gemini-only routing text.
- Required betting prompts are materially under-specified and do not yet encode anti-loop, continuation, no-silent-omission, hard-stop, or exact schema contracts in a production-grade way.
- Existing continuation audit is narrow and tied to one repair-run naming pattern rather than a generalized continuation/resume gate.
- No dedicated anti-loop and step-budget contract document exists yet.
- No single master production audit script exists yet.

## Required Repairs

- Remove or rewrite stale Gemini-only and provider-exclusive role text.
- Replace stale Betclic operator-flow language with manual human Superbet quote language where flow/operator policy is described.
- Add explicit no-silent-omission, continuation/resume, anti-loop, retry-limit, and false-PASS guards across prompts and audits.
- Add a master system audit covering roles, tools, model inheritance, and output schemas.

This report was intentionally written before repair edits.

## Post-Repair Status

- Stale Gemini-only role text was removed from required betting agent files.
- Stale Betclic operator-flow language was replaced with manual human Superbet quote language.
- Mandatory Qwen-only and Gemini-only runtime requirements are not present in the repaired active contract files.
- Anti-loop, continuation, no-silent-omission, and false-PASS gates are now codified in prompts, docs, and the new master production audit.
