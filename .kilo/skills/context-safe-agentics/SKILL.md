---
name: context-safe-agentics
description: Compact control-plane, artifact persistence, and safe-checkpoint rules for long or multi-phase agentic work.
---

# Context-Safe Agentics

- Treat chat context as a control plane, not a data store.
- Persist detailed outputs immediately; reference paths and line ranges.
- Keep one model generation and one subagent active at a time.
- Ask tools for aggregates, filters, limits and narrow ranges.
- Keep subagent return under 1,200 tokens.
- Compact manually before a major shift in objective.
- Keep the same run identity and do not repeat completed phases after continuation.
- Before an unavoidable UI/context limit, finish the current atomic operation and persist a safe checkpoint as compact JSON with status, decision, completed phases, branch, HEAD, changed files, tests passed, tests pending, risks, safe-to-continue flag, handoff path, run ID, and exact continuation prompt.
- A checkpoint is `STATUS: CHECKPOINT` and `DECISION: SAFE_CONTINUATION_REQUIRED`; it never claims PASS.
- Never terminate with generic maximum-step-limit prose. Resume from the handoff in a fresh session only when necessary.
