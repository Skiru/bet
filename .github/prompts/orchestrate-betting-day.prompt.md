---
name: orchestrate-betting-day
description: "Agent-driven daily cycle: YOU are the orchestrator. Scripts are tools. NEVER run pipeline_orchestrator.py."
agent: bet-orchestrator
skills:
   - bet-orchestrating-workflows
argument-hint: "run_date=2026-05-08 session=full" or "run_date=2026-05-08 session=night rerun=true"
---

# BETTING DAY ORCHESTRATOR

## ⛔ NEVER run `python3 scripts/pipeline_orchestrator.py`

Use the shared workflow skill for reusable routing and handoff mechanics. Keep this prompt focused on the day-specific phase spine and session inputs.

---

## 🟢 WHAT A GOOD SESSION LOOKS LIKE (memorize this)

```
 1. Read pipeline-errors journal → acknowledge lessons
 2. Read config + methodology files → present recovery plan → user confirms
 3. S0:   settle_on_finish.py + analyze_betclic_learning.py → delegate to bet-settler
 4. S0.5: delegate to bet-db-analyst (DB quality check)
 5. S1:   discover_events.py → delegate to bet-scanner
 6. S1▸   ingest_scan_stats.py (stats ingestion — no delegation needed)
 7. S1a:  seed_espn_data.py (ESPN seeding — DO NOT SKIP)
 8. S1b:  fetch_odds_api.py + fetch_odds_api_io.py + fetch_esports_odds.py + fetch_weather.py + tipster_aggregator.py (DO NOT SKIP)
 9. S1e:  build_shortlist.py → delegate to bet-scanner
10. S2:   tipster_xref.py → delegate to bet-scout
11. S2.3: run_scrapers.py → delegate to bet-enricher
12. S2.5: data_enrichment_agent.py → delegate to bet-enricher
12b. S2.6: fetch_tennis_elo.py + enrich_tennis_flashscore.py + tennis_h2h_warmup.py → delegate to bet-enricher
12c. S2.7: enrich_volleyball_stats.py → delegate to bet-enricher (Flashscore + API-Volleyball)
12d. S2.8: enrich_hockey_stats.py → delegate to bet-enricher (Flashscore EU + MoneyPuck/ESPN)
12e. S2.9: enrich_basketball_stats.py → delegate to bet-enricher (Flashscore EU + Sofascore/BDL)
13. ⛔    validate_phase.py --phase data (GATE — exit 1 = STOP)
14. S3:   deep_stats_report.py → delegate to bet-statistician
15. S4:   odds_evaluator.py → delegate to bet-valuator
16. S5+6: context_checks.py + upset_risk.py → delegate to bet-challenger
17. ⛔    STEP COMPLETENESS GATE (S3+S4+S5/6 all have verdicts?)
18. S7:   gate_checker.py → delegate to bet-challenger
19. ⛔    validate_phase.py --phase analysis (GATE)
20. S7.5: validate_betclic_markets.py + check_48h_repeats.py
21. S8:   coupon_builder.py + validate_coupons.py → delegate to bet-builder
22. ⛔    validate_phase.py --phase build (GATE)
23. S10:  Present FULL statistical matrix + coupons with per-pick reasoning
```

**The pattern is ALWAYS: run script → delegate to agent → receive verdict → proceed.**
**If you ever do "run script → proceed" without delegation — YOU HAVE FAILED.**

---

## 🔴 TOP 3 FAILURE MODES (from 23.05.2026)

1. **SKIPPING STEPS.** You skipped S0, S0.5, S1a, S1b, S2.3, all validation gates. Result: garbage coupon with PARTIAL data everywhere. FIX: Follow the EXECUTION SPINE below IN ORDER. Every step is mandatory.

2. **NO DELEGATION.** You ran scripts and moved on without calling `runSubagent`. Result: no specialist analysis, no bear cases, no data quality assessment. FIX: After EVERY script, your next action MUST be `runSubagent(mapped_agent)`.

3. **NO REASONING IN COUPON.** Output was "Kupon HR z 2 nogami" instead of "Espanyol o5.5 cards: L5=7.4 vs line 5.5 (+34%), 85% hit rate L10." FIX: Every pick needs: WHY + L10/H2H/L5 data + mechanism + bear case.

---

## INPUTS

