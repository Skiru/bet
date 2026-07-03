from bet.pipeline.final_artifact_consistency import validate_cross_artifact_consistency


def _final() -> dict:
    return {"STATUS": "PASS", "MANUAL_SUPERBET_QUOTE_REVIEW_ALLOWED": True, "QUOTE_CARDS_BY_SPORT": {"football": 1}, "UNIQUE_QUOTE_CARD_COUNT": 1}


def _cards() -> list[dict]:
    return [{"quote_card_id": "q1", "event_id": "e", "sport": "football", "market_family": "result", "human_searchable_market_name": "DNB", "line_free_market_type": "DNB"}]


def test_builder_group_requires_group_sport_competition_event_and_leg_identity() -> None:
    report = validate_cross_artifact_consistency(
        final_report=_final(),
        daily_certification=None,
        adversarial_review=None,
        wimbledon_audit=None,
        export_manifest=None,
        quote_cards=_cards(),
        builder_groups=[{"group_id": "g1", "legs": [{"candidate_id": "c1"}], "combined_bookmaker_odds_computed": False}],
    )
    codes = {issue.code for issue in report.blockers}
    assert "BUILDER_GROUP_SPORT_MISSING" in codes
    assert "BUILDER_GROUP_COMPETITION_MISSING" in codes
    assert "BUILDER_GROUP_EVENT_ID_MISSING" in codes
    assert "BUILDER_GROUP_LEG_FIELD_MISSING" in codes


def test_builder_group_with_full_identity_passes() -> None:
    report = validate_cross_artifact_consistency(
        final_report=_final(),
        daily_certification=None,
        adversarial_review=None,
        wimbledon_audit=None,
        export_manifest=None,
        quote_cards=_cards(),
        builder_groups=[{"group_id": "g1", "sport": "football", "competition": "League", "event_id": "e", "combined_bookmaker_odds_computed": False, "legs": [{"candidate_id": "c1", "event_id": "e", "sport": "football"}]}],
    )
    assert report.ok, [issue.__dict__ for issue in report.issues]
