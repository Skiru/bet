# Agent Execution Protocol

- `bet-executor` runs scripts using Fish and records `$pipestatus`; business agents deny shell.
- Domain agents gather only source-bound evidence and return compact status, decision, evidence, calculations, uncertainty, risks, and one next action.
- `bet-researcher` resolves factual conflicts; `bet-risk-gatekeeper` resolves risk conflicts; `bet-auditor` verifies unresolved final consistency without repairing.
- Tipster absence is explicit and does not block core analysis. Every event receives a terminal status or reason.
- Missing odds permit analysis but prohibit EV, bettable status, Kelly/stakes, and executable coupons.
- S9 is human-only and requires a real Superbet quote. No browser/operator automation or generated approval is valid.
- Persist verbose output outside chat. Use a safe checkpoint before an unavoidable UI/context limit and continue the same `RUN_ID` without replaying completed phases.
