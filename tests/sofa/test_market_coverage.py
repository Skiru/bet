# ruff: noqa: E501  - the parametrize table holds whole Superbet names.
"""MARKET COVERAGE (plan 2026-10-05 F1.1): one label per unmapped Superbet name.

Names are the strings OFFER wrote into 2026-10-05's ``04_offer.json``
``unmapped_markets`` (cut down to one fixture each).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.market_coverage import (
    COMBO_FAMILY,
    FOOTBALL_RULES,
    LABELS,
    TENNIS_RULES,
    build_report,
    classify_market_name,
    template_of,
)
from scripts.sofa.report_market_coverage import main

FB = ["Nestos Chrisoupolis", "GS Marko"]
TN = ["Duje Ajdukovic", "Filip Cristian Jianu"]


def test_template_folds_names_numbers_and_keeps_ordinals() -> None:
    t = template_of("1.połowa - GS Marko strzeli powyżej 1.5 gola", FB)
    assert t == "1.polowa - {b} strzeli powyzej # gola"
    # "ł" has no NFD decomposition - it must still fold (market_mapper.fold).
    assert "polowa" in template_of("2. połowa - liczba kartek", FB)
    assert template_of("Zostanie rozegrany 3. set", TN) == "zostanie rozegrany 3. set"
    assert template_of("1. set - dokładny wynik 6:3", TN) == "1. set - dokladny wynik #:#"


def test_side_is_replaced_only_as_a_whole_word() -> None:
    # A side called "Fran" must not eat the start of "Francesco" (09-2x boards).
    t = template_of("Francesco Pio Esposito powyżej 0.5 celnych strzałów", ["Fran", "X"])
    assert t.startswith("francesco pio esposito")


@pytest.mark.parametrize(
    ("name", "sport", "sides", "label", "family"),
    [
        ("GS Marko strzeli gola", "football", FB, "MAPPABLE", "fb.team_scores"),
        ("1.połowa - obie drużyny strzelą", "football", FB, "MAPPABLE", "fb.btts_half"),
        ("Każda drużyna powyżej X rzutów z autu", "football", FB, "MAPPABLE", "fb.both_over_throw_ins"),
        ("Zostanie rozegrany 3. set", "tennis", TN, "MAPPABLE", "tn.deciding_set_played"),
        ("Mecz", "football", FB, "COMPUTABLE", "fb.result"),
        ("1. gol (przedziały 10-minutowe)", "football", FB, "COMPUTABLE", "fb.goal_timing"),
        ("Zawodnik - strzeli gola głową", "football", FB, "COMPUTABLE", "fb.player_goal_detail"),
        ("Duje Ajdukovic wygra bez straty seta", "tennis", TN, "COMPUTABLE", "tn.sets"),
        ("1. set - dokładny wynik", "tennis", TN, "COMPUTABLE", "tn.set_score"),
        ("Kto wykona 1. rzut rożny", "football", FB, "NOT_COMPUTABLE", "fb.non_goal_event_timing"),
        ("Zawodnik - liczba strzałów głową", "football", FB, "NOT_COMPUTABLE", "fb.player_shot_detail"),
        ("1. set - będzie prowadzić po 2 gemach", "tennis", TN, "NOT_COMPUTABLE", "tn.game_order"),
        ("Duje Ajdukovic 1. gem serwisowy - dokładny wynik", "tennis", TN, "NOT_COMPUTABLE", "tn.points_in_game"),
        ("Boost", "tennis", TN, "NOT_COMPUTABLE", "boost"),
    ],
)
def test_one_name_one_label(name: str, sport: str, sides: list[str], label: str, family: str) -> None:
    c = classify_market_name(name, sport, sides)
    assert (c.label, c.family) == (label, family)
    assert c.note  # every labelled family says what it proposes / needs / lacks


def test_alternatives_are_anchored_as_a_whole() -> None:
    # Regression: "^a|b$" matched "dokladny wynik" as a PREFIX, so a point-level
    # market read as a set-score one.
    c = classify_market_name(
        "Dokładny wynik - wynik po 3 punktach w 1. gemie serwisowym Duje Ajdukovic", "tennis", TN
    )
    assert c.label == "NOT_COMPUTABLE"
    assert c.family == "tn.points_in_game"


def test_set_three_is_not_the_declared_set_metrics() -> None:
    one = classify_market_name("Liczba gemów: powyżej 20.5; 1. set - powyżej 9.5 gemów", "tennis", TN)
    assert one.label == "COMPUTABLE" and one.family == COMBO_FAMILY
    assert [p.family for p in one.parts] == ["tn.games_total", "tn.games_set_total"]
    assert {p.label for p in one.parts} == {"MAPPABLE"}
    three = classify_market_name("3. set - powyżej 9.5 gemów; Zwycięzca - Duje Ajdukovic", "tennis", TN)
    assert three.parts[0].label == "COMPUTABLE"  # games_set3_total is not a metric


def test_combination_takes_its_worst_part() -> None:
    nc = classify_market_name(
        "Duje Ajdukovic 1. gem serwisowy - Duje Ajdukovic wygra; Zwycięzca - Duje Ajdukovic", "tennis", TN
    )
    assert nc.label == "NOT_COMPUTABLE"
    assert "tn.game_order" in nc.note
    unknown = classify_market_name("Powyżej 1.5 gola w meczu; Coś zupełnie nowego", "football", FB)
    assert unknown.label == "UNCLASSIFIED"
    ok = classify_market_name("Powyżej 1.5 gola w meczu; GS Marko wygra lub zremisuje", "football", FB)
    assert ok.label == "COMPUTABLE"
    assert [p.label for p in ok.parts] == ["MAPPABLE", "COMPUTABLE"]


def test_unknown_name_is_unclassified_never_guessed() -> None:
    c = classify_market_name("Liczba dronów nad stadionem", "football", FB)
    assert c.label == "UNCLASSIFIED"


def test_player_pattern_never_reads_a_side() -> None:
    # "<side> powyżej X strzałów" is not a player prop; with no team rule for
    # the shape it must stay visible rather than be filed as player_shots_for.
    c = classify_market_name("GS Marko powyżej 9.5 strzałów; Mecz", "football", FB)
    assert c.parts[0].family != "fb.player_shots"


def test_name_today_mapper_reads_is_labelled_mapped() -> None:
    # Unmapped on an older day's code, read by today's market_mapper.
    c = classify_market_name("1. set - liczba gemów", "tennis", TN)
    assert (c.label, c.family) == ("MAPPABLE", "mapper.current")
    assert c.note.startswith("games_set1_total")
    nl = classify_market_name("Liczba goli (no line)", "football", FB)
    assert (nl.label, nl.family) == ("MAPPABLE", "mapper.line_refused")


def test_ampersand_in_a_club_name_is_a_mapping_gap() -> None:
    sides = ["Dagenham & Redbridge", "Ebbsfleet"]
    c = classify_market_name("Dagenham & Redbridge - liczba goli", "football", sides)
    assert (c.label, c.family) == ("MAPPABLE", "mapper.side_name_refused")
    assert c.note.startswith("goals_for")


def test_rule_tables_carry_one_of_the_three_labels() -> None:
    for rule in FOOTBALL_RULES + TENNIS_RULES:
        assert rule.label in LABELS[:3]
        assert rule.note


def _day() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    board = [{"superbet_event_id": "1", "side_a": "Nestos Chrisoupolis", "side_b": "GS Marko"}]
    fixtures = [{"sofascore_event_id": 10, "superbet_event_ids": ["1"], "sport": "football",
                 "home_name": "Nestos", "away_name": "Marko"}]
    offers = [{
        "sofascore_event_id": 10,
        "rungs": [
            {"market": "goals_total", "subject": "", "line": 2.5},
            {"market": "goals_total", "subject": "", "line": 3.5},
            {"market": "corners_for", "subject": "gs marko", "line": 4.5},
            {"market": "handicap_corners", "subject": "gs marko", "line": -1.5},
            {"market": "handicap_corners", "subject": "nestos chrisoupolis", "line": 1.5},
        ],
        "unmapped_markets": ["Mecz", "GS Marko strzeli gola", "Kto wykona 1. rzut rożny",
                             "Liczba dronów nad stadionem"],
    }]
    return board, fixtures, offers


def test_report_counts_every_name_once() -> None:
    board, fixtures, offers = _day()
    r = build_report(offers, fixtures, board, date="2026-10-05")
    assert r["unmapped"]["occurrences"] == 4
    assert {k: v["occurrences"] for k, v in r["by_label"].items()} == {
        "MAPPABLE": 1, "COMPUTABLE": 1, "NOT_COMPUTABLE": 1, "UNCLASSIFIED": 1}
    # ladders once per (market, subject); a handicap once for all selections
    assert r["mapped"]["instances"] == 3
    assert r["offered_market_instances"] == 7
    assert r["unclassified"] == [{"template": "liczba dronow nad stadionem", "occurrences": 1}]


def test_script_exit_codes(tmp_path: Path) -> None:
    board, fixtures, offers = _day()
    day = tmp_path / "2026-10-05"
    day.mkdir()
    for name, data in (("01_board.json", board), ("02_fixtures.json", fixtures), ("04_offer.json", offers)):
        (day / name).write_text(json.dumps(data), encoding="utf-8")
    assert main(["--date", "2026-10-05", "--runs-dir", str(tmp_path)]) == 1  # one UNCLASSIFIED
    report = json.loads((day / "market_coverage.json").read_text(encoding="utf-8"))
    assert report["by_label"]["UNCLASSIFIED"]["occurrences"] == 1
    assert "UNCLASSIFIED" in (day / "market_coverage.md").read_text(encoding="utf-8")
    offers[0]["unmapped_markets"].remove("Liczba dronów nad stadionem")
    (day / "04_offer.json").write_text(json.dumps(offers), encoding="utf-8")
    assert main(["--date", "2026-10-05", "--runs-dir", str(tmp_path)]) == 0
    assert main(["--date", "2026-10-06", "--runs-dir", str(tmp_path)]) == 2
