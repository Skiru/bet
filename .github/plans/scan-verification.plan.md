# Scan Verification Mode — Implementation Plan

**Created:** 2026-05-11
**Status:** DRAFT
**Goal:** Add deep, continuous verification of scan results to the existing 2-tier scanner hierarchy (orchestrator + 5 per-sport agents).

---

## Problem Statement

Currently `bet-scanner` only performs basic health checks (event counts, source failures via `scan_health_report.py`). There is no:
- Trend analysis (comparison with previous days)
- Phantom fixture detection (duplicates, already-played matches)
- Per-event data quality validation (kickoff times, team names, leagues)
- Source trend tracking (coverage degradation over time)
- Anomaly alerts (sudden deviations from normal patterns)
- Cross-source consistency checks (same match, different data)

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  bet-scanner (orchestrator)                                  │
│                                                              │
│  PHASE 1: Parallel Scan ──────────────────── (existing)      │
│  PHASE 2: Health Check + Self-Healing ─────── (existing)     │
│  PHASE 2.5: VERIFICATION ─────────────────── (NEW)           │
│    └─ run verify_scan_results.py (cross-sport)               │
│    └─ analyze: trends, phantoms, anomalies                   │
│    └─ dispatch per-sport agents in verification mode         │
│  PHASE 3: Merge + Enrich ─────────────────── (existing)      │
└──────────────────────────────────────────────────────────────┘
         │                                │
    ┌────▼────┐                      ┌────▼────┐
    │ per-sport│  (5 agents)         │ verify_ │
    │ agent    │                     │ scan_   │
    │          │ verification mode:  │ results │
    │ Step 5:  │ run script --sport  │ .py     │
    │ Verify   │ → interpret results │ (NEW)   │
    └──────────┘                     └─────────┘
