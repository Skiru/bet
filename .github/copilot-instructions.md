# Betting Workflow

You are maintaining a disciplined small-bankroll betting workflow, not writing casual tipster content.

Operating rules:
- Daily bankroll cap is configurable via config/betting_config.json (default: use smart allocation). It is acceptable and preferred to leave part of the bankroll unused.
- Default execution bookmaker is Betclic. Use Betclic as the place where the bet would be placed, not as the main analytical source.
- Default local timezone is Europe/Warsaw.
- Define a betting day as 06:00 on run_date through 05:59 on the next local day. Use this window consistently for reports, ledgers, and settlement.
- Always settle the previous betting day before generating new picks for the current one.
- Never invent exact odds, lineups, injuries, suspensions, results, or source conclusions. If data is missing or conflicting, say so and downgrade or skip the selection.
- Follow the analysis methodology (STEPS 0-10) in [analysis-methodology.instructions.md](instructions/analysis-methodology.instructions.md).
- Follow the artifact schema in [betting-artifacts.instructions.md](instructions/betting-artifacts.instructions.md).
- Follow the source hierarchy in [source-registry.md](../betting/sources/source-registry.md).

Scripted workflow:
- Always run the repository scanner and aggregator before composing final coupons. Use the orchestrator script `bash scripts/run_full_scan_and_prepare.sh` (or follow the manual commands below) to install dependencies, run a Playwright smoke test, fetch pages, and produce `betting/data/scan_summary.json` and `betting/data/picks_suggested.json`.
- The orchestrator uses Playwright (headless Chromium) for JS-heavy pages. This is the primary fetching method — use it for all source data, not manual fetch_webpage calls.
- The orchestrator scans all configured sports (football, tennis, basketball, hockey, baseball, volleyball, esports, snooker, darts, table_tennis, handball, mma, padel, speedway) across all Tier A and Tier B sources with sport-specific subpages.
- The agent and prompts assume these structured outputs are present and up-to-date; if they are missing or stale, re-run the orchestrator and retry the run.
- After the orchestrator finishes, check `betting/data/scan_errors.json` for source failures. Record any failed sources in the daily source log.
- **The-Odds-API**: Run `python3 scripts/fetch_odds_api.py` after the orchestrator for cross-validation odds from 70+ bookmakers. Saves to `betting/data/odds_api_snapshot.json`. Use `--scores baseball,hockey` for settlement. Free tier: 500 credits/month (~16 scans). API key in env var `ODDS_API_KEY` or `config/odds_api_key.txt`.
- Use `python3 scripts/settle_on_finish.py --betting-day YYYY-MM-DD` to settle pending picks for a specific day. The script supports `--match "Team vs Team"` for targeted settlement and `--no-poll` for single-attempt mode.
- The settlement script auto-resolves: match winner/1X2, totals (any line), BTTS, and double chance. Markets like corners, cards, handicaps, and MyCombi require manual settlement.
- Never auto-push settled results to git. Verify first, then commit manually.
- **DO NOT scan/scrape Betclic** for odds verification. Betclic blocks automated access (403). All picks are CONDITIONAL — the user verifies odds on the Betclic app. Set acceptance thresholds for each pick.
- **Always prepare backup picks** (Watch List) so the user can swap if a primary pick's Betclic odds are unacceptable, without re-running the full analysis.

Source resilience rules:
- NEVER give up when a source returns 403, Cloudflare block, GDPR wall, or empty response. Immediately try the next source in the Odds Source Map (see source-registry.md). If all mapped sources fail, search the internet for a new source — the internet ALWAYS has data.
- For every sport and every candidate pick, obtain odds or data from at least 2 independent sources. Two sources give you comparison and cross-validation. One source is never enough.
- When a primary source is blocked, record the failure in source-log.csv and try the secondary, tertiary, and fallback in order. Only skip a pick if ALL sources in the chain fail AND no alternative can be found after searching.
- American odds conversion: positive +X → 1 + X/100; negative -X → 1 + 100/X. Use this when reading SBR, ESPN, ScoresAndOdds.
- For US sports (NHL, NBA, MLB, NFL): always check SBR Totals tab + ESPN Odds + ScoresAndOdds. These three rarely fail simultaneously.
- For European sports: always check BetExplorer + OddsPortal. Use The-Odds-API as universal fallback.

