# Sport-Specific Scanning Agents — Research Document

**Date:** 2026-05-07  
**Status:** Research Complete  
**Scope:** Restructure S1 scanning from monolithic → per-sport Copilot agent architecture

---

## 1. Current State Analysis

### 1.1 End-to-End Scanning Flow

The current scanning pipeline operates as a **single monolithic process** controlled by `scripts/scan_events.py`:

```
scan_urls.json (232 URLs)
    → scan_events.py (groups by domain, 6-8 parallel workers)
        → per-domain fetch (Playwright or requests, 45s timeout per page)
        → adapter parsing (domain-specific HTML→structured data)
        → deep-link discovery (sub-page crawling for flashscore/betexplorer/etc.)
    → scan_summary.json (all results merged)
    → ingest_scan_stats.py (feeds into stats cache)
    → discover_fixtures.py (API fixture discovery + merge)
    → aggregate_and_select.py (dedup + merge all data)
    → generate_market_matrix.py (consolidated matrix)
    → build_shortlist.py (ranked candidates)
```

The `pipeline_orchestrator.py` assigns a **30-minute (1800s) timeout** to the entire S1 scan step, which must cover all 232+ URLs across all 14 sports.

### 1.2 Current Architecture Components

| Component | File | Role |
|-----------|------|------|
| Scanner entry point | `scripts/scan_events.py` | Groups URLs by domain, parallel fetch |
| Adapter registry | `scripts/adapters/__init__.py` | Maps 25 domains → parsers |
| Sport detection | `scan_events.py:detect_sport()` | URL pattern matching for 14 sports |
| Deep-link discovery | `scripts/deep_link_discovery.py` | Sub-page crawling for 7 domains |
| Source health tracking | DB `source_health` table | Records per-domain success/failure |
| URL configuration | `config/scan_urls.json` | 232 seed URLs |
| Pipeline orchestration | `scripts/pipeline_orchestrator.py` | Runs full S0-S10 with timeouts |

### 1.3 Sport-Specific Logic Already Present

**URL Pattern Detection** (`SPORT_URL_PATTERNS` in scan_events.py):
- Football: 17 patterns (largest coverage)
- Tennis: 4 patterns (`/tennis`, `/tenis`, `tennisabstract`, `tennisexplorer`)
- Basketball: 5 patterns
- Esports: 6 patterns (`/esports`, `gosugamers`, `bo3.gg`, `hltv`, `/csgo`, `/lol`)
- Other sports: 1-4 patterns each

**Domain-Specific Adapters** (18 custom + 1 raw fallback):
| Adapter | Sports Served | Richness |
|---------|---------------|----------|
| `flashscore_adapter.py` | ALL 14 sports | Fixtures + scores (no stats) |
| `sofascore_adapter.py` | ALL sports | Fixtures + live data |
| `betexplorer_adapter.py` | ALL sports | Odds comparison |
| `oddsportal_adapter.py` | 8 sports | Odds comparison |
| `scores24_adapter.py` | 13 sports | Fixtures + basic stats |
| `forebet_adapter.py` | Football focus + 5 more | Predictions + stats |
| `soccerstats_adapter.py` | Football ONLY | Deep football stats |
| `totalcorner_adapter.py` | Football ONLY | Corner/goal data |
| `whoscored_adapter.py` | Football ONLY | Advanced football stats |
| `tennisexplorer_adapter.py` | Tennis ONLY | ATP/WTA schedules + H2H |
| `tennisabstract_adapter.py` | Tennis ONLY | Elo ratings |
| `basketball_reference_adapter.py` | Basketball ONLY | NBA deep stats |
| `hockey_reference_adapter.py` | Hockey ONLY | NHL deep stats |
| `hltv_adapter.py` | Esports (CS2) ONLY | CS2 matches + rankings |
| `covers_adapter.py` | US sports (NBA/NHL/MLB) | US odds + lines |
| `betclic_adapter.py` | ALL sports | Betclic markets listing |
| `soccerway_adapter.py` | Football ONLY | League standings + results |

**Rate Limiting / Domain Delays:**
- `betclic.pl`: 2.0s delay
- `soccerstats.com`: 1.5s
- `totalcorner.com`: 1.0s
- `hltv.org`: 2.0s
- `dartsorakel.com`: 2.0s

