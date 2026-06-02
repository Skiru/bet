# STATE OF ART — Definitively Plan (Review v3 — DeepSeek V4 PRO Validated)

**Target:** Qwen3.6-35B-A3B MoE 4-bit (131K context, Rapid-MLX localhost:8000)
**Hardware:** Apple M4 Pro 48GB  
**Goal:** 100% Kilo Code. Zero Copilot/Roo/Continue.

---

## ⚠️ HAZARD MARKERS (read before ANY rm command)

| ⚠️ | Marker | Znaczenie |
|-----|--------|-----------|
| 🔴 | `DESTRUCTIVE` | Nieodwracalna operacja — upewnij się że backup istnieje |
| 🟡 | `CRITICAL ORDER` | Kolejność ma znaczenie — nie zmieniaj |
| 🟢 | `SAFE` | Bezpieczne, można powtórzyć |

---

## 🔴 ALL BUGS (27 total — 17 from reviews #1+2 + 10 from review #3)

### BUGS from reviews #1-2 (already fixed in plan)
B1-B17 — see previous versions. All incorporated below.

### BUGS found in review #3 (THIS review — DeepSeek):

| # | Bug | Evidence | Severity | Fix |
|---|-----|----------|----------|-----|
| **C1** | **Phase B ładuje .kilo/shared/execution-core.md i .kilo/docs/execution-protocol.md ZANIM one istnieją (tworzone w Phase C)** | Plan: B1d → C1, C3 | 🔴 CRITICAL | Przenieś tworzenie tych plików do Phase A (A7, A8) |
| **C2** | **37 komend `PYTHONPATH=src cmd` w execution-spine — bash syntax, fish NIE wspiera** | execution-spine.md:37 matches | 🔴 CRITICAL | Każdą komendę zmień na `env PYTHONPATH=src cmd` |
| **C3** | **37 `{date}` / `{prev_date}` zmiennych bez definicji** | execution-spine.md:37 matches | 🔴 CRITICAL | Dodaj nagłówek definiujący zmienne w runbooku |
| **C4** | **`new_task` (Roo API) na linii 347 — Kilo używa `task`** | execution-spine.md line 347 | 🔴 CRITICAL | Zmień `new_task` → `task` |
| **C5** | **Anti-drift ma 3 referencje sequentialthinking (nie 2)** | Lines 7, 25, 32 | 🟡 HIGH | Fix ALL 3, nie tylko 7 i 13 |
| **C6** | **Orchestrator prompt (linia 10) BANIUJE sequentialthinking — ale plan ENABLUJE MCP** | .kilo/prompts/bet-orchestrator.md line 10 | 🟡 HIGH | Spójna polityka: ENABLE sequentialthinking, ALLOW guided usage |
| **C7** | **`python3 -c` na linii 92 execution-spine — FORBIDDEN by terminal rules** | execution-spine.md line 92 | 🟡 HIGH | Replace with `sqlite_read_query` call |
| **C8** | **Brak systemu checkpoint/milestone do trackowania implementacji** | User request | 🟡 HIGH | Dodaj CHECKPOINT po każdej fazie |
| **C9** | **T6 mierzy GLOBAL token budget, nie per-agent** | Plan T6 | 🟢 MEDIUM | Dodaj per-agent breakdown |
| **C10** | **Brak pre-flight weryfikacji czy wszystkie skrypty z runbook istnieją** | execution-spine: ~30 unikalnych skryptów | 🟢 MEDIUM | Dodaj Phase 0.5: pre-flight script check |

---

## 📍 CHECKPOINT SYSTEM

Po każdej fazie, zapisz 1-liniowy checkpoint. Jeśli implementacja zostanie przerwana, możesz wznowić od ostatniego CHECKPOINT.

```
CHECKPOINT po Phase 0: BACKUP_COMPLETE=[timestamp] BACKUP_PATH=[git hash or /tmp/bet-backup-*]
CHECKPOINT po Phase A: FILES_MIGRATED=ok A6_INTEGRITY=ok SYNTACTIC_FIXES=ok
CHECKPOINT po Phase B: KILOJSONC_UPDATED=ok MCP_CONSOLIDATED=ok SERVER_SCRIPT=ok GLOBAL_CONFIG=ok
CHECKPOINT po Phase C: PROMPTS_TRIMMED=ok TOKEN_BUDGET=ok
CHECKPOINT po Phase D: DELETIONS_VERIFIED=ok NO_REMNANTS=ok
CHECKPOINT po Phase E: CONSISTENCY_FIXED=ok
CHECKPOINT po Phase F: TESTS_PASSED=[T1-T8 results]
CHECKPOINT po Phase G: MONITORING_STARTED=[date]
```

---

## 🎯 MILESTONES

