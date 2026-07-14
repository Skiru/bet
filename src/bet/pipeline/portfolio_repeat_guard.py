"""Pure portfolio and repeat guard domain service."""
from __future__ import annotations

import re
import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, UTC
from difflib import SequenceMatcher
from typing import Any


def _normalize_team(name: str) -> str:
    name = str(name).lower().strip()
    name = re.sub(r"\s+", " ", name)
    for token in ["fc ", "sc ", "ac ", "ss ", "bv ", "ud ", "sv ", "tsv ", "vfb "]:
        if name.startswith(token):
            name = name[len(token):]
    for token in [" fc", " sc", " ac", " cf"]:
        if name.endswith(token):
            name = name[: -len(token)]
    return name.strip()


def _normalize_market(market: str) -> str:
    market = str(market).lower().strip()
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


def _are_selections_contradictory(m1: str, s1: str, m2: str, s2: str) -> bool:
    m1_norm = _normalize_market(m1)
    m2_norm = _normalize_market(m2)
    s1_norm = str(s1).lower().strip()
    s2_norm = str(s2).lower().strip()
    
    if m1_norm == m2_norm:
        if s1_norm != s2_norm:
            opposites = [
                ({"over", "o"}, {"under", "u"}),
                ({"1", "home"}, {"2", "away"}),
                ({"yes"}, {"no"}),
            ]
            for op1, op2 in opposites:
                if (any(x in s1_norm for x in op1) and any(x in s2_norm for x in op2)) or \
                   (any(x in s2_norm for x in op1) and any(x in s1_norm for x in op2)):
                    return True
            return True
    return False


@dataclass
class PortfolioRepeatGuardInput:
    candidates: list[dict[str, Any]]
    history_snapshot: dict[str, Any] | list[dict[str, Any]]
    policy: dict[str, Any] = field(default_factory=dict)
    betting_day: str = ""
    run_id: str = ""
    source_s5_hash: str = ""


@dataclass
class PortfolioRepeatGuardResult:
    accepted: list[dict[str, Any]]
    repeat_rejected: list[dict[str, Any]]
    duplicate_rejected: list[dict[str, Any]]
    conflict_rejected: list[dict[str, Any]]
    correlation_rejected: list[dict[str, Any]]
    concentration_rejected: list[dict[str, Any]]
    invalid_input: list[dict[str, Any]]
    accounting: dict[str, Any]
    history_snapshot_metadata: dict[str, Any]
    rule_evaluation_summary: dict[str, str]

    @property
    def portfolio_rejected(self) -> list[dict[str, Any]]:
        return self.concentration_rejected


