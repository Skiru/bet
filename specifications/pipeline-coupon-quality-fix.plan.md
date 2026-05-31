# Pipeline Coupon Quality Fix Plan

**Version:** 1.0  
**Date:** 2026-05-31  
**Scope:** 10 bugs (4×P0, 5×P1, 1×P2) in gate_checker.py and coupon_builder.py  
**Triggered by:** 2026-05-31 coupon validation — negative EV picks, zero tipster data, unsafe picks in coupons  
**System size:** gate_checker.py ~2300 LOC, coupon_builder.py ~3100 LOC  

---

## Technical Context

### Data Flow (S7→S8)
```
gate_checker.py (S7)
  ├── check_18_point_gate() per candidate
  ├── Systemic discount: if >80% fail same gate point → discount it
  ├── Bucketing: HARD REJECT string → rejected; else → advisory_tier (STRONG/MODERATE/WEAK/FLAGGED)
  └── Output: gate_results DB table + JSON

coupon_builder.py (S8)
  ├── Reads gate output → separates approved/extended/rejected
  ├── Assigns picks to tiers: LR (safety≥0.75, gate≥16), HR, MS, NIGHT
  ├── Builds: singles, core coupons (tier-grouped), combos, extended pool
  ├── ID format: CP-{date}-{type}{num}
  └── Output: coupons DB + markdown + JSON
```

### Key Code Locations
| Concern | File | Lines |
|---------|------|-------|
| EV gate check | gate_checker.py | 312-321 |
| Hard reject logic | gate_checker.py | 1648-1658 |
| Systemic discount calculation | gate_checker.py | 1600-1610 |
| Advisory tier assignment | gate_checker.py | 1668-1690 |
| Singles generation | coupon_builder.py | 2177-2215 |
| Core coupon tier assignment | coupon_builder.py | 1170-1230 |
| Coupon ID generation | coupon_builder.py | 1184, 2191 |
| Market matrix builder | coupon_builder.py | 2654-2690 |
| Extended pool renderer | coupon_builder.py | 2880-2930 |
| MS tier title mapping | coupon_builder.py | 2850 |

### Config Reference (`betting_config.json`)
- `min_safety_score`: 0.35 (currently unused as hard floor in coupon builder)
- `max_same_sport_legs_in_coupon`: 3
- `max_singles`: 10

---

## Architecture Decision: Systemic Discount

**Problem:** The systemic discount mechanism (lines 1600-1610) was designed to handle infrastructure gaps (e.g., scraper down → all candidates fail "source freshness" gate). When S2 produces 0 tipster picks, gate #6 (tipster argument) fails for 100% of candidates and gets discounted — effectively hiding a pipeline failure.

**Decision:** Introduce a **non-discountable gates** list. Certain gates represent pipeline prerequisites, not infrastructure quality signals. When these gates fail systemically, the correct response is to HALT the pipeline, not discount the failure.

**Non-discountable gates:**
- Gate #6 (tipster argument) — tipster data is a pipeline input, not optional enrichment
- Gate #8 (EV calculation) — if no picks have EV, odds pipeline failed

**Discountable gates (infrastructure quality):**
- Gate #2 (source freshness)
- Gate #3 (L10 data availability)
- Gate #14 (live odds comparison)

This is a tradeoff: non-discountable gates can block the pipeline entirely if S2 fails. The mitigation is that `coupon_builder.py` adds a prominent "TIPSTER-BLIND" warning when tipster data is missing, allowing the user to consciously proceed.

---

## Phase 1 — P0 Critical Fixes (Financial Loss Prevention)

### Task 1.1: Hard-reject negative EV picks in gate_checker.py
`[MODIFY] scripts/gate_checker.py`

**Change:** In the bucket assignment loop (line ~1648), add a secondary hard-reject condition: if `ev is not None and ev < 0`, set `hard_reject = True`.

**Implementation:**
```python
# After the existing HARD REJECT string scan (line ~1658):
# New: Hard reject for calculated negative EV
if not hard_reject and ev is not None and ev < 0:
    hard_reject = True
    hard_reject_reason = f"NEGATIVE_EV: EV={ev:.3f} — calculated negative expected value"
```

**Side effects:**
- Picks previously reaching APPROVED with negative EV will now be REJECTED
- This only affects picks where EV was actually calculated (has odds data). Stats-first picks (EV=None) are unaffected
- May reduce approved count by 5-15% on typical days with odds data

