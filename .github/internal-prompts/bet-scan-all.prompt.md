---
description: "Complete scan orchestration: dispatches 11 sport scanners in parallel, validates, self-heals gaps, merges results, produces shortlist. Fully autonomous — no human intervention needed."
mode: agent
agent: bet-scanner
---

> **PERMANENT RULES (from copilot-instructions.md §NON-NEGOTIABLE):**
> R7 TOURNAMENT PROTECTION: Major tournaments NEVER skipped. R8 MINOR LEAGUE VALUE: Less popular = more profit. R9 SELF-HEALING: Missing data → enrichment sub-agents.

# SCAN ORCHESTRATION — Full Autonomous Pipeline

> **YOUR ANALYTICAL VALUE:** You don't just launch scanners and report event counts. You assess SOURCE QUALITY — which domains returned shallow fixture-only data vs. rich statistical data, which sources are degrading (increasing 403s, slower response), and whether the overall coverage ACTUALLY supports the markets we need. A script can say "7200 events scanned". Only YOU can determine that 6800 of those are fixture-only from a single shallow source while the 400 with real stat data are all football — meaning tennis/volleyball/basketball analysis will be data-starved in S3.

## MANDATORY: Agent Intelligence Protocol

> **⛔ Follow `agent-execution-protocol.instructions.md` for EVERY script execution.**
> Run script → read FULL output → extract metrics → `sequentialthinking` → structured verdict.
> Raw output paste = YOUR RESPONSE WILL BE REJECTED by the orchestrator.

You MUST follow the Agent Intelligence Protocol defined in your agent definition. Specifically:
1. Use `sequentialthinking` to plan scan dispatch strategy and evaluate coverage
2. Read `/memories/repo/pipeline-lessons-learned.md` — check for known scan failures and source health patterns
3. Use `todo` to track per-sport scanner dispatch (5 core sports + supplementary)
4. Write source health and coverage observations to `/memories/session/`
5. Self-validate: ALL 5 core sports scanned, no phantom fixtures, tournament matches present

You are executing the S1 scan step. You MUST complete all 5 phases below without asking the user anything. If errors occur, diagnose and fix them yourself using the troubleshooting section.

## PHASE 1: PRE-FLIGHT CHECKS

Run these BEFORE launching scanners. Fix any failures before proceeding.

```bash
python3 scripts/validate_phase.py --date {YYYY-MM-DD} --phase pre-flight
```

**If pre-flight fails:**
- Playwright missing → run `python3 -m playwright install chromium`
- DB tables missing → run `python3 scripts/init_database.py`
- Config format old → the `--parallel-sport` flag handles legacy format too
- Import error → check `PYTHONPATH=src:.` is set

## PHASE 2: LAUNCH PARALLEL SPORT SCANNERS

Execute the parallel scan dispatch:

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 scripts/scan_events.py \
  --parallel-sport \
  --urls-file config/scan_urls.json \
  --deep \
  --max-deep-links 30
```

This launches all 5 scanners in parallel with independent timeouts:

| Scanner Group | Agent to Delegate | Timeout | Min Events | Key Sources |
|---------------|-------------------|---------|------------|-------------|
| football | `bet-scanner-football` | 15 min | 200 | flashscore, soccerstats, totalcorner, whoscored, forebet |
| tennis | `bet-scanner-tennis` | 5 min | 30 | tennisexplorer, tennisabstract, flashscore |
| basketball | `bet-scanner-basketball` | 5 min | 20 | basketball-reference, flashscore, covers |
| volleyball | `bet-scanner-volleyball` | 5 min | 15 | flashscore, betexplorer, scores24 |
| hockey | `bet-scanner-hockey` | 3 min | 10 | hockey-reference, flashscore, covers |

**If the parallel command times out or fails**, run sport scanners individually:

```bash
# Run each sport independently (use when parallel dispatch has issues)
python3 scripts/run_scanner.py --sport football --date {YYYY-MM-DD}
```

Repeat for each scanner class: `TennisScanner`, `BasketballScanner`, `VolleyballScanner`, `HockeyScanner`, `EsportsScanner`, `HandballScanner`, `CombatScanner`, `RacketScanner`, `NicheScanner`, `BaseballScanner`.

## PHASE 3: VALIDATE SCAN RESULTS

After scan completes, run validation:

```bash
python3 scripts/verify_scan.py --sport all --date {YYYY-MM-DD}
```

**Validation Gates:**
- [ ] All 11 scanner groups attempted (check run_stats count)
- [ ] Football ≥ 200 events
- [ ] Tennis ≥ 30 events  
- [ ] Basketball ≥ 20 events
- [ ] Volleyball ≥ 15 events
- [ ] Total across all sports ≥ 300 events
- [ ] No Tier 1 sport (football, tennis, basketball, volleyball) at ZERO
- [ ] Error rate < 30% per sport (sources_failed / (sources_ok + sources_failed))

## PHASE 4: SELF-HEAL GAPS (only if Phase 3 found issues)

For each sport below threshold, retry with targeted approach:

```bash
# Retry a specific sport scanner independently
python3 scripts/run_scanner.py --sport SPORT --date {YYYY-MM-DD}
```

**Common fixes by sport:**

| Sport | Likely Cause | Fix |
|-------|-------------|-----|
| Football 0 events | Flashscore JS timeout | Retry with `--max-deep-links 10` (reduce load) |
| Tennis 0 events | TennisExplorer 403 | Flashscore tennis + Scores24 tennis sufficient |
| Esports 0 events | HLTV rate-limited | Wait 60s, retry with `timeout_per_page=90` |
| Niche 0 events | DartsOrakel/CueTracker down | Normal if no tournaments today |
| Combat 0 events | No UFC event today | Normal — UFC is weekly, not daily |
| Baseball 0 (Nov-Mar) | Off-season | Expected — mark as seasonal |
| Volleyball 0 events | All sources returned fixtures only | Run `fetch_api_stats.py --sports volleyball` |
| Any sport: adapter crash | HTML format changed | Fall back to `raw_adapter` (will produce shallow data) |

**If a Tier 1 sport is still at 0 after retry → ESCALATE to user with diagnosis.**

## PHASE 5: MERGE + ENRICHMENT + SHORTLIST

After scan is validated (or gaps are documented), run the full enrichment chain:

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:.

# 5a. Merge scan results — use ingest_scan_stats which handles merge internally
python3 scripts/ingest_scan_stats.py --verbose

# 5b. Discover fixtures via APIs (run sequentially — R17: no background jobs)
python3 scripts/discover_fixtures.py --date {YYYY-MM-DD}
python3 scripts/fetch_api_stats.py --date {YYYY-MM-DD}

# 5c. Fetch odds from multiple sources
python3 scripts/fetch_odds_multi.py

# 5d. Fetch weather for outdoor sports
python3 scripts/fetch_weather.py --date {YYYY-MM-DD}

# 5e. Aggregate all data (handled by build_shortlist.py)
python3 scripts/build_shortlist.py --date {YYYY-MM-DD} --stats-first

# 5f. Generate market matrix (STATS-FIRST mode)
python3 scripts/generate_market_matrix.py --date {YYYY-MM-DD} --stats-first

# 5g. Build ranked shortlist
python3 scripts/build_shortlist.py --date {YYYY-MM-DD} --stats-first
```

