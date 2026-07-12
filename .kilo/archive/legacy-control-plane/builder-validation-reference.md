# Builder Validation Reference

This document contains detailed validation queries, market tables, and patterns used by bet-builder during S8 coupon construction. The main prompt references this file — load it before presenting any coupon.

---

## V1 — TEAM IDENTITY CHECK (use sqlite_read_query)

```sql
-- For EACH pick: verify team names match the fixture
SELECT f.id, th.name as home, ta.name as away
FROM fixtures f JOIN teams th ON f.home_team_id = th.id JOIN teams ta ON f.away_team_id = ta.id
WHERE f.id = ?;
-- Compare: is the team you described actually HOME or AWAY in this fixture?
```

- If you wrote "Tottenham fouls" but Tottenham is AWAY → check if you used HOME team stats for AWAY team
- If you wrote "Player A Games O12.5" → verify Player A IS the player in that slot

## V2 — HALLUCINATION CHECK (use sqlite_read_query for EACH stat)

```sql
-- For EACH stat you cited: get the ACTUAL L10 values
SELECT tf.value, tf.match_date FROM team_form tf
WHERE tf.team_id = ? AND tf.stat_key = ?
ORDER BY tf.match_date DESC LIMIT 10;
```

- Print the actual values returned
- Compare to what you wrote in the coupon narrative
- If they differ → use the DB values, delete what you "remembered"
- If query returns 0 rows → mark as "UNVERIFIED DATA" in the pick

## V3 — HIT RATE vs AVERAGE CHECK (compute from actual L10)

**For OVER picks:**
```sql
-- Count how many L10 values ACTUALLY exceed the line
-- Replace {line} with the numeric line value (e.g., 87.5)
SELECT
  COUNT(*) as total,
  SUM(CASE WHEN CAST(value AS REAL) > {line} THEN 1 ELSE 0 END) as hits
FROM (
  SELECT tf.value FROM team_form tf
  WHERE tf.team_id = ? AND tf.stat_key = ?
  ORDER BY tf.match_date DESC LIMIT 10
);
```

**For UNDER picks:**
```sql
-- For UNDER direction: count values BELOW the line
SELECT
  COUNT(*) as total,
  SUM(CASE WHEN CAST(value AS REAL) < {line} THEN 1 ELSE 0 END) as hits
FROM (
  SELECT tf.value FROM team_form tf
  WHERE tf.team_id = ? AND tf.stat_key = ?
  ORDER BY tf.match_date DESC LIMIT 10
);
```

- If hits/total < 6/10 (60%) → the pick is MARGINAL, not strong
- NEVER say "strong edge" when hit rate < 60%
- Example: avg=87.7 but only 6/10 > 87.5 → MARGINAL (60%), not "consistently hitting over"
- **CRITICAL:** Use the correct direction! OVER → count > line. UNDER → count < line.

## V4 — LINE vs BETCLIC REALITY

```sql
-- Check what line Betclic actually offers
SELECT oh.line, oh.over_odds, oh.under_odds
FROM odds_history oh
WHERE oh.fixture_id = ? AND oh.market_type = ? AND oh.source LIKE '%betclic%'
ORDER BY oh.fetched_at DESC LIMIT 1;
```

- If Betclic's line differs >20% from our analysis line → REJECT the pick
- If no Betclic odds found → mark as "VERIFY ON APP"
- **Edge case:** If Betclic offers a DIFFERENT line that's still favorable (e.g., we analyzed O9.5, Betclic offers O8.5) → the pick is STRONGER, re-calculate hit rate at Betclic's line

## V5 — HARD REJECT RULES (from betting-mistakes-rules.instructions.md)

Run through EACH pick against ALL hard reject rules:
- TENNIS_SETS_001: O3.5 sets conditions met?
- TENNIS_GAMES_001: Underdog games over conditions?
- GOALS_001: Combined L5 > line + 0.5?
- CORNERS_CONTEXT_001: Dead rubber penalty applied?
- CORRELATION_001: Same pick in 2+ coupons? → INSTANT REJECT
- SAFETY_FLOOR_001: safety < 0.15? → INSTANT REJECT

### EXECUTION ORDER (non-negotiable):