**Definition of done:**
- [ ] Negative EV picks (ev < 0) are placed in `rejected` bucket, never in `approved`
- [ ] Stats-first picks (ev=None) continue to pass gate #8 unchanged
- [ ] `hard_reject_reason` contains the EV value for traceability
- [ ] Existing tests pass; new test covers this case

---

### Task 1.2: Add safety floor filter in coupon_builder.py
`[MODIFY] scripts/coupon_builder.py`

**Change:** Before any pick enters a coupon (singles, core, combo), enforce a hard safety floor. Add a `_passes_inclusion_filter(pick, config)` function that checks:
1. `safety_score >= 0.30` (absolute floor — never in ANY coupon)
2. For core coupons (LR/MS tiers): `safety_score >= 0.40`

**Implementation location:** Add filter function near line ~2177 (before singles loop) and in `assign_picks_to_core()` entry.

**Config addition** (`betting_config.json`):
```json
"hard_safety_floor": 0.30,
"core_coupon_min_safety": 0.40
```

**Side effects:**
- Picks with safety 0.09-0.29 are excluded from ALL coupons (still visible in extended pool)
- Picks with safety 0.30-0.39 are excluded from core (LR/MS) but can appear in HR/NIGHT singles
- May reduce total coupon legs by 10-20% on low-data days

**Definition of done:**
- [ ] No pick with `safety_score < 0.30` appears in any coupon section (singles, core, combo)
- [ ] No pick with `safety_score < 0.40` appears in LR or MS tier coupons
- [ ] Thresholds are configurable via `betting_config.json`
- [ ] Filtered picks still appear in extended pool with a note
- [ ] Existing tests pass; new test verifies the floor

---

### Task 1.3: Enforce sport diversity in MULTI-SPORT combos
`[MODIFY] scripts/coupon_builder.py`

**Change:** In the core coupon builder (`assign_picks_to_core` and tier grouping logic), when assigning to MS tier, validate that no single sport exceeds 2 legs. If violated, overflow legs go to HR tier instead.

**Implementation:** In the tier-assignment loop (line ~1170), add sport-count check for MS coupons:
```python
# When building MS coupon, enforce max 2 same-sport legs
sports_in_coupon = Counter(leg.get("sport") for leg in current_legs)
if any(count > 2 for count in sports_in_coupon.values()):
    # Reassign excess legs to HR
    ...
```

**Alternative (simpler):** Post-processing pass after all core coupons are built — scan MS coupons, if any has ≤2 distinct sports with >2 legs from one sport, relabel it as HR.

**Side effects:**
- MS coupons will have genuine sport diversity (min 3 sports for 4+ leg coupons, or max 2 legs per sport)
- Some days with only 1-2 active sports may produce 0 MS coupons — this is correct behavior

**Definition of done:**
- [ ] Every coupon labeled MS has max 2 legs from the same sport
- [ ] Excess same-sport legs are moved to HR tier or overflow coupon
- [ ] Config key `max_same_sport_in_ms` (default: 2) controls the threshold
- [ ] Existing tests pass; new test verifies enforcement

---

### Task 1.4: Non-discountable gates + TIPSTER-BLIND warning
`[MODIFY] scripts/gate_checker.py`  
`[MODIFY] scripts/coupon_builder.py`

**Part A — gate_checker.py:** Add a `NON_DISCOUNTABLE_GATES` set. In the systemic discount calculation (line ~1602), exclude these gates from the `systemic_points` set:

```python
NON_DISCOUNTABLE_GATES = {6, 8}  # tipster argument, EV calculation

# In systemic calculation:
for pt, cnt in point_failure_counts.items():
    if cnt / total_count > systemic_threshold and pt not in NON_DISCOUNTABLE_GATES:
        systemic_points.add(pt)
```

**Part B — gate_checker.py:** When gate #6 fails for >80% of candidates, emit a structured warning in the output JSON:
```python
"pipeline_warnings": ["TIPSTER_DATA_MISSING: Gate #6 failed for {pct}% of candidates. S2 may have failed."]
```

**Part C — coupon_builder.py:** At the start of `build_coupons()`, check for tipster data presence. If 0 tipster enrichment found across all approved picks, prepend a "⚠️ KUPONY BEZ DANYCH TIPSTERÓW" warning header in the markdown output.

**Side effects:**
- Gate #6 failures will no longer be discounted — candidates that genuinely lack tipster backing will show more gate failures, reducing their advisory tier
- This may push more candidates from STRONG→MODERATE→WEAK, reducing core coupon pool
- The pipeline won't auto-halt (that's the orchestrator's job), but the warning in output makes the gap visible

