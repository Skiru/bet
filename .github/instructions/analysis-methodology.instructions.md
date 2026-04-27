---
applyTo: "betting/**/*"
---

# Analysis Methodology — Daily Protocol (Compact)

## ULTIMATE RULE: BET STATISTICS, NOT OUTCOMES

We bet on **statistical markets** (corners, fouls, shots, games, sets, points, frames, rounds) — NOT on who wins. Statistical markets accumulate throughout the match, are driven by team/player STYLE (structural), survive in-match chaos, and are systematically mispriced by bookmakers. Outcome markets (ML, winner, goals) depend on finishing luck and single moments. **Every pick must be a statistical market unless no statistical market exists for that event.**

Goal: find MISPRICED ODDS in statistical markets. EV > 0 is the only valid reason to bet.

> **Sport-specific protocols** (stats tables, upset checklists, red flags) are in [sport-analysis-protocols.instructions.md](sport-analysis-protocols.instructions.md). Load that file when performing STEP 3+ analysis.

---

## SPORT TIERS

| Tier | Sports | Scanning | Analysis |
|------|--------|----------|----------|
| **KEY (Tier 1)** | Football, Volleyball, Basketball, Tennis | ALL leagues/divisions/tournaments — not just top leagues. Go deep: 2nd/3rd divisions, cups, youth internationals, women's leagues, regional tournaments. Every sub-page. | Full STEPS 3-7 per candidate. |
| **SUPPORT (Tier 2)** | Hockey, Baseball, Esports, Snooker, Darts, Table Tennis, Handball, MMA, Padel, Speedway | Top leagues + major tournaments. Don't drill into every sub-division but cover main events. | Full STEPS 3-7 per candidate. Same quality, fewer leagues scanned. |

**KEY sport league depth (CRITICAL):** For Football, Volleyball, Basketball, Tennis — scan beyond the obvious. Examples:
- Football: not just EPL/LaLiga/Bundesliga but also Ekstraklasa, 2. Bundesliga, Serie B, Ligue 2, Eredivisie, Belgian Pro League, Turkish Super Lig, MLS, Liga MX, K-League, J-League, women's leagues, youth tournaments.
- Volleyball: PlusLiga, SuperLega, Ligue A, women's leagues, CEV Champions League, national cups.
- Basketball: not just NBA/Euroleague but also NBP (Poland), ACB, BSL, LNB, BCL, women's leagues.
- Tennis: all ATP/WTA draws at every level (250/500/1000/GS), Challengers (but NOT ITF).

---

## SCANNING MANDATE (NEVER VIOLATE)

1. **WIDE:** ALL 14 sports every run. KEY sports get league-depth priority. Never say "no events" without exhausting the FULL fallback chain (see source-registry.md) + a Google search.
2. **DEEP:** Enter EVERY tournament/league for KEY sports. For SUPPORT sports, cover main tournaments. Landing pages hide 80%. Count matches. Cross-validate counts between ≥2 sources (>20% discrepancy = missed events).
3. **MULTI-LEVEL:** Per candidate: Tier A stats → Tier A markets → Tier B tipsters (read REASONING) → specialist sources → context.
4. **AGGRESSIVELY:** Source fails? Log the error, try next in chain immediately. All chain sources fail? Google `"[sport] matches today site:flashscore.com OR site:sofascore.com"` or `"[tournament] schedule [date]"`. After finishing other sports, RETRY failed sources (rate limits often clear in 15-30 min). **Never declare a sport empty without trying ≥3 independent sources + 1 Google search.**
5. **COMPARE:** Every data point needs ≥2 independent confirmations.
6. **RETRY LOOP:** After the first scan pass, review `scan_errors.json` and ALL failed sources. Retry each failed source ONCE. If it works now, add its events. Log final status.

**Minimums:** ≥50 events scanned, ≥80% scan completeness, 15-40 shortlist across ≥8 sports, final picks from ≥5 sports, core coupons scale with picks (target ≥5 when 10+ approved) + ≥4 combo coupons. KEY sports ≥60% of shortlist.

**SESSION PARITY:** Session type (full/day/night) controls ONLY the event time window. Analysis depth, coupon count, all steps, all validation = IDENTICAL regardless of session.

---

## STEP 0: SETTLE PREVIOUS DAY + LEARN FROM HISTORY

1. Run `python3 scripts/settle_on_finish.py --betting-day YYYY-MM-DD`.
2. Auto-resolves: winner/1X2, totals, BTTS, DC. Manual: corners, cards, HC, MyCombi.
3. Update `picks-ledger.csv` (status, pnl), `coupons-ledger.csv` (status, pnl).
4. Calculate: day PnL, rolling 7-day PnL, per-market hit rates, per-league ROI.
5. **Post-mortem each LOSS:** bad thesis or variance? Record in learning log.
6. **CLV:** Record closing odds. `CLV = (closing_implied / placement_implied) - 1`. Track weekly avg.
7. Update `working_bankroll_pln` in config. If −20% from peak → reduce daily cap 25%.

### §0.2 HISTORICAL LEARNING QUERY (MANDATORY before scanning)
Before STEP 1, query the picks-ledger to extract actionable patterns. This takes 2 minutes and prevents repeating proven failures.