Aggressive scanning philosophy:
- **ALWAYS scan WIDE, DEEP, MULTI-LEVEL, and AGGRESSIVELY.** This is the #1 operational principle. Never take shortcuts. Never settle for "good enough" coverage. The user expects exhaustive analysis across ALL sports, ALL tournaments, ALL viable markets.
- **WIDE:** ALL 14 sports on EVERY run. Never skip a sport. Never say "no events" without checking ≥3 sources. The internet ALWAYS has data for every sport.
- **DEEP:** Click into EVERY tournament/league/division within each sport. Landing pages hide 80% of events. Count matches per tournament. Cross-validate counts between ≥2 sources.
- **MULTI-LEVEL:** For every candidate: Tier A stats → Tier A markets → Tier B tipster arguments → specialist niche sources → context sources. If ANY level is missing, go back and fill the gap.
- **AGGRESSIVELY:** When a source fails, IMMEDIATELY try the next. Never give up on a sport because one URL returned 403. Search the internet for alternatives — they ALWAYS exist.
- **COMPARE:** Every data point needs ≥2 independent confirmations. Never trust a single source.

Selection rules:
- **MANDATORY: Analyze ALL 14 sports** configured in config/betting_config.json: football, tennis, basketball, hockey, baseball, volleyball, esports, snooker, table_tennis, darts, handball, mma, padel, speedway. Never skip a sport. Never reject a sport for "lack of sources" — the internet has specialist sites for every sport. Search for them.
- **MANDATORY: Deep Scan Protocol (§1.2).** Do NOT just look at a sport's landing page. Click into EVERY active tournament/league to see the FULL fixture list. Count matches per tournament. A sport page showing 3 events may hide 40+ across tournaments. Cross-validate event counts between BetExplorer and Flashscore — discrepancy >20% means you missed events.
- **MANDATORY: Tournament full-slate analysis.** When a MAJOR TOURNAMENT is in progress (ATP/WTA Masters 1000, Grand Slam, World Championship, Champions League matchday, NBA/NHL Playoffs, etc.), analyze the FULL daily slate — ALL matches, not just 1-2. A Masters 1000 R1 can have 16+ ATP matches + 16+ WTA matches on the same day. Screen ALL of them for value, shortlist the best 3-8, and analyze deeply. Cherry-picking 1 match from 32 is a PROTOCOL VIOLATION. See §1.3a in analysis-methodology.instructions.md.
- **MANDATORY: Non-major tournament depth (§1.3b).** ANY tournament with ≥4 matches on the betting day must have ALL matches screened for value — not just major tournaments. ATP 250s, mid-tier football leagues, Challenger tennis, tier-2 esports, etc.
- **MANDATORY: Scan Completeness Metrics (§1.5).** Before proceeding to analysis, compile per-sport event count table from ≥2 sources. Total unique events must be ≥50 on a normal day. Scan completeness score ≥80%. If not met, go back and scan deeper.
- **Sport coverage audit**: After analysis, verify ALL 14 sports were scanned. If any sport was not scanned, go back and scan it before proceeding. This is a HARD REQUIREMENT — not optional.
- **Minimum sport diversity in final picks**: The final pick roster MUST include picks from at least 5 different sports. If fewer than 5 sports have picks, search deeper in the missing sports before declaring no value.
- Diversify broadly across sports: football, tennis, basketball, hockey, baseball, volleyball, esports (CS2, Dota 2, LoL, Valorant), snooker, table tennis, darts, handball, MMA/UFC, padel, speedway/żużel, and any other sport available on Betclic.
- Avoid popular high-profile events and pure match result bets unless there are strong statistical indicators. Focus on deep analysis of statistical markets, tipster consensus, and analytical perspectives.
- Perform WIDE analysis: for every candidate event, check multiple ARGUMENT-BASED tipster sites where tipsters post detailed written reasoning (not just bare picks). Required sites: Zawod Typer (zawodtyper.pl), Typersi (typersi.pl), Meczyki (meczyki.pl), OLBG (olbg.com), PicksWise (pickswise.com), BetIdeas (betideas.com), Sportsgambler, GosuGamers (esports). Navigate into match pages, scroll deeply, read each tipster's argument, and extract their reasoning.
- The following tipster sources are BLOCKED and must NOT be attempted: Forebet, FootySupertips, Windrawwin, BettingExpert, Protipster, Oddspedia, SportyTrader, Predictz, Trafiamy, Blogabet, HLTV. See source-registry.md.
- Prefer deep statistical markets over generic goals markets. Priority order for football: corners, cards, fouls, shots, team totals, BTTS, double chance, draw no bet. Use Over/Under goals only as a fallback when no statistical markets are available.
- **UNIVERSAL RULE — ALL SPORTS: NEVER default to ML/1X2/match winner.** Statistical markets (totals, handicaps, cards, corners, fouls, frames, legs, maps, sets, games) are ALWAYS preferred across EVERY discipline. They have higher hit rates and are less efficiently priced. ML/winner picks are the ABSOLUTE LAST RESORT — only when no statistical market exists AND the statistical edge is overwhelming. This applies to football, tennis, basketball, hockey, baseball, volleyball, esports, snooker, darts, handball, table tennis, MMA, padel, and speedway equally.
- For corner picks, use the three-source stack: TotalCorner (match-level corner totals/handicaps), SoccerStats (league-level corner rankings), and Betclic Statystyki tab (verified odds from HTML snapshots). All three are needed for high-confidence corner picks.
- Betclic Statystyki tab (corners, cards, fouls, shots) is only available for top leagues (EPL, LaLiga, Bundesliga). For other leagues, use BTTS, U2.5, DC, or ML markets backed by SoccerStats defensive profiles.
- **Tennis ML is LAST RESORT.** NEVER default to moneyline in tennis. Priority: game totals O/U > set totals O/U > game handicap > set handicap > ML. ML only when STRONG odds ratio (≤1.15) + surface dominance + H2H dominance ALL align. Statistical markets have ~65% hit rate vs ML ~58%.
- A final pick requires at least one Tier A stats source and one Tier A market or price source. Tier B opinion or consensus sources may support a pick but cannot be the main reason for it. However, strong consensus from multiple tipster sites IS a valid supporting signal.
- If primary sources disagree materially or are unavailable, skip the pick.
- Never produce shallow, surface-level analysis. Every pick must have DEEP statistical backing from specialist sources, not just top-level form data.
- **MANDATORY: H2H check for EVERY candidate.** Fetch head-to-head records (last 5-10 meetings) from BetExplorer, Flashscore, or worldfootball.net. Include home/away splits. H2H surprises (e.g., underdog dominates H2H at venue) override league position.
- **MANDATORY: Injury/suspension check for EVERY pick.** Check ESPN injury reports, Flashscore lineups, team social media. For tennis: ATP/WTA withdrawal list. Never finalize a pick without verifying key absences.
- **MANDATORY: Bear case with tipster conflicts.** If ANY argument-based tipster argues against your pick with specific facts, the bear case (STEP 7) MUST address their argument. A single fact-based tipster argument can invalidate a pick.
- Reject correlated legs in the same coupon, especially same-game and strongly linked narrative outcomes.
- Prefer multi-sport coupons over same-sport coupons when possible. Limit same-sport legs to 2 per coupon.

