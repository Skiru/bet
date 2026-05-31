---
description: "Hard reject rules from settled losses. MANDATORY during S3/S5/S7/S8. Apply at COUPON CONSTRUCTION — candidates still appear in matrix (R3) but are FLAGGED/REJECTED in coupons."
---

# Betting Mistakes — Hard Rules

> Read during S3, S5, S7, S8. Source: settled losses.
> R3 compliant: candidates appear in matrix/extended pool. Rules fire at coupon build.

## ⛔ HARD REJECT TABLE

| ID | Market/Situation | Rule | Origin |
|----|------------------|------|--------|
| TENNIS_SETS_001 | O3.5 sets | ALL: ranking gap <15, H2H competitive, both <60% straight-set wins L5, no surface specialist, no injury return | Etcheverry/Borges 2026-05-24 |
| TENNIS_GAMES_001 | Underdog games OVER | Ranking gap <50, service hold >50% L5, odds ≤2.00 | Ferro O6.5 @2.45 lost |
| HANDBALL_001 | Handball ML in AKO | Implied prob ≥70% (≤1.43), never in 2+ coupons, prefer totals/HC | Wisła Płock ML @1.70 |
| GOALS_001 | Over X goals | Combined L5 > line + 0.5 buffer. If below → FLIP to UNDER or SKIP | Parma O2.5 (combined L5=2.2) |
| UNDER_GOALS_001 | Under 2.5 goals | FORBIDDEN when: team MUST win + combined L5>2.5 + odds≥2.00. Max 1 coupon. | Palace/Arsenal U2.5 in 3 coupons |
| LOWER_LEAGUE_001 | Lower league ML | No ML below 3rd tier. 2-3 Liga: only ≤1.40. Prefer stat markets. | Pcimianka @2.17 (7th tier) |
| SOT_001 | Shots on Target Over | Combined L5 > line + 1.5 buffer. If L5 < line → INSTANT REJECT. Dead rubber: −1.5 | Brighton/ManU O9.5 (L5=7.4) |
| CORNERS_CONTEXT_001 | Dead rubber corners | Apply −2.5 penalty to expected. If post-penalty < line → REJECT | Napoli/Udinese O9.5 |
| BTTS_CONTEXT_001 | BTTS | Relegation matches → default NO. Never bet live 0-0 at 30'+ defensive. | Catanzaro/Monza BTTS |
| CORRELATION_001 | Pick repetition | **MAX 1 coupon per unique pick.** Never repeat. Diversify events. | 4 picks × 2.25 coupons = 9 losses |
| SAFETY_FLOOR_001 | Low safety score | <0.15 → INSTANT REJECT. <0.30 → extended pool ONLY. | Bologna/Trento safety=0.0 |
| DIRECTION_CONTEXT_001 | Must-win direction | margin ≤0.5 + must-win context → verify direction. L5 contradicts → REJECT/FLIP | Fürth Shots U13.5 (avg=line) |
| SYNTHETIC_RESCUE_001 | High-consistency rescue | L5 ≥4/5 (80%+) → NEVER auto-demote. Rescue from EXTENDED to coupon. | Waltert/Siniakova L5 5/5 missed |
| KICKOFF_GUARD_001 | Time validation | kickoff > NOW at presentation. Started events → REJECT from bettable. | 4 tennis picks already LIVE |

## 📋 Quick Decision Matrix

| Signal | Action |
|--------|--------|
| safety < 0.15 | INSTANT REJECT |
| safety < 0.30 | Extended pool only |
| Same pick in 2+ coupons | REJECT from 2nd+ |
| Combined L5 < line (Over bet) | REJECT or FLIP |
| L5 contradicts direction | FLAG, likely REJECT |
| Dead rubber + stat market | Apply −2.5, re-evaluate |
| Lower league ML odds > 1.40 | REJECT |
| Tennis O3.5 sets, gap > 15 | REJECT |
| L5 ≥ 4/5 in extended pool | RESCUE to coupon |
| kickoff < NOW | INSTANT REJECT |

## ✅ Positive Signals (what WORKS)

| Market | Data Signal | Hit Rate |
|--------|------------|----------|
| Team corners OVER | Combined L5 > line + 1.0 | 87% |
| Team fouls OVER | L5 > line, rising trend | 77%+ |
| SOT OVER | Combined L5 > line + 1.5 | 70%+ |
| Under 2.5 goals | Combined L5 < 1.8 | 74% |