1. **Per-market hit rate:** Group settled picks by `market` column. Calculate win% per market type (e.g., corners: 75%, ML: 40%, BTTS: 55%). Any market <40% on 10+ picks → AUTO-DOWNGRADE (STEP 5 rule). Any market <30% → WATCHLIST ONLY.
2. **Per-sport hit rate:** Group by `sport`. Any sport with <30% hit rate on 5+ picks → FLAG. Scan that sport but apply −1 confidence to all picks from it. **NEVER blanket-reject an entire sport.** <5 settled picks = insufficient sample for any sport-level action. Each candidate is analyzed individually through STEP 3-7 regardless of sport-level hit rate.
3. **Coupon failure analysis:** For each LOST coupon, identify the leg that failed. Track which pick types are the "coupon killers." If a specific market/sport kills coupons >50% of the time → exclude from LR coupons.
4. **Streak check:** Any team/player appearing 3+ times in recent picks? Check if the thesis is stale or if the edge has been priced in.
5. **Write a 3-line summary** of what the data says today. Example: "Corners 6/8 (75%). Tennis ML 1/5 (20%) — avoid. Hockey totals killing coupons — HR only."

---

## STEP 1: SCAN — Complete Event Discovery

1. Run `bash scripts/run_full_scan_and_prepare.sh`. Check `scan_errors.json`.
2. Run `python3 scripts/fetch_odds_api.py` for cross-validation (30 credits/scan, 500/month free).
3. Browse BetExplorer + Flashscore + OddsPortal for ALL 14 sports.
4. **Deep Scan (§1.2):** Click into EVERY active tournament/league. Count matches per tournament.
5. **Tournament depth (§1.3):** Major tournament active? Analyze FULL daily slate (all matches, not 1-2). ANY tournament with ≥4 matches → screen ALL.
6. **Cross-validate:** Compare event counts per sport between ≥2 sources. Discrepancy >20% → investigate.
7. Record per event: sport, competition, event, kickoff, initial odds, source.

**14-SPORT CHECKLIST (mandatory — check each):**
- **KEY (deep league scan):** Football, Tennis, Basketball, Volleyball.
- **SUPPORT (main leagues):** Hockey, Baseball, Esports, Snooker, Darts, Table Tennis, Handball, MMA, Padel, Speedway.

### §1.5 TIPSTER PRE-FETCH (MANDATORY — runs as part of STEP 1)

Before STEP 2 filtering, fetch TODAY's pages from ALL argument-based tipster sites using Playwright. This ensures tipster arguments are available for STEP 4 analysis.

**Execution:**
```bash
# Fetch today's tipster pages (zawodtyper uses daily URL pattern)
python3 scripts/fetch_with_playwright.py "https://zawodtyper.pl/typy-dnia-[DD]-[month-polish]-[weekday-polish]/"
python3 scripts/fetch_with_playwright.py "https://typersi.pl/"
python3 scripts/fetch_with_playwright.py "https://www.sportsgambler.com/predictions/today/"
python3 scripts/fetch_with_playwright.py "https://www.pickswise.com/tennis/"
python3 scripts/fetch_with_playwright.py "https://www.betideas.com/tips/football"
```

**Zawodtyper daily URL pattern:** `/typy-dnia-[DD]-[month]-[weekday]/` where month and weekday are in Polish lowercase (e.g., `kwietnia`, `poniedzialek`). The page is lazy-loaded — Playwright handles this.

**Parse the fetched HTML** to extract ALL tipster entries: sport, event, tipster name, pick, odds, and FULL WRITTEN ARGUMENT. Save structured output to `betting/data/{date}_s1_tipster_prefetch.md`.

**Tipster-sourced candidates:** Any tipster pick that targets a **statistical market** (corners, cards, fouls, totals, games, frames) with argument-backed data (H2H stats, corner counts, historical lines) → add to shortlist even if not found in Tier A stats scan. These picks enter STEP 3+ analysis like any other candidate.

**GATE:** If zawodtyper fetch fails → retry once after 5 min. If still fails → proceed but mark S4 as `TIPSTER-DEGRADED`. Never skip the fetch attempt.

**Source fallback chains per sport:** See [source-registry.md](../../betting/sources/source-registry.md).

**Scan Completeness Gate (§1.6):** Before STEP 2, compile per-sport event count table from ≥2 sources. Total ≥50 events, ≥6 sports with events, completeness ≥80%. If not met → go back.

---

## STEP 2: FILTER — Shortlist

Remove: outside betting window, no Tier A coverage, <2h to kickoff, already started, exhibitions.
Prioritize: events WITH statistical markets (corners, totals, HC) over basic ML-only.
**Early Betclic market hint:** For niche sports (volleyball, table tennis, padel, speedway), check Betclic market availability BEFORE deep analysis. If market doesn't exist on Betclic → don't waste analysis time.
Preferred odds range: 1.30-3.50.
**Target: 15-40 events across ≥8 sports in shortlist (≥5 sports minimum in final picks).** KEY sports (Football+Volleyball+Basketball+Tennis) should be ≥60% of shortlist but no single sport >40%.

---

## STEP 3: STATS — Deep Analysis (per candidate)

> Load [sport-analysis-protocols.instructions.md](sport-analysis-protocols.instructions.md) for sport-specific stat tables and market decision protocols.

