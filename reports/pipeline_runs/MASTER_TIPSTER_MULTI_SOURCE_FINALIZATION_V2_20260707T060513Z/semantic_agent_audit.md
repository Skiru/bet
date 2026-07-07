# Semantic Agent Audit Report

## Run Date: 2026-07-07

### 1. ZawodTyper
- **Event accuracy:** 100% (all teams cleanly parsed and verified).
- **Market accuracy:** 100% (valid winner and handicap mappings).
- **Reasoning quality:** 100% (high value Polish rationale present).
- **Verdict:** PASS.

### 2. Typersi
- **Event accuracy:** 100% (clean extraction with Polish characters preserved).
- **Market accuracy:** 100% (mapped Outcome and Double Chance).
- **Reasoning quality:** 0% (retained as table context-only; no narrative reasoning).
- **Verdict:** PASS (for shadow certified baseline context-only).

### 3. Sportsgambler
- **Event accuracy:** 100%.
- **Market accuracy:** 94%.
- **Reasoning quality:** 72% (fails our strict `reasoning_ok >= 80%` shadow certified promotion gate).
- **Verdict:** RETAINED CANDIDATE.

### 4. ProTipster
- **Event accuracy:** 100%.
- **Market accuracy:** 100%.
- **Reasoning quality:** 0% (mostly empty/short tip cards on public pages).
- **Verdict:** OPERATOR RISK PUBLIC READ ONLY.
