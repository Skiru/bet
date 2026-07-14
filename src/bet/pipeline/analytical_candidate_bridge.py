"""Bridge S3/S4 shortlist candidates into analytical handoff drafts."""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from bet.pipeline.analyzability_prefilter import (
    evaluate_candidate_analyzability,
    rank_analyzable_candidates,
)
from bet.pipeline.market_probability_inputs import (
    build_market_probability_input,
    extract_market_semantics,
    validate_market_probability_input,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _resolve_analyzability_report_path(source_artifact_path: str) -> Path:
    runtime_artifact_dir = _normalized(os.environ.get("BET_PIPELINE_ARTIFACT_DIR"))
    if runtime_artifact_dir:
        return Path(runtime_artifact_dir) / "analyzability_prefilter_report.json"

    source_path = Path(source_artifact_path)
    source_parent = source_path.parent
    if source_parent.name == "data":
        return source_parent.parent / "artifacts" / "analyzability_prefilter_report.json"
    return source_parent / "analyzability_prefilter_report.json"


def _normalized(value: Any) -> str:
    return str(value or "").strip()


def _normalized_key(home: Any, away: Any, kickoff: Any = "") -> str:
    return "|".join(
        part.lower()
        for part in (
            _normalized(home),
            _normalized(away),
            _normalized(str(kickoff)[:10]),
        )
        if part
    )


def _identity_key(entry: dict[str, Any]) -> str:
    fixture_id = entry.get("fixture_id") or entry.get("event_id")
    if fixture_id not in (None, ""):
        return f"fixture:{fixture_id}"
    return _normalized_key(
        entry.get("home_team"),
        entry.get("away_team"),
        entry.get("scheduled_time") or entry.get("kickoff") or entry.get("start_time"),
    )


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    decimal_value = _to_decimal(value)
    if decimal_value is None:
        return None
    return float(decimal_value)


def _market_family_from_seed(seed: dict[str, Any]) -> str:
    return extract_market_semantics(seed).market_family


def _supported_analytical_family(family: str) -> bool:
    return family in {"RESULT", "TOTALS", "GOALS_TOTALS", "CORNERS", "CARDS", "HANDICAP", "SHOTS", "SHOTS_ON_TARGET"}


def _pick_from_seed(seed: dict[str, Any], participants: list[str]) -> str:
    pick = _normalized(seed.get("pick") or seed.get("direction") or seed.get("outcome"))
    if pick in {"home", "HOME"} and participants:
        return participants[0]
    if pick in {"away", "AWAY"} and len(participants) > 1:
        return participants[1]
    if pick in {"draw", "DRAW"}:
        return "DRAW"
    return pick


def _match_shortlist_market(
    shortlist_entry: dict[str, Any] | None,
    valuation_entry: dict[str, Any],
) -> dict[str, Any] | None:
    if not shortlist_entry:
        return None
    odds_markets = shortlist_entry.get("odds_markets") or []
    if not isinstance(odds_markets, list):
        return None
    target_odds = _to_float((valuation_entry.get("odds") or {}).get("market_best"))
    if target_odds is None:
        return None
    exact_matches = []
    for market in odds_markets:
        market_odds = _to_float(market.get("best_odds"))
        if market_odds is None:
            continue
        if abs(market_odds - target_odds) < 0.0001:
            exact_matches.append(market)
    if not exact_matches:
        return None

    def _priority(entry: dict[str, Any]) -> tuple[int, int, str]:
        market_type = _normalized(entry.get("market_type") or entry.get("market")).lower()
        outcome = _normalized(entry.get("outcome")).lower()
        if market_type in {"ml", "moneyline", "h2h"}:
            bucket = 0
        elif market_type in {"draw_no_bet", "double_chance"}:
            bucket = 1
        elif any(token in market_type for token in ("goal", "total", "over", "under")):
            bucket = 2
        else:
            bucket = 3
        outcome_penalty = 1 if outcome == "hdp" else 0
        return (bucket, outcome_penalty, market_type)

    return sorted(exact_matches, key=_priority)[0]


def _market_seed(
    valuation_entry: dict[str, Any],
    s3_entry: dict[str, Any] | None,
    shortlist_entry: dict[str, Any] | None,
    participants: list[str],
    *,
    source_artifact_path: str,
) -> dict[str, Any]:
    valuation_semantics = extract_market_semantics(
        valuation_entry,
        participants=participants,
        source_artifact_path=source_artifact_path,
        field_path="candidate",
    )
    if valuation_semantics.market_family or valuation_semantics.mapping_status:
        return {
            "market_family": valuation_semantics.market_family,
            "market_type": valuation_semantics.market_type,
            "market_label": valuation_semantics.market_label,
            "pick": valuation_semantics.selection,
            "selection": valuation_semantics.selection,
            "direction": valuation_semantics.direction,
            "line": valuation_semantics.line,
            "mapping_status": valuation_semantics.mapping_status,
            "source_artifact_path": valuation_semantics.source_artifact_path,
            "field_path": valuation_semantics.field_path,
            "source": "valuation_candidate",
        }

    best_market = (valuation_entry.get("best_market") or {}) or ((s3_entry or {}).get("best_market") or {})
    if isinstance(best_market, dict) and best_market:
        best_market_semantics = extract_market_semantics(
            best_market,
            participants=participants,
            source_artifact_path=source_artifact_path,
            field_path="best_market",
        )
        if best_market_semantics.market_family or best_market_semantics.mapping_status:
            return {
                "market_family": best_market_semantics.market_family,
                "market_type": best_market_semantics.market_type,
                "market_label": best_market_semantics.market_label,
                "pick": best_market_semantics.selection,
                "selection": best_market_semantics.selection,
                "direction": best_market_semantics.direction,
                "line": best_market_semantics.line,
                "mapping_status": best_market_semantics.mapping_status,
                "source_artifact_path": best_market_semantics.source_artifact_path,
                "field_path": best_market_semantics.field_path,
                "source": "s3_best_market",
            }

    shortlist_market = _match_shortlist_market(shortlist_entry, valuation_entry)
    if shortlist_market:
        shortlist_semantics = extract_market_semantics(
            shortlist_market,
            participants=participants,
            source_artifact_path=_normalized((shortlist_entry or {}).get("source_artifact_path") or source_artifact_path),
            field_path="odds_markets[]",
        )
        return {
            "market_family": shortlist_semantics.market_family,
            "market_type": shortlist_semantics.market_type,
            "market_label": shortlist_semantics.market_label,
            "pick": shortlist_semantics.selection,
            "selection": shortlist_semantics.selection,
            "direction": shortlist_semantics.direction,
            "line": shortlist_semantics.line,
            "mapping_status": shortlist_semantics.mapping_status,
            "source_artifact_path": shortlist_semantics.source_artifact_path,
            "field_path": shortlist_semantics.field_path,
            "source": "shortlist_odds_market",
        }

    return {
        "market_family": "",
        "market_type": "",
        "market_label": "",
        "pick": "",
        "selection": "",
        "direction": "",
        "line": None,
        "mapping_status": "",
        "source_artifact_path": source_artifact_path,
        "field_path": "candidate",
        "source": "missing",
    }


def _supporting_stats_from_s3(s3_entry: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not s3_entry:
        return []
    results: list[dict[str, Any]] = []
    for label, key in (("team_a_form", "stats_a_summary"), ("team_b_form", "stats_b_summary")):
        section = s3_entry.get(key) or {}
        l10_avg = section.get("l10_avg") or {}
        if section.get("has_data") and l10_avg:
            results.append(
                {
                    "metric": label,
                    "value": l10_avg,
                    "source": list(section.get("sources") or []),
                    "as_of": s3_entry.get("probability_as_of") or s3_entry.get("generated_at") or "UNKNOWN",
                }
            )
    h2h = s3_entry.get("h2h_summary") or {}
    if h2h.get("has_data") and h2h.get("meetings_count"):
        results.append(
            {
                "metric": "h2h_meetings",
                "value": h2h.get("meetings_count"),
                "source": "s3_h2h_summary",
                "as_of": s3_entry.get("probability_as_of") or s3_entry.get("generated_at") or "UNKNOWN",
            }
        )
    return results


def _probability_contract(
    valuation_entry: dict[str, Any],
    s3_entry: dict[str, Any] | None,
) -> dict[str, Any]:
    model_probability = _to_decimal(
        valuation_entry.get("model_probability")
        or valuation_entry.get("probability")
        or (s3_entry or {}).get("model_probability")
    )
    probability_method = _normalized(
        valuation_entry.get("probability_method")
        or (s3_entry or {}).get("probability_method")
    )
    probability_sources = valuation_entry.get("probability_sources")
    if probability_sources in (None, ""):
        probability_sources = (s3_entry or {}).get("probability_sources") or []
    probability_as_of = _normalized(
        valuation_entry.get("probability_as_of")
        or (s3_entry or {}).get("probability_as_of")
    )
    probability_confidence = _normalized(
        valuation_entry.get("probability_confidence")
        or (s3_entry or {}).get("probability_confidence")
    )
    probability_missing_reason = _normalized(
        valuation_entry.get("probability_missing_reason")
        or (s3_entry or {}).get("probability_missing_reason")
    )
    if probability_method == "BOOKMAKER_IMPLIED_REFERENCE_ONLY":
        model_probability = None
        if not probability_missing_reason:
            probability_missing_reason = "BOOKMAKER_IMPLIED_REFERENCE_ONLY"
    if model_probability is None and not probability_missing_reason:
        probability_missing_reason = "INSUFFICIENT_MODEL_PROBABILITY"
    return {
        "model_probability": model_probability,
        "probability_method": probability_method,
        "probability_sources": probability_sources,
        "probability_as_of": probability_as_of,
        "probability_confidence": probability_confidence,
        "probability_missing_reason": probability_missing_reason,
    }


def _probability_confidence_is_blocked(probability_confidence: str) -> bool:
    normalized = _normalized(probability_confidence).upper()
    return normalized in {"BLOCKED", "LOW", "MINIMAL", "LOW_CONFIDENCE"}


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class CandidateDraft:
    candidate_id: str
    event_id: str
    fixture_id: str
    sport: str
    competition: str
    participants: list[str]
    start_time: str
    market_family: str
    market_type: str
    market_label: str
    outcome_name: str
    selection: str
    pick: str
    direction: str
    line: Any
    odds_decimal: Decimal | None
    odds_source: str
    odds_as_of: str
    model_probability: Decimal | None
    probability_status: str
    probability_method: str
    probability_sources: list[Any]
    probability_as_of: str
    probability_confidence: str
    probability_missing_reason: str
    hydration_status: str = "UNKNOWN"
    promotion_status: str = "BLOCKED_HYDRATION_FAILED"
    source_provider: str = ""
    stats_as_of: str = "UNKNOWN"
    stat_semantics_status: str = "UNKNOWN"
    promotion_safe_model_probability: bool = False
    market_probability_validation_reason: str = "UNKNOWN"
    ready_for_manual_operator_quote_review: bool = False
    supporting_stats: list[dict[str, Any]] = field(default_factory=list)
    source_gaps: list[dict[str, Any]] = field(default_factory=list)
    analytical_status: str = "NOT_ANALYTICAL_ELIGIBLE"
    source_artifact_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass(frozen=True)
class ResearchCandidateBlocked(CandidateDraft):
    blocking_reason: str = "NOT_ANALYTICAL_ELIGIBLE"


def _build_indexes(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    candidates = payload.get("candidates") or payload.get("analyses") or []
    if not isinstance(candidates, list):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        key = _identity_key(entry)
        if key:
            index[key] = entry
        alt_key = _normalized_key(
            entry.get("home_team"),
            entry.get("away_team"),
            entry.get("scheduled_time") or entry.get("kickoff") or entry.get("start_time"),
        )
        if alt_key:
            index.setdefault(alt_key, entry)
    return index


def build_analytical_candidate_handoff(
    valuation_payload: dict[str, Any],
    *,
    s3_payload: dict[str, Any] | None = None,
    shortlist_payload: dict[str, Any] | None = None,
    source_artifact_path: str,
) -> dict[str, Any]:
    valuation_candidates = valuation_payload.get("candidates") or []
    s3_index = _build_indexes(s3_payload)
    shortlist_index = _build_indexes(shortlist_payload)

    analytical_ready: list[dict[str, Any]] = []
    blocked_probability_missing: list[dict[str, Any]] = []
    blocked_stats_missing: list[dict[str, Any]] = []
    blocked_identity_missing: list[dict[str, Any]] = []
    review_only_partial_data: list[dict[str, Any]] = []
    research_gap_minimal_hydration: list[dict[str, Any]] = []
    priced_candidates: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    rejection_ledger: list[dict[str, Any]] = []

    for position, valuation_entry in enumerate(valuation_candidates):
        if not isinstance(valuation_entry, dict):
            continue
        key = _identity_key(valuation_entry)
        alt_key = _normalized_key(
            valuation_entry.get("home_team"),
            valuation_entry.get("away_team"),
            valuation_entry.get("scheduled_time") or valuation_entry.get("kickoff") or valuation_entry.get("start_time"),
        )
        s3_entry = s3_index.get(key) or (s3_index.get(alt_key) if alt_key else None)
        shortlist_entry = shortlist_index.get(key) or (shortlist_index.get(alt_key) if alt_key else None)

        upstream_sport = _normalized((s3_entry or {}).get("sport") or (shortlist_entry or {}).get("sport"))
        upstream_competition = _normalized((s3_entry or {}).get("competition") or (shortlist_entry or {}).get("competition"))

        sport = _normalized(valuation_entry.get("sport") or upstream_sport)
        competition = _normalized(valuation_entry.get("competition") or upstream_competition)
        participants = [
            _normalized(valuation_entry.get("home_team") or (s3_entry or {}).get("home_team") or (shortlist_entry or {}).get("home_team")),
            _normalized(valuation_entry.get("away_team") or (s3_entry or {}).get("away_team") or (shortlist_entry or {}).get("away_team")),
        ]
        participants = [participant for participant in participants if participant]
        start_time = _normalized(
            valuation_entry.get("scheduled_time")
            or valuation_entry.get("kickoff")
            or (s3_entry or {}).get("kickoff")
            or (shortlist_entry or {}).get("kickoff")
        )
        candidate_id = _normalized(
            valuation_entry.get("candidate_id")
            or (s3_entry or {}).get("candidate_id")
            or valuation_entry.get("fixture_key")
            or valuation_entry.get("fixture_id")
            or f"candidate-{position + 1}"
        )
        fixture_id = _normalized(valuation_entry.get("fixture_id") or (s3_entry or {}).get("fixture_id"))
        event_id = _normalized(valuation_entry.get("event_id") or fixture_id)

        source_gaps: list[dict[str, Any]] = []
        if not sport:
            source_gaps.append(
                {
                    "code": "SPORT_PROPAGATION_BUG" if upstream_sport else "UPSTREAM_IDENTITY_INCOMPLETE",
                    "field": "sport",
                    "artifact": source_artifact_path,
                    "field_path": f"candidates[{position}].sport",
                    "upstream_value": upstream_sport or None,
                }
            )
        if not competition:
            source_gaps.append(
                {
                    "code": "COMPETITION_PROPAGATION_BUG" if upstream_competition else "UPSTREAM_IDENTITY_INCOMPLETE",
                    "field": "competition",
                    "artifact": source_artifact_path,
                    "field_path": f"candidates[{position}].competition",
                    "upstream_value": upstream_competition or None,
                }
            )
        if len(participants) < 2:
            source_gaps.append(
                {
                    "code": "UPSTREAM_IDENTITY_INCOMPLETE",
                    "field": "participants",
                    "artifact": source_artifact_path,
                    "field_path": f"candidates[{position}]",
                }
            )

        market_seed = _market_seed(
            valuation_entry,
            s3_entry,
            shortlist_entry,
            participants,
            source_artifact_path=source_artifact_path,
        )
        if market_seed.get("mapping_status") in {"AMBIGUOUS_MARKET_LABEL", "UNSUPPORTED_PROP_MATCH", "LINE_MISSING", "DIRECTION_MISSING"}:
            source_gaps.append(
                {
                    "code": market_seed["mapping_status"],
                    "field": "market_semantics",
                    "artifact": market_seed.get("source_artifact_path") or source_artifact_path,
                    "field_path": market_seed.get("field_path") or f"candidates[{position}]",
                }
            )
        elif not market_seed["market_family"]:
            source_gaps.append(
                {
                    "code": "MARKET_FAMILY_MAPPING_MISSING",
                    "field": "market_family",
                    "artifact": market_seed.get("source_artifact_path") or source_artifact_path,
                    "field_path": market_seed.get("field_path") or f"candidates[{position}]",
                }
            )

        supporting_stats = _supporting_stats_from_s3(s3_entry)
        probability_contract = _probability_contract(valuation_entry, s3_entry)
        if _probability_confidence_is_blocked(probability_contract["probability_confidence"]):
            probability_contract["model_probability"] = None
            if not probability_contract["probability_missing_reason"]:
                probability_contract["probability_missing_reason"] = "LOW_CONFIDENCE_MODEL_PROBABILITY"

        runtime_candidate = dict(valuation_entry)
        runtime_candidate.update(
            {
                "market_family": market_seed.get("market_family"),
                "market_type": market_seed.get("market_type"),
                "market_label": market_seed.get("market_label"),
                "selection": market_seed.get("selection"),
                "pick": market_seed.get("pick"),
                "direction": market_seed.get("direction"),
                "line": market_seed.get("line"),
                "source_artifact_path": market_seed.get("source_artifact_path") or source_artifact_path,
                "field_path": market_seed.get("field_path") or "candidate",
            }
        )
        probability_input = build_market_probability_input(runtime_candidate, s3_entry)
        probability_input_valid, probability_input_reason = validate_market_probability_input(probability_input)

        if probability_input_reason == "SOURCE_PROVIDER_MISSING":
            source_gaps.append({
                "code": "SOURCE_PROVIDER_MISSING",
                "field": "source_provider",
                "artifact": probability_input.source_artifact_path or source_artifact_path,
                "field_path": market_seed.get("field_path") or "candidate",
            })
        elif probability_input_reason == "SOURCE_ARTIFACT_PATH_MISSING":
            source_gaps.append({
                "code": "SOURCE_ARTIFACT_PATH_MISSING",
                "field": "source_artifact_path",
                "artifact": source_artifact_path,
                "field_path": market_seed.get("field_path") or "candidate",
            })
        elif probability_input_reason == "STATS_AS_OF_MISSING_OR_UNKNOWN":
            source_gaps.append({
                "code": "STATS_AS_OF_MISSING_OR_UNKNOWN",
                "field": "stats_as_of",
                "artifact": probability_input.source_artifact_path or source_artifact_path,
                "field_path": market_seed.get("field_path") or "candidate",
            })

        odds_decimal = _to_decimal(
            valuation_entry.get("odds_decimal")
            or (valuation_entry.get("odds") or {}).get("market_best")
        )
        report = evaluate_candidate_analyzability(valuation_entry, s3_entry, market_seed)
        reports.append(report)

        if report["analyzability_status"] == "REVIEW_ONLY_PARTIAL_DATA":
            analytical_status = "REVIEW_ONLY_PARTIAL_DATA"
            probability_contract["model_probability"] = None
        elif report["analyzability_status"] == "RESEARCH_GAP_MINIMAL_HYDRATION":
            if _normalized(probability_contract["probability_confidence"]).upper() in {"LOW", "LOW_CONFIDENCE", "BLOCKED"}:
                analytical_status = "INSUFFICIENT_MODEL_PROBABILITY"
            else:
                analytical_status = "RESEARCH_GAP_MINIMAL_HYDRATION"
            probability_contract["model_probability"] = None
        elif report["analyzability_status"] == "BLOCKED_HYDRATION_FAILED":
            if _normalized(probability_contract["probability_confidence"]).upper() in {"LOW", "LOW_CONFIDENCE", "BLOCKED"}:
                analytical_status = "INSUFFICIENT_MODEL_PROBABILITY"
            else:
                analytical_status = "BLOCKED_HYDRATION_FAILED"
            probability_contract["model_probability"] = None
        elif report["analyzability_status"] == "ANALYZABLE" and probability_input_valid and probability_input.promotion_safe_model_probability:
            analytical_status = "ANALYTICAL_READY"
        elif report["analyzability_status"] == "RESEARCH_GAP_STATS_MISSING":
            analytical_status = "INSUFFICIENT_SUPPORTING_STATS"
        elif report["analyzability_status"] == "RESEARCH_GAP_L10_MISSING":
            if "SAMPLE_SIZE_INSUFFICIENT" in report["blocker_reasons"]:
                analytical_status = "INSUFFICIENT_SUPPORTING_STATS"
            else:
                analytical_status = "INSUFFICIENT_MODEL_PROBABILITY"
        elif report["analyzability_status"] == "RESEARCH_GAP_UNKNOWN_STAT_SEMANTICS":
            analytical_status = "INSUFFICIENT_SUPPORTING_STATS"
        elif report["analyzability_status"] == "RESEARCH_GAP_MARKET_INPUT_NOT_BUILT":
            analytical_status = "INSUFFICIENT_MODEL_PROBABILITY"
        elif report["analyzability_status"] == "LINE_OR_DIRECTION_GAP":
            if "LINE_MISSING" in report["blocker_reasons"]:
                analytical_status = "MISSING_LINE"
            else:
                analytical_status = "DIRECTION_MISSING"
            if not source_gaps:
                source_gaps.append({
                    "code": "LINE_MISSING" if "LINE_MISSING" in report["blocker_reasons"] else "DIRECTION_MISSING",
                    "field": "line" if "LINE_MISSING" in report["blocker_reasons"] else "direction",
                    "artifact": source_artifact_path,
                    "field_path": f"candidates[{position}]",
                })
        elif report["analyzability_status"] == "IDENTITY_GAP":
            analytical_status = "MISSING_SPORT"
        elif report["analyzability_status"] == "UNSUPPORTED_MARKET_FAMILY":
            if "UNSUPPORTED_PROP_MATCH" in report["blocker_reasons"]:
                analytical_status = "UNSUPPORTED_PROP_MATCH"
            elif "AMBIGUOUS_MARKET_LABEL" in report["blocker_reasons"]:
                analytical_status = "AMBIGUOUS_MARKET_LABEL"
            else:
                analytical_status = "MISSING_MARKET_FAMILY"
                if not source_gaps:
                    source_gaps.append({
                        "code": "MISSING_MARKET_FAMILY",
                        "field": "market_family",
                        "artifact": source_artifact_path,
                        "field_path": "candidate",
                    })
        else:
            analytical_status = "ANALYTICAL_READY"
            if not sport:
                analytical_status = "MISSING_SPORT"
            elif not competition:
                analytical_status = "MISSING_COMPETITION"
            elif market_seed.get("mapping_status") == "UNSUPPORTED_PROP_MATCH":
                analytical_status = "UNSUPPORTED_PROP_MATCH"
            elif market_seed.get("mapping_status") == "AMBIGUOUS_MARKET_LABEL":
                analytical_status = "AMBIGUOUS_MARKET_LABEL"
            elif not market_seed["market_family"]:
                analytical_status = "MISSING_MARKET_FAMILY"
            elif market_seed.get("mapping_status") == "LINE_MISSING" or (market_seed["market_family"] in {"TOTALS", "GOALS_TOTALS", "HANDICAP", "CORNERS", "CARDS", "SHOTS", "SHOTS_ON_TARGET"} and market_seed["line"] in (None, "", "MISSING")):
                analytical_status = "MISSING_LINE"
            elif market_seed.get("mapping_status") == "DIRECTION_MISSING":
                analytical_status = "DIRECTION_MISSING"
            elif probability_contract["model_probability"] is None:
                analytical_status = "INSUFFICIENT_MODEL_PROBABILITY"
            elif _probability_confidence_is_blocked(probability_contract["probability_confidence"]):
                analytical_status = "INSUFFICIENT_MODEL_PROBABILITY"
            elif not supporting_stats:
                analytical_status = "INSUFFICIENT_SUPPORTING_STATS"

        if analytical_status != "ANALYTICAL_READY":
            probability_contract["model_probability"] = None
            if not probability_contract["probability_missing_reason"] and probability_input_reason != "PASS":
                probability_contract["probability_missing_reason"] = probability_input_reason

        probability_status = (
            "MODEL_PROBABILITY_READY"
            if probability_contract["model_probability"] is not None and analytical_status == "ANALYTICAL_READY"
            else "INSUFFICIENT_MODEL_PROBABILITY"
        )

        draft = CandidateDraft(
            candidate_id=candidate_id,
            event_id=event_id,
            fixture_id=fixture_id,
            sport=sport,
            competition=competition,
            participants=participants,
            start_time=start_time,
            market_family=market_seed["market_family"],
            market_type=market_seed["market_type"],
            market_label=market_seed.get("market_label", market_seed["market_type"]),
            outcome_name=market_seed.get("selection", ""),
            selection=market_seed["selection"],
            pick=market_seed["pick"],
            direction=market_seed.get("direction", ""),
            line=market_seed["line"],
            odds_decimal=odds_decimal,
            odds_source=_normalized(valuation_entry.get("odds_source")),
            odds_as_of=_normalized(valuation_entry.get("odds_as_of") or valuation_entry.get("odds_captured_at_utc")),
            model_probability=probability_contract["model_probability"],
            probability_status=probability_status,
            probability_method=probability_contract["probability_method"],
            probability_sources=list(probability_contract["probability_sources"] or []),
            probability_as_of=probability_contract["probability_as_of"],
            probability_confidence=probability_contract["probability_confidence"],
            probability_missing_reason=probability_contract["probability_missing_reason"],
            hydration_status=probability_input.hydration_status,
            promotion_status=probability_input.promotion_status,
            source_provider=probability_input.source_provider,
            stats_as_of=probability_input.stats_as_of,
            stat_semantics_status=probability_input.stat_semantics_status,
            promotion_safe_model_probability=probability_input.promotion_safe_model_probability,
            market_probability_validation_reason=probability_input_reason,
            ready_for_manual_operator_quote_review=(
                analytical_status == "ANALYTICAL_READY" and probability_input_valid
            ),
            supporting_stats=supporting_stats,
            source_gaps=source_gaps,
            analytical_status=analytical_status,
            source_artifact_path=source_artifact_path,
        )

        draft_dict = draft.to_dict()
        if analytical_status == "ANALYTICAL_READY":
            analytical_ready.append(draft_dict)
        elif analytical_status == "REVIEW_ONLY_PARTIAL_DATA":
            review_only_partial_data.append(draft_dict)
        elif analytical_status == "RESEARCH_GAP_MINIMAL_HYDRATION":
            research_gap_minimal_hydration.append(draft_dict)
        elif analytical_status == "BLOCKED_HYDRATION_FAILED":
            blocked_stats_missing.append(
                ResearchCandidateBlocked(**asdict(draft), blocking_reason=analytical_status).to_dict()
            )
        elif analytical_status == "INSUFFICIENT_MODEL_PROBABILITY":
            blocked_probability_missing.append(
                ResearchCandidateBlocked(**asdict(draft), blocking_reason=analytical_status).to_dict()
            )
        elif analytical_status in {"MISSING_SPORT", "MISSING_COMPETITION", "MISSING_MARKET_FAMILY", "MISSING_LINE", "DIRECTION_MISSING", "UNSUPPORTED_PROP_MATCH", "AMBIGUOUS_MARKET_LABEL"}:
            blocked_identity_missing.append(
                ResearchCandidateBlocked(**asdict(draft), blocking_reason=analytical_status).to_dict()
            )
        elif analytical_status == "INSUFFICIENT_SUPPORTING_STATS":
            blocked_stats_missing.append(
                ResearchCandidateBlocked(**asdict(draft), blocking_reason=analytical_status).to_dict()
            )
        else:
            blocked_identity_missing.append(
                ResearchCandidateBlocked(**asdict(draft), blocking_reason="NOT_ANALYTICAL_ELIGIBLE").to_dict()
            )

        # Define helper mapping to structured reason
        def _map_to_structured_reason(status: str) -> str:
            if status == "ANALYTICAL_READY":
                return "READY"
            if status == "REVIEW_ONLY_PARTIAL_DATA":
                return "PARTIAL"
            if status in {"INSUFFICIENT_MODEL_PROBABILITY", "PROBABILITY_MISSING"}:
                return "PROBABILITY_MISSING"
            if status == "PROBABILITY_INVALID":
                return "PROBABILITY_INVALID"
            if status in {"INSUFFICIENT_SUPPORTING_STATS", "BLOCKED_HYDRATION_FAILED", "SUPPORTING_STATS_MISSING"}:
                return "SUPPORTING_STATS_MISSING"
            if status in {"MISSING_MARKET_FAMILY", "UNSUPPORTED_PROP_MATCH", "AMBIGUOUS_MARKET_LABEL", "MARKET_IDENTITY_INVALID"}:
                return "MARKET_IDENTITY_INVALID"
            if status in {"MISSING_SPORT", "MISSING_COMPETITION", "IDENTITY_GAP", "EVENT_IDENTITY_INVALID"}:
                return "EVENT_IDENTITY_INVALID"
            if status == "STALE_INPUT":
                return "STALE_INPUT"
            if status == "UNSUPPORTED_MARKET":
                return "UNSUPPORTED_MARKET"
            if status == "SOURCE_BINDING_INVALID":
                return "SOURCE_BINDING_INVALID"
            return "OTHER_EXPLICIT_REASON"

        rejection_ledger.append({
            "candidate_id": candidate_id,
            "input_s3_hash": valuation_payload.get("source_s3_sha256") or (s3_payload or {}).get("source_s3_sha256"),
            "input_s4_hash": valuation_payload.get("source_s4_sha256") or valuation_payload.get("source_s4_hash"),
            "fields_inspected": ["model_probability", "best_market", "stats_summary"],
            "analytical_result": analytical_status,
            "pricing_result": valuation_entry.get("pricing_status") or "UNPRICED",
            "reason_codes": [_map_to_structured_reason(analytical_status)],
            "evidence_paths": [source_artifact_path],
        })

        if odds_decimal is not None and odds_decimal > Decimal("1") and analytical_status == "ANALYTICAL_READY":
            priced_candidates.append(draft_dict)

    # Rank ready candidates preferentially
    analytical_ready = rank_analyzable_candidates(analytical_ready)

    # Compute gap reasons
    gap_reasons: dict[str, int] = {}
    for r in reports:
        if r["analyzability_status"] != "ANALYZABLE":
            for blocker in r["blocker_reasons"]:
                gap_reasons[blocker] = gap_reasons.get(blocker, 0) + 1

    # Write analyzability prefilter report to approved path (must not catch silently)
    from bet.pipeline.analyzability_prefilter import write_analyzability_report
    workspace_report_path = _resolve_analyzability_report_path(source_artifact_path)
    write_analyzability_report(workspace_report_path, reports)

    # Set package type
    if analytical_ready:
        package_type = "ANALYTICAL_ONLY"
    elif review_only_partial_data:
        package_type = "REVIEW_ONLY_PARTIAL_DATA_PACKAGE"
    else:
        package_type = "RESEARCH_GAP_PACKAGE"

    # Enforce strict partition invariant of Phase 7
    input_ids = set()
    for position, valuation_entry in enumerate(valuation_candidates):
        key = _identity_key(valuation_entry)
        alt_key = _normalized_key(
            valuation_entry.get("home_team"),
            valuation_entry.get("away_team"),
            valuation_entry.get("scheduled_time") or valuation_entry.get("kickoff") or valuation_entry.get("start_time"),
        )
        s3_entry = s3_index.get(key) or (s3_index.get(alt_key) if alt_key else None)
        shortlist_entry = shortlist_index.get(key) or (shortlist_index.get(alt_key) if alt_key else None)
        c_id = _normalized(
            valuation_entry.get("candidate_id")
            or (s3_entry or {}).get("candidate_id")
            or valuation_entry.get("fixture_key")
            or valuation_entry.get("fixture_id")
            or f"candidate-{position + 1}"
        )
        input_ids.add(c_id)

    ready_ids = set(c["candidate_id"] for c in analytical_ready)
    partial_ids = set(c["candidate_id"] for c in review_only_partial_data)
    blocked_ids = set(c["candidate_id"] for c in blocked_probability_missing)
    blocked_ids.update(c["candidate_id"] for c in blocked_stats_missing)
    blocked_ids.update(c["candidate_id"] for c in blocked_identity_missing)
    blocked_ids.update(c["candidate_id"] for c in research_gap_minimal_hydration)

    all_assigned = ready_ids.union(partial_ids).union(blocked_ids)
    disappeared = input_ids - all_assigned
    if disappeared:
        raise ValueError(f"Candidate partition invariant failed: {disappeared} are missing from any terminal categories!")

    return {
        "artifact_type": "ANALYTICAL_CANDIDATE_HANDOFF",
        "created_at_utc": _now_iso(),
        "source_artifact_path": source_artifact_path,
        "source_input_path": valuation_payload.get("source_input_path"),
        "package_type": package_type,
        "gap_reasons": gap_reasons,
        "analyzability_reports": reports,
        "analytical_ready": analytical_ready,
        "blocked_probability_missing": blocked_probability_missing,
        "blocked_stats_missing": blocked_stats_missing,
        "blocked_identity_missing": blocked_identity_missing,
        "review_only_partial_data": review_only_partial_data,
        "research_gap_minimal_hydration": research_gap_minimal_hydration,
        "priced_candidates": priced_candidates,
        "rejection_ledger": rejection_ledger,
        "counts": {
            "analytical_ready": len(analytical_ready),
            "blocked_probability_missing": len(blocked_probability_missing),
            "blocked_stats_missing": len(blocked_stats_missing),
            "blocked_identity_missing": len(blocked_identity_missing),
            "review_only_partial_data": len(review_only_partial_data),
            "research_gap_minimal_hydration": len(research_gap_minimal_hydration),
            "priced_candidates": len(priced_candidates),
        },
    }


def write_analytical_candidate_handoff(path: Path, payload: dict[str, Any]) -> Path:
    from bet.pipeline.run_evidence import write_json_atomic
    write_json_atomic(path, payload)
    return Path(path)
