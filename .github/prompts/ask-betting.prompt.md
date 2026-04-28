---
description: "Ask any betting question — routes to the right specialist agent via the orchestrator. Use for questions, actions, and status checks."
agent: bet-orchestrator
argument-hint: "Ask any betting question, e.g. 'what is the current bankroll?'"
---

# ASK BETTING

Route this user message to the appropriate specialist agent.

## USER MESSAGE

{{input}}

## INSTRUCTIONS

1. Classify the intent of the user message (QUESTION / ACTION / STATUS).
   - This is NOT a pipeline invocation — do NOT enter S0→S8 mode.
2. Discover current session state (date, version, pipeline progress, last settlement).
3. Match the message against the knowledge domain map.
4. For STATUS: answer directly from artifacts.
5. For QUESTION/ACTION: delegate to the matched specialist agent with context files and session state.
6. For multi-domain messages: follow the multi-domain triage protocol (max 2 agent calls).
7. Return the specialist's answer to the user.
