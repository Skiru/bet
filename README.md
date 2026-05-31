# Agent-Driven Sports Betting Pipeline

A fully autonomous, agent-orchestrated sports betting pipeline built on GitHub Copilot custom agents, skills, and instructions — powered by a locally-hosted **Qwen3.6-35B-A3B MoE 4-bit** language model (131K context window, chain-of-thought reasoning always enabled) running on Apple Silicon (M4 Pro 48GB). It targets small-bankroll disciplined betting on the **Betclic** bookmaker, covering **8 sports**: Football, Volleyball, Basketball, Tennis, Hockey, CS2, Dota 2, and Valorant.

**Core design principle:** Scripts compute raw data; the language model reasons, analyzes, and constructs arguments. Python scripts are data producers; AI agents are the analysts, challengers, and portfolio constructors. There is no monolithic orchestrator script — the LLM itself IS the orchestrator, running each step sequentially, delegating analysis to specialist sub-agents, and making routing decisions based on live data.

---

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
# Optional: dev tools
pip install -e ".[dev]"
```

---

## What This Project Requires From a Language Model

This system demands an extremely specific and rare combination of capabilities:

### 1. Multi-Turn Sequential Orchestration
The model must maintain pipeline state across 12+ discrete phases, remembering what was accomplished, what failed, and what comes next. It tracks hundreds of candidates simultaneously across a single session.

### 2. Structured Analytical Reasoning with Chain-of-Thought
Every decision (market selection, risk scoring, coupon construction) requires explicit `<think>` blocks and sequential thinking tool calls. The model reasons about probabilities, safety scores, expected value calculations, and Poisson/Negative Binomial distributions.

### 3. Tool-Use Orchestration
The model calls 20+ distinct tools (SQLite queries, web search, terminal commands, Playwright browser automation, file I/O, sequential thinking) in a disciplined order, interpreting outputs and routing decisions dynamically.

### 4. Multi-Agent Delegation
The orchestrator model spawns specialist sub-agents (via `runSubagent`) with focused context windows, each receiving structured payloads and returning structured verdicts (`APPROVED` / `FLAGGED` / `REJECTED`).

### 5. Domain Expertise in Sports Statistics
Understanding of L10/L5 averages, hit rates, H2H market-specific validation, Poisson modeling (`λ = 40%×L5 + 35%×L10 + 25%×H2H`), Kelly criterion (¼ fraction), EV calculation (`EV = hit_rate × odds - 1`), and closing line value (CLV) tracking.

### 6. Anti-Hallucination Discipline
Every stat cited must trace back to an actual DB query or file read. The model NEVER invents odds, lineups, injuries, results, or statistical values. A mechanical 4-pass validation is mandatory before presenting any coupon to the user.

### 7. Error Recovery and Self-Healing
When scripts fail, data is missing, or sources are blocked, the model diagnoses root causes, tries fallback chains (L1→L7c across 7 layers), and decides when to escalate vs. retry.

### 8. Sport-Specific Protocol Adherence
6 distinct statistical protocol sets (Football §3.1, Tennis §3.2, Basketball §3.3, Hockey §3.4, Volleyball §3.5, Esports §3.6) with different stat tables, market hierarchies, red flag checklists, and upset risk calculations per sport.

### 9. Bilingual Output
Internal analysis in English, but final coupon artifacts with Polish market names matching the Betclic UI exactly (e.g., "Powyżej 9.5 rzutów rożnych").

### 10. Long-Context Utilization
Processing 131K tokens of accumulated pipeline state, DB query results, tipster arguments, and analysis artifacts within a single session without losing track of earlier findings.

---

## Pipeline Phases (Complete Detail)

### S0 — Settlement & Historical Learning

| | |
|---|---|
| **Script** | `settle_on_finish.py --betting-day YYYY-MM-DD` |
| **Agent** | `bet-settler` |
| **Purpose** | Settle all pending picks from the previous betting day |

**What happens:**
- Calculate PnL per pick and per coupon using strict rules (win/loss/push/void/half_win/half_loss)
- Identify "coupon killers" — the single leg that killed each lost accumulator
- Run post-mortem per loss: was it **bad thesis** (wrong analysis) or **variance** (correct thesis, unlucky)?
- Update working bankroll in `config/betting_config.json`
- Apply 20% drawdown protection: if bankroll dropped >20% from peak → reduce daily exposure by 25%

**Mandatory sub-step §0.2 — Historical Learning Query:**
- Analyze `betclic_bets_history.json` (ground truth of ALL placed bets) + `picks-ledger.csv`
- Extract: per-market hit rates, per-sport hit rates, streak detection, coupon failure patterns
- This is **ADVISORY data shown to the user** — never used for auto-rejection of any market or sport
- Run `analyze_betclic_learning.py` for live statistics

**Gate:** If `betclic_bets_history.json` is not read, S0 is INCOMPLETE. Pipeline cannot proceed.

**Output:** Settlement report, updated ledgers, bankroll adjustment, 3-line advisory summary.

---

### S1 — Event Discovery & Scan

| | |
|---|---|
| **Scripts** | `discover_events.py` + `ingest_scan_stats.py` |
| **Agent** | `bet-scanner` |
| **Purpose** | Scan ALL available sporting events for the betting day |

**What happens:**
- Discover fixtures from multiple sources (Flashscore, SofaScore, Odds-API.io, The-Odds-API, API-Football)
- Cross-validate each fixture appears in ≥2 independent sources (§1.8 fixture verification)
- Deep-link into tournament sub-pages — include 2nd/3rd divisions, cups, women's leagues
- Track source health (response times, failure rates, consecutive failures)

**Coverage mandate:** ≥50 events, ≥5 sports. Wide scan across ALL leagues, not just top divisions.

**Circuit breaker:** If 0 events → retry with extended timeout → check source health → try alternative sources.

**Output:** `{date}_s1_events.json`, `market_matrix_{date}.json`, populated `scan_results` + `fixtures` + `fixture_sources` DB tables.

---

### S1e — Shortlist Construction

| | |
|---|---|
| **Script** | `build_shortlist.py --stats-first --all-fixtures` |
| **Agent** | `bet-scanner` (continued) |
| **Purpose** | Build the canonical candidate universe from raw scan |

**What happens:**
- Apply stats-first filtering (statistical markets prioritized over outcome markets)
- Verify sport diversity across the shortlist
- Flag phantom fixtures (events that don't actually exist)
- Ensure no artificial caps, auto-filtering, or aggressive narrowing

**Critical validation:** Candidate count must be ≥20% of raw events. If suspiciously low → wrong input file detected → re-run.

**Output:** `{date}_s2_shortlist.json` — THE source of truth for all subsequent steps (S2–S8).

---

### S2 — Tipster Aggregation & Cross-Reference

| | |
|---|---|
| **Scripts** | `tipster_aggregator.py` + `tipster_xref.py` |
| **Agent** | `bet-scout` |
| **Purpose** | Aggregate tipster picks and find consensus |

**What happens:**
- Scrape Tier B tipster sites via Playwright DOM scraping
- Each pick includes: source site, tipster name, sport, event, market, direction, odds, AND **full textual reasoning** + **stats cited**
- Cross-reference tipster picks against the shortlist to find consensus (≥2 independent tipsters agree on same event/market)
- Identify analytical angles that pure statistics might miss (tactical setups, motivational factors, insider context)

**Core value:** Tipster arguments provide TACTICAL and MOTIVATIONAL reasoning that statistics cannot capture:
- "Manager recently sacked, players lack motivation"
- "Team fighting relegation, expect aggressive fouls"
- "Key striker back from injury, team's L5 attack stats misleading"

**Gate (NEVER SKIP):** If S2 returns 0 tips → brave-search tipster sites → if still 0 → **ASK USER** before continuing. Without tipster data, coupons are worthless pure math.

**Output:** `tipster_picks` + `tipster_consensus` DB tables, `{date}_tipster_consensus.json`.

---

### S2.3–S2.9 — Data Enrichment & Scraping

| | |
|---|---|
| **Scripts** | `run_scrapers.py` + `data_enrichment_agent.py` |
| **Agent** | `bet-enricher` |
| **Purpose** | Multi-layer enrichment to populate team statistics |

**What happens — 7-layer fallback chain:**

| Layer | Source | Method |
|-------|--------|--------|
| L1 | Scan retry | Extended timeout, alternative endpoints |
| L2 | Parallel enrichment | odds-api + weather + tipsters concurrently |
| L3 | Batch enrichment | Flashscore (primary, 2s rate limit) → ESPN (fallback) |
| L3.5 | Google Sports H2H | SerpAPI Knowledge Panel (15 queries/run, 250/month) |
| L4 | Pre-analysis batch | Final batch before S3 starts |
| L5 | Inline per-candidate | `extract_team_stats` / `extract_h2h_stats` fallback |
| L6 | Context fetch | Weather API + ESPN injury scrape |
| L7a | Brave Search + LM Studio | Web research via local model (unlimited) |
| L7b | SerpAPI search | Fallback when primary fails |
| L7c | Playwright direct | Last resort for specific URLs |

**Quality threshold:** If >50% candidates have MINIMAL data quality (<4/10 score) after all layers → escalate to user.

**Output:** Populated `team_form` (L10/L5/H2H per stat key), `match_stats`, `league_profiles`, `standings` DB tables.

---

### S3 — Deep Statistical Analysis

| | |
|---|---|
| **Script** | `deep_stats_report.py` |
| **Agent** | `bet-statistician` |
| **Purpose** | The analytical heart of the pipeline |

**What happens per candidate (10-section structured output):**

1. **§3.0 Market Ranking** — List ALL bettable statistical markets for that sport. Per market: L10 avg, H2H avg, L5 avg, bookmaker line, hit rate. Calculate **safety score** = `min(hit_rate_L10, hit_rate_H2H)`. Rank by safety. Minimum ≥3 markets (≥4 for football).

2. **§3.0c H2H Market-Specific Validation** — Verify H2H data exists for the EXACT stat being bet. Betting corners? Need H2H corner data specifically, not generic match results.

3. **Three-Way Cross-Check** — L10 avg + H2H avg + L5 trend must ALL align:
   - 3/3 align → STRONG signal
   - 2/3 align → proceed with caution
   - 2/3 conflict → DOWNGRADE
   - 3/3 conflict → REJECT

4. **Probability Modeling:**
   ```
   λ = 40% × L5_avg + 35% × L10_avg + 25% × H2H_avg
   P(Over X.5) = 1 - CDF(X, λ)  [Poisson]
   If var/mean > 1.5 → Negative Binomial
   Fair odds = 1 / P(hit)
   EV = P(hit) × bookmaker_odds - 1
   Kelly ¼: f = (b×p - q) / b, stake = bankroll × f / 4
   ```

5. **Sport-Specific Multi-Market Tables (MANDATORY):**
   - Football §3.1M: Fouls O/U, Cards O/U, Corners O/U, Shots O/U, Team CK O/U, Goals O/U (min 4 rows)
   - Tennis §3.2M: Total games O/U, Sets O/U 2.5, Game HC, Tiebreaks O/U, Aces O/U
   - Basketball §3.3M: Team pts O/U, Total pts O/U, Q1 total O/U, 1H total O/U, Spread
   - Hockey §3.4M: Total Shots O/U, Hits O/U, Blocks O/U, PIM O/U, PP Goals O/U, Goals O/U
   - Volleyball §3.5M: Sets O/U, Total Points O/U, 5th set probability

**Market hierarchy (Football):** Fouls → Cards → Corners → Shots → Team totals → BTTS → U2.5 → O2.5 → DC/DNB → 1X2

**Circuit breaker:** If <20 analyses produced → wrong shortlist input file. Verify path and re-run.

**Output:** `analysis_results` + `analysis_raw_data` DB tables with full per-candidate structured data.

---

### S4 — Odds Evaluation & EV Calculation

| | |
|---|---|
| **Script** | `odds_evaluator.py` |
| **Agent** | `bet-valuator` |
| **Purpose** | Price validation and expected value assessment |

**What happens per candidate:**
1. Cross-validate pricing across bookmakers (BetExplorer, OddsPortal, The-Odds-API, ESPN)
2. Calculate Expected Value: `EV = (hit_rate × odds) - 1`. Only EV > 0 proceeds.
3. Detect odds drift >8% since initial fetch → mandatory re-evaluation or SKIP (Zero Tolerance #5)
4. Apply Kelly ¼ criterion for stake sizing
5. For stats-first mode (no API odds available): calculate minimum acceptable odds = `1 / hit_rate`
6. Assess CLV potential — will the line still be available at placement time?
7. Track line movement direction and velocity

**Output:** EV, odds, drift flags merged into `analysis_results.stats_summary_json`.

---

### S5 — Context & Motivation Analysis

| | |
|---|---|
| **Script** | `context_checks.py` |
| **Agent** | `bet-challenger` |
| **Purpose** | Real-world context that statistics alone cannot capture |

**Checks performed:**
- Weather impact on outdoor sports (wind affects corners, rain affects shots)
- Injury/suspension significance — star player absence vs. rotation squad member
- Tournament stage and motivation (dead rubber vs. relegation fight vs. cup final vs. title clincher)
- Venue effects (altitude, playing surface, crowd hostility)
- Referee tendencies (card-heavy refs inflate fouls/cards markets)
- Travel fatigue (back-to-back games, timezone changes, long flights)
- Compounding risk factors — multiple negative flags on same event multiply risk

**Output:** `context_flags` merged into `analysis_results.stats_summary_json`.

---

### S6 — Upset Risk Scoring

| | |
|---|---|
| **Script** | `upset_risk.py` |
| **Agent** | `bet-challenger` (continued) |
| **Purpose** | Quantify probability of unexpected outcomes |

**Sport-specific checklists with numerical thresholds:**

| Sport | Red Flags |
|-------|-----------|
| Football | Relegation match, manager sacked <7d, 3+ key injuries, cup rotation (CL/EL <5d), dead rubber |
| Tennis | WC/Q/LL status, previous round fatigue (3h+), new surface transition, ambiguous player names |
| Basketball | B2B 2nd night (−3-5 pts), star GTD/resting, tank mode, elimination game (OVER bias) |
| Hockey | Backup goalie (sv% −3-5%), B2B, 0-3 in series (4% comeback rate), goalie unconfirmed |
| Volleyball | Coach change, import player rotation, derby motivation |
| Esports | Stand-in player, patch day (<7d), LAN vs online format, bracket position |

**Paradox Rule:** Heavy favorites (>80% implied probability) in low-motivation spots = upset magnet.

**Output:** `upset_risk` scores merged into `analysis_results.stats_summary_json`.

---

### S7 — Gate Decision (18-Point Verification)

| | |
|---|---|
| **Script** | `gate_checker.py` |
| **Agent** | `bet-challenger` |
| **Purpose** | Binary PASS/FAIL gate with 18 verification points |

**The 18-Point Checklist:**

| # | Check | What It Verifies |
|---|-------|-----------------|
| 1 | Identity verified | Full team/player name correct, no confusion |
| 2 | WC/Q/LL/debut/stand-in | Special status checked and accounted for |
| 3 | H2H ≥5 meetings | Sufficient head-to-head history (surface/venue splits) |
| 4 | Injuries/suspensions | Checked against current reports |
| 5 | ≥2 independent sources | Data from multiple origins |
| 6 | ≥1 tipster argument | At least one reasoned tipster opinion read |
| 7 | Upset risk scored | Numerical upset probability assigned |
| 8 | EV > 0 | Positive expected value confirmed |
| 9 | Odds drift <8% | Price hasn't moved significantly against us |
| 10 | Red flags checked | Sport-specific instant red flags evaluated |
| 11 | Contrarian thinking | Actively looked for reasons pick is WRONG |
| 12 | Bear case < bull case | Arguments against are weaker than arguments for |
| 13 | Not anchored | Not fixated on initial impression, re-evaluated |
| 14 | 48h repeat check | Not repeating a recent pick (thesis might be stale) |
| 15 | ≥3 alternative markets | Market ranking table with ≥3 options calculated |
| 16 | H2H stat-specific | H2H data exists for exact market being bet |
| 17 | Three-way alignment | L10 + H2H + L5 directionally consistent |
| 18 | Data quality sufficient | Both teams have adequate statistical coverage |

**Tier classification:**
- ALL 18 PASS → APPROVED (bucket: `approved`)
- ≤2 fail → STRONG
- 3-5 fail → MODERATE
- 6-9 fail → WEAK
- 10+ fail → FLAGGED

**Three output buckets:**
- `approved` → core coupons (primary betting candidates)
- `extended_pool` → extended selection shown to user with bull/bear cases (EV>0 but gate-failed)
- `rejected` → shown in ODRZUCONE section with rejection reasons

**Circuit breaker:** If <5 approved → re-run without `--strict` flag.

**Output:** `gate_results` DB table with per-candidate gate_score, status, and detailed breakdown.

---

### S8 — Coupon Construction & Validation

| | |
|---|---|
| **Script** | `coupon_builder.py` |
| **Agent** | `bet-builder` |
| **Purpose** | Build the final betting portfolio |

**Portfolio structure:**

1. **PEŁNA MATRYCA RYNKÓW** — Top 30-50 candidates by safety score. Full visibility for user.

2. **Core Portfolio** — Unique event per coupon. Split by risk tier:
   - LOW-RISK (max 3.00 PLN stake) — highest safety picks
   - MULTI-SPORT — diversified across sports
   - HIGHER-RISK (max 2.00 PLN stake) — higher odds, lower safety
   - NIGHT — late-night events (separate time window)

3. **Combination Menu** — 4-8 extra COMBO coupons remixing approved picks (reuse allowed across combos).

4. **Extended Pool (ROZSZERZONY WYBÓR)** — ALL EV>0 picks that failed some gate checks, each with:
   - Event, market, odds, EV, gate score
   - Bull case (why it might win)
   - Bear case (why it might lose)
   - Missing data, when to bet, suggested combo partners

**Validation layers:**
- **Stress Test (§8.2):** Multiply probabilities for P(coupon). <10% → HR tier only. Weakest-leg swap analysis. Catastrophe scenario modeling.
- **V1-V10 Validation Suite:** 10 mechanical verification checks
- **§S8.FINAL Mechanical Verification:** Arithmetic correctness, placement order, cross-reference integrity
- **Correlation checks:** Same match FORBIDDEN. Same league ≥2 FLAG. Same narrative → REMOVE weaker.
- **Hard reject rules:** All rules from `betting-mistakes-rules.instructions.md` fire at coupon build time (not before — candidates still appear in matrix).

**Mandatory post-build validation (4 passes — NEVER SKIP):**

| Pass | What It Catches |
|------|----------------|
| Team Identity Check | Did I assign home team stats to away team? Player A confused with Player B? |
| Hallucination Check | Can every stat I cited be traced to an actual DB query or file? |
| Average vs Raw Value Check | L10_avg=87.7 does NOT mean "hits O87.5 every game" — count actual hits |
| Line vs Reality Check | Count `[val > line for val in l10_values]` → that's the REAL hit rate |

**Output:** `betting/coupons/YYYY-MM-DD.md` with 10 sections (matrix, per-type coupons, combo menu, extended pool, reasoning, summary, placement order, watch list, rejected picks).

---

## Architecture & Infrastructure

| Component | Technology |
|-----------|-----------|
| Language Model | Qwen3.6-35B-A3B MoE 4-bit (35B total params, 3B active per token) |
| Inference Server | Rapid-MLX serve (port 8000, ~19GB VRAM) |
| Hardware | Apple M4 Pro, 48GB unified memory |
| Context Window | 131K tokens |
| Reasoning | Always-on `<think>` blocks (qwen3 parser) + sequential thinking tool |
| Tool Calling | qwen3_coder_xml parser with auto tool choice |
| Database | SQLite WAL (`betting/data/betting.db`) — 28+ tables across 7 domains |
| Browser Automation | Playwright (headless Chromium for tipster scraping) |
| Web Search | Brave Search API (2000 queries/month) |
| Odds Data | The-Odds-API (500 credits/month), BetExplorer, OddsPortal |
| Sports Data | ESPN API, Flashscore, SofaScore, TennisAbstract, api-hockey, FBref |
| H2H Enrichment | Google Sports via SerpAPI (250 searches/month) |
| Agent Framework | GitHub Copilot Custom Agents (10 specialists) |
| Autocomplete | Codestral 22B via Continue.dev |
| Shell | Fish (no bash syntax allowed) |
| Timezone | Europe/Warsaw (betting day 06:00–05:59) |
| Bookmaker | Betclic (all picks conditional until user verifies in app) |

---

## Agent Roster (10 Specialists)

| Agent | Role | Key Responsibilities |
|-------|------|---------------------|
| `bet-orchestrator` | Pipeline sequencing & delegation | Runs scripts, delegates to specialists, manages state, enforces circuit breakers |
| `bet-scanner` | Event discovery & shortlist | Verifies 5-sport coverage, cross-validates fixtures, flags phantoms |
| `bet-scout` | Tipster consensus analyst | Reads full tipster arguments, assesses quality, finds consensus picks |
| `bet-enricher` | Data quality guardian | Monitors enrichment yield, triggers self-healing fallbacks |
| `bet-statistician` | Market ranking & safety scores | §3.0 protocol, three-way cross-check, probability modeling |
| `bet-valuator` | EV & odds specialist | Kelly sizing, drift detection, CLV tracking, price validation |
| `bet-challenger` | Devil's advocate & risk assessor | Bear cases, context analysis, upset risk, gate verdicts |
| `bet-builder` | Portfolio constructor | Coupon composition, correlation checks, stress tests, validation |
| `bet-settler` | PnL & performance analyst | Settlement, post-mortem, bankroll management, learning extraction |
| `bet-db-analyst` | Database specialist | Table census, gap analysis, integrity checks, source health |

---

## Source Fusion — The Core Value Proposition

The fundamental insight: **no single data source is sufficient.** The pipeline's value comes from fusing three independent information streams:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   TIPSTERS      │    │   STATISTICS     │    │   WEB SEARCH    │
│                 │    │                  │    │                 │
│ • Tactical      │    │ • L10/L5/H2H     │    │ • Live injuries │
│   reasoning     │    │   averages       │    │ • Lineup news   │
│ • Motivational  │    │ • Hit rates      │    │ • Standings     │
│   context       │    │ • Safety scores  │    │ • Motivation    │
│ • Insider info  │    │ • Poisson model  │    │ • Weather       │
└────────┬────────┘    └────────┬─────────┘    └────────┬────────┘
         │                      │                       │
         └──────────────────────┼───────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │    FUSED ANALYSIS     │
                    │                       │
                    │  WHY (tipster) +      │
                    │  DATA (stats) +       │
                    │  CONTEXT (web)        │
                    │  = STRONG COUPON      │
                    └───────────────────────┘
```

