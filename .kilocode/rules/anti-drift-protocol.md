# Anti-Drift Rules (MoE Model Robustness)

> These rules exist because Qwen3.6-35B-A3B (3B active params) drifts in long sessions.

## 5 Mandatory Behaviors

1. **CITE-OR-DELETE** — Every statistic needs a `sqlite_read_query` verification. If you can't query it, write "UNVERIFIED" or delete it. NEVER guess a number.

2. **RUN-DELEGATE-PROCEED** — (Orchestrator only) After every script: use `task` tool to delegate to specialist. NEVER skip delegation.

3. **CHECK-BEFORE-RUN** — (Orchestrator only) Read `betting/data/.pipeline_checkpoint.md` before every step. Verify you're at the correct position.

4. **WRITE-AFTER-DONE** — (Orchestrator only) Update checkpoint after every step completion with key metrics.

5. **RE-GROUND AT 2000 TOKENS** — If you've generated >2000 tokens without a tool call, STOP. You are drifting. Call `sequentialthinking_sequentialthinking` to recenter.

## What Drift Looks Like (detect these in yourself)

- You wrote "L10 avg = 13.6" but didn't run a query → DRIFT (hallucination)
- You ran a script and are about to write the next command without delegating → DRIFT (skipping)
- You can't remember which step you completed last → DRIFT (state loss)
- You're explaining methodology instead of analyzing data → DRIFT (filler)
- Your output has 0 tool calls in the last 5 paragraphs → DRIFT (untethered generation)

## Recovery

1. STOP generating text immediately
2. Call `sequentialthinking_sequentialthinking` with thought: "What step am I at? What did I just complete? What's next?"
3. Read the checkpoint file or relevant DB data
4. Resume from verified state
