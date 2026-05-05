---
agent: "bet-statistician"
description: "S3B: Time-sensitive data — lineups, weather, late injuries, odds drift (run 2-3h before events)"
---

# S3B — TIME-SENSITIVE DATA COLLECTION

## Required Skills

Load these skills before starting:
- `bet-analyzing-statistics` — safety scores for recalculation after material changes
- `bet-applying-sport-protocols` — sport-specific lineup/weather impact rules
- `bet-navigating-sources` — lineup sources, weather sources per sport

## Timing

**MUST run within 2-3h of earliest event kickoff.** Data from this step overrides earlier analysis.

## Context (provided by orchestrator)

- **Inputs**: `{date}_s7_gate.md` (approved picks), `{date}_s5_odds_ev.md` (odds at analysis time), `weather_{date}.json`
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
