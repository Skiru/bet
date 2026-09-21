#!/usr/bin/env python3
"""Build the frozen payload bundle the offline e2e test replays (T36).

Provenance, stated up front because it decides what the e2e can be trusted for:

* The **shapes** are real. Every listing, event and statistics payload in the
  bundle is derived from a response recorded in `docs/sofa/evidence/`
  on 2026-09-17, so field names, nesting and types are the provider's, not ours.
* The **cast** is partly derived. Only two entities were ever recorded with a
  full listing (Real Madrid 2829, Carlos Alcaraz 275923). A three-fixture day
  needs six, so the remaining sides' listings are the recorded events with the
  entity ids re-pointed. Each such entity is listed in `derived_entities`.

What that means: the e2e is a **regression guard across stage boundaries** — it
proves that six artifacts still come out the shape and size they came out
before. It is **not** a measurement of provider coverage or of matching quality;
those are T04 and the live checks, and neither may be quoted from this file.

The sampled markets are chosen to come from the **listing** (goals, sets), not
from `/statistics` (PLAN §5.3). That is not a shortcut: it is the same path the
cheapest and highest-volume rows take in production.

Usage:
    python -m scripts.sofa.build_e2e_bundle
"""

from __future__ import annotations

import copy
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

EVIDENCE = Path("docs/sofa/evidence")
OUT_PATH = Path("tests/fixtures/sofascore/e2e_bundle.json")

RUN_DATE = "2026-09-17"
KICKOFF_BASE = datetime(2026, 9, 17, 18, 0, tzinfo=UTC)

# (entity_id, display name, source listing, whether the listing is the real one)
FOOTBALL_HOME = (2829, "Real Madrid")
FOOTBALL_AWAY = (900001, "Benfica")
FOOTBALL2_HOME = (900002, "Getafe")
FOOTBALL2_AWAY = (900003, "Sevilla")
TENNIS_HOME = (275923, "Carlos Alcaraz")
TENNIS_AWAY = (900004, "Tommy Paul")

DERIVED_ENTITIES = [FOOTBALL_AWAY, FOOTBALL2_HOME, FOOTBALL2_AWAY, TENNIS_AWAY]


def evidence_body(name: str) -> Any:
    raw = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    return raw["response"]["body"]


def repoint_listing(
    listing: dict[str, Any],
    entity_id: int,
    entity_name: str,
    *,
    id_offset: int,
    day_shift: int,
) -> dict[str, Any]:
    """Re-point a recorded listing at a different entity.

    Event ids and kickoffs are shifted so the derived side's history is a
    distinct set of matches; otherwise both sides of a fixture would share
    every historical event and the dedup rule would collapse the sample to
    half its size for reasons that have nothing to do with the code.
    """
    out = copy.deepcopy(listing)
    for event in out.get("events", []):
        event["id"] = event["id"] + id_offset
        event["startTimestamp"] = event["startTimestamp"] + day_shift * 86400
        event["homeTeam"] = {"id": entity_id, "name": entity_name}
        event["awayTeam"] = {
            "id": 950000 + (event["id"] % 1000),
            "name": f"Opponent {event['id'] % 1000}",
        }
    return out


def cap_before(listing: dict[str, Any], kickoff: datetime) -> dict[str, Any]:
    """Drop anything at or after kickoff so the fixture's own leak guard is
    exercised on a listing that genuinely contains only the past."""
    out = copy.deepcopy(listing)
    limit = int(kickoff.timestamp())
    out["events"] = [e for e in out["events"] if e["startTimestamp"] < limit]
    return out


def event_detail(
    event_id: int,
    home: tuple[int, str],
    away: tuple[int, str],
    kickoff: datetime,
    *,
    template: dict[str, Any],
) -> dict[str, Any]:
    """An /event/{id} body built on a recorded one, with our cast."""
    out = copy.deepcopy(template)
    event = out["event"] if "event" in out else out
    event["id"] = event_id
    event["startTimestamp"] = int(kickoff.timestamp())
    event["homeTeam"] = {"id": home[0], "name": home[1]}
    event["awayTeam"] = {"id": away[0], "name": away[1]}
    return {"event": event}


def superbet_odds(
    market_name: str, lines: list[tuple[float, float, float]]
) -> dict[str, Any]:
    """A Superbet event body with one market's ladder.

    Shape follows tests/fixtures/sofascore/superbet_events_by_date.json and the
    offer parser: a flat `odds` list of {marketName, specialBetValue, name, price}.
    """
    odds: list[dict[str, Any]] = []
    for line, over, under in lines:
        odds.append(
            {
                "marketName": market_name,
                "specialBetValue": str(line),
                "name": "Powyżej",
                "price": over,
            }
        )
        odds.append(
            {
                "marketName": market_name,
                "specialBetValue": str(line),
                "name": "Poniżej",
                "price": under,
            }
        )
    return {"odds": odds}


