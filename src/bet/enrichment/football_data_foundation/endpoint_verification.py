from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from .event_identity import normalize_team_name, parse_datetime_flexible
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
    scanner_event_id: str | None
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
    score_home: int | None = None
    score_away: int | None = None
    broadcasts: tuple[str, ...] = ()
    team_records: tuple[Mapping[str, Any], ...] = ()
    statistics: tuple[Mapping[str, Any], ...] = ()
    leaders_summary: tuple[Mapping[str, Any], ...] = ()
    retrieval_timestamp_utc: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["broadcasts"] = list(self.broadcasts)
        payload["team_records"] = list(self.team_records)
        payload["statistics"] = list(self.statistics)
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
    retrieval_timestamp_utc: str
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
            "retrieval_timestamp_utc": self.retrieval_timestamp_utc,
            "status": self.status,
            "diagnostics": dict(self.diagnostics),
            "events": [e.to_dict() for e in self.events],
        }


_EVIDENCE_IDENTITY_RE = re.compile(r"^[a-f0-9]{64}$")


def validate_evidence_identity(evidence_identity: str) -> str:
    candidate = evidence_identity.strip()
    if not _EVIDENCE_IDENTITY_RE.fullmatch(candidate):
        raise ValueError(
            "evidence_identity must be a contiguous lowercase sha256 fingerprint with no spaces."
        )
    return candidate


def _normalize_metric_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_statistics(competitor: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    statistics = []
    for statistic in competitor.get("statistics") or []:
        stat_name = str(statistic.get("name") or "").strip()
        if not stat_name:
            continue
        display_value = statistic.get("displayValue")
        raw_value = statistic.get("value", display_value)
        entry = {
            "team_name": str(
                (competitor.get("team") or {}).get("displayName")
                or (competitor.get("team") or {}).get("name")
                or ""
            ),
            "team_code": str((competitor.get("team") or {}).get("abbreviation") or ""),
            "home_away": str(competitor.get("homeAway") or ""),
            "name": stat_name,
            "display_value": None
            if display_value in (None, "")
            else str(display_value),
            "value": _normalize_metric_value(raw_value),
        }
        statistics.append(entry)
    return statistics


def _normalize_team_records(competitor: Mapping[str, Any]) -> Mapping[str, Any] | None:
    team = competitor.get("team") or {}
    raw_records = competitor.get("records") or []
    summaries = []
    for record in raw_records:
        summary = record.get("summary")
        if summary in (None, ""):
            continue
        summaries.append(
            {
                "name": str(record.get("name") or "unknown"),
                "summary": str(summary),
            }
        )
    if not summaries:
        return None
    return {
        "team_name": str(team.get("displayName") or team.get("name") or ""),
        "team_code": str(team.get("abbreviation") or ""),
        "records": summaries,
        "team_record_summary": ", ".join(item["summary"] for item in summaries),
    }


def _extract_group_label(
    event: Mapping[str, Any], competition: Mapping[str, Any]
) -> str | None:
    for note in competition.get("notes") or []:
        headline = note.get("headline")
        if headline:
            return str(headline)
    group = competition.get("group") or event.get("group") or {}
    if isinstance(group, Mapping):
        short_name = (
            group.get("shortName") or group.get("displayName") or group.get("name")
        )
        if short_name:
            return str(short_name)
    headline = event.get("groupLabel")
    if headline:
        return str(headline)
    return None


def _matches_scanner_candidate(
    summary: EndpointEventSummary,
    scanner_candidate: ScannerEventCandidate,
) -> bool:
    summary_home = normalize_team_name(summary.home_team_name)
    summary_away = normalize_team_name(summary.away_team_name)
    scanner_home = normalize_team_name(scanner_candidate.home_team_name)
    scanner_away = normalize_team_name(scanner_candidate.away_team_name)
    if summary_home != scanner_home or summary_away != scanner_away:
        return False
    try:
        summary_kickoff = parse_datetime_flexible(summary.event_date_utc)
        scanner_kickoff = parse_datetime_flexible(scanner_candidate.kickoff_utc)
    except Exception:
        return summary.event_date_utc == scanner_candidate.kickoff_utc
    return summary_kickoff == scanner_kickoff


def parse_espn_scoreboard_payload(
    payload_dict: dict[str, Any],
    scanner_candidate: ScannerEventCandidate | None = None,
    retrieval_timestamp_utc: str | None = None,
) -> list[EndpointEventSummary]:
    """Parse a site.api.espn.com scoreboard payload into normalized event summaries."""
    summaries: list[EndpointEventSummary] = []
    events_list = payload_dict.get("events") or []
    retrieved_at = retrieval_timestamp_utc or datetime.now(UTC).isoformat()

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
        score_home, score_away = None, None
        team_records: list[Mapping[str, Any]] = []
        statistics: list[Mapping[str, Any]] = []

        for competitor in competitors:
            team_dict = competitor.get("team") or {}
            c_name = str(team_dict.get("displayName") or team_dict.get("name") or "")
            c_code = str(team_dict.get("abbreviation", ""))
            role = str(competitor.get("homeAway", ""))
            score_value = competitor.get("score")
            parsed_score = None
            if score_value not in (None, ""):
                try:
                    parsed_score = int(str(score_value))
                except ValueError:
                    parsed_score = None

            if role == "home":
                home_team_name = c_name
                home_team_code = c_code
                score_home = parsed_score
            elif role == "away":
                away_team_name = c_name
                away_team_code = c_code
                score_away = parsed_score

            record_summary = _normalize_team_records(competitor)
            if record_summary is not None:
                team_records.append(record_summary)
            statistics.extend(_normalize_statistics(competitor))

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
            scanner_event_id=scanner_candidate.scanner_event_id
            if scanner_candidate
            else None,
            provider_event_id=p_id,
            event_date_utc=date_raw,
            event_date_local=date_raw,
            name=name,
            short_name=short_name,
            home_team_name=home_team_name,
            home_team_code=home_team_code,
            away_team_name=away_team_name,
            away_team_code=away_team_code,
            status_name=status_name,
            status_state=status_state,
            completed=completed,
            group_label=_extract_group_label(ev, comp),
            venue_name=venue_name,
            venue_city=venue_city,
            venue_country=venue_country,
            score_home=score_home,
            score_away=score_away,
            broadcasts=tuple(broadcasts),
            team_records=tuple(team_records),
            statistics=tuple(statistics),
            leaders_summary=tuple(leaders_summary),
            retrieval_timestamp_utc=retrieved_at,
        )

        summaries.append(summary)

    if scanner_candidate is not None:
        filtered = [
            s for s in summaries if _matches_scanner_candidate(s, scanner_candidate)
        ]
        if filtered:
            return filtered

    return summaries


