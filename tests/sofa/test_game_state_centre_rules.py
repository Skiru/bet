"""The game-state fit's centre follows SHEET's rules when asked
(scripts/sofa/measure_game_state.py / fit_game_state.py).

The installed betas (2026-10-13 11:39Z) were fitted on the 0.5 blend outside
UNRATED_MARKETS and the sample alone for cards_points_for; SHEET since
2026-10-13 18:10Z rates RATED_SCOPE_MARKETS (B2) at each market's own W
(B14). ``CentreRules`` replays either; the default stays the old centre,
operation for operation. Offline and synthetic.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.sofa import centre_replay as cr
from bet.sofa import count_dispersion, epochs
from bet.sofa import football_rating as fr
from bet.sofa.rating_weight import RatingWeightTable
from scripts.sofa import measure_game_state as mgs


def _row(market: str, rating: float | None = 6.0, sample: float = 4.0,
         ts: int = 0, event_id: int = 1, y: float = 5.0,
         supremacy: float | None = 0.5) -> cr.CentreRow:
    return cr.CentreRow(event_id, ts, 17, market, "side_a", y, sample, rating,
                        supremacy, None)


def test_default_rules_are_the_old_centre() -> None:
    w = fr.W_FOOTBALL_RATING
    assert mgs.live_centre(_row("corners_for")) == w * 6.0 + (1 - w) * 4.0
    # cards_points_for is UNRATED: the sample alone, even with a rating
    assert mgs.live_centre(_row("cards_points_for")) == 4.0
    assert mgs.live_centre(_row("corners_for", rating=None)) == 4.0
    assert mgs.live_centre(_row("cards_points_for"), mgs.DEFAULT_RULES) == 4.0


def test_rated_scope_rates_cards_at_the_default_weight() -> None:
    rules = mgs.CentreRules(rated_scope=fr.RATED_SCOPE_MARKETS)
    assert mgs.live_centre(_row("cards_points_for"), rules) == 0.5 * 6.0 + 0.5 * 4.0
    # an UNRATED market outside the scope keeps the sample
    assert "corners_total" not in fr.RATED_SCOPE_MARKETS
    assert mgs.live_centre(_row("corners_total"), rules) == 4.0
    assert mgs.live_centre(_row("cards_points_for", rating=None), rules) == 4.0


def test_rating_weight_reads_the_markets_own_w() -> None:
    table = RatingWeightTable({"corners_for": 0.8})
    rules = mgs.CentreRules(fr.RATED_SCOPE_MARKETS, table)
    assert mgs.live_centre(_row("corners_for"), rules) == pytest.approx(
        0.8 * 6.0 + 0.2 * 4.0)
    # a market absent from the table keeps W_FOOTBALL_RATING
    assert mgs.live_centre(_row("cards_points_for"), rules) == 5.0
    # weights without the scope leave cards_points_for unrated
    only_w = mgs.CentreRules(rating_weights=table)
    assert mgs.live_centre(_row("cards_points_for"), only_w) == 4.0


def _weights(tmp_path: Path) -> Path:
    path = tmp_path / "w.json"
    path.write_text(json.dumps({"markets": {"shots_for": {"w": 0.85}}}))
    return path


def test_rules_as_of_follow_epochs(monkeypatch: pytest.MonkeyPatch,
                                   tmp_path: Path) -> None:
    on = datetime(2026, 10, 13, 18, 10, tzinfo=UTC)
    monkeypatch.setattr(epochs, "FOOTBALL_RATED_SCOPE_FROM_UTC", None)
    monkeypatch.setattr(epochs, "FOOTBALL_RATING_WEIGHT_FROM_UTC", None)
    assert mgs.rules_as_of("2026-10-13", on) == mgs.DEFAULT_RULES
    monkeypatch.setattr(epochs, "FOOTBALL_RATED_SCOPE_FROM_UTC", on)
    monkeypatch.setattr(epochs, "FOOTBALL_RATING_WEIGHT_FROM_UTC", on)
    before = mgs.rules_as_of("2026-10-13", datetime(2026, 10, 13, 12, tzinfo=UTC),
                             _weights(tmp_path))
    assert before == mgs.DEFAULT_RULES
    after = mgs.rules_as_of("2026-10-13", datetime(2026, 10, 14, tzinfo=UTC),
                            _weights(tmp_path))
    assert after.rated_scope == fr.RATED_SCOPE_MARKETS
    assert after.rating_weights is not None
    assert after.rating_weights.weight("shots_for") == 0.85


def _ns(**kw: object) -> argparse.Namespace:
    base: dict[str, object] = {"live_rules": False, "rated_scope": False,
                               "rating_weight": None}
    base.update(kw)
    return argparse.Namespace(**base)


def test_rules_from_args(tmp_path: Path) -> None:
    assert mgs.rules_from_args(_ns(), "2026-10-13") == mgs.DEFAULT_RULES
    ap = argparse.ArgumentParser()
    mgs.add_rule_args(ap)
    assert mgs.rules_from_args(ap.parse_args([]), "2026-10-13") == mgs.DEFAULT_RULES
    r = mgs.rules_from_args(
        ap.parse_args(["--rated-scope", "--rating-weight", str(_weights(tmp_path))]),
        "2026-10-13")
    assert r.rated_scope == fr.RATED_SCOPE_MARKETS
    assert r.rating_weights is not None and r.rating_weights.weight("shots_for") == 0.85
    with pytest.raises(SystemExit):
        mgs.rules_from_args(_ns(live_rules=True, rated_scope=True), "2026-10-13")


def test_measure_compares_against_fixed_betas() -> None:
    ts0 = int(datetime(2025, 6, 1, tzinfo=UTC).timestamp())
    ts1 = int(datetime(2025, 8, 5, tzinfo=UTC).timestamp())
    rows = []
    eid = 0
    for base_ts in (ts0, ts1):
        for i in range(400):
            s = (i % 9 - 4) / 2.0
            c = 5.0
            y = float(round(c * math.exp(0.1 * s)))
            eid += 1
            rows.append((_row("corners_for", ts=base_ts + i, event_id=eid, y=y,
                              supremacy=s, sample=c, rating=None), c))
    out = mgs.measure(rows, "2025-08-01", "2025-08-31",
                      count_dispersion.DispersionTable({}),
                      fixed={"corners_for": 0.0})
    cell = out["corners_for"]
    assert cell["fixed_beta"] == 0.0
    # beta 0 is no term at all: vs fixed equals vs none
    assert cell["d_logloss_vs_fixed"][0] == pytest.approx(cell["d_logloss"][0])
    assert cell["d_logloss"][0] < 0
    assert "d_logloss_vs_fixed" not in mgs.measure(
        rows, "2025-08-01", "2025-08-31",
        count_dispersion.DispersionTable({}))["corners_for"]
