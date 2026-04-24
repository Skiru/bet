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
- The orchestrator scans all configured sports (football, tennis, basketball, hockey, baseball, volleyball, esports, snooker, darts, table_tennis, handball, mma) across all Tier A and Tier B sources with sport-specific subpages.
- The agent and prompts assume these structured outputs are present and up-to-date; if they are missing or stale, re-run the orchestrator and retry the run.
- After the orchestrator finishes, check `betting/data/scan_errors.json` for source failures. Record any failed sources in the daily source log.
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

Selection rules:
- **MANDATORY: Analyze ALL 12 sports** configured in config/betting_config.json: football, tennis, basketball, hockey, baseball, volleyball, esports, snooker, table_tennis, darts, handball, mma. Never skip a sport. Never reject a sport for "lack of sources" — the internet has specialist sites for every sport. Search for them.
- **Sport coverage audit**: After analysis, verify ALL 12 sports were scanned. If any sport was not scanned, go back and scan it before proceeding. This is a HARD REQUIREMENT — not optional.
- **Minimum sport diversity in final picks**: The final pick roster MUST include picks from at least 5 different sports. If fewer than 5 sports have picks, search deeper in the missing sports before declaring no value.
- Diversify broadly across sports: football, tennis, basketball, hockey, baseball, volleyball, esports (CS2, Dota 2, LoL, Valorant), snooker, table tennis, darts, handball, MMA/UFC, and any other sport available on Betclic.
- Avoid popular high-profile events and pure match result bets unless there are strong statistical indicators. Focus on deep analysis of statistical markets, tipster consensus, and analytical perspectives.
- Perform WIDE analysis: for every candidate event, check multiple ARGUMENT-BASED tipster sites where tipsters post detailed written reasoning (not just bare picks). Required sites: Zawod Typer (zawodtyper.pl), Typersi (typersi.pl), Meczyki (meczyki.pl), OLBG (olbg.com), PicksWise (pickswise.com), BetIdeas (betideas.com), Sportsgambler, GosuGamers (esports). Navigate into match pages, scroll deeply, read each tipster's argument, and extract their reasoning.
- The following tipster sources are BLOCKED and must NOT be attempted: Forebet, FootySupertips, Windrawwin, BettingExpert, Protipster, Oddspedia, SportyTrader, Predictz, Trafiamy, Blogabet, HLTV. See source-registry.md.
- Prefer deep statistical markets over generic goals markets. Priority order for football: corners, cards, fouls, shots, team totals, BTTS, double chance, draw no bet. Use Over/Under goals only as a fallback when no statistical markets are available.
- For corner picks, use the three-source stack: TotalCorner (match-level corner totals/handicaps), SoccerStats (league-level corner rankings), and Betclic Statystyki tab (verified odds from HTML snapshots). All three are needed for high-confidence corner picks.
- Betclic Statystyki tab (corners, cards, fouls, shots) is only available for top leagues (EPL, LaLiga, Bundesliga). For other leagues, use BTTS, U2.5, DC, or ML markets backed by SoccerStats defensive profiles.
- Use 1X2 or moneyline only when the edge is strong and the price is still acceptable.
- A final pick requires at least one Tier A stats source and one Tier A market or price source. Tier B opinion or consensus sources may support a pick but cannot be the main reason for it. However, strong consensus from multiple tipster sites IS a valid supporting signal.
- If primary sources disagree materially or are unavailable, skip the pick.
- Never produce shallow, surface-level analysis. Every pick must have DEEP statistical backing from specialist sources, not just top-level form data.
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
- On reruns for the same betting day, update existing records instead of duplicating them.
- Learning means process adjustments backed by settled results. Do not add emotional commentary and do not claim model retraining.