**Universal requirements for EVERY candidate:**
1. **H2H MANDATORY:** Last 5-10 meetings, home/away splits. H2H surprises override league position.
2. **Collect ALL stats** from sport-specific table (not some — ALL). Split by home/away.
3. **Calculate hit rates** for O/U lines.
4. **Run §3.0 STATISTICAL MARKET RANKING** (below). Rank ALL available stat markets by safety score. Choose SAFEST, not most interesting.
5. **Present TOP 2-3 markets** per match from §3.0 ranking table BEFORE choosing.
6. **NEVER default to ML/1X2.** Statistical markets ALWAYS preferred across ALL 14 sports.
7. ML only when: (1) no statistical market on Betclic AND (2) statistical edge overwhelming AND (3) price acceptable.
8. **COACH/ROSTER STABILITY CHECK (mandatory):** For EVERY candidate: Did the coach change in the last 5 matches? Any major transfers, loan returns, or squad changes in the last 14 days? New coach bounce = volatile form (first 5 games unreliable). Major roster change = stats from previous games may not apply.

### §3.0 STATISTICAL MARKET RANKING PROTOCOL (MANDATORY — NEVER SKIP)

**For EVERY candidate, BEFORE selecting a market:**

1. **List ALL bettable statistical markets** for that sport (see §3.0b table below).
2. **For EACH available market**, collect: (a) team/player L10 average, (b) H2H average for that SPECIFIC stat (last 5 meetings minimum), (c) recent form L5 average, (d) bookmaker line, (e) hit rate (how often L10 + H2H covered that line).
3. **Calculate SAFETY SCORE** per market: `safety = min(hit_rate_L10, hit_rate_H2H)`. Higher = safer. Use avg margin vs line as tiebreaker (Over: avg/line, Under: line/avg — bigger = more margin).
4. **Rank all markets** by safety score. Pick the TOP market — not your default/favorite.
5. **CONFLICT CHECK:** If H2H avg and L10 avg disagree by >20% on the same stat → FLAG. Weight recent form (L5) as tiebreaker. If L5 also conflicts with H2H → DOWNGRADE or SKIP.
6. **PRESENT the ranking table** in the analysis. Show WHY the chosen market beat alternatives.

**This means:** Football picks are NOT always corners. They could be fouls, cards, shots, throw-ins — whichever stat has the best safety score for THAT specific match. Tennis is NOT always O22.5 games — it could be U21.5, O/U sets, or game handicap. Basketball is NOT always total points — it could be team totals, quarter totals, or rebounds.

### §3.0b BETTABLE STATISTICAL MARKETS BY SPORT

| Sport | Statistical Markets (ranked by typical reliability) |
|-------|-----------------------------------------------------|
| **Football** | Fouls O/U, Cards O/U, Corners team O/U, Corners total O/U, Shots O/U, Shots on target O/U, Throw-ins O/U, Goal kicks O/U, Offsides O/U, Team goals O/U, Total goals O/U, BTTS |
| **Tennis** | Total games O/U, Sets O/U, Game handicap, Set handicap, Tiebreaks O/U, Aces O/U, Double faults O/U |
| **Basketball** | Team points O/U, Quarter totals, Half totals, Total points O/U, Rebounds O/U, Assists O/U, 3-pointers O/U, Spread |
| **Volleyball** | Total sets O/U, Total points O/U, Set handicap, Points per set O/U |
| **Hockey** | Period totals O/U, Total goals O/U, Shots O/U, Power play goals O/U, Puck line |
| **Baseball** | F5 innings total O/U, Team totals, Total runs O/U, Hits O/U, Strikeouts O/U, Run line |
| **Snooker** | Frame totals O/U, Century breaks O/U, 50+ breaks O/U, Frame handicap |
| **Darts** | 180s O/U, Total legs O/U, Set totals, Checkout % props |
| **Handball** | Half totals O/U, Total goals O/U, Team goals O/U, Suspensions O/U |
| **Esports** | Round totals O/U, Map totals O/U, Kill totals, Map handicap |
| **Table Tennis** | Set totals O/U, Total points O/U, Set handicap |
| **MMA** | Total rounds O/U, Method of victory, ITD Y/N |
| **Padel** | Game totals O/U, Set totals O/U, Set handicap |
| **Speedway** | Total points O/U, Team handicap |

### §3.0c H2H MARKET-SPECIFIC VALIDATION (MANDATORY — NEVER SKIP)

**For EVERY selected market, you MUST have H2H data for THAT SPECIFIC STAT:**

- Picking corners? → Get H2H corner totals between these exact teams (last 3-5 meetings).
- Picking total games in tennis? → Get H2H game totals between these exact players (last 3-5 meetings, surface-filtered).
- Picking total points in basketball? → Get H2H combined scoring (last 3-5 meetings at this venue).
- Picking frame totals in snooker? → Get H2H frame counts (last 3-5 meetings).

**If H2H data for the SPECIFIC stat is unavailable:**
1. Mark pick as `H2H-STAT-BLIND` in the analysis.
2. Apply −0.5 confidence penalty.
3. The pick CANNOT be in a LR coupon.
4. Increase weight on L5 recent form as substitute.

