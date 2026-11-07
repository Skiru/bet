"""One event under two market names prints once (audit 2026-11-07,
epochs.SAME_EVENT_DEDUP_FROM_UTC; bet.sofa.leg_identity)."""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import leg_identity as li
from scripts.sofa.build_coupon import assemble

MATCH = "Raith Rovers - Dunfermline Athletic"
BOARD = ("Raith Rovers", "Dunfermline")


def _fb(market: str, subject: str = "", line: float = 0.5,
        direction: str = "OVER", odds: float = 1.5, conf: float = 0.7,
        eid: int = 1, **extra: Any) -> dict[str, Any]:
    return {"sport": "football", "sofascore_event_id": eid,
            "group_key": f"sofa:{eid}", "match": MATCH, "market": market,
            "subject": subject, "line": line, "direction": direction,
            "offered_odds": odds, "confidence": conf,
            "kickoff_utc": "2026-11-08T15:00:00Z", **extra}


def _sp(sport: str, family: str, side: str, line: float | None = None,
        subject: str = "", period: int = 0, odds: float = 1.3,
        conf: float = 0.75, **extra: Any) -> dict[str, Any]:
    return {"sport": sport, "sofascore_event_id": 2, "group_key": "sofa:2",
            "match": "Alpha - Beta", "family": family, "market": family,
            "side": side, "direction": side, "line": line, "subject": subject,
            "period": period, "odds": odds, "confidence": conf,
            "kickoff_utc": "2026-11-08T18:00:00Z", **extra}


def _same(a: dict[str, Any], b: dict[str, Any], board: Any = None) -> bool:
    ka, kb = li.event_key(a, board), li.event_key(b, board)
    return ka is not None and ka == kb


# --- football: the identities seen on the coupons --------------------------

def test_btts_in_neither_half_is_no_no():
    assert _same(_fb("btts_any_half", direction="UNDER"),
                 _fb("btts_halves", "Nie/Nie"))
    assert not _same(_fb("btts_any_half", direction="OVER"),
                     _fb("btts_halves", "Nie/Nie"))


def test_team_scores_is_team_wins_or_btts_by_board_name():
    # the subject is Superbet's name ("dunfermline"), the match Sofascore's
    away = _fb("goals_for", "dunfermline")
    assert _same(away, _fb("result_or_btts", "2"), BOARD)
    assert not _same(away, _fb("result_or_btts", "1"), BOARD)
    assert _same(_fb("goals_for", "raith rovers"), _fb("result_or_btts", "1"), BOARD)


def test_not_nil_nil_has_four_names():
    legs = [_fb("goals_total"), _fb("result_or_over", "1"),
            _fb("result_or_over", "2"), _fb("btts_or_over")]
    for a, b in itertools.combinations(legs, 2):
        assert _same(a, b)
    assert not _same(_fb("goals_total"), _fb("goals_total", line=1.5))


def test_unrelated_and_unknown_legs_have_no_shared_key():
    assert not _same(_fb("goals_total", line=2.5), _fb("btts_or_over", line=2.5))
    assert li.event_key(_fb("corners_total", line=9.5)) is None
    # a side nobody can tell has no key
    assert li.event_key(_fb("goals_for", "somebody else")) is None
    # a line beyond every path is constant there: no key
    assert li.event_key(_fb("goals_1h_for", "raith rovers", line=7.5), BOARD) is None


def test_dnb_is_not_the_double_chance():
    # same wins, but the draw refunds one and wins the other: not one bet
    assert li.event_key(_fb("draw_no_bet", "1")) is None


# --- the measured sports ------------------------------------------------------

def test_hockey_half_goal_handicap_is_the_double_chance():
    hk = "hockey"
    assert _same(_sp(hk, "handicap", "T1", 0.5), _sp(hk, "double_chance", "1X"))
    assert _same(_sp(hk, "handicap", "T2", -0.5), _sp(hk, "double_chance", "X2"))
    assert _same(_sp(hk, "handicap", "T1", -0.5), _sp(hk, "result_1x2", "T1"))
    assert _same(_sp("hockey", "period_handicap", "T1", 0.5, period=1),
                 _sp("hockey", "period_double_chance", "1X", period=1))
    assert not _same(_sp("hockey", "period_handicap", "T1", 0.5, period=1),
                     _sp("hockey", "period_double_chance", "1X", period=2))
    assert not _same(_sp(hk, "handicap", "T1", 1.5), _sp(hk, "double_chance", "1X"))


