from __future__ import annotations

from bet.pipeline.tipster_opinion_quality import (
    TipsterContextState,
    determine_tipster_context_status,
    validate_tipster_opinion_alignment,
)


def test_tipster_context_states() -> None:
    status = determine_tipster_context_status(attempted=True, usable_opinions_count=0)
    assert status == TipsterContextState.ATTEMPTED_NO_MATCHES

    status = determine_tipster_context_status(attempted=True, usable_opinions_count=5)
    assert status == TipsterContextState.MATCHED_OPINIONS

    status = determine_tipster_context_status(attempted=False, usable_opinions_count=0)
    assert status == TipsterContextState.NOT_ATTEMPTED


def test_misaligned_tipster_claims_raise_errors() -> None:
    cards = [{"quote_card_id": "qc1", "tipster_consensus_ref": "op1"}]
    # Case 1: Status is ATTEMPTED_NO_MATCHES
    errors = validate_tipster_opinion_alignment(status=TipsterContextState.ATTEMPTED_NO_MATCHES, quote_cards=cards, opinions=[])
    assert len(errors) == 1
    assert "claims tipster support" in errors[0]

    # Case 2: Ref not in opinions list
    errors = validate_tipster_opinion_alignment(status=TipsterContextState.MATCHED_OPINIONS, quote_cards=cards, opinions=[])
    assert len(errors) == 1
    assert "does not exist in matched opinions" in errors[0]
