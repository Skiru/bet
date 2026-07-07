"""Tipster Evidence Handoff construction and compliance validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from .agent_readiness import FORBIDDEN_ACTIONS, ALLOWED_PIPELINE_STAGES


def build_tipster_evidence_handoff(payload: dict[str, Any]) -> dict[str, Any]:
    """Compiles the S2 tipster evidence handoff payload for S3/S4 stages.

    This ensures that downstream agents only use context/sentiment and are structurally
    blocked from creating bets, coupons, or sizing decisions.
    """
    consensus = payload.get("consensus", [])
    events = []

    for c in consensus:
        picks_in_group = c.get("picks", [])
        if not picks_in_group:
            continue

        # Extract readiness records
        readiness_list = [p.get("agent_readiness", {}) for p in picks_in_group]
        
        needs_match_resolution = any(r.get("requires_match_resolution", False) for r in readiness_list)
        needs_manual_review = any(
            r.get("agent_use_decision") == "NEEDS_MANUAL_REVIEW" 
            or not p.get("reasoning") 
            or len(p.get("reasoning", "")) < 30 
            for p, r in zip(picks_in_group, readiness_list)
        )

        avg_quality = c.get("avg_extraction_quality", 0.0)
        if avg_quality >= 0.75:
            evidence_quality = "HIGH"
        elif avg_quality >= 0.5:
            evidence_quality = "MEDIUM"
        else:
            evidence_quality = "LOW"

        from .source_registry import CERTIFIED_SHADOW_SOURCE_IDS
        certified_srcs = sorted(list({p.get("source_id") for p in picks_in_group if p.get("source_id") and p.get("source_id") in CERTIFIED_SHADOW_SOURCE_IDS}))
        operator_srcs = sorted(list({p.get("source_id") for p in picks_in_group if p.get("source_id") and p.get("source_id") not in CERTIFIED_SHADOW_SOURCE_IDS}))
        
        if certified_srcs and operator_srcs:
            source_risk_mix = "mixed"
        elif certified_srcs:
            source_risk_mix = "certified_only"
        else:
            source_risk_mix = "operator_risk_only"

        if source_risk_mix == "mixed" and evidence_quality == "HIGH":
            # if event group is mixed, evidence_quality cannot be HIGH solely due operator-risk sources
            certified_picks = [p for p in picks_in_group if p.get("source_id") in CERTIFIED_SHADOW_SOURCE_IDS]
            avg_cert_quality = sum(p.get("extraction_quality", 0.0) for p in certified_picks) / len(certified_picks) if certified_picks else 0.0
            if avg_cert_quality < 0.75:
                evidence_quality = "MEDIUM"

        # Structural enforcement: ensure no forbidden fields exist in the picks
        for p in picks_in_group:
            for forbidden in FORBIDDEN_ACTIONS:
                if forbidden in p:
                    del p[forbidden]
                # Check lowered casing/underlines as well
                for k in list(p.keys()):
                    if forbidden.lower().replace(" ", "_") == k.lower():
                        del p[k]

        events.append({
            "normalized_event_key": readiness_list[0].get("normalized_event_key", ""),
            "event": c.get("event"),
            "sport": c.get("sport"),
            "markets": sorted(list({p.get("market") for p in picks_in_group if p.get("market")})),
            "tipster_sentiment": c.get("consensus_direction"),
            "qualitative_reasoning_summaries": sorted(list({p.get("reasoning") for p in picks_in_group if p.get("reasoning")})),
            "source_count": c.get("total_tipsters"),
            "evidence_quality": evidence_quality,
            "certified_sources": certified_srcs,
            "operator_risk_sources": operator_srcs,
            "source_risk_mix": source_risk_mix,
            "needs_match_resolution": needs_match_resolution,
            "needs_manual_review": needs_manual_review,
            "agent_use_decisions": sorted(list({r.get("agent_use_decision") for r in readiness_list if r.get("agent_use_decision")})),
            "source_ids": sorted(list({p.get("source_id") for p in picks_in_group if p.get("source_id")})),
            "forbidden_actions": list(FORBIDDEN_ACTIONS),
        })

    # Deduce fail_closed
    total_picks = payload.get("total_picks", 0)
    has_usable = any(
        c.get("agent_readiness_summary", {}).get("usable_context_count", 0) > 0
        for c in consensus
    )
    fail_closed = payload.get("fail_closed", False) or (total_picks == 0) or (not has_usable) or (not events)

    return {
        "schema_version": "tipster_evidence_handoff_v1",
        "contract": "evidence_only_not_betting_decision",
        "source_stage": "S2 tipster evidence",
        "allowed_consumers": list(ALLOWED_PIPELINE_STAGES),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "sources": payload.get("sources", []),
        "events": events,
        "fail_closed": fail_closed,
    }


def write_handoff_artifact(payload: dict[str, Any], path: Path) -> None:
    """Safely serializes the handoff dictionary to the specified path."""
    handoff = build_tipster_evidence_handoff(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(handoff, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