- **run_date** = {{run_date}} (default: today)
- **session** = {{session}} (default: `full`). Options: `full`, `day`, `night`, `morning`
- **rerun** = {{rerun}} (default: `false`)
- **rescan** = {{rescan}} (default: `false`)
- Timezone: Europe/Warsaw. Bookmaker: Betclic.

---

## ═══════════════════════════════════════════════════════════════
## EXECUTION SPINE — FOLLOW THIS EXACTLY, IN ORDER, NO SKIPPING
## ═══════════════════════════════════════════════════════════════

### PRE-FLIGHT: Detect Progress + Load Context

1. **Check state:** `python3 scripts/inspect_pipeline.py --step all --date {run_date} --verbose`
2. **Read errors journal (HARD GATE):**
   - `betting/journal/{run_date}-pipeline-errors.md` (if exists)
   - `betting/journal/{prev_date}-pipeline-errors.md` (if exists)
   - Print: "Lessons loaded: [3-5 key takeaways]"
3. **Read config files:**
   - `config/betting_config.json`, `config/lmstudio_config.json`
   - `.github/instructions/analysis-methodology.instructions.md`
   - `.github/instructions/betting-artifacts.instructions.md`
   - `betting/sources/source-registry.md`
   - `/memories/repo/pipeline-knowledge-base.md`
4. **Present recovery plan** to user. Wait for confirmation.

---

### S0: Settlement + History

```bash
PYTHONPATH=src .venv/bin/python3 scripts/settle_on_finish.py --betting-day {prev_date} --no-poll
PYTHONPATH=src .venv/bin/python3 scripts/analyze_betclic_learning.py
PYTHONPATH=src .venv/bin/python3 scripts/evaluate_decisions.py --date {prev_date}
PYTHONPATH=src .venv/bin/python3 scripts/data_rotation.py --execute --days 30
PYTHONPATH=src .venv/bin/python3 scripts/build_league_profiles.py
```
**→ `runSubagent("bet-settler")`** — read `bet-settle.prompt.md` first. Pass settlement output + betclic learning summary.

---

### S0.5: DB Quality Check

**→ `runSubagent("bet-db-analyst")`** — read `bet-db-quality.prompt.md` first.
**GATE:** If critical gaps reported → fix before S1.

---

### S1: Event Discovery

```bash
PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date {date} --verbose
```
Mode: sync, timeout: 120000. Parse `AGENT_SUMMARY:{json}`.
**→ `runSubagent("bet-scanner")`** — read `bet-scan.prompt.md`. Check: 5-sport coverage, tournament protection, major domestic leagues, source cross-refs.

---

### S1-ingest: Stats Ingestion

```bash
PYTHONPATH=src .venv/bin/python3 scripts/ingest_scan_stats.py --date {date} --verbose
```
Transforms discovery data into `stats_cache/` + DB `team_form`. No delegation needed.

---

### S1a: ESPN Seeding (DO NOT SKIP)

```bash
PYTHONPATH=src .venv/bin/python3 scripts/seed_espn_data.py --skip-players --verbose
```
Timeout: 300000. Seeds: standings, ATS/OU records, predictions, power index. This data is NOT available from any other source. Without it, S5 (context_checks) has no injury/coach data.

---

### S1b: Odds + Weather + Tipster Fetch (DO NOT SKIP)

```bash
PYTHONPATH=src .venv/bin/python3 scripts/fetch_odds_api.py --verbose
PYTHONPATH=src .venv/bin/python3 scripts/fetch_odds_api_io.py --date {date} --verbose
PYTHONPATH=src .venv/bin/python3 scripts/fetch_esports_odds.py --date {date} --verbose
PYTHONPATH=src .venv/bin/python3 scripts/fetch_weather.py --date {date} --verbose
PYTHONPATH=src .venv/bin/python3 scripts/tipster_aggregator.py --date {date} --use-gemini --verbose
```
These provide: cross-validated odds (for S4), esports odds from bo3.gg (CS2/Valorant), weather context for outdoor events (for S5), raw tipster picks (for S2). Without them, downstream steps lack critical inputs.

---

### S1e: Build Shortlist

```bash
PYTHONPATH=src .venv/bin/python3 scripts/build_shortlist.py --date {date} --stats-first --verbose
```
**→ `runSubagent("bet-scanner")`** — read `bet-shortlist.prompt.md`. Check: ≥20 candidates, data quality distribution, major leagues + tournaments present, no phantom fixtures.

---

### S2: Tipster Cross-Reference

