from bet.pipeline.coupon_draft_diversification import build_diversified_coupon_draft
from bet.pipeline.final_artifact_consistency import validate_cross_artifact_consistency


def _cards() -> list[dict]:
    return [
        {"quote_card_id": "f1", "candidate_id": "cf1", "event_id": "ef1", "sport": "football", "market_family": "result", "human_searchable_market_name": "DNB A", "line_free_market_type": "DNB", "final_status": "QUOTE_REVIEW_ONLY", "bettable": False, "combined_bookmaker_odds_computed": False},
        {"quote_card_id": "f2", "candidate_id": "cf2", "event_id": "ef2", "sport": "football", "market_family": "result", "human_searchable_market_name": "DNB B", "line_free_market_type": "DNB", "final_status": "QUOTE_REVIEW_ONLY", "bettable": False, "combined_bookmaker_odds_computed": False},
        {"quote_card_id": "t1", "candidate_id": "ct1", "event_id": "et1", "sport": "tennis", "market_family": "result", "human_searchable_market_name": "Match winner", "line_free_market_type": "MATCH_WINNER", "final_status": "QUOTE_REVIEW_ONLY", "bettable": False, "combined_bookmaker_odds_computed": False},
        {"quote_card_id": "b1", "candidate_id": "cb1", "event_id": "eb1", "sport": "basketball", "market_family": "result", "human_searchable_market_name": "Moneyline", "line_free_market_type": "MONEYLINE", "final_status": "QUOTE_REVIEW_ONLY", "bettable": False, "combined_bookmaker_odds_computed": False},
    ]


def _final() -> dict:
    return {"STATUS": "PASS", "MANUAL_SUPERBET_QUOTE_REVIEW_ALLOWED": True, "QUOTE_CARDS_BY_SPORT": {"football": 2, "tennis": 1, "basketball": 1}, "UNIQUE_QUOTE_CARD_COUNT": 4}


def test_diversified_draft_uses_multiple_sports_when_available() -> None:
    draft = build_diversified_coupon_draft(_cards(), draft_id="balanced", max_legs=4)
    assert draft["bettable"] is False
    assert draft["combined_odds"] is None
    assert len({leg["sport"] for leg in draft["legs"]}) >= 2
    assert draft["diversification_blocker"] is None


def test_single_sport_draft_without_reason_blocks_when_quote_board_is_multisport() -> None:
    bad_draft = {"coupon_draft_id": "draft", "status": "DRAFT_REQUIRES_HUMAN_QUOTES", "bettable": False, "combined_odds": None, "legs": [
        {"quote_card_id": "f1", "candidate_id": "cf1", "event_id": "ef1", "sport": "football"},
        {"quote_card_id": "f2", "candidate_id": "cf2", "event_id": "ef2", "sport": "football"},
        {"quote_card_id": "f3", "candidate_id": "cf3", "event_id": "ef3", "sport": "football"},
    ]}
    report = validate_cross_artifact_consistency(final_report=_final(), daily_certification=None, adversarial_review=None, wimbledon_audit=None, export_manifest=None, quote_cards=_cards(), coupon_drafts=[bad_draft])
    assert not report.ok
    assert any(issue.code == "COUPON_DRAFT_SINGLE_SPORT_WITHOUT_REASON" for issue in report.blockers)


def test_single_sport_draft_with_explicit_reason_is_allowed() -> None:
    draft = {"coupon_draft_id": "draft", "status": "DRAFT_REQUIRES_HUMAN_QUOTES", "bettable": False, "combined_odds": None, "diversification_blocker": "CORRELATION_OR_PRICE_REVIEW_LIMITED_TO_FOOTBALL", "legs": [
        {"quote_card_id": "f1", "candidate_id": "cf1", "event_id": "ef1", "sport": "football"},
        {"quote_card_id": "f2", "candidate_id": "cf2", "event_id": "ef2", "sport": "football"},
        {"quote_card_id": "f2", "candidate_id": "cf2", "event_id": "ef2", "sport": "football"},
    ]}
    report = validate_cross_artifact_consistency(final_report=_final(), daily_certification=None, adversarial_review=None, wimbledon_audit=None, export_manifest=None, quote_cards=_cards(), coupon_drafts=[draft])
    assert report.ok, [issue.__dict__ for issue in report.issues]
