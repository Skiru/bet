# Implementation Plan: Audit Fixes + Tipster Insight on Coupon

**Created:** 2026-05-18  
**Status:** Ready for implementation  
**Scope:** 8 code fixes (Part A) + 1 new feature (Part B)

---

## Technical Context

| Item | Path |
|------|------|
| AgentOutput pattern | `scripts/agent_output.py` → `AgentOutput`, `add_agent_args()` |
| Tipster data structure | `tipster_support: {count, tipsters, tips}` (set by `tipster_xref.py:120`) |
| Gate output builder | `scripts/gate_checker.py:1080-1110` (only passes `tipster_count`) |
| Coupon rich desc | `scripts/coupon_builder.py:126` → `_build_rich_description()` |
| Value ranges (3 copies) | `data_enrichment_agent.py:106`, `flashscore_enricher.py:38`, `src/bet/scrapers/flashscore.py:56` |
| Actual API clients | `src/bet/api_clients/`: flashscore, espn, espn_stats, api_football, api_basketball, api_hockey, betexplorer, scores24, soccerway, sofascore, oddsportal |
| Auto-install block | `scripts/flashscore_enricher.py:499-501` |

---

## Phase 1: Standalone Fixes (No Dependencies Between Tasks)

### Task 1.1 — [MODIFY] Add AGENT_SUMMARY to `fetch_odds_api.py`

**File:** `scripts/fetch_odds_api.py`

**Changes:**
1. Import `AgentOutput`, `add_agent_args` from `agent_output`
2. Add `add_agent_args(parser)` call at line ~536 (after parser creation)
3. Instantiate `out = AgentOutput("s_odds", verbose=args.verbose, stop_on_error=args.stop_on_error)` after parse
4. In `run_full_scan()`: accept optional `out` param, emit `out.event(...)` for each sport fetched
5. At end of `run_full_scan()`: call `out.summary(verdict=..., metrics={...})` with:
   - `events_fetched`: `len(all_events)`
   - `credits_used`: `total_credits_used`
   - `credits_remaining`: `credits_remaining`
   - `db_persisted`: bool (whether DB save succeeded)
   - `sports_covered`: list of sport keys scanned
   - `errors`: list of any HTTP errors encountered

**Pattern reference:** `scripts/tipster_xref.py:148-180`

**Definition of Done:**
- [ ] `python3 scripts/fetch_odds_api.py --verbose` emits `AGENT_SUMMARY:{...}` JSON on last line
- [ ] `python3 scripts/fetch_odds_api.py` (no --verbose) behaves identically to before
- [ ] Exit code 0 on success, 1 on partial (some sports failed), 2 on critical (no API key)

---

### Task 1.2 — [MODIFY] Remove auto-install `curl_cffi` from `flashscore_enricher.py`

**File:** `scripts/flashscore_enricher.py`

**Changes:**
Replace lines 497-501:
```python
try:
    from curl_cffi import requests as c_requests
except ImportError:
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "curl_cffi"])
    from curl_cffi import requests as c_requests
```
With:
```python
from curl_cffi import requests as c_requests
```

**Rationale:** `curl_cffi` is already in `pyproject.toml`. Auto-installing packages at runtime is a security anti-pattern (supply chain risk, arbitrary code execution).

**Definition of Done:**
- [ ] No `subprocess` or `pip install` call in the file
- [ ] `from curl_cffi import requests as c_requests` is a direct import (will fail fast if missing)
- [ ] Existing tests pass

---

### Task 1.3 — [CREATE] Unify `SPORT_VALUE_RANGES` into single source of truth

**File to create:** `src/bet/stats/value_ranges.py`

**Content:** Canonical `SPORT_VALUE_RANGES` dict — superset of keys from `flashscore_enricher.py` (which has the most keys: `2_pointers`, `3_pointers`, `free_throws`, `shots_on_goal`, `penalties_in_minutes`, `win_1st_serve`, `break_points_saved`).