1. Run V1 queries → fix team errors
2. Run V2 queries → delete unverifiable claims
3. Run V3 queries → downgrade marginal picks
4. Run V4 queries → remove line-mismatched picks
5. Run V5 checks → apply hard reject rules
6. ONLY THEN present the coupon to orchestrator

---

## BETCLIC PL MARKET REALITY

Betclic Poland does NOT offer corners/fouls/shots/cards for most events. Only TOP leagues sometimes have them.

| Market | Availability on Betclic PL |
|--------|---------------------------|
| Goals O/U (total + team) | ✅ Always available |
| BTTS (both teams to score) | ✅ Always available |
| Handicap / Asian Handicap | ✅ Always available |
| 1X2 / Double Chance | ✅ Always available |
| Player props (scorers, SOT OPTA) | ✅ Major leagues |
| Red Card yes/no | ✅ Most events |
| Corners O/U | ⚠️ ONLY EPL, LaLiga, Bundesliga, Serie A, Ligue 1 |
| Fouls O/U | ❌ NOT available on Betclic PL |
| Team Shots O/U | ❌ NOT available on Betclic PL |
| Cards Total O/U | ❌ NOT available on Betclic PL |

**Rule:** When building coupons with stat-market picks:
1. Check `betclic_market_validation` sidecar for confirmed availability
2. If market is CONFIRMED unavailable → move pick to Extended Pool (R3 compliance)
3. If market availability is UNKNOWN (null) → keep but FLAG for user verification
4. Pivot strategy: when corners/fouls unavailable → apply same statistical rigor to Goals O/U, BTTS, Handicap

---

## LEAGUE-SPECIFIC LINES (CRITICAL for basketball)

NEVER use a generic line across different league levels:

| League | Total Points Range | Default Line |
|--------|:---:|:---:|
| NBA | 210-235 | 220.5 |
| Euroleague / ACB / BSL | 145-170 | 157.5 |
| Brazilian NBB | 155-168 | 160.5 |
| Women's WNBA | 155-175 | 165.5 |
| Women's European | 135-160 | 148.5 |
| Minor leagues (Paraguay, Venezuela, TBL) | 150-175 | 162.5 |

**If Betclic's balanced line differs >20% from our pipeline line → REJECT the pick.**
**Query:** `SELECT line FROM odds_history WHERE fixture_id = ? AND market_type = 'totals' ORDER BY fetched_at DESC LIMIT 1`

---

## PROVEN WINNING PATTERNS (from settled results)

| Pattern | Signal | Historical Hit Rate |
|---------|--------|:---:|
| Team corners OVER | L5 > line + 1.0, rising trend | **87%** |
| Team fouls OVER | L5 > line + 0.5, physical style | **77%** |
| SOT OVER (reasonable line) | Combined L5 > line + 1.5 | **70%** |
| Under 2.5 goals | Combined L5 < 1.8, both teams low-scoring | **74%** |
| Stat market with 3-way alignment | L10+H2H+L5 all support direction | **72%** |

| Anti-Pattern | Signal | Historical Loss Rate |
|--------------|--------|:---:|
| Same pick in 2+ coupons | Repetition across portfolio | **100% of catastrophic days** |
| avg ≈ line (zero margin) | L10_avg within ±0.5 of line | **coin flip — no edge** |
| Over X when combined L5 < X | Data contradicts direction | **72% loss rate** |
| Lower league ML >1.40 | No data = pure gamble | **68% loss rate** |
| Dead rubber stat market | Motivation penalty ignored | **60% loss rate** |

---

## Hard Reject at Construction Stage

| Rule | Condition | Action |
|------|-----------|--------|
| CORRELATION_001 | Same pick in 2+ coupons | Block — **#1 cause of catastrophic days** |
| SAFETY_FLOOR_001 | safety < 0.15 | INSTANT REJECT — zero edge |
| SAFETY_FLOOR_002 | safety < 0.30 in core coupon | REJECT from core — extend only |
| KICKOFF_GUARD_001 | kickoff ≤ NOW | REMOVE — already started |
| MAX_LEGS | > 4 legs per coupon | Split — AKO5/7 = 0 wins historically |
| Same market concentration | > 3 picks from same market type | Distribute across coupons |
| Event reuse cap | Event in > 5 coupons total | Block |
| DIRECTION_CONFLICT | avg ≈ line AND L5 contradicts direction | REJECT or FLIP |
| BETCLIC_UNAVAIL | market confirmed unavailable on Betclic | Move to Extended (R3) |
| LEAGUE_LINE_001 | Our line vs Betclic line >20% difference | REJECT — line calibration broken |

