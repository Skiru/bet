# Pipeline Session Audit — 2026-05-29 & 2026-05-30 (FAILED)

> Reviewed by: Copilot (tsh-engineering-manager mode)  
> Session 1 ran: 2026-05-29 ~06:30–10:56 Europe/Warsaw (completed, for May 29 events)  
> Session 2 ran: 2026-05-30 morning (FAILED at 49%, for May 30 events)  
> Agent: Bet Orchestrator (Kilo Code) on Qwen3.6-35B-A3B MoE  

---

## 🔴 SESSION 2 FAILURE (May 30 — CRASHED at 49%)

### Failure Mode
The orchestrator hit its **output token limit (32768)** while still in `<think>` reasoning blocks. It produced NO actionable output — the entire 32K tokens were consumed by internal reasoning about the fixtures table errors.

### Error Loop (visible in screenshot)
```
fixtures table (date format mismatch — stale state is from fixtures that no longer 
exist in the fixtures table (date format mismatch — stale state is from fixtures that 
no longer exist in the fixtures table ...
```
This message repeats in a LOOP — the model got stuck in a reasoning spiral about the DB quality issue and burned all output tokens without ever producing a tool call or response.

### Root Causes

**A. DB Fixtures Table is a MESS (triggers the error loop):**
- 39,759 total fixtures
- 1,714 fixtures with TIME-ONLY kickoff (e.g., "20:00" instead of "2026-05-29T20:00:00+00:00")
- 111 fixtures with EMPTY kickoff
- 10,762 stale fixtures still marked "scheduled" from before May 30
- 0 fixtures for 2026-05-30 (nothing to work with!)
- Status field has 60+ different values (NS, Not Started, Not started, scheduled, pending, live, 1H, 2H, FT, Ended, etc.) — no normalization
- The model sees this mess during S0.5 (DB audit) and enters a reasoning death spiral

**B. Output Token Limit Too Low for Complex Reasoning:**
- Server: `--max-tokens 32768` 
- Kilo Code config: `"output": 32768`
- The model uses `<think>` blocks ALWAYS (required by config)
- For complex DB audit scenarios, thinking can easily consume 20K+ tokens
- Leaving <8K for actual tool calls and response → guaranteed failure on complex steps

**C. No May 30 Fixtures Discovered:**
- `SELECT COUNT(*) FROM fixtures WHERE kickoff LIKE '2026-05-30%'` → **0 rows**
- The S1 (discover_events) step either never ran or failed silently
- Without fixtures for the target date, the entire pipeline has nothing to process

**D. Session State Never Updated:**
- `.kilocode/memory/session-state.md` still shows May 28 data
- `.pipeline_checkpoint.md` shows May 30 date but all steps unchecked (S0 boot only)
- The failed session wrote the checkpoint header but crashed before completing S0

### What the Session Managed Before Crash (4 files modified):
These are likely:
1. `betting/data/.pipeline_checkpoint.md` — reset to May 30 (confirmed: 23:34 timestamp)
2. `betting/data/betting.db` — possible fixture cleanup or audit queries (23:44 timestamp)
3. Two other files (possibly settlement attempt or DB audit artifacts)

### Immediate Fixes Needed for May 30 Session:

| Fix | Action | Priority |
|-----|--------|----------|
| Increase output tokens | `--max-tokens 65536` in server plist + kilo.jsonc `"output": 65536` | P0 |
| Populate May 30 fixtures | Run `discover_events.py` manually first | P0 |
| Clean fixtures table | DELETE time-only kickoffs, normalize status values | P1 |
| Mark stale fixtures | `UPDATE fixtures SET status='expired' WHERE kickoff < '2026-05-30' AND status='scheduled'` | P1 |
| Add output budget guard | If thinking uses >50% of output budget, force a tool call | P2 |

---

## CRITICAL ISSUES (Fix Tomorrow — High Priority)

### 1. 🚨 ZERO TIPSTER DATA — S2 FULLY SKIPPED/FAILED