**Files to modify (import from new module):**
1. `scripts/data_enrichment_agent.py` — replace inline dict at line 106 with `from bet.stats.value_ranges import SPORT_VALUE_RANGES`
2. `scripts/flashscore_enricher.py` — replace inline dict at line 38 with `from bet.stats.value_ranges import SPORT_VALUE_RANGES`  
3. `src/bet/scrapers/flashscore.py` — replace inline dict at line 56 with `from bet.stats.value_ranges import SPORT_VALUE_RANGES`
4. `scripts/clean_garbage_team_form.py` — update import at line 16 to use new location

**Definition of Done:**
- [ ] Single canonical dict in `src/bet/stats/value_ranges.py`
- [ ] All 4 consumers import from the new module
- [ ] No duplicate `SPORT_VALUE_RANGES` definitions remain
- [ ] All keys from all previous copies are present in the canonical version
- [ ] Existing tests pass

---

### Task 1.4 — [MODIFY] Remove `playwright/*` from `bet-scanner.agent.md`

**File:** `.github/agents/bet-scanner.agent.md`

**Change:** Remove `"playwright/*"` from the tools list at line 16.

**Definition of Done:**
- [ ] No `playwright` reference in scanner agent tools

---

### Task 1.5 — [MODIFY] Fix stale API client references in `bet-statistician.agent.md`

**File:** `.github/agents/bet-statistician.agent.md`

**Change:** Replace reference to "flashscore, espn, basketball_reference, moneypuck" with actual clients:
`flashscore, espn, espn_stats, api_football, api_basketball, api_hockey, betexplorer, scores24, soccerway`

**Definition of Done:**
- [ ] Client list in statistician agent matches `src/bet/api_clients/` directory contents
- [ ] No references to `basketball_reference` or `moneypuck`

---

## Phase 2: Documentation Updates (Depends on Phase 1.3 for value_ranges path)

### Task 2.1 — [MODIFY] Document `google_sports_client.py` in agent files

**Files:**
1. `.github/agents/bet-enricher.agent.md` — Add "Google Sports Client (SerpAPI)" section:
   - Source: `scripts/api_clients/google_sports_client.py`
   - Budget: 15 queries/run, 250/month (SerpAPI free tier)
   - Output: H2H match results, recent form, head-to-head stats
   - Position: Last fallback before Flashscore in all sport chains

2. `.github/internal-prompts/bet-enrich.prompt.md` — Add Google Sports to enrichment sources checklist

3. `.github/skills/bet-navigating-sources/SKILL.md` — Add new section "### Google Sports / SerpAPI (Tier A — H2H)" with:
   - URL patterns (SerpAPI endpoints)
   - Rate limits (250/month)
   - Data returned (H2H scores, dates, competitions)
   - Fallback position (after sport-specific APIs, before Flashscore)

**Definition of Done:**
- [ ] Enricher agent references `google_sports_client.py` with budget limits
- [ ] Navigating-sources skill has Google Sports section
- [ ] Internal prompt includes Google Sports in enrichment sources

---

### Task 2.2 — [MODIFY] Document H2H retrieval path

**Files:**
1. `.github/agents/bet-statistician.agent.md` — Add "H2H Data Retrieval" section:
   - Primary: `db_data_loader.load_h2h_from_db(team_a, team_b, sport)`
   - Enrichment path: `enrich_h2h()` → Google Sports → Flashscore → `team_form.h2h_values`
   - DB table: `team_form` (column `h2h_values` = JSON)

2. `.github/internal-prompts/bet-deep-stats.prompt.md` — Add H2H retrieval step to analysis workflow

3. `.github/skills/bet-querying-database/SKILL.md` — Add `load_h2h_from_db()` function with example:
   ```python
   from scripts.db_data_loader import load_h2h_from_db
   h2h = load_h2h_from_db("Arsenal", "Chelsea", "football")
   # Returns: {"meetings": 12, "home_wins": 5, "away_wins": 4, "draws": 3, "stats": {...}}
   ```