```bash
PYTHONPATH=src .venv/bin/python3 scripts/tipster_xref.py --date {date} --verbose
```
Mode: async, timeout: 300000.
**→ `runSubagent("bet-scout")`** — read `bet-tipsters.prompt.md`. Check: consensus quality, argument independence, angle discovery.

---

### S2.3: Scrapers (DO NOT SKIP)

```bash
PYTHONPATH=src .venv/bin/python scripts/run_scrapers.py --sport all --season 2425 --verbose
```
Mode: async, timeout: 300000. Writes: league_profiles, player_season_stats.
**→ `runSubagent("bet-enricher")`** — read `bet-enrich.prompt.md`. Check: scraper coverage, gaps for S2.5.

> **PARALLEL:** S2 and S2.3 are independent — run both scripts, then delegate both analyses.

---

### S2.5: Data Enrichment

**Gap check:** Run `--dry-run` or DB query. Only skip if <15 teams truly missing AND you can VERIFY existing data quality is FULL for >70% of candidates.

```bash
PYTHONPATH=src .venv/bin/python3 scripts/data_enrichment_agent.py --date {date} --news --gamelogs --verbose
```
Mode: sync, timeout: 600000.
**→ `runSubagent("bet-enricher")`** — read `bet-enrich.prompt.md`. Check: yield %, per-sport quality, gap recoverability.
**GATE:** If REJECTED (yield <40%) → escalate to user.

**H2H Self-Healing (R9):** After enrichment, check `h2h_status`. If >50% candidates are SPARSE → run `web_research_agent.py` for top 20 candidates.

---

### S2.6: Tennis Deep Enrichment (DO NOT SKIP for tennis events)

**Condition:** Run if shortlist contains ≥1 tennis event. These scripts provide surface-aware L10 arrays, H2H serve stats, and Elo ratings that `deep_stats_report.py` and `compute_safety_scores.py` consume for tennis.

```bash
PYTHONPATH=src .venv/bin/python3 scripts/fetch_tennis_elo.py --verbose
PYTHONPATH=src .venv/bin/python3 scripts/enrich_tennis_flashscore.py --date {date} --verbose
PYTHONPATH=src .venv/bin/python3 scripts/tennis_h2h_warmup.py --date {date} --verbose
```
Order matters: Elo first (used by safety scores), then Flashscore L10 (per-match arrays), then H2H warmup (uses both).
**→ `runSubagent("bet-enricher")`** — Check: tennis player coverage %, Flashscore match yield, H2H cache hit rate. Flag players with MINIMAL data (<4 keys).

---

### S2.7: Volleyball Deep Enrichment (DO NOT SKIP for volleyball events)

**Condition:** Run if shortlist contains ≥1 volleyball event. Provides per-match L10 arrays (total_points, aces, blocks, errors) via Flashscore + API-Volleyball rich completion.

```bash
PYTHONPATH=src .venv/bin/python3 scripts/enrich_volleyball_stats.py --date {date} --verbose
```
**→ `runSubagent("bet-enricher")`** — Check: coverage before/after %, teams enriched, Flashscore yield. Flag teams with <3 L10 values.

---

### S2.8: Hockey Deep Enrichment (DO NOT SKIP for hockey events)

**Condition:** Run if shortlist contains ≥1 hockey event. Provides per-match L10 arrays (goals, shots_on_goal, PIM, power_play_goals) via Flashscore (EU leagues) + MoneyPuck/ESPN (NHL).

```bash
PYTHONPATH=src .venv/bin/python3 scripts/enrich_hockey_stats.py --date {date} --verbose
```
**→ `runSubagent("bet-enricher")`** — Check: coverage before/after %, EU vs NHL split, source reliability.

---

### S2.9: Basketball Deep Enrichment (DO NOT SKIP for basketball events)

**Condition:** Run if shortlist contains ≥1 basketball event. Provides per-match L10 arrays (points, rebounds, assists, steals, blocks) via Flashscore (EU leagues) + Sofascore/BDL (NBA).

```bash
PYTHONPATH=src .venv/bin/python3 scripts/enrich_basketball_stats.py --date {date} --verbose
```
**→ `runSubagent("bet-enricher")`** — Check: coverage before/after %, EU vs NBA split, rich key completion rate.

---

### ⛔ DATA PHASE GATE

