"""Audit 2026-10-23 P5: SETTLE grades a "slug" player sample by the squad
name SAMPLES matched (run_settle.player_token_names), never the board name."""

from __future__ import annotations

from datetime import UTC, datetime

from bet.sofa import epochs
from bet.sofa.contracts import PlayerSample
from scripts.sofa import run_settle

KEY = "player_shots_for|Julian Chabot"


def test_a_slug_sample_is_graded_by_its_matched_name() -> None:
    doc = [{"sofascore_event_id": 7, "players": {KEY: {
        "match_rule": "slug", "matched_name": "jeff chabot",
        "side": "side_a"}}}]
    assert run_settle.player_token_names(doc) == {(7, KEY): "jeff chabot"}


def test_a_fuzzy_sample_is_still_graded_by_the_board_name() -> None:
    doc = [{"sofascore_event_id": 7, "players": {KEY: {
        "match_rule": "fuzzy", "matched_name": "jeff chabot"}}}]
    assert run_settle.player_token_names(doc) == {}


def test_the_contract_admits_the_slug_rule() -> None:
    fields = PlayerSample.model_fields["match_rule"]
    assert "slug" in str(fields.annotation)


def test_the_switch_is_on_from_2026_10_24() -> None:
    assert epochs.player_slug_name("2026-10-24",
                                   datetime(2026, 10, 24, 0, 0, tzinfo=UTC))
    assert not epochs.player_slug_name(
        "2026-10-23", datetime(2026, 10, 24, 1, 0, tzinfo=UTC))
    assert not epochs.player_slug_name(
        "2026-10-24", datetime(2026, 10, 23, 23, 59, tzinfo=UTC))
