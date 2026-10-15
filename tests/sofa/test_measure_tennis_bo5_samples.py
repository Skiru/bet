"""measure_tennis_bo5_samples: the replay's games sample (any format) against
the format-scoped one SAMPLES reads, on synthetic matches. Offline, fast."""

from __future__ import annotations

from scripts.sofa import calibrate_from_cache as cfc
from scripts.sofa import measure_tennis_bo5_samples as m


def _match(eid: int, ts: int, home: int, away: int, games: tuple[float, float],
           bo5: bool = False) -> cfc.Played:
    return cfc.Played(
        event_id=eid, timestamp=ts, home_id=home, away_id=away, sport="tennis",
        competition_id=1, values={"games": games},
        tennis=cfc.TennisContext(category_name="ATP", ground_type="Hardcourt outdoor",
                                 best_of_five=bo5))


def test_pooled_total_counts_each_match_once() -> None:
    a = [(1, 6.0, 10.0, False), (2, 7.0, 12.0, False)]
    b = [(2, 5.0, 12.0, False), (3, 6.0, 11.0, True)]
    assert m.pooled_total(a, b) == [10.0, 12.0, 11.0]


def test_a_grand_slam_in_the_sample_is_measured_and_a_clean_one_is_not() -> None:
    played: list[cfc.Played] = []
    eid = 0
    ts = 1_700_000_000
    # players 1 and 2 build bo3 histories against fillers; player 1 also plays
    # two five-setters (40 games) just before the measured match
    for k in range(12):
        for p in (1, 2):
            eid += 1
            played.append(_match(eid, ts, p, 100 + eid, (12.0, 10.0)))
        ts += 86400
    for k in range(2):
        eid += 1
        played.append(_match(eid, ts, 1, 900 + k, (24.0, 16.0), bo5=True))
        ts += 86400
    played.append(_match(10_000, ts, 1, 2, (12.0, 9.0)))
    res = m.replay(played, 0)
    tot = res["markets"]["games_total"]
    assert tot["n"] >= 1
    # the five-setters pull the replay's total centre up
    assert tot["shift_R_minus_S"][0] > 0
    assert res["counts"]["total_differs"] >= 1
    # a bo5 fixture is never measured (SHEET does not price it)
    played.append(_match(10_001, ts + 86400, 1, 2, (20.0, 18.0), bo5=True))
    again = m.replay(played, ts + 86400)
    assert again["counts"].get("bo3_fixtures", 0) == 0


def test_replay_scopes_a_tennis_sample_like_samples(monkeypatch: object) -> None:
    """--tennis-sample-scope: the replay's tennis sample is the fixture's
    format on a comparable surface (samples.py's rule); off = as before."""
    import pytest

    mp = pytest.MonkeyPatch()
    hist = []
    for k in range(14):
        hist.append(cfc.Past(k, k, 10.0 + k, 20.0, 1, True, "home", 99,
                             5 if k in (12, 13) else 3,
                             "Red clay" if k in (10, 11) else "Hardcourt outdoor"))
    fixture = cfc.TennisContext("ATP", "Hardcourt outdoor", False, best_of=3)
    try:
        mp.setattr(cfc, "TENNIS_SAMPLE_SCOPE", False)
        assert [p.event_id for p in cfc.recent_for(hist, "games_total", 1, fixture)] \
            == list(range(4, 14))
        mp.setattr(cfc, "TENNIS_SAMPLE_SCOPE", True)
        got = [p.event_id for p in cfc.recent_for(hist, "games_total", 1, fixture)]
        assert got == list(range(0, 10))          # no clay, no five-setter
        generic = cfc.TennisContext("ATP", "Hard", False, best_of=3)
        assert [p.event_id for p in cfc.recent_for(hist, "games_total", 1, generic)] \
            == list(range(0, 10))
        unknown = cfc.TennisContext("ATP", None, False, best_of=3)
        assert cfc.recent_for(hist, "games_total", 1, unknown) == []
        # a football / tennis-less call is untouched
        assert len(cfc.recent_for(hist, "games_total", 1, None)) == 10
    finally:
        mp.undo()
