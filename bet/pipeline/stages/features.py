"""Feature derivation stage: compute simple features from canonical fixtures.

In early refactor iterations this can be very simple (e.g., basic counts,
synthetic features). Downstream scoring logic should be adapted to the feature
shape produced here.
"""
from __future__ import annotations

from typing import List

from ..contracts import CanonicalFixture, FixtureFeatures


def compute_features(fixtures: List[CanonicalFixture]) -> List[FixtureFeatures]:
    out: List[FixtureFeatures] = []
    for f in fixtures:
        feats = {
            "has_team_names": bool(f.home_team and f.away_team),
            "home_len": len(f.home_team) if f.home_team else 0,
            "away_len": len(f.away_team) if f.away_team else 0,
        }
        out.append(FixtureFeatures(external_id=f.external_id, features=feats))
    return out
