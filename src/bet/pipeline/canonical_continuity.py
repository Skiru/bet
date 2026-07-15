"""Canonical identity, lineage, and partition contracts for S3 through S8."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping


class ContinuityContractError(ValueError):
    """Stable, fail-closed contract failure."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _token(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().casefold())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def canonical_line(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ContinuityContractError("INVALID_SELECTION_LINE") from exc
    if not number.is_finite():
        raise ContinuityContractError("INVALID_SELECTION_LINE")
    rendered = format(number.normalize(), "f")
    return "0" if rendered in {"-0", "-0.0"} else rendered


def _participants(candidate: Mapping[str, Any]) -> tuple[str, str]:
    home = candidate.get("home_team") or candidate.get("participant_a")
    away = candidate.get("away_team") or candidate.get("participant_b")
    if not home or not away:
        participants = candidate.get("participants")
        if isinstance(participants, list) and len(participants) == 2:
            home, away = participants
    if not home or not away:
        raise ContinuityContractError("MISSING_EVENT_PARTICIPANTS")
    return _token(home), _token(away)


def event_identity_fields(candidate: Mapping[str, Any]) -> dict[str, str]:
    home, away = _participants(candidate)
    kickoff = candidate.get("kickoff") or candidate.get("start_time") or candidate.get("scheduled_at_utc")
    if not kickoff:
        raise ContinuityContractError("MISSING_EVENT_KICKOFF")
    sport = _token(candidate.get("sport"))
    competition = _token(candidate.get("competition") or candidate.get("league"))
    if not sport or not competition:
        raise ContinuityContractError("MISSING_EVENT_CONTEXT")
    return {
        "sport": sport,
        "competition": competition,
        "participant_a": home,
        "participant_b": away,
        "kickoff": str(kickoff).strip(),
    }


def derive_event_id(candidate: Mapping[str, Any]) -> str:
    return f"evt_{canonical_sha256(event_identity_fields(candidate))[:32]}"


def selection_identity_fields(candidate: Mapping[str, Any], event_id: str) -> dict[str, str]:
    best_market = candidate.get("best_market")
    best = best_market if isinstance(best_market, Mapping) else {}
    market = candidate.get("market_family") or candidate.get("market_type") or candidate.get("market") or best.get("name")
    selection = candidate.get("selection") or best.get("selection") or best.get("direction")
    if not market or not selection:
        raise ContinuityContractError("MISSING_SELECTION_IDENTITY")
    return {
        "event_id": event_id,
        "market_family": _token(candidate.get("market_family") or market),
        "market_type": _token(candidate.get("market_type") or market),
        "subject_id": _token(candidate.get("subject_id") or candidate.get("player_id")),
        "selection": _token(selection),
        "direction": _token(candidate.get("direction")),
        "line": canonical_line(candidate.get("line", best.get("line"))),
        "period": _token(candidate.get("period") or "full_time"),
    }


def derive_selection_id(candidate: Mapping[str, Any], event_id: str | None = None) -> str:
    resolved_event_id = event_id or derive_event_id(candidate)
    return f"sel_{canonical_sha256(selection_identity_fields(candidate, resolved_event_id))[:32]}"


