from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
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
    group_label: str | None = None
    evidence_identity: str = ""


@dataclass(frozen=True)
class IdentityMatchResult:
    profile_id: str
    identity_status: str
    canonical_competition_scope: str
    canonical_season_scope: str
    scanner_event_id: str | None = None
    matched_provider_ids: tuple[str, ...] = ()
    mismatch_reasons: tuple[str, ...] = ()
    time_tolerance_seconds: int = 18000
    name_normalization_notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["matched_provider_ids"] = list(self.matched_provider_ids)
        payload["mismatch_reasons"] = list(self.mismatch_reasons)
        payload["name_normalization_notes"] = list(self.name_normalization_notes)
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
    # Strip any trailing 'Z' or offset if needed, but let's try standard isoformat
    s = dt_str.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def match_identities(
    seed: IdentitySeed,
    providers: list[ProviderEventIdentity],
    time_tolerance_seconds: int = 18000,
) -> IdentityMatchResult:
    """Identity matching engine using flexible fuzzy team name and kickoff window comparison."""
    matched_ids = []
    mismatch_reasons = []
    notes = []

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

    for p in providers:
        # Check kickoff window
        try:
            p_kickoff = parse_datetime_flexible(p.kickoff_utc)
            delta = abs((seed_kickoff - p_kickoff).total_seconds())
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
            (seed_home_norm in p_home_norm)
            or (p_home_norm in seed_home_norm)
            or (seed_home_code == p_home_code)
            or (seed_home_code == p_home_norm)
            or (seed_home_norm == p_home_code)
        )
        away_matches = (
            (seed_away_norm in p_away_norm)
            or (p_away_norm in seed_away_norm)
            or (seed_away_code == p_away_code)
            or (seed_away_code == p_away_norm)
            or (seed_away_norm == p_away_code)
        )

        if home_matches and away_matches:
            matched_ids.append(p.provider_id)
            notes.append(
                f"Fuzzy home/away matched: {p.home_team_name} vs {p.away_team_name} for {p.provider_id}"
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
        mismatch_reasons=tuple(mismatch_reasons),
        time_tolerance_seconds=time_tolerance_seconds,
        name_normalization_notes=tuple(notes),
    )