**THREE-WAY CROSS-CHECK (mandatory for every pick):**
```
L10 AVERAGE → [value] → hit rate vs line: [X/10]
H2H AVERAGE → [value] → hit rate vs line: [X/5]
L5 RECENT  → [value] → trend: [UP/DOWN/STABLE]
ALL THREE must support the pick direction. 2/3 conflict → DOWNGRADE. 3/3 conflict → REJECT.
```

---

## STEP 3B: TIME-SENSITIVE DATA (run 2-3h before earliest event)

1. **Lineups:** Flashscore (~1h), SportoweFakty for speedway (~2-3h), DailyFaceoff for NHL goalies.
2. **Late injuries:** ESPN, team social media, ATP/WTA Order of Play.
3. **Weather:** Outdoor sports — rain/wind impacts.
4. **Odds movement:** Compare current vs analysis-time. If Betclic moved >10% → recalculate EV.
5. **If ANY finding contradicts thesis → re-evaluate. Downgrade or void if bear case strengthens.**

---

## STEP 4: TIPSTER DEEP-DIVE (per candidate)

Check ≥2 ARGUMENT-BASED tipster sites per candidate. Read WRITTEN REASONING, not bare picks.

**Sites:** ZawodTyper (PL), Typersi (PL), Meczyki (PL), OLBG (EN), PicksWise (EN), BetIdeas (EN), Sportsgambler (EN), Tipstrr (EN, verified ROI), GosuGamers (esports).

**Sport-specific tipster fallback chains (try in order until ≥2 sources found):**

| Sport | Primary | Secondary | Tertiary |
|-------|---------|-----------|----------|
| Football (PL) | ZawodTyper → Meczyki | Typersi → OLBG | Sportsgambler |
| Football (INT) | PicksWise → BetIdeas | OLBG → Sportsgambler | Typersi |
| Football (US/MX) | PicksWise | Sportsgambler | OLBG |
| Tennis | ZawodTyper → OLBG | Sportsgambler → PicksWise | Typersi |
| Basketball (EU) | Sportsgambler | ZawodTyper | Typersi |
| Basketball (US) | PicksWise | Sportsgambler | OLBG |
| Volleyball | ZawodTyper → Typersi | Sportsgambler | Meczyki |
| Hockey | PicksWise | Sportsgambler | OLBG |
| Baseball | PicksWise | Sportsgambler | OLBG |
| Handball | Sportsgambler | ZawodTyper | OLBG |
| Snooker | Sportsgambler → OLBG | Tipstrr | — |
| Darts | Sportsgambler → OLBG | Tipstrr | — |
| Esports | GosuGamers | Tipstrr | BO3.gg |
| Table Tennis | Sportsgambler | OLBG | Tipstrr |
| MMA | Sportsgambler | PicksWise | Tipstrr |
| Padel | Google "[event] prediction" | Sportsgambler | — |
| Speedway | ZawodTyper | Typersi | Google "[event] tips" |

**Extract per tipster:** site, tipster name, specific pick, odds, reasoning summary (1-2 sentences with stats/facts cited).

**Consensus:** ≥70% agreement → +0.5 confidence. ≥60% contradiction → investigate, −1 or skip. Strong fact-based argument from 1 tipster against your thesis → investigate before finalizing.

### §4.2 STEP 4 COMPLETENESS GATE (MANDATORY)
Before proceeding to STEP 5, verify:
- [ ] Every shortlisted candidate has ≥1 tipster source with extracted reasoning.
- [ ] ≥80% of candidates have ≥2 tipster sources.
- [ ] If a candidate has 0 tipster sources after exhausting the fallback chain → mark as `TIPSTER-BLIND` in report. Still allowed but gets −0.5 confidence and CANNOT be in LR coupons.
- [ ] Record per-candidate tipster coverage in a summary table: `| Event | Sources checked | Sources with reasoning | Consensus |`
- [ ] §1.5 tipster pre-fetch HTML was used (not just web-fetch summaries).
- [ ] ALL tipster picks on statistical markets (corners, cards, games, frames, etc.) with argument-backed reasoning have been cross-referenced with shortlist.

**If <60% of candidates have ≥1 tipster source → STOP and fetch more before STEP 5.**

### §4.3 TIPSTER-SOURCED WATCHLIST PROMOTION (MANDATORY)

After STEP 4 analysis, review ALL tipster picks from the §1.5 pre-fetch that were NOT in the original shortlist. For each tipster pick that meets ALL of:
1. Targets a **statistical market** (corners, cards, fouls, totals, games, sets, frames — NOT ML/winner)
2. Has **argument-backed reasoning** with cited stats (H2H corner counts, historical line coverage, motivation context)
3. Tipster has **>55% tracked accuracy** on the site (or is a verified tipster on Tipstrr)
4. The event is within today's betting window
5. The event is available on Betclic (or likely to be)

→ **Add to LISTA OBSERWACYJNA (Watchlist)** with:
- Full tipster argument (translated to Polish if needed)
- Tipster name and accuracy % from the site
- The specific statistical data they cited
- Promotion criteria: "Wstaw jeśli: kurs Betclic ≥X.XX + potwierdzone przez ≥1 dodatkowe źródło statystyczne"

These are NOT auto-approved picks — they enter the watchlist with rich context so the user can evaluate and promote them manually.