**Evidence:** `tipster_picks` table has 0 rows for 2026-05-29. All 277 gate candidates have `tipster_count: 0` and `tipster_support: {}`.

**Impact:** The CORE VALUE of the pipeline (source fusion: tipsters + stats + web search) was completely absent. Coupons were built from statistics alone — no argumentative reasoning, no tactical context, no tipster consensus.

**Root cause to investigate:**
- Was `tipster_xref.py` run at all? (no tipster_consensus file for 2026-05-29)
- Was the brave-search web fallback attempted for manual tipster check?
- Session state from May 28 says "S2: Tipster xref skipped (no tipster data in DB)" — this pattern repeated!

**Rule violated:** User memory says "S2 is NEVER OPTIONAL" and "Without tipster data → coupons are pure math → NO argumentative reasoning → WORTHLESS"

---

### 2. 🚨 100% H2H BLIND — All 277 Candidates

**Evidence:** Every single gate candidate has `h2h_blind: True`. H2H depth is consistently "SPARSE" (1 meeting) or "BLIND" (0 meetings).

**Impact:** Three-way cross-check (L10 + H2H + L5) is impossible. All picks rely on single-source L10 data only. The 3-way alignment field shows "H2H N/A" for every pick.

**Root cause to investigate:**
- H2H scrapers (flashscore-h2h) only produced 135 records total since session start
- Are H2H queries running for the correct fixture IDs?
- Are esports H2H sources (bo3.gg, vlr.gg) being queried?

---

### 3. 🚨 SYSTEMIC DISCOUNT MASKING — 277/277 Items Forgiven >3 Gate Failures

**Evidence:** Every single item has `systemic_discount.systemic_failures > 3`. The systemic discount mechanism is forgiving 5-7 gate failures per item, inflating gate scores from ~8/20 to 13-15/20.

**Impact:** The gate is NOT functioning as a quality filter. Items that would normally be rejected (score < 12/20) are being rubber-stamped because their failures are "systemic" (shared across all items). This turns the gate into a pass-through.

**Example:** Item with 7 original failures → 6 forgiven as systemic → effective failures = 1 → APPROVED with gate_score 13/20.

**Fix needed:** Review systemic discount logic. If ALL items share the same failures, the gate is meaningless. Should cap systemic forgiveness or raise approval threshold when systemic discount is heavy.

---

### 4. 🚨 COUPONS NOT WRITTEN TO DATABASE

**Evidence:** `coupons` table last entry is from `2026-05-14`. Zero new coupon records for 2026-05-29. The coupon JSON and MD files exist but were never persisted to the DB.

**Impact:** Settlement (S0) cannot find pending picks to settle. PnL tracking is broken. Historical learning queries return stale data. The `settle_log.txt` shows "No pending picks to settle" continuously since May 23.

**Root cause:** `coupon_builder.py` or the DB write step after S8 is broken or was skipped. The agent should have run `persist_coupons_to_db()` or equivalent after building coupons.

---

### 5. 🚨 ESPORTS COMPLETELY ABSENT FROM COUPONS

**Evidence:**
- Shortlist had 64 esports candidates (37 CS2, 22 Dota2, 5 Valorant)
- Gate received 39 esports (25 lost between shortlist and gate — why?)
- Gate APPROVED: 0 esports
- All 39 esports → extended pool with `data_quality: MINIMAL`, `h2h: BLIND`
- Final coupon: zero esports mentions

**Impact:** An entire category of the pipeline's coverage scope is dead. User explicitly wants esports included.

**Root cause:** Esports enrichment produces only MINIMAL data quality. No esports scrapers ran successfully for H2H or deeper stats. Gate threshold requires higher data quality than esports can achieve with current scraper coverage.

---

## MAJOR ISSUES (Fix Tomorrow — Medium Priority)

### 6. ⚠️ 15 APPROVED PICKS WITH HEAVY NEGATIVE EV (< -10%)

