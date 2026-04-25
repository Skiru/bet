---
name: s4-tipsters
description: "STEP 4: Argument-based tipster deep-dive per candidate"
agent: bet-analyst
---

# STEP 4 — TIPSTER DEEP-DIVE

## INPUTS
- `betting/data/{date}_s3_deep_stats.md` — candidates with stats

## TASK
For EACH candidate, check ≥2 argument-based tipster sites. Read FULL WRITTEN ARGUMENTS — not just bare picks.

### TIPSTER SOURCES BY SPORT

| Sport | Primary | Secondary | Tertiary | Emergency |
|-------|---------|-----------|----------|-----------|
| Football (PL) | ZawodTyper | Typersi | Meczyki | OLBG |
| Football (INT) | PicksWise | BetIdeas | OLBG | Sportsgambler |
| Tennis | ZawodTyper | Typersi | PicksWise | OLBG |
| NBA/NHL/MLB | PicksWise | Covers | Sportsgambler | Google "[game] picks" |
| Esports | GosuGamers | BO3.gg | — | Google "[match] prediction" |
| Other | OLBG | Sportsgambler | ZawodTyper | Google "[event] tips" |

### BLOCKED SOURCES (NEVER attempt):
Forebet, FootySupertips, Windrawwin, BettingExpert, Protipster, Oddspedia, SportyTrader, Predictz, Trafiamy, Blogabet, HLTV tips

### SOURCE-SPECIFIC WARNINGS:
- **BetIdeas**: `/tips/` returns 404 or horse racing only. Use CATEGORY pages: `/tips/football`, `/corner-betting-tips`, `/btts-tips`, `/over-under-tips`.
- **Meczyki**: use `/typy-bukmacherskie` path. Daily page. Click individual match for tipster arguments.
- **ZawodTyper**: daily page at `/typy-dnia-[DD]-[month]-[weekday]/`. Scroll deeply (lazy-loaded). Use `/szukaj?q=[team]` for search.
- **Niche sports** (padel, speedway, TT): if no dedicated tipster page found, Google `"[event] prediction"` or `"[event] tips"` — record what you find.

### EXTRACTION PROTOCOL (for EACH tipster site per candidate):
1. Navigate to the site's daily tips page for the relevant sport
2. Search for the specific match/event
3. Find ALL tipsters who posted picks for this event
4. Read EACH tipster's FULL WRITTEN ARGUMENT
5. Record:
   - Site name
   - Tipster name/username
   - Their specific pick (market + line + odds)
   - Their argument (1-3 sentences summarizing the reasoning)
   - Stat/injury/tactical facts they cite
6. Calculate consensus: what % of tipsters agree with our S3 recommended market?

### OUTPUT FORMAT
Save to: `betting/data/{date}_s4_tipsters.md`

For each candidate:
```
## [Event Name] — Tipster Analysis

### Source 1: [Site Name]
| Tipster | Pick | Odds | Argument Summary |
|---------|------|------|-----------------|
| user123 | O2.5 goals | 1.85 | "Both teams scored in 4/5 recent H2H..." |
| expertX | BTTS Yes | 1.72 | "Arsenal conceded in 8 of last 10 away..." |

### Source 2: [Site Name]
| Tipster | Pick | Odds | Argument Summary |
...

### Consensus
- Direction alignment: X/Y tipsters agree with our analysis (Z%)
- Key supporting arguments: [bullets]
- Key OPPOSING arguments: [bullets — CRITICAL if any tipster argues against us]
- Consensus impact: +0.5 confidence / -1 confidence / investigate further
- New angles discovered: [any insight we missed in S3]
```

## SELF-VERIFICATION CHECKLIST

- [ ] **V-S4-01**: Every candidate has ≥2 tipster sites checked
- [ ] **V-S4-02**: Every tipster site check includes ACTUAL tipster arguments (not "no data")
- [ ] **V-S4-03**: If site returned empty → fallback site attempted
- [ ] **V-S4-04**: Consensus % calculated for each candidate
- [ ] **V-S4-05**: ALL opposing arguments recorded (tipster arguing AGAINST our pick)
- [ ] **V-S4-06**: Football picks: ZawodTyper AND at least one of Typersi/Meczyki checked
- [ ] **V-S4-07**: US sports: PicksWise or Covers checked
- [ ] **V-S4-08**: Esports: GosuGamers checked
- [ ] **V-S4-09**: No blocked sources attempted
- [ ] **V-S4-10**: New angles/insights recorded (injuries, tactical, weather, motivation)

### ERROR LOG
```
| Check | Status | Error | Fix |
|-------|--------|-------|-----|
```

### PASS/FAIL GATE
- ALL checks pass → "S4 PASSED" → proceed to S5
- ANY fail → fix → re-verify