**Blocked tipster sites:** Forebet, FootySupertips, Windrawwin, BettingExpert, Protipster, Oddspedia, SportyTrader, Predictz, Trafiamy, Blogabet, HLTV tips.

---

## STEP 5: ODDS + EV (per candidate)

1. **Market-best:** BetExplorer/OddsPortal. Cross-validate with The-Odds-API.
2. **True probability:** Pinnacle implied (strip margin) > statistical model > market consensus.
3. **EV = (true_prob × betclic_odds) − 1.** Must be > 0.
4. **Price gap:** `100 × ((betclic_odds / market_best) − 1)`. LR reject < −3%, HR reject < −5%.
5. **Line movement:** Steam moves (follow if aligned), RLM (follow sharp money).
6. **§5.5a DRIFT GATE:** If odds moved >8% from analysis → MANDATORY re-eval. No explanation → SKIP.
7. **Kelly (1/4):** `stake = (bankroll × f) / 4` where `f = (b×p − q) / b`. If f ≤ 0 → NO BET.
8. **MARKET PERFORMANCE TRACKER:** Before picking any market, check hit rate in picks-ledger. If <40% on 10+ picks → AUTO-DOWNGRADE confidence −1. If <30% → WATCHLIST ONLY.

**Learned caution zones:** MLB totals 33% hit rate → all MLB totals get −1 confidence until >50%. MLB overs ≥8.5 → HARD REJECT.

---

## STEP 6: CONTEXT (per candidate)

- [ ] Fixture confirmed (not postponed)?
- [ ] Key absences (injuries, suspensions, rest)? — check ESPN, Flashscore, team social media.
- [ ] **Coach change in last 5 matches?** New coach = form data unreliable. Check Flashscore coach section.
- [ ] **Roster changes in last 14 days?** Transfers, loans, returns. Major signings disrupt chemistry.
- [ ] Competition context (relegation, dead rubber, cup final)?
- [ ] Fixture congestion (<72h between games)?
- [ ] Weather (outdoor sports)?
- [ ] Referee (cards/fouls markets)? — specific referee stats, not just "checked."

### §6.5 UPSET RISK ASSESSMENT (MANDATORY)

> Load [sport-analysis-protocols.instructions.md](sport-analysis-protocols.instructions.md) §6.5 for sport-specific checklists and thresholds.

Score EVERY candidate. Record: `UPSET: [X/Y] — [top 3 factors]`.
If score ≥ threshold → **ML BANNED**, statistical markets only.
**Paradox Rule:** High upset → OVER totals premium (competitive = more play). Low upset → OVERS dangerous (blowout).

---

## STEP 7: BEAR CASE + RED FLAGS + CONTRARIAN + GATE (per candidate)

### 7.1 Bear Case Template
```
PICK: [selection]
UPSET SCORE: [X/Y] — [top 3 factors]
BULL CASE: [1-2 sentences]
BEAR CASE: [1-2 sentences]
STREAK DEPENDENCY: [Y/N — if >5 games, reduce −1]
REGRESSION RISK: [xG mismatch? Overperformance?]
KEY FAILURE SCENARIO: [most likely way this fails]
20%-LOWER-ODDS TEST: [Y/N — if N, coupon leg only]
```

### §7.3 Instant Red Flags (30 seconds each)
> Load [sport-analysis-protocols.instructions.md](sport-analysis-protocols.instructions.md) §7.3. Run ALL sport-specific red flags. Any fired → REJECT, downgrade, or justify.

### §7.4 Contrarian Thinking (4 questions, EVERY pick)
1. Am I applying the right MODEL to this SPECIFIC case?
2. What's the #1 way this bet type LOSES?
3. Would I take it FRESH at CURRENT odds? (defeat anchoring)
4. What would a sharp disagree-er say?

### §7.5 PICK APPROVAL GATE (17 points, EVERY pick)
```
[ ] 1. Identity verified (full name, no slashes)
[ ] 2. WC/Q/LL / debut / stand-in / backup checked
[ ] 3. H2H ≥5 meetings checked (surface/venue splits)
[ ] 4. Injuries/suspensions/load management checked
[ ] 5. ≥2 independent sources (1 stats + 1 market)
[ ] 6. ≥1 tipster argument READ (reasoning extracted, site+name+pick logged). If 0 → TIPSTER-BLIND, −0.5 confidence, NO LR coupon.
[ ] 7. Upset risk scored (§6.5 checklist)
[ ] 8. EV > 0 calculated
[ ] 9. Odds drift <8% verified (or re-evaluated)
[ ] 10. Red flags checked (§7.3)
[ ] 11. Contrarian thinking done (§7.4)
[ ] 12. Bear case < bull case
[ ] 13. Not anchored (would take at current odds)
[ ] 14. 48h repeat check (same team+market lost → HARD REJECT)
[ ] 15. MULTI-MARKET COMPARISON: ≥3 alternative stat markets calculated for this match (§3.0). Best safety score selected.
[ ] 16. H2H STAT-SPECIFIC: H2H data for the EXACT stat being bet exists (§3.0c). If missing → H2H-STAT-BLIND, −0.5 confidence, no LR coupon.
[ ] 17. THREE-WAY ALIGNMENT: L10 avg + H2H avg + L5 recent all support pick direction. 2/3 conflict → DOWNGRADE. 3/3 conflict → REJECT.
ALL 17 PASS → APPROVED | ANY FAIL → REJECT/DOWNGRADE/WATCHLIST
```

