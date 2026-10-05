"""The SPORT_IDENTITY matcher on its golden set (plan 2026-10-05 production
grade, F1.2): docs/sofa/evidence/sport_identity_golden_<sport>.json, built by
scripts/sofa/measure_sport_identity.py from the settled days 09-28..10-04 -
each case a Superbet event whose Sofascore event is verified offline (the
settle's id, in the cache, finished, the start within an hour, the graded
score equal, both sides confirmed by name / verified entity or read by a
person), with the listing the matcher is given. Offline: the listing is the
checked-in copy, never the bridge.

0 wrong ids, every sport >= 50 cases, and no fewer identified than at build.
Decoys: each case's team2 swapped for another case's - a game that does not
exist - must never be identified as the case's event."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import sport_identity as si

EVIDENCE = Path(__file__).resolve().parents[2] / "docs" / "sofa" / "evidence"
AT = datetime(2026, 9, 28, 0, 0, tzinfo=UTC)


class Listings:
    def __init__(self, listings: dict[str, list[dict[str, Any]]]) -> None:
        self.listings = listings

    def entity_events(self, entity_id: int, kind: Any, page: int) -> Any | None:
        return {"events": self.listings.get(str(entity_id), [])}


def _golden(sport: str) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(
        (EVIDENCE / f"sport_identity_golden_{sport}.json").read_text(encoding="utf-8"))
    return doc


def _run(case: dict[str, Any], team2: str | None = None) -> dict[str, Any]:
    t2 = team2 if team2 is not None else case["team2"]
    ev = si.BoardEvent(case["sport"], case["superbet_event_id"],
                       f"{case['team1']}·{t2}", case["team1"], t2,
                       case["kickoff_utc"], case["tournament"], case["date"])
    ids = {case["team1"]: case["team_ids"]["team1"]}
    qids = {case["team1"]: case["query_ids"]["team1"]}
    if team2 is None:
        ids[t2] = case["team_ids"]["team2"]
        qids[t2] = case["query_ids"]["team2"]
    return si.identify_event(ev, Listings(case["listings"]), None,
                             lambda s, n: ids.get(n), AT,
                             lambda s, n: qids.get(n))


@pytest.mark.parametrize("sport", si.SPORT_KEYS)
def test_the_golden_set_has_no_wrong_id(sport: str) -> None:
    doc = _golden(sport)
    cases = doc["cases"]
    assert len(cases) >= 50
    wrong, identified = [], 0
    for case in cases:
        rec = _run(case)
        if rec["status"] != si.IDENTIFIED:
            continue
        identified += 1
        if (rec["sofascore_event_id"] != case["expected_sofascore_event_id"]
                or rec["home_is_team1"] != case["expected_home_is_team1"]):
            wrong.append((case["superbet_event_id"], case["match_name"],
                          rec["sofascore_event_id"], rec.get("sofascore_match")))
    assert wrong == []
    assert identified >= doc["identified_at_build"]


@pytest.mark.parametrize("sport", si.SPORT_KEYS)
def test_a_game_that_does_not_exist_is_never_identified(sport: str) -> None:
    cases = _golden(sport)["cases"]
    pinned = []
    for i, case in enumerate(cases):
        other = cases[(i + 7) % len(cases)]
        own = {si.fold_team(sport, case["team1"]), si.fold_team(sport, case["team2"])}
        if (other["expected_sofascore_event_id"] == case["expected_sofascore_event_id"]
                or si.fold_team(sport, other["team2"]) in own):
            continue  # the same team again is not a decoy
        rec = _run(case, team2=other["team2"])
        if (rec["status"] == si.IDENTIFIED
                and rec["sofascore_event_id"] == case["expected_sofascore_event_id"]):
            pinned.append((case["match_name"], other["team2"]))
    assert pinned == []
