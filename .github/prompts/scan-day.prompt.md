---
name: scan-day
description: "FULLY AUTONOMOUS data engine: parallel Python scan → agent-driven health monitoring → self-healing per sport → enrichment → shortlist. Two-phase architecture: speed (Python threads) + intelligence (per-sport agents)."
agent: bet-scanner
argument-hint: "run_date=2026-05-07" or just run for today
---

# SCAN DAY — Two-Phase Autonomous Data Engine

**YOU MUST COMPLETE THIS ENTIRE PIPELINE WITHOUT ASKING THE USER ANYTHING.**

## ARCHITECTURE: Speed + Intelligence

```
PHASE 1: PARALLEL PYTHON SCAN (all 11 sports simultaneously, ~5 min)
    ↓
    scan_health_{date}.json produced with per-sport status
    ↓
PHASE 2: AGENT-DRIVEN MONITORING + HEALING (sequential, only for failed/degraded sports)
    ↓
    Per-sport agents diagnose and heal with domain knowledge
    ↓
PHASE 3: ENRICHMENT + SHORTLIST (standard pipeline)
```

## EXECUTION ORDER

### Step 1: Launch Parallel Scan (Phase 1)

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 scripts/scan_events.py --parallel-sport --date {{run_date}}
```

This runs ALL 11 sport scanners in parallel Python threads. Takes ~5 min.
Automatically produces `betting/data/scan_health_{date}.json` with health status.

### Step 2: Read Health Report (Phase 2 Decision Point)

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 scripts/scan_health_report.py --date {{run_date}}
```

The health report tells you exactly which sports need attention:
- `HEALTHY` → proceed, no action needed
- `DEGRADED` → invoke per-sport agent for targeted retry
- `FAILED` → invoke per-sport agent for full retry with fallback chain
- `MISSING` → invoke per-sport agent to diagnose crash

### Step 3: Heal Failed Sports (Phase 2 Execution)

For each sport in `healing_priority` order, delegate to the appropriate agent:

| Health Status | Agent Action |
|---------------|-------------|
| FAILED (critical sport) | MUST heal — invoke agent, retry with fallbacks |
| FAILED (support sport) | SHOULD heal — invoke agent if time permits |
| DEGRADED | Invoke agent for targeted source retry |
| MISSING | Invoke agent to diagnose and re-run |

**Each per-sport agent will:**
1. Read the health report for its sport
2. Diagnose the root cause (source 403s? timeout? adapter crash?)
3. Apply sport-specific healing (fallback URLs, alternative sources, reduced concurrency)
4. Re-validate and report success/failure

### Step 4: Continue Standard Pipeline (Phase 3)

After healing, run enrichment and shortlist building:
- Load internal prompt: `.github/internal-prompts/bet-scan-all.prompt.md`
- Execute enrichment phases (stats, odds, weather)
- Build market matrix and shortlist

## DELEGATION ARCHITECTURE

You are the orchestrator (`bet-scanner`). You delegate to sport-specific agents ONLY for healing:

| Agent | Trigger Condition |
|-------|------------------|
| `bet-scanner-football` | Football status DEGRADED/FAILED/MISSING |
| `bet-scanner-tennis` | Tennis status DEGRADED/FAILED/MISSING |
| `bet-scanner-basketball` | Basketball status DEGRADED/FAILED/MISSING |
| `bet-scanner-volleyball` | Volleyball status DEGRADED/FAILED/MISSING |
| `bet-scanner-hockey` | Hockey status DEGRADED/FAILED/MISSING |
| `bet-scanner-esports` | Esports status DEGRADED/FAILED/MISSING |
| `bet-scanner-handball` | Handball status DEGRADED/FAILED/MISSING |
| `bet-scanner-combat` | Combat/MMA status FAILED (ignore MISSING on non-event days) |
| `bet-scanner-racket` | Racket sports status DEGRADED/FAILED/MISSING |
| `bet-scanner-niche` | Niche sports status FAILED (ignore seasonal zeros) |
| `bet-scanner-baseball` | Baseball status DEGRADED/FAILED/MISSING |

Each sport agent is FULLY AUTONOMOUS with its own:
- Execution commands and fallback URLs
- Validation criteria and thresholds
- Self-healing protocols (retry, expand, alternative sources)
- Error pattern recognition (403 = skip domain, timeout = reduce workers)
- Seasonal awareness (MMA non-event days, baseball off-season)

## INPUTS

- **run_date** = {{run_date}} (default: today)
- Config: `config/betting_config.json` + `config/scan_urls.json`

## WHAT YOU PRODUCE

| Artifact | Path | Purpose |
|----------|------|---------|
| Health report | `betting/data/scan_health_{date}.json` | Per-sport status + healing priority |
| Raw scan | `betting/data/scan_summary.json` | All discovered events |
| Shortlist | `betting/data/{date}_s2_shortlist.json` | Top ranked events |
| Market matrix | `betting/data/market_matrix_{date}.json` + `.md` | All events × all markets |
| Decision matrix | `betting/data/decision_matrix_{date}.md` | Approve/watchlist/reject |
| Scan report | `betting/data/{date}_s1_scan_report.md` | Quality report with gaps |

## AFTER SCAN

Use `/orchestrate-betting-day` to continue from S3 (deep stats → odds → coupons).

## CRITICAL RULES

1. **NEVER ask the user to run commands** — you run them yourself
2. **NEVER stop on first error** — diagnose, fix, continue
3. **NEVER report "I couldn't do X"** — try alternatives from troubleshooting section
4. **ALWAYS set PYTHONPATH** — every command needs `PYTHONPATH=src:.`
5. **ALWAYS cd first** — every command starts with `cd /Users/mkoziol/projects/bet`
6. **Seasonal zeros are NOT failures** — baseball off-season, MMA non-event day = normal
7. **Read health report BEFORE delegating** — don't heal sports that are already HEALTHY
8. **Heal in priority order** — critical sports first (football > tennis > basketball > volleyball)

<!-- BET:prompt:scan-day:v3 -->
