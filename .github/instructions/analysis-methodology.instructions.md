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

**Minimums:** ≥50 events scanned, ≥80% scan completeness, 15-40 shortlist across ≥8 sports, final picks from ≥5 sports, core coupons scale with picks (target ≥5 when 10+ approved) + ≥4 combo coupons. KEY sports ≥60% of shortlist. **Target ≥30 picks in final market matrix for user to choose from.**

**SESSION PARITY:** Session type (full/day/night) controls ONLY the event time window. Analysis depth, coupon count, all steps, all validation = IDENTICAL regardless of session.

**NO AUTO-REJECTION RULE:** The pipeline NEVER auto-rejects events based on EV, safety scores, or historical hit rates. ALL discovered fixtures with available markets are shown in the market matrix. The USER decides which to bet on. The pipeline's job is to provide maximum information — odds, safety scores, H2H data, market alternatives — not to filter down to a tiny list. **This policy is enforced at script level:** `aggregate_and_select.py` uses advisory flags instead of auto-rejection, ensuring all events flow through to the market matrix regardless of calculated scores.

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
Before STEP 1, query the picks-ledger AND the Betclic bet history to extract actionable patterns. This takes 2 minutes and prevents repeating proven failures.

**§0.2a BETCLIC HISTORY FILE (MANDATORY — NEVER SKIP)**
```
read_file: betting/data/betclic_bets_history.json
run: python3 scripts/analyze_betclic_learning.py
```
This file contains **ALL actually placed bets** from the Betclic account (ground truth). It MUST be read and its analyzer output applied BEFORE any analysis begins. The analyzer produces current stats — always use its live output, not memorized numbers. Core patterns (verified by data):
- Statistical markets consistently outperform outcome markets. ALWAYS prefer statistical.
- Football corners = top core market. Match winner = #1 coupon killer. DEMOTE ML to last resort.
- AKO (5+) has near-zero win rate. MAX coupon size = 4 legs. Sweet spot: AKO (2-3).
- UNDER direction outperforms OVER. Actively seek UNDER plays.
- High-stakes coupons (5+ PLN) have significantly worse win rate. Keep stakes small.

**GATE: If `betclic_bets_history.json` is not read, the §0.2 step is INCOMPLETE. Do NOT proceed to STEP 1.**

If the file is missing, run: `python3 scripts/parse_betclic_bets.py` (requires HTML export from betclic.pl/my-bets).

1. **Per-market hit rate:** Group settled picks by `market` column. Calculate win% per market type (e.g., corners: 75%, ML: 40%, BTTS: 55%). Cross-reference with Betclic history market rates. **ADVISORY ONLY** — show rates prominently in report for user awareness. NEVER auto-reject or auto-exclude any market based on hit rate alone.
2. **Per-sport hit rate:** Group by `sport`. Cross-reference with Betclic history sport rates. Any sport with <30% hit rate on 5+ picks → **FLAG for user attention** (show in report). **NEVER blanket-reject an entire sport. NEVER apply automatic confidence penalties.** <5 settled picks = insufficient sample for any sport-level action. Each candidate is analyzed individually through STEP 3-7 regardless of sport-level hit rate.
3. **Coupon failure analysis:** For each LOST coupon, identify the leg that failed. Cross-reference with Betclic §7 coupon killer analysis. Track which pick types are the "coupon killers." Show coupon killer data in report for user awareness — do NOT auto-exclude from any coupon tier.
4. **Streak check:** Any team/player appearing 3+ times in recent picks? Check if the thesis is stale or if the edge has been priced in.
5. **Betclic history cross-check (ADVISORY ONLY):** Show all market/sport hit rates from Betclic history in the report. **NEVER AUTO-REJECT any market/sport combination based on historical hit rates.** All markets must receive full STEP 3-7 analysis regardless of past performance. The user decides whether to act on low hit rate warnings.
6. **Write a 3-line summary** of what the data says today. Example: "Corners 6/8 (75%). Tennis ML 1/5 (20%) — ⚠️ low rate. Hockey totals killing coupons — ⚠️ flagged."