**Definition of Done:**
- [ ] Statistician agent documents the full H2H path
- [ ] Querying-database skill includes `load_h2h_from_db()` with usage example
- [ ] Deep-stats prompt includes H2H retrieval as an explicit step

---

### Task 2.3 — [MODIFY] Update fallback chains in `bet-enricher.agent.md`

**File:** `.github/agents/bet-enricher.agent.md`

**Change:** Replace abstract L1-L6 layer descriptions with actual per-sport chains from `scripts/fetch_api_stats.py`:

```
FALLBACK CHAINS (actual):
- football: ESPN → API-Football → Football-Data-Org → Understat → Google Sports → SerpAPI → Flashscore (curl_cffi)
- basketball: ESPN → NBA-API → API-Basketball → Google Sports → SerpAPI → Flashscore (curl_cffi)
- hockey: ESPN → API-Hockey → Google Sports → SerpAPI → Flashscore (curl_cffi)
- tennis: ESPN → Google Sports → SerpAPI → Flashscore (curl_cffi)
- volleyball: ESPN → API-Volleyball → Google Sports → SerpAPI → Flashscore (curl_cffi)

LAST RESORT: flashscore_enricher.py (curl_cffi only, NO Playwright)
```

**Definition of Done:**
- [ ] Per-sport chains listed explicitly
- [ ] No abstract "L1-L6" without concrete mapping
- [ ] Flashscore marked as curl_cffi-only (no Playwright)

---

## Phase 3: Tipster Insight on Coupon (New Feature)

**Dependencies:** None on Phase 1/2 (can be built in parallel), but conceptually ships after.

### Task 3.1 — [MODIFY] Pass `tipster_support` dict through gate output

**File:** `scripts/gate_checker.py`

**Change:** In the gate output builder (~line 1099-1104), add `tipster_support` alongside `tipster_count`:

```python
# Current (line 1099):
"tipster_count": (
    analysis.get("tipster_count")
    or (analysis.get("tipster_support") or {}).get("count")
    or 0
),

# Add after tipster_count:
"tipster_support": analysis.get("tipster_support") or {},
```

This preserves backward compatibility (tipster_count still present) while adding the full dict.

**Definition of Done:**
- [ ] Gate output JSON includes `tipster_support: {count, tipsters, tips}` for matched candidates
- [ ] `tipster_count` still present (no breaking change)
- [ ] Gate output file size increase is acceptable (tips have `reasoning` field — typically 50-200 chars each)

---

### Task 3.2 — [MODIFY] Add tipster insight rendering to `coupon_builder.py`

**File:** `scripts/coupon_builder.py`

**Changes:**

1. Add new function `_build_tipster_insight(pick: dict) -> str`:
   - Reads `pick["tipster_support"]["tips"]` 
   - For each tip: format source, market prediction, truncated reasoning (max 80 chars)
   - Add "↔ NASZ WYBÓR" line showing our pick + why it differs (if it does)
   - If `tipster_support` is empty/missing: query DB as fallback (import `TipsterRepo`)

2. Add DB fallback function `_get_tipster_data_fallback(home: str, away: str, date: str) -> list`:
   - Import from `bet.db.repositories import TipsterRepo`
   - Query `TipsterRepo.get_picks_by_date(date)`
   - Fuzzy-match by team names (same logic as `tipster_xref.py:106-115`)
   - Return matching tips list

3. Modify `_build_rich_description()` — append tipster insight at the end:
   ```python
   tipster_section = _build_tipster_insight(pick)
   if tipster_section:
       lines.append("")  # blank line separator
       lines.append(tipster_section)
   ```

4. Two call sites already use `_build_rich_description` (lines 1513, 1561) — no changes needed there.

