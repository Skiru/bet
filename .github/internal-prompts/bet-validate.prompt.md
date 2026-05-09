---
agent: "bet-builder"
description: "S9: Final coupon validation — mechanical verification of all artifacts"
---

> **PERMANENT RULES (from copilot-instructions.md §NON-NEGOTIABLE):**
> R3 NO AUTO-REJECTION: Verify ALL candidates appear in matrix (§S8.FINAL.I). R5 STATS > OUTCOMES: Verify statistical markets dominate. R12 CONDITIONAL: Verify conditional disclaimer present.

# S9 — FINAL VALIDATION

## MANDATORY: Agent Intelligence Protocol

> **⛔ Follow `agent-execution-protocol.instructions.md` for EVERY script execution.**
> Run script → read FULL output → extract metrics → `sequentialthinking` → structured verdict.
> Raw output paste = YOUR RESPONSE WILL BE REJECTED by the orchestrator.

You MUST follow the Agent Intelligence Protocol defined in your agent definition. Specifically:
1. Use `sequentialthinking` to reason about portfolio-level quality (not just per-coupon checks)
2. Read `/memories/repo/pipeline-lessons-learned.md` — check for known validation failures
3. Use `todo` to track each validation check (V1-V10 + §S8.FINAL A-I)
4. Self-validate: run `validate_coupons.py` and fix ALL FAIL results before returning
5. Write validation insights to `/memories/session/`

## Required Skills

Load these skills before starting:
- `bet-building-coupons` — V1-V10 validation suite, §S8.FINAL verification
- `bet-formatting-artifacts` — ledger consistency, ID format verification

## Context (provided by orchestrator)

- **Inputs**: `betting/coupons/{date}-v{version}.md`, `betting/coupons/{date}.json`, all ledger files
- **Validation script**: `python3 scripts/validate_coupons.py betting/coupons/{date}*.md --format json`

## Workflow

### 1. Run Automated Validation

```bash
python3 scripts/validate_coupons.py betting/coupons/{date}*.md --format json
```

Review all errors. Fix any that are found.

### 2. Manual Cross-Verification

1. **Pick IDs match** across coupon file, picks-ledger, and coupons-ledger
2. **Coupon arithmetic** — re-multiply every coupon's legs independently
3. **Placement order** — verify deadlines match earliest kickoff per coupon
4. **Home/away** — cross-check every event's direction
5. **EV consistency** — stated EV matches actual formula
6. **Total exposure** — sum stakes ≤ daily cap ≤ 25% bankroll
7. **No orphan picks** — every approved pick appears in ≥1 coupon
8. **Polish descriptions** — every leg has proper Polish market description

### 3. Ledger Consistency

- Previous version picks/coupons marked `superseded` with correct version reference
- New entries have correct pick_id/coupon_id format
- All required CSV columns populated

### 4. Final Report

Generate `betting/reports/{date}.md` with:
- Executive summary (picks, coupons, exposure, key stats)
- Per-sport breakdown
- Betclic history insights (from §0.2)
- Version history
- Known risks and conditional notes

## Output

- Validated coupon file (fixes applied in-place)
- Updated ledger files
- Daily report

## Pass/Fail Gate

Zero validation errors → "S9 PASSED" → orchestrator presents final artifacts to user.

<!-- BET:internal-prompt:bet-validate:v1 -->
