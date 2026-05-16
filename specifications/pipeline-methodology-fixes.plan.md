# Pipeline Methodology Fixes — Implementation Plan

**Created:** 2026-05-16 (updated with user feedback)
**Source:** `betting/journal/2026-05-16-pipeline-errors.md`
**Scope:** Code bugs + documentation fixes + agent enforcement + Flashscore circuit breaker to prevent 13+ methodology violations from recurring.

**User additions (v2):**
1. **Agent enforcement:** The orchestrator didn't call subagents on 2026-05-16. The prompt has delegation templates but no mechanical verification. Fix: add delegation compliance gate + simplify the 1000-line prompt.
2. **Flashscore circuit breaker:** Playwright rate limit (10/10) exhausted instantly, but enrichment kept trying Flashscore for 8+ minutes. Fix: per-source circuit breaker.

---

## Phase 1: Python Script Code Fixes

### Task 1.1: Fix misleading "tennis player" log message + dead code
[MODIFY] `scripts/data_enrichment_agent.py`

**Problem:** Line ~1137 — when Flashscore retry loop exhausts all attempts, the `else` clause logs `"Skipping Flashscore HTML for tennis player '{team_name}'"` regardless of actual sport. Additionally, lines 1132-1135 (`if err:` / `if attempt < max_retries:`) are UNREACHABLE dead code — there's a `return result` at line 1131 that always executes before them.

**Changes:**
1. **Line ~1137:** Replace misleading log message:
   - Old: `logger.info(f"Skipping Flashscore HTML for tennis player '{team_name}' — player pages 404")`
   - New: `logger.info(f"Flashscore retry exhausted for {sport} entity '{team_name}' — all attempts returned no data")`
2. **Lines 1132-1135:** Remove unreachable dead code block (`if err:` / `if attempt < max_retries:` / `time.sleep(1.0)`) that sits after `return result`.

**Definition of Done:**
- [ ] Log message includes actual `sport` parameter, not hardcoded "tennis player"
- [ ] Unreachable code after `return result` is removed
- [ ] Existing tests pass (`pytest tests/ -k enrichment`)

---

### Task 1.2: Add consecutive failure early-break in `batch_enrich()` Phase 2
[MODIFY] `scripts/data_enrichment_agent.py`

**Problem:** `batch_enrich()` Phase 2 (lines ~1382-1396) retries ALL failed teams on the main thread even after hitting rate limits or seeing hundreds of consecutive failures. This wastes 8+ minutes enriching irrelevant teams.

**Changes in `batch_enrich()` function (around line 1382):**
1. Add a `consecutive_failures` counter initialized to 0 before the Phase 2 loop.
2. On each successful retry (stats found), reset counter to 0.
3. On each failure, increment counter.
4. After counter reaches `MAX_CONSECUTIVE_FAILURES = 15`, log a WARNING and `break` the Phase 2 loop.
5. Include the break reason in the function's return (add a summary log).

**Sketch:**
```python
MAX_CONSECUTIVE_FAILURES = 15
consecutive_failures = 0
for i, res in enumerate(retry_needed):
    # ... existing retry logic ...
    try:
        retry_res = enrich_team(team_name, sport)
        if retry_res.get("stats_found") or retry_res.get("status") == "enriched":
            results[retry_indices[i]] = retry_res
            consecutive_failures = 0
        else:
            consecutive_failures += 1
    except Exception as exc:
        consecutive_failures += 1
        logger.debug(...)
    
    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        remaining = len(retry_needed) - (i + 1)
        logger.warning(
            f"[batch_enrich] Phase 2 early-break: {consecutive_failures} consecutive failures. "
            f"Skipping remaining {remaining} teams."
        )
        break
```

**Definition of Done:**
- [ ] Phase 2 loop breaks after 15 consecutive failures
- [ ] Warning log emitted with count of skipped teams
- [ ] Counter resets on any successful enrichment
- [ ] Existing tests pass

---

### Task 1.3: Add prominent WARNING when `--no-enrich` flag is active
[MODIFY] `scripts/deep_stats_report.py`

**Problem:** Lines 1773-1774 — `--no-enrich` silently sets `NO_ENRICH=1` environment variable with no prominent log output. Agents use it without understanding it skips ALL inline enrichment, leading to degraded data quality.

**Changes around line 1774:**
After `os.environ["NO_ENRICH"] = "1"`, add a prominent warning:
```python
if args.no_enrich:
    os.environ["NO_ENRICH"] = "1"
    out.warning("⚠️  --no-enrich ACTIVE: ALL inline enrichment SKIPPED. "
                "Candidates without cached/DB data will have MINIMAL quality. "
                "Only use this flag when enrichment already ran separately.")
```

