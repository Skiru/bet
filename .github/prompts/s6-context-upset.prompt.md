---
name: s6-context-upset
description: "STEP 6: Context verification + Upset Risk Assessment per candidate"
agent: bet-challenger
---

# STEP 6 — CONTEXT + UPSET RISK

## INPUTS
- `betting/data/{date}_s5_odds_ev.md` — approved candidates with EV > 0

## TASK
For EACH approved candidate: verify context factors, score upset risk, apply Paradox Rule.

### PER-CANDIDATE CONTEXT CHECK:
1. **Fixture confirmed?** Not postponed/cancelled? (Flashscore live)
2. **Key absences**: injuries, suspensions, rest — VERIFY on day of analysis
3. **Coach change in last 5 matches?** New coach = form data unreliable. Check Flashscore coach section + TransferMarkt.
4. **Roster changes in last 14 days?** Transfers, loans, returns. Major signings disrupt chemistry. Check TransferMarkt.
5. **Competition context**: relegation, dead rubber, cup rotation, playoff elimination
6. **Fixture congestion**: <72h since last match?
7. **Weather**: outdoor sports — rain/wind impact on corners/goals/play style
8. **Referee**: for cards/fouls markets — specific referee stats, not just "checked"
9. **Motivation**: what's at stake for each team/player?

### UPSET RISK ASSESSMENT (MANDATORY for EVERY candidate):

Score each factor 0 or 1 (some 0-2 per methodology). Sum = upset risk score.

**THRESHOLDS BY SPORT (ML BANNED at or above threshold):**

| Sport | Threshold | Max Score |
|-------|-----------|-----------|
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

---

#### Per-Sport Upset Checklists
Apply the sport-specific upset risk checklists from the `bet-applying-sport-protocols` skill. Each sport has detailed factors scored 0-1 (some 0-2):

- **Tennis** (14 factors): surface mismatch, rising underdog, giant-killer history, age/trajectory, tournament history, qualifier fitness, first H2H, serve dependency, altitude, fatigue, complacency, return strength, sharp money, draw look-ahead
- **Football** (8 factors): derby, cup rotation, dead rubber, international break, key absences, synthetic pitch, manager change, travel fatigue
- **Basketball** (6 factors): B2B, load management, tank mode, elimination, travel, altitude
- **Hockey** (6 factors): backup goalie, B2B, sweep risk, goalie unconfirmed, travel, playoff intensity
- **Baseball** (6 factors): bullpen game, debut pitcher, wind, day-after-night, overworked bullpen, lineup unconfirmed
- **Volleyball** (6), **Esports** (5), **Snooker** (5), **Darts** (5), **Handball** (6), **Table Tennis** (5), **MMA** (6), **Padel** (6), **Speedway** (6): see skill for full factor lists

Score each applicable factor. Sum = upset risk score. Compare to sport threshold in table above.

### PARADOX RULE:
- **HIGH upset risk** (≥threshold) → competitive match → MORE total play → prefer OVER totals
- **LOW upset risk** (<threshold-2) → blowout risk → UNDER bias, avoid overs
- **MODERATE** → standard analysis applies

### OUTPUT FORMAT
Save to: `betting/data/{date}_s6_context.md`

```
## [Event] — Context & Upset Risk

### Context
- Fixture: CONFIRMED / POSTPONED / CHECK
- Injuries: [list or "none confirmed"]
- Competition context: [stakes for each side]
- Congestion: [days since last match for each]
- Weather: [if outdoor — conditions]
- Referee: [name + stats if cards/fouls market]

### Upset Risk Score
| Factor | Score | Notes |
|--------|-------|-------|
| [factor1] | 0/1 | [reason] |
...
| **TOTAL** | X/Y | |

- **Threshold**: [sport-specific]
- **ML status**: ALLOWED / BANNED
- **Paradox Rule**: HIGH → over bias / LOW → under caution / MODERATE → standard
- **Impact on pick**: [how this changes/confirms the S5 recommendation]
```

## SELF-VERIFICATION CHECKLIST

- [ ] **V-S6-01**: Every approved candidate has context check
- [ ] **V-S6-02**: Every candidate has upset risk scored (not skipped)
- [ ] **V-S6-03**: ML picks checked against upset threshold — banned if score ≥ threshold
- [ ] **V-S6-04**: Paradox Rule applied (high risk → over bias noted)
- [ ] **V-S6-05**: Injury check done for EVERY candidate (source listed)
- [ ] **V-S6-06**: Fixture confirmation verified on Flashscore
- [ ] **V-S6-07**: Weather checked for outdoor sport picks
- [ ] **V-S6-08**: Competition context stated (what's at stake)
- [ ] **V-S6-09**: No candidate has only "N/A" for all context fields
- [ ] **V-S6-10**: Candidates with POSTPONED status removed from approved list

### PASS/FAIL GATE
- ALL checks pass → "S6 PASSED" → proceed to S7
