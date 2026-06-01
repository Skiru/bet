"""Scoring stage: take features and produce signals.

This is intentionally simplistic: for the refactor, we implement a naive scoring
function to demonstrate the pipeline flow. Replace with model-backed scoring
in future iterations.
"""
from __future__ import annotations

from typing import List

from ..contracts import FixtureFeatures, Signal


def score_candidates(features: List[FixtureFeatures], model_meta: dict | None = None) -> List[Signal]:
    signals: List[Signal] = []
    for f in features:
        # naive rule: prefer home if home_len > away_len
        home_len = f.features.get("home_len", 0)
        away_len = f.features.get("away_len", 0)
        if home_len > away_len:
            pick = "home"
            confidence = 0.55 + min(0.4, (home_len - away_len) * 0.01)
        elif away_len > home_len:
            pick = "away"
            confidence = 0.55 + min(0.4, (away_len - home_len) * 0.01)
        else:
            pick = "draw"
            confidence = 0.5
        signals.append(Signal(external_id=f.external_id, pick=pick, confidence=float(confidence), score_details={"rule": "length_based"}))
    return signals
