---
name: s6-context-upset
description: "STEP 6: Context verification + Upset Risk Assessment per candidate"
agent: bet-analyst
---

# STEP 6 — CONTEXT + UPSET RISK

## INPUTS
- `betting/data/{date}_s5_odds_ev.md` — approved candidates with EV > 0

## TASK
For EACH approved candidate: verify context factors, score upset risk, apply Paradox Rule.

### PER-CANDIDATE CONTEXT CHECK:
1. **Fixture confirmed?** Not postponed/cancelled? (Flashscore live)
2. **Key absences**: injuries, suspensions, rest — VERIFY on day of analysis
3. **Competition context**: relegation, dead rubber, cup rotation, playoff elimination
4. **Fixture congestion**: <72h since last match?
5. **Weather**: outdoor sports — rain/wind impact on corners/goals/play style
6. **Referee**: for cards/fouls markets — referee stats if available
7. **Motivation**: what's at stake for each team/player?

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

**Tennis** (threshold ≥4, max 12):
- [ ] Surface mismatch (0-2) — favorite's surface win% 10%+ lower than overall?
- [ ] Rising underdog (0-2) — career-high ranking? recent title? NextGen?
- [ ] Giant-killer history (0-1) — top-20 scalps in last 12 months?
- [ ] Age/trajectory (0-1) — underdog ≤22 breakthrough, favorite ≥30 declining?
- [ ] Favorite tournament history (0-1) — never past QF here?
- [ ] Qualifier match fitness (0-0.5) — underdog through qualifying?
- [ ] First H2H meeting (0-0.5) — unknown matchup dynamics
- [ ] Serve dependency on slow surface (0-1) — big server on clay?
- [ ] Altitude factor (0-0.5) — Madrid 660m, thin air
- [ ] Previous round fatigue (0-0.5) — 3h+ previous round?
- [ ] Late-career complacency (0-0.5) — 28+yo in R1/R2?
- [ ] Return game strength (0-0.5) — underdog high RPW% on surface?
- [ ] Sharp money signal (0-0.5) — line moving toward underdog?
- [ ] Draw section look-ahead (0-0.5) — favorite might look past opponent?

**Football** (threshold ≥4, max 8):
- [ ] Derby / rivalry match
- [ ] Cup rotation (CL/EL within 5 days)
- [ ] Dead rubber (nothing to play for)
- [ ] International break return
- [ ] Key player suspended/injured
- [ ] Synthetic/unusual pitch
- [ ] Manager recently fired/appointed
- [ ] Travel fatigue (long away trip)

**Basketball** (threshold ≥3, max 6):
- [ ] B2B (2nd night of back-to-back)
- [ ] Load management (stars rested)
- [ ] Tank mode (eliminated from playoff contention)
- [ ] Elimination game (desperation)
- [ ] Travel fatigue (coast-to-coast)
- [ ] Altitude (Denver home)

**Hockey** (threshold ≥3, max 6):
- [ ] Backup goalie starting
- [ ] B2B (2nd night)
- [ ] Down 0-3 in series (sweep risk)
- [ ] Goalie unconfirmed at analysis time
- [ ] Travel (3rd road game in row)
- [ ] Playoff intensity mismatch

**Baseball** (threshold ≥3, max 6):
- [ ] Bullpen game (no true starter)
- [ ] MLB debut pitcher
- [ ] Wind blowing out (inflates totals unpredictably)
- [ ] Day game after night game
- [ ] Overworked bullpen (high innings last 3 days)
- [ ] Lineup not confirmed (key bats may sit)

**Volleyball** (threshold ≥3, max 6):
- [ ] Playoff clinched (nothing to play for)
- [ ] 5th set to 15 (high variance)
- [ ] Home crowd >70% (pressure on visitors)
- [ ] Key setter/libero absent
- [ ] Travel fatigue (international)
- [ ] Rotation for European midweek

**Esports** (threshold ≥2, max 5):
- [ ] Stand-in player (roster change)
- [ ] New patch <2 weeks (meta not settled)
- [ ] Online vs LAN (different performance)
- [ ] BO1 (map variance huge — upsets 2x more likely)
- [ ] Map pool mismatch (opponent has clear map advantage)

**Snooker** (threshold ≥2, max 5):
- [ ] Long-format fatigue (multi-session match)
- [ ] Morning session (slower starts common)
- [ ] Century frequency mismatch
- [ ] Crucible/venue pressure (R1 WC upsets)
- [ ] Player on losing streak >3

**Darts** (threshold ≥2, max 5):
- [ ] Sets vs legs format (affects dynamics)
- [ ] Premier League vs ranking event (different)
- [ ] 180s power matchup imbalance
- [ ] Floor event (upsets more common)
- [ ] Checkout % collapse in recent matches

**Handball** (threshold ≥3, max 6):
- [ ] European week rotation (resting for CL)
- [ ] 7m specialist absent
- [ ] Starting GK injured
- [ ] Derby (physical, lower scoring)
- [ ] Fixture congestion
- [ ] Home advantage extreme (60-65%)

**Table Tennis** (threshold ≥2, max 5):
- [ ] Division gap in cup (lower vs higher)
- [ ] BO5 vs BO7 format
- [ ] Withdrawal history (frequent retirements)
- [ ] Style matchup (chopper vs attacker)
- [ ] Multiple matches same day (fatigue)

**MMA** (threshold ≥3, max 6):
- [ ] Late opponent change (<2 weeks)
- [ ] Failed weight cut (missed weight)
- [ ] Layoff >1 year (ring rust)
- [ ] Reach advantage >4 inches
- [ ] Stylistic nightmare (wrestler vs pure striker)
- [ ] Camp change (new gym/coach)

**Padel** (threshold ≥3, max 6):
- [ ] New pair <3 events (no chemistry data)
- [ ] Indoor vs outdoor change (wind impact)
- [ ] FIP ranking gap <500 (too close to predict)
- [ ] Travel fatigue (different continent)
- [ ] Tournament tier change (Major vs P2)
- [ ] Fatigue (3-set QF yesterday)

**Speedway** (threshold ≥3, max 6):
- [ ] Rain/wet track conditions
- [ ] Key rider's track record poor at this venue
- [ ] Junior rider rule (weak U24 contributions)
- [ ] Guest rider unfamiliar with track
- [ ] Early season (riders finding form)
- [ ] Championship/relegation stakes

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