Also add a summary metric at the end of `generate_deep_stats()` that reports how many candidates had no data due to `no_enrich` mode.

**Definition of Done:**
- [ ] Prominent WARNING log emitted when `--no-enrich` is used
- [ ] Warning includes explanation of impact (no inline enrichment)
- [ ] AGENT_SUMMARY includes `"no_enrich": true` flag when active
- [ ] Existing tests pass

---

### Task 1.4: Fix scraper status masking in `run_scrapers.py`
[MODIFY] `scripts/run_scrapers.py`

**Problem:** `run_single()` (lines 45-87) initializes `results["status"] = "ok"` and NEVER changes it, even when `team_stats` or `player_stats` fail with exceptions. The AGENT_SUMMARY verdict (line ~170) checks `all(r["status"] == "ok")` which is ALWAYS true, masking all failures.

**Changes in `run_single()` function:**
1. After each `except Exception` block that sets `results["counts"][key] = f"error: {e}"`, also set `results["status"] = "partial"`.
2. Only keep `"ok"` if no exceptions were raised.

**Sketch for each existing except block:**
```python
except Exception as e:
    log.warning("  team_stats FAILED: %s", e)
    results["counts"]["team_stats"] = f"error: {e}"
    results["status"] = "partial"  # ← ADD THIS LINE
```

Apply to all 3 `except Exception` blocks (team_stats, player_stats, fixtures).

**Also update AGENT_SUMMARY** (line ~170) to count failures:
```python
failures = [r for r in all_results if r["status"] != "ok"]
print("\n" + "=" * 60)
print("AGENT_SUMMARY:" + json.dumps({
    "verdict": "OK" if not failures else "PARTIAL",
    "scrapers_run": len(all_results),
    "scrapers_failed": len(failures),
    "failed_sources": [f"{r['sport']}/{r['source']}" for r in failures],
    "results": all_results,
}))
```

**Definition of Done:**
- [ ] `run_single()` sets `status = "partial"` on any exception
- [ ] AGENT_SUMMARY verdict correctly reflects actual failures
- [ ] AGENT_SUMMARY includes `scrapers_failed` count and `failed_sources` list
- [ ] Existing tests pass

---

### Task 1.5: Document team_form concurrent write hazard
[MODIFY] `src/bet/db/repositories.py`

**Problem:** `save_team_form()` (lines 518-559) uses DELETE+INSERT with SAVEPOINT — atomic for single writes but NOT safe against concurrent writers from different scripts (data_enrichment_agent, deep_stats_report inline enrichment, build_stats_cache). Last-writer-wins.

**Changes:**
Add a docstring warning to `save_team_form()`:
```python
def save_team_form(self, form: TeamForm) -> None:
    """Upsert team_form row (denormalized cache).

    Uses DELETE+INSERT wrapped in a SAVEPOINT to ensure atomicity.
    SQLite ON CONFLICT doesn't work with expression-based unique indexes
    (NULL h2h_opponent_id).

    ⚠️ CONCURRENT WRITE HAZARD: Three scripts write team_form:
    - build_stats_cache.py (via ingest_scan_stats)
    - data_enrichment_agent.py (via _save_to_db)
    - deep_stats_report.py (inline enrichment when NO_ENRICH is not set)
    Pipeline must serialize these writes (run sequentially, not in parallel).
    If parallel execution is needed, use WAL mode + retry on SQLITE_BUSY.
    """
```

**Definition of Done:**
- [ ] Docstring documents the concurrent write hazard
- [ ] Lists all three scripts that write team_form
- [ ] Recommends serialization or WAL mode
- [ ] No functional code changes

---

### Task 1.6: Add per-source circuit breaker to `enrich_team()`
[MODIFY] `scripts/data_enrichment_agent.py`

**Problem:** ERROR 10 from pipeline-errors: "Playwright rate limit reached (10/10)" within 1 minute, then hundreds more teams still attempted via Flashscore. Each call to `enrich_team()` tries Flashscore independently — it doesn't know that Flashscore has been returning errors for the past 30 teams. There's no source-level circuit breaker.

**Changes:**
1. Add a module-level `_source_circuit_breaker` dict tracking consecutive failures per source domain.
2. In `enrich_team()`, before calling `_try_flashscore()`: check if `flashscore.com` has ≥5 consecutive failures → skip it entirely, fall through to next source.
3. Same for `_try_scores24()` and `scores24.live` domain.
4. On success: reset that source's failure counter to 0.
5. On failure: increment.
6. Log a WARNING when a source is circuit-broken: `"[Circuit Breaker] Skipping flashscore.com — {N} consecutive failures. Source marked DOWN for this run."`

