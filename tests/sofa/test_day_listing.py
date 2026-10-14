"""bet.sofa.day_listing - a tournament's games of a day (cached) and the
match inside that small list (identity plan K3). Offline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import day_listing as dl
from bet.sofa.db import get_connection, migrate
from bet.sofa.errors import ProviderError

KICK = datetime(2026, 10, 14, 18, 0, tzinfo=UTC)


def _ev(
    eid: int,
    home: str,
    away: str,
    start: datetime = KICK,
    status: str = "notstarted",
    gender: str = "M",
    slug: str = "basketball",
) -> dict[str, Any]:
    return {
        "id": eid,
        "startTimestamp": int(start.timestamp()),
        "status": {"type": status},
        "tournament": {"category": {"sport": {"slug": slug}}},
        "homeTeam": {"id": eid * 10, "name": home, "gender": gender},
        "awayTeam": {"id": eid * 10 + 1, "name": away, "gender": gender},
    }


def _match(
    team1: str,
    team2: str,
    events: list[dict[str, Any]],
    min_score: float = 60,
    lead: float = 20,
) -> dict[str, Any]:
    return dl.tournament_day_match(
        "basketball", team1, team2, KICK, events, "basketball", min_score, lead
    )


def test_both_names_in_one_tournaments_hour_pick_the_game() -> None:
    # 10-14: Superbet "Bilbao - SK Slavia Prague ERA NBK" (both TEAM_UNRESOLVED),
    # Sofascore "Surne Bilbao Basket - SK Slavia Praha" 16611519 (BCL group G)
    events = [
        _ev(16611519, "Surne Bilbao Basket", "SK Slavia Praha"),
        _ev(16611512, "KK Spartak Office Shoes", "Hapoel Netanel Holon"),
    ]
    r = _match("Bilbao", "SK Slavia Prague ERA NBK", events)
    assert r["status"] == "IDENTIFIED" and r["event"]["id"] == 16611519
    assert r["home_is_team1"] is True and r["match_method"] == "TOURNAMENT_DAY"
    crossed = _match("SK Slavia Prague ERA NBK", "Bilbao", events)
    assert crossed["status"] == "IDENTIFIED" and crossed["home_is_team1"] is False


def test_the_weaker_side_must_reach_the_floor_and_lead_the_next_game() -> None:
    events = [_ev(1, "Surne Bilbao Basket", "SK Slavia Praha")]
    assert _match("Bilbao", "Totally Other", events)["reason"] == "BELOW_MIN_SCORE"
    # two first-team games of the hour, both readable: no lead, no pick
    two = [
        _ev(1, "Bilbao Basket", "Slavia Praha"),
        _ev(2, "Bilbao Athletic", "Slavia Sofia"),
    ]
    r = _match("Bilbao", "Slavia", two, min_score=50, lead=20)
    assert r["status"] == "NOT_IDENTIFIED" and r["reason"] == "NO_CLEAR_LEAD"
    # a reserve squad is no rival at all (same_squad)
    reserve = [
        _ev(1, "Bilbao Basket", "Slavia Praha"),
        _ev(2, "Bilbao Basket B", "Slavia"),
    ]
    assert _match("Bilbao Basket", "Slavia Praha", reserve)["event"]["id"] == 1


def test_the_hour_the_gender_and_the_schedule_hold() -> None:
    late = [_ev(1, "Surne Bilbao Basket", "SK Slavia Praha", KICK + timedelta(hours=2))]
    assert _match("Bilbao", "SK Slavia Praha", late)["reason"] == "NO_GAME_WITHIN_1H"
    off = [_ev(1, "Surne Bilbao Basket", "SK Slavia Praha", status="postponed")]
    assert _match("Bilbao", "SK Slavia Praha", off)["reason"] == "NO_GAME_WITHIN_1H"
    women = [_ev(1, "Surne Bilbao Basket", "SK Slavia Praha", gender="F")]
    assert _match("Bilbao", "SK Slavia Praha", women)["status"] == "NOT_IDENTIFIED"
    other = [_ev(1, "Surne Bilbao Basket", "SK Slavia Praha", slug="volleyball")]
    assert _match("Bilbao", "SK Slavia Praha", other)["status"] == "NOT_IDENTIFIED"


class _Client:
    def __init__(self, payload: Any = None, refuse: bool = False) -> None:
        self.payload, self.refuse, self.calls = payload, refuse, 0

    def tournament_day_events(self, ut: int, day: str) -> Any | None:
        self.calls += 1
        if self.refuse:
            raise ProviderError("HTTP 403")
        return self.payload

    def scheduled_tournaments(self, slug: str, day: str, page: int) -> Any | None:
        raise AssertionError


def test_a_past_day_is_asked_once_today_again_after_the_ttl(tmp_path: Path) -> None:
    path = str(tmp_path / "s.db")
    migrate(path)
    conn = get_connection(path)
    client = _Client({"events": [_ev(1, "A", "B")]})
    now = datetime(2026, 10, 14, 12, tzinfo=UTC)
    ev, hit = dl.tournament_day_events(client, conn, 9357, "2026-10-13", now)
    assert (len(ev), hit, client.calls) == (1, False, 1)
    later = now + timedelta(days=3)
    assert dl.tournament_day_events(client, conn, 9357, "2026-10-13", later)[1] is True
    dl.tournament_day_events(client, conn, 9357, "2026-10-14", now)
    assert (
        dl.tournament_day_events(
            client, conn, 9357, "2026-10-14", now + timedelta(minutes=30)
        )[1]
        is True
    )
    assert (
        dl.tournament_day_events(
            client, conn, 9357, "2026-10-14", now + timedelta(minutes=50)
        )[1]
        is False
    )
    assert client.calls == 3


def test_a_404_is_an_empty_day_and_a_refusal_raises(tmp_path: Path) -> None:
    path = str(tmp_path / "s.db")
    migrate(path)
    conn = get_connection(path)
    assert dl.tournament_day_events(_Client(None), conn, 1, "2026-10-01")[0] == []
    with pytest.raises(ProviderError):
        dl.tournament_day_events(_Client(refuse=True), conn, 2, "2026-10-01")
    assert dl.cached(conn, dl.TOURNAMENT_DAY, "2", "2026-10-01") is None


# --- SPORT_IDENTITY's TOURNAMENT_DAY (identity plan K3) -------------------------------


def _bev(t1: str, t2: str, sport: str = "basketball"):
    from bet.sofa import sport_identity as si

    return si.BoardEvent(
        sport,
        "1",
        f"{t1}·{t2}",
        t1,
        t2,
        KICK.isoformat().replace("+00:00", "Z"),
        "Liga Mistrzów - gr.G",
    )


class _NoListing:
    def entity_events(self, entity_id: int, kind: Any, page: int) -> Any | None:
        raise AssertionError("no team to ask")


def test_identify_event_matches_by_the_tournament_day_only_with_no_id() -> None:
    from bet.sofa import sport_identity as si

    events = [_ev(16611519, "Surne Bilbao Basket", "SK Slavia Praha")]
    at = datetime(2026, 10, 14, 6, tzinfo=UTC)
    off = si.identify_event(
        _bev("Bilbao", "SK Slavia Prague ERA NBK"),
        _NoListing(),
        None,
        lambda s, n: None,
        at,
    )
    assert off["reason"] == "TEAM_UNRESOLVED"
    on = si.identify_event(
        _bev("Bilbao", "SK Slavia Prague ERA NBK"),
        _NoListing(),
        None,
        lambda s, n: None,
        at,
        tournament_day=lambda ev: events,
    )
    assert on["status"] == "IDENTIFIED" and on["match_method"] == "TOURNAMENT_DAY"
    assert on["sofascore_event_id"] == 16611519 and on["home_is_team1"] is True
    # CS2 never; a side with an id never (it has its own listing to ask)
    cs2 = si.identify_event(
        _bev("Bilbao", "SK Slavia", "cs2"),
        _NoListing(),
        None,
        lambda s, n: None,
        at,
        tournament_day=lambda ev: events,
    )
    assert cs2["status"] == "NOT_IDENTIFIED"


def test_the_source_reads_the_tournament_map_and_turns_a_refusal_into_an_abort(
    tmp_path: Path,
) -> None:
    from bet.sofa import sport_identity as si

    path = str(tmp_path / "s.db")
    migrate(path)
    conn = get_connection(path)
    conn.execute(
        "INSERT INTO sofa_tournament_map (sport, superbet_tournament,"
        " competition_id, events, first_seen_utc, last_seen_utc) VALUES"
        " ('basketball', 'Liga Mistrzów - gr.G', 138, 3, 'x', 'x')"
    )
    good = _Client({"events": [_ev(1, "A", "B")]})
    src = dl.tournament_day_source(good, conn)
    assert [e["id"] for e in src(_bev("A", "B"))] == [1]
    assert (
        src(
            si.BoardEvent(
                "basketball", "2", "x", "x", "y", "2026-10-14T18:00:00Z", "Unmapped Cup"
            )
        )
        == []
    )
    bad = dl.tournament_day_source(_Client(refuse=True), conn)
    later = _bev("A", "B")
    with pytest.raises(si.BridgeAbortedError):
        bad(
            si.BoardEvent(
                later.sport,
                "3",
                later.match_name,
                "A",
                "B",
                "2026-10-13T18:00:00Z",
                later.tournament,
            )
        )
