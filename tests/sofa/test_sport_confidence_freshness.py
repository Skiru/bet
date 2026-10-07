"""The basketball history replay simulates with the live noise by freshness
(epochs.BB_FRESHNESS_FROM_UTC, 2026-10-07): sport_confidence.walk_forward_rows
(freshness=True) asks ScoreModel.noise_mult for every game, and its `recent`
book grows with the replay instead of staying as of the last rebuild."""

from __future__ import annotations

import random
from typing import Any

import pytest

from bet.sofa import score_model as sm
from bet.sofa import sport_confidence as scf
from bet.sofa.shadow import SPORTS
from scripts.sofa.fit_sport_confidence import bb_freshness_on

BASKETBALL = SPORTS["basketball"]
DAY = 86400


def _event(eid: int, ts: int, home: int, away: int, rng: random.Random
           ) -> dict[str, Any]:
    hp = [rng.randint(20, 32) for _ in range(4)]
    ap = [rng.randint(20, 32) for _ in range(4)]
    hs, as_ = sum(hp), sum(ap)
    if hs == as_:
        hp[3] += 1
        hs += 1
    return {
        "id": eid, "startTimestamp": ts,
        "tournament": {"id": 9, "name": "L",
                       "uniqueTournament": {"id": 5, "name": "L"},
                       "category": {"sport": {"slug": "basketball"}}},
        "status": {"type": "finished", "description": "Ended"},
        "homeTeam": {"id": home, "name": f"T{home}", "gender": "M"},
        "awayTeam": {"id": away, "name": f"T{away}", "gender": "M"},
        "homeScore": {**{f"period{i + 1}": v for i, v in enumerate(hp)},
                      "current": hs, "normaltime": hs},
        "awayScore": {**{f"period{i + 1}": v for i, v in enumerate(ap)},
                      "current": as_, "normaltime": as_},
        "winnerCode": 1 if hs > as_ else 2,
    }


def _events() -> dict[int, dict[str, Any]]:
    """Four established sides for 200 days; team 109 joins on day 140 and
    plays every other day: five games by the window's start (the rating needs
    five), then its games-in-120-days count climbs past 9 inside one build."""
    rng = random.Random(5)
    out: dict[int, dict[str, Any]] = {}
    eid = 1
    for d in range(200):
        for k, (h, a) in enumerate(((101, 102), (103, 104))):
            out[eid] = _event(eid, d * DAY + k * 7200, h, a, rng)
            eid += 1
        if d >= 140 and d % 2 == 0:
            out[eid] = _event(eid, d * DAY + 20000, 109, 101, rng)
            eid += 1
    return out


def _mults(freshness: bool, monkeypatch: pytest.MonkeyPatch
           ) -> dict[int, float]:
    seen: dict[int, float] = {}
    real = sm.ScoreModel.simulate

    def spy(self: sm.ScoreModel, mu1: Any, mu2: Any, seed: int = 0,
            n: int = 0, noise_mult: float = 1.0) -> Any:
        seen[seed] = noise_mult
        return real(self, mu1, mu2, seed=seed, n=min(n, 20), noise_mult=noise_mult)

    monkeypatch.setattr(sm.ScoreModel, "simulate", spy)
    history = scf.parse_history(_events(), BASKETBALL)
    scf.walk_forward_rows(history, BASKETBALL, 150 * DAY, 199 * DAY, 20, None,
                          "t", freshness)
    return seen


def test_freshness_off_never_touches_the_noise(monkeypatch) -> None:
    assert set(_mults(False, monkeypatch).values()) == {1.0}


def test_the_recent_book_grows_with_the_replay(monkeypatch) -> None:
    mult = _mults(True, monkeypatch)
    ev = _events()
    by_id = {eid: e for eid, e in ev.items()
             if e["homeTeam"]["id"] == 109 or e["awayTeam"]["id"] == 109}
    games = sorted(by_id.values(), key=lambda e: e["startTimestamp"])
    _, le9 = sm.SimParams().bb_fresh_mult
    # the model is rebuilt every REBUILD_DAYS (30): the build at day 150 holds
    # five games of team 109, the book must count the ones played after it
    assert games[0]["id"] not in mult           # unrated: no forecast
    assert mult[games[5]["id"]] == le9          # 5 games before it: 3..9
    assert mult[games[9]["id"]] == le9          # 9
    assert mult[games[10]["id"]] == 1.0         # 10: only if `recent` grew
    assert mult[games[20]["id"]] == 1.0
    # established sides' own games are unchanged
    established = [eid for eid, e in ev.items() if eid not in by_id
                   and e["startTimestamp"] >= 150 * DAY]
    assert {mult[i] for i in established if i in mult} == {1.0}


def test_bb_freshness_on_follows_the_live_rule() -> None:
    assert bb_freshness_on("2026-10-08", "auto")
    assert not bb_freshness_on("2026-10-07", "auto")
    assert bb_freshness_on("2026-10-01", "on")
    assert not bb_freshness_on("2026-10-08", "off")
