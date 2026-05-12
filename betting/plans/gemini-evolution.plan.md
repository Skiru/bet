# Gemini Evolution Plan — Hybrid Pipeline Enhancement

**Version:** 1.0
**Created:** 2026-05-12
**Strategy:** Hybrid evolution — NOT a rewrite. Gemini augments existing Python pipeline.

---

## 1. Executive Summary

This plan evolves the existing Python betting pipeline through 4 phases:

1. **Phase 1 — Gemini Data Intelligence Layer** (HIGH value, LOW risk): Replace fragile HTML scrapers and rate-limited web research with Gemini's Search Grounding and URL reading. Keep all reliable structured APIs (Sofascore, ESPN, The-Odds-API).
2. **Phase 2 — Gemini Deep Analysis Engine** (HIGH value, MEDIUM risk): Add Gemini as a "second opinion" analyst for per-candidate reasoning — bear/bull cases, market confidence, upset risk narratives. Complements Python safety scores.
3. **Phase 3 — React Dashboard** (MEDIUM value, MEDIUM risk): Read-only Next.js viewer over existing SQLite DB. No logic porting. Trigger Python scripts via API routes.
4. **Phase 4 — Agent Consolidation** (LOW value, LOW risk, optional): Reduce 10 Copilot agents to 5-6 by merging related roles.

**Non-negotiable constraints:**
- Probability engine (Poisson/NB, Kelly 1/4, bootstrap CIs) stays in Python — no porting
- Existing APIs (Sofascore, ESPN, The-Odds-API) stay — they're reliable and cheap
- SQLite stays as primary DB (optional PostgreSQL upgrade in Phase 3)
- Agent-driven pipeline (R1) — scripts are data tools, agents are analysts
- All 20 non-negotiable rules (R1-R20) remain enforced

---

## 2. Technical Context

### 2.1 Current Architecture

| Component | Technology | Files |
|-----------|-----------|-------|
| Language | Python 3.11+ | `pyproject.toml` |
| Database | SQLite WAL, 28 tables, 6 domains | `src/bet/db/connection.py`, `repositories.py`, `models.py` |
| Pipeline scripts | ~60 Python scripts | `scripts/` |
| Core library | DB access, market ranking, config | `src/bet/` |
| API clients | 14 sport adapters + base class | `scripts/api_clients/` (BaseAPIClient, RateLimiter) |
| Odds sources | 6 adapters | `scripts/odds_sources/` |
| Agent config | Protocol, skills map, data flow contracts | `scripts/agent_protocol.py` (~700 lines) |
| Probability | Poisson, NB, Kelly, bootstrap CIs | `scripts/probability_engine.py` (~400 lines) |
| Structured output | JSON-line events, AGENT_SUMMARY | `scripts/agent_output.py` (AgentOutput class) |
| Copilot agents | 10 agents, 7 internal prompts, 5 skills | `.github/agents/`, `.github/prompts/`, `.github/skills/` |

### 2.2 Pipeline Steps (S0→S10)

```
S0  → Betclic history analysis (analyze_betclic_learning.py)
S1  → Scan events (scan_events.py → Sofascore API)
S1b → Tipster aggregation (tipster_aggregator.py → 12 HTTP+BS4 adapters)
S1e → Build shortlist (build_shortlist.py)
S2  → Tipster cross-reference (tipster_xref.py)
S2.5→ Data enrichment (data_enrichment_agent.py → Flashscore/Sofascore HTTP)
S3  → Deep stats report (deep_stats_report.py → safety scores, Poisson/NB)
S4  → Odds evaluation (odds_evaluator.py → multi-source)
S5  → Context checks (context_checks.py → weather, injuries, motivation)
S6  → Upset risk (upset_risk.py → sport-specific checklists)
S7  → Gate checker (gate_checker.py → 18-point approval)
S8  → Coupon builder (coupon_builder.py)
S9  → Settlement (settle_on_finish.py)
S10 → Learning & post-mortem
```

### 2.3 Pain Points Addressed

| # | Pain Point | Phase | Solution |
|---|-----------|-------|----------|
| 1 | Fragile HTML tipster scrapers (12 sites, frequent breakage) | P1 | Gemini URL reading extracts structured data from any HTML |
| 2 | Web research agent limited (5 SerpAPI + 10 Playwright/run) | P1 | Gemini Search Grounding — unlimited search queries in single call |
| 3 | Missing injury/news data (L6 gaps) | P1 | Gemini news enrichment via search grounding |
| 4 | Context/upset reasoning is scripted heuristics | P2 | Gemini with HIGH thinking for multi-dimensional reasoning |
| 5 | No visual interface (all terminal/markdown) | P3 | React dashboard reading from SQLite |
| 6 | 10 agents with massive prompt management | P4 | Consolidate to 5-6 by merging related roles |

### 2.4 Existing Patterns to Follow

- **API clients** extend `BaseAPIClient` (ABC) with `RateLimiter` file-based daily counters
- **Structured output** via `AgentOutput` class (`--verbose` JSON-line events, `AGENT_SUMMARY:{json}`)
- **DB access** via `get_db()` context manager, repositories in `src/bet/db/repositories.py`
- **Data models** as dataclasses in `src/bet/db/models.py`
- **Config** loaded from `config/` JSON files, wrapped in `src/bet/config.py`
- **Self-healing** registered in `SELF_HEALING_REGISTRY` in `agent_protocol.py`
- **Data flow** contracts in `DATA_FLOW_CONTRACTS` in `agent_protocol.py`

---

## 3. Phase 1 — Gemini Data Intelligence Layer

**Goal:** Replace fragile unstructured data fetching with Gemini LLM extraction.
**Risk:** LOW — additive layer, all existing sources kept as fallbacks.
**Dependencies:** Gemini API key, `google-genai` Python package.

### P1-T01: Add google-genai dependency [S]

- [ ] **Action:** [MODIFY] `pyproject.toml`
- [ ] **Changes:** Add `"google-genai>=1.0.0"` and `"pydantic>=2.0.0"` to `dependencies`
- [ ] **Rules:** R20 (install via `.venv/bin/pip install -e .`, NOT inline Python)
- [ ] **Definition of Done:** `from google import genai` importable in project venv; `from pydantic import BaseModel` importable; `pyproject.toml` contains both deps

### P1-T02: Create Gemini configuration [S]

- [ ] **Action:** [CREATE] `config/gemini_config.json`
- [ ] **Format:**
```json
{
  "api_key_env_var": "GEMINI_API_KEY",
  "default_model": "gemini-3-flash-preview",
  "deep_analysis_model": "gemini-3-pro-preview",
  "daily_request_limit": 1500,
  "daily_token_budget": 2000000,
  "rate_limit_rpm": 15,
  "rate_limit_delay_seconds": 4.0,
  "timeout_seconds": 60,
  "max_retries": 3,
  "search_grounding_enabled": true,
  "url_context_enabled": true,
  "cost_tracking": {
    "enabled": true,
    "alert_threshold_usd": 5.0
  }
}
```
- [ ] **Action:** [MODIFY] `config/api_keys.example.json` — add `"gemini": "YOUR_GEMINI_API_KEY"`
- [ ] **Action:** [MODIFY] `config/api_keys.json` — add actual Gemini API key entry
- [ ] **Rules:** API key loaded from `config/api_keys.json`, NEVER hardcoded
- [ ] **Definition of Done:** Config file exists, loads without error, api_keys.example.json documents the key requirement

### P1-T03: Create Gemini base client [M]

