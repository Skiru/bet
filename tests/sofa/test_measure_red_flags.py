"""measure_red_flags: the side's expected goal difference and the paired gap."""
# ruff: noqa: E501  - the sheet rows are one line each.

from __future__ import annotations

from scripts.sofa.measure_red_flags import Leg, gap, leg_key, paired, side_egd


def _leg(event: int, won: bool, conf: float, day: str = "2026-10-18") -> Leg:
    return Leg(day=day, event=event, sport="football", market="shots_for", subject="a",
               direction="OVER", odds=1.25, confidence=conf, won=won, single=None, egd=None)


def test_side_egd_reads_the_note_of_a_team_row_only() -> None:
    sheet = [
        {"sport": "football", "sofascore_event_id": 1, "market": "shots_for", "subject": "columbus crew",
         "notes": ["GAME_STATE: centre 13.1 = 12.5 x 1.05 (expected goal difference +0.94, beta +0.0506)"]},
        {"sport": "football", "sofascore_event_id": 1, "market": "player_shots_for", "subject": "x",
         "notes": ["PLAYER_STRETCH: (expected goal difference +0.94)"]},
        {"sport": "football", "sofascore_event_id": 1, "market": "shots_for", "subject": "fc cincinnati",
         "notes": ["COUNT_STRETCH: centre 5 (expected goal difference -0.94, beta 0.05)"]},
        {"sport": "football", "sofascore_event_id": 1, "market": "goals_total", "subject": "",
         "notes": ["expected goal difference +0.94"]},
    ]
    assert side_egd(sheet) == {(1, "columbus crew"): 0.94, (1, "fc cincinnati"): -0.94}


def test_leg_key_matches_the_results_key() -> None:
    assert leg_key(15171715, "shots_for", "columbus crew", 10.5, "OVER") == \
        '[15171715, "shots_for", "columbus crew", 10.5, "OVER"]'
    assert leg_key(1, "goals_total", None, 1.5, "OVER") == '[1, "goals_total", "", 1.5, "OVER"]'


def test_paired_gap_is_flagged_minus_control() -> None:
    flagged = [_leg(1, False, 0.8), _leg(2, True, 0.8)]
    control = [_leg(1, True, 0.8), _leg(3, True, 0.8)]
    assert abs(gap(flagged) - (-0.3)) < 1e-9
    diff, lo, hi = paired(flagged, control, gap)
    assert abs(diff - (-0.5)) < 1e-9
    assert lo <= diff <= hi
