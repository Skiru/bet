# Betting Power-Agent Tool Ownership

Use only tool names exposed by the active Kilo runtime. Agent YAML is the permission source of truth.

| Agent | Execution and data boundary |
|---|---|
| `bet-executor` | Bash and artifact writes; task delegation exactly to six partners; no DB/web/repository mutation |
| `bet-researcher` | DB reads, current public-source reads, and artifact writes; no Bash or picks |
| `bet-modeler` | DB reads and artifact writes; no Bash or public web |
| `bet-risk-gatekeeper` | DB reads, current public-source reads, and artifact writes; no Bash |
| `bet-builder` | File reads and artifact writes only; no Bash, DB, web, or operator tools |
| `bet-auditor` | Bash for read-only verification, DB reads, and artifact writes; no mutation or repair |
| `bet-settler-postevent` | DB reads and artifact writes; no Bash or pre-match authority |

All seven deny `question`, repository mutation, browser/operator automation, and explicit model overrides. A failed tool call is evidence of unavailability, never permission to invent data. Retry the same operation once, then change strategy or mark the dependent claim UNKNOWN.
