# Pipeline State Protocol (Anti-Drift for MoE Models)

This protocol prevents context drift in long pipeline sessions by externalizing state to a checkpoint file. It is MANDATORY for the orchestrator and RECOMMENDED for specialist agents.

## Why This Exists

Qwen3.6-35B-A3B (MoE 3B active/35B total) loses track of pipeline position after ~40 steps. Without external state, the model:
- Skips steps it "thinks" were completed
- Forgets which specialist verdicts it received
- Repeats work or proceeds without required gates
- Loses the thread of accumulated evidence

## Checkpoint File

**Path:** `betting/data/.pipeline_checkpoint.md`

**Written by:** Orchestrator after EVERY step completion.
**Read by:** Orchestrator BEFORE every step start.

## Mandatory Write Points

After each of these events, write the checkpoint:
1. Script execution completes (success or failure)
2. Specialist verdict received from `task` tool
3. Validation gate passes or fails
4. Phase transition (data → analysis → build)

## Checkpoint Format

```markdown
# Pipeline Checkpoint — {date}
## Position
- CURRENT_STEP: S{n}
- NEXT_ACTION: {what to do next}
- PHASE: {data|analysis|build|presentation}
- STEPS_COMPLETED: {n}/23

## Completed Steps
- [x] S0: settled | PnL: +X.XX PLN | learning: {key signal}
- [x] S0.5: DB OK | blockers: none
- [x] S1: {N} fixtures | 5 sports: ✓
- [x] S1e: {N} candidates | quality: {FULL/PARTIAL mix}
- [x] S2: {N} tips | consensus: {key picks}
- [ ] S3: (not started)

## Active Verdicts (carry forward)
- bet-scanner: APPROVED (quality=8, candidates=302, gaps=hockey sparse)
- bet-scout: APPROVED (consensus=12 picks, contrarian=3, fusion: strong)

## Flags & Blockers
- {any quality flags, data gaps, or stop conditions}

## Key Numbers (cite these, don't reinvent)
- shortlist_count: 302
- team_form_coverage: 67%
- tipster_tips_count: 15
- approved_count: (pending S7)
```

## Read Protocol (BEFORE each step)

1. `cat betting/data/.pipeline_checkpoint.md`
2. Verify: "Am I at the correct step?"
3. Verify: "Do I have all prerequisites for this step?"
4. If checkpoint says S3 completed but you're about to run S3 again → STOP, you're looping

## Anti-Drift Anchors (memorize these)

| Mnemonic | Rule |
|----------|------|
| **RUN-DELEGATE-PROCEED** | Script → task tool → verdict → next. NEVER skip `task`. |
| **CITE-OR-DELETE** | Every number needs a source. No source = delete it. |
| **CHECK-BEFORE-RUN** | Read checkpoint. Verify position. Then execute. |
| **WRITE-AFTER-DONE** | Update checkpoint immediately after step completes. |
| **COUNT-AND-VERIFY** | After each script: count outputs, verify vs checkpoint expectations. |

## Recovery From Drift

If you notice you're confused about pipeline position:
1. STOP generating text
2. `cat betting/data/.pipeline_checkpoint.md`
3. Compare checkpoint to your current action
4. If mismatch → trust the checkpoint, not your memory
5. Resume from the checkpoint's NEXT_ACTION

## Integration With Specialist Agents

When delegating to a specialist via `task`:
- Include the checkpoint's "Key Numbers" in your delegation message
- After receiving verdict: extract the specialist's key metrics and write them to "Active Verdicts"
- This ensures the next delegation has cumulative context

## Checkpoint Initialization

At session start (before S0):
```markdown
# Pipeline Checkpoint — 2026-05-29
## Position
- CURRENT_STEP: PRE-FLIGHT
- NEXT_ACTION: Load config + check previous settlement
- PHASE: initialization
- STEPS_COMPLETED: 0/23

## Completed Steps
(none)

## Active Verdicts
(none)

## Flags & Blockers
(none)

## Key Numbers
(pending discovery)
```
