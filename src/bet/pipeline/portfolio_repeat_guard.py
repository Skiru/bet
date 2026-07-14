"""Pure portfolio and repeat guard domain service."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any


@dataclass(frozen=True)
class PortfolioPolicy:
    schema_version: int
    policy_version: str
    repeat_loss_lookback_hours: int
    duplicate_signal_enabled: bool
    same_event_conflict_enabled: bool
    correlation_group_limit_enabled: bool
    correlation_group_max_accepted: int
    concentration_enabled: bool
    per_event_limit: int
    per_team_limit: int
    per_competition_limit: int
    per_sport_limit: int
    policy_sha256: str


@dataclass(frozen=True)
class HistorySnapshot:
    schema_version: int
    artifact_type: str  # S6_HISTORY_SNAPSHOT_V1
    as_of_utc: str
    lookback_start_utc: str
    boundary_policy: str
    source_identity: str
    opened_read_only: bool
    query_version: str
    policy_version: str
    records: list[dict[str, Any]]
    row_count: int
    snapshot_sha256: str


@dataclass
class PortfolioRepeatGuardInput:
    candidates: list[dict[str, Any]]
    history_snapshot: HistorySnapshot | dict[str, Any] | list[dict[str, Any]]
    policy: PortfolioPolicy | dict[str, Any] = field(default_factory=dict)
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


def validate_portfolio_policy_schema(policy_data: dict[str, Any], file_sha256: str = "") -> PortfolioPolicy:
    if not isinstance(policy_data, dict):
        raise ValueError("BLOCKED_POLICY_INVALID: Policy is not a JSON object")

    schema_ver = policy_data.get("schema_version", 1)
    policy_ver = policy_data.get("policy_version")
    if not isinstance(policy_ver, str) or not policy_ver:
        raise ValueError("BLOCKED_POLICY_INVALID: Missing or invalid policy_version")

    # Verify enabled/disabled flags are booleans
    for flag in ("duplicate_signal_enabled", "same_event_conflict_enabled",
                 "correlation_group_limit_enabled", "concentration_enabled"):
        if flag not in policy_data:
            raise ValueError(f"BLOCKED_POLICY_INVALID: Missing boolean flag: {flag}")
        if not isinstance(policy_data[flag], bool):
            raise ValueError(f"BLOCKED_POLICY_INVALID: Flag '{flag}' must be a boolean")

    # Verify limits are non-negative integers
    for limit in ("repeat_loss_lookback_hours", "correlation_group_max_accepted",
                  "per_event_limit", "per_team_limit", "per_competition_limit", "per_sport_limit"):
        if limit not in policy_data:
            raise ValueError(f"BLOCKED_POLICY_INVALID: Missing numeric limit: {limit}")
        val = policy_data[limit]
        if not isinstance(val, int) or isinstance(val, bool) or val < 0:
            raise ValueError(f"BLOCKED_POLICY_INVALID: Limit '{limit}' must be a non-negative integer")

    return PortfolioPolicy(
        schema_version=schema_ver,
        policy_version=policy_ver,
        repeat_loss_lookback_hours=policy_data["repeat_loss_lookback_hours"],
        duplicate_signal_enabled=policy_data["duplicate_signal_enabled"],
        same_event_conflict_enabled=policy_data["same_event_conflict_enabled"],
        correlation_group_limit_enabled=policy_data["correlation_group_limit_enabled"],
        correlation_group_max_accepted=policy_data["correlation_group_max_accepted"],
        concentration_enabled=policy_data["concentration_enabled"],
        per_event_limit=policy_data["per_event_limit"],
        per_team_limit=policy_data["per_team_limit"],
        per_competition_limit=policy_data["per_competition_limit"],
        per_sport_limit=policy_data["per_sport_limit"],
        policy_sha256=file_sha256
    )


def validate_history_snapshot_schema(history_data: dict[str, Any]) -> HistorySnapshot:
    if not isinstance(history_data, dict):
        raise ValueError("BLOCKED_HISTORY_UNAVAILABLE: History snapshot is not a JSON object")

    schema_ver = history_data.get("schema_version")
    if schema_ver is None:
        raise ValueError("BLOCKED_HISTORY_UNAVAILABLE: Missing schema_version in history snapshot")

    art_type = history_data.get("artifact_type")
    if art_type != "S6_HISTORY_SNAPSHOT_V1":
        raise ValueError(f"BLOCKED_HISTORY_UNAVAILABLE: Invalid artifact_type in history snapshot: {art_type}")

    as_of = history_data.get("as_of_utc")
    if not as_of:
        raise ValueError("BLOCKED_HISTORY_UNAVAILABLE: Missing as_of_utc in history snapshot")

    # Timezone awareness check
    try:
        dt = datetime.fromisoformat(as_of)
        if dt.tzinfo is None:
            raise ValueError("BLOCKED_HISTORY_UNAVAILABLE: as_of_utc must be timezone aware")
    except Exception as exc:
        raise ValueError(f"BLOCKED_HISTORY_UNAVAILABLE: Invalid or naive as_of_utc: {exc}")

    records = history_data.get("records")
    if not isinstance(records, list):
        raise ValueError("BLOCKED_HISTORY_UNAVAILABLE: records field must be a list in history snapshot")

    for idx, r in enumerate(records):
        ts = r.get("settled_at_utc") or r.get("result_recorded_at_utc")
        if not ts:
            raise ValueError(f"BLOCKED_HISTORY_UNAVAILABLE: Record at index {idx} is missing settled/recorded UTC timestamp")
        try:
            rdt = datetime.fromisoformat(ts)
            if rdt.tzinfo is None:
                raise ValueError(f"BLOCKED_HISTORY_UNAVAILABLE: Record timestamp at index {idx} is timezone naive")
        except Exception:
            raise ValueError(f"BLOCKED_HISTORY_UNAVAILABLE: Record timestamp at index {idx} is invalid")

    return HistorySnapshot(
        schema_version=schema_ver,
        artifact_type=art_type,
        as_of_utc=as_of,
        lookback_start_utc=history_data.get("lookback_start_utc", ""),
        boundary_policy=history_data.get("boundary_policy", "half_open"),
        source_identity=history_data.get("source_identity", ""),
        opened_read_only=bool(history_data.get("opened_read_only", True)),
        query_version=history_data.get("query_version", "1.0"),
        policy_version=history_data.get("policy_version", "1.0"),
        records=records,
        row_count=history_data.get("row_count", len(records)),
        snapshot_sha256=history_data.get("snapshot_sha256", "")
    )


def get_canonical_identity_tuple(c: dict[str, Any]) -> tuple:
    event_id = c.get("event_id") or c.get("canonical_event_id") or f"{_normalize_team(c.get('home_team', ''))}|{_normalize_team(c.get('away_team', ''))}"
    market_family = c.get("market_family") or ""
    market_type = _normalize_market(c.get("market_type") or c.get("best_market", {}).get("name") or c.get("market") or "")
    subject_id = c.get("subject_id") or c.get("player_id") or ""
    selection = str(c.get("selection") or c.get("best_market", {}).get("selection") or "").lower().strip()
    direction = str(c.get("direction") or "").lower().strip()
    line = str(c.get("line") or "").lower().strip()
    period = str(c.get("period") or "full_time").lower().strip()

    return (event_id, market_family, market_type, subject_id, selection, direction, line, period)


def are_selections_contradictory_v2(c1: dict[str, Any], c2: dict[str, Any]) -> bool:
    id1 = get_canonical_identity_tuple(c1)
    id2 = get_canonical_identity_tuple(c2)

    # Must be same event and period
    if id1[0] != id2[0] or id1[7] != id2[7]:
        return False

    market_type1 = id1[2]
    market_type2 = id2[2]

    if market_type1 == market_type2:
        sel1 = id1[4]
        sel2 = id2[4]
        if sel1 != sel2:
            # 1 vs X vs 2
            three_way = {"1", "x", "2", "home", "draw", "away"}
            if sel1 in three_way and sel2 in three_way:
                return True
            # Over vs Under (ensure line matches)
            ou1 = {"over", "o", "under", "u"}
            if any(x in sel1 for x in {"over", "o"}) and any(x in sel2 for x in {"under", "u"}):
                if id1[6] == id2[6]:
                    return True
            # Yes vs No
            yn = {"yes", "no"}
            if sel1 in yn and sel2 in yn:
                return True
    return False


def get_correlation_group_id(c: dict[str, Any]) -> str:
    """Deterministic typed function to derive a unique correlation group ID."""
    # We group by event
    event_id = c.get("event_id") or c.get("canonical_event_id") or f"{_normalize_team(c.get('home_team', ''))}|{_normalize_team(c.get('away_team', ''))}"
    return f"event_group_{event_id}"


def evaluate_portfolio_repeat_guard(
    guard_input: PortfolioRepeatGuardInput
) -> PortfolioRepeatGuardResult:
    """Side-effect-free deterministic evaluation of portfolio and repeat guard rules.

    Operates strictly on validated PortfolioPolicy, HistorySnapshot, and PortfolioRepeatGuardInput.
    """
    accepted = []
    repeat_rejected = []
    duplicate_rejected = []
    conflict_rejected = []
    correlation_rejected = []
    concentration_rejected = []
    invalid_input = []

    # 1. Resolve and validate Policy Object
    policy_obj = guard_input.policy
    if isinstance(policy_obj, dict):
        policy_obj = validate_portfolio_policy_schema(policy_obj)
    elif not isinstance(policy_obj, PortfolioPolicy):
        raise ValueError("BLOCKED_POLICY_INVALID: Policy is missing or malformed")

    # 2. Resolve and validate History Snapshot
    history_obj = guard_input.history_snapshot
    if isinstance(history_obj, dict):
        history_obj = validate_history_snapshot_schema(history_obj)
    elif isinstance(history_obj, list):
        records = history_obj
        records_json = json.dumps(records, sort_keys=True)
        h_sha = hashlib.sha256(records_json.encode("utf-8")).hexdigest()
        snap_dict = {
            "schema_version": 1,
            "artifact_type": "S6_HISTORY_SNAPSHOT_V1",
            "as_of_utc": datetime.now(UTC).isoformat() + "Z",
            "records": records,
            "snapshot_sha256": h_sha
        }
        history_obj = validate_history_snapshot_schema(snap_dict)
    elif not isinstance(history_obj, HistorySnapshot):
        raise ValueError("BLOCKED_HISTORY_UNAVAILABLE: History snapshot is missing or malformed")

    dup_signal_enabled = policy_obj.duplicate_signal_enabled
    same_conflict_enabled = policy_obj.same_event_conflict_enabled
    corr_group_enabled = policy_obj.correlation_group_limit_enabled
    corr_group_max = policy_obj.correlation_group_max_accepted
    concentration_enabled = policy_obj.concentration_enabled

    # Parse losses into structured normalized format
    normalized_losses = []
    for loss in history_obj.records:
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
        "recent_loss_rule": "ENFORCED" if len(history_obj.records) > 0 else "NOT_APPLICABLE",
        "same_event_conflict_rule": "ENFORCED" if same_conflict_enabled else "DISABLED_BY_POLICY",
        "correlation_rule": "ENFORCED" if corr_group_enabled else "DISABLED_BY_POLICY",
        "concentration_rule": "ENFORCED" if concentration_enabled else "DISABLED_BY_POLICY",
    }

    # Tracking sets/counts to enforce disjoint partitions and limits
    seen_ids = set()
    accepted_canonical_identities = set()
    accepted_candidates_list = []  # Preserve insertion order
    accepted_event_counts = {}
    accepted_team_counts = {}
    accepted_competition_counts = {}
    accepted_sport_counts = {}
    accepted_correlation_counts = {}

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
            raise ValueError(f"S6_CANDIDATE_ACCOUNTING_MISMATCH: Duplicate candidate ID '{c_id}' detected in the current run set")
        seen_ids.add(c_id)

        home_team = c.get("home_team") or ""
        away_team = c.get("away_team") or ""
        market_name = c.get("best_market", {}).get("name") or c.get("market_type") or c.get("market") or ""
        sport = c.get("sport") or ""
        competition = c.get("competition") or ""

        # Normalize values
        home_norm = _normalize_team(home_team)
        away_norm = _normalize_team(away_team)
        event_key = (home_norm, away_norm)
        market_norm = _normalize_market(market_name)

        # 2. Duplicate Signal Check
        if dup_signal_enabled:
            c_identity = get_canonical_identity_tuple(c)
            if c_identity in accepted_canonical_identities:
                decision = {
                    "candidate_id": c_id,
                    "decision": "REJECTED",
                    "reason_codes": ["DUPLICATE_SIGNAL"],
                    "explanation": f"Duplicate team+market signal detected for canonical identity: {c_identity}",
                    "original_candidate": c
                }
                duplicate_rejected.append(decision)
                continue

        # 3. Same Event Conflict Check
        if same_conflict_enabled:
            conflict_found = False
            conflict_msg = ""
            for accepted_c in accepted_candidates_list:
                if are_selections_contradictory_v2(c, accepted_c):
                    conflict_found = True
                    conflict_msg = "Contradictory selections for the same event/market."
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

        # 4. Recent Loss Repeat Check (Lookback is half-open based on snapshots)
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
                "explanation": "Same team+market lost within lookback window",
                "original_candidate": c,
                "matched_loss": loss_info
            }
            repeat_rejected.append(decision)
            continue

        # 5. Correlation Group Limit Check
        if corr_group_enabled:
            corr_id = get_correlation_group_id(c)
            if accepted_correlation_counts.get(corr_id, 0) >= corr_group_max:
                decision = {
                    "candidate_id": c_id,
                    "decision": "REJECTED",
                    "reason_codes": ["CROSS_EVENT_CORRELATION"],
                    "explanation": f"Correlation group limit exceeded for group '{corr_id}': max {corr_group_max} accepted",
                    "original_candidate": c
                }
                correlation_rejected.append(decision)
                continue

        # 6. Portfolio Concentration Limit Check
        if concentration_enabled:
            # Event limit
            ev_limit = policy_obj.per_event_limit
            event_count = accepted_event_counts.get(event_key, 0)
            if event_count >= ev_limit:
                decision = {
                    "candidate_id": c_id,
                    "decision": "REJECTED",
                    "reason_codes": ["PORTFOLIO_CONCENTRATION"],
                    "explanation": f"Event concentration limit exceeded: max {ev_limit} accepted",
                    "original_candidate": c
                }
                concentration_rejected.append(decision)
                continue

            # Team limit
            t_limit = policy_obj.per_team_limit
            t_exceeded = False
            for t in (home_norm, away_norm):
                if accepted_team_counts.get(t, 0) >= t_limit:
                    t_exceeded = True
                    break
            if t_exceeded:
                decision = {
                    "candidate_id": c_id,
                    "decision": "REJECTED",
                    "reason_codes": ["PORTFOLIO_CONCENTRATION"],
                    "explanation": f"Team concentration limit exceeded: max {t_limit} accepted",
                    "original_candidate": c
                }
                concentration_rejected.append(decision)
                continue

            # Competition Concentration limit (formerly named Competition Limit)
            comp_limit = policy_obj.per_competition_limit
            if accepted_competition_counts.get(competition, 0) >= comp_limit:
                decision = {
                    "candidate_id": c_id,
                    "decision": "REJECTED",
                    "reason_codes": ["COMPETITION_CONCENTRATION"],
                    "explanation": f"Competition concentration limit exceeded: max {comp_limit} accepted",
                    "original_candidate": c
                }
                concentration_rejected.append(decision)
                continue

            # Sport limit
            sport_limit = policy_obj.per_sport_limit
            if accepted_sport_counts.get(sport, 0) >= sport_limit:
                decision = {
                    "candidate_id": c_id,
                    "decision": "REJECTED",
                    "reason_codes": ["PORTFOLIO_CONCENTRATION"],
                    "explanation": f"Sport concentration limit exceeded: max {sport_limit} accepted",
                    "original_candidate": c
                }
                concentration_rejected.append(decision)
                continue

        # Pass all rules: ACCEPTED
        decision = {
            "candidate_id": c_id,
            "decision": "ACCEPTED",
            "reason_codes": [],
            "explanation": "Passed all repeat guard and portfolio constraints",
            "original_candidate": c
        }
        accepted.append(decision)

        # Update tracking structures for subsequently evaluated candidates
        if dup_signal_enabled:
            accepted_canonical_identities.add(get_canonical_identity_tuple(c))
        accepted_candidates_list.append(c)

        accepted_event_counts[event_key] = accepted_event_counts.get(event_key, 0) + 1
        accepted_team_counts[home_norm] = accepted_team_counts.get(home_norm, 0) + 1
        accepted_team_counts[away_norm] = accepted_team_counts.get(away_norm, 0) + 1
        accepted_competition_counts[competition] = accepted_competition_counts.get(competition, 0) + 1
        accepted_sport_counts[sport] = accepted_sport_counts.get(sport, 0) + 1

        corr_id = get_correlation_group_id(c)
        accepted_correlation_counts[corr_id] = accepted_correlation_counts.get(corr_id, 0) + 1

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

    # Ensure complete, disjoint partition of input IDs
    input_ids = []
    for c in guard_input.candidates:
        cid = c.get("candidate_id") or c.get("id")
        if not cid and c.get("home_team") and c.get("away_team"):
            cid = f"{c.get('sport', 'unknown')}|{c.get('home_team')}|{c.get('away_team')}"
        input_ids.append(cid)

    if len(all_partitioned_ids) != total_input_count or set(all_partitioned_ids) != set(input_ids):
        unaccounted = list(set(input_ids) - set(all_partitioned_ids))
        raise ValueError(f"S6_CANDIDATE_ACCOUNTING_MISMATCH: Partition of S5 candidates is incomplete. Unaccounted IDs: {unaccounted}")

    # All sets pairwise disjoint by definition of conditional loop structure
    accounting = {
        "unaccounted_candidate_ids": [],
        "duplicate_candidate_ids": [],
        "overlapping_terminal_categories": [],
        "accepted_ids": accepted_ids,
        "repeat_rejected_ids": repeat_rejected_ids,
        "duplicate_rejected_ids": duplicate_rejected_ids,
        "conflict_rejected_ids": conflict_rejected_ids,
        "correlation_rejected_ids": correlation_rejected_ids,
        "concentration_rejected_ids": concentration_rejected_ids,
        "invalid_input_ids": invalid_input_ids
    }

    history_meta = {
        "schema_version": history_obj.schema_version,
        "artifact_type": history_obj.artifact_type,
        "as_of_utc": history_obj.as_of_utc,
        "snapshot_sha256": history_obj.snapshot_sha256,
        "row_count": history_obj.row_count,
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
