"""refused_markets: the operator keeps a market (or one direction of it) off
both coupons by name, whatever the fitted curve says (2026-10-03, for the open
decision on shots_total / fouls_total UNDER)."""

import json
from pathlib import Path
from typing import Any

from bet.sofa.confidence import Calibration
from bet.sofa.fit_meta import OPERATOR_KEYS, carry_operator_keys

REPO = Path(__file__).resolve().parents[2]


def _cal(tmp_path: Path, extra: dict[str, Any]) -> Calibration:
    path = tmp_path / "cal.json"
    path.write_text(json.dumps({"pooled": {}, "by_market": {}, **extra}))
    return Calibration.load(path)


def test_nothing_is_refused_by_default(tmp_path: Path) -> None:
    cal = _cal(tmp_path, {})
    assert not cal.refused_by_operator("shots_total", "UNDER")


def test_a_direction_or_a_whole_market_is_refused_by_name(tmp_path: Path) -> None:
    cal = _cal(tmp_path, {"refused_markets": ["shots_total|UNDER", "fouls_total"]})
    assert cal.refused_by_operator("shots_total", "UNDER")
    assert cal.refused_by_operator("shots_total", "under")
    assert not cal.refused_by_operator("shots_total", "OVER")
    assert cal.refused_by_operator("fouls_total", "OVER")
    assert cal.refused_by_operator("fouls_total", None)
    assert not cal.refused_by_operator("shots_on_target_total", "UNDER")


def test_run_confidence_refuses_before_the_curve_lookup() -> None:
    source = (REPO / "scripts/sofa/run_confidence.py").read_text()
    i = source.index('cal.refused_by_operator(\n            row["market"], row.get("direction")\n        )')
    assert 'refused["OPERATOR_REFUSED"]' in source[i:i + 200]
    assert i < source.index("else cal.realised(")
    # from epochs.LINE_EVIDENCE_FROM_UTC the line evidence replaces the refusal
    assert "if evidence is None and cal.refused_by_operator(" in source


def test_the_refusal_list_survives_a_refit() -> None:
    assert "refused_markets" in OPERATOR_KEYS
    new: dict[str, Any] = {"by_market": {}}
    carry_operator_keys(new, {"refused_markets": ["shots_total|UNDER"]})
    assert new["refused_markets"] == ["shots_total|UNDER"]
