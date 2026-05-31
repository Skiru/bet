# Pipeline Knowledge Base — Roo Code Summary

## Enrichment Fallback Chains
- **Football:** api-football → flashscore → soccerway → sofascore
- **Volleyball:** api-volleyball → flashscore-volleyball → sofascore
- **Hockey:** espn-hockey → moneypuck → flashscore-hockey → api-hockey
- **Basketball:** espn-basketball → nba-api → flashscore-basketball → sofascore
- **Tennis:** flashscore → tennis-abstract → ATP/WTA official
- **Esports:** bo3.gg (CS2/Valorant) → vlr.gg (Valorant) → HLTV (CS2)

## API Quotas
- API-Sports (football/volleyball/basketball/hockey): 100 req/day per sport (independent pools)
- Odds-API: 500 credits/month free (30 credits/scan)
- Brave Search: standard tier

## Critical Scripts (most used)
- `settle_on_finish.py` — settlement (S0)
- `analyze_betclic_learning.py` — historical learning patterns (S0.2)
- `discover_events.py` — fixture discovery (S1)
- `ingest_scan_stats.py` — transform scan data into DB (S1.2)
- `tipster_aggregator.py` — tipster fetch (S1b, STEP 6 — MUST run before tipster_xref)
- `tipster_xref.py` — tipster cross-reference (S2, STEP 8 — requires tipster_picks in DB)
- `build_shortlist.py` — ranked shortlist (S1e, STEP 7)
- `deep_stats_report.py` — S3 analysis
- `gate_checker.py` — S7 18-point gate
- `coupon_builder.py` — S8 portfolio

## Recent Key Fixes (2026-05)
- Rate limiter: each sport has independent 100/day quota
- API-Volleyball: no /statistics endpoint; extract from /games response
- Fuzzy match: `src/bet/fuzzy_match.py` (not utils/)
- Multi-sport enrichment: S2.7 volleyball, S2.8 hockey, S2.9 basketball steps added