**Output format:**
```
🎯 TIPSTER INSIGHT:
• ZawodTyper (87% acc): Kornery >10.5 @1.85 — "Oba zespoły atakują bokami..."
• OLBG: Match Winner Home @1.60 — "Dominacja w lidze, 8W z 10"
↔ NASZ WYBÓR: Kornery Total OVER 9.5 @1.75 (safety 0.72, L10 avg 11.2)
   Różnica: Niższa linia = wyższe prawdopodobieństwo
```

**Edge cases:**
- No tipster data → no section rendered (silent)
- Tipsters agree with our pick → show "✓ Zgodność z tipsterami" instead of "Różnica"
- Multiple tipsters on same market → group together

**Definition of Done:**
- [ ] Every coupon leg shows tipster insight when data exists
- [ ] DB fallback works when gate output lacks `tipster_support` (legacy mode)
- [ ] Formatting uses Polish labels per `betting-artifacts.instructions.md`
- [ ] No tipster data = no section (graceful degradation)
- [ ] Existing coupon structure unchanged (tipster section appended, not inserted)

---

### Task 3.3 — [MODIFY] Update documentation for tipster insight

**Files:**

1. `.github/skills/bet-building-coupons/SKILL.md` — Add section:
   ```
   ### Tipster Insight Section
   Every coupon leg includes tipster predictions when available.
   Shows: source, market prediction, reasoning summary.
   Compares tipster view vs pipeline analysis when they disagree.
   Data source: gate_output.tipster_support.tips[] or DB fallback.
   ```

2. `.github/internal-prompts/bet-portfolio.prompt.md` — Add verification step:
   ```
   VERIFY: Each approved pick has tipster_support in gate output.
   If missing: warn that tipster insight will use DB fallback (slower).
   ```

3. `.github/instructions/betting-artifacts.instructions.md` — Add tipster insight format to coupon format spec (under rich description format section).

**Definition of Done:**
- [ ] Building-coupons skill documents the tipster insight section
- [ ] Portfolio prompt instructs agent to verify tipster data presence
- [ ] Artifacts instructions include the tipster insight format example

---

## Dependency Graph

```
Phase 1 (all independent):
  1.1 (fetch_odds_api AGENT_SUMMARY)
  1.2 (remove auto-install)
  1.3 (unify value_ranges)  ──→  Phase 2 (2.1, 2.2 reference correct paths)
  1.4 (remove playwright)
  1.5 (fix client list)

Phase 2 (independent of each other, depends on 1.3 for path references):
  2.1 (google_sports_client docs)
  2.2 (H2H path docs)
  2.3 (fallback chains)

Phase 3 (independent of Phase 1 & 2):
  3.1 (gate_checker pass-through)  ──→  3.2 (coupon_builder rendering)  ──→  3.3 (docs)
```

---

## Security Considerations

| Risk | Mitigation |
|------|------------|
| Task 1.2: Auto-install removed | Direct import; crash-fast on missing dep |
| Task 3.2: DB fallback query | Uses parameterized queries via `TipsterRepo` (no raw SQL) |
| Task 3.2: Fuzzy match | Uses `fuzz.token_sort_ratio` — no regex injection risk |
| Task 1.1: API key exposure | `fetch_odds_api.py` already masks key in output; AGENT_SUMMARY must NOT include `api_key` |

---

## Testing Strategy

| Task | Test approach |
|------|--------------|
| 1.1 | Run `fetch_odds_api.py --verbose --list-sports` (0 credits) → verify AGENT_SUMMARY JSON |
| 1.2 | `import scripts.flashscore_enricher` succeeds without subprocess |
| 1.3 | `from bet.stats.value_ranges import SPORT_VALUE_RANGES; assert "football" in SPORT_VALUE_RANGES` |
| 3.1 | Run gate_checker on test data → verify `tipster_support` key in output |
| 3.2 | Run coupon_builder on gate output with tipster data → verify "TIPSTER INSIGHT" in coupon |
| 3.2 | Run coupon_builder on gate output WITHOUT tipster data → verify no crash, fallback used |

All tests via existing `pytest tests/` suite + manual pipeline run on next betting day.