---

## STEP 8: COUPONS + COMBINATION MENU

### §8.1 CORE PORTFOLIO (primary deliverable)

1. Rank approved picks: EV (highest) → confidence → price_gap.
2. **NO SINGLES.** Every pick in a coupon. Min 2 legs per coupon.
3. **UNIQUE EVENT PER COUPON (ABSOLUTE).** Each pick in ONLY ONE core coupon. Zero sharing.
4. **Coupon count = f(quality, NOT money).** Target ≥5 core coupons (requires ≥10 approved picks). Scale: 4-5 picks → 2 core, 6-7 → 3 core, 8-9 → 4 core, 10+ → 5+ core. <4 approved picks → NO BET.
5. Build diverse coupons: vary sports, markets, risk levels.
6. **Risk tier labels:** LOW-RISK, MULTI-SPORT, HIGHER-RISK, NIGHT. Target distribution: ≥2 LR, ≥1 MS, ≥1 HR (scale up with approved picks).
7. **Correlation check:** Same match = FORBIDDEN. Same league ≥2 = FLAG. Same narrative = REMOVE weaker.
8. Suggest stakes for ALL coupons. Total may exceed daily cap — user decides.
9. **Watchlist:** 2-3 backup picks with promotion criteria ("Promote if Betclic ≥ X.XX").

### §8.1b COMBINATION MENU (additional — user picks favorites)

After building the core portfolio, generate **additional combination coupons** that remix approved picks into new groupings. These are EXTRA options on top of the core list.

1. **Reuse allowed:** Picks from the core portfolio MAY be recombined into new coupons here. Same pick can appear in multiple menu combos.
2. **Target: 4-8 extra combos** across risk tiers (at least 2 LR, 1 MS, 1 HR).
3. **Each combo must have a distinct thesis** — don't just shuffle the same legs. Vary the angle: "all-corners combo", "safe-totals combo", "high-EV longshot", "3-sport diversifier", etc.
4. **Label clearly:** Prefix with "COMBO-" (e.g., COMBO-LR1, COMBO-MS1, COMBO-HR1) so user can distinguish core vs. menu coupons.
5. **Same rules apply:** min 2 legs, max same-sport 2, correlation check, combined odds arithmetic.
6. **User picks from the full list** (core + combos). Total suggested stakes WILL exceed daily cap — that's the point.

### §8.2 COUPON STRESS TEST (MANDATORY per coupon)
For EACH coupon, before finalizing:
1. **Probability estimate:** Multiply estimated true probabilities of all legs. P(coupon) = P(leg1) × P(leg2) × ... Example: 0.60 × 0.55 × 0.58 = 19.1%. If P(coupon) < 10% → HR only. If < 5% → consider dropping a leg or splitting.
2. **Weakest-leg identification:** Which leg has the lowest P(win)? Can it be swapped for a better pick from the approved pool WITHOUT creating correlation? If yes → SWAP.
3. **Catastrophe scenario:** Write ONE sentence: "This coupon fails if [specific scenario]." Example: "Fails if Madrid rains and corners drop below 8."
4. **Betclic market existence check:** Before building a coupon around a pick, verify the market EXISTS on Betclic. If the market doesn't exist (e.g., O20.5 games not offered, only O17.5) → drop or adjust the line.

**Coupon limits:** LR max 3.00 PLN, HR max 2.00 PLN. Max same-sport legs: 2 per coupon.

---

## STEP 9: VALIDATE V1-V10

### V1: Artifact Consistency
- pick_ids in coupon file exist in picks-ledger
- coupon_ids exist in coupons-ledger
- Stakes sum = total exposure. No duplicate IDs. UNIQUE EVENT PER COUPON in core portfolio. Combo coupons may reuse picks.

### V2: Per-Pick Sources
- Tier A stats source with specific data point?
- Tier A market source with specific odds?
- EV > 0 calculated? Confidence 1-5 justified?

### V3: Tennis
- Market hierarchy respected (games > sets > HC > ML)?
- Odds ratio ≤1.50, correct grade (STRONG/GOOD/BORDERLINE/REJECT)?
- Player identity verified? WC/Q/LL checked? Drift <8%?

### V4: Football
- Market hierarchy respected? Corner 3-source stack? BTTS >55%?

### V4b-V4k: Sport-specific checks
- V4b Volleyball: set totals checked, ML range 1.30-2.00, set handicap considered.
- V4c Esports: map pool checked, BO format noted, roster/stand-in confirmed.
- V4d Snooker: frame stats from CueTracker, format (BO) noted.
- V4e Darts: 3-dart avg, format (sets vs legs) noted.
- V4f Handball: home advantage factored (60-65%), half totals checked.
- V4g Table Tennis: ranking gap assessed, high variance noted.
- V4h MMA: finish rates checked, method of victory considered.
- V4i Padel: FIP ranking gap checked, partnership duration noted, indoor/outdoor surface.
- V4j Speedway: rider TRACK-SPECIFIC averages used (not season avg), lineup confirmed.
- V4k: Upset risk scored for EVERY candidate. ML bans enforced. Paradox Rule applied.