**Parallel-Safe Domains** (can fetch multiple pages concurrently):
- `flashscore.com`: 3 concurrent
- `sofascore.com`, `betexplorer.com`, `oddsportal.com`, `forebet.com`, `scores24.live`, `soccerway.com`: 2 concurrent

### 1.4 Timeout Issues & Bottlenecks

| Issue | Root Cause | Impact |
|-------|-----------|--------|
| 30-min hard timeout | All 14 sports share one timeout | Late sports get cut off |
| 45s per-page timeout | Some JS-heavy sites need longer | Flashscore/BetExplorer retry doubles to 90s |
| Deep-link expansion | 50 sub-links per domain × 7 domains = 350 extra fetches | Football dominates (70+ flashscore URLs × 50 deep links) |
| Sequential domain groups | Rate-limited domains block workers | HLTV/DartsOrakel at 2s delay bottleneck |
| Football URL dominance | 90+ football URLs vs 1-5 for niche sports | Football consumes >70% of scan time |

**Observed failure modes:**
1. Football flashscore deep-links consume 15+ minutes → tennis/volleyball/esports get squeezed
2. Rate-limited niche domains (HLTV, DartsOrakel) occupy workers doing nothing but waiting
3. Source failures cascade — if flashscore stalls, all sports sharing that domain are delayed

### 1.5 Source Coverage Gaps Per Sport

| Sport | # Seed URLs | # Dedicated Adapters | Data Richness | Gap Severity |
|-------|-------------|---------------------|---------------|--------------|
| Football | 90+ | 5 (soccerstats, totalcorner, whoscored, forebet, soccerway) | DEEP | None |
| Tennis | 8 | 2 (tennisexplorer, tennisabstract) | MEDIUM | Missing H2H, serve stats |
| Basketball | 15 | 1 (basketball-reference) | GOOD | EU leagues thin |
| Volleyball | 12 | 0 dedicated | SHALLOW | Zero stats cache |
| Hockey | 8 | 1 (hockey-reference) | GOOD | EU leagues thin |
| Handball | 10 | 0 dedicated | SHALLOW | Zero stats cache |
| Esports | 5 | 1 (HLTV) | MEDIUM (CS2 only) | LoL/Dota2 no adapter |
| Snooker | 3 | 0 dedicated | THIN | CueTracker no adapter |
| Darts | 3 | 0 dedicated | THIN | DartsOrakel no adapter |
| Baseball | 4 | 0 dedicated | MEDIUM | Via covers + ESPN |
| Table Tennis | 2 | 0 dedicated | MINIMAL | Only generic parsing |
| MMA | 3 | 0 dedicated | THIN | No UFCstats adapter |
| Padel | 3 | 0 dedicated | THIN | No PremierPadel adapter |
| Speedway | 3 | 0 dedicated | THIN | No SpeedwayEkstraliga adapter |

---

## 2. Target Architecture

### 2.1 Per-Sport Agent Design

Each sport gets a dedicated `.agent.md` that:
1. **Owns** its sport's scanning lifecycle (fetch → parse → validate → report)
2. **Knows** its sport-specific sources, fallback chains, and data requirements
3. **Validates** fixture coverage against expected event counts
4. **Reports** gaps and recommends remediation actions
5. **Hands off** to the orchestrator when complete

**Proposed agent file structure:**
```
.github/agents/
├── bet-scanner-football.agent.md
├── bet-scanner-tennis.agent.md
├── bet-scanner-basketball.agent.md
├── bet-scanner-volleyball.agent.md
├── bet-scanner-hockey.agent.md
├── bet-scanner-esports.agent.md
├── bet-scanner-handball.agent.md
├── bet-scanner-combat.agent.md       ← MMA + boxing (shared sources)
├── bet-scanner-racket.agent.md       ← table_tennis + padel (shared sources)
├── bet-scanner-niche.agent.md        ← snooker + darts + speedway (low volume)
└── bet-scanner-baseball.agent.md
```