def verify_endpoint(
    request: EndpointVerificationRequest,
    mock_payload: dict[str, Any] | None = None,
) -> EndpointVerificationResult:
    """Execute generic endpoint verification with strict shape validation and robust exception mapping."""
    retrieval_timestamp_utc = datetime.now(UTC).isoformat()
    diagnostics = {
        "max_calls": request.max_calls,
        "timeout_seconds": request.timeout_seconds,
        "store_raw_payload": request.store_raw_payload,
        "no_secrets_cookies_proxy_browser_profiles": (
            "No secrets, cookies, proxy settings, Tor, or browser profiles were used."
        ),
    }

    if mock_payload is not None:
        try:
            all_events = parse_espn_scoreboard_payload(
                mock_payload,
                None,
                retrieval_timestamp_utc=retrieval_timestamp_utc,
            )
            events = parse_espn_scoreboard_payload(
                mock_payload,
                request.scanner_event_candidate,
                retrieval_timestamp_utc=retrieval_timestamp_utc,
            )
            serialized = json.dumps(mock_payload, sort_keys=True, separators=(",", ":"))
            schema_fingerprint = compute_schema_fingerprint(mock_payload)
            evidence_identity = validate_evidence_identity(
                hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            )
            diagnostics = {
                **diagnostics,
                "matched_event_count": len(events),
                "total_event_count": len(all_events),
            }

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
                retrieval_timestamp_utc=retrieval_timestamp_utc,
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
                retrieval_timestamp_utc=retrieval_timestamp_utc,
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
                retrieval_timestamp_utc=retrieval_timestamp_utc,
                status="ENDPOINT_SCHEMA_ERROR",
                diagnostics={"error": str(exc), "exception_type": type(exc).__name__},
            )

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
                    retrieval_timestamp_utc=retrieval_timestamp_utc,
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
                    retrieval_timestamp_utc=retrieval_timestamp_utc,
                    status="ENDPOINT_BLOCKED",
                    diagnostics={"status_code": 403},
                )

            raw_bytes = response.read()
            retrieval_timestamp_utc = datetime.now(UTC).isoformat()
            payload = json.loads(raw_bytes.decode("utf-8"))

            all_events = parse_espn_scoreboard_payload(
                payload,
                None,
                retrieval_timestamp_utc=retrieval_timestamp_utc,
            )
            events = parse_espn_scoreboard_payload(
                payload,
                request.scanner_event_candidate,
                retrieval_timestamp_utc=retrieval_timestamp_utc,
            )
            schema_fingerprint = compute_schema_fingerprint(payload)
            evidence_identity = validate_evidence_identity(
                hashlib.sha256(raw_bytes).hexdigest()
            )
            diagnostics = {
                **diagnostics,
                "http_status_code": status_code,
                "matched_event_count": len(events),
                "total_event_count": len(all_events),
            }

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
                retrieval_timestamp_utc=retrieval_timestamp_utc,
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
            retrieval_timestamp_utc=retrieval_timestamp_utc,
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
            retrieval_timestamp_utc=retrieval_timestamp_utc,
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
            retrieval_timestamp_utc=retrieval_timestamp_utc,
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
            retrieval_timestamp_utc=retrieval_timestamp_utc,
            status="ENDPOINT_SCHEMA_ERROR",
            diagnostics={"error": str(exc), "exception_type": type(exc).__name__},
        )