---

## STEP 1: SCAN — Complete Event Discovery

1. Run `python3 scripts/pipeline_orchestrator.py --date YYYY-MM-DD` (preferred — orchestrates all steps with state tracking and resume capability) or `bash scripts/run_full_scan_and_prepare.sh` (manual fallback). Check `scan_errors.json`.
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

### §1.9 MARKET MATRIX GENERATION (MANDATORY — after scan completeness gate)

**After scan + fixture discovery, generate the comprehensive market matrix:**
```bash
python3 scripts/generate_market_matrix.py --date YYYY-MM-DD
```

This produces THREE files:
1. `betting/data/market_matrix_{date}.json` — full structured matrix
2. `betting/data/market_matrix_{date}.md` — human-readable market matrix with ALL events
3. `betting/data/decision_matrix_{date}.md` — compact bettable opportunities list

**Purpose:** Bridge the gap between fixture discovery (hundreds of events) and analysis (which requires cached stats). The market matrix shows ALL discovered events with whatever data is available — odds, safety scores, scan data. Nothing is auto-rejected.

**Data tiers in the matrix:**
- **FULL:** Odds + safety stats + H2H data (best quality)
- **ODDS_RICH:** Odds from multiple sources (no deep stats yet)
- **ODDS_BASIC:** Odds from single source
- **STATS_ONLY:** Safety stats but no odds found (user checks Betclic)
- **FIXTURE_ONLY:** Fixture exists but no odds/stats attached yet

**The matrix is the PRIMARY input for STEP 2 shortlisting.** Events at ANY data tier can be shortlisted — FIXTURE_ONLY events just need manual odds lookup on Betclic. The user sees the full landscape of what's available.

### §1.8 FIXTURE VERIFICATION GATE (MANDATORY — before shortlisting)

**Problem:** Tipster sites (especially ZawodTyper) frequently reference wrong opponents, wrong dates, matches already played, or events from other rounds. On 2026-04-29, 58% of the shortlist (19/33) turned out to be phantom fixtures. This wastes pipeline capacity and distorts shortlist quality metrics.

**Rule: EVERY candidate entering the S2 shortlist MUST be fixture-verified against ≥2 independent non-tipster sources.**

Verification sources (use ≥2 per candidate):
- **Odds-API snapshot** (`odds_api_snapshot.json`) — if event has live odds from ≥3 bookmakers, it exists
- **Flashscore** — check sport-specific daily schedule page
- **BetExplorer** — check competition page for today's matches
- **Official tournament site** (ATP/WTA draws, EHF schedule, ekstraliga.pl, etc.)
- **Sofascore** — alternative fixture verification

**Tipster-only candidates (no independent fixture confirmation):**
- If tipster references an event that appears in ZERO non-tipster sources → **DO NOT SHORTLIST**. Log as `UNVERIFIED-SKIP` in S1 notes.
- If tipster references a specific round/opponent but independent sources show a different opponent → **use the independently verified opponent**. Log the tipster confusion.

**Tennis-specific (critical — highest phantom rate):**
- ATP/WTA draws change daily. Before shortlisting ANY tennis match, verify the EXACT draw pairing on the tournament's official order of play or Flashscore.
- R16 results from yesterday may make today's R4/QF pairings different from what tipsters predicted. Always check CURRENT draw state.

**Quick verification protocol (per candidate, ~15 seconds each):**
```
1. Search event in odds_api_snapshot.json → found? ✅ verified
2. Not found? → Check Flashscore daily page for that sport → found? ✅ verified
3. Not found? → Check BetExplorer competition page → found? ✅ verified
4. Not found in ANY of the above? → DO NOT SHORTLIST. Log as UNVERIFIED-SKIP.
```

**§1.8a OVERNIGHT GAME TRAP (MANDATORY — prevents phantom inclusions):**