Example fused pick reasoning:
> "Tottenham fouls Over 12.5 @ 1.85 — Spurs L5 avg = 14.0 fouls/game (hit 5/5), H2H vs Arsenal = 15.3 avg (hit 4/5). Sportsgambler explicit tip with reasoning: 'NLD derbies are physical, both fighting for top 4.' Reuters confirms Walker questionable (impacts discipline). Safety = 0.80, EV = +0.48."

---

## Database Schema (28+ Tables, 7 Domains)

### Core Domain
- `sports` — Sport registry with tier and stat keys
- `teams` — Team profiles with aliases, country, style tags
- `competitions` — League/tournament metadata with importance ranking
- `fixtures` — All events with kickoff, status, scores
- `athletes` — 6,648 player profiles

### Statistics Domain
- `team_form` — **PRIMARY**: L10/L5/H2H values per team per stat key (the core analytical data)
- `match_stats` — Per-match raw statistics
- `league_profiles` — League baselines (avg, median, std_dev) for deviation analysis
- `player_season_stats` — Per-player season aggregates
- `player_gamelogs` — 25,943 game-by-game individual stats
- `standings` — 233 enriched league standings with form strings

### Analysis Domain
- `analysis_results` — S3 output: market rankings, safety scores, EV, context flags
- `analysis_raw_data` — Raw stat inputs for reproducibility
- `gate_results` — S7 output: approved/extended/rejected with per-point breakdown
- `decision_snapshots` — Pre-bet decision state for learning
- `decision_outcomes` — Post-settlement outcome analysis

