"""A player prop with a fitted curve is still refused until the operator
admits it by name (review 2026-10-02: the next fit_confidence would have
lifted AWAITING_OWN_CURVE by itself)."""

from __future__ import annotations

import json
from pathlib import Path

from bet.sofa.confidence import PLAYER_PROP_MARKETS, Calibration


def _write(tmp_path: Path, doc: dict[str, object]) -> Path:
    path = tmp_path / "cal.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_a_curved_player_prop_is_not_admitted_by_default(tmp_path: Path) -> None:
    curve = {"0.70-0.75": {"realised_lo95": 0.72, "n": 900}}
    cal = Calibration.load(_write(tmp_path, {"by_market": {"player_shots_for": curve}}))
    assert cal.player_prop_not_admitted("player_shots_for")
    assert not cal.player_prop_not_admitted("goals_total")


def test_the_operator_admits_a_market_by_name(tmp_path: Path) -> None:
    cal = Calibration.load(
        _write(tmp_path, {"admitted_player_markets": ["player_shots_for"]})
    )
    assert not cal.player_prop_not_admitted("player_shots_for")
    assert cal.player_prop_not_admitted("player_assists_for")


def test_every_player_metric_is_covered() -> None:
    from bet.sofa.players import PLAYER_METRICS

    assert set(PLAYER_METRICS) == set(PLAYER_PROP_MARKETS)
