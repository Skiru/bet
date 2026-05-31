# Anti-Drift Rules (3B Active Params — Drifts in Long Sessions)

## 5 Behaviors (memorize — break ANY and you drift)

| # | Rule | Violation = |
|---|------|------------|
| 0 | First tool call = `sequentialthinking` | Blind query spam |
| 1 | Every stat has a query behind it | Hallucination |
| 2 | After every script → delegate via `task` | Script runner |
| 3 | All scripts → `/tmp/sN.txt 2>&1` | Output flood |
| 4 | >2000 tokens without tool call → STOP | Untethered generation |

## Drift Detection (if true → you're drifting, STOP NOW)

- Stat without query → **hallucination** → delete it
- >10 lines of terminal/JSON in your response → **raw dump** → replace with 1-line summary
- About to run next script without delegating → **skipping** → delegate first
- Can't recall current step → **state loss** → read checkpoint
- >3 tool calls without narrating → **blind spam** → narrate findings
- Explaining methodology instead of showing data → **filler** → cut it

## Recovery (always the same)

```
sequentialthinking: "Where am I? What did I just do? What's next?"
→ read checkpoint
→ resume from verified state
```

## Tool Budget

**3 per turn: 1 sequentialthinking + 2 data tools. Then NARRATE.**
