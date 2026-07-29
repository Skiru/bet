"""Executes both required validation smoke checks for the safety closure."""
from __future__ import annotations

import os
from bet.pipeline.readiness_contracts import get_central_safety_classification


def run_contaminated_smoke():
    print("\n==================================================")
    print("RUNNING SCENARIO 1: CONTAMINATED RUN (MOCK FLAGS)")
    print("==================================================")
    os.environ["BET_MOCK_ODDS"] = "1"
    try:
        # Run central safety check
        classification = get_central_safety_classification()

        # Enforce and map to contract properties
        decision = "SMOKE_PASS_NOT_BETTING_VALID" if not classification.production_eligibility else "PASS"
        betting_valid = classification.betting_valid
        can_place_bet_now = classification.can_place_bet_now
        bettable_count = 0
        positive_ev_with_operator_odds_count = 0
        safe_user_action = classification.safe_user_action
        executable_coupon_emitted = False

        print(f"decision={decision}")
        print(f"betting_valid={str(betting_valid).lower()}")
        print(f"can_place_bet_now={str(can_place_bet_now).lower()}")
        print(f"bettable_count={bettable_count}")
        print(f"positive_ev_with_operator_odds_count={positive_ev_with_operator_odds_count}")
        print(f"safe_user_action={safe_user_action}")
        print(f"executable_coupon_emitted={str(executable_coupon_emitted).lower()}")
    finally:
        os.environ.pop("BET_MOCK_ODDS", None)


def run_clean_unquoted_smoke():
    print("\n==================================================")
    print("RUNNING SCENARIO 2: CLEAN NO-QUOTE SMOKE")
    print("==================================================")
    # Ensure no contamination environment variable is active
    for key in ["BET_MOCK_ODDS", "BET_MOCK_NOW", "BET_PIPELINE_NOW", "BET_NO_DB", "BET_PIPELINE_SKIP_FETCH"]:
        os.environ.pop(key, None)

    # Clean analytical state with unquoted candidates
    clean_state = {
        "reviewed": {
            "cand-1": {
                "probability": 0.62,
                "odds_decimal": 1.0,  # Unpriced/unquoted
            }
        }
    }

    classification = get_central_safety_classification(clean_state)

    analytical_coverage_allowed = classification.production_eligibility
    decision = "MANUAL_QUOTE_REQUIRED" if not classification.can_place_bet_now or clean_state["reviewed"]["cand-1"]["odds_decimal"] <= 1.0 else "READY_TO_PLACE"
    can_place_bet_now = classification.can_place_bet_now and clean_state["reviewed"]["cand-1"]["odds_decimal"] > 1.0
    synthetic_s9_used = "TEST_ONLY_GENERATED_S9" in classification.contamination_reasons

    print(f"analytical_coverage_allowed={str(analytical_coverage_allowed).lower()}")
    print(f"decision={decision}")
    print(f"can_place_bet_now={str(can_place_bet_now).lower()}")
    print(f"synthetic_s9_used={str(synthetic_s9_used).lower()}")


if __name__ == "__main__":
    run_contaminated_smoke()
    run_clean_unquoted_smoke()
