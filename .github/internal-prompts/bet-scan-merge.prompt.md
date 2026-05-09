---
description: "Post-scan merge — combines all sport scan results, validates coverage, runs enrichment, builds shortlist. Final gate before deep analysis."
mode: agent
agent: bet-scanner
---

> **PERMANENT RULES (from copilot-instructions.md §NON-NEGOTIABLE):**
> R3 NO AUTO-REJECTION: ALL events from all scanners merge into shortlist. R7 TOURNAMENT PROTECTION: Verify tournament matches present. R10 STATS-FIRST: Events without odds included. R13 MAJOR DOMESTIC LEAGUE PROTECTION: Verify protected domestic leagues present (Brasileirão, MLS, Liga MX, CSL, J-League, K-League, Saudi Pro, ISL, etc.). If any protected league is active today but missing → scan coverage FAILED → re-scan.

# SCAN MERGE + ENRICHMENT — Final Assembly

## MANDATORY: Agent Intelligence Protocol

> **⛔ Follow `agent-execution-protocol.instructions.md` for EVERY script execution.**
> Run script → read FULL output → extract metrics → `sequentialthinking` → structured verdict.
> Raw output paste = YOUR RESPONSE WILL BE REJECTED by the orchestrator.

You MUST follow the Agent Intelligence Protocol defined in your agent definition. Specifically:
1. Use `sequentialthinking` to plan merge strategy and evaluate data completeness
2. Read `/memories/repo/pipeline-lessons-learned.md` — check for known merge/enrichment failures
3. Use `todo` to track merge phases (merge → enrich → validate → shortlist)
4. Write coverage and data quality observations to `/memories/session/`
5. Self-validate: all sport results merged, enrichment yield >60%, shortlist sport diversity ≥6

Run after all sport scanners complete. Merges results, enriches with APIs, validates coverage, produces shortlist.

## STEP 1: Merge All Sport Results

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
from scripts.scanners.merge_results import merge_scan_results
from datetime import date
today = str(date.today())
path = merge_scan_results(today)
print(f'Merged scan results to: {path}')

# Verify merge quality
import json
from pathlib import Path
data = json.loads(Path(path).read_text())
if isinstance(data, dict):
    total = sum(len(v) for v in data.values() if isinstance(v, list))
    print(f'Total merged events: {total}')
    print(f'URL keys: {len(data)}')
else:
    print(f'Events in list format: {len(data)}')
"
```

## STEP 2: Run Enrichment Chain

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:.

# Stats enrichment (parallel per sport)
python3 scripts/fetch_api_stats.py --date $(date +%Y-%m-%d)

# Odds from multiple sources
python3 scripts/fetch_odds_multi.py

# Weather for outdoor sports
python3 scripts/fetch_weather.py --date $(date +%Y-%m-%d)

# Ingest scan data into stats cache
python3 scripts/ingest_scan_stats.py
```

**If fetch_api_stats fails:**
- Check if API rate limits exhausted: `cat scripts/api_clients/.rate_limit_state/*.json 2>/dev/null`
- ESPN is free/unlimited — should always work
- API-Sports (api_football, etc.) has 100/day shared limit

**If fetch_odds_multi fails:**
- STATS-FIRST mode: odds are OPTIONAL. Proceed without them.
- User checks Betclic app manually for odds.

## STEP 3: Generate Analysis Artifacts

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:.

# Deep analysis pool
python3 scripts/deep_analysis_pool.py --date $(date +%Y-%m-%d)

# Aggregate and rank
python3 scripts/aggregate_and_select.py --date $(date +%Y-%m-%d)

# Generate market matrix (STATS-FIRST mode)
python3 scripts/generate_market_matrix.py --date $(date +%Y-%m-%d) --stats-first

