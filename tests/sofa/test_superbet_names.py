"""bet.sofa.superbet_names - a leg named as Superbet's screen names it.

The case behind it (2026-10-15, Tampa Bay - Seattle): a chat slip said
"Seattle +1.5 w 3. tercji" (period_handicap) and the bet placed was the
market beside it, "3. tercja - Seattle Kraken - liczba goli: Poniżej 1.5".
The two must never read alike.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bet.sofa import superbet_names as sn

MATCH = "Tampa Bay Lightning - Seattle Kraken"


def _hockey(market_id: int, family: str, period: int, side: str,
            line: float | None, subject: str = "") -> dict[str, Any]:
    return {"sport": "hockey", "market_id": market_id, "family": family,
            "market": family, "period": period, "subject": subject,
            "line": line, "side": side, "direction": side, "match": MATCH}


def test_period_handicap_and_period_team_total_never_read_alike() -> None:
    hcp = sn.names(_hockey(678, "period_handicap", 3, "T2", -1.5))
    goals = sn.names(_hockey(638, "period_team_total", 3, "UNDER", 1.5, "T2"))
    assert hcp == ("3. tercja - handicap", "Seattle Kraken (1.5)")
    assert goals == ("3. tercja - Seattle Kraken - liczba goli", "poniżej 1.5")
    # team 1's period goals: Superbet writes no dash before "liczba goli"
    assert sn.names(_hockey(674, "period_team_total", 3, "UNDER", 2.5, "T1")) == (
        "3. tercja - Tampa Bay Lightning liczba goli", "poniżej 2.5")
    # team 1's own handicap is the line, team 2's its negation
    assert sn.names(_hockey(678, "period_handicap", 1, "T1", -1.5)) == (
        "1. tercja - handicap", "Tampa Bay Lightning (-1.5)")


def test_hockey_codes_name_the_team() -> None:
    assert sn.names(_hockey(630, "winner", 0, "T1", None)) == (
        "Zwycięzca (z dogrywką i rzutami karnymi)", "1 (Tampa Bay Lightning)")
    assert sn.names(_hockey(660, "period_1x2", 2, "DRAW", None)) == (
        "X.tercja - zwycięzca", "2.tercja - X (remis)")
    assert sn.names(_hockey(662, "period_dnb", 3, "T2", None)) == (
        "X.tercja - zakład bez remisu", "3.tercja - Seattle Kraken")
    assert sn.names(_hockey(616, "period_double_chance", 1, "X2", None)) == (
        "1. tercja - podwójna szansa", "X2 (remis lub Seattle Kraken)")


def test_hockey_player_market_uses_shadows_own_name() -> None:
    leg = _hockey(232584, "player_pp_points", 0, "UNDER", 0.5, "Brandon Montour")
    assert sn.names(leg) == (
        "Zawodnik - liczba punktów w przewadze (z dogrywką)",
        "Brandon Montour - poniżej 0.5")


def test_basketball_double_chance_pair_reads_its_base_market() -> None:
    leg = {"sport": "basketball", "market_id": -101, "family": "double_chance",
           "period": 0, "subject": "", "line": None, "side": "1X",
           "match": "Barcelona - Olympiacos"}
    assert sn.names(leg) == ("Podwójna szansa", "1X (Barcelona lub remis)")
    quarter = {**leg, "market_id": 200795, "family": "quarter_team_total",
               "period": 4, "side": "OVER", "line": 21.5}
    assert sn.names(quarter) == ("4. kwarta - Olympiacos liczba punktów",
                                 "powyżej 21.5")


def test_volleyball_set_markets() -> None:
    base = {"sport": "volleyball", "period": 0, "subject": "T2",
            "match": "Wrocław (K) - Chemik Police (K)"}
    assert sn.names({**base, "market_id": -14, "family": "team_sets_exact",
                     "line": 2.0, "side": "NO"}) == (
        "Chemik Police (K) wygra dokładnie 2 sety", "Nie")
    assert sn.names({**base, "market_id": -15, "family": "sets_count",
                     "line": None, "side": "SETS=4"}) == (
        "Dokładna liczba setów", "4")
    assert sn.names({**base, "market_id": 744, "family": "set_winner",
                     "period": 2, "line": None, "side": "T1"}) == (
        "X set - zwycięzca", "2. set - Wrocław (K)")


def test_cs2_by_family_and_map() -> None:
    leg = {"sport": "cs2", "family": "map_rounds_handicap", "map_nr": 2,
           "period": 2, "subject": "", "line": 3.5, "side": "T2",
           "match": "9z - Aurora"}
    assert sn.names(leg) == ("2. mapa - Handicap rund (z dogrywką)", "Aurora (-3.5)")
    team = {**leg, "family": "team_maps", "map_nr": 0, "subject": "Aurora",
            "line": 0.5, "side": "OVER"}
    assert sn.names(team) == ("Aurora liczba map", "powyżej 0.5")


def test_football_subject_takes_superbets_spelling_from_the_board() -> None:
    leg = {"sport": "football", "market": "corners_1h_for",
           "subject": "atletico madryt", "line": 4.5, "direction": "UNDER",
           "match": "Atlético Madrid - Manchester United"}
    sides = ("Atlético Madryt", "Manchester United")
    assert sn.names(leg, sides) == (
        "1. połowa - Atlético Madryt liczba rzutów rożnych", "poniżej 4.5")
    goals = {**leg, "market": "goals_1h_for"}
    assert sn.names(goals, sides)[0] == "1.połowa - Atlético Madryt - liczba goli"


def test_football_result_markets_both_directions() -> None:
    sides = ("Preston Lions", "Wollongong Wolves")
    base = {"sport": "football", "line": 0.5,
            "match": "Preston Lions FC - Wollongong Wolves"}
    dc = {**base, "market": "double_chance", "subject": "1X"}
    assert sn.names({**dc, "direction": "OVER"}, sides) == (
        "Podwójna szansa", "1X (Preston Lions lub remis)")
    # the double chance's UNDER is the 1X2 outcome it leaves out
    assert sn.names({**dc, "direction": "UNDER"}, sides) == (
        "Mecz", "2 (Wollongong Wolves)")
    one = {**base, "market": "result_1x2", "subject": "1"}
    assert sn.names({**one, "direction": "OVER"}, sides) == (
        "Mecz", "1 (Preston Lions)")
    assert sn.names({**one, "direction": "UNDER"}, sides) == (
        "Podwójna szansa", "X2 (remis lub Wollongong Wolves)")
    dnb = {**base, "market": "draw_no_bet", "subject": "1"}
    assert sn.names({**dnb, "direction": "UNDER"}, sides) == (
        "Zakład bez remisu", "Wollongong Wolves")


def test_football_player_and_score_markets() -> None:
    player = {"sport": "football", "market": "player_left_foot_shots_for",
              "subject": "Quinones, Julian", "line": 0.5, "direction": "OVER",
              "match": "A - B"}
    assert sn.names(player) == ("Zawodnik - liczba strzałów lewą nogą",
                                "Quinones, Julian - powyżej 0.5")
    score = {"sport": "football", "market": "result_or_over", "subject": "2",
             "line": 2.5, "direction": "OVER", "match": "Home FC - Away FC"}
    assert sn.names(score) == (
        "Mecz lub liczba goli: Away FC lub powyżej 2.5", "Tak")


def test_tennis_winner_set_and_score() -> None:
    sides = ("Han Shi", "Leylah Fernandez")
    base = {"sport": "tennis", "line": 0.5, "match": "Han Shi - Leylah Fernandez"}
    assert sn.names({**base, "market": "match_won_for", "subject": "Han Shi",
                     "direction": "UNDER"}, sides) == ("Zwycięzca",
                                                       "2 (Leylah Fernandez)")
    assert sn.names({**base, "market": "set2_won_for", "subject": "Han Shi",
                     "direction": "OVER"}, sides) == ("X. set - zwycięzca",
                                                      "2. set - Han Shi")
    # a score read from the second player is Superbet's score flipped
    assert sn.names({**base, "market": "set_score",
                     "subject": "Leylah Fernandez 2:0", "direction": "OVER"},
                    sides) == ("Dokładny wynik", "0:2 (Leylah Fernandez 2:0)")
    games = {**base, "market": "games_won_set1_for", "subject": "leylah fernandez",
             "line": 4.5, "direction": "UNDER"}
    assert sn.names(games, sides) == ("1. set - Leylah Fernandez liczba gemów",
                                      "poniżej 4.5")


def test_unknown_market_is_not_guessed() -> None:
    assert sn.names({"sport": "football", "market": "both_over_goals",
                     "subject": "", "line": 0.5, "direction": "OVER",
                     "match": "A - B"}) is None
    assert sn.names(_hockey(999999, "mystery", 0, "OVER", 1.5)) is None


def test_annotate_names_builder_legs_from_their_builder_and_drops_stale() -> None:
    doc: dict[str, Any] = {
        "singles": [{"sport": "football", "sofascore_event_id": 7,
                     "market": "both_over_goals", "subject": "", "line": 0.5,
                     "direction": "OVER", "match": "A FC - B FC",
                     sn.FIELD_MARKET: "stale", sn.FIELD_SELECTION: "stale"}],
        "builders": [{"sofascore_event_id": 7, "match": "A FC - B FC",
                      "legs": [{"market": "goals_for", "subject": "b",
                                "line": 0.5, "direction": "OVER"}]}],
    }
    assert sn.annotate(doc, {7: ("A", "B")}) == 1
    assert sn.FIELD_MARKET not in doc["singles"][0]
    leg = doc["builders"][0]["legs"][0]
    assert (leg[sn.FIELD_MARKET], leg[sn.FIELD_SELECTION]) == (
        "B - liczba goli", "powyżej 0.5")
    assert sn.label(leg) == "B - liczba goli: powyżej 0.5"


def test_board_sides_joins_fixtures_to_the_board(tmp_path: Path) -> None:
    (tmp_path / "01_board.json").write_text(json.dumps([
        {"superbet_event_id": "15", "side_a": "Atlético Madryt",
         "side_b": "Manchester United"}]), encoding="utf-8")
    (tmp_path / "02_fixtures.json").write_text(json.dumps([
        {"sofascore_event_id": 7, "superbet_event_ids": ["15"]}]),
        encoding="utf-8")
    assert sn.board_sides(tmp_path) == {7: ("Atlético Madryt", "Manchester United")}
    assert sn.board_sides(tmp_path / "missing") == {}


def test_pdf_cell_bolds_the_selection() -> None:
    from scripts.sofa.build_coupon_pdf import market_cell

    leg = {sn.FIELD_MARKET: "3. tercja - Seattle Kraken - liczba goli",
           sn.FIELD_SELECTION: "poniżej 1.5"}
    assert market_cell(leg, "", "x") == (
        "3. tercja - Seattle Kraken - liczba goli: <b>poniżej 1.5</b>")
    assert market_cell({"display_market": "a & b"}, "", "x") == "a &amp; b"
    assert market_cell({}, "", "fallback") == "fallback"


def test_html_view_uses_the_superbet_label() -> None:
    from bet.sofa.coupon_html import market_label

    assert market_label({sn.FIELD_MARKET: "Liczba goli",
                         sn.FIELD_SELECTION: "powyżej 2.5",
                         "display_market": "old"}) == "Liczba goli: powyżej 2.5"
    assert market_label({"display_market": "old"}) == "old"


def test_peer_note_and_ladder_rungs_take_their_singles_names() -> None:
    def leg(line: float, pos: int) -> dict[str, Any]:
        return {**_hockey(649, "period_total", 1, "UNDER", line),
                "sofascore_event_id": 9, "position": pos}
    a, b = leg(2.5, 1), leg(3.5, 2)
    a["peer"] = {"preferred": False, "peers": 1, "d_confidence": -0.01,
                 "band": [1.0, 1.1],
                 "best": {"position": 2, "market": "period_total", "subject": "",
                          "line": 3.5, "direction": "UNDER", "period": 1,
                          "sport": "hockey", "odds": 1.1}}
    doc: dict[str, Any] = {"singles": [a, b], "ladders": [{
        "group_key": "sofa:9", "ladder_no": 1, "n_rungs": 2, "label": "period_total",
        "rungs": [{"position": p, "market": "period_total", "subject": "",
                   "line": ln, "direction": "UNDER", "period": 1, "sport": "hockey"}
                  for p, ln in ((1, 2.5), (2, 3.5))]}]}
    sn.annotate(doc, {})
    from bet.sofa.peer_choice import label as peer_label
    assert "1. tercja - liczba goli: poniżej 3.5" in peer_label(a)
    lad = doc["ladders"][0]
    assert lad[sn.FIELD_MARKET] == "1. tercja - liczba goli"
    assert [r[sn.FIELD_SELECTION] for r in lad["rungs"]] == ["poniżej 2.5",
                                                             "poniżej 3.5"]
    from scripts.sofa.coupon_structure_pdf import ladder_header
    header = ladder_header(lad)
    assert "1. tercja - liczba goli" in header and "poniżej 3.5 (#2)" in header
