"""backfill_event_stats.py - the barren-competition rule per sport.

Coverage audit 2026-10-23 (docs/sofa/history/AUDYT_POKRYCIA_2026-10-23.md):
the "208 barren competitions" a tennis dry run printed counted every sport's
listings (174 were tennis), and the rule's premise - 25 404s in a row mean
the competition publishes nothing - is wrong for ITF tennis, where Sofascore
publishes statistics match by match (ITF M15 Monastir 2: 25 cached 404s,
a never-asked match answered 200). Tennis is no longer cut by it.
"""

from __future__ import annotations

from typing import Any

from scripts.sofa import backfill_event_stats as bes


def _event(eid: int, comp: int, sport: str) -> dict[str, Any]:
    return {"id": eid, "status": {"type": "finished"},
            "tournament": {"uniqueTournament": {"id": comp},
                           "category": {"sport": {"slug": sport}}}}


def _listings() -> list[list[dict[str, Any]]]:
    tennis = [_event(i, 24573, "tennis") for i in range(1, 30)]
    football = [_event(100 + i, 17, "football") for i in range(1, 30)]
    return [tennis, football]


def test_barren_counts_only_the_asked_sport() -> None:
    asked = {e["id"]: False for page in _listings() for e in page}
    assert bes.barren_competitions(_listings(), asked) == {24573, 17}
    assert bes.barren_competitions(_listings(), asked, sport="football") == {17}


def test_tennis_is_exempt_from_the_barren_rule() -> None:
    asked = {e["id"]: False for page in _listings() for e in page}
    assert bes.barren_competitions(_listings(), asked, sport="tennis") == set()
    run = bes.Backfill(client=None, cache=None, sport="tennis")
    run.misses[24573] = bes.MAX_BARREN_MISSES + 5
    assert run.exhausted() == set()
    football = bes.Backfill(client=None, cache=None, sport="football")
    football.misses[17] = bes.MAX_BARREN_MISSES
    assert football.exhausted() == {17}
