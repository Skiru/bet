# Runtime Reload Required

- Kilo loads `.ts`/`.js` plugins and tools at startup.
- `.kilo/tool/*.ts` standalone tool files can define callable tool names by filename.
- After this repair, the user must fully restart Kilo/IDE before rerunning `J2A2`.
- The first live smoke after restart must verify the active tool version and a successful write under `reports/pipeline_runs`.
