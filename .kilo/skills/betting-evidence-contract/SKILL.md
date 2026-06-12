---
name: betting-evidence-contract
description: Evidence and data contract for betting specialists. Defines approved sources, as_of rules, fact vs inference, UNKNOWN handling, and artifact traceability.
---

# Betting Evidence Contract

## Approved Source Types

### Primary sources (highest authority)
- Database rows via `bet_sqlite_query`
- Generated artifacts under `.kilo/artifacts/`
- Phase handoffs under `.kilo/state/`

### External sources (require `as_of`)
- Web pages fetched via `webfetch`
- Search results via `brave-search_brave_web_search`, `brave-search_brave_news_search`
- Library documentation via `context7_*`

### Prohibited sources
- Invented or hallucinated data
- Unverified claims from memory
- Stale cached data without timestamp

## as_of Rules

Every external fact must include:
- `as_of`: ISO 8601 timestamp of fetch
- `source`: URL or query identifier
- `retrieved_by`: Tool name

Example:
```
odds: 1.85
as_of: 2026-06-12T09:30:00Z
source: https://example.com/fixture/123
retrieved_by: webfetch
```

## Fact vs Calculation vs Inference

| Type | Definition | Example |
|------|------------|---------|
| Fact | Directly observed from source | Odds 1.85 from bookmaker page |
| Calculation | Derived from facts with explicit formula | EV = (probability * odds) - 1 |
| Inference | Conclusion drawn from patterns | "Team likely tired" from schedule |

- Facts require source citation
- Calculations require formula and inputs
- Inferences require explicit uncertainty flag

## UNKNOWN Handling

When data cannot be verified:
- Use `UNKNOWN` as the value
- Lower confidence rating
- Document what was attempted
- Do not substitute guesses

Example:
```
injury_status: UNKNOWN
reason: Source page returned 404
attempted: webfetch https://team.com/injuries
```

## Source Independence

For material external facts:
- Prefer two independent sources
- If sources conflict, invoke `bet-reconciler`
- Document source disagreement

## Contradiction Handling

When sources contradict:
1. Record both values with sources
2. Assess source authority (official > aggregator > social)
3. Assess recency (newer > older)
4. If unresolved, invoke `bet-reconciler`
5. Never silently choose one source

## No Invented Data

Never invent:
- Odds values
- Fixture times
- Team names or lineups
- Injury status
- Statistics
- Consensus percentages
- Model outputs

If data is missing and cannot be fetched, use `UNKNOWN`.

## Bounded Result Requirements

- Tool output: maximum 8 KiB displayed
- Specialist output: maximum 900 tokens
- Handoff: maximum 1,000 tokens
- Save verbose output to `.kilo/artifacts/`

## Specialist Result Schema

Every betting specialist must return:

```
STATUS: PASS | FAIL | BLOCKED | NO_DATA
DECISION: <one-line verdict>
EVIDENCE: <paths to artifacts or source citations>
CALCULATIONS: <derived values with formulas>
UNCERTAINTY: <confidence level and unknowns>
RISKS: <material risks identified>
NEXT_ACTION: <exactly one action>
```

## Artifact Traceability

Every artifact must include:
- Creation timestamp
- Creating agent
- Source references
- Phase identifier

Example artifact header:
```markdown
# Phase D Handoff

Created: 2026-06-12T09:30:00Z
Agent: bet-valuator
Phase: D
Sources: .kilo/artifacts/odds-2026-06-12.md
```