Tipster sites (especially ZawodTyper) list tips for overnight games (01:00-06:00 CEST) that were ALREADY PLAYED the previous night. This is the #1 source of phantom fixtures.

**Detection protocol:**
1. For ANY event with kickoff time 00:00-06:00 on the ZT daily page: check if the tip was posted >12 hours ago AND the game time has already passed.
2. Look for post-game comments on the ZT page (e.g., "W plecy 97:113", results, score references) — these confirm the game is OVER.
3. Cross-check: search Flashscore for the event. If result is already posted → PHANTOM. Do NOT shortlist.
4. NBA/NHL playoff games at 01:00-04:00 CEST on a Wednesday ZT page typically played TUESDAY NIGHT (already over by Wednesday morning).

**Rule:** Events with kickoff < current_time → automatically PHANTOM unless confirmed as future event via live odds (odds_api_snapshot or BetExplorer showing active markets).

**Lesson (v5, 2026-04-29):** BOS-76ers (01:00), EDM-ANA (04:00), NYK-ATL (02:00), SAS-POR (03:30) were all on the ZT środa page but had ALREADY PLAYED Tuesday night. ZT comments confirmed results. These wasted analysis capacity in earlier versions.

**S2 shortlist MUST include a verification column:**
```
| # | Event | Fixture Verified | Verification Sources |
```
Any row with `Fixture Verified = ❌` → cannot enter shortlist.

### §1.7 EXOTIC LEAGUE PROTOCOL

**Definition:** An "exotic league" is any football competition OUTSIDE:
- Top 5 European leagues (EPL, LaLiga, Bundesliga, Serie A, Ligue 1) and their 2nd divisions
- Top established European leagues (Eredivisie, Belgian Pro League, Portuguese Primeira, Turkish Super Lig, Russian Premier, Swiss Super League, Austrian Bundesliga, Scottish Premiership, Greek Super League, Czech First League, Polish Ekstraklasa, Danish Superliga, Swedish Allsvenskan, Norwegian Eliteserien, Croatian HNL, Serbian SuperLiga, Ukrainian Premier, Romanian Liga 1)
- Primary US/MX/BR/AR/JP/KR leagues (MLS, Liga MX, Brasileirão, Argentine Primera, J-League, K-League)
- Continental club competitions (UCL, UEL, UECL, Copa Libertadores, Copa Sudamericana, AFC Champions League)

**Everything else is EXOTIC:** Peru Liga 1, Egyptian Premier League, Kings League, Uzbekistan Super League, Algerian Ligue 1, Saudi Pro League, Indian ISL, Vietnamese V-League, Faroe Islands, Gibraltar, Kosovo, all Central American leagues, all Central Asian leagues, etc.

**§1.7a BETCLIC MARKET GATE (MANDATORY — check BEFORE deep analysis):**
Before investing analysis time on ANY candidate (not just exotic — ALL candidates):
1. Check if the league/event exists on Betclic (betclic.pl relevant sport section).
2. If NO markets on Betclic → SKIP (no execution path). Log as `BETCLIC-UNAVAILABLE`.
3. If ONLY ML/1X2 on Betclic → proceed only if strong statistical edge exists AND ML is acceptable per §6.5 upset risk.
4. If statistical markets (corners, cards, totals, frames, games) exist on Betclic → proceed normally.
5. **For non-exotic leagues:** Check SPECIFIC STATISTICAL MARKET availability (e.g., fouls, team corners). Some leagues have corners but not fouls on Betclic. If the §3.0 top-ranked market doesn't exist on Betclic, use the next-ranked market that DOES exist.

**Lesson (v4, 2026-04-29):** Inter Turku vs HJK (Veikkausliiga) — fouls O22.5 was top-ranked market (safety 0.80) but Betclic does NOT offer fouls for Finnish football. This forced a last-minute market change to goals O2.5 (safety 0.60), significantly weakening the pick. CHECK BETCLIC MARKET AVAILABILITY BEFORE completing §3.0 analysis to avoid wasted effort.