**Sketch:**
```python
# Module-level circuit breaker (thread-safe)
_source_failures: dict[str, int] = {}
_source_lock = threading.Lock()
CIRCUIT_BREAKER_THRESHOLD = 5

def _source_is_down(domain: str) -> bool:
    """Check if a source has exceeded the circuit breaker threshold."""
    with _source_lock:
        return _source_failures.get(domain, 0) >= CIRCUIT_BREAKER_THRESHOLD

def _record_source_failure(domain: str) -> None:
    with _source_lock:
        _source_failures[domain] = _source_failures.get(domain, 0) + 1
        if _source_failures[domain] == CIRCUIT_BREAKER_THRESHOLD:
            logger.warning(f"[Circuit Breaker] {domain} marked DOWN — {CIRCUIT_BREAKER_THRESHOLD} consecutive failures")

def _record_source_success(domain: str) -> None:
    with _source_lock:
        _source_failures[domain] = 0
```

Then in `enrich_team()`, wrap the Flashscore retry loop:
```python
    # Try Flashscore (skip if circuit-broken)
    if not _source_is_down("flashscore.com"):
        for attempt in range(1, max_retries + 1):
            stats, err = _try_flashscore(team_name, sport)
            if stats:
                _record_source_success("flashscore.com")
                # ... existing success logic ...
                return result
        else:
            _record_source_failure("flashscore.com")
            logger.info(f"Flashscore retry exhausted for {sport} entity '{team_name}' — all attempts returned no data")
    else:
        logger.debug(f"Skipping Flashscore for {team_name} — source circuit-broken")
```

**Definition of Done:**
- [ ] Per-source circuit breaker with threshold of 5 consecutive failures
- [ ] Thread-safe (module-level lock)
- [ ] WARNING log when source is circuit-broken
- [ ] Flashscore, Scores24 both protected
- [ ] Counter resets on ANY success for that source
- [ ] Existing tests pass

---

## Phase 2: Agent Documentation Fixes

### Task 2.1: Fix bet-enricher.agent.md schema and DB references
[MODIFY] `.github/agents/bet-enricher.agent.md`

**Problem:** The "Key Behaviors / Manual Enrichment DB Write" code example (lines ~117-120) references a `form_data` column that does NOT exist in the `team_form` table. The actual schema has `stat_key`, `l10_values`, `l5_values`, `l10_avg`, `l5_avg`, `h2h_values`, `h2h_opponent_id`, `trend`, `source`. Also uses raw `conn.execute()` which violates R2 (DB-FIRST).

**Changes:**
1. Replace the raw SQL code block (lines 112-121) with proper repository usage:
```python
from bet.db.connection import get_db
from bet.db.repositories import TeamRepo, StatsRepo
from bet.db.models import TeamForm

try:
    team = TeamRepo.find_or_create(team_name, sport)
except ValueError as e:
    logger.warning(f"Rejected garbage team name: {team_name} — {e}")
    return

with get_db() as conn:
    stats_repo = StatsRepo(conn)
    form = TeamForm(
        id=None,
        team_id=team.id,
        sport_id=sport_id,
        stat_key=stat_key,
        l10_values=l10_values,
        l5_values=l5_values,
        l10_avg=l10_avg,
        l5_avg=l5_avg,
        h2h_values=[],
        h2h_opponent_id=None,
        trend="",
        updated_at=None,
        source="enrichment-agent",
    )
    stats_repo.save_team_form(form)
    conn.commit()
```

2. **Line ~241:** Replace `sqlite3.OperationalError: database is locked` with the correct guidance:
   - Old: "wait 5s, retry once"
   - New: "This indicates concurrent writes to team_form. Check that enrichment and deep_stats are not running simultaneously. See `save_team_form()` docstring for details."

**Definition of Done:**
- [ ] Code example uses `StatsRepo.save_team_form()` instead of raw SQL
- [ ] No reference to non-existent `form_data` column
- [ ] Correct `TeamForm` fields shown (stat_key, l10_values, l5_values, etc.)
- [ ] `sqlite3.OperationalError` guidance updated to mention concurrent write hazard

---

### Task 2.2: Fix bet-statistician.agent.md match_stats assumption
[MODIFY] `.github/agents/bet-statistician.agent.md`

**Problem:** Lines 63 and 77 reference `match_stats` as a primary data source, but no current pipeline step reliably populates it. `fetch_api_stats.py` was removed; only `data_enrichment_agent.py` writes to `match_stats` sporadically.

