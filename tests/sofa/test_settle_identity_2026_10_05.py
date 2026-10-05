"""Plan 2026-10-05, part 4B-4D: which match a measured sport's grade belongs to.

B0 one set of settle states; B1 one Sofascore id for two Superbet events;
B2 the searched team's own name; B3 a pinned id; B4 one event in two dates'
files; B5 UNUSUAL; B6 orientation by ids; B7 the shadow sweep; C1-C5 CS2;
D-a the audit; D-b the match evidence on every record.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import cs2, shadow
from bet.sofa import settle_identity as si
from bet.sofa import sport_coupon as sc
from bet.sofa.config import SofaConfig
from bet.sofa.names import normalize_name
from bet.sofa.resolve import SofaResolver, name_stopwords, superbet_gender
from scripts.sofa import (
    audit_settle_identity,
    cs2_watchdog,
    purge_entity_alias,
    record_results,
    settle_cs2,
    settle_shadow,
)
from tests.sofa import test_cs2_stages as cs2_stages
from tests.sofa.test_shadow import (
    DATE,
    HOCKEY_AET,
    T1,
    T2,
    FakeClient,
    FakeResolver,
    run_settle,
    settled,
    sofa_event,
    write_snapshot,
)

# --- B0 ----------------------------------------------------------------------


def test_every_settle_reads_one_set_of_states() -> None:
    assert settle_shadow.TERMINAL is shadow.TERMINAL
    assert settle_cs2.TERMINAL is shadow.TERMINAL
    assert settle_shadow.RETRYABLE is settle_cs2.RETRYABLE is shadow.RETRYABLE
    assert record_results.FINAL_STATES is shadow.TERMINAL
    assert cs2_watchdog.RETRYABLE is shadow.RETRYABLE
    assert shadow.EXCLUDED < shadow.TERMINAL
    assert not shadow.TERMINAL & shadow.RETRYABLE
    # B5: UNUSUAL is asked again; an awarded match is final.
    assert shadow.is_retryable("UNUSUAL") and shadow.is_terminal("AWARDED")
    for state in (
        "DUPLICATE_SOFASCORE_ID",
        "WITHDRAWN",
        "ID_CHANGED",
        "MOVED_TO:2026-10-03",
        "AMBIGUOUS_START",
        "DUPLICATE_SUPERBET_TEAM",
    ):
        assert shadow.is_terminal(state) and shadow.is_excluded(state)
    assert shadow.moved_to_date("MOVED_TO:2026-10-03") == "2026-10-03"
    assert sc.TERMINAL_UNGRADED >= shadow.EXCLUDED - {shadow.MOVED_TO}


def _graded(outcome: str = "WIN") -> dict[str, Any]:
    return {
        "superbet_event_id": "x",
        "market_id": 623,
        "family": "total",
        "period": 0,
        "subject": "",
        "line": 5.5,
        "side": "OVER",
        "odds": 1.9,
        "partner_odds": 1.9,
        "fair_p": 0.5,
        "outcome": outcome,
    }


def test_the_ledger_never_counts_an_identity_state(tmp_path: Path) -> None:
    day = tmp_path / "shadow" / "hockey" / DATE
    day.mkdir(parents=True)
    events = {
        "1": {"state": "SETTLED", "graded": [_graded("WIN")]},
        # a duplicate and a moved record keep their rows for the audit
        "2": {"state": "DUPLICATE_SOFASCORE_ID", "graded": [_graded("LOSS")] * 5},
        "3": {"state": "MOVED_TO:2026-09-29", "graded": [_graded("LOSS")] * 5},
        "4": {"state": "UNUSUAL"},
        "5": {"state": "WITHDRAWN"},
    }
    (day / "settled.json").write_text(json.dumps({"events": events}))
    (row,) = record_results.measure_rows(str(tmp_path), DATE)
    assert row["favourite_side"]["sides"] == 1  # the SETTLED game's line only
    assert row["retryable"] == 1  # UNUSUAL
    assert row["excluded"] == 3


# --- B1 / B4 / C5 / WITHDRAWN: the identity pass ---------------------------------


def _snap(eid: str, t1: str, t2: str, kickoff: str, last: str) -> si.SnapInfo:
    return si.SnapInfo(last, last, kickoff, t1, t2)


def _rec(t1: str, t2: str, sid: int | None, home: str, away: str) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "match_name": f"{t1}·{t2}",
        "state": "SETTLED" if sid else "NOT_ON_SOFASCORE",
        "graded": [_graded()],
    }
    if sid:
        rec.update(
            sofascore_event_id=sid,
            sofascore_match=f"{home} - {away}",
            home_is_team1=True,
        )
    return rec


def test_one_sofascore_id_for_two_superbet_events_keeps_the_named_one() -> None:
    # Volleyball 16885527, 10-01, without the shared opponent (C5 is tested
    # apart): the record whose both names pass is kept, the other is a
    # duplicate of it.
    files = {
        DATE: {
            "a": _rec("Alpha Wolves", "Beta Bears", 5, "Alpha Wolves", "Beta Bears"),
            "b": _rec("Omega Hawks", "Beta Bearz", 5, "Alpha Wolves", "Beta Bears"),
        }
    }
    ko = "2026-09-28T18:00:00Z"
    snaps = {
        DATE: {
            "a": _snap("a", "Alpha Wolves", "Beta Bears", ko, "2026-09-28T17:30:00Z"),
            "b": _snap("b", "Omega Hawks", "Beta Bearz", ko, "2026-09-28T17:40:00Z"),
        }
    }
    changes = si.plan_identity("shadow", files, snaps)
    assert set(changes) == {(DATE, "b")}
    assert changes[(DATE, "b")]["state"] == "DUPLICATE_SOFASCORE_ID"
    assert changes[(DATE, "b")]["duplicate_of"] == "a"
    # Neither passing both names: no record is kept.
    files[DATE]["a"] = _rec("Gamma Owls", "Beta Bearz", 5, "Alpha Wolves", "Beta Bears")
    changes = si.plan_identity("shadow", files, snaps)
    assert {c["state"] for c in changes.values()} == {"DUPLICATE_SOFASCORE_ID"}
    assert len(changes) == 2


def test_a_withdrawn_event_gives_way_to_the_same_pair_quoted_later() -> None:
    ko = "2026-09-28T18:00:00Z"
    files = {
        DATE: {
            "old": _rec(T1, T2, 9, T1, T2),
            "new": _rec(T1, T2, 9, T1, T2),
        }
    }
    snaps = {
        DATE: {
            # last quoted 6 h before the start, then re-listed under "new"
            "old": _snap("old", T1, T2, ko, "2026-09-28T12:00:00Z"),
            "new": _snap("new", T1, T2, ko, "2026-09-28T17:50:00Z"),
        }
    }
    changes = si.plan_identity("shadow", files, snaps)
    assert set(changes) == {(DATE, "old")}
    assert changes[(DATE, "old")]["state"] == "WITHDRAWN"
    assert changes[(DATE, "old")]["withdrawn_for"] == "new"


def test_one_event_in_two_dates_files_is_counted_once_where_last_seen() -> None:
    # Basketball 15132383: 10-02 23:05Z, moved to 10-03 00:00Z.
    d1, d2 = "2026-10-02", "2026-10-03"
    rec = _rec(
        "Regatas Corrientes",
        "Instituto Cordoba",
        17174375,
        "Regatas Corrientes",
        "Instituto Atlético Central Córdoba",
    )
    files = {d1: {"15132383": dict(rec)}, d2: {"15132383": dict(rec)}}
    snaps = {
        d1: {
            "15132383": _snap(
                "x",
                "Regatas Corrientes",
                "Instituto Cordoba",
                "2026-10-02T23:05:00Z",
                "2026-10-02T15:00:00Z",
            )
        },
        d2: {
            "15132383": _snap(
                "x",
                "Regatas Corrientes",
                "Instituto Cordoba",
                "2026-10-03T00:00:00Z",
                "2026-10-02T23:30:00Z",
            )
        },
    }
    changes = si.plan_identity("shadow", files, snaps)
    assert changes == {
        (d1, "15132383"): {
            "state": "MOVED_TO:2026-10-03",
            "identity_reason": "the event's last snapshot is in 2026-10-03's file",
        }
    }
    moved = si.apply_change(files[d1]["15132383"], changes[(d1, "15132383")])
    assert moved["pre_identity_state"] == "SETTLED"
    assert moved["moved_from_state"] == "SETTLED"
    # Idempotent: nothing more to change once applied ...
    files[d1]["15132383"] = moved
    assert si.plan_identity("shadow", files, snaps) == {}
    # ... and reverted when the doubt is gone.
    del snaps[d2]["15132383"]
    revert = si.plan_identity("shadow", files, snaps)
    assert revert == {(d1, "15132383"): {"state": "SETTLED"}}
    back = si.apply_change(moved, revert[(d1, "15132383")])
    assert back["state"] == "SETTLED" and "pre_identity_state" not in back


def test_a_moved_coupon_leg_is_graded_from_the_later_file(tmp_path: Path) -> None:
    d1, d2 = "2026-10-02", "2026-10-03"
    result = {
        "state": "SETTLED",
        "t1_periods": [17, 12, 18, 26],
        "t2_periods": [12, 19, 16, 16],
        "t1_full": 73,
        "t2_full": 63,
        "overtime": False,
        "winner": "T1",
    }
    leg = {
        "superbet_event_id": "15132383",
        "market_id": 230585,  # winner incl. overtime (basketball)
        "family": "winner",
        "period": 0,
        "subject": "",
        "line": None,
        "side": "T1",
        "odds": 1.5,
        "kickoff_utc": "2026-10-02T23:05:00Z",
        "source_date": d1,
    }
    if 230585 not in shadow.MARKETS["basketball"]:
        leg["market_id"] = next(
            m for m, s in shadow.MARKETS["basketball"].items() if s.kind == "winner"
        )
    for d, rec in ((d1, {"state": "MOVED_TO:2026-10-03"}), (d2, result)):
        day = sc.day_dir(str(tmp_path), "basketball", d)
        day.mkdir(parents=True)
        (day / "settled.json").write_text(json.dumps({"events": {"15132383": rec}}))
    settled_docs = sc.settled_for(str(tmp_path), "basketball", {d1})
    assert set(settled_docs) == {d1, d2}  # the moved-to file is loaded too
    (graded,) = sc.grade_coupon(
        {"sport": "basketball", "date": d1, "legs": [leg]}, settled_docs
    )
    assert graded["outcome"] == "WIN"
    # the target file not settled yet: pending, not lost
    (pending,) = sc.grade_coupon(
        {"sport": "basketball", "date": d1, "legs": [leg]}, {d1: settled_docs[d1]}
    )
    assert pending["outcome"] == "PENDING:PENDING"


def test_one_team_in_two_superbet_events_under_three_hours_is_in_doubt() -> None:
    # C5: CS2 10-05, Vitality Academy in two series at 10:30Z.
    ko = "2026-10-05T10:30:00Z"
    files = {
        DATE: {
            "x": {
                **_rec("Vitality Academy", "Alpha", 1, "Vitality Academy", "Alpha"),
            },
            "y": _rec("Vitality Academy", "Beta", None, "", ""),
        }
    }
    snaps = {
        DATE: {
            "x": _snap("x", "Vitality Academy", "Alpha", ko, "2026-10-05T10:00:00Z"),
            "y": _snap("y", "Vitality Academy", "Beta", ko, "2026-10-05T10:00:00Z"),
        }
    }
    changes = si.plan_identity("cs2", files, snaps)
    # The found match goes; the one never found grades nothing already.
    assert set(changes) == {(DATE, "x")}
    assert changes[(DATE, "x")]["state"] == "DUPLICATE_SUPERBET_TEAM"
    assert changes[(DATE, "x")]["duplicate_team_events"] == ["y"]
    # Four hours apart: two different series.
    snaps[DATE]["y"] = _snap(
        "y", "Vitality Academy", "Beta", "2026-10-05T14:30:00Z", "2026-10-05T14:00:00Z"
    )
    assert si.plan_identity("cs2", files, snaps) == {}


def test_two_series_of_one_team_told_apart_by_both_names_stay() -> None:
    # 10-02: Glitch in five BO1 series inside three hours, each found on
    # Sofascore with both names - measured 68 such series 10-01..10-04.
    files = {
        DATE: {
            "x": _rec("Glitch", "Sashi", 1, "GLITCH", "Sashi"),
            "y": _rec("Glitch", "Team Voca", 2, "GLITCH", "Team Voca"),
        }
    }
    snaps = {
        DATE: {
            "x": _snap(
                "x", "Glitch", "Sashi", "2026-10-02T10:00:00Z", "2026-10-02T09:50:00Z"
            ),
            "y": _snap(
                "y",
                "Glitch",
                "Team Voca",
                "2026-10-02T11:00:00Z",
                "2026-10-02T10:50:00Z",
            ),
        }
    }
    assert si.plan_identity("cs2", files, snaps) == {}


def test_the_settle_writes_the_identity_states(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    day = tmp_path / "shadow" / "hockey" / DATE
    # a second Superbet event with the same opponent at the same time
    other = json.loads((day / "snapshots.jsonl").read_text())
    other = {
        **other,
        "superbet_event_id": "2",
        "match_name": f"Someone·{T2}",
        "team1": "Someone",
    }
    with (day / "snapshots.jsonl").open("a") as fh:
        fh.write(json.dumps(other) + "\n")
    run_settle(
        tmp_path,
        FakeResolver(sofa_event()),
        FakeClient({**sofa_event(), **HOCKEY_AET}),
        6,
    )
    recs = settled(tmp_path)
    # The fake resolver refuses the second board (an ERROR, no match found):
    # the found game is in doubt, the other grades nothing and is retried.
    assert recs["1"]["state"] == "DUPLICATE_SUPERBET_TEAM"
    assert recs["1"]["pre_identity_state"] == "SETTLED"
    assert recs["1"]["duplicate_team_events"] == ["2"]
    assert recs["2"]["state"] == "ERROR"
    # final: a rerun keeps it
    again = run_settle(tmp_path, FakeResolver(sofa_event()), FakeClient({}), 30)
    assert again["metrics"]["hockey"]["metrics"]["kept"] == 1
    assert settled(tmp_path)["1"]["state"] == "DUPLICATE_SUPERBET_TEAM"


# --- B2: the searched team's own name ------------------------------------------

SLUG = {"hockey": "ice-hockey", "basketball": "basketball", "volleyball": "volleyball"}


def _resolver() -> SofaResolver:
    return SofaResolver(SofaConfig(), None, None)  # type: ignore[arg-type]


def _method(
    sport: str,
    t1: str,
    t2: str,
    home: str,
    away: str,
    gap_min: int = 0,
    team_ids: tuple[int, int] = (1, 2),
    searched_team_id: int | None = None,
) -> list[str | None]:
    """How the event matched with team1 searched, then team2 (find_event's
    order) - the opponent passed as resolve_entity normalises it."""
    ko = datetime(2026, 10, 3, 18, tzinfo=UTC)
    women = "W" in {superbet_gender(t1), superbet_gender(t2)}
    gender = "F" if women else "M"
    event = {
        "id": 1,
        "startTimestamp": int((ko + timedelta(minutes=gap_min)).timestamp()),
        "homeTeam": {"name": home, "gender": gender, "id": team_ids[0]},
        "awayTeam": {"name": away, "gender": gender, "id": team_ids[1]},
        "tournament": {"name": "x", "category": {"name": "y"}},
    }
    return [
        _resolver().match_method(
            event,
            ko,
            normalize_name(opponent),
            sport=sport,
            superbet_side_a=t1,
            superbet_side_b=t2,
            check_orientation=False,
            searched_team_id=searched_team_id,
        )
        for opponent in (t2, t1)
    ]


def test_hapoel_tel_aviv_is_not_maccabi_tel_aviv() -> None:
    # Under the old one-word rule "aviv" (4 letters) confirmed it.
    for sport in SLUG.values():
        assert _method(
            sport,
            "Bnei Herzliya",
            "Hapoel Tel Aviv",
            "Bnei Herzliya",
            "Maccabi Tel Aviv",
        ) == [None, None]
    assert {"aviv", "tel", "texas", "miami"} <= name_stopwords()


def test_u_de_santiago_is_not_universidad_catolica() -> None:
    # Basketball 17207292, 10-03: Colo Colo's name alone confirmed the game;
    # the searched team (the candidate 233778) never matched its own name.
    assert (
        _method(
            "basketball",
            "U. De Santiago",
            "Colo Colo",
            "Universidad Católica",
            "Colo Colo",
            team_ids=(233778, 208038),
            searched_team_id=233778,
        )[0]
        is None
    )
    assert _method(
        "basketball", "U. De Santiago", "Colo Colo", "Universidad Católica", "Colo Colo"
    ) == [None, None]


# True pairs SHADOW_SETTLE graded 10-01..10-04 (runs/sofa/shadow/*/2026-10-0[1-4]/
# settled.json, read 2026-10-05): (sport, team1, team2, home, away, gap min).
FROZEN_TRUE_PAIRS = [
    ("ice-hockey", "Linkoping", "Lulea", "Linköping HC", "Luleå Hockey", 0),
    (
        "ice-hockey",
        "Kometa Brno",
        "Mlada Boleslav",
        "HC Kometa Brno",
        "BK Mladá Boleslav",
        0,
    ),
    (
        "ice-hockey",
        "Prince Albert Raiders",
        "Red Deer Rebels",
        "Prince Albert Raiders",
        "Red Deer Rebels",
        60,
    ),
    ("ice-hockey", "Finlandia (K)", "Szwajcaria (K)", "Finland", "Switzerland", 0),
    (
        "ice-hockey",
        "N. Michigan Wildcats",
        "Miami RedHawks",
        "Northern Michigan Wildcats",
        "Miami Ohio Redhawks",
        0,
    ),
    (
        "ice-hockey",
        "Stars Kobe",
        "Nikko Kobe",
        "Stars Kobe",
        "H.C. Tochigi Nikko Ice Bucks",
        0,
    ),
    (
        "ice-hockey",
        "Anglet Hormadi",
        "Gothiques d’Amiens",
        "Anglet Hormadi Pays Basque",
        "Amiens Hockey Élite",
        0,
    ),
    (
        "ice-hockey",
        "Alaska Nanooks",
        "Boston Univ. Terriers",
        "Alaska Nanooks",
        "Boston University",
        0,
    ),
    ("basketball", "Quimsa", "Platense", "Quimsa Santiago del Estero", "Platense", 0),
    (
        "basketball",
        "Regatas Corrientes",
        "Instituto Cordoba",
        "Regatas Corrientes",
        "Instituto Atlético Central Córdoba",
        0,
    ),
    (
        "basketball",
        "Hiroshima Dragonflies",
        "Nishinomiya Storks",
        "Hiroshima Dragonflies",
        "Kobe Storks",
        0,
    ),
    (
        "basketball",
        "Rotterdam City",
        "ZZ Leiden",
        "Rotterdam City Basketball",
        "Zorg en Zekerheid Leiden",
        0,
    ),
    (
        "basketball",
        "Levhartice Chomutov (K)",
        "Avenir Chartres (K)",
        "Levhartice Chomutov",
        "C'Chartres Basket Feminin",
        0,
    ),
    (
        "basketball",
        "Kortrijk Spurs",
        "Donar Groningen",
        "House of Talents Spurs",
        "Donar Groningen",
        0,
    ),
    (
        "volleyball",
        "Weber State Wildcats (K)",
        "Portland St. (K)",
        "Weber State Wildcats",
        "Portland State Vikings",
        0,
    ),
    (
        "volleyball",
        "VC Gotha",
        "Volleyyoungstars Friedrichshafen",
        "Blue Volleys Gotha",
        "Volley YoungStars Friedrichshafen",
        0,
    ),
    ("volleyball", "America Montes Claros", "JF", "Montes Claros Vôlei", "JF Vôlei", 5),
    (
        "volleyball",
        "Texas AM Commerce Lions (K)",
        "New Orleans Privateers (K)",
        "Texas AM Commerce Lions",
        "New Orleans Privateers",
        0,
    ),
]


@pytest.mark.parametrize(
    ("sport", "t1", "t2", "home", "away", "gap"), FROZEN_TRUE_PAIRS
)
def test_true_pairs_of_10_01_to_10_04_are_still_accepted(
    sport: str, t1: str, t2: str, home: str, away: str, gap: int
) -> None:
    assert any(_method(sport, t1, t2, home, away, gap))


def test_football_and_tennis_never_reach_the_shadow_rule() -> None:
    # The relaxed / searched-name rule is SPORT_SCOPED_SEARCH only: football
    # keeps RESOLVE's strict opponent score and its verdict on this pair.
    resolver = _resolver()
    ko = datetime(2026, 10, 3, 18, tzinfo=UTC)
    event = {
        "id": 1,
        "startTimestamp": int(ko.timestamp()),
        "homeTeam": {"name": "Universidad Católica", "gender": "M"},
        "awayTeam": {"name": "Colo Colo", "gender": "M"},
        "tournament": {"name": "Primera", "category": {"name": "Chile"}},
    }
    kwargs: dict[str, Any] = {
        "superbet_side_a": "U. De Santiago",
        "superbet_side_b": "Colo Colo",
    }
    # football: the opponent's name alone, as before 2026-10-05
    assert (
        resolver.match_quality(event, ko, "colo colo", sport="football", **kwargs)
        is not None
    )
    assert (
        resolver.match_quality(event, ko, "colo colo", sport="basketball", **kwargs)
        is None
    )


class _Cache:
    def __init__(self) -> None:
        self.saved: list[dict[str, Any]] = []

    def get_entity(self, sport: str, key: str) -> None:
        return None

    def get_entity_miss(self, sport: str, key: str) -> bool:
        return False

    def get_entity_events(self, eid: int, kind: str, page: int) -> Any:
        return None

    def get_listing_miss(self, eid: int, kind: str, page: int) -> bool:
        return False

    def save_entity_events(self, *a: Any) -> None:
        pass

    def save_listing_miss(self, *a: Any) -> None:
        pass

    def save_entity_miss(self, *a: Any) -> None:
        pass

    def clear_entity_miss(self, *a: Any) -> None:
        pass

    def save_entity(self, **kw: Any) -> None:
        self.saved.append(kw)


class _Client:
    def __init__(self, event: dict[str, Any]) -> None:
        self.event = event

    def search(self, q: str, sport: str | None = None) -> dict[str, Any]:
        return {
            "results": [
                {
                    "type": "team",
                    "entity": {
                        "id": 10,
                        "name": "Hiroshima Dragonflies",
                        "sport": {"slug": "basketball"},
                        "gender": "M",
                    },
                }
            ]
        }

    def entity_events(self, eid: int, kind: str, page: int) -> dict[str, Any]:
        return {"events": [self.event]}


@pytest.mark.parametrize(
    ("away", "method", "cached"),
    [("Nishinomiya Storks", "NAME", True), ("Kobe Storks", "SHARED_WORD", False)],
)
def test_only_a_match_of_both_names_is_cached_as_verified(
    away: str, method: str, cached: bool
) -> None:
    ko = datetime(2026, 10, 3, 18, tzinfo=UTC)
    event = {
        "id": 5,
        "startTimestamp": int(ko.timestamp()),
        "homeTeam": {"name": "Hiroshima Dragonflies", "gender": "M", "id": 10},
        "awayTeam": {"name": away, "gender": "M", "id": 11},
        "tournament": {"name": "B.League", "category": {"name": "Japan"}},
    }
    cache = _Cache()
    resolver = SofaResolver(SofaConfig(), _Client(event), cache)  # type: ignore[arg-type]
    _, found, ambiguous = resolver.resolve_entity(
        "basketball",
        "Hiroshima Dragonflies",
        ko,
        "Nishinomiya Storks",
        board_side_a="Hiroshima Dragonflies",
        board_side_b="Nishinomiya Storks",
        record_miss=False,
        check_orientation=False,
    )
    assert found is not None and found["_match_method"] == method
    assert "_match_method" not in event  # the cached listing is never written
    assert bool(cache.saved) is cached


def test_the_purge_removes_only_the_named_alias(tmp_path: Path) -> None:
    db = tmp_path / "sofa.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE sofa_entity (sport TEXT, query_key TEXT, sofascore_id INTEGER,"
        " sofascore_name TEXT, entity_type TEXT, country TEXT, status TEXT,"
        " verified_at TEXT, last_used_at TEXT, hit_count INTEGER,"
        " PRIMARY KEY (sport, query_key))"
    )
    rows = [
        ("basketball", "u. de santiago", 233778, "Universidad Católica"),
        ("basketball", "colo colo", 208038, "Colo Colo"),
        ("basketball", "nishinomiya storks", 99, "Kobe Storks"),
    ]
    for sport, key, sid, name in rows:
        conn.execute(
            "INSERT INTO sofa_entity VALUES (?, ?, ?, ?, 'team', NULL, 'verified',"
            " NULL, NULL, 0)",
            (sport, key, sid, name),
        )
    conn.commit()
    conn.close()

    def keys() -> set[str]:
        c = sqlite3.connect(db)
        try:
            return {r[0] for r in c.execute("SELECT query_key FROM sofa_entity")}
        finally:
            c.close()

    assert purge_entity_alias.main(["--db", str(db), "--dry-run"]) == 0
    assert len(keys()) == 3
    assert purge_entity_alias.main(["--db", str(db), "--list-suspects"]) == 0
    # an id that does not match removes nothing
    assert purge_entity_alias.main(["--db", str(db), "--sofascore-id", "1"]) == 0
    assert len(keys()) == 3
    assert purge_entity_alias.main(["--db", str(db)]) == 0
    assert keys() == {"colo colo", "nishinomiya storks"}


# --- B3 / B5 / B6 / D-b: one shadow game ----------------------------------------


def _prev(tmp_path: Path, rec: dict[str, Any]) -> None:
    day = tmp_path / "shadow" / "hockey" / DATE
    (day / "settled.json").write_text(json.dumps({"events": {"1": rec}}))


def test_a_pinned_id_is_asked_directly_never_searched(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    _prev(
        tmp_path,
        {
            "state": "PENDING",
            "sofascore_event_id": 700,
            "home_is_team1": True,
            "orientation_unclear": False,
        },
    )
    resolver = FakeResolver(None)  # a search would find nothing
    client = FakeClient({**sofa_event(), **HOCKEY_AET})
    run_settle(tmp_path, resolver, client, 6)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "SETTLED" and rec["pinned_id"] is True
    assert resolver.calls == [] and client.asked == [700]


def test_a_search_contradicting_the_pinned_id_is_id_changed(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    _prev(tmp_path, {"state": "PENDING", "sofascore_event_id": 701})
    # the pinned id answers nothing; the search finds 700
    run_settle(tmp_path, FakeResolver(sofa_event()), FakeClient({}), 6)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "ID_CHANGED"
    assert rec["sofascore_event_id"] == 701
    assert rec["searched_sofascore_event_id"] == 700
    assert "graded" not in rec


def test_id_changed_keeps_the_grades_already_on_file(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    graded = [{"family": "total", "outcome": "WIN"}]
    _prev(
        tmp_path,
        {
            "state": "SETTLED",
            "sofascore_event_id": 701,
            "player_retry": True,
            "graded": graded,
        },
    )
    run_settle(tmp_path, FakeResolver(sofa_event()), FakeClient({}), 6)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "SETTLED" and rec["graded"] == graded
    assert rec["id_changed_to"] == 700 and rec["player_retry"] is False


def _status(description: str) -> dict[str, Any]:
    return {"status": {"type": "finished", "description": description}}


def test_an_unusual_status_is_graded_when_the_score_adds_up(tmp_path: Path) -> None:
    # Hockey 15025409, 10-02: "finished" / "Halftime".
    write_snapshot(tmp_path)
    detail = {**sofa_event(), **HOCKEY_AET, **_status("Halftime")}
    run_settle(tmp_path, FakeResolver(sofa_event()), FakeClient(detail), 6)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "SETTLED" and rec["status_unusual"] == "Halftime"


def test_an_unusual_status_that_does_not_add_up_is_asked_again(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    broken = json.loads(
        json.dumps({**sofa_event(), **HOCKEY_AET, **_status("Halftime")})
    )
    del broken["homeScore"]["period3"], broken["awayScore"]["period3"]
    run_settle(tmp_path, FakeResolver(sofa_event()), FakeClient(broken), 6)
    assert settled(tmp_path)["1"]["state"] == "UNUSUAL"
    # retryable: the next run asks again (pinned) and grades the corrected game
    client = FakeClient({**sofa_event(), **HOCKEY_AET})
    run_settle(tmp_path, FakeResolver(None), client, 8)
    assert settled(tmp_path)["1"]["state"] == "SETTLED" and client.asked == [700]


@pytest.mark.parametrize(
    "detail",
    [
        _status("Walkover"),
        {**_status("Ended"), "isAwarded": True},
        _status("Retired"),
    ],
)
def test_an_awarded_match_is_final_and_a_refund(tmp_path: Path, detail: dict) -> None:
    write_snapshot(tmp_path)
    run_settle(
        tmp_path,
        FakeResolver(sofa_event()),
        FakeClient({**sofa_event(), **HOCKEY_AET, **detail}),
        6,
    )
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "AWARDED" and "graded" not in rec
    leg = {"superbet_event_id": "1", "kickoff_utc": "2026-09-28T16:00:00Z"}
    (out,) = sc.grade_coupon(
        {"sport": "hockey", "date": DATE, "legs": [leg]},
        {DATE: {"events": {"1": rec}}},
    )
    assert out["outcome"] == "VOID"


def test_ids_that_disagree_with_the_listing_grade_only_the_totals(
    tmp_path: Path,
) -> None:
    write_snapshot(tmp_path)
    listed = {
        **sofa_event(),
        "homeTeam": {"name": T1, "id": 1},
        "awayTeam": {"name": T2, "id": 2},
    }
    detail = {
        **listed,
        **HOCKEY_AET,
        "homeTeam": {"name": T1, "id": 3},
        "awayTeam": {"name": T2, "id": 2},
    }
    run_settle(tmp_path, FakeResolver(listed), FakeClient(detail), 6)
    rec = settled(tmp_path)["1"]
    assert rec["orientation_check"] == "IDS_DIFFER"
    assert rec["orientation_unclear"] is True and rec["home_is_team1"] is None
    assert {g["family"] for g in rec["graded"]} == {"total"}


def test_every_match_records_its_evidence(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    run_settle(
        tmp_path,
        FakeResolver(sofa_event()),
        FakeClient({**sofa_event(), **HOCKEY_AET}),
        6,
    )
    rec = settled(tmp_path)["1"]
    assert rec["name_scores"] == {"team1": 100.0, "team2": 100.0}
    assert rec["start_gap_h"] == 0.0
    assert rec["matched_at_utc"] == "2026-09-28T22:00:00Z"
    assert "match_method" in rec  # the fake resolver says nothing: None
    assert rec["team1"] == T1 and rec["last_snapshot_utc"] == "2026-09-28T15:00:00Z"


# --- B7 -------------------------------------------------------------------------


def test_the_sweep_picks_only_days_with_a_waiting_game(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    assert settle_shadow.waiting_sports(str(tmp_path), DATE) == ["hockey"]
    _prev(tmp_path, {"state": "SETTLED"})
    assert settle_shadow.waiting_sports(str(tmp_path), DATE) == []
    _prev(tmp_path, {"state": "UNUSUAL"})
    assert settle_shadow.waiting_sports(str(tmp_path), DATE) == ["hockey"]
    _prev(tmp_path, {"state": "SETTLED", "player_retry": True})
    assert settle_shadow.waiting_sports(str(tmp_path), DATE) == ["hockey"]
    _prev(tmp_path, {"state": "DUPLICATE_SOFASCORE_ID"})
    assert settle_shadow.waiting_sports(str(tmp_path), DATE) == []


# --- C1-C4: CS2 -----------------------------------------------------------------


def test_a_series_far_from_superbets_time_while_still_quoted_is_ambiguous() -> None:
    # Review 2026-10-04: Hotu - Black Phoenix 12:15 on Sofascore, Superbet
    # 18:00 and quoting at 17:30.
    sofa_start = datetime(2026, 10, 4, 12, 15, tzinfo=UTC)
    kickoff = datetime(2026, 10, 4, 18, 0, tzinfo=UTC)
    quoted = [{"fetched_at_utc": "2026-10-04T17:30:00Z"}]
    assert settle_cs2.ambiguous_start(sofa_start, kickoff, quoted)
    # quoted only before Sofascore's start: Superbet merely had a late time
    assert not settle_cs2.ambiguous_start(
        sofa_start, kickoff, [{"fetched_at_utc": "2026-10-04T12:00:00Z"}]
    )
    # within the hour: the same series
    assert not settle_cs2.ambiguous_start(
        kickoff - timedelta(minutes=50), kickoff, quoted
    )


def test_ambiguous_start_is_recorded_and_never_graded(tmp_path: Path) -> None:
    cs2_stages.write_snapshot(tmp_path)  # kickoff 15:00, quoted 12:00
    sofa = cs2_stages.FakeSofascore()
    early = cs2_stages.KICKOFF - timedelta(hours=4)
    sofa._event = lambda base=sofa._event: {
        **base(),
        "startTimestamp":  # type: ignore[method-assign]
        int(early.timestamp()),
    }
    snap_path = tmp_path / "cs2" / cs2_stages.DATE / "snapshots.jsonl"
    rec = json.loads(snap_path.read_text())
    rec["fetched_at_utc"] = "2026-09-26T14:00:00Z"  # 3 h after Sofascore's start
    snap_path.write_text(json.dumps(rec) + "\n")
    cs2_stages.run_settle(tmp_path, sofa, 6)
    out = cs2_stages.settled(tmp_path)["1"]
    assert out["state"] == "AMBIGUOUS_START" and out["start_gap_h"] == -4.0
    assert "graded" not in out


def test_a_pinned_series_id_is_asked_directly(tmp_path: Path) -> None:
    cs2_stages.write_snapshot(tmp_path)
    no_stats = [
        dict(g, hasCompleteStatistics=False) for g in cs2_stages.FakeSofascore().games
    ]
    cs2_stages.run_settle(tmp_path, cs2_stages.FakeSofascore(games=no_stats), 50)
    first = cs2_stages.settled(tmp_path)["1"]
    assert first["match_method"] == "NAME" and first["pending_sides"] == 2
    # the listing is gone; the pinned id still answers
    sofa = cs2_stages.FakeSofascore(listed=False)
    cs2_stages.run_settle(tmp_path, sofa, 60)
    rec = cs2_stages.settled(tmp_path)["1"]
    assert rec["pinned_id"] is True and rec["pending_sides"] == 0
    assert not any(c.startswith("search") for c in sofa.calls)
    assert rec["name_scores"] == {"team1": 100.0, "team2": 100.0}


def test_a_series_search_contradicting_the_pinned_id_is_id_changed(
    tmp_path: Path,
) -> None:
    cs2_stages.write_snapshot(tmp_path)
    day = tmp_path / "cs2" / cs2_stages.DATE
    (day / "settled.json").write_text(
        json.dumps({"events": {"1": {"state": "PENDING", "sofascore_event_id": 901}}})
    )
    cs2_stages.run_settle(tmp_path, cs2_stages.FakeSofascore(event_answers=False), 6)
    rec = cs2_stages.settled(tmp_path)["1"]
    assert rec["state"] == "ID_CHANGED" and rec["searched_sofascore_event_id"] == 900


def test_an_ex_roster_is_not_its_organisation() -> None:
    assert cs2.esports_score("ex fingers crossed", "fingers crossed") == 0.0
    assert (
        cs2.esports_score(
            cs2.esports_name("ex-Zero Tenacity"), cs2.esports_name("ex-Zero Tenacity")
        )
        == 100.0
    )


def test_a_map_never_played_is_a_refund() -> None:
    maps = [cs2.MapResult(13, 5, {}), cs2.MapResult(13, 9, {})]  # 2-0
    leg = {
        "superbet_event_id": "1",
        "family": "map_rounds_total",
        "map_nr": 3,
        "subject": "",
        "line": 21.5,
        "side": "OVER",
        "odds": 1.8,
        "team1": "A",
        "team2": "B",
    }
    ev = {"state": "SETTLED", "maps": [[m.t1_rounds, m.t2_rounds] for m in maps]}
    assert sc._grade_leg("cs2", leg, ev) == "VOID"
    # ...also on a series graded from its score alone
    assert sc._grade_leg("cs2", leg, {**ev, "series_only": True}) == "VOID"
    snap = cs2.SnapshotEvent("1", "A·B", "A", "B", "2026-10-01T10:00:00Z", None)
    for side, odds in (("OVER", 1.8), ("UNDER", 1.95)):
        line = cs2.Cs2Line("1", "map_rounds_total", 3, "", 21.5, side, odds)
        key = (line.family, 3, "", 21.5, side)
        snap.sides[key] = line  # type: ignore[index]
        snap.fetched_at[key] = "2026-10-01T09:00:00Z"  # type: ignore[index]
    rows, counts = cs2.settle_event(snap, maps)
    assert rows == [] and counts["void"] == 2 and counts["ungradeable"] == 0


# --- D-a: the audit -------------------------------------------------------------


def test_the_identity_audit_names_every_doubt(tmp_path: Path) -> None:
    day = tmp_path / "shadow" / "hockey" / DATE
    day.mkdir(parents=True)
    base = {
        "state": "SETTLED",
        "home_is_team1": True,
        "kickoff_utc": "2026-09-28T16:00:00Z",
    }
    events = {
        "1": {
            **base,
            "match_name": f"{T1}·{T2}",
            "sofascore_event_id": 5,
            "sofascore_match": f"{T1} - {T2}",
            "sofascore_start_utc": "2026-09-28T16:00:00Z",
        },
        "2": {
            **base,
            "match_name": f"Someone·{T2}",
            "sofascore_event_id": 5,
            "sofascore_match": f"{T1} - {T2}",
            "sofascore_start_utc": "2026-10-01T10:00:00Z",
        },
        "3": {"state": "DUPLICATE_SOFASCORE_ID", "match_name": "x·y"},
        "4": {
            "state": "ID_CHANGED",
            "match_name": "x·y",
            "searched_sofascore_event_id": 9,
        },
        "5": {
            **base,
            "match_name": "Hiroshima Dragonflies·Nishinomiya Storks",
            "sofascore_event_id": 6,
            "sofascore_match": "Hiroshima Dragonflies - Kobe Storks",
            "match_method": "SHARED_WORD",
        },
    }
    (day / "settled.json").write_text(json.dumps({"events": events}))
    findings = audit_settle_identity.run(
        str(tmp_path), str(tmp_path / "none.db"), DATE, DATE, ("hockey",)
    )
    checks = {(f["check"], f["superbet_event_id"]) for f in findings}
    assert ("ID_USED_TWICE", "1") in checks and ("ID_USED_TWICE", "2") in checks
    assert ("MOVED_GRADED", "2") in checks
    assert ("NAME_BELOW", "2") in checks
    assert ("IDENTITY_STATE", "3") in checks and ("ID_CHANGED", "4") in checks
    by_design = [f for f in findings if f["superbet_event_id"] == "5"]
    assert [f["check"] for f in by_design] == ["NAME_BELOW_BY_DESIGN"]
    assert not audit_settle_identity.is_failure(by_design[0])
    # clean: nothing
    (day / "settled.json").write_text(json.dumps({"events": {"1": events["1"]}}))
    assert (
        audit_settle_identity.run(
            str(tmp_path), str(tmp_path / "none.db"), DATE, DATE, ("hockey",)
        )
        == []
    )


def test_old_records_without_the_new_fields_read_as_before() -> None:
    old = {
        "match_name": f"{T1}·{T2}",
        "sofascore_match": f"{T2} - {T1}",
        "home_is_team1": False,
        "state": "SETTLED",
    }
    assert si.record_name_scores("shadow", old) == {"team1": 100.0, "team2": 100.0}
    assert si.record_name_scores("shadow", {"state": "NOT_ON_SOFASCORE"}) is None


def test_a_settle_two_days_back_does_not_revert_a_moved_mark(tmp_path: Path) -> None:
    """Review 2026-10-05: settling D-2 rewrote D-1 without D's snapshot in
    view and reverted D-1's MOVED_TO:D every morning (double counting)."""
    import json as _json

    from bet.sofa import settle_identity as sid

    def dd(d: str) -> Path:
        p = tmp_path / d
        p.mkdir(exist_ok=True)
        return p

    def snap(d: str, at: str) -> None:
        with open(dd(d) / "snaps.jsonl", "a") as f:
            f.write(_json.dumps({"superbet_event_id": "E", "fetched_at_utc": at,
                                 "kickoff_utc": "2026-10-03T23:30:00Z",
                                 "team1": "A Team", "team2": "B Team"}) + "\n")

    snap("2026-10-02", "2026-10-02T10:00:00Z")
    snap("2026-10-03", "2026-10-03T20:00:00Z")
    rec = {"state": "SETTLED", "sofascore_event_id": 1,
           "match_name": "A Team · B Team",
           "sofascore_match": "A Team - B Team", "home_is_team1": True}
    for d in ("2026-10-01", "2026-10-02", "2026-10-03"):
        (dd(d) / "settled.json").write_text(_json.dumps(
            {"date": d, "events": {} if d == "2026-10-01" else {"E": dict(rec)}}))

    def settle(date: str) -> None:
        ev = sid.load_events(dd(date) / "settled.json")
        snaps = sid.load_snaps(date, dd, "snaps.jsonl")
        done, _ = sid.reconcile("shadow", date, ev, dd, "settled.json", snaps)
        (dd(date) / "settled.json").write_text(_json.dumps({"date": date, "events": done}))
        sid.reconcile_neighbours("shadow", date, done, dd, "settled.json", snaps)

    def state(d: str) -> str:
        return str(sid.load_events(dd(d) / "settled.json")["E"]["state"])

    settle("2026-10-03")
    assert state("2026-10-02") == "MOVED_TO:2026-10-03"
    settle("2026-10-01")  # the morning's D-2 settle
    assert state("2026-10-02") == "MOVED_TO:2026-10-03"
    assert state("2026-10-03") == "SETTLED"
