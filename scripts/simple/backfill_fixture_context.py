#!/usr/bin/env python3
"""Refill an EVENT_LIST's ``fixture_context`` from the provider, in place.

Why this exists rather than "just re-run DISCOVER". DISCOVER's breadth is the
one thing a spent Highlightly quota destroys irrecoverably (memory note
``rerunning-a-day-resume-at-enrich``), so a re-run resumes downstream of it and
inherits whatever the morning's event list happened to carry. When the fault
being fixed is *in* the event list -- as it was on 2026-09-03, where
``round_name``, ``group_name`` and ``previous_leg_event_id`` were null on 165 of
165 fixtures because the discovery adapter never copied them out of the row it
had already fetched -- resuming downstream reproduces the fault.

This reads the same ``/events/?date_from=&date_to=`` listing the adapter reads,
matches on the bzzoiro id the event list already carries, and rewrites only
``fixture_context``. Nothing else on the record is touched: not the id, not the
sources, not the competition, not the status. So it cannot change which
fixtures the day has, which is the property that makes it safe to run on a
slate you cannot rediscover.

Costs one listing page per day in the window (two, since the offer window runs
to 06:00 the next morning) plus one ``/events/{id}/`` per two-legged tie. No
metered quota: bzzoiro football is uncapped on PRO.

    python3 scripts/simple/backfill_fixture_context.py --event-list PATH [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "src")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from bet.api_clients import get_client  # noqa: E402
from bet.integration.source_result import SourceResultStatus  # noqa: E402
from bet.simple_stats.artifact_io import write_json_atomic  # noqa: E402
from bet.simple_stats.contracts import EventListV1, FixtureContext  # noqa: E402

_PAGE = 200
_MAX_PAGES = 5


def _listing(client, date: str) -> dict[str, dict]:
    """``{provider_match_id: raw row}`` for one calendar day."""
    rows: dict[str, dict] = {}
    for page in range(_MAX_PAGES):
        result = client.get_events_result(
            date_from=date, date_to=date, limit=_PAGE, offset=page * _PAGE
        )
        if result.status not in (
            SourceResultStatus.SUCCESS,
            SourceResultStatus.VALID_EMPTY,
        ):
            break
        matches = (result.value or {}).get("matches") or []
        for match in matches:
            rows[str(match.get("provider_match_id") or "")] = match
        total = (result.value or {}).get("total_count") or 0
        if len(matches) < _PAGE or (page + 1) * _PAGE >= total:
            break
    return rows


def _previous_leg(client, cache: dict, previous_id: str, home_id: str, away_id: str):
    """The first leg's score mapped onto tonight's sides, or ``{}``.

    The same mapping ``discover.BzzoiroDiscoveryAdapter._previous_leg_score``
    performs, repeated here rather than imported because that one reads a
    listing row and this one reads a normalised event -- and getting the
    orientation wrong is worth catching twice.
    """
    if previous_id not in cache:
        try:
            result = client.get_event_result(previous_id)
        except Exception:  # noqa: BLE001
            cache[previous_id] = None
        else:
            event = (result.value or {}).get("event") or {}
            score = event.get("score") or {}
            leg_home = (event.get("home_team") or {}).get("provider_team_id")
            leg_away = (event.get("away_team") or {}).get("provider_team_id")
            if (
                leg_home is None
                or leg_away is None
                or score.get("home") is None
                or score.get("away") is None
            ):
                cache[previous_id] = None
            else:
                cache[previous_id] = (
                    str(leg_home), str(leg_away),
                    int(score["home"]), int(score["away"]),
                )
    leg = cache[previous_id]
    if leg is None:
        return {}
    leg_home_id, leg_away_id, goals_home, goals_away = leg
    if (leg_home_id, leg_away_id) == (home_id, away_id):
        return {"previous_leg_goals_home": goals_home, "previous_leg_goals_away": goals_away}
    if (leg_home_id, leg_away_id) == (away_id, home_id):
        return {"previous_leg_goals_home": goals_away, "previous_leg_goals_away": goals_home}
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-list", required=True)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would change and write nothing.",
    )
    args = parser.parse_args()

    path = Path(args.event_list)
    event_list = EventListV1.model_validate_json(path.read_text(encoding="utf-8"))

    client = get_client("bzzoiro")
    # The offer window runs to 06:00 the morning after, so a fixture on the
    # slate can be listed under either date.
    day = datetime.strptime(event_list.date, "%Y-%m-%d")
    rows: dict[str, dict] = {}
    for offset in (0, 1):
        rows.update(_listing(client, (day + timedelta(days=offset)).strftime("%Y-%m-%d")))

    previous_cache: dict = {}
    changed = 0
    filled: dict[str, int] = {}
    events = []
    for event in event_list.events:
        native = (event.source_ids or {}).get("bzzoiro")
        row = rows.get(str(native)) if native else None
        if row is None:
            events.append(event)
            continue
        home = row.get("home_team") or {}
        away = row.get("away_team") or {}
        home_id = str(home.get("provider_team_id") or "")
        away_id = str(away.get("provider_team_id") or "")
        previous_id = row.get("previous_leg_event_id")
        extras = (
            _previous_leg(client, previous_cache, str(previous_id), home_id, away_id)
            if previous_id else {}
        )
        context = FixtureContext(
            referee_id=row.get("referee_id"),
            venue_id=row.get("venue_id"),
            league_id=str(row.get("competition_provider_id") or "") or None,
            is_local_derby=bool(row.get("is_local_derby")),
            is_neutral_ground=bool(row.get("is_neutral_ground")),
            travel_distance_km=row.get("travel_distance_km"),
            weather=row.get("weather"),
            round_name=row.get("round_name"),
            group_name=row.get("group_name"),
            previous_leg_event_id=str(previous_id) if previous_id else None,
            home_team_id=home_id or None,
            away_team_id=away_id or None,
            **extras,
        )
        if event.fixture_context is not None and (
            event.fixture_context.model_dump() == context.model_dump()
        ):
            events.append(event)
            continue
        changed += 1
        for field in (
            "round_name", "group_name", "previous_leg_event_id",
            "previous_leg_goals_home", "home_team_id",
        ):
            before = getattr(event.fixture_context, field, None) if event.fixture_context else None
            if before is None and getattr(context, field) is not None:
                filled[field] = filled.get(field, 0) + 1
        events.append(event.model_copy(update={"fixture_context": context}))

    print(f"events: {len(events)}  with a bzzoiro id: {sum(1 for e in events if (e.source_ids or {}).get('bzzoiro'))}")
    print(f"contexts rewritten: {changed}")
    for field, count in sorted(filled.items()):
        print(f"  newly populated {field}: {count}")
    if args.dry_run:
        print("dry run: nothing written")
        return 0
    write_json_atomic(
        path, event_list.model_copy(update={"events": events}).model_dump(mode="json")
    )
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
