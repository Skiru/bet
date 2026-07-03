from bet.pipeline.final_artifact_consistency import validate_cross_artifact_consistency


def test_wimbledon_mismatch_blocks_all_final_artifacts() -> None:
    cards = [
        {"quote_card_id": f"q{i}", "event_id": f"w{i}", "sport": "tennis", "market_family": "result", "human_searchable_market_name": f"Match winner {i}", "line_free_market_type": "MATCH_WINNER"}
        for i in range(30)
    ]
    final = {"STATUS": "PASS", "MANUAL_SUPERBET_QUOTE_REVIEW_ALLOWED": True, "QUOTE_CARDS_BY_SPORT": {"tennis": 30}, "UNIQUE_QUOTE_CARD_COUNT": 30}
    daily = {"WIMBLEDON_QUOTE_CARDS": 0, "QUOTE_CARDS_BY_SPORT": {"tennis": 30}, "UNIQUE_QUOTE_CARD_COUNT": 30}
    adv = {"WIMBLEDON_QUOTE_CARDS": 0, "QUOTE_CARDS_BY_SPORT": {"tennis": 30}, "UNIQUE_QUOTE_CARD_COUNT": 30}
    manifest = {"quote_cards_by_sport": {"tennis": 30}, "unique_quote_card_count": 30}
    wim = {"wimbledon_singles_quote_cards": 30}
    report = validate_cross_artifact_consistency(
        final_report=final,
        daily_certification=daily,
        adversarial_review=adv,
        wimbledon_audit=wim,
        export_manifest=manifest,
        quote_cards=cards,
    )
    assert not report.ok
    assert {i.code for i in report.blockers} >= {"WIMBLEDON_QUOTE_CARD_MISMATCH", "WIMBLEDON_QUOTE_CARD_DECLARATION_MISSING"}


def test_consistent_wimbledon_and_counts_pass_without_groups_or_drafts() -> None:
    cards = [
        {"quote_card_id": "qf", "event_id": "f", "sport": "football", "market_family": "result", "human_searchable_market_name": "DNB", "line_free_market_type": "DNB"},
        {"quote_card_id": "qt", "event_id": "w", "sport": "tennis", "market_family": "result", "human_searchable_market_name": "Match winner", "line_free_market_type": "MATCH_WINNER"},
    ]
    final = {"STATUS": "PASS", "MANUAL_SUPERBET_QUOTE_REVIEW_ALLOWED": True, "QUOTE_CARDS_BY_SPORT": {"football": 1, "tennis": 1}, "UNIQUE_QUOTE_CARD_COUNT": 2, "WIMBLEDON_QUOTE_CARDS": 1}
    daily = dict(final)
    adv = dict(final)
    manifest = {"quote_cards_by_sport": {"football": 1, "tennis": 1}, "unique_quote_card_count": 2, "WIMBLEDON_QUOTE_CARDS": 1}
    wim = {"wimbledon_singles_quote_cards": 1}
    report = validate_cross_artifact_consistency(
        final_report=final,
        daily_certification=daily,
        adversarial_review=adv,
        wimbledon_audit=wim,
        export_manifest=manifest,
        quote_cards=cards,
    )
    assert report.ok, [issue.__dict__ for issue in report.issues]
