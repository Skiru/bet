from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping
from bet.enrichment.models import (
    NormalizedEvent,
    NormalizedParticipant,
    NormalizedTeamMatch,
    NormalizedStandingTable,
    NormalizedLineupState,
    NormalizedAvailabilityState,
    NormalizedRoster,
    NormalizedVenueContext,
    NormalizedOfficialContext,
)

@dataclass(frozen=True)
class FootballEnrichmentSnapshot:
    schema_version: str = "1.0"
    run_id: str = ""
    snapshot_id: str = ""
    snapshot_state: str = "COMPLETE" # COMPLETE, DEGRADED, BLOCKED
    canonical_fixture_id: int = 0
    analysis_cutoff_at: datetime | None = None
    
    # Event metadata
    kickoff_at: datetime | None = None
    event_status: str = ""
    competition_canonical_id: int | None = None
    season_canonical_id: int | None = None
    
    # Participants
    home_participant: NormalizedParticipant | None = None
    away_participant: NormalizedParticipant | None = None
    
    # Form and H2H
    home_form: tuple[NormalizedTeamMatch, ...] = field(default_factory=tuple)
    away_form: tuple[NormalizedTeamMatch, ...] = field(default_factory=tuple)
    h2h_records: tuple[NormalizedTeamMatch, ...] = field(default_factory=tuple)
    
    # Standings
    standings: NormalizedStandingTable | None = None
    
    # Lineups and availability
    home_lineup: NormalizedLineupState | None = None
    away_lineup: NormalizedLineupState | None = None
    home_availability: NormalizedAvailabilityState | None = None
    away_availability: NormalizedAvailabilityState | None = None
    home_roster: NormalizedRoster | None = None
    away_roster: NormalizedRoster | None = None
    
    # Context
    venue: NormalizedVenueContext | None = None
    official: NormalizedOfficialContext | None = None
    
    # Metrics and advanced metrics
    selected_metrics: dict[str, Any] = field(default_factory=dict)
    advanced_metrics: dict[str, Any] = field(default_factory=dict)
    
    # Provenance and metadata
    selected_provider_ids: dict[str, str] = field(default_factory=dict)
    attempt_summaries: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    bundle_ids: tuple[str, ...] = field(default_factory=tuple)
    freshness_staleness: dict[str, Any] = field(default_factory=dict)
    confidence_components: dict[str, float] = field(default_factory=dict)
    missing_fields: tuple[str, ...] = field(default_factory=tuple)


from dataclasses import is_dataclass, fields
from datetime import timezone
from enum import Enum
from typing import get_type_hints, get_origin, get_args, Union
import hashlib
import json

def format_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")

def parse_datetime(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt

def to_dict(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, datetime):
        return format_datetime(obj)
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj):
        res = {}
        for f in sorted(fields(obj), key=lambda x: x.name):
            val = getattr(obj, f.name)
            res[f.name] = to_dict(val)
        return res
    if isinstance(obj, (list, tuple)):
        return [to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {str(k): to_dict(v) for k, v in sorted(obj.items())}
    return obj

def from_dict(cls: Any, data: Any) -> Any:
    if data is None:
        return None
    if cls is datetime:
        return parse_datetime(data)
    if isinstance(cls, type) and issubclass(cls, Enum):
        return cls(data)
    if is_dataclass(cls):
        if "schema_version" in data:
            expected_version = getattr(cls, "schema_version", None)
            if expected_version is not None and data["schema_version"] != expected_version:
                raise ValueError(f"Unknown schema version: {data['schema_version']} (expected {expected_version})")
        type_hints = get_type_hints(cls)
        kwargs = {}
        for f in fields(cls):
            val = data.get(f.name)
            if val is None:
                kwargs[f.name] = None
                continue
            field_type = type_hints.get(f.name, f.type)
            kwargs[f.name] = _deserialize_type(field_type, val)
        return cls(**kwargs)
    return data

def _deserialize_type(t: Any, val: Any) -> Any:
    if val is None:
        return None
    origin = get_origin(t)
    args = get_args(t)
    
    import types
    if origin in (Union, types.UnionType) or origin is type(Union):
        non_none_types = [a for a in args if a is not type(None)]
        if not non_none_types:
            return val
        return _deserialize_type(non_none_types[0], val)
        
    if origin in (list, tuple):
        item_type = args[0] if args else Any
        items = [_deserialize_type(item_type, item) for item in val]
        if origin is tuple:
            return tuple(items)
        return items
        
    if origin is dict:
        val_type = args[1] if len(args) > 1 else Any
        return {k: _deserialize_type(val_type, v) for k, v in val.items()}
        
    if isinstance(t, type):
        if issubclass(t, datetime):
            return parse_datetime(val)
        if issubclass(t, Enum):
            return t(val)
        if is_dataclass(t):
            return from_dict(t, val)
            
    return val

def canonical_json_bytes(data: Any) -> bytes:
    dict_data = to_dict(data)
    return json.dumps(
        dict_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")

def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(obj)).hexdigest()
