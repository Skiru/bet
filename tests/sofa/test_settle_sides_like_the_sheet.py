"""SETTLE grades the side SHEET priced (review 2026-10-04).

SETTLE matched a team subject with resolve.name_score at the RESOLVE
threshold while SHEET and CONFIDENCE use run_sheet.determine_side, so a
subject SHEET priced could be refused at settle and the printed leg was never
graded: "utsikten" against Utsiktens BK (official coupon 10-03), "ny cosmos",
"polonia sroda wlkp.", 1-8 subjects a day. Over 10,503 priced subjects
09-20..10-04: 39 gained a side, 0 changed one.
"""

from __future__ import annotations

from typing import Any

from scripts.sofa.run_settle import _subject_is_home

UTSIKTEN: dict[str, Any] = {  # runs/sofa/2026-10-03/02_fixtures.json
    "sofascore_event_id": 15458621,
    "superbet_event_ids": ["15041012"],
    "sport": "football",
    "kickoff_utc": "2026-10-03T14:00:00Z",
    "home_name": "Skövde AIK",
    "away_name": "Utsiktens BK",
    "home_entity_id": 7063,
    "away_entity_id": 7536,
    "competition_name": "Ettan, Sodra",
    "competition_id": 11617,
    "season_id": 89299,
    "category_name": "Sweden",
    "identity": "CONFIRMED",
    "round_number": 25,
    "round_name": None,
    "cup_round_type": None,
    "previous_leg_event_id": None,
    "venue_name": None,
    "referee": None,
    "ground_type": None,
    "default_period_count": 2,
    "superbet_kickoff_utc": "2026-10-03T14:00:00Z",
    "kickoff_disagreement_h": 0.0,
}


def test_the_subject_sheet_priced_is_graded_on_the_same_side() -> None:
    assert UTSIKTEN["away_name"] == "Utsiktens BK"
    assert _subject_is_home("utsikten", UTSIKTEN) is False


def test_a_subject_naming_neither_side_is_still_refused() -> None:
    assert _subject_is_home("ifk goteborg", UTSIKTEN) is None


def test_totals_and_derived_subjects_are_unchanged() -> None:
    assert _subject_is_home("", UTSIKTEN) is True
    assert _subject_is_home("1", UTSIKTEN) is None


def test_an_exact_hit_on_an_integer_line_is_skipped_not_written() -> None:
    # settle() returns "PUSH", never None; the guard tested `is None` and
    # could not fire (review 2026-10-04).
    from pathlib import Path

    from bet.sofa.settle import settle
    from scripts.sofa import run_settle

    assert settle(9.0, 9.0, "OVER") == "PUSH"
    src = Path(run_settle.__file__).read_text(encoding="utf-8")
    assert 'if outcome == "PUSH":' in src
    assert "if outcome is None:" not in src


def test_a_derived_row_is_sided_like_a_marginal_one() -> None:
    # Review round 2: most_* / handicap_* rows still used the strict matcher.
    from scripts.sofa.run_settle import _handicap_side

    event = {"homeTeam": {"name": UTSIKTEN["home_name"]},
             "awayTeam": {"name": UTSIKTEN["away_name"]}}
    assert _handicap_side("utsikten", {}, event) is None  # no fixture: as before
    assert _handicap_side("utsikten", {}, event, UTSIKTEN) == "away"
    assert _handicap_side("1", {}, event, UTSIKTEN) == "home"