### Betting Domain
- `coupons` — Coupon registry (core/combo/discovery types)
- `bets` — Individual picks within coupons
- `odds_history` — Odds movement tracking for CLV analysis

### Pipeline Domain
- `pipeline_runs` — Step execution tracking
- `scan_results` — Raw scan output per source
- `fixture_sources` — Cross-references from discovery module
- `scraper_runs` — Operational tracking for scrapers
- `source_health` — Source reliability metrics

### Tipster Domain
- `tipster_picks` — Individual picks with full reasoning text
- `tipster_consensus` — Aggregated consensus per event

### ESPN/External Domain
- `espn_predictions` — Power index and win probabilities
- `player_splits` — Home/away/conference splits
- `team_ats_records` / `team_ou_records` — Against-the-spread and over/under records
- `team_rosters` — Current roster depth charts

---

## Zero Tolerance Rules (From Real Losses)

Every hard rule traces to a specific settled loss with a post-mortem:

| ID | Rule | Origin |
|----|------|--------|
| ZT1 | Tennis: NEVER default to Match Winner. Statistical markets first. | Shelton ML loss |
| ZT2 | Low upset risk → UNDER bias (blowout = fewer stats generated) | Struff O22.5 loss |
| ZT3 | WC/Q/LL vs top 30 → O22.5+ games HARD REJECT | Jodar loss |
| ZT5 | >8% odds drift → MANDATORY re-eval or SKIP | Jodar drift ignored |
| ZT6 | Verify EVERY fixture against ≥2 non-tipster sources | 58% phantom fixture rate discovered |
| ZT8 | Skip ITF tournaments. ATP/WTA only. | ITF: all bets lost |
| ZT13 | ALWAYS run §3.0 market ranking for ALL available stats | Corner tunnel vision |
| ZT14 | H2H must be for EXACT stat being bet (not generic match H2H) | Wrong H2H used |
| ZT16 | §S3.3 ranking table ≥3 rows mandatory output | PSG cards: no table = no alternatives considered |
| ZT19 | 100% of shortlisted candidates get full S3 analysis | 16/33 silently dropped |
| ZT20 | §1.8 fixture verification ≥2 sources mandatory | Phantom fixtures bet |
| ZT24 | P(draw)≥25% + fouls UNDER + avg ±1.5 of line → SKIP | Close game fouls loss |