**Agent .agent.md template (per copilot-collections pattern):**
```yaml
---
description: "Scans [SPORT] events, validates fixture coverage, manages source health for [SPORT]-specific domains."
tools: [execute/runInTerminal, read/readFile, edit/editFiles, search/textSearch, web/fetch, browser/*, sequential-thinking/*]
model: "Claude Opus 4.6 (Copilot)"
instructions:
  - ../instructions/analysis-methodology.instructions.md
handoffs:
  - label: "Sport scan complete"
    agent: bet-scanner
    prompt: "Sport [SPORT] scan complete. Results merged."
    send: false
---
```

**Agent body contains:**
- Role definition (sport scanning specialist)
- Source registry (sport-specific subset from bet-navigating-sources)
- Data quality requirements (what "rich data" means for this sport)
- Validation criteria (minimum event counts, required stat keys)
- Failure handling (retry logic, fallback sources, escalation)
- Known gaps awareness (from bet-scanner.agent.md knowledge base)

### 2.2 Per-Sport SKILL.md Structure

```
.github/skills/
├── bet-scanning-football/SKILL.md
├── bet-scanning-tennis/SKILL.md
├── bet-scanning-basketball/SKILL.md
├── bet-scanning-volleyball/SKILL.md
├── bet-scanning-hockey/SKILL.md
├── bet-scanning-esports/SKILL.md
├── bet-scanning-handball/SKILL.md
├── bet-scanning-combat/SKILL.md
├── bet-scanning-racket/SKILL.md
├── bet-scanning-niche/SKILL.md
└── bet-scanning-baseball/SKILL.md
```

**SKILL.md content pattern (follows tsh-creating-skills conventions):**
```yaml
---
name: bet-scanning-[sport]
description: "[Sport]-specific scanning knowledge — source URLs, adapters, data quality requirements, validation criteria, timeout configuration, and fallback chains."
user-invokable: false
---
```

**Body sections:**
1. **Source Registry** — URLs, domains, access notes specific to this sport
2. **Adapter Knowledge** — Which adapter to use per domain, expected output format
3. **Data Quality Requirements** — Minimum stat keys, expected event counts per day
4. **Validation Rules** — How to verify scan completeness
5. **Timeout Configuration** — Per-domain timeouts, retry limits
6. **Fallback Chains** — What to do when primary source fails
7. **Known Issues** — Sport-specific quirks (JS rendering, rate limits, seasonal availability)

### 2.3 Python Code Split

**Current:** `scripts/scan_events.py` (single file, ~420 lines)

**Target:**
```
scripts/
├── scan_events.py                    ← Orchestration shell (dispatches to sport modules)
├── scanners/
│   ├── __init__.py                   ← Registry: sport → scanner module
│   ├── base_scanner.py              ← Abstract base class with shared logic
│   ├── football_scanner.py          ← Football-specific scan config + validation
│   ├── tennis_scanner.py
│   ├── basketball_scanner.py
│   ├── volleyball_scanner.py
│   ├── hockey_scanner.py
│   ├── esports_scanner.py
│   ├── handball_scanner.py
│   ├── combat_scanner.py           ← MMA
│   ├── racket_scanner.py           ← Table tennis + padel
│   ├── niche_scanner.py            ← Snooker + darts + speedway
│   └── baseball_scanner.py
├── adapters/                         ← Existing (unchanged)
│   ├── __init__.py
│   ├── flashscore_adapter.py
│   └── ...
```

**Base scanner interface:**
```python
class BaseSportScanner:
    sport: str
    urls: list[str]                    # From scan_urls.json, filtered for this sport
    adapters: dict[str, callable]      # Domain → adapter mapping
    timeout_per_page: int = 45
    max_deep_links: int = 30
    required_stat_keys: list[str]      # What "rich data" means for this sport
    min_expected_events: int           # Minimum daily events
    
    def scan(self) -> ScanResult: ...
    def validate(self, result: ScanResult) -> ValidationReport: ...
    def get_fallback_urls(self) -> list[str]: ...
```

**Per-sport scanner responsibilities:**
- Define sport-specific URL list (filtered from scan_urls.json or hardcoded)
- Configure timeouts per domain (football deep-links get more time)
- Define validation criteria (football expects 200+ events, darts expects 5-10)
- Handle sport-specific adapter selection
- Report scan quality metrics

