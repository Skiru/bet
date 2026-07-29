"""Adapters from v2 tipster contract to the existing Skiru/bet S2 shape."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .contracts import ExtractionResult, TipsterPick
from .normalization import names_score, normalize_key
from .agent_readiness import analyze_pick_readiness, ALLOWED_PIPELINE_STAGES, FORBIDDEN_ACTIONS


def to_legacy_pick(p: TipsterPick) -> dict:
    from .risk_policy import get_risk_policy
    from .source_registry import CERTIFIED_SHADOW_SOURCE_IDS
    is_certified = p.source_id in CERTIFIED_SHADOW_SOURCE_IDS
    policy = get_risk_policy(p.source_id, is_certified=is_certified)

    warnings_list = list(p.warnings or [])
    if not is_certified:
        for rw in policy.risk_warnings:
            if rw not in warnings_list:
                warnings_list.append(rw)

    return {
        "source_site": p.source_name,
        "source_id": p.source_id,
        "tipster_name": p.tipster_name or p.source_name,
        "sport": p.sport,
        "event": p.event,
        "home_team": p.home_team,
        "away_team": p.away_team,
        "competition": p.competition or "",
        "market": p.market,
        "market_type": "statistical" if p.market_family not in {"winner", "btts", "correct_score", "unknown"} else "outcome",
        "market_family": p.market_family,
        "direction": p.direction,
        "line": p.line,
        "odds": p.odds_decimal,
        "reasoning": p.reasoning,
        "accuracy_pct": None,
        "confidence": p.confidence_label,
        "stats_cited": p.stats_cited,
        "fetch_time": p.extracted_at_utc,
        "source_url": p.source_url,
        "extraction_quality": p.extraction_quality,
        "warnings": warnings_list,
        "valuable_signals": p.valuable_signals,
        "source_record_type": p.source_record_type,
        "pipeline_use": p.pipeline_use,
        "decision_boundary": "evidence_only_not_a_bet",
        "compliance_tier": policy.compliance_tier.value,
        "evidence_use": "certified_context" if is_certified else "manual_review_only_or_low_trust_context",
        "promotion_allowed": policy.promotion_allowed,
        "agent_readiness": analyze_pick_readiness(p),
    }


def consensus_from_picks(picks: Iterable[TipsterPick]) -> list[dict]:
    grouped: dict[str, list[TipsterPick]] = defaultdict(list)
    canonical_keys: list[tuple[str, str, str]] = []
    for p in picks:
        home = normalize_key(p.home_team)
        away = normalize_key(p.away_team)
        key = (p.sport, home, away)
        matched: tuple[str, str, str] | None = None
        for existing in canonical_keys:
            if existing[0] != p.sport:
                continue
            direct = min(names_score(home, existing[1]), names_score(away, existing[2]))
            swapped = min(names_score(home, existing[2]), names_score(away, existing[1]))
            if max(direct, swapped) >= 82:
                matched = existing
                break
        if matched is None:
            matched = key
            canonical_keys.append(key)
        grouped["|".join(matched)].append(p)
    out: list[dict] = []
    for _, event_picks in grouped.items():
        first = event_picks[0]
        dirs: dict[str, int] = defaultdict(int)
        markets: dict[str, int] = defaultdict(int)
        for p in event_picks:
            dirs[p.direction] += 1
            markets[p.market] += 1
        best_dir = max(dirs, key=dirs.get)
        best_market = max(markets, key=markets.get)
        total = len(event_picks)
        evidence_fields = sorted({key for p in event_picks for key in p.valuable_signals.keys()})

        # Calculate agent readiness summary for consensus
        readiness_list = [analyze_pick_readiness(p) for p in event_picks]
        needs_match_resolution_count = sum(1 for r in readiness_list if r["agent_use_decision"] == "NEEDS_MATCH_ID_RESOLUTION")
        needs_manual_review_count = sum(1 for r in readiness_list if r["agent_use_decision"] == "NEEDS_MANUAL_REVIEW")
        reject_low_quality_count = sum(1 for r in readiness_list if r["agent_use_decision"] == "REJECT_LOW_QUALITY")
        reject_garbage_count = sum(1 for r in readiness_list if r["agent_use_decision"] == "REJECT_GARBAGE")
        usable_context_count = sum(
            1 for r in readiness_list
            if r["agent_use_decision"] in {
                "USE_AS_CONTEXT",
                "USE_AS_MARKET_SANITY_CHECK",
                "USE_AS_QUALITATIVE_REASONING",
                "USE_AS_TIPSTER_SENTIMENT",
            }
        )
        agent_readiness_summary = {
            "all_evidence_only": True,
            "allowed_pipeline_stages": list(ALLOWED_PIPELINE_STAGES),
            "forbidden_actions": list(FORBIDDEN_ACTIONS),
            "needs_match_resolution_count": needs_match_resolution_count,
            "needs_manual_review_count": needs_manual_review_count,
            "reject_low_quality_count": reject_low_quality_count,
            "reject_garbage_count": reject_garbage_count,
            "usable_context_count": usable_context_count,
            "decisions": [r["agent_use_decision"] for r in readiness_list],
        }

        out.append({
            "event": first.event,
            "sport": first.sport,
            "home_team": first.home_team,
            "away_team": first.away_team,
            "total_tipsters": total,
            "tipster_sources": sorted({p.source_name for p in event_picks}),
            "consensus_market": best_market,
            "consensus_direction": best_dir,
            "agreement_pct": round(dirs[best_dir] / total * 100, 1),
            "has_reasoning": any(p.reasoning for p in event_picks),
            "evidence_fields": evidence_fields,
            "avg_extraction_quality": round(sum(p.extraction_quality for p in event_picks) / total, 2),
            "pipeline_usage": ["s3_factor_discovery", "s4_market_sanity_check", "manual_superbet_quote_context"],
            "agent_readiness_summary": agent_readiness_summary,
            "picks": [to_legacy_pick(p) for p in event_picks],
        })
    return sorted(out, key=lambda x: (x["total_tipsters"], x["agreement_pct"], x["avg_extraction_quality"]), reverse=True)


def write_artifact(results: list[ExtractionResult], path: Path) -> None:
    picks = [p for r in results for p in r.picks]
    blocked_sources = [
        {
            "source_id": r.source_id,
            "reason": r.block_reason,
            "url": r.url,
            "fallback": r.fallback or "fixture_snapshot_only",
            "live_fetch_allowed": False,
        }
        for r in results
        if r.block_reason
    ]
    skipped_sources = []
    for r in results:
        if not r.skip_reason:
            continue
        entry = {"source_id": r.source_id, "reason": r.skip_reason}
        if r.required_flags_missing:
            entry["required_flags_missing"] = r.required_flags_missing
        if r.invalid_attestation:
            entry["invalid_attestation"] = r.invalid_attestation
        skipped_sources.append(entry)
    sources_with_picks = len({r.source_id for r in results if r.pick_count > 0})
    active_results = [r for r in results if not r.block_reason and not r.skip_reason and r.live_fetch_allowed]
    payload = {
        "schema_version": "tipster_consensus_v2.3",
        "contract": "evidence_only_not_betting_decision",
        "sources": [r.to_dict() for r in results],
        "total_picks": len(picks),
        "sources_with_picks": sources_with_picks,
        "all_picks": [to_legacy_pick(p) for p in picks],
        "consensus": consensus_from_picks(picks),
        "blocked_sources": blocked_sources,
        "skipped_sources": skipped_sources,
        "pipeline_consumers": ["S3 contextual cross-check", "S4 market sanity", "manual Superbet quote review"],
        "fail_closed": len(picks) == 0 or (bool(results) and not active_results),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