**Worst offenders in APPROVED list:**
- Ruud vs Paul: EV = **-60.2%** (!!!)
- Sierra vs Cirstea: EV = **-41.3%**
- Andorra vs Iraq: EV = **-32.2%**
- Teichmann vs Muchova: EV = **-31.9%**
- KFUM Oslo vs Tromsoe: EV = **-24.3%**

**Impact:** These are mathematically losing bets. Placing them guarantees expected loss.

**Rule violated:** Constitution says "Only invalid fixtures, wrong dates, and negative-EV positions may be auto-removed." These should have been flagged or removed.

**Fix needed:** Gate should at minimum FLAG picks with EV < -15% and REJECT picks with EV < -30%.

---

### 7. ⚠️ 12 APPROVED PICKS WITH 3-WAY CONFLICT

**Evidence:** 12 approved picks show "1/2 CONFLICT → DOWNGRADE" in three_way_alignment. L10 and L5 trends DISAGREE on direction.

**Impact:** These picks have internal statistical contradiction — the trend is moving against the pick direction. They should not be in core coupons.

**Fix needed:** 3-way CONFLICT should be a gate rejection criterion, or at minimum force to extended pool only.

---

### 8. ⚠️ 98% MISSING BETCLIC ODDS

**Evidence:** 274 out of 277 items have `betclic: null` in odds. Only the Betclic validation script ran (on 13 events), covering just 4.7% of the shortlist.

**Impact:** Every coupon has estimated odds only (footnote says "Kursy szacunkowe (1/safety_score)"). User cannot verify if picks are even available on Betclic.

**Root cause:** Betclic validation only scanned 13 early-morning events. The rest got no market check. The `curl_cffi` dependency issue from May 28 persists.

---

### 9. ⚠️ ALL CORE COUPONS ARE 5-LEG LOTTERY TICKETS

**Evidence:**
- CP-20260529-MS1: 5 legs, odds 137.94 (P≈2%)
- CP-20260529-HR1: 5 legs, odds 137.12 (P≈1%)
- CP-20260529-HR2: 5 legs, odds 2214.0 (P<0.1%)
- CP-20260529-HR3: 5 legs, odds 5244.0 (P<0.1%)

**Impact:** User memory explicitly says "2-3 leg coupons preferred (AKO5/7 = 0 wins historically)". Four out of seven core coupons have 5 legs — historically 0% win rate.

**Fix needed:** Coupon builder should cap core coupons at 3 legs maximum. 4-5 leg combos go to combo menu only.

---

### 10. ⚠️ NEGATIVE EV LEGS IN CORE COUPONS (12 legs)

**Evidence:** 12 individual legs in core coupons have EV between -10% and -60%.

**Most egregious:**
- HR4 contains legs with EV=-32.2%, EV=-41.3%, EV=-60.2% — the entire coupon is mathematically doomed.

**Fix needed:** No leg with EV < -10% should appear in any core coupon. Move to extended pool or watchlist.

---

## MODERATE ISSUES (Improve When Possible)

### 11. 📊 ESPN ENRICHMENT NEARLY EMPTY

**Evidence:** `espn_enrichment_2026-05-29.json` shows: odds=0, injuries=2, form=0. Only 2 injury records.

**Impact:** No external odds validation, no injury context for 275+ candidates.

---

### 12. 📊 DATA QUALITY DISTRIBUTION ALARMING

**Evidence:**
- FULL: 2 items (0.7%)
- PARTIAL: 135 items (49%)
- MINIMAL: 140 items (51%)

**Impact:** Over half the pipeline operates on MINIMAL data. Only 2 items have what the system considers complete data.

---

### 13. 📊 RISK TIER DISTRIBUTION EXTREME

**Evidence:**
- MS (Moderate Safety): 2 items
- N (Normal): 29 items
- HR (High Risk): 246 items (89%)

**Impact:** Nearly everything is classified as high risk. The tier system provides no discrimination. When 89% is HR, the label is meaningless.

