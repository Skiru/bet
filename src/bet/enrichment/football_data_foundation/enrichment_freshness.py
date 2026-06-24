from __future__ import annotations

import datetime
import json
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidenceFreshnessPolicy:
    capability: str
    ttl_seconds_pre_match: int
    ttl_seconds_live: int
    ttl_seconds_post_final: int
    final_state_locks: tuple[str, ...]
    status_sensitive: bool


@dataclass(frozen=True)
class EvidenceFreshnessInput:
    profile_id: str
    capability: str
    provider_id: str
    provider_event_id: str
    scanner_event_id: str
    evidence_retrieved_at: str  # ISO timestamp
    evidence_event_status_state: str  # e.g., "pre", "in", "post"
    evidence_event_status_name: str  # e.g., "STATUS_SCHEDULED", etc.
    current_event_status_state: str | None
    current_event_status_name: str | None
    now_utc: str  # ISO timestamp
    evidence_score_home: int | None = None
    evidence_score_away: int | None = None
    current_score_home: int | None = None
    current_score_away: int | None = None
    evidence_period: int | None = None
    current_period: int | None = None
    evidence_clock: str | None = None
    current_clock: str | None = None
    completed: bool | None = None
    has_final_stats: bool | None = None


@dataclass(frozen=True)
class EvidenceFreshnessDecision:
    decision: str
    reason: str
    stale_reason: str | None = None
    must_refresh: bool = False
    live_ttl_seconds: int | None = None
    expires_at_utc: str | None = None
    snapshot_valid_until_utc: str | None = None
    status_sensitive: bool = False
    complete_kind: str | None = None
    pre_match_ttl_seconds: int | None = None

    @property
    def freshness_decision(self) -> str:
        return self.decision


def _parse_iso(dt_str: str) -> datetime.datetime:
    """Parse ISO timestamp with timezone support."""
    s = dt_str.replace("Z", "+00:00")
    return datetime.datetime.fromisoformat(s)


def is_live_status(state: str | None, name: str | None) -> bool:
    if state == "in":
        return True
    if name:
        name_upper = name.upper()
        live_prefixes = (
            "STATUS_FIRST",
            "STATUS_HALF",
            "STATUS_SECOND",
            "STATUS_EXTRA",
            "STATUS_IN_PROGRESS",
            "STATUS_LIVE",
        )
        for prefix in live_prefixes:
            if prefix in name_upper:
                return True
    return False


def is_final_status(
    state: str | None,
    name: str | None,
    final_state_locks: tuple[str, ...],
    completed: bool | None = None,
) -> bool:
    if state == "post":
        return True
    if completed is True:
        return True
    if name and name in final_state_locks:
        return True
    return False