| Milestone | Po fazie | Co osiągnięto |
|-----------|----------|---------------|
| **M1: SAFE** | Phase 0 | Backup istnieje — można cofnąć WSZYSTKIE zmiany |
| **M2: READY** | Phase A | Wszystkie pliki skopiowane, ścieżki poprawne, składnia fish |
| **M3: CONFIGURED** | Phase B | kilo.jsonc zoptymalizowany, MCP skonsolidowane |
| **M4: LEAN** | Phase C | Prompty przycięte o 50%, token budget < 10K |
| **M5: CLEAN** | Phase D | TYLKO Kilo Code — zero Copilot/Roo/Continue |
| **M6: CONSISTENT** | Phase E | Wszystkie instruction files spójne, bez kontradykcji |
| **M7: VERIFIED** | Phase F | 8 testów PASS — system działa |
| **M8: STABLE** | Phase G | 2-3 pipeline runs bez capacity errors |

---

## PHASE 0 — BACKUP

**🔴 DESTRUCTIVE PREPARATION — MUSI być pierwszy**

```fish
cd /Users/mkoziol/projects/bet

# Git backup
git add .github/ .roo/ .roomodes .clinerules .vscode/ .continuerc.json .kilocode/mcp.json
git commit -m "BACKUP: pre-cleanup snapshot — all Copilot+Roo+Continue configs"

# Filesystem backup (extra safety)
mkdir -p /tmp/bet-backup-2026-06-02
cp -r .github/ .roo/ .roomodes .clinerules .vscode/ .continuerc.json /tmp/bet-backup-2026-06-02/

echo "Git:"; git log --oneline -1
echo "FS:"; ls /tmp/bet-backup-2026-06-02/
```

**✅ CHECKPOINT Phase 0:** BACKUP_COMPLETE = `date`, BACKUP_PATH = git + /tmp/bet-backup-2026-06-02/

---

## 🔵 PHASE 0.5 — PRE-FLIGHT: Script Existence Check

**🟢 SAFE — read-only**

```fish
cd /Users/mkoziol/projects/bet
set SCRIPTS settle_on_finish analyze_betclic_learning evaluate_decisions data_rotation \
    build_league_profiles discover_events ingest_scan_stats seed_espn_data \
    fetch_odds_api fetch_odds_api_io fetch_esports_odds fetch_weather tipster_aggregator \
    build_shortlist tipster_xref run_scrapers data_enrichment_agent \
    fetch_tennis_elo enrich_tennis_flashscore tennis_h2h_warmup \
    enrich_volleyball_stats enrich_hockey_stats enrich_basketball_stats \
    deep_stats_report odds_evaluator context_checks upset_risk gate_checker \
    validate_phase validate_betclic_markets check_48h_repeats coupon_builder validate_coupons generate_coupon_pdf

echo "=== Script existence check ==="
for s in $SCRIPTS
    if test -f "scripts/$s.py"
        echo "✅ scripts/$s.py"
    else
        echo "❌ MISSING: scripts/$s.py"
    end
end

# Also verify venv
test -f ".venv/bin/python3"; and echo "✅ .venv/bin/python3"; or echo "❌ MISSING: .venv/bin/python3"
```

**Jeśli jakikolwiek MISSING — NIE kontynuuj.** Najpierw napraw skrypty.

---

## PHASE A — MIGRATE + CREATE NEW FILES (pre-deletion)

**🟡 CRITICAL ORDER — wszystkie pliki referencjonowane w Phase B MUSZĄ istnieć po tej fazie**

### A1: 8 .roo/rules-bet-* files → .kilo/docs/agent-rules/

```fish
mkdir -p .kilo/docs/agent-rules/{bet-scanner,bet-enricher,bet-builder,bet-challenger,bet-statistician}

cp .roo/rules-bet-scanner/source-navigation.md    .kilo/docs/agent-rules/bet-scanner/
cp .roo/rules-bet-enricher/source-navigation.md   .kilo/docs/agent-rules/bet-enricher/
cp .roo/rules-bet-builder/mistakes-rules.md        .kilo/docs/agent-rules/bet-builder/
cp .roo/rules-bet-builder/artifacts-format.md      .kilo/docs/agent-rules/bet-builder/
cp .roo/rules-bet-challenger/mistakes-rules.md     .kilo/docs/agent-rules/bet-challenger/
cp .roo/rules-bet-challenger/sport-protocols.md    .kilo/docs/agent-rules/bet-challenger/
cp .roo/rules-bet-statistician/market-tables.md    .kilo/docs/agent-rules/bet-statistician/
cp .roo/rules-bet-statistician/sport-protocols.md  .kilo/docs/agent-rules/bet-statistician/
```

### A2: 4 compact rules → .kilo/docs/

```fish
cp .roo/rules/analysis-methodology-compact.md .kilo/docs/analysis-methodology.md
cp .roo/rules/sport-protocols-compact.md      .kilo/docs/sport-protocols.md
cp .roo/rules/mistakes-rules-compact.md       .kilo/docs/mistakes-rules.md
cp .roo/rules/artifacts-format-compact.md     .kilo/docs/artifacts-format.md
```

### A3: Orchestrator-runbook + routing (copy first, THEN apply ALL fixes)

