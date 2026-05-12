# Gemini Evolution — Integration Complete (2026-05-12)

## What Was Built
4 Gemini modules + dashboard + full orchestrator integration, all behind feature flags.

## Modules Created
| Module | Purpose | Feature Flag |
|--------|---------|-------------|
| `scripts/gemini_tipster_reader.py` | Read tipster sites via Gemini URL reading (replaces BS4) | `--use-gemini` on `tipster_aggregator.py` |
| `scripts/gemini_web_research.py` | L7a web research via Gemini Search Grounding (replaces SerpAPI) | `use_gemini=True` on `web_research_agent.py` (default on) |
| `scripts/gemini_news_enrichment.py` | Injuries/coaching/morale via Search Grounding → `team_news` DB | `--news` on `data_enrichment_agent.py` |
| `scripts/gemini_deep_analyst.py` | Per-candidate "second opinion" with agreement_score | `--gemini` on `deep_stats_report.py` |

## Key Files Modified
- `scripts/tipster_aggregator.py` — `--use-gemini` flag, Gemini-first path per site
- `scripts/data_enrichment_agent.py` — `--news` flag, calls `batch_enrich_news()` + `save_news_to_db()`
- `scripts/deep_stats_report.py` — `--gemini` flag, calls `analyze_candidate()` + `compute_agreement_score()`
- `scripts/web_research_agent.py` — L7a Gemini in `research_missing_data()`, falls back to L7b SerpAPI
- `scripts/context_checks.py` — Reads `team_news` DB table, adds COACHING/MORALE/NEWS/INJURY flags
- `scripts/agent_protocol.py` — `gemini_research`, `gemini_tipster`, `gemini_news` in SELF_HEALING_REGISTRY
- `src/bet/db/repositories.py` — `TeamNewsRepo` (upsert, get_for_team_date, get_for_date)
- `src/bet/schemas/gemini_responses.py` — All Pydantic schemas (TipsterPageResult, WebResearchResult, NewsEnrichmentResult, CandidateDeepAnalysis, MarketAnalysis, etc.)

## Config
- `config/gemini_config.json` — default_model, deep_analysis_model, daily_request_limit, rate_limit_delay
- `scripts/api_clients/gemini_client.py` — GeminiClient with generate(), search_grounded_query(), read_url()

## DB Changes
- Migration `003_team_news.py` — `team_news` table (team_id, sport_id, betting_date, injuries/news/coaching/morale JSON, confidence, source)

## Dashboard
- `dashboard/` — Next.js 16 + React 19 + Tailwind 4 + better-sqlite3
- Dark purple theme, sidebar (Dashboard/Coupons/Terminal), KPI cards from real DB
- Components: KpiCards, CouponViewer, AgentStatus, GeminiStatus, SportBreakdown
- Reads from `betting.db` (scan_results, coupons tables) and `betting_config.json`
- Start: `cd dashboard && npm run dev`

## Orchestrator Integration
- `orchestrate-betting-day.prompt.md` — Gemini feature flags table, flags at S1b/S2.5/S3, gemini_config.json in context loading
- `bet-orchestrator.agent.md` — Gemini scripts in allowed list
- `bet-tipsters.prompt.md` — `--use-gemini` documented
- `bet-enrich.prompt.md` — `--news` flag, `team_news` table in sources
- `bet-deep-stats.prompt.md` — §5 Gemini Second Opinion with agreement_score interpretation
- `bet-context-upset.prompt.md` — `team_news` in DB tables reference

## Fallback Chain (updated)
L1→L6 unchanged. L7a: Gemini Search Grounding (primary). L7b: SerpAPI (fallback). L7c: Playwright (last resort).

## Important Notes
- All Gemini features are ADDITIVE — pipeline works unchanged without them
- All modules have `try/except ImportError` guards — graceful degradation
- agreement_score: ≥0.8 HIGH (strong), 0.5-0.8 MODERATE (investigate), <0.5 LOW (manual review)
- Gemini budget tracked via `RateLimiter` from `api_clients/rate_limiter.py`
