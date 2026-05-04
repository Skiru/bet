---
name: s2-shortlist
description: "STEP 2: Build ranked shortlist of 50-100 candidates using build_shortlist.py + agent refinement"
agent: bet-scanner
---

# STEP 2 — SHORTLIST FILTERING

## INPUTS
- `betting/data/{date}_s1_master_events.md` — from STEP 1
- **Market matrix** (PRIMARY): `betting/data/market_matrix_{date}.json` + `betting/data/decision_matrix_{date}.md` — consolidated view of ALL events with odds from all sources and safety scores, sorted by quality. If available, use this as the primary shortlist input instead of raw S1 output.
- **Analysis pool**: `betting/data/analysis_pool_{date}.json` — events pre-analyzed via API stats with safety scores and market rankings. Events with `data_quality: FULL` or `PARTIAL` should be PRIORITIZED in shortlist (they already have L10 form, H2H, and safety scores computed).
- **Session**: {{session}} — controls event time window filter
- **Event window**: resolved from session (full/day/night/morning) + betting_window_days in config

## TASK

**Automated shortlist generation (run first):**
```bash
python3 scripts/build_shortlist.py --date {date} --top 100 --stats-first
```
This produces `{date}_s2_shortlist.md` + `{date}_s2_shortlist.json` with 100 ranked candidates.

Then review and refine the auto-generated shortlist:

Filter the Master Event List to a shortlist of 50-100 candidates for deep analysis.

### REMOVAL CRITERIA (apply in order):
1. **Outside window**: kickoff not in the resolved session event window
2. **No Tier A source**: event has no BetExplorer/Flashscore/OddsPortal coverage
3. **Too close to kickoff**: <2h from analysis time
4. **Already started**: any event already in-play → REMOVE
5. **Exhibition/friendly**: unless odds available and Tier A coverage exists
6. **ITF tennis**: skip ALL ITF events (unreliable)
7. **Random/unverifiable**: unranked esports, regional table tennis without odds

### EARLY BETCLIC MARKET CHECK
For niche sports (volleyball, table tennis, padel, speedway): check Betclic market availability BEFORE deep analysis. If market doesn't exist on Betclic → don't waste analysis time.

### SCREENING CRITERIA (for remaining events):
For each event, assess:
1. **Statistical market available?** (corners, cards, totals, handicaps, frames, etc.)
   - YES → higher priority
   - Only 1X2/ML → lower priority (ML is LAST RESORT)
2. **Odds in preferred range?** (1.30-3.50 for individual legs)
3. **Major tournament?** → flag for mandatory full-slate analysis
4. **Tier A data quality**: form, H2H, stats available?

### SPORT DIVERSITY GATE
- Shortlist MUST include events from ≥8 sports (≥5 sports minimum in final picks)
- Football ≤50% of shortlist
- If <8 sports → go back to S1, scan missing sports deeper

### OUTPUT FORMAT
Save to: `betting/data/{date}_s2_shortlist.md`

```
# Shortlist — {date}

## Summary
- Total events scanned: X (from S1)
- Events removed: Y
- Shortlisted: Z events from N sports
- Sport diversity: [list sports with counts]

## Removal Log
| # | Event | Sport | Removal Reason |
|---|-------|-------|---------------|
...

## Shortlisted Candidates

### Tier 1 — Statistical markets available (PRIORITY)
| # | Sport | Event | Tournament | Kickoff | Market Opportunity | Odds Range |
|---|-------|-------|-----------|---------|-------------------|------------|
...

### Tier 2 — ML/basic markets only (LOWER PRIORITY)
| # | Sport | Event | Tournament | Kickoff | Market Opportunity | Odds Range |
|---|-------|-------|-----------|---------|-------------------|------------|
...

## Major Tournaments Requiring Full Screening
- ATP Madrid R32: X matches shortlisted / Y total
- WTA Madrid R32: X/Y
- EPL Round 35: X/Y
- ...
```

## SELF-VERIFICATION CHECKLIST

- [ ] **V-S2-01**: Shortlist has 50-100 events
- [ ] **V-S2-02**: ≥8 sports represented in shortlist (≥5 sports minimum in final picks)
- [ ] **V-S2-03**: Football ≤50% of shortlist
- [ ] **V-S2-04**: All removed events have valid removal reason
- [ ] **V-S2-05**: No events outside betting-day window remain
- [ ] **V-S2-06**: Every major tournament (≥4 matches) has ALL matches screened
- [ ] **V-S2-07**: Tier 1 (statistical markets) candidates > Tier 2 (ML only)
- [ ] **V-S2-08**: No ITF tennis in shortlist
- [ ] **V-S2-09**: Every shortlisted event has odds recorded
- [ ] **V-S2-10**: Sport counts tallied and verified
- [ ] **V-S2-11**: Tipster-sourced statistical-market candidates from §1.5 pre-fetch included in shortlist (if any qualify)

### ERROR LOG
```
| Check | Status | Error | Fix |
|-------|--------|-------|-----|
```

### PASS/FAIL GATE
- ALL 11 checks pass → "S2 PASSED" → proceed to S3
- ANY fail → fix → re-verify
