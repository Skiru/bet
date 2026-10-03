"""A leg whose claim sits in a curve's catch-all bottom bucket is never printed
(night review 2026-10-03).

The 10-03 refit's `player_offsides_for|UNDER` bucket 0.000-0.600 carries
realised_lo95 0.7215, above both profiles' floors, so an UNDER offsides row the
model put at p = 0.05 read confidence 0.72. Superbet quotes player props OVER
only, so it never printed - but the floor was the only thing between the long
shot and the coupon, and here the floor did not hold.
"""

from __future__ import annotations

import json
from pathlib import Path

from bet.sofa.confidence import (
    CATCH_ALL_BUCKET_TOP,
    PROFILES,
    Calibration,
    reads_catch_all_bucket,
)

REPO = Path(__file__).resolve().parents[2]

# The bottom of the installed 10-03 curve, verbatim.
OFFSIDES_UNDER = {
    "0.000-0.600": {"n": 8155, "realised": 0.7312, "realised_lo95": 0.7215},
    "0.600-0.700": {"n": 3168, "realised": 0.8302, "realised_lo95": 0.8167},
}


def _cal(tmp_path: Path) -> Calibration:
    path = tmp_path / "cal.json"
    path.write_text(
        json.dumps(
            {
                "by_market_direction": {"player_offsides_for|UNDER": OFFSIDES_UNDER},
                "admitted_player_markets": ["player_offsides_for"],
            }
        ),
        encoding="utf-8",
    )
    return Calibration.load(path)


def test_the_bottom_bucket_clears_every_floor_on_its_own(tmp_path: Path) -> None:
    # The defect: the curve alone lets a p = 0.05 claim through both floors.
    hit = _cal(tmp_path).realised(
        "player_offsides_for", 0.05, "football", "UNDER"
    )
    assert hit is not None
    assert all(hit[0] >= profile.floor for profile in PROFILES.values())


def test_a_claim_in_the_catch_all_bucket_is_refused() -> None:
    assert reads_catch_all_bucket(0.05)
    assert reads_catch_all_bucket(0.5999)
    assert not reads_catch_all_bucket(0.60)
    assert not reads_catch_all_bucket(0.75)


def test_the_gate_follows_the_fit_grid() -> None:
    from scripts.sofa import fit_confidence

    assert fit_confidence.EDGES[0] == 0.0
    assert fit_confidence.EDGES[1] == CATCH_ALL_BUCKET_TOP


def test_the_bucket_top_sits_below_every_profile_floor() -> None:
    # A claim the gate lets through is at least 0.60; a floor at or below that
    # would make the curve's bottom bucket the binding rule again.
    assert all(profile.floor > CATCH_ALL_BUCKET_TOP for profile in PROFILES.values())


def test_confidence_and_the_disagreement_replay_apply_it() -> None:
    src = (REPO / "scripts/sofa/run_confidence.py").read_text(encoding="utf-8")
    assert 'refused["CATCH_ALL_BUCKET"]' in src
    assert src.index('refused["BELOW_CONFIDENCE_FLOOR"]') < src.index(
        'refused["CATCH_ALL_BUCKET"]'
    ) < src.index('refused["NEGATIVE_LEG_EV"]')
    replay = (REPO / "scripts/sofa/measure_disagreement.py").read_text(
        encoding="utf-8"
    )
    assert "reads_catch_all_bucket(g.row.p_central)" in replay
