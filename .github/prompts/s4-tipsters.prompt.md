---
name: s4-tipsters
description: "STEP 4: Argument-based tipster deep-dive per candidate"
agent: bet-scout
---

# STEP 4 — TIPSTER DEEP-DIVE

## INPUTS
- `betting/data/{date}_s3_deep_stats.md` — candidates with stats

## TASK
For EACH candidate, check ≥2 argument-based tipster sites. Read FULL WRITTEN ARGUMENTS — not just bare picks.

### §1.5 PRE-FETCHED HTML (MANDATORY — use these FIRST)

Before web-fetching any tipster sites, check if Playwright pre-fetched HTML exists from STEP 1:
- `betting/data/zawodtyper.pl/` — latest `.html` file for today
- `betting/data/typersi.pl/` — latest `.html` file
- `betting/data/sportsgambler.com/` — latest `.html` file
- `betting/data/pickswise.com/` — latest `.html` file
- `betting/data/betideas.com/` — latest `.html` file

**Parse the pre-fetched HTML** with BeautifulSoup to extract tipster entries matching each candidate. This gives you FULL tipster arguments (not the truncated web-fetch summaries). If pre-fetched HTML is missing or stale (>12h old), fetch now:
```bash
python3 scripts/fetch_with_playwright.py "https://zawodtyper.pl/typy-dnia-[DD]-[month]-[weekday]/"
```

### §4.3 TIPSTER-SOURCED WATCHLIST PROMOTION (MANDATORY)

After processing all candidates, scan the pre-fetched tipster HTML for picks NOT in your shortlist. Any tipster pick that:
1. Targets a **statistical market** (corners, cards, fouls, totals, games, frames — NOT ML)
2. Has **argument-backed reasoning** citing stats (H2H data, historical line coverage, etc.)
3. Falls within today's betting window

→ **Add to LISTA OBSERWACYJNA (Watchlist)** with FULL tipster argument, tipster accuracy %, cited data, and promotion criteria.

### TIPSTER SOURCES BY SPORT

| Sport | Primary | Secondary | Tertiary | Emergency |
|-------|---------|-----------|----------|-----------|
| Football (PL) | ZawodTyper | Typersi | Meczyki | OLBG |
| Football (INT) | PicksWise | BetIdeas | OLBG | Sportsgambler |
| Tennis | ZawodTyper | Typersi | PicksWise | Tipstrr |
| NBA/NHL/MLB | PicksWise | Covers | Sportsgambler | Tipstrr |
| Esports | GosuGamers | BO3.gg | Tipstrr | Google "[match] prediction" |
| Other | OLBG | Sportsgambler | Tipstrr | Google "[event] tips" |

**Tipstrr** (tipstrr.com): verified tipster platform with tracked ROI. Use as secondary/tertiary for ANY sport — search for tipsters covering the specific sport or league.

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

**CRITICAL: The orchestrator will structurally verify this output. Missing sections = step sent back for fix.**

**The file MUST start with the TIPSTER COVERAGE SUMMARY TABLE (before per-candidate sections):**
```
# Tipster Analysis — {date}

## Tipster Coverage Summary (orchestrator reads this table to verify depth)
| # | Event | Sport | Sites Checked | Sites With Arguments | Best Consensus % | Tipster-Sourced Stat Pick? | Status |
|---|-------|-------|---------------|---------------------|-----------------|---------------------------|--------|
| 1 | [event] | [sport] | ZT, Typersi, OLBG | ZT(3 tipsters), OLBG(2) | 80% agree | No | ✅ OK |
| 2 | [event] | [sport] | PicksWise, SG | PicksWise(1 expert) | 100% agree | Yes: O9.5 CK @1.75 | ⚠️ 1-source |
| 3 | [event] | [sport] | ZT, PW, SG | ZT(2), PW(1), SG(1) | 50% split | No | ✅ OK |
...
| **TOTAL** | **X candidates** | | **avg X.X sites/cand** | **avg X.X with args** | | **X stat picks found** | **X% ≥2-source** |
```

**Status codes:** ✅ OK (≥2 sites with args) / ⚠️ 1-source (only 1 site found args) / ❌ TIPSTER-BLIND (0 sites, −0.5 conf, no LR) / 🔄 RETRY (fallback chain not exhausted)

Then per-candidate sections:

For each candidate:
```
## [Event Name] — Tipster Analysis

### Source 1: [Site Name] (via §1.5 pre-fetch / fresh fetch)
| Tipster | Pick | Odds | Argument Summary |
|---------|------|------|-----------------|
| user123 | O2.5 goals | 1.85 | "Both teams scored in 4/5 recent H2H..." |
| expertX | BTTS Yes | 1.72 | "Arsenal conceded in 8 of last 10 away..." |

### Source 2: [Site Name]
| Tipster | Pick | Odds | Argument Summary |
...

### Source 3 (if available): [Site Name]
...

### Consensus
- Direction alignment: X/Y tipsters agree with our S3 analysis (Z%)
- Key supporting arguments: [bullets — specific facts/stats cited by tipsters]
- Key OPPOSING arguments: [bullets — CRITICAL: any tipster who argues AGAINST our pick with data]
- Consensus impact: +0.5 confidence / −1 confidence / neutral / investigate further
- New angles discovered: [any insight not in S3 — injuries, tactics, weather, motivation]
- **Statistical market picks from tipsters**: [list any tipster picks on stat markets we didn't consider]
```

### §4.3 WATCHLIST PROMOTION SECTION (MANDATORY — at end of file)
```
## §4.3 Tipster-Sourced Watchlist Candidates

### Reviewed Tipster Stat-Market Picks Not in Shortlist
| # | Tipster | Site | Event | Market | Odds | Argument | Accuracy % | In Window? | On Betclic? | Promoted? |
|---|---------|------|-------|--------|------|----------|-----------|-----------|------------|-----------|
| 1 | user456 | ZT | [event] | O4.5 CK | 1.65 | "Team X avg 6.2 CK/match..." | 62% | Yes | Likely | ✅ → Watchlist |
| 2 | tipstrr_X | Tipstrr | [event] | O180s 4.5 | 1.80 | "Both avg >3 180s..." | 58% | Yes | Unknown | ❌ — no stat backup |
...

### Promoted to LISTA OBSERWACYJNA
[List events promoted with full tipster argument, accuracy, cited data, and promotion criteria]
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
- [ ] **V-S4-11**: §1.5 pre-fetched HTML was used for tipster analysis (not just web-fetch summaries)
- [ ] **V-S4-12**: §4.3 watchlist promotion completed — all tipster statistical-market picks reviewed, qualifying ones added to LISTA OBSERWACYJNA

### ERROR LOG
```
| Check | Status | Error | Fix |
|-------|--------|-------|-----|
```

### PASS/FAIL GATE
- ALL checks pass → "S4 PASSED" → proceed to S5
- ANY fail → fix → re-verify