### 2.4 Orchestration Changes

**Current:** Sequential scan of all URLs in one pass (grouped by domain, parallel within)

**Target:** Parallel sport scans with independent timeouts:

```
pipeline_orchestrator.py
    │
    ├── Football Scanner (timeout: 15 min) ──→ 90+ URLs, deep-links
    ├── Tennis Scanner (timeout: 5 min)    ──→ 8 URLs
    ├── Basketball Scanner (timeout: 5 min) ──→ 15 URLs
    ├── Volleyball Scanner (timeout: 5 min) ──→ 12 URLs
    ├── Hockey Scanner (timeout: 3 min)    ──→ 8 URLs
    ├── Esports Scanner (timeout: 5 min)   ──→ 5 URLs (HLTV rate-limited)
    ├── Handball Scanner (timeout: 3 min)  ──→ 10 URLs
    ├── Combat Scanner (timeout: 2 min)    ──→ 3 URLs
    ├── Racket Scanner (timeout: 3 min)    ──→ 5 URLs
    ├── Niche Scanner (timeout: 5 min)     ──→ 9 URLs (rate-limited domains)
    └── Baseball Scanner (timeout: 3 min)  ──→ 4 URLs
    
    ALL run in parallel → merge results → scan_summary.json
```

**Key orchestration changes:**
1. Each sport scanner runs **independently** with its own timeout
2. Failure of one sport does NOT affect others
3. Results merge via a **coordinator** that collects per-sport outputs
4. Multi-sport domains (flashscore, betexplorer, scores24) are **partitioned** — each sport claims its URLs from shared domains
5. Shared domain rate limits are coordinated via a **domain semaphore** (prevents 3 sport scanners all hitting flashscore simultaneously)

### 2.5 Result Merging

Per-sport scanners each produce:
```json
{
  "sport": "football",
  "scan_time_seconds": 420,
  "events_found": 312,
  "sources_ok": 15,
  "sources_failed": 2,
  "deep_links_found": 87,
  "validation": {
    "passed": true,
    "min_events_met": true,
    "stat_keys_coverage": 0.85
  },
  "results": { "url": [...events...] }
}
```

A **merge step** (`scripts/scanners/merge_results.py`) combines all sport results into the unified `scan_summary.json` format expected by downstream pipeline steps.

---

## 3. Sport Groupings

### 3.1 Shared Source Analysis

| Source Domain | Sports Covered | Access Pattern |
|--------------|----------------|----------------|
| flashscore.com | ALL 14 | URL path determines sport (`/tennis/`, `/basketball/`, etc.) |
| sofascore.com | ALL 14 | URL path determines sport |
| betexplorer.com | 10 (all except tennis, hockey, baseball, mma) | URL path determines sport |
| scores24.live | 13 (all except padel) | URL path determines sport |
| oddsportal.com | 8 (football, tennis, basketball, hockey, baseball, volleyball, handball) | URL path |
| forebet.com | 6 (football, tennis, basketball, hockey, handball, volleyball) | URL path |
| betclic.pl | ALL 14 | Polish sport paths (`/pilka-nozna-s1`, `/tenis-s2`, etc.) |
| covers.com | 4 (NBA, NHL, MLB, NFL) | US sports hub |

### 3.2 Sport-Exclusive Sources

| Source | Sport | Reason for Exclusivity |
|--------|-------|----------------------|
| HLTV.org | Esports (CS2) | Only CS2 competitive data |
| TennisAbstract | Tennis | Elo ratings, player stats |
| TennisExplorer | Tennis | ATP/WTA/ITF schedules |
| Basketball-Reference | Basketball (NBA) | Deep NBA historical stats |
| Hockey-Reference | Hockey (NHL) | Deep NHL historical stats |
| SoccerStats | Football | Football-specific statistical profiles |
| TotalCorner | Football | Corner/goal market data |
| WhoScored | Football | Advanced football analytics |
| Soccerway | Football | League tables, results |
| DartsOrakel | Darts | Dart-specific predictions |
| CueTracker | Snooker | Snooker rankings, results |
| SpeedwayEkstraliga | Speedway | Polish speedway data |
| PremierPadel | Padel | Padel tour data |
| GosuGamers | Esports | Multi-title esports |