def main() -> int:
    rm_listing = evidence_body("team_2829_events_last_0.json")
    alcaraz_listing = evidence_body("team_275923_events_last_0.json")
    football_event_tpl = evidence_body("event_16363633_details.json")
    tennis_event_tpl = evidence_body("event_15345277_details.json")

    kickoff_f1 = KICKOFF_BASE
    kickoff_f2 = KICKOFF_BASE + timedelta(hours=1)
    kickoff_t1 = KICKOFF_BASE + timedelta(hours=2)

    listings: dict[str, Any] = {
        f"team/{FOOTBALL_HOME[0]}/events/last/0": cap_before(rm_listing, kickoff_f1),
        f"team/{TENNIS_HOME[0]}/events/last/0": cap_before(alcaraz_listing, kickoff_t1),
    }
    for index, (entity_id, name) in enumerate(DERIVED_ENTITIES):
        source = alcaraz_listing if entity_id == TENNIS_AWAY[0] else rm_listing
        kickoff = kickoff_t1 if entity_id == TENNIS_AWAY[0] else kickoff_f1
        listings[f"team/{entity_id}/events/last/0"] = cap_before(
            repoint_listing(
                source,
                entity_id,
                name,
                id_offset=1_000_000 * (index + 1),
                day_shift=-(index + 1),
            ),
            kickoff,
        )

    fixtures = [
        (
            16900001,
            FOOTBALL_HOME,
            FOOTBALL_AWAY,
            kickoff_f1,
            "football",
            football_event_tpl,
        ),
        (
            16900002,
            FOOTBALL2_HOME,
            FOOTBALL2_AWAY,
            kickoff_f2,
            "football",
            football_event_tpl,
        ),
        (15900001, TENNIS_HOME, TENNIS_AWAY, kickoff_t1, "tennis", tennis_event_tpl),
    ]

    sofascore: dict[str, Any] = dict(listings)
    board: list[dict[str, Any]] = []
    superbet_events: dict[str, Any] = {}

    for index, (event_id, home, away, kickoff, sport, template) in enumerate(fixtures):
        superbet_id = str(20000 + index)

        sofascore[f"search/all?q={home[1].lower()}"] = {
            "results": [
                {
                    "type": "team",
                    "entity": {
                        "id": home[0],
                        "name": home[1],
                        "sport": {"slug": sport},
                        "country": {"name": "Spain"},
                    },
                }
            ]
        }
        detail = event_detail(event_id, home, away, kickoff, template=template)
        sofascore[f"event/{event_id}"] = detail

        # The day's own fixture lives on the home side's "next" listing — that
        # is how resolve finds it (E4 step 5). Without it the entity resolves
        # but the event never does.
        upcoming = copy.deepcopy(detail["event"])
        upcoming["status"] = {
            "code": 0,
            "type": "notstarted",
            "description": "Not started",
        }
        sofascore[f"team/{home[0]}/events/next/0"] = {
            "events": [upcoming],
            "hasNextPage": False,
        }

        board.append(
            {
                "eventId": int(superbet_id),
                "matchName": f"{home[1]}·{away[1]}",
                "utcDate": kickoff.isoformat().replace("+00:00", "Z"),
                "sportId": 5 if sport == "football" else 2,
            }
        )

        if sport == "football":
            superbet_events[superbet_id] = superbet_odds(
                "Liczba goli",
                [(1.5, 1.28, 3.55), (2.5, 1.95, 1.85), (3.5, 3.60, 1.28)],
            )
        else:
            superbet_events[superbet_id] = superbet_odds(
                "Liczba setów",
                [(2.5, 1.72, 2.05)],
            )

    bundle = {
        "_doc": [
            "Frozen payload bundle for the offline e2e (T36).",
            "",
            "Shapes are real: every body is derived from a response recorded in",
            "docs/sofa/evidence/ on 2026-09-17.",
            "",
            "The cast is partly derived: only entities 2829 (Real Madrid) and",
            "275923 (Carlos Alcaraz) were ever recorded with a full listing. The",
            "sides named in `derived_entities` reuse those recorded events with",
            "their ids re-pointed and shifted.",
            "",
            "This bundle is a REGRESSION GUARD across stage boundaries. It is not",
            "a measurement of provider coverage or of matching quality.",
            "",
            "Markets are listing-sourced on purpose (goals, sets): PLAN §5.3.",
            "",
            "Rebuild: python -m scripts.sofa.build_e2e_bundle",
        ],
        "date": RUN_DATE,
        "derived_entities": [
            {"entity_id": eid, "name": name} for eid, name in DERIVED_ENTITIES
        ],
        "real_entities": [
            {
                "entity_id": FOOTBALL_HOME[0],
                "name": FOOTBALL_HOME[1],
                "source": "docs/sofa/evidence/team_2829_events_last_0.json",
            },
            {
                "entity_id": TENNIS_HOME[0],
                "name": TENNIS_HOME[1],
                "source": "docs/sofa/evidence/team_275923_events_last_0.json",
            },
        ],
        "superbet": {"events_by_date": board, "event_odds": superbet_events},
        "sofascore": sofascore,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"wrote {OUT_PATH}: {len(board)} board fixtures, "
        f"{len(sofascore)} sofascore routes, {len(superbet_events)} odds bodies"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