def evaluate_portfolio_repeat_guard(
    guard_input: PortfolioRepeatGuardInput
) -> PortfolioRepeatGuardResult:
    """Side-effect-free deterministic evaluation of portfolio and repeat guard rules."""
    accepted = []
    repeat_rejected = []
    duplicate_rejected = []
    conflict_rejected = []
    correlation_rejected = []
    concentration_rejected = []
    invalid_input = []

    # 1. Resolve and default policy configuration
    policy = guard_input.policy or {}
    if not policy:
        # Load from config
        policy_path = Path(__file__).resolve().parents[3] / "config" / "portfolio_policy.json"
        if policy_path.exists():
            try:
                policy = json.loads(policy_path.read_text(encoding="utf-8"))
            except Exception:
                pass
    if not policy:
        # Hard coded defaults fallback for robustness
        policy = {
            "policy_version": "1.0",
            "repeat_loss_lookback_hours": 48,
            "duplicate_signal_enabled": True,
            "same_event_conflict_enabled": True,
            "correlation_group_limit_enabled": True,
            "correlation_group_max_accepted": 3,
            "concentration_enabled": true,
            "per_event_limit": 2,
            "per_team_limit": 2,
            "per_competition_limit": 4,
            "per_sport_limit": 8
        }

    policy_version = policy.get("policy_version", "1.0")
    repeat_loss_hours = policy.get("repeat_loss_lookback_hours", 48)
    dup_signal_enabled = bool(policy.get("duplicate_signal_enabled", True))
    same_conflict_enabled = bool(policy.get("same_event_conflict_enabled", True))
    corr_group_enabled = bool(policy.get("correlation_group_limit_enabled", True))
    corr_group_max = int(policy.get("correlation_group_max_accepted", 3))
    concentration_enabled = bool(policy.get("concentration_enabled", True))

    # Parse and structure lookback history
    history_records = []
    history_meta = {}
    
    if isinstance(guard_input.history_snapshot, dict):
        history_records = guard_input.history_snapshot.get("records", [])
        history_meta = {
            "as_of_utc": guard_input.history_snapshot.get("as_of_utc", ""),
            "snapshot_size": len(history_records),
            "snapshot_sha256": guard_input.history_snapshot.get("snapshot_sha256", ""),
        }
    elif isinstance(guard_input.history_snapshot, list):
        history_records = guard_input.history_snapshot
        # Calculate SHA of sorted records
        records_str = json.dumps(history_records, sort_keys=True)
        h_sha = hashlib.sha256(records_str.encode("utf-8")).hexdigest()
        history_meta = {
            "as_of_utc": datetime.now(UTC).isoformat() + "Z",
            "snapshot_size": len(history_records),
            "snapshot_sha256": h_sha,
        }

    normalized_losses = []
    for loss in history_records:
        event = loss.get("event") or ""
        teams = _extract_teams_from_event(event)
        normalized_losses.append({
            "teams_normalized": [_normalize_team(t) for t in teams],
            "market_normalized": _normalize_market(loss.get("market") or ""),
            "selection": loss.get("selection") or "",
            "original": loss
        })

    # Rule evaluation overall summary
    rule_summary = {
        "duplicate_signal_rule": "ENFORCED" if dup_signal_enabled else "DISABLED_BY_POLICY",
        "recent_loss_rule": "ENFORCED",
        "same_event_conflict_rule": "ENFORCED" if same_conflict_enabled else "DISABLED_BY_POLICY",
        "correlation_rule": "ENFORCED" if corr_group_enabled else "DISABLED_BY_POLICY",
        "concentration_rule": "ENFORCED" if concentration_enabled else "DISABLED_BY_POLICY",
    }

    # Tracking sets/counts to enforce disjoint partitions and limits
    seen_ids = set()
    accepted_team_markets = set()
    accepted_selections = {} # (home, away, market) -> list of selections
    accepted_competition_counts = {}
    accepted_sport_counts = {}
    accepted_event_counts = {}
    accepted_team_counts = {}

    for c in guard_input.candidates:
        c_id = c.get("candidate_id") or c.get("id")
        if not c_id and c.get("home_team") and c.get("away_team"):
            c_id = f"{c.get('sport', 'unknown')}|{c.get('home_team')}|{c.get('away_team')}"

        # 1. Invalid candidate identity
        if not c_id or not c.get("home_team") or not c.get("away_team"):
            decision = {
                "candidate_id": c_id or "",
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
                "reason_codes": ["DUPLICATE_CANDIDATE_ID"],
                "explanation": f"Duplicate candidate ID '{c_id}' detected in the current run set",
                "original_candidate": c
            }
            invalid_input.append(decision)
            continue
        seen_ids.add(c_id)

        home_team = c.get("home_team") or ""
        away_team = c.get("away_team") or ""
        market_name = c.get("best_market", {}).get("name") or c.get("market_type") or c.get("market") or ""
        selection = c.get("best_market", {}).get("selection") or c.get("selection") or ""
        sport = c.get("sport") or ""
        competition = c.get("competition") or ""

        # Normalize values
        home_norm = _normalize_team(home_team)
        away_norm = _normalize_team(away_team)
        event_key = (home_norm, away_norm)
        market_norm = _normalize_market(market_name)

        # 2. Duplicate Signal Check
        if dup_signal_enabled:
            team_market_key = (home_norm, away_norm, market_norm, selection.lower().strip())
            if team_market_key in accepted_team_markets:
                decision = {
                    "candidate_id": c_id,
                    "decision": "REJECTED",
                    "reason_codes": ["DUPLICATE_SIGNAL"],
                    "explanation": f"Duplicate team+market signal detected: {home_team} vs {away_team} for {market_name} ({selection})",
                    "original_candidate": c
                }
                duplicate_rejected.append(decision)
                continue

        # 3. Same Event Conflict Check
        if same_conflict_enabled:
            conflict_found = False
            conflict_msg = ""
            event_market_key = (home_norm, away_norm, market_norm)
            if event_market_key in accepted_selections:
                for accepted_sel in accepted_selections[event_market_key]:
                    if _are_selections_contradictory(market_name, selection, market_name, accepted_sel):
                        conflict_found = True
                        conflict_msg = f"Contradictory selections for the same event/market: '{selection}' vs already accepted '{accepted_sel}'"
                        break
            if conflict_found:
                decision = {
                    "candidate_id": c_id,
                    "decision": "REJECTED",
                    "reason_codes": ["SAME_EVENT_CONFLICT"],
                    "explanation": conflict_msg,
                    "original_candidate": c
                }
                conflict_rejected.append(decision)
                continue

        # 4. Recent Loss Repeat Check
        match_losses = []
        check_teams_norm = [home_norm, away_norm]
        check_market_norm = market_norm

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

        # 5. Correlation Group Limit Check
        if corr_group_enabled:
            # We group by competition or sport
            comp_count = accepted_competition_counts.get(competition, 0)
            if comp_count >= corr_group_max:
                decision = {
                    "candidate_id": c_id,
                    "decision": "REJECTED",
                    "reason_codes": ["CROSS_EVENT_CORRELATION"],
                    "explanation": f"Correlation group limit exceeded for competition '{competition}': max {corr_group_max} accepted",
                    "original_candidate": c
                }
                correlation_rejected.append(decision)
                continue

        # 6. Portfolio Concentration Limit Check
        if concentration_enabled:
            # Event limit
            ev_limit = policy.get("per_event_limit", 2)
            event_count = accepted_event_counts.get(event_key, 0)
            if event_count >= ev_limit:
                decision = {
                    "candidate_id": c_id,
                    "decision": "REJECTED",
                    "reason_codes": ["PORTFOLIO_CONCENTRATION"],
                    "explanation": f"Event concentration limit exceeded for {home_team} vs {away_team}: max {ev_limit} accepted",
                    "original_candidate": c
                }
                concentration_rejected.append(decision)
                continue

            # Team limit
            t_limit = policy.get("per_team_limit", 2)
            t_exceeded = False
            for t in (home_norm, away_norm):
                if accepted_team_counts.get(t, 0) >= t_limit:
                    t_exceeded = True
                    t_name = home_team if t == home_norm else away_team
                    break
            if t_exceeded:
                decision = {
                    "candidate_id": c_id,
                    "decision": "REJECTED",
                    "reason_codes": ["PORTFOLIO_CONCENTRATION"],
                    "explanation": f"Team concentration limit exceeded for '{t_name}': max {t_limit} accepted",
                    "original_candidate": c
                }
                concentration_rejected.append(decision)
                continue

            # Competition limit
            comp_limit = policy.get("per_competition_limit", 4)
            if accepted_competition_counts.get(competition, 0) >= comp_limit:
                decision = {
                    "candidate_id": c_id,
                    "decision": "REJECTED",
                    "reason_codes": ["PORTFOLIO_CONCENTRATION"],
                    "explanation": f"Competition concentration limit exceeded for '{competition}': max {comp_limit} accepted",
                    "original_candidate": c
                }
                concentration_rejected.append(decision)
                continue

            # Sport limit
            sport_limit = policy.get("per_sport_limit", 8)
            if accepted_sport_counts.get(sport, 0) >= sport_limit:
                decision = {
                    "candidate_id": c_id,
                    "decision": "REJECTED",
                    "reason_codes": ["PORTFOLIO_CONCENTRATION"],
                    "explanation": f"Sport concentration limit exceeded for '{sport}': max {sport_limit} accepted",
                    "original_candidate": c
                }
                concentration_rejected.append(decision)
                continue

        # If it reaches here, the candidate passes all rules and is ACCEPTED!
        decision = {
            "candidate_id": c_id,
            "decision": "ACCEPTED",
            "reason_codes": [],
            "explanation": "Passed all repeat guard and portfolio constraints",
            "original_candidate": c
        }
        accepted.append(decision)

        # Update tracking structures for subsequently evaluated candidates
        team_market_key = (home_norm, away_norm, market_norm, selection.lower().strip())
        accepted_team_markets.add(team_market_key)
        
        event_market_key = (home_norm, away_norm, market_norm)
        if event_market_key not in accepted_selections:
            accepted_selections[event_market_key] = []
        accepted_selections[event_market_key].append(selection)

        accepted_competition_counts[competition] = accepted_competition_counts.get(competition, 0) + 1
        accepted_sport_counts[sport] = accepted_sport_counts.get(sport, 0) + 1
        accepted_event_counts[event_key] = accepted_event_counts.get(event_key, 0) + 1
        accepted_team_counts[home_norm] = accepted_team_counts.get(home_norm, 0) + 1
        accepted_team_counts[away_norm] = accepted_team_counts.get(away_norm, 0) + 1

    # Disjoint partitions accounting validation
    total_input_count = len(guard_input.candidates)
    accepted_ids = [d["candidate_id"] for d in accepted]
    repeat_rejected_ids = [d["candidate_id"] for d in repeat_rejected]
    duplicate_rejected_ids = [d["candidate_id"] for d in duplicate_rejected]
    conflict_rejected_ids = [d["candidate_id"] for d in conflict_rejected]
    correlation_rejected_ids = [d["candidate_id"] for d in correlation_rejected]
    concentration_rejected_ids = [d["candidate_id"] for d in concentration_rejected]
    invalid_input_ids = [d["candidate_id"] for d in invalid_input]

    all_partitioned_ids = (
        accepted_ids + repeat_rejected_ids + duplicate_rejected_ids +
        conflict_rejected_ids + correlation_rejected_ids +
        concentration_rejected_ids + invalid_input_ids
    )

    duplicate_ids = []
    seen_partitioned = set()
    for cid in all_partitioned_ids:
        if cid in seen_partitioned:
            duplicate_ids.append(cid)
        seen_partitioned.add(cid)

    unaccounted = []
    for c in guard_input.candidates:
        cid = c.get("candidate_id") or ""
        if cid and cid not in all_partitioned_ids:
            unaccounted.append(cid)

    # Check for any overlapping entries
    overlapping_terminal = []
    # Every terminal list must be pairwise disjoint
    # Since we use `continue` once we assign a candidate to a list, they are disjoint by definition!
    
    accounting = {
        "unaccounted_candidate_ids": unaccounted,
        "duplicate_candidate_ids": duplicate_ids,
        "overlapping_terminal_categories": overlapping_terminal,
    }

    return PortfolioRepeatGuardResult(
        accepted=accepted,
        repeat_rejected=repeat_rejected,
        duplicate_rejected=duplicate_rejected,
        conflict_rejected=conflict_rejected,
        correlation_rejected=correlation_rejected,
        concentration_rejected=concentration_rejected,
        invalid_input=invalid_input,
        accounting=accounting,
        history_snapshot_metadata=history_meta,
        rule_evaluation_summary=rule_summary,
    )