def evaluate_freshness(
    policy: EvidenceFreshnessPolicy, input_data: EvidenceFreshnessInput
) -> EvidenceFreshnessDecision:
    """Evaluate freshness of cached evidence against policy and current live status.
    This evaluation function is physically normalized to prevent stale usage.
    """
    if (
        not input_data.evidence_retrieved_at
        or not input_data.evidence_event_status_state
        or not input_data.evidence_event_status_name
    ):
        return EvidenceFreshnessDecision(
            decision="MISSING_REFRESH_REQUIRED",
            reason="Retrieved time or cached status is missing",
            stale_reason="missing_metadata",
            must_refresh=True,
        )

    try:
        evidence_retrieved_dt = _parse_iso(input_data.evidence_retrieved_at)
        now_dt = _parse_iso(input_data.now_utc)
        age_seconds = (now_dt - evidence_retrieved_dt).total_seconds()
    except Exception as e:
        return EvidenceFreshnessDecision(
            decision="STALE_REFRESH_REQUIRED",
            reason=f"Timestamp parsing failed: {e}",
            stale_reason="timestamp_parse_error",
            must_refresh=True,
        )

    is_live = is_live_status(
        input_data.current_event_status_state,
        input_data.current_event_status_name,
    ) or is_live_status(
        input_data.evidence_event_status_state,
        input_data.evidence_event_status_name,
    )

    is_final = is_final_status(
        input_data.current_event_status_state,
        input_data.current_event_status_name,
        policy.final_state_locks,
        input_data.completed,
    ) or is_final_status(
        input_data.evidence_event_status_state,
        input_data.evidence_event_status_name,
        policy.final_state_locks,
        input_data.completed,
    )

    is_pre = not is_live and not is_final

    if is_live:
        live_ttl_seconds = policy.ttl_seconds_live
        expires_at_dt = evidence_retrieved_dt + datetime.timedelta(
            seconds=live_ttl_seconds
        )
        expires_at_utc = expires_at_dt.isoformat()
        snapshot_valid_until_utc = expires_at_utc
        pre_match_ttl_seconds = None
        status_sensitive = True
        complete_kind = "COMPLETE_FOR_SNAPSHOT"
    elif is_pre:
        pre_ttl = policy.ttl_seconds_pre_match
        expires_at_dt = evidence_retrieved_dt + datetime.timedelta(
            seconds=pre_ttl
        )
        expires_at_utc = expires_at_dt.isoformat()
        snapshot_valid_until_utc = expires_at_utc
        live_ttl_seconds = None
        pre_match_ttl_seconds = pre_ttl
        status_sensitive = policy.status_sensitive
        complete_kind = None
    else:
        post_ttl = policy.ttl_seconds_post_final
        expires_at_dt = evidence_retrieved_dt + datetime.timedelta(
            seconds=post_ttl
        )
        expires_at_utc = expires_at_dt.isoformat()
        snapshot_valid_until_utc = expires_at_utc
        live_ttl_seconds = None
        pre_match_ttl_seconds = None
        status_sensitive = policy.status_sensitive
        complete_kind = None

    live_status_unavailable = (
        input_data.current_event_status_name is None
        or input_data.current_event_status_state is None
    )

    if live_status_unavailable:
        if is_final:
            return EvidenceFreshnessDecision(
                decision="FINAL_LOCKED_REUSABLE",
                reason=(
                    "Final state is locked and immutable (live scoreboard "
                    "unavailable)"
                ),
                must_refresh=False,
                expires_at_utc=expires_at_utc,
                snapshot_valid_until_utc=snapshot_valid_until_utc,
                status_sensitive=status_sensitive,
                complete_kind=complete_kind,
            )

        ttl = policy.ttl_seconds_pre_match
        if is_live:
            ttl = policy.ttl_seconds_live

        if age_seconds > ttl:
            decision_name = (
                "LIVE_STATUS_UNAVAILABLE_REFRESH_REQUIRED"
                if is_live
                else "STALE_REFRESH_REQUIRED"
            )
            return EvidenceFreshnessDecision(
                decision=decision_name,
                reason=(
                    "Live status check is unavailable and cached "
                    "evidence is stale"
                ),
                stale_reason="live_status_unavailable_and_stale",
                must_refresh=True,
                live_ttl_seconds=live_ttl_seconds,
                pre_match_ttl_seconds=pre_match_ttl_seconds,
                expires_at_utc=expires_at_utc,
                snapshot_valid_until_utc=snapshot_valid_until_utc,
                status_sensitive=status_sensitive,
                complete_kind=complete_kind,
            )

        decision_name = (
            "LIVE_SHORT_TTL_REUSABLE" if is_live else "FRESH_REUSABLE"
        )
        return EvidenceFreshnessDecision(
            decision=decision_name,
            reason=(
                "Live status is unavailable but cached evidence is "
                "within TTL"
            ),
            must_refresh=False,
            live_ttl_seconds=live_ttl_seconds,
            pre_match_ttl_seconds=pre_match_ttl_seconds,
            expires_at_utc=expires_at_utc,
            snapshot_valid_until_utc=snapshot_valid_until_utc,
            status_sensitive=status_sensitive,
            complete_kind=complete_kind,
        )

    has_status_drift = (
        input_data.evidence_event_status_name
        != input_data.current_event_status_name
        or input_data.evidence_event_status_state
        != input_data.current_event_status_state
    )

    if has_status_drift:
        decision_name = (
            "LIVE_STATUS_SENSITIVE_REFRESH_REQUIRED"
            if is_live
            else "STATUS_DRIFT_REFRESH_REQUIRED"
        )
        return EvidenceFreshnessDecision(
            decision=decision_name,
            reason=(
                f"Status drifted from {input_data.evidence_event_status_name}/"
                f"{input_data.evidence_event_status_state} to "
                f"{input_data.current_event_status_name}/"
                f"{input_data.current_event_status_state}"
            ),
            stale_reason="STATUS_DRIFT_REFRESH_REQUIRED",
            must_refresh=True,
            live_ttl_seconds=live_ttl_seconds,
            pre_match_ttl_seconds=pre_match_ttl_seconds,
            expires_at_utc=expires_at_utc,
            snapshot_valid_until_utc=snapshot_valid_until_utc,
            status_sensitive=status_sensitive,
            complete_kind=complete_kind,
        )

    if is_live:
        score_drift = (
            (
                input_data.evidence_score_home is not None
                and input_data.current_score_home is not None
                and input_data.evidence_score_home
                != input_data.current_score_home
            )
            or (
                input_data.evidence_score_away is not None
                and input_data.current_score_away is not None
                and input_data.evidence_score_away
                != input_data.current_score_away
            )
        )
        period_drift = (
            input_data.evidence_period is not None
            and input_data.current_period is not None
            and input_data.evidence_period != input_data.current_period
        )
        clock_drift = (
            input_data.evidence_clock is not None
            and input_data.current_clock is not None
            and input_data.evidence_clock != input_data.current_clock
        )

        if score_drift or period_drift or clock_drift:
            return EvidenceFreshnessDecision(
                decision="LIVE_STATUS_SENSITIVE_REFRESH_REQUIRED",
                reason=(
                    f"Live metric drift detected (score={score_drift}, "
                    f"period={period_drift}, clock={clock_drift})"
                ),
                stale_reason="LIVE_CLOCK_OR_SCORE_DRIFT",
                must_refresh=True,
                live_ttl_seconds=live_ttl_seconds,
                expires_at_utc=expires_at_utc,
                snapshot_valid_until_utc=snapshot_valid_until_utc,
                status_sensitive=status_sensitive,
                complete_kind=complete_kind,
            )

    if is_final:
        if input_data.completed is False:
            return EvidenceFreshnessDecision(
                decision="STALE_REFRESH_REQUIRED",
                reason=(
                    "Completed is explicitly False for a final/post status, "
                    "blocking final state lock"
                ),
                stale_reason="unverified_final_status",
                must_refresh=True,
                expires_at_utc=expires_at_utc,
                snapshot_valid_until_utc=snapshot_valid_until_utc,
                status_sensitive=status_sensitive,
                complete_kind=complete_kind,
            )

        if (
            input_data.capability == "detailed_metrics"
            and input_data.has_final_stats is False
        ):
            return EvidenceFreshnessDecision(
                decision="STALE_REFRESH_REQUIRED",
                reason=(
                    "Detailed metrics are not final-lockable because provider "
                    "evidence lacks final stats"
                ),
                stale_reason="missing_final_stats",
                must_refresh=True,
                expires_at_utc=expires_at_utc,
                snapshot_valid_until_utc=snapshot_valid_until_utc,
                status_sensitive=status_sensitive,
                complete_kind=complete_kind,
            )

        return EvidenceFreshnessDecision(
            decision="FINAL_LOCKED_REUSABLE",
            reason="Final state matches current state and is locked",
            must_refresh=False,
            expires_at_utc=expires_at_utc,
            snapshot_valid_until_utc=snapshot_valid_until_utc,
            status_sensitive=status_sensitive,
            complete_kind=complete_kind,
        )

    ttl = pre_match_ttl_seconds if is_pre else live_ttl_seconds
    if ttl is not None and age_seconds > ttl:
        decision_name = (
            "LIVE_STATUS_SENSITIVE_REFRESH_REQUIRED"
            if is_live
            else "STALE_REFRESH_REQUIRED"
        )
        return EvidenceFreshnessDecision(
            decision=decision_name,
            reason=f"TTL expired: age {age_seconds}s exceeds limit {ttl}s",
            stale_reason="ttl_expired",
            must_refresh=True,
            live_ttl_seconds=live_ttl_seconds,
            pre_match_ttl_seconds=pre_match_ttl_seconds,
            expires_at_utc=expires_at_utc,
            snapshot_valid_until_utc=snapshot_valid_until_utc,
            status_sensitive=status_sensitive,
            complete_kind=complete_kind,
        )

    decision_name = "LIVE_SHORT_TTL_REUSABLE" if is_live else "FRESH_REUSABLE"
    return EvidenceFreshnessDecision(
        decision=decision_name,
        reason="Within TTL and status matches",
        must_refresh=False,
        live_ttl_seconds=live_ttl_seconds,
        pre_match_ttl_seconds=pre_match_ttl_seconds,
        expires_at_utc=expires_at_utc,
        snapshot_valid_until_utc=snapshot_valid_until_utc,
        status_sensitive=status_sensitive,
        complete_kind=complete_kind,
    )