### V5: Coupon Structure
- Min 2 legs. Same-sport ≤2. No same-match.
- **Combined odds ARITHMETIC:** Multiply legs explicitly. Write product. Tolerance ±2%.
- Core portfolio: UNIQUE EVENT PER COUPON. Combo menu: reuse allowed.
- Core coupons scale with approved picks (2-5+). ≥4 combo coupons. Distribute across risk tiers.

### V6: Portfolio + Menu Completeness
- Core portfolio covers all approved picks (no orphans).
- Combo menu has ≥4 extra coupons with distinct theses (not reshuffled core legs).
- Multi-sport diversification within coupons. No tournament concentration.
- Total suggested stakes (core + combos) exceed daily cap — user picks.

### V7: Weaknesses
- List BORDERLINE picks, CONDITIONAL picks, weakest leg per coupon.
- V7b: Date & fixture verified for EVERY event.
- V7c: Cross-coupon integrity — core portfolio: no event in >1 coupon. Combo menu: reuse OK but no correlated narratives within single combo.

### V8: Source Completeness
- Every pick: ≥2 independent sources + ≥1 argument-based tipster.
- Sport-specific sources checked (football corners: TotalCorner+SoccerStats, tennis: TennisAbstract, MLB: BaseballSavant, esports: Liquipedia/GosuGamers, snooker: CueTracker).
- H2H, injuries verified for EVERY pick.
- **V8b: H2H STAT-SPECIFIC CHECK:** For EVERY pick, H2H data for the SPECIFIC stat market exists (not just match results). If H2H-STAT-BLIND → pick is flagged, −0.5 confidence, excluded from LR coupons.
- **V8c: STATISTICAL MARKET RANKING AUDIT:** For EVERY pick, §3.0 ranking table was produced showing ≥3 alternative markets considered. If no ranking table → FAIL.

### V9: Coupon Optimization
- Picks ranked by EV×confidence. No orphan picks. No ≥3 same-market-type in coupon.
- Night coupons = night games only. Weakest-leg swap test per coupon.
- Combined odds sweet spots: 2-leg 2-4, 3-leg 4-10, 4-leg 8-20.

### V10: Final Sign-Off

**V10a: Forced Sport Enumeration** — ALL 14 sports listed with events/sources/candidates/picks. KEY sports (Football, Volleyball, Basketball, Tennis): 0 events + <3 sources → go back. SUPPORT sports: 0 events + <2 sources → go back.

**V10b: Pick Approval Gates** — every pick passed 17-point gate (§7.5).

**V10c: Red Flags** — every pick had §7.3 checked. All fired flags addressed.

**V10d: Portfolio Damage** — if most-concentrated pick loses, ≥3 coupons survive.

**V10e: PER-PICK COMPLETENESS MATRIX (MANDATORY)**
```
| Pick ID | Tipster≥1 | H2H≥5 | H2H-Stat | StatRank | 3WayChk | Injuries | Sources≥2 | RedFlags | EV>0 | Gate17 | PASS |
|---------|-----------|--------|----------|----------|---------|----------|-----------|----------|------|--------|------|
```
- **H2H-Stat:** H2H data exists for the SPECIFIC stat being bet (§3.0c). ❌ = H2H-STAT-BLIND, −0.5 confidence, no LR coupon.
- **StatRank:** §3.0 statistical market ranking was done — ≥3 alternative markets evaluated, best safety score chosen.
- **3WayChk:** THREE-WAY CROSS-CHECK passed — L10 avg + H2H avg + L5 trend all support pick direction.
ALL 10 columns ✅ for EVERY pick. ANY ❌ → STOP, fix, re-check. **No coupon file without this matrix.**

ALL V1-V10 pass → **PORTFOLIO APPROVED.**

---

## STEP 10: ARTIFACTS

Write: report, coupon file, picks-ledger, coupons-ledger, source-log, learning-log.
Record `odds_checked_at` for every pick. Cross-check all IDs across files.

On reruns: increment version (v5→v6). Mark old pending as `superseded`. Keep all versions.

---

## ZERO TOLERANCE SHIELD — Proven Failures

| # | Failure | Root cause | Prevention |
|---|---------|-----------|-----------|
| 1 | Shelton ML lost (36 games) | ML on tennis | NEVER default to ML. O22.5 would have won. |
| 2 | Struff O22.5 lost (15 games) | Low upset risk = blowout | Paradox: LOW upset → UNDER bias. |
| 3 | Jodar O22.5 lost (16 games) | WC = binary outcome | WC/Q/LL → O22.5+ HARD REJECT. |
| 4 | Jodar identity confusion | Slash = two players | Full name + ranking + country. |
| 5 | Jodar drift +10.3% ignored | Not caught | >8% drift = MANDATORY re-eval. |
| 6 | Palmeiras date wrong | Wrong day | V7b: verify EVERY date on BetExplorer. |
| 7 | N11-01 in 5/7 coupons | Concentration | >60% → add resilience coupon. |
| 8 | ITF tennis all lost | Low-level unreliable | Skip ITF. ATP/WTA only. |
| 9 | HR1v5 odds wrong | No arithmetic | ALWAYS multiply legs explicitly. |
| 10 | Liverpool O1.5 TG vs Palace | H2H not checked | ALWAYS check H2H. Palace won ALL 3 recent. |
| 11 | PHI @ ATL direction wrong | "@" = Away @ Home confused | Verify home/away for EVERY event. |
| 12 | Basketball blanket-rejected on 0/2 | Small sample panic | NEVER blanket-reject sport on <5 picks. FLAG ≠ BAN. |
| 13 | Football defaulted to corners (fouls/cards/shots not checked) | Tunnel vision on one stat | ALWAYS run §3.0 RANKING for ALL available stats. Pick highest safety score. |
| 14 | Corner pick missing H2H corner data | H2H was match-level only | ALWAYS get H2H for the EXACT stat being bet (§3.0c). Match H2H alone ≠ stat H2H. |

