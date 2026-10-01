"""One football side cannot play twice inside a day (2026-10-01).

Six football fixtures of 111 carried a side whose Sofascore id held two squads
(France / Slovenia / Switzerland / Poland U19, Deportivo Santo Domingo) or one
match listed twice against an opponent filed under two ids (Hapoel Ironi
Karmiel). Replayed on 990 football sides of 09-28..10-01 the first version also
flagged three things that were not two squads, and each one is pinned here:
a postponement listed twice (same opponent, same score, a day apart), a
renamed opponent (same score an hour apart), and a seven-a-side tournament
(several matches a day; now an excluded competition).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bet.sofa.contracts import GapReason
from bet.sofa.samples import (
    FRIENDLY_COMPETITION_IDS,
    MIN_HOURS_BETWEEN_MATCHES,
    one_squad_per_entity,
)

REPO = Path(__file__).resolve().parents[2]
ME = 7
H = 3600
T0 = 1_780_000_000


def ev(
    eid: int,
    hours: float,
    opp_id: int,
    opp_name: str,
    gf: int,
    ga: int,
    home: bool = True,
) -> dict[str, Any]:
    me = {"id": ME, "name": "Me"}
    other = {"id": opp_id, "name": opp_name}
    return {
        "id": eid,
        "startTimestamp": int(T0 + hours * H),
        "homeTeam": me if home else other,
        "awayTeam": other if home else me,
        "homeScore": {"current": gf if home else ga},
        "awayScore": {"current": ga if home else gf},
    }


def ids(events: list[dict[str, Any]]) -> list[int]:
    return sorted(int(e["id"]) for e in events)


def test_a_normal_week_is_untouched() -> None:
    events = [ev(1, 0, 10, "A", 1, 0), ev(2, 72, 11, "B", 2, 2), ev(3, 168, 12, "C", 0, 1)]
    kept, conflict = one_squad_per_entity(events, ME)
    assert conflict is None and ids(kept) == [1, 2, 3]


def test_karmiel_one_match_two_opponent_ids_same_kickoff() -> None:
    events = [
        ev(16990514, 0, 501, "Hapoel Ihud Bnei Jatt F.C.", 2, 2, home=False),
        ev(16988403, 0, 500, "Hapoel Bnei Jat United", 2, 2, home=False),
        ev(3, 96, 12, "C", 1, 0),
    ]
    kept, conflict = one_squad_per_entity(events, ME)
    assert conflict is None
    assert ids(kept) == [3, 16988403], "kept once, the lowest id"


def test_a_postponement_listed_twice_a_day_apart_is_one_match() -> None:
    """Hapoel Marmorek - FC Tzeirey Tira, 0-0 on 01-09 10:45 and 01-10 10:00."""
    events = [ev(15332192, 0, 40, "FC Tzeirey Tira", 0, 0), ev(15552672, 23.25, 40, "FC Tzeirey Tira", 0, 0)]
    kept, conflict = one_squad_per_entity(events, ME)
    assert conflict is None and ids(kept) == [15332192]


def test_a_renamed_opponent_with_the_same_score_an_hour_apart_is_one_match() -> None:
    """Naft Masjed Soleyman 1-0 'Arka Alborz' 10:30 and 'Arka City FC' 11:30."""
    events = [ev(15306038, 0, 1140408, "Arka Alborz", 0, 1), ev(17155275, 1, 1285860, "Arka City FC", 0, 1)]
    kept, conflict = one_squad_per_entity(events, ME)
    assert conflict is None and ids(kept) == [15306038]


def test_one_match_with_two_scores_keeps_neither() -> None:
    events = [ev(1, 0, 40, "X", 3, 0), ev(2, 20, 40, "X", 1, 1), ev(3, 100, 41, "Y", 0, 0)]
    kept, conflict = one_squad_per_entity(events, ME)
    assert conflict is None and ids(kept) == [3]


def test_two_qualifiers_a_day_against_different_opponents_is_two_squads() -> None:
    """France U19: Croatia U19 at 10:00 and Switzerland U19 at 16:30, 03-31."""
    events = [ev(15224868, 0, 1, "Croatia U19", 1, 0), ev(15598150, 6.5, 2, "Switzerland U19", 2, 1, home=False)]
    kept, conflict = one_squad_per_entity(events, ME)
    assert conflict is not None
    assert "15224868" in conflict and "15598150" in conflict
    assert "two squads" in conflict


def test_santo_domingo_league_and_amateur_side_two_and_a_half_hours_apart() -> None:
    events = [
        ev(17066310, 0, 9, "CDEyF Patria", 2, 7),
        ev(16962506, 2.5, 8, "LDU Portoviejo", 0, 1, home=False),
    ]
    _, conflict = one_squad_per_entity(events, ME)
    assert conflict is not None


def test_the_boundary_is_a_day() -> None:
    events = [ev(1, 0, 1, "A", 1, 0), ev(2, MIN_HOURS_BETWEEN_MATCHES, 2, "B", 0, 0)]
    assert one_squad_per_entity(events, ME)[1] is None
    events = [ev(1, 0, 1, "A", 1, 0), ev(2, MIN_HOURS_BETWEEN_MATCHES - 0.5, 2, "B", 0, 0)]
    assert one_squad_per_entity(events, ME)[1] is not None


def test_seven_a_side_is_an_excluded_competition_with_its_evidence() -> None:
    assert 26767 in FRIENDLY_COMPETITION_IDS
    cfg = json.loads((REPO / "config/sofa_friendly_competitions.json").read_text())
    entry = next(e for e in cfg["excluded"] if e["competition_id"] == 26767)
    assert (REPO / entry["evidence"]).exists()


def test_get_historical_events_leaves_a_two_squad_side_empty_and_says_why() -> None:
    from datetime import UTC, datetime

    from bet.sofa.config import SofaConfig
    from bet.sofa.contracts import Fixture, GapEntry
    from bet.sofa.samples import get_historical_events

    listing = {
        "events": [
            {
                **ev(100 + i, -24 * 3 * (i + 1), 50 + i, f"Opp {i}", 1, 0),
                "status": {"type": "finished", "code": 100},
                "tournament": {"uniqueTournament": {"id": 17}},
            }
            for i in range(6)
        ]
        + [
            {
                **ev(999, -24 * 3 * 1 + 4, 77, "Other", 0, 3),
                "status": {"type": "finished", "code": 100},
                "tournament": {"uniqueTournament": {"id": 17}},
            }
        ]
    }

    class Cache:
        def get_entity_events(self, *_: Any) -> dict[str, Any] | None:
            return listing if _[2] == 0 else None

        def save_entity_events(self, *_: Any) -> None:
            raise AssertionError("no write expected")

    class Client:
        def entity_events(self, *_: Any) -> None:
            return None

    fixture = Fixture(
        sofascore_event_id=1, superbet_event_ids=["1"], sport="football",
        kickoff_utc=datetime.fromtimestamp(T0, UTC),
        home_name="Me", away_name="X", home_entity_id=ME, away_entity_id=8,
        competition_name="C", competition_id=17, season_id=1, category_name="X",
        identity="CONFIRMED", round_number=None, round_name=None,
        cup_round_type=None, previous_leg_event_id=None, venue_name=None,
        referee=None, ground_type=None, default_period_count=None,
    )
    gaps: list[GapEntry] = []
    got = get_historical_events(
        Client(), Cache(), ME, "football", fixture, SofaConfig.from_env(), gaps  # type: ignore[arg-type]
    )
    assert got == []
    assert [g.reason for g in gaps] == [GapReason.ENTITY_CONFLICT]
    assert "entity 7" in gaps[0].detail
