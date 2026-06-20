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
    evidence_event_status_name: str  # e.g., "STATUS_SCHEDULED", "STATUS_FIRST_HALF", etc.
    current_event_status_state: str | None
    current_event_status_name: str | None
    now_utc: str  # ISO timestamp


@dataclass(frozen=True)
class EvidenceFreshnessDecision:
    decision: str
    reason: str
    stale_reason: str | None = None
    must_refresh: bool = False


def _parse_iso(dt_str: str) -> datetime.datetime:
    """Parse ISO timestamp with timezone support."""
    s = dt_str.replace("Z", "+00:00")
    return datetime.datetime.fromisoformat(s)


def evaluate_freshness(
    policy: EvidenceFreshnessPolicy, input_data: EvidenceFreshnessInput
) -> EvidenceFreshnessDecision:
    """Evaluate freshness of cached evidence against policy and current live status."""
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
        age_seconds = (
            _parse_iso(input_data.now_utc)
            - _parse_iso(input_data.evidence_retrieved_at)
        ).total_seconds()
    except Exception as e:
        return EvidenceFreshnessDecision(
            decision="STALE_REFRESH_REQUIRED",
            reason=f"Timestamp parsing failed: {e}",
            stale_reason="timestamp_parse_error",
            must_refresh=True,
        )

    # 1. Live status unavailable
    if (
        input_data.current_event_status_name is None
        or input_data.current_event_status_state is None
    ):
        is_cached_final = (
            input_data.evidence_event_status_state == "post"
            or input_data.evidence_event_status_name in policy.final_state_locks
        )
        if is_cached_final:
            return EvidenceFreshnessDecision(
                decision="FINAL_LOCKED_REUSABLE",
                reason="Final state is locked and immutable (live scoreboard unavailable)",
                must_refresh=False,
            )

        if policy.status_sensitive:
            ttl = policy.ttl_seconds_pre_match
            if input_data.evidence_event_status_state == "in":
                ttl = policy.ttl_seconds_live
            elif input_data.evidence_event_status_state == "post":
                ttl = policy.ttl_seconds_post_final

            if age_seconds > ttl:
                return EvidenceFreshnessDecision(
                    decision="LIVE_STATUS_UNAVAILABLE_REFRESH_REQUIRED",
                    reason="Live status check is unavailable and cached status-sensitive evidence is stale",
                    stale_reason="live_status_unavailable_and_stale",
                    must_refresh=True,
                )

        return EvidenceFreshnessDecision(
            decision="FRESH_REUSABLE",
            reason="Live status is unavailable but cached evidence is within TTL",
            must_refresh=False,
        )

    # 2. Check for drift (live scoreboard is available)
    has_status_drift = (
        input_data.evidence_event_status_name != input_data.current_event_status_name
        or input_data.evidence_event_status_state != input_data.current_event_status_state
    )

    if has_status_drift:
        return EvidenceFreshnessDecision(
            decision="STATUS_DRIFT_REFRESH_REQUIRED",
            reason=(
                f"Status drifted from {input_data.evidence_event_status_name}/"
                f"{input_data.evidence_event_status_state} to "
                f"{input_data.current_event_status_name}/{input_data.current_event_status_state}"
            ),
            stale_reason="status_drift",
            must_refresh=True,
        )

    # 3. Final state is locked
    is_final = (
        input_data.current_event_status_state == "post"
        or input_data.current_event_status_name in policy.final_state_locks
    )
    if is_final:
        return EvidenceFreshnessDecision(
            decision="FINAL_LOCKED_REUSABLE",
            reason="Final state matches current state and is locked",
            must_refresh=False,
        )

    # 4. Check TTL
    ttl = policy.ttl_seconds_pre_match
    if input_data.evidence_event_status_state == "in":
        ttl = policy.ttl_seconds_live
    elif input_data.evidence_event_status_state == "post":
        ttl = policy.ttl_seconds_post_final

    if age_seconds > ttl:
        return EvidenceFreshnessDecision(
            decision="STALE_REFRESH_REQUIRED",
            reason=f"TTL expired: age {age_seconds}s exceeds limit {ttl}s",
            stale_reason="ttl_expired",
            must_refresh=True,
        )

    return EvidenceFreshnessDecision(
        decision="FRESH_REUSABLE",
        reason="Within TTL and status matches",
        must_refresh=False,
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
        url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
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
                    current_status_name = status_dict.get("type", {}).get("name")
                    current_status_state = status_dict.get("type", {}).get("state")

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
    # Set retrieved_at to 10 minutes ago if the live check is unavailable
    if endpoint_status != "ENDPOINT_VERIFIED":
        dt_retrieved = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=10)
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
        reason = f"Upstream endpoint is unavailable or target event not found: {error_message or 'EVENT_NOT_FOUND'}"
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