```bash
PYTHONPATH=src python3 scripts/validate_phase.py --date {date} --phase data --format json
```
**Exit code 1 = STOP. Fix before proceeding to S3.**

---

### S3: Deep Statistical Analysis

```bash
PYTHONPATH=src .venv/bin/python3 scripts/deep_stats_report.py --date {date} --gemini --verbose
```
> Note: `--shortlist` is no longer required. deep_stats reads from `pipeline_candidates` DB table (DB-first). Use `--shortlist path.json` only as manual override.
Mode: async, timeout: 600000.
**→ `runSubagent("bet-statistician")`** — read `bet-deep-stats.prompt.md`. Key: R5 compliance, three-way cross-check, edge mechanisms, competition context.

---

### S4: Odds Evaluation

```bash
PYTHONPATH=src .venv/bin/python3 scripts/odds_evaluator.py --date {date} --verbose
```
Mode: async, timeout: 300000.
**→ `runSubagent("bet-valuator")`** — read `bet-odds-ev.prompt.md`. Key: EV per candidate, drift >8%, Kelly sizing.

---

### S5+S6: Context + Upset Risk

```bash
PYTHONPATH=src .venv/bin/python3 scripts/context_checks.py --date {date} --verbose
PYTHONPATH=src .venv/bin/python3 scripts/upset_risk.py --date {date} --verbose
```
Both async, timeout: 300000. Run context first, then upset.
**→ `runSubagent("bet-challenger")`** — read `bet-context-upset.prompt.md`. Key: bear cases, injuries, weather, upset scoring.

---

### ⛔ STEP COMPLETENESS GATE (before S7)

Verify ALL completed:
- [ ] S3 → bet-statistician verdict received
- [ ] S4 → bet-valuator verdict received
- [ ] S5+S6 → bet-challenger verdict received

**ANY missing → STOP. Run the missing step.**

---

### S7: Decision Gate

```bash
PYTHONPATH=src .venv/bin/python3 scripts/gate_checker.py --date {date} --verbose
```
Mode: async, timeout: 300000.
**→ `runSubagent("bet-challenger")`** — read `bet-gate.prompt.md`. The challenger's verdict is AUTHORITATIVE: STRONG/MODERATE/WEAK tiers + mechanism per candidate.

---

### ⛔ ANALYSIS PHASE GATE

```bash
PYTHONPATH=src python3 scripts/validate_phase.py --date {date} --phase analysis --format json
```
Verify: gate_results exist, ≥3 STRONG+MODERATE candidates. If <3 → emergency expansion.

---

### S7.5: Betclic Market Validation

```bash
PYTHONPATH=src .venv/bin/python3 scripts/validate_betclic_markets.py --date {date} --verbose
```
Confirms which markets EXIST on Betclic. Unavailable → flag for coupon builder.

---

### S7.6: 48h Repeat Check

```bash
PYTHONPATH=src .venv/bin/python3 scripts/check_48h_repeats.py --date {date} --format json --verbose
```

---

### S8+S9: Build + Validate Coupons

```bash
PYTHONPATH=src .venv/bin/python3 scripts/coupon_builder.py --date {date} --verbose
PYTHONPATH=src .venv/bin/python3 scripts/validate_coupons.py --date {date} --verbose
PYTHONPATH=src .venv/bin/python3 scripts/generate_coupon_pdf.py --date {date}
```
**→ `runSubagent("bet-builder")`** — read `bet-portfolio.prompt.md`. Key: arithmetic, unique events, >50% stat markets, per-pick narrative reasoning, correlation check.

---

### ⛔ BUILD PHASE GATE

```bash
PYTHONPATH=src python3 scripts/validate_phase.py --date {date} --phase build --format json
```

---

### S10: Present Results

1. **Settlement Summary** — PnL, rolling 7-day, bankroll
2. **Scan Summary** — events per sport, completeness %
3. **FULL STATISTICAL MATRIX** — ALL candidates: Event | Market | Direction | Line | L10% | H2H% | Safety | P(hit) | Min kurs | 3-Way | Data Quality
4. **Final Coupons** — per-leg: WHY + L10/H2H data + mechanism + bear case. Combined odds (arithmetic shown). Stake.
5. **Extended Pool** — gate-failed with EV>0, bull/bear case each
6. **Watchlist** — picks awaiting triggers

---

## ═══════════════════════════════════════════════
## DELEGATION PROTOCOL
## ═══════════════════════════════════════════════

### Template (use for ALL delegations)

