# Agent System File Inventory

Run ID: `AGENT_SYSTEM_BATTLE_TESTED_PRODUCTION_AUDIT_E_20260701_140823`

## Pre-Repair Snapshot

- `AGENTS.md`: present
- `.kilo/agents/`: present with required betting agents plus `code-simplifier.md`
- `.kilo/prompts/`: present with required betting prompts plus local utility prompts
- `.kilo/skills/`: present
- `.kilo/profiles/`: present with `kilo.local.jsonc`
- `.kilo/rules/`: present
- `.kilo/artifacts/`: present
- `.kilo/state/`: present
- `.kilocode/`: not present
- `docs/pipeline/`: present
- `config/bet-script-operations.json`: present
- `scripts/audit_bet_agent_roster.py`: present
- `scripts/audit_orchestrated_session_continuation.py`: present
- `tests/test_bet_agent_roster_contract.py`: present
- `tests/test_orchestrated_session_continuation_protocol.py`: present
- `tests/test_kilo_agent_model_contract.py`: present
- `~/.config/kilo/kilo.json`: present
- `~/.config/kilo/kilo.jsonc`: present

## Global Config Summary

- `~/.config/kilo/kilo.json`: exists
- `~/.config/kilo/kilo.jsonc`: exists
- Provider names observed: `local`, `google-vertex`
- Model keys observed in sampled sections: local Qwen, Gemini 3.5 Flash variants
- Permission categories observed in sampled sections: read, glob, grep, skill, todowrite, question, edit, write, apply_patch, bash, task, webfetch, websearch, MCP patterns, browser patterns
- `KILO_CONFIG_CONTENT`: not verified in environment at audit write time
- Potential inheritance conflict risk before repair: project profile contains explicit model pins for non-betting utility agents and broad profile-level permissions that required validation against UI-selected runtime inheritance policy

## Required Betting Agent Files

- `bet-orchestrator.md`
- `bet-scanner.md`
- `bet-scout.md`
- `bet-enricher.md`
- `bet-statistician.md`
- `bet-valuator.md`
- `bet-challenger.md`
- `bet-builder.md`
- `bet-test-engineer.md`
- `bet-engineer.md`
- `bet-reconciler.md`
- `bet-db-analyst.md`
- `bet-settler.md`

This inventory was written before repair edits and will be updated with final status after verification.
