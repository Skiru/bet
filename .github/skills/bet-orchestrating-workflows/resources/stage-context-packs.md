# Stage Context Packs

This file owns mandatory post-output, pre-handoff `Stage Context Pack` policy for eligible stages.
This file does not own in-flight wait behavior, generic handoff payloads, or source-selection rules. [async-wait-overlap.md](async-wait-overlap.md) remains the only owner of wait-window behavior, [handoff-contracts.md](handoff-contracts.md) remains the generic payload owner, and [bet-navigating-sources](../../bet-navigating-sources/SKILL.md) remains the source-selection owner.

## Trigger And Consequence

- Named trigger: `Finished Output Read`.
- Mandatory after the orchestrator reads finished output for an eligible stage and before it delegates to the next specialist.
- Named consequence: `Handoff Incomplete`.
- If the required pack is missing, the handoff is incomplete.

## Independence From Async Waits

- A `Stage Context Pack` is a bounded artifact, not an open-ended research activity.
- The pack may be assembled from evidence gathered during async waits or after script completion.
- The pack requirement is independent from the wait-window policy in [async-wait-overlap.md](async-wait-overlap.md).

## Stage Eligibility Matrix

| Stage surface | Decision | Frontier limit |
| --- | --- | --- |
| S2 tipsters | Excluded | No mandatory stage pack. |
| S2.3 / S2.5 enrichment | Required when the finished output exposes material gaps, stale coverage, or blocked bridges. | Only the surfaced gaps or blocked-source questions. |
| S3 deep stats | Required when the finished output flags anomalies, thin context, or advancement candidates. | Only the flagged candidates or one surfaced topic. |
| S4 odds and EV | Required when drift, stale lines, or bookmaker divergence needs explanation. | Only the surfaced pricing conflicts. |
| S5 / S6 context and upset | Required by default for flagged or advancing picks. | Only the advancing or flagged frontier. |
| S7 gate | Required for borderline, escalated, or evidence-thin picks. | Only the unresolved final-judgment subset. |
| S3B time-sensitive recheck | Required by default. | Only the late-breaking changes tied to the affected picks. |
| S8 portfolio | Excluded | No mandatory stage pack. |
| Final validation | Excluded | No mandatory stage pack. |

## Scope Limits

- Scope the pack only to the finished-artifact frontier already surfaced by the completed stage.
- Never reopen the full event universe, prior stage matrices, or unrelated candidates.
- Max one `Stage Context Pack` per eligible handoff.
- One pack may cover up to two frontier targets or one stage-level topic.
- Each target may use up to three Brave queries (`web`, `news`, `llm-context`) plus read-only local checks.
- Use [bet-navigating-sources](../../bet-navigating-sources/SKILL.md) for source selection and browsing safety instead of duplicating those rules here.

## Pack Shape

Append the pack alongside the finished stage artifact through [handoff-contracts.md](handoff-contracts.md).

```text
### Stage Context Pack (when required)
- stage: <S2.3/S2.5, S3, S4, S5/S6, S7, or S3B>
- finished-artifact frontier: <candidate subset or stage-level topic already surfaced>
- why Brave is needed now: <material gap, drift explanation, motivation question, etc.>
- Brave sources checked: <web/news/llm-context>
- read-only local checks: <DB/file artifacts consulted>
- findings for specialist verification: <supplemental evidence, not final truth>
- unresolved follow-up: <what the specialist must verify against finished output>
```

## Hard Stops

- The pack is supplemental and never replaces the finished stage artifact as the primary input.
- The pack never authorizes early delegation, dependent script execution, or shared-state mutation.
- The downstream specialist must verify the pack against the finished output before changing the stage verdict.