**Lesson (v3, 2026-04-29):** Higgins vs Robertson — analysis assumed Betclic line 20.5 frames, but actual Betclic line was 22.5. When L10 avg = line (22.5 = 22.5), there is ZERO margin = no edge. ALWAYS verify the actual Betclic line before calculating safety scores.

**§1.7b DATA THRESHOLDS (relaxed for exotic leagues):**

| Requirement | Mainstream | Exotic |
|-------------|-----------|--------|
| H2H meetings minimum | 5 | 3 (flag as EXOTIC-THIN if <5) |
| Stat sources minimum | 3 | 2 (Flashscore/Sofascore + 1 specialist) |
| Tipster sources | ≥2 with reasoning | ≥1 (exotic leagues rarely covered by tipsters) |
| Corner/card stat source | TotalCorner + SoccerStats + Betclic | Soccerway + Flashscore match stats (fallback) |
| §3.0 market ranking | ≥3 alternative markets | ≥2 alternative markets (if data allows 3, do 3) |

Picks with EXOTIC-THIN data flags:
- CANNOT be in LR coupons
- Get −0.5 confidence adjustment
- Maximum 2 exotic picks per coupon
- Maximum 1 exotic pick per LR coupon (only if NOT EXOTIC-THIN)

**§1.7c SOURCE FALLBACK CHAIN (exotic football):**
```
Primary: Flashscore (fixture, H2H, match stats) + Sofascore (form, stats)
├── H2H thin? → Soccerway H2H + AiScore H2H
├── Corner/card stats missing? → Flashscore match-level stats (last 10 games, manual count)
├── League standings missing? → Soccerway standings + BetExplorer results
├── No SoccerStats/TotalCorner? → Betaminic (covers some exotic leagues) → Flashscore per-match corner counts (manual)
└── All fail? → Google "[league name] statistics [season]" for specialist sites
```

**§1.7d RED FLAGS SPECIFIC TO EXOTIC LEAGUES:**

| Red Flag | Description | Action |
|----------|-------------|--------|
| Match-fixing risk | League/country on known match-fixing watchlists (spotfixing.eu, IBIA alerts) | HARD REJECT for exotic leagues with active alerts. For flagged countries: skip low-division matches, only top-flight with high attendance. |
| Scheduling irregularities | Mid-week matches with no clear reason, frequent postponements, irregular kickoff times | FLAG — investigate before proceeding. Unusual schedule = potential integrity issue. |
| Extreme weather/altitude | High-altitude venues (Bolivia, Peru highlands, Central Asian cities), extreme heat (Middle East summer), monsoon season (SEA) | Adjust totals expectations. High altitude = more goals/corners. Extreme heat = fewer goals, lower pace. Monsoon = match postponement risk. |
| Kings League special rules | Shorter halves (20 min), special gameplay mechanics (shootouts, power-ups), entertainment format | SEPARATE ANALYSIS PROTOCOL. Do NOT apply standard football stats. Kings League H2H/form from previous Kings League seasons ONLY. Standard football metrics DO NOT TRANSFER. |
| Low attendance / closed doors | Matches with <1000 attendance or behind closed doors | FLAG — home advantage reduced. Adjust H/A split expectations. |
| Roster instability | Frequent mid-season transfers, loan army turnover, player migration between exotic leagues | INCREASE weight on L5 recent form (post-transfer window) over L10. Coach/roster stability check is CRITICAL. |
| Time zone mismatch | Kickoff at unusual local time (e.g., 3 AM local = potential integrity concern) | FLAG — investigate reason. Official schedule adjustments for TV are OK; unexplained off-hour matches = caution. |

