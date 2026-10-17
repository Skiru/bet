"""Defects found by the line-by-line re-grade of 2026-10-16 (2026-10-17).

1. A card shown to a player on the bench counted toward card points -
   Superbet's komunikat 06/2022 does not count it (Leganés - Córdoba,
   Rapid Wien - Hartberg: 6 rows flipped). SETTLE and regrade now read the
   incidents without such cards; samples keep them.
2. A half's goals read off an /event Sofascore rewrote after the match
   (IFK Stocksund - Enköpings SK, period1 0-0 against HT 0-2): refused when
   settling, so a regrade leaves the correct row alone.
3. Basketball / hockey player names: football's token and surname rules.
4. A basketball game Ended with a decided score and no winnerCode (Shumen -
   Botev 87-84): graded by SHADOW_SETTLE, still refused by the history.
5. A CS2 nickname Superbet extends ("MartinezSa" / "martinez").
"""

from __future__ import annotations

import json
from typing import Any

from bet.sofa.contracts import GapReason
from bet.sofa.cs2 import MapResult
from bet.sofa.metrics import (
    calculate_cards_points,
    drop_bench_cards,
    extract_metric,
    half_time_disagrees,
)
from bet.sofa.shadow import SPORTS, PlayerBox, ShadowLine, build_result, player_value
from scripts.sofa.regrade_settled import grade_live


def _card(pid: int, home: bool, time: int, cls: str = "yellow") -> dict[str, Any]:
    return {"incidentType": "card", "incidentClass": cls, "player": {"id": pid},
            "isHome": home, "time": time}


def _sub(p_in: int, p_out: int, home: bool, time: int) -> dict[str, Any]:
    return {"incidentType": "substitution", "playerIn": {"id": p_in},
            "playerOut": {"id": p_out}, "isHome": home, "time": time}


def _lineups(**players: tuple[bool, int | None]) -> dict[str, Any]:
    """pid name -> (substitute, minutesPlayed), all on the home side."""
    rows = []
    for name, (sub, minutes) in players.items():
        stats = {} if minutes is None else {"minutesPlayed": minutes}
        rows.append({"player": {"id": int(name.removeprefix("p"))},
                     "substitute": sub, "statistics": stats})
    return {"home": {"players": rows}, "away": {"players": []}}


LINEUPS = _lineups(p1=(False, 90), p2=(True, None), p3=(True, 30), p4=(False, 60))
INCIDENTS = {"incidents": [
    _card(1, True, 20),          # starter on the pitch: counts
    _card(2, True, -5),          # unused substitute (Millán, Marić): dropped
    _card(3, True, 50),          # booked before coming on at 60: dropped
    _card(3, True, 80),          # booked after coming on: counts
    _card(4, True, 75),          # booked after going off at 60: dropped
    _sub(3, 4, True, 60),
]}


def test_bench_cards_are_dropped_and_pitch_cards_kept() -> None:
    kept = drop_bench_cards(INCIDENTS, LINEUPS)
    assert kept is not None
    cards = [(i["player"]["id"], i["time"]) for i in kept["incidents"]
             if i["incidentType"] == "card"]
    assert cards == [(1, 20), (3, 80)]
    assert calculate_cards_points(INCIDENTS) == (5.0, 0.0)
    assert calculate_cards_points(kept) == (2.0, 0.0)


def test_no_lineups_or_no_substitution_feed_keeps_every_card() -> None:
    assert drop_bench_cards(INCIDENTS, None) is INCIDENTS
    no_subs = {"incidents": [_card(2, True, -5)]}
    # without substitutions in the feed "never came on" cannot be proven
    assert drop_bench_cards(no_subs, LINEUPS) is no_subs
    unknown = {"incidents": [_card(99, True, 10), _sub(3, 4, True, 60)]}
    assert drop_bench_cards(unknown, LINEUPS) is unknown


def test_regrade_reads_card_rows_like_settle() -> None:
    event = {"status": {"type": "finished", "code": 100},
             "homeScore": {"current": 1, "normaltime": 1, "period1": 1, "period2": 0},
             "awayScore": {"current": 0, "normaltime": 0, "period1": 0, "period2": 0}}
    row = {"market": "cards_points_total", "sport": "football", "subject": "",
           "line": 2.5, "direction": "OVER"}
    fixture = {"home_name": "A", "away_name": "B"}
    with_bench = grade_live(row, event, fixture, None, json.dumps(INCIDENTS))
    without = grade_live(row, event, fixture, None, json.dumps(INCIDENTS),
                         json.dumps(LINEUPS))
    assert with_bench == (5.0, "WIN")
    assert without == (2.0, "LOSS")


