# Agent Frontmatter Audit

Run ID: `AGENT_SYSTEM_BATTLE_TESTED_PRODUCTION_AUDIT_E_20260701_140823`

## Pre-Repair Findings

- Required betting agent files exist.
- Required betting agent frontmatter currently has no explicit `model:` pin in the sampled required files, which is good.
- Role text is inconsistent across files and some bodies contain stale provider-specific runtime instructions.
- Frontmatter permissions do not consistently reflect the target production boundaries for scanner, scout, enricher, statistician, valuator, challenger, builder, test-engineer, engineer, reconciler, db-analyst, and settler.
- Orchestrator boundary is mostly aligned in frontmatter, but the profile-layer permissions still require hardening to prevent repo mutation at runtime.

## Required Repairs

- Normalize role boundaries and hard-stop sections across all required agent files.
- Remove stale provider-specific runtime text from `bet-reconciler`, `bet-db-analyst`, and `bet-settler`.
- Ensure no required betting agent keeps a default model pin.
- Align production permissions with the orchestrator/specialist/engineer split.

This report was intentionally written before repair edits.

## Post-Repair Status

- Required betting agents remain free of default frontmatter model pins.
- Engineering-only mutation is enabled for `bet-engineer`.
- Orchestration and specialist role boundaries were normalized.
- DB-read and artifact-write permissions were aligned with read-only specialist roles where needed.
