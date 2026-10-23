"""Review R3 F10: a CS2 side priced through the unrated pairs' lineup
calibration (audit 2026-10-23 P7, epochs.CS2_LINEUP_ELO_UNRATED) carries
`lineup_unrated_rule` on its leg (08_confidence_sports.json; coupon_sports
.normalize copies a leg whole into the coupon), so the verifier, the analysts
and the ledger can tell P7's legs apart. A rated pair, a side the unrated
calibration does not move and a model built without the switch carry none."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from bet.sofa import coupon_sports
from bet.sofa import cs2_engine as eng
from bet.sofa import sport_identity as si
from scripts.sofa import run_sport_confidence as rsc
from tests.sofa.test_audit1023_p7_cs2_lineup_unrated import _history
from tests.sofa.test_sport_late_window import (
    EVENING,
    D,
    FakeForecaster,
    _calibration,
    _fixtures,
    _snap,
)
from tests.sofa.test_sport_late_window import (
    _price as _late_price,
)

WINNER = eng.Cs2Line("e", "match_winner", 0, "", None, "T1", 1.8)


def _forecaster(unrated: bool) -> rsc.DbForecaster:
    hist = _history()
    fc = rsc.DbForecaster("unused.db", EVENING, D)
    fc._cs2 = (hist, {}, eng.build_ratings(hist, (), unrated))
    fc._cs2_exposure = None
    return fc


def _p(fc: rsc.DbForecaster, home: int, away: int,
       line: eng.Cs2Line = WINNER) -> float | None:
    fixture = {"home_id": home, "away_id": away, "home_is_team1": True,
               "best_of": 3}
    ev = SimpleNamespace(superbet_event_id="e", team1="a", team2="b")
    return fc.probability("cs2", fixture, ev, line)


def test_an_unrated_pair_priced_by_the_lineup_carries_the_rule(monkeypatch: Any
                                                               ) -> None:
    monkeypatch.setattr(rsc.DbForecaster, "_cs2_counts", lambda self, maps: None)
    fc = _forecaster(True)
    assert _p(fc, 3, 2) is not None
    ev = SimpleNamespace(superbet_event_id="e")
    assert fc.unrated_rule("cs2", ev, WINNER)
    assert not fc.unrated_rule("hockey", ev, WINNER)
    # another side of another event: not marked
    assert not fc.unrated_rule("cs2", SimpleNamespace(superbet_event_id="x"),
                               WINNER)


def test_a_rated_pair_or_the_switch_off_carries_none(monkeypatch: Any) -> None:
    monkeypatch.setattr(rsc.DbForecaster, "_cs2_counts", lambda self, maps: None)
    ev = SimpleNamespace(superbet_event_id="e")
    rated = _forecaster(True)
    assert _p(rated, 1, 2) is not None
    assert not rated.unrated_rule("cs2", ev, WINNER)
    off = _forecaster(False)
    assert _p(off, 3, 2) is None and not off.unrated_rule("cs2", ev, WINNER)


class _Marking(FakeForecaster):
    def unrated_rule(self, sport: str, ev: Any, line: Any) -> bool:
        return line.side == "OVER"


def test_the_leg_carries_the_marker_and_keeps_it_in_the_coupon(
        tmp_path: Path, monkeypatch: Any) -> None:
    kick = "2026-10-23T23:00:00Z"
    _snap(tmp_path, D, kick, EVENING - timedelta(minutes=10))
    _fixtures(tmp_path, D, kick)
    # a forecaster without unrated_rule (every one before the fix): no marker
    _, (leg,) = _late_price(tmp_path, D, EVENING)
    assert "lineup_unrated_rule" not in leg
    doc = si.load_fixtures(tmp_path / D / si.FIXTURES_FILE)
    _, (leg,) = rsc.build_sport("hockey", D, str(tmp_path), doc, _calibration(),
                                _Marking(), EVENING, None, None, None,
                                rsc.prev_printed(str(tmp_path), D))
    assert leg["lineup_unrated_rule"] == eng.LINEUP_UNRATED_RULE
    assert coupon_sports.normalize(leg)["lineup_unrated_rule"] == \
        eng.LINEUP_UNRATED_RULE
