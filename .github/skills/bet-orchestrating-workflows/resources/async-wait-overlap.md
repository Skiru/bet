# Async Wait Overlap

This file is the canonical owner of orchestrator-specific async-wait overlap. Only prompts or agents that reference this resource inherit the behavior. The first consumer is [orchestrate-betting-day.prompt.md](../../../prompts/orchestrate-betting-day.prompt.md).

For the generic async execution law, use [agent-execution-protocol.instructions.md](../../../instructions/agent-execution-protocol.instructions.md). For source selection, fallback order, and browsing safety, use [bet-navigating-sources](../../bet-navigating-sources/SKILL.md). This file owns only the trigger, scope, budget, pause/stop behavior, and Async Wait Addendum details for proactive Brave overlap.

## Activation

- Mandatory whenever the orchestrator launches a step in async mode under the existing `>120s` execution rule.
- Optional for shorter manually async waits only when a known context gap already exists and a single-pass overlap can shorten the downstream specialist path.
- If no meaningful read-only gap exists, monitor the running step and prepare the next handoff without forcing search activity.

## Scope

- Default to the active-stage frontier, not the full scan universe.
- Use explicit-gap-first ordering: candidates already named in the current shortlist, gate, or coupon-candidate artifact with known missing context go first.
- If no explicit gap list exists, use the top three unresolved candidates or one stage-level topic from the current artifact.
- Never widen to the full scan universe during the same wait window.

## Brave Budget

- Max two Brave research packs per async wait window.
- One pack = up to three Brave queries (`web`, `news`, `llm-context`) for one candidate or one stage-level topic.
- If the budget is exhausted, turn the remaining questions into a checkpoint note or Async Wait Addendum for the post-script specialist instead of widening search.

## Allowed Overlap Work

- Brave web/news/llm-context research packs on the active-stage frontier.
- Read-only DB inspection, artifact reads, and source-policy loads needed to sharpen the same frontier.
- Drafting a checkpoint note or optional Async Wait Addendum for the next specialist handoff.
- Reading finished terminal output as soon as the async step resolves, then returning to the normal delegate-after-finish loop.

## Prohibited Overlap Work

- Launching the next pipeline step or any dependent script before the current async step finishes.
- Delegating specialist analysis before finished output exists.
- Starting concurrent DB-writing pipeline work or other shared-state mutation.
- Parallel Playwright-heavy browsing, tipster scraping, or other browser-led work in the same wait window.

## Pause And Stop

- Pause overlap immediately if the terminal requests input, a blocking error changes the current stage hypothesis, or the current wait window ends.
- Stop overlap as soon as the script completes, then read the full output, validate the artifact, and delegate through [handoff-contracts.md](handoff-contracts.md).
- Resume or stop decisions still come from [resume-stop-gates.md](resume-stop-gates.md); this file does not replace that baseline.

## Async Wait Addendum

Use this optional addendum only when wait-window research produces evidence the next specialist should verify after the script finishes. Append it by reference to the generic payload from [handoff-contracts.md](handoff-contracts.md); do not rewrite that resource here.

```text
### Async Wait Addendum (optional)
- wait window: <step + timestamp>
- frontier target: <candidate or stage-level topic>
- context gap closed: <what Brave/read-only research answered>
- sources checked: <web/news/llm-context or read-only files/DB>
- unresolved follow-up: <what the specialist should verify against finished output>
```

Specialist verdicts on finished outputs remain authoritative. The addendum is supplemental and never replaces the finished-output-first delegation rule.