### 3.3 Recommended Groupings

Based on source overlap, daily event volume, and scanning complexity:

| Agent Group | Sports | Rationale |
|-------------|--------|-----------|
| **Football** | football | Dominant volume (90+ URLs, 200+ daily events), 5 dedicated adapters, needs own timeout |
| **Tennis** | tennis | Unique sources (TennisAbstract, TennisExplorer), moderate volume |
| **Basketball** | basketball | NBA deep sources + EU leagues, moderate volume |
| **Volleyball** | volleyball | Tier 1 sport with critical data gaps, needs focused attention |
| **Hockey** | hockey | Dual US/EU coverage (Hockey-Reference + European leagues) |
| **Esports** | esports (CS2, LoL, Dota2) | HLTV + GosuGamers, rate-limited, needs patient fetching |
| **Handball** | handball | Same data gap profile as volleyball, EU-focused |
| **Combat** | mma | Single-source (UFCstats/Tapology), low volume |
| **Racket** | table_tennis, padel | Both use Sofascore/BetExplorer, very low volume, similar data patterns |
| **Niche** | snooker, darts, speedway | All use specialist single sources, very low volume (1-10 events/day) |
| **Baseball** | baseball | US-focused, covers.com + ESPN, seasonal |

**Total: 11 scanner groups** (vs 14 individual sports)

---

## 4. Copilot Agent Design Patterns

### 4.1 Agent File Structure (Following copilot-collections)

Based on analysis of `tsh-software-engineer.agent.md` and `tsh-e2e-engineer.agent.md`:

```yaml
---
description: "Short summary of agent's role"
tools: [list of tool access patterns]
model: "Claude Opus 4.6 (Copilot)"
instructions:
  - path to relevant instruction files
handoffs:
  - label: "What triggers handoff"
    agent: target-agent
    prompt: /prompt-name Description
    send: false
---

## Agent Role and Responsibilities
Role: You are... (core identity)

## Skills Usage Guidelines
- skill-name - when to use

## Tool Usage Guidelines  
(per tool: MUST use when / IMPORTANT / SHOULD NOT)
```

### 4.2 Sport Scanner Agent Template

```markdown
---
description: "Scans [SPORT] fixtures across [N] sources, validates data quality, manages [SPORT]-specific timeouts and fallback chains. Reports enrichment gaps."
tools:
  [execute/runInTerminal, execute/getTerminalOutput, read/readFile, edit/editFiles, search/textSearch, sequential-thinking/*]
model: "Claude Opus 4.6 (Copilot)"
instructions:
  - ../instructions/analysis-methodology.instructions.md
handoffs:
  - label: "[Sport] scan complete → merge into master"
    agent: bet-scanner
    prompt: "[Sport] scan finished. [N] events found. Merge results."
    send: false
---

## Agent Role and Responsibilities

Role: You are the [SPORT] scanning specialist. You OWN the complete scan lifecycle for [sport] events:
discover fixtures → fetch source pages → parse with adapters → validate coverage → report quality.

You know [sport]'s unique data requirements:
- [list of required stat keys]
- [expected daily event count range]
- [sport-specific validation rules]

## Source Registry

| Source | Role | URL Pattern | Adapter | Rate Limit |
|--------|------|-------------|---------|------------|
[sport-specific source table]

## Validation Criteria

- Minimum events: [N]
- Required stat keys: [list]
- Multi-source verification: ≥2 sources per event
- Freshness: All data from today's date

## Failure Handling

1. Primary source down → try secondary (from fallback chain)
2. Adapter error → fall back to raw_adapter
3. Timeout → report partial, flag affected events
4. Zero results → escalate to bet-scanner orchestrator

## Skills

Load: `bet-scanning-[sport]` — source URLs, adapter knowledge, known issues
```

### 4.3 SKILL.md Design for Scanning

Following `tsh-creating-skills` pattern (concise, <500 lines, progressive disclosure):

