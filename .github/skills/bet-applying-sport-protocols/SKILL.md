---
name: bet-applying-sport-protocols
description: "Sport-specific analysis protocols for 5 core betting sports (football, volleyball, basketball, tennis, hockey) plus archived protocols for additional sports — required stat tables (Football §3.1, Tennis §3.2, Basketball §3.3, Volleyball §3.4, Hockey §3.5), mandatory multi-market calculation tables per sport, upset risk checklists with thresholds, instant red flags (§7.3), and market decision hierarchies. Use when performing deep per-candidate analysis, scoring upset risk, or running red flag checks."
user-invokable: false
---

# Applying Sport-Specific Protocols

Detailed per-sport analysis requirements. Load this skill when performing STEP 3+ analysis or STEP 6-7 context/gate checks. Each sport has required stats, market decision rules, upset thresholds, and red flags.

## Sport Tiers

| Tier | Sports | Scanning Depth | Analysis |
|------|--------|---------------|----------|
| **KEY (Tier 1)** | Football, Volleyball, Basketball, Tennis | ALL leagues/divisions deeply | Full per candidate |
| **SUPPORT (Tier 2)** | Hockey, Baseball, Esports, Snooker, Darts, Table Tennis, Handball, MMA, Padel, Speedway | Main leagues/tournaments | Full per candidate (same quality) |

## Per-Sport Protocols

Detailed protocols for each sport are in the reference file. Load when analyzing candidates for that sport:

→ See [references/sport-details.md](references/sport-details.md) for full stat tables, multi-market calculation templates, and red flag checklists per sport.

## Quick Reference: Market Hierarchies

| Sport | Priority (→ least preferred) | Key Statistical Markets |
|-------|------------------------------|------------------------|
| Football | Fouls → Cards → Corners → Shots → Team totals → BTTS → U2.5 → O2.5 → DC/DNB → 1X2 | Corners, fouls, cards, shots |
| Tennis | Game totals O/U → Set totals → Game HC → Set HC → ML | Games, sets |
| Basketball | Team totals → Quarter totals → Game totals → Spreads → ML | Points, team totals |
| Hockey | Period totals → Game totals → Puck line → ML | Period totals, shots |
| Baseball | F5 totals → Team totals → Game totals → Run line → ML | F5 innings, team totals |
| Volleyball | Set score O/U → Point totals → Set totals → Set HC → ML | Sets, total points |
| Esports | Round totals → Map totals → Map HC → Kill totals → ML | Rounds, maps |
| Snooker | Century O/U → Frame totals → Frame HC → ML | Frames, centuries |
| Darts | 180s O/U → Leg totals → Set totals → ML | 180s, legs |
| Handball | Half totals → Game totals → HC → ML | Half totals, game totals |
| Table Tennis | Point totals → Set totals → Set HC → ML | Points, sets |
| MMA | Method → O/U rounds → ITD → ML | Rounds |
| Padel | Game totals → Set totals → Set HC → ML | Games, sets |
| Speedway | Total pts → HC → Match winner | Total points |

## Quick Reference: Upset Risk Thresholds

| Sport | ML Ban Threshold | Max Score |
|-------|-----------------|-----------|
| Tennis | ≥4 | 12 |
| Football | ≥4 | 8 |
| Basketball | ≥3 | 6 |
| Hockey | ≥3 | 6 |
| Baseball | ≥3 | 6 |
| Volleyball | ≥3 | 6 |
| Esports | ≥2 | 5 |
| Snooker | ≥2 | 5 |
| Darts | ≥2 | 5 |
| MMA | ≥3 | 6 |
| Handball | ≥3 | 6 |
| Table Tennis | ≥2 | 5 |
| Padel | ≥3 | 6 |
| Speedway | ≥3 | 6 |

**Paradox Rule:** High upset risk → OVER totals premium (competitive = more play). Low upset risk → OVERS dangerous (blowout).

## Quick Reference: Instant Red Flags (§7.3)

| Sport | Critical Red Flags |
|-------|-------------------|
| Tennis | WC/Q/LL? Fatigue (3h+ prev)? First match on surface? Identity slash? Drift >8%? |
| Football | Dead rubber? Cup rotation (CL/EL <5d)? Derby? International break? Synthetic pitch? |
| Basketball | B2B? Load management? Tank mode? Elimination? |
| Hockey | Backup goalie? B2B? Down 0-3 in series? |
| Baseball | Bullpen game? MLB debut pitcher? Wind blowing out? |
| Volleyball | Playoff clinched? 5th set to 15? |
| Esports | Stand-in? New patch <2wk? Online vs LAN? BO1? |
| Snooker | Long-format fatigue? Morning session? |
| Darts | Sets vs legs format? 180s power matchup? |
| Handball | European week rotation? 7m specialist absent? |
| Table Tennis | Division gap in cup? BO5 vs BO7? |
| MMA | Late opponent change? Failed weight cut? Layoff >1yr? |
| Padel | New pair <3 events? Indoor vs outdoor? |
| Speedway | Rain/wet? Rider track record? |

**ANY red flag fired → REJECT, DOWNGRADE, or explicitly JUSTIFY with data.**

## Connected Skills

- `bet-analyzing-statistics` — §3.0 Statistical Market Ranking Protocol that uses the per-sport stat tables defined here
- `bet-building-coupons` — Sport-specific validations (V3-V4k) that verify compliance with protocols defined here
- `bet-navigating-sources` — Sport-specific source chains for collecting the data required by each protocol