```fish
# Copy first (keep .roo/ original intact)
cp .roo/rules-bet-orchestrator/execution-spine.md .kilo/docs/orchestrator-runbook.md
cp .roo/rules-bet-orchestrator/routing.md .kilo/docs/orchestrator-routing.md
```

**NOW apply ALL fixes to `.kilo/docs/orchestrator-runbook.md`:**

| # | Fix | oldString → newString |
|---|-----|------------------------|
| F1 | Add date variables header after `## HOW TO READ THIS FILE` | Insert: `## DATE VARIABLES\n- \`{date}\` = today (YYYY-MM-DD, Europe/Warsaw)\n- \`{prev_date}\` = previous betting day\nAlways run \`date +%Y-%m-%d\` to verify before execution.` |
| F2 | Fix ALL 37 `PYTHONPATH=src .venv/bin/python3` → fish | `PYTHONPATH=src .venv/bin/python3` → `env PYTHONPATH=src .venv/bin/python3` (global replaceAll) |
| F3 | Fix `python3 -c` on verify step | Replace the entire `python3 -c "..."` block with: `sqlite_read_query("SELECT COUNT(*) FROM tipster_picks WHERE betting_date='{date}'")` |
| F4 | Fix `new_task` → `task` (line 347) | `\`new_task\` to specialist` → `\`task\` to specialist` |
| F5 | Add delegation syntax note after `## DELEGATION PROTOCOL` | Insert: `Delegation syntax: \`task(description="S0 settlement", prompt="...", subagent_type="bet-settler")\`` |

### A4: Memory → .kilocode/memory/

```fish
cp .roo/memory-bank/project-structure.md  .kilocode/memory/project-structure.md
cp .roo/memory-bank/pipeline-knowledge.md .kilocode/memory/pipeline-knowledge.md
cp .roo/memory-bank/workflow.md          .kilocode/memory/workflow.md

# Merge betting-preferences (read both, combine into .kilocode/memory/betting-preferences.md):
# - .roo version has philosophy + practical notes
# - .kilocode version has concrete numbers (5% bankroll, Kelly 1/4)
# → Merge into one file with philosophy + practical + numbers sections
```

**🔴 NIE kopiuj:** `coupon-risk-lessons.md` — .kilocode ma pełniejszą wersję.

### A5: Dedup check

`.kilo/docs/builder-validation-reference.md` ↔ `.kilo/docs/agent-rules/bet-builder/mistakes-rules.md`
→ Komplementarne (builder = queries + portfolio, rules = sport-specific hard reject). **Keep both.**

`.kilo/docs/challenger-gates-reference.md` ↔ `.kilo/docs/agent-rules/bet-challenger/mistakes-rules.md`
→ Komplementarne (gates = 20-point + bear cases, rules = hard reject). **Keep both.**

**→ Brak duplikacji wymagającej merge.**

### A6: Reference integrity check

```fish
set FAIL 0
for ref in (grep -oP '"([^"]+\.(md|json|jsonc))"' kilo.jsonc | string trim -c '"')
    if test -f "$ref"
        echo "✅ $ref"
    else
        echo "❌ MISSING: $ref"
        set FAIL (math $FAIL + 1)
    end
end
echo "Missing: $FAIL"
test $FAIL -eq 0; or echo "❌ NAPRAW zanim przejdziesz do Phase B"
```

### A7: 🆕 Create `.kilo/shared/execution-core.md` (~30 lines)

**🟡 CRITICAL: MUSI istnieć przed Phase B**

```markdown
# Execution Core — Subagent Protocol

## Pattern: THINK → ACT(1) → REASON → ACT(1) → SYNTHESIZE
- Use native `<think>` tags by default for routine deliberation.
- For complex multi-step branching (market ranking, gate decisions, bear cases) — `sequentialthinking` MCP IS available.
- 1 tool call per `<think>` block max.
- After each call: `<think>` what you LEARNED before next.
- **Budget: 5 tool calls max total** — synthesize after.

## ❌ No data dumps
- Never fire >2 tools without `<think>` between.
- "Get all data first" = drift.
- Every stat needs a query behind it this session.
- Can't say WHY you need next query → STOP, synthesize.
- Output: verdict with ≥3 numbers from actual queries.

## Behavioral guardrails
- Find MECHANISMS: "Safety=0.72" is data. "L5 fouls drop 30% in dead rubbers" is insight.
- Source fusion: ≥2 of {DB stats, web context, tipster} per STRONG verdict.
- Cite-or-Delete: every number without a DB/file query = hallucination.
```

### A8: 🆕 Create `.kilo/docs/execution-protocol.md` (~40 lines)

**🟡 CRITICAL: MUSI istnieć przed Phase B**  
**Zastępuje agent-execution-protocol.instructions.md (148 linii).**

