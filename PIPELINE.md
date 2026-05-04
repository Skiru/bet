# Betting Pipeline — Automated Coupon Generation

Fully automated pipeline that scans 14 sports, analyzes hundreds of events with deep statistics, and produces ready-to-bet coupons.

## Quick Start

```bash
# Full run (today's date)
python3 scripts/pipeline_orchestrator.py

# Specific date
python3 scripts/pipeline_orchestrator.py --date 2026-05-01

# Resume after failure
python3 scripts/pipeline_orchestrator.py --date 2026-05-01 --resume

# Skip scan (re-run analysis on existing data)
python3 scripts/pipeline_orchestrator.py --date 2026-05-01 --skip-scan

# Check status
python3 scripts/pipeline_orchestrator.py --status

# List all steps
python3 scripts/pipeline_orchestrator.py --list-steps
```

## Pipeline Steps

| Step | Name | Type | Duration | Description |
|------|------|------|----------|-------------|
| S0 | Settle + History | Shell | ~1 min | Betclic history analysis (§0.2 MANDATORY) |
| S1 | Complete Scan | Shell | 5-10 min | 14-sport Playwright scan + API fixtures (PARALLEL: 6 domain workers) |
| S1b | Odds+Weather+Tipsters | Python | ~5 min | **PARALLEL**: odds API + weather + tipster aggregation (3 threads) |
| S1d | Market Matrix | Shell | ~2 min | Consolidated market matrix from all sources |
| S1e | Shortlist | Shell | ~1 min | Ranked shortlist of top 100 events |
| S3 | Deep Stats + Probability | Python | ~1 min | Per-candidate L10/H2H/L5 analysis + Poisson probability engine (PARALLEL: 8 workers) |
| S7 | Gate Check | Python | ~1 min | 17-point approval gate, risk classification |
| S8 | Coupons | Python | ~1 min | Core portfolio + combo menu + extended pool |
| S9 | Validation | Python | ~1 min | Coupon arithmetic and structure validation |
| S10 | Summary | Python | instant | Final summary and artifact listing |

**Total estimated runtime: 12-20 minutes** (3-4x faster with parallel scanning and analysis)

## Output Files

After a successful run, find your coupons at:

| File | Description |
|------|-------------|
| `betting/coupons/YYYY-MM-DD.md` | **Main coupon file** (Polish, ready to bet) |
| `betting/coupons/YYYY-MM-DD.json` | Structured coupon data |
| `betting/data/{date}_s3_deep_stats.md` | Deep analysis per candidate |
| `betting/data/{date}_s7_gate_results.md` | Gate check results |
| `betting/data/market_matrix_{date}.md` | Full market matrix |
| `betting/data/{date}_s2_shortlist.md` | Ranked shortlist |

## Pipeline Architecture

```
                     S0: Betclic History
                            │
                     S1: Full 14-Sport Scan (PARALLEL: 6 domain workers)
              ┌──────┬──────┼──────┬──────┬──────┐
           Flash  Sofa   Bet    Odds   Bet   Other
           score  score  clic   portal Expl  domains
              └──────┴──────┼──────┴──────┴──────┘
                            │
                  S1b: PARALLEL ENRICHMENT
                  ┌─────────┼─────────┐
              S1b-Odds  S1b-Weather S1b-Tipsters
                  └─────────┼─────────┘
                     S1d: Market Matrix
                            │
                     S1e: Shortlist (100 events)
                            │
                     S3: Deep Stats + Probability Engine (PARALLEL: 8 workers)
                     (L10/H2H/L5 + Poisson/NegBin → P(hit))
                            │
                     S7: 17-Point Gate Check
                     (approved/extended/rejected)
                            │
                     S8: Coupon Builder
                     (core + combos + extended)
                            │
                     S9: Validation (V1-V10)
                            │
                     S10: Summary + Artifacts
```

## How Deep Analysis Works

For **every** candidate event, the pipeline:

1. **Reads stats cache** — L10 match-by-match stats (corners, fouls, shots, cards, goals for football; games, aces, sets for tennis; points, rebounds for basketball; etc.)
2. **Computes per-market safety scores** — For ALL available statistical markets, calculates hit rates and ranks by `safety = min(hit_rate_L10, hit_rate_H2H)`
3. **Runs probability engine** — Poisson distribution model converts raw stats → true probability → fair odds:
   - λ = 40% × L5_avg + 35% × L10_avg + 25% × H2H_avg (recency-weighted)
   - P(Over X.5) = 1 - CDF(X, λ) using Poisson (or negative binomial for overdispersed data)
   - Fair odds = 1 / P(hit), True EV = P(hit) × bookmaker_odds - 1
   - 90% confidence interval via 1000-sample bootstrap
