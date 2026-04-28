# Learning Log

Rules:
- Append only.
- Record process changes, not emotions.
- Tie every rule change to settled results, source reliability, or repeated pricing issues.
- Keep entries short.

Template:

## YYYY-MM-DD
- Settlement summary:
- What worked:
- What failed:
- Rule changes for future runs:
- Source notes:

No entries yet.
## 2026-04-21
- Settlement summary: none — no picks settled from previous day.
- What worked: source stack availability check completed; Tier A sources accessible except execution bookmaker.
- What failed: Betclic execution price retrieval failed due to dynamic content or geo-blocking; recommend manual odds recheck when composing final picks.
- Rule changes for future runs: add explicit fallback step to recheck bookmaker odds via mobile or alternative access method before finalising picks.
- Source notes: mark Betclic as partial until execution-price endpoint accessible from run environment.
 - Deviation note: live AKO placed today with 2.00 PLN stake (outside default planned split). This was a deliberate one-off decision; resume normal workflow tomorrow.
 - Pre-system bets recorded: added several pre-system coupons from user screenshots into ledgers and report. These were reconciled into `picks-ledger.csv` and `coupons-ledger.csv` and marked `placed` where screenshot showed stake. Continue to require screenshot or bookmaker confirmation for any manual-entry bets.
 - Automated market scan note: attempted automated scan of OddsPortal, BetExplorer, Oddspedia, Flashscore and Sofascore for tonight's candidate lines. Scan was partially blocked by privacy/consent overlays and some endpoints returned errors; plan to use manual recheck for finalisation and add a fallback interactive-check step to the workflow.
- Settlement summary (update 2026-04-21 16:50): Settled 3 failed coupons recorded from user screenshots (tennis AKO + two pre-system AKOs). Total realised PnL: -7.00 PLN. Continue manual verification for coupon-level settlements when screenshot evidence is provided.
- What worked: quick reconciliation from user screenshots; monitor script ready for automated checks where accessible.
- What failed: some aggregator endpoints blocked; cannot rely solely on automated scanning for every bookmaker.

## 2026-04-22
- Settlement summary: Apr 21 settled PnL +13.44 PLN (CP-HR +12.52, CP-05 +7.92, CP-06 -2.00, CP-07 -3.00, CP-08 -2.00). 8 picks still pending (corners/cards).
- What worked: AKO on Brighton+Inter+Real U3.5 was the big winner (+12.52). Combinatorial value in less obvious markets.
- What failed: All tennis picks (PK-16 to PK-22) lost. ITF/low-level tennis is unreliable. Over-games on one-sided matches failed.
- Rule changes for future runs:
  1. Prefer less popular leagues (Austrian BL, Icelandic, etc.) over compressed popular league lines.
  2. Austrian BL shows consistent avg_goals >3.0 — use as systematic league-level trait.
  3. Cup semi-finals: default to UNDER unless data strongly contradicts.
  4. Skip ITF tennis entirely. Only ATP/WTA main draw or strong Challengers.
  5. Check Betclic LAST to avoid 403 rate limiting.
- Source notes: Betclic 403 rate limit hit again (~14:25). Space requests or use app for final verification.
- Rule changes for future runs: accept screenshot-confirmed pre-system bets into ledgers as `placed` and settle only when a confirmed final-status screenshot or two Tier A settlement sources (Flashscore + Sofascore) confirm result.
- Source notes: User screenshots are an acceptable verification source when bookmaker confirmation is not accessible; record ref id and timestamp.
 - Bankroll update: user provided current balance 43.26 PLN. Workflow change: use available balance or configured bankroll as the working bankroll for the next runs (see config/betting_config.json).
 - Operational rule: place bets only that are recorded in the ledger; accept screenshot/bookmaker confirmation for manual entries and settle when two Tier A sources or bookmaker confirmation exist.

## 2026-04-22 (settlement of 2026-04-21)
- Settlement summary: Settled 7 picks as WIN (PK-01, 02, 03, 06, 12, 13, 14) + 7 picks already LOSS (PK-16–22). 8 picks remain pending (corners/cards/minor-league/tennis need manual data). 2 coupons WON: CP-HR +12.52, CP-05 +7.92. 3 coupons LOST: CP-06 -2.00, CP-07 -3.00, CP-08 -2.00. 3 coupons still pending (CP-02, 03, 04). Settled PnL: +13.44 PLN.
- What worked: 3-leg AKO (Brighton + Inter + UNDER 3.5) hit at 7.26x — good combined value from independent top-league picks. Inter single at 4.96x also hit.
- What failed: 7 tennis legs all lost (poor tennis pick accuracy). Corner/card picks remain unsettleable without detailed stats — auto-settlement script cannot handle these.
- Rule changes for future runs:
  - Reduce tennis exposure: tennis legs had 0% hit rate on 2026-04-21. Require stronger Tier-A tennis source evidence before including tennis.
  - Stop recording corner/card picks unless a reliable settlement source for detailed stats is available.
  - Pre-system bets should be tagged distinctly to separate from system-generated picks in performance analysis.
- Source notes: Flashscore results pages successfully parsed for PL, LaLiga, Coppa Italia, Ligue 1, Championship. Rotherham vs Luton not found in Championship (likely League One — competition field was wrong in ledger).

## 2026-04-22 (codebase audit)
- Settlement summary: no new settlements — codebase audit day.
- What worked: identified and fixed critical bugs across all scripts.
- What failed (fixed):
  - adapters/__init__.py: broken __import__() calls crashed the adapter system — replaced with proper Python imports.
  - site_selectors.json: invalid JSON (two concatenated objects) — merged into one valid JSON.
  - settle_on_finish.py: hardcoded to one match, operator precedence bug in match winner logic, hardcoded totals threshold at 3.5 — rewritten as generic settlement with dynamic line parsing, BTTS/DC support, CLI args, and coupon settlement.
  - aggregate_and_select.py: `or True` in market filter included all sources as market sources (bypassing Tier-A requirement); import inside loop; no config loading; no risk-tier differentiation — rewritten with proper Tier-A filtering, fuzzy match dedup, config-driven allocation, and risk tiers.
  - scan_events.py: no rate limiting between fetches, deprecated datetime.utcnow() — added 3s delay, error log output, progress counter.
  - fetch_with_playwright.py: deprecated datetime.utcnow(), no user-agent rotation — fixed timezone, added UA rotation and viewport/locale.
  - quick_betclic_extract.py: picked lowest-odds favorites instead of value — rewritten to prefer 1.30-3.50 range with source-count weighting.
  - requirements.txt: pinned playwright breaking upgrades — changed to >=1.45.0.
  - run_full_scan_and_prepare.sh: no error handling, no timing info — added pipeline steps, timing, error summary, graceful failure handling.
- Rule changes for future runs:
  - Use `settle_on_finish.py --betting-day YYYY-MM-DD` for targeted settlement instead of editing the script per match.
  - Check `betting/data/scan_errors.json` after every orchestrator run for source availability issues.
  - Config thresholds (price gap, max legs, odds range) are now in config/betting_config.json — change config not code.
- Source notes: all adapter domains now mapped in adapters/__init__.py (predictz, bettingexpert, zawodtyper, oddspedia, betexplorer added).

