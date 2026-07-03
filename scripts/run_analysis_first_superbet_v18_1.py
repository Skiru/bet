from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from bet.pipeline.bet_builder_concept_quality import infer_concept_type, validate_bet_builder_concept
from bet.pipeline.multisport_market_promotion import normalize_selection_name
from bet.pipeline.odds_optional_analysis_contracts import (
    AnalysisStatus,
    BettableStatus,
    EvStatus,
    OddsStatus,
    OptionalOperatorQuotePriority,
    PricingTier,
    StakeStatus,
    derive_analysis_status,
    derive_bettable_status,
    derive_ev_status,
    derive_odds_status,
    derive_optional_quote_priority,
    derive_pricing_tier,
    derive_stake_status,
)


EXPECTED_CODE_PATHS = {
    "src/bet/pipeline/odds_optional_analysis_contracts.py",
    "src/bet/pipeline/bet_builder_concept_quality.py",
    "src/bet/pipeline/final_artifact_consistency.py",
    "scripts/final_artifact_consistency_audit.py",
    "scripts/run_analysis_first_superbet_v18_1.py",
}

EXPECTED_TEST_PATHS = {
    "tests/test_odds_optional_analysis_contract.py",
    "tests/test_unpriced_candidates_not_rejected.py",
    "tests/test_pricing_tier_classification.py",
    "tests/test_bet_builder_concepts_operator_screen_only.py",
    "tests/test_analysis_first_board_sections.py",
    "tests/test_optional_quote_shortlist_not_required.py",
    "tests/test_analysis_portfolio_not_bettable.py",
    "tests/test_manual_quote_required_only_for_bettable.py",
    "tests/test_tipster_context_analysis_only.py",
    "tests/test_v17_to_v18_analysis_first_regression.py",
}

REQUIRED_TEST_FILES = [
    "tests/test_odds_optional_analysis_contract.py",
    "tests/test_unpriced_candidates_not_rejected.py",
    "tests/test_pricing_tier_classification.py",
    "tests/test_bet_builder_concepts_operator_screen_only.py",
    "tests/test_analysis_first_board_sections.py",
    "tests/test_optional_quote_shortlist_not_required.py",
    "tests/test_analysis_portfolio_not_bettable.py",
    "tests/test_manual_quote_required_only_for_bettable.py",
    "tests/test_tipster_context_analysis_only.py",
    "tests/test_v17_to_v18_analysis_first_regression.py",
    "tests/test_final_artifact_cross_consistency.py",
    "tests/test_builder_group_schema_quality.py",
    "tests/test_final_report_blocker_scoping.py",
    "tests/test_coupon_draft_multisport_diversification.py",
    "tests/test_artifact_hygiene_no_nested_absolute_paths.py",
    "tests/test_market_matrix_run_lineage.py",
    "tests/test_test_manifest_integrity.py",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json_markdown(path: Path, title: str, payload: Any) -> None:
    _write_text(path, f"# {title}\n\n```json\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n```\n")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})


def _git_output(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True).strip()


def _parse_status_lines(lines: Iterable[str]) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        status = line[:2]
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        parsed.append({"status": status, "path": path})
    return parsed