**Definition of done:**
- [ ] Gates 6 and 8 are never added to `systemic_points`
- [ ] `pipeline_warnings` list is included in gate_checker output JSON when applicable
- [ ] Coupon markdown starts with visible warning when tipster data is absent
- [ ] Existing tests pass; new tests verify non-discountable behavior

---

## Phase 2 — P1 Methodology & Format Fixes

### Task 2.1: Merge SINGLES into tier structure
`[MODIFY] scripts/coupon_builder.py`

**Change:** Instead of rendering a separate "## SINGLE BETS" section, assign each single to its appropriate tier section (LR/MS/HR/NIGHT) based on the pick's `risk_tier`. The markdown renderer already has tier sections — singles should flow into them marked as "(SINGLE)".

**Implementation:** In `write_coupon_markdown()` (line ~2793 area), instead of rendering singles in a separate block, merge them into `tier_groups` before rendering:
```python
# Merge singles into tier groups
for s in singles:
    tier = s.get("tier", "MS")
    bucket = tier if tier in tier_groups else "MS"
    tier_groups[bucket].append(s)
```

Remove or skip the separate "## SINGLE BETS" and "## 🏆 BANKER" rendering blocks.

**Side effects:**
- Output format now matches betting-artifacts.instructions.md §3
- Users who relied on "SINGLE BETS" section will see picks under their tier header instead
- Banker concept is deprecated (was already rarely populated)

**Definition of done:**
- [ ] No "## SINGLE BETS" or "## 🏆 BANKER" sections in coupon markdown output
- [ ] Singles appear within their respective tier section (LR/MS/HR/NIGHT) marked as single
- [ ] Empty tier sections are not rendered (no "## LOW-RISK" with 0 entries)
- [ ] Existing tests updated; output format matches spec

---

### Task 2.2: Filter extended pool empty entries
`[MODIFY] scripts/coupon_builder.py`

**Change:** In the extended pool renderer (line ~2880), already has a filter in `_market_matrix_rows()` (line 2659: `if p.get("best_market") and p.get("best_market").get("name")`). Apply the same filter when building `extended_pool` list in `build_coupons()`.

**Implementation:** Where extended pool is populated, add:
```python
extended_pool = [p for p in extended_pool if (p.get("best_market") or {}).get("name")]
```

**Side effects:**
- Reduces extended pool visual noise
- Picks without market data still exist in DB but won't render in coupon artifact

**Definition of done:**
- [ ] Extended pool only shows entries with a non-empty `best_market.name`
- [ ] No blank/dash-only rows in extended pool table
- [ ] Existing tests pass

---

### Task 2.3: Add bull/bear reasoning to extended pool
`[MODIFY] scripts/coupon_builder.py`

**Change:** In the extended pool table renderer, replace the "G1, G2, G7" gate-point-ID display with extracted reasoning from `gate_details`. Add columns or inline text for: bull case, bear case, missing data.

