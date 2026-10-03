"""International Friendly Games (851) is a friendly (2026-10-04).

It sat in `allowed`, so senior national-team friendlies entered samples and
moved the football rating: 2,427 cached finished matches of 268 national
teams. Six more friendly / exhibition competitions found in the cache join
it, each with its evidence (docs/sofa/evidence/friendly_competitions_2026-10-04.json).
The list is a code contract keyed on provider ids, not a fitted constant.
"""

from __future__ import annotations

import json
from pathlib import Path

from bet.sofa import football_rating
from bet.sofa.samples import FRIENDLY_COMPETITION_IDS, is_friendly_fixture

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "config/sofa_friendly_competitions.json"
ADDED = {851, 18553, 18593, 23238, 28748, 28832, 25657}


def test_international_and_preseason_friendlies_are_excluded() -> None:
    assert ADDED <= FRIENDLY_COMPETITION_IDS
    assert all(is_friendly_fixture("football", c) for c in ADDED)


def test_every_added_id_is_in_its_evidence_file() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    for entry in cfg["excluded"]:
        if entry["competition_id"] not in ADDED:
            continue
        evidence = json.loads((REPO / entry["evidence"]).read_text(encoding="utf-8"))
        ids = {c["competition_id"] for c in evidence["competitions"]}
        assert entry["competition_id"] in ids, entry


def test_a_supercup_and_a_competitive_summer_cup_are_not_friendlies() -> None:
    # Charity Shields are one-off super cups; the NWSL x Liga MX Femenil
    # Summer Cup is an official competition. Listed for review, not excluded.
    for comp in (20621, 36687, 38123, 32767, 22802):
        assert comp not in FRIENDLY_COMPETITION_IDS


def test_an_international_friendly_moves_no_rating() -> None:
    event = {
        "id": 17219232,
        "startTimestamp": 1_759_500_000,
        "status": {"type": "finished"},
        "tournament": {"id": 70, "uniqueTournament": {"id": 851},
                       "category": {"sport": {"slug": "football"}}},
        "homeTeam": {"id": 4820, "name": "Colombia", "national": True},
        "awayTeam": {"id": 4819, "name": "Paraguay", "national": True},
        "homeScore": {"current": 2, "period1": 1, "period2": 1, "normaltime": 2},
        "awayScore": {"current": 0, "period1": 0, "period2": 0, "normaltime": 0},
    }
    assert football_rating.parse_event(event) is None
    # The same match as a World Cup qualifier (11) is a rated result.
    event["tournament"]["uniqueTournament"] = {"id": 11}
    assert football_rating.parse_event(event) is not None