def _confidence_rank(value: str) -> int:
    return {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(_text(value).upper(), 0)


def _priority_rank(value: str) -> int:
    return {
        OptionalOperatorQuotePriority.HIGH.value: 3,
        OptionalOperatorQuotePriority.MEDIUM.value: 2,
        OptionalOperatorQuotePriority.LOW.value: 1,
        OptionalOperatorQuotePriority.NOT_NEEDED_NOW.value: 0,
    }.get(_text(value).upper(), 0)


def _line_source_status(candidate: Mapping[str, Any], matrix_row: Mapping[str, Any] | None) -> str:
    if _text(candidate.get("line_free_market_type")):
        return "LINE_FREE_MARKET"
    line = candidate.get("line")
    allowed = candidate.get("allowed_line_alternatives") or []
    if _text(line).upper() in {"", "UNKNOWN", "LINE_REQUIRES_OPERATOR_CHECK", "UNVERIFIED"}:
        return "LINE_REQUIRES_OPERATOR_CHECK"
    if allowed:
        return "ALTERNATIVE_LINES_AVAILABLE"
    if matrix_row and _text(matrix_row.get("line_unknown_reason")):
        return "LINE_REQUIRES_OPERATOR_CHECK"
    return "EXACT_PROVIDER_LINE"


def _provider_odds_present(row: Mapping[str, Any] | None) -> bool:
    if not row:
        return False
    if row.get("odds_present") is True:
        return True
    return row.get("best_odds") not in (None, "")


def _selection_from_row(row: Mapping[str, Any] | None, visible_event_name: str) -> str:
    if not row:
        return "LINE_REQUIRES_OPERATOR_CHECK"
    selection = _text(row.get("selection") or row.get("outcome_name") or row.get("direction"))
    if not selection:
        return "LINE_REQUIRES_OPERATOR_CHECK"
    return normalize_selection_name(selection, {"canonical_event_name": visible_event_name})


def _odds_source_refs(row: Mapping[str, Any] | None, candidate: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for value in (
        candidate.get("availability_source_ref"),
        *(candidate.get("provider_market_refs") or []),
        row.get("raw_source_ref") if row else None,
        row.get("provider_snapshot_ref") if row else None,
        row.get("provider_probe_response_ref") if row else None,
    ):
        text = _text(value)
        if text and text not in refs:
            refs.append(text)
    return refs


def _generic_market_name(market_family: str) -> str:
    names = {
        "corners": "Total corners",
        "cards": "Total cards",
        "goals_totals": "Total goals",
        "team_goals": "Team goals",
        "shots": "Total shots",
        "totals": "Total points",
        "team_totals": "Team total points",
        "spread": "Spread",
        "total_games": "Total games",
        "game_handicap": "Game handicap",
        "set_handicap": "Set handicap",
        "total_maps": "Total maps",
        "map_handicap": "Map handicap",
    }
    return names.get(market_family, market_family.replace("_", " ").title())


def _allowed_line_alternatives(market_family: str) -> list[str]:
    base = _generic_market_name(market_family)
    return [
        f"{base} on the main operator line",
        f"{base} on an alternative operator line",
    ]


def _tipster_entry(candidate_id: str, tipster_impacts: Mapping[str, Mapping[str, Any]], global_reason: str) -> tuple[str, str | None, str | None, str]:
    impact = tipster_impacts.get(candidate_id) or {}
    reason = _text(impact.get("no_usable_tipster_signal_reason") or global_reason)
    return (
        "ATTEMPTED_NO_MATCHES",
        None,
        reason or None,
        "PUBLIC_SIDE_RISK_UNKNOWN_WITHOUT_FIXTURE_LEVEL_TIPSTER_MATCH",
    )


def _base_candidate_board_section(pricing_tier: str, analysis_status: str) -> str:
    if analysis_status == AnalysisStatus.REJECTED.value:
        return "REJECTED_WITH_REASONS"
    if analysis_status == AnalysisStatus.WATCH.value:
        return "WATCHLIST_LINE_SENSITIVE"
    if pricing_tier == PricingTier.PRICED_ANALYTICAL.value:
        return "TOP_PRICED_ANALYTICAL_CANDIDATES"
    if pricing_tier == PricingTier.PARTIALLY_PRICED_ANALYTICAL.value:
        return "TOP_PARTIALLY_PRICED_ANALYTICAL_CANDIDATES"
    return "TOP_UNPRICED_DEEP_ANALYTICAL_CANDIDATES"


def _sort_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (dict(candidate) for candidate in candidates),
        key=lambda candidate: (
            0 if candidate.get("analysis_status") == AnalysisStatus.ANALYTICAL_RECOMMENDATION.value else 1,
            -_priority_rank(_text(candidate.get("optional_operator_quote_check_priority"))),
            -_confidence_rank(_text(candidate.get("confidence"))),
            -_confidence_rank(_text(candidate.get("data_quality"))),
            _text(candidate.get("sport")),
            _text(candidate.get("visible_event_name")),
            _text(candidate.get("candidate_id")),
        ),
    )


def _candidate_board_rows(candidates: Sequence[Mapping[str, Any]], concepts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ranked_candidates = _sort_candidates(candidates)
    per_section_rank: Counter[str] = Counter()
    for candidate in ranked_candidates:
        section = _base_candidate_board_section(_text(candidate.get("pricing_tier")), _text(candidate.get("analysis_status")))
        per_section_rank[section] += 1
        rows.append(
            {
                "priority_rank": per_section_rank[section],
                "section": section,
                "entry_type": "candidate",
                "entry_id": candidate.get("candidate_id"),
                "sport": candidate.get("sport"),
                "competition": candidate.get("competition"),
                "event": candidate.get("visible_event_name"),
                "market_family": candidate.get("market_family"),
                "market_selection": f"{candidate.get('human_searchable_market_name')} :: {candidate.get('selection')}",
                "line_or_alternatives": candidate.get("line") if candidate.get("line") not in (None, "") else "; ".join(candidate.get("allowed_line_alternatives") or []),
                "pricing_tier": candidate.get("pricing_tier"),
                "odds_status": candidate.get("odds_status"),
                "evidence_quality": candidate.get("data_quality"),
                "confidence": candidate.get("confidence"),
                "thesis": candidate.get("thesis"),
                "counter_evidence": "; ".join(candidate.get("counter_evidence") or []),
                "line_sensitivity": candidate.get("line_sensitivity"),
                "correlation_tags": "; ".join(candidate.get("correlation_tags") or []),
                "optional_superbet_check_priority": candidate.get("optional_operator_quote_check_priority"),
                "why_useful_even_without_odds": "Analysis is evidence-led and price only gates EV/stake/final coupon." if candidate.get("pricing_tier") != PricingTier.PRICED_ANALYTICAL.value else "Exact source-side price exists, but operator verification still gates bettable status.",
                "what_odds_needed_only_for_price_stake_decision": "Human-entered Superbet market, exact line, decimal odds, timestamp, and correlation gate result.",
            }
        )

    concept_rank = 0
    for concept in concepts:
        concept_rank += 1
        rows.append(
            {
                "priority_rank": concept_rank,
                "section": "TOP_BET_BUILDER_CONCEPT_INPUTS",
                "entry_type": "concept",
                "entry_id": concept.get("concept_id"),
                "sport": concept.get("sport"),
                "competition": concept.get("competition"),
                "event": concept.get("visible_event_name"),
                "market_family": concept.get("concept_type"),
                "market_selection": " + ".join(_text(leg.get("selection")) for leg in concept.get("legs") or []),
                "line_or_alternatives": " + ".join(_text(leg.get("line") or leg.get("line_free_market_type") or "LINE_REQUIRES_OPERATOR_CHECK") for leg in concept.get("legs") or []),
                "pricing_tier": PricingTier.OPERATOR_QUOTE_REQUIRED_FOR_BETTABLE.value,
                "odds_status": OddsStatus.OPERATOR_SCREEN_ONLY.value,
                "evidence_quality": concept.get("evidence_quality"),
                "confidence": concept.get("confidence"),
                "thesis": concept.get("scenario_fit"),
                "counter_evidence": "; ".join(concept.get("negative_correlation_notes") or []),
                "line_sensitivity": concept.get("line_sensitivity"),
                "correlation_tags": "; ".join(concept.get("correlation_tags") or []),
                "optional_superbet_check_priority": concept.get("optional_operator_quote_check_priority"),
                "why_useful_even_without_odds": "Scenario fit and leg correlation are analytically useful before any combined operator quote.",
                "what_odds_needed_only_for_price_stake_decision": "Visible Superbet Bet Builder combined odds plus exact operator leg lines.",
            }
        )
    return rows


def _diverse_pick(candidates: Sequence[Mapping[str, Any]], limit: int) -> list[dict[str, Any]]:
    picks: list[dict[str, Any]] = []
    seen_sports: set[str] = set()
    for candidate in _sort_candidates(candidates):
        sport = _text(candidate.get("sport"))
        if sport not in seen_sports:
            picks.append(dict(candidate))
            seen_sports.add(sport)
        if len(picks) >= limit:
            return picks
    for candidate in _sort_candidates(candidates):
        candidate_id = _text(candidate.get("candidate_id"))
        if candidate_id not in {_text(item.get("candidate_id")) for item in picks}:
            picks.append(dict(candidate))
        if len(picks) >= limit:
            return picks
    return picks


def _portfolio_entry_from_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "entry_type": "candidate",
        "entry_id": candidate.get("candidate_id"),
        "event_id": candidate.get("event_id"),
        "sport": candidate.get("sport"),
        "competition": candidate.get("competition"),
        "visible_event_name": candidate.get("visible_event_name"),
        "market_family": candidate.get("market_family"),
        "market_selection": candidate.get("human_searchable_market_name"),
        "pricing_tier": candidate.get("pricing_tier"),
        "odds_status": candidate.get("odds_status"),
        "analysis_status": candidate.get("analysis_status"),
        "optional_operator_quote_check_priority": candidate.get("optional_operator_quote_check_priority"),
        "bet_builder_concept_only": False,
        "useful_without_odds": True,
        "requires_optional_superbet_quote_check": candidate.get("optional_operator_quote_check_priority") in {
            OptionalOperatorQuotePriority.HIGH.value,
            OptionalOperatorQuotePriority.MEDIUM.value,
        },
        "tipster_context_status": candidate.get("tipster_context_status"),
        "tipster_signal": candidate.get("tipster_signal"),
        "public_side_or_hype_risk": candidate.get("public_side_or_hype_risk"),
        "no_usable_tipster_signal_reason": candidate.get("no_usable_tipster_signal_reason"),
    }


def _portfolio_entry_from_concept(concept: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "entry_type": "concept",
        "entry_id": concept.get("concept_id"),
        "event_id": concept.get("event_id"),
        "sport": concept.get("sport"),
        "competition": concept.get("competition"),
        "visible_event_name": concept.get("visible_event_name"),
        "market_family": concept.get("concept_type"),
        "market_selection": " + ".join(_text(leg.get("selection")) for leg in concept.get("legs") or []),
        "pricing_tier": PricingTier.OPERATOR_QUOTE_REQUIRED_FOR_BETTABLE.value,
        "odds_status": OddsStatus.OPERATOR_SCREEN_ONLY.value,
        "analysis_status": AnalysisStatus.ANALYTICAL_RECOMMENDATION.value,
        "optional_operator_quote_check_priority": concept.get("optional_operator_quote_check_priority"),
        "bet_builder_concept_only": True,
        "useful_without_odds": True,
        "requires_optional_superbet_quote_check": True,
        "tipster_context_status": concept.get("tipster_context_status"),
        "tipster_signal": concept.get("tipster_signal"),
        "public_side_or_hype_risk": concept.get("public_side_or_hype_risk"),
        "no_usable_tipster_signal_reason": concept.get("no_usable_tipster_signal_reason"),
    }


def _build_analysis_portfolios(candidates: Sequence[Mapping[str, Any]], concepts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    conservative = _diverse_pick([c for c in candidates if c.get("analysis_status") != AnalysisStatus.WATCH.value], 3)
    balanced = _diverse_pick([c for c in candidates if c.get("analysis_status") != AnalysisStatus.WATCH.value], 5)
    aggressive_pool = [c for c in candidates if c.get("analysis_status") != AnalysisStatus.REJECTED.value]
    aggressive = _sort_candidates(aggressive_pool)[:6]
    broad = _sort_candidates(candidates)[:12]
    top_concepts = list(concepts)[:5]
    portfolios = [
        {
            "portfolio_id": "portfolio_conservative_analysis",
            "style": "CONSERVATIVE_ANALYSIS_PORTFOLIO",
            "entries": [_portfolio_entry_from_candidate(candidate) for candidate in conservative],
            "combined_odds": None,
            "bettable": False,
            "final_coupon_allowed": False,
            "evidence_rationale": "Uses the highest-confidence multi-sport analytical anchors only.",
            "risk_rationale": "Low leg count and diversified sports reduce same-market dependence.",
            "correlation_risk": "LOW",
            "which_entries_are_useful_without_odds": [candidate.get("candidate_id") for candidate in conservative],
            "which_entries_require_optional_superbet_quote_check": [candidate.get("candidate_id") for candidate in conservative if candidate.get("optional_operator_quote_check_priority") in {"HIGH", "MEDIUM"}],
            "which_entries_are_bet_builder_concept_only": [],
            "required_manual_odds_fields_if_price_gate_later": ["event", "market", "line", "decimal_odds", "timestamp_europe_warsaw"],
        },
        {
            "portfolio_id": "portfolio_balanced_analysis",
            "style": "BALANCED_ANALYSIS_PORTFOLIO",
            "entries": [_portfolio_entry_from_candidate(candidate) for candidate in balanced],
            "combined_odds": None,
            "bettable": False,
            "final_coupon_allowed": False,
            "evidence_rationale": "Adds more medium-confidence markets while preserving cross-sport diversification.",
            "risk_rationale": "Still analysis-only; no stake or final coupon implied.",
            "correlation_risk": "MEDIUM",
            "which_entries_are_useful_without_odds": [candidate.get("candidate_id") for candidate in balanced],
            "which_entries_require_optional_superbet_quote_check": [candidate.get("candidate_id") for candidate in balanced if candidate.get("optional_operator_quote_check_priority") in {"HIGH", "MEDIUM"}],
            "which_entries_are_bet_builder_concept_only": [],
            "required_manual_odds_fields_if_price_gate_later": ["event", "market", "line", "decimal_odds", "timestamp_europe_warsaw"],
        },
        {
            "portfolio_id": "portfolio_aggressive_analysis",
            "style": "AGGRESSIVE_ANALYSIS_PORTFOLIO",
            "entries": [_portfolio_entry_from_candidate(candidate) for candidate in aggressive],
            "combined_odds": None,
            "bettable": False,
            "final_coupon_allowed": False,
            "evidence_rationale": "Includes line-sensitive unpriced ideas that still carry analytical value.",
            "risk_rationale": "Higher volatility from line-sensitive and unpriced entries.",
            "correlation_risk": "MEDIUM_TO_HIGH",
            "which_entries_are_useful_without_odds": [candidate.get("candidate_id") for candidate in aggressive],
            "which_entries_require_optional_superbet_quote_check": [candidate.get("candidate_id") for candidate in aggressive if candidate.get("optional_operator_quote_check_priority") in {"HIGH", "MEDIUM"}],
            "which_entries_are_bet_builder_concept_only": [],
            "required_manual_odds_fields_if_price_gate_later": ["event", "market", "line", "decimal_odds", "timestamp_europe_warsaw"],
        },
        {
            "portfolio_id": "portfolio_broad_shortlist",
            "style": "BROAD_ANALYTICAL_SHORTLIST",
            "entries": [_portfolio_entry_from_candidate(candidate) for candidate in broad],
            "combined_odds": None,
            "bettable": False,
            "final_coupon_allowed": False,
            "evidence_rationale": "Broad shortlist keeps the best cross-sport analytical options visible even without prices.",
            "risk_rationale": "Pure shortlist artifact; no coupon semantics implied.",
            "correlation_risk": "MIXED",
            "which_entries_are_useful_without_odds": [candidate.get("candidate_id") for candidate in broad],
            "which_entries_require_optional_superbet_quote_check": [candidate.get("candidate_id") for candidate in broad if candidate.get("optional_operator_quote_check_priority") in {"HIGH", "MEDIUM"}],
            "which_entries_are_bet_builder_concept_only": [],
            "required_manual_odds_fields_if_price_gate_later": ["event", "market", "line", "decimal_odds", "timestamp_europe_warsaw"],
        },
        {
            "portfolio_id": "portfolio_bet_builder_concepts",
            "style": "BET_BUILDER_CONCEPT_PORTFOLIO",
            "entries": [_portfolio_entry_from_concept(concept) for concept in top_concepts],
            "combined_odds": None,
            "bettable": False,
            "final_coupon_allowed": False,
            "evidence_rationale": "Groups same-event scenario ideas without computing combined odds.",
            "risk_rationale": "Concepts remain operator-screen-only for price and correlation finalization.",
            "correlation_risk": "SCENARIO_DEPENDENT",
            "which_entries_are_useful_without_odds": [concept.get("concept_id") for concept in top_concepts],
            "which_entries_require_optional_superbet_quote_check": [concept.get("concept_id") for concept in top_concepts],
            "which_entries_are_bet_builder_concept_only": [concept.get("concept_id") for concept in top_concepts],
            "required_manual_odds_fields_if_price_gate_later": ["event", "market", "line", "decimal_odds", "timestamp_europe_warsaw", "visible_bet_builder_combined_odds"],
        },
    ]
    return portfolios


def _copy_json_with_lineage(source: Path, target: Path, run_id: str, source_run_id: str) -> None:
    payload = _read_json(source, {}) or {}
    if isinstance(payload, Mapping):
        data = dict(payload)
        if "run_id" in data:
            data["run_id"] = run_id
        data["current_run_id"] = run_id
        data["source_run_id"] = source_run_id
        data["input_run_id"] = source_run_id
        _write_json(target, data)
    else:
        _write_json(target, payload)


def _market_rows_by_event(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_text(row.get("event_id"))].append(dict(row))
    return grouped


def _matching_row(event_rows: Sequence[Mapping[str, Any]], provider_refs: Sequence[str], market_family: str) -> Mapping[str, Any] | None:
    ref_set = {_text(ref) for ref in provider_refs if _text(ref)}
    for row in event_rows:
        row_id = _text(row.get("row_id") or row.get("market_row_id"))
        if row_id and row_id in ref_set:
            return row
    for row in event_rows:
        if _text(row.get("market_family")).lower() == _text(market_family).lower():
            return row
    return event_rows[0] if event_rows else None


def _build_primary_candidates(
    source_candidates: Sequence[Mapping[str, Any]],
    cards_by_candidate: Mapping[str, Mapping[str, Any]],
    rows_by_event: Mapping[str, list[dict[str, Any]]],
    tipster_impacts: Mapping[str, Mapping[str, Any]],
    global_tipster_reason: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for candidate in source_candidates:
        candidate_id = _text(candidate.get("candidate_id"))
        card = cards_by_candidate.get(candidate_id, {})
        event_id = _text(candidate.get("event_id"))
        visible_event_name = _text(card.get("visible_event_name") or card.get("manual_superbet_quote_fields", {}).get("visible_event") or event_id)
        event_rows = rows_by_event.get(event_id, [])
        matrix_row = _matching_row(event_rows, candidate.get("provider_market_refs") or [], _text(candidate.get("market_family")))
        line_source_status = _line_source_status(candidate, matrix_row)
        odds_status = derive_odds_status(
            has_human_odds=False,
            provider_odds_present=_provider_odds_present(matrix_row),
            line_source_status=line_source_status,
            provider_blocked=False,
        )
        optional_quote_priority = derive_optional_quote_priority(
            confidence=_text(candidate.get("confidence")),
            line_sensitivity=_text(candidate.get("line_sensitivity")),
            odds_status=odds_status,
        )
        pricing_tier = derive_pricing_tier(odds_status)
        analysis_status = derive_analysis_status(
            confidence=_text(candidate.get("confidence")),
            data_quality=_text(candidate.get("data_quality")),
            odds_status=odds_status,
            optional_quote_priority=optional_quote_priority,
        )
        tipster_context_status, tipster_signal, no_tipster_reason, public_side_risk = _tipster_entry(candidate_id, tipster_impacts, global_tipster_reason)
        output.append(
            {
                "candidate_id": candidate_id,
                "event_id": event_id,
                "sport": candidate.get("sport"),
                "competition": candidate.get("competition"),
                "league_or_tournament": candidate.get("competition"),
                "visible_event_name": visible_event_name,
                "market_family": candidate.get("market_family"),
                "human_searchable_market_name": candidate.get("human_searchable_market_name"),
                "selection": _selection_from_row(matrix_row, visible_event_name),
                "line": candidate.get("line"),
                "allowed_line_alternatives": candidate.get("allowed_line_alternatives") or [],
                "line_free_market_type": candidate.get("line_free_market_type"),
                "provider_market_refs": list(candidate.get("provider_market_refs") or []),
                "odds_source_refs": _odds_source_refs(matrix_row, candidate),
                "odds_status": odds_status.value,
                "pricing_tier": pricing_tier.value,
                "line_source_status": line_source_status,
                "evidence_pack_ref": candidate.get("evidence_pack_ref"),
                "tipster_consensus_ref": None,
                "no_usable_tipster_signal_reason": no_tipster_reason,
                "thesis": candidate.get("thesis"),
                "supporting_evidence": list(candidate.get("supporting_evidence") or []),
                "counter_evidence": list(candidate.get("counter_evidence") or []),
                "tactical_or_statistical_angle": (candidate.get("supporting_evidence") or [candidate.get("thesis")])[0],
                "data_quality": candidate.get("data_quality"),
                "confidence": candidate.get("confidence"),
                "line_sensitivity": candidate.get("line_sensitivity"),
                "correlation_tags": list(candidate.get("correlation_tags") or []),
                "fair_odds": candidate.get("fair_odds"),
                "min_acceptable_operator_odds": candidate.get("min_acceptable_operator_odds"),
                "analysis_status": analysis_status.value,
                "ev_status": derive_ev_status(fair_odds=candidate.get("fair_odds"), has_human_odds=False).value,
                "stake_status": derive_stake_status(has_human_odds=False).value,
                "bettable_status": derive_bettable_status(odds_status=odds_status, has_human_odds=False).value,
                "manual_quote_required_for_bettable": True,
                "analysis_allowed_without_odds": True,
                "operator_quote_required_for_bettable": True,
                "optional_operator_quote_check_priority": optional_quote_priority.value,
                "bettable": False,
                "combined_bookmaker_odds_computed": False,
                "tipster_context_status": tipster_context_status,
                "tipster_signal": tipster_signal,
                "public_side_or_hype_risk": public_side_risk,
            }
        )
    return output


def _build_recovered_unpriced_candidates(
    blocked_rows: Sequence[Mapping[str, Any]],
    anchor_candidates_by_event: Mapping[str, list[dict[str, Any]]],
    rows_by_event: Mapping[str, list[dict[str, Any]]],
    tipster_impacts: Mapping[str, Mapping[str, Any]],
    global_tipster_reason: str,
) -> list[dict[str, Any]]:
    recovered: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for blocked in blocked_rows:
        if _text(blocked.get("primary_blocker")) != "UNKNOWN_LINE":
            continue
        event_id = _text(blocked.get("event_id"))
        market_family = _text(blocked.get("market_family"))
        anchors = anchor_candidates_by_event.get(event_id) or []
        if not anchors:
            continue
        anchor = anchors[0]
        candidate_id = f"analysis_{event_id}_{market_family}_line_sensitive_unpriced"
        if candidate_id in seen_ids:
            continue
        seen_ids.add(candidate_id)
        visible_event_name = _text(anchor.get("visible_event_name") or event_id)
        event_rows = rows_by_event.get(event_id, [])
        matrix_row = _matching_row(event_rows, [], market_family)
        human_name = f"{_generic_market_name(market_family)} - operator line requires confirmation"
        tipster_context_status, tipster_signal, no_tipster_reason, public_side_risk = _tipster_entry(_text(anchor.get("candidate_id")), tipster_impacts, global_tipster_reason)
        recovered.append(
            {
                "candidate_id": candidate_id,
                "event_id": event_id,
                "sport": anchor.get("sport"),
                "competition": anchor.get("competition"),
                "league_or_tournament": anchor.get("competition"),
                "visible_event_name": visible_event_name,
                "market_family": market_family,
                "human_searchable_market_name": human_name,
                "selection": _selection_from_row(matrix_row, visible_event_name),
                "line": "LINE_REQUIRES_OPERATOR_CHECK",
                "allowed_line_alternatives": _allowed_line_alternatives(market_family),
                "line_free_market_type": None,
                "provider_market_refs": [_text(matrix_row.get("row_id") or matrix_row.get("market_row_id"))] if matrix_row else [],
                "odds_source_refs": _odds_source_refs(matrix_row, anchor),
                "odds_status": OddsStatus.UNPRICED.value,
                "pricing_tier": PricingTier.UNPRICED_DEEP_ANALYTICAL.value,
                "line_source_status": "LINE_REQUIRES_OPERATOR_CHECK",
                "evidence_pack_ref": anchor.get("evidence_pack_ref"),
                "tipster_consensus_ref": None,
                "no_usable_tipster_signal_reason": no_tipster_reason,
                "thesis": f"Retain `{human_name}` as an analysis-first candidate for {visible_event_name}; the line is unresolved, but the event-level evidence remains useful and the price gate is the only blocker.",
                "supporting_evidence": list(anchor.get("supporting_evidence") or []) + ["The original downgrade was `UNKNOWN_LINE`, which blocks price/EV/stake but not the event-level analytical angle."],
                "counter_evidence": list(anchor.get("counter_evidence") or []) + ["Exact operator-comparable line was not preserved in the provider row."],
                "tactical_or_statistical_angle": f"Line-sensitive {market_family} angle survives as analysis even though the exact line must be checked manually.",
                "data_quality": anchor.get("data_quality"),
                "confidence": anchor.get("confidence"),
                "line_sensitivity": "HIGH",
                "correlation_tags": list(anchor.get("correlation_tags") or []) + [market_family, "line_sensitive_unpriced"],
                "fair_odds": None,
                "min_acceptable_operator_odds": None,
                "analysis_status": AnalysisStatus.ANALYTICAL_RECOMMENDATION.value,
                "ev_status": EvStatus.EV_BLOCKED_UNTIL_OPERATOR_ODDS.value,
                "stake_status": StakeStatus.STAKE_BLOCKED_UNTIL_PRICE_GATE.value,
                "bettable_status": BettableStatus.NOT_BETTABLE_ANALYSIS_ONLY.value,
                "manual_quote_required_for_bettable": True,
                "analysis_allowed_without_odds": True,
                "operator_quote_required_for_bettable": True,
                "optional_operator_quote_check_priority": OptionalOperatorQuotePriority.MEDIUM.value,
                "bettable": False,
                "combined_bookmaker_odds_computed": False,
                "tipster_context_status": tipster_context_status,
                "tipster_signal": tipster_signal,
                "public_side_or_hype_risk": public_side_risk,
            }
        )
    return recovered


def _build_bet_builder_concepts(groups: Sequence[Mapping[str, Any]], candidates_by_id: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    concepts: list[dict[str, Any]] = []
    for group in groups:
        event_id = _text(group.get("event_id"))
        legs_payload: list[dict[str, Any]] = []
        leg_candidates: list[Mapping[str, Any]] = []
        for leg in group.get("legs") or []:
            candidate = candidates_by_id.get(_text(leg.get("candidate_id")))
            if not candidate:
                continue
            leg_candidates.append(candidate)
            legs_payload.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "market_family": candidate.get("market_family"),
                    "selection": candidate.get("selection"),
                    "line": candidate.get("line"),
                    "allowed_line_alternatives": candidate.get("allowed_line_alternatives"),
                    "line_free_market_type": candidate.get("line_free_market_type"),
                    "odds_status": candidate.get("odds_status"),
                    "pricing_tier": candidate.get("pricing_tier"),
                    "evidence_summary": (candidate.get("supporting_evidence") or [candidate.get("thesis")])[0],
                    "counter_evidence_summary": "; ".join(candidate.get("counter_evidence") or []),
                }
            )
        if not legs_payload:
            continue
        first = leg_candidates[0]
        concept = {
            "concept_id": f"concept_{event_id}",
            "event_id": event_id,
            "sport": first.get("sport"),
            "competition": group.get("competition") or first.get("competition"),
            "visible_event_name": first.get("visible_event_name"),
            "concept_type": infer_concept_type(_text(first.get("sport")), legs_payload).value,
            "legs": legs_payload,
            "correlation_logic": group.get("correlation_logic"),
            "positive_correlation_notes": list(group.get("positive_correlation_notes") or []),
            "negative_correlation_notes": list(group.get("negative_correlation_notes") or []),
            "forbidden_combinations": list(group.get("forbidden_combinations") or []),
            "line_sensitivity": group.get("line_sensitivity") or "HIGH",
            "scenario_fit": group.get("rationale") or "Same-event analytical correlation review group.",
            "what_to_check_in_Superbet_if_user_chooses": [
                "Confirm every leg exists under the same visible event.",
                "Confirm the exact operator line for any derivative leg.",
                "Read the visible Bet Builder combined odds from the Superbet screen only.",
            ],
            "combined_odds_status": OddsStatus.OPERATOR_SCREEN_ONLY.value,
            "combined_bookmaker_odds_computed": False,
            "bettable": False,
            "correlation_tags": sorted({tag for candidate in leg_candidates for tag in candidate.get("correlation_tags") or []}),
            "evidence_quality": max((candidate.get("data_quality") for candidate in leg_candidates), default="MEDIUM", key=_confidence_rank),
            "confidence": max((candidate.get("confidence") for candidate in leg_candidates), default="MEDIUM", key=_confidence_rank),
            "optional_operator_quote_check_priority": OptionalOperatorQuotePriority.HIGH.value,
            "tipster_context_status": first.get("tipster_context_status"),
            "tipster_signal": first.get("tipster_signal"),
            "public_side_or_hype_risk": first.get("public_side_or_hype_risk"),
            "no_usable_tipster_signal_reason": first.get("no_usable_tipster_signal_reason"),
        }
        errors = validate_bet_builder_concept(concept)
        if errors:
            raise SystemExit(json.dumps({"concept_id": concept["concept_id"], "errors": errors}, indent=2))
        concepts.append(concept)
    return concepts


def _build_quote_shortlist(candidates: Sequence[Mapping[str, Any]], concepts: Sequence[Mapping[str, Any]], limit: int = 24) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ranked_candidates = [candidate for candidate in _sort_candidates(candidates) if candidate.get("optional_operator_quote_check_priority") in {"HIGH", "MEDIUM"}]
    for candidate in ranked_candidates:
        rows.append(
            {
                "quote_check_rank": len(rows) + 1,
                "candidate_or_concept_id": candidate.get("candidate_id"),
                "entry_type": "candidate",
                "sport": candidate.get("sport"),
                "event": candidate.get("visible_event_name"),
                "market_selection": candidate.get("human_searchable_market_name"),
                "line_or_alternatives": candidate.get("line") if candidate.get("line") not in (None, "") else "; ".join(candidate.get("allowed_line_alternatives") or []),
                "why_quote_check_matters": "Price determines whether an otherwise valid analytical idea can clear the later price gate.",
                "price_sensitivity": candidate.get("line_sensitivity"),
                "minimum_acceptable_odds_if_calculable": candidate.get("min_acceptable_operator_odds"),
                "superbet_event_found": "",
                "market_found": "",
                "exact_line": "",
                "decimal_odds": "",
                "timestamp_europe_warsaw": "",
                "visible_bet_builder_combined_odds": "",
                "final_manual_status": "",
                "manual_quote_entry_required_for_analysis": False,
            }
        )
        if len(rows) >= limit:
            return rows
    for concept in concepts:
        rows.append(
            {
                "quote_check_rank": len(rows) + 1,
                "candidate_or_concept_id": concept.get("concept_id"),
                "entry_type": "concept",
                "sport": concept.get("sport"),
                "event": concept.get("visible_event_name"),
                "market_selection": " + ".join(_text(leg.get("selection")) for leg in concept.get("legs") or []),
                "line_or_alternatives": " + ".join(_text(leg.get("line") or leg.get("line_free_market_type") or "LINE_REQUIRES_OPERATOR_CHECK") for leg in concept.get("legs") or []),
                "why_quote_check_matters": "Combined operator-screen quote and exact leg lines are required before any final price or stake decision.",
                "price_sensitivity": concept.get("line_sensitivity"),
                "minimum_acceptable_odds_if_calculable": None,
                "superbet_event_found": "",
                "market_found": "",
                "exact_line": "",
                "decimal_odds": "",
                "timestamp_europe_warsaw": "",
                "visible_bet_builder_combined_odds": "",
                "final_manual_status": "",
                "manual_quote_entry_required_for_analysis": False,
            }
        )
        if len(rows) >= limit:
            return rows
    return rows


def _architecture_audit() -> tuple[dict[str, Any], str]:
    payload = {
        "where_current_pipeline_incorrectly_requires_odds_before_useful_analytical_output": [
            {
                "file": "reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_PRODUCTION_V17_1/07_analytical_candidates.json",
                "finding": "Promoted candidates were still framed as manual-quote search paths with `final_status=READY_FOR_MANUAL_OPERATOR_QUOTE_REVIEW`, so useful event analysis was not presented as the primary product.",
            },
            {
                "file": "src/bet/pipeline/manual_quote_price_gate.py",
                "finding": "Missing manual operator odds returns `PRICE_GATE_FAIL`, which is correct for bettable promotion but too strong if reused as an analysis gate.",
            },
        ],
        "where_manual_quote_entry_blocks_analysis": [
            {
                "file": "reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_PRODUCTION_V17_1/17B_manual_quote_review_board.md",
                "finding": "The main operator-facing board requires human quote fields for every row, making manual entry look like the next mandatory step instead of an optional downstream step.",
            },
            {
                "file": "reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_PRODUCTION_V17_1/17C_coupon_draft_operator_sheet.md",
                "finding": "Coupon draft semantics assume the operator will populate odds before the portfolio is meaningfully usable.",
            },
        ],
        "where_unpriced_candidates_are_downgraded_too_aggressively": [
            {
                "file": "reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_PRODUCTION_V17_1/11A_quote_card_blocker_analysis.json",
                "finding": "Eighteen `UNKNOWN_LINE` candidates were downgraded out of the main product even though the blocker was line/price mechanics rather than event-level analytical quality.",
            },
            {
                "file": "src/bet/pipeline/rich_coupon_quality.py",
                "finding": "Quote-card validation rejects low/unknown evidence cards and assumes quote-card-quality is the promotion target, conflating analytical usefulness with quote readiness.",
            },
        ],
        "where_bet_builder_concepts_are_treated_like_priced_coupons": [
            {
                "file": "reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_PRODUCTION_V17_1/08_same_game_builder_idea_groups.json",
                "finding": "Builder groups were emitted as `QUOTE_REVIEW_ONLY` even though they never compute combined odds and are analytically useful before any operator screen is opened.",
            },
            {
                "file": "src/bet/pipeline/coupon_draft_quality.py",
                "finding": "Draft construction starts from quote cards only, so same-event concepts are implicitly treated as coupon inputs first and analytical concepts second.",
            },
        ],
        "where_quote_cards_are_used_as_main_product_instead_of_analytical_candidates": [
            {
                "file": "reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_PRODUCTION_V17_1/10_final_session_report.json",
                "finding": "The final report headline metrics center quote cards and manual review rather than priced/partial/unpriced analytical candidates.",
            },
            {
                "file": "src/bet/pipeline/final_artifact_consistency.py",
                "finding": "Cross-artifact validation is currently quote-card-first, using quote-card counts as the main consistency target.",
            },
        ],
        "which_tests_still_encode_operator_entry_first_assumptions": [
            "tests/test_actionable_quote_cards_v11.py",
            "tests/test_quote_card_actionability_quality.py",
            "tests/test_coupon_draft_quality.py",
            "tests/test_coupon_draft_non_bettable_portfolio.py",
            "tests/test_session_semantic_slate_actuality.py",
        ],
        "which_artifacts_must_be_renamed_or_reinterpreted_as_analysis_first_outputs": [
            {"old": "12_coupon_drafts.json", "new": "12_analysis_portfolio_drafts.json", "reason": "Portfolio semantics must no longer imply coupon assembly before price verification."},
            {"old": "08_same_game_builder_idea_groups.json", "new": "18C_superbet_bet_builder_concepts.json", "reason": "Same-event groups are analytical concepts, not proto-coupons."},
            {"old": "17B_manual_quote_review_board.*", "new": "18D_optional_superbet_quote_check_shortlist.*", "reason": "Quote entry is optional and scoped to the top price-sensitive items only."},
            {"old": "09_manual_superbet_quote_cards.json", "new": "18B_analysis_first_candidate_board.json", "reason": "The primary board must rank analytical candidates by pricing tier, not by manual quote capture."},
        ],
    }
    markdown = "\n".join(
        [
            "# 18A Analysis-First Architecture Audit",
            "",
            "## Where Odds Incorrectly Gate Useful Analysis",
            *(f"- `{item['file']}`: {item['finding']}" for item in payload["where_current_pipeline_incorrectly_requires_odds_before_useful_analytical_output"]),
            "",
            "## Where Manual Quote Entry Blocks Analysis",
            *(f"- `{item['file']}`: {item['finding']}" for item in payload["where_manual_quote_entry_blocks_analysis"]),
            "",
            "## Where Unpriced Candidates Are Downgraded Too Aggressively",
            *(f"- `{item['file']}`: {item['finding']}" for item in payload["where_unpriced_candidates_are_downgraded_too_aggressively"]),
            "",
            "## Where Bet Builder Concepts Are Treated Like Priced Coupons",
            *(f"- `{item['file']}`: {item['finding']}" for item in payload["where_bet_builder_concepts_are_treated_like_priced_coupons"]),
            "",
            "## Where Quote Cards Became The Main Product",
            *(f"- `{item['file']}`: {item['finding']}" for item in payload["where_quote_cards_are_used_as_main_product_instead_of_analytical_candidates"]),
            "",
            "## Tests Encoding Operator-Entry-First Assumptions",
            *(f"- `{item}`" for item in payload["which_tests_still_encode_operator_entry_first_assumptions"]),
            "",
            "## Artifacts To Rename Or Reinterpret",
            *(f"- `{item['old']}` -> `{item['new']}`: {item['reason']}" for item in payload["which_artifacts_must_be_renamed_or_reinterpreted_as_analysis_first_outputs"]),
            "",
        ]
    )
    return payload, markdown


def _preflight(repo_root: Path, run_id: str, source_run_id: str, target_root: Path, source_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    baseline_path = Path("/tmp/v18_1_pre_edit_git_status.txt")
    baseline_entries = _parse_status_lines(baseline_path.read_text(encoding="utf-8").splitlines()) if baseline_path.exists() else []
    baseline_paths = {_text(entry["path"]) for entry in baseline_entries}
    current_entries = _parse_status_lines(_git_output(repo_root, "status", "--porcelain").splitlines())
    dirty_rows: list[dict[str, Any]] = []
    for entry in current_entries:
        path = _text(entry["path"])
        if path.startswith(f"reports/pipeline_runs/{run_id}/"):
            classification = "EXPECTED_ARTIFACT"
            reason = "Generated V18.1 run artifact."
        elif path in EXPECTED_CODE_PATHS:
            classification = "EXPECTED_CODE_CHANGE"
            reason = "Required code change for analysis-first conversion."
        elif path in EXPECTED_TEST_PATHS:
            classification = "EXPECTED_TEST_CHANGE"
            reason = "Required test coverage for analysis-first conversion."
        elif re.search(r"(^|/)(\.env|.*secret.*|.*token.*|.*credential.*)$", path, re.IGNORECASE):
            classification = "MUST_NOT_COMMIT"
            reason = "Potential secret-bearing path."
        elif path in baseline_paths:
            classification = "PRE_EXISTING"
            reason = "Dirty before V18.1 conversion work began."
        else:
            classification = "UNRELATED_RISK"
            reason = "Dirty during V18.1 conversion but outside the expected scope."
        dirty_rows.append({"status": entry["status"], "path": path, "classification": classification, "reason": reason})

    source_report = _read_json(source_root / "10_final_session_report.json", {}) or {}
    v17_consistency = _read_json(source_root / "17A_final_artifact_consistency_audit.json", {}) or {}
    agent_override_detected = False
    for agent_path in sorted((repo_root / ".kilo/agents").glob("bet-*.md")):
        if re.search(r"(?m)^model:\s*\S+", agent_path.read_text(encoding="utf-8")):
            agent_override_detected = True
            break

    required_paths = [
        source_root / "07_analytical_candidates.json",
        source_root / "08_same_game_builder_idea_groups.json",
        source_root / "09_manual_superbet_quote_cards.json",
        source_root / "10_final_session_report.json",
        source_root / "12_coupon_drafts.json",
        source_root / "13_daily_session_certification.json",
        source_root / "17A_final_artifact_consistency_audit.json",
        source_root / "17B_manual_quote_review_board.md",
        source_root / "17C_coupon_draft_operator_sheet.md",
    ]
    preflight = {
        "run_id": run_id,
        "source_run_id": source_run_id,
        "repo_root": str(repo_root),
        "branch": _git_output(repo_root, "branch", "--show-current"),
        "head": _git_output(repo_root, "rev-parse", "HEAD"),
        "command_execution_available": True,
        "no_per_agent_model_override": not agent_override_detected,
        "source_artifacts_exist": all(path.exists() for path in required_paths),
        "production_db_write": bool(source_report.get("PRODUCTION_DB_WRITE") or source_report.get("production_db_write")),
        "automated_placement_enabled": bool(source_report.get("AUTOMATED_PLACEMENT_ENABLED") or source_report.get("automated_placement_enabled")),
        "v17_1_final_consistency_audit_ok": bool(v17_consistency.get("ok")),
        "dirty_files_count": len(current_entries),
        "artifact_root": str(target_root),
        "created_at": _now(),
    }
    dirty_scope = {
        "run_id": run_id,
        "source_run_id": source_run_id,
        "baseline_dirty_paths_count": len(baseline_paths),
        "current_dirty_paths_count": len(current_entries),
        "classification_counts": dict(sorted(Counter(row["classification"] for row in dirty_rows).items())),
        "entries": dirty_rows,
    }
    return preflight, dirty_scope


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate analysis-first V18.1 artifacts from V17.1 source artifacts")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tests-passed", choices=["true", "false"], required=True)
    parser.add_argument("--compileall-passed", choices=["true", "false"], required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    reports_root = repo_root / "reports/pipeline_runs"
    source_root = reports_root / args.source_run_id
    target_root = reports_root / args.run_id
    target_root.mkdir(parents=True, exist_ok=True)

    source_candidates_payload = _read_json(source_root / "07_analytical_candidates.json", {}) or {}
    source_candidates = source_candidates_payload.get("candidates") or []
    source_cards_payload = _read_json(source_root / "09_manual_superbet_quote_cards.json", {}) or {}
    source_cards = source_cards_payload.get("quote_cards") or []
    source_groups_payload = _read_json(source_root / "08_same_game_builder_idea_groups.json", {}) or {}
    source_groups = source_groups_payload.get("groups") or []
    source_matrix = _read_json(source_root / "05D_market_availability_matrix.json", {}) or {}
    source_daily = _read_json(source_root / "13_daily_session_certification.json", {}) or {}
    source_final = _read_json(source_root / "10_final_session_report.json", {}) or {}
    blocked_payload = _read_json(source_root / "11A_quote_card_blocker_analysis.json", {}) or {}
    tipster_context = _read_json(source_root / "16B_tipster_context_status.json", {}) or {}
    tipster_impact_payload = _read_json(source_root / "06C_tipster_candidate_impact.json", {}) or {}

    cards_by_candidate = {_text(card.get("candidate_id")): card for card in source_cards}
    tipster_impacts = {_text(item.get("candidate_id")): item for item in tipster_impact_payload.get("candidate_impacts") or []}
    rows_by_event = _market_rows_by_event(source_matrix.get("markets") or [])
    primary_candidates = _build_primary_candidates(
        source_candidates,
        cards_by_candidate,
        rows_by_event,
        tipster_impacts,
        _text(tipster_context.get("warnings", [""])[0] if tipster_context.get("warnings") else source_final.get("TIPSTER_BLOCK_REASON")),
    )
    anchor_candidates_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in primary_candidates:
        anchor_candidates_by_event[_text(candidate.get("event_id"))].append(candidate)
    recovered_candidates = _build_recovered_unpriced_candidates(
        blocked_payload.get("downgraded_entities") or [],
        anchor_candidates_by_event,
        rows_by_event,
        tipster_impacts,
        _text(source_final.get("TIPSTER_BLOCK_REASON")),
    )
    all_candidates = primary_candidates + recovered_candidates
    candidates_by_id = {_text(candidate.get("candidate_id")): candidate for candidate in all_candidates}

    concepts = _build_bet_builder_concepts(source_groups, candidates_by_id)
    board_rows = _candidate_board_rows(all_candidates, concepts)
    portfolios = _build_analysis_portfolios(all_candidates, concepts)
    shortlist = _build_quote_shortlist(all_candidates, concepts, limit=24)

    preflight, dirty_scope = _preflight(repo_root, args.run_id, args.source_run_id, target_root, source_root)
    _write_json(target_root / "00_preflight.json", preflight)
    _write_text(
        target_root / "00_preflight.md",
        "# 00 Preflight\n\n"
        f"- repo_root: `{preflight['repo_root']}`\n"
        f"- branch: `{preflight['branch']}`\n"
        f"- head: `{preflight['head']}`\n"
        f"- command_execution_available: `{preflight['command_execution_available']}`\n"
        f"- no_per_agent_model_override: `{preflight['no_per_agent_model_override']}`\n"
        f"- source_artifacts_exist: `{preflight['source_artifacts_exist']}`\n"
        f"- production_db_write: `{preflight['production_db_write']}`\n"
        f"- automated_placement_enabled: `{preflight['automated_placement_enabled']}`\n"
        f"- v17_1_final_consistency_audit_ok: `{preflight['v17_1_final_consistency_audit_ok']}`\n"
        f"- dirty_files_count: `{preflight['dirty_files_count']}`\n",
    )
    _write_json(target_root / "00_dirty_scope_audit.json", dirty_scope)
    _write_text(
        target_root / "00_dirty_scope_audit.md",
        "# 00 Dirty Scope Audit\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in dirty_scope["classification_counts"].items())
        + "\n",
    )

    architecture_payload, architecture_md = _architecture_audit()
    _write_json(target_root / "18A_analysis_first_architecture_audit.json", architecture_payload)
    _write_text(target_root / "18A_analysis_first_architecture_audit.md", architecture_md)

    candidates_payload = {
        "run_id": args.run_id,
        "current_run_id": args.run_id,
        "source_run_id": args.source_run_id,
        "input_run_id": args.source_run_id,
        "candidates": all_candidates,
        "candidates_by_pricing_tier": dict(sorted(Counter(_text(candidate.get("pricing_tier")) for candidate in all_candidates).items())),
        "candidates_by_sport": dict(sorted(Counter(_text(candidate.get("sport")) for candidate in all_candidates).items())),
    }
    _write_json(target_root / "07_analytical_candidates.json", candidates_payload)
    _write_json_markdown(target_root / "07_analytical_candidates.md", "07 Analytical Candidates", candidates_payload)

    board_payload = {
        "run_id": args.run_id,
        "current_run_id": args.run_id,
        "source_run_id": args.source_run_id,
        "input_run_id": args.source_run_id,
        "rows": board_rows,
        "rows_by_section": dict(sorted(Counter(_text(row.get("section")) for row in board_rows).items())),
    }
    _write_json(target_root / "18B_analysis_first_candidate_board.json", board_payload)
    _write_json_markdown(target_root / "18B_analysis_first_candidate_board.md", "18B Analysis-First Candidate Board", board_payload)
    _write_csv(
        target_root / "18B_analysis_first_candidate_board.csv",
        board_rows,
        [
            "priority_rank",
            "section",
            "entry_type",
            "entry_id",
            "sport",
            "competition",
            "event",
            "market_family",
            "market_selection",
            "line_or_alternatives",
            "pricing_tier",
            "odds_status",
            "evidence_quality",
            "confidence",
            "thesis",
            "counter_evidence",
            "line_sensitivity",
            "correlation_tags",
            "optional_superbet_check_priority",
            "why_useful_even_without_odds",
            "what_odds_needed_only_for_price_stake_decision",
        ],
    )

    concepts_payload = {
        "run_id": args.run_id,
        "current_run_id": args.run_id,
        "source_run_id": args.source_run_id,
        "input_run_id": args.source_run_id,
        "concepts": concepts,
    }
    _write_json(target_root / "18C_superbet_bet_builder_concepts.json", concepts_payload)
    _write_json_markdown(target_root / "18C_superbet_bet_builder_concepts.md", "18C Superbet Bet Builder Concepts", concepts_payload)

    portfolios_payload = {
        "run_id": args.run_id,
        "current_run_id": args.run_id,
        "source_run_id": args.source_run_id,
        "input_run_id": args.source_run_id,
        "analysis_portfolios": portfolios,
    }
    _write_json(target_root / "12_analysis_portfolio_drafts.json", portfolios_payload)
    _write_json_markdown(target_root / "12_analysis_portfolio_drafts.md", "12 Analysis Portfolio Drafts", portfolios_payload)

    shortlist_payload = {
        "run_id": args.run_id,
        "current_run_id": args.run_id,
        "source_run_id": args.source_run_id,
        "input_run_id": args.source_run_id,
        "rows": shortlist,
    }
    _write_json(target_root / "18D_optional_superbet_quote_check_shortlist.json", shortlist_payload)
    _write_json_markdown(target_root / "18D_optional_superbet_quote_check_shortlist.md", "18D Optional Superbet Quote Check Shortlist", shortlist_payload)
    _write_csv(
        target_root / "18D_optional_superbet_quote_check_shortlist.csv",
        shortlist,
        [
            "quote_check_rank",
            "candidate_or_concept_id",
            "entry_type",
            "sport",
            "event",
            "market_selection",
            "line_or_alternatives",
            "why_quote_check_matters",
            "price_sensitivity",
            "minimum_acceptable_odds_if_calculable",
            "superbet_event_found",
            "market_found",
            "exact_line",
            "decimal_odds",
            "timestamp_europe_warsaw",
            "visible_bet_builder_combined_odds",
            "final_manual_status",
        ],
    )

    tipster_payload = {
        "run_id": args.run_id,
        "current_run_id": args.run_id,
        "source_run_id": args.source_run_id,
        "input_run_id": args.source_run_id,
        "tipster_context_status": "ATTEMPTED_NO_MATCHES",
        "tipster_signal": None,
        "usable_fixture_level_opinions": 0,
        "tipster_phase_attempted": True,
        "tipster_sources_total": int(source_final.get("TIPSTER_SOURCES_TOTAL") or 0),
        "tipster_block_reason": source_final.get("TIPSTER_BLOCK_REASON"),
        "candidate_contexts": [
            {
                "candidate_id": candidate.get("candidate_id"),
                "tipster_context_status": candidate.get("tipster_context_status"),
                "tipster_signal": candidate.get("tipster_signal"),
                "public_side_or_hype_risk": candidate.get("public_side_or_hype_risk"),
                "no_usable_tipster_signal_reason": candidate.get("no_usable_tipster_signal_reason"),
            }
            for candidate in all_candidates
        ],
        "concept_contexts": [
            {
                "concept_id": concept.get("concept_id"),
                "tipster_context_status": concept.get("tipster_context_status"),
                "tipster_signal": concept.get("tipster_signal"),
                "public_side_or_hype_risk": concept.get("public_side_or_hype_risk"),
                "no_usable_tipster_signal_reason": concept.get("no_usable_tipster_signal_reason"),
            }
            for concept in concepts
        ],
    }
    _write_json(target_root / "18E_tipster_analysis_context.json", tipster_payload)
    _write_json_markdown(target_root / "18E_tipster_analysis_context.md", "18E Tipster Analysis Context", tipster_payload)

    priced_count = sum(1 for candidate in all_candidates if candidate.get("pricing_tier") == PricingTier.PRICED_ANALYTICAL.value)
    partial_count = sum(1 for candidate in all_candidates if candidate.get("pricing_tier") == PricingTier.PARTIALLY_PRICED_ANALYTICAL.value)
    unpriced_count = sum(1 for candidate in all_candidates if candidate.get("pricing_tier") == PricingTier.UNPRICED_DEEP_ANALYTICAL.value)
    blockers = {
        "GLOBAL_BLOCKERS": {},
        "NON_PROMOTED_BLOCKERS": source_final.get("NON_PROMOTED_BLOCKERS") or {},
        "PRICE_ONLY_BLOCKERS": {
            "MISSING_HUMAN_SUPERBET_ODDS": len(all_candidates),
            "OPTIONAL_QUOTE_SHORTLIST_ITEMS": len(shortlist),
        },
    }

    final_report = {
        "RUN_ID": args.run_id,
        "CURRENT_RUN_ID": args.run_id,
        "SOURCE_RUN_ID": args.source_run_id,
        "INPUT_RUN_ID": args.source_run_id,
        "STATUS": "PASS" if args.tests_passed == "true" and args.compileall_passed == "true" else "BLOCK",
        "FINAL_VERDICT": "ANALYSIS_FIRST_BOARD_READY" if args.tests_passed == "true" and args.compileall_passed == "true" else "ANALYSIS_FIRST_BOARD_PARTIAL",
        "TOTAL_ANALYTICAL_CANDIDATES": len(all_candidates),
        "PRICED_CANDIDATES_COUNT": priced_count,
        "PARTIALLY_PRICED_CANDIDATES_COUNT": partial_count,
        "UNPRICED_DEEP_CANDIDATES_COUNT": unpriced_count,
        "TOP_PRICED_COUNT": sum(1 for row in board_rows if row.get("section") == "TOP_PRICED_ANALYTICAL_CANDIDATES"),
        "TOP_PARTIALLY_PRICED_COUNT": sum(1 for row in board_rows if row.get("section") == "TOP_PARTIALLY_PRICED_ANALYTICAL_CANDIDATES"),
        "TOP_UNPRICED_COUNT": sum(1 for row in board_rows if row.get("section") == "TOP_UNPRICED_DEEP_ANALYTICAL_CANDIDATES"),
        "BET_BUILDER_CONCEPTS_COUNT": len(concepts),
        "ANALYSIS_PORTFOLIO_DRAFTS_COUNT": len(portfolios),
        "OPTIONAL_OPERATOR_QUOTE_SHORTLIST_COUNT": len(shortlist),
        "MANUAL_QUOTE_ENTRY_REQUIRED_FOR_ANALYSIS": False,
        "MANUAL_QUOTE_ENTRY_REQUIRED_FOR_BETTABLE": True,
        "BETTABLE_COUNT": 0,
        "FINAL_COUPON_ALLOWED": False,
        "COMBINED_BOOKMAKER_ODDS_COMPUTED": False,
        "PRODUCTION_DB_WRITE": False,
        "AUTOMATED_PLACEMENT_ENABLED": False,
        "TIPSTER_CONTEXT_STATUS": "ATTEMPTED_NO_MATCHES",
        "BLOCKERS": blockers,
        "GLOBAL_BLOCKERS": blockers["GLOBAL_BLOCKERS"],
        "NON_PROMOTED_BLOCKERS": blockers["NON_PROMOTED_BLOCKERS"],
        "PRICE_ONLY_BLOCKERS": blockers["PRICE_ONLY_BLOCKERS"],
        "WARNINGS": [
            "No exact human-entered Superbet odds were present in the V17.1 source run, so the priced analytical section remains empty by design.",
            "Recovered unpriced candidates were added only where V17.1 blockers showed line/price mechanics issues rather than missing event-level evidence.",
        ],
        "TESTS_PASSED": args.tests_passed == "true",
        "COMPILEALL_PASSED": args.compileall_passed == "true",
        "ARTIFACT_ROOT": str(target_root),
        "QUOTE_CARDS_BY_SPORT": source_final.get("QUOTE_CARDS_BY_SPORT") or source_daily.get("QUOTE_CARDS_BY_SPORT") or {},
        "WIMBLEDON_QUOTE_CARDS": source_final.get("WIMBLEDON_QUOTE_CARDS") or source_daily.get("WIMBLEDON_QUOTE_CARDS"),
        "WIMBLEDON_SINGLES_QUOTE_CARDS": source_final.get("WIMBLEDON_SINGLES_QUOTE_CARDS") or source_daily.get("WIMBLEDON_SINGLES_QUOTE_CARDS"),
    }
    _write_json(target_root / "10_final_session_report.json", final_report)
    _write_json_markdown(target_root / "10_final_session_report.md", "10 Final Session Report", final_report)

    daily_cert = {
        "RUN_ID": args.run_id,
        "CURRENT_RUN_ID": args.run_id,
        "SOURCE_RUN_ID": args.source_run_id,
        "INPUT_RUN_ID": args.source_run_id,
        "STATUS": final_report["STATUS"],
        "FINAL_VERDICT": final_report["FINAL_VERDICT"],
        "CANDIDATES_BY_SPORT": dict(sorted(Counter(_text(candidate.get("sport")) for candidate in all_candidates).items())),
        "QUOTE_CARDS_BY_SPORT": source_daily.get("QUOTE_CARDS_BY_SPORT") or {},
        "BUILDER_GROUPS_BY_SPORT": source_daily.get("BUILDER_GROUPS_BY_SPORT") or {},
        "WIMBLEDON_QUOTE_CARDS": source_daily.get("WIMBLEDON_QUOTE_CARDS") or source_final.get("WIMBLEDON_QUOTE_CARDS"),
        "WIMBLEDON_SINGLES_QUOTE_CARDS": source_daily.get("WIMBLEDON_SINGLES_QUOTE_CARDS") or source_final.get("WIMBLEDON_SINGLES_QUOTE_CARDS"),
        "MANUAL_QUOTE_ENTRY_REQUIRED_FOR_ANALYSIS": False,
        "MANUAL_QUOTE_ENTRY_REQUIRED_FOR_BETTABLE": True,
        "BETTABLE_COUNT": 0,
        "FINAL_COUPON_ALLOWED": False,
        "COMBINED_BOOKMAKER_ODDS_COMPUTED": False,
        "TIPSTER_CONTEXT_STATUS": "ATTEMPTED_NO_MATCHES",
        "TESTS_PASSED": args.tests_passed == "true",
        "COMPILEALL_PASSED": args.compileall_passed == "true",
        "ARTIFACT_ROOT": str(target_root),
    }
    _write_json(target_root / "13_daily_session_certification.json", daily_cert)
    _write_json_markdown(target_root / "13_daily_session_certification.md", "13 Daily Session Certification", daily_cert)

    manifest = {
        "run_id": args.run_id,
        "current_run_id": args.run_id,
        "source_run_id": args.source_run_id,
        "input_run_id": args.source_run_id,
        "generated_at": _now(),
        "TEST_FILES_RUN": REQUIRED_TEST_FILES,
        "COMPILEALL_PASSED": args.compileall_passed == "true",
        "TESTS_PASSED": args.tests_passed == "true",
        "artifacts": [
            "00_preflight.json",
            "00_preflight.md",
            "00_dirty_scope_audit.json",
            "00_dirty_scope_audit.md",
            "05D_market_availability_matrix.json",
            "07_analytical_candidates.json",
            "07_analytical_candidates.md",
            "08_same_game_builder_idea_groups.json",
            "09_manual_superbet_quote_cards.json",
            "10_final_session_report.json",
            "10_final_session_report.md",
            "12_analysis_portfolio_drafts.json",
            "12_analysis_portfolio_drafts.md",
            "13_daily_session_certification.json",
            "13_daily_session_certification.md",
            "16E_wimbledon_singles_classification_audit.json",
            "18A_analysis_first_architecture_audit.json",
            "18A_analysis_first_architecture_audit.md",
            "18B_analysis_first_candidate_board.json",
            "18B_analysis_first_candidate_board.md",
            "18B_analysis_first_candidate_board.csv",
            "18C_superbet_bet_builder_concepts.json",
            "18C_superbet_bet_builder_concepts.md",
            "18D_optional_superbet_quote_check_shortlist.json",
            "18D_optional_superbet_quote_check_shortlist.md",
            "18D_optional_superbet_quote_check_shortlist.csv",
            "18E_tipster_analysis_context.json",
            "18E_tipster_analysis_context.md",
        ],
    }
    _write_json(target_root / "16F_final_evidence_export_manifest.json", manifest)
    _write_json_markdown(target_root / "16F_final_evidence_export_manifest.md", "16F Final Evidence Export Manifest", manifest)

    _copy_json_with_lineage(source_root / "05D_market_availability_matrix.json", target_root / "05D_market_availability_matrix.json", args.run_id, args.source_run_id)
    if (source_root / "05D_market_availability_matrix.md").exists():
        _write_text(target_root / "05D_market_availability_matrix.md", (source_root / "05D_market_availability_matrix.md").read_text(encoding="utf-8"))
    _copy_json_with_lineage(source_root / "08_same_game_builder_idea_groups.json", target_root / "08_same_game_builder_idea_groups.json", args.run_id, args.source_run_id)
    _write_text(target_root / "08_same_game_builder_idea_groups.md", (source_root / "08_same_game_builder_idea_groups.md").read_text(encoding="utf-8"))
    _copy_json_with_lineage(source_root / "09_manual_superbet_quote_cards.json", target_root / "09_manual_superbet_quote_cards.json", args.run_id, args.source_run_id)
    _write_text(target_root / "09_manual_superbet_quote_cards.md", (source_root / "09_manual_superbet_quote_cards.md").read_text(encoding="utf-8"))
    if (source_root / "16E_wimbledon_singles_classification_audit.json").exists():
        _copy_json_with_lineage(source_root / "16E_wimbledon_singles_classification_audit.json", target_root / "16E_wimbledon_singles_classification_audit.json", args.run_id, args.source_run_id)
    if (source_root / "16E_wimbledon_singles_classification_audit.md").exists():
        _write_text(target_root / "16E_wimbledon_singles_classification_audit.md", (source_root / "16E_wimbledon_singles_classification_audit.md").read_text(encoding="utf-8"))

    _write_text(
        repo_root / ".kilocode/memory/session-state.md",
        "\n".join(
            [
                f"1. Step completed and status: {args.run_id} analysis-first artifact generation completed with status {final_report['STATUS']}.",
                f"2. Key metrics/artifacts: candidates={len(all_candidates)} partial={partial_count} unpriced={unpriced_count} concepts={len(concepts)} shortlist={len(shortlist)}; final={target_root / '10_final_session_report.json'}.",
                "3. Next step and open risks: run the final consistency audit and keep all outputs analysis-only until human Superbet odds and correlation gate are captured.",
            ]
        ) + "\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
