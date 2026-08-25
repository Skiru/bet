"""Provider Event Revalidation Registry and Service for BET V5/V8 (C4).

Primary exact-ID lookup with controlled, strict fallback policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from bet.pipeline.event_runtime_contract import (
    ProviderRequestStatus,
    CanonicalEventStatus,
    ProviderObservationRecord,
    normalize_provider_status,
    build_participant_identity,
    parse_utc_timestamp,
)
from bet.utils.common import normalize_for_matching


# Provider Alias Registry
PROVIDER_ALIASES: dict[str, str] = {
    "api-football": "api_football",
    "api_football": "api_football",
    "odds-api": "odds_api",
    "odds_api": "odds_api",
    "odds-api-io": "odds_api_io",
    "odds_api_io": "odds_api_io",
    "api-basketball": "api_basketball",
    "api_basketball": "api_basketball",
    "api-volleyball": "api_volleyball",
    "api_volleyball": "api_volleyball",
    "api-hockey": "api_hockey",
    "api_hockey": "api_hockey",
    "espn": "espn",
    "football-data-org": "football_data_org",
    "football_data_org": "football_data_org",
}


def normalize_provider_alias(raw_alias: str) -> str:
    """Normalize provider alias to canonical provider name."""
    norm = raw_alias.strip().lower()
    return PROVIDER_ALIASES.get(norm, norm.replace("-", "_"))


@dataclass
class ProviderRevalidationResult:
    provider: str
    provider_event_id: str | None
    request_status: ProviderRequestStatus
    raw_provider_status: str | None = None
    canonical_event_status: CanonicalEventStatus = CanonicalEventStatus.UNKNOWN
    raw_observed_kickoff: str | None = None
    observed_kickoff_utc: datetime | str | None = None
    observed_home_name: str | None = None
    observed_away_name: str | None = None
    participant_identity_sha256: str | None = None
    competition_identity_sha256: str | None = None
    upstream_evidence_bundle_id: str | None = None
    upstream_evidence_refs: list[str] | None = None
    error_code: str | None = None
    error_detail: str | None = None

    @property
    def is_exact_match(self) -> bool:
        return self.request_status == ProviderRequestStatus.SUCCESS and bool(
            self.provider_event_id
        )


class ProviderEventRevalidationService:
    """Service for exact-ID provider event revalidation and strict fallback."""

    def revalidate_exact_event(
        self,
        provider: str,
        provider_event_id: str,
        available_events: list[dict[str, Any]],
        expected_home: str | None = None,
        expected_away: str | None = None,
        allow_fallback: bool = False,
    ) -> ProviderRevalidationResult:
        canon_provider = normalize_provider_alias(provider)
        target_id = str(provider_event_id).strip()

        exact_matches = []
        for evt in available_events:
            evt_provider = normalize_provider_alias(
                evt.get("provider") or evt.get("source") or ""
            )
            evt_id = str(
                evt.get("provider_event_id") or evt.get("external_id") or ""
            ).strip()
            if evt_provider == canon_provider and evt_id == target_id:
                exact_matches.append(evt)

        if len(exact_matches) == 1:
            match = exact_matches[0]
            raw_status = match.get("status") or match.get("raw_status")
            raw_kickoff = match.get("kickoff") or match.get("raw_kickoff")
            home = match.get("home") or match.get("home_team")
            away = match.get("away") or match.get("away_team")

            kickoff_dt = None
            if raw_kickoff:
                try:
                    kickoff_dt = parse_utc_timestamp(raw_kickoff)
                except Exception:
                    kickoff_dt = None

            c_status = normalize_provider_status(
                raw_status, observed_kickoff_utc=kickoff_dt
            )

            part_sha = None
            if home and away:
                part_sha = build_participant_identity(home, away).identity_sha256

            return ProviderRevalidationResult(
                provider=canon_provider,
                provider_event_id=target_id,
                request_status=ProviderRequestStatus.SUCCESS,
                raw_provider_status=raw_status,
                canonical_event_status=c_status,
                raw_observed_kickoff=str(raw_kickoff) if raw_kickoff else None,
                observed_kickoff_utc=kickoff_dt.isoformat() if kickoff_dt else None,
                observed_home_name=home,
                observed_away_name=away,
                participant_identity_sha256=part_sha,
                competition_identity_sha256=match.get("competition_identity_sha256"),
            )

        if len(exact_matches) > 1:
            return ProviderRevalidationResult(
                provider=canon_provider,
                provider_event_id=target_id,
                request_status=ProviderRequestStatus.IDENTITY_CONFLICT,
                error_code="MULTIPLE_EXACT_IDS",
                error_detail=f"Found {len(exact_matches)} events with exact provider_event_id {target_id}",
            )

        if not allow_fallback or not (expected_home and expected_away):
            return ProviderRevalidationResult(
                provider=canon_provider,
                provider_event_id=target_id,
                request_status=ProviderRequestStatus.IDENTITY_MISSING,
                error_code="EXACT_ID_NOT_FOUND",
                error_detail=f"No event found with exact provider_event_id {target_id}",
            )

        # Strict fallback
        return self.revalidate_fallback(
            provider=canon_provider,
            expected_home=expected_home,
            expected_away=expected_away,
            expected_kickoff_utc=None,
            available_events=available_events,
        )

    def revalidate_fallback(
        self,
        provider: str,
        expected_home: str,
        expected_away: str,
        expected_kickoff_utc: datetime | str | None,
        available_events: list[dict[str, Any]],
        tolerance_minutes: int = 5,
    ) -> ProviderRevalidationResult:
        canon_provider = normalize_provider_alias(provider)
        exp_home_norm = normalize_for_matching(expected_home)
        exp_away_norm = normalize_for_matching(expected_away)

        exp_dt = (
            parse_utc_timestamp(expected_kickoff_utc) if expected_kickoff_utc else None
        )

        candidates = []
        reversed_matches = []

        for evt in available_events:
            evt_provider = normalize_provider_alias(
                evt.get("provider") or evt.get("source") or ""
            )
            if evt_provider != canon_provider:
                continue

            home = evt.get("home") or evt.get("home_team") or ""
            away = evt.get("away") or evt.get("away_team") or ""
            home_norm = normalize_for_matching(home)
            away_norm = normalize_for_matching(away)

            # Check reversed home/away
            if home_norm == exp_away_norm and away_norm == exp_home_norm:
                reversed_matches.append(evt)
                continue

            if home_norm != exp_home_norm or away_norm != exp_away_norm:
                continue

            # Kickoff tolerance check
            if exp_dt:
                raw_k = evt.get("kickoff") or evt.get("raw_kickoff")
                if raw_k:
                    try:
                        k_dt = parse_utc_timestamp(raw_k)
                        if abs((k_dt - exp_dt).total_seconds()) > (
                            tolerance_minutes * 60
                        ):
                            continue
                    except Exception:
                        continue

            candidates.append(evt)

        if reversed_matches and not candidates:
            return ProviderRevalidationResult(
                provider=canon_provider,
                provider_event_id=None,
                request_status=ProviderRequestStatus.IDENTITY_CONFLICT,
                error_code="HOME_AWAY_REVERSED",
                error_detail="Home and away participants are reversed",
            )

        if len(candidates) == 1:
            match = candidates[0]
            target_id = str(
                match.get("provider_event_id") or match.get("external_id") or ""
            )
            raw_status = match.get("status") or match.get("raw_status")
            raw_kickoff = match.get("kickoff") or match.get("raw_kickoff")
            home = match.get("home") or match.get("home_team")
            away = match.get("away") or match.get("away_team")

            kickoff_dt = None
            if raw_kickoff:
                try:
                    kickoff_dt = parse_utc_timestamp(raw_kickoff)
                except Exception:
                    kickoff_dt = None

            c_status = normalize_provider_status(
                raw_status, observed_kickoff_utc=kickoff_dt
            )
            part_sha = (
                build_participant_identity(home, away).identity_sha256
                if (home and away)
                else None
            )

            return ProviderRevalidationResult(
                provider=canon_provider,
                provider_event_id=target_id if target_id else None,
                request_status=ProviderRequestStatus.SUCCESS,
                raw_provider_status=raw_status,
                canonical_event_status=c_status,
                raw_observed_kickoff=str(raw_kickoff) if raw_kickoff else None,
                observed_kickoff_utc=kickoff_dt.isoformat() if kickoff_dt else None,
                observed_home_name=home,
                observed_away_name=away,
                participant_identity_sha256=part_sha,
                competition_identity_sha256=match.get("competition_identity_sha256"),
            )

        if len(candidates) > 1:
            return ProviderRevalidationResult(
                provider=canon_provider,
                provider_event_id=None,
                request_status=ProviderRequestStatus.IDENTITY_CONFLICT,
                error_code="AMBIGUOUS_FALLBACK_CANDIDATES",
                error_detail=f"Found {len(candidates)} candidates matching participant identity in fallback",
            )

        return ProviderRevalidationResult(
            provider=canon_provider,
            provider_event_id=None,
            request_status=ProviderRequestStatus.IDENTITY_MISSING,
            error_code="NO_FALLBACK_CANDIDATES",
            error_detail="No candidates found matching participant identity in fallback",
        )

    def build_observation_record(
        self,
        db_row: dict[str, Any],
        provider_response: dict[str, Any],
        attempted_at_utc: datetime | str | None = None,
        provider_name: str = "api_football",
    ) -> ProviderObservationRecord:
        if attempted_at_utc is None:
            attempted_at_dt = datetime.now(UTC)
        else:
            attempted_at_dt = parse_utc_timestamp(attempted_at_utc)

        raw_status = provider_response.get("status") or provider_response.get(
            "raw_status"
        )
        raw_kickoff = provider_response.get("kickoff") or provider_response.get(
            "raw_kickoff"
        )

        observed_kickoff_dt = None
        if raw_kickoff:
            try:
                observed_kickoff_dt = parse_utc_timestamp(raw_kickoff)
            except Exception:
                observed_kickoff_dt = None

        canonical_status = normalize_provider_status(
            raw_status,
            provider=provider_name,
            observed_kickoff_utc=observed_kickoff_dt,
            observed_at_utc=attempted_at_dt,
        )

        home_name = provider_response.get("home") or provider_response.get("home_team")
        away_name = provider_response.get("away") or provider_response.get("away_team")

        part_sha = None
        if home_name and away_name:
            part_sha = build_participant_identity(home_name, away_name).identity_sha256

        provider_evt_id = provider_response.get(
            "provider_event_id"
        ) or provider_response.get("external_id")

        return ProviderObservationRecord(
            canonical_event_id=str(
                db_row.get("canonical_event_id") or db_row.get("fixture_id") or ""
            ),
            fixture_id=db_row.get("fixture_id"),
            provider=provider_name,
            provider_event_id=provider_evt_id,
            attempted_at_utc=attempted_at_dt.isoformat(),
            request_status=ProviderRequestStatus.SUCCESS,
            raw_provider_status=raw_status,
            canonical_event_status=canonical_status,
            raw_observed_kickoff=str(raw_kickoff) if raw_kickoff else None,
            observed_kickoff_utc=observed_kickoff_dt.isoformat()
            if observed_kickoff_dt
            else None,
            observed_home_name=home_name,
            observed_away_name=away_name,
            participant_identity_sha256=part_sha,
            competition_identity_sha256=provider_response.get(
                "competition_identity_sha256"
            ),
            upstream_evidence_bundle_id=provider_response.get(
                "upstream_evidence_bundle_id"
            ),
            upstream_evidence_refs_json=provider_response.get(
                "upstream_evidence_refs_json"
            ),
            observation_envelope_sha256=provider_response.get(
                "observation_envelope_sha256"
            ),
            evidence_path=provider_response.get("evidence_path"),
        )