**Changes:**
1. **Line 63 (DB-first workflow):** Add caveat:
   - Change `"team_form", "match_stats", "analysis_results"` to `"team_form" (PRIMARY), "match_stats" (sparse — only populated by enrichment agent for some teams), "analysis_results"`
2. **Line 77 (Database Access list):** Add note:
   - Change `match_stats — per-fixture per-team stat values (corners, fouls, shots, etc.)` to `match_stats — per-fixture per-team stat values. ⚠️ SPARSELY POPULATED: only written by enrichment agent. Primary L10/L5 data source is team_form. If match_stats is empty for a team, fall back to team_form.l10_values.`

**Definition of Done:**
- [ ] `match_stats` documented as sparsely populated with explicit fallback to `team_form`
- [ ] DB-first workflow lists `team_form` as PRIMARY
- [ ] Agent knows to check `team_form` first, not `match_stats`

---

### Task 2.3: Add script-to-table data flow matrix to bet-orchestrator.agent.md
[MODIFY] `.github/agents/bet-orchestrator.agent.md`

**Problem:** No centralized reference for which script writes which DB table. Agents make wrong assumptions about data availability.

**Changes:** Add a new section after the "Identity" section:

```markdown
## Script → DB Table Data Flow Matrix

| Script | Reads | Writes | Notes |
|--------|-------|--------|-------|
| `discover_events.py` | scan_urls.json | `fixtures`, `scan_results` | S1 scan |
| `build_stats_cache.py` | `fixtures`, stats_cache/ | `team_form` | Ingests scan stats |
| `run_scrapers.py` | — | `league_profiles`, `player_season_stats`, `athletes`, `scraper_runs` | S2.3 — does NOT write team_form |
| `data_enrichment_agent.py` | `team_form`, `fixtures` | `team_form`, `match_stats`, `source_health` | S2.5 gap-fill |
| `deep_stats_report.py` | `team_form`, `match_stats` | `analysis_results`, `team_form` (if inline enrich) | S3 — writes team_form ONLY when --no-enrich is NOT set |
| `compute_safety_scores.py` | `team_form` | — (stdout) | Pure computation |
| `odds_evaluator.py` | `odds_history`, analysis_results | `analysis_results` (EV injection) | S4 |
| `context_checks.py` | `fixtures`, ESPN API | `analysis_results` (context) | S5 |
| `upset_risk.py` | `analysis_results` | `analysis_results` (upset risk) | S6 |
| `gate_checker.py` | `analysis_results` | `gate_results` | S7 |
| `coupon_builder.py` | `gate_results`, `analysis_results` | coupons/*.md, coupons/*.json | S8 |
| `settle_on_finish.py` | betclic_bets_history.json | `bets`, `coupons` | S0 |

⚠️ **Concurrent write hazard:** `build_stats_cache`, `data_enrichment_agent`, and `deep_stats_report` all write `team_form`. Run sequentially.
```

**Definition of Done:**
- [ ] Data flow matrix present in orchestrator agent
- [ ] All 12+ pipeline scripts mapped to their DB reads/writes
- [ ] Concurrent write hazard noted
- [ ] Matrix is accurate (verified against actual script code)

---

### Task 2.4: Agent definitions consistency audit — all 9 specialist agents
[MODIFY] All `.github/agents/bet-*.agent.md` files (9 agents)

**Problem:** The orchestrator on 2026-05-16 didn't call subagents. One root cause: agent definitions have inconsistencies that may confuse the orchestrator about how to delegate. Some agents have `user-invokable: true` but shouldn't (or vice versa). Some are missing critical skills. Some have outdated rules references.

**Changes — audit and fix each agent for consistency:**

| Agent | Check | Fix if needed |
|-------|-------|---------------|
| bet-scanner | `user-invokable: true` correct (can be called directly for scanning) | ✅ OK |
| bet-enricher | `user-invokable: false` — cannot run scripts per R17. Check: description matches actual role (data quality guardian, NOT script runner) | Fix description if it says "triggers enrichment" — it ANALYZES enrichment output |
| bet-statistician | Skills: needs `bet-analyzing-statistics`, `bet-applying-sport-protocols`. Check match_stats issue (Task 2.2) | Ensure skills array is complete |
| bet-scout | `user-invokable: false`. Role: tipster analysis only. | Verify has `bet-navigating-sources` skill |
| bet-valuator | `user-invokable: false`. Role: odds analysis only. | Verify has `bet-evaluating-odds` skill |
| bet-challenger | `user-invokable: false`. Role: context + upset + gate analysis. | Verify has adversarial reasoning focus |
| bet-builder | `user-invokable: false`. Role: portfolio analysis only. | Verify has `bet-building-coupons`, `bet-formatting-artifacts` |
| bet-settler | Check if `user-invokable` should be true (settlement can be standalone) | Verify settlement skills |
| bet-db-analyst | `user-invokable: false`. Role: DB quality analysis. | Verify has `bet-querying-database` skill |

