# Agent Prompt Instruction Audit

Run ID: `AGENT_SYSTEM_BATTLE_TESTED_PRODUCTION_AUDIT_E_20260701_140823`

## Pre-Repair Findings

- `bet-orchestrator-v2.md` contains runtime inheritance language, but the prompt is too short for full production gating.
- Most required betting prompts are one-line instructions and do not yet contain the mandated sections:
  role mission, exact inputs, exact outputs/artifacts, forbidden behavior, allowed tools, role boundary, hard stops, retry limit, anti-loop rule, no hidden reasoning rule, evidence rules, no fake facts, no silent omissions, continuation behavior, phase-bounded scope, escalation path, and exact final response schema.
- Builder prompt does not yet explicitly forbid final coupon output without a human Superbet quote.
- Valuator prompt does not yet explicitly forbid EV without both odds and model probability in contract language.

## Required Repairs

- Expand every required betting prompt into a schema-bound production contract.
- Add explicit no-silent-omission and continuation/checkpoint requirements.
- Add anti-loop, retry, and escalation rules.
- Update operator-flow wording to manual Superbet quote where relevant.

This report was intentionally written before repair edits.

## Post-Repair Status

- All required betting prompts now include role mission, exact inputs, exact outputs/artifacts, allowed tools, forbidden behavior, retry/continuation rules, and exact final response schemas.
- Builder now blocks final operator-facing output without a manual human Superbet quote.
- Valuator now explicitly blocks EV without both valid odds and model probability.
- No-silent-omission and checkpoint behavior are now explicit.