```markdown
# Agent Execution Protocol

## Universal Rules (ALL agents)
- Fish shell ONLY. `.venv/bin/python3` always.
- ALL scripts → `> /tmp/sN.txt 2>&1` then `tail -20`
- NEVER output raw terminal. Synthesize: "✅ S1 — 547 events, 5 sports"

## Turn Structure
1. `<think>` → "What do I need? Which 1 query?"
2. 1 data tool call (sqlite / bash / brave)
3. `<think>` → "What did I learn?"
4. 0-1 more tool calls max
5. NARRATE findings (not data dump) + verdict

## Verdict Template
```
verdict: APPROVED | FLAGGED | REJECTED
metrics: [≥3 numbers from actual queries]
analysis: [2-3 sentences — what numbers MEAN]
```

## Forbidden
- `python3 -c "..."`, `--help`, bare `python3` (no venv)
- List all items → AGGREGATE: "147 events in 5 sports"
- Continue past `S2=0 matched tips` without user confirmation
- Skip delegation after running a script
```

### A9: 🆕 Add hallucination prevention to `.kilo/docs/analysis-methodology.md`

After the file header, insert:

```markdown
## Hallucination Prevention (ALL agents — mandatory)
| Sport | Risk | ONLY analyze |
|-------|------|-------------|
| Tennis | HIGH | Markets with real L10 games data per player |
| Volleyball | HIGH | Total Points O/U + Sets O/U |
| Basketball | HIGH | Total Points O/U + Handicap |
| Hockey | HIGH | Total Goals O/U + Total Shots O/U |
| Esports | HIGH | Match Winner (unless map_win_rate exists) |

## Data Depth Minimums
| Dimension | Minimum | Below = Flag |
|-----------|---------|-------------|
| L10 | ≥8 data points | PARTIAL quality |
| H2H | ≥3 meetings | H2H-BLIND (×0.7 safety penalty) |
| L5 | ≥4 data points | PARTIAL quality |
```

**✅ CHECKPOINT Phase A:** FILES_MIGRATED=ok A6_INTEGRITY=[pass/fail] SYNTACTIC_FIXES=ok  

**🟡 Jeśli A6_INTEGRITY=fail → NAPRAW zanim przejdziesz do Phase B.**

---

## PHASE B — CONFIGURE KILO

**🟡 CRITICAL ORDER — kilo.jsonc references files created w Phase A**

### B1: kilo.jsonc — wszystkie 12 fixów

| # | Lokalizacja | Pole | Obecnie | Po zmianie |
|---|-------------|------|---------|------------|
| 1 | global | `default_agent` | [nie istnieje] | `"bet-orchestrator"` |
| 2 | L59-61 | global `instructions` | `[".github/instructions/agent-execution-protocol.instructions.md"]` | `[]` (puste — protokół per-agent) |
| 3 | L134-138 | model output `limit` | `8192` | `16384` |
| 4 | L415-417 | compaction `reserved` | `14000` | `18432` |
| 5 | L422 | `experimental.mcp_timeout` | `30000` | `60000` |
| 6 | L364 | MCP sequentialthinking `enabled` | `false` | `true` |
| 7 | L366 | MCP sequentialthinking `timeout` | `120000` | `300000` |
| 8 | MCP brave-search | `timeout` | `25000` | `45000` |
| 9 | tool_output | `max_lines` | `100` | `200` |
| 10 | tool_output | `max_bytes` | `16384` | `32768` |
| 11 | model key | name | `"qwen3.6-35b-a3b"` | `"qwen3.6-35b"` |
| 12 | L427 | default model | `"openai-compatible/qwen3.6-35b-a3b"` | `"openai-compatible/qwen3.6-35b"` |

### B1b: Steps per agent

| Agent | Current | New |
|-------|---------|-----|
| bet-orchestrator | 80 | **50** |
| bet-engineer | 50 | **30** |
| bet-statistician | 8 | **8** (keep) |
| bet-challenger | 8 | **8** (keep) |
| bet-builder | 8 | **8** (keep) |
| bet-scanner | 8 | **6** |
| bet-scout | 8 | **6** |
| bet-enricher | 8 | **6** |
| bet-valuator | 8 | **6** |
| bet-settler | 8 | **6** |
| bet-db-analyst | 8 | **6** |

### B1c: Browser permissions

| Agent | browser |
|-------|---------|
| orchestrator, scanner, scout, enricher, engineer | `allow` |
| statistician, challenger, builder, valuator, settler, db-analyst | `deny` |

### B1d: Instructions per agent (LOAD ORDER: core → protocol → domain — PROVEN mechanism)

**Uwaga:** engine NIE ładuje execution-core — to coding agent, nie analityczny.

