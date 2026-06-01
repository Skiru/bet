"""Service helpers to run pipeline stages individually for local dev and REPL."""
from __future__ import annotations

from datetime import date
from typing import List

from .contracts import RawEvent, CanonicalFixture, FixtureFeatures, Signal, Coupon, SettlementPlan
from .stages.ingestion import ingest_events
from .stages.normalize import normalize_raw_events
from .stages.features import compute_features
from .stages.scoring import score_candidates
from .stages.coupon_builder import build_coupons
from .stages.settlement import prepare_settlement


def run_single_day_pipeline(date: date, adapter, source_name: str = "bookmaker") -> dict:
    raw = ingest_events(date, adapter, source_name=source_name)
    fixtures = normalize_raw_events(raw)
    features = compute_features(fixtures)
    signals = score_candidates(features)
    coupons = build_coupons(signals)
    settlements = prepare_settlement(coupons)
    return {
        "raw": raw,
        "fixtures": fixtures,
        "features": features,
        "signals": signals,
        "coupons": coupons,
        "settlements": settlements,
    }
