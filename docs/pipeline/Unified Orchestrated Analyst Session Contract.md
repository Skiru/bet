# Unified Orchestrated Analyst Session Contract

This contract establishes the formal specification, agent responsibilities, execution phases, required artifacts, quality gates, and schema requirements for the production-grade, orchestrator-led betting session.

## 1. Executive Summary & Flow Philosophy
The session follows a single unified live analyst flow led entirely by the `bet-orchestrator`. Subagents are invoked sequentially to perform isolated analysis, and the orchestrator never performs specialist analysis itself.
Odds, HYDRATED statuses, and model probabilities are treated as **optional** reference points. Missing elements do not block recommendations; they lower confidence levels, place items on a watchlist, or affect EV calculations.

---

## 2. Required Subagents & Roles
- **bet-orchestrator (Primary/Leader):** Sequentially plans and invokes required subagents, creates the subagent manifest and omission ledger, enforces hard stop gates, and prevents any silent omissions.
- **bet-scanner:** Fixture and event universe discovery covering football, tennis, basketball, volleyball, hockey (if available), CS2, Dota2, and Valorant. Drops unsupported sports/events with explicit reasons.
- **bet-scout:** Tipster and opinion aggregation layer. Classifies source types, affiliate bias, documents consensus/disagreements, and scores argument quality. Tipster is never the primary truth.
- **bet-enricher:** Context enrichment layer. Collects and logs key match factors: injuries, lineups, referee, weather, venue, travel, surface, and round. Unfilled gaps are marked as `UNKNOWN`.
- **bet-statistician:** Statistical market analysis. Computes corners, cards, goals, shots, and shots on target (SOT) for football; tennis games, handicap, tiebreaks, and aces (only if evidence exists).
- **bet-valuator:** Valuation-reference layer. Standardizes reference odds. The absence of odds lowers EV confidence but never blocks analyst recommendations. Implies no bookmaker odds as model probabilities.
- **bet-challenger:** Adversarial challenger. Audits all top/secondary recommendations, rejects generic placeholders, challenges tipster bias, and evaluates the KEEP_TOP gate.
- **bet-builder:** Package constructor. Aggregates findings into the structured analyst package.
- **bet-test-engineer:** Independent test and quality gate validator. Performs PASS/FAIL verification across all logs, routing, and quality rules.

---

## 3. Required Session Artifacts

The session is only complete and verified when all of the following artifacts exist and conform to their schemas:

1. `orchestrator_session_plan.md`
2. `orchestrator_subagent_manifest.json`
3. `model_routing_matrix.json`
4. `active_model_runtime_proof.md`
5. `scanner_event_universe.md` / `scanner_event_universe.json`
6. `scout_tipster_opinion_layer.md` / `scout_tipster_opinion_layer.json`
7. `enricher_context_layer.md` / `enricher_context_layer.json`
8. `statistician_market_analysis.md` / `statistician_market_analysis.json`
9. `valuator_reference_odds_layer.md` / `valuator_reference_odds_layer.json`
10. `challenger_adversarial_review.md` / `challenger_adversarial_review.json`
11. `builder_package.md` / `builder_package.json`
12. `omission_ledger.md` / `omission_ledger.json`
13. `package_quality_review.md`
14. `status_safety_review.md`

---

## 4. Omission Ledger and No-Silent-Omission Gate
To satisfy the no-silent-omission contract, any sport, league, event, or data gap that is discovered but not recommended must be accounted for in the `omission_ledger.json` with a valid category:
- `OMITTED`: Sport/competition explicitly excluded with a valid reason.
- `WATCHLIST`: Put on watchlist due to missing data (e.g., missing HYDRATED status or lineups).
- `REJECTED`: Discovered but rejected by a subagent or the adversarial challenger.

---

## 5. Model Routing Specifications
Every active required agent must route to the high-reasoning Gemini 3.5 Flash Flex model.
- **Provider:** `google-vertex`
- **Model:** `gemini-3.5-flash`
- **Alias:** `gemini-3.5-flash-flex-high`
- **Tier:** `flex`
- **Thinking Level:** `HIGH`

No routing to local Qwen, GPT, or Anthropic models is permitted for the active betting analyst session.

---

## 6. Quality Gates and Final Safety Policies
1. **Zero Valid Tips Gate:** If Phase C (`bet-scout`) identifies 0 valid tips, a hard stop is triggered (`NO_DATA`).
2. **Adversarial Gate:** `bet-challenger` must issue a `KEEP_TOP` verdict for any top recommendation to remain in the final list.
3. **Validation Gate:** `bet-test-engineer` must run independent tests and format checks and issue a `PASS`.
4. **Human Superbet Quote Safety:** No final coupon or combined Bet Builder odds may be computed or combined automatically. Final manual coupons strictly require a real, human-entered Superbet operator quote.
5. **No Automated Placement:** Auto-betting, scraping of Betclic/Superbet APIs, and browser automation are strictly forbidden.