---

### 14. 📊 ZERO REJECTIONS FROM GATE

**Evidence:** `rejected_count: 0` out of 277 candidates.

**Impact:** A gate that rejects nothing is not a gate. Combined with systemic discount (issue #3), the gate_checker.py is effectively disabled.

---

### 15. 📊 25 ESPORTS CANDIDATES LOST BETWEEN SHORTLIST AND GATE

**Evidence:** Shortlist had 64 esports, gate processed only 39. Where did 25 go?

**Possible causes:** Deep stats script couldn't analyze them (missing data), or S3 output didn't include them, or date filter removed them.

---

### 16. 📊 COUPON DATE DISCREPANCY

**Evidence:** The user said "session for tomorrow" (May 30) but all data, kickoff dates, and coupon header says 2026-05-29. The pipeline checkpoint was reset to May 30 at 23:30.

**Clarification needed:** Was this session for today's (May 29) events or tomorrow's (May 30)? If for today, events may have already started by coupon delivery time (10:56). First approved event (Taranaki vs Manawatu) kicked off at 07:30 UTC = 09:30 Warsaw, before gate completed at 08:39.

---

### 17. 📊 LOW SAFETY PICKS APPROVED (22 items with safety < 0.4)

**Evidence:** 22 approved picks have safety_score below 0.4, including:
- Fredrikstad FK corners: safety=0.23, hit=4/7 (57%)
- Sligo Rovers corners: safety=0.23, hit=4/6 (67%)
- Kostyuk games: safety=0.21, hit=3/5 (60%)
- Orgryte vs Elfsborg: safety=0.16, hit=3/4 (75%)

**Impact:** These low-safety picks inflate coupon options without providing reliable edge.

---

## PROCESS DRIFTS (Agent Behavior)

### 18. 🔄 SESSION-STATE.MD NOT UPDATED FOR May 29

**Evidence:** `.kilocode/memory/session-state.md` still references 2026-05-28 session. It was never updated to reflect the May 29 run.

**Impact:** Next session boot will read stale state. Recovery instructions point to wrong date.

---

### 19. 🔄 NO SETTLEMENT ARTIFACT FOR MAY 29

**Evidence:** No `2026-05-29_s0_settlement.md` exists. Settlement shows "No pending picks" (because DB coupons stopped being written on May 14).

**Impact:** PnL tracking completely broken. Cannot learn from historical results.

---

### 20. 🔄 FIXED GATE FILE EXISTS — UNCLEAR WHAT TRIGGERED RE-RUN

**Evidence:** `2026-05-29_s7_gate_results_fixed.json` (10:52) exists alongside original (08:39). Only `safety_score` values changed per item. Same approval counts.

**Possible issue:** The orchestrator ran gate_checker twice, wasting compute. If only safety_score changed, this wasn't a real "fix" — more a recalculation.

---

## SUMMARY TABLE

| # | Severity | Issue | Quick Fix? |
|---|----------|-------|------------|
| 1 | CRITICAL | Zero tipster data | Fix S2 runner / web fallback |
| 2 | CRITICAL | 100% H2H blind | Fix H2H scraper coverage |
| 3 | CRITICAL | Systemic discount bypasses gate | Cap discount or raise threshold |
| 4 | CRITICAL | DB coupon write broken since May 14 | Fix persist_coupons_to_db |
| 5 | CRITICAL | Esports completely dropped | Fix esports enrichment pipeline |
| 6 | MAJOR | 15 picks with EV < -10% approved | Auto-reject EV < -30% |
| 7 | MAJOR | 12 picks with 3-way CONFLICT approved | Reject or force to extended |
| 8 | MAJOR | 98% missing Betclic odds | Fix curl_cffi / market scanner |
| 9 | MAJOR | Core coupons are 5-leg lottery | Cap core at 3 legs |
| 10 | MAJOR | Negative EV legs in core | EV floor for coupon legs |
| 11 | MODERATE | ESPN enrichment empty | Debug ESPN scraper |
| 12 | MODERATE | 51% MINIMAL data quality | Improve scraper coverage |
| 13 | MODERATE | 89% classified HR | Recalibrate risk tiers |
| 14 | MODERATE | Zero gate rejections | Gate threshold review |
| 15 | MODERATE | 25 esports lost shortlist→gate | Debug S3 esports path |
| 16 | MODERATE | Date confusion (today vs tomorrow) | Verify betting day targeting |
| 17 | MODERATE | 22 picks with safety < 0.4 | Consider minimum safety threshold |
| 18 | PROCESS | Session state not updated | Add write_session_state call |
| 19 | PROCESS | No settlement artifact | Fix DB write → settlement flow |
| 20 | PROCESS | Unclear gate re-run | Document why _fixed exists |

---

## RECOMMENDED FIX ORDER (Today — May 30)

### P0 — UNBLOCK TODAY'S SESSION (do FIRST before any pipeline run):

1. **Increase output tokens** — `--max-tokens 65536` in `config/com.rapid-mlx.server.plist` + `kilo.jsonc` `"output": 65536`. This prevents the reasoning death spiral from consuming all output capacity.
2. **Populate May 30 fixtures** — Run `discover_events.py` manually. The DB has ZERO events for today.
3. **Clean fixtures table** — Delete/fix 1,714 time-only kickoff rows, 111 empty kickoff rows.
4. **Expire stale scheduled fixtures** — `UPDATE fixtures SET status='expired' WHERE kickoff < '2026-05-30' AND status IN ('scheduled','NS','Not started','Not Started','pending')`.

### P1 — FIX CORE PIPELINE BUGS:

5. **Fix DB coupon persistence** (#4) — unblocks settlement, PnL, learning (broken since May 14!)
6. **Fix S2 tipster pipeline** (#1) — unblocks source fusion core value
7. **Normalize status field** — Map 60+ status values to: `{scheduled, live, completed, cancelled, postponed, expired}`. Create a migration script.
8. **Cap systemic discount in gate** (#3) — restores gate as quality filter

### P2 — QUALITY IMPROVEMENTS:

9. **Add EV floor for approval** (#6, #10) — prevents mathematically losing bets
10. **Fix esports enrichment** (#5, #15) — restores full sport coverage
11. **Cap core coupons at 3 legs** (#9) — aligns with historical win patterns
12. **Reject 3-way CONFLICT from approval** (#7) — prevents contradictory picks
13. **Fix Betclic market scanner** (#8) — enables odds verification
14. **Fix H2H scraper coverage** (#2) — enables three-way cross-check

---

## FIXTURES TABLE STATUS CLEANUP — Reference

Current state (60+ values, 39,759 total rows):
```
TERMINAL (should map to 'completed'):
  Ended=3932, FT=799, STATUS_FINAL=236, Finished=76, AET=29, finished=4, 
  AP=12, PEN=25, AOT=4, AWD=8, Awarded=1, BT=1, FINISHED=1

LIVE (should map to 'live' — frozen in-game states, now STALE):
  1H=148, 2H=92, HT=25, 1st set=146, 2nd set=183, 3rd set=55, 
  1st half=1, 2nd half=17, Halftime=5, live=66, Q1-Q4=21, P1-P2=3,
  Inning 1-9=24, Set 2-4=6, Second Half=1, OT=1, PAUSED=2, TIMED=1

NOT STARTED (should be 'scheduled' or 'expired' if past):
  scheduled=12598, NS=8208, Not started=5755, Not Started=556, pending=6275

CANCELLED:
  Canceled=118, CANC=15, Cancelled=3, Canc=1

SPECIAL:
  Walkover=52, Retired=66, STATUS_RETIRED=1, Postponed=39, PST=78, 
  POST=6, Interrupted=38, SUSP=4, Suspended=2, ABD=1
```

Target schema: `{scheduled, live, completed, cancelled, postponed, walkover, retired, expired}`