---

## Key Design Decisions

1. **No monolithic orchestrator script** — The LLM IS the orchestrator. Analytical reasoning happens BETWEEN every step, not just at the end. `pipeline_orchestrator.py` is explicitly BANNED.

2. **Statistical markets over outcome markets** — Corners, fouls, cards, shots, games, sets accumulate throughout matches. They are lower variance, style-driven, shock-resistant, and mispriced by bookmakers who focus liquidity on ML/goals.

3. **Source fusion as core value** — Tipster opinions + deep statistics + web search combined produce insights no single source can. Skipping S2 (tipsters) = FAILED SESSION.

4. **DB-first architecture** — SQLite is the single source of truth. JSON/Markdown are secondary human-readable artifacts. All reads via repository pattern + `get_db()`.

5. **Never auto-reject based on historical performance** — Hit rates are shown to the user as advisory. The user decides. Only invalid fixtures, wrong dates, and negative-EV positions may be auto-removed.

6. **Versioned reruns** — Pipeline reruns create new versions (v1→v2→v3). History is never overwritten. Old pending artifacts marked `superseded`.

7. **Zero-tolerance rules from real losses** — Every hard reject rule traces to a specific settled loss with a post-mortem. Rules fire at coupon build time (S8), not earlier — candidates still appear in the analysis matrix.

