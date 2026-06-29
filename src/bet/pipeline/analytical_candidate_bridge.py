"""Bridge S3/S4 shortlist candidates into analytical handoff drafts."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    market_type = _normalized(seed.get("market_type") or seed.get("market_family") or seed.get("name")).lower()
    if not market_type:
        return ""
    if any(token in market_type for token in ("goal", "total", "over", "under")):
        return "TOTALS"
    if "corner" in market_type:
        return "CORNERS"
    if any(token in market_type for token in ("card", "booking")):
        return "CARDS"
    if any(token in market_type for token in ("moneyline", "match winner", "winner", "ml", "draw_no_bet", "double_chance")):
        return "RESULT"
    if "spread" in market_type or "handicap" in market_type:
        return "HANDICAP"
    return market_type.upper().replace(" ", "_")


def _supported_analytical_family(family: str) -> bool:
    return family in {"RESULT", "TOTALS", "CORNERS", "CARDS", "HANDICAP"}


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
) -> dict[str, Any]:
    best_market = (s3_entry or {}).get("best_market") or (valuation_entry.get("best_market") or {})
    if isinstance(best_market, dict) and best_market.get("name"):
        family = _market_family_from_seed(best_market)
        return {
            "market_family": family if _supported_analytical_family(family) else "",
            "market_type": _normalized(best_market.get("name")),
            "pick": _pick_from_seed(best_market, participants),
            "selection": _pick_from_seed(best_market, participants),
            "line": best_market.get("line"),
            "source": "s3_best_market",
        }

    shortlist_market = _match_shortlist_market(shortlist_entry, valuation_entry)
    if shortlist_market:
        family = _market_family_from_seed(shortlist_market)
        return {
            "market_family": family if _supported_analytical_family(family) else "",
            "market_type": _normalized(shortlist_market.get("market_type") or shortlist_market.get("market")),
            "pick": _pick_from_seed(shortlist_market, participants),
            "selection": _pick_from_seed(shortlist_market, participants),
            "line": shortlist_market.get("point"),
            "source": "shortlist_odds_market",
        }

    return {
        "market_family": "",
        "market_type": "",
        "pick": "",
        "selection": "",
        "line": None,
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
    selection: str
    pick: str
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
    priced_candidates: list[dict[str, Any]] = []

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

        market_seed = _market_seed(valuation_entry, s3_entry, shortlist_entry, participants)
        if not market_seed["market_family"]:
            source_gaps.append(
                {
                    "code": "MARKET_FAMILY_MAPPING_MISSING",
                    "field": "market_family",
                    "artifact": source_artifact_path,
                    "field_path": f"candidates[{position}].best_market",
                }
            )

        supporting_stats = _supporting_stats_from_s3(s3_entry)
        probability_contract = _probability_contract(valuation_entry, s3_entry)
        odds_decimal = _to_decimal(
            valuation_entry.get("odds_decimal")
            or (valuation_entry.get("odds") or {}).get("market_best")
        )

        probability_status = (
            "MODEL_PROBABILITY_READY"
            if probability_contract["model_probability"] is not None
            else "INSUFFICIENT_MODEL_PROBABILITY"
        )
        analytical_status = "ANALYTICAL_READY"
        if not sport:
            analytical_status = "MISSING_SPORT"
        elif not competition:
            analytical_status = "MISSING_COMPETITION"
        elif not market_seed["market_family"]:
            analytical_status = "MISSING_MARKET_FAMILY"
        elif market_seed["market_family"] in {"TOTALS", "HANDICAP", "CORNERS", "CARDS"} and market_seed["line"] in (None, "", "MISSING"):
            analytical_status = "MISSING_LINE"
        elif probability_contract["model_probability"] is None:
            analytical_status = "INSUFFICIENT_MODEL_PROBABILITY"
        elif not supporting_stats:
            analytical_status = "INSUFFICIENT_SUPPORTING_STATS"

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
            selection=market_seed["selection"],
            pick=market_seed["pick"],
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
            supporting_stats=supporting_stats,
            source_gaps=source_gaps,
            analytical_status=analytical_status,
            source_artifact_path=source_artifact_path,
        )

        draft_dict = draft.to_dict()
        if analytical_status == "ANALYTICAL_READY":
            analytical_ready.append(draft_dict)
        elif analytical_status == "INSUFFICIENT_MODEL_PROBABILITY":
            blocked_probability_missing.append(
                ResearchCandidateBlocked(**asdict(draft), blocking_reason=analytical_status).to_dict()
            )
        elif analytical_status in {"MISSING_SPORT", "MISSING_COMPETITION", "MISSING_MARKET_FAMILY", "MISSING_LINE"}:
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

        if odds_decimal is not None and odds_decimal > Decimal("1"):
            priced_candidates.append(draft_dict)

    return {
        "artifact_type": "ANALYTICAL_CANDIDATE_HANDOFF",
        "created_at_utc": _now_iso(),
        "source_artifact_path": source_artifact_path,
        "source_input_path": valuation_payload.get("source_input_path"),
        "analytical_ready": analytical_ready,
        "blocked_probability_missing": blocked_probability_missing,
        "blocked_stats_missing": blocked_stats_missing,
        "blocked_identity_missing": blocked_identity_missing,
        "priced_candidates": priced_candidates,
        "counts": {
            "analytical_ready": len(analytical_ready),
            "blocked_probability_missing": len(blocked_probability_missing),
            "blocked_stats_missing": len(blocked_stats_missing),
            "blocked_identity_missing": len(blocked_identity_missing),
            "priced_candidates": len(priced_candidates),
        },
    }


def write_analytical_candidate_handoff(path: Path, payload: dict[str, Any]) -> Path:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return resolved
