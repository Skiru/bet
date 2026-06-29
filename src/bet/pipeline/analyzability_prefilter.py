"""Analyzability prefilter module for selecting candidates for analytical smoke."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from bet.pipeline.market_probability_inputs import (
    build_market_probability_input,
    validate_market_probability_input,
    extract_market_semantics,
    MarketSemantics,
)


@dataclass
class AnalyzabilityReport:
    candidate_id: str
    sport: str
    market_family: Optional[str]
    market_type: Optional[str]
    line: Optional[float]
    direction: Optional[str]
    stats_seed_status: bool
    l10_series_status: bool
    stat_semantics_status: bool
    market_probability_input_status: bool
    analyzability_score: float
    analyzability_status: str
    blocker_reasons: list[str]
    source_artifact_path: str
    field_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_candidate_analyzability(
    candidate: dict[str, Any],
    stats_seed: Optional[dict[str, Any]],
    market_semantics: Optional[MarketSemantics] = None,
) -> dict[str, Any]:
    candidate_id = candidate.get("candidate_id") or candidate.get("fixture_key") or ""
    sport = candidate.get("sport") or ""
    home_team = candidate.get("home_team") or ""
    away_team = candidate.get("away_team") or ""
    
    # Traceability fields
    source_artifact_path = candidate.get("source_artifact_path") or ""
    field_path = candidate.get("field_path") or "candidate"
    
    if isinstance(market_semantics, dict):
        market_semantics = MarketSemantics(
            market_family=market_semantics.get("market_family", ""),
            market_type=market_semantics.get("market_type", ""),
            market_label=market_semantics.get("market_label", ""),
            selection=market_semantics.get("selection", "") or market_semantics.get("pick", ""),
            direction=market_semantics.get("direction", ""),
            line=market_semantics.get("line"),
            source_artifact_path=market_semantics.get("source_artifact_path", ""),
            field_path=market_semantics.get("field_path", ""),
        )

    # Semantics fallback extraction if not provided
    if not market_semantics:
        participants = [name for name in (home_team, away_team) if name]
        market_semantics = extract_market_semantics(
            candidate,
            participants=participants,
            source_artifact_path=source_artifact_path,
            field_path=field_path,
        )
        if not market_semantics.market_family:
            best_market = candidate.get("best_market") or (stats_seed or {}).get("best_market")
            if isinstance(best_market, dict) and best_market:
                market_semantics = extract_market_semantics(
                    best_market,
                    participants=participants,
                    source_artifact_path=(stats_seed or {}).get("source_artifact_path") or source_artifact_path,
                    field_path="best_market",
                )
                
    market_family = market_semantics.market_family or None
    market_type = market_semantics.market_type or None
    line = market_semantics.line
    direction = market_semantics.direction or None
    
    if market_semantics.source_artifact_path:
        source_artifact_path = market_semantics.source_artifact_path
    field_path = candidate.get("field_path") or market_semantics.field_path or field_path

    blocker_reasons: list[str] = []
    stats_seed_status = False
    l10_series_status = False
    stat_semantics_status = False
    market_probability_input_status = False
    analyzability_status = "ANALYZABLE"

    # Anti-fake data check
    is_fake = (
        candidate.get("is_fake") is True
        or (stats_seed or {}).get("is_fake") is True
        or "fake" in str(candidate.get("probability_method") or "").lower()
        or "fake" in str((stats_seed or {}).get("probability_method") or "").lower()
    )
    if is_fake:
        blocker_reasons.append("FAKE_DATA_DETECTED")
        analyzability_status = "UNSUPPORTED_MARKET_FAMILY"

    # Sport validation
    elif sport != "football":
        blocker_reasons.append("UNSUPPORTED_SPORT")
        analyzability_status = "UNSUPPORTED_MARKET_FAMILY"

    # Identity verification
    elif not home_team or not away_team:
        blocker_reasons.append("IDENTITY_GAP")
        analyzability_status = "IDENTITY_GAP"

    # Market semantics validation
    elif market_semantics.mapping_status == "UNSUPPORTED_PROP_MATCH":
        blocker_reasons.append("UNSUPPORTED_MARKET_FAMILY")
        analyzability_status = "UNSUPPORTED_MARKET_FAMILY"

    elif market_semantics.mapping_status == "AMBIGUOUS_MARKET_LABEL":
        blocker_reasons.append("UNSUPPORTED_MARKET_FAMILY")
        analyzability_status = "UNSUPPORTED_MARKET_FAMILY"

    elif not market_family:
        blocker_reasons.append("MARKET_SPECIFIC_INPUT_NOT_BUILT")
        analyzability_status = "UNSUPPORTED_MARKET_FAMILY"

    elif market_family in {"TOTALS", "GOALS_TOTALS", "HANDICAP", "CORNERS", "CARDS", "SHOTS", "SHOTS_ON_TARGET"} and line in (None, "", "MISSING"):
        blocker_reasons.append("LINE_MISSING")
        analyzability_status = "LINE_OR_DIRECTION_GAP"
        stat_semantics_status = True

    elif market_family in {"TOTALS", "GOALS_TOTALS", "HANDICAP", "CORNERS", "CARDS", "SHOTS", "SHOTS_ON_TARGET"} and not direction:
        blocker_reasons.append("DIRECTION_MISSING")
        analyzability_status = "LINE_OR_DIRECTION_GAP"
        stat_semantics_status = True

    else:
        # Check model probability availability
        val_prob = candidate.get("model_probability") or candidate.get("probability") or (stats_seed or {}).get("model_probability")
        val_conf = str(candidate.get("probability_confidence") or (stats_seed or {}).get("probability_confidence") or "").strip().upper()
        val_method = str(candidate.get("probability_method") or (stats_seed or {}).get("probability_method") or "").strip().upper()
        
        has_existing_model_prob = False
        if val_prob is not None and val_conf not in {"BLOCKED", "LOW", "MINIMAL", "LOW_CONFIDENCE"} and val_method != "BOOKMAKER_IMPLIED_REFERENCE_ONLY":
            has_existing_model_prob = True

        probability_missing = False
        if val_prob is None or val_conf in {"BLOCKED", "LOW", "MINIMAL", "LOW_CONFIDENCE"} or val_method == "BOOKMAKER_IMPLIED_REFERENCE_ONLY":
            probability_missing = True

        if probability_missing and not has_existing_model_prob:
            blocker_reasons.append("L10_SERIES_MISSING")
            analyzability_status = "RESEARCH_GAP_L10_MISSING"

        # Check stats seed presence
        elif not stats_seed or not (
            stats_seed.get("has_data") is True
            or (stats_seed.get("stats_a_summary") or {}).get("has_data") is True
            or (stats_seed.get("stats_b_summary") or {}).get("has_data") is True
        ):
            blocker_reasons.append("STATS_SEED_MISSING")
            analyzability_status = "RESEARCH_GAP_STATS_MISSING"

        else:
            stats_seed_status = True
            
            # Build probability input using native module
            inp = build_market_probability_input(candidate, stats_seed)
            valid, reason = validate_market_probability_input(inp)
            
            if valid or has_existing_model_prob:
                stats_seed_status = True
                l10_series_status = True
                stat_semantics_status = True
                market_probability_input_status = True
                analyzability_status = "ANALYZABLE"
            else:
                if reason == "AMBIGUOUS_MARKET_LABEL":
                    blocker_reasons.append("UNSUPPORTED_MARKET_FAMILY")
                    analyzability_status = "UNSUPPORTED_MARKET_FAMILY"
                elif reason == "UNSUPPORTED_PROP_MATCH":
                    blocker_reasons.append("UNSUPPORTED_MARKET_FAMILY")
                    analyzability_status = "UNSUPPORTED_MARKET_FAMILY"
                elif reason == "MARKET_SPECIFIC_INPUT_NOT_BUILT":
                    blocker_reasons.append("MARKET_SPECIFIC_INPUT_NOT_BUILT")
                    analyzability_status = "RESEARCH_GAP_MARKET_INPUT_NOT_BUILT"
                elif reason == "UNKNOWN_SPLIT_STAT_SEMANTICS":
                    blocker_reasons.append("UNKNOWN_SPLIT_STAT_SEMANTICS")
                    analyzability_status = "RESEARCH_GAP_UNKNOWN_STAT_SEMANTICS"
                elif reason == "MARKET_FAMILY_NOT_SUPPORTED_BY_ENGINE":
                    blocker_reasons.append("UNSUPPORTED_MARKET_FAMILY")
                    analyzability_status = "UNSUPPORTED_MARKET_FAMILY"
                elif reason == "LINE_MISSING":
                    blocker_reasons.append("LINE_MISSING")
                    analyzability_status = "LINE_OR_DIRECTION_GAP"
                    stat_semantics_status = True
                elif reason == "DIRECTION_MISSING":
                    blocker_reasons.append("DIRECTION_MISSING")
                    analyzability_status = "LINE_OR_DIRECTION_GAP"
                    stat_semantics_status = True
                elif reason == "L10_SERIES_MISSING":
                    blocker_reasons.append("L10_SERIES_MISSING")
                    analyzability_status = "RESEARCH_GAP_L10_MISSING"
                    stat_semantics_status = True
                elif reason == "INSUFFICIENT_SAMPLE_SIZE":
                    blocker_reasons.append("SAMPLE_SIZE_INSUFFICIENT")
                    analyzability_status = "RESEARCH_GAP_L10_MISSING"
                    stat_semantics_status = True
                    l10_series_status = True
                else:
                    blocker_reasons.append(reason)
                    analyzability_status = "RESEARCH_GAP_MARKET_INPUT_NOT_BUILT"

    # Score calculation
    # Score 1.0 if fully ready, or intermediate parts if not
    score = 0.0
    if analyzability_status == "ANALYZABLE":
        score = 1.0
    else:
        # Give partial weight to having a stats seed
        if stats_seed_status:
            score += 0.4
        if l10_series_status:
            score += 0.2
        if stat_semantics_status:
            score += 0.2
        if market_probability_input_status:
            score += 0.2

    report = AnalyzabilityReport(
        candidate_id=candidate_id,
        sport=sport,
        market_family=market_family,
        market_type=market_type,
        line=line,
        direction=direction,
        stats_seed_status=stats_seed_status,
        l10_series_status=l10_series_status,
        stat_semantics_status=stat_semantics_status,
        market_probability_input_status=market_probability_input_status,
        analyzability_score=score,
        analyzability_status=analyzability_status,
        blocker_reasons=blocker_reasons,
        source_artifact_path=source_artifact_path,
        field_path=field_path,
    )
    return report.to_dict()


def rank_analyzable_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sorts candidates descending by analyzability_score, favoring probability input ready."""
    def _rank_key(c: dict[str, Any]) -> tuple[float, int, int]:
        score = float(c.get("analyzability_score") or 0.0)
        input_ready = 1 if c.get("market_probability_input_status") is True else 0
        model_ready = 1 if c.get("model_probability") is not None else 0
        return (score, input_ready, model_ready)

    return sorted(candidates, key=_rank_key, reverse=True)


def split_analyzable_and_research_gap(
    candidates_reports: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Splits reports into analyzable, research_gap, and unsupported candidates."""
    analyzable = []
    research_gap = []
    unsupported = []

    for r in candidates_reports:
        status = r.get("analyzability_status")
        if status == "ANALYZABLE":
            analyzable.append(r)
        elif status in {
            "RESEARCH_GAP_STATS_MISSING",
            "RESEARCH_GAP_L10_MISSING",
            "RESEARCH_GAP_UNKNOWN_STAT_SEMANTICS",
            "RESEARCH_GAP_MARKET_INPUT_NOT_BUILT",
            "LINE_OR_DIRECTION_GAP",
            "IDENTITY_GAP"
        }:
            research_gap.append(r)
        else:
            unsupported.append(r)

    return analyzable, research_gap, unsupported


def write_analyzability_report(path: Path, payload: list[dict[str, Any]]) -> Path:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return resolved