## 2026-04-22 (full analysis run — rerun with tennis + multi-coupon)
- Settlement summary: no new settlements.
- What worked: expanded analysis to include tennis over-games totals. BetExplorer provides Tier A market odds for ATP/WTA Madrid. Identified 5 competitive tennis matches (match odds 1.50-2.50 range) suitable for over 20.5 games market on clay.
- What failed: previous run incorrectly blocked all tennis. User correction: over-games direction is viable even though 7 specific ITF picks lost. The concept (evenly matched best-of-3 on clay → 3 sets → over games) is statistically sound.
- Rule changes for future runs:
  - Tennis over-games totals are approved when match odds are between 1.50 and 2.50 (indicating competitive match with high 3-set probability). Apply strict ratio grading: STRONG ≤1.15, GOOD 1.16–1.30, BORDERLINE 1.31–1.50, REJECT >1.50. Drop BORDERLINE picks from portfolio.
  - Build multiple coupons with ZERO event overlap — this maximizes diversification and overall win probability vs repeating events. Tennis-only coupons must be labeled low-risk (cannot meet higher-risk min 2 sports requirement).
  - Use BetExplorer tennis tournament pages for Tier A match odds (1X2 for both players). Combined with Flashscore fixture data, this satisfies the Tier A requirement for tennis picks.
- Source notes: BetExplorer tennis pages work well for match odds (ATP + WTA Madrid). Forebet tennis predictions return 404 — not available.

## 2026-04-22 (portfolio rebuild — analysis-first approach)
- Settlement summary: no new settlements this run.
- What worked: reversed workflow to build picks from Forebet/BetExplorer data FIRST, then plan minimal Betclic verification. Avoided rate limiting entirely.
- What failed: all 10 original picks and 4 coupons from earlier run were invalid — tennis O20.5 lines do not exist on Betclic (max O17.5 for qualifying), and match O2.5 prices too compressed (1.27-1.32 vs estimated 1.45-1.60). All Madrid tennis matches started by 11:00 before portfolio was ready.
- Rule changes for future runs:
  - ALWAYS build portfolio from analytical sources first, then verify on Betclic last with minimal page loads (target 3-5 pages max per verification run).
  - Team totals (e.g. Barcelona O2.5, Man City O2.5) often offer better value than match totals when one team is a massive favorite. Match O2.5 gets compressed but team O2.5 stays at higher odds.
  - For Madrid tennis qualifying: morning session starts 11:00 local. If picks depend on qualifying matches, compose and place before 10:30 or skip.
- Source notes: Betclic 403 rate limit clears after ~15 minutes. HTML snapshots from verification runs are valid for team totals and BTTS market extraction.

## 2026-04-22 (deep statistical analysis — user philosophy update)
- Settlement summary: no new settlements this run. All 33 earlier Apr 22 picks voided; clean slate.
- What worked: Deep multi-source statistical workflow. Betclic Statystyki HTML snapshots (corners/cards/fouls/shots) for Barca, City, Leverkusen. SoccerStats league-level corner rankings and defensive profiles across 7 leagues. TotalCorner match-level corner totals/handicaps for 11 matches. BetExplorer market-best odds cross-validation. Multi-sport diversification (football + volleyball).
- What failed: Betclic Statystyki tab only available for top 3 leagues (EPL, LaLiga, Bundesliga). Championship, Austrian BL, Coppa Italia, Coupe de France have NO statistical markets on Betclic. BetExplorer Playwright scraping intermittent (403s, timeouts). Cannot auto-verify Betclic odds for non-statistical matches.
- Rule changes for future runs:
  1. Statistical markets (corners, cards, fouls, shots) are PRIMARY picks. Goals/BTTS/1X2 are SECONDARY, only used when statistical markets unavailable.
  2. For non-statistical matches, use CONDITIONAL odds with minimum acceptance threshold. User verifies on Betclic app.
  3. Source stack for corner analysis: TotalCorner (match totals) + SoccerStats (league rankings) + Betclic Statystyki (verified odds). All 3 needed for high-confidence corner pick.
- Source notes: TotalCorner free tier provides match-level corner totals and handicaps for all leagues — extremely valuable. SoccerStats provides league-level corner team rankings. Betaminic accessible for team-level corner/card stats tables.

## 2026-04-22 (settlement + overnight coupons)
- Settlement summary: 11 picks settled (10W 1L = 90.9%). 5 coupons settled (4W 1L = 80%). Day PnL: +7.77 PLN. Balance: 43.26 → 51.03 PLN.
- What worked:
  1. Statistical markets dominated: corners 3/3, U2.5 defensive profiles 2/2, BTTS 1/1, volleyball 2/2, DC 1/1, O2.5 1/1. Total 10/11 = 90.9%.
  2. Corner three-source stack (TotalCorner + SoccerStats + Betclic Statystyki) delivered 3/3. This is the highest-confidence pick type.
  3. Multi-sport diversification (football + volleyball) worked perfectly.
  4. CONDITIONAL odds approach (user verifies on app) is practical and avoids rate limiting.
  5. Defensive profile plays (U2.5 backed by SoccerStats league data) are high-probability.
- What failed:
  1. Only loss was Strasbourg DC (1X) in CP-HR2 — a form-based pick, NOT a statistical market. Nice won 2-0.
  2. Betclic rate limiting (403) continues to block automated odds verification.
- Rule changes for future runs:
  1. Statistical markets (corners, U2.5 defensive, BTTS, volleyball totals) are confirmed PRIMARY picks. Non-statistical picks (DC, ML) are supplementary only.
  2. The loss pattern is clear: form-based DC/ML picks without statistical backing are the weak link. Downgrade non-statistical picks to HR-only.

## 2026-04-23 (night session — REVISED v2)
- Settlement summary: no new settlements. Corners/cards picks require manual stats from Flashscore match detail pages.
- What worked: REVISED — full sport-by-sport scan found 2 additional NHL candidates (Kings-Avalanche U5.5, Senators-Hurricanes U5.5). Hockey-reference GF/GA data enabled proper EV calculation. PicksWise provided tipster validation (supported Senators U5.5, contradicted Kings U5.5).
- What failed:
  1. CRITICAL ERROR: Original analysis only scanned 2 events (Hawks-Knicks, Bruins-Sabres) and declared NO BET. Missed 2 actionable NHL games + full MLB slate.
  2. BetExplorer data-dt field confusion: initially counted 28+ football matches as upcoming, but most were from previous days (data-dt showed April 22, not 23/24). Proper data-dt filtering is essential.
  3. ESPN scraping blocked by cookie consent overlay.
- Rule changes for future runs:
  1. MANDATORY: Night sessions must run FULL sport-by-sport scan — same rigor as day sessions. NEVER limit to just 1-2 games.
  2. When parsing BetExplorer HTML, always filter by data-dt to distinguish upcoming from finished matches.
  3. NBA Playoffs: apply playoff adjustment factor (-10 to -15 pts from season average) for totals.
  4. When tipster (PicksWise) contradicts stats thesis, reduce confidence by 1 point but don't auto-reject if Tier A stats are strong.
  5. Accept cookie consent overlays on ESPN by clicking accept button in Playwright.
- Source notes: hockey-reference.com is excellent for NHL GF/GA (Tier A). ScoresAndOdds provides team O/U records. OddsPortal reliable for NHL 1X2 odds.
  3. For overnight/MLS sessions: use BetExplorer standings as primary source. MLS table gaps (top-5 vs bottom-5) provide actionable edge.
  4. DC United (4GF in 8 = 0.5/game) and Orlando City (25GA in 8 = 3.125/game) are extreme statistical outliers — usable for Under and opponent ML plays.
  5. Betclic correct URLs: football = football-sfootball/usa-mls-c504, NBA = basketball-sbasketball/nba-c13.
- Source notes: BetExplorer MLS standings reliably available. Betclic MLS and NBA pages confirmed at user-provided URLs. Flashscore still 403.

