"""Bridge legacy S2 tipster picks into the v2 evidence contract."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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
    market_text = collapse_ws(market or "")
    combined = market_text if market_text else collapse_ws(str(market_type or ""))
    family = market_family(combined)
    mapped_direction = _DIRECTION_MAP.get(str(direction or "").strip().upper())
    if mapped_direction is None:
        mapped_direction = parse_direction(combined)
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
        published_at=None,
        source_url=collapse_ws(str(_get_field(payload, "source_url") or _get_field(payload, "url") or "")) or None,
        extracted_at_utc=extracted_at,
        extraction_quality=extraction_quality,
        warnings=warnings,
        valuable_signals=valuable_signals,
        source_record_type="legacy_source_claim_bridge",
        pipeline_use=["s2_tipster_evidence", "s3_context_cross_check", "legacy_bridge_reference_only"],
    )
