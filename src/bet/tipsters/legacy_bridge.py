"""Bridge legacy S2 tipster picks into the v2 evidence contract."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .claim import classify_claim
from .contracts import Direction, MarketFamily, TipsterPick
from .market_parser import direction as parse_direction
from .market_parser import extract_odds, market_family, parse_line
from .normalization import ascii_fold, collapse_ws

FORBIDDEN_KEYS = (
    "stake",
    "coupon",
    "final bet",
    "ev",
    "expected value",
    "superbet combined odds",
)

SOURCE_ALIASES = {
    "zawod typer": "zawodtyper",
    "zawodtyper": "zawodtyper",
    "typersi": "typersi",
    "pickswise": "pickswise",
    "betideas": "betideas",
    "sportsgambler": "sportsgambler",
    "feedinco": "feedinco",
    "bettingclosed": "bettingclosed",
}

_DIRECTION_MAP: dict[str, Direction] = {
    "OVER": "OVER",
    "UNDER": "UNDER",
    "WIN": "WIN",
    "DRAW": "DRAW",
    "BTTS": "BTTS_YES",
    "BTTS_YES": "BTTS_YES",
    "BTTS_NO": "BTTS_NO",
    "HOME": "HOME",
    "AWAY": "AWAY",
    "DC": "DC",
    "DNB": "DNB",
    "OTHER": "OTHER",
}


def _get_field(payload: dict[str, Any], attr: str, default: Any = "") -> Any:
    return payload.get(attr, default)


def _as_dict(legacy_pick: dict | object) -> dict[str, Any]:
    if isinstance(legacy_pick, dict):
        return dict(legacy_pick)
    return dict(vars(legacy_pick))


def normalize_legacy_source_id(name: str | None) -> str:
    folded = collapse_ws(ascii_fold(name or "").lower())
    folded = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in folded)
    folded = collapse_ws(folded)
    return SOURCE_ALIASES.get(folded, folded.replace(" ", ""))


def map_legacy_market_to_v2(market: str | None, market_type: str | None, direction: str | None) -> tuple[MarketFamily, Direction, float | None]:
    """Family, direction and line for one legacy pick.

    Direction is read from the claim text first and only falls back to the
    caller's value when the claim itself says nothing. The old order was
    inverted, and because ZawodTyper's caller derived its direction from
    ``pick_type + " " + content``, a claim of "Pow.2,5 gola" (over) inside a
    paragraph containing the word "mniej" (fewer) was stored as UNDER -- the
    signal flipped by prose it was not about. Live run 2026-08-25 reproduced it.
    """
    market_text = collapse_ws(market or "")
    combined = market_text if market_text else collapse_ws(str(market_type or ""))
    family = market_family(combined)

    mapped_direction: Direction = parse_direction(combined)
    if mapped_direction == "OTHER":
        mapped_direction = _DIRECTION_MAP.get(str(direction or "").strip().upper()) or "OTHER"
    return family, mapped_direction, parse_line(combined)


def enforce_evidence_only_boundary(pick: dict | object) -> dict[str, Any]:
    payload = _as_dict(pick)
    warnings = list(payload.get("warnings") or [])
    forbidden_seen: list[str] = []
    for key in list(payload.keys()):
        key_norm = collapse_ws(str(key).replace("_", " ").lower())
        if key_norm in FORBIDDEN_KEYS:
            forbidden_seen.append(key)
            payload.pop(key, None)
    if forbidden_seen:
        warnings.append("forbidden_fields_dropped:" + ",".join(sorted(forbidden_seen)))
    payload["warnings"] = warnings
    return payload


def convert_legacy_pick_to_v2(legacy_pick: dict | object) -> TipsterPick:
    payload = enforce_evidence_only_boundary(legacy_pick)
    source_name = collapse_ws(str(_get_field(payload, "source_site") or _get_field(payload, "source_name") or _get_field(payload, "source_id") or "legacy"))
    source_id = normalize_legacy_source_id(str(_get_field(payload, "source_id") or source_name))
    market = collapse_ws(str(_get_field(payload, "market") or "N/A")) or "N/A"
    family, mapped_direction, line = map_legacy_market_to_v2(
        market,
        str(_get_field(payload, "market_type") or ""),
        str(_get_field(payload, "direction") or ""),
    )

    warnings = list(payload.get("warnings") or [])
    warnings.append("legacy_bridge_evidence_only")

    reasoning = collapse_ws(str(_get_field(payload, "reasoning") or ""))
    stats = [str(item) for item in (_get_field(payload, "stats_cited") or []) if str(item).strip()]
    odds = _get_field(payload, "odds")
    try:
        odds_decimal = float(odds) if odds is not None else None
    except (TypeError, ValueError):
        odds_decimal = extract_odds(str(odds)) if odds else None
    if odds_decimal is not None:
        warnings.append("odds_reference_only")

    accuracy = _get_field(payload, "accuracy_pct")
    valuable_signals: dict[str, list[str]] = {
        "decision_boundary": ["evidence_only_not_a_bet"],
    }
    if accuracy not in (None, ""):
        warnings.append("accuracy_pct_reference_only")
        valuable_signals["source_quality"] = [f"accuracy_pct={accuracy}"]
    if stats:
        valuable_signals["stats_cited"] = stats[:12]

    extraction_quality = 0.38
    if market != "N/A":
        extraction_quality += 0.14
    if reasoning:
        extraction_quality += 0.16
    else:
        warnings.append("weak_or_empty_reasoning")
    if line is not None:
        extraction_quality += 0.08
    if stats:
        extraction_quality += 0.06
    if not reasoning:
        extraction_quality = min(extraction_quality, 0.52)
    extraction_quality = round(min(0.88, extraction_quality), 2)

    extracted_at = str(_get_field(payload, "fetch_time") or _get_field(payload, "extracted_at_utc") or "").strip()
    if not extracted_at:
        extracted_at = datetime.now(timezone.utc).isoformat()

    match_date = str(_get_field(payload, "match_date") or "").strip() or None
    if match_date is None:
        warnings.append("match_date_absent_cannot_attribute_to_betting_day")

    # A combo is either declared by the source (ZawodTyper's is_betbuilder) or
    # visible in the claim text. Both are recorded here rather than left for the
    # consensus layer, so a pick that reaches the column has already been judged
    # once on whether its legs are separable.
    is_combo = bool(_get_field(payload, "is_combo_source_flag") or False)
    claim = classify_claim(market, str(_get_field(payload, "home_team") or ""), str(_get_field(payload, "away_team") or ""))
    if claim.is_combo:
        is_combo = True
    if is_combo:
        warnings.append("combo_bet_legs_not_separable")

    is_settled = bool(_get_field(payload, "is_settled") or False)
    if is_settled:
        warnings.append("already_settled_at_source_historical_claim")

    accuracy_int: int | None
    try:
        accuracy_int = int(accuracy) if accuracy not in (None, "") else None
    except (TypeError, ValueError):
        accuracy_int = None

    bet_count = _get_field(payload, "tipster_bet_count")
    try:
        bet_count_int = int(bet_count) if bet_count not in (None, "") else None
    except (TypeError, ValueError):
        bet_count_int = None

    return TipsterPick(
        source_id=source_id,
        source_name=source_name or source_id,
        sport=collapse_ws(str(_get_field(payload, "sport") or "football")) or "football",
        event=collapse_ws(str(_get_field(payload, "event") or "")),
        home_team=collapse_ws(str(_get_field(payload, "home_team") or "")),
        away_team=collapse_ws(str(_get_field(payload, "away_team") or "")),
        market=market,
        market_family=family,
        direction=mapped_direction,
        line=line,
        odds_decimal=odds_decimal,
        confidence_label="source_claim",
        reasoning=reasoning,
        stats_cited=stats[:12],
        tipster_name=collapse_ws(str(_get_field(payload, "tipster_name") or "")) or None,
        competition=collapse_ws(str(_get_field(payload, "competition") or "")) or None,
        published_at=match_date,
        source_url=collapse_ws(str(_get_field(payload, "source_url") or _get_field(payload, "url") or "")) or None,
        match_date=match_date,
        kickoff_time=collapse_ws(str(_get_field(payload, "kickoff_time") or "")) or None,
        is_combo=is_combo,
        is_settled=is_settled,
        tipster_accuracy_pct=accuracy_int,
        tipster_bet_count=bet_count_int,
        source_ref=collapse_ws(str(_get_field(payload, "source_comment_id") or "")) or None,
        extracted_at_utc=extracted_at,
        extraction_quality=extraction_quality,
        warnings=warnings,
        valuable_signals=valuable_signals,
        source_record_type="legacy_source_claim_bridge",
        pipeline_use=["s2_tipster_evidence", "s3_context_cross_check", "legacy_bridge_reference_only"],
    )