def check_live_status_drift(
    cached_status_name: str,
    cached_status_state: str,
    mock_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a bounded check of live status drift against cached evidence status."""
    current_status_name = None
    current_status_state = None
    scores = None
    endpoint_status = "ENDPOINT_VERIFIED"
    error_message = None
    payload = {}

    if mock_payload is not None:
        payload = mock_payload
    else:
        url = (
            "https://site.api.espn.com/apis/site/v2/sports/soccer/"
            "fifa.world/scoreboard"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as e:
            endpoint_status = "ENDPOINT_TRANSPORT_ERROR"
            error_message = str(e)

    if endpoint_status == "ENDPOINT_VERIFIED":
        events = payload.get("events") or []
        event_found = False
        for ev in events:
            if str(ev.get("id")) == "760442":
                event_found = True
                competitions = ev.get("competitions") or []
                if competitions:
                    comp = competitions[0]
                    status_dict = comp.get("status") or {}
                    current_status_name = status_dict.get("type", {}).get(
                        "name"
                    )
                    current_status_state = status_dict.get("type", {}).get(
                        "state"
                    )

                    competitors = comp.get("competitors") or []
                    scores_dict = {}
                    for competitor in competitors:
                        role = competitor.get("homeAway")
                        score = competitor.get("score")
                        scores_dict[role] = score
                    scores = scores_dict
                break
        if not event_found:
            endpoint_status = "EVENT_NOT_FOUND"

    policy = EvidenceFreshnessPolicy(
        capability="current_discovery",
        ttl_seconds_pre_match=300,
        ttl_seconds_live=60,
        ttl_seconds_post_final=86400,
        final_state_locks=("STATUS_FULL_TIME", "STATUS_POSTPONED"),
        status_sensitive=True,
    )

    now_str = datetime.datetime.now(datetime.UTC).isoformat()
    if endpoint_status != "ENDPOINT_VERIFIED":
        dt_retrieved = datetime.datetime.now(
            datetime.UTC
        ) - datetime.timedelta(minutes=10)
        retrieved_at = dt_retrieved.isoformat()
    else:
        retrieved_at = now_str

    input_data = EvidenceFreshnessInput(
        profile_id="world-cup-2026",
        capability="current_discovery",
        provider_id="espn-fifa-worldcup",
        provider_event_id="760442",
        scanner_event_id="66456944",
        evidence_retrieved_at=retrieved_at,
        evidence_event_status_state=cached_status_state,
        evidence_event_status_name=cached_status_name,
        current_event_status_state=current_status_state,
        current_event_status_name=current_status_name,
        now_utc=now_str,
    )

    if endpoint_status in ("ENDPOINT_TRANSPORT_ERROR", "EVENT_NOT_FOUND"):
        decision_val = "LIVE_STATUS_UNAVAILABLE_REFRESH_REQUIRED"
        must_refresh = True
        reason = (
            "Upstream endpoint is unavailable or target event not found: "
            f"{error_message or 'EVENT_NOT_FOUND'}"
        )
        stale_reason = "live_status_unavailable"
        decision_obj = EvidenceFreshnessDecision(
            decision=decision_val,
            reason=reason,
            stale_reason=stale_reason,
            must_refresh=must_refresh,
        )
    else:
        decision_obj = evaluate_freshness(policy, input_data)

    return {
        "endpoint_status": endpoint_status,
        "provider_event_id": "760442",
        "cached_status_name": cached_status_name,
        "cached_status_state": cached_status_state,
        "current_status_name": current_status_name,
        "current_status_state": current_status_state,
        "scores": scores,
        "decision": decision_obj.decision,
        "must_refresh": decision_obj.must_refresh,
        "stale_reason": decision_obj.stale_reason,
        "reason": decision_obj.reason,
    }