| Agent | `"instructions"` array |
|-------|------------------------|
| **bet-orchestrator** | `[".kilo/shared/execution-core.md", ".kilo/docs/execution-protocol.md", ".kilo/docs/orchestrator-runbook.md", ".kilo/docs/orchestrator-routing.md"]` |
| **bet-scanner** | `[".kilo/shared/execution-core.md", ".kilo/docs/execution-protocol.md", ".kilo/docs/analysis-methodology.md", ".kilo/docs/agent-rules/bet-scanner/source-navigation.md"]` |
| **bet-scout** | `[".kilo/shared/execution-core.md", ".kilo/docs/execution-protocol.md", ".kilo/docs/analysis-methodology.md"]` |
| **bet-enricher** | `[".kilo/shared/execution-core.md", ".kilo/docs/execution-protocol.md", ".kilo/docs/analysis-methodology.md", ".kilo/docs/agent-rules/bet-enricher/source-navigation.md"]` |
| **bet-statistician** | `[".kilo/shared/execution-core.md", ".kilo/docs/execution-protocol.md", ".kilo/docs/analysis-methodology.md", ".kilo/docs/mistakes-rules.md", ".kilo/docs/agent-rules/bet-statistician/market-tables.md", ".kilo/docs/agent-rules/bet-statistician/sport-protocols.md"]` |
| **bet-valuator** | `[".kilo/shared/execution-core.md", ".kilo/docs/execution-protocol.md", ".kilo/docs/analysis-methodology.md", ".kilo/docs/mistakes-rules.md"]` |
| **bet-challenger** | `[".kilo/shared/execution-core.md", ".kilo/docs/execution-protocol.md", ".kilo/docs/analysis-methodology.md", ".kilo/docs/sport-protocols.md", ".kilo/docs/mistakes-rules.md", ".kilo/docs/agent-rules/bet-challenger/mistakes-rules.md", ".kilo/docs/agent-rules/bet-challenger/sport-protocols.md"]` |
| **bet-builder** | `[".kilo/shared/execution-core.md", ".kilo/docs/execution-protocol.md", ".kilo/docs/analysis-methodology.md", ".kilo/docs/mistakes-rules.md", ".kilo/docs/artifacts-format.md", ".kilo/docs/agent-rules/bet-builder/mistakes-rules.md", ".kilo/docs/agent-rules/bet-builder/artifacts-format.md"]` |
| **bet-settler** | `[".kilo/shared/execution-core.md", ".kilo/docs/execution-protocol.md"]` |
| **bet-db-analyst** | `[".kilo/shared/execution-core.md", ".kilo/docs/execution-protocol.md"]` |
| **bet-engineer** | `[".kilo/docs/execution-protocol.md", ".kilocode/rules/terminal-environment.md", ".kilocode/rules/tool-names.md"]` |

### B2: scripts/start_local_model.sh

```fish
# Zmień max-tokens
--max-tokens 32768  →  --max-tokens 16384

# Opcjonalnie (jeśli rapid-mlx wspiera):
--max-thought-tokens 8192
```

### B3: ~/.config/kilo/kilo.jsonc

```jsonc
"model": "openai-compatible/qwen3.6-27b"  →  "openai-compatible/qwen3.6-35b"
```

### B4: Remove .kilocode/mcp.json (MCP dup)

```fish
# Verify kilo.jsonc ma wszystkie MCP
grep -A5 'sequentialthinking' kilo.jsonc | grep -q '"enabled": true'; or echo "❌ sequentialthinking nie enabled!"
grep -q 'brave-search' kilo.jsonc; or echo "❌ brak brave-search!"
grep -q 'sqlite' kilo.jsonc; or echo "❌ brak sqlite!"

# Jeśli wszystkie OK → usuń duplikat
rm .kilocode/mcp.json
```

### B5: Verify no .github/ refs remain in kilo.jsonc

```fish
grep -n '\.github' kilo.jsonc
# → 0 hits required. If any hit → fix before proceeding.
```

**✅ CHECKPOINT Phase B:** KILOJSONC_UPDATED=ok MCP_CONSOLIDATED=ok SERVER_SCRIPT=ok GLOBAL_CONFIG=ok

---

## PHASE C — TRIM PROMPTS (token optimization)

**🟢 SAFE — tylko edycja promptów, nic nie usuwa**

### C1: Trim ALL 11 prompt files

**Wspólne dla wszystkich subagentów — usuń:**
- ❌ Deliberation loop boilerplate (loaded via execution-core.md)
- ❌ Tool name reminders (loaded via .kilocode/rules/tool-names.md)
- ❌ BAD vs GOOD tables (educational, not operational)
- ❌ MCP Tools section
- ❌ Responsibilities section
- ❌ "NO EXTERNAL THINKING TOOLS" block (zastąpione przez execution-core.md)

**Zachowaj w każdym prompcie:**
- 1-2 linie tożsamości: "You are X. You analyze Y → produce Z."
- 3-5 Hard Rules (unikalne dla agenta)
- Verdict template
- Agent-specific decision tables

### C2: Specific trim targets