## 2026-04-23
- Settlement summary: Apr 22 night MLS session settled: 0W/3L picks, 0W/2L coupons. Night PnL: -2.50 PLN. Apr 22 total: +5.27 PLN. PK-07 Rotherham DC settled WIN. Rolling 7d: +18.71 PLN.
- What worked: Apr 22 day session (90.9% hit rate) validated statistical markets approach. Bankroll grew to 51.03 PLN.
- What failed:
  1. MLS night picks: 0/3. Charlotte lost 4:1 to Orlando (despite Orlando worst-defense narrative). Toronto drew 3:3 (despite Philly worst form). DC United scored 4 goals vs 0.50/game average. MLS variance is extreme.
  2. Betclic 403 rate limiting continues — cannot verify odds from agent environment.
  3. Existing Apr 23 picks from previous run (Leipzig, Betis-RM, Napoli, Brest-Lens) all referenced Apr 24 matches — betting-day window was applied incorrectly in that run.
- Rule changes for future runs:
  1. MLS is unreliable for ML and U2.5 picks. Require at least 2 Tier A stats sources (not just BetExplorer standings) for MLS.
  2. Verify NBA game schedules before composing night picks — Detroit ML was pending because game may not have been scheduled.
  3. Triple-check betting-day window: matches must kick off between 06:00 run_date and 05:59 next day local time. Evening matches in Europe are typically next-day in source listings but are within the window.
  4. When source data is thin (e.g., midweek with few matches), prefer fewer higher-confidence picks over filling a quota. 4 tickets from 7 picks is acceptable when only 5 football + 2 tennis + 1 volleyball qualify.
- Source notes: SoccerStats La Liga/Eredivisie league stats available. BetExplorer 1X2 odds available for all sports. Covers NBA pages empty. Forebet returned empty for today. TotalCorner not yet loaded for tomorrow.

## 2026-04-23 (methodology overhaul — user directive)
- Settlement summary: User-placed night AKO (5.00 PLN, 8.81x, 4-leg) settled LOSS (-5.00 PLN). Detroit ML WON but 3 legs lost. Total night losses: -7.50 PLN. Apr 22 final: +0.27 PLN.
- What worked: Detroit ML analysis was correct (98:83). Statistical market approach (corners/BTTS) continues 90% day-session hit rate.
- What failed: Night MLS analysis was shallow and ineffective — 0/3 MLS picks. Analysis relied on surface-level standings without checking tipster consensus or specialist MLS sources. User correctly flagged this as unacceptable.
- Rule changes (MAJOR USER DIRECTIVE — permanent):
  1. NEVER reject a sport for "lack of sources." The internet has specialist sites for every sport (esports: HLTV, Liquipedia; snooker: CueTracker; table tennis: tt-series.com; darts: DartsOrakel; etc.). Always search for them.
  2. MANDATORY wide tipster cross-check: check Zawod Typer, Trafiamy, Typersi, Protipster, Tipstrr, Blogabet, OLBG, FootySupertips, PicksWise, Windrawwin, BetIdeas, bettingexpert for every candidate. These sites provide angles and perspectives statistics miss.
  3. Avoid popular high-profile events for pure match-result bets. Focus on deep statistical markets and analytical perspectives. Never produce shallow analysis.
  4. Goal is MANY coupons with varying risk/stake/sport coverage — not a few conservative ones. Diversify broadly: football, tennis, basketball, volleyball, esports, snooker, table tennis, darts, handball, MMA.
- Source notes: Added 20+ new sources to source-registry.md. Updated config to include 12 sports. Updated all instruction files.

## 2026-04-23 (deep analysis rerun)
- Settlement summary: No new settlements. Apr 22 fully settled (+0.27 PLN). Bankroll 46.03 PLN.
- What worked:
  1. SoccerStats deep dive: La Liga + Eredivisie O2.5%, BTTS%, home/away splits, FTS rates all available and rich.
  2. TennisAbstract clay-specific analysis: Atmane's 40% clay win rate is a strong contrarian signal supporting Kecmanovic ML.
  3. CueTracker snooker H2H: Murphy-Xiao 4-2 record with frame-by-frame data available.
  4. PSV O2.5 at 83% season rate = highest-confidence pick on the board (conf 5).
  5. BetExplorer 1X2 odds available across all competitions for price gap checking.
- What failed:
  1. Tipster sites massively blocked: FootySupertips (DNS), Windrawwin (redirect), Forebet (Cloudflare), Protipster (Cloudflare), Oddspedia (Cloudflare), BettingExpert (nav issue). 7/7 tipster sites failed. Tipster consensus check impossible.
  2. NBA/esports/darts data unavailable: Covers empty, HLTV empty, no darts odds on BetExplorer. These sports cannot be analyzed without data.
  3. Only 4 constructs produced vs target of 5 coupons. Board limited by sport data availability.
  4. Wilson vs Allen (snooker) dropped from HR2 coupon due to missing H2H stats — CueTracker not checked for that pair.
- Rule changes for future runs:
  1. Accept that tipster consensus is currently impossible due to Cloudflare/DNS blocks. Do not force it. Rely on Tier A stats sources which remain accessible.
  2. When targeting many coupons, prioritize collecting data for multiple sports early in the scan phase.
  3. CueTracker H2H should be checked for ALL snooker candidates, not just the most obvious one.
- Source notes: SoccerStats, BetExplorer, TennisAbstract, CueTracker, OddsPortal all reliable Tier A. Flashscore schedule data reliable. All tipster Tier B sites blocked.

## 2026-04-23 (v2 statistical markets rebuild)
- Settlement summary: no new settlements. PK-01 through PK-06 voided (generic markets replaced). CP-LR1/HR1 voided.
- What worked:
  1. TotalCorner match-level corner handicaps: PSV -2.25, GA Eagles +0.25, Oviedo-Villarreal +0.25, Rayo-Espanyol -0.25. Directly actionable for corner O/U lines.
  2. BetExplorer tennis set-score histories: confirmed 3-set rates for Atmane (47%) and Kecmanovic (56%) supporting O21.5 games.
  3. Multi-sport diversification: football corners + tennis game totals + snooker frame totals across 3 coupons + 3 singles.
  4. Corner priority fully implemented: 4/8 picks are corners, 2/8 game totals, 1/8 BTTS, 1/8 frame totals. Zero generic O2.5 goals or raw ML.
- What failed:
  1. SoccerStats team pages (team.asp) returned empty for corner/card data — only league-level stats available.
  2. FBref miscellaneous stats returned empty for La Liga/Eredivisie.
  3. BetExplorer upcoming match pages have no Corners/Cards tabs — only available for completed matches.
  4. Forebet corner predictions blocked by Cloudflare.
- Rule changes (permanent):
  1. **STATISTICAL MARKETS ARE THE FOUNDATION.** Priority: corners > cards > fouls > shots > team totals > BTTS > DC > goals O/U. For tennis: game_totals > set_totals > games_handicap > ML. For snooker: total_frames > frame_handicap > ML.
  2. Never produce O2.5 goals or raw ML as primary picks. These are last-resort fallbacks only.
  3. TotalCorner is the primary source for match-level corner analysis. SoccerStats for league-level rankings. Combined = sufficient for corner picks even without Betclic Statystyki tab.
  4. Fish shell does NOT support heredocs (`<< 'EOF'`). Always use Python for multi-line file appends.
- Source notes: TotalCorner confirmed as most reliable corner source (free tier). SoccerStats league-level only. BetExplorer corners only for historical matches.

