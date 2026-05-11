# Scan Self-Verification — Implementation Plan v2

**Created:** 2026-05-11
**Status:** DRAFT
**Replaces:** v1 (REJECTED — created a new script, kept orchestrator fat)

---

## Design Principles

1. **NO new Python scripts.** Verification = agent reading DB via inline Python + reasoning.
2. **Per-sport agents own their full lifecycle** — scan + verify + self-heal + report.
3. **Orchestrator is THIN** — dispatch, wait, aggregate.
4. **SHORTER = BETTER** — enhanced Step 2 adds ≤30 lines per agent file.
5. **Agents are COLLECTORS + VERIFIERS, not CALCULATORS** — they check "did I collect enough good data?"

## Architecture

```
bet-scanner (THIN coordinator)
  ├─ PHASE 1: run scan_events.py --parallel-sport (existing)
  ├─ PHASE 2: dispatch 5 per-sport agents in VERIFICATION mode
  │    ├─ bet-scanner-football   → Step 2 (enhanced)
  │    ├─ bet-scanner-basketball → Step 2 (enhanced)
  │    ├─ bet-scanner-tennis     → Step 2 (enhanced)
  │    ├─ bet-scanner-volleyball → Step 2 (enhanced)
  │    └─ bet-scanner-hockey     → Step 2 (enhanced)
  └─ PHASE 3: aggregate verdicts → proceed or heal
```

Each per-sport agent's enhanced Step 2 runs 6 verification checks via inline DB queries, then the agent interprets results using `sequentialthinking`.

---

## Files to Modify

| # | File | Action | Change Summary | Est. Lines |
|---|------|--------|----------------|------------|
| 1 | `bet-scanner.agent.md` | [MODIFY] | Slim down: remove KNOWLEDGE BASE, KNOWN PIPELINE GAPS, duplicated OPERATIONAL WORKFLOW, detailed validation snippets. Replace with thin dispatch-aggregate flow. | −150 |
| 2 | `bet-scanner-football.agent.md` | [MODIFY] | Add verification mode to Step 0, enhance Step 2 with 6 checks + interpretation guidance | +25 |
| 3 | `bet-scanner-basketball.agent.md` | [MODIFY] | Same structure as football, basketball-specific params/interpretation | +25 |
| 4 | `bet-scanner-tennis.agent.md` | [MODIFY] | Same structure, tennis-specific params/interpretation | +25 |
| 5 | `bet-scanner-volleyball.agent.md` | [MODIFY] | Same structure, volleyball-specific params/interpretation | +25 |
| 6 | `bet-scanner-hockey.agent.md` | [MODIFY] | Same structure, hockey-specific params/interpretation | +25 |
| 7 | `bet-scan.prompt.md` | [MODIFY] | Update workflow description to reflect per-sport verification | +5 |

**No new files. No new scripts.**

---

## Phase A: Slim Down Orchestrator [MODIFY bet-scanner.agent.md]

### What to REMOVE

| Section | Current Location | Lines | Reason |
|---------|-----------------|-------|--------|
| KNOWLEDGE BASE: What "Rich Data" Means Per Sport | Lines ~200-250 | ~50 | Per-sport agents know their own data requirements |
| KNOWN PIPELINE GAPS table | Lines ~260-290 | ~30 | Move relevant gaps to each sport's agent |
| Duplicated OPERATIONAL WORKFLOW (2nd copy) | Lines ~300-420 | ~120 | Duplicate of Phase 1-3 with different commands and inline Python validation blocks |

### What to KEEP (slimmed)

**PHASE 1: PARALLEL SCAN** — Keep as-is (the `scan_events.py --parallel-sport` command + timeout table).

**PHASE 2: DISPATCH VERIFICATION** — Replace current PHASE 2 (detailed health monitoring + self-healing delegation) with:

