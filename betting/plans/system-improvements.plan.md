# Betting Analysis System Improvements — Implementation Plan

## Task Details

| Field            | Value                                                                                                |
| ---------------- | ---------------------------------------------------------------------------------------------------- |
| Title            | Automated Validation, Statistical Computation, Instruction Deduplication, and Orchestration Upgrades |
| Description      | Address the 6 key system problems: fragile data collection, S3 validation errors, context overflow, sequential orchestration, no automated QA, and no source health tracking |
| Priority         | High — S3 structural violations are the #1 pipeline failure category                                 |
| Related Research | `betting/plans/s3-enforcement-hardening.md` (partially overlaps with Task 1.1)                       |

## Proposed Solution

A three-phase improvement plan that introduces **scripted validation** to replace LLM-based mechanical verification, a **deterministic safety score engine** to eliminate manual computation errors, and **instruction deduplication** to reduce context window pressure. The plan also adds a **stats cache** for cross-session data persistence, **parallel step support** in the orchestrator, and **source health tracking** for adaptive fallback chains.

### Architecture Overview

```
┌────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR                            │
│  S0 → S1 → S2 → ┬─ S3 ──┬─→ S5 ──┬─→ S7 → S3B → S8        │
│                  │       │        │                            │
│                  └─ S4 ──┘  S6 ───┘                           │
│                  (parallel)  (parallel)                         │
│                                                                │
│  NEW: validate_s3_output.py called after S3 (replaces LLM QA) │
│  NEW: validate_coupons.py called after S8 (replaces LLM QA)   │
│  NEW: check_48h_repeats.py called during S7 (gate #14)        │
│  NEW: compute_safety_scores.py called during S3 (algorithmic) │
│  NEW: source_health.py appended after S1 (historical log)     │
└────────────────────────────────────────────────────────────────┘

Data Flow (new scripts):
  S3 markdown output → validate_s3_output.py → PASS/FAIL per candidate
  Stats JSON input   → compute_safety_scores.py → §3.0 ranking table (markdown)
  Scan session       → source_health.py → source_health_log.csv (append)
  Picks-ledger.csv   → check_48h_repeats.py → warnings for shortlist
  Coupon .md files    → validate_coupons.py → PASS/FAIL per coupon

Cache Layer (new):
  betting/data/stats_cache/{sport}/{team_slug}.json
  TTL: 24h for form data, 7d for H2H data
  Populated by: build_stats_cache.py (Playwright + adapters)
  Consumed by: bet-statistician agent (read before web-fetching)
```

## Current Implementation Analysis

### Already Implemented

- `scripts/settle_on_finish.py` — CSV-based settlement with Sofascore/Flashscore polling, auto-settles ML/totals/BTTS/DC
- `scripts/analyze_betclic_learning.py` — Betclic history analysis with market categorization (MARKET_CATEGORIES dict with 30+ Polish→English mappings)
- `scripts/fetch_odds_api.py` — The-Odds-API integration, sport key mapping, credit tracking
- `scripts/scan_events.py` — Multi-URL scanning with sport detection from URL patterns, adapter-based parsing
- `scripts/fetch_with_playwright.py` — Playwright fetcher with cookie selectors, storage state, retry logic, HTML snapshots
- `scripts/aggregate_and_select.py` — Fuzzy team name matching (SequenceMatcher), price gap calculation, tier classification
- `scripts/historical_learning.py` — Picks-ledger analysis: per-sport, per-market, per-day hit rates
- `scripts/run_session.sh` — Session orchestrator with `--date`, `--session`, `--skip-settle`, `--verbose` flags
- `scripts/run_full_scan_and_prepare.sh` — Full scan pipeline (venv, deps, Playwright, smoke test, multi-sport scan, tipster prefetch, aggregation)
- `scripts/adapters/` — 5 adapters: raw, flashscore, sofascore, oddsportal, betclic with `parse(html, url) -> List[Dict]` interface
- `scripts/requirements.txt` — requests, beautifulsoup4, playwright>=1.45.0, lxml
- `scripts/site_selectors.json` — Cookie consent selectors for 15+ domains
- `betting/journal/picks-ledger.csv` — 24-column ledger (betting_day, version, pick_id, event, sport, market, status, pnl, etc.)
- `betting/journal/coupons-ledger.csv` — 15-column ledger (coupon_id, variant, selections_count, pick_ids, combined_odds, etc.)
- `betting/data/scan_summary.json` — Extracted events from scan (home, away, time, source_url, sport)
- `betting/data/scan_errors.json` — Session-scoped error log (url, error message)
- `config/betting_config.json` — Bankroll, daily cap, sports lists, odds range, coupon rules

### To Be Modified

- `analysis-methodology.instructions.md` (750 lines) — Remove duplicated content that exists in skills/sport-protocols. Add cross-references. Target: ~450 lines.
- `orchestrate-betting-day.prompt.md` — Replace LLM-based "mechanical verification" with script calls to `validate_s3_output.py` and `validate_coupons.py`. Add parallel step support for S3+S4 and S5+S6. Add adaptive pass protocol.
- `bet-statistician.agent.md` (131 lines) — Add instructions to call `compute_safety_scores.py` after raw data collection. Add stats cache read step. Trim constraint duplication.
- `bet-builder.agent.md` (106 lines) — Add instructions to call `validate_coupons.py` as part of §S8.FINAL.
- `bet-orchestrator.agent.md` (272 lines) — Add parallel delegation support. Add script-based validation calls. Trim duplicated constraints.
- `bet-scanner.agent.md` (108 lines) — Add source_health.py call after scan. Add stats cache population trigger.
- `run_session.sh` — Add stats cache build step. Add source health logging call.
- All 8 agent files — Replace inline constraint repetitions with references to instruction files.

### To Be Created