```

**Design principle:** The Python script does ALL heavy computation (DB queries, comparisons, statistics). Agents interpret results and provide qualitative analysis.

---

## Files to Modify/Create

| # | File | Action | Lines Added (est.) |
|---|------|--------|--------------------|
| 1 | `scripts/verify_scan_results.py` | CREATE | ~280 |
| 2 | `.github/agents/bet-scanner.agent.md` | MODIFY | ~25 |
| 3 | `.github/agents/bet-scanner-football.agent.md` | MODIFY | ~18 |
| 4 | `.github/agents/bet-scanner-basketball.agent.md` | MODIFY | ~18 |
| 5 | `.github/agents/bet-scanner-tennis.agent.md` | MODIFY | ~18 |
| 6 | `.github/agents/bet-scanner-volleyball.agent.md` | MODIFY | ~18 |
| 7 | `.github/agents/bet-scanner-hockey.agent.md` | MODIFY | ~18 |
| 8 | `.github/internal-prompts/bet-scan.prompt.md` | MODIFY | ~6 |
| 9 | `scripts/agent_protocol.py` | MODIFY | ~22 |

---

## Phase 1: Create Verification Script [CREATE]

### Task 1.1: `scripts/verify_scan_results.py`

**Purpose:** Query DB, compute verification metrics, produce structured report for agent consumption.

**CLI interface:**
```
python3 scripts/verify_scan_results.py --date YYYY-MM-DD [--sport SPORT] [--verbose] [--stop-on-error] [--days-back 7]
```

**Arguments:**
- `--date` (required) — betting date to verify
- `--sport` — filter to single sport (for per-sport agent invocation)
- `--verbose` / `-v` — JSON-line events (R19 compliance)
- `--stop-on-error` — halt on critical (R19 compliance)
- `--days-back` — historical comparison window (default: 7)

**Imports:**
- `from bet.db.connection import get_db` (R2 DB-first)
- `from agent_output import AgentOutput, add_agent_args, add_sport_filter_arg`
- Standard: `argparse`, `json`, `collections.Counter`, `datetime`, `statistics`

**Verification checks (7 functions):**

1. **`check_trend_analysis(conn, date, sport, days_back) → dict`**
   - Query `scan_run_stats` for last `days_back` days per sport
   - Compute 7-day average `events_found` per sport
   - Compare today vs average → flag deviations >30%
   - Return: `{sport: {today, avg_7d, deviation_pct, status}}`

2. **`check_phantom_fixtures(conn, date, sport) → dict`**
   - Query `scan_results` for today
   - Find events with `kickoff` in the past (>2h before scan time)
   - Find duplicate `event_key` within same source (true duplicates, not cross-source which is expected)
   - Return: `{past_kickoff_count, duplicate_count, examples: [...]}`

3. **`check_event_quality(conn, date, sport) → dict`**
   - Iterate all `scan_results` for today
   - Check per-event: `home_team` not empty, `away_team` not empty, `kickoff` is valid ISO datetime, `competition` not empty
   - Count issues per field per sport
   - Return: `{total_events, issues_by_field: {home_team: N, away_team: N, ...}, quality_pct}`

4. **`check_cross_source_consistency(conn, date, sport) → dict`**
   - Group `scan_results` by normalized `event_key`
   - For events appearing from 2+ sources: compare `home_team`, `away_team`, `kickoff`
   - Flag mismatches (team name differences beyond minor variations, kickoff >30min apart)
   - Return: `{multi_source_events, mismatches, mismatch_examples: [...]}`

5. **`check_sport_specific_quality(conn, date, sport) → dict`**
   - Sport-dependent raw_data checks:
     - Football: check `raw_data` JSON for presence of stat-related keys (corners, fouls, shots)
     - Basketball: check for points, rebounds, assists keys
     - Tennis: check for sets, games keys
     - Volleyball: check for points, sets keys
     - Hockey: check for shots, goals keys
   - Return: `{events_with_stats, events_without_stats, stat_coverage_pct}`

6. **`check_league_coverage(conn, date, sport, days_back) → dict`**
   - Get distinct `competition` values from today's scan_results per sport
   - Get distinct `competition` values from last 7d scan_results per sport
   - Find leagues present in all 7 prior days but missing today → flag as potential gap
   - Return: `{leagues_today, leagues_7d_avg, missing_leagues: [...]}`

7. **`check_source_health_trend(conn, sport) → dict`**
   - Query `source_health` table for sources related to this sport
   - Flag sources with `consecutive_failures > 3` or failure rate >20%
   - Return: `{sources_checked, degraded_sources: [{name, failure_rate, consecutive_failures}]}`

**Output structure (AGENT_SUMMARY):**
```json
{
  "step": "verify_scan",
  "verdict": "OK|PARTIAL|FAILED",
  "metrics": {
    "total_events_today": 8500,
    "phantom_fixtures": 12,
    "past_kickoff_events": 45,
    "duplicate_event_keys": 3,
    "event_quality_pct": 94.2,
    "cross_source_match_pct": 97.1,
    "sports_with_trend_anomaly": 1,
    "missing_historical_leagues": 2,
    "degraded_sources": 1
  },
  "per_sport": {
    "football": {"events": 4200, "avg_7d": 4100, "deviation_pct": 2.4, "quality_pct": 96.0, "issues": []},
    "tennis": {"events": 80, "avg_7d": 150, "deviation_pct": -46.7, "quality_pct": 88.0, "issues": ["trend_anomaly"]}
  },
  "issues": [
    {"level": "warning", "message": "Tennis event count 46.7% below 7-day average", "sport": "tennis"},
    {"level": "warning", "message": "12 phantom fixtures detected (past kickoff)", "sport": "all"}
  ]
}
```

**Exit codes:** 0 = all clean, 1 = warnings found, 2 = critical issues

**Output file:** `betting/data/scan_verification_{date}.json`

**Definition of done:**
- [ ] Script runs with `--date 2026-05-11` and produces valid AGENT_SUMMARY JSON
- [ ] `--sport football` correctly filters to football-only checks
- [ ] `--verbose` produces JSON-line events during execution
- [ ] All 7 check functions have unit tests in `tests/test_verify_scan_results.py`
- [ ] Uses `from bet.db.connection import get_db` (not raw `sqlite3.connect`)
- [ ] Uses `AgentOutput` from `agent_output.py` for all structured output
- [ ] Writes `betting/data/scan_verification_{date}.json` with full report
- [ ] All SQL queries use parameterized arguments (no f-string interpolation)

---

## Phase 2: Modify Orchestrator Agent [MODIFY]

### Task 2.1: Add PHASE 2.5: VERIFICATION to `bet-scanner.agent.md`

**Location:** Insert after the existing "PHASE 2b: SELF-HEALING" section and before "PHASE 3: MERGE + ENRICH".

**Content to add (~25 lines):**

```markdown
### PHASE 2.5: VERIFICATION — Deep quality checks (runs after healing)