STOCKSUND = {
    "status": {"type": "finished", "code": 100},
    "homeScore": {"current": 1, "normaltime": 1, "period1": 0, "period2": 1},
    "awayScore": {"current": 3, "normaltime": 3, "period1": 0, "period2": 3},
}
STOCKSUND_INC = {"incidents": [
    {"incidentType": "period", "text": "HT", "homeScore": 0, "awayScore": 2},
    {"incidentType": "goal", "time": 35, "homeScore": 0, "awayScore": 1},
]}


def test_half_rewritten_after_the_match_is_refused_when_settling() -> None:
    assert half_time_disagrees(STOCKSUND, STOCKSUND_INC)
    for metric in ("goals_1h_total", "goals_2h_total"):
        assert extract_metric(metric, "football", {}, STOCKSUND_INC, STOCKSUND,
                              True, settling=True) is GapReason.INTERNAL_INCONSISTENT
        # samples keep reading the listing as before
        assert extract_metric(metric, "football", {}, STOCKSUND_INC, STOCKSUND,
                              True) == (0.0 if metric == "goals_1h_total" else 4.0)
    agreeing = {"incidents": [{"incidentType": "period", "text": "HT",
                               "homeScore": 0, "awayScore": 0}]}
    assert not half_time_disagrees(STOCKSUND, agreeing)


BASKETBALL = SPORTS["basketball"]


def test_basketball_player_found_by_surname_and_tokens() -> None:
    box = PlayerBox({
        "jean claudio montero": {"secondsPlayed": 1500, "points": 14},
        "mouhamet rassoul diouf": {"secondsPlayed": 900, "points": 6},
        "someone else": {"secondsPlayed": 900, "points": 2},
    }, ok=True)

    def line(name: str) -> ShadowLine:
        return ShadowLine("1", 233565, "player_points", 0, name, 10.5, "OVER", 1.9)

    assert player_value(line("Montero, Jean"), box, BASKETBALL) == 14.0
    assert player_value(line("Mouhamet Diouf"), box, BASKETBALL) == 6.0
    assert player_value(line("Nobody Here"), box, BASKETBALL) == "UNMATCHED"
    jr = PlayerBox({"derrick samuel alston jr": {"secondsPlayed": 895, "points": 8},
                    "olek balcerowski": {"secondsPlayed": 600, "points": 5}}, ok=True)
    assert player_value(line("Alston Jr., Derrick"), jr, BASKETBALL) == 8.0
    # a nickname is never guessed
    assert player_value(line("Balcerowski, Aleksander"), jr, BASKETBALL) == "UNMATCHED"


def test_missing_winner_code_graded_by_settle_only() -> None:
    # 16923354 Shumen - Botev, 2026-10-16: Ended 87-84, winnerCode null
    periods_h, periods_a = (20, 25, 22, 20), (21, 20, 23, 20)
    home = {"current": 87, "normaltime": 87,
            **{f"period{i + 1}": v for i, v in enumerate(periods_h)}}
    away = {"current": 84, "normaltime": 84,
            **{f"period{i + 1}": v for i, v in enumerate(periods_a)}}
    detail = {"status": {"type": "finished", "description": "Ended"},
              "winnerCode": None, "homeScore": home, "awayScore": away}
    assert build_result(detail, BASKETBALL, True) is None  # history unchanged
    r = build_result(detail, BASKETBALL, True, allow_final_only=True)
    assert r is not None and r.winner == "T1" and not r.overtime
    level = {**detail, "homeScore": {**home, "current": 84, "normaltime": 84,
                                     "period4": 17}}
    assert build_result(level, BASKETBALL, True, allow_final_only=True) is None


def test_cs2_extended_nickname() -> None:
    mp = MapResult(13, 10, {("T2", "martinez"): {"kills": 17},
                            ("T2", "susp"): {"kills": 12},
                            ("T1", "rez"): {"kills": 20}})
    assert mp.player("MartinezSa") == {"kills": 17}
    assert mp.player("martinez") == {"kills": 17}
    assert mp.player("rezzz") is None  # "rez" is shorter than the prefix floor
    assert mp.player("susp") == {"kills": 12}
