---
applyTo: "betting/**/*"
---

# Analysis Methodology — Compact Protocol

## ULTIMATE RULE: BET STATISTICS, NOT OUTCOMES

Statistical markets (corners, fouls, cards, shots, games, sets, points, frames) beat outcome markets because they:
- **Accumulate** throughout the match (lower variance)
- Are **style-driven** (structural, persistent even in upsets)
- Are **shock-resistant** (red card barely affects total corners)
- Are **mispriced** (bookmakers focus liquidity on ML/goals)

EV > 0 is the only valid reason to bet. Every pick MUST be a statistical market unless none exists for that event.

---

## DATA ARCHITECTURE

Primary: SQLite `betting/data/betting.db`. JSON = human-readable fallback.
Gateway: `scripts/db_data_loader.py` (all DB read/write functions).

| Table | Purpose |
|-------|---------|
| `fixtures` | All events for betting day |
| `odds_history` | Odds from all sources |
| `team_form` | L10/L5/H2H per team (primary stats) |
| `match_stats` | Per-match raw statistics |
| `analysis_results` | S3 output: market rankings, safety scores |
| `gate_results` | S7 output: approved/extended/rejected |
| `coupons` + `bets` | Placed bets and coupon history |
| `athletes` (6,648) | Player profiles |
| `player_gamelogs` (25,943) | Game-by-game individual stats |
| `standings` (233) | Enriched league standings |
| `team_ats_records` / `team_ou_records` | ATS and O/U betting history |

**state.json** = pipeline position + decisions + flags (see `src/bet/pipeline/state.py`).

---

## PIPELINE STEPS

| Step | Script | Model Role |
|------|--------|-----------|
| S0 | `settle_on_finish.py` | MONITOR: check PnL, record learnings |
| S1 | `discover_events.py` + `ingest_scan_stats.py` | MONITOR: verify coverage ≥50 events, 5 sports |
| S1e | `build_shortlist.py --stats-first --all-fixtures` | MONITOR: verify sport diversity, no phantoms |
| S2 | `tipster_aggregator.py` + `tipster_xref.py` | MONITOR: verify consensus, promote statistical picks |
| S2.3-S2.9 | `run_scrapers.py` + `data_enrichment_agent.py` | MONITOR: verify data quality tiers |
| S3 | `deep_stats_report.py` | **REASON**: fuse sources, market ranking, bear cases |
| S4 | `odds_evaluator.py` | **REASON**: EV analysis, drift detection |
| S5-S6 | `context_checks.py` + `upset_risk.py` | **REASON**: injury impact, upset scenarios |
| S7 | `gate_checker.py` | **REASON**: gate verdict, approved list |
| S8 | `coupon_builder.py` | **REASON**: narrative per pick, coupon composition |

Phase boundary: S0-S2.9 = DATA (scripts compute, model monitors). S3-S10 = ANALYSIS_BUILD (model reasons).

---

## CORE CONSTRAINTS

1. **Scripts compute, model reasons.** Model NEVER calculates averages, hit rates, or EV.
2. **DB-first.** All reads via `db_data_loader.py`. JSON = fallback.
3. **Statistical > outcome.** Always. Football: Fouls→Cards→Corners→Shots→...→1X2.
4. **Never invent.** No fabricated odds, lineups, injuries, results, or stats.
5. **Hit rate > average.** L10_avg crossing the line ≠ reliable. Count games that ACTUALLY exceed.
6. **H2H is market-specific.** Betting corners? Need H2H corner data, not just match results.
7. **Three-way cross-check.** L10 + H2H + L5 must align. 2/3 conflict → DOWNGRADE. 3/3 → REJECT.

---

## HALLUCINATION PREVENTION

When `hallucination_risk=HIGH` in S3 report for ANY sport:
- ONLY analyze markets backed by real L10 data (listed in `real_data_keys`)
- NEVER cite a stat value not explicitly in the S3 structured data
- Markets with empty keys = SKIP with reason "insufficient enrichment"

| Sport | Allowed if HIGH risk | Forbidden |
|-------|---------------------|-----------|
| Tennis | Total Games O/U, Total Sets O/U, Player Games O/U | Aces, DF, 1st serve% |
| Volleyball | Total Points O/U, Sets O/U | Aces, blocks, hitting% |
| Hockey | Total Goals O/U, Total Shots O/U | PIM, hits, blocks |
| Basketball | Total Points O/U, Handicap | Rebounds, assists, steals |
| Esports | Match Winner only (if only win_rate_l10) | Round/map numbers |

---

## SCANNING MANDATE

- **WIDE:** ALL 5 sports, ALL leagues (not just top). ≥50 events, ≥3 sports in shortlist.
- **DEEP:** Enter every tournament sub-page. 2nd/3rd divisions, cups, women's leagues.
- **RETRY:** Source fails → next in chain → Google → retry after 15 min. NEVER declare empty.
- **VERIFY:** §1.8 Fixture verification against ≥2 non-tipster sources before shortlisting.
- **PROTECT:** Major tournaments + protected domestic leagues NEVER filtered out.
- **NO AUTO-REJECTION:** ALL fixtures shown in market matrix. User decides.

