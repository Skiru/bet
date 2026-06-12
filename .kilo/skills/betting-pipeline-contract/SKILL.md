---
name: betting-pipeline-contract
description: Betting pipeline phase contract for orchestrator and specialists. Defines phases A-E, mandatory specialists, entry/exit requirements, hard stops, and handoff artifacts.
---

# Betting Pipeline Contract

## Phase Overview

| Phase | Scope | Mandatory specialists | Exit artifact |
|---|---|---|---|
| A | S0 settlement and historical learning | `bet-settler`, `bet-db-analyst`, `bet-test-engineer` | `.kilo/state/phase-A-handoff.md` |
| B | S1–S1e discovery and shortlist | `bet-scanner`, `bet-test-engineer` | `.kilo/state/phase-B-handoff.md` |
| C | S2 tipster aggregation | `bet-scout`, `bet-test-engineer` | `.kilo/state/phase-C-handoff.md` |
| D | S2.3–S7 enrichment, modelling and gates | `bet-enricher`, `bet-statistician`, `bet-valuator`, `bet-challenger`, `bet-test-engineer` | `.kilo/state/phase-D-handoff.md` |
| E | S8–S10 construction and final validation | `bet-builder`, `bet-test-engineer` | `.kilo/state/phase-E-handoff.md` |

## Phase Entry Requirements

### Phase A
- Previous session closed with explicit handoff or fresh start
- Database accessible and verified by `bet-db-analyst`
- No pending script failures

### Phase B
- Phase A handoff exists and passes `bet-test-engineer` validation
- Database contains current fixture data
- No unresolved settlement issues

### Phase C
- Phase B handoff exists and passes validation
- Shortlist contains at least one fixture
- Zero valid tips is a **hard stop** — do not proceed to Phase D

### Phase D
- Phase C handoff exists with at least one valid tip
- All mandatory specialists have returned PASS
- `bet-challenger` must approve before Phase E

### Phase E
- Phase D handoff exists with approved candidates
- All gates passed
- `bet-test-engineer` must validate final artifacts

## Phase Exit Requirements

Each phase must:
1. Complete all mandatory specialist invocations
2. Receive PASS from `bet-test-engineer`
3. Persist handoff artifact under `.kilo/state/`
4. Return exactly one next action

## Hard Stops

- **Zero valid tips in Phase C**: Stop pipeline, return `NO_DATA`
- **Two bounded technical failures**: Escalate to `bet-engineer`
- **Missing mandatory evidence**: Block phase, request enrichment
- **`bet-test-engineer` FAIL**: Do not proceed, repair and re-validate

## Reconciler Conditions

Invoke `bet-reconciler` when:
- Two sources provide conflicting material facts
- Database and external source disagree on fixture/odds
- Timestamp ordering is ambiguous

Return: `RESOLVED` with chosen source, or `UNRESOLVED` with explicit conflict record.

## Engineer Escalation

Invoke `bet-engineer` only after:
1. Two bounded attempts to fix a script/runtime issue
2. Clear diagnosis of the failure
3. Focused regression test requirement

`bet-engineer` must:
- Make the smallest reversible repair
- Run focused tests
- Return PASS/FAIL with evidence

## Test-Engineer Gate

`bet-test-engineer` must:
- Independently validate artifacts and invariants
- Return PASS/FAIL with exact commands and evidence paths
- Never repair failures

## Handoff Requirements

Each handoff must contain:
- Phase identifier
- Status: PASS/FAIL/BLOCKED/NO_DATA
- Evidence paths (artifact files)
- Key metrics (counts, coverage, confidence)
- Risks and uncertainties
- Next action

Maximum handoff size: 1,000 tokens.

## Session Boundary

- Run exactly one phase per session
- Start fresh session after phase completion
- Do not carry context across phases
