---
name: s1-scan
description: "STEP 1: Exhaustive 14-sport event scan with self-verification"
agent: bet-analyst
---

# STEP 1 — COMPLETE EVENT SCAN

## CONFIG
- **Date**: {{run_date}}
- **Session**: {{session}} (full/day/night/morning — controls event time window)
- **Event window**:
  - `full`: 06:00 run_date → 05:59 next day
  - `day`: 06:00 → 21:59 run_date
  - `night`: 22:00 run_date → 05:59 next day
  - `morning`: 06:00 → 14:59 run_date
  - If `betting_window_days` > 1 in config → extend window to cover N days
- **Bankroll**: see config/betting_config.json
- **14 sports**: football, tennis, basketball, hockey, baseball, volleyball, esports, snooker, darts, table_tennis, handball, mma, padel, speedway

## TASK
Build the Master Event List. SCAN ONLY — no analysis, no picks.

### EXECUTION (for each sport):
1. Open BetExplorer page for the sport
2. Click into EVERY active tournament/league — NOT just landing page
3. Count ALL matches scheduled in the betting-day window
4. Record: sport | tournament | match | kickoff CEST | odds (fav/dog) | source
5. Cross-validate with Flashscore or specialist source — note discrepancies
6. If source fails (403/empty) → try next in chain (see source-registry.md)

### SPORT ORDER + SOURCES

| # | Sport | Primary | Secondary | Specialist |
|---|-------|---------|-----------|------------|
| 1 | Football | BetExplorer /soccer/ | Flashscore | SoccerStats |
| 2 | Tennis | BetExplorer /tennis/ | Flashscore /tennis/ | ATP/WTA draws |
| 3 | Basketball | BetExplorer /basketball/ | ESPN NBA | Basketball-Ref |
| 4 | Hockey | BetExplorer /hockey/ | ESPN NHL | DailyFaceoff |
| 5 | Baseball | BetExplorer /baseball/ | ESPN MLB | BaseballSavant |
| 6 | Volleyball | BetExplorer /volleyball/ | Flashscore | — |
| 7 | Esports | BetExplorer /esports/ | HLTV (stats) | GosuGamers |
| 8 | Snooker | BetExplorer /snooker/ | Flashscore | WorldSnooker |
| 9 | Darts | BetExplorer /darts/ | Flashscore | PDC.tv |
| 10 | Handball | BetExplorer /handball/ | Flashscore | EHF |
| 11 | Table Tennis | BetExplorer /table-tennis/ | Flashscore | — |
| 12 | MMA | Tapology | UFC.com | BetExplorer |
| 13 | Padel | Sofascore /padel/ | BetExplorer | PremierPadel |
| 14 | Speedway | SpeedwayEkstraliga.pl | SportoweFakty | BetExplorer |

### OUTPUT FORMAT
Save to: `betting/data/{date}_s1_master_events.md`

```
# Master Event List — {date}

## Scan Completeness Table

| Sport | Source1 | Count1 | Source2 | Count2 | Discrepancy% | Tournaments Entered |
|-------|--------|--------|--------|--------|-------------|---------------------|
| Football | BE | ? | FS | ? | ?% | ? |
...all 14 rows...
| **TOTAL** | | **?** | | **?** | | **?** |

## Events by Sport

### 1. Football
| # | Tournament | Match | Kickoff CEST | Odds 1/X/2 | Source |
|---|-----------|-------|-------------|------------|--------|
...

### 2. Tennis
...repeat for all 14...

## Major Tournaments Flagged (≥4 matches today)
- ATP Madrid R32: 24 matches → FULL SLATE ANALYSIS REQUIRED
- ...

## Source Failures
| Source | Sport | Error | Fallback Used |
...
```

## SELF-VERIFICATION CHECKLIST (must ALL pass before proceeding)

Run after completing the scan. Mark each ✅ or ❌:

- [ ] **V-S1-01**: All 14 sports listed with event counts (0 = "NO EVENTS" with source checked)
- [ ] **V-S1-02**: Total unique events ≥ 50
- [ ] **V-S1-03**: At least 6 sports have events
- [ ] **V-S1-04**: Every sport checked from ≥2 sources
- [ ] **V-S1-05**: Discrepancy ≤30% between sources for every sport
- [ ] **V-S1-06**: Every tournament with ≥4 matches flagged for full screening
- [ ] **V-S1-07**: All events within betting-day window (06:00→05:59+1 CEST)
- [ ] **V-S1-08**: Source failures logged with fallback used
- [ ] **V-S1-09**: ALL major tournament full slates listed (ATP/WTA Masters, Grand Slam, World Championship, NBA/NHL Playoffs — every match, not just 2-3)
- [ ] **V-S1-10**: NBA/NHL/MLB full slate listed (not just featured games)
- [ ] **V-S1-11**: **§1.5 TIPSTER PRE-FETCH completed** — HTML snapshots exist in `betting/data/` for zawodtyper, typersi, sportsgambler, pickswise, betideas (run Playwright if missing). Tipster-sourced statistical-market candidates noted for shortlist inclusion.

### ERROR LOG
If any check fails, log here:
```
| Check | Status | Error Description | Fix Applied |
|-------|--------|-------------------|-------------|
```

### PASS/FAIL GATE
- ALL 11 checks pass → output "S1 PASSED" → proceed to S2
- ANY check fails → fix and re-verify → do NOT proceed until all pass
