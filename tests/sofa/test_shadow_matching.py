"""SHADOW_SETTLE's event lookup on the real pairs it lost, 2026-09-29..10-02.

Every name, id, kickoff and competition below is the board's (Superbet) and
the cached Sofascore event's, read from runs/sofa/shadow/*/settled.json and
data/sofa.db (data/night_2026-10-03/matching/). Before the fix each game was
NOT_ON_SOFASCORE; the offline replay over the four days found ten of them,
and none of the 618 games already matched moved to another event.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from bet.sofa.config import SofaConfig
from bet.sofa.names import levels_compatible, normalize_name, team_levels
from bet.sofa.resolve import (
    SofaResolver,
    event_tournament_tokens,
    mutual_listing_event,
    opponent_resembles,
    tournament_confirmed_event,
    tournament_tokens,
)
from bet.sofa.shadow import SPORTS, SnapshotEvent
from scripts.sofa import settle_shadow


def _ev(
    eid: int,
    ts: int,
    home: tuple[str, int, str],
    away: tuple[str, int, str],
    tournament: str,
    unique: str,
    category: str,
) -> dict[str, Any]:
    return {
        "id": eid,
        "startTimestamp": ts,
        "status": {"type": "finished"},
        "homeTeam": {"name": home[0], "id": home[1], "gender": home[2]},
        "awayTeam": {"name": away[0], "id": away[1], "gender": away[2]},
        "tournament": {
            "name": tournament,
            "uniqueTournament": {"name": unique},
            "category": {"name": category},
        },
    }


ROUEN = _ev(
    16355253, 1790704800, ("Rouen Dragons", 26318, "M"),
    ("Amiens Hockey Élite", 26312, "M"), "Ligue Magnus", "Ligue Magnus", "France",
)  # fmt: skip
KAC = _ev(
    16664805, 1790788500, ("EC KAC", 3922, "M"), ("HC Milano Rossoblu", 79569, "M"),
    "ICE Hockey League", "ICE Hockey League", "Austria",
)  # fmt: skip
MAC = _ev(
    16836834, 1790960400, ("Budapest Jégkorong Akadémia HC", 242132, "M"),
    ("FEHA19", 446155, "M"), "Erste Liga", "Erste Liga", "International",
)  # fmt: skip
TOPO = _ev(
    16561959, 1790955000, ("Kouvottaret", 308779, "F"), ("Torpan Pojat", 333333, "F"),
    "Korisliiga, Women", "Korisliiga, Women", "Finland",
)  # fmt: skip
HEIDELBERG = _ev(
    16476450, 1790962200, ("MLP Academics Heidelberg", 35344, "M"),
    ("ETB Miners", 80753, "M"), "Germany Pro A", "Germany Pro A", "Germany",
)  # fmt: skip
RUDOLFOV = _ev(
    16501653, 1790960400, ("Volejbal Rudolfov", 1135655, "F"),
    ("VK Dukla Liberec B", 1135654, "F"), "1. Liga, Women, Group A",
    "1. Liga, Women", "Czech Republic",
)  # fmt: skip
SAN_JOSE = _ev(
    16885556, 1790902800, ("San Jose St. Spartans", 297966, "F"),
    ("Wyoming Cowgirls", 333978, "F"), "NCAA, Women, Regular Season",
    "NCAA Regular Season, Women", "USA",
)  # fmt: skip


def _ko(event: dict[str, Any], minutes: float = 0) -> datetime:
    return datetime.fromtimestamp(event["startTimestamp"], UTC) + timedelta(
        minutes=minutes
    )


def _resolver() -> SofaResolver:
    return SofaResolver(SofaConfig(), None, None)  # type: ignore[arg-type]


# --- the name gate ------------------------------------------------------------


def test_an_elided_article_no_longer_glues_onto_the_club_word() -> None:
    # "Gothiques d'Amiens" folded to "gothiques damiens", which shares no word
    # with "Amiens Hockey Elite": Rouen - Amiens (09-29) and Anglet - Amiens
    # (10-02) were both refused with the right game in Rouen's listing.
    assert normalize_name("Gothiques d’Amiens") == "gothiques damiens"
    assert (
        normalize_name("Gothiques d’Amiens", split_elisions=True)
        == "gothiques d amiens"
    )
    assert (
        normalize_name("C'Chartres Basket Feminin", split_elisions=True)
        == "c chartres basket feminin"
    )
    board = ("Dragons de Rouen", "Gothiques d’Amiens")
    kwargs: dict[str, Any] = {
        "sport": "ice-hockey",
        "superbet_side_a": board[0],
        "superbet_side_b": board[1],
        "check_orientation": False,
    }
    opp = normalize_name(board[1])
    assert _resolver().match_quality(ROUEN, _ko(ROUEN), opp, **kwargs) is not None
    # The shared word still needs both clocks within 15 minutes.
    assert _resolver().match_quality(ROUEN, _ko(ROUEN, -16), opp, **kwargs) is None
    # Football keeps RESOLVE's strict gate.
    football = {**kwargs, "sport": "football"}
    assert _resolver().match_quality(ROUEN, _ko(ROUEN), opp, **football) is None


def test_a_womens_b_side_is_a_reserve_side() -> None:
    # "Dukla Liberec B (K)" -> "dukla liberec b (w)": the end-anchored reserve
    # rule missed the "b", and the side read senior against Sofascore's
    # "VK Dukla Liberec B" (2026-10-02, Rudolfov - Dukla Liberec B).
    board_b = normalize_name("Dukla Liberec B (K)")
    assert team_levels(board_b) == frozenset({"R"})
    assert levels_compatible(board_b, normalize_name("VK Dukla Liberec B"))
    # Still a senior side without the "B", and a "b" inside a name is not one.
    assert team_levels(normalize_name("Dukla Liberec (K)")) == frozenset({"S"})
    assert team_levels(normalize_name("B Mladost (K)")) == frozenset({"S"})
    kwargs: dict[str, Any] = {
        "sport": "volleyball",
        "superbet_side_a": "Rudolfov (K)",
        "superbet_side_b": "Dukla Liberec B (K)",
        "check_orientation": False,
    }
    assert (
        _resolver().match_quality(RUDOLFOV, _ko(RUDOLFOV), board_b, **kwargs)
        is not None
    )
    # The senior side's name against the B side's game stays refused.
    senior = {**kwargs, "superbet_side_b": "Dukla Liberec (K)"}
    assert (
        _resolver().match_quality(
            RUDOLFOV, _ko(RUDOLFOV), normalize_name("Dukla Liberec (K)"), **senior
        )
        is None
    )


# --- the second reading: both listings ----------------------------------------


def test_the_game_both_sides_own_listings_hold_needs_no_name() -> None:
    # 2026-09-30, KAC Klagenfurt - HC Mediolan: both searches found their
    # team, both listings held EC KAC - HC Milano Rossoblu at 17:15, and the
    # opponent gate refused it from both sides (Mediolan / Milano).
    assert mutual_listing_event([(3922, KAC)], [(79569, KAC)]) is KAC
    # The same team on both sides is not two searches agreeing.
    assert mutual_listing_event([(3922, KAC)], [(3922, KAC)]) is None
    # A team that is not one of the game's two is no confirmation.
    assert mutual_listing_event([(3922, KAC)], [(1, KAC)]) is None
    # Two such games: no answer.
    other = {**KAC, "id": 1, "homeTeam": {"name": "X", "id": 3922}}
    other["awayTeam"] = {"name": "Y", "id": 79569}
    assert (
        mutual_listing_event(
            [(3922, KAC), (3922, other)], [(79569, KAC), (79569, other)]
        )
        is None
    )


# --- the second reading: one name and the competition --------------------------


def test_one_side_by_name_and_the_competition() -> None:
    # 2026-10-02: FEHA19's one game at 17:00, in Erste Liga, against the side
    # Superbet calls "MAC Budapeszt".
    assert (
        tournament_confirmed_event(
            "Feha19", "MAC Budapeszt", "Erste Liga", [(446155, MAC)], []
        )
        is MAC
    )
    # ToPo is Torpan Pojat; Kouvottaret's own game, Korisliiga both ways.
    assert (
        tournament_confirmed_event(
            "Kouvottaret (K)", "ToPo (K)", "Finlandia - Korisliiga (K)",
            [(308779, TOPO)], [],
        )
        is TOPO
    )  # fmt: skip


def test_the_competition_reading_refuses() -> None:
    # Costa Rica's San Jose is not San Jose State, though the name passes: no
    # competition word in common (2026-10-02, 30 minutes apart as well).
    assert (
        tournament_tokens("Kostaryka - Championship")
        & event_tournament_tokens(SAN_JOSE)
        == set()
    )
    assert (
        tournament_confirmed_event(
            "San Jose", "Universidad de Costa Rica", "Kostaryka - Championship",
            [(297966, SAN_JOSE)], [],
        )
        is None
    )  # fmt: skip
    # A country is not a competition: "Niemcy" is aliased to "germany", which
    # Sofascore's "Germany Pro A" carries - the category takes it out.
    assert "germany" in tournament_tokens("Niemcy - Pro A")
    assert "germany" not in event_tournament_tokens(HEIDELBERG)
    assert (
        tournament_confirmed_event(
            "Heidelberg", "Essen", "Niemcy - Pro A", [(35344, HEIDELBERG)], []
        )
        is None
    )
    # The searched side's own name must pass the full score.
    assert (
        tournament_confirmed_event(
            "Szolnok", "MAC Budapeszt", "Erste Liga", [(446155, MAC)], []
        )
        is None
    )
    # Two games of the candidate in the window: which one is unknown.
    twin = {**MAC, "id": 1}
    assert (
        tournament_confirmed_event(
            "Feha19", "MAC Budapeszt", "Erste Liga", [(446155, MAC), (446155, twin)], []
        )
        is None
    )
    # The other side's own listing holds a different game at that time.
    assert (
        tournament_confirmed_event(
            "Feha19", "MAC Budapeszt", "Erste Liga", [(446155, MAC)], [(9, twin)]
        )
        is None
    )
    # A squad level that disagrees with the other board side's.
    assert (
        tournament_confirmed_event(
            "Feha19", "MAC Budapeszt U20", "Erste Liga", [(446155, MAC)], []
        )
        is None
    )


def test_the_same_league_two_days_later_is_not_the_game() -> None:
    # Negative control (every board kickoff moved 48 h): without an opponent
    # sign the competition reading took Skelleftea's SHL game of 10-01
    # against Malmo for the board's Skelleftea - Lulea of 09-29 - leagues
    # play at fixed hours. 15 of 17 control hits were of this kind.
    skelleftea = _ev(
        1, 1790787600, ("Skellefteå AIK", 11, "M"), ("Malmö Redhawks", 12, "M"),
        "SHL", "SHL", "Sweden",
    )  # fmt: skip
    assert (
        tournament_confirmed_event(
            "Skelleftea", "Lulea", "Szwecja - SHL", [(11, skelleftea)], []
        )
        is None
    )
    allsvenskan = _ev(
        2, 1790960400, ("Visby/Roma HK", 21, "M"), ("MoDo Hockey", 22, "M"),
        "Hockey Allsvenskan", "Hockey Allsvenskan", "Sweden",
    )  # fmt: skip
    assert (
        tournament_confirmed_event(
            "Visby-Roma", "AIK Stockholm", "Szwecja - Allsvenskan",
            [(21, allsvenskan)], [],
        )
        is None
    )  # fmt: skip


@pytest.mark.parametrize(
    ("board", "sofascore", "same"),
    [
        ("Goverla", "BC Hoverla", True),  # transliteration
        ("MAC Budapeszt", "Budapest Jégkorong Akadémia HC", True),  # exonym
        ("ASA", "Alliance Sport Alsace", True),  # initials
        ("ToPo (K)", "Torpan Pojat", True),  # two letters of each word
        ("Lulea", "Malmö Redhawks", False),
        ("TPS Turku", "Oulun Kärpät", False),
        ("KooKoo Kouvola", "Jokerit Helsinki", False),
        # A two-letter club prefix is not an acronym of anything.
        ("HC Rytsary", "Hockey Club", False),
        # Generic club words never count as the shared word.
        ("Basket Brno", "Basket Zaragoza", False),
    ],
)
def test_opponent_resembles(board: str, sofascore: str, same: bool) -> None:
    assert opponent_resembles(board, sofascore) is same


# --- end to end through the real resolver --------------------------------------


class _Cache:
    """Read-only: listings per team id, no entities, no misses."""

    def __init__(self, listings: dict[int, list[dict[str, Any]]]) -> None:
        self.listings = listings

    def get_entity(self, sport: str, key: str) -> None:
        return None

    def get_entity_miss(self, sport: str, key: str) -> bool:
        return False

    def get_listing_miss(self, entity_id: int, kind: str, page: int) -> bool:
        return False

    def get_entity_events(
        self, entity_id: int, kind: str, page: int
    ) -> dict[str, Any] | None:
        if entity_id not in self.listings:
            return None
        return {"events": self.listings[entity_id], "hasNextPage": False}

    def __getattr__(self, name: str) -> Any:
        return lambda *a, **k: None


class _Client:
    def __init__(self, searches: dict[str, list[dict[str, Any]]]) -> None:
        self.searches = searches
        self.requests: list[str] = []

    def search(self, q: str, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(q)
        teams = self.searches.get(q, [])
        return {"results": [{"type": "team", "entity": t} for t in teams]}

    def entity_events(self, *a: Any, **k: Any) -> None:
        raise AssertionError("every listing is in the cache")


def _team(name: str, tid: int, slug: str = "ice-hockey") -> dict[str, Any]:
    return {"name": name, "id": tid, "gender": "M", "sport": {"slug": slug}}


def _find(
    board: tuple[str, str], tournament: str, kickoff: datetime, cache: Any, client: Any
) -> Any:
    resolver = SofaResolver(SofaConfig(), client, cache)
    ev = SnapshotEvent(
        "1", "·".join(board), board[0], board[1],
        kickoff.isoformat().replace("+00:00", "Z"), tournament,
    )  # fmt: skip
    explain: dict[str, Any] = {}
    return settle_shadow.find_event(
        resolver, SPORTS["hockey"], ev, kickoff, explain
    ), explain


def test_find_event_takes_the_game_both_listings_hold() -> None:
    cache = _Cache({3922: [KAC], 79569: [KAC]})
    client = _Client(
        {
            "kac klagenfurt": [_team("EC KAC", 3922)],
            "hc milan": [_team("HC Milano Rossoblu", 79569)],
        }
    )
    found, _ = _find(
        ("KAC Klagenfurt", "HC Mediolan"),
        "Austria - ICE League",
        _ko(KAC),
        cache,
        client,
    )
    assert isinstance(found, dict) and found["id"] == KAC["id"]
    assert found["_shadow_match_rule"] == "MUTUAL_LISTING"
    assert found["_shadow_home_is_team1"] is True
    # No request beyond the two searches the name gates already made (the
    # alias table turns "Mediolan" into "milan", still no word of "Milano").
    assert client.requests == ["kac klagenfurt", "hc milan"]
    # Twenty minutes off the board's time: refused, and explained.
    missed, explain = _find(
        ("KAC Klagenfurt", "HC Mediolan"), "Austria - ICE League", _ko(KAC, 20),
        cache, client,
    )  # fmt: skip
    assert missed == "NOT_ON_SOFASCORE"
    assert explain["team1"]["reason"] == "OPPONENT_REFUSED"


def test_find_event_falls_back_to_the_competition() -> None:
    cache = _Cache({446155: [MAC]})
    client = _Client({"feha19": [_team("FEHA19", 446155)]})
    found, _ = _find(("MAC Budapeszt", "Feha19"), "Erste Liga", _ko(MAC), cache, client)
    assert isinstance(found, dict) and found["id"] == MAC["id"]
    assert found["_shadow_match_rule"] == "TOURNAMENT"
    # The same game under a competition that shares no word: not found.
    missed, _ = _find(
        ("MAC Budapeszt", "Feha19"), "Slowacja - Extraliga", _ko(MAC), cache, client
    )
    assert missed == "NOT_ON_SOFASCORE"


def test_settle_one_records_the_rule_and_the_orientation_by_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # DEAC - DAB Docler (2026-10-02): no name reads the orientation, the ids do.
    deac = _ev(
        16836837, 1790958600, ("Debreceni Egyetemi AC", 294784, "M"),
        ("Dunaújvárosi Acélbikák", 54707, "M"), "Erste Liga", "Erste Liga",
        "International",
    )  # fmt: skip
    assert settle_shadow.home_is_team1(deac, "DEAC", "DAB Docler") is None
    monkeypatch.setattr(
        settle_shadow,
        "find_event",
        lambda *a, **k: {**deac, "_shadow_match_rule": "MUTUAL_LISTING",
                         "_shadow_home_is_team1": True},
    )  # fmt: skip

    class Client:
        def event(self, eid: int) -> dict[str, Any]:
            return {"event": {**deac, "status": {"type": "inprogress"}}}

    ev = SnapshotEvent(
        "1",
        "DEAC·DAB Docler",
        "DEAC",
        "DAB Docler",
        "2026-10-02T16:30:00Z",
        "Erste Liga",
    )
    rec = settle_shadow.settle_one(
        ev,
        SPORTS["hockey"],
        None,
        Client(),
        None,
        _ko(deac, 600),  # type: ignore[arg-type]
    )
    assert rec["match_rule"] == "MUTUAL_LISTING"
    assert rec["home_is_team1"] is True and rec["orientation_unclear"] is False
    assert "_shadow_match_rule" not in rec


def test_orientation_reads_word_order_when_the_ratio_cannot() -> None:
    # 2026-10-02 Assat Pori - Lukko Rauma / Porin Assat - Rauman Lukko: the
    # only game of 09-29..10-02 graded totals-only for an unclear orientation.
    def reads(home: str, away: str, t1: str, t2: str) -> bool | None:
        return settle_shadow.home_is_team1(
            {"homeTeam": {"name": home}, "awayTeam": {"name": away}}, t1, t2
        )

    assert reads("Porin Ässät", "Rauman Lukko", "Assat Pori", "Lukko Rauma") is True
    assert reads("Rauman Lukko", "Porin Ässät", "Assat Pori", "Lukko Rauma") is False
    assert (
        reads(
            "Rouen Dragons",
            "Amiens Hockey Élite",
            "Dragons de Rouen",
            "Gothiques d’Amiens",
        )
        is True
    )
    # Each board name inside both Sofascore names: still no reading.
    assert reads("Lions Tigers", "Tigers Lions", "Lions", "Tigers") is None
