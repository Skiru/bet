"""Canonical tipster-source registry and status helpers.

Keeps S1b/S2 aligned on which sports have configured tipster ingestion,
which are externally unsupported today, and how zero-result sports should be
reported instead of silently treated as generic misses.
"""

from __future__ import annotations

from bet.pipeline.tipster_sources import TIPSTER_SOURCE_CONTRACTS


def _active_sources_for_sport(sport: str) -> list[str]:
    sport_key = str(sport or "").strip().lower()
    return [contract.name for contract in TIPSTER_SOURCE_CONTRACTS if sport_key in contract.sports]

TIPSTER_SOURCE_REGISTRY: dict[str, dict[str, object]] = {
    "football": {
        "status": "configured",
        "active_sources": _active_sources_for_sport("football"),
    },
    "tennis": {
        "status": "configured",
        "active_sources": _active_sources_for_sport("tennis"),
    },
    "basketball": {
        "status": "configured",
        "active_sources": _active_sources_for_sport("basketball"),
    },
    "hockey": {
        "status": "configured",
        "active_sources": _active_sources_for_sport("hockey"),
    },
    "volleyball": {
        "status": "configured",
        "active_sources": _active_sources_for_sport("volleyball"),
        "note": "Configured generic tipster sites, but live same-day pair coverage may still be zero.",
    },
    "cs2": {
        "status": "no_source_verified",
        "active_sources": [],
        "candidate_sources": ["bo3.gg"],
        "note": "No production-grade parsed tipster source is enabled yet for CS2.",
    },
    "dota2": {
        "status": "no_source_verified",
        "active_sources": [],
        "candidate_sources": ["GosuGamers"],
        "note": "No production-grade parsed tipster source is enabled yet for Dota 2.",
    },
    "valorant": {
        "status": "no_source_verified",
        "active_sources": [],
        "candidate_sources": ["VLR.gg"],
        "note": "No production-grade parsed tipster source is enabled yet for Valorant.",
    },
}


def get_tipster_source_status(sport: str, live_pick_count: int | None = None) -> dict[str, object]:
    entry = dict(TIPSTER_SOURCE_REGISTRY.get(str(sport or "").strip().lower(), {
        "status": "unknown",
        "active_sources": [],
    }))
    if live_pick_count is not None and entry.get("status") == "configured" and live_pick_count == 0:
        entry["status"] = "configured_zero_live"
    return entry