4. **Runs three-way cross-check** — L10 avg + H2H avg + L5 trend must ALL support pick direction
5. **Selects best market** — Highest safety score, NOT default (corners can lose to fouls)
6. **Integrates tipster consensus** — Checks tipster agreement and cited stats for the event
7. **Generates 10-section report** — §S3.1 H2H, §S3.2 Form, §S3.3 Ranking (with probability), §S3.4 Three-Way, §S3.5 Coach, §S3.6 Injuries, §S3.7 Top 3, §S3.8 Recommended, §S3.9 Sources, §S3.10 Depth

### Example output for a football match:
```
Liverpool L10: corners 9.5/game, fouls 14.5, shots 16.5, cards 2.0
Arsenal L10:   corners 5.0/game, fouls 13.5, shots 14.5, cards 2.5
H2H (5 meetings): corners avg 12.0, fouls avg 24.0

Market Ranking:
1. Fouls Total O22.5  — Safety 0.80, P(hit)=73.2%, fair=1.37, λ=24.8
2. Corners Total O9.5 — Safety 0.80, P(hit)=87.6%, fair=1.14, λ=13.7
3. Cards Total O3.5   — Safety 0.60, P(hit)=65.1%, fair=1.54, λ=4.2
4. Shots Total O22.5  — Safety 0.56, P(hit)=81.4%, fair=1.23, λ=27.5
→ Recommended: Fouls Total O22.5 (highest safety)
→ Best probability: Corners O9.5 (87.6% → Betclic ≥1.14 for EV>0)
```

## Gate Check (17 Points)

Each candidate is checked against 17 criteria:

1. Identity verified (no slashes)
2. WC/Q/LL status checked
3. H2H ≥5 meetings
4. Injuries/suspensions checked
5. ≥2 independent sources
6. ≥1 tipster argument
7. Upset risk scored
8. EV > 0
9. Odds drift <8%
10. Red flags checked
11. Contrarian thinking
12. Bear case < bull case
13. Not anchored
14. 48h repeat check
15. ≥3 alternative markets
16. H2H for specific stat
17. Three-way alignment

**Classification:**
- **APPROVED** → Core coupons (passed most checks, EV > 0)
- **EXTENDED** → Extended pool (EV > 0 but failed some checks)
- **REJECTED** → Only for HARD REJECT (48h repeat, critical red flags)

## Coupon Structure

- **Core Portfolio** — Unique event per coupon, min 2 legs, risk-tier labeled (LR/MS/HR/N)
- **Combo Menu** — 4-8 extra combos remixing approved picks with themed strategies
- **Extended Pool** — EV>0 picks that failed some gates, shown with bull/bear cases
- **Stakes** — Kelly 1/4 criterion, capped at 3.00 PLN (LR) / 2.00 PLN (HR)

## CLI Options

```
--date YYYY-MM-DD    Betting date (default: today)
--session TYPE       Session type: full|day|night|morning
--resume             Resume from last completed step
--skip-scan          Skip S0-S1e, start at S3 (reuse existing scan data)
--step STEP_ID       Run a single step
--top N              Limit S3 analysis to top N candidates
--version VERSION    Pipeline version label
--status             Show current status
--list-steps         List all steps
```

## State & Resume

Pipeline state is saved to `betting/data/pipeline_state/pipeline_YYYY-MM-DD.json` after each step. If the pipeline fails, use `--resume` to continue from the last completed step.

## Tests

```bash
python3 -m pytest tests/test_pipeline_modules.py -v   # Pipeline module tests (35)
python3 -m pytest tests/ -v                             # Full suite (256)
```

## Key Scripts

| Script | Purpose |
|--------|---------|
| `pipeline_orchestrator.py` | Main orchestrator — runs everything |
| `deep_stats_report.py` | S3: Per-candidate deep statistical analysis |
| `gate_checker.py` | S7: 17-point pick approval gate |
| `coupon_builder.py` | S8: Coupon construction + Polish output |
| `run_full_scan_and_prepare.sh` | S1: Full Playwright scan (called by orchestrator) |
| `compute_safety_scores.py` | §3.0 safety score calculator |
| `normalize_stats.py` | Stats normalizer + market definitions |
| `build_shortlist.py` | S1e: Ranked shortlist builder |
| `validate_coupons.py` | S9: Coupon validation |
| `analyze_betclic_learning.py` | S0: Betclic history analysis |