```markdown
### PHASE 2: PER-SPORT VERIFICATION — Dispatch agents

After parallel scan completes, dispatch each per-sport agent in **verification mode**:

**Dispatch prompt:**
> Parallel scan completed. Verify your sport's scan results — run your enhanced Step 2.
> Date: {date}. Report: event count, data quality, league coverage, issues found.

Dispatch all 5 agents. Each runs Step 2 (DB queries + interpretation) and reports back with:
- Event count + verdict (PASS/MARGINAL/FAIL)
- Phantom fixtures found
- Missing leagues vs yesterday
- Data completeness %
- Sport-specific stat coverage
- Self-heal recommendation (if FAIL)

### PHASE 2b: AGGREGATE + DECIDE

After all 5 agents report:

| Check | Gate |
|-------|------|
| All 5 sports reported | Required |
| Total events across sports > 250 | Required |
| No sport in FAIL state | Advisory — if FAIL, dispatch that agent in healing mode |

If any sport reports FAIL → dispatch that sport's agent in **healing mode** (existing Step 3).
If all PASS/MARGINAL → proceed to enrichment.
```

**PHASE 3** — Remove entirely (enrichment validation belongs to the enrichment step, not scanner).

### What to MOVE to per-sport agents

| Knowledge | From orchestrator | To agent |
|-----------|-------------------|----------|
| Football needs 28+ stat keys, corners/fouls/shots | KNOWLEDGE BASE | bet-scanner-football Step 2 |
| Tennis has 3/7 stat keys, no H2H | KNOWLEDGE BASE | bet-scanner-tennis Step 2 |
| Basketball needs rebounds/assists | KNOWLEDGE BASE | bet-scanner-basketball Step 2 |
| Volleyball has zero cache files | KNOWN PIPELINE GAPS #2 | bet-scanner-volleyball Step 2 |
| Volleyball API quota issue | KNOWN PIPELINE GAPS #7 | bet-scanner-volleyball Step 3 |
| Tennis 3/7 stat keys | KNOWN PIPELINE GAPS #3 | bet-scanner-tennis Step 2 |
| Injuries never populated | KNOWN PIPELINE GAPS #1 | Remove (not scan-phase concern) |
| Coach data never populated | KNOWN PIPELINE GAPS #4 | Remove (not scan-phase concern) |
| Forebet/Scores24 data lost | KNOWN PIPELINE GAPS #5 | Remove (not scan-phase concern) |
| Odds coverage ~5.6% | KNOWN PIPELINE GAPS #6 | Remove (STATS-FIRST handles this) |
| 13/18 adapters shallow | KNOWN PIPELINE GAPS #8 | Remove (info only) |

### Definition of done

