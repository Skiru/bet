---
name: bet-applying-sport-protocols
description: "Sport-specific analysis protocols for 5 core betting sports (football, volleyball, basketball, tennis, hockey) plus archived protocols for additional sports — required stat tables (Football §3.1, Tennis §3.2, Basketball §3.3, Volleyball §3.4, Hockey §3.5), mandatory multi-market calculation tables per sport, upset risk checklists with thresholds, instant red flags (§7.3), and market decision hierarchies. Use when performing deep per-candidate analysis, scoring upset risk, or running red flag checks."
user-invokable: false
---

# Applying Sport-Specific Protocols

Detailed per-sport analysis requirements. Load this skill when performing STEP 3+ analysis or STEP 6-7 context/gate checks. Each sport has required stats, market decision rules, upset thresholds, and red flags.

## Sport Tiers

| Tier | Sports | Scanning Depth |
|------|--------|---------------|
| **Tier 1 (CORE)** | Football, Volleyball, Basketball, Tennis, Hockey | ALL leagues/divisions deeply |

## Per-Sport Protocols

Detailed protocols for each sport are in the reference file. Load when analyzing candidates for that sport:

→ See [references/sport-details.md](references/sport-details.md) for full stat tables, multi-market calculation templates, and red flag checklists per sport.

## Market Hierarchies

→ Full market hierarchy tables are in `bet-analyzing-statistics` §3.0. Load that skill for market ranking protocol and priority order per sport.

## Quick Reference: Upset Risk Thresholds

| Sport | ML Ban Threshold | Max Score |
|-------|-----------------|-----------|
| Tennis | ≥4 | 12 |
| Football | ≥4 | 8 |
| Basketball | ≥3 | 6 |
| Hockey | ≥3 | 6 |
| Volleyball | ≥3 | 6 |

**Paradox Rule:** High upset risk → OVER totals premium (competitive = more play). Low upset risk → OVERS dangerous (blowout).

## Quick Reference: Instant Red Flags (§7.3)

| Sport | Critical Red Flags |
|-------|-------------------|
| Tennis | WC/Q/LL? Fatigue (3h+ prev)? First match on surface? Identity slash? Drift >8%? |
| Football | Dead rubber? Cup rotation (CL/EL <5d)? Derby? International break? Synthetic pitch? |
| Basketball | B2B? Load management? Tank mode? Elimination? |
| Hockey | Backup goalie? B2B? Down 0-3 in series? |
| Volleyball | Playoff clinched? 5th set to 15? |

**ANY red flag fired → REJECT, DOWNGRADE, or explicitly JUSTIFY with data.**

## Connected Skills

| Skill | Load for |
|-------|----------|
| `bet-analyzing-statistics` | §3.0 market ranking protocol, safety score formula, probability engine |
| `bet-building-coupons` | V3-V4k sport-specific validations during coupon construction |
| `bet-navigating-sources` | Source fallback chains per sport for data collection |