## 2026-04-23 (v7 midday update)
- Settlement summary: PK-08 (Atmane vs Kecmanovic O21.5 games) VOIDED — match started at 12:10 while portfolio was being finalized. 7 coupons containing PK-08 voided. 1 triple dropped (3 same-sport legs rule).
- What worked:
  1. Early detection of live match via BetExplorer scan (showed "1S 0:0" status).
  2. 3 remaining pewniaki (PSV corners, Oviedo corners, Nordsjaelland BTTS) all conf 4-5 with Tier A backing.
  3. Streamlined portfolio: 1 single + 3 doubles = 6.00 PLN (13% bankroll). Clean, low-correlation.
- What failed:
  1. Tennis match started before portfolio could be placed. Need to compose portfolios EARLIER for morning-session tennis matches.
  2. Pewniaki system with 4 picks generates too many coupons (11) — operational overhead. With 3 picks, 3 doubles is manageable.
  3. 3 same-sport rule caught in validation (V5 failure for ACD triple) — good that V1-V8 checks are working.
- Rule changes:
  1. For ATP/WTA Madrid: qualifying/R128 matches start 11:00-12:00 local. Portfolio must be finalized by 10:30 if including tennis.
  2. Max pewniaki for combinatorial system: 4 is practical. 5+ generates too many combos.
  3. When a key pick is voided mid-workflow, immediately rebuild portfolio with remaining picks rather than continuing full analysis.

## 2026-04-23 (fresh procedure rerun v3)
- Settlement summary: Apr 22 fully settled (+0.27 PLN). Apr 21 pending 7 picks VOIDED (unsettleable). Apr 23 prior 20 picks + 21 coupons VOIDED for fresh rerun. Bankroll: 46.03 PLN.
- What worked:
  1. Full orchestrator (53 URLs, 988 matches, 49 sources OK, 4 failed) gives comprehensive scan in ~5 min.
  2. SoccerStats BTTS/goals distributions are EXCELLENT for BTTS No thesis (Oviedo 68% BTTS No rate = massive edge).
  3. BetIdeas provided specific contrarian picks (BTTS No) that aligned with statistical analysis.
  4. PicksWise NBA expert picks (Hawks ML, Nuggets ML, Raptors ML) with reasoning available.
  5. basketball-reference ORtg/DRtg data enables EV estimation for NBA.
  6. Multi-source tipster cross-check (Typersi + BetIdeas + PicksWise) provides consensus/contrarian signals.
- What failed:
  1. BetExplorer match-level pages (O/U, BTTS tabs) returned consent/GDPR wall content — could not extract specific market odds.
  2. OddsPortal specific match pages empty (JS rendering issue).
  3. Betclic search function broken for match lookup — all 6 picks returned NOT FOUND.
  4. BetExplorer snooker/esports/darts/table-tennis endpoints return empty 39-char responses.
  5. Covers.com NBA/NHL matchup pages mostly empty (JS-heavy, not fully rendering).
  6. Sportsgambler match prediction pages return generic navigation content.
- Rule changes for future runs:
  1. BTTS No thesis is strongest when team has <1.0 GF/game AND >60% BTTS No rate. Oviedo fits perfectly.
  2. For market-level odds (O/U, BTTS), use BetExplorer competition page (not match page) — competition pages render correctly.
  3. BetIdeas contrarian picks should FLAG a pick (coupon only, not single) rather than reject it — contrarian can be wrong.
  4. Pewniaki system (all combinations of top 3) is effective portfolio construction — covers partial wins.
  5. NBA ML picks work as HR coupon diversifiers but not as singles (true probability hard to estimate precisely).
- Source notes: 19 working, 4 failed, 11 blocked. Key: SoccerStats + TotalCorner + BetExplorer competition pages = reliable football data stack. basketball-reference + hockey-reference = reliable US sports stats.

## 2026-04-23 (source audit + philosophy overhaul)
- Settlement summary: no new settlements this entry. Prior entries cover Apr 23 settlement.
- What worked:
  1. SBR (sportsbookreview.com) Totals tab provides NHL/NBA/MLB/NFL O/U lines + American odds from 6+ books. No GDPR wall, renders in Playwright.
  2. ESPN Odds (espn.com/nhl/odds, /nba/odds, /mlb/odds) provides totals + moneylines for US sports. Accessible from EU/PL IP.
  3. ScoresAndOdds (scoresandodds.com) provides totals + line movements for US sports. Accessible from EU/PL IP.
  4. Multi-source validation caught line discrepancies: SBR showed BOS@BUF O6.0 while ESPN showed O6.5 — confirms need for 2+ sources.
  5. American odds conversion (positive +X → 1 + X/100; negative -X → 1 + 100/X) enables proper decimal odds comparison.
- What failed:
  1. BetExplorer NHL match pages → GDPR consent wall with no odds extracted. Match-level pages are unreliable for US sports.
  2. OddsChecker, DraftKings, FanDuel, Betfair, Pinnacle all geoblocked from EU/PL IP. These US-only sportsbooks return empty responses.
  3. Covers.com NBA/NHL pages render mostly empty (JS-heavy, partial access).
  4. Single-source reliance led to incorrect line (O5.5 from one source when consensus was O6.0).
- Rule changes (PERMANENT — embedded in all instruction files):
  1. **NO SINGLES.** All picks go into coupons. Minimum 2 legs per coupon. Minimum 5 coupons per day.
  2. **NEVER give up on source failures.** Follow the Odds Source Map: Primary → Secondary → Tertiary → Fallback → internet search. The internet ALWAYS has data.
  3. **Minimum 2 independent sources per pick for cross-validation.** SBR vs ESPN vs ScoresAndOdds for US sports. BetExplorer vs OddsPortal for EU sports.
- Source notes: Added SBR, ESPN Odds, ScoresAndOdds as Tier A market sources. Added The-Odds-API as universal fallback. Documented all geoblocked sources. Updated Odds Source Map by Sport table in source-registry.md.

## 2026-04-23 (run 2 — portfolio construction)
- Settlement summary: Apr 22 fully settled. Day PnL +7.77, Night PnL -7.50, Total +0.27. Bankroll 45.27 PLN.
- What worked:
  1. Home/away split analysis caught a false BTTS signal: LEV-SEV BTTS Yes looked +17% EV on aggregate but was -25% EV with proper away splits (Sevilla away 1.00 GF/game). CRITICAL discovery.
  2. Poisson model with H2H lambda (3.07 for LEV-SEV) provides more reliable O2.5 estimates than league averages.
  3. BetExplorer match pages NOW rendering correctly with Playwright (match IDs from league pages). Fixed by navigating from league page to find correct match URLs with unique IDs.
  4. Pewniaki system (all 3-pick combinations: 3 doubles + 1 triple) provides 4 low-risk coupons efficiently.
  5. Oviedo BTTS No (0.77 GF/game) = strongest statistical signal today. P(BTTS No) = 69.5%, EV +39%.
- What failed:
  1. BetExplorer O/U and BTTS tabs for Eredivisie/Denmark matches show no Betclic odds (smaller leagues not covered).
  2. NHL O/U odds from BetExplorer extracted wrong values (18.00 / 1.05 — picked up wrong bookmaker or misread). SBR remains better for NHL totals.
  3. NBA/NHL ML odds not found on BetExplorer match pages (possibly US sportsbooks not listed or format issue).
  4. Fish shell heredoc syntax incompatible — caused multiple script creation failures. Always write scripts via Python or file editor.