| Plik | Current | Target | Co zachować |
|------|---------|--------|-------------|
| bet-orchestrator.md | 122 | **75** | Commands table, DELEGATION ROUTING, CIRCUIT BREAKERS, RULES |
| bet-challenger.md | 92 | **50** | Bear case mechanism, 18-point gate, Advisory Tiers, Verdict |
| bet-statistician.md | 100 | **55** | Cite-or-delete, three-way alignment, safety caps, Verdict |
| bet-builder.md | 90 | **50** | Hard Rules (11), Post-Build Validation, Portfolio Structure |
| bet-scanner.md | 73 | **40** | Coverage requirements, Verdict |
| bet-scout.md | 81 | **42** | Argument quality, Verdict |
| bet-enricher.md | 74 | **40** | FULL/PARTIAL/MINIMAL, Circuit breakers, Verdict |
| bet-valuator.md | 86 | **45** | Core formulas (EV, Kelly, drift), Verdict |
| bet-settler.md | 77 | **42** | PnL calculation, Learning Extraction, Verdict |
| bet-db-analyst.md | 74 | **40** | Key tables, freshness thresholds, Verdict |
| bet-engineer.md | 136 | **80** | Tech stack, Environment, Reasoning protocol, Anti-patterns |

### 🆕 C3: Orchestrator prompt — FIX sequentialthinking policy

**Bug C6 fix:** Obecny prompt banuje sequentialthinking (line 10). W execution-core.md sequentialthinking jest ALLOWED dla complex branching.

**Fix w bet-orchestrator.md:** Usuń lines 9-10 (NO EXTERNAL THINKING TOOLS block). W trimmed version, użyj: "Use native `<think>` by default. For complex multi-step decisions (gate analysis, market ranking), `sequentialthinking` MCP is available."

**✅ CHECKPOINT Phase C:** PROMPTS_TRIMMED=ok TOKEN_BUDGET=ok

---

## PHASE D — DELETE ALL NON-KILO

**🔴 DESTRUCTIVE — weryfikuj przed każdym rm**

### D0: Pre-deletion verification

```fish
# Upewnij się że wszystkie pliki referencyjne ISTNIEJĄ:
test -f .kilo/shared/execution-core.md;    and echo "✅"; or echo "❌ MISSING: execution-core.md"
test -f .kilo/docs/execution-protocol.md;  and echo "✅"; or echo "❌ MISSING: execution-protocol.md"
test -f .kilo/docs/orchestrator-runbook.md; and echo "✅"; or echo "❌ MISSING: orchestrator-runbook.md"
test -f .kilo/docs/orchestrator-routing.md; and echo "✅"; or echo "❌ MISSING: orchestrator-routing.md"
test -d .kilo/docs/agent-rules/;           and echo "✅"; or echo "❌ MISSING: agent-rules/"
test -f .kilo/docs/analysis-methodology.md; and echo "✅"; or echo "❌ MISSING: analysis-methodology.md"
test -f .kilo/docs/sport-protocols.md;      and echo "✅"; or echo "❌ MISSING: sport-protocols.md"
test -f .kilo/docs/mistakes-rules.md;       and echo "✅"; or echo "❌ MISSING: mistakes-rules.md"
test -f .kilo/docs/artifacts-format.md;     and echo "✅"; or echo "❌ MISSING: artifacts-format.md"

# Upewnij się że kilo.jsonc NIE ma .github/ references
grep -c '\.github' kilo.jsonc
# → 0 lub zatrzymaj

# Upewnij się że backup istnieje
git log --oneline -1
```

**Jeśli JAKIKOLWIEK ❌ → NIE uruchamiaj rm.**

### D1: Execute deletions

```fish
# Delete Copilot
rm -rf .github/

# Delete Roo/Cline
rm -rf .roo/
rm .roomodes
rm .clinerules

# Delete config conflicts
rm .vscode/mcp.json
rm .continuerc.json

# Delete backup files
rm -rf .kilo/prompts.bak/
find . -name "*.bak" -type f -delete
```

### D2: Verify deletions

```fish
for path in .github/ .roo/ .roomodes .clinerules .vscode/mcp.json .continuerc.json
    if test -e "$path"
        echo "❌ STILL EXISTS: $path"
    else
        echo "✅ Clean: $path"
    end
end

# Verify no Roo/Copilot-specific file patterns remain in root
find . -maxdepth 2 -name "*.agent.md" -o -name "*.prompt.md" -o -name "copilot-instructions.md" 2>/dev/null
```

**✅ CHECKPOINT Phase D:** DELETIONS_VERIFIED=ok NO_REMNANTS=ok

---

## PHASE E — CONSISTENCY

### E1: AGENTS.md — fix ALL contradictions

| Linia | Stare | Nowe |
|-------|-------|------|
| 6 | `Deep reasoning → sequentialthinking_sequentialthinking tool` | `Deep reasoning → native <think> tags (sequentialthinking MCP for complex branching)` |
| 12 | `brief planning <think> → sequentialthinking → data tool` | `brief planning <think> → data tool → reasoning <think>` |
| 24 | `→ STOP → sequentialthinking` | `→ STOP → native <think>` |
| 31 | Model — verify | Keep if Qwen3.6-35B-A3B MoE 4-bit (should be correct) |

### E2: anti-drift-protocol.md — fix ALL 3 sequentialthinking refs