- `scripts/validate_s3_output.py` — S3 markdown structural validator
- `scripts/validate_coupons.py` — Coupon markdown structural + arithmetic validator
- `scripts/check_48h_repeats.py` — 48h repeat pick detector from ledger
- `scripts/compute_safety_scores.py` — Deterministic §3.0 safety score calculator
- `scripts/build_stats_cache.py` — Stats fetcher with persistent file-based cache
- `scripts/source_health.py` — Source health tracker with CSV append
- `betting/data/stats_cache/` — Cache directory structure

## Open Questions

| #   | Question                                                                                  | Answer                                                                                                          | Status      |
| --- | ----------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ----------- |
| 1   | Should `validate_s3_output.py` exit non-zero on failure or just output JSON?              | Output JSON `{candidates: [{name, status, errors}]}` + exit code 1 if ANY candidate fails. Orchestrator reads JSON. | ✅ Resolved |
| 2   | Should `compute_safety_scores.py` read from cache or accept JSON stdin?                   | Accept JSON file path as arg (structured stats). Can also read from cache if `--from-cache` flag passed.          | ✅ Resolved |
| 3   | Should the stats cache use SQLite or flat JSON files?                                     | Flat JSON files per team — simpler, no new dependency, easy to inspect/debug. One file per team per sport.        | ✅ Resolved |
| 4   | Should parallel S3+S4 use subagents or sequential-thinking branches?                      | Subagents via `agent/runSubagent` — the orchestrator already has this tool. S3→bet-statistician, S4→bet-scout run in parallel. | ✅ Resolved |
| 5   | How should the adaptive pass protocol decide "zero critical errors"?                      | `validate_s3_output.py` output. If all candidates PASS and V10e matrix complete → skip to Pass 4. Any FAIL → Pass 2. | ✅ Resolved |
| 6   | Should deduplication preserve backward compatibility for existing sessions?                | Yes. All instruction changes are content-only (no structural/format changes). Agents reference the same file paths. | ✅ Resolved |
| 7   | What Playwright endpoints should `build_stats_cache.py` target?                           | Flashscore H2H tab, Flashscore team stats, Sofascore team stats, TennisAbstract player pages. Use existing `fetch_with_playwright.fetch()`. | ✅ Resolved |

## Implementation Plan

---

### Phase 1: Automated Validation Scripts (HIGH PRIORITY)

> **Goal:** Replace all LLM-based structural verification with deterministic scripts. This is the highest-impact change because S3 structural violations are the #1 pipeline failure.
>
> **Dependencies:** None — these scripts are standalone and can be tested immediately.

---

#### Task 1.1 - [CREATE] `scripts/validate_s3_output.py` — S3 Output Structural Validator

**Complexity:** LARGE

**Description:** A Python script that parses the `{date}_s3_deep_stats.md` markdown file and validates every candidate against the §3.0e template requirements. The orchestrator calls this script AFTER receiving S3 output from bet-statistician, INSTEAD of doing LLM-based "mechanical verification." Any FAIL result triggers a targeted re-run of the failing candidate.

**Input:** Path to S3 markdown file (e.g., `betting/data/20260428_s3_deep_stats.md`)

**Output:** JSON to stdout + exit code:
```json
{
  "file": "20260428_s3_deep_stats.md",
  "total_candidates": 12,
  "passed": 10,
  "failed": 2,
  "candidates": [
    {
      "name": "Football — Liverpool vs Arsenal | Premier League | 16:30",
      "status": "PASS",
      "sections_found": ["§S3.1","§S3.2","§S3.3","§S3.4","§S3.5","§S3.6","§S3.7","§S3.8","§S3.9","§S3.10"],
      "errors": []
    },
    {
      "name": "Tennis — Medvedev vs Cobolli | ATP Madrid | 20:10",
      "status": "FAIL",
      "sections_found": ["§S3.1","§S3.2","§S3.3","§S3.4","§S3.5","§S3.8"],
      "errors": [
        "MISSING: §S3.6 (Injury/Suspension Check)",
        "MISSING: §S3.7 (Top 3 Markets)",
        "MISSING: §S3.9 (Sources Used)",
        "MISSING: §S3.10 (Analysis Depth Proof)",
        "BANNED_WORD: §S3.5 cell contains 'checked' as sole content",
        "INVALID_SAFETY: §S3.3 row 2 safety value 'good' is not a decimal 0.00-1.00"
      ]
    }
  ]
}
```

**Key functions:**
- `parse_candidates(md_text: str) -> list[dict]` — Split markdown by `══ CANDIDATE:` markers, extract candidate name and body
- `check_sections(body: str) -> tuple[list[str], list[str]]` — Find §S3.1-§S3.10 markers, return (found, missing)
- `check_banned_words(body: str) -> list[str]` — Parse all markdown table cells (regex: `\|[^|]+\|`), check if any cell's stripped content matches banned words list: `{"checked", "verified", "confirmed", "good", "fine", "ok", "done", "yes", "—", "n/a", "see above"}`
- `check_ranking_table(body: str, sport: str) -> list[str]` — Find §S3.3 table, verify: ≥3 data rows (≥4 if sport is football), Safety column values are floats 0.00-1.00, no empty cells
- `check_three_way(body: str) -> list[str]` — Find §S3.4 table, verify 3 data rows (L10, H2H, L5) with numeric values and SUPPORTS/CONFLICTS verdict
- `check_sources_table(body: str) -> list[str]` — Find §S3.9 table, verify ≥2 data rows
- `detect_sport(candidate_name: str) -> str` — Extract sport from the `══ CANDIDATE: [Sport] —` pattern

**Dependencies:** Python stdlib only (re, json, sys, pathlib, argparse). No pip dependencies.

**CLI:**
```bash
python3 scripts/validate_s3_output.py betting/data/20260428_s3_deep_stats.md
python3 scripts/validate_s3_output.py --format text betting/data/20260428_s3_deep_stats.md  # human-readable
python3 scripts/validate_s3_output.py --strict betting/data/20260428_s3_deep_stats.md  # exit 1 on any warning too
```

**Definition of Done:**