def test_basketball_full_game_never_matched():
    # the full-game handicap counts overtime, the 1X2 does not
    assert li.event_key(_sp("basketball", "handicap", "T1", -0.5)) is None
    assert _same(_sp("basketball", "quarter_handicap", "T1", -0.5, period=2),
                 _sp("basketball", "quarter_1x2", "T1", period=2))


def test_volleyball_set_handicap_two_and_a_half_is_wins_a_set():
    assert _same(_sp("volleyball", "set_handicap", "T2", -2.5),
                 _sp("volleyball", "team_wins_set", "YES", subject="T2"))
    assert _same(_sp("volleyball", "set_handicap", "T1", 2.5),
                 _sp("volleyball", "team_wins_set", "YES", subject="T1"))
    assert not _same(_sp("volleyball", "set_handicap", "T2", -1.5),
                     _sp("volleyball", "team_wins_set", "YES", subject="T2"))


def test_cs2_only_when_best_of_three_is_known():
    a = _sp("cs2", "maps_handicap", "T1", 1.5, best_of=3)
    b = _sp("cs2", "team_maps", "OVER", 0.5, subject="Alpha", best_of=3)
    assert _same(a, b)
    assert _same(_sp("cs2", "match_winner", "T2", best_of=3),
                 _sp("cs2", "team_maps", "OVER", 1.5, subject="Beta", best_of=3))
    no_format = {k: v for k, v in a.items() if k != "best_of"}
    assert li.event_key(no_format) is None


# --- dedupe -------------------------------------------------------------------

def test_dedupe_keeps_the_higher_price_then_the_lower_confidence():
    a = _fb("goals_for", "raith rovers", odds=1.28, conf=0.72)
    b = _fb("result_or_btts", "1", odds=1.27, conf=0.73)
    kept, removed = li.dedupe([], [b, a], {1: BOARD})
    assert kept == [a]
    assert removed[0]["market"] == "result_or_btts"
    assert removed[0]["same_event_as"]["market"] == "goals_for"
    c = _fb("btts_any_half", direction="UNDER", odds=1.5, conf=0.62)
    d = _fb("btts_halves", "Nie/Nie", odds=1.5, conf=0.61)
    kept, removed = li.dedupe([], [c, d])
    assert kept == [d] and len(removed) == 1


def test_a_locked_leg_stays_and_its_fresh_twin_goes():
    locked = _fb("btts_halves", "Nie/Nie", odds=1.4, locked=True)
    fresh = _fb("btts_any_half", direction="UNDER", odds=1.6)
    other = _fb("goals_total", line=2.5)
    kept, removed = li.dedupe([locked], [fresh, other])
    assert kept == [other]
    assert removed[0]["market"] == "btts_any_half"


def test_different_matches_never_merge():
    a = _fb("btts_any_half", direction="UNDER", eid=1)
    b = _fb("btts_halves", "Nie/Nie", eid=3)
    kept, removed = li.dedupe([], [a, b])
    assert len(kept) == 2 and not removed


# --- the switch and the coupon -------------------------------------------------

def test_switch_from_2026_11_08():
    on = epochs.same_event_dedup
    assert not on("2026-11-07", datetime(2026, 11, 7, 23, tzinfo=UTC))
    assert on("2026-11-08", datetime(2026, 11, 8, 0, 1, tzinfo=UTC))
    # a rebuild of an earlier day keeps its old print
    assert not on("2026-11-06", datetime(2026, 11, 9, tzinfo=UTC))


def _conf_doc(singles: list[dict[str, Any]]) -> dict[str, Any]:
    return {"profile": "standard", "epoch": "stats_only", "created_at_utc": "x",
            "singles": singles, "legs": singles, "builders": [],
            "removed_by_reads": []}


@pytest.mark.parametrize("active", [False, True])
def test_coupon_prints_one_leg_per_event_only_under_the_switch(active):
    singles = [_fb("btts_any_half", direction="UNDER", odds=1.5, conf=0.62),
               _fb("btts_halves", "Nie/Nie", odds=1.52, conf=0.62),
               _fb("goals_total", line=2.5, odds=1.9, conf=0.7)]
    doc = assemble(_conf_doc(singles), None, [], {}, "now",
                   same_event_active=active, boards={1: BOARD})
    markets = [s["market"] for s in doc["singles"]]
    if active:
        assert sorted(markets) == ["btts_halves", "goals_total"]
        assert [r["market"] for r in doc[li.REMOVED_FIELD]] == ["btts_any_half"]
        assert doc["same_event_dedup"] == {"active": True, "removed": 1}
    else:
        assert len(markets) == 3 and doc[li.REMOVED_FIELD] == []
