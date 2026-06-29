# High-Risk Probability Code Review

## Remediation Status

- Review completed against the requested path: `db_data_loader -> deep_stats_report -> probability_engine -> market_probability_inputs -> analytical_candidate_bridge -> package/manual review gates`.
- Verified findings discovered during review: `P0=1`, `P1=3`, `P2=0`.
- Remediations applied and regression-tested:
  - unsafe surname-based fallback removed in favor of exact normalized fallback only, with recorded identity source/confidence metadata;
  - split home/away averages now use explicit mean-based aggregation policy, and unknown split semantics fail closed;
  - hit-rate parser now accepts `5/10`, `0.5`, `50%`, `5 of 10` and preserves explicit fail-closed reasons;
  - low-confidence model probability is blocked from analytical promotion and no longer propagates as ready guidance.
- Post-fix verification:
  - focused regression tests passed;
  - required regression suite passed;
  - full pytest passed;
  - analytical smoke produced a fail-closed `RESEARCH_GAP_PACKAGE`, not a false-ready analytical package.

## Final Verdicts

- `IDENTITY_FALLBACK_VERDICT=PASS`
- `STAT_AGGREGATION_SEMANTICS_VERDICT=PASS`
- `PROBABILITY_PARSER_VERDICT=PASS`
- `PROBABILITY_INPUT_VERDICT=PASS`
- `PROMOTION_GUARD_VERDICT=PASS`

## Phase 1 Review Findings

### 1. Team Identity Fallback
*   **Can `LIKE "%surname%"` map the wrong team?**
    Yes, absolutely. In `scripts/db_data_loader.py`, when a team's primary form is sparse (<= 3 rows), it splits the team name by spaces/commas, takes the longest token (`surname = max(parts, key=len)`), and queries `teams` with `name LIKE "%{surname}%"`. For example, "Real Madrid" is split into "Real" and "Madrid". The longest token is "Madrid". A `LIKE "%Madrid%"` query will match "Atletico Madrid" or any other team with "Madrid" in its name. If Atletico Madrid has form data, it will be mapped onto Real Madrid!
*   **Does fallback use competition/country context?**
    No, it only filters by `sport_id`. It does not verify the competition or country context, making it extremely prone to cross-country or cross-league false positives (e.g., matching "Liverpool" in England with "Liverpool" in Uruguay).
*   **Does it record confidence and source?**
    No, it overlays the stats directly without marking the match confidence as `LOW` or tracking that a fallback name was used.
*   **Can a low-confidence match produce model probability?**
    Yes, the fallback-overlaid stats are propagated silently, and the probability engine computes Poisson probabilities using these incorrect stats, resulting in high-risk, completely invalid betting models.
*   **Classification:** `P1_FIX_BEFORE_MERGE` (Needs false-positive guards, confidence tracking, and a ban on low-confidence fallback matches producing model probability).

### 2. Split Stat Semantics
*   **Are `_home/_away` values counts, averages, or already normalized rates?**
    They are already averages (rates) representing the team's performance specifically in home games or specifically in away games (e.g., `goals_home` is the average goals scored per home match, and `goals_away` is the average goals scored per away match).
*   **Is summing them correct per stat key?**
    No! This is a severe mathematical bug. In `scripts/deep_stats_report.py`, it computes overall L10 counting stats by summing `home_val` and `away_val`. If a team averages 1.5 goals at home and 1.2 goals away, summing them yields 2.7 goals/match. This is exactly double the correct overall average (~1.35 goals/match). As a result, Poisson lambda parameters are doubled, completely breaking all subsequent probability calculations.
*   **Are percentage stats handled safely?**
    No. For percentage stats, it currently keeps `home_val` only, ignoring `away_val` entirely. This is highly inaccurate and ignores how the team performs when playing away.
*   **What happens for unknown stat semantics?**
    They are treated as counting stats and incorrectly summed, leading to doubled average rates.
*   **Classification:** `P0_BLOCKER` (This severe mathematical bug breaks all Poisson models by doubling the input rates).

### 3. Probability Parser
*   **Does it support hit-rate formats?**
    *   `5/10`: Yes, splits by `/`.
    *   `0.5`: Yes, parses as float directly.
    *   `50%`: No, fails with ValueError and returns None.
    *   `5 of 10`: No, returns None.
    *   Malformed values: Returns None (fails closed).
*   **Does malformed parsing fail closed with reason, not silent null?**
    It fails closed by returning `None`, but does not preserve or propagate a reason, making debugging difficult.
*   **Classification:** `P1_FIX_BEFORE_MERGE` (Harden the parser to support percentage strings and word fractions, and log precise parsing failure reasons).

### 4. Probability Input
*   **Are line and direction required for O/U style markets?**
    Yes, they are validated in `validate_market_probability_input` inside `src/bet/pipeline/market_probability_inputs.py`.
*   **Are L10 numeric series required for both teams?**
    Yes, they are required for all totals-style and RESULT markets.
*   **Is sample size enforced?**
    Yes, a minimum of 5 historical matches in L10 is enforced.
*   **Is bookmaker implied probability forbidden as model input?**
    Yes, it is explicitly blocked from being used as model probability in the bridge when `probability_method` is `"BOOKMAKER_IMPLIED_REFERENCE_ONLY"`.
*   **Classification:** `NO_ISSUE` (The input schema and validation contracts are well-defined).

### 5. Promotion
*   **Can LOW confidence become analytical-ready?**
    Yes, under the current bridge code, any candidate with a valid model probability can become `ANALYTICAL_READY` even if its `probability_confidence` is `"LOW"`. Only `"BLOCKED"` confidence is prevented from promoting.
*   **Does package clearly label confidence?**
    Yes, it labels the confidence in `CandidateDraft` and `UnpricedBetBuilderAnalyticalCandidate`, but it does not block the promotion of LOW confidence candidates.
*   **Does any candidate become `BETTABLE_MANUAL_ONLY` without quote/evidence/correlation?**
    No, a candidate can only reach `BETTABLE_MANUAL_ONLY` state through a `ManualQuoteDecision`, which requires an explicit operator quote, line check, and evidence review.
*   **Classification:** `P1_FIX_BEFORE_MERGE` (Block LOW confidence or fallback-derived probability candidates from becoming `ANALYTICAL_READY`).

---

## Findings Summary

| ID | Location | Vulnerability / Issue | Severity | Verdict |
|---|---|---|---|---|
| F1 | `scripts/db_data_loader.py` | Identity fallback splits team names blindly, leading to wrong-team mapping and incorrect model inputs. Lacks context/confidence checks. | P1 | FIX_REQUIRED |
| F2 | `scripts/deep_stats_report.py` | Sums home and away averages for counting stats, which doubles the true overall averages and corrupts all Poisson calculations. | P0 | BLOCKER_FIX_REQUIRED |
| F3 | `scripts/probability_engine.py` | Hit-rate parser fails to handle common formats like `"50%"` and `"5 of 10"`, resulting in silent null gaps. | P1 | FIX_REQUIRED |
| F4 | `src/bet/pipeline/analytical_candidate_bridge.py` | Allows candidates with `"LOW"` confidence to promote to `ANALYTICAL_READY`. | P1 | FIX_REQUIRED |
