---
description: Start one phase-bounded betting pipeline session from the current handoff.
agent: bet-orchestrator
---

Determine the requested phase A-E from the user's message. Read `AGENTS.md`, `.kilo/CONTEXT_POLICY.md`, the relevant runtime skill, and `.kilo/state/CURRENT_HANDOFF.md` when present. State the phase exit criteria, work only within that phase, and finish by writing both the phase-specific handoff and `CURRENT_HANDOFF.md`.