**Step 1:** Use `read_file` to load the internal prompt: `.github/internal-prompts/bet-{task}.prompt.md`
**Step 2:** Include the internal prompt content in your `runSubagent` call:

```
runSubagent("{agent_name}"):
## Task: {step_name} for {date}

### Internal Prompt
{PASTE the full content of .github/internal-prompts/bet-{task}.prompt.md here}

### Script Output (executed by orchestrator)
AGENT_SUMMARY: {paste the extracted JSON}
Exit code: {0|1|2}
Key warnings/errors from log: {paste relevant lines, max 50}

### Upstream Context
Previous verdicts: {list step verdicts received so far}
Quality flags: {list flags from previous agents}
Focus points: {specific concerns for this step}

### ⛔ Analysis-Only Mode
Do NOT run scripts. Analyze provided output with specialist knowledge.
Return structured verdict per agent-execution-protocol.instructions.md.
Your response MUST have: subagent_verdict block + Metrics (≥3) + Analysis + User Summary + Data For Orchestrator.
```

**WHY paste the internal prompt:** The specialist agent needs the full task protocol to know what checks to perform. Without it, they return generic analysis.

### Delegation Map

| Step | Agent | Internal Prompt |
|------|-------|-----------------|
| S0 | bet-settler | bet-settle.prompt.md |
| S0.5 | bet-db-analyst | bet-db-quality.prompt.md |
| S1/S1e | bet-scanner | bet-scan.prompt.md / bet-shortlist.prompt.md |
| S2 | bet-scout | bet-tipsters.prompt.md |
| S2.3/S2.5 | bet-enricher | bet-enrich.prompt.md |
| S3 | bet-statistician | bet-deep-stats.prompt.md |
| S4 | bet-valuator | bet-odds-ev.prompt.md |
| S5+S6 | bet-challenger | bet-context-upset.prompt.md |
| S7 | bet-challenger | bet-gate.prompt.md |
| S8+S9 | bet-builder | bet-portfolio.prompt.md |

### Verdict Quality Gate (reject if ANY is NO)

1. Has `subagent_verdict` block with verdict + quality_score?
2. `### Metrics` has ≥3 specific numbers?
3. `### Analysis` has original reasoning?
4. `### Data For Orchestrator` has next_step_ready + quality_flags + focus_points?
5. `### User Summary` is plain-language and different from Analysis?

---

## ═══════════════════════════════════════════════
## RULES (inline — check at enforcement point)
## ═══════════════════════════════════════════════

| Rule | When | Check |
|------|------|-------|
| R3 NO AUTO-REJECT | S7, S8 | ALL candidates in matrix. Gate-failed → Extended Pool |
| R5 STATS FIRST | S3, S8 | Every football ≥1 stat market. Portfolio >50% stat markets |
| R6 BETCLIC ADVISORY | S0, S3 | Show hit rates, NEVER auto-penalize |
| R9 SELF-HEALING | S2.5 | H2H sparse >50% → web_research_agent for top 20 |
| R12 CONDITIONAL | S8 | "⚠️ Wszystkie typy są WARUNKOWE" in every coupon |
| R14 DATA DEPTH | S3, S8 | data_quality_score per candidate. FULL/PARTIAL in core only |
| R17 MONITORING | ALL | --verbose. Read output. Cite numbers. React to errors |
| R18 DATA FLOW | ALL | Verify format match between producer/consumer scripts |
| R20 DELEGATION | ALL | Script → runSubagent = your NEXT action. No exceptions |

---

## ═══════════════════════════════════════════════
## TECHNICAL REFERENCE
## ═══════════════════════════════════════════════

### Script → DB Data Flow

