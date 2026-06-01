"""Pipeline stage unit and integration tests using a mock adapter."""
from __future__ import annotations

from datetime import date, datetime, timezone

from bet.pipeline.stages.ingestion import ingest_events
from bet.pipeline.stages.normalize import normalize_raw_events
from bet.pipeline.stages.features import compute_features
from bet.pipeline.stages.scoring import score_candidates
from bet.pipeline.stages.coupon_builder import build_coupons
from bet.pipeline.stages.settlement import prepare_settlement


class MockAdapter:
    def fetch_events(self, date):
        # Return two simple payloads
        return [
            {"id": "m1", "home": "Alpha", "away": "Beta", "event_time": datetime(2026,6,1,18,0,tzinfo=timezone.utc)},
            {"id": "m2", "home": "Gamma", "away": "Delta", "event_time": datetime(2026,6,1,20,0,tzinfo=timezone.utc)},
        ]


def test_pipeline_stages_happy_path():
    adapter = MockAdapter()
    raw = ingest_events(date(2026,6,1), adapter)
    fixtures = normalize_raw_events(raw)
    features = compute_features(fixtures)
    signals = score_candidates(features)
    coupons = build_coupons(signals)
    settlements = prepare_settlement(coupons)

    assert len(raw) == 2
    assert len(fixtures) == 2
    assert len(features) == 2
    assert len(signals) == 2
    assert len(coupons) == 2
    assert len(settlements) == 2
