from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class IdentitySeed:
    profile_id: str
    fixture_seed_id: str
    canonical_competition_scope: str
    canonical_season_scope: str
    kickoff_local: str
    kickoff_utc: str
    home_team_name: str
    home_team_code: str
    away_team_name: str
    away_team_code: str
    group_label: str | None = None


@dataclass(frozen=True)
class ProviderEventIdentity:
    profile_id: str
    provider_id: str
    provider_event_id: str
    kickoff_utc: str
    kickoff_local: str
    home_team_name: str
    home_team_code: str
    away_team_name: str
    away_team_code: str
    canonical_competition_scope: str = ""
    canonical_season_scope: str = ""
    group_label: str | None = None
    evidence_identity: str = ""
    status_name: str | None = None
    status_state: str | None = None


@dataclass(frozen=True)
class IdentityMatchResult:
    profile_id: str
    identity_status: str
    canonical_competition_scope: str
    canonical_season_scope: str
    scanner_event_id: str | None = None
    matched_provider_ids: tuple[str, ...] = ()
    matched_provider_events: tuple[Mapping[str, Any], ...] = ()
    mismatch_reasons: tuple[str, ...] = ()
    time_tolerance_seconds: int = 18000
    name_normalization_notes: tuple[str, ...] = ()
    timezone_conversion_notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["matched_provider_ids"] = list(self.matched_provider_ids)
        payload["matched_provider_events"] = list(self.matched_provider_events)
        payload["mismatch_reasons"] = list(self.mismatch_reasons)
        payload["name_normalization_notes"] = list(self.name_normalization_notes)
        payload["timezone_conversion_notes"] = list(self.timezone_conversion_notes)
        return payload


def normalize_team_name(name: str) -> str:
    """Strict trimmed, lowercased name normalization for robust football team matching."""
    s = name.strip().lower()
    # Replace common abbreviations & noise
    s = re.sub(
        r"\b(fc|sc|afc|ud|cd|united|utd|athletic|club|de|la|sports|city|usa|aus|sco|mar|bra|hai|tur|par|sui|can)\b",
        "",
        s,
    )
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def parse_datetime_flexible(dt_str: str) -> datetime:
    """Parse iso format datetimes gracefully."""
    s = dt_str.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(s)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def match_identities(
    seed: IdentitySeed,
    providers: list[ProviderEventIdentity],
    time_tolerance_seconds: int = 18000,
) -> IdentityMatchResult:
    """Match providers by normalized team names, reconciled scope, and kickoff tolerance."""
    matched_ids: list[str] = []
    matched_provider_events: list[Mapping[str, Any]] = []
    mismatch_reasons: list[str] = []
    notes: list[str] = []
    timezone_notes: list[str] = []

    seed_home_norm = normalize_team_name(seed.home_team_name)
    seed_away_norm = normalize_team_name(seed.away_team_name)
    seed_home_code = seed.home_team_code.strip().lower() if seed.home_team_code else ""
    seed_away_code = seed.away_team_code.strip().lower() if seed.away_team_code else ""

    try:
        seed_kickoff = parse_datetime_flexible(seed.kickoff_utc)
    except Exception as exc:
        return IdentityMatchResult(
            profile_id=seed.profile_id,
            identity_status="IDENTITY_INSUFFICIENT_EVIDENCE",
            canonical_competition_scope=seed.canonical_competition_scope,
            canonical_season_scope=seed.canonical_season_scope,
            scanner_event_id=seed.fixture_seed_id,
            mismatch_reasons=(f"Failed to parse seed kickoff_utc: {exc}",),
        )
    timezone_notes.append(
        f"seed kickoff_local {seed.kickoff_local} normalized to kickoff_utc {seed_kickoff.isoformat()}"
    )

    for p in providers:
        if (
            p.canonical_competition_scope
            and p.canonical_competition_scope != seed.canonical_competition_scope
        ):
            mismatch_reasons.append(
                f"Provider {p.provider_id} scope mismatch: {p.canonical_competition_scope} != {seed.canonical_competition_scope}."
            )
            continue
        if (
            p.canonical_season_scope
            and p.canonical_season_scope != seed.canonical_season_scope
        ):
            mismatch_reasons.append(
                f"Provider {p.provider_id} season mismatch: {p.canonical_season_scope} != {seed.canonical_season_scope}."
            )
            continue

        try:
            p_kickoff = parse_datetime_flexible(p.kickoff_utc)
            delta = abs((seed_kickoff - p_kickoff).total_seconds())
            timezone_notes.append(
                f"provider {p.provider_id} kickoff_local {p.kickoff_local} normalized to kickoff_utc {p_kickoff.isoformat()}"
            )
            if delta > time_tolerance_seconds:
                mismatch_reasons.append(
                    f"Provider {p.provider_id} kickoff delta {delta}s exceeds tolerance {time_tolerance_seconds}s."
                )
                continue
        except Exception as exc:
            mismatch_reasons.append(
                f"Provider {p.provider_id} invalid kickoff format: {exc}."
            )
            continue

        # Match home/away teams
        p_home_norm = normalize_team_name(p.home_team_name)
        p_away_norm = normalize_team_name(p.away_team_name)
        p_home_code = p.home_team_code.strip().lower() if p.home_team_code else ""
        p_away_code = p.away_team_code.strip().lower() if p.away_team_code else ""

        home_matches = (
            seed_home_norm == p_home_norm
            or (seed_home_code == p_home_code)
            or (seed_home_code == p_home_norm)
            or (seed_home_norm == p_home_code)
        )
        away_matches = (
            seed_away_norm == p_away_norm
            or (seed_away_code == p_away_code)
            or (seed_away_code == p_away_norm)
            or (seed_away_norm == p_away_code)
        )

        if home_matches and away_matches:
            matched_ids.append(p.provider_id)
            matched_provider_events.append(
                {
                    "provider_id": p.provider_id,
                    "provider_event_id": p.provider_event_id,
                    "kickoff_utc": p.kickoff_utc,
                    "kickoff_local": p.kickoff_local,
                    "status_name": p.status_name,
                    "status_state": p.status_state,
                    "evidence_identity": p.evidence_identity,
                }
            )
            notes.append(
                f"Normalized home/away matched: {p.home_team_name} vs {p.away_team_name} for {p.provider_id}."
            )
        else:
            mismatch_reasons.append(
                f"Provider {p.provider_id} home/away match failure: {p.home_team_name} ({p.home_team_code}) "
                f"vs {p.away_team_name} ({p.away_team_code}) against seed {seed.home_team_name} vs {seed.away_team_name}"
            )

    if not providers:
        status = "IDENTITY_INSUFFICIENT_EVIDENCE"
    elif len(matched_ids) == len(providers):
        status = "IDENTITY_CONFIRMED"
    elif matched_ids:
        status = "IDENTITY_PARTIAL"
    else:
        status = "IDENTITY_MISMATCH"

    return IdentityMatchResult(
        profile_id=seed.profile_id,
        identity_status=status,
        canonical_competition_scope=seed.canonical_competition_scope,
        canonical_season_scope=seed.canonical_season_scope,
        scanner_event_id=seed.fixture_seed_id,
        matched_provider_ids=tuple(matched_ids),
        matched_provider_events=tuple(matched_provider_events),
        mismatch_reasons=tuple(mismatch_reasons),
        time_tolerance_seconds=time_tolerance_seconds,
        name_normalization_notes=tuple(notes),
        timezone_conversion_notes=tuple(timezone_notes),
    )