| Linia | Stare | Nowe |
|-------|-------|------|
| 7 | `` `First tool call = sequentialthinking` `` | `` `First tool call = native <think>` `` |
| 25 | `sequentialthinking: "Where am I? What did I just do? What's next?"` | `<think>: "Where am I? What did I just do? What's next?"` |
| 32 | `**3 per turn: 1 sequentialthinking + 2 data tools. Then NARRATE.**` | `**3 per turn: 1 native <think> + 2 data tools. Then NARRATE.**` |

### E3: Verify consistency

```fish
# Zero deprecated references
grep -rn 'runSubagent\|\.github/\|\.roo/\|\.roomodes\|\.clinerules\|new_task' \
    kilo.jsonc .kilo/ .kilocode/ AGENTS.md 2>/dev/null
# → 0 results

# No contradiction: sequentialthinking ban + sequentialthinking enable
echo "=== Checking sequentialthinking consistency ==="
grep 'sequentialthinking.*enabled.*true' kilo.jsonc; and echo "✅ MCP enabled"
grep -c 'sequentialthinking.*FORBIDDEN\|NO EXTERNAL THINKING' .kilo/prompts/*.md
# → 0 hits after trimming
```

**✅ CHECKPOINT Phase E:** CONSISTENCY_FIXED=ok

---

## PHASE F — 🧪 TEST SUITE

### T1: Config Integrity (bash)

```fish
set FAIL 0
for ref in (grep -oP '"([^"]+\.(md|json|jsonc))"' kilo.jsonc | string trim -c '"')
    if test -f "$ref"; echo "✅ $ref"
    else; echo "❌ MISSING: $ref"; set FAIL (math $FAIL + 1); end
end
echo "Missing: $FAIL / Total refs"
test $FAIL -eq 0; and echo "✅ T1 PASS"; or echo "❌ T1 FAIL — $FAIL broken refs"
```

### T2: No Remnants

```fish
set DIRTY 0
for path in .github/ .roo/ .roomodes .clinerules .vscode/mcp.json .continuerc.json
    test -e "$path"; and echo "❌ EXISTS: $path"; set DIRTY (math $DIRTY + 1); or echo "✅ clean: $path"
end
grep -rn "runSubagent" kilo.jsonc .kilo/ .kilocode/ AGENTS.md 2>/dev/null; and set DIRTY (math $DIRTY + 1)
test $DIRTY -eq 0; and echo "✅ T2 PASS"; or echo "❌ T2 FAIL — $DIRTY issues"
```

### T3: MCP Connectivity (manual)

Switch to `bet-db-analyst` → send:
```
Test 3 MCPs:
1. sqlite_list_tables
2. sequentialthinking_sequentialthinking(thought="connection test")
3. brave-search_brave_web_search(query="test", count=1)
Report which responded.
```
**PASS:** All 3 respond. **FAIL:** Check B1 MCP config.

### T4: Agent Delegation (manual)

Switch to `bet-orchestrator` → send:
```
Delegation test: task(description="S1 scan test", prompt="TEST only: verify you received this delegation. Reply: 'Delegation working.'", subagent_type="bet-scanner")
```
**PASS:** bet-scanner responds. **FAIL:** Check task permissions in kilo.jsonc.

### T5: Model Capacity (manual — DO THIS FIRST ON NEW SERVER)

Switch to `bet-orchestrator` → send detailed query with thinking. Watch 3-5 min.
**PASS:** Structured verdict without "capacity limit" error. **FAIL:** See capacity fix section.

**Capacity fix escalation:**
1. `--gc-interval 5` in start_local_model.sh
2. `--max-tokens 12288` 
3. Monitor server logs for memory fragmentation

### 🆕 T6: Per-Agent Token Budget (bash)

```fish
echo "=== Per-Agent Token Budget ==="
echo "Agent | Instructions | Prompt | Total chars | Est tokens"
echo "------|-------------|--------|------------|-----------"

for agent in bet-orchestrator bet-scanner bet-scout bet-enricher bet-statistician \
             bet-valuator bet-challenger bet-builder bet-settler bet-db-analyst bet-engineer
    set TOTAL 0
    # Prompt
    test -f ".kilo/prompts/$agent.md"; and set TOTAL (math "$TOTAL + "(wc -c < ".kilo/prompts/$agent.md" 2>/dev/null | string trim || echo 0))
    
    # Instructions (extract from kilo.jsonc — approximate)
    # This requires semi-manual counting. For automation:
    # grep instruction paths for this agent from kilo.jsonc, sum char counts
    
    echo "$agent | — | — | "(wc -c < ".kilo/prompts/$agent.md" | string trim)" | "(math "round("(wc -c < ".kilo/prompts/$agent.md" | string trim)" / 3.5)")
end

echo "---"
echo "Target: each agent < 3000 chars prompt + instructions for core agents"
```