- [ ] **Action:** [CREATE] `scripts/api_clients/gemini_client.py`
- [ ] **Pattern:** Follows existing `BaseAPIClient` conventions but adapted for LLM calls (not REST fixture fetches)
- [ ] **Class:** `GeminiClient`
- [ ] **Key methods:**
```python
class GeminiClient:
    """Gemini API client with rate limiting, cost tracking, and response schema enforcement.

    Unlike BaseAPIClient (designed for REST APIs returning fixture data), this client
    wraps google.genai for LLM calls with structured output. It shares the same
    RateLimiter infrastructure for daily budget tracking.
    """

    def __init__(self, config_path: Path = CONFIG_DIR / "gemini_config.json"):
        """Load config, init genai.Client, set up rate limiter."""

    def generate(
        self,
        prompt: str,
        response_schema: type[BaseModel] | None = None,
        tools: list | None = None,
        thinking_level: str = "MEDIUM",
        model: str | None = None,
    ) -> GeminiResponse:
        """Core generation method with rate limiting, cost tracking, retries.

        Args:
            prompt: User prompt text
            response_schema: Pydantic model for controlled generation (JSON output)
            tools: List of types.Tool (e.g., google_search, url_context)
            thinking_level: MINIMAL / LOW / MEDIUM / HIGH
            model: Override default model

        Returns:
            GeminiResponse with .parsed (if schema), .text, .thoughts, .search_results, .usage
        """

    def search_grounded_query(
        self,
        query: str,
        response_schema: type[BaseModel] | None = None,
        thinking_level: str = "LOW",
    ) -> GeminiResponse:
        """Query with Google Search grounding enabled.

        Wraps generate() with tools=[types.Tool(google_search=types.GoogleSearch())].
        """

    def read_url(
        self,
        url: str,
        extraction_prompt: str,
        response_schema: type[BaseModel] | None = None,
    ) -> GeminiResponse:
        """Read a URL via urlContext tool and extract structured data.

        Wraps generate() with tools=[types.Tool(url_context=types.UrlContext())].
        The URL is embedded in the prompt for the model to fetch and parse.
        """

    def _track_cost(self, usage: dict) -> None:
        """Track token usage and estimated cost. Alert if daily budget exceeded."""

    def _check_budget(self) -> bool:
        """Check if daily token/request budget allows another call."""

    def get_usage_report(self) -> dict:
        """Return daily usage: requests, tokens, estimated cost USD."""
```
- [ ] **Data class:**
```python
@dataclass
class GeminiResponse:
    text: str
    parsed: BaseModel | None  # Populated when response_schema used
    thoughts: list[str]       # From thinking_config include_thoughts
    search_results: list[dict] | None  # Grounding metadata
    usage: dict               # {prompt_tokens, completion_tokens, total_tokens}
    model: str
    latency_ms: float
```
- [ ] **Rate limiting:** Uses existing `RateLimiter` from `scripts/api_clients/rate_limiter.py` with new `"gemini"` entry in `API_DAILY_LIMITS`
- [ ] **Cost tracking:** File-based daily tracker at `betting/data/.api_usage/gemini_{date}.json` — fields: `requests`, `input_tokens`, `output_tokens`, `thinking_tokens`, `estimated_cost_usd`
- [ ] **Error handling:** Retry on 429/503, raise on 400/401, log all errors to `source_health` DB table
- [ ] **Rules:** R2 (DB-first for source_health tracking), R17 (log all calls for agent monitoring), R18 (document input/output contract)
- [ ] **Integration points:**
  - Reads: `config/gemini_config.json`, `config/api_keys.json`
  - Writes: `betting/data/.api_usage/gemini_{date}.json`, `source_health` DB table
- [ ] **Definition of Done:** Client instantiates with valid API key, `generate()` returns structured response, rate limiter prevents budget overrun, cost tracking persists to file, unit tests pass with mocked API

### P1-T04: Add RateLimiter entry for Gemini [S]

- [ ] **Action:** [MODIFY] `scripts/api_clients/rate_limiter.py`
- [ ] **Changes:** Add to `API_DAILY_LIMITS`:
```python
"gemini": 1500,        # Daily request limit (configurable via gemini_config.json)
"gemini-search": 500,  # Search grounding calls (higher cost per call)
```
- [ ] **Definition of Done:** `RateLimiter` tracks Gemini calls alongside existing API clients

### P1-T05: Create Pydantic response schemas [M]

- [ ] **Action:** [CREATE] `src/bet/schemas/gemini_responses.py`
- [ ] **Schemas for Phase 1:**
```python
from pydantic import BaseModel, Field

class TipsterPickExtracted(BaseModel):
    """Single pick extracted from a tipster page via Gemini URL reading."""
    sport: str
    home_team: str
    away_team: str
    competition: str = ""
    market: str              # e.g., "Corners O9.5", "Over 2.5 goals"
    market_type: str         # "statistical" or "outcome"
    direction: str           # "OVER", "UNDER", "WIN", "DRAW"
    odds: float | None = None
    reasoning: str = ""
    confidence: str = "medium"  # "high", "medium", "low"
    stats_cited: list[str] = Field(default_factory=list)

class TipsterPageResult(BaseModel):
    """All picks extracted from a single tipster page."""
    source_site: str
    tipster_name: str = ""
    picks: list[TipsterPickExtracted]
    page_date: str = ""
    extraction_confidence: float = 0.0  # 0-1, how confident Gemini is in extraction

class WebResearchResult(BaseModel):
    """Structured result from Gemini search grounding research."""
    query: str
    data_type: str           # "h2h", "injuries", "form", "coach"
    team: str
    sport: str
    findings: list[str]      # Bullet points of factual findings
    sources_cited: list[str] # URLs of sources used
    confidence: float        # 0-1
    data_freshness: str      # "today", "this_week", "this_month", "older"

class NewsEnrichmentResult(BaseModel):
    """Injury/news/coaching enrichment from Gemini search."""
    team: str
    sport: str
    injuries: list[InjuryReport] = Field(default_factory=list)
    team_news: list[str] = Field(default_factory=list)
    coaching_changes: list[str] = Field(default_factory=list)
    morale_indicators: list[str] = Field(default_factory=list)
    sources_cited: list[str] = Field(default_factory=list)
    search_date: str = ""

class InjuryReport(BaseModel):
    """Single injury report for a player."""
    player_name: str
    status: str              # "out", "doubtful", "questionable", "probable"
    injury_type: str = ""
    expected_return: str = ""
    impact: str = "low"      # "critical", "high", "medium", "low"
    source: str = ""
```
- [ ] **Schemas for Phase 2 (defined here, used in Phase 2):**
```python
class MarketAnalysis(BaseModel):
    """Gemini's analysis of a single betting market for a candidate."""
    market_name: str
    direction: str
    confidence: float        # 0-1
    reasoning: str           # 2-3 sentence analytical reasoning
    bull_case: str           # Why this market wins
    bear_case: str           # Why this market loses
    key_stats: list[str]     # Stats that support the pick
    risk_factors: list[str]  # Factors that could upset the pick

class CandidateDeepAnalysis(BaseModel):
    """Full Gemini deep analysis for a single candidate event."""
    event: str
    sport: str
    competition: str
    recommended_markets: list[MarketAnalysis]
    upset_risk_score: float  # 0-1
    upset_risk_reasoning: str
    context_flags: list[str] # ["motivation_low", "key_player_out", etc.]
    overall_confidence: float # 0-1
    narrative: str           # 3-5 sentence summary of the event
    data_quality_assessment: str  # "FULL", "PARTIAL", "MINIMAL"
```
- [ ] **Rules:** These schemas enforce Gemini's output structure via controlled generation. No unstructured LLM output in the pipeline.
- [ ] **Definition of Done:** All schemas importable, Pydantic validation works, used by gemini_client.py for response_schema parameter

### P1-T06: Create Gemini tipster reader [L]

- [ ] **Action:** [CREATE] `scripts/gemini_tipster_reader.py`
- [ ] **Purpose:** Replace fragile BS4 HTML parsing of 12 tipster sites with Gemini URL reading. For each tipster URL, Gemini reads the page and extracts structured picks using `TipsterPageResult` schema.
- [ ] **Key function:**
```python
def read_tipster_page(
    url: str,
    source_site: str,
    sport_filter: str | None = None,
    date_filter: str | None = None,
) -> TipsterPageResult:
    """Read a tipster page via Gemini urlContext and extract picks.

    Args:
        url: Full URL of the tipster page
        source_site: Site identifier (e.g., "olbg", "pickwise")
        sport_filter: Optional sport to focus extraction on
        date_filter: Date string to filter picks for (YYYY-MM-DD)

    Returns:
        TipsterPageResult with extracted picks
    """
```
- [ ] **Prompt template:**
```
You are extracting betting picks from this tipster page.
URL: {url}
Date filter: {date_filter}
Sport filter: {sport_filter}

Extract ALL betting picks visible on the page. For each pick, identify:
- The sport, teams, competition
- The specific market (e.g., "Corners Over 9.5", "Total Goals Over 2.5")
- Whether it's a statistical market or outcome market
- The direction (OVER/UNDER/WIN/DRAW)
- Any odds mentioned
- The tipster's reasoning or analysis
- Any stats cited by the tipster

Return ONLY picks for today's date ({date_filter}). Skip ads, promotions, and non-betting content.
```
- [ ] **Fallback chain:** Gemini urlContext → existing BS4 adapter → skip (log failure)
- [ ] **Rate limiting:** One Gemini call per tipster URL. 12 sites × 1 call = 12 calls per pipeline run.
- [ ] **Integration:** Output is `list[TipsterPickExtracted]` — maps directly to existing `TipsterPick` dataclass in `tipster_aggregator.py`
- [ ] **CLI:**
```
python3 scripts/gemini_tipster_reader.py --url "https://www.olbg.com/tips" --source olbg --date 2026-05-12
python3 scripts/gemini_tipster_reader.py --batch --date 2026-05-12  # All configured sites
python3 scripts/gemini_tipster_reader.py --batch --date 2026-05-12 --sport football
```
- [ ] **Structured output:** Uses `AgentOutput` class with `--verbose` support and `AGENT_SUMMARY:{json}`
- [ ] **Rules:** R17 (--verbose), R19 (AGENT_SUMMARY), R18 (document data flow: URL → Gemini → TipsterPickExtracted → tipster_aggregator.py consumption)
- [ ] **Definition of Done:** Successfully extracts picks from ≥3 tipster sites with >80% extraction confidence; maps cleanly to existing TipsterPick format; fallback to BS4 works when Gemini fails; unit tests with mocked Gemini responses pass