| Script | Reads | Writes |
|--------|-------|--------|
| discover_events.py | scan_urls.json | fixtures, scan_results |
| generate_market_matrix.py | fixtures, odds_history, team_form | **market_matrix_events**, market_matrix_runs, JSON (debug) |
| build_shortlist.py | **market_matrix_events** (DB-first), JSON fallback | **pipeline_candidates**, JSON (debug) |
| ingest_scan_stats.py | fixtures, stats_cache/ | team_form |
| run_scrapers.py | — | league_profiles, player_season_stats, athletes, scraper_runs |
| tipster_aggregator.py | tipster sites | tipster_picks, tipster_consensus |
| tipster_xref.py | tipster_picks, **pipeline_candidates** | **pipeline_candidates** (tipster enrichment) |
| data_enrichment_agent.py | team_form, fixtures | team_form, match_stats, source_health |
| fetch_tennis_elo.py | tennisabstract.com | stats_cache/tennis_elo/ |
| enrich_tennis_flashscore.py | fixtures, flashscore.com | team_form (source=flashscore-tennis) |
| tennis_h2h_warmup.py | team_form, tennis-abstract | team_form (h2h_values) |
| deep_stats_report.py | **pipeline_candidates** (DB-first), team_form | analysis_results |
| odds_evaluator.py | odds_history, analysis_results | analysis_results (EV) |
| context_checks.py | fixtures, ESPN API | analysis_results (context) |
| upset_risk.py | analysis_results | analysis_results (upset) |
| gate_checker.py | **analysis_results** (DB-first) | gate_results |
| validate_betclic_markets.py | gate_results, Betclic API | betclic_markets |
| coupon_builder.py | **gate_results** (DB-first) | coupons/*.md, *.json |

> **DB-first architecture (2026-05-26):** All inter-step data flows through DB tables. JSON is kept as debug/fallback only. Key tables: `pipeline_candidates` (shortlist), `market_matrix_events` (matrix), `analysis_results` (S3), `gate_results` (S7).

⚠️ Write hazard: ingest_scan_stats, data_enrichment_agent, deep_stats_report all write team_form → run sequentially.

### AGENT_SUMMARY Emitters

Confirmed: `discover_events`, `run_scrapers`, `validate_betclic_markets`, `odds_evaluator`, `context_checks`, `upset_risk`, `validate_coupons`. Others: parse verbose stdout.

### LM Studio Flags

| Flag | Script | Effect |
|------|--------|--------|
| `--use-gemini` | tipster_aggregator.py | LM Studio reads tipster pages via httpx + local LLM |
| `--news` | data_enrichment_agent.py | Brave Search + LM Studio → team_news |
| `--gemini` | deep_stats_report.py | LM Studio second opinion per candidate |

### RERUN (rerun=true)

Increment version. Old pending → superseded. ALL steps from scratch.

### RESCAN (rescan=true)

```bash
sqlite3 betting/data/betting.db "DELETE FROM scan_results WHERE date(created_at) >= '{date}';"
sqlite3 betting/data/betting.db "DELETE FROM analysis_results WHERE betting_date='{date}';"
sqlite3 betting/data/betting.db "DELETE FROM gate_results WHERE betting_date='{date}';"
rm -f betting/data/{date}_s2_shortlist.json betting/data/{date}_s3_deep_stats.json betting/data/{date}_s7_gate_results.json
```
Then full pipeline from S0.5.

### §S8.FINAL Verification

A. ARITHMETIC: leg odds × = combined (±0.02)
B. PLACEMENT ORDER: earliest kickoff − 30-60 min
C. CROSS-CHECK: no orphans, max 2 same-sport per coupon
D. EV: (true_prob × odds) − 1
E. EXPOSURE: stakes ≤ 25% bankroll
F. MATRIX: ALL analyzed events shown

### Infrastructure Modules (2026-05-26)

| Module | Purpose |
|--------|---------|
| `src/bet/fuzzy_match.py` | Unified team/player name matching with `name_mappings` DB cache |
| `src/bet/stats/stat_validation.py` | Cross-sport stat key validation (prevents contamination) |
| `src/bet/stats/value_ranges.py` | Canonical value ranges per sport per stat |
| `scripts/audit_data_quality.py` | Data quality audit: fake L10, contamination, stale data, coverage |
| `scripts/source_health.py` | Source reliability tracker (CSV log + fallback suggestions) |
| `scripts/migrate_pipeline_tables.py` | Creates pipeline_candidates table |
| `scripts/migrate_market_matrix.py` | Creates market_matrix_events/runs tables |

### Known Bugs (2026-05-23)

1. odds_evaluator.py market mapping: "h2h"/"totals" ≠ "Goals Total O/U" → only 6/547 get EV
2. validate_coupons.py: mis-parses narrative headings as 1-leg coupons
3. ESPN diacritics: "Białystok" ≠ "Bialystok"

### S11: Knowledge Transfer

Save lessons to `/memories/session/{date}-notes.md` and update `/memories/repo/pipeline-knowledge-base.md`.

<!-- BET:prompt:orchestrate-betting-day:v8 -->