```markdown
---
name: bet-scanning-[sport]
description: "[Sport]-specific scanning — source URLs, adapter mappings, data requirements, timeouts, fallback chains, and validation rules."
user-invokable: false
---

# Scanning [Sport]

## Source URLs
[list of all seed URLs for this sport with their domain/role]

## Adapter Mapping
[domain → adapter function with expected output fields]

## Data Quality Standards
[what stat keys are needed, minimum confidence]

## Timeout Configuration
[per-domain timeouts specific to this sport]

## Fallback Chains
[ordered list of alternatives when each source fails]

## Seasonal/Schedule Considerations
[off-season handling, competition calendars affecting event counts]

## Known Issues
[sport-specific quirks documented from bet-scanner.agent.md knowledge base]
```

### 4.4 Agent Oversight Model

Sport scanner agents "oversee" their scan by:

1. **Pre-scan validation:** Check source health history (DB `source_health` table) before starting
2. **In-scan monitoring:** Watch for adapter errors, empty responses, stale content
3. **Post-scan verification:** 
   - Compare event count to historical daily averages
   - Verify stat key presence for required fields
   - Check multi-source overlap (≥2 sources confirm each event)
4. **Remediation:** Trigger fallback sources, retry after delay, flag unresolvable gaps
5. **Escalation:** If validation fails after retries → report to `bet-scanner` orchestrator with recommendations

### 4.5 Internal Prompts for Scan Orchestration

```
.github/internal-prompts/
├── bet-scan-football.prompt.md    ← Triggers football scanner agent
├── bet-scan-tennis.prompt.md
├── bet-scan-basketball.prompt.md
├── bet-scan-all.prompt.md         ← Master prompt that triggers all sport scans in parallel
└── bet-scan-merge.prompt.md       ← Triggered after all sport scans complete
```

**Master scan prompt (`bet-scan-all.prompt.md`):**
```markdown
---
description: "Launch parallel sport scans across all 14 sports"
mode: agent
agent: bet-scanner
---

Run all sport scanners in parallel:
1. Dispatch to each sport scanner agent
2. Collect results as they complete
3. Merge into unified scan_summary.json
4. Validate overall coverage (≥14 sports represented, ≥50 total events)
5. Report any sport that failed or returned below-threshold results
```

---

## 5. Integration Points

### 5.1 How Sport Scanners Feed Into S1→S1e Pipeline (DB-First)

**Critical: DB-First principle applies.** Per the existing pipeline convention (see db-first-migration-complete-20260505), scan results must be **persisted to the database as primary storage**, with JSON as secondary human-readable output.

```
[Sport Scanner Agents] (parallel)
    │
    ↓ (each writes: DB scan_results table + sport_scan_{sport}.json for debug)
    │
[Merge/Validation Step] (scripts/scanners/merge_results.py)
    │
    ↓ reads from DB, produces: betting/data/scan_summary.json (backward-compat)
    │
[EXISTING PIPELINE CONTINUES UNCHANGED]
    ↓
ingest_scan_stats.py → discover_fixtures.py → fetch_api_stats.py
    → aggregate_and_select.py → generate_market_matrix.py → build_shortlist.py
```

**DB-First requirements for sport scanners:**
1. New `scan_results` table — stores per-event scan results (sport, source, event_key, raw_data, timestamp)
2. New `ScanResultRepo` class in `repositories.py` — CRUD for scan results
3. Each sport scanner **dual-writes**: DB first (primary), then JSON (debug/human)
4. Downstream scripts read from DB via repository, fall back to JSON
5. `SourceHealthRepo` already exists — sport scanners use it for health tracking
6. `FixtureRepo` already exists — sport scanners write discovered fixtures to DB
7. Per-sport scan metadata (events_found, sources_ok, duration) stored in `pipeline_runs` via `PipelineRepo`