# Build shortlist
python3 scripts/build_shortlist.py --date $(date +%Y-%m-%d) --stats-first
```

## STEP 4: Validate Final Outputs

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
import json, os
from datetime import date
from pathlib import Path
from collections import Counter

today = str(date.today())
print(f'=== MERGE VALIDATION for {today} ===')

# Check all required artifacts
checks = {
    'scan_summary.json': Path('betting/data/scan_summary.json'),
    f'{today}_s2_shortlist.json': Path(f'betting/data/{today}_s2_shortlist.json'),
    f'market_matrix_{today}.json': Path(f'betting/data/market_matrix_{today}.json'),
    f'market_matrix_{today}.md': Path(f'betting/data/market_matrix_{today}.md'),
    f'decision_matrix_{today}.md': Path(f'betting/data/decision_matrix_{today}.md'),
}

all_ok = True
for name, path in checks.items():
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    status = '✅' if exists and size > 100 else '❌'
    if not exists:
        all_ok = False
    print(f'  {status} {name}: {size:,} bytes' if exists else f'  {status} {name}: MISSING')

# Shortlist diversity check
sl_path = checks[f'{today}_s2_shortlist.json']
if sl_path.exists():
    sl = json.loads(sl_path.read_text())
    events = sl if isinstance(sl, list) else sl.get('events', sl.get('shortlist', []))
    sports = Counter(e.get('sport', 'unknown') for e in events)
    print(f'\nShortlist: {len(events)} events, {len(sports)} sports')
    for s, c in sports.most_common():
        pct = c * 100 / max(len(events), 1)
        flag = ' ⚠️ >50%' if pct > 50 else ''
        print(f'  {s}: {c} ({pct:.0f}%){flag}')
    
    # Gates
    passed = True
    if len(events) < 50:
        print(f'⚠️ Only {len(events)} events (target 50-100)')
        passed = False
    if len(sports) < 8:
        print(f'⚠️ Only {len(sports)} sports (target ≥8)')
        passed = False
    if passed:
        print('✅ Shortlist quality gates PASS')
    else:
        print('⚠️ Shortlist below ideal — but PROCEEDING (non-blocking)')

# Stats cache summary
print(f'\nStats cache health:')
for sport in ['football', 'tennis', 'basketball', 'volleyball', 'hockey']:
    cache_dir = f'betting/data/stats_cache/{sport}'
    count = len(os.listdir(cache_dir)) if os.path.exists(cache_dir) else 0
    print(f'  {sport}: {count} files')

if all_ok:
    print(f'\n✅ ALL ARTIFACTS READY — S1+S2 complete, ready for S3')
else:
    print(f'\n⚠️ Missing artifacts — check specific errors above')
"
```

## STEP 5: Self-Heal Missing Artifacts

**If shortlist missing:**
```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:.
# Rebuild from scan_summary.json directly
python3 scripts/build_shortlist.py --date $(date +%Y-%m-%d) --stats-first --force
```

**If market matrix missing:**
```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:.
python3 scripts/generate_market_matrix.py --date $(date +%Y-%m-%d) --stats-first --force
```

**If shortlist has <50 events:**
- This may be correct if few events today
- Check scan_summary total — if raw scan had 300+, aggregation thresholds may be too strict
- Proceed with what's available — user decides from market matrix

**If <8 sports in shortlist:**
- Check which sports are missing
- Seasonal gaps (baseball off-season, combat no-event-today) are acceptable
- If a Tier 1 sport is missing, that's a real problem — check its scanner report

## TROUBLESHOOTING

| Error | Cause | Fix |
|-------|-------|-----|
| `aggregate_and_select.py` crashes | Missing dependency file | Check scan_summary.json exists first |
| `generate_market_matrix.py` no output | Zero events after filtering | Add `--stats-first` to lower threshold |
| `build_shortlist.py` produces 0 | No events pass safety score | Use `--force` to include all events |
| `fetch_api_stats.py` timeout | API slow | Proceed without — scan data is primary |
| `ingest_scan_stats.py` error | scan_summary format mismatch | Check if using new sport-grouped format |

## SUCCESS CRITERIA

Merge is COMPLETE when:
1. `scan_summary.json` exists and has data
2. `{date}_s2_shortlist.json` exists with ≥ 30 events
3. `market_matrix_{date}.json` and `.md` exist
4. `decision_matrix_{date}.md` exists
5. Stats cache has data for at least 4 sports

Report completion to orchestrator with: event counts, sport breakdown, any gaps documented.