**Manual extension:** Dla każdego agenta policz:
```
agent_name = load all instruction files + prompt → sum chars → / 3.5 → tokens
docelowo: scanner/scout/enricher/settler/db-analyst < 1500 tokenów
          statistician/challenger/builder < 3000 tokenów
          orchestrator < 5000 tokenów
          engineer < 2000 tokenów
```

### T7: Agent Prompt Verification (bash)

```fish
for agent in bet-orchestrator bet-scanner bet-scout bet-enricher bet-statistician \
             bet-valuator bet-challenger bet-builder bet-settler bet-db-analyst bet-engineer
    if test -f ".kilo/prompts/$agent.md"
        set CHARS (wc -c < ".kilo/prompts/$agent.md" | string trim)
        echo "✅ $agent.md — $CHARS chars"
    else
        echo "❌ $agent.md — MISSING!"
    end
end
```

### T8: Pipeline Dry Run (manual — orchestrator)

Switch to `bet-orchestrator` → send:
```
Pipeline dry run: (1) Current date? (2) First command for S0? (3) Which agent for delegation after S0?
```
**PASS:** Fish syntax, correct delegation (bet-settler), correct date.
**FAIL:** Bash syntax or wrong delegation → fix orchestrator prompt/runbook.

**✅ CHECKPOINT Phase F:** TESTS_PASSED=[T1=pass T2=pass T3=pass T4=pass T5=pass T6=under_target T7=pass T8=pass]

---

## PHASE G — MONITORING (2-3 pipeline runs)

| Symptom | Diagnoza | Fix |
|---------|----------|-----|
| Agent nie followuje protokołu | Za mocno przycięty prompt | Przywróć 1-2 behavioral lines |
| Instrukcja "file not found" | Literówka w ścieżce w kilo.jsonc | Popraw path |
| sequentialthinking MCP offline | B1 fix nie zapisany | Sprawdź `mcp.sequentialthinking.enabled` |
| Delegacja nie działa | Task permission brak | `task: {"bet-*": "allow"}` |
| Capacity limit persists | Memory fragmentation | `--gc-interval 5` lub `--max-tokens 12288` |
| System prompt > target | Za dużo instrukcji | Zmniejsz instructions array |
| Fish syntax error | Runbook ma `PYTHONPATH=src` | Zmień na `env PYTHONPATH=src` |

---

## 📊 EXECUTION ORDER — ONE VIEW

```
⚠️ HAZARD MARKERS: 🔴=destructive 🟡=order-critical 🟢=safe-repeatable

🟢 M0: PRE-FLIGHT CHECK ──→ scripts exist? .venv exists?
🔴 M1: BACKUP ──────────────→ git commit + cp -r /tmp/ [CHECKPOINT]
🟢 M2: MIGRATE FILES ───────→ copy .roo/ rules → .kilo/docs/agent-rules/
🟡 M3: CREATE NEW FILES ────→ execution-core.md, execution-protocol.md
🟢 M4: FIX RUNBOOK ─────────→ 37 PYTHONPATH→fish, new_task→task, date vars
🟡 M5: UPDATE KILOJSONC ────→ 12 fixes + instructions per agent [CHECKPOINT]
🟡 M6: TRIM PROMPTS ────────→ 11 prompts -40/55% each [CHECKPOINT]
🔴 M7: DELETE ───────────────→ rm -rf .github/ .roo/ .roomodes .clinerules [CHECKPOINT]
🟢 M8: CONSISTENCY ─────────→ AGENTS.md + anti-drift + grep checks [CHECKPOINT]
🟢 M9: TEST SUITE ──────────→ T1-T8 all pass [CHECKPOINT]
🟢 M10: MONITOR ────────────→ 2-3 pipeline runs [CHECKPOINT]
```

---

## 📈 EXPECTED OUTCOMES

| Metric | Before | After |
|--------|--------|-------|
| Tools in workspace | Copilot + Roo + Continue + Kilo | **Kilo only** |
| Config files | 70+ (3 tools) | **~25** |
| System prompt tokens | ~19,000 | **< 10,000** |
| MCP conflicts | 3 configs (.vscode, .kilocode, kilo.jsonc) | **1 (kilo.jsonc)** |
| sequentialthinking MCP | disabled | **enabled** |
| Output token mismatch | Server=32768, Kilo=8192 | **Server=16384, Kilo=16384** |
| Thinking policy | Contradiction (banned but prompted) | **Consistent (allowed, guided)** |
| Bash syntax in runbook | 37 `PYTHONPATH=src` cmds → crash | **37 `env PYTHONPATH=src` → works** |
| Delegation API | `runSubagent` / `new_task` (dead) | **`task` (works)** |
| Date variables | Undefined `{date}` in 37 cmds | **Defined in runbook header** |
| Default agent on startup | `code` (generic) | **`bet-orchestrator`** |
| Pipeline scripts ref | `python3` (no venv) | **`.venv/bin/python3`** |
| Post-cleanup safety | Manual check | **8 tests + checkpoint system** |
| Rollback capability | None | **2 backups (git + fs)** |
| Recovery from interruption | Unknown | **Checkpoint per phase** |
