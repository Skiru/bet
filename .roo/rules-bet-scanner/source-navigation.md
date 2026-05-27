# Source Navigation — Scanner Reference

## Source Tiers
- **Tier A (Stats):** Flashscore, SoccerStats, TotalCorner, ESPN, TennisAbstract, MoneyPuck
- **Tier A (Markets):** BetExplorer, OddsPortal, The-Odds-API, Betclic (reference only)
- **Tier B (Tipsters):** ZawodTyper, Typersi, PicksWise, BetIdeas, Sportsgambler, Feedinco, BettingClosed
- **Tier C (Specialists):** CueTracker (snooker), DailyFaceoff (NHL goalies), bo3.gg (CS2), vlr.gg (Valorant)

## Blocked Sources (NEVER use)
Forebet, FootySupertips, Windrawwin, BettingExpert, Protipster, Oddspedia, SportyTrader, Predictz, Trafiamy, Blogabet, HLTV tips section.

## Scan Fallback Chain per Sport
- **Football:** Odds-API → API-Football → Flashscore → BetExplorer → Google
- **Tennis:** Flashscore → ATP/WTA official → BetExplorer → Google
- **Basketball:** Odds-API → ESPN → Flashscore → BetExplorer → Google
- **Volleyball:** Flashscore → CEV → PlusLiga → BetExplorer → Google
- **Hockey:** Odds-API → ESPN → Flashscore → DailyFaceoff → Google

## Coverage Requirements
- ≥50 events scanned total
- ≥80% scan completeness
- ALL 5 sports must have events (unless genuinely no fixtures today)
- Cross-validate counts between ≥2 sources (>20% discrepancy = missed events)
- Major tournaments: NEVER SKIP (verify ALL matches present)
- Protected domestic leagues: +10 score boost (MLS, Brasileirão, NBA, etc.)

## Tournament Protection (R7)
ALL major tournaments worldwide (World Cup, Olympics, Grand Slams, Champions League, Europa League, etc.) are NEVER skipped, filtered, or deprioritized. Tournament events:
- Bypass FIXTURE_ONLY filtering
- Get +15 score boost
- If tournament matches are missing from matrix → scan FAILED → re-scan

## Minor League Value (R8)
Less popular leagues = MORE PROFIT (market inefficiency). Bookmakers focus on top leagues → minor leagues have weak/static lines. Rules:
- Never penalize events for being "obscure"
- Events with data + non-top-5 league get +6 VALUE BOOST
- Statistical markets in minor leagues are especially strong

## Major Domestic League Protection (R13)
Top domestic leagues WORLDWIDE are NEVER skipped — regardless of region. Protected:
- Americas: MLS, Liga MX, Brasileirão (A/B), Argentine Liga Profesional, Liga BetPlay
- Asia/Oceania: Chinese Super League, J-League, K League, Saudi Pro League, A-League, Indian Super League
- Africa: Egyptian Premier League
- Basketball: CBA, NBB, NBA G-League
- Hockey: KHL
- Volleyball: Superliga, V-League
- Tennis: All Grand Slams + Masters 1000
These get +10 boost, bypass FIXTURE_ONLY, and trigger scan failure if active but missing. Americas/Asia leagues are critical for night-session coverage.

## Live Betting Window (R16)
Events already in progress are VALID targets — Betclic allows live betting.
- When ≤1h before kickoff or match is running → flag as LIVE, include in scan
- Never exclude an event just because it's about to start or has started

## Fixture Verification (§1.8)
Every candidate needs verification against ≥2 non-tipster sources before shortlisting.
Protocol: Odds-API snapshot → Flashscore → BetExplorer → tournament official site.
Tipster-only (no independent confirmation) → UNVERIFIED-SKIP.

## Overnight Game Trap
Events 00:00-06:00 from tipster sites may be ALREADY PLAYED the previous night.
Check: kickoff < current_time? → PHANTOM unless live odds confirm active markets.