8. **Conditional picks** — ALL picks are conditional until the user manually verifies the market and odds exist in the Betclic app. The system never scrapes Betclic.

---

## Output Artifacts

| Path | Content |
|------|---------|
| `betting/coupons/YYYY-MM-DD.md` | Full daily coupon file with matrix, coupons, combos, extended pool |
| `betting/reports/` | Detailed daily analysis reports |
| `betting/journal/picks-ledger.csv` | Registry of all individual picks and their outcomes |
| `betting/journal/coupons-ledger.csv` | Registry of all coupons and their outcomes |
| `betting/data/betting.db` | Primary data store (SQLite) |
| `betting/data/{date}_*.json` | Per-step JSON artifacts for human readability |

---

## Directory Structure

```
betting/
    coupons/          # Daily coupon files (final output)
    data/             # betting.db + JSON artifacts + stats cache
    journal/          # Ledgers (picks, coupons) + learning log
    plans/            # Betting day plans
    reports/          # Detailed analysis reports
    sources/          # Source documentation
config/               # betting_config.json, API keys, scan URLs
scripts/              # Active pipeline scripts (S0-S8) + utilities
src/bet/              # Core Python package
    db/               # Database schema, connection, models, repositories
    discovery/        # Event discovery + deduplication engine
    scrapers/         # 19 sport-specific scrapers
    stats/            # Normalization, safety scores, market ranking
    pipeline/         # State management
    utils/            # Name matching, shared utilities
    resilience/       # Atomic writes, error handling
tests/                # Test suite
specifications/       # Integration specs, process documentation
```

---

## Running the Pipeline

The system does **NOT** run via a blind script. It operates interactively as an agent-driven process:

1. Activate the `bet-orchestrator` agent mode
2. Request a full pipeline run for the target date
3. The orchestrator runs scripts one-by-one, delegates analysis to specialists, and presents findings
4. User reviews coupons, verifies odds in Betclic app, and places bets manually

```
"Run full pipeline for 2026-05-31, session=full, version=v1"
```

The orchestrator enforces: script → think → delegate → present → advance. Skipping delegation = FAILED SESSION.

---

## Core Constraints

- **Timezone:** Europe/Warsaw. Betting day runs 06:00–05:59 local time.
- **Always settle** the previous betting day before generating new picks.
- **Never invent** odds, lineups, injuries, results, or statistical values.
- **Statistical before outcome:** Always evaluate stat markets first.
- **Max coupon legs:** 4 (AKO 5+ has near-zero historical win rate).
- **Unique events per core coupon** — no same event in multiple legs.
- **Max same-sport:** 2 picks per coupon.
- **Stake limits:** LR max 3.00 PLN, HR max 2.00 PLN.
- **Safety floor:** <0.15 = INSTANT REJECT. <0.30 = extended pool only.

