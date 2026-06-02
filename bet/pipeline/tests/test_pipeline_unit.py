"""Unit tests for the lightweight pipeline stages implemented in `bet.pipeline`.

These tests are intentionally self-contained and avoid the repository `tests/`
`conftest.py` to make them runnable in isolation.
"""
from datetime import datetime, timezone

from bet.pipeline.stages.ingestion import ingest_events
from bet.pipeline.stages.normalize import normalize_raw_events
from bet.pipeline.stages.features import compute_features
from bet.pipeline.stages.scoring import score_candidates
from bet.pipeline.stages.coupon_builder import build_coupons
from bet.pipeline.stages.settlement import prepare_settlement
from bet.pipeline.service import run_single_day_pipeline


class DummyAdapter:
    def __init__(self, payloads):
        self._payloads = payloads

    def fetch_events(self, date):
        return self._payloads


def test_pipeline_stage_flow():
    payloads = [
        {"id": "1", "home": "Team A", "away": "Team B", "event_time": "2026-06-02T10:00:00+02:00"},
        {"id": "2", "home_team": "Alpha", "away_team": "Beta", "start_time": 1710000000},
        {"id": "3", "team_home": "X", "team_away": "Y", "timestamp": datetime(2026, 6, 2, 8, 0)},
    ]

    adapter = DummyAdapter(payloads)

    raw = ingest_events(datetime(2026, 6, 2), adapter)
    assert len(raw) == 3

    fixtures = normalize_raw_events(raw)
    assert len(fixtures) == 3
    for f in fixtures:
        assert f.event_time.tzinfo is not None
        # normalized to UTC
        assert f.event_time.tzinfo.utcoffset(f.event_time) == timezone.utc.utcoffset(f.event_time)

    features = compute_features(fixtures)
    assert len(features) == 3

    signals = score_candidates(features)
    assert len(signals) == 3
    for s in signals:
        assert 0.0 <= s.confidence <= 1.0
        assert s.pick in ("home", "away", "draw")

    coupons = build_coupons(signals)
    assert len(coupons) == 3

    settlements = prepare_settlement(coupons)
    assert len(settlements) == 3
    for c, p in zip(coupons, settlements):
        avg_conf = sum(s.confidence for s in c.picks) / len(c.picks)
        assert abs(p.expected_payout - (c.stake * avg_conf * 2)) < 1e-8


def test_run_single_day_pipeline_smoke():
    payloads = [{"id": "x", "home": "A", "away": "B", "event_time": "2026-06-02T06:00:00+02:00"}]
    adapter = DummyAdapter(payloads)
    out = run_single_day_pipeline(datetime(2026, 6, 2), adapter)
    assert set(out.keys()) >= {"raw", "fixtures", "features", "signals", "coupons", "settlements"}
