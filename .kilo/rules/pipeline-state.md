# Pipeline State

Before every pipeline step, read the current handoff under `.kilo/state/` if it exists.
After every step, write a compact checkpoint:
1. Step completed and status.
2. Key metrics/artifacts.
3. Next step and open risks.
Never rely on chat memory alone.
Keep the same `RUN_ID` across bounded continuation. Before an unavoidable UI/context limit, add branch, HEAD, changed files, completed phases, passed/pending tests, risks, handoff path, and exact continuation prompt. A safe checkpoint never claims PASS.