**§1.7e EXOTIC LEAGUE CLASSIFICATION:**
- **Tier E1 (established exotic):** Saudi Pro League, Egyptian Premier League, Moroccan Botola, Algerian Ligue 1, UAE Pro League, Indian ISL, Colombian Liga BetPlay, Chilean Primera, Paraguayan Primera, Ecuadorian LigaPro, Peruvian Liga 1, Uzbekistan Super League, Kazakhstan Premier League, Georgian Erovnuli Liga, Kosovo Superliga, North Macedonian First League — reasonable data coverage, Flashscore/Sofascore available, BetExplorer usually has odds.
- **Tier E2 (thin data):** Bolivian Primera, Costa Rican Primera, Central American leagues, Iranian PGPL, Iraqi Stars League, Jordanian Pro League, Armenian/Azerbaijani leagues, Faroe Islands, Gibraltar, Andorra, San Marino — sparse data, limited H2H, Soccerway may be only reliable source.
- **Tier E3 (ultra-thin):** Bangladesh, Myanmar, Cambodia, Laos, Mongolia, Turkmenistan, Tajikistan, Kyrgyzstan — minimal data coverage, avoid unless strong reason and Betclic offers markets.
- **Entertainment:** Kings League — separate protocol, non-standard football rules.

Tier E3 picks require ALL of: Betclic market confirmed, ≥2 sources with data, EV > 0, and user explicit approval before placement.

---

## STEP 2: FILTER — Shortlist

Remove: outside betting window, no Tier A coverage, <2h to kickoff, already started, exhibitions.
Prioritize: events WITH statistical markets (corners, totals, HC) over basic ML-only.
**Early Betclic market hint:** For niche sports (volleyball, table tennis, padel, speedway), check Betclic market availability BEFORE deep analysis. If market doesn't exist on Betclic → don't waste analysis time.
Preferred odds range: 1.30-3.50.
**Target: 15-40 events across ≥8 sports in shortlist (≥5 sports minimum in final picks).** KEY sports (Football+Volleyball+Basketball+Tennis) should be ≥60% of shortlist but no single sport >40%.

**§2.1 MINIMUM PICK EXPANSION TRIGGER:**
If after S7 gate fewer than 4 picks survive → DO NOT proceed to S8 with <4 picks. Instead:
1. Go back to S2 and expand the shortlist by 5-10 candidates from ZT tipster-backed statistical markets.
2. Specifically target sports NOT yet represented (volleyball, tennis, basketball, snooker) to improve diversity.
3. Re-run S3-S7 for the new candidates ONLY.
4. If STILL <4 picks after expansion → declare NO BET day.

**Lesson (v4, 2026-04-29):** v4 had only 3 picks (below minimum 4) because PK-02 (Higgins frames) was dropped for Betclic line mismatch. The pipeline should have triggered expansion rather than producing coupons with only 3 picks.

**CRITICAL: The S2 shortlist is a COMMITMENT.** Every candidate that enters the shortlist WILL receive full §3.0 analysis in S3 (see §3.0f). The only removals between S2 and S3 are PHANTOM/VOID/WRONG DATE/ALREADY STARTED — verified against ≥2 sources. Do NOT shortlist candidates you plan to skip later. If data looks thin at S2, either investigate further NOW or don't shortlist.

**§1.8 ENFORCEMENT:** Every S2 candidate MUST have passed §1.8 fixture verification (≥2 non-tipster sources). If a candidate was shortlisted without verification → REJECT at S2 gate. This prevents phantom fixtures from contaminating the shortlist and wasting S3 analysis capacity.

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

