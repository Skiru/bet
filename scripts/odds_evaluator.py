#!/usr/bin/env python3
"""S4 Odds Evaluation — cross-validate odds, compute EV, detect drift.

Extracted from pipeline_orchestrator.py (Phase 3.1).
Supports --verbose + AGENT_SUMMARY for agent-driven pipeline (R17/R19).
"""

import argparse
import copy
from datetime import datetime, timezone
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (same as orchestrator)
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).parent
ROOT_DIR = SCRIPTS_DIR.parent
DATA_DIR = Path(os.environ.get("BET_PIPELINE_DATA_DIR", str(ROOT_DIR / "betting" / "data")))

# Add scripts/ and src/ to path for imports
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))

from utils import normalize_team_name as _norm_team
from bet.utils import names_match
from bet.pipeline.market_probability_inputs import extract_market_semantics
from bet.pipeline.canonical_continuity import (
    ContinuityContractError,
    bind_candidate_identity,
    bind_event_identity,
    file_sha256,
)


def _runtime_mode_value(runtime_mode: str | None) -> str:
    return str(runtime_mode or os.environ.get("BET_PIPELINE_RUNTIME_MODE") or "DRY_RUN").upper()


def _is_production_mode(runtime_mode: str | None) -> bool:
    return _runtime_mode_value(runtime_mode) == "PRODUCTION"


def _is_protected_repo_path(path: Path | str | None) -> bool:
    if not path:
        return False
    abs_path = Path(path).resolve()
    for parent in (
        (ROOT_DIR / "betting" / "data").resolve(),
        (ROOT_DIR / "betting" / "coupons").resolve(),
        (ROOT_DIR / "reports").resolve(),
    ):
        try:
            abs_path.relative_to(parent)
            return True
        except ValueError:
            pass
    return False


