"""bet.sofa.shot_detail on a real shotmap: Viking - Bayern, 2026-10-13
(Sofascore 16939021, trimmed to the fields the module reads).

Pinned against two outside facts: Sofascore's own team statistic
totalShotsOutsideBox for this match (Viking 2, Bayern 8, cached /statistics)
and Superbet's settlement of "Michael Olise - celne strzały spoza pola
karnego powyżej 0.5", which the operator's slip shows WON."""

from __future__ import annotations

import json
from pathlib import Path

from bet.sofa import shot_detail as sd

GOLDEN = Path(__file__).parent / "golden" / "shotmap_viking_bayern_2026-10-13.json"
OLISE = 978838


def _payload() -> dict[str, list[dict[str, object]]]:
    data: dict[str, list[dict[str, object]]] = json.loads(GOLDEN.read_text())
    return data


def test_team_outside_box_matches_sofascore_statistic() -> None:
    shots = _payload()["shotmap"]
    home = sum(1 for s in shots if s["isHome"] and sd.is_outside_box(s))
    away = sum(1 for s in shots if not s["isHome"] and sd.is_outside_box(s))
    assert (home, away) == (2, 8)


def test_olise_outside_box_on_target_settles_as_superbet_did() -> None:
    got = sd.player_counts(_payload(), OLISE)
    assert got is not None
    assert got["player_shots_outside_box_for"] == 2
    assert got["player_sot_outside_box_for"] == 1  # > 0.5: WON
    assert got["player_left_foot_shots_for"] == 3
    assert got["player_headed_shots_for"] == 0


def test_missing_shotmap_is_unknown_and_absent_player_is_zero() -> None:
    assert sd.player_counts(None, OLISE) is None
    assert sd.player_counts({"shotmap": []}, OLISE) is None
    zero = sd.player_counts(_payload(), 1)
    assert zero is not None and set(zero.values()) == {0}


def test_market_names_cover_every_metric_once() -> None:
    assert sorted(set(sd.MARKET_NAMES.values())) == list(sd.METRICS)
    assert len(sd.METRICS) == 8


def test_p_over_is_the_poisson_tail() -> None:
    import math

    m = 0.8
    assert abs(sd.p_over(m, 0.5) - (1 - math.exp(-m))) < 1e-12
    assert abs(sd.p_over(m, 1.5) - (1 - math.exp(-m) * (1 + m))) < 1e-12
    assert sd.p_over(0.0, 0.5) == 0.0


def test_forecast_shrinks_to_the_position_and_needs_five_starts() -> None:
    fitted = {"metrics": {"player_shots_outside_box_for": {
        "k": 5, "pool": {"M": 0.5}, "pool_all": 0.3}}}
    values = [2.0, 1.0, 2.0, 1.0, 2.0, 1.0]  # mean 1.5
    p = sd.forecast(values, "M", "player_shots_outside_box_for", 0.5, fitted)
    mean = (9.0 + 5 * 0.5) / 11
    assert p is not None and abs(p - sd.p_over(mean, 0.5)) < 1e-12
    # an unknown position reads the all-positions mean
    q = sd.forecast(values, "G", "player_shots_outside_box_for", 0.5, fitted)
    assert q is not None and abs(q - sd.p_over((9.0 + 1.5) / 11, 0.5)) < 1e-12
    assert sd.forecast(values[:4], "M", "player_shots_outside_box_for", 0.5,
                       fitted) is None
    assert sd.forecast(values, "M", "player_headed_shots_for", 0.5, fitted) is None


def test_a_hockey_shotmap_is_not_a_football_record() -> None:
    hockey = {"shotmap": [{"player": {"id": 5}, "x": 10, "y": 40,
                           "shotType": "wrist"}]}
    assert sd.player_counts(hockey, 5) is None
