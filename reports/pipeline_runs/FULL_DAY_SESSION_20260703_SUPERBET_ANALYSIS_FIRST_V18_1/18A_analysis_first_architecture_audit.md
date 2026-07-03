# 18A Analysis-First Architecture Audit

## Where Odds Incorrectly Gate Useful Analysis
- `reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_PRODUCTION_V17_1/07_analytical_candidates.json`: Promoted candidates were still framed as manual-quote search paths with `final_status=READY_FOR_MANUAL_OPERATOR_QUOTE_REVIEW`, so useful event analysis was not presented as the primary product.
- `src/bet/pipeline/manual_quote_price_gate.py`: Missing manual operator odds returns `PRICE_GATE_FAIL`, which is correct for bettable promotion but too strong if reused as an analysis gate.

## Where Manual Quote Entry Blocks Analysis
- `reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_PRODUCTION_V17_1/17B_manual_quote_review_board.md`: The main operator-facing board requires human quote fields for every row, making manual entry look like the next mandatory step instead of an optional downstream step.
- `reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_PRODUCTION_V17_1/17C_coupon_draft_operator_sheet.md`: Coupon draft semantics assume the operator will populate odds before the portfolio is meaningfully usable.

## Where Unpriced Candidates Are Downgraded Too Aggressively
- `reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_PRODUCTION_V17_1/11A_quote_card_blocker_analysis.json`: Eighteen `UNKNOWN_LINE` candidates were downgraded out of the main product even though the blocker was line/price mechanics rather than event-level analytical quality.
- `src/bet/pipeline/rich_coupon_quality.py`: Quote-card validation rejects low/unknown evidence cards and assumes quote-card-quality is the promotion target, conflating analytical usefulness with quote readiness.

## Where Bet Builder Concepts Are Treated Like Priced Coupons
- `reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_PRODUCTION_V17_1/08_same_game_builder_idea_groups.json`: Builder groups were emitted as `QUOTE_REVIEW_ONLY` even though they never compute combined odds and are analytically useful before any operator screen is opened.
- `src/bet/pipeline/coupon_draft_quality.py`: Draft construction starts from quote cards only, so same-event concepts are implicitly treated as coupon inputs first and analytical concepts second.

## Where Quote Cards Became The Main Product
- `reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_PRODUCTION_V17_1/10_final_session_report.json`: The final report headline metrics center quote cards and manual review rather than priced/partial/unpriced analytical candidates.
- `src/bet/pipeline/final_artifact_consistency.py`: Cross-artifact validation is currently quote-card-first, using quote-card counts as the main consistency target.

## Tests Encoding Operator-Entry-First Assumptions
- `tests/test_actionable_quote_cards_v11.py`
- `tests/test_quote_card_actionability_quality.py`
- `tests/test_coupon_draft_quality.py`
- `tests/test_coupon_draft_non_bettable_portfolio.py`
- `tests/test_session_semantic_slate_actuality.py`

## Artifacts To Rename Or Reinterpret
- `12_coupon_drafts.json` -> `12_analysis_portfolio_drafts.json`: Portfolio semantics must no longer imply coupon assembly before price verification.
- `08_same_game_builder_idea_groups.json` -> `18C_superbet_bet_builder_concepts.json`: Same-event groups are analytical concepts, not proto-coupons.
- `17B_manual_quote_review_board.*` -> `18D_optional_superbet_quote_check_shortlist.*`: Quote entry is optional and scoped to the top price-sensitive items only.
- `09_manual_superbet_quote_cards.json` -> `18B_analysis_first_candidate_board.json`: The primary board must rank analytical candidates by pricing tier, not by manual quote capture.
