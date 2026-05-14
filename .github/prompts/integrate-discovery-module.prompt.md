---
name: integrate-discovery-module
description: "Replace scan_events.py with discovery module across all agents, prompts, instructions, and scripts. Full integration + cleanup."
agent: bet-orchestrator
argument-hint: "Just run it — no arguments needed"
---

# INTEGRATE DISCOVERY MODULE — Replace scan_events.py Pipeline-Wide

> **Prerequisite:** `src/bet/discovery/` module is COMPLETE and live-tested (1734 events, 3 sources, 29s).
> **Reference:** `betting/plans/discovery-integration-handoff.md` for full context.

## WHAT CHANGED

The new `src/bet/discovery/` module replaces `scripts/scan_events.py` for event discovery (S1).

| Aspect | OLD (scan_events.py) | NEW (discover_events.py) |
|--------|---------------------|--------------------------|
| Sources | Flashscore + ESPN via UnifiedAPIClient | SofaScore API + Odds API + API-Football |
| Speed | 10-15 min | ~30 seconds |
| Execution | `mode=async`, `timeout=600000` | `mode=sync`, `timeout=120000` |
| Output JSON | `global_events_api.json` | `{date}_s1_events.json` |
| Command | `python3 scripts/scan_events.py --parallel-sport --date {date} --verbose` | `PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date {date} --verbose` |
| Deep data | Built into scan (form, H2H, odds) | NOT in scan (handled by enrichment S2) |
| AGENT_SUMMARY | Yes | Yes (same format) |

**CRITICAL:** Discovery does NOT fetch deep data (form, H2H, injuries). That's now purely enrichment's job (S2). Adjust all scan review expectations accordingly.

---

## TASK LIST — Execute in order

### TASK 1: `[MODIFY]` `.github/copilot-instructions.md` — Scripted Workflow

In the `# 1. Run pipeline` comment block (~line 26-33), add `discover_events.py` as the first step:

```python
# 1. Run pipeline (AGENT-DRIVEN — individual scripts, NOT pipeline_orchestrator.py)
# ⛔ NEVER run: python3 scripts/pipeline_orchestrator.py
# Instead: the orchestrator agent calls individual scripts one at a time:
#   PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date YYYY-MM-DD --verbose
#   python3 scripts/build_shortlist.py --date YYYY-MM-DD --stats-first
#   python3 scripts/deep_stats_report.py --date YYYY-MM-DD --shortlist ...
#   python3 scripts/gate_checker.py --date YYYY-MM-DD
#   python3 scripts/coupon_builder.py --date YYYY-MM-DD
# See orchestrate-betting-day.prompt.md for the full step-by-step protocol.
```

---

### TASK 2: `[MODIFY]` `.github/prompts/orchestrate-betting-day.prompt.md` — STEP S1

**2a.** Replace STEP S1 scan command block (~line 381-389):

OLD:
```bash
# Unified scan via 7 sources (Flashscore, BetExplorer, Soccerway, ESPN + OddsPortal, TotalCorner, Scores24)
python3 scripts/scan_events.py --date {date} --verbose 2>&1
```

NEW:
```bash
# API-first discovery via 3 sources (SofaScore, Odds API, API-Football) — ~30s
PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date {date} --verbose 2>&1
```

**2b.** Replace the execution guidance (~line 391):

OLD:
```
**WHILE RUNNING:** Use `mode=async` with `timeout=600000`. THINK-WHILE-WAITING...
```

NEW:
```
**EXECUTION:** Use `mode=sync` with `timeout=120000`. Discovery completes in ~30s. Parse `AGENT_SUMMARY:{json}` from output.
```

