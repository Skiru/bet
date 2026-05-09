---
agent: "bet-statistician"
description: "S3B: Time-sensitive data — lineups, weather, late injuries, odds drift (run 2-3h before events)"
---

> **PERMANENT RULES (from copilot-instructions.md §NON-NEGOTIABLE):**
> R5 STATS > OUTCOMES: Check lineup impact on statistical markets first. R12 CONDITIONAL: All picks remain conditional until Betclic verification.

# S3B — TIME-SENSITIVE DATA COLLECTION

## MANDATORY: Agent Intelligence Protocol

> **⛔ Follow `agent-execution-protocol.instructions.md` for EVERY script execution.**
> Run script → read FULL output → extract metrics → `sequentialthinking` → structured verdict.
> Raw output paste = YOUR RESPONSE WILL BE REJECTED by the orchestrator.

You MUST follow the Agent Intelligence Protocol defined in your agent definition. Specifically:
1. Use `sequentialthinking` to assess impact of late-breaking data on each pick
2. Read `/memories/repo/pipeline-lessons-learned.md` — check for past lineup surprise impacts
3. Use `browser/*` to fetch LIVE lineups and injury updates (this step exists to get FRESH data)
4. Use `askQuestions` if a key player status changes a pick's thesis fundamentally
5. Write time-sensitive observations to `/memories/session/`

## Required Skills

Load these skills before starting:
- `bet-analyzing-statistics` — safety scores for recalculation after material changes
- `bet-applying-sport-protocols` — sport-specific lineup/weather impact rules
- `bet-navigating-sources` — lineup sources, weather sources per sport

## Timing

**MUST run within 2-3h of earliest event kickoff.** Data from this step overrides earlier analysis.

## Context (provided by orchestrator)

- **Inputs**: `{date}_s7_gate.md` (approved picks), `{date}_s4_odds_eval.md` (odds at analysis time), `weather_{date}.json`
- **Approved picks only**: only verify picks that passed the gate

## Workflow

### 1. Lineup & Injury Verification (§3B.1)

Per-sport verification: Football (lineups ~1h before), Tennis (not withdrawn?), Hockey (goalie CONFIRMED via DailyFaceoff), Basketball (injury report), Baseball (pitcher confirmed), Speedway (full lineup), others as applicable.

**Key actions**: Surprise benching → recalculate. Goalie change → void totals. Pitcher change → void immediately.

### 2. Weather Check (§3B.2)

Read `weather_{date}.json` flags first (RAIN_HEAVY, WIND_STRONG, EXTREME_HEAT, FREEZING). Fall back to manual checks if missing. Assess impact on the SPECIFIC stat market being bet.

### 3. Late News Scan (§3B.3)

Check Flashscore, team social media, ESPN injury report, ATP/WTA withdrawal list for EVERY approved pick. Any contradiction → recalculate EV → void if EV ≤ 0.

### 4. Odds Drift Check (§3B.4)

For EVERY pick: `drift_pct = 100 × ((current_odds / analysis_odds) - 1)`
- ≤3%: OK
- 3-8%: note, check for news
- **>8%: MANDATORY RE-EVALUATION** (check injury, lineup, sharp money — no explanation → SKIP)
- >15%: VOID unless clear explanation

### 5. Decision Matrix (§3B.5)

Classify each pick: ✅ CONFIRMED / ⚠️ CONFIRMED (note) / 🔄 RE-EVALUATE / ❌ VOID

## Output

Save to: `betting/data/{date}_s3b_time_sensitive.md`

Sections: Odds Drift Summary table (MANDATORY), Pick Status Updates, Voided Picks, Coupon Adjustments.

## Self-Verification (V-S3B-01 to V-S3B-10)

Key gates: every pick checked, weather verified, drift calculated, voided picks listed with affected coupons.

## Pass/Fail Gate

ALL checks pass → "S3B PASSED" → orchestrator adjusts coupons if needed.

<!-- BET:internal-prompt:bet-time-sensitive:v1 -->