> **Full table** in `bet-analyzing-statistics` SKILL.md §3.0b. Per-sport mandatory multi-market calculation tables in sport-analysis-protocols.instructions.md (§3.1M-§3.14M).
>
> **Quick reference:** Football (Fouls, Cards, Corners, Shots, Throw-ins, Goal kicks, Offsides, Goals, BTTS) | Tennis (Games, Sets, HC, Tiebreaks, Aces) | Basketball (Team pts, Quarter, Half, Total, Rebounds, 3PT) | Volleyball (Sets, Points, Set HC) | Hockey (Period, Goals, Shots, PP) | Baseball (F5, Team, Total, Hits, K's) | Snooker (Frames, Centuries, 50+) | Darts (180s, Legs, Sets) | Handball (Half, Total, Team, Suspensions) | Esports (Rounds, Maps, Kills) | Table Tennis (Sets, Points) | MMA (Rounds, Method, ITD) | Padel (Games, Sets) | Speedway (Points, HC)

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

### §3.0d DATA PROVENANCE (MANDATORY — NEVER SKIP)

**Every stat cited in S3 output MUST include ALL THREE:**
1. **Source name** — the exact website or tool (e.g., "SoccerStats", "TennisAbstract", "Flashscore H2H tab")
2. **Exact data point** — the specific number with context (e.g., "Liverpool avg 11.2 corners/match at home, L10 games")
3. **Fetch reference** — how the data was obtained (e.g., "web-fetch", "Playwright scan", "Odds-API snapshot")

**BANNED WORDS in S3 table cells** — if ANY of these appear as the SOLE content of a table cell, it is a STRUCTURAL VIOLATION and the candidate is REJECTED:
- "checked", "verified", "confirmed", "good", "fine", "OK", "done", "yes", "—", "N/A", "n/a", "see above"

**Examples:**
- ❌ `| Injury check | checked |` → VIOLATION
- ✅ `| Injury check | No injuries — ESPN injury report, 2026-04-28 08:30 |` → VALID
- ❌ `| H2H avg | good |` → VIOLATION
- ✅ `| H2H avg | 5.8 cards (5 meetings, Flashscore H2H) |` → VALID
- ❌ `| Safety | — |` → VIOLATION
- ✅ `| Safety | 0.70 |` → VALID

**Enforcement:** The orchestrator scans every cell in the S3 output. Banned word as sole content → auto-reject that candidate, return to bet-statistician.

### §3.0e MANDATORY PER-CANDIDATE OUTPUT TEMPLATE

> **Full template code block** in `bet-analyzing-statistics` SKILL.md. The template below is a COMPACT reference — the full version with all table formats lives in the skill.

**EVERY candidate in `{date}_s3_deep_stats.md` MUST have these 10 sections** (delimited by `══ CANDIDATE ... ══` and `══ END CANDIDATE ══`):

1. **§S3.1** H2H Analysis (market-specific) — ≥3 meetings, H2H avg, BLIND status
2. **§S3.2** Form & Stats Table — sport-specific, all columns, home/away split
3. **§S3.3** Market Ranking (§3.0) — ≥3 rows (≥4 football), Safety 0.00-1.00
4. **§S3.4** Three-Way Cross-Check — L10, H2H, L5 rows with alignment verdict
5. **§S3.5** Coach/Roster Stability — source named, date checked
6. **§S3.6** Injury/Suspension Check — source + timestamp per entry
7. **§S3.7** Top 3 Markets — from ranking with safety scores
8. **§S3.8** Recommended Market — cites §S3.3, explains WHY
9. **§S3.9** Sources Used — ≥2 rows with actual source names
10. **§S3.10** Depth Proof — 5 metrics with numbers

**VALIDATION (automated via `validate_s3_output.py`):**
1. All 10 section markers present
2. §S3.3 ≥3 data rows (≥4 football), Safety values are decimal 0.00-1.00
3. §S3.4 has 3 rows with numeric values + alignment verdict
4. §S3.9 has ≥2 rows
5. No BANNED WORD (§3.0d) as sole cell content
6. §S3.6 injury check has source + timestamp
7. §S3.10 has 5 metrics with numbers

### §3.0f S3 COMPLETENESS GATE (MANDATORY — NEVER SKIP)

**EVERY candidate that survives the S2 shortlist MUST receive full §3.0 analysis. No exceptions.**

The ONLY valid reasons to remove a candidate BEFORE S3 analysis are:
1. **PHANTOM (ZT#6):** Fixture does not exist — wrong date, wrong opponent pairing, event already played. Verified against ≥2 independent sources (Odds-API, Flashscore, BetExplorer).
2. **VOID:** Fixture cannot be independently verified by ANY source outside the tipster that suggested it.
3. **WRONG DATE:** Event is not within today's betting window.
4. **ALREADY STARTED:** Event has already begun.

These pre-S3 removals are logged in a `PRE-S3 REMOVALS` table with the exact reason and verification sources.

**ALL remaining candidates after pre-S3 filtering MUST receive:**
- Full §3.0e template (all 10 sections §S3.1-§S3.10)
- §3.0 statistical market ranking with ≥3 markets
- §3.0c H2H market-specific validation
- Three-way cross-check

**S3 COVERAGE CHECK (gate before proceeding to S4):**
```
S2 shortlist count:           [N]
Pre-S3 removals (PHANTOM/VOID): [X]
Candidates requiring S3:       [N - X]
Candidates WITH completed S3:  [Y]
S3 COVERAGE:                   [Y / (N - X)] = must be 100%
```
**If S3 COVERAGE < 100% → STOP. Complete missing analyses before proceeding.**

**After S3, ALL candidates with completed analysis are classified:**
- **CORE:** Passed 17-point gate fully → enters core portfolio
- **EXTENDED POOL:** Has EV > 0 but failed some gate checks → enters extended pool with bull/bear case
- **REJECTED:** EV ≤ 0, or bear > bull, or critical red flag → enters ODRZUCONE section with specific reason

**The user sees ALL three groups.** No candidate with completed §3.0 analysis and EV > 0 is silently dropped. Every analyzed candidate appears in either core, extended pool, or rejected list.

---

## STEP 3B: TIME-SENSITIVE DATA (run 2-3h before earliest event)

1. **Lineups:** Flashscore (~1h), SportoweFakty for speedway (~2-3h), DailyFaceoff for NHL goalies.
2. **Late injuries:** ESPN, team social media, ATP/WTA Order of Play.
3. **Weather:** Outdoor sports — run `python3 scripts/fetch_weather.py --date YYYY-MM-DD` (Open-Meteo API, free, no key) for automated weather data per venue. Covers temperature, precipitation, wind speed, conditions. Impact: rain → fewer corners/shots; wind → fewer goals; extreme heat → lower pace. If weather changed significantly since S3 → re-evaluate stat market direction.
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
| Football (Exotic SA) | Feedinco → Bettingclosed | Sportsgambler | OLBG → Google "[league] tips [date]" |
| Football (Exotic Africa/ME) | Tips180 → Feedinco | Bettingclosed → Tips180 | Sportsgambler → Google "[league] tips [date]" |
| Football (Exotic Asia) | AsiaBet → Feedinco | Bettingclosed → Tips180 | Sportsgambler → Google "[league] tips [date]" |
| Football (Exotic Europe minor) | ZawodTyper → Typersi | Feedinco → Bettingclosed | OLBG → Sportsgambler |

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
8. **MARKET PERFORMANCE TRACKER:** Before picking any market, check hit rate in picks-ledger AND `betclic_bets_history.json`. Show rates prominently in the report. **ADVISORY ONLY** — NEVER auto-downgrade confidence or auto-exclude based on hit rates. The USER decides. Betclic history complements picks-ledger (larger sample).

**Learned caution zones (ADVISORY):** MLB totals 33% historical hit rate — ⚠️ flag for user. MLB overs ≥8.5 — ⚠️ flag for user. Show these observations prominently but NEVER auto-reject or auto-downgrade.

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
| 15 | Betclic history skipped → repeated known failures | §0.2a not executed | ALWAYS read `betclic_bets_history.json` + run `analyze_betclic_learning.py` before ANY analysis. This is ground truth. |
| 16 | PSG vs Bayern cards approved without §3.0 ranking table | S3 output was narrative ("H2H avg 5.8 cards") without structured ranking table comparing cards vs corners vs fouls vs shots | §3.0e template is MANDATORY. §S3.3 ranking table must have ≥3 rows with real numbers. Orchestrator mechanically verifies section markers. |
| 17 | Narrative analysis substituted for structured template | Agent wrote paragraphs instead of filling §S3.1-§S3.10 sections with tables and numbers | Every candidate MUST have all 10 sections (§S3.1-§S3.10). Missing markers = STRUCTURAL VIOLATION = auto-reject. |
| 18 | Exotic league analyzed without Betclic market check | Full S3-S7 done on a league where Betclic has no markets | §1.7a BETCLIC MARKET GATE: Check Betclic market existence BEFORE starting deep analysis. No markets → SKIP. |
| 19 | 16/33 shortlisted candidates skipped S3 entirely | S3 only run for "top" candidates; rest silently dropped without analysis or user visibility | §3.0f S3 COMPLETENESS GATE: 100% of non-PHANTOM shortlisted candidates MUST receive full §3.0 analysis. ALL analyzed candidates appear in core, extended pool, or rejected list. User sees everything. |
| 20 | 58% shortlist was phantom fixtures (19/33) | Tipster-sourced events not verified against independent sources before shortlisting. Wrong opponents, wrong dates, matches already played | §1.8 FIXTURE VERIFICATION GATE: Every candidate must be verified against ≥2 non-tipster sources BEFORE entering S2 shortlist. Tipster-only = UNVERIFIED-SKIP. Tennis draws must be checked against current tournament state. |

---

## COMMON MISTAKES (read before writing — entries unique to this section, not covered by Zero Tolerance Shield above)

1. Using "medium" as variant — only low-risk or higher-risk.
2. Old-style metadata in .md coupon file — metadata in ledger CSVs only.
3. Tennis ratio 1.12 as "GOOD" — it's ≤1.15 = STRONG.
4. Different confidence scores across files — one score everywhere.
5. Not flagging tournament concentration (>4 picks same tournament).
6. Labeling coupons "MEDIUM" or "ATP CLAY" — only LOW-RISK, MULTI-SPORT, HIGHER-RISK, NIGHT.
7. Inventing ratio grades — only STRONG, GOOD, BORDERLINE, REJECT exist.
8. Producing too few coupons — scale core with picks (2-5+), ≥4 combos = genuine choice for the user.
9. Missing Polish descriptions — every leg needs Polish parenthetical.
10. Claiming combined odds "verified" without showing arithmetic.
11. V10e matrix missing — PROTOCOL VIOLATION. Every pick must have ✅ on all 10 columns.

---

## MARKET HIERARCHY (ALL SPORTS — STATISTICAL MARKETS FIRST, ML IS LAST RESORT)

### WHY statistical markets beat outcome markets (CORE DOCTRINE)

Statistical/peripheral markets (corners, fouls, shots, points, games, sets, frames) are **fundamentally more predictable** than outcome markets (goals, ML, winner). This is not a preference — it's structural:

1. **Accumulation:** They pile up throughout the match (a team wins 5-8 corners per half regardless of score). High in-match sample = lower variance.
2. **Style-driven:** A pressing team always forces corners; a physical team always commits fouls. These are structural traits that persist even in upsets. Goals depend on finishing luck.
3. **Shock-resistant:** A red card or freak goal destroys ML but barely moves total corners/fouls/shots. Statistical markets survive in-match chaos.
4. **Mispriced:** Bookmakers focus liquidity on ML/goals. Peripheral markets get less attention = more edge for us.

**EVERY football match in shortlist MUST have ≥1 corners/fouls/shots market evaluated.** Never default to goals-only.

> **Full per-sport priority order table** in `bet-analyzing-statistics` SKILL.md and sport-analysis-protocols.instructions.md (§3.XM tables). Quick reference: Football (Fouls→Cards→Corners→Shots→…→1X2) | Tennis (Games→Sets→HC→ML) | Basketball (Team totals→Quarter→Game→Spreads→ML) | All sports: statistical markets FIRST, ML is LAST RESORT.