---

## SYNTHETIC_RESCUE_001 — High-Consistency Rescue Protocol

When a pick from EXTENDED pool has:
- L5 hit rate ≥ 80% (4/5 or 5/5)
- Clear directional signal (not marginal)
- Any safety_score (even low due to synthetic penalty)

→ **RESCUE to core coupon consideration.** L5 consistency beats data source completeness.
Evidence: 2026-05-26 Waltert L5 5/5 was best pick of the day, but got stuck in EXTENDED.

---

## Per-Pick Narrative Format (REQUIRED — Source Fusion)

Each pick in the coupon MUST have ALL THREE legs of evidence:
- **WHY (Tipster):** If tipster covered this — their ARGUMENT (not just "agrees"). If no tipster → "brak wsparcia tipsterów"
- **DATA (Stats):** L10/L5/H2H specific values supporting direction. Include HIT RATE not just average!
- **CONTEXT (Web):** Injuries, motivation, standings position, form, referee/weather. From brave web search.
- **RISK:** Specific bear case — the ONE thing that could break this edge
- **BETCLIC:** Market confirmed available? YES (confirmed) / UNKNOWN (verify!) / NO (extended only)
- **PROBABILITY:** P(hit) from probability engine, fair odds, EV at offered odds

Example of a GOOD per-pick narrative:
```
🎯 Tottenham Fouls O12.5 @1.85
WHY: Sportsgambler explicit tip — cites physical derby pressure + new ref tendency
DATA: L10=13.6, L5=14.0 (rising!), H2H=13.8. Hit rate: 9/10 L10, 5/5 L5
CONTEXT: North London Derby, both teams mid-table, Postecoglou press = systematic fouls (Reuters)
RISK: If Spurs rest starters midweek, intensity drops. But L5 is POST-rotation and still 14.0.
BETCLIC: ❌ Fouls NOT available on Betclic PL — MOVED TO EXTENDED
P(hit): 0.82, Fair odds: 1.22, EV at 1.85: +0.52
```

---

## Portfolio Damage Test (MANDATORY before final presentation)

For EACH coupon, answer:
1. If the WEAKEST leg fails — what % of daily budget is lost?
2. If a SINGLE EVENT loses across multiple coupons — how many coupons die?
3. Max allowed: 1 event killing max 1 core coupon + 2 combos (total max 30% budget)
4. If damage exceeds this → RESTRUCTURE (swap the repeated pick out of one coupon)

---

## Key DB Queries for Coupon Building

```sql
-- Load gate-approved picks (batch all at once)
SELECT fixture_id, status, best_market_name, safety_score, hit_rate_l10,
       advisory_tier, rejection_reason
FROM gate_results WHERE betting_date = ? AND status IN ('APPROVED', 'EXTENDED');

-- Verify Betclic availability for multiple markets (batch)
SELECT fixture_id, confirmed_available, market_type
FROM betclic_market_validation
WHERE fixture_id IN (?, ?, ?) AND market_type IN (?, ?, ?);

-- Get probability engine output
SELECT fixture_id, market_name, p_hit, fair_odds, ev_at_offered, model_type
FROM analysis_results WHERE fixture_id IN (?, ?, ?) AND betting_date = ?;

-- Check if events are started (batch)
SELECT id, kickoff FROM fixtures
WHERE id IN (?, ?, ?) AND kickoff > datetime('now');

-- Tipster support for picks
SELECT fixture_id, source, market, reasoning FROM tipster_picks
WHERE betting_date = ? AND fixture_id IN (?, ?, ?);
```

**Batching rule:** Use `WHERE id IN (...)` to check multiple picks in a single query. Never run one query per pick — that wastes tool call budget.
