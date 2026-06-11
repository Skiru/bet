# Position Management Rules

> Magee's Stage 5: Pre-match position management for manual Betclic execution.
> Since Betclic lacks API, these rules guide human execution timing and abandon decisions.

---

## Execution Timing

### Timestamp Tracking
- Each pick has `ev_calculated_at` timestamp from S7 gate
- **STALE WARNING**: >2 hours since EV calculation
- **STALE REJECT**: >4 hours since EV calculation

### Drift Tolerance Rules
| Condition | Action |
|-----------|--------|
| Odds drift >8% from approval price | **FLAG** — re-verify |
| Odds drift >15% from approval price | **DO NOT PLACE** |
| Odds improved >5% | Pass-through (favorable drift) |

---

## Pre-Match Exit Rules

### Hard Abandon (DO NOT PLACE)
1. **Injury confirmed <6h before kickoff** — Key player out (starter in last 5 games)
2. **Lineup different from assumed** — >2 starters missing from expected XI
3. **Weather change (outdoor)** — Rain → Under bias, Wind >15mph → Corners volatility
4. **Odds removed from Betclic** — Market no longer available

### Soft Abandon (VERIFY BEFORE PLACING)
1. **Injury question mark** — Player listed doubtful, not confirmed out
2. **Manager change** — New manager debut (tactics uncertain)
3. **Weather threat** — Forecast calls for adverse conditions
4. **Lineup hint differs** — Press conference suggests rotation

### Verify-and-Proceed
1. **Knockout/final context** — Different motivation from league games
2. ** derby/rivalry** — Emotional factors override stats
3. **End-of-season** — Dead rubber vs relegation battle

---

## Market-Specific Exit Triggers

### Football
| Market | Abandon Trigger |
|--------|-----------------|
| Total Goals | Star striker confirmed out (Team A) |
| Corners | Starting RB/LB out (reduced width) |
| Cards | VAR referee assigned (lower card rate) |
| Fouls | High-stakes rivalry (intensity up) |

### Tennis
| Market | Abandon Trigger |
|--------|-----------------|
| Total Games | Retirement in previous round |
| Sets O/U | Walkover warning (opponent injured) |
| Player Games | Surface specialist vs all-rounder |

### Basketball
| Market | Abandon Trigger |
|--------|-----------------|
| Total Points | Star player game-time decision |
| Team Points | Back-to-back (fatigue factor) |

---

## Drift Decision Tree

```
EV calculated at T0
User places bet at T1

Delta = T1 - T0

if Delta > 4 hours:
    REJECT — recalculate EV
elif Delta > 2 hours:
    WARN — verify current odds
    if odds drifted > 8%:
        REJECT — edge may have disappeared
    else:
        PROCEED — note drift
else:
    PROCEED — acceptable timing
```

---

## Execution Checklist

Before placing each bet in Betclic:

- [ ] **Time Check**: EV calculated <2h ago? (If >4h, recalculate)
- [ ] **Odds Check**: Betclic odds match expected? (If >15% drift, ABANDON)
- [ ] **Lineup Check**: No key players missing? (Check Betclic lineup info)
- [ ] **Weather Check**: No adverse conditions? (Rain/wind for outdoor)
- [ ] **Market Available**: Betclic still offering this market?
- [ ] **Line Match**: Line in Betclic matches analyzed line? (±0.25 tolerance)

---

## Post-Placement Documentation

After placing bet:

1. Record `odds_at_placement` (actual odds obtained)
2. Record `placed_at` timestamp
3. Calculate `execution_drift` vs calculated odds
4. If drift >8%, flag for post-mortem review

---

## Rationale

**Why timing matters (Magee Ch.5)**:
- Oddsmakers adjust continuously based on betting action and news
- A 2-hour gap between EV calculation and execution is the threshold for
  meaningful line movement in liquid markets
- >4 hours = information asymmetry risk (someone knows something you don't)

**Why abandon triggers matter**:
- Statistical edge is calculated from historical data
- Real-time news (injuries, weather, motivation) can invalidate the assumption
  that past performance predicts future results
- "The best bet you don't place is the one you avoid" — Magee

---

## Implementation

These rules are enforced at:
- S7 gate (timestamp injection)
- S8 coupon builder (timing warnings)
- Manual Betclic verification (execution checklist)
