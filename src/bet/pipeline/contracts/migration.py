"""Explicit versioned migration adapters for step artifacts and legacy aliases."""
from __future__ import annotations

from typing import Any, Callable


class MigrationAdapterError(ValueError):
    """Raised when an explicit migration adapter fails or is missing required fields."""
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


def _get_field(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in item and item[k] not in (None, ""):
            return item[k]
    for nested_key in ("original_candidate", "candidate", "source_candidate", "analytical_candidate", "best_market"):
        nested = item.get(nested_key)
        if isinstance(nested, dict):
            for k in keys:
                if k in nested and nested[k] not in (None, ""):
                    return nested[k]
    if "canonical_event_id" in keys:
        if item.get("home_team") and item.get("away_team"):
            from bet.pipeline.event_accounting import canonical_event_id
            try:
                return canonical_event_id(item)
            except Exception:
                pass
    return None


def _require_field(item: dict[str, Any], keys: tuple[str, ...], field_name: str, target_type: str) -> Any:
    val = _get_field(item, keys)
    if val not in (None, ""):
        return val
    raise MigrationAdapterError(
        f"MIGRATION_FAILED: Missing required field '{field_name}' in item when adapting to {target_type}."
    )


def _opt_field(item: dict[str, Any], keys: tuple[str, ...], default: Any) -> Any:
    val = _get_field(item, keys)
    return val if val not in (None, "") else default


def adapt_legacy_artifact(data: dict[str, Any], target_type: str) -> dict[str, Any]:
    """Losslessly adapt a legacy artifact payload to canonical target contract structure.

    Fails with MigrationAdapterError if required decision-bearing values are missing.
    Does NOT fabricate missing event IDs, market families, selections, probabilities, risks, statuses, or quote cards.
    """
    if not isinstance(data, dict):
        return data

    actual_type = data.get("artifact_type") or data.get("artifact_kind") or ""
    if actual_type == target_type:
        return data

    key = (actual_type, target_type)
    adapter = _ALIAS_ADAPTERS.get(key)
    if adapter:
        return adapter(data)

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
        raise MigrationAdapterError(f"STEP_TYPE_MISMATCH: Unsupported or unapproved artifact_type '{actual_type}' for target '{target_type}'")

    migrated = dict(data)
    migrated["artifact_type"] = target_type

    if target_type == "S0_HISTORICAL_PNL":
        if "settled_records" not in migrated:
            migrated["settled_records"] = migrated.get("records") or migrated.get("settled_bets") or []

    elif target_type == "S1_FIXTURES_SHORTLIST":
        if "events" not in migrated:
            raw_events = migrated.get("shortlist") or migrated.get("fixtures") or migrated.get("discovered_events") or []
            norm_events = []
            for item in (raw_events if isinstance(raw_events, list) else []):
                if isinstance(item, dict):
                    eid = _require_field(item, ("canonical_event_id", "fixture_id", "event_id"), "canonical_event_id", target_type)
                    sport = _require_field(item, ("sport",), "sport", target_type)
                    comp = _require_field(item, ("competition", "league"), "competition", target_type)
                    home = _require_field(item, ("home_team", "home"), "home_team", target_type)
                    away = _require_field(item, ("away_team", "away"), "away_team", target_type)
                    start = _require_field(item, ("event_start_time", "start_time"), "event_start_time", target_type)
                    disc = _require_field(item, ("discovery_status",), "discovery_status", target_type)
                    term_st = _require_field(item, ("terminal_status", "status"), "terminal_status", target_type)
                    norm_events.append({
                        "canonical_event_id": str(eid),
                        "sport": str(sport),
                        "competition": str(comp),
                        "home_team": str(home),
                        "away_team": str(away),
                        "event_start_time": str(start),
                        "discovery_status": str(disc),
                        "terminal_status": str(term_st),
                    })
            migrated["events"] = norm_events
            migrated["discovered_event_count"] = len(norm_events)

    elif target_type == "S1E_CANONICAL_EVENT_UNIVERSE":
        if "deduplicated_events" not in migrated:
            raw_events = migrated.get("event_records") or migrated.get("events") or []
            norm_events = []
            for item in (raw_events if isinstance(raw_events, list) else []):
                if isinstance(item, dict):
                    eid = _require_field(item, ("canonical_event_id", "fixture_id", "event_id"), "canonical_event_id", target_type)
                    sport = _require_field(item, ("sport",), "sport", target_type)
                    comp = _require_field(item, ("competition", "league"), "competition", target_type)
                    home = _require_field(item, ("home_team", "home"), "home_team", target_type)
                    away = _require_field(item, ("away_team", "away"), "away_team", target_type)
                    start = _require_field(item, ("event_start_time", "start_time"), "event_start_time", target_type)
                    disc = _require_field(item, ("discovery_status",), "discovery_status", target_type)
                    term_st = _require_field(item, ("terminal_status", "status"), "terminal_status", target_type)
                    norm_events.append({
                        "canonical_event_id": str(eid),
                        "sport": str(sport),
                        "competition": str(comp),
                        "home_team": str(home),
                        "away_team": str(away),
                        "event_start_time": str(start),
                        "discovery_status": str(disc),
                        "terminal_status": str(term_st),
                    })
            migrated["deduplicated_events"] = norm_events
            migrated["total_events"] = len(norm_events)
            migrated["source_s1_hash"] = _require_field(migrated, ("source_s1_hash",), "source_s1_hash", target_type)

    elif target_type == "S2_TIPSTER_CONSENSUS":
        if "consensus_records" not in migrated or not migrated["consensus_records"]:
            raw_c = (
                migrated.get("consensus_records")
                or migrated.get("consensus")
                or migrated.get("shortlist")
                or migrated.get("candidates")
                or migrated.get("event_records")
                or []
            )
            norm_c = []
            for item in (raw_c if isinstance(raw_c, list) else []):
                if isinstance(item, dict):
                    eid = _require_field(item, ("canonical_event_id", "fixture_id", "candidate_id", "event_id"), "canonical_event_id", target_type)
                    term_st = _require_field(item, ("terminal_status", "status"), "terminal_status", target_type)
                    norm_c.append({
                        "canonical_event_id": str(eid),
                        "tipster_count": item.get("tipster_count", 0),
                        "consensus_signal": item.get("consensus_signal"),
                        "confidence": float(item.get("confidence", 0.0)),
                        "opinion_summary": item.get("opinion_summary"),
                        "terminal_status": str(term_st),
                    })
            migrated["consensus_records"] = norm_c

    elif target_type in {"S3_CALIBRATED_PROBABILITIES", "S3_DEEP_STATS"}:
        has_raw = any(k in migrated for k in ("analyses", "estimates", "candidates", "probability_estimates"))
        if has_raw:
            raw_p = migrated.get("analyses") or migrated.get("estimates") or migrated.get("candidates") or migrated.get("probability_estimates") or []
            norm_p = []
            for item in (raw_p if isinstance(raw_p, list) else []):
                if isinstance(item, dict):
                    eid = _require_field(item, ("canonical_event_id", "fixture_id", "event_id"), "canonical_event_id", target_type)
                    m_fam = _require_field(item, ("market_family", "market", "best_market"), "market_family", target_type)
                    sel = _opt_field(item, ("selection", "pick", "outcome", "selection_id", "recommended_selection", "side"), "ANALYSIS_ONLY")
                    prob = _opt_field(item, ("calibrated_probability", "model_fair_probability", "model_probability"), None)
                    model_id = _opt_field(item, ("model_id",), None)
                    ds_rec = _opt_field(item, ("dataset_receipt_sha256",), None)
                    cal_rec = _opt_field(item, ("calibration_report_sha256",), None)
                    term_st = _opt_field(item, ("terminal_status", "status", "analytical_status", "analysis_status"), "PASS")
                    norm_p.append({
                        "canonical_event_id": str(eid),
                        "market_family": str(m_fam),
                        "selection": str(sel),
                        "calibrated_probability": float(prob) if prob is not None else None,
                        "uncertainty_margin": float(item.get("uncertainty_margin", 0.02)),
                        "model_id": str(model_id) if model_id else None,
                        "dataset_receipt_sha256": str(ds_rec) if ds_rec else None,
                        "calibration_report_sha256": str(cal_rec) if cal_rec else None,
                        "terminal_status": str(term_st),
                    })
            migrated["probabilities"] = norm_p
            migrated["total_probabilities_derived"] = len(norm_p)
            migrated["event_records"] = norm_p

    elif target_type in {"S4_EXPECTED_VALUE_ESTIMATES", "S4_VALUATION_CANDIDATE_SET_V2"}:
        raw_v = migrated.get("candidates") or migrated.get("valuations") or migrated.get("valuation_candidates") or []
        norm_v = []
        for item in (raw_v if isinstance(raw_v, list) else []):
            if isinstance(item, dict):
                eid = _require_field(item, ("canonical_event_id", "fixture_id", "event_id"), "canonical_event_id", target_type)
                m_fam = _require_field(item, ("market_family", "market", "best_market"), "market_family", target_type)
                sel = _require_field(item, ("selection", "pick"), "selection", target_type)
                fair_o = _opt_field(item, ("fair_decimal_odds", "fair_odds", "model_fair_odds"), None)
                min_o = _opt_field(item, ("minimum_acceptable_operator_odds", "minimum_acceptable_odds", "recommended_minimum_odds"), None)
                ev_est = _opt_field(item, ("ev_estimate", "ev"), None)
                term_st = _require_field(item, ("status", "valuation_status", "terminal_status"), "status", target_type)
                norm_v.append({
                    "canonical_event_id": str(eid),
                    "market_family": str(m_fam),
                    "selection": str(sel),
                    "fair_odds": float(fair_o) if fair_o is not None else None,
                    "ev_estimate": float(ev_est) if ev_est is not None else None,
                    "minimum_acceptable_odds": float(min_o) if min_o is not None else None,
                    "status": str(term_st),
                })
        migrated["estimates"] = norm_v
        migrated["total_candidates_valued"] = len(norm_v)
        migrated["event_records"] = norm_v

    elif target_type in {"S5_CONTEXT_MOTIVATION_RISK", "S5_CONTEXT_RISK_CANDIDATE_SET_V2"}:
        raw_ctx = migrated.get("candidates") or migrated.get("reviews") or migrated.get("context_reviews") or []
        norm_ctx = []
        for item in (raw_ctx if isinstance(raw_ctx, list) else []):
            if isinstance(item, dict):
                eid = _require_field(item, ("canonical_event_id", "fixture_id", "event_id"), "canonical_event_id", target_type)
                sport = _require_field(item, ("sport",), "sport", target_type)
                mot_score = _opt_field(item, ("motivation_score",), 1.0)
                risk_cls = _require_field(item, ("risk_classification",), "risk_classification", target_type)
                term_st = _require_field(item, ("terminal_status", "status"), "terminal_status", target_type)
                norm_ctx.append({
                    "canonical_event_id": str(eid),
                    "sport": str(sport),
                    "motivation_score": float(mot_score),
                    "risk_classification": str(risk_cls),
                    "context_notes": item.get("context_notes"),
                    "terminal_status": str(term_st),
                })
        migrated["context_records"] = norm_ctx
        migrated["total_candidates_screened"] = len(norm_ctx)
        migrated["event_records"] = norm_ctx

    elif target_type in {"S6_PORTFOLIO_REPEAT_GUARD", "S6_PORTFOLIO_REPEAT_GUARD_V2", "S6_REPEAT_LOSS_HANDOFF_V2"}:
        raw_f = migrated.get("accepted") or migrated.get("candidates") or migrated.get("filtered") or migrated.get("filtered_candidates") or []
        norm_f = []
        for item in (raw_f if isinstance(raw_f, list) else []):
            if isinstance(item, dict):
                eid = _require_field(item, ("canonical_event_id", "fixture_id", "event_id"), "canonical_event_id", target_type)
                sel = _require_field(item, ("selection", "pick", "selection_id"), "selection", target_type)
                act = _require_field(item, ("action", "decision", "status"), "action", target_type)
                term_st = _require_field(item, ("terminal_status", "status", "action", "decision"), "terminal_status", target_type)
                norm_f.append({
                    "canonical_event_id": str(eid),
                    "selection": str(sel),
                    "repeat_risk_flag": bool(item.get("repeat_risk_flag", False)),
                    "action": str(act),
                    "terminal_status": str(term_st),
                })
        migrated["guarded_records"] = norm_f
        migrated["total_candidates_guarded"] = len(norm_f)
        migrated["event_records"] = norm_f

    return migrated


def _migrate_s7b_v1_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(payload)
    migrated["schema_version"] = 2
    if "operator_workflow" not in migrated:
        migrated["operator_workflow"] = "SUPERBET_MANUAL_BET_BUILDER"
    if "operator_availability_asserted" not in migrated:
        migrated["operator_availability_asserted"] = False
    return migrated


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
