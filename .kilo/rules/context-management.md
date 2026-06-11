# Context Management & Anti-Drift (CRITICAL)

## Token Budget (32768 context / 24576 input)

- Fixed overhead: ~10K (instructions + system)
- Reserved: 2K
- Preserve recent: 8K
- Available: ~4.5K per turn before compaction

## Anti-Drift Rules

| # | Rule | Violation |
|---|------|-----------|
| 0 | First tool = native `