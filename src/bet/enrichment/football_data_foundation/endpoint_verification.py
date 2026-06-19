from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from .fingerprints import compute_schema_fingerprint
from .scanner_contracts import ScannerEventCandidate


@dataclass(frozen=True)
class EndpointVerificationRequest:
    profile_id: str
    provider_id: str
    endpoint_url: str
    canonical_competition_scope: str
    canonical_season_scope: str
    scanner_event_candidate: ScannerEventCandidate | None = None
    max_calls: int = 2
    timeout_seconds: int = 20
    store_raw_payload: bool = False
    expected_shape: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EndpointEventSummary:
    provider_event_id: str
    event_date_utc: str
    event_date_local: str
    name: str
    short_name: str
    home_team_name: str
    home_team_code: str
    away_team_name: str
    away_team_code: str
    status_name: str
    status_state: str
    completed: bool
    group_label: str | None = None
    venue_name: str | None = None
    venue_city: str | None = None
    venue_country: str | None = None
    broadcasts: tuple[str, ...] = ()
    team_records: tuple[Mapping[str, Any], ...] = ()
    leaders_summary: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["broadcasts"] = list(self.broadcasts)
        payload["team_records"] = list(self.team_records)
        payload["leaders_summary"] = list(self.leaders_summary)
        return payload


@dataclass(frozen=True)
class EndpointVerificationResult:
    profile_id: str
    provider_id: str
    endpoint_url: str
    canonical_competition_scope: str
    canonical_season_scope: str
    event_count: int
    schema_fingerprint: str
    evidence_identity: str
    status: str
    diagnostics: Mapping[str, Any]
    events: tuple[EndpointEventSummary, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "provider_id": self.provider_id,
            "endpoint_url": self.endpoint_url,
            "canonical_competition_scope": self.canonical_competition_scope,
            "canonical_season_scope": self.canonical_season_scope,
            "event_count": self.event_count,
            "schema_fingerprint": self.schema_fingerprint,
            "evidence_identity": self.evidence_identity,
            "status": self.status,
            "diagnostics": dict(self.diagnostics),
            "events": [e.to_dict() for e in self.events],
        }


def parse_espn_scoreboard_payload(
    payload_dict: dict[str, Any],
    scanner_candidate: ScannerEventCandidate | None = None,
) -> list[EndpointEventSummary]:
    """Parse a site.api.espn.com scoreboard payload into normalized event summaries."""
    summaries = []
    events_list = payload_dict.get("events") or []

    for ev in events_list:
        p_id = str(ev.get("id", ""))
        date_raw = ev.get("date", "")
        name = str(ev.get("name", ""))
        short_name = str(ev.get("shortName", ""))

        competitions = ev.get("competitions") or []
        if not competitions:
            continue
        comp = competitions[0]

        status_dict = comp.get("status") or {}
        status_name = str(status_dict.get("type", {}).get("name", "STATUS_UNKNOWN"))
        status_state = str(status_dict.get("type", {}).get("state", "pre"))
        completed = bool(status_dict.get("type", {}).get("completed", False))

        # Competitors (home/away)
        competitors = comp.get("competitors") or []
        home_team_name, home_team_code = "", ""
        away_team_name, away_team_code = "", ""
        team_records: list[Mapping[str, Any]] = []

        for competitor in competitors:
            team_dict = competitor.get("team") or {}
            c_name = str(team_dict.get("name", ""))
            c_code = str(team_dict.get("abbreviation", ""))
            role = str(competitor.get("homeAway", ""))

            if role == "home":
                home_team_name = c_name
                home_team_code = c_code
            elif role == "away":
                away_team_name = c_name
                away_team_code = c_code

            # Extract records if present
            recs = competitor.get("records") or []
            if recs:
                team_records.append(
                    {
                        "team_name": c_name,
                        "records": recs,
                    }
                )

        # Venue
        venue_dict = comp.get("venue") or {}
        venue_name = venue_dict.get("fullName")
        venue_city = venue_dict.get("address", {}).get("city")
        venue_country = venue_dict.get("address", {}).get("country")

        # Broadcasts
        broadcasts_list = comp.get("broadcasts") or []
        broadcasts = []
        for b in broadcasts_list:
            names = b.get("names") or []
            broadcasts.extend(names)

        # Leaders (example leaders mapping extraction)
        leaders_list = comp.get("leaders") or []
        leaders_summary: list[Mapping[str, Any]] = []
        for leader in leaders_list:
            display_name = leader.get("displayName")
            leaders_summary.append(
                {
                    "category": display_name,
                    "leaders": leader.get("leaders", []),
                }
            )

        summary = EndpointEventSummary(
            provider_event_id=p_id,
            event_date_utc=date_raw,
            event_date_local=date_raw,  # simplest representation
            name=name,
            short_name=short_name,
            home_team_name=home_team_name,
            home_team_code=home_team_code,
            away_team_name=away_team_name,
            away_team_code=away_team_code,
            status_name=status_name,
            status_state=status_state,
            completed=completed,
            venue_name=venue_name,
            venue_city=venue_city,
            venue_country=venue_country,
            broadcasts=tuple(broadcasts),
            team_records=tuple(team_records),
            leaders_summary=tuple(leaders_summary),
        )

        summaries.append(summary)

    # Optional scanner filter/matching logic
    if scanner_candidate is not None:
        filtered = []
        for s in summaries:
            # We match if either teams match or event date is identical
            if (
                s.home_team_code == scanner_candidate.home_team_code
                or s.home_team_name == scanner_candidate.home_team_name
            ):
                filtered.append(s)
            elif (
                s.away_team_code == scanner_candidate.away_team_code
                or s.away_team_name == scanner_candidate.away_team_name
            ):
                filtered.append(s)
        if filtered:
            return filtered

    return summaries