---

## COMMON MISTAKES (read before writing)

1. Using "medium" as variant — only low-risk or higher-risk.
2. Old-style metadata in .md coupon file — metadata in ledger CSVs only.
3. Tennis ratio 1.12 as "GOOD" — it's ≤1.15 = STRONG.
4. Different confidence scores across files — one score everywhere.
5. Not flagging tournament concentration (>4 picks same tournament).
6. Labeling coupons "MEDIUM" or "ATP CLAY" — only LOW-RISK, MULTI-SPORT, HIGHER-RISK, NIGHT.
7. Inventing ratio grades — only STRONG, GOOD, BORDERLINE, REJECT exist.
8. Singles instead of coupons — NO SINGLES. Min 2 legs.
9. Producing too few coupons — scale core with picks (2-5+), ≥4 combos = genuine choice for the user.
10. Giving up after first 403 — use fallback chain, then search internet.
11. Shallow scanning — enter every tournament, count matches.
12. Missing Polish descriptions — every leg needs Polish parenthetical.
13. Claiming combined odds "verified" without showing arithmetic.
14. Skipping H2H — MANDATORY for every candidate, every sport.
15. Skipping injury check — one absent star invalidates entire thesis.
16. Defaulting to ML in any sport — statistical markets always preferred.
17. O22.5+ for WC/Q/LL — HARD REJECT. O20.5 max.
18. Ignoring drift >8% — MANDATORY re-eval.
19. Home/away reversed in US sports — "@" = Away @ Home.
20. V10e matrix missing — PROTOCOL VIOLATION. Every pick must have ✅ on all 10 columns.

---

## MARKET HIERARCHY (ALL SPORTS — STATISTICAL MARKETS FIRST, ML IS LAST RESORT)

### WHY statistical markets beat outcome markets (CORE DOCTRINE)

Statistical/peripheral markets (corners, fouls, shots, points, games, sets, frames) are **fundamentally more predictable** than outcome markets (goals, ML, winner). This is not a preference — it's structural:

1. **Accumulation:** They pile up throughout the match (a team wins 5-8 corners per half regardless of score). High in-match sample = lower variance.
2. **Style-driven:** A pressing team always forces corners; a physical team always commits fouls. These are structural traits that persist even in upsets. Goals depend on finishing luck.
3. **Shock-resistant:** A red card or freak goal destroys ML but barely moves total corners/fouls/shots. Statistical markets survive in-match chaos.
4. **Mispriced:** Bookmakers focus liquidity on ML/goals. Peripheral markets get less attention = more edge for us.

**EVERY football match in shortlist MUST have ≥1 corners/fouls/shots market evaluated.** Never default to goals-only.

| Sport | Priority order (→ least preferred) | Primary statistical markets |
|-------|-----------------------------------|-----------------------------|
| Football | Fouls → Cards → Corners → Shots → Team totals → BTTS → U2.5 → O2.5 → DC/DNB → 1X2 | Corners, fouls, cards, shots (accumulate, style-driven) |
| Tennis | Game totals O/U → Set totals → Game HC → Set HC → ML | Games, sets (accumulate per match, serve/return driven) |
| Basketball | Team totals → Quarter totals → Game totals → Spreads → ML | Points, team totals (pace-driven, accumulate in quarters) |
| Hockey | Period totals → Game totals → Puck line → ML | Period totals, shots on goal |
| Baseball | F5 totals → Team totals → Game totals → Run line → ML | F5 innings, team totals (pitcher-driven) |
| Volleyball | Set score O/U → Point totals → Set totals → Set HC → ML | Sets, total points (accumulate, reception/attack driven) |
| Esports | Round totals → Map totals → Map HC → Kill totals → ML | Rounds, maps (map pool driven, accumulate) |
| Snooker | Century O/U → Frame totals → Frame HC → ML | Frames, centuries (session-driven, accumulate) |
| Darts | 180s O/U → Leg totals → Set totals → ML | 180s, legs (average-driven, accumulate) |
| Handball | Half totals → Game totals → HC → ML | Half totals, game totals (pace-driven) |
| Table Tennis | Point totals → Set totals → Set HC → ML | Points, sets (rally style driven) |
| MMA | Method → O/U rounds → ITD → ML | Rounds (style-driven: wrestler vs striker) |
| Padel | Game totals → Set totals → Set HC → ML | Games, sets (rally-driven, accumulate) |
| Speedway | Total pts → HC → Match winner | Total points (rider form driven) |

**Key:** Statistical markets accumulate, are style-driven, survive in-match chaos, and are mispriced. This is our edge. The less popular the market, the more likely mispriced.
