---
name: context-safe-agentics
description: Use when a task has many tool calls, subagents, long logs, large files, compaction risk or ContextOverflowError.
---

# Context-Safe Agentics

- Treat chat context as a control plane, not a data store.
- Persist detailed outputs immediately; reference paths and line ranges.
- Keep one model generation and one subagent active at a time.
- Ask tools for aggregates, filters, limits and narrow ranges.
- Keep subagent return under 1,200 tokens.
- Compact manually before a major shift in objective.
- When overflow happens, end the session and resume from a handoff; do not retry the same oversized turn.
