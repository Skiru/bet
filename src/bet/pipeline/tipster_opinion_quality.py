"""Tipster phase contract validation and opinion quality tracking.

Ensures that tipster alignment claims on quote cards/coupon legs are fully backed by
actual matched opinions, and manages Tipster Context States under strict quality rules.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


class TipsterContextState:
    MATCHED_OPINIONS = "MATCHED_OPINIONS"
    ATTEMPTED_NO_MATCHES = "ATTEMPTED_NO_MATCHES"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_BLOCKED = "SOURCE_BLOCKED"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


def determine_tipster_context_status(
    *,
    attempted: bool,
    usable_opinions_count: int,
    sources_available: bool = True,
    blocked: bool = False,
    configured: bool = True,
) -> str:
    """Determines the active TipsterContextState."""
    if not configured:
        return TipsterContextState.NOT_CONFIGURED
    if not attempted:
        return TipsterContextState.NOT_ATTEMPTED
    if blocked:
        return TipsterContextState.SOURCE_BLOCKED
    if not sources_available:
        return TipsterContextState.SOURCE_UNAVAILABLE
    if usable_opinions_count > 0:
        return TipsterContextState.MATCHED_OPINIONS
    return TipsterContextState.ATTEMPTED_NO_MATCHES


def validate_tipster_opinion_alignment(
    *,
    status: str,
    quote_cards: Sequence[Mapping[str, Any]],
    opinions: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Validates that no quote card or coupon leg incorrectly claims tipster support."""
    errors: list[str] = []
    
    # Extract matched opinion refs from tipster opinion payload
    opinion_ids = {str(op.get("opinion_id") or op.get("id") or "").strip() for op in opinions if op}
    opinion_ids.discard("")

    for card in quote_cards:
        card_id = card.get("quote_card_id") or card.get("candidate_id") or "UNKNOWN_CARD"
        claims_tipster = card.get("tipster_consensus_ref") or card.get("tipster_alignment_claimed")
        
        if claims_tipster:
            ref_str = str(claims_tipster).strip()
            # If status says no matches/not configured/etc., or ref is not in actual opinions list
            if status in {TipsterContextState.ATTEMPTED_NO_MATCHES, TipsterContextState.NOT_CONFIGURED, TipsterContextState.NOT_ATTEMPTED}:
                errors.append(f"quote card {card_id} claims tipster support ({ref_str}) but tipster status is {status}")
            elif ref_str not in opinion_ids:
                errors.append(f"quote card {card_id} claims tipster ref {ref_str} which does not exist in matched opinions")

    return errors


def generate_tipster_context_report(
    *,
    run_id: str,
    attempted: bool,
    usable_opinions_count: int,
    quote_cards: Sequence[Mapping[str, Any]],
    opinions: Sequence[Mapping[str, Any]],
    sources_available: bool = True,
    blocked: bool = False,
    configured: bool = True,
    mandatory: bool = True,
) -> dict[str, Any]:
    """Generates the tipster context verification audit report."""
    status = determine_tipster_context_status(
        attempted=attempted,
        usable_opinions_count=usable_opinions_count,
        sources_available=sources_available,
        blocked=blocked,
        configured=configured,
    )
    
    errors = validate_tipster_opinion_alignment(status=status, quote_cards=quote_cards, opinions=opinions)
    
    if mandatory and status == TipsterContextState.NOT_ATTEMPTED:
        errors.append("Tipster phase is MANDATORY but was NOT_ATTEMPTED, blocking production")

    ok = len(errors) == 0
    return {
        "run_id": run_id,
        "ok": ok,
        "status": "PASS" if ok else "BLOCK",
        "tipster_context_status": status,
        "usable_opinions_count": usable_opinions_count,
        "errors": errors,
        "warnings": [
            "Tipster phase was attempted but zero usable opinions were matched."
        ] if status == TipsterContextState.ATTEMPTED_NO_MATCHES else [],
    }


def write_tipster_status_artifacts(report: dict[str, Any], output_dir: Path) -> None:
    """Writes 16B_tipster_context_status.json and .md."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # JSON
    json_path = output_dir / "16B_tipster_context_status.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    
    # MD
    md_path = output_dir / "16B_tipster_context_status.md"
    md_lines = [
        f"# Tipster Context Status Audit — {report['run_id']}",
        "",
        f"- **STATUS**: {report['status']}",
        f"- **TIPSTER_CONTEXT_STATUS**: {report['tipster_context_status']}",
        f"- **USABLE_OPINIONS_COUNT**: {report['usable_opinions_count']}",
        "",
        "## Errors / Blocker Warnings",
    ]
    if report["errors"]:
        for err in report["errors"]:
            md_lines.append(f"- :red_circle: {err}")
    else:
        md_lines.append("- :white_check_mark: None")
        
    md_lines.extend([
        "",
        "## Warnings",
    ])
    if report["warnings"]:
        for warn in report["warnings"]:
            md_lines.append(f"- :warning: {warn}")
    else:
        md_lines.append("- None")
        
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