- Rule changes:
  1. ALWAYS use home/away splits for BTTS analysis. Overall GF/game is misleading. P(BTTS) = P(home team scores) * P(away team scores away).
  2. For smaller leagues (Eredivisie, Denmark SL), Betclic odds must be verified on app — BetExplorer does not list them.
  3. Continue using SBR + ESPN + ScoresAndOdds for US sports totals instead of BetExplorer match pages.
- Source notes: BetExplorer match pages work for LaLiga/DFB Pokal (top leagues). Not reliable for Eredivisie/Denmark. PicksWise provided expert NHL+NBA picks with reasoning.

## 2026-04-23 (post-loss correction — tennis lesson)
- Settlement summary: PK-68 (Vallejo vs Dimitrov O21.5 games) confirmed LOSS by user. PK-69 (Trungelliti vs Merida O21.5) had NEGATIVE EV (-0.038) — hard rule violation, should never have been included. 2 coupons dead: CP-23-MS1 (-1.00 PLN), CP-23-HR1 (-0.50 PLN). Loss: -1.50 PLN. 5 coupons survive.
- What worked:
  1. ZawodTyper deep extraction found GOLD data for PK-65 (Rayo-Espanyol cards): referee Cordero Vega avg 26.44 fouls/season, Rayo 13.2 + Espanyol 13.8 = 27 avg fouls, H2H 7/9 covered O24.5 fouls. Confidence boosted 4→5.
  2. All football picks (PK-60, 63, 64, 65) had some level of tipster validation from ZawodTyper.
  3. Surviving coupons (P1-P4, MS2) have strong football core confirmed by tipster consensus.
- What failed:
  1. PK-68 had thin EV (+0.044) and failed the "20% lower odds" test. No tipster covered tennis on ZawodTyper (0/75 tips). Should have been confidence 3, not 4.
  2. PK-69 had NEGATIVE EV — this is an automatic skip per hard rules. Including it was a methodology violation.
  3. STEP 4 (tipster deep-dive) was done superficially in original v3 analysis. Deep ZawodTyper extraction was not performed until post-loss correction.