**If any enrichment step fails:** Continue with remaining steps. Non-scan enrichment failures are non-blocking — the pipeline operates in STATS-FIRST mode where odds are optional.

## PHASE 5 FINAL VALIDATION

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 scripts/validate_phase.py --date {YYYY-MM-DD} --phase data
```

Also verify with `verify_scan.py`:
```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 scripts/verify_scan.py --sport all --date {YYYY-MM-DD}
```

Use `read_file` tool to inspect key outputs:
- `betting/data/{YYYY-MM-DD}_s2_shortlist.json` — check event count, sport diversity
- `betting/data/market_matrix_{YYYY-MM-DD}.json` — check artifact exists
- `betting/data/scan_summary.json` — overall scan health

## TROUBLESHOOTING REFERENCE

| Error | Diagnosis | Fix Command |
|-------|-----------|-------------|
| `playwright._impl._errors.Error: Browser closed` | Chromium not installed | `python3 -m playwright install chromium` |
| `TimeoutError: Page fetch timed out` | Source slow/down | Retry with `timeout_per_page=90` or skip source |
| `HTTP 403 on betclic.pl` | Expected — never scrape Betclic | Ignore, use other sources for odds |
| `HTTP 403 on HLTV` | Rate-limited | Wait 60s between requests, max 1 concurrent |
| `sqlite3.OperationalError: database is locked` | Concurrent writes | Retry after 1s — WAL mode handles this |
| `ImportError: No module named 'scripts.scanners'` | PYTHONPATH not set | Always use `PYTHONPATH=src:.` prefix |
| `KeyError: 'sports' in config` | Old config format | Add `--parallel-sport` flag — it handles legacy too |
| `ConnectionError` on any domain | Network/DNS issue | Retry once; if persistent, skip and use fallbacks |
| `MemoryError` during football deep-links | Too many pages buffered | Reduce `--max-deep-links 15` |
| Scan takes >20 min | Football deep-links dominate | Normal for 1000+ pages; let it finish |

## DELEGATION RULES

When you encounter issues that require sport-specific expertise:
- **Football issues** → delegate to `bet-scanner-football` agent with the specific error
- **Tennis/Elo issues** → delegate to `bet-scanner-tennis` agent
- **Basketball issues** → delegate to `bet-scanner-basketball` agent
- **Volleyball issues** → delegate to `bet-scanner-volleyball` agent
- **Hockey issues** → delegate to `bet-scanner-hockey` agent

Each sport agent has its own SKILL loaded (`bet-scanning-{sport}`) with source URLs, adapter mappings, and known issues. They know their domain better than you.

## SUCCESS CRITERIA

The scan is DONE when:
1. `scan_summary.json` exists with ≥ 300 events
2. `{date}_s2_shortlist.json` exists with 50-100 events
3. `market_matrix_{date}.json` exists
4. DB `scan_results` table has data for today
5. No Tier 1 sport (football, tennis, basketball, volleyball, hockey) has zero events (unless seasonal)

After success, report to user: event counts per sport, any gaps, total duration, and confirm readiness for S3.
