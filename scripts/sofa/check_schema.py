#!/usr/bin/env python3
import sys

from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig

EVENT_IDS_FOOTBALL = [16363633, 16416342, 11352378, 11352402, 11352410]
EVENT_IDS_TENNIS = [15345277, 11456123, 11456124, 11456125, 11456126]


# Keys the football metric table depends on. Their disappearance silently
# empties whole market families, so each is probed by name (PLAN §5.6).
FOOTBALL_KEYS_EXPECTED = {
    "shotsOnGoal",
    "totalShotsOnGoal",
    "shotsOffGoal",
    "blockedScoringAttempt",
    "cornerKicks",
    "yellowCards",
    "fouls",
    "offsides",
}


def check_schema() -> None:
    config = SofaConfig.from_env()
    client = SofascoreClient(config)

    missing_fields: list[str] = []
    keys_seen: set[str] = set()

    # 1. Check Football
    for event_id in EVENT_IDS_FOOTBALL:
        print(f"Checking football event {event_id}...")

        details = client.event(event_id)
        if details:
            event = details.get("event", {})
            if (
                "tournament" not in event
                or "uniqueTournament" not in event["tournament"]
                or "id" not in event["tournament"]["uniqueTournament"]
            ):
                missing_fields.append(
                    f"Event {event_id}: missing tournament.uniqueTournament.id"
                )
            if "roundInfo" not in event:
                missing_fields.append(f"Event {event_id}: missing roundInfo")
            if "referee" in event and "name" not in event["referee"]:
                missing_fields.append(f"Event {event_id}: referee has no name")

        incidents = client.event_incidents(event_id)
        if incidents and "incidents" in incidents:
            has_cards = any(
                inc.get("incidentType") == "card" for inc in incidents["incidents"]
            )
            if has_cards:
                has_class = any(
                    "incidentClass" in inc
                    for inc in incidents["incidents"]
                    if inc.get("incidentType") == "card"
                )
                if not has_class:
                    missing_fields.append(
                        f"Event {event_id}: card incident missing incidentClass"
                    )

        stats = client.event_statistics(event_id)
        if stats and "statistics" in stats:
            for group in stats["statistics"]:
                for subgroup in group.get("groups", []):
                    for item in subgroup.get("statisticsItems", []):
                        key = item.get("key")
                        if key in FOOTBALL_KEYS_EXPECTED:
                            keys_seen.add(key)

    # T42: a key that never appears on ANY probed event has disappeared from
    # the API. That is an error, not a data gap — this API is reverse-engineered
    # and has no SLA, so a field vanishing is exactly what we are watching for.
    # Per-event absence is normal (not every match has offsides recorded); total
    # absence across the whole probe is not.
    for key in sorted(FOOTBALL_KEYS_EXPECTED - keys_seen):
        missing_fields.append(
            f"statistic key '{key}' absent from every probed football event"
        )

    # 2. Check Tennis
    for event_id in EVENT_IDS_TENNIS:
        print(f"Checking tennis event {event_id}...")

        details = client.event(event_id)
        if details:
            event = details.get("event", {})
            if "groundType" not in event:
                missing_fields.append(f"Event {event_id}: missing groundType")
            if "defaultPeriodCount" not in event:
                missing_fields.append(f"Event {event_id}: missing defaultPeriodCount")

    if missing_fields:
        print("\nSchema errors found:")
        for err in missing_fields:
            print(f" - {err}")
        sys.exit(2)
    else:
        print("\nSchema is stable.")
        sys.exit(0)


if __name__ == "__main__":
    check_schema()
