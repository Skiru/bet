"""scripts/sofa/measure_team_identity.py - offline, on temp run dirs and a temp DB."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa import cs2_engine
from scripts.sofa import measure_team_identity as m


def _write(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _fixture(
    sb: str,
    sport: str,
    status: str,
    reason: str | None = None,
    tournament: str = "Liga",
    **kw: Any,
) -> dict[str, Any]:
    return {
        "superbet_event_id": sb,
        "sport": sport,
        "match_name": "A·B",
        "team1": kw.pop("team1", "A"),
        "team2": kw.pop("team2", "B"),
        "kickoff_utc": kw.pop("kickoff_utc", "2026-10-14T12:00:00Z"),
        "tournament": tournament,
        "status": status,
        "reason": reason,
        **kw,
    }


def test_parse_player_gap_reads_repr_names_and_reasons() -> None:
    assert m.parse_player_gap("player 'Castellanos, Taty' matched no squad member") == (
        "Castellanos, Taty",
        "NO_SQUAD_MATCH",
    )
    assert m.parse_player_gap(
        'player "O\'Neill, Aiden" named in 2 squads, never started'
    ) == ("O'Neill, Aiden", "NEVER_STARTED")
    assert m.parse_player_gap("player 'X' named in 1 squads, never came on") == (
        "X",
        "NEVER_CAME_ON",
    )
    assert m.parse_player_gap("player 'X' event 1 gap") is None
    assert m.parse_player_gap("Side A event 1 gap") is None


def test_resolve_gap_reason() -> None:
    assert m.resolve_gap_reason(0, False) == "GAP_NO_SIDE_KNOWN"
    assert m.resolve_gap_reason(1, True) == "GAP_ONE_SIDE_KNOWN_GAME_IN_LISTING"
    assert m.resolve_gap_reason(2, False) == "GAP_BOTH_SIDES_KNOWN_NO_GAME_IN_LISTING"


def test_fixture_item_states() -> None:
    ok = m.fixture_item(_fixture("1", "hockey", "IDENTIFIED"))
    assert (ok.state, ok.reason, ok.day) == (m.IDENTIFIED, None, "2026-10-14")
    bad = m.fixture_item(_fixture("2", "hockey", "NOT_IDENTIFIED", "NO_GAME_WITHIN_1H"))
    assert (bad.state, bad.reason) == (m.UNEXPLAINED, "NO_GAME_WITHIN_1H")
    dup = m.fixture_item(_fixture("3", "cs2", "DUPLICATE_SUPERBET_TEAM"))
    assert (dup.state, dup.reason) == (m.EXCLUDED, "DUPLICATE_SUPERBET_TEAM")
    loop = m.fixture_item(_fixture("4", "cs2", "IDENTIFIED", tournament="Winners 1x1"))
    assert (loop.state, loop.reason) == (m.EXCLUDED, "1x1")


def test_sport_fixture_records_keep_the_latest_record(tmp_path: Path) -> None:
    _write(
        tmp_path / "2026-10-13" / "sport_fixtures.json",
        {
            "created_at_utc": "x",
            "fixtures": [_fixture("1", "hockey", "NOT_IDENTIFIED", "BRIDGE_ABORTED")],
        },
    )
    _write(
        tmp_path / "2026-10-14" / "sport_fixtures.json",
        {"created_at_utc": "y", "fixtures": [_fixture("1", "hockey", "IDENTIFIED")]},
    )
    recs = m.sport_fixture_records(str(tmp_path))
    assert recs["1"]["status"] == "IDENTIFIED"


class _Resolver:
    def __init__(self, known: dict[str, int]) -> None:
        self.known = known

    def team_id(self, sport: str, name: str) -> int | None:
        return self.known.get(name)


def test_team_name_stats_learnable_and_conflicts() -> None:
    recs = [
        _fixture(
            "1",
            "basketball",
            "IDENTIFIED",
            team1="Known",
            team2="New",
            home_id=10,
            away_id=20,
            home_is_team1=True,
        ),
        _fixture(
            "2",
            "basketball",
            "IDENTIFIED",
            team1="Known",
            team2="Clash",
            home_id=10,
            away_id=30,
            home_is_team1=True,
        ),
        _fixture(
            "3",
            "basketball",
            "IDENTIFIED",
            team1="Clash",
            team2="Known",
            home_id=10,
            away_id=31,
            home_is_team1=False,
        ),
        _fixture(
            "4",
            "basketball",
            "NOT_IDENTIFIED",
            "TEAM_UNRESOLVED",
            team1="New",
            team2="Ghost",
        ),
    ]
    st = m.team_name_stats("basketball", recs, _Resolver({"Known": 10}))  # type: ignore[arg-type]
    assert st.names == 4
    assert st.unresolved_now == 3  # New, Clash, Ghost
    assert st.learnable == 1  # New -> 20; Clash -> {30, 31} is a conflict
    assert [k for k, _ in st.conflicts] == ["clash"]
    assert st.unresolved_in_unexplained == 2  # New, Ghost
    assert [nm for _, nm, _ in st.top_unlearnable] == ["Ghost"]


def _db(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute(
        "create table sofa_entity (sport text, query_key text, sofascore_id int,"
        " sofascore_name text, entity_type text, country text, status text)"
    )
    con.execute(
        "create table sofa_entity_events (sofascore_entity_id int, kind text,"
        " page int, fetched_at text, events_json text)"
    )
    con.execute(
        "insert into sofa_entity values ('football', 'known fc', 7, 'Known FC',"
        " 'team', null, 'verified')"
    )
    start = int(datetime(2026, 10, 14, 12, tzinfo=UTC).timestamp())
    events = {
        "events": [
            {
                "id": 99,
                "startTimestamp": start,
                "homeTeam": {"id": 7},
                "awayTeam": {"id": 8},
            }
        ]
    }
    con.execute(
        "insert into sofa_entity_events values (7, 'next', 0, 'x', ?)",
        (json.dumps(events),),
    )
    con.commit()
    return con


def test_resolve_items_reconstruct_gaps_and_tournaments(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _write(
        runs / "2026-10-14" / "01_board.json",
        [
            {
                "superbet_event_id": "1",
                "sport": "football",
                "match_name": "Known FC·Other",
                "kickoff_utc": "2026-10-14T12:00:00Z",
                "tournament_id": 5,
            },
            {
                "superbet_event_id": "2",
                "sport": "football",
                "match_name": "Nobody·Else",
                "kickoff_utc": "2026-10-14T12:00:00Z",
                "tournament_id": 5,
            },
            {
                "superbet_event_id": "3",
                "sport": "football",
                "match_name": "X·Y",
                "kickoff_utc": "2026-10-14T15:00:00Z",
                "tournament_id": 6,
            },
            {
                "superbet_event_id": "4",
                "sport": "volleyball",
                "match_name": "V·W",
                "kickoff_utc": "2026-10-14T15:00:00Z",
                "tournament_id": 6,
            },
        ],
    )
    _write(
        runs / "2026-10-14" / "02_fixtures.json",
        [{"superbet_event_ids": ["3"], "competition_id": 600}],
    )
    con = _db(tmp_path / "s.db")
    items, tours = m.resolve_items(str(runs), con, ("football",))
    by = {i.key: i for i in items}
    assert set(by) == {"1", "2", "3"}
    assert by["1"].reason == "GAP_ONE_SIDE_KNOWN_GAME_IN_LISTING"
    assert by["2"].reason == "GAP_NO_SIDE_KNOWN"
    assert by["3"].state == m.IDENTIFIED
    assert tours["football"] == {"5": set(), "6": {600}}


def test_football_player_items_identified_wins_and_never_started_is_explained(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "2026-10-14" / "03_samples.json",
        [
            {
                "sofascore_event_id": 1,
                "players": {"player_shots_for|Pablo": {"player": "Pablo"}},
                "gaps": [
                    {
                        "reason": "NO_ENTITY_FOUND",
                        "metric": "player_fouls_for",
                        "detail": "player 'Pablo' matched no squad member",
                    },
                    {
                        "reason": "NO_ENTITY_FOUND",
                        "metric": "player_fouls_for",
                        "detail": "player 'Taty' matched no squad member",
                    },
                    {
                        "reason": "NO_ENTITY_FOUND",
                        "metric": "player_fouls_for",
                        "detail": "player 'Bench' named in 2 squads, never started",
                    },
                    {
                        "reason": "NO_STATISTICS",
                        "metric": "player_fouls_for",
                        "detail": "player 'Other' event 1 gap",
                    },
                ],
            }
        ],
    )
    got = {i.name: (i.state, i.reason) for i in m.football_player_items(str(tmp_path))}
    assert got == {
        "Pablo": (m.IDENTIFIED, None),
        "Taty": (m.UNEXPLAINED, "NO_SQUAD_MATCH"),
        "Bench": (m.EXPLAINED, "NEVER_STARTED"),
    }


def test_sport_player_items_read_the_latest_row(tmp_path: Path) -> None:
    base = {"superbet_event_id": "9", "kickoff_utc": "2026-10-14T18:00:00Z"}
    _jsonl(
        tmp_path / "shadow" / "hockey" / "2026-10-14" / "player_model.jsonl",
        [
            {
                **base,
                "subject": "A",
                "model_reason": "TEAM_UNRESOLVED",
                "computed_at_utc": "1",
            },
            {**base, "subject": "A", "model_reason": None, "computed_at_utc": "2"},
            {
                **base,
                "subject": "B",
                "model_reason": "NOT_IN_HISTORY",
                "computed_at_utc": "1",
            },
            {
                **base,
                "subject": "C",
                "model_reason": "THIN_SAMPLE",
                "computed_at_utc": "1",
            },
        ],
    )
    got = {
        i.name: (i.state, i.reason)
        for i in m.sport_player_items(str(tmp_path), "hockey")
    }
    assert got == {
        "A": (m.IDENTIFIED, None),
        "B": (m.UNEXPLAINED, "NOT_IN_HISTORY"),
        "C": (m.IDENTIFIED, None),
    }


def _map(
    team_a: int, team_b: int, players: list[tuple[int, int, str]]
) -> cs2_engine.MapRow:
    return cs2_engine.MapRow(
        1,
        0,
        1,
        team_a,
        team_b,
        13,
        5,
        True,
        tuple((t, pid, nick, ()) for t, pid, nick in players),
    )


def test_cs2_player_state_mirrors_player_id() -> None:
    history = [
        _map(1, 2, [(1, 100, "magic"), (1, 101, "twin"), (2, 200, "zeus")]),
        _map(1, 3, [(1, 102, "twin")]),
    ]
    assert m.cs2_player_state(history, [1, 2], "magic") == (m.IDENTIFIED, None)
    assert m.cs2_player_state(history, [1, 2], "Zeus") == (m.IDENTIFIED, None)
    assert m.cs2_player_state(history, [1, 2], "twin") == (
        m.UNEXPLAINED,
        "NAME_UNCERTAIN",
    )
    assert m.cs2_player_state(history, [1, 2], "ghost") == (
        m.UNEXPLAINED,
        "NOT_IN_HISTORY",
    )


def test_cs2_player_items_follow_the_event_identity(tmp_path: Path) -> None:
    lines = [{"family": "player_kills", "subject": s} for s in ("p1", "p2")]
    _jsonl(
        tmp_path / "cs2" / "2026-10-14" / "snapshots.jsonl",
        [
            {
                "superbet_event_id": e,
                "kickoff_utc": "2026-10-14T10:00:00Z",
                "lines": lines,
            }
            for e in ("1", "2", "3")
        ],
    )
    recs = {
        "1": _fixture("1", "cs2", "NOT_IDENTIFIED", "NO_MATCH_IN_LISTING"),
        "2": _fixture("2", "cs2", "DUPLICATE_SUPERBET_TEAM"),
    }
    items, no_record = m.cs2_player_items(str(tmp_path), recs, None, None, None)
    assert no_record == 2  # event 3 has no identity record
    assert {(i.key, i.state, i.reason) for i in items} == {
        ("1|p1", m.UNEXPLAINED, "EVENT_NOT_IDENTIFIED"),
        ("1|p2", m.UNEXPLAINED, "EVENT_NOT_IDENTIFIED"),
        ("2|p1", m.EXCLUDED, "EVENT_EXCLUDED"),
        ("2|p2", m.EXCLUDED, "EVENT_EXCLUDED"),
    }


def test_summarise_and_render() -> None:
    items = [
        m.Item("hockey", "event", "2026-10-13", "1", m.IDENTIFIED),
        m.Item("hockey", "event", "2026-10-14", "2", m.UNEXPLAINED, "BRIDGE_ABORTED"),
        m.Item("hockey", "event", "2026-10-14", "3", m.UNEXPLAINED, "BRIDGE_ABORTED"),
        m.Item("cs2", "event", "2026-10-14", "4", m.EXCLUDED, "1x1"),
    ]
    s = m.summarise(items)
    h = s["hockey/event"]
    assert (h["total"], h[m.UNEXPLAINED], h["days"]) == (3, 2, 2)
    assert h["unexplained_per_day"] == 1.0
    assert h["reasons"] == {"BRIDGE_ABORTED": 2}
    assert h["by_day"]["2026-10-14"][m.UNEXPLAINED] == 2
    assert s["cs2/event"]["other_reasons"] == {"EXCLUDED:1x1": 1}
    md = m.render(
        {
            "first": "2026-10-13",
            "last": "2026-10-14",
            "computed_at_utc": "t",
            "summary": s,
            "names": {},
            "tournaments": {},
        }
    )
    assert "| hockey/event | 2 | 3 | 1 | 0 | 0 | **2** (66.7%)" in md
    assert "| 2026-10-14 | " in md


def test_measure_end_to_end_without_db(tmp_path: Path) -> None:
    _write(
        tmp_path / "2026-10-14" / "sport_fixtures.json",
        {
            "fixtures": [
                _fixture("1", "volleyball", "NOT_IDENTIFIED", "TEAM_UNRESOLVED"),
                _fixture("2", "volleyball", "IDENTIFIED", competition_id=55),
                _fixture(
                    "3", "volleyball", "IDENTIFIED", kickoff_utc="2026-10-01T10:00:00Z"
                ),
            ]
        },
    )
    r = m.measure(str(tmp_path), None, ("volleyball",), "2026-10-14", "2026-10-14")
    v = r["summary"]["volleyball/event"]
    assert (v["total"], v[m.IDENTIFIED], v[m.UNEXPLAINED]) == (2, 1, 1)
    assert r["tournaments"]["volleyball"] == {
        "tournaments": 1,
        "mapped": 1,
        "unmapped": 0,
        "several_competitions": 0,
    }
