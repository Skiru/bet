# Source Navigation — Enricher Reference

## Enrichment Fallback Chains (per sport)
- **Football:** api-football → flashscore → soccerway → sofascore → betaminic
- **Volleyball:** api-volleyball → flashscore → sofascore → enrichment-agent
- **Hockey:** espn-hockey → moneypuck → flashscore → api-hockey → sofascore
- **Basketball:** espn-basketball → nba-api → flashscore → sofascore → api-basketball
- **Tennis:** flashscore → tennis-abstract → ATP/WTA official sites
- **Esports:** bo3.gg → vlr.gg → HLTV (CS2)

## API Quotas (CRITICAL)
- API-Sports: 100 requests/day per sport (football, volleyball, basketball, hockey = INDEPENDENT pools)
- Odds-API: 500 credits/month (30/scan)
- Circuit breaker: 5 consecutive failures from same source → mark DOWN for the run

## Data Quality Scoring (R14)
- **FULL (≥7/10):** Both teams have L10 form + H2H + per-stat data. Ready for core coupons.
- **PARTIAL (4-6/10):** One team has gaps or H2H is thin (<3 meetings). Can enter analysis with flag.
- **MINIMAL (<4/10):** Major data missing. Extended Pool only.

## Per-Sport Readiness Criteria
- **Football:** team_form L10 exists + corners/fouls available + H2H ≥3 meetings
- **Tennis:** player L10 games avg + surface filter + H2H matches ≥2
- **Basketball:** team total pts L10 + ESPN enrichment (gamelogs, standings)
- **Volleyball:** total points L10 + sets data
- **Hockey:** goals + shots L10 + goalie stats

## Web Research Agent — L7 Fallback (R15)
When critical data is MISSING after all API/scraping fallback chains (L1-L6):
- Spawn web_research_agent.py or use brave-search MCP to search the open web
- Use for: H2H data, injury reports, coach changes, team form
- Rate limits: max 5 SerpAPI + 10 Playwright searches per pipeline run
- This is LAST RESORT — always exhaust API chains first
- Agent MUST be spawned automatically — never leave gaps unfilled without trying

## Key Fixes to Remember
- API-Volleyball has NO /statistics endpoint — extract from /games response
- API-Volleyball season is "2024" not "2025" for current data
- `--no-enrich` flag silently skips ALL enrichment — WARNING log when active
- Early-break after 15 consecutive enrichment failures
