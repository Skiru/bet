"""bet.sofa.entity_map - the one Superbet -> Sofascore entity map (identity
plan K1): what SPORT_IDENTITY learns, what it queues, and that a learned row
is read only from epochs.ENTITY_MAP_FROM_UTC."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import entity_map as em
from bet.sofa import epochs, resolve
from bet.sofa import sport_identity as si
from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.db import get_connection, migrate
from bet.sofa.player_model import resolve_team

BEFORE = "2026-10-14T12:00:00Z"
AFTER = "2026-10-15T06:00:00Z"
AT = "2026-10-14T12:00:00Z"


def _db(tmp_path: Path) -> sqlite3.Connection:
    path = str(tmp_path / "sofa.db")
    migrate(path)
    return get_connection(path)


def _rec(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "superbet_event_id": "1",
        "sport": "basketball",
        "status": "IDENTIFIED",
        "team1": "Spartak Subotica",
        "team2": "Hapoel Holon",
        "sofascore_event_id": 16611512,
        "home_id": 174744,
        "away_id": 3510,
        "home_is_team1": True,
        "match_method": "LISTING_NAMES",
        "name_scores": {"team1": 90.0, "team2": 100.0},
        "sofascore_match": "KK Spartak Office Shoes - Hapoel Holon",
        "sofascore_home": "KK Spartak Office Shoes",
        "sofascore_away": "Hapoel Holon",
        "competition_id": 138,
        "tournament": "Liga Mistrzów - gr.F",
        "sofascore_tournament": "Basketball Champions League",
    }
    base.update(kw)
    return base


def _row(conn: sqlite3.Connection, slug: str, key: str) -> tuple[Any, ...] | None:
    r = conn.execute(
        "SELECT sofascore_id, source, evidence_event_id FROM sofa_entity"
        " WHERE sport = ? AND query_key = ?",
        (slug, key),
    ).fetchone()
    return None if r is None else tuple(r)


def test_threshold_is_resolves() -> None:
    assert em.NAME_MATCH_THRESHOLD == resolve.NAME_MATCH_THRESHOLD


def test_the_switch_is_next_days_midnight_on_day_and_clock() -> None:
    assert epochs.ENTITY_MAP_FROM_UTC == datetime(2026, 10, 15, tzinfo=UTC)
    on = datetime(2026, 10, 15, 0, 1, tzinfo=UTC)
    off = datetime(2026, 10, 14, 23, 59, tzinfo=UTC)
    assert epochs.entity_map("2026-10-15", on)
    assert not epochs.entity_map("2026-10-15", off)
    assert not epochs.entity_map("2026-10-14", on)  # a built day is never re-read
    assert epochs.entity_map(None, on) and not epochs.entity_map(None, off)


def test_record_sides_follow_the_orientation() -> None:
    straight = em.record_sides(_rec())
    assert [(s.name, s.sofascore_id, s.sofascore_name, s.score) for s in straight] == [
        ("Spartak Subotica", 174744, "KK Spartak Office Shoes", 90.0),
        ("Hapoel Holon", 3510, "Hapoel Holon", 100.0),
    ]
    crossed = em.record_sides(_rec(home_is_team1=False))
    assert [(s.name, s.sofascore_id, s.sofascore_name) for s in crossed] == [
        ("Spartak Subotica", 3510, "Hapoel Holon"),
        ("Hapoel Holon", 174744, "KK Spartak Office Shoes"),
    ]
    # the names split back out of sofascore_match for an older record
    old = em.record_sides(_rec(sofascore_home=None, sofascore_away=None))
    assert old[0].sofascore_name == "KK Spartak Office Shoes"
    assert em.record_sides(_rec(status="NOT_IDENTIFIED")) == []


def test_only_a_side_its_own_name_confirmed_is_learnable() -> None:
    s = em.record_sides(_rec())[0]
    assert em.name_confirmed(s)
    weak = em.record_sides(_rec(match_method="LISTING_ID_AND_OPPONENT"))[0]
    assert not em.name_confirmed(weak)
    low = em.record_sides(_rec(name_scores={"team1": 82.0, "team2": 100.0}))[0]
    assert not em.name_confirmed(low)  # the threshold itself is not above it


def test_learn_new_same_and_conflict(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    side = em.record_sides(_rec())[0]
    assert em.learn(conn, side, AT) == em.LEARNED
    assert _row(conn, "basketball", "spartak subotica") == (
        174744,
        "identity_names",
        16611512,
    )
    assert em.learn(conn, side, AT) == em.ALREADY_HELD
    other = em.Side(
        "basketball",
        "Spartak Subotica",
        999,
        "Spartak Moscow",
        5,
        95.0,
        "LISTING_NAMES",
    )
    assert em.learn(conn, other, AT) == em.CONFLICT
    assert (
        _row(conn, "basketball", "spartak subotica")[0] == 174744
    )  # never overwritten
    q = conn.execute(
        "SELECT held_id, offered_id, evidence_event_id, status"
        " FROM sofa_entity_conflict"
    ).fetchall()
    assert [tuple(r) for r in q] == [(174744, 999, 5, "OPEN")]
    # hockey lives under Sofascore's slug, as RESOLVE / SHADOW_SETTLE write it
    hk = em.Side("hockey", "Ritten", 7, "Rittner Buam", 9, 100.0, "LISTING_NAMES")
    em.learn(conn, hk, AT)
    assert _row(conn, "ice-hockey", "ritten") is not None


def test_learn_records_once_per_event_with_candidates_and_tournaments(
    tmp_path: Path,
) -> None:
    conn = _db(tmp_path)
    weak = _rec(
        superbet_event_id="2",
        sofascore_event_id=17117429,
        team1="Kavkasia",
        team2="Lausanne",
        home_id=1,
        away_id=2,
        match_method="LISTING_ID_AND_OPPONENT",
        name_scores={"team1": 40.0, "team2": 100.0},
        sofascore_home="BC CIU",
        sofascore_away="Pully Lausanne Foxes",
        competition_id=21144,
        tournament="Europe Cup",
    )
    counts = em.learn_records(conn, [_rec(), weak, _rec()], AT)
    assert counts["events"] == 2  # the repeated record teaches nothing twice
    assert counts[em.LEARNED] == 2  # both sides of the name-matched event
    assert counts[em.CANDIDATE] == 2  # opponent rule: queued, not learned
    assert _row(conn, "basketball", "kavkasia") is None
    cand = conn.execute(
        "SELECT superbet_name, candidate_id, candidate_name, reason"
        " FROM sofa_entity_candidate ORDER BY candidate_id"
    ).fetchall()
    assert [tuple(r) for r in cand] == [
        ("Kavkasia", 1, "BC CIU", "LISTING_ID_AND_OPPONENT"),
        ("Lausanne", 2, "Pully Lausanne Foxes", "LISTING_ID_AND_OPPONENT"),
    ]
    tours = conn.execute(
        "SELECT superbet_tournament, competition_id, events"
        " FROM sofa_tournament_map ORDER BY competition_id"
    ).fetchall()
    assert [tuple(r) for r in tours] == [
        ("Liga Mistrzów - gr.F", 138, 1),
        ("Europe Cup", 21144, 1),
    ]
    assert em.learn_records(conn, [_rec()], AT)["events"] == 0  # a later run too


def test_a_learned_row_is_read_only_with_learned(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    em.learn(conn, em.record_sides(_rec())[0], AT)
    conn.execute(
        "INSERT INTO sofa_entity (sport, query_key, sofascore_id,"
        " sofascore_name, entity_type, status) VALUES"
        " ('basketball', 'old name', 5, 'Old', 'team', 'verified')"
    )
    assert resolve_team(conn, "basketball", "Spartak Subotica", {}) is None
    assert resolve_team(conn, "basketball", "Spartak Subotica", {}, True) == 174744
    assert resolve_team(conn, "basketball", "Old Name", {}) == 5  # legacy: as before
    off = si.TeamResolver(conn, 0)
    on = si.TeamResolver(conn, 0, learned=True)
    assert off.team_id("basketball", "Spartak Subotica") is None
    assert on.team_id("basketball", "Spartak Subotica") == 174744


def test_a_database_without_the_k1_columns_reads_as_before() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE sofa_entity (sport TEXT, query_key TEXT,"
        " sofascore_id INT, status TEXT)"
    )
    conn.execute("INSERT INTO sofa_entity VALUES ('basketball', 'a', 1, 'verified')")
    assert em.verified_id(conn, "basketball", "a", False) == 1
    assert em.learned_id(conn, "basketball", "a") is None


def test_cs2_reads_only_learned_rows_never_backfills(tmp_path: Path) -> None:
    conn = _db(tmp_path)  # cs2_series exists, empty (migrate)
    # backfill_cs2's own verified row (the NIP Impact defect) is never read
    conn.execute(
        "INSERT INTO sofa_entity (sport, query_key, sofascore_id,"
        " sofascore_name, entity_type, status, source) VALUES"
        " ('cs2', 'ninjas in pyjamas', 448738, 'NIP Impact', 'team',"
        " 'verified', 'backfill_cs2')"
    )
    em.learn(
        conn,
        em.Side(
            "cs2", "Overtake", 1221658, "Overtake Sector", 3, 100.0, "CS2_PICK_EVENT"
        ),
        AT,
    )
    off, on = si.TeamResolver(conn, 0), si.TeamResolver(conn, 0, learned=True)
    assert off.team_id("cs2", "Overtake") is None
    assert on.team_id("cs2", "Overtake") == 1221658
    assert on.team_id("cs2", "Ninjas in Pyjamas") is None


def _cache(tmp_path: Path) -> SofaCache:
    return SofaCache(SofaConfig(db_path=str(tmp_path / "c.db"), runs_dir=str(tmp_path)))


def test_cache_hides_learned_rows_until_the_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = _cache(tmp_path)
    with get_connection(cache.config.db_path) as conn:
        em.learn(conn, em.record_sides(_rec())[0], AT)
        conn.commit()
    monkeypatch.setenv("SOFA_NOW", BEFORE)
    assert cache.get_entity("basketball", "spartak subotica") is None
    monkeypatch.setenv("SOFA_NOW", AFTER)
    got = cache.get_entity("basketball", "spartak subotica")
    assert got is not None and got["sofascore_id"] == 174744


def test_save_entity_queues_another_id_and_keeps_the_held_one_from_the_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = _cache(tmp_path)
    monkeypatch.setenv("SOFA_NOW", BEFORE)
    cache.save_entity(
        "football",
        "wisla",
        1,
        "Wisła Kraków",
        "team",
        None,
        "verified",
        source="resolve",
    )
    cache.save_entity(
        "football",
        "wisla",
        2,
        "Wisła Płock",
        "team",
        None,
        "verified",
        source="resolve",
    )
    held = cache.get_entity("football", "wisla")
    assert held is not None and held["sofascore_id"] == 2  # before: overwritten
    monkeypatch.setenv("SOFA_NOW", AFTER)
    cache.save_entity(
        "football",
        "wisla",
        3,
        "Wisła Sandomierz",
        "team",
        None,
        "verified",
        source="resolve",
    )
    held = cache.get_entity("football", "wisla")
    assert held is not None and held["sofascore_id"] == 2  # after: kept
    with get_connection(cache.config.db_path) as conn:
        offers = [
            tuple(r)
            for r in conn.execute(
                "SELECT held_id, offered_id FROM sofa_entity_conflict"
                " ORDER BY offered_id"
            )
        ]
    assert offers == [(1, 2), (2, 3)]  # both recorded


def test_run_sport_identity_learn_reports_and_never_fails(tmp_path: Path) -> None:
    from scripts.sofa import run_sport_identity as rsi

    path = str(tmp_path / "sofa.db")
    migrate(path)
    doc = {
        "fixtures": [
            _rec(),
            _rec(superbet_event_id="9", sport="hockey", sofascore_event_id=4),
        ]
    }
    got = rsi.learn(path, doc, ["basketball"])
    assert got[em.LEARNED] == 2 and got["events"] == 1  # hockey not asked
    assert "error" in rsi.learn(str(tmp_path / "missing" / "x.db"), doc, ["basketball"])


def test_player_model_rows_by_name_carry_the_marker_only_when_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bet.sofa import player_model
    from tests.sofa.test_player_team_from_side import _forecast, make_db, traded_history

    db = tmp_path / "db.sqlite"
    traded_history(make_db(db))
    assert all("entity_map_rule" not in r for r in _forecast(db))  # 2026-09-28: off
    monkeypatch.setattr(
        epochs, "ENTITY_MAP_FROM_UTC", datetime(2026, 9, 28, tzinfo=UTC)
    )
    on = _forecast(db)
    assert on and {r["entity_map_rule"] for r in on} == {epochs.ENTITY_MAP_RULE}
    assert "entity_map_rule" in player_model.MODEL_KEYS


def test_resolve_tournaments_keyed_by_superbet_id_once_per_event(
    tmp_path: Path,
) -> None:
    conn = _db(tmp_path)
    rows = [
        ("football", 1643, 11535, "Primera División", 16317843),
        ("football", 1643, 11535, "Primera División", 16317843),
        ("football", 1643, 11535, "Primera División", 16317844),
        ("tennis", None, 9, "ITF", 5),
    ]
    assert em.learn_resolve_tournaments(conn, rows, AT) == 2  # no id: no key
    got = conn.execute(
        "SELECT sport, superbet_tournament, competition_id, events,"
        " superbet_tournament_id FROM sofa_tournament_map"
    ).fetchall()
    assert [tuple(r) for r in got] == [("football", "id:1643", 11535, 2, 1643)]


def test_run_resolve_tournament_write_never_fails_the_stage(tmp_path: Path) -> None:
    from scripts.sofa import run_resolve

    path = str(tmp_path / "sofa.db")
    migrate(path)
    assert run_resolve.learn_tournaments(path, [("football", 1, 2, "L", 3)]) == 1
    assert run_resolve.learn_tournaments(str(tmp_path / "no" / "x.db"), []) is None


def test_reteach_learns_a_newly_learnable_side_and_closes_its_candidate(
    tmp_path: Path,
) -> None:
    conn = _db(tmp_path)
    rec = _rec(
        match_method="LISTING_ID_AND_OPPONENT",
        name_scores={"team1": 40.0, "team2": 100.0},
        team1_id=174744,
    )
    side = em.record_sides(rec)[0]
    em.queue_candidate(conn, side, "LISTING_ID_AND_OPPONENT", AT)  # the old rule
    got = em.reteach_sides(conn, [rec], AT)
    assert got[em.LEARNED] == 1 and got["closed"] == 1
    assert _row(conn, "basketball", "spartak subotica")[0] == 174744
    st = conn.execute("SELECT status FROM sofa_entity_candidate").fetchone()[0]
    assert st == "HELD"


def test_manual_aliases_replace_a_held_id_and_close_the_queue_only_from_the_switch(
    tmp_path: Path,
) -> None:
    conn = _db(tmp_path)
    nip = em.Side(
        "cs2", "Ninjas in Pyjamas", 366560, "NIP", 17317278, 100.0, "CS2_PICK_EVENT"
    )
    conn.execute(
        "INSERT INTO sofa_entity (sport, query_key, sofascore_id,"
        " sofascore_name, entity_type, status, source) VALUES ('cs2',"
        " 'ninjas in pyjamas', 448738, 'NIP Impact', 'team', 'verified',"
        " 'backfill_cs2')"
    )
    assert em.learn(conn, nip, AT) == em.CONFLICT
    weak = em.Side(
        "basketball", "Takamatsu", 124602, "Kagawa Five Arrows", 1, 20.0, "DAY_ANCHOR"
    )
    em.queue_candidate(conn, weak, "DAY_ANCHOR", AT)
    other = em.Side("basketball", "Takamatsu", 999, "Other", 2, 20.0, "DAY_ANCHOR")
    em.queue_candidate(conn, other, "DAY_ANCHOR", AT)
    decisions = {
        "aliases": [
            {
                "sport": "cs2",
                "superbet_name": "Ninjas in Pyjamas",
                "sofascore_id": 366560,
                "sofascore_name": "NIP",
                "decided_by": "operator",
                "decided_at": "2026-10-15",
            },
            {
                "sport": "basketball",
                "superbet_name": "Takamatsu",
                "sofascore_id": 124602,
                "decided_by": "operator",
                "decided_at": "2026-10-15",
            },
        ],
        "rejected": [],
    }
    before = em.sync_manual(conn, decisions, AT, datetime(2026, 10, 14, 12, tzinfo=UTC))
    assert before["skipped_before_switch"] == 2
    assert _row(conn, "cs2", "ninjas in pyjamas")[0] == 448738  # untouched
    after = em.sync_manual(conn, decisions, AT, datetime(2026, 10, 15, 1, tzinfo=UTC))
    assert after["aliases"] == 2
    assert _row(conn, "cs2", "ninjas in pyjamas")[:2] == (366560, "manual")
    assert em.open_queue(conn) == {"conflicts": [], "candidates": []}
    states = dict(
        conn.execute("SELECT candidate_id, status FROM sofa_entity_candidate")
    )
    assert states == {124602: "ACCEPTED", 999: "SUPERSEDED"}


def test_load_manual_refuses_a_malformed_entry(tmp_path: Path) -> None:
    import json

    p = tmp_path / "a.json"
    assert em.load_manual(str(tmp_path / "none.json")) == {
        "aliases": [],
        "rejected": [],
    }
    p.write_text(
        json.dumps(
            {"aliases": [{"sport": "cs2", "superbet_name": "X", "sofascore_id": "12"}]}
        )
    )
    with pytest.raises(ValueError):
        em.load_manual(str(p))
    p.write_text(
        json.dumps(
            {
                "aliases": [
                    {
                        "sport": "darts",
                        "superbet_name": "X",
                        "sofascore_id": 1,
                        "decided_by": "o",
                        "decided_at": "2026-10-15",
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError):
        em.load_manual(str(p))
    real = em.load_manual()  # the shipped file parses
    assert set(real) == {"aliases", "rejected"}


def test_the_queue_report_lists_conflicts_and_candidates(tmp_path: Path) -> None:
    from scripts.sofa import report_entity_queue as rq

    conn = _db(tmp_path)
    em.queue_candidate(
        conn,
        em.Side(
            "basketball",
            "Takamatsu",
            124602,
            "Kagawa Five Arrows",
            16491061,
            20.0,
            "DAY_ANCHOR",
        ),
        "DAY_ANCHOR",
        AT,
    )
    md = rq.render(em.open_queue(conn), "2026-10-14", 10)
    assert "Kolejka mapy encji" in md and "Takamatsu" in md
    assert '"sofascore_id": 124602' in md and '"sport": "basketball"' in md