- [ ] Script exists at `scripts/validate_s3_output.py` and is executable
- [ ] Correctly parses a real S3 file (e.g., `2026-04-28_s3_deep_stats.md`) and produces JSON output
- [ ] Detects all 10 section markers (§S3.1-§S3.10) — MISSING marker = error
- [ ] Detects all 11 banned words as sole cell content (case-insensitive) — each = error
- [ ] Validates §S3.3 ranking table row count (≥3 general, ≥4 football) and safety score format (decimal 0.00-1.00)
- [ ] Validates §S3.4 three-way table has 3 rows with numeric values
- [ ] Validates §S3.9 sources table has ≥2 rows
- [ ] Returns exit code 0 if all candidates PASS, exit code 1 if any FAIL
- [ ] `--format text` flag produces human-readable error list
- [ ] Runs against existing `betting/data/20260428_s3_deep_stats.md` without crashing (may report errors — that validates detection works)

---

#### Task 1.2 - [CREATE] `scripts/validate_coupons.py` — Coupon File Structural + Arithmetic Validator

**Complexity:** MEDIUM

**Description:** A Python script that parses coupon markdown files (`betting/coupons/YYYY-MM-DD*.md`) and validates structural integrity and arithmetic correctness. Called by bet-builder agent after §S8.FINAL, and by the orchestrator as a gate before publishing.

**Input:** Path to coupon markdown file(s)

**Output:** JSON to stdout:
```json
{
  "file": "2026-04-28-v3.md",
  "coupons_found": 8,
  "passed": 7,
  "failed": 1,
  "checks": [
    {
      "coupon_id": "CP-20260428-LR1",
      "status": "PASS",
      "combined_odds_stated": 2.43,
      "combined_odds_computed": 2.44,
      "tolerance_pct": 0.41,
      "legs": 2,
      "unique_events": true,
      "pick_ids_valid": true,
      "polish_descriptions": true,
      "errors": []
    },
    {
      "coupon_id": "CP-20260428-HR2",
      "status": "FAIL",
      "errors": [
        "ARITHMETIC: stated combined odds 5.12 but computed 4.87 (diff 5.1%, tolerance ±2%)",
        "DUPLICATE_EVENT: 'Medvedev vs Cobolli' appears in CP-20260428-LR1 and CP-20260428-HR2 (core portfolio violation)"
      ]
    }
  ]
}
```

**Key functions:**
- `parse_coupon_tables(md_text: str) -> list[dict]` — Extract coupon tables from markdown (regex for `| # |` table headers), parse each row for coupon_id, odds per leg, combined_odds, stake
- `verify_arithmetic(legs_odds: list[float], stated_combined: float, tolerance: float = 0.02) -> tuple[bool, float, float]` — Multiply leg odds, compare to stated. Return (pass, computed, diff_pct)
- `check_unique_events(coupons: list[dict], section: str) -> list[str]` — For core portfolio coupons only (not COMBO-prefixed), verify no event appears in more than one coupon
- `check_pick_ids(coupons: list[dict], ledger_path: Path) -> list[str]` — Cross-reference pick_ids from coupon file against picks-ledger.csv. Flag any missing IDs.
- `check_polish_descriptions(coupons: list[dict]) -> list[str]` — Verify each leg has a Polish description (heuristic: contains Polish characters or known Polish betting terms like "powyżej", "poniżej", "bramek", "gemów", "rzutów rożnych")

**Dependencies:** Python stdlib only. Reads `betting/journal/picks-ledger.csv` for pick_id cross-reference.

**CLI:**
```bash
python3 scripts/validate_coupons.py betting/coupons/2026-04-28-v3.md
python3 scripts/validate_coupons.py betting/coupons/2026-04-28*.md  # validate all versions
```

**Definition of Done:**

- [ ] Script exists at `scripts/validate_coupons.py` and is executable
- [ ] Correctly parses coupon tables from real coupon markdown files
- [ ] Verifies combined odds arithmetic (multiply all legs, ±2% tolerance) for every coupon
- [ ] Detects duplicate events across core portfolio coupons (COMBO-prefixed coupons exempt)
- [ ] Cross-references pick_ids against picks-ledger.csv and reports missing IDs
- [ ] Checks for Polish description presence in each leg
- [ ] Returns exit code 0 if all coupons PASS, exit code 1 if any FAIL
- [ ] Runs against existing coupon files (e.g., `2026-04-28-v3.md`) without crashing

---

#### Task 1.3 - [CREATE] `scripts/check_48h_repeats.py` — 48-Hour Repeat Pick Detector

**Complexity:** SMALL

