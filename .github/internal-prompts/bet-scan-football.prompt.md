---
description: "Autonomous football scanner — discovers 200+ events from 90 seeds, deep-links to 500+ pages, validates stat market data. Self-heals on all known failures."
mode: agent
agent: bet-scanner-football
---

# FOOTBALL SCAN — Fully Autonomous

You are the football scanning specialist. Execute this entire workflow without human intervention.

## STEP 1: Execute Scanner

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
from scripts.scanners.football_scanner import FootballScanner
from scripts.scanners.domain_semaphore import DomainSemaphoreMap
from datetime import date
scanner = FootballScanner()
stats = scanner.scan(str(date.today()), DomainSemaphoreMap())
print(f'Football: {stats.events_found} events | {stats.sources_ok} OK | {stats.sources_failed} failed')
print(f'Deep links expanded: {stats.deep_links_found}')
print(f'Validation: {\"PASS\" if stats.validation_passed else \"FAIL\"}')
if not stats.validation_passed:
    print(f'  Gaps: {stats.gaps_description}')
"
```

## STEP 2: Validate Results

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
from bet.db.connection import get_db
from datetime import date
today = str(date.today())
with get_db() as conn:
    c = conn.execute('SELECT COUNT(*) FROM scan_results WHERE sport=\"football\" AND date=?', (today,))
    count = c.fetchone()[0]
    # Check stat key coverage
    c2 = conn.execute('''SELECT data FROM scan_results WHERE sport=\"football\" AND date=? LIMIT 20''', (today,))
    import json
    stat_keys_found = set()
    for row in c2:
        data = json.loads(row[0]) if row[0] else {}
        stat_keys_found.update(data.get('stat_keys', []))
    print(f'Football events in DB: {count}')
    print(f'Stat keys detected: {sorted(stat_keys_found)}')
    required = {'corners', 'fouls', 'yellow_cards', 'shots', 'shots_on_target'}
    missing = required - stat_keys_found
    if missing:
        print(f'⚠️ Missing required keys: {missing}')
    if count >= 200:
        print('✅ PASS: Football ≥ 200 events')
    elif count >= 100:
        print('⚠️ MARGINAL: 100-199 events (acceptable)')
    else:
        print('❌ FAIL: < 100 events — self-heal needed')
"
```

## STEP 3: Self-Heal (only if FAIL)

**If < 100 events:**

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
# Try with reduced deep-link load (avoids timeouts)
from scripts.scanners.football_scanner import FootballScanner
from scripts.scanners.domain_semaphore import DomainSemaphoreMap
from datetime import date
scanner = FootballScanner()
scanner.max_deep_links = 10  # Reduce from 30 to avoid timeout
scanner.timeout_per_page = 60  # Longer timeout for slow sources
stats = scanner.scan(str(date.today()), DomainSemaphoreMap())
print(f'Retry: {stats.events_found} events')
"
```

**If Flashscore JS rendering fails:**
```bash
# Fall back to non-JS sources only
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
import json
config = json.loads(open('config/scan_urls.json').read())
football_urls = config['sports'].get('football', {}).get('urls', [])
# Filter out JS-heavy sources
non_js = [u for u in football_urls if 'flashscore' not in u]
print(f'Non-JS football sources: {len(non_js)}')
# Manually scan these with raw_adapter + soccerstats + totalcorner
from scripts.scanners.football_scanner import FootballScanner
from scripts.scanners.domain_semaphore import DomainSemaphoreMap
scanner = FootballScanner()
scanner.seed_urls = non_js  # Override to skip flashscore
from datetime import date
stats = scanner.scan(str(date.today()), DomainSemaphoreMap())
print(f'Non-JS fallback: {stats.events_found} events')
"
```

**If SoccerStats/TotalCorner specific errors:**
- HTTP 403 → These sites rarely block; check if URL format changed
- Timeout → Normal for large league pages; retry individually
- Parse error → HTML structure changed; use `raw_adapter` fallback

## STEP 4: Report

After completion (pass or heal), report:
- Total events found
- Source success/failure breakdown
- Stat key coverage (which keys available)
- Any remaining gaps to flag

## TROUBLESHOOTING QUICK REFERENCE

| Symptom | Cause | Fix |
|---------|-------|-----|
| 0 events | All sources timed out | Reduce `max_deep_links` to 10 |
| <100 events | Deep-link expansion failed | Run without `--deep` flag |
| Missing corners/fouls keys | TotalCorner/SoccerStats down | Proceed — API enrichment adds keys later |
| `TimeoutError` on flashscore | JS rendering slow | Skip flashscore, use BetExplorer/Scores24 |
| `NavigationError` | Playwright browser crashed | `python3 -m playwright install chromium` |
| Very slow (>15 min) | Deep-linking 1000+ pages | Expected — football is the largest scanner |

## SKILL REFERENCE

Load `bet-scanning-football` skill for: all 90+ source URLs, 5 adapter mappings, data quality requirements, full league coverage.
