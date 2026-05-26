---
description: "Agent-driven question router for ad-hoc betting questions, actions, and status checks — not a full pipeline run."
agent: bet-orchestrator
skills:
  - bet-orchestrating-workflows
argument-hint: "Ask any betting question, e.g. 'what is the current bankroll?' or 'why did the tennis pick fail yesterday?'"
---

# ASK BETTING

## Scope
Use this prompt for ad-hoc questions, actions, and status checks. Do not enter the full S0-S10 pipeline here.

## User Message

{{input}}

## Routing Contract
- Use `sequentialthinking` before deciding whether to answer directly or delegate.
- Use `bet-orchestrating-workflows/resources/routing-matrix.md` for the specialist map.
- Use `bet-orchestrating-workflows/resources/handoff-contracts.md` for the delegation payload.
- Keep multi-domain questions to at most two specialist calls before synthesis.

## Direct Answer Cases
- simple lookups from config, ledgers, reports, or pipeline state
- computations where the orchestrator itself can run the relevant script and synthesize the finished output
- methodology or system questions answered directly from canonical instructions

## Delegation Cases
- specialist analysis, action requests, or judgment calls that need a domain agent
- questions where the answer depends on finished output from a pipeline stage
- multi-domain asks where one agent provides the core answer and another adds supporting context

## Minimum Context
- `/memories/repo/pipeline-knowledge-base.md`
- `/memories/session/`
- `config/betting_config.json`
- `betting/journal/picks-ledger.csv`
- `betting/data/pipeline_state/`

## Response Shape
- direct answer: short, source-backed reply
- delegated answer: synthesized verdict with evidence and next action
- ambiguous request: ask one clarifying question before routing
