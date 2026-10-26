"""Nine more basketball player lines (shadow.PLAYER_V2_MARKETS), read by SHADOW
behind epochs.BASKETBALL_PLAYER_V2_FROM_UTC. Offline, fast.

The golden payload is Superbet's own (tests/sofa/golden/
superbet_basketball_player_v2_2026-10-22.json, fetched pre-match 2026-10-22:
14486087 Philadelphia 76ers - Cleveland Cavaliers, NBA, trimmed to three
players). The operator staked "Beringer - liczba trafionych rzutów wolnych:
powyżej 0.5" on 2026-10-21, a market SHADOW never read.
"""

from __future__ import annotations

import copy
import importlib
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs, leg_relations, player_model, shadow, superbet_names
from bet.sofa import sport_confidence as scf
from bet.sofa.line_evidence import LineEvidence
from bet.sofa.player_model import line_probability, load_appearances
from bet.sofa.shadow import (
    PLAYER_MARKETS,
    PLAYER_V2_MARKETS,
    SPORTS,
    ShadowLine,
    build_player_box,
    grade,
    parse_event,
    player_value,
)
from bet.sofa.superbet import odds_items, split_match_name
from tests.sofa.test_player_model import (
    HOME_ID,
    KO_TS,
    add_game,
    entry,
    make_db,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests/sofa/golden/superbet_basketball_player_v2_2026-10-22.json"
BASKETBALL = SPORTS["basketball"]
ON = datetime(2026, 10, 23, 0, 0, tzinfo=UTC)
V2_FAMILIES = {
    231804: ("player_ft_made", ("freeThrowsMade",)),
    231805: ("player_ft_attempts", ("freeThrowAttempts",)),
    231806: ("player_fg_made", ("fieldGoalsMade",)),
    231807: ("player_fg_attempts", ("fieldGoalAttempts",)),
    231808: ("player_twos_made", ("twoPointsMade",)),
    231809: ("player_twos_attempts", ("twoPointAttempts",)),
    231810: ("player_threes_attempts", ("threePointAttempts",)),
    231811: ("player_fouls", ("personalFouls",)),
    200985: ("player_turnovers", ("turnovers",)),
}


def _event() -> dict[str, Any]:
    (ev,) = json.loads(GOLDEN.read_text(encoding="utf-8"))["events"]
    return dict(ev)


def _parse(player_v2: bool) -> list[ShadowLine]:
    ev = _event()
    t1, t2 = split_match_name(ev["matchName"])
    assert t1 and t2
    return parse_event(odds_items(ev), "basketball", str(ev["eventId"]), t1, t2,
                       True, True, player_v2)


# --- the switch and the map ---------------------------------------------------------


def test_switch_is_on_from_the_next_day() -> None:
    assert epochs.BASKETBALL_PLAYER_V2_FROM_UTC == ON
    assert epochs.BASKETBALL_PLAYER_V2 == "basketball_player_v2"
    assert epochs.basketball_player_v2("2026-10-23", ON)
    assert not epochs.basketball_player_v2("2026-10-22", ON)
    assert not epochs.basketball_player_v2(
        "2026-10-23", datetime(2026, 10, 22, 23, 59, tzinfo=UTC))


def test_the_nine_markets_are_basketball_player_specs_of_one_box_key() -> None:
    assert PLAYER_V2_MARKETS["basketball"] == frozenset(V2_FAMILIES)
    assert not PLAYER_V2_MARKETS["hockey"] and not PLAYER_V2_MARKETS["volleyball"]
    for mid, (family, keys) in V2_FAMILIES.items():
        spec = PLAYER_MARKETS["basketball"][mid]
        assert (spec.family, spec.keys) == (family, keys)
    # one family per id, and no family borrowed from an older market
    old = {s.family for m, s in PLAYER_MARKETS["basketball"].items()
           if m not in V2_FAMILIES}
    assert not old & {f for f, _ in V2_FAMILIES.values()}


# --- SHADOW: off byte-identical, on the nine families paired -------------------------


def test_off_reads_none_of_them_and_the_old_lines_are_unchanged() -> None:
    off = _parse(False)
    assert off and not {ln.market_id for ln in off} & set(V2_FAMILIES)
    on = _parse(True)
    assert [ln for ln in on if ln.market_id not in V2_FAMILIES] == off


def test_on_reads_every_family_with_both_sides_once() -> None:
    lines = _parse(True)
    got: dict[tuple[str, str, float | None], dict[str, float]] = {}
    for ln in lines:
        if ln.market_id in V2_FAMILIES:
            got.setdefault((ln.family, ln.subject, ln.line), {})[ln.side] = ln.odds
    assert {f for f, _, _ in got} == {f for f, _ in V2_FAMILIES.values()}
    assert all(set(sides) == {"OVER", "UNDER"} for sides in got.values())
    assert {s for _, s, _ in got} == {"Anfernee Simons", "Donovan Mitchell",
                                      "Evan Mobley"}
    # Superbet's prices, as fetched
    assert got[("player_ft_made", "Anfernee Simons", 0.5)] == {
        "OVER": 1.92, "UNDER": 1.78}
    assert got[("player_fouls", "Evan Mobley", 3.5)] == {"OVER": 2.07, "UNDER": 1.66}
    assert got[("player_turnovers", "Donovan Mitchell", 2.5)] == {
        "OVER": 1.82, "UNDER": 1.87}
    # a made line is never above the same player's attempted line
    for made, att in (("player_ft_made", "player_ft_attempts"),
                      ("player_fg_made", "player_fg_attempts"),
                      ("player_twos_made", "player_twos_attempts")):
        for (f, s, v) in got:
            if f == made:
                (a,) = [v2 for (f2, s2, v2) in got if f2 == att and s2 == s]
                assert v is not None and a is not None and v <= a


def test_the_markets_still_not_read_stay_unread() -> None:
    # first-quarter player points, double-double, the one-sided "N+" ladder
    assert not {ln.market_id for ln in _parse(True)} & {240717, 233573, 235311}


def test_a_name_other_than_the_ids_own_is_dropped() -> None:
    ev = _event()
    item = next(i for i in ev["odds"] if i["marketId"] == 231811)
    t1, t2 = split_match_name(ev["matchName"])
    assert shadow.parse_line(item, "basketball", "e", t1, t2, player_v2=True)
    wrong = {**item, "marketName": "Zawodnik - liczba fauli (z dogrywką)"}
    assert shadow.parse_line(wrong, "basketball", "e", t1, t2, player_v2=True) is None
    assert shadow.parse_line(item, "basketball", "e", t1, t2) is None


class _Board:
    def events_by_date(self, start: datetime, end: datetime, offer_state: str
                       ) -> list[dict[str, Any]]:
        ev = _event()
        return [{"sportId": 4, "eventId": ev["eventId"], "matchName": ev["matchName"],
                 "utcDate": "2026-10-23T23:00:00Z", "tournamentId": 164}]

    def event_odds(self, event_id: str) -> dict[str, Any]:
        return {"odds": _event()["odds"]}

    def _get_json(self, path: str) -> dict[str, Any]:
        return {"data": {"tournaments": []}}


def _snapshot(tmp_path: Path) -> dict[str, Any]:
    if "scripts.sofa.run_shadow" in sys.modules:
        run_shadow = sys.modules["scripts.sofa.run_shadow"]
    else:
        run_shadow = importlib.import_module("scripts.sofa.run_shadow")
    at = datetime(2026, 10, 23, 20, tzinfo=UTC)
    run_shadow.snapshot("2026-10-23", _Board(), str(tmp_path), at=at)
    path = tmp_path / "shadow" / "basketball" / "2026-10-23" / "snapshots.jsonl"
    (rec,) = [json.loads(x) for x in path.read_text().splitlines()]
    return dict(rec)


def test_snapshot_off_is_what_it_was(tmp_path: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "BASKETBALL_PLAYER_V2_FROM_UTC", None)
    rec = _snapshot(tmp_path)
    assert "player_v2_rule" not in rec
    assert rec["lines"] == [ln.as_dict() for ln in _parse(False)]


def test_snapshot_on_adds_the_lines_and_the_rule(tmp_path: Path) -> None:
    rec = _snapshot(tmp_path)
    assert rec["player_v2_rule"] == "basketball_player_v2"
    assert rec["lines"] == [ln.as_dict() for ln in _parse(True)]
    assert {ln["market_id"] for ln in rec["lines"]} >= set(V2_FAMILIES)


# --- SHADOW_SETTLE: graded from the player's own row ---------------------------------


def _player(name: str, stats: dict[str, Any]) -> dict[str, Any]:
    return {"player": {"name": name}, "statistics": {"secondsPlayed": 1800, **stats}}


def _lineups() -> dict[str, Any]:
    beringer = {"points": 9, "twoPointsMade": 3, "twoPointAttempts": 5,
                "threePointsMade": 0, "threePointAttempts": 1,
                "freeThrowsMade": 3, "freeThrowAttempts": 4, "fieldGoalsMade": 3,
                "fieldGoalAttempts": 6, "personalFouls": 4, "turnovers": 0}
    return {
        "home": {"players": [_player("Joan Beringer", beringer),
                             _player("Home Other", {"points": 11}),
                             {"player": {"name": "Home Bench"}, "statistics": {}}]},
        "away": {"players": [_player("Away One", {"points": 15})]},
    }


def _detail(home: int, away: int) -> dict[str, Any]:
    return {"status": {"type": "finished", "description": "Ended"}, "winnerCode": 1,
            "homeScore": {"current": home}, "awayScore": {"current": away}}


@pytest.mark.parametrize(
    ("mid", "line", "actual", "over"),
    [
        (231804, 0.5, 3.0, "WIN"),   # the operator's "powyżej 0.5"
        (231805, 4.5, 4.0, "LOSS"),
        (231806, 2.5, 3.0, "WIN"),
        (231807, 6.5, 6.0, "LOSS"),
        (231808, 3.5, 3.0, "LOSS"),
        (231809, 4.5, 5.0, "WIN"),
        (231810, 0.5, 1.0, "WIN"),
        (231811, 3.5, 4.0, "WIN"),
        (200985, 0.5, 0.0, "LOSS"),
    ],
)
def test_the_grade_reads_the_players_own_key(mid: int, line: float, actual: float,
                                             over: str) -> None:
    box = build_player_box(_lineups(), _detail(20, 15), BASKETBALL)
    assert box is not None and box.ok
    ln = ShadowLine("e", mid, V2_FAMILIES[mid][0], 0, "Beringer, Joan", line,
                    "OVER", 1.9)
    assert player_value(ln, box, BASKETBALL) == actual
    assert grade(ln, actual) == over
    under = ShadowLine("e", mid, V2_FAMILIES[mid][0], 0, "Beringer, Joan", line,
                       "UNDER", 1.9)
    assert grade(under, actual) == ("LOSS" if over == "WIN" else "WIN")


def test_a_missing_key_is_no_stat_and_a_bench_player_dnp() -> None:
    box = build_player_box(_lineups(), _detail(20, 15), BASKETBALL)
    assert box is not None
    fouls = ShadowLine("e", 231811, "player_fouls", 0, "Other, Home", 2.5, "OVER", 1.9)
    assert player_value(fouls, box, BASKETBALL) == "NO_STAT"
    bench = ShadowLine("e", 231811, "player_fouls", 0, "Bench, Home", 2.5, "OVER", 1.9)
    assert player_value(bench, box, BASKETBALL) == "DNP"


# --- the player model prices them as any count family --------------------------------


def test_the_count_model_prices_fouls_from_his_own_minutes(tmp_path: Path) -> None:
    conn: sqlite3.Connection = make_db(tmp_path / "db.sqlite")
    for i in range(12):
        add_game(conn, 500 + i, KO_TS - (i + 1) * 86400,
                 [entry(HOME_ID, 1, "Joan Beringer",
                        {"secondsPlayed": 1500, "personalFouls": 3 + (i % 2),
                         "freeThrowsMade": i % 3}, "C"),
                  entry(HOME_ID, 2, "Al Jones",
                        {"secondsPlayed": 1500, "personalFouls": 2,
                         "freeThrowsMade": 1}, "G")],
                 slug="basketball")
    conn.commit()
    apps = load_appearances(conn, "basketball", [HOME_ID], KO_TS - 60, None)

    def p(mid: int, value: float, side: str) -> player_model.PlayerProbability:
        return line_probability(ShadowLine("1", mid, "x", 0, "Beringer, Joan", value,
                                           side, 1.9), "basketball", apps)

    over, under = p(231811, 2.5, "OVER"), p(231811, 2.5, "UNDER")
    assert over.n == 12 and over.mean is not None and 3.0 < over.mean < 3.5
    assert over.p is not None and under.p is not None
    assert over.p + under.p == pytest.approx(1.0)
    assert over.p > 0.5
    ft = p(231804, 0.5, "OVER")
    assert ft.p is not None and ft.mean is not None and 0.5 < ft.mean < 1.5


# --- SPORT_CONFIDENCE: a leg, but NO_LINE_EVIDENCE until its own lines decide --------


def test_sport_confidence_takes_them_only_under_the_evidence_and_refuses_them(
        ) -> None:
    rsc = importlib.import_module("scripts.sofa.run_sport_confidence")
    for mid, (family, _) in V2_FAMILIES.items():
        assert scf.family_of("basketball", mid, family, extended=True) == family
        assert scf.family_of("basketball", mid, family) is None
    calibration = scf.SportCalibration.load(scf.calibration_path_for("2026-10-23"))
    assert calibration is not None
    live = LineEvidence.load(v2=True, bucket_deff=True)
    # the installed file gains settled lines every morning (10-26: free
    # throws made); the families' own keys taken out = none settled yet
    keys = {scf.curve_key(f, side) for f, _ in V2_FAMILIES.values()
            for side in ("OVER", "UNDER")}
    doc = copy.deepcopy(live.doc)
    bb = (doc.get("keys") or {}).get("basketball") or {}
    for k in keys:
        bb.pop(k, None)
    bare = LineEvidence(doc, live.v2, live.bucket_deff)
    for family, _ in V2_FAMILIES.values():
        for side in ("OVER", "UNDER"):
            for p in (0.55, 0.75, 0.95):
                # no history curve and no settled line of the family: refused,
                # whatever p - never a pooled offset or another family's curve
                conf, offset, cap, why = rsc.read_confidence(
                    calibration, bare, "basketball", family, side, p, 1.5)
                assert (conf, offset, cap, why) == (None, 0.0, None,
                                                    "NO_LINE_EVIDENCE")
                # with the installed lines: refused, or read from its own key
                conf, _, _, why = rsc.read_confidence(
                    calibration, live, "basketball", family, side, p, 1.5)
                assert why == "NO_LINE_EVIDENCE" or (
                    conf is not None and conf.calibrated_on
                    == f"sb:basketball:{scf.curve_key(family, side)}")


# --- the screen's words and the relations ---------------------------------------------


def _leg(mid: int, family: str, line: float, side: str = "OVER",
         subject: str = "Joan Beringer") -> dict[str, Any]:
    return {"sport": "basketball", "market_id": mid, "family": family, "period": 0,
            "subject": subject, "line": line, "side": side,
            "team1": "Miami Heat", "team2": "Minnesota Timberwolves"}


def test_superbets_words_name_the_leg() -> None:
    assert superbet_names.names(_leg(231804, "player_ft_made", 0.5)) == (
        "Zawodnik - liczba trafionych rzutów wolnych (z dogrywką)",
        "Joan Beringer - powyżej 0.5")
    assert superbet_names.names(_leg(231811, "player_fouls", 2.5, "UNDER")) == (
        "Zawodnik - liczba fauli osobistych (z dogrywką)",
        "Joan Beringer - poniżej 2.5")


def test_shots_of_one_kind_are_linked_and_fouls_are_not() -> None:
    rel = leg_relations.relate
    ft_made = _leg(231804, "player_ft_made", 0.5)
    assert rel(ft_made, _leg(231805, "player_ft_attempts", 1.5)).label == "DEPENDENT"
    assert rel(ft_made, _leg(233565, "player_points", 12.5)).label == "DEPENDENT"
    # a free throw is not a field goal
    assert rel(ft_made, _leg(231806, "player_fg_made", 3.5)).label == \
        "INDEPENDENT_ASSUMED"
    threes = _leg(233568, "player_threes", 1.5)
    assert rel(_leg(231810, "player_threes_attempts", 4.5), threes).label == "DEPENDENT"
    assert rel(_leg(231806, "player_fg_made", 3.5), threes).label == "DEPENDENT"
    assert rel(_leg(231811, "player_fouls", 2.5),
               _leg(233565, "player_points", 12.5)).label == "INDEPENDENT_ASSUMED"
    # a made shot feeds the score, a foul does not
    total = {"sport": "basketball", "market_id": 753, "family": "total", "period": 0,
             "subject": "", "line": 220.5, "side": "OVER"}
    assert rel(ft_made, total).label == "DEPENDENT"
    assert rel(_leg(231811, "player_fouls", 2.5), total).label == "INDEPENDENT_ASSUMED"