After health check and any self-healing, run deep verification:

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 scripts/verify_scan_results.py --date {date} --verbose
```

Parse `AGENT_SUMMARY:{json}` — this contains trend analysis, phantom detection, event quality, cross-source consistency, and league coverage checks.

**Agent decision logic after verification:**
- `verdict: OK` → Proceed to Phase 3
- `verdict: PARTIAL` → Review `per_sport` for flagged sports. If a sport has `trend_anomaly` or `quality_pct < 80` → dispatch that sport's scanner agent in **verification mode** with the report
- `verdict: FAILED` → Critical issues found (>20 phantom fixtures or quality_pct <60). Investigate before proceeding.

**Per-sport verification dispatch template:**
```
Your sport has verification issues. Here is your verification report:
- Quality score: {quality_pct}%
- Trend: {deviation_pct}% vs 7-day average
- Issues: {issues_list}

Run verification mode — deep-check your sport's scan results and report findings.
```
```

**Also modify:** The overview workflow diagram at the top to show VERIFICATION between HEAL and MERGE.

**Definition of done:**
- [ ] PHASE 2.5 section exists between Phase 2b and Phase 3
- [ ] Includes the `verify_scan_results.py` command with `--verbose`
- [ ] Includes decision logic (OK/PARTIAL/FAILED → actions)
- [ ] Includes per-sport verification dispatch template
- [ ] Overview diagram updated to include VERIFICATION step
- [ ] File size increase ≤ 30 lines

---

### Task 2.2: Add verification handoff labels to `bet-scanner.agent.md` frontmatter

**Location:** YAML frontmatter `handoffs:` array.

**Content to add:** No change needed — existing per-sport dispatch handoffs already cover verification mode (same agents, different prompt). The dispatch template in PHASE 2.5 provides the verification-mode prompt.

---

## Phase 3: Add Verification Mode to Per-Sport Agents [MODIFY]

All 5 per-sport agents get the same structural change. Each gets ~15-18 lines added.

### Task 3.1: Modify `bet-scanner-football.agent.md`

**Location 1:** Modify the "TWO INVOCATION MODES" section to become "THREE INVOCATION MODES":
```markdown
**THREE INVOCATION MODES:**
1. **Fresh scan** — No context. Run full workflow from Step 1.
2. **Healing mode** — Invoked with health context. Skip to Step 3 (self-heal).
3. **Verification mode** — Invoked with verification report. Run Step 5 (verify).
```

**Location 2:** Modify Step 0 to detect verification context:
```markdown
If you received verification context (quality_pct, deviation_pct, issues), you are in **verification mode**:
- Go directly to Step 5
```

**Location 3:** Add new Step 5 section after existing Step 4:
```markdown
### Step 5: Verification Mode (only when invoked with verification context)

Run sport-specific verification:
```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 scripts/verify_scan_results.py --date $(date +%Y-%m-%d) --sport football --verbose
```

**Interpret results using `sequentialthinking`:**
- Trend: Is event count deviation explained by schedule (weekday vs weekend)?
- Quality: Football events MUST have `home_team` + `away_team` + `competition`. Quality <90% = problem.
- Stat coverage: What percentage of events have `corners`/`fouls`/`shots` in raw_data? Football should have >40% with stat keys.
- League coverage: Are protected leagues (§SCAN.9) present? Are major tournaments (§SCAN.7) covered?
- Cross-source: Mismatches in team names between Flashscore and Scores24 are common (transliteration). Only flag kickoff time mismatches >1h.

Report findings to orchestrator with sport-specific context.
```

**Definition of done:**
- [ ] "TWO INVOCATION MODES" → "THREE INVOCATION MODES" with verification described
- [ ] Step 0 detects verification context and routes to Step 5
- [ ] Step 5 section exists with script command + interpretation guidance
- [ ] Football-specific interpretation includes stat key checks (corners/fouls/shots)
- [ ] File size increase ≤ 20 lines

---

### Task 3.2: Modify `bet-scanner-basketball.agent.md`

Same structure as Task 3.1 with basketball-specific interpretation:
- Trend: NBA schedule has natural off-days (Mon/Thu lighter). EU leagues have weekday-only schedules.
- Quality: Basketball events need `home_team` + `away_team`. Quality <85% = problem.
- Stat coverage: Check for `rebounds`/`assists`/`steals` in raw_data.
- League coverage: Check NBA, Euroleague, CBA, NBB presence when in season.