def _extract_candidate_entries(payload):
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("analyses", "candidates", "results", "valuations", "events"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    inner = payload.get("payload")
    if isinstance(inner, dict):
        return _extract_candidate_entries(inner)
    return []


def _load_candidates_from_json(path: Path) -> tuple[list[dict], dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates = [copy.deepcopy(item) for item in _extract_candidate_entries(payload)]
    return candidates, {
        "source": "explicit_input",
        "parity": {"status": "explicit_input"},
        "counts": {
            "json": len(candidates),
            "db": 0,
            "canonical": len(candidates),
        },
        "input_path": str(path),
    }


def _coerce_probability(value):
    if value is None:
        return None
    try:
        value_str = str(value).strip().rstrip("%")
        if "/" in value_str:
            num, den = value_str.split("/", 1)
            parsed = float(num) / float(den)
        else:
            parsed = float(value_str)
            if parsed > 1.0:
                parsed = parsed / 100.0
        return round(parsed, 4)
    except (ValueError, ZeroDivisionError):
        return None


def _candidate_fixture_key(candidate: dict) -> str | None:
    existing = candidate.get("fixture_key")
    if existing:
        return str(existing)
    home = candidate.get("home_team") or ""
    away = candidate.get("away_team") or ""
    if home and away:
        return f"{_norm_team(home)}|{_norm_team(away)}"
    return None


def _candidate_safety_score(candidate: dict):
    best_market = candidate.get("best_market") or {}
    if isinstance(best_market, dict) and best_market.get("safety_score") is not None:
        return best_market.get("safety_score")
    return candidate.get("safety_score")


def _probability_confidence_blocks_promotion(confidence: str | None) -> bool:
    return str(confidence or "").strip().upper() in {"BLOCKED", "LOW", "MINIMAL", "LOW_CONFIDENCE"}


def _load_json_payload(path: Path | None) -> dict | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _resolve_shortlist_payload(input_path: Path | None) -> dict | None:
    if input_path is None:
        return None
    payload = _load_json_payload(input_path)
    if not isinstance(payload, dict):
        return None
    source_label = str(payload.get("source") or "")
    if source_label.startswith("shortlist:"):
        shortlist_path = Path(source_label.split(":", 1)[1])
        return _load_json_payload(shortlist_path)
    sibling = input_path.with_name(input_path.name.replace("_s3_deep_stats.json", "_s2_shortlist.json"))
    return _load_json_payload(sibling)


def _shortlist_identity_key(entry: dict) -> str:
    return "|".join(
        [
            str(entry.get("sport") or "").strip(),
            str(entry.get("home_team") or "").strip(),
            str(entry.get("away_team") or "").strip(),
            str(entry.get("kickoff") or entry.get("scheduled_time") or "")[:10],
        ]
    )


def _build_shortlist_index(shortlist_payload: dict | None) -> dict[str, dict]:
    if not isinstance(shortlist_payload, dict):
        return {}
    return {
        _shortlist_identity_key(entry): entry
        for entry in shortlist_payload.get("candidates", [])
        if isinstance(entry, dict)
    }


def _candidate_identity_key(entry: dict) -> str:
    return "|".join(
        [
            str(entry.get("sport") or "").strip(),
            str(entry.get("home_team") or "").strip(),
            str(entry.get("away_team") or "").strip(),
            str(entry.get("kickoff") or entry.get("scheduled_time") or "")[:10],
        ]
    )


def _to_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _match_shortlist_market(shortlist_entry: dict | None, candidate: dict) -> dict | None:
    if not shortlist_entry:
        return None
    odds_markets = shortlist_entry.get("odds_markets") or []
    if not isinstance(odds_markets, list):
        return None
    target_odds = _to_float((candidate.get("odds") or {}).get("market_best") or candidate.get("odds_decimal"))
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

    def _priority(entry: dict) -> tuple[int, int, str]:
        market_type = str(entry.get("market_type") or entry.get("market") or "").strip().lower()
        outcome = str(entry.get("outcome") or "").strip().lower()
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


def _apply_market_semantics(candidate: dict, semantics_source: dict, *, participants: list[str], source_artifact_path: str, field_path: str) -> bool:
    semantics = extract_market_semantics(
        semantics_source,
        participants=participants,
        source_artifact_path=source_artifact_path,
        field_path=field_path,
    )
    if not semantics.market_family and not semantics.mapping_status:
        return False
    candidate["market_family"] = semantics.market_family or candidate.get("market_family")
    candidate["market_type"] = semantics.market_type or candidate.get("market_type")
    candidate["market"] = semantics.market_label or candidate.get("market") or semantics.market_type
    candidate["market_label"] = semantics.market_label or candidate.get("market_label")
    candidate["outcome_name"] = semantics.outcome_name or candidate.get("outcome_name")
    candidate["selection"] = semantics.selection or candidate.get("selection")
    candidate["pick"] = candidate.get("pick") or semantics.selection or semantics.direction
    candidate["direction"] = semantics.direction or candidate.get("direction")
    if candidate.get("line") is None:
        candidate["line"] = semantics.line
    if candidate.get("point") is None:
        candidate["point"] = semantics.point
    candidate["provider_market_key"] = semantics.provider_market_key or candidate.get("provider_market_key")
    candidate["bookmaker"] = semantics.bookmaker or candidate.get("bookmaker")
    candidate["source_artifact_path"] = candidate.get("source_artifact_path") or semantics.source_artifact_path
    candidate["market_semantics"] = semantics.to_dict()
    return True


def _enrich_candidate_market_semantics(candidates: list[dict], shortlist_payload: dict | None, source_artifact_path: str) -> None:
    shortlist_index = _build_shortlist_index(shortlist_payload)
    shortlist_artifact_path = str(shortlist_payload.get("source_artifact_path") or "") if isinstance(shortlist_payload, dict) else ""
    for candidate in candidates:
        participants = [part for part in (candidate.get("home_team"), candidate.get("away_team")) if part]
        if _apply_market_semantics(
            candidate,
            candidate,
            participants=participants,
            source_artifact_path=source_artifact_path,
            field_path="candidate",
        ):
            continue
        best_market = candidate.get("best_market") or {}
        if isinstance(best_market, dict) and best_market:
            if _apply_market_semantics(
                candidate,
                best_market,
                participants=participants,
                source_artifact_path=source_artifact_path,
                field_path="best_market",
            ):
                continue
        shortlist_entry = shortlist_index.get(_candidate_identity_key(candidate))
        shortlist_market = _match_shortlist_market(shortlist_entry, candidate)
        if shortlist_market:
            _apply_market_semantics(
                candidate,
                shortlist_market,
                participants=participants,
                source_artifact_path=shortlist_artifact_path or source_artifact_path,
                field_path="odds_markets[]",
            )


def _valuation_warnings(candidate: dict, has_odds: bool, has_ev: bool, has_safety: bool) -> list[str]:
    warnings = []
    for source_key in ("valuation_warnings", "warnings"):
        source = candidate.get(source_key)
        if isinstance(source, list):
            warnings.extend(str(item) for item in source if item is not None)
    if not has_odds:
        warnings.append("NO_ODDS")
    if not has_ev:
        warnings.append("NO_EV")
    if not has_safety:
        warnings.append("NO_SAFETY")
    deduped: list[str] = []
    seen: set[str] = set()
    for item in warnings:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def _valuation_status(candidate: dict, *, has_odds: bool, has_ev: bool, has_safety: bool) -> str:
    if has_odds and has_ev and has_safety:
        return "VALUED"
    if has_odds and has_ev:
        return "PARTIAL"
    if not has_odds:
        return "NO_ODDS"
    if not has_ev:
        return "NO_EV"
    if not has_safety and not candidate.get("best_market"):
        return "INSUFFICIENT_DATA"
    return "PARTIAL"


def _odds_snapshot_paths() -> list[str]:
    snapshots: list[str] = []
    for name in ("odds_api_snapshot.json", "odds_api_io_snapshot.json", "odds_multi_sources.json"):
        path = DATA_DIR / name
        if path.exists():
            snapshots.append(str(path.resolve()))
    return snapshots


def _build_valuation_candidate(candidate: dict) -> dict:
    best_market = candidate.get("best_market") or {}
    odds = candidate.get("odds") if isinstance(candidate.get("odds"), dict) else {}
    market_count = candidate.get("market_count")
    markets_evaluated = candidate.get("markets_evaluated")
    participants = candidate.get("participants") or [candidate.get("home_team"), candidate.get("away_team")]
    participants = [participant for participant in participants if participant]
    
    # Precedence: best_market.probability > top-level.probability > hit_rate_l10
    probability = None
    if isinstance(best_market, dict) and best_market.get("probability") is not None:
        probability = best_market.get("probability")
    else:
        for k in ("probability", "model_probability", "prob"):
            if candidate.get(k) is not None:
                probability = candidate.get(k)
                break
    if probability is None:
        probability = candidate.get("hit_rate_l10") or best_market.get("hit_rate_l10")

    has_odds = bool(odds) or candidate.get("best_odds") is not None
    has_ev = candidate.get("ev") is not None
    has_safety = _candidate_safety_score(candidate) is not None or bool(candidate.get("safety_markets"))
    return {
        "candidate_id": candidate.get("candidate_id") or _candidate_fixture_key(candidate) or candidate.get("fixture_id"),
        "event_id": candidate.get("canonical_event_id") or candidate.get("event_id") or candidate.get("fixture_id"),
        "canonical_event_id": candidate.get("canonical_event_id"),
        "selection_id": candidate.get("selection_id"),
        "fixture_key": _candidate_fixture_key(candidate),
        "fixture_id": candidate.get("fixture_id"),
        "sport": candidate.get("sport"),
        "home_team": candidate.get("home_team"),
        "away_team": candidate.get("away_team"),
        "participants": participants,
        "competition": candidate.get("competition"),
        "scheduled_time": candidate.get("scheduled_time") or candidate.get("kickoff"),
        "kickoff": candidate.get("kickoff") or candidate.get("scheduled_time"),
        "source_steps": ["S3", "S4"],
        "market_family": candidate.get("market_family"),
        "market": candidate.get("market") or candidate.get("market_label") or candidate.get("market_type") or best_market.get("name"),
        "market_type": candidate.get("market_type") or best_market.get("name"),
        "market_label": candidate.get("market_label") or candidate.get("market") or candidate.get("market_type") or best_market.get("name"),
        "outcome_name": candidate.get("outcome_name"),
        "selection": candidate.get("selection") or candidate.get("pick") or best_market.get("selection") or best_market.get("direction"),
        "pick": candidate.get("pick") or best_market.get("direction"),
        "direction": candidate.get("direction") or best_market.get("direction"),
        "line": candidate.get("line") if candidate.get("line") is not None else best_market.get("line"),
        "period": candidate.get("period") or "full_time",
        "point": candidate.get("point"),
        "provider_market_key": candidate.get("provider_market_key") or candidate.get("market_type"),
        "bookmaker": candidate.get("bookmaker") or candidate.get("best_bookmaker"),
        "source_artifact_path": candidate.get("source_artifact_path"),
        "market_semantics": candidate.get("market_semantics") or {},
        "model_probability": _coerce_probability(candidate.get("model_probability")),
        "reference_model_probability": _coerce_probability(candidate.get("reference_model_probability")),
        "probability_method": candidate.get("probability_method"),
        "probability_sources": candidate.get("probability_sources") or [],
        "probability_as_of": candidate.get("probability_as_of"),
        "probability_confidence": candidate.get("probability_confidence"),
        "probability_missing_reason": candidate.get("probability_missing_reason"),
        "stats_gap_reason": candidate.get("stats_gap_reason"),
        "probability": _coerce_probability(probability),
        "hit_rate_l10": candidate.get("hit_rate_l10") or best_market.get("hit_rate_l10"),
        "hit_rate_l5": candidate.get("hit_rate_l5") or best_market.get("hit_rate_l5"),
        "best_market": best_market if isinstance(best_market, dict) else {},
        "market_count": market_count,
        "markets_evaluated": markets_evaluated,
        "odds_decimal": (odds or {}).get("market_best") or candidate.get("best_odds"),
        "odds_as_of": candidate.get("odds_as_of") or candidate.get("odds_captured_at_utc"),
        "odds": odds,
        "odds_source": candidate.get("odds_source"),
        "ev": candidate.get("ev"),
        "ev_source": candidate.get("ev_source"),
        "ev_components": candidate.get("ev_components"),
        "ev_missing_reason": candidate.get("ev_missing_reason"),
        "safety_score": _candidate_safety_score(candidate),
        "safety_markets": candidate.get("safety_markets") if isinstance(candidate.get("safety_markets"), list) else [],
        "valuation_warnings": _valuation_warnings(candidate, has_odds, has_ev, has_safety),
        "valuation_status": _valuation_status(candidate, has_odds=has_odds, has_ev=has_ev, has_safety=has_safety),
    }


def _build_valuation_output(
    candidates: list[dict],
    *,
    date: str,
    run_id: str | None,
    runtime_mode: str | None,
    source_input_path: Path | None,
) -> dict:
    valuation_candidates = []
    for index, candidate in enumerate(candidates):
        item = _build_valuation_candidate(candidate)
        
        # Determine analytical_status
        prob = item.get("model_probability") or item.get("probability")
        conf = str(item.get("probability_confidence") or "").upper()
        
        if prob is not None:
            if conf in {"BLOCKED", "LOW", "MINIMAL", "LOW_CONFIDENCE"}:
                analytical_status = "REVIEW_ONLY_PARTIAL_DATA"
            else:
                analytical_status = "ANALYTICAL_READY"
        else:
            analytical_status = "ANALYTICAL_BLOCKED"
            
        # Determine pricing_status
        odds_dec = (item.get("odds") or {}).get("market_best") or item.get("odds_decimal")
        if odds_dec is not None:
            pricing_status = "PRICED"
        else:
            if analytical_status == "ANALYTICAL_BLOCKED":
                pricing_status = "PRICING_BLOCKED_INVALID_INPUT"
            else:
                pricing_status = "PRICING_DEGRADED"
                
        # Determine risk_status
        if analytical_status == "ANALYTICAL_READY":
            risk_status = "ACCEPTABLE_FOR_MANUAL_QUOTE_REVIEW"
        elif analytical_status == "REVIEW_ONLY_PARTIAL_DATA":
            risk_status = "RECHECK_REQUIRED"
        else:
            risk_status = "REJECTED"
            
        # Determine final_status
        if analytical_status == "ANALYTICAL_READY":
            if pricing_status == "PRICED":
                final_status = "READY_FOR_PRICED_REVIEW"
            else:
                final_status = "READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW"
        elif analytical_status == "REVIEW_ONLY_PARTIAL_DATA":
            final_status = "READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW"
        else:
            final_status = "BLOCKED"
            
        identity_error: str | None = None
        try:
            item = bind_candidate_identity(item)
        except ContinuityContractError as exc:
            identity_error = str(exc)
            try:
                item = bind_event_identity(item)
            except ContinuityContractError:
                pass
            analytical_status = "ANALYTICAL_BLOCKED"
            pricing_status = "PRICING_BLOCKED_INVALID_INPUT"
            risk_status = "REJECTED"
            final_status = "BLOCKED"
        item["identity_error"] = identity_error
        item["analytical_status"] = analytical_status
        item["pricing_status"] = pricing_status
        item["risk_status"] = risk_status
        item["final_status"] = final_status
        
        # Missing odds must block EV, Kelly, stakes, bettable, final placement
        if pricing_status != "PRICED":
            item["ev"] = None
            item["kelly_fraction"] = None
            item["stake"] = None
            item["bettable"] = False
            if "ev_components" in item and isinstance(item["ev_components"], dict):
                item["ev_components"]["odds"] = None
                item["ev_components"]["ev"] = None
            
        valuation_candidates.append(item)

    market_semantics_ready_count = 0
    promotion_safe_model_probability_count = 0
    reference_model_probability_count = 0
    for candidate in valuation_candidates:
        family = candidate.get("market_family") or ""
        direction = candidate.get("direction") or ""
        line = candidate.get("line")
        if family and (family == "RESULT" or direction) and (family not in {"GOALS_TOTALS", "CORNERS", "CARDS", "SHOTS", "SHOTS_ON_TARGET"} or line is not None):
            market_semantics_ready_count += 1
        if candidate.get("model_probability") is not None:
            promotion_safe_model_probability_count += 1
        if candidate.get("reference_model_probability") is not None:
            reference_model_probability_count += 1
    
    from collections import Counter
    reasons = [c.get("ev_missing_reason") for c in valuation_candidates if c.get("ev_missing_reason") is not None]
    ev_missing_reason_counts = dict(Counter(reasons))
    
    candidates_with_ev = sum(1 for c in valuation_candidates if c.get("ev") is not None)
    positive_ev_count = sum(1 for c in valuation_candidates if c.get("ev") is not None and c.get("ev") > 0)

    # Classify S4 top-level status
    if not valuation_candidates:
        status = "READY_ANALYTICAL_PRICE_PENDING"
    else:
        any_analytical_ready = any(c.get("analytical_status") == "ANALYTICAL_READY" for c in valuation_candidates)
        all_analytical_blocked = all(c.get("analytical_status") == "ANALYTICAL_BLOCKED" for c in valuation_candidates)
        
        if all_analytical_blocked:
            status = "BLOCKED_INVALID_ANALYTICAL_INPUT"
        else:
            all_priced = all(c.get("pricing_status") == "PRICED" for c in valuation_candidates if c.get("analytical_status") != "ANALYTICAL_BLOCKED")
            any_priced = any(c.get("pricing_status") == "PRICED" for c in valuation_candidates if c.get("analytical_status") != "ANALYTICAL_BLOCKED")
            all_degraded = all(c.get("pricing_status") in ("PRICING_DEGRADED", "PRICING_BLOCKED_INVALID_INPUT") for c in valuation_candidates)
            
            if any_analytical_ready:
                if all_priced:
                    status = "READY_PRICED"
                elif any_priced:
                    status = "READY_MIXED"
                elif all_degraded:
                    status = "PRICING_DEGRADED_ANALYSIS_PRESERVED"
                else:
                    status = "READY_ANALYTICAL_PRICE_PENDING"
            else:
                status = "BLOCKED_INVALID_ANALYTICAL_INPUT"

    event_records = []
    seen_events = set()
    for candidate in valuation_candidates:
        evt_id = candidate.get("canonical_event_id")
        if evt_id and evt_id not in seen_events:
            seen_events.add(evt_id)
            has_tips = int(candidate.get("tipster_count") or 0) > 0
            terminal_status = "CONTINUE" if has_tips else "DEGRADED_CONTINUE"
            if candidate.get("final_status") == "BLOCKED":
                terminal_status = "BLOCKED"
            event_records.append({
                "canonical_event_id": evt_id,
                "terminal_status": terminal_status,
                "reason_codes": [] if has_tips else ["DEGRADED_NO_TIPSTER_PICKS"],
                "candidate_ids": [candidate.get("selection_id")] if candidate.get("selection_id") else []
            })

    return {
        "schema_version": 2,
        "artifact_type": "S4_VALUATION_CANDIDATE_SET_V2",
        "status": status,
        "betting_day": date,
        "run_id": run_id or os.environ.get("BET_PIPELINE_RUN_ID"),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_mode": _runtime_mode_value(runtime_mode),
        "source_s3_path": str(source_input_path.resolve(strict=True)) if source_input_path else None,
        "source_s3_sha256": file_sha256(source_input_path) if source_input_path else None,
        "odds_snapshot_paths": _odds_snapshot_paths(),
        "candidate_count": len(valuation_candidates),
        "contains_odds": any(bool(candidate.get("odds")) for candidate in valuation_candidates),
        "contains_ev": any(candidate.get("ev") is not None for candidate in valuation_candidates),
        "contains_safety": any(candidate.get("safety_score") is not None or candidate.get("safety_markets") for candidate in valuation_candidates),
        "contains_market_count": any(candidate.get("market_count") is not None or candidate.get("markets_evaluated") is not None for candidate in valuation_candidates),
        "market_semantics_ready_count": market_semantics_ready_count,
        "promotion_safe_model_probability_count": promotion_safe_model_probability_count,
        "reference_model_probability_count": reference_model_probability_count,
        "candidates_with_ev": candidates_with_ev,
        "positive_ev_count": positive_ev_count,
        "ev_missing_reason_counts": ev_missing_reason_counts,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "no_pick_edge_stake_coupon_emitted": True,
        "event_records": event_records,
        "candidates": valuation_candidates,
    }

# ---------------------------------------------------------------------------
# GAP 1 FIX: Uncertainty-Adjusted Kelly Criterion
# Research shows 10-20% fractional Kelly optimal when probability estimates
# are uncertain (synthetic/incomplete data). Kelly formula assumes known p.
# When using synthetic data, reduce Kelly fraction proportionally.
# ---------------------------------------------------------------------------

KELLY_FRACTIONS = {
    "poor": 0.10,       # Data quality < 0.50 (synthetic/estimated)
    "moderate": 0.15,   # Data quality 0.50-0.75 (partial data)
    "good": 0.25,       # Data quality > 0.75 (real match data)
    "default": 0.25,    # Default when quality unknown
}


def compute_adjusted_kelly(hit_rate: float, odds: float, data_quality_score: float,
                           h2h_blind: bool = False, sample_size: int = 10) -> dict:
    """Compute Kelly fraction adjusted for data uncertainty.
    
    Args:
        hit_rate: Estimated probability (0.0-1.0)
        odds: Decimal odds
        data_quality_score: Data quality metric (0.0-1.0)
        h2h_blind: True if no H2H data available
        sample_size: Number of data points in L10
    
    Returns dict with:
        kelly_fraction: Recommended fraction of bankroll
        base_kelly: Unadjusted Kelly value
        quality_tier: "poor" | "moderate" | "good"
        adjustment_reason: Explanation
    """
    if odds <= 1.0 or hit_rate <= 0:
        return {
            "kelly_fraction": 0.0,
            "base_kelly": 0.0,
            "quality_tier": "poor",
            "adjustment_reason": "Invalid odds or hit_rate",
        }
    
    # Base Kelly: f = (b*p - q) / b where b = odds-1, p = prob, q = 1-p
    b = odds - 1.0
    p = hit_rate
    q = 1.0 - p
    base_kelly = (b * p - q) / b if b > 0 else 0.0
    
    # Negative edge = no bet
    if base_kelly <= 0:
        return {
            "kelly_fraction": 0.0,
            "base_kelly": base_kelly,
            "quality_tier": "none",
            "adjustment_reason": f"Negative edge: base_kelly={base_kelly:.3f}",
        }
    
    # Determine quality tier
    # Additional penalties for data gaps
    effective_quality = data_quality_score
    
    # H2H blind reduces quality
    if h2h_blind:
        effective_quality = min(effective_quality, 0.60)
    
    # Small sample size reduces quality
    if sample_size < 8:
        effective_quality = min(effective_quality, 0.50)
    
    # Select Kelly fraction based on quality
    if effective_quality < 0.50:
        quality_tier = "poor"
        kelly_frac = KELLY_FRACTIONS["poor"]
        reason = f"Poor data quality ({effective_quality:.2f}) → {kelly_frac*100:.0f}% Kelly"
    elif effective_quality < 0.75:
        quality_tier = "moderate"
        kelly_frac = KELLY_FRACTIONS["moderate"]
        reason = f"Moderate data quality ({effective_quality:.2f}) → {kelly_frac*100:.0f}% Kelly"
    else:
        quality_tier = "good"
        kelly_frac = KELLY_FRACTIONS["good"]
        reason = f"Good data quality ({effective_quality:.2f}) → {kelly_frac*100:.0f}% Kelly"
    
    # Add penalty notations
    penalties = []
    if h2h_blind:
        penalties.append("H2H-blind")
    if sample_size < 8:
        penalties.append(f"sample={sample_size}")
    if penalties:
        reason += f" (penalties: {', '.join(penalties)})"
    
    adjusted_kelly = base_kelly * kelly_frac
    
    return {
        "kelly_fraction": round(adjusted_kelly, 4),
        "base_kelly": round(base_kelly, 4),
        "quality_tier": quality_tier,
        "adjustment_reason": reason,
        "effective_quality": round(effective_quality, 2),
        "kelly_frac_used": kelly_frac,
    }

# Progress tracking for background execution
try:
    from _background_runner import ProgressTracker
except ImportError:
    try:
        from scripts._background_runner import ProgressTracker
    except ImportError:
        ProgressTracker = None  # type: ignore


# ---------------------------------------------------------------------------
# ESPN American odds → decimal conversion
# ---------------------------------------------------------------------------
def _convert_espn_odds_to_decimal(odds_data: dict) -> dict:
    """Convert ESPN American odds to decimal format.

    American odds: +X → 1 + X/100; −X → 1 + 100/X
    """
    def _american_to_decimal(american) -> float | None:
        try:
            val = float(american)
        except (ValueError, TypeError):
            return None
        if val > 0:
            return round(1 + val / 100, 3)
        elif val < 0:
            return round(1 + 100 / abs(val), 3)
        return None

    result = {}

    # Moneyline
    ml = odds_data.get("moneyline", {})
    if ml:
        result["moneyline"] = {}
        for side in ("home", "away", "draw"):
            dec = _american_to_decimal(ml.get(side))
            if dec:
                result["moneyline"][side] = dec

    # Total
    total = odds_data.get("total", {})
    if total:
        result["total"] = {"line": total.get("line", "")}
        over_dec = _american_to_decimal(total.get("over_odds"))
        under_dec = _american_to_decimal(total.get("under_odds"))
        if over_dec:
            result["total"]["over"] = over_dec
        if under_dec:
            result["total"]["under"] = under_dec

    # Spread
    spread = odds_data.get("spread", {})
    if spread:
        result["spread"] = {
            "home_line": spread.get("home_line", ""),
            "away_line": spread.get("away_line", ""),
        }
        home_dec = _american_to_decimal(spread.get("home_odds"))
        away_dec = _american_to_decimal(spread.get("away_odds"))
        if home_dec:
            result["spread"]["home"] = home_dec
        if away_dec:
            result["spread"]["away"] = away_dec

    return result


# ---------------------------------------------------------------------------
# Market name → DB market key mapping (for statistical market EV matching)
# ---------------------------------------------------------------------------
def _relevant_market_keys(market_name: str) -> set[str]:
    """Map analysis best_market.name → set of DB market_key values to search for odds."""
    lower = market_name.lower()
    if "corner" in lower:
        return {"corners_totals", "total_corners", "alternative_corners",
                "team_corners_home", "team_corners_away", "corners_totals_ht"}
    if "shot" in lower:
        if "on target" in lower or "on_target" in lower:
            return {"match_shots_on_target", "team_shots_on_target_home",
                    "team_shots_on_target_away"}
        return {"team_shots_home", "team_shots_away", "match_shots",
                "match_shots_on_target", "team_shots_on_target_home",
                "team_shots_on_target_away"}
    if "card" in lower or "booking" in lower:
        return {"bookings_totals", "number_of_cards_in_match"}
    if "goal" in lower:
        return {"totals", "goals_over/under", "alternative_total_goals",
                "team_total_goals_home", "team_total_goals_away"}
    if "point" in lower:
        return {"totals", "points_o/u", "total_points"}
    if "rebound" in lower:
        return {"rebounds_o/u"}
    if "assist" in lower:
        return {"assists_o/u"}
    if "block" in lower:
        return {"blocks_o/u"}
    if "steal" in lower:
        return {"steals_o/u"}
    if "three" in lower or "3pm" in lower:
        return {"threes_made_o/u"}
    if "game" in lower or "set" in lower:
        return {"totals_(games)", "spread_(games)", "totals"}
    if "foul" in lower:
        return {"fouls_totals", "total_fouls"}
    # Generic fallback
    return {"totals"}


# ---------------------------------------------------------------------------
# EV injection from odds API
# ---------------------------------------------------------------------------
def _inject_ev_from_odds(candidates: list[dict], date: str):
    """Compute and inject EV into candidates using odds API snapshots.

    Sources: SQLite odds history and configured provider snapshots.
    + the-odds-api (odds_api_snapshot.json) + odds-api.io (odds_api_io_snapshot.json).
    EV = (probability × odds) - 1. If no odds snapshot exists, candidates
    keep ev=None and the gate handles it gracefully (stats-first mode).

    The odds_lookup stores:  key = "home|away" -> {
        "market_best": float,   # best ML/totals odds from any bookmaker
        "bet365": float|None,   # Bet365 odds
        "totals": [{line, over, under, bookmaker}],  # totals lines
    }
    """
    odds_lookup: dict[str, dict] = {}

    def _ensure_entry(key: str) -> dict:
        if key not in odds_lookup:
            odds_lookup[key] = {"market_best": 0, "bet365": None, "totals": []}
        return odds_lookup[key]

    # Market keys that represent totals/over-under data (loaded into entry["totals"])
    _TOTALS_MARKET_KEYS = frozenset({
        "totals", "goals_over/under", "alternative_total_goals", "alternative_totals",
        "total_corners", "corners_totals", "corners_totals_ht", "alternative_corners",
        "team_corners_home", "team_corners_away",
        "bookings_totals", "number_of_cards_in_match",
        "team_shots_home", "team_shots_away", "match_shots", "match_shots_on_target",
        "team_shots_on_target_home", "team_shots_on_target_away",
        "totals_(games)", "spread_(games)",
        "points_o/u", "rebounds_o/u", "assists_o/u", "blocks_o/u", "steals_o/u",
        "threes_made_o/u", "total_points",
    })

    # Source 0: SQLite DB with normalized multi-bookmaker observations.
    db_path = DATA_DIR / "betting.db"
    if db_path.exists():
        try:
            sys.path.insert(0, str(ROOT_DIR / "src"))
            from bet.db.connection import get_db

            with get_db() as conn:
                cur = conn.cursor()
                # Query odds by FIXTURE date (kickoff), not fetch date.
                # Odds for tomorrow's games are fetched today — fetched_at != target date.
                cur.execute('''
                    SELECT t1.name, t2.name, o.bookmaker, o.market, o.selection, o.odds, o.line
                    FROM odds_history o
                    JOIN fixtures f ON o.fixture_id = f.id
                    JOIN teams t1 ON f.home_team_id = t1.id
                    JOIN teams t2 ON f.away_team_id = t2.id
                    WHERE date(f.kickoff) = ?
                ''', (date,))
                db_rows = cur.fetchall()

            # Parse DB odds: group totals lines with their over/under prices
            # DB stores totals as interleaved rows: hdp (line), over (price), under (price)
            totals_buffer: dict[str, dict] = {}  # key -> {current_line, entries}
            for home, away, bookmaker, market, selection, odds_val, line_val in db_rows:
                h = _norm_team(home)
                a = _norm_team(away)
                key = f"{h}|{a}"
                entry = _ensure_entry(key)

                bk_lower = (bookmaker or "").lower()
                is_bet365 = "bet365" in bk_lower

                if market in ("h2h", "ml"):
                    # ML odds — track market_best (highest) + per-bookmaker
                    if odds_val and odds_val > entry["market_best"]:
                        entry["market_best"] = float(odds_val)
                    sel_lower = (selection or "").lower()
                    if sel_lower in ("draw", "x"):
                        pass  # Skip draw for per-bookmaker tracking
                    elif is_bet365:
                        prev_bet365 = entry.get("bet365") or 0
                        if odds_val and odds_val > prev_bet365:
                            entry["bet365"] = float(odds_val)

                elif market in _TOTALS_MARKET_KEYS or "totals" in (market or "") or "over" in (market or "") or "under" in (market or ""):
                    # ALL totals-style markets: goals, corners, cards, shots, points, etc.
                    sel_lower = (selection or "").lower()
                    # Format 1: standard Over/Under with line in `line` column
                    if line_val is not None and sel_lower in ("over", "under"):
                        line_f = float(line_val)
                        # Find existing entry for this line+bookmaker+market, or create
                        found = False
                        for tl in entry["totals"]:
                            if (abs(tl.get("line", 0) - line_f) < 0.01
                                    and tl.get("bookmaker") == bookmaker
                                    and tl.get("market_key", "totals") == market):
                                tl[sel_lower] = float(odds_val)
                                found = True
                                break
                        if not found:
                            new_tl = {"line": line_f, "bookmaker": bookmaker,
                                      "over": None, "under": None, "market_key": market}
                            new_tl[sel_lower] = float(odds_val)
                            entry["totals"].append(new_tl)

                    # Format 2: interleaved hdp/over/under rows without a line column.
                    else:
                        buf_key = f"{key}|{bookmaker}|{market}"
                        if buf_key not in totals_buffer:
                            totals_buffer[buf_key] = {"line": None, "over": None, "under": None, "market_key": market}
                        buf = totals_buffer[buf_key]

                        if sel_lower == "hdp":
                            # This is the line value (stored in odds column)
                            if buf["line"] is not None and buf["over"] is not None:
                                # Flush previous complete line
                                entry["totals"].append({
                                    "line": buf["line"], "over": buf["over"],
                                    "under": buf["under"], "bookmaker": bookmaker,
                                    "market_key": market,
                                })
                            buf["line"] = float(odds_val)
                            buf["over"] = None
                            buf["under"] = None
                        elif sel_lower == "over":
                            buf["over"] = float(odds_val)
                        elif sel_lower == "under":
                            buf["under"] = float(odds_val)

                        # Flush complete line
                        if buf["line"] is not None and buf["over"] is not None and buf["under"] is not None:
                            entry["totals"].append({
                                "line": buf["line"], "over": buf["over"],
                                "under": buf["under"], "bookmaker": bookmaker,
                                "market_key": market,
                            })
                            totals_buffer[buf_key] = {"line": None, "over": None, "under": None, "market_key": market}

            # Flush any remaining incomplete totals buffers (line+over without under)
            for buf_key, buf in totals_buffer.items():
                if buf["line"] is not None and buf["over"] is not None:
                    parts = buf_key.split("|")
                    bk = parts[2] if len(parts) > 2 else "unknown"
                    mkt_key = parts[3] if len(parts) > 3 else "totals"
                    match_key = f"{parts[0]}|{parts[1]}" if len(parts) > 1 else buf_key
                    if match_key in odds_lookup:
                        odds_lookup[match_key]["totals"].append({
                            "line": buf["line"], "over": buf["over"],
                            "under": buf.get("under"), "bookmaker": bk,
                            "market_key": mkt_key,
                        })

            if db_rows:
                print(f"  → DB: loaded {len(db_rows)} odds rows → {len(odds_lookup)} fixtures")
        except Exception as e:
            print(f"  ⚠️ DB odds load failed: {e}")

    # Source 1: the-odds-api snapshot
    odds_path = DATA_DIR / "odds_api_snapshot.json"
    if odds_path.exists():
        try:
            odds_data = json.loads(odds_path.read_text(encoding="utf-8"))
            for event in odds_data if isinstance(odds_data, list) else odds_data.get("events", []):
                home = _norm_team(event.get("home_team") or "")
                away = _norm_team(event.get("away_team") or "")
                if not home or not away:
                    continue
                key = f"{home}|{away}"
                entry = _ensure_entry(key)

                # Try pre-computed best_odds first
                best_odds = event.get("best_odds") or event.get("odds", {}).get("market_best")
                if best_odds:
                    val = float(best_odds)
                    if val > entry["market_best"]:
                        entry["market_best"] = val

                # Parse bookmakers array (raw the-odds-api format)
                for bm in event.get("bookmakers") or []:
                    bk_title = (bm.get("title") or bm.get("key") or "").lower()
                    is_bet365 = "bet365" in bk_title
                    for mkt in bm.get("markets") or []:
                        mkt_key = (mkt.get("key") or "").lower()
                        if mkt_key in ("ml", "h2h", "moneyline"):
                            for outcome in mkt.get("outcomes") or []:
                                price = outcome.get("price")
                                if not price or price <= 1.0:
                                    continue
                                if price > entry["market_best"]:
                                    entry["market_best"] = float(price)
                                side = (outcome.get("name") or "").lower()
                                if side in ("draw", "x"):
                                    continue
                                if is_bet365:
                                    prev = entry.get("bet365") or 0
                                    if price > prev:
                                        entry["bet365"] = float(price)
                        elif mkt_key in ("totals", "over_under"):
                            for outcome in mkt.get("outcomes") or []:
                                price = outcome.get("price")
                                point = outcome.get("point")
                                side = (outcome.get("name") or "").lower()
                                if price and point is not None and side in ("over", "under"):
                                    entry["totals"].append({
                                        "line": float(point),
                                        side: float(price),
                                        "bookmaker": bm.get("title") or bm.get("key"),
                                    })

                # Load pre-computed totals from API snapshot
                api_totals = event.get("totals")
                if api_totals and isinstance(api_totals, list):
                    for tl in api_totals:
                        if tl.get("line") is not None:
                            entry["totals"].append(tl)
        except (json.JSONDecodeError, OSError):
            pass

    # Source 2: odds-api.io snapshot (265 bookmakers, more coverage)
    io_path = DATA_DIR / "odds_api_io_snapshot.json"
    if io_path.exists():
        try:
            io_data = json.loads(io_path.read_text(encoding="utf-8"))
            for event in io_data.get("events", []):
                home = _norm_team(event.get("home") or "")
                away = _norm_team(event.get("away") or "")
                if not home or not away:
                    continue
                key = f"{home}|{away}"
                entry = _ensure_entry(key)
                for bookie_name, markets in (event.get("bookmakers") or {}).items():
                    if not isinstance(markets, list):
                        continue
                    for market in markets:
                        if market.get("name") == "ML":
                            for odds_entry in market.get("odds", []):
                                for side in ["home", "away"]:
                                    try:
                                        val = float(odds_entry.get(side, 0))
                                        if val > entry["market_best"]:
                                            entry["market_best"] = val
                                    except (ValueError, TypeError):
                                        pass
            # Inject from value bets (pre-calculated EV!)
            for vb in io_data.get("value_bets", []):
                ev_data = vb.get("event", {})
                home = _norm_team(ev_data.get("home") or "")
                away = _norm_team(ev_data.get("away") or "")
                if home and away:
                    pre_ev = vb.get("expectedValue")
                    if pre_ev is not None:
                        for c in candidates:
                            ch = _norm_team(c.get("home_team") or "")
                            ca = _norm_team(c.get("away_team") or "")
                            if ch == home and ca == away and c.get("ev") is None:
                                c["ev"] = round(float(pre_ev) / 100 - 1, 4)
                                c["ev_source"] = "odds-api-io-value-bet"
                                c.setdefault("odds_source", "api")
        except (json.JSONDecodeError, OSError):
            pass

    injected = 0
    odds_enriched = 0
    for c in candidates:
        best_market = c.get("best_market") or {}
        market_name = best_market.get("name")
        has_market = bool(market_name)
        
        # Precedence: best_market.probability > top-level.probability > hit_rate_l10
        prob_val = None
        prob_src = None
        
        # 1. best_market probability
        if isinstance(best_market, dict) and best_market.get("probability") is not None:
            prob_val = best_market.get("probability")
            prob_src = "best_market.probability"
        # 2. top-level candidate probability
        else:
            for k in ("probability", "model_probability", "prob"):
                if c.get(k) is not None:
                    prob_val = c.get(k)
                    prob_src = "candidate.probability"
                    break
        # 3. hit_rate_l10 fallback
        if prob_val is None:
            if c.get("hit_rate_l10") is not None:
                prob_val = c.get("hit_rate_l10")
                prob_src = "hit_rate_l10"
            elif isinstance(best_market, dict) and best_market.get("hit_rate_l10") is not None:
                prob_val = best_market.get("hit_rate_l10")
                prob_src = "hit_rate_l10"

        p_val = _coerce_probability(prob_val) if prob_val is not None else None
        explicit_method = str(c.get("probability_method") or "").strip()
        raw_reference_probability = p_val
        if explicit_method == "BOOKMAKER_IMPLIED_REFERENCE_ONLY":
            p_val = None
            prob_src = None
            if raw_reference_probability is not None:
                c["reference_model_probability"] = raw_reference_probability
        elif p_val is not None and _probability_confidence_blocks_promotion(c.get("probability_confidence")):
            c["reference_model_probability"] = raw_reference_probability
            p_val = None
            prob_src = None
        if p_val is None:
            prob_src = None
        has_prob = p_val is not None

        if explicit_method:
            probability_method = explicit_method
        elif prob_src == "best_market.probability":
            probability_method = "S3_PROBABILITY_ENGINE"
        elif prob_src == "candidate.probability":
            probability_method = "S3_EXPLICIT_PROBABILITY"
        elif prob_src == "hit_rate_l10":
            probability_method = "S3_HIT_RATE_PROXY"
        else:
            probability_method = ""

        if has_prob:
            c["model_probability"] = p_val
            c["probability_method"] = probability_method
            c["probability_sources"] = c.get("probability_sources") or ([prob_src] if prob_src else [])
            c["probability_as_of"] = c.get("probability_as_of") or datetime.now(timezone.utc).isoformat()
            c["probability_confidence"] = c.get("probability_confidence") or "UNSPECIFIED"
            c["probability_missing_reason"] = None
        else:
            c["model_probability"] = None
            c["probability_method"] = explicit_method or probability_method
            if not c.get("probability_missing_reason"):
                if explicit_method == "BOOKMAKER_IMPLIED_REFERENCE_ONLY":
                    c["probability_missing_reason"] = "BOOKMAKER_IMPLIED_REFERENCE_ONLY"
                elif raw_reference_probability is not None and _probability_confidence_blocks_promotion(c.get("probability_confidence")):
                    c["probability_missing_reason"] = "LOW_CONFIDENCE_MODEL_PROBABILITY"
                elif c.get("stats_gap_reason"):
                    c["probability_missing_reason"] = c.get("stats_gap_reason")
                else:
                    c["probability_missing_reason"] = "NO_MODEL_PROBABILITY_AVAILABLE"

        home = _norm_team(c.get("home_team") or "")
        away = _norm_team(c.get("away_team") or "")
        key = f"{home}|{away}"
        entry = odds_lookup.get(key) if odds_lookup else None
        
        # Fuzzy fallback: use names_match() for robust team matching
        if odds_lookup and not entry:
            best_score = 0
            for ok, ov in odds_lookup.items():
                parts = ok.split("|", 1)
                if len(parts) != 2:
                    continue
                oh, oa = parts
                score_h = names_match(home, oh, threshold=70)
                score_a = names_match(away, oa, threshold=70)
                if score_h >= 70 and score_a >= 70:
                    combined = score_h + score_a
                    if combined > best_score:
                        best_score = combined
                        entry = ov

        if not entry and (os.environ.get("BET_MOCK_ODDS") or os.environ.get("BET_PIPELINE_SKIP_FETCH")):
            import random
            mock_price = round(random.uniform(1.85, 2.20), 2)
            entry = {
                "market_best": mock_price,
                "bet365": mock_price,
                "totals": [
                    {
                        "line": float(best_market.get("line") or 0.0) if best_market else 0.0,
                        "bookmaker": "TEST_ONLY",
                        "over": mock_price,
                        "under": mock_price,
                        "market_key": "totals",
                    }
                ],
            }
            odds_lookup[key] = entry

        # Use the best normalized quote; provider-specific values are advisory only.
        use_odds = None
        if entry:
            bet365_odds = entry.get("bet365")
            market_best = entry.get("market_best", 0)
            use_odds = market_best if market_best > 1.0 else bet365_odds

            if use_odds:
                c.setdefault("odds", {})["market_best"] = use_odds
                if bet365_odds:
                    c["odds"]["bet365"] = bet365_odds
                    c["odds_source"] = "api"
                else:
                    c["odds_source"] = "api"
                odds_enriched += 1

                if os.environ.get("BET_MOCK_ODDS") or os.environ.get("BET_PIPELINE_SKIP_FETCH"):
                    c["odds_as_of"] = c.get("probability_as_of") or "2026-07-10T10:00:00+00:00"
                    c["odds_captured_at_utc"] = c["odds_as_of"]
                    c["odds_source"] = "TEST_ONLY_MOCK_ODDS"

            if entry.get("totals"):
                c.setdefault("odds", {})["totals"] = entry["totals"]

        # If EV already exists (e.g. from value_bets), populate components and skip
        if c.get("ev") is not None:
            c["ev_components"] = {
                "probability": p_val,
                "probability_source": prob_src,
                "odds": (c.get("odds") or {}).get("market_best"),
                "odds_source": c.get("ev_source"),
                "odds_matched_market": "value_bet",
                "market_name": market_name,
                "market_line": best_market.get("line") if isinstance(best_market, dict) else None,
                "market_direction": best_market.get("direction") if isinstance(best_market, dict) else None,
            }
            c["ev_missing_reason"] = None
            continue

        is_ml_market = any(kw in market_name.lower() for kw in ("winner", "ml", "match winner", "moneyline", "1x2")) if has_market else False
        is_totals_market = any(kw in market_name.lower() for kw in ("o/u", "over", "under", "total", "corners", "fouls", "cards", "shots", "games", "sets", "frames", "points", "goals")) if has_market else False

        matched_odds = None
        odds_src = None
        odds_matched_market = None

        if entry:
            if is_totals_market and entry.get("totals"):
                line = best_market.get("line")
                direction = (best_market.get("direction") or "").upper()
                if line is not None:
                    relevant_keys = _relevant_market_keys(market_name)
                    # First pass: try to match line from relevant market_key
                    for tl in entry["totals"]:
                        tl_key = tl.get("market_key", "totals")
                        if relevant_keys and tl_key not in relevant_keys:
                            continue
                        if abs(tl.get("line", 0) - float(line)) < 0.01:
                            if "OVER" in direction and tl.get("over"):
                                if matched_odds is None or tl["over"] > matched_odds:
                                    matched_odds = tl["over"]
                                    odds_src = "db+api-composite" if tl.get("bookmaker") else "api"
                                    odds_matched_market = tl_key
                            elif "UNDER" in direction and tl.get("under"):
                                if matched_odds is None or tl["under"] > matched_odds:
                                    matched_odds = tl["under"]
                                    odds_src = "db+api-composite" if tl.get("bookmaker") else "api"
                                    odds_matched_market = tl_key
                    # Fallback: if no relevant-key match, try any totals line
                    if matched_odds is None:
                        for tl in entry["totals"]:
                            if abs(tl.get("line", 0) - float(line)) < 0.01:
                                if "OVER" in direction and tl.get("over"):
                                    if matched_odds is None or tl["over"] > matched_odds:
                                        matched_odds = tl["over"]
                                        odds_src = "db+api-composite" if tl.get("bookmaker") else "api"
                                        odds_matched_market = "totals"
                                elif "UNDER" in direction and tl.get("under"):
                                    if matched_odds is None or tl["under"] > matched_odds:
                                        matched_odds = tl["under"]
                                        odds_src = "db+api-composite" if tl.get("bookmaker") else "api"
                                        odds_matched_market = "totals"
            elif is_ml_market:
                matched_odds = use_odds
                odds_src = c.get("odds_source") or "api"
                odds_matched_market = "ml"

        # Fallback: standard bookmaker pricing estimate for totals
        if not matched_odds and is_totals_market and has_prob:
            matched_odds = 1.87  # Standard balanced O/U pricing
            c["ev_source_note"] = "estimated_odds_1.87 (no API match for this market)"
            odds_src = "estimated"
            odds_matched_market = "estimated"

        odds_for_ev = matched_odds

        ev = None
        if has_prob and odds_for_ev is not None:
            ev = round(p_val * float(odds_for_ev) - 1, 4)
            injected += 1

        c["ev"] = ev
        c["ev_source"] = odds_src if ev is not None else None

        ev_missing_reason = None
        if ev is None:
            if not has_prob:
                ev_missing_reason = "MISSING_PROBABILITY"
            elif not has_market:
                ev_missing_reason = "MISSING_ANALYZED_MARKET"
            elif odds_for_ev is None:
                ev_missing_reason = "MISSING_MATCHED_ODDS"
            else:
                ev_missing_reason = "UNSUPPORTED_MARKET_SHAPE"

        c["ev_missing_reason"] = ev_missing_reason
        c["ev_components"] = {
            "probability": p_val,
            "probability_source": prob_src,
            "odds": odds_for_ev,
            "odds_source": odds_src,
            "odds_matched_market": odds_matched_market,
            "market_name": market_name if has_market else None,
            "market_line": best_market.get("line") if isinstance(best_market, dict) else None,
            "market_direction": best_market.get("direction") if isinstance(best_market, dict) else None,
        }

    print(f"  → Odds enriched: {odds_enriched}/{len(candidates)} candidates")
    if injected:
        print(f"  → EV injected: {injected}/{len(candidates)} candidates")


def run_odds_eval(
    date: str,
    state: dict,
    *,
    input_path: Path | None = None,
    output_path: Path | None = None,
    runtime_mode: str | None = None,
) -> tuple[bool, str]:
    """S4: Cross-validate odds, compute EV, detect drift."""
    tracker = ProgressTracker("s4") if ProgressTracker else None
    if tracker:
        tracker.start(3, f"Odds evaluation for {date}")

    candidates = []
    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
    s3_data = None
    resolved_input_path = Path(input_path).resolve() if input_path else None
    resolved_output_path = Path(output_path).resolve() if output_path else None
    run_id = os.environ.get("BET_PIPELINE_RUN_ID")

    if not _is_production_mode(runtime_mode):
        for protected_path in (resolved_input_path, resolved_output_path):
            if protected_path is not None and _is_protected_repo_path(protected_path):
                return False, f"Protected non-production valuation path rejected: {protected_path}"

    try:
        if resolved_input_path is not None:
            candidates, candidate_load = _load_candidates_from_json(resolved_input_path)
        else:
            from db_data_loader import load_s3_candidates_with_parity

            candidates, candidate_load = load_s3_candidates_with_parity(date)
    except Exception as e:
        return False, f"S4 candidate load error: {e}"

    if candidate_load.get("blocking_error"):
        error = candidate_load["blocking_error"]
        return False, (
            "S4 candidate parity failure: "
            f"{error.get('message', 'unknown error')} "
            f"(json={candidate_load['counts']['json']}, db={candidate_load['counts']['db']})"
        )

    if candidates:
        state["candidate_load"] = candidate_load
        print(
            "  → Candidate load: "
            f"source={candidate_load['source']} "
            f"status={candidate_load['parity']['status']} "
            f"json={candidate_load['counts']['json']} "
            f"db={candidate_load['counts']['db']} "
            f"canonical={candidate_load['counts']['canonical']}"
        )

    if not candidates:
        state["candidate_load"] = candidate_load
        valuation_output = _build_valuation_output(
            candidates,
            date=date,
            run_id=run_id,
            runtime_mode=runtime_mode,
            source_input_path=resolved_input_path or s3_path,
        )
        if resolved_output_path is not None:
            resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
            resolved_output_path.write_text(json.dumps(valuation_output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            state["valuation_output_path"] = str(resolved_output_path)
            state["valuation_output"] = valuation_output
        if tracker:
            tracker.done({"candidates": 0, "note": "no S3 data"})
        return True, "S4: No S3 data yet — skipping EV injection"

    if tracker:
        tracker.update(1, f"Loaded {len(candidates)} candidates")

    shortlist_payload = _resolve_shortlist_payload(resolved_input_path or s3_path)
    _enrich_candidate_market_semantics(
        candidates,
        shortlist_payload,
        str(resolved_input_path or s3_path),
    )

    try:
        _inject_ev_from_odds(candidates, date)
        _enrich_candidate_market_semantics(
            candidates,
            shortlist_payload,
            str(resolved_input_path or s3_path),
        )

        if tracker:
            tracker.update(2, f"EV injected for {len(candidates)} candidates")

        # Count how many have EV and log details
        with_ev = 0
        positive_ev = 0
        for c in candidates:
            ev = c.get("ev")
            if ev is not None:
                with_ev += 1
                if ev > 0:
                    positive_ev += 1
                home = c.get("home_team", "?")
                away = c.get("away_team", "?")
                odds = (c.get("odds") or {}).get("market_best", 0)
                source = c.get("ev_source", "calculated")
                marker = "💰" if ev > 0 else "📉"
                print(f"    {marker} {home} vs {away}: EV={ev:+.1%} @{odds:.2f} ({source})")
        total = len(candidates)

        valuation_output = _build_valuation_output(
            candidates,
            date=date,
            run_id=run_id,
            runtime_mode=runtime_mode,
            source_input_path=resolved_input_path or s3_path,
        )

        if resolved_output_path is not None:
            resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
            resolved_output_path.write_text(json.dumps(valuation_output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            state["valuation_output_path"] = str(resolved_output_path)
            state["valuation_output"] = valuation_output
        elif s3_path.exists() or resolved_input_path is None:
            if s3_path.exists():
                try:
                    s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    s3_data = None
            if s3_data is None:
                s3_data = {"analyses": []}
            s3_data["analyses"] = candidates
            try:
                s3_path.write_text(
                    json.dumps(s3_data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            except OSError:
                pass

        if _is_production_mode(runtime_mode):
            try:
                from bet.db.connection import get_db
                from bet.db.repositories import AnalysisResultRepo, FixtureRepo, SportRepo
                with get_db() as conn:
                    repo = AnalysisResultRepo(conn)
                    existing = repo.get_by_date(date)
                    db_lookup = {ar.fixture_id: ar for ar in existing}

                    # Build name→fixture_id resolver for candidates without fixture_id
                    fixture_repo = FixtureRepo(conn)
                    sport_repo = SportRepo(conn)

                    def _resolve_fid(c: dict) -> int | None:
                        fid = c.get("fixture_id")
                        if fid:
                            return fid
                        sport_name = c.get("sport", "")
                        s = sport_repo.get_by_name(sport_name) if sport_name else None
                        if not s:
                            return None
                        ko = c.get("kickoff", date)
                        f = fixture_repo.get_by_teams_and_date(
                            c.get("home_team", ""), c.get("away_team", ""),
                            ko[:10] if ko else date, s.id,
                        )
                        return f.id if f else None

                    updated = 0
                    for c in candidates:
                        ev = c.get("ev")
                        if ev is None:
                            continue
                        fid = _resolve_fid(c)
                        if fid and fid in db_lookup:
                            ar = db_lookup[fid]
                            summary = ar.stats_summary_json or {}
                            summary["ev"] = ev
                            summary["ev_source"] = c.get("ev_source", "calculated")
                            odds_data = c.get("odds", {})
                            if odds_data:
                                summary["odds_market_best"] = odds_data.get("market_best")
                                summary["odds_market_best"] = odds_data.get("market_best")
                            repo.update_stats_summary(fid, date, summary)
                            updated += 1
                        elif fid is None:
                            print(f"  ⚠ S4 DB: fixture_id not resolved for {c.get('home_team', '?')} vs {c.get('away_team', '?')}")
                    conn.commit()
                    if updated:
                        print(f"  → DB: updated {updated} analysis_results with EV data")
            except Exception as e:
                print(f"  ⚠ DB EV update failed (non-fatal): {e}")

        if tracker:
            tracker.done({"candidates": total, "with_ev": with_ev, "positive_ev": positive_ev})

        return True, f"S4 completed: {with_ev}/{total} with EV data ({positive_ev} positive EV)"
    except Exception as e:
        return False, f"S4 odds evaluation error: {e}"


# ---------------------------------------------------------------------------
# CLI entry point with --verbose + AGENT_SUMMARY (R17/R19)
# ---------------------------------------------------------------------------
def main():
    from agent_output import AgentOutput, add_agent_args

    parser = argparse.ArgumentParser(
        description="S4 Odds Evaluation — cross-validate odds, compute EV, detect drift"
    )
    parser.add_argument("--date", required=True, help="Betting date YYYY-MM-DD")
    parser.add_argument("--input", type=Path, default=None, help="Explicit S4 candidate universe input JSON")
    parser.add_argument("--output", type=Path, default=None, help="Explicit S4 valuation output JSON")
    parser.add_argument("--runtime-mode", default=os.environ.get("BET_PIPELINE_RUNTIME_MODE", "DRY_RUN"), help="Runtime mode")
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput("s4_odds_eval", verbose=args.verbose, stop_on_error=args.stop_on_error)

    state = {}
    ok, msg = run_odds_eval(
        args.date,
        state,
        input_path=args.input,
        output_path=args.output,
        runtime_mode=args.runtime_mode,
    )

    # Parse the message for metrics
    import re
    m = re.search(r"(\d+)/(\d+) with EV data \((\d+) positive", msg)
    with_ev = int(m.group(1)) if m else 0
    total = int(m.group(2)) if m else 0
    positive_ev = int(m.group(3)) if m else 0

    if not m:
        # Regex didn't match — error path or unexpected format
        verdict = "PARTIAL" if ok else "FAILED"
    elif positive_ev > 0:
        verdict = "OK"
    elif with_ev > 0:
        verdict = "PARTIAL"
    else:
        verdict = "FAILED"


    out.summary(
        verdict=verdict,
        metrics={
            "input_source": (state.get("candidate_load") or {}).get("source", "none"),
            "input_status": (state.get("candidate_load") or {}).get("parity", {}).get("status", "missing"),
            "input_json_candidates": (state.get("candidate_load") or {}).get("counts", {}).get("json", 0),
            "input_db_candidates": (state.get("candidate_load") or {}).get("counts", {}).get("db", 0),
            "input_canonical_candidates": (state.get("candidate_load") or {}).get("counts", {}).get("canonical", 0),
            "input_path": str(args.input) if args.input else (state.get("candidate_load") or {}).get("input_path"),
            "output_path": str(args.output) if args.output else state.get("valuation_output_path"),
            "total_candidates": total,
            "with_ev": with_ev,
            "positive_ev": positive_ev,
            "ev_coverage_pct": round(with_ev / max(total, 1) * 100, 1),
        },
        issues=[] if ok else [{"level": "error", "message": msg}],
    )

    try:
        from bet.pipeline import PipelineState
        ps = PipelineState.load(args.date)
        ps.advance("S4", summary={"total": total, "positive_ev": positive_ev})
    except Exception:
        pass

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