---

## §3.0 MARKET RANKING (MANDATORY per candidate)

1. List ALL bettable statistical markets for that sport
2. Per market: L10 avg, H2H avg, L5 avg, bookmaker line, hit rate
3. **Safety score** = `min(hit_rate_L10, hit_rate_H2H)`. Higher = safer.
4. Rank by safety. Pick TOP market, not your default/favorite.
5. Present ranking table in output. Show WHY chosen market beat alternatives.

**Minimum:** ≥3 markets ranked (≥4 for football). Football MUST include fouls, cards, corners, shots.

---

## §3.0e OUTPUT TEMPLATE (10 sections per candidate)

1. §S3.1 H2H Analysis (market-specific, ≥3 meetings)
2. §S3.2 Form & Stats Table (sport-specific, home/away split)
3. §S3.3 Market Ranking (≥3 rows, safety 0.00-1.00)
4. §S3.4 Three-Way Cross-Check (L10, H2H, L5 + alignment verdict)
5. §S3.5 Coach/Roster Stability
6. §S3.6 Injury/Suspension Check (source + timestamp)
7. §S3.7 Top 3 Markets
8. §S3.8 Recommended Market (with reasoning)
9. §S3.9 Sources Used (≥2 rows)
10. §S3.10 Depth Proof (5 metrics with numbers)

**BANNED sole-cell content:** "checked", "verified", "confirmed", "good", "OK", "—", "N/A"

---

## PROBABILITY ENGINE (Poisson/NegBin)

λ = 40% × L5_avg + 35% × L10_avg + 25% × H2H_avg (H2H missing: 55/45 split)
- P(Over X.5) = 1 - CDF(X, λ)
- Overdispersed (var/mean > 1.5) → negative binomial
- Fair odds = 1 / P(hit). EV = P(hit) × bookmaker_odds - 1
- Kelly 1/4: f = (b×p - q) / b, stake = bankroll × f / 4

---

## GATE (§7.5 — 18 points)

| # | Check |
|---|-------|
| 1 | Identity verified (full name) |
| 2 | WC/Q/LL/debut/stand-in checked |
| 3 | H2H ≥5 meetings (surface/venue splits) |
| 4 | Injuries/suspensions checked |
| 5 | ≥2 independent sources |
| 6 | ≥1 tipster argument read |
| 7 | Upset risk scored |
| 8 | EV > 0 |
| 9 | Odds drift <8% |
| 10 | Red flags checked |
| 11 | Contrarian thinking done |
| 12 | Bear case < bull case |
| 13 | Not anchored |
| 14 | 48h repeat check |
| 15 | ≥3 alternative markets calculated (§3.0) |
| 16 | H2H stat-specific data exists (§3.0c) |
| 17 | Three-way alignment (L10+H2H+L5) |
| 18 | Data quality sufficient (both teams) |

ALL 18 PASS → APPROVED. Tiers: STRONG (≤2 fail), MODERATE (3-5), WEAK (6-9), FLAGGED (10+). Advisory only.

---

## COUPONS (§8)

- **Core portfolio:** unique event per coupon. Min 2 legs. Scale: 4-5 picks→2, 6-7→3, 10+→5+.
- **Combo menu:** 4-8 extra combos remixing approved picks. Reuse allowed.
- **Risk tiers:** LOW-RISK, MULTI-SPORT, HIGHER-RISK, NIGHT.
- **Stress test:** P(coupon) multiply probabilities. <10%→HR only. Weakest-leg swap. Catastrophe scenario.
- **Limits:** LR max 3.00 PLN, HR max 2.00 PLN. Max same-sport: 2/coupon.
- **Correlation:** Same match FORBIDDEN. Same league ≥2 FLAG. Same narrative REMOVE weaker.

---

## ZERO TOLERANCE (proven failures — hard rules)

| # | Rule | Origin |
|---|------|--------|
| ZT1 | Tennis: NEVER default to ML. Statistical markets first. | Shelton ML loss |
| ZT2 | Low upset risk → UNDER bias (blowout = fewer stats). | Struff O22.5 loss |
| ZT3 | WC/Q/LL → O22.5+ HARD REJECT. | Jodar loss |
| ZT5 | >8% odds drift → MANDATORY re-eval or SKIP. | Jodar drift |
| ZT6 | Verify EVERY fixture against ≥2 non-tipster sources. | 58% phantom rate |
| ZT8 | Skip ITF. ATP/WTA only. | ITF all lost |
| ZT13 | ALWAYS run §3.0 ranking for ALL available stats. | Corner tunnel vision |
| ZT14 | H2H must be for EXACT stat being bet. | Match H2H ≠ stat H2H |
| ZT16 | §S3.3 ranking table ≥3 rows mandatory. | PSG cards no table |
| ZT19 | 100% of shortlisted candidates get full S3 analysis. | 16/33 silently dropped |
| ZT20 | §1.8 fixture verification ≥2 sources. | Phantom fixtures |
| ZT24 | Close game (P(draw)≥25%) + fouls UNDER near line → SKIP. | Post-mortem 2026-05-22 |
