# Handoff Contracts

Use this payload shape whenever one prompt or agent hands work to another.

## Required Fields

- task
- source artifact
- current date or betting day
- input artifacts and timestamps
- minimum required evidence
- expected response shape
- stop conditions

## Standard Payload

```text
runSubagent("bet-<specialist>"):
---
## Task: <concise description>

### Internal Prompt
[load the named prompt or resource]

### Context
- date: <YYYY-MM-DD>
- source files: <list>
- current stage: <S0-S10>

### Expected Response
- metrics
- specialist analysis
- verdict
- next action
---
```

## Rule

Keep the handoff payload short and explicit. The specialist should receive finished context, not a pasted manual.