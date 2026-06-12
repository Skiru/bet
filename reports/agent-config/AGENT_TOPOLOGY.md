# Agent Topology

## Primary Agents

| Name | Mode | Model | Description |
|------|------|-------|-------------|
| bet-orchestrator | primary | openai-compatible/qwen36-local-35b | Phase-bounded betting-pipeline controller |

## Subagent Specialists

| Name | Mode | Model | Steps | Temperature | Description |
|------|------|-------|-------|-------------|-------------|
| bet-settler | subagent | openai-compatible/qwen36-local-35b | 12 | 0.1 | S0 settlement reconciliation |
| bet-db-analyst | subagent | openai-compatible/qwen36-local-35b | 10 | 0.05 | Database readiness auditor |
| bet-scanner | subagent | openai-compatible/qwen36-local-35b | 14 | 0.15 | Fixture discovery specialist |
| bet-scout | subagent | openai-compatible/qwen36-local-35b | 16 | 0.15 | Tipster aggregation specialist |
| bet-enricher | subagent | openai-compatible/qwen36-local-35b | 14 | 0.12 | Evidence enrichment specialist |
| bet-statistician | subagent | openai-compatible/qwen36-local-35b | 12 | 0.12 | Statistical evidence specialist |
| bet-valuator | subagent | openai-compatible/qwen36-local-35b | 12 | 0.1 | Odds valuation specialist |
| bet-challenger | subagent | openai-compatible/qwen36-local-35b | 10 | 0.18 | Adversarial challenger |
| bet-reconciler | subagent | openai-compatible/qwen36-local-35b | 8 | 0.05 | Evidence conflict resolver |
| bet-builder | subagent | openai-compatible/qwen36-local-35b | 11 | 0.1 | Coupon constructor |
| bet-test-engineer | subagent | openai-compatible/qwen36-local-35b | 10 | 0.02 | Independent test validator |
| bet-engineer | subagent | openai-compatible/qwen36-local-35b | 14 | 0.08 | Repair specialist |

## Delegation Graph

```
bet-orchestrator (primary)
├── bet-settler
├── bet-db-analyst
├── bet-scanner
├── bet-scout
├── bet-enricher
├── bet-statistician
├── bet-valuator
├── bet-challenger
├── bet-reconciler
├── bet-builder
├── bet-test-engineer
└── bet-engineer
```

## Phase Assignment

| Phase | Specialists |
|-------|-------------|
| A | bet-settler, bet-db-analyst, bet-test-engineer |
| B | bet-scanner, bet-test-engineer |
| C | bet-scout, bet-test-engineer |
| D | bet-enricher, bet-statistician, bet-valuator, bet-challenger, bet-test-engineer |
| E | bet-builder, bet-test-engineer |

## Conditional Specialists

| Specialist | Invocation Condition |
|------------|---------------------|
| bet-reconciler | Material evidence conflict |
| bet-engineer | Two bounded technical failures |