**Definition of done:**
- [ ] THREE INVOCATION MODES listed
- [ ] Step 0 routes verification context to Step 5
- [ ] Step 5 with basketball-specific interpretation (NBA schedule awareness, stat keys)
- [ ] File size increase ≤ 20 lines

---

### Task 3.3: Modify `bet-scanner-tennis.agent.md`

Same structure with tennis-specific interpretation:
- Trend: Tennis has dramatic day-to-day variation (Grand Slam week = 200+ matches, off-week = 30).
- Quality: Tennis uses player names (not team names) — `home_team` = player1, `away_team` = player2.
- Stat coverage: Only 3/7 stat keys populated (known gap). Check for `sets_won`/`games_won`.
- League coverage: Check Grand Slam, Masters 1000, ATP/WTA 500/250 presence.

**Definition of done:**
- [ ] THREE INVOCATION MODES listed
- [ ] Step 0 routes verification context to Step 5
- [ ] Step 5 with tennis-specific interpretation (tournament schedule variance, known stat key gap)
- [ ] File size increase ≤ 20 lines

---

### Task 3.4: Modify `bet-scanner-volleyball.agent.md`

Same structure with volleyball-specific interpretation:
- Trend: Volleyball has seasonal patterns. European leagues Oct-May, South American Jun-Nov.
- Quality: Quality <80% expected due to fewer sources.
- Stat coverage: Volleyball has ZERO enrichment (known gap #2). Flag but don't fail.
- League coverage: Check SuperLiga, V-League, CEV Champions League presence when active.

**Definition of done:**
- [ ] THREE INVOCATION MODES listed
- [ ] Step 0 routes verification context to Step 5
- [ ] Step 5 with volleyball-specific interpretation (known enrichment gap acknowledgment)
- [ ] File size increase ≤ 20 lines

---

### Task 3.5: Modify `bet-scanner-hockey.agent.md`

Same structure with hockey-specific interpretation:
- Trend: NHL regular season Oct-Apr, playoffs Apr-Jun. KHL Sep-Apr.
- Quality: Hockey events need `home_team` + `away_team`. Quality <85% = problem.
- Stat coverage: Check for `shots`/`hits`/`powerplay` in raw_data.
- League coverage: Check NHL, KHL, SHL, Liiga presence when active.

**Definition of done:**
- [ ] THREE INVOCATION MODES listed
- [ ] Step 0 routes verification context to Step 5
- [ ] Step 5 with hockey-specific interpretation (seasonal awareness, stat keys)
- [ ] File size increase ≤ 20 lines

---

## Phase 4: Integration Updates [MODIFY]

### Task 4.1: Add verification checks to `bet-scan.prompt.md`

**Location:** The "Self-Verification" table at the bottom of the file (V-S1-01 to V-S1-15).

**Content to add (4 rows):**

| # | Check | Gate |
|---|-------|------|
| 16 | Phantom fixtures (past kickoff + duplicates) < 10 | Required |
| 17 | Per-sport trend deviation < 40% vs 7-day average | Required |
| 18 | Event data quality > 80% (non-empty team names + kickoff) | Required |
| 19 | Cross-source consistency > 85% (matching team names + kickoff) | Advisory |

**Also update** the Pass/Fail section to reflect 19 total checks:
- **19/19** → S1 PASSED
- **15-18** → S1 CONDITIONAL
- **<15** → S1 FAILED

**Definition of done:**
- [ ] V-S1-16 through V-S1-19 added to self-verification table
- [ ] Pass/Fail thresholds updated to reflect 19 checks
- [ ] Checks reference verification script output metrics

---

### Task 4.2: Add `s1_verify` step to `scripts/agent_protocol.py`

**Location:** `STEP_AGENT_CONFIG` dict, after `s1e_shortlist` entry.

**Content to add:**
```python
"s1_verify": {
    "agent": "bet-scanner",
    "task": "Deep verification of scan results: trend analysis vs 7-day history, phantom fixture detection, per-event data quality validation, cross-source consistency, league coverage gaps",
    "required_input": ["scan_verification_{date}.json"],
    "output_metrics": ["phantom_fixtures", "event_quality_pct", "trend_deviations", "cross_source_match_pct", "missing_leagues"],
    "think_in_the_middle": True,
    "error_handling": "ERROR_HANDLING_PROTOCOL",
    "validate_output": True,
    "detailed_instructions": [
        "1. Run verify_scan_results.py --date {date} --verbose",
        "2. Parse AGENT_SUMMARY — check verdict (OK/PARTIAL/FAILED)",
        "3. Review per_sport breakdown — flag sports with trend anomalies or quality < 80%",
        "4. Check phantom fixtures count — > 10 requires investigation",
        "5. Check cross-source mismatches — investigate kickoff time conflicts",
        "6. Check missing historical leagues — may indicate source failure or seasonal end",
        "7. For flagged sports: dispatch per-sport agent in verification mode",
    ],
    "recovery_actions": [
        "If trend anomaly → check if schedule-related (weekday, off-season) vs source failure",
        "If phantom fixtures → check if events were already played (settle_on_finish may have missed)",
        "If quality < 80% → specific source may be returning malformed data — check source_health",
        "If missing leagues → targeted re-scan for that league's source URLs",
    ],
},
```

**Also add** `verify_scan_results.py` to the `STRUCTURED_OUTPUT_PROTOCOL.scripts_with_verbose` list.

**Definition of done:**
- [ ] `s1_verify` key exists in `STEP_AGENT_CONFIG`
- [ ] All fields populated: agent, task, required_input, output_metrics, detailed_instructions, recovery_actions
- [ ] `verify_scan_results.py` listed in `scripts_with_verbose`

---

## Phase 5: Tests [CREATE]

### Task 5.1: `tests/test_verify_scan_results.py`

**Purpose:** Unit tests for the 7 verification functions + integration test for main().

**Test strategy:**
- Use in-memory SQLite DB with schema from `src/bet/db/schema.sql`
- Seed test data: scan_results, scan_run_stats, fixtures, source_health for 7 days
- Test each check function independently:
  1. `test_trend_analysis_normal` — no deviation → status OK
  2. `test_trend_analysis_anomaly` — 50% drop → flags sport
  3. `test_phantom_fixtures_none` — all kickoffs in future → 0 phantoms
  4. `test_phantom_fixtures_detected` — seed past-kickoff events → detected
  5. `test_event_quality_clean` — all fields populated → 100% quality
  6. `test_event_quality_gaps` — missing team names → quality < 100%
  7. `test_cross_source_consistency` — matching data → high match%
  8. `test_cross_source_mismatch` — different kickoff times → flagged
  9. `test_sport_specific_football` — with/without stat keys in raw_data
  10. `test_league_coverage_gap` — league present 7 days but missing today
  11. `test_source_health_degraded` — high consecutive failures → flagged
- Integration: `test_main_full_run` — run main() with test DB, verify AGENT_SUMMARY JSON parseable

**Definition of done:**
- [ ] 11+ unit tests covering all 7 check functions
- [ ] 1 integration test for end-to-end execution
- [ ] All tests pass with `pytest tests/test_verify_scan_results.py -v`
- [ ] Tests use in-memory DB seeded from schema.sql (no external dependencies)

---

## Task Dependency Graph

```
Phase 1 (Task 1.1: create script)
    │
    ├──► Phase 2 (Task 2.1: orchestrator agent)
    │
    ├──► Phase 3 (Tasks 3.1-3.5: per-sport agents) — all 5 can be done in parallel
    │
    ├──► Phase 4 (Tasks 4.1-4.2: prompt + protocol) — can be done in parallel with Phase 3
    │
    └──► Phase 5 (Task 5.1: tests) — can be done in parallel with Phases 2-4
```

**Critical path:** Phase 1 → Phase 2 (script must exist before orchestrator references it)

Phases 3, 4, 5 are independent of each other and can be implemented in parallel after Phase 1.

---

## Security Considerations

- All SQL queries use parameterized arguments (`?` placeholders) — no f-string interpolation into SQL
- Script reads from local SQLite DB only — no external network calls
- Output files written to `betting/data/` (existing data directory) — no new filesystem locations
- No user-supplied input flows into SQL queries beyond validated `--date` and `--sport` CLI args

## Quality Assurance

- Script follows R19 structured output protocol: `AGENT_SUMMARY:{json}`, `--verbose`, exit codes 0/1/2
- Script follows R2 DB-first approach: `from bet.db.connection import get_db`
- Agent modifications follow instruction-design-lessons: compact sections, no file size doubling
- All agents follow agent-execution-protocol.instructions.md 4-step cycle for script output analysis
- Unit tests cover all 7 verification functions with positive and negative cases
- Integration test validates end-to-end AGENT_SUMMARY output is valid JSON
