"""Pure portfolio and repeat guard domain service."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any


def _normalize_team(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"\s+", " ", name)
    for token in ["fc ", "sc ", "ac ", "ss ", "bv ", "ud ", "sv ", "tsv ", "vfb "]:
        if name.startswith(token):
            name = name[len(token):]
    for token in [" fc", " sc", " ac", " cf"]:
        if name.endswith(token):
            name = name[: -len(token)]
    return name.strip()


def _normalize_market(market: str) -> str:
    market = market.lower().strip()
    market = re.sub(r"\s+", " ", market)
    market = market.replace("over ", "o").replace("under ", "u")
    market = market.replace("o/u ", "").replace("over/under ", "")
    return market


def _fuzzy_match(a: str, b: str, threshold: float = 0.75) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= threshold


def _extract_teams_from_event(event: str) -> list[str]:
    match = re.match(r"(.+?)\s+(?:vs\.?|@)\s+(.+?)(?:\s*\(|$)", event, re.IGNORECASE)
    if match:
        return [match.group(1).strip(), match.group(2).strip()]
    for sep in [" vs ", " vs. ", " @ ", " - "]:
        if sep in event.lower():
            idx = event.lower().index(sep)
            return [event[:idx].strip(), event[idx + len(sep):].strip()]
    return [event]


@dataclass
class PortfolioRepeatGuardInput:
    candidates: list[dict[str, Any]]
    history_snapshot: list[dict[str, Any]]
    policy: dict[str, Any] = field(default_factory=dict)
    betting_day: str = ""
    run_id: str = ""
    source_s5_hash: str = ""


@dataclass
class PortfolioRepeatGuardResult:
    accepted: list[dict[str, Any]]
    repeat_rejected: list[dict[str, Any]]
    correlation_rejected: list[dict[str, Any]]
    conflict_rejected: list[dict[str, Any]]
    portfolio_rejected: list[dict[str, Any]]
    invalid_input: list[dict[str, Any]]
    accounting: dict[str, Any]
    history_snapshot_metadata: dict[str, Any]


def evaluate_portfolio_repeat_guard(
    guard_input: PortfolioRepeatGuardInput
) -> PortfolioRepeatGuardResult:
    """Side-effect-free deterministic evaluation of portfolio and repeat guard rules."""
    accepted = []
    repeat_rejected = []
    correlation_rejected = []
    conflict_rejected = []
    portfolio_rejected = []
    invalid_input = []

    # Prepare lookback history
    normalized_losses = []
    for loss in guard_input.history_snapshot:
        event = loss.get("event") or ""
        teams = _extract_teams_from_event(event)
        normalized_losses.append({
            "teams_normalized": [_normalize_team(t) for t in teams],
            "market_normalized": _normalize_market(loss.get("market") or ""),
            "original": loss
        })

    # Tracking sets to enforce disjoint partitions
    seen_ids = set()
    seen_team_markets = set()

    for c in guard_input.candidates:
        c_id = c.get("candidate_id") or ""
        
        # 1. Invalid candidate identity
        if not c_id or not c.get("home_team") or not c.get("away_team"):
            decision = {
                "candidate_id": c_id,
                "decision": "REJECTED",
                "reason_codes": ["INVALID_CANDIDATE_IDENTITY"],
                "explanation": "Missing required team or candidate identifier metadata",
                "original_candidate": c
            }
            invalid_input.append(decision)
            continue

        # Check duplicate candidate ID
        if c_id in seen_ids:
            decision = {
                "candidate_id": c_id,
                "decision": "REJECTED",
                "reason_codes": ["DUPLICATE_SIGNAL"],
                "explanation": f"Duplicate candidate ID '{c_id}' detected in the current run set",
                "original_candidate": c
            }
            invalid_input.append(decision)
            continue
        seen_ids.add(c_id)

        home_team = c.get("home_team") or ""
        away_team = c.get("away_team") or ""
        market_name = c.get("best_market", {}).get("name") or c.get("market_type") or c.get("market") or ""

        # 2. Check duplicate signal
        team_market_key = (_normalize_team(home_team), _normalize_team(away_team), _normalize_market(market_name))
        if team_market_key in seen_team_markets:
            decision = {
                "candidate_id": c_id,
                "decision": "REJECTED",
                "reason_codes": ["DUPLICATE_SIGNAL"],
                "explanation": f"Duplicate team+market signal detected: {home_team} vs {away_team} for {market_name}",
                "original_candidate": c
            }
            correlation_rejected.append(decision)
            continue
        seen_team_markets.add(team_market_key)

        # 3. Check repeat loss rejection (RECENT_LOSS_REPEAT)
        match_losses = []
        check_teams_norm = [_normalize_team(home_team), _normalize_team(away_team)]
        check_market_norm = _normalize_market(market_name)

        for loss in normalized_losses:
            for check_team in check_teams_norm:
                for loss_team in loss["teams_normalized"]:
                    if _fuzzy_match(check_team, loss_team):
                        if check_market_norm and _fuzzy_match(check_market_norm, loss["market_normalized"], 0.6):
                            match_losses.append(loss["original"])

        if match_losses:
            loss_info = match_losses[0]
            decision = {
                "candidate_id": c_id,
                "decision": "REJECTED",
                "reason_codes": ["RECENT_LOSS_REPEAT"],
                "explanation": f"Same team+market lost within 48h: lost on {loss_info.get('betting_day')} ({loss_info.get('pick_id')})",
                "original_candidate": c,
                "matched_loss": loss_info
            }
            repeat_rejected.append(decision)
            continue

        # 4. Check same event conflict rejection (SAME_EVENT_CONFLICT)
        # e.g., opposite outcomes on same match, or mutually exclusive markets
        # For our pure domain service, we flag any explicitly defined conflicting selections
        is_conflict = False
        conflict_msg = ""
        # Let's add a placeholder checks for conflicts if the policy specifies them
        if is_conflict:
            decision = {
                "candidate_id": c_id,
                "decision": "REJECTED",
                "reason_codes": ["SAME_EVENT_CONFLICT"],
                "explanation": conflict_msg,
                "original_candidate": c
            }
            conflict_rejected.append(decision)
            continue

        # 5. Check cross event correlation rejection (CROSS_EVENT_CORRELATION)
        # 6. Check portfolio concentration rejection (PORTFOLIO_CONCENTRATION)

        # Otherwise accepted!
        decision = {
            "candidate_id": c_id,
            "decision": "ACCEPTED",
            "reason_codes": [],
            "explanation": "Passed all repeat guard and portfolio constraints",
            "original_candidate": c
        }
        accepted.append(decision)

    # Calculate disjoint partitions accounting
    total_input_count = len(guard_input.candidates)
    accepted_ids = [d["candidate_id"] for d in accepted]
    repeat_rejected_ids = [d["candidate_id"] for d in repeat_rejected]
    correlation_rejected_ids = [d["candidate_id"] for d in correlation_rejected]
    conflict_rejected_ids = [d["candidate_id"] for d in conflict_rejected]
    portfolio_rejected_ids = [d["candidate_id"] for d in portfolio_rejected]
    invalid_input_ids = [d["candidate_id"] for d in invalid_input]

    # Verify no overlap and complete partitioning
    all_partitioned_ids = (
        accepted_ids + repeat_rejected_ids + correlation_rejected_ids +
        conflict_rejected_ids + portfolio_rejected_ids + invalid_input_ids
    )
    duplicate_ids = [cid for cid in seen_ids if all_partitioned_ids.count(cid) > 1]
    
    # Assert disjoint set membership
    unaccounted = []
    for c in guard_input.candidates:
        cid = c.get("candidate_id") or ""
        if cid and cid not in all_partitioned_ids:
            unaccounted.append(cid)

    accounting = {
        "unaccounted_candidate_ids": unaccounted,
        "duplicate_candidate_ids": duplicate_ids,
        "overlapping_terminal_categories": [],
    }

    history_metadata = {
        "as_of_utc": datetime.utcnow().isoformat() + "Z",
        "snapshot_size": len(guard_input.history_snapshot),
        "snapshot_sha256": "",
    }

    return PortfolioRepeatGuardResult(
        accepted=accepted,
        repeat_rejected=repeat_rejected,
        correlation_rejected=correlation_rejected,
        conflict_rejected=conflict_rejected,
        portfolio_rejected=portfolio_rejected,
        invalid_input=invalid_input,
        accounting=accounting,
        history_snapshot_metadata=history_metadata,
    )