### P1-T07: Integrate Gemini into tipster aggregator [M]

- [ ] **Action:** [MODIFY] `scripts/tipster_aggregator.py`
- [ ] **Changes:**
  1. Add `--use-gemini` CLI flag (default: False for safe rollout)
  2. When `--use-gemini` is set, call `gemini_tipster_reader.read_tipster_page()` instead of BS4 adapter for each site
  3. Convert `TipsterPickExtracted` → existing `TipsterPick` dataclass (field mapping)
  4. Keep existing BS4 adapters as fallback when Gemini fails per-site
  5. Add Gemini success/failure tracking in output metrics
- [ ] **Data flow:**
  - `--use-gemini` OFF: URL → HTTP fetch → BS4 parse → TipsterPick (existing path, unchanged)
  - `--use-gemini` ON: URL → GeminiClient.read_url() → TipsterPickExtracted → TipsterPick
  - Fallback: if Gemini fails for a site → fall through to existing BS4 adapter
- [ ] **Rules:** R3 (NO auto-rejection of Gemini-extracted picks), R18 (verify TipsterPickExtracted → TipsterPick field mapping matches)
- [ ] **Definition of Done:** `--use-gemini` flag works; Gemini path produces picks in same format as BS4 path; fallback activates on Gemini failure; AGENT_SUMMARY includes gemini_success_count and bs4_fallback_count

### P1-T08: Create Gemini web research module [L]

- [ ] **Action:** [CREATE] `scripts/gemini_web_research.py`
- [ ] **Purpose:** Replace L7 web research (5 SerpAPI + 10 Playwright per run) with Gemini Search Grounding. Single Gemini call can search + synthesize, replacing the SerpAPI→URL→Playwright→parse chain.
- [ ] **Key functions:**
```python
def research_team(
    team: str,
    sport: str,
    data_types: list[str],  # ["h2h", "injuries", "form", "coach"]
    opponent: str | None = None,
) -> list[WebResearchResult]:
    """Research missing data for a team via Gemini Search Grounding.

    One Gemini call per data_type (search grounding + structured output).
    More efficient than SerpAPI (5 calls) + Playwright (10 calls) chain.
    """

def research_event_context(
    home_team: str,
    away_team: str,
    sport: str,
    competition: str,
) -> EventContextResult:
    """Research full event context: injuries, form, motivation, venue, weather.

    Single Gemini call with search grounding for comprehensive context.
    """
```
- [ ] **Prompt template for research_team:**
```
Search for current {data_type} information about {team} ({sport}).
{f"Opponent: {opponent}" if opponent else ""}

Find the most recent and reliable data. Focus on:
- {data_type_specific_instructions}

Cite your sources with URLs. Only include factual information from reliable sports sites.
Freshness matters — prefer data from the last 7 days.
```
- [ ] **Rate limiting:** Uses `RateLimiter` with `"gemini-search"` key (higher cost per call). Budget: ~50 search-grounded calls per day.
- [ ] **Advantages over SerpAPI+Playwright:**
  - No per-query API cost (SerpAPI = $50/5000 searches)
  - No Playwright browser overhead (memory, startup time, Cloudflare blocks)
  - Single call synthesizes multiple search results (vs. fetch-then-parse chain)
  - Better at extracting relevant data from complex pages
- [ ] **CLI:**
```
python3 scripts/gemini_web_research.py --team "Arsenal" --sport football --need injuries,form
python3 scripts/gemini_web_research.py --team1 "Arsenal" --team2 "Chelsea" --sport football --need h2h
```
- [ ] **Structured output:** AgentOutput with --verbose, AGENT_SUMMARY
- [ ] **Rules:** R17, R19, R18
- [ ] **Definition of Done:** Successfully researches team data with >70% confidence; returns structured WebResearchResult; rate limiter prevents budget overrun; saves results to DB (team_form, or dedicated gemini_research_cache table)

### P1-T09: Integrate Gemini into web research agent [M]

- [ ] **Action:** [MODIFY] `scripts/web_research_agent.py`
- [ ] **Changes:**
  1. Add Gemini as L7a (primary), SerpAPI as L7b (fallback)
  2. When Gemini search is available (budget not exceeded), use `gemini_web_research.research_team()` first
  3. If Gemini fails or budget exceeded, fall back to existing SerpAPI + Playwright chain
  4. Update counter tracking to include Gemini searches
- [ ] **Rate limit update:** `COUNTER_FILE` format extended: `{"date": "...", "serp_count": 0, "playwright_count": 0, "gemini_search_count": 0}`
- [ ] **Rules:** R18 (verify Gemini output feeds into same downstream format as SerpAPI output)
- [ ] **Definition of Done:** Gemini is primary research method; SerpAPI activates only on Gemini failure; counter tracks all three methods

### P1-T10: Create Gemini news enrichment module [L]

- [ ] **Action:** [CREATE] `scripts/gemini_news_enrichment.py`
- [ ] **Purpose:** Injury reports, team news, coaching changes via Gemini Search Grounding. Fills the L2.5 gap — currently no automated news/injury pipeline.
- [ ] **Key function:**
```python
def enrich_team_news(
    team: str,
    sport: str,
    date: str,
) -> NewsEnrichmentResult:
    """Fetch current news, injuries, and coaching changes for a team.

    Uses Gemini with search grounding to find and structure team news.
    Results saved to DB for downstream use by context_checks.py (S5).
    """

def batch_enrich_news(
    candidates: list[dict],  # [{home_team, away_team, sport}]
    date: str,
    max_workers: int = 4,
) -> list[NewsEnrichmentResult]:
    """Batch news enrichment for all candidates in shortlist.

    Parallelized via ThreadPoolExecutor. One Gemini call per team.
    Deduplicates teams appearing in multiple fixtures.
    """
```
- [ ] **DB storage:** New table `team_news` in betting.db:
```sql
CREATE TABLE IF NOT EXISTS team_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER REFERENCES teams(id),
    sport_id INTEGER REFERENCES sports(id),
    betting_date TEXT NOT NULL,
    injuries_json TEXT DEFAULT '[]',
    news_json TEXT DEFAULT '[]',
    coaching_json TEXT DEFAULT '[]',
    morale_json TEXT DEFAULT '[]',
    sources_json TEXT DEFAULT '[]',
    confidence REAL DEFAULT 0.0,
    fetched_at TEXT NOT NULL,
    source TEXT DEFAULT 'gemini'
);
```
- [ ] **CLI:**
```
python3 scripts/gemini_news_enrichment.py --team "Arsenal" --sport football --date 2026-05-12
python3 scripts/gemini_news_enrichment.py --date 2026-05-12 --verbose  # Batch: all shortlisted teams
```
- [ ] **Structured output:** AgentOutput with --verbose
- [ ] **Rules:** R2 (save to DB via new TeamNewsRepo), R17 (--verbose), R19 (AGENT_SUMMARY)
- [ ] **Definition of Done:** Successfully fetches news for ≥80% of shortlisted teams; injuries stored in DB; context_checks.py can read from team_news table; AGENT_SUMMARY shows per-team success/failure counts

### P1-T11: Integrate news enrichment into pipeline [M]

