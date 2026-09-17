"""T41 — the sample-bias audit actually checks things.

The failure mode this guards is specific: an audit that writes "Status: OK, no
bias flags found" while its inspection loop is empty. Every rule below is
therefore tested twice — once with a planted violation it must catch, once with
the data absent, where it must say UNVERIFIABLE and never OK.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.sofa.audit_sample_bias import (
    check_card_points,
    check_friendlies,
    check_one_row_one_sample,
    check_tennis_surface,
    check_tiebreak_games,
    check_total_vs_for,
    check_zero_inflation,
    render_report,
    run_audit,
)


def obs(event_id: int, value: float, competition_id: int = 17) -> dict[str, Any]:
    return {
        "sofascore_event_id": event_id,
        "match_date_utc": "2026-09-01T00:00:00Z",
        "opponent": "Opp",
        "value": value,
        "competition_id": competition_id,
        "season_id": 1,
        "venue": "home",
    }


def fixture_samples(event_id: int, metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "sofascore_event_id": event_id,
        "readiness": "READY",
        "metrics": metrics,
        "gaps": [],
    }


def metric(side_a: list[Any], side_b: list[Any], h2h: list[Any] | None = None) -> Any:
    return {"side_a": side_a, "side_b": side_b, "h2h": h2h or []}


# --------------------------------------------------------------------------
# Cards: points must never fall below yellows on the same event (L4).
# --------------------------------------------------------------------------

def test_card_rule_catches_a_points_sample_counting_yellows() -> None:
    samples = [
        fixture_samples(
            1,
            {
                "cards_points_total": metric([obs(10, 2.0)], []),
                "cards_total": metric([obs(10, 3.0)], []),
            },
        )
    ]
    result = check_card_points(samples)
    assert result.status == "FLAGGED"
    assert result.observations == 1
    assert "counting yellows" in result.flags[0]


def test_card_rule_passes_when_points_exceed_yellows() -> None:
    samples = [
        fixture_samples(
            1,
            {
                "cards_points_total": metric([obs(10, 5.0)], []),
                "cards_total": metric([obs(10, 3.0)], []),
            },
        )
    ]
    result = check_card_points(samples)
    assert result.status == "OK"
    assert result.observations == 1


def test_card_rule_is_unverifiable_without_both_samples() -> None:
    samples = [fixture_samples(1, {"cards_total": metric([obs(10, 3.0)], [])})]
    assert check_card_points(samples).status == "UNVERIFIABLE"


# --------------------------------------------------------------------------
# Tennis games must clear six per set (L5, PULAPKA #5).
# --------------------------------------------------------------------------

def test_tiebreak_rule_catches_games_below_the_floor() -> None:
    """serviceGamesTotal is short one game per tie-break set, one-directionally."""
    samples = [
        fixture_samples(
            1,
            {
                "games_total": metric([obs(10, 16.0)], []),
                "sets_total": metric([obs(10, 3.0)], []),
            },
        )
    ]
    result = check_tiebreak_games(samples)
    assert result.status == "FLAGGED"
    assert "tie-break games are missing" in result.flags[0]


def test_tiebreak_rule_passes_on_a_real_game_count() -> None:
    samples = [
        fixture_samples(
            1,
            {
                "games_total": metric([obs(10, 35.0)], []),
                "sets_total": metric([obs(10, 3.0)], []),
            },
        )
    ]
    assert check_tiebreak_games(samples).status == "OK"


def test_tiebreak_rule_is_unverifiable_without_sets() -> None:
    samples = [fixture_samples(1, {"games_total": metric([obs(10, 35.0)], [])})]
    assert check_tiebreak_games(samples).status == "UNVERIFIABLE"


# --------------------------------------------------------------------------
# _total is not one side's value (L6).
# --------------------------------------------------------------------------

def test_total_rule_catches_a_total_holding_one_side_s_value() -> None:
    samples = [
        fixture_samples(
            1,
            {
                "corners_total": metric([obs(10, 6.0)], []),
                "corners_for": metric([obs(10, 6.0)], [obs(10, 4.0)]),
            },
        )
    ]
    result = check_total_vs_for(samples)
    assert result.status == "FLAGGED"
    assert "sides sum to" in result.flags[0]


def test_total_rule_passes_when_the_sides_add_up() -> None:
    samples = [
        fixture_samples(
            1,
            {
                "corners_total": metric([obs(10, 10.0)], []),
                "corners_for": metric([obs(10, 6.0)], [obs(10, 4.0)]),
            },
        )
    ]
    assert check_total_vs_for(samples).status == "OK"


# --------------------------------------------------------------------------
# Friendlies are out of a football counting sample (§6.1).
# --------------------------------------------------------------------------

def test_friendly_rule_catches_a_friendly_in_the_sample() -> None:
    samples = [
        fixture_samples(
            1, {"corners_total": metric([obs(10, 9.0, competition_id=853)], [])}
        )
    ]
    result = check_friendlies(samples, {1: "football"})
    assert result.status == "FLAGGED"
    assert "friendly competition 853" in result.flags[0]


def test_friendly_rule_passes_on_league_matches_only() -> None:
    samples = [fixture_samples(1, {"corners_total": metric([obs(10, 9.0)], [])})]
    assert check_friendlies(samples, {1: "football"}).status == "OK"


def test_friendly_rule_is_unverifiable_with_no_football() -> None:
    samples = [fixture_samples(1, {"aces_total": metric([obs(10, 9.0)], [])})]
    assert check_friendlies(samples, {1: "tennis"}).status == "UNVERIFIABLE"


# --------------------------------------------------------------------------
# Tennis surface and format.
# --------------------------------------------------------------------------

class FakeCache:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = events

    def iter_entity_events(self) -> Any:
        yield (1, "last", 0, {"events": self._events})


def _tennis_event(event_id: int, ground: str, sets_won: int) -> dict[str, Any]:
    return {
        "id": event_id,
        "groundType": ground,
        "homeScore": {"current": sets_won},
        "awayScore": {"current": 0},
    }


def test_surface_rule_catches_a_clay_match_in_a_hard_court_sample() -> None:
    samples = [fixture_samples(1, {"games_total": metric([obs(10, 22.0)], [])})]
    fixtures = {
        1: {
            "sofascore_event_id": 1,
            "sport": "tennis",
            "ground_type": "Hardcourt outdoor",
            "best_of": 3,
        }
    }
    cache = FakeCache([_tennis_event(10, "Red clay", 2)])
    result = check_tennis_surface(samples, fixtures, cache)  # type: ignore[arg-type]
    assert result.status == "FLAGGED"
    assert "Red clay" in result.flags[0]


def test_surface_rule_catches_a_best_of_five_in_a_best_of_three_sample() -> None:
    samples = [fixture_samples(1, {"games_total": metric([obs(10, 22.0)], [])})]
    fixtures = {
        1: {
            "sofascore_event_id": 1,
            "sport": "tennis",
            "ground_type": "Hardcourt outdoor",
            "best_of": 3,
        }
    }
    cache = FakeCache([_tennis_event(10, "Hardcourt outdoor", 3)])
    result = check_tennis_surface(samples, fixtures, cache)  # type: ignore[arg-type]
    assert result.status == "FLAGGED"
    assert "best-of-5" in result.flags[0]


def test_surface_rule_passes_on_a_matching_sample() -> None:
    samples = [fixture_samples(1, {"games_total": metric([obs(10, 22.0)], [])})]
    fixtures = {
        1: {
            "sofascore_event_id": 1,
            "sport": "tennis",
            "ground_type": "Hardcourt outdoor",
            "best_of": 3,
        }
    }
    cache = FakeCache([_tennis_event(10, "Hardcourt outdoor", 2)])
    result = check_tennis_surface(samples, fixtures, cache)  # type: ignore[arg-type]
    assert result.status == "OK"


def test_surface_rule_is_unverifiable_without_a_cache() -> None:
    """No cache means the rule was not evaluated. It must not report OK."""
    samples = [fixture_samples(1, {"games_total": metric([obs(10, 22.0)], [])})]
    result = check_tennis_surface(samples, {}, None)
    assert result.status == "UNVERIFIABLE"
    assert "cache" in result.detail


def test_surface_rule_is_unverifiable_when_nothing_can_be_traced() -> None:
    samples = [fixture_samples(1, {"games_total": metric([obs(99, 22.0)], [])})]
    fixtures = {
        1: {
            "sofascore_event_id": 1,
            "sport": "tennis",
            "ground_type": "Hardcourt outdoor",
            "best_of": 3,
        }
    }
    cache = FakeCache([_tennis_event(10, "Hardcourt outdoor", 2)])
    result = check_tennis_surface(samples, fixtures, cache)  # type: ignore[arg-type]
    assert result.status == "UNVERIFIABLE"
    assert "untraceable" in result.detail


# --------------------------------------------------------------------------
# Zero inflation and one-row-one-sample.
# --------------------------------------------------------------------------

def test_zero_inflation_flags_a_metric_that_is_mostly_zero() -> None:
    """L1: a median of 0 is a statement about the provider, not about football."""
    samples = [
        fixture_samples(
            1, {"offsides_total": metric([obs(i, 0.0) for i in range(10)], [])}
        )
    ]
    result = check_zero_inflation(samples)
    assert result.status == "FLAGGED"
    assert "median is 0" in result.flags[0]


def test_zero_inflation_passes_on_a_real_distribution() -> None:
    samples = [
        fixture_samples(
            1,
            {
                "offsides_total": metric(
                    [obs(i, float(i % 5 + 1)) for i in range(10)], []
                )
            },
        )
    ]
    assert check_zero_inflation(samples).status == "OK"


def test_one_row_one_sample_catches_a_duplicated_event() -> None:
    samples = [
        fixture_samples(
            1, {"goals_total": metric([obs(10, 2.0), obs(10, 2.0)], [])}
        )
    ]
    result = check_one_row_one_sample(samples)
    assert result.status == "FLAGGED"
    assert "appears twice" in result.flags[0]


# --------------------------------------------------------------------------
# The report is generated from the results, not written independently.
# --------------------------------------------------------------------------

def test_report_never_says_ok_for_an_unevaluated_rule() -> None:
    results = run_audit([], [], None)
    report = render_report(results, "2026-09-17")
    assert results, "run_audit must return a result per rule"
    for result in results:
        assert result.status in {"OK", "FLAGGED", "UNVERIFIABLE"}
        if result.observations == 0:
            assert result.status == "UNVERIFIABLE", (
                f"{result.name} claimed {result.status} having checked nothing"
            )
    assert "OK, no bias flags found" not in report
    assert "UNVERIFIABLE" in report


def test_report_prints_the_observation_count_of_every_rule() -> None:
    samples = [fixture_samples(1, {"goals_total": metric([obs(10, 2.0)], [])})]
    fixtures = [{"sofascore_event_id": 1, "sport": "football"}]
    results = run_audit(samples, fixtures, None)
    report = render_report(results, "2026-09-17")
    for result in results:
        assert f"Observations checked: {result.observations}" in report


@pytest.mark.parametrize(
    "rule",
    [
        check_card_points,
        check_tiebreak_games,
        check_total_vs_for,
        check_zero_inflation,
        check_one_row_one_sample,
    ],
)
def test_every_rule_reports_unverifiable_on_an_empty_day(rule: Any) -> None:
    assert rule([]).status == "UNVERIFIABLE"
