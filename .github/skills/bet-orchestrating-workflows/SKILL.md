---
name: bet-orchestrating-workflows
description: Reusable workflow mechanics for bet customizations — delegation flow, routing rules, resume/stop gates, and shared handoff contracts.
user-invocable: false
---

# Bet Orchestrating Workflows

This skill provides reusable workflow mechanics that are shared across bet prompts and agents. It is an on-demand HOW layer, not a constitution or always-on ruleset.

Load this skill when an entry point needs shared execution mechanics that recur across more than one artifact. Keep the prompt or agent body thin and let the resources below carry the reusable coordination detail.

## Use When

- You need a shared orchestration spine for a bet workflow entry point.
- You need routing rules for deciding which specialist agent should handle a task.
- You need resume, stop, or handoff semantics that appear in more than one prompt.
- You need a common validation flow that coordinates several steps without restating domain rules.

## What This Skill Owns

- execution spines for multi-step bet workflows
- delegation matrices for routing work to specialist agents
- resume and stop gates for long-running workflows
- shared handoff contracts between prompts and agents
- thin framing for autonomous workflow prompts that need reusable orchestration mechanics

## What This Skill Does Not Own

- repo-wide constitution rules
- always-on execution law from the agent execution protocol
- betting methodology or sport-specific analysis rules
- artifact formatting schema tables
- domain memory or permanent rulebooks

## Resource Map

- [execution-spine.md](resources/execution-spine.md) — the reusable multi-step loop for coordinated workflow entry points.
- [routing-matrix.md](resources/routing-matrix.md) — intent-to-agent routing and the canonical delegation targets.
- [resume-stop-gates.md](resources/resume-stop-gates.md) — pause, continue, and stop conditions for long workflows.
- [handoff-contracts.md](resources/handoff-contracts.md) — the standard payload shape for subagent delegation.
- [async-wait-overlap.md](resources/async-wait-overlap.md) — an opt-in add-on for orchestrator entry points that want bounded read-only overlap during qualifying async waits.

## Companion Loads

- For analysis doctrine, load [analysis-methodology.instructions.md](../../instructions/analysis-methodology.instructions.md).
- For sport-specific rules, load [sport-analysis-protocols.instructions.md](../../instructions/sport-analysis-protocols.instructions.md).
- For artifact formatting, load [betting-artifacts.instructions.md](../../instructions/betting-artifacts.instructions.md).
- For execution law, load [agent-execution-protocol.instructions.md](../../instructions/agent-execution-protocol.instructions.md).

## Operating Rule

If a detail is shared across two or more prompts or agents and is not a permanent rule, place it in the matching resource here instead of duplicating it in each artifact.

If an orchestrator entry point wants proactive wait-window overlap, load [async-wait-overlap.md](resources/async-wait-overlap.md). That resource owns the wait-policy details; [execution-spine.md](resources/execution-spine.md), [resume-stop-gates.md](resources/resume-stop-gates.md), and [handoff-contracts.md](resources/handoff-contracts.md) remain generic baselines rather than secondary policy owners.

## Progressive Disclosure

Keep this skill concise. If a workflow entry point needs a larger step list, split that detail into a referenced resource file under this package rather than expanding the activation body.