- [ ] **Action:** [MODIFY] `scripts/data_enrichment_agent.py`
- [ ] **Changes:**
  1. After L3 Flashscore/Sofascore enrichment completes, call `gemini_news_enrichment.batch_enrich_news()` as L2.5 layer
  2. Controlled by `--news` flag (default: True when Gemini configured)
  3. Skipped if Gemini API key not configured or budget exceeded
- [ ] **Action:** [MODIFY] `scripts/context_checks.py`
- [ ] **Changes:**
  1. Read `team_news` table for injury/context data before generating context flags
  2. If `team_news` has data for a team, use it instead of (or in addition to) ESPN injury scrape
  3. Add `news_source: "gemini"` flag to context output
- [ ] **Rules:** R18 (verify team_news table schema matches what context_checks.py reads)
- [ ] **Definition of Done:** News enrichment runs as part of S2.5; context_checks.py reads Gemini news data; pipeline works with and without Gemini configured

### P1-T12: Update agent_protocol.py for Gemini [M]

- [ ] **Action:** [MODIFY] `scripts/agent_protocol.py`
- [ ] **Changes:**
  1. Add Gemini to `SELF_HEALING_REGISTRY`:
```python
"gemini_research": {
    "module": "gemini_web_research",
    "functions": {
        "research_team": "Search grounded research for missing team data. Args: (team, sport, data_types, opponent). Returns: WebResearchResult.",
        "research_event_context": "Full event context via search. Args: (home, away, sport, competition). Returns: EventContextResult.",
    },
    "use_when": "L1-L6 exhausted, or when unstructured web data needed. Preferred over L7 SerpAPI.",
    "rate_limit": "~50 search-grounded calls/day, tracked via RateLimiter('gemini-search')",
    "saves_to": ["team_news (DB)", "team_form (DB, if form data found)"],
},
"gemini_tipster": {
    "module": "gemini_tipster_reader",
    "functions": {
        "read_tipster_page": "Read tipster URL and extract structured picks. Args: (url, source_site, sport_filter, date_filter). Returns: TipsterPageResult.",
    },
    "use_when": "tipster_aggregator.py --use-gemini flag set. Replaces BS4 HTML parsing.",
    "rate_limit": "~12 urlContext calls/day (one per tipster site)",
},
"gemini_news": {
    "module": "gemini_news_enrichment",
    "functions": {
        "enrich_team_news": "Fetch injuries, news, coaching changes. Args: (team, sport, date). Returns: NewsEnrichmentResult.",
        "batch_enrich_news": "Batch news for all candidates. Args: (candidates, date). Returns: list[NewsEnrichmentResult].",
    },
    "use_when": "S2.5 enrichment phase, before S3 deep stats. Fills injury/news gaps for S5 context checks.",
    "saves_to": ["team_news (DB)"],
},
```
  2. Update `fallback_layers` list to include Gemini layers
  3. Add `DATA_FLOW_CONTRACTS` entry for `s2_5_news` step
  4. Add Gemini to `API_DAILY_LIMITS` reference in comments
- [ ] **Definition of Done:** agent_protocol.py documents all Gemini integration points; agents can discover Gemini tools via SELF_HEALING_REGISTRY

### P1-T13: Create DB migration for team_news table [S]

- [ ] **Action:** [CREATE] `scripts/migrations/003_team_news.py`
- [ ] **Purpose:** Add `team_news` table to betting.db schema
- [ ] **Also:** [MODIFY] `src/bet/db/models.py` — add `TeamNews` dataclass
- [ ] **Also:** [MODIFY] `src/bet/db/repositories.py` — add `TeamNewsRepo` class with standard CRUD + `get_by_team_and_date()`
- [ ] **Rules:** R2 (all access through repository, parameterized queries)
- [ ] **Definition of Done:** Migration runs without error; TeamNewsRepo can save and load; existing tables untouched

### P1-T14: Create unit tests for Gemini client [M]

- [ ] **Action:** [CREATE] `tests/test_gemini_client.py`
- [ ] **Test cases:**
  1. `test_generate_with_schema` — mock Gemini API, verify Pydantic parsing
  2. `test_search_grounded_query` — mock search grounding, verify search results in response
  3. `test_read_url` — mock urlContext, verify extraction
  4. `test_rate_limiter_blocks_when_budget_exceeded` — verify 429 behavior
  5. `test_cost_tracking_persists` — verify daily cost file updated
  6. `test_retry_on_503` — verify exponential backoff
  7. `test_fallback_on_gemini_failure` — tipster reader falls back to BS4
- [ ] **Mocking:** Use `unittest.mock.patch` on `google.genai.Client.models.generate_content`
- [ ] **Rules:** Tests must NOT make real API calls
- [ ] **Definition of Done:** All tests pass; covers happy path + error paths + rate limiting

### P1-T15: Create unit tests for Gemini modules [M]

- [ ] **Action:** [CREATE] `tests/test_gemini_tipster_reader.py`
- [ ] **Action:** [CREATE] `tests/test_gemini_web_research.py`
- [ ] **Action:** [CREATE] `tests/test_gemini_news_enrichment.py`
- [ ] **Test strategy:** Mock `GeminiClient` at module level; test extraction logic, data mapping, fallback chains, batch processing
- [ ] **Definition of Done:** ≥80% code coverage on Gemini modules; all data mappings to existing formats verified

### Phase 1 Summary

| Task | Complexity | Files | Type |
|------|-----------|-------|------|
| P1-T01 | S | pyproject.toml | MODIFY |
| P1-T02 | S | config/gemini_config.json, api_keys.example.json | CREATE+MODIFY |
| P1-T03 | M | scripts/api_clients/gemini_client.py | CREATE |
| P1-T04 | S | scripts/api_clients/rate_limiter.py | MODIFY |
| P1-T05 | M | src/bet/schemas/gemini_responses.py | CREATE |
| P1-T06 | L | scripts/gemini_tipster_reader.py | CREATE |
| P1-T07 | M | scripts/tipster_aggregator.py | MODIFY |
| P1-T08 | L | scripts/gemini_web_research.py | CREATE |
| P1-T09 | M | scripts/web_research_agent.py | MODIFY |
| P1-T10 | L | scripts/gemini_news_enrichment.py | CREATE |
| P1-T11 | M | data_enrichment_agent.py, context_checks.py | MODIFY |
| P1-T12 | M | scripts/agent_protocol.py | MODIFY |
| P1-T13 | S | migrations/003, models.py, repositories.py | CREATE+MODIFY |
| P1-T14 | M | tests/test_gemini_client.py | CREATE |
| P1-T15 | M | tests/test_gemini_*.py (3 files) | CREATE |

---

## 4. Phase 2 — Gemini Deep Analysis Engine

**Goal:** Add Gemini as a "second opinion" analyst for per-candidate deep reasoning.
**Risk:** MEDIUM — introduces LLM reasoning into statistical pipeline; must not replace Python calculations.
**Dependencies:** Phase 1 (P1-T03 gemini_client, P1-T05 schemas).

### P2-T01: Create Gemini deep analyst module [XL]

- [ ] **Action:** [CREATE] `scripts/gemini_deep_analyst.py`
- [ ] **Purpose:** For each candidate event, feed ALL available data to Gemini with HIGH thinking level. Get back structured analysis: market rankings, bear/bull cases, upset risk, recommended markets.
- [ ] **Key functions:**
```python
def analyze_candidate(
    candidate: dict,
    stats_a: dict,
    stats_b: dict,
    h2h: dict,
    league_profile: dict | None,
    standings: dict | None,
    odds: dict | None,
    tipster_consensus: dict | None,
    news: dict | None,
    sport: str,
) -> CandidateDeepAnalysis:
    """Deep per-candidate analysis using Gemini with HIGH thinking.

    Feeds ALL data → Gemini → structured CandidateDeepAnalysis response.
    The model reasons about: market selection, upset risk, context impact,
    bear/bull cases — things that scripted heuristics cannot capture well.

    This is a SECOND OPINION — it does NOT replace Python safety scores.
    """

def batch_analyze(
    candidates: list[dict],
    date: str,
    max_parallel: int = 3,
) -> list[CandidateDeepAnalysis]:
    """Batch analyze all candidates. Rate-limited parallel execution.

    Collects data from DB for each candidate, calls analyze_candidate().
    """
```
- [ ] **System prompt for Gemini:**
```
You are a professional sports betting analyst. You are given comprehensive statistical
data for a sporting event and must produce a structured analysis.

Your analysis MUST include:
1. Recommended STATISTICAL markets first (corners, fouls, cards, shots, totals, games, sets)
   before outcome markets (winner, ML). This is the core edge — statistical markets
   accumulate, are style-driven, and are mispriced by bookmakers.
2. For each recommended market: a clear bull case (why it wins) and bear case (why it loses).
3. An upset risk assessment with numerical score (0-1).
4. Context flags: motivation, injuries, venue, weather factors that affect the pick.
5. An overall confidence score (0-1) reflecting data quality and analysis certainty.

Base your analysis ONLY on the data provided. Do not invent statistics or cite sources
not in the input. If data is insufficient, say so and lower confidence accordingly.
```
- [ ] **Data assembly per candidate:** Reads from DB via repositories:
  - `StatsRepo.load_team_form()` → L10/L5/H2H data
  - `AnalysisResultRepo.load()` → existing Python safety scores (for comparison)
  - `StandingRepo.get_by_team()` → league standings
  - `OddsRepo.get_latest()` → current odds
  - `TeamNewsRepo.get_by_team_and_date()` → injuries/news (from P1-T10)