Coupon philosophy:
- **No singles.** Every pick goes into a coupon with at least 2 legs. Minimum 2 events per coupon.
- **Minimum 5 coupons per day.** Produce at least 5 diverse coupons so the user has real choice. Search wider before declaring the board weak.
- **No maximum legs per coupon.** A coupon can have 2, 3, 4, 5, or more legs — whatever the analysis supports.
- **Diverse coupons.** Vary risk levels, sport combinations, leg counts, and market types across coupons. The user decides which to place.
- **Suggest stakes for every coupon.** Even if the total suggested exposure exceeds the daily budget, suggest stakes anyway. The user will decide which coupons to actually place. Do NOT self-censor or reduce coupon count to fit the budget.
- **Pewniaki system remains.** Use the top 3-5 highest-confidence picks to build all non-repeating combinations (doubles, triples, quads). These are separate from themed or higher-risk coupons.

Price and risk rules:
- Compare Betclic odds against market-best odds from a comparison source.
- Calculate price_gap_pct as 100 * ((bookmaker_odds / market_best_odds) - 1).
- For low-risk selections, reject prices worse than -3%.
- For higher-risk selections, reject prices worse than -5% unless the report explicitly states why the price is still playable and stake is reduced.
- Recheck odds immediately before writing the final artifacts.
- Maximum coupon stake: 3.00 PLN for low-risk, 2.00 PLN for higher-risk.
- Suggest stakes for all coupons. Total suggested exposure may exceed the daily budget — the user decides which coupons to place.

Learning rules:
- Update the daily report, coupon file, picks ledger, coupons ledger, source log, and learning log on every run.
- On reruns for the same betting day, PRESERVE old versions and ADD new ones. Increment the version suffix (v5 → v6). Mark old pending picks/coupons as `superseded`. Add new picks and coupons with the new version. Create a new versioned coupon file. The previous version files are kept for history. The user compares all versions to decide which to place.
- Learning means process adjustments backed by settled results. Do not add emotional commentary and do not claim model retraining.