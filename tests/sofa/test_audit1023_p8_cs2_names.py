"""Coverage audit 2026-10-23 P8 (B9), CS2 part, under
epochs.NAME_RULES_1023_FROM_UTC: "prospect" is the roster marker "prospects"
(Privateer - Inner Circle Prospects, 10-22, Sofascore's "Inner Circle
Prospect"), and the engine finds a nickname by prefix as the settlement does
(cs2.MapResult.player: "MartinezSa" for "martinez")."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bet.sofa import cs2, epochs
from bet.sofa import cs2_engine as eng
from bet.sofa.resolve import NAME_MATCH_THRESHOLD

KICK = datetime(2026, 10, 24, 15, tzinfo=UTC)


def test_prospect_is_the_prospects_marker_only_under_the_rule() -> None:
    a, b = "inner circle prospects", "inner circle prospect"
    assert cs2.esports_score(a, b) == 0.0
    assert cs2.esports_score(a, b, True) > NAME_MATCH_THRESHOLD
    # under the rule the singular is a roster marker: never the main roster
    assert cs2.esports_score("inner circle", b, True) == 0.0
    assert cs2.esports_score("cybershoke prospects", "cybershoke prospects",
                             True) == 100.0


def test_pick_event_finds_the_prospect_series_only_under_the_rule() -> None:
    ev = {"id": 7, "startTimestamp": int(KICK.timestamp()),
          "homeTeam": {"name": "Privateer"},
          "awayTeam": {"name": "Inner Circle Prospect"},
          "tournament": {"category": {"name": "Counter Strike"}}}
    assert cs2.pick_event([ev], "Privateer", "Inner Circle Prospects", KICK) is None
    hit = cs2.pick_event([ev], "Privateer", "Inner Circle Prospects", KICK, True)
    assert hit is not None and hit != "AMBIGUOUS" and hit[0]["id"] == 7 and hit[1]


def test_settle_reads_the_rule_by_the_offered_day(monkeypatch: pytest.MonkeyPatch
                                                  ) -> None:
    from scripts.sofa import settle_cs2 as sc

    monkeypatch.setattr(epochs, "NAME_RULES_1023_FROM_UTC",
                        datetime(2026, 10, 24, tzinfo=UTC))
    detail = {"homeTeam": {"name": "Privateer"},
              "awayTeam": {"name": "Inner Circle Prospect"}}
    for kick, want in (("2026-10-23T15:00:00Z", None), ("2026-10-24T15:00:00Z", True)):
        ev = cs2.SnapshotEvent("1", "x", "Privateer", "Inner Circle Prospects",
                               kick, None)
        assert sc.pinned_orientation({}, detail, ev) is want


def _row(eid: int, nicks: dict[int, str]) -> eng.MapRow:
    players = tuple((1, pid, cs2.esports_name(n), (("kills", 20),))
                    for pid, n in nicks.items()) + tuple(
        (2, 100 + i, f"opp{i}", (("kills", 15),)) for i in range(5))
    return eng.MapRow(eid, eid, 1, 1, 2, 13, 9, True, players)


def test_the_engine_finds_a_nickname_by_prefix_only_under_the_rule() -> None:
    hist = [_row(i, {11: "martinez", 12: "s1", 13: "zont1x", 14: "b1t", 15: "jl"})
            for i in range(10)]
    assert eng.player_id(hist, 1, "MartinezSa") is None
    assert eng.player_id(hist, 1, "MartinezSa", True) == 11
    assert eng.player_id(hist, 1, "martinez", True) == 11  # exact first
    assert eng.player_id(hist, 1, "s1mple", True) is None  # "s1" under 5 letters
    assert len(eng.player_values(hist, 1, "MartinezSa", "kills", True)) == 10
    line = cs2.Cs2Line("e", "player_kills", 1, "MartinezSa", 19.5, "OVER", 1.8)
    ratings = eng.build_ratings(hist)
    assert eng.model_probability(line, 1, 2, "a", "b", 3, hist, ratings,
                                 True) is None
    assert eng.model_probability(line, 1, 2, "a", "b", 3, hist, ratings, True,
                                 name_rules=True) is not None


def test_two_players_fitting_the_prefix_are_no_one() -> None:
    hist = [_row(i, {11: "martinez", 12: "martinezsan", 13: "a", 14: "b", 15: "c"})
            for i in range(10)]
    assert eng.player_id(hist, 1, "martinezs", True) is None


def test_the_switch_is_on_from_the_24th() -> None:
    assert not epochs.name_rules_1023("2026-10-23",
                                      datetime(2026, 10, 23, 23, tzinfo=UTC))
    assert epochs.name_rules_1023("2026-10-24", datetime(2026, 10, 24, tzinfo=UTC))


def test_an_exact_nickname_on_either_roster_beats_a_prefix_on_team1() -> None:
    """Review R1 F1: the settlement (cs2.MapResult.player) tries the exact
    nickname on both rosters before any prefix; the engine must price the
    same player - team2's exact "martin", not team1's "martinez"."""
    hist = []
    for i in range(10):
        players = (
            (1, 11, "martinez", (("kills", 30),)),
            *((1, 12 + k, f"teamone{k}", (("kills", 20),)) for k in range(4)),
            (2, 21, "martin", (("kills", 10),)),
            *((2, 22 + k, f"teamtwo{k}", (("kills", 15),)) for k in range(4)),
        )
        hist.append(eng.MapRow(i, i, 1, 1, 2, 13, 9, True, players))
    ratings = eng.build_ratings(hist)
    line = cs2.Cs2Line("e", "player_kills", 1, "martin", 19.5, "OVER", 1.8)
    for rules in (False, True):
        mp = eng.model_probability(line, 1, 2, "a", "b", 3, hist, ratings,
                                   True, name_rules=rules)
        assert mp is not None and mp.p < 0.5  # martin's 10 kills, not 30
    # no exact nickname anywhere: the prefix still finds the one player
    line_sa = cs2.Cs2Line("e", "player_kills", 1, "MartinezSa", 19.5, "OVER", 1.8)
    mp = eng.model_probability(line_sa, 1, 2, "a", "b", 3, hist, ratings, True,
                               name_rules=True)
    assert mp is not None and mp.p > 0.5
