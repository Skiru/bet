"""Discovery accounting and event classification engine for BET V5/V8 (C4).

Truthful accounting of genuinely new canonical events vs existing event updates and new provider refs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DiscoveryAccountingSummary:
    total_fetched: int = 0
    genuinely_new_events: int = 0
    existing_events_updated: int = 0
    new_provider_refs: int = 0
    unchanged_events: int = 0
    identity_conflicts: int = 0
    rejected_invalid_events: int = 0

    @property
    def new_provider_events_discovered(self) -> int:
        """NEW_PROVIDER_EVENTS_DISCOVERED is strictly genuinely new canonical events."""
        return self.genuinely_new_events


class DiscoveryAccountingEngine:
    """Engine for truthful discovery accounting and idempotency checks."""

    def calculate_accounting(
        self,
        fetched_raw_events: list[dict[str, Any]],
        existing_canonical_ids: set[str],
        existing_source_refs: set[tuple[str, str]],
    ) -> DiscoveryAccountingSummary:
        summary = DiscoveryAccountingSummary(total_fetched=len(fetched_raw_events))

        seen_new_ids_in_batch: set[str] = set()

        for evt in fetched_raw_events:
            c_id = str(evt.get("canonical_event_id") or "")
            provider = str(evt.get("provider") or evt.get("source") or "")
            p_id = str(evt.get("provider_event_id") or evt.get("external_id") or "")

            if evt.get("is_conflict") or evt.get("has_identity_conflict"):
                summary.identity_conflicts += 1
                continue

            if evt.get("is_invalid") or not c_id:
                summary.rejected_invalid_events += 1
                continue

            ref_tuple = (provider, p_id)

            if c_id not in existing_canonical_ids and c_id not in seen_new_ids_in_batch:
                summary.genuinely_new_events += 1
                seen_new_ids_in_batch.add(c_id)
            elif ref_tuple not in existing_source_refs:
                summary.new_provider_refs += 1
            elif evt.get("is_updated") or evt.get("kickoff_changed") or evt.get("status_changed"):
                summary.existing_events_updated += 1
            else:
                summary.unchanged_events += 1

        return summary
