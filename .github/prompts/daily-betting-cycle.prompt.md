---
name: daily-betting-cycle
description: "Full daily cycle: settle previous day, scan events, deep analysis (EV/CLV/Kelly), build pewniaki coupons."
agent: bet-analyst
argument-hint: "run_date=2026-04-24 session=full" or "run_date=2026-04-24 session=full rerun=true"
tools:
  - search
  - editFiles
  - runCommands
  - terminalLastCommand
  - changes
  - memory/*
  - sequentialthinking/*
---

## Inputs

- **run_date** = ${input:run_date:today}
  If "today" or empty, use the current calendar date.
- **session** = ${input:session:full}
  Controls which events to analyze:
  - `full` — entire betting day (06:00 → 05:59 next day). Default.
  - `day` — daytime events only (06:00 → 21:59).
  - `night` — night events only (22:00 → 05:59 next day). For pre-sleep coupon.
  - `morning` — settle overnight results + scan early events (06:00 → 14:59).
- **rerun** = ${input:rerun:false}
  When `true`, forces a complete fresh analysis for run_date, even if artifacts already exist:
  - Settlement (STEP 1) is SKIPPED if previous day was already settled.
  - Orchestrator is re-run to get fresh data (forced, even if scan_summary.json exists).
  - **Versioning (CRITICAL):** Previous picks and coupons are PRESERVED, not replaced. New analysis creates a new version:
    - Determine next version: scan `betting/coupons/YYYY-MM-DD*.md` for highest existing version (e.g., v5 → next is v6). If no versioned file, start at v1.
    - New picks get NEW pick_ids (next available PK-YYYYMMDD-## after the highest existing one for that day).
    - New coupons get versioned coupon_ids (e.g., CP-YYYYMMDD-PD1v6).
    - picks-ledger.csv: ADD new rows with `version=vN`. Old version rows stay untouched.
    - coupons-ledger.csv: ADD new rows with `version=vN`. Old version rows stay untouched.
    - Coupon file: create `betting/coupons/YYYY-MM-DD-vN.md`. Previous version files are kept.
    - Report file: create `betting/reports/YYYY-MM-DD-vN.md`. Previous version files are kept.
    - The user sees ALL versions in the ledger and compares them to decide which to place.
    - Set old version's pending picks/coupons to `status=superseded` (new status value).
  - ALL analysis steps (3-8) run from scratch — do NOT reuse previous analysis or picks.
  - Learning-log gets an entry noting the rerun and reason (methodology change, new sources, etc.).
- **bookmaker** = Betclic
- **local_timezone** = Europe/Warsaw
- Load all other parameters from `config/betting_config.json` (bankroll, stakes, caps, thresholds, sports).

## References

Follow [methodology STEPS 0-10](../instructions/analysis-methodology.instructions.md) — the SINGLE SOURCE OF TRUTH.
Also: [repo rules](../copilot-instructions.md), [artifact rules](../instructions/betting-artifacts.instructions.md), [model-ready rules](../instructions/model-ready-betting.instructions.md), [source registry](../../betting/sources/source-registry.md).

**MANDATORY: Use the `sequentialthinking` tool for EVERY STEP (0-10). Per-candidate steps (3-7) require one call PER candidate. Do not reason only in text — call the tool explicitly. This prevents shortcuts, counting errors, and skipped checks.**

Core philosophy: find MISPRICED ODDS, not predict winners. Only bet when EV > 0.

---

## STEP 0: ORCHESTRATOR + SETUP

0a. Resolve run_date → betting day window based on session:
    - `full`: 06:00 run_date → 05:59 next day
    - `day`: 06:00 → 21:59 run_date
    - `night`: 22:00 run_date → 05:59 next day
    - `morning`: 06:00 → 14:59 run_date
0b. Ensure artifact directories and files exist (bootstrap with exact headers if missing).
0c. **If rerun=true**: ALWAYS re-run the orchestrator for fresh data, regardless of scan_summary.json age.
    **If rerun=false**: Check `betting/data/scan_summary.json` freshness. If stale or missing, run orchestrator.
    ```
    cd /Users/mkoziol/projects/bet && bash scripts/run_full_scan_and_prepare.sh
    ```
0d. Check `betting/data/scan_errors.json` for source failures. Note them for source log.
0e. **If rerun=true**: Determine next version suffix and prepare versioned artifacts.
    - List existing coupon files for this betting_day: `betting/coupons/YYYY-MM-DD*.md`
    - Find highest version number (e.g., v5 → next is v6). If no versioned file exists, start at v1.
    - Find highest existing pick_id for this day in picks-ledger.csv (e.g., PK-20260424-09 → next starts at PK-20260424-10).
    - Mark all existing `pending` picks and coupons for this betting_day as `status=superseded` in the ledgers.
    - New rows will be ADDED with the new version — old rows are preserved for history.

## STEP 1: SETTLEMENT (skip if rerun=true and previous day already settled, or if session=night and previous day already settled)

1a. Determine previous betting day.
1b. Run `python3 scripts/settle_on_finish.py --betting-day <prev_date>` for auto-resolvable markets.
1c. For corners, cards, handicaps, MyCombi — settle manually via Flashscore + Sofascore (2 sources minimum).
1d. Update picks-ledger.csv (status, pnl_pln) and coupons-ledger.csv (derive from legs).
1e. Compute: previous-day PnL, rolling 7-day PnL, per-market hit rates.
1f. Post-mortem each loss: bad thesis or variance?
1g. Record CLV for settled picks where closing odds are available.
1h. Update bankroll in config/betting_config.json.

## STEP 2: LEARNING + SOURCE LOG

2a. Append to learning-log.md (max 3 rule changes, tied to settled results).
2b. Update source-log.csv — one row per source, noting availability and usage.

## STEP 3: EVENT SCAN — DEEP SCAN PROTOCOL

3a. Scan ALL 14 sports: football, tennis, basketball, hockey, volleyball, esports, snooker, table tennis, darts, handball, MMA, baseball, padel, speedway.
3b. Use orchestrator outputs + BetExplorer + Flashscore + OddsPortal + specialist sites (CueTracker, GosuGamers, etc.).
3c. **Source resilience:** if ANY source returns 403/Cloudflare/GDPR, move to next source in the Odds Source Map (source-registry.md). For US sports: use SBR + ESPN Odds + ScoresAndOdds. For EU sports: BetExplorer + OddsPortal. NEVER give up — the internet always has data.
3d. **DEEP SCAN (CRITICAL — prevents shallow scanning):**
    - For EVERY sport, do NOT just look at the landing page. Click into EACH active tournament/league to see the FULL fixture list.
    - **Count matches per tournament.** Record the count. A sport page showing 3 events may hide 40+ when you enter individual tournaments.
    - **Cross-validate event counts:** Compare BetExplorer vs Flashscore event counts per sport. Discrepancy >20% → investigate.
    - **Enter every tournament with ≥4 matches.** Screen ALL matches for value (odds, form, H2H).
    - Example failure: scanning "Tennis" and seeing 3 matches when ATP Madrid (16), WTA Madrid (16), ATP 250 (8), and Challengers (12) exist = 50 matches missed.
3e. **TOURNAMENT FULL-SLATE (CRITICAL):** When a MAJOR TOURNAMENT is active (ATP/WTA Masters 1000, Grand Slam, World Championship, Champions League matchday, NBA/NHL Playoffs, etc.), analyze the FULL daily slate — ALL matches. Cherry-picking 1 match from 32 is a PROTOCOL VIOLATION.
3f. **Scan Completeness Metrics:** Before proceeding, compile per-sport event count table (see methodology §1.5). Total unique events must be ≥50 on a normal day. At least 6 sports must have events. Scan completeness score (events from ≥2 sources / total) must be ≥80%.
3g. Filter to session window. Remove events outside time range, without Tier A coverage, or <1h to kickoff.
3h. Build Master Event List: sport, competition, event, kickoff, initial odds.
3i. Target 15-40 shortlisted events (fewer for night/morning sessions).

## STEPS 4-8: DEEP ANALYSIS (one sequentialthinking call PER candidate)

For each shortlisted candidate, execute in sequence:

**STEP 4 — Deep Stats:**
- Football: SoccerStats + Betaminic + TotalCorner (corner 3-source stack) + xG regression.
- Tennis: TennisAbstract Elo + surface + H2H + odds ratio grading.
- Basketball: pace + OFF/DEF rating + injury report.
- Hockey: xG + goalie + PP/PK + B2B fatigue.
- Padel: FIP ranking gap + pair chemistry + tournament tier (Major/P1/P2/Bronze) + indoor/outdoor + H2H (Sofascore).
- Speedway: rider track-specific averages (SpeedwayEkstraliga.pl) + home/away team record + junior rider assessment + SportoweFakty expert analysis.
- Other sports: specialist sources per methodology appendix.

**STEP 4.5 — Time-Sensitive Data Collection (run within 2-3h of earliest event — see methodology STEP 3B):**
- Lineup verification: Flashscore lineups (~1h before), SportoweFakty for speedway (~2-3h before).
- Late injury/withdrawal check: ESPN injury report, team social media, ATP/WTA Order of Play.
- Weather check for outdoor sports: football (rain/wind), tennis (heat/wind), speedway (rain → track change), padel (wind disrupts lobs).
- Odds movement check: compare current odds to analysis-time odds. If Betclic odds moved >10% → recalculate EV.
- If ANY time-sensitive finding contradicts the pick thesis → re-evaluate. Downgrade or void if bear case strengthens.

**STEP 5 — Tipster Deep-Dive (argument-based, multi-site):**
- Check >=2 ARGUMENT-BASED tipster sites per candidate. These sites have tipsters who post WRITTEN REASONING, not just bare picks:
  - **Polish**: ZawodTyper (zawodtyper.pl), Typersi (typersi.pl), Meczyki (meczyki.pl/typy-bukmacherskie)
  - **International**: OLBG (olbg.com/tips), PicksWise (pickswise.com), BetIdeas (betideas.com/tips), Sportsgambler
  - **Esports**: GosuGamers
- **Deep extraction protocol (MANDATORY — same for ALL argument sites):**
  1. Navigate to the site's daily tips page for the relevant sport. Scroll deeply (content is often lazy-loaded).
  2. For each candidate event: find ALL tipsters/analysts who posted picks.
  3. Read each tipster's FULL WRITTEN ARGUMENT — not just the pick, but WHY (stats cited, injuries, tactical context, motivation, referee, H2H, model outputs).
  4. Record: site name, tipster name, specific pick, stated odds, argument summary. Count agree vs disagree.
  5. Arguments citing specific facts ("Villarreal averages 6.2 corners away", "Lakers 2-8 ATS on B2B") are high-value signals.
- BLOCKED (do NOT attempt): Forebet, FootySupertips, Windrawwin, BettingExpert, Protipster, Oddspedia, SportyTrader, Predictz, Trafiamy, Blogabet, HLTV.
- If a tipster source is blocked, search Google for "[event] prediction tips" to find alternatives. NEVER declare tipster consensus impossible.
- Extract: specific pick, tipster's reasoning/argument, confidence, consensus %.
- >=70% agreement → +0.5 confidence. >=60% contradiction → investigate, reduce -1 or skip.
- Strong fact-based argument from even 1 tipster against your thesis → investigate before finalizing.

**STEP 6 — Odds + EV:**
- Get market-best odds from BetExplorer/OddsPortal. For US sports: SBR Totals tab + ESPN Odds + ScoresAndOdds.
- Minimum 2 independent sources per pick for cross-validation.
- American odds conversion: +X → 1 + X/100; -X → 1 + 100/X.
- Estimate true probability (Pinnacle implied > statistical model > market consensus).
- Calculate EV = (true_probability × betclic_odds) - 1. Must be > 0.
- Calculate price_gap_pct. Reject if outside threshold (-3% LR, -5% HR).
- Check line movement (steam, RLM).
- Apply 1/4 Kelly for stake guidance.

**STEP 7 — Context:**
- Fixture confirmed? Injuries/suspensions? Competition context? Congestion? Weather? Referee?

**STEP 8 — Bear Case (Devil's Advocate):**
- Bull case (1-2 sentences) vs Bear case (1-2 sentences).
- Streak dependency? If >5-game streak → reduce confidence -1.
- Regression risk? xG mismatch?
- 20%-lower-odds test: still bet? If NO → lower confidence, coupon leg only.
- If bear > bull → REJECT.

## STEP 9: PORTFOLIO CONSTRUCTION

9a. Rank approved candidates by: EV (highest) → confidence → price_gap.
9b. Build coupons only (NO SINGLES). Minimum 2 legs per coupon. Minimum 5 coupons.
9c. **Pewniaki system**: identify 3-5 best picks, build ALL non-repeating combinations:
    - All doubles, all triples, quad (if 4+ pewniaki).
    - This automatically maximizes coupon count from the board.
9d. Build themed/higher-risk coupons from remaining approved picks.
9e. Correlation check: same match FORBIDDEN, same league FLAG, same narrative REMOVE weaker.
9f. Suggest stakes for ALL coupons. Total may exceed daily cap — user decides which to place.
9g. Build Watch List with promotion criteria ("Promote if Betclic >= X.XX").
9h. If board weak (<2 confident picks) → NO BET day.
9i. For `night` session: build 1-2 compact coupons only — user goes to sleep after placing.

## STEP 10: ODDS THRESHOLD + ARTIFACTS

10a. **DO NOT scan Betclic** (403 blocks). All picks are CONDITIONAL.
10b. Set acceptance threshold per pick (minimum odds for Betclic app).
10c. Record odds_checked_at_local as analysis timestamp.
10d. Write/update all artifacts:
    - `betting/reports/YYYY-MM-DD.md` (or `YYYY-MM-DD-night.md` for night session)
    - `betting/coupons/YYYY-MM-DD.md` (or `YYYY-MM-DD-night.md`)
    - `betting/journal/picks-ledger.csv` — reuse existing IDs, no duplicates
    - `betting/journal/coupons-ledger.csv` — reuse existing IDs, no duplicates
    - `betting/journal/source-log.csv`
    - `betting/journal/learning-log.md`
10e. If no bets: write NO BET TODAY, still update logs.
10f. Every coupon leg MUST include a Polish-language description in parentheses (see betting-artifacts.instructions.md for standard translations). Example: `Over 10.5 corners @ 1.50 (Powyżej 10.5 rzutów rożnych)`.

## STEP 11: VALIDATION (V1-V10) — NEVER SKIP

Run ALL validation checks. If ANY fails, fix it before presenting. This is the QUALITY GATE — it catches every shortcut, missing source, and coupon gap.

11a. V1: Artifact consistency (pick_ids, coupon_ids, stake sums, exposure totals match across all files).
11b. V2: Per-pick validation (Tier A stats source with SPECIFIC data, Tier A market source with SPECIFIC odds, EV > 0, confidence 1-5).
11c. V3-V4: Sport-specific checks (tennis odds ratio, football corner 3-source stack, volleyball ML range, hockey goalie, baseball pitcher, snooker frames, esports maps).
11d. V5: Coupon structure (min 2 legs, same-sport ≤2 per coupon, correlation check, **combined odds ARITHMETIC: multiply each coupon's legs explicitly — never claim verified without showing math**, min 5 coupons).
11e. V6: Portfolio risk (no coupon > 3.00 PLN LR / 2.00 PLN HR, exposure < 25% bankroll).
11f. V7: Weakness flagging (borderline picks, CONDITIONAL, weakest leg per coupon, tournament concentration).
11f2. V7b: Date & fixture verification — confirm EVERY event exists on correct date, correct teams, correct competition. Cross-check on BetExplorer/Betclic.
11f3. V7c: Cross-coupon integrity — no duplicate legs outside pewniaki, no identical coupons, no correlated narratives across coupons.
11g. **V8: Source Completeness Audit (CRITICAL — this catches missed sources):**
     - Every pick has ≥2 independent sources (stats + market minimum).
     - Every pick had ≥1 argument-based tipster site checked (ZawodTyper/Typersi/Meczyki/OLBG/PicksWise/BetIdeas/GosuGamers).
     - Football corners: TotalCorner + SoccerStats + Betclic Statystyki (3-source stack). Missing any → flag.
     - Tennis: TennisAbstract Elo + surface form checked. Missing → flag.
     - MLB: BaseballSavant or pitcher stats source checked. Missing → flag.
     - Esports: Liquipedia or GosuGamers form data. Missing → flag.
     - Snooker: CueTracker frame stats. Missing → flag.
     - Every sport with picks had ≥2 tipster/analysis sites checked.
     - ALL tipster conflicts recorded and addressed in bear case.
     - If tipster consensus <50% for pick direction → explicit justification or removal.
11h. **V9: Coupon Composition Optimization (CRITICAL — this catches suboptimal coupons):**
     - Re-rank picks by EV × confidence. Highest-ranked picks in most coupons (especially pewniaki)?
     - No coupon has ≥3 legs of same market type. Max 2 same-type per coupon.
     - Every active pick in at least 1 coupon (no orphans under NO SINGLES rule).
     - Night coupons contain only night games (≥00:00 CEST).
     - Weakest-leg swap test: for each coupon, can the weakest leg be replaced by a stronger unused pick?
     - Combined odds in sweet spots: pewniaki 2.00-8.00, multi-sport 3.00-10.00, HR 8.00-20.00.
11i. **V10: Final Sign-Off** — ALL V1-V9 pass → PORTFOLIO APPROVED. Any fail → fix and re-check.

---

## REQUIRED RESPONSE

After all artifacts are written, respond with:

1. **Settlement:** X picks settled (Y win, Z loss), N coupons settled
2. **Previous day PnL:** ±X.XX PLN (rolling 7d: ±X.XX PLN, bankroll: XX.XX PLN)
3. **Session:** full/day/night/morning — event window HH:MM → HH:MM
4. **Board:** N events scanned (from scan completeness table: X sports checked, Y total unique events, Z% completeness) → M shortlisted → K approved (L rejected, W watchlist)
5. **Portfolio:** M coupons (pewniaki system: X doubles + Y triples + Z quad + W themed)
6. **Exposure:** X.XX PLN / Y.YY cap (Z.ZZ unused, W.WW% of bankroll)
7. **Source issues:** any outages or stale data
8. Summary table: all tickets with pick_ids, market, odds, stake, EV, confidence
9. **Watch List:** backup picks with promotion criteria
10. **Conditional picks:** list ALL picks requiring manual Betclic odds verification with acceptance thresholds
11. **Validation summary:** V8 source audit result (gaps found/none), V9 coupon optimization result (changes made/none)