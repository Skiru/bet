"""Canonical S1e event universe and lossless boundary accounting."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from bet.pipeline.artifact_io import publish_run_artifact
from bet.pipeline.run_evidence import sha256_file
from bet.pipeline.canonical_continuity import derive_event_id, ContinuityContractError


class EventAccountingError(ValueError):
    pass


def canonical_event_id(event: dict[str, Any]) -> str:
    try:
        recomputed = derive_event_id(event)
    except Exception as exc:
        raise EventAccountingError("EVENT_IDENTITY_INCOMPLETE") from exc
    for key in ("canonical_event_id", "event_id"):
        val = event.get(key)
        if val not in (None, ""):
            if val != recomputed:
                raise EventAccountingError("CANONICAL_EVENT_ID_MISMATCH")
    return recomputed


def deduplicate_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for event in events:
        if not isinstance(event, dict):
            raise EventAccountingError("EVENT_RECORD_INVALID")
        event_id = canonical_event_id(event)
        normalized = dict(event)
        normalized["canonical_event_id"] = event_id
        if event_id in unique and unique[event_id] != normalized:
            raise EventAccountingError("EVENT_IDENTITY_CONFLICT")
        unique[event_id] = normalized
    return [unique[event_id] for event_id in sorted(unique)]


class EventAccountingLedger:
    def __init__(self, run_root: Path, *, betting_day: str, run_id: str):
        self.run_root = Path(run_root)
        self.betting_day = betting_day
        self.run_id = run_id
        self.path = self.run_root / "event_accounting_ledger.json"

    @classmethod
    def initialize(
        cls, run_root: Path, universe_path: Path, *, betting_day: str, run_id: str
    ) -> "EventAccountingLedger":
        ledger = cls(run_root, betting_day=betting_day, run_id=run_id)

        resolved_run_root = Path(run_root).resolve()
        resolved_universe_path = Path(universe_path).resolve()
        try:
            rel = resolved_universe_path.relative_to(resolved_run_root)
            curr = resolved_run_root
            for part in rel.parts:
                curr = curr / part
                if curr.is_symlink():
                    raise EventAccountingError(
                        f"Symlink detected in S1e universe path: {curr}"
                    )
        except ValueError:
            raise EventAccountingError("S1e universe path is outside run root")

        if universe_path.is_symlink() or resolved_universe_path.is_symlink():
            raise EventAccountingError("S1e universe path is a symlink")

        if not universe_path.exists():
            raise EventAccountingError(f"S1e universe file missing: {universe_path}")

        from bet.pipeline.run_evidence import sha256_file

        u_sha = sha256_file(universe_path)

        try:
            universe = json.loads(universe_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise EventAccountingError(f"Failed to parse S1e universe JSON: {exc}")

        if (
            universe.get("artifact_type") != "S1E_EVENT_UNIVERSE_LEDGER"
            or int(universe.get("schema_version", 0)) < 1
            or universe.get("betting_day") != betting_day
            or universe.get("run_id") != run_id
        ):
            raise EventAccountingError("EVENT_UNIVERSE_BINDING_INVALID")

        events = universe.get("events")
        if not isinstance(events, list):
            raise EventAccountingError("EVENT_UNIVERSE_EVENTS_INVALID")

        unique_ids = {}
        for event in events:
            if not isinstance(event, dict):
                raise EventAccountingError("EVENT_RECORD_INVALID")
            sport = event.get("sport")
            home = event.get("home_team") or event.get("home")
            away = event.get("away_team") or event.get("away")
            kickoff = event.get("kickoff") or event.get("start_time")
            competition = event.get("competition") or event.get("league")
            if not all(
                isinstance(x, str) and x.strip()
                for x in (sport, home, away, kickoff, competition)
            ):
                raise EventAccountingError("EVENT_IDENTITY_INCOMPLETE")

            try:
                from bet.pipeline.canonical_continuity import derive_event_id

                recomputed_id = derive_event_id(event)
            except Exception as e:
                raise EventAccountingError(f"Failed to recompute event ID: {e}")

            declared_id = event.get("canonical_event_id")
            if declared_id and declared_id != recomputed_id:
                raise EventAccountingError("CANONICAL_EVENT_ID_MISMATCH")

            normalized = dict(event)
            normalized["canonical_event_id"] = recomputed_id
            if recomputed_id in unique_ids and unique_ids[recomputed_id] != normalized:
                raise EventAccountingError("EVENT_IDENTITY_CONFLICT")
            unique_ids[recomputed_id] = normalized

        sorted_event_ids = sorted(unique_ids.keys())

        payload = {
            "schema_version": 1,
            "artifact_type": "EVENT_ACCOUNTING_LEDGER",
            "betting_day": betting_day,
            "run_id": run_id,
            "source_s1e_path": str(universe_path),
            "source_s1e_sha256": u_sha,
            "canonical_event_ids": sorted_event_ids,
            "after_dedup_count": len(sorted_event_ids),
            "boundaries": {},
            "events_with_terminal_status": 0,
            "unaccounted_event_ids": sorted_event_ids,
        }
        ledger._publish(payload)
        return ledger

    def _load(self) -> dict[str, Any]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if (
            payload.get("betting_day") != self.betting_day
            or payload.get("run_id") != self.run_id
        ):
            raise EventAccountingError("EVENT_ACCOUNTING_BINDING_INVALID")
        return payload

    def _publish(self, payload: dict[str, Any]) -> None:
        publish_run_artifact(
            run_root=self.run_root,
            target=self.path,
            payload=payload,
            betting_day=self.betting_day,
            run_id=self.run_id,
            artifact_type="EVENT_ACCOUNTING_LEDGER",
            immutable=False,
        )

    def record_boundary(
        self,
        step_id: str,
        *,
        records: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        payload = self._load()
        universe = set(payload["canonical_event_ids"])
        statuses: dict[str, list[str]] = {}
        if records is None:
            raise EventAccountingError("EVENT_BOUNDARY_RECORDS_MISSING")
        for record in records:
            if not isinstance(record, dict):
                raise EventAccountingError("EVENT_BOUNDARY_RECORD_INVALID")
            event_id = str(
                record.get("canonical_event_id")
                or record.get("event_id")
                or record.get("fixture_id")
                or record.get("candidate_id")
                or record.get("id")
                or ""
            )
            status = str(
                record.get("terminal_status")
                or record.get("status")
                or record.get("analytical_status")
                or "PASS"
            )
            if event_id not in universe:
                raise EventAccountingError("EVENT_BOUNDARY_UNKNOWN_EVENT")
            if not status:
                raise EventAccountingError("EVENT_BOUNDARY_STATUS_MISSING")
            if event_id in statuses:
                raise EventAccountingError("EVENT_BOUNDARY_DUPLICATE_EVENT")
            statuses[event_id] = [status]
        missing = sorted(universe - set(statuses))
        if missing:
            raise EventAccountingError(f"EVENT_BOUNDARY_LOSS:{','.join(missing)}")
        payload["boundaries"][step_id] = {
            event_id: {"terminal_statuses": values}
            for event_id, values in sorted(statuses.items())
        }
        payload["events_with_terminal_status"] = len(statuses)
        payload["unaccounted_event_ids"] = missing
        if payload["after_dedup_count"] != len(universe) or payload[
            "events_with_terminal_status"
        ] != len(universe):
            raise EventAccountingError("EVENT_ACCOUNTING_INVARIANT_FAILED")
        self._publish(payload)
        return payload


ACCOUNTING_BOUNDARY_STEPS = frozenset(
    {"S2", "S2.3", "S2.5", "S2.7", "S2.9", "S3", "S4", "S5", "S6", "S7", "S7b", "S8"}
)
