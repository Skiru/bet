from bet.pipeline.final_artifact_consistency import validate_cross_artifact_consistency


def test_pass_with_unscoped_blockers_is_blocked() -> None:
    cards = [{"quote_card_id": "q", "event_id": "e", "sport": "football", "market_family": "result", "human_searchable_market_name": "DNB", "line_free_market_type": "DNB"}]
    final = {"STATUS": "PASS", "MANUAL_SUPERBET_QUOTE_REVIEW_ALLOWED": True, "QUOTE_CARDS_BY_SPORT": {"football": 1}, "UNIQUE_QUOTE_CARD_COUNT": 1, "BLOCKERS": {"UNKNOWN_LINE": 18}}
    report = validate_cross_artifact_consistency(final_report=final, daily_certification=None, adversarial_review=None, wimbledon_audit=None, export_manifest=None, quote_cards=cards)
    assert not report.ok
    assert any(issue.code == "UNSCOPED_BLOCKERS_IN_PASS" for issue in report.blockers)


def test_pass_with_global_blockers_is_blocked_even_if_scope_exists() -> None:
    cards = [{"quote_card_id": "q", "event_id": "e", "sport": "football", "market_family": "result", "human_searchable_market_name": "DNB", "line_free_market_type": "DNB"}]
    final = {"STATUS": "PASS", "MANUAL_SUPERBET_QUOTE_REVIEW_ALLOWED": True, "QUOTE_CARDS_BY_SPORT": {"football": 1}, "UNIQUE_QUOTE_CARD_COUNT": 1, "BLOCKERS": {"UNKNOWN_LINE": 18}, "BLOCKER_SCOPE": "BLOCKED_CANDIDATES_ONLY", "GLOBAL_BLOCKERS": {"WIMBLEDON": 1}}
    report = validate_cross_artifact_consistency(final_report=final, daily_certification=None, adversarial_review=None, wimbledon_audit=None, export_manifest=None, quote_cards=cards)
    assert not report.ok
    assert any(issue.code == "GLOBAL_BLOCKERS_IN_PASS" for issue in report.blockers)


def test_scoped_non_promoted_blockers_are_allowed() -> None:
    cards = [{"quote_card_id": "q", "event_id": "e", "sport": "football", "market_family": "result", "human_searchable_market_name": "DNB", "line_free_market_type": "DNB"}]
    final = {"STATUS": "PASS", "MANUAL_SUPERBET_QUOTE_REVIEW_ALLOWED": True, "QUOTE_CARDS_BY_SPORT": {"football": 1}, "UNIQUE_QUOTE_CARD_COUNT": 1, "BLOCKERS": {"UNKNOWN_LINE": 18}, "BLOCKER_SCOPE": "BLOCKED_CANDIDATES_ONLY"}
    report = validate_cross_artifact_consistency(final_report=final, daily_certification=None, adversarial_review=None, wimbledon_audit=None, export_manifest=None, quote_cards=cards)
    assert report.ok, [issue.__dict__ for issue in report.issues]
