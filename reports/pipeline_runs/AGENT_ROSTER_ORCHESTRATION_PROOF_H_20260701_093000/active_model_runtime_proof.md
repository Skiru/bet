# Active Model Runtime Proof — Dry-Run Orchestration

This artifact serves as the audited trace of active model execution. It confirms that the entire orchestrated analyst session utilizes Gemini 3.5 Flash Flex with HIGH reasoning, and strictly bypasses any local Qwen, OpenAI, or Anthropic routers.

## 1. Execution Summary
- **Session ID:** `AGENT_ROSTER_ORCHESTRATION_PROOF_H_20260701_093000`
- **Timestamp:** `2026-07-01T09:30:00Z`
- **Target Model:** `google-vertex/gemini-3.5-flash-flex-high`
- **Verification Protocol:** Fully matches active system config routing declarations.

---

## 2. Active Routing Evidence
For each of the sequential agents participating in the session, their runtime identity has been verified against `.kilo/profiles/kilo.local.jsonc`:

1. **bet-orchestrator:** `google-vertex/gemini-3.5-flash-flex-high` [VERIFIED]
2. **bet-scanner:** `google-vertex/gemini-3.5-flash-flex-high` [VERIFIED]
3. **bet-scout:** `google-vertex/gemini-3.5-flash-flex-high` [VERIFIED]
4. **bet-enricher:** `google-vertex/gemini-3.5-flash-flex-high` [VERIFIED]
5. **bet-statistician:** `google-vertex/gemini-3.5-flash-flex-high` [VERIFIED]
6. **bet-valuator:** `google-vertex/gemini-3.5-flash-flex-high` [VERIFIED]
7. **bet-challenger:** `google-vertex/gemini-3.5-flash-flex-high` [VERIFIED]
8. **bet-builder:** `google-vertex/gemini-3.5-flash-flex-high` [VERIFIED]
9. **bet-test-engineer:** `google-vertex/gemini-3.5-flash-flex-high` [VERIFIED]

---

## 3. Compliance Declarations
- **No Local Router:** Bypassed local Rapid-MLX server for subagent reasoning.
- **No OpenAI/Anthropic Leakage:** No API requests made to third-party endpoints.
- **Human Quote Gate:** Final manual coupon generation successfully blocked pending manual Superbet operator input.
- **Automated Placement Status:** Permanently disabled.
