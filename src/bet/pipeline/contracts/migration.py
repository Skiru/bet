"""Explicit versioned migration adapters for step artifacts and legacy aliases."""
from __future__ import annotations

from typing import Any, Callable


class MigrationAdapterError(ValueError):
    """Raised when an explicit migration adapter fails or is missing."""
    pass


_MIGRATION_REGISTRY: dict[tuple[str, int, int], Callable[[dict[str, Any]], dict[str, Any]]] = {}
_ALIAS_ADAPTERS: dict[tuple[str, str], Callable[[dict[str, Any]], dict[str, Any]]] = {}


def register_migration_adapter(
    contract_id: str,
    from_version: int,
    to_version: int,
    adapter_fn: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    """Register an explicit migration adapter function."""
    key = (contract_id, from_version, to_version)
    _MIGRATION_REGISTRY[key] = adapter_fn


def register_legacy_alias_adapter(
    from_type: str,
    to_type: str,
    adapter_fn: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    """Register a legacy alias migration adapter."""
    _ALIAS_ADAPTERS[(from_type, to_type)] = adapter_fn


def migrate_artifact_payload(
    contract_id: str,
    from_version: int,
    to_version: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Migrate payload from from_version to to_version using a registered adapter."""
    if from_version == to_version:
        return payload

    key = (contract_id, from_version, to_version)
    adapter = _MIGRATION_REGISTRY.get(key)
    if adapter is None:
        raise MigrationAdapterError(
            f"No migration adapter registered for {contract_id} from v{from_version} to v{to_version}."
        )
    return adapter(payload)


def _extract_event_id(item: dict[str, Any], idx: int) -> str:
    eid = item.get("canonical_event_id")
    if isinstance(eid, str) and eid.startswith("evt_"):
        return eid
    orig = item.get("original_candidate")
    if isinstance(orig, dict):
        orig_eid = orig.get("canonical_event_id")
        if isinstance(orig_eid, str) and orig_eid.startswith("evt_"):
            return orig_eid
    if item.get("fixture_id") is not None:
        return str(item["fixture_id"])
    if item.get("event_id") is not None:
        return str(item["event_id"])
    if isinstance(eid, str) and eid:
        return eid
    cand_id = item.get("candidate_id")
    if isinstance(cand_id, str) and cand_id:
        return cand_id
    sel_id = item.get("selection_id")
    if isinstance(sel_id, str) and sel_id:
        return sel_id
    return f"EVT_{idx+1:04d}"


def adapt_legacy_artifact(data: dict[str, Any], target_type: str) -> dict[str, Any]:
    """Adapt a legacy artifact payload to the canonical target contract structure if needed."""
    if not isinstance(data, dict):
        return data

    actual_type = data.get("artifact_type") or data.get("artifact_kind") or ""
    if actual_type == target_type and data.get("event_records"):
        return data

    key = (actual_type, target_type)
    adapter = _ALIAS_ADAPTERS.get(key)
    if adapter:
        res = adapter(data)
        data.update(res)
        return data

    # Check if actual_type is a known legacy alias for target_type
    known_aliases = {
        "S0_HISTORICAL_PNL": {"HISTORICAL_PNL"},
        "HISTORICAL_PNL": {"S0_HISTORICAL_PNL"},
        "S1_FIXTURES_SHORTLIST": {"S1_SHORTLIST", "FIXTURES_SHORTLIST"},
        "S1_SHORTLIST": {"S1_FIXTURES_SHORTLIST"},
        "FIXTURES_SHORTLIST": {"S1_FIXTURES_SHORTLIST"},
        "S1E_CANONICAL_EVENT_UNIVERSE": {"S1E_EVENT_UNIVERSE_LEDGER"},
        "S1E_EVENT_UNIVERSE_LEDGER": {"S1E_CANONICAL_EVENT_UNIVERSE"},
        "S2_TIPSTER_CONSENSUS": {"S2_SHORTLIST", "TIPSTER_CONSENSUS"},
        "S2_SHORTLIST": {"S2_TIPSTER_CONSENSUS"},
        "TIPSTER_CONSENSUS": {"S2_TIPSTER_CONSENSUS"},
        "S2_3_ENRICHMENT_GAPS": {"AGENT_ARTIFACT"},
        "S2_5_PROVIDER_OBSERVATIONS": {"AGENT_ARTIFACT"},
        "S2_7_RECONCILED_FACTS": {"AGENT_ARTIFACT"},
        "S2_9_DATA_READINESS": {"AGENT_ARTIFACT"},
        "S3_CALIBRATED_PROBABILITIES": {"S3_DEEP_STATS"},
        "S3_DEEP_STATS": {"S3_CALIBRATED_PROBABILITIES"},
        "S4_EXPECTED_VALUE_ESTIMATES": {"S4_VALUATION_CANDIDATE_SET_V2"},
        "S4_VALUATION_CANDIDATE_SET_V2": {"S4_EXPECTED_VALUE_ESTIMATES"},
        "S5_CONTEXT_MOTIVATION_RISK": {"S5_CONTEXT_RISK_CANDIDATE_SET_V2", "AGENT_ARTIFACT"},
        "S5_CONTEXT_RISK_CANDIDATE_SET_V2": {"S5_CONTEXT_MOTIVATION_RISK", "AGENT_ARTIFACT"},
        "AGENT_ARTIFACT": {"S2_3_ENRICHMENT_GAPS", "S2_5_PROVIDER_OBSERVATIONS", "S2_7_RECONCILED_FACTS", "S2_9_DATA_READINESS", "S5_CONTEXT_MOTIVATION_RISK", "S5_CONTEXT_RISK_CANDIDATE_SET_V2"},
        "S6_PORTFOLIO_REPEAT_GUARD": {"S6_PORTFOLIO_REPEAT_GUARD_V2", "S6_REPEAT_LOSS_HANDOFF_V2"},
        "S6_PORTFOLIO_REPEAT_GUARD_V2": {"S6_PORTFOLIO_REPEAT_GUARD", "S6_REPEAT_LOSS_HANDOFF_V2"},
        "S6_REPEAT_LOSS_HANDOFF_V2": {"S6_PORTFOLIO_REPEAT_GUARD", "S6_PORTFOLIO_REPEAT_GUARD_V2"},
        "S7_APPROVED_PICKS": {"S7_ANALYTICAL_APPROVAL_SET_V2", "S7_DECISION_GATE_REPORT", "S7_HARD_APPROVAL_GATE_V2"},
        "S7_ANALYTICAL_APPROVAL_SET_V2": {"S7_APPROVED_PICKS", "S7_DECISION_GATE_REPORT", "S7_HARD_APPROVAL_GATE_V2"},
        "S7_DECISION_GATE_REPORT": {"S7_APPROVED_PICKS", "S7_ANALYTICAL_APPROVAL_SET_V2", "S7_HARD_APPROVAL_GATE_V2"},
        "S7_HARD_APPROVAL_GATE_V2": {"S7_APPROVED_PICKS", "S7_ANALYTICAL_APPROVAL_SET_V2", "S7_DECISION_GATE_REPORT"},
        "S7B_SUPERBET_MANUAL_MAPPING": {"S7B_SUPERBET_MANUAL_MAPPING"},
        "S8_SUPERBET_MANUAL_QUOTE_PACK": {"S8_SUPERBET_MANUAL_QUOTE_PACK"},
    }

    allowed = known_aliases.get(target_type, set())
    if actual_type not in allowed and actual_type != target_type:
        # Not a known alias or target type; do not touch artifact_type
        return data

    migrated = dict(data)
    migrated["artifact_type"] = target_type

    # Map S0
    if target_type == "S0_HISTORICAL_PNL":
        if "settled_records" not in migrated:
            migrated["settled_records"] = migrated.get("records") or migrated.get("settled_bets") or []

    # Map S1
    elif target_type == "S1_FIXTURES_SHORTLIST":
        if "events" not in migrated:
            raw_events = migrated.get("shortlist") or migrated.get("fixtures") or migrated.get("discovered_events") or []
            norm_events = []
            for idx, item in enumerate(raw_events if isinstance(raw_events, list) else []):
                if isinstance(item, dict):
                    eid = item.get("canonical_event_id") or item.get("fixture_id") or item.get("event_id") or f"EVT_{idx+1:04d}"
                    norm_events.append({
                        "canonical_event_id": str(eid),
                        "sport": item.get("sport", "football"),
                        "competition": item.get("competition", "League"),
                        "home_team": item.get("home_team") or item.get("home", "Home"),
                        "away_team": item.get("away_team") or item.get("away", "Away"),
                        "event_start_time": item.get("event_start_time") or item.get("start_time", "2026-07-27T18:00:00Z"),
                        "discovery_status": item.get("discovery_status", "VERIFIED"),
                        "terminal_status": item.get("terminal_status", "PASS"),
                    })
            migrated["events"] = norm_events
            migrated["discovered_event_count"] = len(norm_events)

    # Map S1e
    elif target_type == "S1E_CANONICAL_EVENT_UNIVERSE":
        if "deduplicated_events" not in migrated:
            raw_events = migrated.get("event_records") or migrated.get("events") or []
            norm_events = []
            for idx, item in enumerate(raw_events if isinstance(raw_events, list) else []):
                if isinstance(item, dict):
                    eid = item.get("canonical_event_id") or item.get("fixture_id") or item.get("event_id") or f"EVT_{idx+1:04d}"
                    norm_events.append({
                        "canonical_event_id": str(eid),
                        "sport": item.get("sport", "football"),
                        "competition": item.get("competition", "League"),
                        "home_team": item.get("home_team") or item.get("home", "Home"),
                        "away_team": item.get("away_team") or item.get("away", "Away"),
                        "event_start_time": item.get("event_start_time") or item.get("start_time", "2026-07-27T18:00:00Z"),
                        "discovery_status": item.get("discovery_status", "VERIFIED"),
                        "terminal_status": item.get("terminal_status", "PASS"),
                    })
            migrated["deduplicated_events"] = norm_events
            migrated["total_events"] = len(norm_events)
            migrated["source_s1_hash"] = migrated.get("source_s1_hash", "0" * 64)

    # Map S2
    elif target_type == "S2_TIPSTER_CONSENSUS":
        if "consensus_records" not in migrated:
            raw_c = migrated.get("consensus") or migrated.get("shortlist") or []
            norm_c = []
            for idx, item in enumerate(raw_c if isinstance(raw_c, list) else []):
                if isinstance(item, dict):
                    eid = item.get("canonical_event_id") or item.get("fixture_id") or item.get("candidate_id") or f"EVT_{idx+1:04d}"
                    norm_c.append({
                        "canonical_event_id": str(eid),
                        "tipster_count": item.get("tipster_count", 0),
                        "consensus_signal": item.get("consensus_signal"),
                        "confidence": float(item.get("confidence", 0.0)),
                        "opinion_summary": item.get("opinion_summary"),
                    })
            migrated["consensus_records"] = norm_c

    # Map S3
    elif target_type in {"S3_CALIBRATED_PROBABILITIES", "S3_DEEP_STATS"}:
        has_raw = any(k in migrated for k in ("analyses", "estimates", "candidates", "probability_estimates"))
        if has_raw:
            raw_p = migrated.get("analyses") or migrated.get("estimates") or migrated.get("candidates") or migrated.get("probability_estimates") or []
            norm_p = []
            for idx, item in enumerate(raw_p if isinstance(raw_p, list) else []):
                if isinstance(item, dict):
                    eid = _extract_event_id(item, idx)
                    norm_p.append({
                        "canonical_event_id": str(eid),
                        "market_family": item.get("market_family") or item.get("market", "result"),
                        "selection": item.get("selection") or item.get("pick", "home"),
                        "calibrated_probability": float(item.get("calibrated_probability") or item.get("model_fair_probability") or item.get("model_probability") or 0.50),
                        "uncertainty_margin": float(item.get("uncertainty_margin") or 0.02),
                        "model_id": item.get("model_id", "FOOTBALL_DIXON_COLES_ENG1_V1"),
                        "dataset_receipt_sha256": item.get("dataset_receipt_sha256", "a" * 64),
                        "calibration_report_sha256": item.get("calibration_report_sha256", "b" * 64),
                        "terminal_status": item.get("terminal_status") or item.get("status") or "PASS",
                    })
            migrated["probability_estimates"] = norm_p
            migrated["probabilities_count"] = len(norm_p)
            migrated["event_records"] = norm_p

    # Map S4
    elif target_type in {"S4_EXPECTED_VALUE_ESTIMATES", "S4_VALUATION_CANDIDATE_SET_V2"}:
        raw_v = migrated.get("candidates") or migrated.get("valuations") or migrated.get("valuation_candidates") or []
        norm_v = []
        for idx, item in enumerate(raw_v if isinstance(raw_v, list) else []):
            if isinstance(item, dict):
                eid = _extract_event_id(item, idx)
                fair_o = float(item.get("fair_odds") or item.get("model_fair_odds") or 2.0)
                min_o = float(item.get("minimum_acceptable_odds") or item.get("recommended_minimum_odds") or 2.1)
                norm_v.append({
                    "canonical_event_id": str(eid),
                    "market_family": item.get("market_family") or item.get("market", "result"),
                    "selection": item.get("selection") or item.get("pick", "home"),
                    "fair_odds": fair_o,
                    "ev_estimate": float(item.get("ev_estimate") or item.get("ev") or 0.0),
                    "minimum_acceptable_odds": min_o,
                    "status": item.get("status") or item.get("valuation_status") or "PASS",
                })
        migrated["valuation_candidates"] = norm_v
        migrated["candidates_valuated_count"] = len(norm_v)
        migrated["event_records"] = norm_v

    # Map S5
    elif target_type in {"S5_CONTEXT_MOTIVATION_RISK", "S5_CONTEXT_RISK_CANDIDATE_SET_V2"}:
        raw_ctx = migrated.get("candidates") or migrated.get("reviews") or migrated.get("context_reviews") or []
        norm_ctx = []
        for idx, item in enumerate(raw_ctx if isinstance(raw_ctx, list) else []):
            if isinstance(item, dict):
                eid = _extract_event_id(item, idx)
                norm_ctx.append({
                    "canonical_event_id": str(eid),
                    "sport": item.get("sport", "football"),
                    "motivation_score": float(item.get("motivation_score", 1.0)),
                    "risk_classification": item.get("risk_classification", "LOW"),
                    "context_notes": item.get("context_notes"),
                    "terminal_status": item.get("terminal_status") or item.get("status") or "PASS",
                })
        migrated["context_reviews"] = norm_ctx
        migrated["events_reviewed_count"] = len(norm_ctx)
        migrated["event_records"] = norm_ctx

    # Map S6
    elif target_type in {"S6_PORTFOLIO_REPEAT_GUARD", "S6_PORTFOLIO_REPEAT_GUARD_V2", "S6_REPEAT_LOSS_HANDOFF_V2"}:
        raw_f = migrated.get("accepted") or migrated.get("candidates") or migrated.get("filtered") or migrated.get("filtered_candidates") or []
        norm_f = []
        for idx, item in enumerate(raw_f if isinstance(raw_f, list) else []):
            if isinstance(item, dict):
                eid = _extract_event_id(item, idx)
                norm_f.append({
                    "canonical_event_id": str(eid),
                    "selection": item.get("selection") or item.get("pick", "home"),
                    "repeat_risk_flag": bool(item.get("repeat_risk_flag", False)),
                    "action": item.get("action", "ALLOW"),
                    "terminal_status": item.get("terminal_status") or item.get("status") or "PASS",
                })
        migrated["filtered_candidates"] = norm_f
        migrated["repeats_filtered_count"] = len(norm_f)
        migrated["event_records"] = norm_f

    # Map S7
    elif target_type in {"S7_APPROVED_PICKS", "S7_ANALYTICAL_APPROVAL_SET_V2", "S7_DECISION_GATE_REPORT", "S7_HARD_APPROVAL_GATE_V2"}:
        if not (isinstance(migrated.get("event_records"), list) and migrated["event_records"]):
            raw_picks = (
                migrated.get("approved_candidates")
                or migrated.get("analytical_approved")
                or migrated.get("priced_approved")
                or migrated.get("picks")
                or migrated.get("candidates")
                or []
            )
            norm_picks = []
            for idx, item in enumerate(raw_picks if isinstance(raw_picks, list) else []):
                if isinstance(item, dict):
                    eid = _extract_event_id(item, idx)
                    pick_id = item.get("pick_id") or item.get("candidate_id") or f"PICK_{idx+1:04d}"
                    prob = float(item.get("model_fair_probability") or item.get("calibrated_probability") or 0.50)
                    min_o = float(item.get("recommended_minimum_odds") or item.get("minimum_acceptable_odds") or 2.0)
                    norm_picks.append({
                        "pick_id": str(pick_id),
                        "canonical_event_id": str(eid),
                        "sport": item.get("sport", "football"),
                        "competition": item.get("competition", "League"),
                        "home_team": item.get("home_team") or item.get("home", "Home"),
                        "away_team": item.get("away_team") or item.get("away", "Away"),
                        "market_family": item.get("market_family") or item.get("market", "result"),
                        "selection": item.get("selection") or item.get("pick", "home"),
                        "line": item.get("line"),
                        "model_fair_probability": prob,
                        "recommended_minimum_odds": min_o,
                        "terminal_status": item.get("terminal_status") or item.get("status") or "PASS",
                    })
            migrated["approved_picks"] = norm_picks
            migrated["approved_candidate_count"] = len(norm_picks)
            migrated["event_records"] = norm_picks

    # Map S7b
    elif target_type == "S7B_SUPERBET_MANUAL_MAPPING":
        raw_sug = migrated.get("mapping_suggestions") or []
        norm_sug = []
        for idx, item in enumerate(raw_sug if isinstance(raw_sug, list) else []):
            if isinstance(item, dict):
                eid = _extract_event_id(item, idx)
                card_id = item.get("quote_card_id") or f"QC_{idx+1:04d}"
                src_id = item.get("source_candidate_id") or item.get("candidate_id") or "CAND_001"
                sel_id = item.get("selection_id") or src_id
                norm_sug.append({
                    "quote_card_id": str(card_id),
                    "source_candidate_id": str(src_id),
                    "canonical_event_id": str(eid),
                    "selection_id": str(sel_id),
                    "manual_operator": "SUPERBET",
                    "mapping_ambiguity": str(item.get("mapping_ambiguity") or "UNAMBIGUOUS"),
                    "visible_operator_market_name": item.get("visible_operator_market_name"),
                    "visible_operator_line": item.get("visible_operator_line"),
                    "human_entered_decimal_quote": item.get("human_entered_decimal_quote"),
                    "quote_as_of": item.get("quote_as_of"),
                    "operator_availability_asserted": bool(item.get("operator_availability_asserted", False)),
                    "executable_coupon": False,
                    "betting_valid": False,
                    "can_place_bet_now": False,
                })
        migrated["mapping_suggestions"] = norm_sug

        raw_ev = migrated.get("event_records") or raw_sug
        norm_ev = []
        for idx, item in enumerate(raw_ev if isinstance(raw_ev, list) else []):
            if isinstance(item, dict):
                eid = _extract_event_id(item, idx)
                norm_ev.append({
                    "canonical_event_id": str(eid),
                    "sport": item.get("sport", "football"),
                    "competition": item.get("competition", "League"),
                    "home_team": item.get("home_team") or item.get("home", "Home"),
                    "away_team": item.get("away_team") or item.get("away", "Away"),
                    "event_start_time": item.get("event_start_time") or item.get("start_time") or "2026-07-27T18:00:00Z",
                    "discovery_status": item.get("discovery_status", "VERIFIED"),
                    "terminal_status": item.get("terminal_status") or item.get("status") or "PASS",
                })
        migrated["event_records"] = norm_ev

    # Map S8
    elif target_type == "S8_SUPERBET_MANUAL_QUOTE_PACK":
        raw_qc = migrated.get("quote_cards") or []
        norm_qc = []
        for idx, item in enumerate(raw_qc if isinstance(raw_qc, list) else []):
            if isinstance(item, dict):
                eid = item.get("canonical_event_id") or item.get("fixture_id") or item.get("candidate_id") or item.get("selection_id") or f"EVT_{idx+1:04d}"
                card_id = item.get("quote_card_id") or f"QC_{idx+1:04d}"
                src_id = item.get("source_candidate_id") or item.get("candidate_id") or "CAND_001"
                sel_id = item.get("selection_id") or src_id
                norm_qc.append({
                    "quote_card_id": str(card_id),
                    "source_candidate_id": str(src_id),
                    "canonical_event_id": str(eid),
                    "selection_id": str(sel_id),
                    "manual_operator": "SUPERBET",
                    "minimum_acceptable_odds": item.get("minimum_acceptable_odds") or item.get("recommended_minimum_odds"),
                })
        migrated["quote_cards"] = norm_qc

        raw_ev = migrated.get("event_records") or raw_qc
        norm_ev = []
        for idx, item in enumerate(raw_ev if isinstance(raw_ev, list) else []):
            if isinstance(item, dict):
                eid = item.get("canonical_event_id") or item.get("fixture_id") or item.get("candidate_id") or item.get("selection_id") or f"EVT_{idx+1:04d}"
                norm_ev.append({
                    "canonical_event_id": str(eid),
                    "sport": item.get("sport", "football"),
                    "competition": item.get("competition", "League"),
                    "home_team": item.get("home_team") or item.get("home", "Home"),
                    "away_team": item.get("away_team") or item.get("away", "Away"),
                    "event_start_time": item.get("event_start_time") or item.get("start_time") or "2026-07-27T18:00:00Z",
                    "discovery_status": item.get("discovery_status", "VERIFIED"),
                    "terminal_status": item.get("terminal_status") or item.get("status") or "PASS",
                })
        migrated["event_records"] = norm_ev

    data.clear()
    data.update(migrated)
    return data


# Example migration adapter for S7b (v1 -> v2)
def _migrate_s7b_v1_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(payload)
    migrated["schema_version"] = 2
    if "operator_workflow" not in migrated:
        migrated["operator_workflow"] = "SUPERBET_MANUAL_BET_BUILDER"
    if "operator_availability_asserted" not in migrated:
        migrated["operator_availability_asserted"] = False
    return migrated


# Example migration adapter for S8 (v1 -> v2)
def _migrate_s8_v1_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(payload)
    migrated["schema_version"] = 2
    if "operator_workflow" not in migrated:
        migrated["operator_workflow"] = "SUPERBET_MANUAL_BET_BUILDER"
    if "idea_groups" not in migrated:
        migrated["idea_groups"] = []
    return migrated


register_migration_adapter("S7B_SUPERBET_MANUAL_MAPPING", 1, 2, _migrate_s7b_v1_to_v2)
register_migration_adapter("S8_SUPERBET_MANUAL_QUOTE_PACK", 1, 2, _migrate_s8_v1_to_v2)
