---
agent: bet-orchestrator
description: "Audit and improve scan, odds scraping, and tipster pipeline scripts for reliability"
---

# Audit: Scan, Odds & Tipster Pipeline Quality

## Context

The enrichment pipeline (`data_enrichment_agent.py`) was recently completely rewritten because it was using broken inline scraping while proper API clients existed unused. We now need to verify that the **scan**, **odds**, and **tipster** subsystems don't have similar problems.

## Your Task

Perform a thorough technical audit of these 3 subsystems. For each one:
1. **Read the code** — understand inputs, outputs, data flow
2. **Test accessibility** — are source URLs still reachable? Do APIs respond?
3. **Check data quality** — does the script produce usable output or garbage?
4. **Identify architectural issues** — dead code, duplicate implementations, broken fallbacks
5. **Verify DB integration** — does data actually reach `betting.db` correctly?

## Subsystem 1: Event Discovery (Scan)

**Entry point:** `scripts/discover_events.py` → `src/bet/discovery/`
**Module structure:** `coordinator.py`, `dedup.py`, `models.py`, `repository.py`, `sources/`
**Dedup:** Discovery uses `DeduplicationEngine` (threshold 85, ±2h kickoff window) for cross-source merging. Downstream pipeline scripts use `is_same_event()`/`names_match()` from `src/bet/utils.py` (threshold 70, multi-strategy).
**Sources:** Odds-API.io (primary, all 5 sports), The-Odds-API (secondary, 4 sports w/ odds), API-Football (tertiary, football). SofaScore adapter disabled (403).
**DB tables written:** `fixtures`, `fixture_sources`, `scan_results`, `teams`, `competitions`, `sports`

### Audit checklist:
- [ ] Run `PYTHONPATH=src .venv/bin/python3 scripts/discover_events.py --date $(date +%Y-%m-%d) --verbose` — does it produce fixtures for all 5 sports?
- [ ] Check each source adapter in `src/bet/discovery/sources/` — are APIs still responding?
- [ ] Verify deduplication logic — are duplicates between sources properly merged?
- [ ] Check tournament protection (R7) — do Grand Slams, Champions League etc. always appear?
- [ ] Verify fixture count sanity: expect 800-1000+ per day across all sports
- [ ] Check if any source returns 403/404/empty consistently

## Subsystem 2: Odds Pipeline

**Scripts:**
- `scripts/fetch_odds_api.py` — Odds-API.io fetcher (5000 req/hour, 265 bookmakers)
- `scripts/daily_odds_warmup.py` — Playwright stealth HTML dump from Betclic.pl
- `scripts/odds_evaluator.py` — EV computation from DB + JSON snapshots
- `scripts/fetch_espn_odds.py` — ESPN odds extraction (American → decimal)

**DB tables:** `odds_history` (fixture_id, bookmaker, market, selection, odds, line, fetched_at)
**JSON outputs:** `odds_api_snapshot.json`, `odds_api_summary.csv`

### Audit checklist:
- [ ] Run `python3 scripts/fetch_odds_api.py` — does it produce valid snapshot?
- [ ] Check Odds-API.io rate limits — are we within 5000 req/hour?
- [ ] Run `daily_odds_warmup.py` — does Playwright stealth still bypass Datadome on Betclic?
- [ ] Verify `odds_evaluator.py` — does EV computation match formula: `hit_rate × odds - 1`?
- [ ] Check if odds_history DB table is being populated (not stale/empty)
- [ ] Verify Betclic HTML cache at `betting/data/html_cache/` — is it fresh?
- [ ] Check for dead bookmaker references (OddsPortal, BetExplorer — both known broken)
- [ ] Verify the interleaved totals parsing (hdp/over/under format) in odds_evaluator

## Subsystem 3: Tipster Aggregation

**Scripts:**
- `scripts/tipster_aggregator.py` (1885 lines) — parallel fetch + parse from 10+ sites
- `scripts/tipster_xref.py` (163 lines) — cross-reference tipster picks with candidates
- `src/bet/api_clients/tipster_playwright.py` — Playwright DOM extraction client

**Sites configured:** ZawodTyper, Typersi, Sportsgambler, PicksWise, BetIdeas, Feedinco, BettingClosed
**DB tables:** `tipster_picks`, `tipster_consensus`

### Audit checklist:
- [ ] Run `PYTHONPATH=src .venv/bin/python3 scripts/tipster_aggregator.py --date $(date +%Y-%m-%d) --verbose` — how many picks extracted?
- [ ] For each site: is it still accessible? Does the parser produce real picks or garbage?
- [ ] Check ZawodTyper URL construction (Polish dates) — is it correct for today?
- [ ] Verify Playwright initialization — does TipsterPlaywrightClient load without errors?
- [ ] Check `tipster_xref.py` — does it read the correct key from aggregator output? (historically had a `"tips"` vs `"all_picks"` key mismatch — R18)
- [ ] Verify DB writes — are `tipster_picks` and `tipster_consensus` tables populated?
- [ ] Check garbage filter effectiveness — run `_is_garbage_event` against sample output
- [ ] Verify market classification accuracy — are statistical markets correctly identified?
- [ ] Check if any sites now return 403/captcha that previously worked

## Expected Output Format

For each subsystem, provide:

```
### [Subsystem Name] — Verdict: OK | PARTIAL | BROKEN

**Working correctly:**
- [list of working components]

**Issues found (severity: Critical/High/Medium/Low):**
- [C1] Description — file:line — fix suggestion
- [H1] Description — file:line — fix suggestion

**Dead code / duplicates:**
- [file] — reason it's dead

**Recommendations:**
- [priority-ordered list of fixes]
```

## Rules

Follow R2, R17, R18, R20 from `agent-execution-protocol.instructions.md` strictly.

- Do NOT auto-reject any site just because it returned few picks — tipster sites vary by day
- If a site returns 403/captcha, report it but don't delete the parser (sites come back)
- Focus on DATA QUALITY over code style — we need REAL picks reaching the DB