**New DB tables needed:**
```sql
CREATE TABLE IF NOT EXISTS scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    betting_date TEXT NOT NULL,
    sport TEXT NOT NULL,
    source_domain TEXT NOT NULL,
    event_key TEXT NOT NULL,        -- normalized: "team_a|team_b|kickoff"
    home_team TEXT,
    away_team TEXT,
    competition TEXT,
    kickoff TEXT,                    -- ISO datetime
    raw_data TEXT,                   -- JSON blob with all parsed fields
    scan_timestamp TEXT NOT NULL,
    UNIQUE(betting_date, sport, source_domain, event_key)
);

CREATE TABLE IF NOT EXISTS scan_run_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    betting_date TEXT NOT NULL,
    sport TEXT NOT NULL,
    scanner_group TEXT NOT NULL,     -- e.g., "football", "racket" (may differ from sport)
    events_found INTEGER DEFAULT 0,
    sources_ok INTEGER DEFAULT 0,
    sources_failed INTEGER DEFAULT 0,
    deep_links_found INTEGER DEFAULT 0,
    duration_seconds REAL,
    validation_passed INTEGER DEFAULT 1,
    gaps_description TEXT,           -- JSON array of gap descriptions
    scan_timestamp TEXT NOT NULL,
    UNIQUE(betting_date, sport)
);
```

**Key principle:** The merge step reads from DB and produces `scan_summary.json` **identical in format** to what `scan_events.py` produces today. All downstream scripts (`ingest_scan_stats.py`, `discover_fixtures.py`, etc.) require ZERO changes initially, but should progressively migrate to DB-first reads.

### 5.2 Database Integration

Existing DB schema supports per-sport scanning:

| Table | Relevance | Usage by Sport Scanners |
|-------|-----------|------------------------|
| `source_health` | Per-domain success/failure tracking | Each scanner records its domains' health |
| `fixtures` | Discovered events with sport tag | Each scanner writes its sport's fixtures |
| `teams` | Normalized team/player names | Shared across all scanners |
| `competitions` | League/tournament registry | Each scanner manages its competitions |
| `sports` | Sport lookup table | Pre-populated with 14 sports |

**Connection pattern** (from existing code):
```python
from bet.db.connection import get_db
from bet.db.repositories import SourceHealthRepo, FixtureRepo, SportRepo
```

Each sport scanner can independently write to the DB since SQLite WAL mode supports concurrent reads and serialized writes.

### 5.3 Error Handling and Fallback Chains

**Per-sport error handling** (replaces current monolithic error accumulation):

| Error Type | Current Handling | Target Handling |
|------------|-----------------|-----------------|
| Fetch timeout | Logged in scan_errors.json | Sport scanner retries with extended timeout, tries fallback URL |
| Adapter failure | Falls back to raw_adapter | Sport scanner knows which alternate adapter to try |
| Empty response | Logged as warning | Sport scanner triggers fallback source chain |
| Rate limiting | 2s delay + continue | Sport scanner waits + retries in background |
| Domain down | Logged, skipped | Sport scanner switches to fallback chain, reports gap |

**Escalation protocol:**
1. Sport scanner retries (max 2 retries per source)
2. Sport scanner tries all fallback sources
3. If still below threshold → report partial results + gap description
4. Master scanner collects all gap reports → creates `scan_gaps_{date}.json`

### 5.4 Configuration Changes

**`config/scan_urls.json` restructure:**

```json
{
  "description": "Scan URLs grouped by sport for per-sport scanners",
  "sports": {
    "football": {
      "urls": ["https://flashscore.com/football/...", ...],
      "dedicated_sources": ["soccerstats.com", "totalcorner.com", "soccerway.com"],
      "timeout_minutes": 15,
      "max_deep_links": 50
    },
    "tennis": {
      "urls": ["https://flashscore.com/tennis/", "https://tennisexplorer.com/", ...],
      "dedicated_sources": ["tennisabstract.com", "tennisexplorer.com"],
      "timeout_minutes": 5,
      "max_deep_links": 20
    }
  },
  "shared_sources": {
    "betclic.pl": {"all_sports": true, "delay": 2.0},
    "betexplorer.com": {"all_sports": true, "parallel": 2}
  }
}
```

### 5.5 Shared Domain Coordination

Multi-sport domains (flashscore, betexplorer, scores24, oddsportal, betclic) need coordination:

**Option A — URL Partitioning:** Each sport scanner claims its sport-specific URLs from shared domains. Example: football scanner takes `flashscore.com/football/*`, tennis scanner takes `flashscore.com/tennis/*`. The shared domain's rate limit is respected per-scanner via a **domain semaphore file** or in-memory lock.

**Option B — Shared Domain Scanner:** A separate "multi-sport fetcher" handles all shared-domain URLs in one pass, then distributes parsed results to sport scanners for validation. Sport scanners handle only their dedicated sources.