- Rule changes (PERMANENT):
  1. Tennis O21.5 requires EV > +0.08 minimum (not just >0). Thin-edge tennis picks are not worth the variance.
  2. ZERO tipster coverage on argument-based sites = automatic confidence reduction of -1. If no tipster anywhere discusses the event, it signals low market interest and higher uncertainty.
  3. STEP 4 must include FULL argument extraction from ZawodTyper (scroll deep, read each tipster's reasoning, extract referee/H2H/tactical data). Superficial "no tips found" is unacceptable.
- Source notes: ZawodTyper 20260423T135931Z.html contains 75 tips with full analyses. Key data: referee names, foul averages, H2H patterns, tactical context. This source is invaluable when properly mined.

## 2026-04-23 (v4 — placed coupons with real Betclic odds, KILL SWITCH lesson)
- Settlement summary: PK-78 (Atmane O21.5) WON (live bet, 6-7 4-5). PK-68 LOST (-1.50 PLN from 2 dead coupons). 9 coupons pending across 11 placed coupons total.
- What worked:
  1. PK-63 (Sonderjyske corners) Betclic @1.73 was BETTER than est @1.70 (+1.8%). Positive surprise.
  2. PK-64 (Wieczysta O10.5 corners) Betclic @1.80 exact match with estimate. Reliable.
  3. Live tennis bet (Atmane O21.5 @1.30 with 22 games already played) was guaranteed — smart opportunistic play.
- What failed:
  1. **CRITICAL FAILURE: No KILL SWITCH before placing.** User placed 8 coupons based on estimated odds without verifying Betclic actuals first. Three picks had severely negative EV at real Betclic odds:
     - Wilson O20.5 frames: est @1.75 → Betclic @1.35 (-23%). EV: -0.16.
     - Istanbul O3.5 sets: est @1.85 → Betclic @1.28 (-31%). EV: -0.26.
     - Fuchse O63.5 goals: analyzed O53.5, Betclic offered O63.5 (different line entirely!).
     - Bruins team O5.5 @6.75: different market (team goals incl OT, not match goals).
  2. Rayo cards O4.5: est @1.70 → Betclic @1.58 (-7%). Still marginally positive EV but weaker.
  3. Agent was not running in bet-analyst mode for prior iterations, leading to less rigorous analysis.
- Rule changes (PERMANENT — KILL SWITCH PROTOCOL):
  1. **NEVER place coupons until real Betclic odds are verified.** Agent provides estimates. User checks Betclic app. User reports actuals. Agent runs KILL SWITCH (EV recalculation at real odds). Only then place.
  2. **If Betclic line differs from analyzed line by more than 2 goals/sets/frames/points, it's a DIFFERENT PICK.** Re-analyze from scratch. Fuchse O63.5 ≠ O53.5. Bruins team O5.5 ≠ match O5.5.
  3. **Bankroll tracking must be real-time.** 45.27 → 30.00 → 29.00 was tracked too slowly. Config must reflect actual balance after each placement.
- Source notes: Screenshots from Betclic app are the ONLY reliable odds source. All estimates are CONDITIONAL.

## 2026-04-23 (night session — superseded by REVISED v2 above)
- Original NO BET call was wrong — failed to scan all sports. See revised v2 entry above.
- Retained lessons: SBR (sportsbettingresearch.com) domain is DEAD. Use sportsbookreview.com. Track cumulative daily exposure in real-time.
- Source notes: SBR scan returned GoDaddy parking page. ESPN and ScoresAndOdds remain viable for US sports odds.

## 2026-04-24 v5 — Deep Scan Protocol First Execution
- **Process change: Deep Scan Protocol (§1.2) implemented and VALIDATED.**
  - v4 scanned ATP Madrid superficially → only 1 tennis pick (PK-206 Shelton ML, odds uncertain).
  - v5 applied Deep Scan: calculated odds ratio for ALL 32 Madrid matches → found 4 STRONG/GOOD O-games candidates.
  - Result: 4 new tennis picks with EV ranging +0.122 to +0.254 (highest new-pick EV in portfolio).
  - Lesson: **Odds ratio grading is the single most effective tennis screening tool.** Ratio ≤1.25 = GOOD/STRONG. Ratio >1.50 = REJECT. Saves time and finds value mechanically.
- **Process change: Scan Completeness Metrics (§1.5) enforced.**
  - 233 total events counted across 12 sports (10 with events, 2 confirmed empty).
  - Cross-validation between BetExplorer and Flashscore confirmed.
  - Gate: ≥50 events → 233 ✓. ≥80% sports → 100% ✓.
  - This gate prevents shallow scanning that plagued v1-v4 analyses.
- **Non-tennis deep analysis yielded 0 new picks.**
  - 12 candidates from esports, handball, hockey (non-NHL), basketball, baseball (NPB/KBO), additional football analyzed.
  - All rejected for negative EV or missing Tier A sources.
  - This is CORRECT — no forcing action. Madrid tennis is the clear value pocket today.
- **PK-206 Shelton ML downgraded to watchlist.**
  - Deep scan revealed Shelton may be priced at ~1.29 (heavy favorite), not 1.57 as estimated in v4.
  - Lesson: Always verify heavy favorite ML odds before including. If <1.40, reject for no value.
- Source notes: TotalCorner cookie wall persists across all sessions. De facto non-functional for this workflow. ZawodTyper + SoccerStats sufficient for 2/3 corner stack.

## 2026-04-24 — POST-MORTEM: Shelton ML & Struff O22.5 losses (user-placed coupons)

### Settled results from user screenshots:
- **AKO(7)**: 7-leg coupon — LOST. Killed by Ben Shelton ML @ 1.61. Stake: ~2-3 PLN.
- **AKO(2)**: 2-leg coupon — LOST. Killed by Ben Shelton ML @ 1.41. Stake: 2.00 PLN. Ref: 69eb557c.
- **AKO(3)**: 3-leg coupon — LOST. Killed by Struff-Michelsen O22.5 games @ 1.71. Stake: 1.00 PLN.

### What failed:

**1. Ben Shelton ML (PK-111/206/606 across versions)**
- Match: Shelton lost 4-6, 7-6, 6-7 to Prizmic. 3 sets, 36 total games.
- CRITICAL: If O22.5 games was used instead of ML, it would have WON by 13.5 games margin.
- The match was EXTREMELY competitive (3 tiebreak-level sets) = perfect for game totals, terrible for ML.
- Shelton appeared in 2 separate placed coupons → concentration risk violation.
- AKO(7) had 6 other legs that may have all won. Shelton ML alone killed a potential 15-25 PLN return.
- Root cause: pick created in v5 era BEFORE the universal ML ban. User placed from old analysis.

**2. Struff vs Michelsen O22.5 games (PK-403/809)**
- Match: Michelsen won 6-2, 6-1 = only 15 games. Miss by 7.5 games.
- Odds ratio was 1.22 (GOOD, not STRONG). 30% straight-set probability.
- Bear case predicted "Michelsen clay inexperience → quick loss" but actual direction was opposite: Michelsen DOMINATED.
- Pick had "zero tipster backing" and "thin EV (+0.155)" — both should have been REJECTION signals.
- Struff age (34) vs Michelsen power (21) on Madrid altitude clay = recipe for blowout.
- Root cause: GOOD ratio used for O22.5 line (too aggressive). Need STRONG ratio (≤1.15) for O22.5+.

### Rule changes (MANDATORY for future runs):

1. **Tennis game totals — line/ratio matrix (NEW):**
   - O22.5+ games: ONLY with STRONG ratio (≤1.15)
   - O21.5 games: GOOD ratio (≤1.25) acceptable
   - O20.5 games: GOOD ratio (≤1.30) acceptable
   - BORDERLINE ratio (1.31-1.50): WATCHLIST ONLY, never main pick

2. **"Zero tipster backing" = automatic rejection (REINFORCED):**
   - Any pick with zero tipster arguments → automatic downgrade to watchlist
   - Thin EV (+0.10 or less) + no tipster support = HARD REJECT

3. **Cross-coupon concentration cap (REINFORCED):**
   - Same player/team in max 2 coupons (pewniaki system excepted)
   - Same pick failing in 2+ coupons = correlated loss = portfolio damage

4. **ML ban CANONICAL CASE:**
   - Shelton ML is now the textbook example. 36 games played, O22.5 wins with massive margin, ML loses.
   - User quote: "BAZUJEMY NA STATYSTYKACH ZAWSZE!" — confirmed by real money loss.
   - This case study should be referenced whenever ML temptation arises in any sport.

5. **7-leg coupons: extreme caution (NEW):**
   - 7 legs × 70% per leg = only 8.2% overall probability
   - Only acceptable if ALL legs are high-confidence (≥4) statistical markets
   - Prefer splitting into 2-3 smaller coupons

### Damage estimate:
- Direct stake loss: ~5 PLN
- Opportunity cost (if other legs hit): potentially 20-30 PLN unrealized returns
- Both losses were preventable with current rules (ML ban + ratio matrix)

## 2026-04-24 — DEEP ANALYSIS: Upset Prediction Framework (all sports)

### Was Shelton's loss predictable? YES — 8.5/10 on upset checklist.

**Red flags that were present but ignored:**
1. **Surface mismatch (+2):** Shelton is a hard-court power player. Clay titles ONLY at 250-level (Houston, Munich — weak fields). Never deep at Madrid/RG Masters level.
2. **Rising underdog (+2):** Prizmic at career-high #87, just won Challengers, NextGen finalist 2025, qualified at Indian Wells 2026. Peak trajectory.
3. **Giant-killer history (+1):** Took Djokovic to 4 sets at AO 2024 (longest Djokovic R1 ever). Beat Lehečka #30 at Stockholm.
4. **Age advantage (+0.5):** Prizmic 20yo in breakthrough phase — no fear, peak fitness, recovers from qualifying fast.
5. **Favorite's tournament history (+1):** Shelton has no known deep run at Madrid Masters on clay.
6. **Qualifier match fitness (+0.5):** Qualifiers are match-sharp and confident after 2-3 wins. Not tired.
7. **First H2H meeting (+0.5):** No data = uncertainty.
8. **Serve dependency on clay (+1):** Shelton's 150mph serve is neutralized on slow clay. His biggest weapon loses 30%+ effectiveness.
- **Prizmic's profile:** Junior Roland Garros champion. ALL 3 Challenger titles on CLAY. Born clay specialist.

### NEW — Tennis Upset Risk Checklist (score 0-10):
| Factor | Points | Check |
|--------|--------|-------|
| Surface mismatch | 0-2 | Favorite's surface win% 10%+ lower than overall? |
| Rising underdog | 0-2 | Career-high ranking? Won event in last 4 weeks? |
| Giant-killer history | 0-1 | Any top-20 scalps or competitive top-10 losses? |
| Age/trajectory advantage | 0-1 | Underdog ≤22yo in breakthrough phase? |
| Favorite's tournament history | 0-1 | Best result at this event worse than QF? |
| Qualifier match fitness | 0-0.5 | Underdog came through qualifying? |
| First H2H meeting | 0-0.5 | No prior data = uncertainty |
| Serve dependency on clay | 0-1 | Favorite's game based on serve, playing on clay? |

**Thresholds:** ≥4 = AVOID ML, use game totals. ≥6 = Extra caution even on totals. ≥8 = SKIP or only STRONG ratio O-games.

### NEW — The Paradox Rule (CRITICAL INSIGHT):
**High upset risk makes STATISTICAL MARKETS MORE profitable:**
- Competitive match = more total play (games, frames, sets, goals, corners)
- Shelton-Prizmic: 36 games. O22.5 wins by +13.5 margin.
- Football relegation battles: more fouls = more cards, more corners from desperate play.
- NBA close games: more possessions, OT risk = higher totals.

**Low upset risk makes statistical OVERS dangerous:**
- Blowouts = low total play. Struff-Michelsen: 15 games. O22.5 missed by -7.5.
- Only use overs with STRONG ratio (≤1.15) or high upset risk flags present.

### NEW — Cross-Sport Upset Checklists:

**Football (threshold ≥4 → avoid ML):**
Fixture congestion (+2), relegation desperation (+1), cup/league priority split (+1), strong team playing away (+1), new manager bounce (+1), H2H bogey team (+1), ≥2 key absences (+1), nothing to play for (+1).

**Basketball (threshold ≥3):**
B2B 2nd night (+2), travel >1500km in 48h (+1), playoff series shift G3/G4 (+1), star player questionable (+2), blowout reversal adjustment (+1).

**Hockey (threshold ≥3):**
Goalie uncertain (+2), B2B (+2), road team in playoffs G3+ (+1), elimination desperation (+1), PP/PK regression (+1).

**Baseball (threshold ≥3):**
SP ERA >4.50 or rookie (+2), bullpen fatigue (+1), platoon advantage (+1), day after night (+1), key batter sitting (+1).

**Snooker (threshold ≥2):**
Short format (+1), form discrepancy (+1), safety-heavy underdog (+1).

**Esports (threshold ≥2):**
Roster change (+2), map pool edge (+1), online match (+1), new patch (+1).

### Rule changes for future runs:
1. Run upset checklist for EVERY candidate pick in EVERY sport.
2. If upset score ≥ threshold → HARD BAN on ML. Only statistical markets.
3. If upset score high + STRONG odds ratio → game totals are PREMIUM picks.
4. If upset score low + only GOOD ratio → risk of blowout → prefer handicap or under, not over.
5. Add upset risk assessment to STEP 6 (Context Verification) in methodology.

## 2026-04-24 — METHODOLOGY INTEGRATION: Upset Risk Assessment embedded in active prompts

### Changes made:
1. **analysis-methodology.instructions.md**: Added STEP 6.5 (Upset Risk Assessment) with 14 sport-specific checklists (tennis 14 factors/12pts, football 12 factors/14pts, basketball 10/10, hockey 8/10, baseball 8/10, volleyball 6/7, esports 8/10, snooker 7/7, darts 6/7, MMA 9/10, handball 6/7, table tennis 6/6, padel 7/8, speedway 7/8).
2. **analysis-methodology.instructions.md**: Added V4k validation check — verifies upset scores calculated, ML bans enforced, Paradox Rule applied, confidence adjusted.
3. **analysis-methodology.instructions.md**: Updated STEP 7 bear case template to include UPSET SCORE field.
4. **analysis-methodology.instructions.md**: Updated Quick Reference checklist with STEP 6.5.
5. **model-ready-betting.instructions.md**: Added Upset Risk Assessment section to market selection rules with Paradox Rule, thresholds, and Shelton case study.
6. **model-ready-betting.instructions.md**: Added common mistakes #39 (skipping upset assessment), #40 (ignoring Paradox Rule), #41 (no upset score in bear case).
7. **model-ready-betting.instructions.md**: Added upset assessment to V8 Source Completeness Audit.

### Key new factors added beyond original 8 (tennis expanded to 14):
- Altitude factor (Madrid 660m), previous round fatigue, late-career complacency, return game strength, sharp money signals, draw section look-ahead.
- Football: international break, manager sacking bounce, derby factor, altitude, artificial turf.
- Basketball: altitude (Denver), overtime previous game, coach revenge, post-trade disruption, schedule 4-in-5.
- Hockey: backup goalie B2B, PP regression, empty net adjustment.
- Baseball: umpire zone, weather at ballpark, catcher framing.
- Esports: stand-in player, meta shift, online vs LAN gap.
- MMA: stylistic mismatch, weight class move, long layoff, short notice, bad weight cut.
- All sports: Decision Matrix (§6.5.15) maps upset score → allowed markets + confidence adjustment.

### Paradox Rule formalized as market selection principle:
- High upset risk → OVER totals PREMIUM (competitive match = more play)
- Low upset risk → OVER totals DANGEROUS (blowout = fewer play units)
- This is now embedded in both methodology (§6.5) and model-ready (market rules).

## 2026-04-24 — POST-MORTEM: Jodar vs De Minaur O22.5 games (wildcard blowout loss)

### Settlement:
- **Pick**: PK-20260424-602, Jodar vs Alex De Minaur, O22.5 games @ 1.82 (Betclic)
- **Result**: Jodar won 6-3, 6-1 = **16 total games**. LOST by 7 games. BLOWOUT.
- **Exposure**: Present in 3 coupons (P2v6, P3v6, HR1v6) = 4.00 PLN at risk.

### Root cause analysis — FIVE compounding failures:

1. **Player identity confusion**: v5 listed "Pedro Martinez Portero / Jodar" — ambiguous slash between two different Spanish players. Pedro Martínez Portero (ATP #42ish) vs Rafael Jodar (wildcard, much lower ranked). Analysis may have used wrong player's data for odds ratio calculation. CRITICAL FAILURE.

2. **Wildcard blowout pattern not recognized**: Rafael Jodar was a Spanish WILDCARD in Madrid Masters 1000 R1. WC/Q/LL matches produce BINARY outcomes (blowout 55-65% vs competitive 25-35%). P(≤16 games) is 40-50% for WC matches. The analysis used standard P(3 sets) ~57% which does NOT apply to wildcard matches.

3. **Odds drift >10% ignored**: Analysis estimated O22.5 @ 1.65 but Betclic offered 1.82 = **+10.3% drift**. This massive move signals the market shifting AWAY from Over. Per §5.5 rules, this should trigger mandatory re-evaluation. It was NOT caught. The market was right — Over was less likely than estimated.

4. **Equal Odds Blowout Fallacy**: Analysis claimed ratio 1.01 → "virtually a coin flip" → high P(3 sets). But even odds mean UNCERTAINTY, not COMPETITIVENESS. A coin-flip match can produce 6-3 6-1 just as easily as 7-6 6-7 7-5. The analysis inflated P(O22.5) to 76% based on ratio closeness alone.

5. **Bear case identified but ignored**: Bear case stated "Madrid altitude = quick sets possible; De Minaur steamroll" — exactly what happened (though Jodar steamrolled instead). This was noted at confidence 4/5 and never acted upon.

### Rule changes implemented:

1. **§3.2F Player Identity Verification Protocol** (NEW): Full name + country + ranking for every tennis pick. No slashes or ambiguous identifiers. WC/Q/LL status flagged explicitly.

2. **§3.2G Wildcard/Qualifier Blowout Rule** (NEW): O22.5+ is HARD REJECT for WC/Q/LL matches. O20.5 max with STRONG ratio only. Binary outcome model replaces standard P(3 sets) model.

3. **§5.5a Odds Movement Gate** (NEW): >8% drift between analysis and placement → MANDATORY re-evaluation. No explanation → SKIP. Applies to ALL sports.

4. **V3 Tennis Validation updated**: Added checks 6-9 (player identity, WC/Q/LL, odds drift, Equal Odds Blowout Fallacy).

5. **V4a Tennis Validation updated**: Added checks 5-6 (WC/Q/LL game total cap, odds drift).

6. **Common mistakes #46-49 added** to model-ready-betting.instructions.md.

### Files modified:
- analysis-methodology.instructions.md: §3.2F, §3.2G, §5.5a, V3, V4a
- model-ready-betting.instructions.md: V3, common mistakes #46-49
- bet-analyst.agent.md: V3, STEP 3 tennis, STEP 5
- daily-betting-cycle.prompt.md: STEP 6, V3-V4
- learning-log.md: this entry
- Memory: common-mistakes.md, betting-workflow-rules.md

## 2026-04-26 — LEARNING-BASED PORTFOLIO REBUILD (v20 → v21)

### Settlement summary:
- Apr 25 settled: 1W-9L = -13.51 PLN. Only CP-PD02 (Higgins+Medvedev) won @2.33.
- NBA Playoff totals: 0/2. MLS O2.5: 1/4. BTTS: 0/3. Tennis game totals: 2/2 (best market!).
- Bankroll: 35.00 → 21.49 PLN.

### Per-market hit rate analysis (FULL LEDGER — ALL historical picks):
| Market | W | L | Hit Rate | Action |
|--------|---|---|----------|--------|
| Football corners | 7 | 3 | **70%** | BEST market, PRIORITIZE |
| Football U2.5 | 3 | 1 | **75%** | Strong, KEEP |
| Volleyball O3.5 sets | 2 | 0 | **100%** | Small sample but ADD MORE |
| Football O2.5 | 2 | 3 | 40% | Weak overall, match-specific only |
| Tennis game totals | 3 | 4 | 43% | Ratio-dependent (STRONG only) |
| Football BTTS | 2 | 3 | 40% | AVOID |
| MLB totals | 1 | 5 | **17%** | TERRIBLE, auto -1 conf |
| NBA totals | 2 | 3 | 40% | AVOID |
| MLS all | 1 | 4 | **20%** | TERRIBLE |
| Hockey totals | 2 | 3 | 40% | Mixed |
| Speedway handicap | 0 | 2 | **0%** | WORST, NEVER USE |

### v20 failures caught in v21:
1. **PK-03 Mainz-Bayern O2.5 — WRONG DATE!** Bayern plays 02.05 not 26.04. V7b date verification caught this. If placed, would have been voided but shows sloppy analysis.
2. **PK-06 Unia speedway -7.5 — 0% HIT RATE MARKET.** Speedway handicap is 0W-2L. Should never have been included. Hit rate data now MANDATORY before adding any market type.
3. **PK-04 Gala U2.5 — EV +2% BORDERLINE.** Minimum EV threshold not enforced. Below +3% = watchlist only.

### Rule changes for future runs:
1. **MANDATORY: Check per-market hit rate before adding any pick.** If market type has <40% hit rate in ledger → auto -1 confidence, reduced stake. If <25% → REJECT unless exceptional circumstances.
2. **MANDATORY: Stake weighting by completeness.** V10e matrix score determines stake tier: all ✅ → max stake; ≥2 ⚠️ → reduced; ≥3 ⚠️ → minimum stake.
3. **Speedway handicap PERMANENTLY banned** until 3+ wins established.
4. **MLS, MLB totals auto -1 confidence** (confirmed by historical data).
5. **Volleyball O3.5 sets is a premium market** — actively seek it out every run.
6. **Football corners remain #1 priority** — when corner data sources (TotalCorner, SoccerStats) are blocked, note gap but still prefer corners over goals markets.

### What worked in v21 rebuild:
- Caught wrong date (Mainz-Bayern) through BetExplorer fixture verification
- Added W0lfx tipster (77% accuracy, #2 ranked on Typersi) backing Rinderknech O20.5
- Graduated stake system: strongest picks 2.00 PLN, weakest 0.50 PLN
- Added volleyball (100% hit rate market)
- Removed all picks from 0% hit rate markets

### Files modified:
- betting/coupons/2026-04-26-v21.md (new file)
- picks-ledger.csv (PK-03/04/06 superseded, 5 new v21 picks added)
- coupons-ledger.csv (v20 MS01/MS02 superseded, 4 new v21 coupons added)
- learning-log.md (this entry)

## 2026-04-27 (Betclic Full History Import & Learning Analysis)

### Source: Betclic /my-bets HTML export (141 coupons, 469 legs, 13.04–27.04.2026)
- Parsed via `scripts/parse_betclic_bets.py` → `betting/data/betclic_bets_history.json`
- Analyzed via `scripts/analyze_betclic_learning.py`
- Data covers ALL real placed coupons from Betclic account — authoritative ground truth.

### Settlement summary (full Betclic history):
- 138 settled coupons: 37W / 101L (26.8% coupon hit rate)
- Staked: 418.84 PLN | Returned: 329.72 PLN | Net PnL: -89.12 PLN | ROI: -21.3%

### KEY FINDING — Statistical vs Outcome markets:
- Statistical markets (corners, cards, fouls, game totals, frame totals): **67% leg hit rate** (145W/71L on 216 legs)
- Outcome markets (match winner, handicap, BTTS, etc.): **46% leg hit rate** (101W/117L on 218 legs)
- **Statistical markets outperform outcomes by +21 percentage points.** This is the single most impactful signal.

### What worked (high hit rate markets confirmed by Betclic data):
- Football corners: **73% hit rate** (46W/17L on 63 legs) — #1 core market ★
- Football totals (O/U goals): **79% hit rate** (33W/9L) ★
- Football cards: **75%** (9W/3L on 12 legs) ★
- Football fouls: **67%** (8W/4L on 12 legs) ★
- Snooker frame totals: **100%** (8W/0L on 8 legs) ★
- Double chance: **83%** (5W/1L on 6 legs) ★
- Tennis game totals: **60%** (27W/18L on 45 legs) — solid ✓
- UNDER direction: **76%** hit rate (32W/10L on 42 legs) — strong edge ★
- OVER direction: **64%** hit rate (129W/74L on 203 legs) — good ✓

### What failed (confirmed weak areas):
- Match winner (Zwycięzca meczu): **37%** hit rate (23W/39L) — worst single killer (39 coupon kills) ✗
- Baseball runs totals: **20%** (2W/8L) — avoid ⛔
- CS2: **0%** (0W/9L) — complete disaster, never use ⛔
- Speedway: **0%** (0W/3L) — avoid ⛔
- Volleyball totals: **14%** (1W/6L) — very poor ✗
- Tennis handicap: **44%** (16W/20L) — below acceptable ✗
- Tennis specials: **33%** (2W/4L) — avoid ✗
- Football match winner: **35%** (6W/11L) — terrible for football ✗

### Coupon size findings:
- AKO (2): 35% win rate — **best AKO size, sweet spot** ★
- AKO (3): 41% win rate (+23.21 PnL!) — **most profitable size** ★
- AKO (4): 29% win rate — acceptable
- AKO (5): **0% win rate** (0W/14L, -59.20 PnL) — ⛔ NEVER USE
- AKO (6): 17% win rate (but +51.17 PnL due to high odds) — risky but can work
- AKO (7+): **0% win rate** across all — ⛔ NEVER USE

### Stake size findings:
- 5+ PLN stakes: **15% win rate** (-74.50 PnL) — worst ROI. Reduce max stake.
- 2-3 PLN stakes: **35% win rate** (+11.80 PnL) — best efficiency ★
- 1-2 PLN stakes: **22% win rate** (-15.26 PnL) — acceptable but low

### Coupon killer analysis:
- #1 killer: **match_winner** (51 leg kills) — responsible for ~50% of coupon failures
- #2 killer: **totals** (26 kills) — mostly football/basketball
- #3 killer: **handicap** (24 kills) — tennis + football
- #4 killer: **game_totals** (18 kills) — tennis

### Rule changes for future runs:
1. **AKO (5)+ BANNED.** Zero wins on 21 attempts. Max AKO size = 4 legs. Exceptions only for extraordinary value (>10x odds, all legs ★ rated).
2. **Match winner market DEMOTED to last resort.** 37% hit rate, #1 coupon killer. Only use when no statistical market is available AND safety score ≥ 8.
3. **CS2, speedway, LoL, handball → PERMANENTLY BANNED.** 0% combined hit rate.
4. **Baseball runs totals → BANNED** (20% hit rate). Baseball match winner only with extreme caution.
5. **Volleyball totals → AVOID.** 14% hit rate. Use only set handicap (62%) or O3.5 sets.
6. **Football corners = KING MARKET.** 73% hit rate confirms. Always default to corners first for football.
7. **Max single bet stake = 3.00 PLN.** 5+ PLN bets had 15% win rate (-74.50 PnL). Cap enforced.
8. **UNDER direction underexplored but dominant.** 76% vs 64% for OVER. Actively seek UNDER plays.
9. **AKO (2-3) optimal.** 2-leg at 35% and 3-leg at 41% are the sweet spots. 3-leg with +23.21 PnL is MOST profitable format.
10. **Tennis: game totals ONLY.** 60% hit rate vs 44% handicap and 50% match winner. Drop tennis handicap and match winner.

### Files created/modified:
- scripts/parse_betclic_bets.py (new — HTML parser)
- scripts/analyze_betclic_learning.py (new — learning analysis)
- betting/data/betclic_bets_history.json (new — structured bet data)
- betting/journal/learning-log.md (this entry)