**Description:** A script that reads `picks-ledger.csv` and identifies any picks in the last 48 hours with the same team+market combination that resulted in a loss. These are flagged for the S7 gate (§7.5 point #14: "48h repeat check — same team+market lost → HARD REJECT"). Currently this check is done by the LLM, which sometimes misses repeats.

**Input:** Current shortlist (optional, as JSON or team names on command line). Without input, outputs all recent losses.

**Output:** JSON to stdout:
```json
{
  "window_hours": 48,
  "repeats_found": 2,
  "warnings": [
    {
      "team": "Liverpool",
      "market": "corners OVER 9.5",
      "lost_on": "2026-04-27",
      "pick_id": "PK-20260427-03",
      "days_ago": 1,
      "action": "HARD REJECT per §7.5 #14"
    }
  ]
}
```

**Key functions:**
- `load_recent_losses(ledger_path: Path, hours: int = 48) -> list[dict]` — Read picks-ledger.csv, filter to status=lost within last 48h from now (Europe/Warsaw timezone)
- `normalize_team(name: str) -> str` — Lowercase, strip FC/SC/AC suffixes, collapse whitespace (reuse pattern from `aggregate_and_select.py`)
- `normalize_market(market: str) -> str` — Lowercase, strip whitespace, normalize "O/U" variants
- `find_repeats(shortlist_teams: list[str], recent_losses: list[dict]) -> list[dict]` — Match team names (fuzzy, SequenceMatcher ≥0.75) AND market type overlap

**Dependencies:** Python stdlib + existing `aggregate_and_select.normalize()` pattern. No new pip dependencies.

**CLI:**
```bash
python3 scripts/check_48h_repeats.py                                    # show all 48h losses
python3 scripts/check_48h_repeats.py --teams "Liverpool,Arsenal"        # check specific teams
python3 scripts/check_48h_repeats.py --shortlist betting/data/20260428_s2_shortlist.md  # parse shortlist file
```

**Definition of Done:**

- [ ] Script exists at `scripts/check_48h_repeats.py` and is executable
- [ ] Reads `betting/journal/picks-ledger.csv` and filters to losses within 48h
- [ ] Correctly normalizes team names and market types for matching
- [ ] Outputs JSON with warnings for each repeat (team, market, lost_on, pick_id)
- [ ] Supports `--teams` flag for targeted checking
- [ ] Handles empty ledger or no recent losses gracefully (outputs `repeats_found: 0`)

---

### Phase 2: Statistical Computation + Data Persistence (HIGH PRIORITY)

> **Goal:** Move safety score computation from LLM to deterministic script. Add persistent stats cache to avoid re-fetching identical H2H data across sessions.
>
> **Dependencies:** Phase 1 (validation scripts provide the quality gate that the computation engine feeds into).

---

#### Task 2.1 - [CREATE] `scripts/compute_safety_scores.py` — Deterministic §3.0 Safety Score Calculator

**Complexity:** LARGE

**Description:** Given structured statistical data as JSON, this script computes the §3.0 ranking table deterministically. The bet-statistician agent collects raw data (via web-fetch or cache), structures it into the input JSON format, and calls this script to get a verified ranking table. This eliminates the most error-prone step: LLM-computed safety scores.

**Input:** JSON file with structured stats for one candidate:
```json
{
  "sport": "football",
  "team_a": "Liverpool",
  "team_b": "Arsenal",
  "competition": "Premier League",
  "markets": [
    {
      "name": "Corners Total O/U",
      "line": 9.5,
      "team_a_l10": [11, 8, 13, 10, 9, 12, 7, 11, 10, 14],
      "team_b_l10": [6, 9, 8, 7, 10, 5, 8, 9, 7, 6],
      "h2h_values": [12, 9, 14, 11, 10],
      "team_a_l5": [12, 7, 11, 10, 14],
      "team_b_l5": [10, 5, 8, 9, 7],
      "source": "TotalCorner + SoccerStats"
    },
    {
      "name": "Fouls Total O/U",
      "line": 22.5,
      "team_a_l10": [12, 15, 11, 14, 13, 16, 10, 12, 14, 11],
      "team_b_l10": [14, 11, 13, 12, 15, 10, 13, 14, 11, 12],
      "h2h_values": [28, 25, 30, 27, 26],
      "team_a_l5": [16, 10, 12, 14, 11],
      "team_b_l5": [10, 13, 14, 11, 12],
      "source": "SoccerStats"
    }
  ]
}
```

**Output:** JSON with computed ranking + markdown table:
```json
{
  "candidate": "Liverpool vs Arsenal",
  "sport": "football",
  "ranking": [
    {
      "rank": 1,
      "market": "Fouls Total O/U",
      "team_a_avg": 12.8,
      "team_b_avg": 12.5,
      "combined_avg": 25.3,
      "h2h_avg": 27.2,
      "line": 22.5,
      "hit_rate_l10": "8/10",
      "hit_rate_h2h": "5/5",
      "safety_score": 0.80,
      "margin": 1.124,
      "source": "SoccerStats"
    }
  ],
  "three_way_check": {
    "market": "Fouls Total O/U",
    "l10_avg": 25.3,
    "h2h_avg": 27.2,
    "l5_avg": 24.3,
    "line": 22.5,
    "l10_direction": "OVER",
    "h2h_direction": "OVER",
    "l5_trend": "STABLE",
    "alignment": "3/3 SUPPORT"
  },
  "recommended_market": "Fouls Total O/U 22.5",
  "markdown_table": "| # | Market | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety | Source |\n..."
}
```

**Key functions:**
- `compute_hit_rate(values: list[float], line: float, direction: str) -> tuple[int, int]` — Count how many values are over/under the line. Direction inferred: if average > line → OVER, else UNDER. Returns (hits, total).
- `compute_safety_score(hit_rate_l10: float, hit_rate_h2h: float) -> float` — `min(hit_rate_l10, hit_rate_h2h)`, rounded to 2 decimal places.
- `compute_margin(avg: float, line: float, direction: str) -> float` — OVER: avg/line. UNDER: line/avg. Tiebreaker metric.
- `compute_three_way_check(l10_values: list, h2h_values: list, l5_values: list, line: float) -> dict` — Compute averages, determine direction vs line, assess alignment (3/3, 2/3, conflict).
- `rank_markets(markets: list[dict]) -> list[dict]` — Sort by safety_score DESC, margin DESC as tiebreaker.
- `generate_markdown_table(ranking: list[dict]) -> str` — Format as §S3.3-compatible markdown table.
- `validate_minimum_markets(ranking: list[dict], sport: str) -> list[str]` — Enforce ≥3 markets (≥4 for football). Return warnings.

**Sport-specific requirements embedded in the script:**
- Football: minimum 4 markets (fouls + cards + corners + shots per §3.1M)
- Tennis: combined game total direction (over vs under per player), surface filtering note
- Basketball: team totals take priority per hierarchy
- All sports: configurable minimum markets from a dict (sport → min_count)

**Dependencies:** Python stdlib only. No pip dependencies.

**CLI:**
```bash
python3 scripts/compute_safety_scores.py stats_input.json                    # compute from file
python3 scripts/compute_safety_scores.py stats_input.json --markdown         # output markdown only
python3 scripts/compute_safety_scores.py stats_input.json --validate-only    # validate input structure only
```

**Definition of Done:**

- [ ] Script exists at `scripts/compute_safety_scores.py` and is executable
- [ ] Correctly computes hit rates for OVER and UNDER directions from raw value arrays
- [ ] Safety score = `min(hit_rate_l10, hit_rate_h2h)` as decimal 0.00-1.00
- [ ] Three-way cross-check correctly identifies alignment (3/3, 2/3, conflict)
- [ ] Outputs sorted ranking table (highest safety first, margin as tiebreaker)
- [ ] Generates §S3.3-compatible markdown table string
- [ ] Enforces minimum market count per sport (football ≥4, all others ≥3)
- [ ] Input validation: rejects JSON with missing fields, empty arrays, non-numeric values
- [ ] Edge cases handled: all values same (hit rate 1.0 or 0.0), single H2H meeting, line exactly equals average

---

#### Task 2.2 - [CREATE] `scripts/build_stats_cache.py` — Persistent Stats Cache Builder

**Complexity:** LARGE

**Description:** Fetches team/player stats from Flashscore and Sofascore using the existing Playwright infrastructure (`fetch_with_playwright.fetch()`), and caches them in `betting/data/stats_cache/{sport}/{team_slug}.json`. Persists H2H data, team averages (L10, L5), and form across sessions with TTL-based expiration. The bet-statistician agent reads the cache before making fresh web requests, avoiding redundant fetching of the same team's data within the TTL window.

**Cache structure:**
```
betting/data/stats_cache/
├── football/
│   ├── liverpool.json
│   ├── arsenal.json
│   └── ...
├── tennis/
│   ├── medvedev-daniil.json
│   └── ...
└── basketball/
    └── ...
```

**Cache file format (per team/player):**
```json
{
  "team": "Liverpool",
  "sport": "football",
  "slug": "liverpool",
  "last_updated": "2026-04-28T08:30:00+02:00",
  "ttl_hours": 24,
  "form": {
    "l10_results": [...],
    "l5_results": [...],
    "home_stats": {...},
    "away_stats": {...}
  },
  "h2h": {
    "arsenal": {
      "last_updated": "2026-04-28T08:30:00+02:00",
      "ttl_hours": 168,
      "meetings": [...]
    }
  },
  "sources": ["flashscore.com", "sofascore.com"]
}
```

**Key functions:**
- `slugify(name: str) -> str` — Convert team/player name to filesystem-safe slug (`"FC Barcelona"` → `"fc-barcelona"`)
- `is_cache_valid(cache_file: Path, ttl_hours: int) -> bool` — Check if cache file exists and `last_updated` + TTL > now
- `fetch_team_form(team: str, sport: str) -> dict` — Use `fetch_with_playwright.fetch()` to get Flashscore team page, parse L10 results, compute averages. Uses existing adapter patterns.
- `fetch_h2h(team_a: str, team_b: str, sport: str) -> dict` — Fetch Flashscore H2H page between two teams, parse last 5-10 meetings with stat breakdowns per meeting
- `update_cache(sport: str, team: str, data: dict) -> Path` — Write/update JSON cache file
- `read_cache(sport: str, team: str) -> dict | None` — Read cached data if valid, return None if expired or missing
- `build_cache_for_shortlist(shortlist_path: Path) -> dict` — Parse shortlist file, extract all team names, fetch and cache stats for each. Returns summary of hits/misses.

**Dependencies:** `fetch_with_playwright` (existing), `adapters/flashscore_adapter` (existing), pathlib, json, datetime. No new pip dependencies.

**CLI:**
```bash
python3 scripts/build_stats_cache.py --shortlist betting/data/20260428_s2_shortlist.md    # cache all teams in shortlist
python3 scripts/build_stats_cache.py --team "Liverpool" --sport football                  # cache single team
python3 scripts/build_stats_cache.py --team "Liverpool" --opponent "Arsenal" --sport football  # cache + H2H
python3 scripts/build_stats_cache.py --expire-all                                         # clear all cache
python3 scripts/build_stats_cache.py --status                                             # show cache hit/miss stats
```

**Definition of Done:**

- [ ] Script exists at `scripts/build_stats_cache.py` and is executable
- [ ] Creates `betting/data/stats_cache/{sport}/` directory structure
- [ ] Writes per-team JSON cache files with `last_updated` and `ttl_hours` fields
- [ ] `is_cache_valid()` correctly compares timestamps and returns True/False
- [ ] Fetches team form data from Flashscore using existing Playwright infrastructure
- [ ] Fetches H2H data between two teams when `--opponent` is specified
- [ ] H2H data has separate TTL (168h / 7 days) from form data (24h)
- [ ] `--shortlist` flag parses the S2 shortlist markdown file and caches all team data
- [ ] `--status` flag shows cache hit/miss/expired counts per sport
- [ ] Handles Playwright failures gracefully (log error, continue to next team, don't crash)
- [ ] Does not re-fetch data that is within TTL window

---

#### Task 2.3 - [MODIFY] `bet-statistician.agent.md` — Integrate Computation Engine + Cache

**Complexity:** SMALL

**Description:** Update the bet-statistician agent definition to instruct it to: (1) read stats cache before web-fetching, (2) call `compute_safety_scores.py` after collecting raw data instead of manually computing safety scores, and (3) validate its own output structure before submission.

**Changes:**
- In `<approach>` section, add: "Before fetching any team's stats, check `betting/data/stats_cache/{sport}/{team_slug}.json`. If cache is valid (within TTL), use cached data instead of web-fetching."
- In `<tool-usage>` section, add: "After collecting raw stats for a candidate, structure them into the JSON input format and call `python3 scripts/compute_safety_scores.py` to get the deterministic §3.0 ranking table. Paste the script's markdown output directly into §S3.3."
- In `<constraints>` section, add: "Before submitting S3 output, call `python3 scripts/validate_s3_output.py` on your own output file. Fix any FAIL results before handing off to the orchestrator."
- Remove duplicated constraint text that restates §3.0 rules already in `analysis-methodology.instructions.md` — replace with: "Follows all §3.0-§3.0e rules from analysis-methodology.instructions.md."

**Definition of Done:**

- [ ] `bet-statistician.agent.md` references stats cache read as first step before web-fetching
- [ ] `bet-statistician.agent.md` references `compute_safety_scores.py` for §3.0 ranking
- [ ] `bet-statistician.agent.md` references `validate_s3_output.py` for self-validation
- [ ] Duplicated §3.0 rules in agent file replaced with cross-reference to methodology
- [ ] Agent file line count reduced (target: ~100 lines from current 131)

---

### Phase 3: Instruction Deduplication + Orchestration Improvements (MEDIUM PRIORITY)

> **Goal:** Reduce context window pressure by eliminating duplicated content across instructions/skills/agents. Add parallel step execution and adaptive pass protocol to the orchestrator.
>
> **Dependencies:** Phase 1 and 2 (validation scripts and computation engine must exist before orchestrator can reference them).

---

#### Task 3.1 - [MODIFY] `analysis-methodology.instructions.md` — Deduplicate to ~450 Lines

**Complexity:** MEDIUM

**Description:** The methodology file is 750 lines and contains content duplicated in skills and sport-analysis-protocols. Remove duplicated sections and replace with cross-references. The file should remain the single source of truth for the PIPELINE FLOW (S0→S8) and UNIVERSAL RULES, while sport-specific details and market ranking mechanics live in their dedicated files.

**Content to REMOVE (with replacement references):**

| Section | Lines (approx) | Duplicated In | Replacement |
|---------|----------------|---------------|-------------|
| §3.0b Bettable Statistical Markets table | ~30 lines | `bet-analyzing-statistics/SKILL.md` §3.0b + `sport-analysis-protocols.instructions.md` per-sport tables | Replace with: `> See bet-analyzing-statistics SKILL.md §3.0b for the full bettable markets table.` |
| Market Hierarchy table (bottom section) | ~40 lines | `bet-analyzing-statistics/SKILL.md` market hierarchy + each sport's `§3.XM` table in sport-protocols | Replace with: `> See sport-analysis-protocols.instructions.md for per-sport market hierarchies.` |
| §3.0e full candidate template (~80 lines of code block) | ~80 lines | This was added by s3-enforcement-hardening plan. Keep a COMPACT version (section list + 3 key validation rules) | Reduce to ~20-line summary: list of 10 section markers + 7 validation rules (no full template code block). Template code block moves to `bet-analyzing-statistics/SKILL.md`. |
| §3.1-§3.14 sport-specific stat tables within STEP 3 | ~20 lines (partial duplicates) | Fully specified in `sport-analysis-protocols.instructions.md` §3.1-§3.14 | Already has cross-reference `> Load sport-analysis-protocols.instructions.md`. Remove inline football/tennis examples that duplicate sport-protocols content. |
| Common Mistakes #1-#20 (partially duplicated in Zero Tolerance Shield) | ~10 lines overlap | Zero Tolerance Shield entries #1-#18 cover the same failures | Merge: remove Common Mistakes entries that are exact duplicates of ZT entries. Keep unique entries only. |

**Content to KEEP (these are unique to methodology and define the pipeline):**
- Ultimate Rule (5 lines)
- Sport Tiers table (10 lines)
- Scanning Mandate (30 lines)
- Step 0-8 headings with gate conditions (pipeline flow)
- §3.0, §3.0c, §3.0d (core ranking rules — NOT the tables, just the algorithm)
- V1-V10 validation checklist (compact, references skills for details)
- Zero Tolerance Shield (unique failure log)
- Common Mistakes (unique entries only)

**Target:** ~450 lines (reduction of ~300 lines / 40%)

**Definition of Done:**

- [ ] `analysis-methodology.instructions.md` is ≤480 lines
- [ ] All removed content has a cross-reference comment pointing to the canonical location
- [ ] §3.0b bettable markets table replaced with reference to SKILL.md
- [ ] Market hierarchy table replaced with reference to sport-analysis-protocols
- [ ] §3.0e template reduced to compact summary (section markers + validation rules, no full code block)
- [ ] No orphaned references (every cross-reference target file and section actually exists)
- [ ] Existing pipeline flow (S0→S8) is preserved unchanged
- [ ] Common Mistakes list has no entries duplicating Zero Tolerance Shield entries

---

#### Task 3.2 - [MODIFY] All 8 Agent Definitions — Remove Duplicated Constraints

**Complexity:** MEDIUM

**Description:** Each agent file repeats constraints from the methodology. Replace inline constraint blocks with references. The agent file should contain ONLY: (1) role description, (2) approach/personality, (3) skills to load, (4) tools to use, (5) agent-specific constraints that are NOT in methodology, and (6) output format (if any).

**Per-agent changes:**

| Agent | Current Lines | Duplicated Content to Remove | Target Lines |
|-------|--------------|------------------------------|--------------|
| `bet-orchestrator.agent.md` | 272 | Session parity rule (in methodology), 4-pass protocol details (in methodology + prompt), knowledge domain map (keep — unique) | ~200 |
| `bet-statistician.agent.md` | 131 | §3.0 ranking protocol summary (in methodology), statistical market preference (in methodology), sport-specific hints (in sport-protocols) | ~90 |
| `bet-challenger.agent.md` | 134 | 17-point gate list (in methodology §7.5), red flag lists (in sport-protocols §7.3), bear case template (in methodology §7.1) | ~90 |
| `bet-builder.agent.md` | 106 | Coupon file structure (in betting-artifacts.instructions.md), V10e template (in methodology V10e), unique-event rule (in methodology §8.1) | ~80 |
| `bet-scanner.agent.md` | 108 | Scanning mandate (in methodology), minimum thresholds (in methodology), 14-sport checklist (in methodology) | ~75 |
| `bet-scout.agent.md` | 105 | Tipster fallback chains (in methodology §4), blocked sites (in methodology §4) | ~70 |
| `bet-valuator.agent.md` | 81 | EV formula (in methodology §5), Kelly formula (in methodology §5), price gap thresholds (in config) | ~65 |
| `bet-settler.agent.md` | 83 | Settlement rules (in methodology §0), CLV formula (in methodology §0.6) | ~65 |

**Standard replacement pattern for each agent:**
```markdown
<domain-standards>
Follows all constraints from analysis-methodology.instructions.md.
Additionally:
- [agent-specific constraint 1]
- [agent-specific constraint 2]
</domain-standards>
```

**Definition of Done:**

- [ ] Each agent file only contains constraints UNIQUE to that agent (not restated from methodology)
- [ ] Each agent file has a `Follows all constraints from analysis-methodology.instructions.md` reference
- [ ] Total agent file lines reduced from 1020 to ≤735 (~28% reduction)
- [ ] No behavioral change — agents still follow all the same rules via instruction file loading
- [ ] Each agent still lists correct skills and tools

---

#### Task 3.3 - [MODIFY] `orchestrate-betting-day.prompt.md` — Script-Based Validation + Parallel Steps + Adaptive Passes

**Complexity:** MEDIUM

**Description:** Update the orchestration prompt to: (1) call validation scripts instead of LLM-based mechanical verification, (2) support parallel execution of S3+S4 and S5+S6, and (3) implement adaptive pass protocol that skips unnecessary passes.

**Change 1 — Script-based validation:**
Replace the existing "Structural Verification after S3" block (which instructs the LLM to manually check sections/banned words/counts) with:
```markdown
After receiving S3 output, run:
```bash
python3 scripts/validate_s3_output.py betting/data/{date}_s3_deep_stats.md
```
If any candidate has status FAIL → return the specific errors to bet-statistician for targeted fix. Only candidates with PASS proceed to S4+.
```

Similarly, after S8:
```markdown
After receiving coupon file, run:
```bash
python3 scripts/validate_coupons.py betting/coupons/{date}*.md
```
Any FAIL → return to bet-builder for targeted fix.
```

**Change 2 — Parallel S3+S4 and S5+S6:**
Replace sequential delegation with parallel subagent calls:
```markdown
## S3+S4 (PARALLEL)
Delegate simultaneously:
- S3 → bet-statistician (deep stats for all shortlisted candidates)
- S4 → bet-scout (tipster deep-dive for all shortlisted candidates)
Both receive the S2 shortlist as input. Neither depends on the other's output.
Wait for BOTH to complete before proceeding.

## S5+S6 (PARALLEL)
Delegate simultaneously:
- S5 → bet-valuator (odds + EV for all candidates)
- S6 → bet-challenger (context + upset risk for all candidates)
Both receive S3+S4 merged output as input. Neither depends on the other's output.
Wait for BOTH to complete before proceeding.
```

**Change 3 — Adaptive pass protocol:**
Replace fixed 4-pass with:
```markdown
## ADAPTIVE PASS PROTOCOL
After Pass 1:
- Run `python3 scripts/validate_s3_output.py` + `python3 scripts/validate_coupons.py`
- If ZERO critical errors (all candidates PASS, all coupons PASS, V10e complete) → SKIP to Pass 4 (Final)
- If ONLY non-critical errors (warnings, minor fixes) → do Pass 2 (Targeted Fixes) then Pass 4
- If critical errors (FAIL candidates, arithmetic errors, missing sections) → full Pass 2 → Pass 3 → Pass 4
This eliminates 2 unnecessary passes when the pipeline produces clean output on the first run.
```

**Definition of Done:**

- [ ] LLM-based "mechanical verification" blocks replaced with script calls
- [ ] S3+S4 documented as parallel delegation (both from S2 shortlist)
- [ ] S5+S6 documented as parallel delegation (both from S3+S4 output)
- [ ] Adaptive pass protocol implemented (0 errors → skip to Pass 4, warnings → Pass 2+4, critical → full 4-pass)
- [ ] Pipeline diagram updated to show parallel branches
- [ ] No other changes to the prompt (preserve all existing gate conditions, session types, etc.)

---

#### Task 3.4 - [CREATE] `scripts/source_health.py` — Persistent Source Health Tracker

**Complexity:** SMALL

**Description:** After each scan session, appends source health data to `betting/data/source_health_log.csv`. The scanner agent reads this file before starting to prioritize sources that have been reliable recently and deprioritize chronically failing sources.

**Input:** `betting/data/scan_errors.json` (session-scoped) + `betting/data/scan_summary.json` (session-scoped)

**Output:** Appends rows to `betting/data/source_health_log.csv`:
```csv
date,source_name,sport,status,response_time_ms,events_extracted,error_message
2026-04-28,flashscore.com,football,ok,1200,45,
2026-04-28,betexplorer.com,snooker,fail,0,0,Empty or too-short response (39 chars)
2026-04-28,sofascore.com,tennis,ok,3400,12,
```

**Key functions:**
- `parse_scan_results(summary_path: Path, errors_path: Path) -> list[dict]` — Merge scan_summary.json (successful fetches) with scan_errors.json (failures) into a unified source health record per domain+sport
- `append_to_log(log_path: Path, records: list[dict])` — Append new rows to CSV (create with headers if file doesn't exist)
- `get_source_reliability(log_path: Path, days: int = 7, source: str = None) -> dict` — Query the log for recent reliability stats: success_rate, avg_response_time, events_per_success per source per sport
- `suggest_fallbacks(log_path: Path) -> dict` — For each sport, rank sources by reliability. Flag sources with <50% success rate in last 7 days.

**Dependencies:** Python stdlib only.

**CLI:**
```bash
python3 scripts/source_health.py --log                                      # append today's session to log
python3 scripts/source_health.py --report                                   # show 7-day reliability report
python3 scripts/source_health.py --report --days 30                         # show 30-day report
python3 scripts/source_health.py --suggest-fallbacks                        # suggest fallback chain adjustments
```

**Definition of Done:**

- [ ] Script exists at `scripts/source_health.py` and is executable
- [ ] Correctly parses `scan_errors.json` and `scan_summary.json` to extract per-source status
- [ ] Appends rows to `betting/data/source_health_log.csv` (creates file with headers if absent)
- [ ] `--report` flag shows success rate, avg response time, and events per source per sport for last N days
- [ ] `--suggest-fallbacks` outputs sources with <50% success rate as candidates for deprioritization
- [ ] Does not overwrite existing log entries (append-only)

---

#### Task 3.5 - [MODIFY] `scripts/run_session.sh` — Add Cache Build + Source Health Steps

**Complexity:** SMALL

**Description:** Add two new steps to the session runner: (1) build stats cache for the shortlist after scan+aggregate, and (2) log source health after scan completes.

**Changes to `run_session.sh`:**

After the existing scan step (step 4/7), add:
```bash
echo ""
echo "[5/9] Logging source health..."
python3 "${SCRIPT_DIR}/source_health.py" --log

echo ""
echo "[6/9] Building stats cache for shortlist..."
if [ -f "${DATA_DIR}/s2_shortlist_${RUN_DATE}.md" ]; then
    python3 "${SCRIPT_DIR}/build_stats_cache.py" --shortlist "${DATA_DIR}/s2_shortlist_${RUN_DATE}.md"
else
    echo "[WARNING] No shortlist file found for ${RUN_DATE}, skipping cache build"
fi
```

Renumber subsequent steps (current 5/7→7/9, 6/7→8/9, 7/7→9/9).

**Definition of Done:**

- [ ] `run_session.sh` calls `source_health.py --log` after scan completes
- [ ] `run_session.sh` calls `build_stats_cache.py --shortlist` after shortlist is generated
- [ ] Steps are correctly numbered and echo'd
- [ ] Failures in new steps produce warnings but don't abort the pipeline (non-critical)
- [ ] `--skip-settle` flag still works correctly
- [ ] Existing step timing/summary output is preserved

---

## Security Considerations

- **No credentials in scripts:** `build_stats_cache.py` uses the existing `fetch_with_playwright.py` infrastructure which handles cookies via `site_selectors.json` and storage state. No new credentials needed.
- **Input validation:** All new scripts validate input file paths and JSON structure before processing. `validate_s3_output.py` and `validate_coupons.py` use regex parsing of untrusted markdown — patterns are anchored and bounded to prevent ReDoS.
- **File system safety:** Cache files are written to a controlled directory (`betting/data/stats_cache/`). `slugify()` strips path separators and special characters to prevent directory traversal via team names.
- **No network exposure:** All scripts run locally. No new network endpoints, servers, or API keys required. `build_stats_cache.py` reuses the existing Playwright fetcher which already has rate limiting and retry logic.
- **CSV injection prevention:** `source_health.py` sanitizes fields before CSV writing — any cell starting with `=`, `+`, `-`, `@` is prefixed with a single quote to prevent formula injection if opened in Excel.

## Quality Assurance

Acceptance criteria checklist to verify the implementation meets the defined requirements:

- [ ] All 6 new scripts (`validate_s3_output.py`, `validate_coupons.py`, `check_48h_repeats.py`, `compute_safety_scores.py`, `build_stats_cache.py`, `source_health.py`) exist and are executable
- [ ] Each script has `--help` output documenting its purpose, inputs, and outputs
- [ ] `validate_s3_output.py` correctly identifies at least 3 types of errors when run against `betting/data/2026-04-28_s3_deep_stats.md`
- [ ] `validate_coupons.py` correctly verifies arithmetic for at least 3 existing coupon files
- [ ] `compute_safety_scores.py` produces identical rankings when given the same input twice (deterministic)
- [ ] `build_stats_cache.py` creates cache files and correctly skips re-fetch when cache is valid
- [ ] `source_health.py` appends to CSV without corrupting existing entries
- [ ] `check_48h_repeats.py` correctly finds repeats from the last 2 days in picks-ledger.csv
- [ ] `analysis-methodology.instructions.md` is ≤480 lines with no broken cross-references
- [ ] Agent files total ≤735 lines with no behavioral changes (same rules enforced via instruction loading)
- [ ] `orchestrate-betting-day.prompt.md` references validation scripts instead of LLM-based checks
- [ ] Parallel S3+S4 and S5+S6 documented in orchestrator prompt
- [ ] Adaptive pass protocol documented in orchestrator prompt
- [ ] `run_session.sh` includes cache build and source health steps without breaking existing flow
- [ ] No new pip dependencies required (all scripts use Python stdlib + existing project deps)

## Improvements (Out of Scope)

Potential improvements identified during planning that are not part of the current task:

- **SQLite-backed cache:** Replace flat JSON cache files with a SQLite database for faster queries and atomic writes. Deferred because JSON files are simpler and sufficient for the current scale (~50-100 teams per session).
- **Automated Betclic market existence check:** A script that checks if a specific market (e.g., "corners over 9.5") exists on Betclic for a given match. Deferred because Betclic blocks automated access (403). Would require a maintained API or manual extraction.
- **Real-time odds tracking:** Continuous odds monitoring between analysis time and kickoff, with automatic drift alerts. Deferred because it requires a persistent background process and significantly more API credits.
- **Machine learning safety score model:** Train a model on historical pick outcomes to weight safety score factors (L10 vs H2H vs L5) optimally per sport. Deferred because insufficient training data exists (<200 settled picks).
- **Automated coupon file generation from picks-ledger:** A script that reads approved picks from the ledger and generates the coupon markdown file automatically. Deferred because coupon construction still requires creative judgment (thesis, risk tier, combination logic).
- **Web dashboard for source health:** A simple Flask/Streamlit dashboard showing source reliability trends. Deferred — the CSV report is sufficient for now.

## Changelog

| Date       | Change Description                               |
| ---------- | ------------------------------------------------ |
| 2026-04-28 | Initial plan created                             |