**Recommendation: Option A** — simpler, keeps sport scanners fully autonomous, domain semaphore prevents rate limit violations.

---

## 6. Migration Path

### 6.1 Phased Approach

**Phase 1 — Python Code Split (no agent changes):**
- Create `scripts/scanners/` module with base class + per-sport scanners
- Refactor `scan_events.py` to dispatch to sport scanners
- Maintain backward compatibility (same output format)
- Add per-sport timeouts and validation

**Phase 2 — Agent + Skill Creation:**
- Create 11 sport scanner `.agent.md` files
- Create 11 `bet-scanning-*` SKILL.md files
- Create internal prompts for scan orchestration
- Update `bet-scanner.agent.md` to become the scan orchestrator (dispatches to sport agents)

**Phase 3 — Orchestration Integration:**
- Update `pipeline_orchestrator.py` to run sport scans in parallel
- Add per-sport health metrics and quality reporting
- Implement domain semaphore for shared sources
- Add scan gap reporting and escalation

### 6.2 Backward Compatibility

- `scan_summary.json` format remains unchanged
- All downstream scripts (`ingest_scan_stats.py`, `discover_fixtures.py`, etc.) require no changes
- `config/scan_urls.json` gets restructured but old format is supported via migration script
- `bet-scanner.agent.md` evolves from "do everything" to "orchestrate sport scanners"

---

## 7. Open Questions

| # | Question | Impact | Recommendation |
|---|----------|--------|----------------|
| 1 | Should shared-domain URLs (flashscore root `/`) be scanned once or per-sport? | Efficiency vs autonomy | Once centrally, results distributed |
| 2 | How to handle domain rate limits across parallel sport scanners? | Could get 403s from concurrent access | Domain semaphore (file lock or asyncio.Semaphore) |
| 3 | Should niche sports (1-5 events/day) really get their own agent? | Overhead of 11 agents | Group into 3-4 clusters as proposed |
| 4 | How do sport scanner agents interact with the existing `bet-scanner` agent? | Delegation vs replacement | bet-scanner becomes orchestrator, sport agents are workers |
| 5 | Should adapters be duplicated per sport or remain shared? | Maintenance vs independence | SHARED — adapters are domain-specific, not sport-specific |
| 6 | Per-sport scan results: separate JSON files or single merged output? | Debugging vs simplicity | Both — per-sport for debugging, merged for pipeline |
| 7 | How to handle sports with zero events on a given day (off-season)? | False failure alerts | Sport scanner knows its season calendar, reports "expected zero" |

---

## 8. Effort Estimation Summary

| Component | Count | Complexity |
|-----------|-------|------------|
| Sport scanner Python modules | 11 | Medium (base class + sport config) |
| Base scanner class | 1 | Medium (shared logic extraction) |
| Agent .agent.md files | 11 | Low-Medium (template + sport customization) |
| SKILL.md files | 11 | Medium (source knowledge per sport) |
| Internal prompts | 5-6 | Low |
| Pipeline orchestrator changes | 1 | Medium (parallel dispatch + merge) |
| Config restructuring | 1 | Low |
| Domain coordination (semaphore) | 1 | Medium |
| Merge/coordinator script | 1 | Low |
| Tests | 11+ | Medium |

---

## 9. Key References

| File | Purpose |
|------|---------|
| `scripts/scan_events.py` | Current monolithic scanner (420 lines) |
| `scripts/adapters/__init__.py` | Domain→adapter registry (25 domains) |
| `scripts/pipeline_orchestrator.py` | Pipeline with timeouts and step definitions |
| `config/scan_urls.json` | 232 seed URLs |
| `.github/agents/bet-scanner.agent.md` | Current scanner agent (orchestration + knowledge) |
| `.github/skills/bet-navigating-sources/SKILL.md` | Full source registry for all 14 sports |
| `copilot-collections/.github/agents/tsh-software-engineer.agent.md` | Agent template pattern |
| `copilot-collections/.github/skills/tsh-creating-agents/SKILL.md` | Agent creation guidelines |
| `copilot-collections/.github/skills/tsh-creating-skills/SKILL.md` | Skill creation guidelines |