**2c.** Update S1 review delegation template (~line 395-415). Replace:
- `betting/data/global_events_api.json` → `betting/data/{date}_s1_events.json`
- "7 sources (Flashscore, BetExplorer...)" → "3 sources (SofaScore, Odds API, API-Football)"
- Remove "Data quality: How many events have deep data (H2H, form, injuries)?" (discovery doesn't fetch deep data)
- Add: "Source cross-references: How many events confirmed by ≥2 sources?"

**2d.** Update §STRUCTURED SCRIPT OUTPUT list (~line 245):
- Replace `scan_events.py` with `discover_events.py` in the 14/15 scripts list
- Update count: "15 analytical scripts emit..."

---

### TASK 3: `[MODIFY]` `.github/agents/bet-orchestrator.agent.md` — Script Table

**3a.** Update the script execution table (~line 312):

OLD:
```
| scan_events.py | `python3 scripts/scan_events.py --parallel-sport --date YYYY-MM-DD --verbose` | 600000 | async |
```

NEW:
```
| discover_events.py | `PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date YYYY-MM-DD --verbose` | 120000 | sync |
```

**3b.** Update the scan phase script list (~line 79):

OLD: `scan_events.py`, `ingest_scan_stats.py`, `html_deep_parser.py` — scan phase

NEW: `discover_events.py`, `ingest_scan_stats.py` — scan phase

---

### TASK 4: `[MODIFY]` `.github/agents/bet-scanner.agent.md` — Full Rewrite of Scan Architecture

**4a.** Update YAML description:

OLD: `"Orchestrates scanning — Flashscore + ESPN scan for all 5 core sports, validates coverage, runs enrichment, and delivers an analysis-ready shortlist."`

NEW: `"Orchestrates scanning — API-first discovery via SofaScore + Odds API + API-Football for all 5 core sports, validates coverage, triggers enrichment, and delivers an analysis-ready shortlist."`

**4b.** Update heading:

OLD: `# BET-SCANNER — Beast Mode Scan Orchestrator`

NEW: `# BET-SCANNER — API-First Discovery Orchestrator`

**4c.** Replace Architecture section:

OLD:
```
## Architecture: Flashscore + ESPN

Scanning uses a **single unified script** (`scan_events.py`) that fetches ALL events via `UnifiedAPIClient` (Flashscore primary, ESPN fallback). Deep enrichment via `get_match_preview()` (form + H2H) and `get_fixture_stats()`.

Deep enrichment is built-in: for each event, the scanner fetches form data (`/event/{id}/pregame-form`), H2H (`/event/{id}/h2h`), and odds (`/event/{id}/odds/1/all`) with 0.3s rate limiting.

Results written to both **DB** (fixtures, scan_results, teams, competitions) and **JSON** (`betting/data/global_events_api.json`).
```

NEW:
```
## Architecture: API-First Discovery (3 Sources)

Discovery uses `src/bet/discovery/` module with 3 structured API sources:
- **SofaScore Daily Schedule API** — all 5 sports, ~1500 events, primary source for canonical names
- **The Odds API** — football (10 leagues) + auto-discovered tennis/hockey, provides structured pre-match odds
- **API-Football** — football only, ~250 events, cross-validates SofaScore fixtures

Sources fetched concurrently (ThreadPoolExecutor, 3 workers). Dedup via exact normalized keys + rapidfuzz fuzzy matching (threshold 85, ±2h kickoff window). ~30s total.

**No deep data at scan time.** Form, H2H, injuries are fetched by enrichment (S2). Discovery only identifies fixtures.

Results written to **DB** (fixtures, scan_results, teams, competitions, fixture_sources) and **JSON** (`betting/data/{date}_s1_events.json`).
```

**4d.** Replace PHASE 1 SCAN command:

OLD:
```bash
python3 scripts/scan_events.py --date {YYYY-MM-DD} --verbose 2>&1
```
Expected: 1000-2000 events, 30-40% deep-enriched, ~15 min runtime.

NEW:
```bash
PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date {YYYY-MM-DD} --verbose 2>&1
```
Expected: 1500-2000 events, 0% deep-enriched (enrichment handles that), ~30s runtime.

**4e.** Update script table:

OLD:
```
| scan_events.py | 900000 | async | YES |
```

NEW:
```
| discover_events.py | 120000 | sync | YES |
```

---

### TASK 5: `[MODIFY]` `.github/internal-prompts/bet-scan.prompt.md` — S1 Review Prompt

**5a.** Update YAML description:

OLD: `"S1-S1e: Scan data engine — Flashscore + ESPN scan for 5 core sports, ingest, enrich, build shortlist"`

NEW: `"S1-S1e: Scan data engine — API-first discovery (SofaScore + Odds API + API-Football) for 5 core sports, ingest, enrich, build shortlist"`

**5b.** Update YOUR ANALYTICAL VALUE:

OLD: "You diagnose DATA DEPTH — not just event count but whether form/H2H data from Flashscore is rich enough..."

NEW: "You diagnose COVERAGE BREADTH — not just event count but whether the fixture universe is COMPLETE across all 5 sports, whether cross-source dedup caught duplicates, and whether source diversity (≥2 sources per event) gives confidence in fixture accuracy. Deep data (form/H2H) is handled by enrichment — your job is fixture completeness."

**5c.** Replace PHASE 1 command and expectations:

OLD:
```bash
python3 scripts/scan_events.py --date {date} --verbose 2>&1
```
Flashscore + ESPN scans ALL 5 sports. Deep enrichment fetches form/H2H per event.
Parse `AGENT_SUMMARY:{json}` — per-sport counts, deep_enriched, errors.
**VALIDATE:** 5 sports present? Total > 300? Tournament matches? Zero critical errors?

NEW:
```bash
PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date {date} --verbose 2>&1
```
API-first discovery from SofaScore + Odds API + API-Football. All 5 sports. No deep data (enrichment handles that).
Parse `AGENT_SUMMARY:{json}` — per-sport counts, source stats, dedup merges, errors.
**VALIDATE:** 5 sports present? Total > 300? All 3 sources responded? Tournament matches? Dedup reasonable (expect 3-5% merges)?

---

### TASK 6: `[MODIFY]` `.github/prompts/scan-day.prompt.md` — User-Facing Scan Prompt

**6a.** Update YAML:

OLD: `description: "Scan: Flashscore + ESPN → all 5 sports → deep enrichment → ingest → shortlist. Fully autonomous."`

NEW: `description: "Scan: API-first discovery (SofaScore + Odds API + API-Football) → all 5 sports → ingest → enrich → shortlist. Fully autonomous."`

**6b.** Update heading: `# SCAN DAY — Flashscore + ESPN` → `# SCAN DAY — API-First Discovery`

**6c.** Update Architecture diagram:

OLD:
```
STEP 1: Flashscore + ESPN scan (all 5 sports, ~15 min with deep enrichment)
    → global_events_api.json + DB (fixtures, scan_results, teams, competitions)
```

NEW:
```
STEP 1: API-first discovery (all 5 sports, ~30s via SofaScore + Odds API + API-Football)
    → {date}_s1_events.json + DB (fixtures, scan_results, teams, competitions, fixture_sources)
```

**6d.** Update Step 1 command:

OLD:
```bash
python3 scripts/scan_events.py --date {{run_date}} --verbose 2>&1
```
Scans ALL 5 sports via Flashscore + ESPN fallback. Deep enrichment fetches form/H2H per event.
Expected: 1000-2000 events, 30-40% deep-enriched.

NEW:
```bash
PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date {{run_date}} --verbose 2>&1
```
Discovers ALL 5 sports via SofaScore + Odds API + API-Football. No deep data — that's enrichment's job.
Expected: 1500-2000 events, cross-source dedup merges ~3-5%.

---

### TASK 7: `[MODIFY]` `scripts/agent_protocol.py` — Update References

**7a.** In `SELF_HEALING_REGISTRY` — update scan-related entries:
- Replace `scan_events.py` references with `discover_events.py` where they refer to event discovery
- Keep `scan_events.py` in entries that refer to deep enrichment (that's now enrichment's job)

**7b.** In `STRUCTURED_OUTPUT_PROTOCOL` (~line 854):
- Add `"discover_events.py"` to the list of scripts that emit `AGENT_SUMMARY`

**7c.** In `CLI_FLAGS` (~line 838):
- Remove `--parallel-sport` from scan_events description (discovery doesn't use it)
- Add `discover_events.py` flags: `--date`, `--sports`, `--verbose`, `--stats-first`, `--db-path`

**7d.** In `STEP_AGENT_CONFIG` — update S1 to reference `discover_events.py`

**7e.** In the think-while-waiting config (~line 679):
- Update from "While scan_events.py runs (~10 min)" to "While discover_events.py runs (~30s)" or note it's fast enough that extensive think-while-waiting isn't needed

---

### TASK 8: `[MODIFY]` `scripts/scan_events.py` — Rename to Legacy

```bash
mv scripts/scan_events.py scripts/_legacy_scan_events.py
```

Keep as fallback. Prefix `_` marks it as deprecated (same convention as other deprecated scripts in the project).

---

### TASK 9: `[MODIFY]` `scripts/ingest_scan_stats.py` — Verify Compatibility

Check `ingest_scan_stats.py` for hardcoded source name comparisons. Old source values: "flashscore", "betexplorer", "soccerway", "espn". New values: "sofascore", "odds-api", "api-football". If any logic branches on source names, update accordingly.

Also verify it reads from `scan_results` table correctly — the new discovery module writes the same columns but with new `source_domain` values.

---

### TASK 10: `[VERIFY]` Downstream Compatibility

Run these scripts with existing data to verify they still work:
```bash
PYTHONPATH=src .venv/bin/python scripts/build_shortlist.py --date 2026-05-14 --stats-first --verbose 2>&1
PYTHONPATH=src .venv/bin/python scripts/inspect_pipeline.py --step s1 --date 2026-05-14 --verbose 2>&1
```

If `inspect_pipeline.py` has hardcoded source name checks, update them.

---

### TASK 11: `[VERIFY]` Full Test Suite

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ --ignore=tests/scrapers --tb=short -q 2>&1
```

All 565+ tests should pass. The 1 pre-existing failure (`test_compute_safety_scores.py::TestComputeMargin::test_avg_zero_under`) is known and unrelated.

---

### TASK 12: `[VERIFY]` Live Discovery + Downstream Pipeline

```bash
# 1. Run discovery
PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date $(date +%Y-%m-%d) --verbose 2>&1

# 2. Build shortlist from discovery output
PYTHONPATH=src .venv/bin/python scripts/build_shortlist.py --date $(date +%Y-%m-%d) --stats-first --verbose 2>&1
```

Verify shortlist contains events from all 5 sports.

---

## FILES MODIFIED (summary for commit message)

```
MODIFIED:
  .github/copilot-instructions.md          — add discover_events.py to workflow
  .github/prompts/orchestrate-betting-day.prompt.md — S1 command, timeout, delegation template
  .github/prompts/scan-day.prompt.md       — full rewrite for API-first discovery
  .github/agents/bet-orchestrator.agent.md — script table + scan phase scripts
  .github/agents/bet-scanner.agent.md      — architecture + commands + description
  .github/internal-prompts/bet-scan.prompt.md — S1 review expectations
  scripts/agent_protocol.py                — references, flags, AGENT_SUMMARY list

RENAMED:
  scripts/scan_events.py → scripts/_legacy_scan_events.py

VERIFIED (no changes expected):
  scripts/ingest_scan_stats.py             — source name compatibility
  scripts/build_shortlist.py               — downstream compatibility
  scripts/inspect_pipeline.py              — step s1 inspection
```

## COMMIT MESSAGE

```
feat: replace scan_events.py with discovery module pipeline-wide

S1 scan now uses API-first discovery (SofaScore + Odds API + API-Football):
- 30s vs 10-15 min, 3 structured API sources vs web scraping
- discover_events.py replaces scan_events.py in all orchestrator flows

Updated files:
- copilot-instructions.md: discover_events.py in workflow
- orchestrate-betting-day.prompt.md: S1 command, timeout 600→120s, sync mode
- scan-day.prompt.md: full rewrite for API-first discovery
- bet-orchestrator.agent.md: script table + scan phase scripts
- bet-scanner.agent.md: architecture rewrite, description, commands
- bet-scan.prompt.md: S1 review expectations (coverage breadth, not deep data)
- agent_protocol.py: references, flags, AGENT_SUMMARY list
- scan_events.py → _legacy_scan_events.py (kept as fallback)
```