**Implementation:** Extract from `pick.get("gate_details", {})`:
- Bull: Concatenate messages from passed gates (especially #5 directional, #12 bull>bear)
- Bear: Concatenate messages from failed gates (#10 red flags, #12 bear≥bull)
- Missing: List failed gate IDs that indicate data gaps (#2, #3, #6)

Replace the "Za ✅ | Przeciw ❌" columns content with these extracted summaries (truncated to ~60 chars each).

**Side effects:**
- Extended pool becomes actionable rather than opaque
- Slightly wider table — may need column width adjustments for readability

**Definition of done:**
- [ ] Extended pool shows summarized reasoning (bull/bear/gaps) instead of gate point IDs
- [ ] Each reasoning column is ≤80 characters
- [ ] Gate point IDs are still available in JSON output for debugging
- [ ] Existing tests updated

---

### Task 2.4: Fix coupon ID format to include version
`[MODIFY] scripts/coupon_builder.py`

**Change:** Update all coupon ID generation locations to use spec-compliant format: `CP-YYYYMMDD-{TIER}{NUM}v{VERSION}`.

**Locations to update:**
- Line 1184: `f"CP-{date_str}-{tier_label}{tier_num}"` → `f"CP-{date_str}-{tier_label}{tier_num}v1"`
- Line 1208: same pattern
- Line 1217: same pattern
- Line 1565: `f"CP-{date_str}-COMBO-{tier_key}{combo_num}"` → `f"CP-{date_str}-COMBO-{tier_key}{combo_num}v1"`
- Line 1633: `f"CP-{date_str}-COMB{k}x{combo_num_total}"` → `f"CP-{date_str}-COMB{k}x{combo_num_total}v1"`
- Line 2191: `f"CP-{date_str}-SINGLE{i}"` → merge into tier (per Task 2.1) with `v1`

**Version logic:** Default `v1`. If a coupon for the same date+tier+num already exists in DB (rerun scenario), increment version. Query: `SELECT MAX(version) FROM coupons WHERE date=? AND tier=? AND num=?`.

**Side effects:**
- All existing coupon IDs in DB lack `v1` suffix — this is fine (old format, not re-processed)
- Settlement scripts that match on coupon ID may need pattern update (check `settle_results.py`)

**Definition of done:**
- [ ] All new coupon IDs follow `CP-YYYYMMDD-{TIER}{NUM}v{VER}` format
- [ ] Version auto-increments on reruns for same date
- [ ] Settlement/ledger scripts handle both old and new ID formats
- [ ] SINGLE prefix replaced with tier prefix (LR/MS/HR/NIGHT) per Task 2.1

---

### Task 2.5: Ensure rejections populate ODRZUCONE section
`[MODIFY] scripts/gate_checker.py` (verification only)

**Change:** This is mostly solved by Tasks 1.1 (negative EV → reject) and 1.2 (safety floor). After those fixes, there WILL be rejected picks.

**Verification:** Confirm that `write_coupon_markdown()` line ~3060 correctly renders the "## ODRZUCONE" section with:
- Event name, market, rejection reason
- Top 10 by gate score (closest to approval)

No code change needed beyond Tasks 1.1 and 1.2 — this task is a verification checkpoint.

**Definition of done:**
- [ ] After Tasks 1.1+1.2 are implemented, running coupon_builder on 2026-05-31 data produces non-empty ODRZUCONE section
- [ ] Rejection reasons are human-readable (EV value, safety value)
- [ ] Top-10 ordering is by gate_score descending (closest to passing)

---

## Phase 3 — P2 Quality Fixes

### Task 3.1: Fix Hit% column in market matrix
`[MODIFY] scripts/coupon_builder.py`

**Change:** The `_market_matrix_rows()` function (line 2654) already reads `hit_rate_l10`:
```python
hit_l10 = best.get("hit_rate_l10")
hit_str = f"{_safe_float(hit_l10):.0%}" if hit_l10 else "-"
```

The issue is that `hit_rate_l10` is stored as a fraction string like `"7/10"` or a float like `0.7`. The `_safe_float()` on `"7/10"` returns 0.0 (can't parse fraction).

**Fix:** Add fraction parsing:
```python
hit_l10 = best.get("hit_rate_l10")
if hit_l10 and isinstance(hit_l10, str) and "/" in hit_l10:
    parts = hit_l10.split("/")
    hit_str = f"{int(parts[0])}/{int(parts[1])}"
elif hit_l10 and isinstance(hit_l10, (int, float)):
    hit_str = f"{float(hit_l10):.0%}"
else:
    hit_str = "-"
```

**Side effects:** None — purely display improvement.

**Definition of done:**
- [ ] Hit% column shows actual values (e.g., "7/10" or "70%") instead of "-"
- [ ] Both fraction strings and float values are handled
- [ ] Existing tests pass

---

## Phase 4 — Config & Test Infrastructure

### Task 4.1: Add new config parameters
`[MODIFY] config/betting_config.json`

**Add keys:**
```json
"hard_safety_floor": 0.30,
"core_coupon_min_safety": 0.40,
"max_same_sport_in_ms": 2,
"non_discountable_gates": [6, 8]
```

**Definition of done:**
- [ ] All new thresholds are configurable (not hardcoded in scripts)
- [ ] Default values match the plan specifications
- [ ] Scripts read these values via `config.get(key, default)`

---

### Task 4.2: Test — Negative EV rejection
`[MODIFY] tests/test_gate_checker.py` (or create if doesn't exist)

**Test cases:**
1. Pick with `ev=-0.05` → bucket = "rejected", reason contains "NEGATIVE_EV"
2. Pick with `ev=0.10` → bucket != "rejected" (passes normally)
3. Pick with `ev=None` → bucket != "rejected" (stats-first pass-through)
4. Pick with `ev=0.0` → bucket = "rejected" (zero EV is not positive)

**Definition of done:**
- [ ] 4 test cases pass
- [ ] Tests are deterministic (no external API calls)

---

### Task 4.3: Test — Safety floor filter
`[MODIFY] tests/test_coupon_builder.py` (or create if doesn't exist)

**Test cases:**
1. Pick with `safety=0.09` → not in any coupon output
2. Pick with `safety=0.35` → appears in HR/NIGHT singles but NOT in LR/MS core
3. Pick with `safety=0.50` → appears in all applicable sections
4. Pick with `safety=0.80` → appears in LR section

**Definition of done:**
- [ ] 4 test cases pass
- [ ] Tests use mock config with known thresholds

---

### Task 4.4: Test — MULTI-SPORT diversity enforcement
`[MODIFY] tests/test_coupon_builder.py`

**Test cases:**
1. Coupon with 3 football + 1 basketball legs → NOT labeled MS (relabeled HR or split)
2. Coupon with 2 football + 1 basketball + 1 tennis → valid MS
3. Coupon with 2 football + 2 basketball → valid MS (2+2, no single sport >2)

**Definition of done:**
- [ ] 3 test cases pass
- [ ] Tests verify the `tier` field of output coupons

---

### Task 4.5: Test — Non-discountable gates
`[MODIFY] tests/test_gate_checker.py`

**Test cases:**
1. Gate #6 fails for 100% of candidates → still counted in effective_failures (NOT in systemic_points)
2. Gate #2 fails for 100% of candidates → IS in systemic_points (discounted)
3. Mix: Gates #2 and #6 both fail systemically → only #2 is discounted

**Definition of done:**
- [ ] 3 test cases pass
- [ ] Tests verify `systemic_points` set contents and `effective_failures` count

---

## Execution Order & Dependencies

```
Phase 1 (parallel-safe within phase):
  Task 1.1 (neg EV reject)  ─── no deps
  Task 1.2 (safety floor)   ─── no deps
  Task 1.3 (MS diversity)   ─── no deps
  Task 1.4 (non-discount)   ─── no deps

Phase 2 (after Phase 1):
  Task 2.1 (merge singles)  ─── depends on 1.2 (safety filter applied before merge)
  Task 2.2 (filter extended) ─── no deps
  Task 2.3 (bull/bear text)  ─── depends on 2.2 (filtered list)
  Task 2.4 (coupon ID)       ─── depends on 2.1 (tier assignment final)
  Task 2.5 (ODRZUCONE verify) ─── depends on 1.1, 1.2

Phase 3 (independent):
  Task 3.1 (Hit% fix)       ─── no deps

Phase 4 (after all code changes):
  Task 4.1 (config)         ─── before all code tasks (or concurrent)
  Task 4.2-4.5 (tests)      ─── after corresponding code tasks
```

---

## Risk Assessment

| Task | Risk | Mitigation |
|------|------|------------|
| 1.1 (neg EV) | Over-rejection on days with noisy odds data | Only rejects when EV is CALCULATED negative, not when missing |
| 1.2 (safety floor) | Too aggressive — wipes out candidates on low-data days | Floor is 0.30 (very low bar); extended pool still shows them |
| 1.3 (MS diversity) | Zero MS coupons on esports-only days | Acceptable — HR tier absorbs these correctly |
| 1.4 (non-discount) | Gate #6 always fails → all candidates get +1 failure → advisory tiers shift down | Correct behavior — forces pipeline to have working S2 |
| 2.1 (merge singles) | Breaking change for users who look for "SINGLE BETS" header | Clear in changelog; format now matches spec |
| 2.4 (coupon ID) | Settlement scripts break on new format | Check `settle_results.py` pattern matching; add backward compat |

---

## Validation Criteria (Full Plan)

After all tasks complete, run `coupon_builder.py --date 2026-05-31` on existing data and verify:
1. **Zero negative EV picks** in any coupon section
2. **Zero picks with safety < 0.30** in any coupon section
3. **All MS coupons** have ≤2 legs from any single sport
4. **No "## SINGLE BETS"** or "## 🏆 BANKER"** headers in output
5. **ODRZUCONE section** is non-empty with clear rejection reasons
6. **Extended pool** has no empty-market entries
7. **Hit% column** shows actual values
8. **Coupon IDs** follow `CP-YYYYMMDD-TIERNUMvVER` format
9. **TIPSTER-BLIND warning** present (since 2026-05-31 has 0 tipster data)
10. **Pipeline warnings** in JSON output mention missing tipster data
