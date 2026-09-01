"""Helpers for stable S2 tipster artifact output."""
from __future__ import annotations

from typing import Any, Mapping

from bet.tipsters.source_contract_types import validate_tipster_pick
from bet.tipsters.source_contracts import TIPSTER_SOURCE_CONTRACTS


def build_tipster_consensus_artifact(
    *,
    date: str,
    timestamp: str,
    all_results: list[dict[str, Any]],
    all_picks: list[dict[str, Any]],
    consensus: list[dict[str, Any]],
    enhanced_entries: list[dict[str, Any]],
    errors: list[str],
    picks_by_sport: dict[str, int],
    source_status_by_sport: dict[str, dict[str, object]],
) -> dict[str, Any]:
    invalid_pick_count = 0
    for pick in all_picks:
        if validate_tipster_pick(pick):
            invalid_pick_count += 1

    return {
        "schema_version": 1,
        "artifact_kind": "tipster_consensus",
        "stage": "S2",
        "date": date,
        "timestamp": timestamp,
        "source_contracts": [contract.name for contract in TIPSTER_SOURCE_CONTRACTS],
        "sites_total": len(TIPSTER_SOURCE_CONTRACTS),
        "site_results": all_results,
        "errors": errors,
        "picks_by_sport": picks_by_sport,
        "source_status_by_sport": source_status_by_sport,
        "events_covered": len(consensus),
        "invalid_pick_count": invalid_pick_count,
        "consensus": consensus,
        "enhanced_entries": enhanced_entries,
        "all_picks": all_picks,
    }