def verify_endpoint(
    request: EndpointVerificationRequest,
    mock_payload: dict[str, Any] | None = None,
) -> EndpointVerificationResult:
    """Execute generic endpoint verification with strict shape validation and robust exception mapping."""
    diagnostics = {
        "max_calls": request.max_calls,
        "timeout_seconds": request.timeout_seconds,
        "store_raw_payload": request.store_raw_payload,
    }

    if mock_payload is not None:
        try:
            events = parse_espn_scoreboard_payload(
                mock_payload, request.scanner_event_candidate
            )
            serialized = json.dumps(mock_payload, sort_keys=True, separators=(",", ":"))
            schema_fingerprint = compute_schema_fingerprint(mock_payload)
            evidence_identity = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

            # Schema validation check: verify expected keys in expected_shape are present
            for k in request.expected_shape:
                if k not in mock_payload:
                    raise KeyError(
                        f"Expected key '{k}' missing from endpoint payload structure."
                    )

            return EndpointVerificationResult(
                profile_id=request.profile_id,
                provider_id=request.provider_id,
                endpoint_url=request.endpoint_url,
                canonical_competition_scope=request.canonical_competition_scope,
                canonical_season_scope=request.canonical_season_scope,
                event_count=len(events),
                schema_fingerprint=schema_fingerprint,
                evidence_identity=evidence_identity,
                status="ENDPOINT_VERIFIED",
                diagnostics=diagnostics,
                events=tuple(events),
            )
        except KeyError as exc:
            return EndpointVerificationResult(
                profile_id=request.profile_id,
                provider_id=request.provider_id,
                endpoint_url=request.endpoint_url,
                canonical_competition_scope=request.canonical_competition_scope,
                canonical_season_scope=request.canonical_season_scope,
                event_count=0,
                schema_fingerprint="",
                evidence_identity="",
                status="ENDPOINT_SCHEMA_ERROR",
                diagnostics={"error": str(exc), "exception_type": "KeyError"},
            )
        except Exception as exc:
            return EndpointVerificationResult(
                profile_id=request.profile_id,
                provider_id=request.provider_id,
                endpoint_url=request.endpoint_url,
                canonical_competition_scope=request.canonical_competition_scope,
                canonical_season_scope=request.canonical_season_scope,
                event_count=0,
                schema_fingerprint="",
                evidence_identity="",
                status="ENDPOINT_SCHEMA_ERROR",
                diagnostics={"error": str(exc), "exception_type": type(exc).__name__},
            )

    # Live verification flow
    try:
        req = urllib.request.Request(
            request.endpoint_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=request.timeout_seconds) as response:
            status_code = response.getcode()
            if status_code == 429:
                return EndpointVerificationResult(
                    profile_id=request.profile_id,
                    provider_id=request.provider_id,
                    endpoint_url=request.endpoint_url,
                    canonical_competition_scope=request.canonical_competition_scope,
                    canonical_season_scope=request.canonical_season_scope,
                    event_count=0,
                    schema_fingerprint="",
                    evidence_identity="",
                    status="ENDPOINT_RATE_LIMITED",
                    diagnostics={"status_code": 429},
                )
            if status_code == 403:
                return EndpointVerificationResult(
                    profile_id=request.profile_id,
                    provider_id=request.provider_id,
                    endpoint_url=request.endpoint_url,
                    canonical_competition_scope=request.canonical_competition_scope,
                    canonical_season_scope=request.canonical_season_scope,
                    event_count=0,
                    schema_fingerprint="",
                    evidence_identity="",
                    status="ENDPOINT_BLOCKED",
                    diagnostics={"status_code": 403},
                )

            raw_bytes = response.read()
            payload = json.loads(raw_bytes.decode("utf-8"))

            events = parse_espn_scoreboard_payload(
                payload, request.scanner_event_candidate
            )
            schema_fingerprint = compute_schema_fingerprint(payload)
            evidence_identity = hashlib.sha256(raw_bytes).hexdigest()

            # Check expected shape keys
            for k in request.expected_shape:
                if k not in payload:
                    raise KeyError(
                        f"Expected key '{k}' missing from live endpoint payload."
                    )

            status = "ENDPOINT_VERIFIED" if events else "ENDPOINT_VALID_EMPTY"

            return EndpointVerificationResult(
                profile_id=request.profile_id,
                provider_id=request.provider_id,
                endpoint_url=request.endpoint_url,
                canonical_competition_scope=request.canonical_competition_scope,
                canonical_season_scope=request.canonical_season_scope,
                event_count=len(events),
                schema_fingerprint=schema_fingerprint,
                evidence_identity=evidence_identity,
                status=status,
                diagnostics=diagnostics,
                events=tuple(events),
            )
    except urllib.error.HTTPError as exc:
        code = exc.code
        status = "ENDPOINT_TRANSPORT_ERROR"
        if code == 429:
            status = "ENDPOINT_RATE_LIMITED"
        elif code in (401, 403):
            status = "ENDPOINT_BLOCKED"
        return EndpointVerificationResult(
            profile_id=request.profile_id,
            provider_id=request.provider_id,
            endpoint_url=request.endpoint_url,
            canonical_competition_scope=request.canonical_competition_scope,
            canonical_season_scope=request.canonical_season_scope,
            event_count=0,
            schema_fingerprint="",
            evidence_identity="",
            status=status,
            diagnostics={"error": str(exc), "http_status_code": code},
        )
    except urllib.error.URLError as exc:
        return EndpointVerificationResult(
            profile_id=request.profile_id,
            provider_id=request.provider_id,
            endpoint_url=request.endpoint_url,
            canonical_competition_scope=request.canonical_competition_scope,
            canonical_season_scope=request.canonical_season_scope,
            event_count=0,
            schema_fingerprint="",
            evidence_identity="",
            status="ENDPOINT_TRANSPORT_ERROR",
            diagnostics={"error": str(exc), "reason": str(exc.reason)},
        )
    except KeyError as exc:
        return EndpointVerificationResult(
            profile_id=request.profile_id,
            provider_id=request.provider_id,
            endpoint_url=request.endpoint_url,
            canonical_competition_scope=request.canonical_competition_scope,
            canonical_season_scope=request.canonical_season_scope,
            event_count=0,
            schema_fingerprint="",
            evidence_identity="",
            status="ENDPOINT_SCHEMA_ERROR",
            diagnostics={"error": str(exc), "exception_type": "KeyError"},
        )
    except Exception as exc:
        return EndpointVerificationResult(
            profile_id=request.profile_id,
            provider_id=request.provider_id,
            endpoint_url=request.endpoint_url,
            canonical_competition_scope=request.canonical_competition_scope,
            canonical_season_scope=request.canonical_season_scope,
            event_count=0,
            schema_fingerprint="",
            evidence_identity="",
            status="ENDPOINT_SCHEMA_ERROR",
            diagnostics={"error": str(exc), "exception_type": type(exc).__name__},
        )