**Consistency checks for ALL agents:**
1. Every agent has R17 ANALYSIS-ONLY rule in MY RULES table (except bet-scanner which has dual-mode R17)
2. Every agent has `agent-execution-protocol.instructions.md` in instructions array
3. Every agent has `analysis-methodology.instructions.md` in instructions array
4. Every agent's description is accurate (matches actual role, no contradictions)
5. Every agent has `model: "Claude Opus 4.6 (Copilot)"` (consistent model)
6. Every agent has `sequential-thinking/*` in tools (needed for R11)

**Definition of Done:**
- [ ] All 9 agents audited against 6 consistency checks
- [ ] Any inconsistencies fixed
- [ ] All agents have R17 analysis-only rule
- [ ] All agents have correct skills array
- [ ] All agents have correct instructions array

---

## Phase 3: Prompt Fixes

### Task 3.1: Add missing anti-patterns to orchestrate-betting-day.prompt.md
[MODIFY] `.github/prompts/orchestrate-betting-day.prompt.md`

**Problem:** The anti-pattern list (lines ~977-995) is missing three patterns that caused the 2026-05-16 failures.

**Changes:** Add to the anti-pattern table (after entry #15):

```markdown
| 16 | Use `--no-enrich` or `--exclude` without logging impact | These flags silently degrade data quality. ALWAYS log what was skipped and why. |
| 17 | Skip steps S4/S5/S6 and jump to S7/S8 | EVERY step S3→S7 is MANDATORY. S4=odds, S5=context, S6=upset risk. Skipping = coupon with zero EV, zero injuries, zero bear cases. |
| 18 | Use script flags you haven't read the code for | R18: Before using ANY flag (--no-enrich, --exclude, --top, --from-db), READ the script to understand its effect. Unknown flags = unknown consequences. |
```

**Definition of Done:**
- [ ] Three new anti-patterns (#16, #17, #18) added
- [ ] Each explains WHY the pattern kills the pipeline
- [ ] Anti-pattern #17 explicitly lists S4/S5/S6 as mandatory

---

### Task 3.2: Add step-skip detection to orchestrate-betting-day.prompt.md
[MODIFY] `.github/prompts/orchestrate-betting-day.prompt.md`

**Problem:** The orchestrator has no mechanism to detect when it accidentally skips steps (went S3→S7 on 2026-05-16, skipping S4/S5/S6).

**Changes:** Add a new section between "ANTI-PATTERNS" and "§THINK IN THE MIDDLE":

```markdown
## §STEP COMPLETENESS GATE

Before running S7 (gate_checker), verify ALL prior analytical steps completed:

| Step | Script | Verification |
|------|--------|-------------|
| S3 | deep_stats_report.py | `{date}_s3_deep_stats.json` exists, >0 candidates |
| S4 | odds_evaluator.py | `analysis_results` has EV data for ≥1 candidate |
| S5 | context_checks.py | `analysis_results` has injury/weather context for ≥1 candidate |
| S6 | upset_risk.py | `analysis_results` has upset_risk data for ≥1 candidate |

**If ANY step is missing → STOP. Do NOT proceed to S7.** Run the missing step first.

Use `inspect_pipeline.py --step all --date {run_date}` to check completeness programmatically.
```

**Definition of Done:**
- [ ] Step completeness gate section added
- [ ] Lists all required steps S3-S6 with verification criteria
- [ ] Explicit STOP instruction when steps are missing
- [ ] References `inspect_pipeline.py` for programmatic checking

---

### Task 3.3: Add pipeline-errors.md as S0 learning input
[MODIFY] `.github/prompts/orchestrate-betting-day.prompt.md`

**Problem:** STEP 0 (line ~57) loads context files but does NOT include the pipeline error journal as a learning input.

**Changes:** Add to STEP 0 file list (after item 8):
```markdown
9. `betting/journal/{previous_date}-pipeline-errors.md` — **If exists:** Post-mortem from previous session. Read BEFORE starting to avoid repeating same mistakes.
```

**Definition of Done:**
- [ ] Pipeline errors journal added to S0 context loading
- [ ] Conditional loading (only if file exists for previous date)
- [ ] Described as post-mortem learning input

---

### Task 3.4: Add DELEGATION COMPLIANCE GATE to orchestration prompt
[MODIFY] `.github/prompts/orchestrate-betting-day.prompt.md`

**Problem:** The 2026-05-16 orchestrator ran scripts but NEVER called `runSubagent`. The prompt has detailed delegation templates for every step, but NO mechanism to verify that delegation actually happened. The orchestrator "forgot" to delegate, and nothing caught it.

**Changes:** Add a new section `§DELEGATION COMPLIANCE GATE` after `§STEP COMPLETENESS GATE`:

```markdown
## §DELEGATION COMPLIANCE GATE (MANDATORY — maintain throughout session)

**The pipeline's ENTIRE VALUE is in specialist agent analysis. Without delegation, you are a script runner.**

### Running Checklist (update after EVERY step)

Maintain this checklist. Before proceeding to the next step, verify the current step's delegation:

| Step | Script Ran | Agent Delegated | Agent Name | Verdict Received | Quality Gate Passed |
|------|-----------|----------------|------------|-----------------|-------------------|
| S0   | ☐         | ☐              | bet-settler | ☐               | ☐                 |
| S0.5 | ☐         | ☐              | bet-db-analyst | ☐            | ☐                 |
| S1   | ☐         | ☐              | bet-scanner | ☐               | ☐                 |
| S1e  | ☐         | ☐              | bet-scanner | ☐               | ☐                 |
| S2   | ☐         | ☐              | bet-scout   | ☐               | ☐                 |
| S2.5 | ☐         | ☐              | bet-enricher | ☐              | ☐                 |
| S3   | ☐         | ☐              | bet-statistician | ☐          | ☐                 |
| S4   | ☐         | ☐              | bet-valuator | ☐              | ☐                 |
| S5+6 | ☐         | ☐              | bet-challenger | ☐            | ☐                 |
| S7   | ☐         | ☐              | bet-challenger | ☐            | ☐                 |
| S8   | ☐         | ☐              | bet-builder | ☐               | ☐                 |

**RULES:**
1. **Script Ran + Agent NOT Delegated = VIOLATION.** Do NOT proceed to the next step.
2. **Before S7:** ALL of S3, S4, S5+6 must show ☑ in "Agent Delegated" column.
3. **Before S8:** S7 must show ☑ in "Agent Delegated" column.
4. **Before presenting to user:** ALL steps must show ☑ in both "Agent Delegated" AND "Quality Gate Passed."

**If you catch yourself about to skip delegation:** STOP. Read the delegation template for that step (in this prompt). Run `runSubagent`. This is the pipeline's core value — specialist analysis.
```

**Also enhance the existing §STEP COMPLETENESS GATE (Task 3.2)** to include delegation verification:
```markdown
## §STEP COMPLETENESS GATE (enhanced)

Before running S7, verify ALL:
| Step | Script Output Exists | Specialist Agent Analyzed |
|------|---------------------|--------------------------|
| S3   | ☑ deep_stats exists   | ☑ bet-statistician verdict |
| S4   | ☑ EV data in DB       | ☑ bet-valuator verdict     |
| S5   | ☑ context data in DB  | ☑ bet-challenger verdict   |
| S6   | ☑ upset_risk in DB    | ☑ bet-challenger verdict   |

**If ANY "Specialist Agent Analyzed" is ☐ → STOP. Delegate to the missing agent BEFORE proceeding.**
```

**Definition of Done:**
- [ ] §DELEGATION COMPLIANCE GATE section with running checklist
- [ ] Checklist covers all 11 pipeline steps with agent names
- [ ] VIOLATION rule: script + no delegation = cannot proceed
- [ ] §STEP COMPLETENESS GATE enhanced to include agent delegation verification
- [ ] 4 clear rules about when gates trigger

---

### Task 3.5: Simplify orchestration prompt — extract verbose delegation blocks
[MODIFY] `.github/prompts/orchestrate-betting-day.prompt.md`

**Problem:** The prompt is ~1000 lines. Each step has a ~30-line delegation template copy-pasted verbatim (runSubagent block with full context, expected response format, analysis-only mode instructions). This repetition causes:
1. Cognitive overload — the LLM loses focus on critical rules
2. Inconsistency — templates drift across steps
3. Maintenance burden — changes to the delegation format require 11 edits

**Changes:**
1. **Extract the COMMON delegation footer** (⛔ Analysis-Only Mode, Expected Response Format) into a single section `§DELEGATION FOOTER` at the top of the prompt.
2. **Simplify each step's delegation block** from ~30 lines to ~10 lines:

Before (current — repeated 11 times):
```
runSubagent("bet-statistician"):
---
## Task: Analyze S3 Deep Stats output for {date}

[Paste content of .github/internal-prompts/bet-deep-stats.prompt.md]

### Script Output (already executed by orchestrator)
AGENT_SUMMARY: {paste extracted JSON}
Exit code: {0|1|2}
Key warnings: {paste data quality issues, missing H2H, etc.}

### Upstream Context
- Enrichment verdict: {from S2.5}
...

### ⛔ Analysis-Only Mode
DO NOT run deep_stats_report.py. Analyze the provided output with specialist knowledge.
Use pylanceRunCodeSnippet to read deep stats JSON for per-candidate details.
Use sequentialthinking for EVERY CANDIDATE (5-part Analytical Reasoning Layer).
Load skills: bet-analyzing-statistics, bet-applying-sport-protocols
Key checks: R5 (stat markets FIRST), three-way cross-check, edge mechanisms
Return: Model A analysis-only verdict
---
```

After (simplified):
```
**Delegate to bet-statistician** — read `.github/internal-prompts/bet-deep-stats.prompt.md`.
Pass: AGENT_SUMMARY JSON + key warnings + upstream S2.5 verdict.
Focus: R5 compliance, three-way cross-check, edge mechanisms.
Append §DELEGATION FOOTER.
```

3. **§DELEGATION FOOTER** (define once, reference everywhere):
```markdown
## §DELEGATION FOOTER (append to every runSubagent call)

### ⛔ Analysis-Only Mode
You do NOT run any scripts. The orchestrator has already run the script and extracted output.
Analyze the provided AGENT_SUMMARY and log excerpts with your specialist knowledge.
Use pylanceRunCodeSnippet for deeper data inspection. Use sequentialthinking for per-candidate reasoning.

### Expected Response Format
Return Model A analysis-only verdict (agent-execution-protocol.instructions.md):
- `subagent_verdict` block: verdict, quality_score, script, exit_code, execution_model: analysis-only
- `### Metrics` — ≥3 specific metrics from script output
- `### Anomalies` — specific anomaly + root cause
- `### Analysis` — YOUR original specialist reasoning
- `### Impact` — what this means for the pipeline
- `### Issues` — specific blockers or "None"
- `### User Summary` — 2-3 plain-language sentences
- `### Data For Orchestrator` — next_step_ready, quality_flags, focus_points
```

4. **Net result:** Prompt shrinks from ~1000 lines to ~700 lines. Critical rules become more visible. Delegation format is defined ONCE and referenced everywhere.

**Definition of Done:**
- [ ] §DELEGATION FOOTER section created (single source of truth for delegation format)
- [ ] All 11 step delegation blocks simplified to ~10 lines each (from ~30)
- [ ] §DELEGATION TEMPLATE section (the verbose example) consolidated or removed
- [ ] Total prompt length reduced by ≥200 lines
- [ ] All steps still reference correct internal prompts and agent names
- [ ] No loss of critical information (focus points per step still present)

---

## Phase 4: Instruction Updates

### Task 4.1: Add Zero Tolerance entries for 2026-05-16 errors
[MODIFY] `.github/instructions/analysis-methodology.instructions.md`

**Problem:** The Zero Tolerance Shield (line ~1049) doesn't cover the 2026-05-16 failure patterns.

**Changes:** Add entries #22-#25 to the Zero Tolerance table:

```markdown
| 22 | S3→S7 with S4/S5/S6 skipped — coupon had zero EV, zero injuries, zero upset risk | Orchestrator rushed to completion, confused "script ran" with "step complete" | §STEP COMPLETENESS GATE: verify S3+S4+S5+S6 all completed BEFORE running S7. Missing any = STOP. |
| 23 | Enrichment logged "tennis player" for football teams (VfL Osnabrück, FC St. Pauli) — 0% Flashscore data | Flashscore retry loop `else` clause had hardcoded "tennis player" log regardless of sport + dead code after `return` | Fix deployed in data_enrichment_agent.py. Log must include actual sport parameter. |
| 24 | Enrichment ran 8+ min enriching Norwegian 5th div / Slovenian 4th div while shortlist teams had 0 data | batch_enrich Phase 2 had no early-break — iterated ALL failed teams even after rate limit exhausted | Early-break after 15 consecutive failures. Per-source circuit breaker after 5 failures. |
| 25 | `--no-enrich` used without understanding → all candidates got PARTIAL (5/10) data quality | Flag silently skips ALL inline enrichment with no warning log | Prominent WARNING log when flag is active. Anti-pattern #18: never use flags you haven't read the code for. |
| 26 | Orchestrator ran all scripts but NEVER called runSubagent — zero specialist analysis, zero bear cases, zero edge reasoning | No mechanical enforcement of delegation. Prompt had templates but no gate checking they were used. | §DELEGATION COMPLIANCE GATE: running checklist per step. Script + no delegation = VIOLATION = cannot proceed. |
| 27 | Flashscore rate limit (10/10) exhausted in <1 min, then enrichment kept trying Flashscore for 8+ min per team | No per-source circuit breaker. Each enrich_team() call tried Flashscore independently, unaware it was down. | Per-source circuit breaker: 5 consecutive failures → source marked DOWN for the run. Skip all future calls. |
```

**Definition of Done:**
- [ ] Six new ZT entries added (#22-#27)
- [ ] Each has: failure description, root cause, prevention
- [ ] Prevention references the specific code/prompt fix from this plan

---

## Phase 5: Memory Update

### Task 5.1: Update pipeline-knowledge-base.md with 2026-05-16 findings
[MODIFY] `/memories/repo/pipeline-knowledge-base.md`

**Changes:** Add a new section at the top (after the header):

```markdown
## 🆕 METHODOLOGY FIX — 2026-05-16

**Plan:** `specifications/pipeline-methodology-fixes.plan.md` — 5 phases, 16 tasks.

### Bugs Fixed
- **data_enrichment_agent.py:** Misleading "tennis player" log (line ~1137) → now shows actual sport. Dead code removed. batch_enrich Phase 2 gets early-break after 15 consecutive failures. Per-source circuit breaker (5 failures → skip source for rest of run).
- **deep_stats_report.py:** `--no-enrich` now emits prominent WARNING log.
- **run_scrapers.py:** Scraper failures now correctly set status="partial" instead of masking as "ok". AGENT_SUMMARY reports failure count.
- **repositories.py:** `save_team_form()` docstring documents concurrent write hazard.

### Documentation Fixed
- **All 9 bet-*.agent.md:** Consistency audit — R17 analysis-only rule, correct skills, correct instructions array.
- **bet-enricher.agent.md:** Removed non-existent `form_data` column reference. Raw SQL replaced with StatsRepo.save_team_form(). sqlite3 error guidance updated.
- **bet-statistician.agent.md:** match_stats documented as sparsely populated. team_form marked as PRIMARY.
- **bet-orchestrator.agent.md:** Script→DB table data flow matrix added (12 scripts mapped).
- **orchestrate-betting-day.prompt.md:** 3 new anti-patterns (#16-#18), §STEP COMPLETENESS GATE, §DELEGATION COMPLIANCE GATE, pipeline-errors.md in S0 context, prompt simplified from ~1000 to ~700 lines.
- **analysis-methodology.instructions.md:** ZT entries #22-#27 for step-skip, tennis-log, no-early-break, --no-enrich, no delegation, circuit breaker.

### Root Cause
Orchestrator confused "script ran" with "step complete." Skipped S4/S5/S6 entirely. Never called runSubagent despite having templates. Used --no-enrich without understanding impact. Enrichment ran unbounded on irrelevant teams — no circuit breaker.
```

**Definition of Done:**
- [ ] 2026-05-16 section added to knowledge base
- [ ] All bugs and documentation fixes listed
- [ ] Root cause documented
- [ ] Plan file referenced

---

## Execution Order & Dependencies

```
Phase 1 (Code) → independent tasks, can be done in any order
  1.1 → no deps
  1.2 → no deps
  1.3 → no deps
  1.4 → no deps
  1.5 → no deps (documentation only)

Phase 2 (Agent Docs) → depends on Phase 1 being designed (references fixes)
  2.1 → no deps
  2.2 → no deps
  2.3 → no deps

Phase 3 (Prompt) → independent of Phases 1-2
  3.1 → no deps
  3.2 → no deps
  3.3 → no deps

Phase 4 (Instructions) → references Phases 1-3 fixes
  4.1 → after Phases 1-3 are planned

Phase 5 (Memory) → after all other phases
  5.1 → after Phases 1-4
```

## Test Strategy

- **Unit tests:** Tasks 1.1-1.4 should have corresponding pytest tests verifying the fix (log output, early-break behavior, status propagation).
- **Integration:** After all fixes, run full pipeline for one date and verify:
  - Enrichment log shows correct sport names
  - Enrichment stops after consecutive failures
  - `--no-enrich` shows WARNING
  - Scraper failures propagate to AGENT_SUMMARY
  - All S3-S6 steps verified before S7
- **No manual QA needed** — all verification is code-reviewable.