- [ ] **Output stored in DB:** `analysis_results.stats_summary_json` gets new field `gemini_analysis` containing the serialized `CandidateDeepAnalysis`
- [ ] **CLI:**
```
python3 scripts/gemini_deep_analyst.py --date 2026-05-12 --verbose
python3 scripts/gemini_deep_analyst.py --date 2026-05-12 --event "Arsenal vs Chelsea" --verbose
python3 scripts/gemini_deep_analyst.py --date 2026-05-12 --top 20 --verbose  # Only top 20 by safety score
```
- [ ] **Structured output:** AgentOutput with AGENT_SUMMARY: `{verdict, candidates_analyzed, avg_confidence, gemini_tokens_used, cost_usd}`
- [ ] **Rules:** R1 (agent interprets Gemini output, doesn't blindly trust it), R2 (DB-first), R3 (NO auto-rejection based on Gemini confidence), R5 (stats over outcomes in system prompt), R11 (sequential thinking per candidate by the monitoring agent), R17 (--verbose), R19 (AGENT_SUMMARY)
- [ ] **Definition of Done:** Analyzes candidates with structured output; Gemini market recommendations align with Python safety scores >60% of the time; bull/bear cases are substantive (not generic); stores in DB; monitoring agent can compare Python vs Gemini rankings

### P2-T02: Integrate into deep_stats_report.py [M]

- [ ] **Action:** [MODIFY] `scripts/deep_stats_report.py`
- [ ] **Changes:**
  1. Add `--gemini` flag (default: False)
  2. After Python safety score computation per candidate, optionally call `gemini_deep_analyst.analyze_candidate()`
  3. Add "Gemini Second Opinion" section to per-candidate report:
     - Agreement/disagreement with Python market ranking
     - Gemini's bear case for top Python pick
     - Gemini's recommended markets vs Python's top 3
  4. Compute `agreement_score` — how often Gemini and Python agree on top market
  5. When both agree → higher confidence label in output
  6. When they disagree → flag for agent review (bet-statistician must reason about disagreement)
- [ ] **Data flow:**
  - Python path: stats_cache → normalize_stats → compute_safety_scores → rank_markets → analysis_results DB
  - Gemini path: all data → Gemini → CandidateDeepAnalysis → analysis_results.stats_summary_json.gemini_analysis
  - Merge: `agreement_score` added to `stats_summary_json`
- [ ] **Rules:** R18 (verify Gemini analysis stored in correct JSON key in stats_summary_json), R3 (Gemini disagreement does NOT auto-reject Python picks)
- [ ] **Definition of Done:** `--gemini` flag works; per-candidate report includes Gemini section; agreement_score computed; pipeline works with and without --gemini

### P2-T03: Update agent_protocol.py for Gemini analysis [S]

- [ ] **Action:** [MODIFY] `scripts/agent_protocol.py`
- [ ] **Changes:**
  1. Add `gemini_deep_analyst` to `SELF_HEALING_REGISTRY`
  2. Update `bet-statistician` in `AGENT_SKILLS_MAP` to reference Gemini as optional second opinion
  3. Update `DATA_FLOW_CONTRACTS.s3_deep_stats` to note optional `gemini_analysis` field in output
- [ ] **Definition of Done:** Protocol documents Gemini analysis integration

### P2-T04: Create unit tests for Gemini analyst [M]

- [ ] **Action:** [CREATE] `tests/test_gemini_analyst.py`
- [ ] **Test cases:**
  1. `test_analyze_candidate_structured_output` — verify CandidateDeepAnalysis parsing
  2. `test_stats_over_outcomes_in_recommendations` — verify statistical markets ranked first
  3. `test_low_data_quality_reduces_confidence` — verify confidence drops with missing data
  4. `test_agreement_score_calculation` — verify Python vs Gemini agreement math
  5. `test_gemini_failure_graceful` — verify pipeline continues without Gemini on API error
- [ ] **Definition of Done:** All tests pass; Gemini failure never breaks the pipeline

### Phase 2 Summary

| Task | Complexity | Files | Type |
|------|-----------|-------|------|
| P2-T01 | XL | scripts/gemini_deep_analyst.py | CREATE |
| P2-T02 | M | scripts/deep_stats_report.py | MODIFY |
| P2-T03 | S | scripts/agent_protocol.py | MODIFY |
| P2-T04 | M | tests/test_gemini_analyst.py | CREATE |

---

## 5. Phase 3 — React Dashboard (Read-Only Viewer)

**Goal:** Lightweight web UI over existing SQLite DB. No Python logic porting.
**Risk:** MEDIUM — new technology stack (TypeScript/Next.js), but read-only = limited blast radius.
**Dependencies:** None (reads existing DB). Can run in parallel with Phase 1-2.

### P3-T01: Initialize Next.js project [M]

- [ ] **Action:** [CREATE] `dashboard/` directory with Next.js App Router scaffolding
- [ ] **Stack:**
  - Next.js 15+ (App Router)
  - TypeScript
  - Tailwind CSS
  - better-sqlite3 (for server-side SQLite reading)
  - shadcn/ui (component library)
- [ ] **Key files:**
```
dashboard/
├── package.json
├── tsconfig.json
├── next.config.ts
├── tailwind.config.ts
├── src/
│   ├── app/
│   │   ├── layout.tsx          # Root layout with nav
│   │   ├── page.tsx            # Pipeline status overview
│   │   ├── candidates/
│   │   │   └── page.tsx        # Candidate board
│   │   ├── coupons/
│   │   │   └── page.tsx        # Coupon viewer
│   │   ├── settlement/
│   │   │   └── page.tsx        # Settlement history
│   │   ├── bankroll/
│   │   │   └── page.tsx        # Bankroll tracker
│   │   └── api/
│   │       ├── data/
│   │       │   └── route.ts    # Read-only DB queries
│   │       └── pipeline/
│   │           └── route.ts    # Trigger Python scripts
│   ├── lib/
│   │   ├── db.ts               # SQLite connection
│   │   └── types.ts            # TypeScript types matching Python models
│   └── components/
│       ├── nav.tsx
│       ├── candidate-card.tsx
│       ├── coupon-table.tsx
│       ├── pipeline-status.tsx
│       └── bankroll-chart.tsx
```
- [ ] **package.json dependencies:**
```json
{
  "dependencies": {
    "next": "^15.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "better-sqlite3": "^11.0.0",
    "tailwindcss": "^4.0.0"
  },
  "devDependencies": {
    "@types/better-sqlite3": "^7.0.0",
    "@types/node": "^22.0.0",
    "@types/react": "^19.0.0",
    "typescript": "^5.7.0"
  }
}
```
- [ ] **Definition of Done:** `npm run dev` starts dashboard at localhost:3000; basic layout renders

### P3-T02: Create SQLite reader [M]

- [ ] **Action:** [CREATE] `dashboard/src/lib/db.ts`
- [ ] **Purpose:** Read-only access to `betting/data/betting.db` via better-sqlite3
- [ ] **Key functions:**
```typescript
import Database from 'better-sqlite3';
import path from 'path';

const DB_PATH = path.resolve(__dirname, '../../../../betting/data/betting.db');

export function getDb(): Database.Database {
  const db = new Database(DB_PATH, { readonly: true });
  db.pragma('journal_mode = WAL');
  return db;
}

// Query helpers
export function getCandidates(date: string): Candidate[] { ... }
export function getCoupons(date: string): Coupon[] { ... }
export function getPipelineStatus(date: string): PipelineRun[] { ... }
export function getSettlementHistory(limit: number): Settlement[] { ... }
export function getBankrollHistory(): BankrollEntry[] { ... }
export function getSourceHealth(): SourceHealth[] { ... }
```
- [ ] **Security:** Read-only mode (better-sqlite3 `readonly: true`). No write operations from dashboard.
- [ ] **Rules:** DB path relative to project root, not hardcoded absolute
- [ ] **Definition of Done:** All query functions return typed data; read-only mode enforced; handles DB not found gracefully

### P3-T03: Create TypeScript types [S]

- [ ] **Action:** [CREATE] `dashboard/src/lib/types.ts`
- [ ] **Purpose:** TypeScript interfaces matching Python dataclasses in `src/bet/db/models.py`
- [ ] **Types:** Candidate, Coupon, Bet, PipelineRun, GateResult, AnalysisResult, SourceHealth, TeamForm, OddsRecord, etc.
- [ ] **Definition of Done:** Types match DB schema; no `any` types in query results

### P3-T04: Pipeline status page [M]

- [ ] **Action:** [CREATE] `dashboard/src/app/page.tsx`
- [ ] **Features:**
  - Current day's pipeline progress (which steps completed, running, failed)
  - Per-step metrics from `pipeline_runs` table
  - Source health overview (from `source_health` table)
  - Quick stats: total candidates, approved, rejected, coupon count
- [ ] **Data source:** `pipeline_runs`, `source_health`, `scan_run_stats` tables
- [ ] **Definition of Done:** Shows real pipeline state for today's date; auto-refreshes; handles no-data state

### P3-T05: Candidate board page [L]

- [ ] **Action:** [CREATE] `dashboard/src/app/candidates/page.tsx`
- [ ] **Features:**
  - Table/grid of all candidates for a date
  - Columns: Event, Sport, Competition, Safety Score, Best Market, Gate Status, EV, Data Quality
  - Filters: by sport, gate status (STRONG/MODERATE/WEAK/FLAGGED), data quality (FULL/PARTIAL/MINIMAL)
  - Sort: by safety score, EV, gate score
  - Expandable row: full market ranking, bear/bull cases, Gemini analysis (if Phase 2 done)
  - Color coding: green (STRONG), yellow (MODERATE), orange (WEAK), red (FLAGGED)
- [ ] **Data source:** `analysis_results`, `gate_results`, `fixtures`, `teams`, `competitions` tables
- [ ] **Definition of Done:** All candidates visible with filtering/sorting; expandable details work; handles 100+ candidates performantly

### P3-T06: Coupon viewer page [M]

- [ ] **Action:** [CREATE] `dashboard/src/app/coupons/page.tsx`
- [ ] **Features:**
  - List of coupons for a date (core, combo, discovery)
  - Per-coupon: legs, total odds, stake, status, PnL
  - Expandable: per-leg details (safety score, market, odds, reasoning)
  - Settlement status colors: pending (blue), won (green), lost (red), partial (yellow)
- [ ] **Data source:** `coupons`, `bets`, `fixtures` tables
- [ ] **Definition of Done:** Coupons render correctly; settlement colors work; handles dates with no coupons

### P3-T07: Settlement history page [M]

- [ ] **Action:** [CREATE] `dashboard/src/app/settlement/page.tsx`
- [ ] **Features:**
  - Historical settlement results with PnL per day
  - Cumulative PnL chart (line graph)
  - Win rate by sport, market type
  - Coupon killer analysis (which legs fail most)
- [ ] **Data source:** `coupons`, `bets`, `decision_outcomes` tables
- [ ] **Definition of Done:** Historical data renders; PnL chart shows trend; win rates calculated correctly

### P3-T08: Bankroll tracker page [S]

- [ ] **Action:** [CREATE] `dashboard/src/app/bankroll/page.tsx`
- [ ] **Features:**
  - Current bankroll from config
  - Daily exposure tracking
  - Bankroll history chart
  - 20% drawdown warning indicator
- [ ] **Data source:** `config/betting_config.json` + `coupons` table aggregates
- [ ] **Definition of Done:** Shows current bankroll; drawdown indicator works

### P3-T09: Pipeline trigger API [M]

- [ ] **Action:** [CREATE] `dashboard/src/app/api/pipeline/route.ts`
- [ ] **Purpose:** API endpoint to trigger Python pipeline scripts from dashboard
- [ ] **Endpoints:**
  - `POST /api/pipeline/scan` → spawns `python3 scripts/scan_events.py --date {date} --verbose`
  - `POST /api/pipeline/enrich` → spawns `python3 scripts/data_enrichment_agent.py --date {date} --verbose`
  - `POST /api/pipeline/analyze` → spawns `python3 scripts/deep_stats_report.py --date {date} --verbose`
  - `POST /api/pipeline/gate` → spawns `python3 scripts/gate_checker.py --date {date} --verbose`
  - `POST /api/pipeline/coupons` → spawns `python3 scripts/coupon_builder.py --date {date} --verbose`
- [ ] **Implementation:** `child_process.spawn()` with stdout/stderr streaming
- [ ] **Security:**
  - Only localhost access (no external exposure)
  - CSRF protection via same-origin check
  - Script path whitelist — only allowed scripts can be triggered
  - No user input passed to shell (date validated as YYYY-MM-DD regex)
  - Rate limit: max 1 pipeline trigger per 60 seconds
- [ ] **Rules:** R1 (dashboard triggers scripts but AGENTS still analyze output), R17 (always --verbose), R20 (no inline Python — spawn full script commands)
- [ ] **Definition of Done:** Scripts spawn correctly; stdout streams to response; security controls tested; only whitelisted scripts allowed

### P3-T10: Data read API [M]

- [ ] **Action:** [CREATE] `dashboard/src/app/api/data/route.ts`
- [ ] **Purpose:** Generic read-only API for dashboard pages to fetch DB data
- [ ] **Endpoints:**
  - `GET /api/data/candidates?date=YYYY-MM-DD`
  - `GET /api/data/coupons?date=YYYY-MM-DD`
  - `GET /api/data/pipeline?date=YYYY-MM-DD`
  - `GET /api/data/settlement?limit=30`
  - `GET /api/data/bankroll`
  - `GET /api/data/source-health`
- [ ] **Security:** Read-only (better-sqlite3 readonly mode). Input validation on date/limit parameters. No SQL injection via parameterized queries.
- [ ] **Definition of Done:** All endpoints return JSON matching TypeScript types; error handling for missing DB/tables

### Phase 3 Summary

| Task | Complexity | Files | Type |
|------|-----------|-------|------|
| P3-T01 | M | dashboard/ (scaffolding) | CREATE |
| P3-T02 | M | dashboard/src/lib/db.ts | CREATE |
| P3-T03 | S | dashboard/src/lib/types.ts | CREATE |
| P3-T04 | M | dashboard/src/app/page.tsx | CREATE |
| P3-T05 | L | dashboard/src/app/candidates/page.tsx | CREATE |
| P3-T06 | M | dashboard/src/app/coupons/page.tsx | CREATE |
| P3-T07 | M | dashboard/src/app/settlement/page.tsx | CREATE |
| P3-T08 | S | dashboard/src/app/bankroll/page.tsx | CREATE |
| P3-T09 | M | dashboard/src/app/api/pipeline/route.ts | CREATE |
| P3-T10 | M | dashboard/src/app/api/data/route.ts | CREATE |

---

## 6. Phase 4 — Agent Consolidation (Optional)

**Goal:** Reduce prompt management overhead by merging related agents.
**Risk:** LOW — refactoring agent definitions, no code changes.
**Dependencies:** None. Independent of Phases 1-3.

### P4-T01: Merge bet-scout + bet-enricher → bet-data-specialist [M]

- [ ] **Action:** [MODIFY] `.github/agents/bet-data-specialist.agent.md` (new, replaces two agents)
- [ ] **Rationale:** Both deal with data acquisition. Scout handles tipster data, enricher handles stats data. Merged agent handles all data sourcing.
- [ ] **Delete:** `bet-scout.agent.md`, `bet-enricher.agent.md`
- [ ] **Update:** Orchestrator prompt references, agent_protocol.py AGENT_SKILLS_MAP
- [ ] **Definition of Done:** Single agent handles S1b + S2 + S2.5; orchestrator prompt updated; old agent files removed

### P4-T02: Merge bet-valuator + bet-challenger → bet-analyst [M]

- [ ] **Action:** [MODIFY] `.github/agents/bet-analyst.agent.md` (new, replaces two agents)
- [ ] **Rationale:** Both analyze existing data. Valuator does odds/EV, challenger does context/upset/gate. Merged agent handles S4 + S5 + S6 + S7.
- [ ] **Delete:** `bet-valuator.agent.md`, `bet-challenger.agent.md`
- [ ] **Update:** Orchestrator prompt, agent_protocol.py
- [ ] **Definition of Done:** Single agent handles S4-S7; orchestrator delegates correctly

### P4-T03: Update orchestrator prompt [S]

- [ ] **Action:** [MODIFY] `.github/prompts/orchestrate-betting-day.prompt.md`
- [ ] **Changes:** Update delegation targets from 10 agents to 6:
  1. `bet-scanner` (S1 scan verification)
  2. `bet-data-specialist` (S1b, S2, S2.5 — tipsters + enrichment)
  3. `bet-statistician` (S3 deep analysis)
  4. `bet-analyst` (S4-S7 — odds, context, upset, gate)
  5. `bet-builder` (S8 coupon construction)
  6. `bet-db-analyst` (cross-cutting DB queries)
- [ ] **Definition of Done:** Orchestrator prompt references correct agent names; delegation instructions updated

### Phase 4 Summary

| Task | Complexity | Files | Type |
|------|-----------|-------|------|
| P4-T01 | M | .github/agents/ | CREATE+DELETE+MODIFY |
| P4-T02 | M | .github/agents/ | CREATE+DELETE+MODIFY |
| P4-T03 | S | .github/prompts/ | MODIFY |

---

## 7. Risk Analysis

### Phase 1 Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Gemini API rate limits hit during pipeline | MEDIUM | LOW | Daily budget tracking in gemini_client.py; fallback to existing sources |
| Gemini extracts wrong picks from tipster pages | MEDIUM | MEDIUM | Extraction confidence score; fallback to BS4; human review of first 10 runs |
| Gemini API key cost overrun | LOW | MEDIUM | `cost_tracking.alert_threshold_usd` in config; daily budget cap |
| Gemini Search Grounding returns stale data | LOW | LOW | `data_freshness` field in WebResearchResult; prefer sources < 7 days old |
| google-genai SDK breaking changes | LOW | MEDIUM | Pin version in pyproject.toml; test suite catches regressions |

### Phase 2 Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Gemini disagrees with Python on market ranking | HIGH | LOW | Agreement score tracking; both shown to user; Python is ground truth |
| Gemini produces generic/low-quality analysis | MEDIUM | MEDIUM | System prompt engineering; thinking_level=HIGH; quality gate on confidence |
| Token cost high with per-candidate analysis | MEDIUM | MEDIUM | `--top N` flag to limit candidates; flash model for routine, pro for complex |
| Gemini hallucinates statistics | MEDIUM | HIGH | Response validated against DB data; any stat not in input flagged as hallucination |

### Phase 3 Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| SQLite concurrent read issues | LOW | LOW | WAL mode + readonly; better-sqlite3 handles well |
| Pipeline trigger API security | MEDIUM | HIGH | Localhost only; script whitelist; input validation; rate limiting |
| Dashboard stale data | LOW | LOW | Polling interval on status page; manual refresh on candidate board |
| better-sqlite3 native module build issues | MEDIUM | LOW | Use prebuild binaries; document Node.js version requirement |

### Phase 4 Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Merged agents lose specialized behavior | LOW | MEDIUM | Comprehensive agent definitions; test with real pipeline runs |
| Orchestrator delegation breaks | LOW | MEDIUM | Test delegation flow before removing old agents |

---

## 8. Cost Analysis

### Gemini API Costs (estimated per day)

| Usage Type | Model | Calls/Day | Tokens/Call | Cost/Day (est.) |
|-----------|-------|-----------|-------------|-----------------|
| Tipster URL reading (P1) | Flash | 12 | ~4K in + 1K out | ~$0.01 |
| Search grounding research (P1) | Flash | 30 | ~2K in + 1K out | ~$0.02 |
| News enrichment (P1) | Flash | 60 (30 teams × 2) | ~2K in + 500 out | ~$0.02 |
| Deep analysis per candidate (P2) | Pro | 40 | ~8K in + 2K out (+ thinking) | ~$0.80 |
| **Total Phase 1 only** | | ~102 | | **~$0.05/day** |
| **Total Phase 1 + 2** | | ~142 | | **~$0.85/day** |
| **Monthly estimate (P1+P2)** | | ~4,260 | | **~$25.50/month** |

*Note: Gemini 3 Flash is significantly cheaper than Pro. Phase 1 uses Flash exclusively. Phase 2 uses Pro for deep analysis (higher thinking token costs). Actual costs depend on response length and thinking depth.*

### Dashboard Costs (Phase 3)

- **Infrastructure:** $0 — runs locally on developer machine
- **Dependencies:** Open source (Next.js, better-sqlite3, Tailwind)
- **Ongoing:** $0 — no hosting, no external services

### Comparison with Current Costs

| Current Service | Monthly Cost | Phase 1 Replacement | New Cost |
|----------------|-------------|---------------------|----------|
| SerpAPI (L7 web research) | ~$50/5000 searches | Gemini Search Grounding | ~$0.60 |
| Playwright (browser overhead) | $0 (compute time) | Gemini URL reading | ~$0.30 |
| The-Odds-API | Free tier (500/month) | KEPT — not replaced | $0 |
| API-Sports (football/basketball/hockey) | Free tier (100/day) | KEPT — not replaced | $0 |

---

## 9. Dependencies & Ordering

```
Phase 1 (Gemini Data Intelligence)
├── P1-T01 (deps) ──────────────────────────→ ALL P1 tasks
├── P1-T02 (config) ────────────────────────→ P1-T03
├── P1-T03 (client) ────────────────────────→ P1-T06, P1-T08, P1-T10
├── P1-T04 (rate limiter) ──────────────────→ P1-T03
├── P1-T05 (schemas) ──────────────────────→ P1-T06, P1-T08, P1-T10
├── P1-T06 (tipster reader) ────────────────→ P1-T07
├── P1-T07 (tipster integration) ───────────→ (none — optional flag)
├── P1-T08 (web research) ─────────────────→ P1-T09
├── P1-T09 (web research integration) ─────→ (none — optional flag)
├── P1-T10 (news enrichment) ──────────────→ P1-T11, P1-T13
├── P1-T11 (pipeline integration) ─────────→ (none — optional flag)
├── P1-T12 (protocol update) ──────────────→ (none — documentation)
├── P1-T13 (DB migration) ────────────────→ P1-T10
├── P1-T14 (tests: client) ───────────────→ (none — validates P1-T03)
└── P1-T15 (tests: modules) ──────────────→ (none — validates P1-T06/T08/T10)

Phase 2 (Gemini Analysis) — REQUIRES P1-T03, P1-T05
├── P2-T01 (deep analyst) ─────────────────→ P2-T02
├── P2-T02 (integration) ─────────────────→ (none — optional flag)
├── P2-T03 (protocol update) ──────────────→ (none — documentation)
└── P2-T04 (tests) ───────────────────────→ (none — validates P2-T01)

Phase 3 (Dashboard) — INDEPENDENT, can run in parallel with P1/P2
├── P3-T01 (scaffolding) ─────────────────→ ALL P3 tasks
├── P3-T02 (DB reader) ───────────────────→ P3-T04 through P3-T10
├── P3-T03 (types) ────────────────────────→ P3-T02
├── P3-T04 through P3-T08 (pages) ────────→ (parallel, independent)
├── P3-T09 (pipeline API) ────────────────→ (none)
└── P3-T10 (data API) ────────────────────→ P3-T04 through P3-T08

Phase 4 (Agent Consolidation) — INDEPENDENT
├── P4-T01 (merge scouts) ────────────────→ P4-T03
├── P4-T02 (merge analysts) ──────────────→ P4-T03
└── P4-T03 (orchestrator update) ─────────→ (none)
```

**Recommended execution order:**
1. P1-T01 → P1-T02 → P1-T04 → P1-T03 → P1-T05 (foundation)
2. P1-T13 (DB migration — unblocks P1-T10)
3. P1-T06 + P1-T08 + P1-T10 (parallel: three Gemini modules)
4. P1-T07 + P1-T09 + P1-T11 (parallel: three integrations)
5. P1-T12 + P1-T14 + P1-T15 (protocol + tests)
6. P3-T01 → P3-T03 → P3-T02 (dashboard foundation — can start during P1)
7. P3-T04 through P3-T10 (dashboard pages — parallel)
8. P2-T01 → P2-T02 → P2-T03 → P2-T04 (after P1 validated in production)
9. P4-T01 → P4-T02 → P4-T03 (whenever convenient)

---

## 10. Success Metrics

### Phase 1

| Metric | Target | Measurement |
|--------|--------|-------------|
| Tipster extraction success rate | ≥80% of sites return valid picks | AGENT_SUMMARY gemini_success_count / total_sites |
| Web research data found rate | ≥70% of queries return useful data | WebResearchResult.confidence > 0.5 |
| News enrichment coverage | ≥80% of shortlisted teams get news | batch_enrich_news success_count / total_teams |
| Pipeline time impact | ≤+2 min vs current pipeline | Measure S1b + S2.5 step duration |
| Daily API cost | ≤$0.10/day for Phase 1 | gemini_{date}.json cost tracker |
| BS4 fallback rate | ≤30% (Gemini handles ≥70%) | tipster_aggregator AGENT_SUMMARY |
| Zero pipeline regressions | 0 failures caused by Gemini integration | Pipeline success rate unchanged when --use-gemini off |

### Phase 2

| Metric | Target | Measurement |
|--------|--------|-------------|
| Python-Gemini agreement on top market | ≥60% | agreement_score in analysis_results |
| Gemini analysis quality (manual review) | ≥4/5 average | User rates 10 random analyses after first week |
| Bear case specificity | ≥80% cite specific stats/context | Manual review: bear cases reference actual data, not generic concerns |
| Daily API cost (P1+P2) | ≤$1.00/day | gemini_{date}.json cost tracker |
| Per-candidate analysis latency | ≤15s average | AGENT_SUMMARY avg_latency_ms |

### Phase 3

| Metric | Target | Measurement |
|--------|--------|-------------|
| Dashboard loads in <2s | ≤2s on localhost | Browser performance tab |
| All DB data visible | 100% of pipeline data queryable | Each page shows data matching terminal output |
| Pipeline trigger works | Scripts spawn correctly | POST /api/pipeline/* returns 200 and script runs |
| Zero security issues | No SQL injection, no arbitrary code exec | Security review of API routes |

### Phase 4

| Metric | Target | Measurement |
|--------|--------|-------------|
| Agent count reduction | 10 → 6 | Count of .agent.md files |
| Pipeline output quality unchanged | Same pick quality as before merge | Compare coupons from 5 days pre/post merge |

---

## 11. Rollback Strategy

### Phase 1 Rollback

- **Gemini tipster reader:** Remove `--use-gemini` flag from tipster_aggregator.py commands. Existing BS4 adapters are untouched and remain default.
- **Gemini web research:** Set Gemini budget to 0 in gemini_config.json. web_research_agent.py falls back to SerpAPI + Playwright.
- **Gemini news enrichment:** Remove `--news` flag from data_enrichment_agent.py commands. context_checks.py falls back to existing injury sources.
- **Nuclear option:** Remove `google-genai` from pyproject.toml dependencies. All Gemini code paths check for importability and gracefully degrade.

**Rollback mechanism:** Every Gemini integration is behind a feature flag:
- `--use-gemini` (tipster aggregator)
- `--gemini` (deep stats report)
- `--news` (data enrichment)
- `gemini_config.json` budget = 0 (kills all Gemini calls)

### Phase 2 Rollback

- **Gemini analyst:** Remove `--gemini` flag from deep_stats_report.py commands. Python safety scores are the primary path and are always computed regardless of Gemini.
- `gemini_analysis` field in `stats_summary_json` is simply ignored if not populated.

### Phase 3 Rollback

- **Dashboard:** Delete `dashboard/` directory. Zero impact on Python pipeline — dashboard is a read-only viewer with no write access to DB.
- Pipeline works identically with or without dashboard running.

### Phase 4 Rollback

- **Agent consolidation:** Restore old .agent.md files from git. Revert orchestrator prompt. Agent definitions are just markdown files — easy to revert.

---

## 12. Non-Negotiable Rules Compliance Matrix

| Rule | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|------|---------|---------|---------|---------|
| R1 (Agent-driven) | Gemini scripts are DATA TOOLS; agents analyze output | Gemini analysis is input FOR agents, not replacement | Dashboard triggers scripts; agents still analyze | Agent merges preserve R1 |
| R2 (DB-first) | team_news table via TeamNewsRepo; source_health tracking | gemini_analysis in analysis_results via repo | better-sqlite3 readonly; no writes from dashboard | N/A |
| R3 (No auto-rejection) | Gemini confidence never auto-rejects picks | Gemini disagreement never auto-rejects Python picks | Dashboard shows ALL candidates regardless of status | N/A |
| R5 (Stats over outcomes) | Gemini system prompt enforces stats-first extraction | Deep analysis system prompt requires stats markets first | Candidate board sorts by safety score (stats) | N/A |
| R6 (Betclic learning advisory) | Not affected | Not affected | Shows hit rates but doesn't filter | N/A |
| R12 (All picks conditional) | Gemini tipster data is informational; no Betclic scraping | Gemini analysis is advisory; user decides | Dashboard shows "CONDITIONAL" on all picks | N/A |
| R14 (Data depth) | data_quality_score computed for Gemini-enriched data | Gemini `data_quality_assessment` in output | Shows data quality label on candidate board | N/A |
| R17 (Live monitoring) | All Gemini scripts support --verbose + AGENT_SUMMARY | gemini_deep_analyst.py supports --verbose | Pipeline trigger API passes --verbose | N/A |
| R18 (Data flow) | All data contracts documented in agent_protocol.py | s3_deep_stats contract updated for gemini_analysis field | API routes return same data as DB queries | N/A |
| R19 (Structured output) | All new scripts emit AGENT_SUMMARY:{json} | AGENT_SUMMARY includes agreement_score | N/A (JS app, not pipeline script) | N/A |
| R20 (Fish shell) | No inline Python; all via script files | No inline Python | `npm run dev` is a simple shell command | N/A |

---

## 13. Implementation Checklist

### Phase 1: Gemini Data Intelligence Layer
- [ ] P1-T01: Add google-genai + pydantic deps to pyproject.toml
- [ ] P1-T02: Create gemini_config.json + update api_keys
- [ ] P1-T03: Create gemini_client.py (base client)
- [ ] P1-T04: Add Gemini to RateLimiter
- [ ] P1-T05: Create Pydantic response schemas
- [ ] P1-T06: Create gemini_tipster_reader.py
- [ ] P1-T07: Integrate Gemini into tipster_aggregator.py
- [ ] P1-T08: Create gemini_web_research.py
- [ ] P1-T09: Integrate Gemini into web_research_agent.py
- [ ] P1-T10: Create gemini_news_enrichment.py
- [ ] P1-T11: Integrate news into data_enrichment + context_checks
- [ ] P1-T12: Update agent_protocol.py
- [ ] P1-T13: DB migration for team_news table
- [ ] P1-T14: Unit tests for gemini_client
- [ ] P1-T15: Unit tests for Gemini modules

### Phase 2: Gemini Deep Analysis Engine
- [ ] P2-T01: Create gemini_deep_analyst.py
- [ ] P2-T02: Integrate into deep_stats_report.py
- [ ] P2-T03: Update agent_protocol.py
- [ ] P2-T04: Unit tests for Gemini analyst

### Phase 3: React Dashboard
- [ ] P3-T01: Initialize Next.js project
- [ ] P3-T02: Create SQLite reader
- [ ] P3-T03: Create TypeScript types
- [ ] P3-T04: Pipeline status page
- [ ] P3-T05: Candidate board page
- [ ] P3-T06: Coupon viewer page
- [ ] P3-T07: Settlement history page
- [ ] P3-T08: Bankroll tracker page
- [ ] P3-T09: Pipeline trigger API
- [ ] P3-T10: Data read API

### Phase 4: Agent Consolidation (Optional)
- [ ] P4-T01: Merge bet-scout + bet-enricher
- [ ] P4-T02: Merge bet-valuator + bet-challenger
- [ ] P4-T03: Update orchestrator prompt

---

*Total tasks: 34 (15 Phase 1 + 4 Phase 2 + 10 Phase 3 + 3 Phase 4 optional)*
*New files: ~20 | Modified files: ~12 | Deleted files: 4 (Phase 4 only)*