- [ ] KNOWLEDGE BASE section removed entirely
- [ ] KNOWN PIPELINE GAPS table removed entirely
- [ ] Duplicated OPERATIONAL WORKFLOW (2nd copy with inline Python validation) removed
- [ ] PHASE 2 replaced with thin dispatch-aggregate pattern (≤25 lines)
- [ ] PHASE 3 removed (not scanner's job)
- [ ] File is ~60% shorter than current version
- [ ] Remaining content: frontmatter + mandate + rules + philosophy + PHASE 1 + PHASE 2 (thin) + skills + DB access + R17/R19 table + banned patterns

---

## Phase B: Enhance Per-Sport Agents [MODIFY × 5]

All 5 agents receive the same structural change. Sport-specific differences are noted per task.

### Shared Change: Enhanced Step 2 (Verification Query Block)

**Location:** Replace current Step 2 content with an enhanced version.

**Structure:**
1. Existing basic checks (event count, league diversity) — keep
2. NEW: 6 verification checks via inline Python — add
3. NEW: Interpretation guidance for the agent — add

**The unified verification query block** (shared across all 5, with `{SPORT}` placeholder):

```bash
python3 scripts/verify_scan.py --sport {SPORT} --date {YYYY-MM-DD}
```

This script performs all 6 verification checks (event count, phantom detection, duplicate event_keys, data completeness, league coverage vs yesterday, cross-source coverage, source health) and sport-specific stat key checks. It outputs a PASS/MARGINAL/FAIL verdict.

### Sport-Specific Check Blocks (replace `{SPORT_SPECIFIC_CHECK}`)

**Football:**
```python
    # Football: check for corners/fouls/shots in raw_data (sample 20)
    c = conn.execute('SELECT raw_data FROM scan_results WHERE sport=? AND betting_date=? AND raw_data IS NOT NULL LIMIT 20', (sport, today))
    stat_keys_found = set()
    for row in c:
        data = json.loads(row[0]) if row[0] else {}
        stat_keys_found.update(data.get('stat_keys', []))
    required = {'corners', 'fouls', 'yellow_cards', 'shots', 'shots_on_target'}
    found = required & stat_keys_found
    print(f'Stat keys: {len(found)}/{len(required)} required ({found or "NONE"})')
```

**Basketball:**
```python
    # Basketball: check for points/rebounds/assists keys
    c = conn.execute('SELECT raw_data FROM scan_results WHERE sport=? AND betting_date=? AND raw_data IS NOT NULL LIMIT 20', (sport, today))
    stat_keys_found = set()
    for row in c:
        data = json.loads(row[0]) if row[0] else {}
        stat_keys_found.update(data.get('stat_keys', []))
    required = {'rebounds', 'assists', 'steals', 'fg_pct'}
    found = required & stat_keys_found
    print(f'Stat keys: {len(found)}/{len(required)} required ({found or "NONE"})')
```

**Tennis:**
```python
    # Tennis: surface detection (must-have for analysis)
    c = conn.execute('SELECT raw_data FROM scan_results WHERE sport=? AND betting_date=? AND raw_data IS NOT NULL LIMIT 30', (sport, today))
    surfaces = set()
    for row in c:
        data = json.loads(row[0]) if row[0] else {}
        if data.get('surface'): surfaces.add(data['surface'])
    print(f'Surfaces detected: {surfaces or "NONE — TennisExplorer may have failed"}')
    # Known gap: only 3/7 stat keys from ESPN (sets_won, games_won, total_sets)
    print('Note: aces/DFs/1st-serve% expected MISSING (known ESPN gap)')
```

**Volleyball:**
```python
    # Volleyball: known zero-enrichment sport — just flag it
    print('Note: volleyball stats cache likely EMPTY (known API quota gap)')
    print('  → Enrichment should run volleyball FIRST to get quota allocation')
```

**Hockey:**
```python
    # Hockey: check for shots/hits/powerplay keys
    c = conn.execute('SELECT raw_data FROM scan_results WHERE sport=? AND betting_date=? AND raw_data IS NOT NULL LIMIT 20', (sport, today))
    stat_keys_found = set()
    for row in c:
        data = json.loads(row[0]) if row[0] else {}
        stat_keys_found.update(data.get('stat_keys', []))
    required = {'shots', 'hits', 'pim', 'powerplay_goals'}
    found = required & stat_keys_found
    print(f'Stat keys: {len(found)}/{len(required)} required ({found or "NONE"})')
```

### Shared Change: Interpretation Guidance

After the query block, add agent interpretation guidance (~5 lines per agent):

```markdown
**Interpret with `sequentialthinking`:**
- Phantoms > 5 → Are these yesterday's unsettled events leaking in? Check kickoff dates.
- Missing leagues vs yesterday → Source failure or genuinely no matches scheduled? Check degraded sources.
- Completeness < 80% → Which source is producing incomplete records? Cross-ref with source health.
- If FAIL → proceed to Step 3 (self-heal). If PASS/MARGINAL → proceed to Step 4 (report).
```

### Shared Change: Add Verification Mode to Step 0

Add a third path in Step 0:

```markdown
**THREE INVOCATION MODES:**
1. **Fresh scan** — No context. Run full workflow: Step 1 → 2 → 2.5 → 3 (if needed) → 4.
2. **Healing mode** — Invoked with health context (status, diagnosis). Skip to Step 3.
3. **Verification mode** — Invoked after parallel scan with "verify your results". Skip to Step 2.
```

Update Step 0 detection:

```markdown
### Step 0: Check Invocation Context

- If you received **health context** (status, events_found, diagnosis) → **healing mode** → Step 3
- If you received **"verify your results"** → **verification mode** → Step 2
- Otherwise → **fresh scan** → Step 1
```

### Validation Criteria Update

Each agent's existing Validation Criteria section stays unchanged — the thresholds are already defined there and the enhanced Step 2 references them via `{MIN_EVENTS}` / `{MIN_EVENTS_MARGINAL}`.

---

### Task B.1: Modify `bet-scanner-football.agent.md`

**Changes:**
1. **Step 0** — "TWO INVOCATION MODES" → "THREE INVOCATION MODES" with verification mode
2. **Step 2** — Replace current ~25-line basic validation with enhanced verification block using `sport='football'`, `MIN_EVENTS=200`, `MIN_EVENTS_MARGINAL=100`, football stat key check
3. **After Step 2** — Add 5-line football interpretation guidance:
   - Stat keys at scan phase may be sparse — enrichment adds them. Only flag if zero.
   - League coverage is critical — football has 30+ leagues daily. Missing > 5 leagues = investigate.
   - §SCAN.7: Check for Champions League, Europa League if active (season Sep-May).
   - §SCAN.9: Check for Brasileirão, MLS, Liga MX if active.

**Definition of done:**
- [ ] Step 0 has THREE INVOCATION MODES with verification mode described
- [ ] Step 2 has all 6 verification checks inline
- [ ] Football-specific stat key check: corners, fouls, yellow_cards, shots, shots_on_target
- [ ] Interpretation guidance references §SCAN.7 and §SCAN.9
- [ ] File growth ≤ 30 lines

---

### Task B.2: Modify `bet-scanner-basketball.agent.md`

**Changes:**
1. **Step 0** — Add verification mode
2. **Step 2** — Enhanced block with `sport='basketball'`, `MIN_EVENTS=20`, `MIN_EVENTS_MARGINAL=10`, basketball stat key check
3. **After Step 2** — Basketball interpretation guidance:
   - NBA has natural off-days (some Mon/Thu). Low event count on those days is normal.
   - EU leagues have weekday-specific schedules (Euroleague Tue/Thu).
   - Jul-Sep: NBA off-season — low/zero events is seasonal, not a failure.

**Definition of done:**
- [ ] Step 0 has THREE INVOCATION MODES
- [ ] Step 2 has all 6 verification checks
- [ ] Basketball stat key check: rebounds, assists, steals, fg_pct
- [ ] Seasonal awareness in interpretation (NBA off-season Jul-Sep)
- [ ] File growth ≤ 30 lines

---

### Task B.3: Modify `bet-scanner-tennis.agent.md`

**Changes:**
1. **Step 0** — Add verification mode
2. **Step 2** — Enhanced block with `sport='tennis'`, `MIN_EVENTS=30`, `MIN_EVENTS_MARGINAL=15`, tennis surface check
3. **After Step 2** — Tennis interpretation guidance:
   - Dramatic day-to-day variation: Grand Slam week = 200+ matches, transition week = 30.
   - Surface detection is critical for analysis — if zero surfaces, TennisExplorer likely failed.
   - Known gap: only 3/7 stat keys from ESPN. Aces/DFs missing is EXPECTED, not a failure.
   - H2H always empty from ESPN — Scores24 provides some tennis H2H.

**Definition of done:**
- [ ] Step 0 has THREE INVOCATION MODES
- [ ] Step 2 has all 6 verification checks
- [ ] Tennis-specific: surface detection check instead of stat keys
- [ ] Known gaps acknowledged in interpretation (3/7 keys, empty H2H)
- [ ] File growth ≤ 30 lines

---

### Task B.4: Modify `bet-scanner-volleyball.agent.md`

**Changes:**
1. **Step 0** — Add verification mode
2. **Step 2** — Enhanced block with `sport='volleyball'`, `MIN_EVENTS=15`, `MIN_EVENTS_MARGINAL=5`, volleyball gap acknowledgment
3. **After Step 2** — Volleyball interpretation guidance:
   - EU volleyball season: Oct-May. Jun-Aug off-season — low/zero events is normal.
   - Stats cache EMPTY is a KNOWN gap (API quota issue) — flag but don't fail.
   - Fewer sources → completeness may be lower than football. <70% completeness is concerning.

**Definition of done:**
- [ ] Step 0 has THREE INVOCATION MODES
- [ ] Step 2 has all 6 verification checks
- [ ] Volleyball-specific: acknowledges zero-enrichment gap
- [ ] Seasonal awareness (EU off-season Jun-Aug)
- [ ] File growth ≤ 30 lines

---

### Task B.5: Modify `bet-scanner-hockey.agent.md`

**Changes:**
1. **Step 0** — Add verification mode
2. **Step 2** — Enhanced block with `sport='hockey'`, `MIN_EVENTS=10`, `MIN_EVENTS_MARGINAL=5`, hockey stat key check
3. **After Step 2** — Hockey interpretation guidance:
   - NHL regular season Oct-Apr, playoffs Apr-Jun. Jul-Sep off-season.
   - KHL runs Sep-Apr. SHL/Liiga Oct-Mar.
   - NHL has off-days — 5-9 events is normal, not a failure.
   - Stat keys (shots, hits, PIM, powerplay) come from ESPN enrichment — may be sparse at scan phase.

**Definition of done:**
- [ ] Step 0 has THREE INVOCATION MODES
- [ ] Step 2 has all 6 verification checks
- [ ] Hockey stat key check: shots, hits, pim, powerplay_goals
- [ ] Seasonal awareness (NHL Jul-Sep off-season, KHL Sep-Apr)
- [ ] File growth ≤ 30 lines

---

## Phase C: Update Scan Prompt [MODIFY bet-scan.prompt.md]

### Task C.1: Update workflow description

**Location:** "Workflow: DISCOVER → VALIDATE → ENRICH → VALIDATE → BUILD → VALIDATE" section.

**Change:** In PHASE 1, after the scan command, replace the current "VALIDATE Phase 1" inline Python checks with:

```markdown
**VALIDATE Phase 1** — Dispatch per-sport agents in verification mode:
> Parallel scan completed. Verify your sport's scan results — run your enhanced Step 2.
> Date: {date}. Report: event count, data quality, league coverage, issues found.

Each per-sport agent runs 6 verification checks (phantoms, duplicates, completeness, league coverage, cross-source, source health + sport-specific) and reports verdict.

Aggregate: all 5 sports reported? Total events > 250? Any FAIL → dispatch healing.
```

**Definition of done:**
- [ ] VALIDATE Phase 1 references per-sport agent dispatch instead of inline Python
- [ ] Text is ≤10 lines
- [ ] No new inline Python validation code in the prompt

---

## Task Dependency & Ordering

```
Phase A (slim orchestrator)  ──┐
                               ├──► Phase C (update prompt) ──► DONE
Phase B (enhance 5 agents)  ──┘
```

- Phase A and Phase B are **independent** — can be done in parallel
- Phase C depends on both A and B being conceptually finalized (but is a minor text change)

## Implementation Checklist

- [ ] Phase A: Slim `bet-scanner.agent.md` (remove ~150 lines, replace PHASE 2)
- [ ] Phase B.1: Enhance `bet-scanner-football.agent.md` Step 2
- [ ] Phase B.2: Enhance `bet-scanner-basketball.agent.md` Step 2
- [ ] Phase B.3: Enhance `bet-scanner-tennis.agent.md` Step 2
- [ ] Phase B.4: Enhance `bet-scanner-volleyball.agent.md` Step 2
- [ ] Phase B.5: Enhance `bet-scanner-hockey.agent.md` Step 2
- [ ] Phase C: Update `bet-scan.prompt.md`
- [ ] Final review: each per-sport agent file grew ≤30 lines, orchestrator shrank ≥100 lines