def bind_event_identity(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Bind the event identity before S4 has selected a market/outcome.

    S3 may legitimately emit an analytical event with no viable market. Such an
    event still needs a stable identity, but manufacturing a selection ID would
    incorrectly turn missing analytical evidence into a pick.
    """
    result = dict(candidate)
    expected_event = derive_event_id(result)
    existing_event = result.get("canonical_event_id")
    if existing_event and existing_event != expected_event:
        raise ContinuityContractError("CANONICAL_EVENT_ID_MISMATCH")
    result["canonical_event_id"] = expected_event
    result["event_id"] = expected_event
    return result


def bind_candidate_identity(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a candidate and bind immutable event/selection identity.

    Existing canonical IDs are verified rather than silently trusted. Legacy
    candidate IDs are retained only as provenance.
    """
    result = bind_event_identity(candidate)
    expected_event = result["canonical_event_id"]
    expected_selection = derive_selection_id(result, expected_event)
    existing_selection = result.get("selection_id")
    if existing_selection and existing_selection != expected_selection:
        raise ContinuityContractError("CANONICAL_SELECTION_ID_MISMATCH")
    legacy_id = result.get("candidate_id")
    if legacy_id and legacy_id != expected_selection:
        result["legacy_candidate_id"] = legacy_id
    result["canonical_event_id"] = expected_event
    result["event_id"] = expected_event
    result["selection_id"] = expected_selection
    result["candidate_id"] = expected_selection
    return result


def candidate_ids(candidates: Iterable[Mapping[str, Any]]) -> list[str]:
    ids: list[str] = []
    for candidate in candidates:
        candidate_id = candidate.get("selection_id") or candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise ContinuityContractError("MISSING_CANONICAL_SELECTION_ID")
        if candidate.get("candidate_id") != candidate_id or candidate.get("selection_id") != candidate_id:
            raise ContinuityContractError("SELECTION_ID_ALIAS_MISMATCH")
        ids.append(candidate_id)
    if len(ids) != len(set(ids)):
        raise ContinuityContractError("DUPLICATE_CANONICAL_SELECTION_ID")
    return ids


def validate_exact_partition(
    predecessor: Iterable[Mapping[str, Any]],
    terminal_categories: Mapping[str, Iterable[Mapping[str, Any]]],
) -> dict[str, Any]:
    source_ids = candidate_ids(predecessor)
    terminal: list[str] = []
    counts: dict[str, int] = {}
    for name, records in terminal_categories.items():
        values = list(records)
        counts[name] = len(values)
        for record in values:
            original = record.get("original_candidate") if isinstance(record, Mapping) else None
            candidate_id = record.get("selection_id") or record.get("candidate_id") if isinstance(record, Mapping) else None
            if not candidate_id and isinstance(original, Mapping):
                candidate_id = original.get("selection_id") or original.get("candidate_id")
            if not isinstance(candidate_id, str) or not candidate_id:
                raise ContinuityContractError("TERMINAL_RECORD_ID_MISSING")
            terminal.append(candidate_id)
    duplicates = sorted(key for key, value in Counter(terminal).items() if value > 1)
    missing = sorted((Counter(source_ids) - Counter(terminal)).elements())
    unexpected = sorted((Counter(terminal) - Counter(source_ids)).elements())
    if duplicates or missing or unexpected:
        raise ContinuityContractError(
            f"CANDIDATE_PARTITION_MISMATCH duplicates={duplicates} missing={missing} unexpected={unexpected}"
        )
    return {
        "input_count": len(source_ids),
        "terminal_count": len(terminal),
        "category_counts": counts,
        "duplicate_candidate_ids": [],
        "unaccounted_candidate_ids": [],
        "unexpected_candidate_ids": [],
        "overlapping_terminal_categories": [],
    }


def validate_lineage(
    artifact: Mapping[str, Any],
    *,
    artifact_type: str,
    betting_day: str,
    run_id: str,
    predecessor_path: Path | str,
    predecessor_field: str,
) -> None:
    if artifact.get("schema_version") != 2:
        raise ContinuityContractError("SCHEMA_VERSION_MISMATCH")
    if artifact.get("artifact_type") != artifact_type:
        raise ContinuityContractError("ARTIFACT_TYPE_MISMATCH")
    if artifact.get("betting_day") != betting_day or artifact.get("run_id") != run_id:
        raise ContinuityContractError("RUN_BINDING_MISMATCH")
    path = Path(predecessor_path).resolve(strict=True)
    supplied_path = artifact.get(f"source_{predecessor_field}_path")
    supplied_hash = artifact.get(f"source_{predecessor_field}_sha256")
    if not supplied_path or Path(supplied_path).resolve(strict=True) != path:
        raise ContinuityContractError("PREDECESSOR_PATH_MISMATCH")
    if supplied_hash != file_sha256(path):
        raise ContinuityContractError("PREDECESSOR_HASH_MISMATCH")
