"""bet.sofa.dossier: the analysts' match fact sheet, built offline."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import dossier
from bet.sofa.db import migrate
from bet.sofa.listing_index import SCHEMA, index_page
from scripts.sofa import read_set

KICK = int(datetime(2026, 10, 20, 12, 0, tzinfo=UTC).timestamp())
DAY = 86400
UT, SEASON = 77, 501
NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


def team(i: int, name: str) -> dict[str, Any]:
    return {"id": i, "name": name, "country": {"name": "Polska", "alpha2": "PL"}}


def ev(
    eid: int,
    ts: int,
    home: int,
    away: int,
    hs: int,
    as_: int,
    *,
    season: int = SEASON,
    status: str = "finished",
    friendly: bool = False,
    sport: str = "football",
    periods: tuple[tuple[int, int], ...] = (),
) -> dict[str, Any]:
    hp = {f"period{n}": p[0] for n, p in enumerate(periods, 1)}
    ap = {f"period{n}": p[1] for n, p in enumerate(periods, 1)}
    names = {1: "Alfa", 2: "Beta", 3: "Gamma", 4: "Delta"}
    winner = 3 if hs == as_ else (1 if hs > as_ else 2)
    return {
        "id": eid,
        "startTimestamp": ts,
        "status": {"type": status, "description": "Ended"},
        "homeTeam": team(home, names.get(home, f"T{home}")),
        "awayTeam": team(away, names.get(away, f"T{away}")),
        "homeScore": {"current": hs, **hp},
        "awayScore": {"current": as_, **ap},
        "winnerCode": winner if status == "finished" else None,
        "tournament": {
            "name": "Friendly" if friendly else "Liga",
            "uniqueTournament": {
                "id": 853 if friendly else UT,
                "name": "Club Friendly Games" if friendly else "Liga",
            },
            "category": {"name": "Polska", "alpha2": "PL", "sport": {"slug": sport}},
        },
        "season": {"id": season, "name": "26/27"},
    }


def make_db(path: Path, events: list[dict[str, Any]], detail: dict[str, Any]) -> None:
    migrate(str(path))
    con = sqlite3.connect(path)
    for stmt in SCHEMA:
        con.execute(stmt)
    by_team: dict[int, list[dict[str, Any]]] = {}
    for e in events:
        for side in ("homeTeam", "awayTeam"):
            by_team.setdefault(e[side]["id"], []).append(e)
    for tid, evs in by_team.items():
        index_page(con, tid, "last", "2026-10-20T08:00:00+00:00", {"events": evs})
    con.execute(
        "INSERT INTO sofa_event_detail (sofascore_event_id, fetched_at, status_type, "
        "detail_json) VALUES (?, ?, ?, ?)",
        (
            detail["id"],
            "2026-10-20T08:00:00+00:00",
            "notstarted",
            json.dumps({"event": detail}),
        ),
    )
    con.commit()
    con.close()


def football_day(tmp_path: Path) -> tuple[Path, Path]:
    events = [
        ev(101, KICK - 3 * DAY, 1, 3, 2, 0),  # Alfa beat Gamma
        ev(102, KICK - 10 * DAY, 2, 1, 1, 1),  # Beta - Alfa draw (h2h)
        ev(103, KICK - 6 * DAY, 3, 4, 0, 3),  # Gamma - Delta: only via Gamma
        ev(104, KICK - 4 * DAY, 2, 3, 1, 0),  # Beta beat Gamma
        ev(105, KICK - 2 * DAY, 1, 4, 5, 0, friendly=True),
        ev(106, KICK - 40 * DAY, 1, 2, 0, 4, season=400),  # last season
        ev(107, KICK + DAY, 1, 3, 9, 9),  # after kickoff: never
        ev(108, KICK - DAY, 2, 4, 0, 0, status="inprogress"),
    ]
    detail = ev(500, KICK, 1, 2, 0, 0, status="notstarted")
    detail["venue"] = {
        "name": "Stadion",
        "city": {"name": "Gdańsk"},
        "country": {"name": "Poland", "alpha2": "PL"},
        "capacity": 40000,
    }
    detail["referee"] = {"name": "Sędzia X", "country": {"name": "Poland"}}
    db = tmp_path / "sofa.db"
    make_db(db, events, detail)
    run = tmp_path / "runs" / "2026-10-20"
    run.mkdir(parents=True)
    legs = [
        {
            "sofascore_event_id": 500,
            "sport": "football",
            "match": "Alfa - Beta",
            "market": "corners_total",
            "superbet_market": "Liczba rzutów rożnych",
            "superbet_selection": "powyżej 7.5",
            "confidence": 0.77,
            "offered_odds": 1.27,
            "position": 1,
            "group_key": "sofa:500",
            "kickoff_utc": "2026-10-20T12:00:00Z",
            "line": 7.5,
            "direction": "OVER",
            "subject": "",
            "price_gap": {"flag": "CONFIDENCE_ABOVE_PRICE"},
            "reads": [{"author": "analyst", "verdict": "KEEP"}],
        }
    ]
    (run / "11_coupon.json").write_text(
        json.dumps({"singles": legs, "removed_by_reads": []})
    )
    (run / "03_samples.json").write_text(
        json.dumps(
            [
                {
                    "sofascore_event_id": 500,
                    "readiness": "READY",
                    "gaps": [],
                    "schedule": {"side_a": {"rest_days": 3.0}},
                    "metrics": {
                        "corners_total": {
                            "side_a": [{"value": 10.0}, {"value": 6.0}],
                            "side_b": [{"value": 8.0}],
                            "h2h": [],
                        }
                    },
                    "players": {},
                }
            ]
        )
    )
    (run / "04_offer.json").write_text(
        json.dumps(
            [
                {
                    "sofascore_event_id": 500,
                    "status": "PRICED",
                    "rungs": [
                        {"market": "corners_total", "line": 7.5, "over_odds": 1.27},
                        {"market": "goals_total", "line": 2.5, "over_odds": 1.9},
                    ],
                }
            ]
        )
    )
    return db, run


def test_football_dossier_form_rest_h2h_table_venue(tmp_path: Path) -> None:
    db, run = football_day(tmp_path)
    legs = [{"sofascore_event_id": 500, "sport": "football"}]
    written = dossier.write_for_legs(run, legs, db_path=db, now=NOW)
    assert legs[0]["dossier"] == written[500]
    doc = json.loads(Path(written[500]).read_text())
    alfa = doc["sides"]["home"]
    # 107 is after kickoff and 108 unfinished: never in the form
    dates = [g["date"] for g in alfa["last_games"]]
    assert len(dates) == 4 and all(d < "2026-10-20" for d in dates)
    friendly = [g for g in alfa["last_games"] if g.get("friendly")]
    assert len(friendly) == 1 and friendly[0]["score"] == [5, 0]
    assert alfa["summary"]["rest_days"] == 2.0
    assert alfa["summary"]["form"] == "WWRP"
    assert doc["head_to_head"][0]["result"] == "R"
    assert {g["score"][0] + g["score"][1] for g in doc["head_to_head"]} == {2, 4}
    table = doc["table"]
    # Gamma - Delta is reached only through Gamma's listing; the friendly
    # and last season's game are not counted
    assert table["games_counted"] == 4 and table["teams"] == 4
    rows = {r["team"]: r for r in table["rows"]}
    assert rows["Alfa"]["pts"] == 4 and rows["Beta"]["pts"] == 4
    assert rows["Delta"]["pts"] == 3 and rows["Gamma"]["pts"] == 0
    assert table["positions"] == {
        "home": rows["Alfa"]["pos"],
        "away": rows["Beta"]["pos"],
    }
    header = doc["header"]
    assert header["city"] == "Gdańsk" and header["venue_zone"] == "Europe/Warsaw"
    assert header["kickoff_venue_local"] == "2026-10-20 14:00"
    assert header["referee"]["name"] == "Sędzia X"
    assert doc["legs"][0]["price_gap"] is True
    assert doc["legs"][0]["reads"] == ["analyst:KEEP"]
    assert doc["samples"]["metrics"]["corners_total"]["side_a"]["mean"] == 8.0
    assert [r["market"] for r in doc["market"]["rungs_of_leg_markets"]] == [
        "corners_total"
    ]
    checklist = " | ".join(doc["web_checklist"])
    assert "pogoda: Gdańsk 2026-10-20 14:00" in checklist
    assert "nastroje i kulisy" in checklist and "składy" in checklist


def test_attach_without_a_database_reports_and_never_raises(tmp_path: Path) -> None:
    legs = [{"sofascore_event_id": 1, "sport": "football"}]
    line = dossier.attach(tmp_path, legs, tmp_path / "missing.db")
    assert "brak bazy" in line and "dossier" not in legs[0]


def test_read_set_cli_writes_dossiers_and_points_each_leg(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db, run = football_day(tmp_path)
    out = tmp_path / "rs"
    assert (
        read_set.main(
            [
                "--date",
                run.name,
                "--runs-dir",
                str(run.parent),
                "--out-dir",
                str(out),
                "--db-path",
                str(db),
                "--no-h2h",
                "--no-lineups",
            ]
        )
        == 0
    )
    rows = json.loads((out / "read_set_football.json").read_text())
    assert rows[0]["dossier"].endswith("dossier/football_500.json")
    assert Path(rows[0]["dossier"]).exists()
    assert "dossier: 1 meczów" in capsys.readouterr().out
    assert (
        read_set.main(
            [
                "--date",
                run.name,
                "--runs-dir",
                str(run.parent),
                "--out-dir",
                str(out),
                "--no-dossier",
            ]
        )
        == 0
    )
    assert "dossier" not in json.loads((out / "read_set_football.json").read_text())[0]


def test_hockey_dossier_reads_period_form_and_superbet_line_moves(
    tmp_path: Path,
) -> None:
    p = ((1, 0), (2, 1), (0, 0))
    events = [
        ev(201, KICK - DAY, 1, 2, 3, 1, sport="ice-hockey", periods=p),
        ev(
            202,
            KICK - 3 * DAY,
            3,
            1,
            2,
            2,
            sport="ice-hockey",
            periods=((1, 1), (1, 0), (0, 1)),
        ),
    ]
    detail = ev(600, KICK, 1, 3, 0, 0, status="notstarted", sport="ice-hockey")
    db = tmp_path / "sofa.db"
    make_db(db, events, detail)
    run = tmp_path / "runs" / "2026-10-20"
    run.mkdir(parents=True)
    snaps = run.parent / "shadow" / "hockey" / "2026-10-20"
    snaps.mkdir(parents=True)
    line = {"family": "total", "period": 0, "subject": "", "line": 5.5, "side": "OVER"}
    with (snaps / "snapshots.jsonl").open("w") as fh:
        for at, odds in (
            ("2026-10-20T06:00:00Z", 1.90),
            ("2026-10-20T09:00:00Z", 1.70),
        ):
            fh.write(
                json.dumps(
                    {
                        "superbet_event_id": "77",
                        "fetched_at_utc": at,
                        "lines": [dict(line, odds=odds)],
                    }
                )
                + "\n"
            )
        fh.write(
            json.dumps({"superbet_event_id": "78", "lines": [dict(line, odds=3.0)]})
            + "\n"
        )
    leg = {
        "sofascore_event_id": 600,
        "sport": "hockey",
        "family": "total",
        "superbet_event_id": "77",
        "source_date": "2026-10-20",
        "match": "Alfa - Gamma",
    }
    (run / "11_coupon.json").write_text(json.dumps({"singles": [leg]}))
    doc = json.loads(
        Path(
            dossier.write_for_legs(run, [dict(leg)], db_path=db, now=NOW)[600]
        ).read_text()
    )
    alfa = doc["sides"]["home"]["summary"]
    assert alfa["avg_periods"] == [[1.0, 0.5], [1.0, 1.0], [0.5, 0.0]]
    assert alfa["games_7d"] == 2 and alfa["rest_days"] == 1.0
    market = doc["market"]
    assert market["snapshots"] == 2 and market["moved"] == 1
    assert market["rows"][0]["first"] == 1.90 and market["rows"][0]["last"] == 1.70
    checklist = " | ".join(doc["web_checklist"])
    assert "bramkarz" in checklist and "pogoda" not in checklist
    assert doc["table"]["games_counted"] == 2


def test_cs2_dossier_flags_a_new_name_in_the_roster(tmp_path: Path) -> None:
    detail = ev(700, KICK, 1, 2, 0, 0, status="notstarted", sport="esports")
    detail["bestOf"] = 3
    db = tmp_path / "sofa.db"
    make_db(db, [], detail)
    con = sqlite3.connect(db)
    for sid, ts, players in ((1, KICK - 2 * DAY, "abcde"), (2, KICK - DAY, "abcdX")):
        con.execute(
            "INSERT INTO cs2_series (sofascore_event_id, start_ts, tournament, "
            "home_id, home_name, away_id, away_name, home_maps, away_maps, best_of, "
            "status_type, fetched_at) "
            "VALUES (?, ?, 'Cup', 1, 'Alfa', 9, 'Omega', 2, 1, 3, 'finished', 'x')",
            (sid, ts),
        )
        con.execute(
            "INSERT INTO cs2_map (game_id, sofascore_event_id, map_order, map_name, "
            "status_type, home_rounds, away_rounds, winner_code, fetched_at) "
            "VALUES (?, ?, 1, 'Nuke', 'finished', 13, 9, 1, 'x')",
            (sid * 10, sid),
        )
        for pid, name in enumerate(players):
            con.execute(
                "INSERT INTO cs2_player_map (game_id, side, player_id, player_name, "
                "kills, deaths) VALUES (?, 'home', ?, ?, 20, 15)",
                (sid * 10, pid, name),
            )
    con.commit()
    con.close()
    run = tmp_path / "runs" / "2026-10-20"
    run.mkdir(parents=True)
    leg = {"sofascore_event_id": 700, "sport": "cs2", "match": "Alfa - Beta"}
    (run / "11_coupon.json").write_text(json.dumps({"singles": [leg]}))
    doc = json.loads(
        Path(
            dossier.write_for_legs(run, [dict(leg)], db_path=db, now=NOW)[700]
        ).read_text()
    )
    alfa = doc["cs2"]["home"]
    assert alfa["roster_new_vs_previous"] == ["X"]
    assert alfa["map_pool_90d"]["Nuke"] == {"n": 2, "won": 2, "avg_rounds": 22.0}
    assert alfa["series"][0]["maps"] == [2, 1]
    assert doc["header"]["best_of"] == 3 and "table" not in doc
    assert any("stand-in" in x for x in doc["web_checklist"])


def _stats(corners: tuple[int, int], possession: tuple[int, int],
           crosses: tuple[int, int] = (20, 10)) -> str:
    items = [
        {"key": "cornerKicks", "homeValue": corners[0], "awayValue": corners[1]},
        {"key": "ballPossession", "homeValue": possession[0],
         "awayValue": possession[1]},
        {"key": "accurateCross", "homeValue": 5, "awayValue": 3,
         "homeTotal": crosses[0], "awayTotal": crosses[1]},
        {"key": "expectedGoals", "homeValue": 1.25, "awayValue": 0.5},
        {"key": "accurateLongBalls", "homeValue": 20, "awayValue": 10,
         "homeTotal": 40, "awayTotal": 30},
    ]
    return json.dumps({"statistics": [
        {"period": "ALL", "groups": [{"groupName": "x", "statisticsItems": items}]},
        {"period": "1ST", "groups": [{"groupName": "x", "statisticsItems": [
            {"key": "cornerKicks", "homeValue": 1, "awayValue": 0}]}]},
    ]})


def test_style_block_sets_own_corners_against_what_the_opponent_concedes(
    tmp_path: Path,
) -> None:
    # Alfa (1) wins plenty of corners; Beta (2) concedes few. A friendly and a
    # partial feed's 0 / 0 possession never count.
    events = [
        ev(201, KICK - 3 * DAY, 1, 3, 1, 0),
        ev(202, KICK - 6 * DAY, 4, 1, 0, 2),
        ev(203, KICK - 9 * DAY, 1, 4, 2, 2),
        ev(204, KICK - 2 * DAY, 1, 3, 3, 0, friendly=True),
        ev(205, KICK - 4 * DAY, 2, 3, 0, 0),
        ev(206, KICK - 8 * DAY, 4, 2, 1, 1),
    ]
    detail = ev(500, KICK, 1, 2, 0, 0, status="notstarted")
    db = tmp_path / "sofa.db"
    make_db(db, events, detail)
    stats = {
        201: _stats((8, 2), (65, 35)),
        202: _stats((3, 6), (40, 60)),  # Alfa away: 6 corners, 60 %
        203: _stats((2, 5), (0, 0)),  # placeholder possession
        204: _stats((15, 0), (80, 20)),  # friendly
        205: _stats((5, 2), (55, 45)),  # Beta home concedes 2
        206: _stats((4, 3), (50, 50)),  # Beta away concedes 4
    }
    con = sqlite3.connect(db)
    for eid, payload in stats.items():
        con.execute(
            "INSERT INTO sofa_event_stats (sofascore_event_id, fetched_at, "
            "statistics_json, status_type) VALUES (?, ?, ?, ?)",
            (eid, "2026-10-20T08:00:00+00:00", payload, "finished"))
    con.commit()
    run = tmp_path / "runs" / "2026-10-20"
    run.mkdir(parents=True)
    legs = [
        {"sofascore_event_id": 500, "sport": "football", "match": "Alfa - Beta",
         "market": "corners_for", "subject": "alfa", "line": 3.5,
         "direction": "OVER", "confidence": 0.8, "offered_odds": 1.25,
         "superbet_market": "Alfa - liczba rzutów rożnych",
         "superbet_selection": "powyżej 3.5"},
        {"sofascore_event_id": 500, "sport": "football", "match": "Alfa - Beta",
         "market": "both_over_corners", "subject": "", "line": 1.5,
         "direction": "OVER", "confidence": 0.85, "offered_odds": 1.15},
    ]
    (run / "11_coupon.json").write_text(
        json.dumps({"singles": legs, "removed_by_reads": []}))
    written = dossier.write_for_legs(
        run, [{"sofascore_event_id": 500, "sport": "football"}], db_path=db, now=NOW)
    style = json.loads(Path(written[500]).read_text())["style"]
    # a scratch dossier dir: the day's dossier stays as it is
    scratch = tmp_path / "scratch"
    moved = dossier.write_for_legs(
        run, [{"sofascore_event_id": 500, "sport": "football"}], db_path=db,
        now=NOW, out_dir=scratch)
    assert moved[500] == str(scratch / "football_500.json")
    assert json.loads(Path(moved[500]).read_text())["schema"] == dossier.SCHEMA_VERSION
    alfa = style["home"]
    assert alfa["n"] == 3  # the friendly is out
    assert [g["corners"] for g in alfa["games"]] == [[8, 2], [6, 3], [2, 5]]
    assert "possession" not in alfa["games"][2]
    assert alfa["means"]["possession"] == 62.5
    assert alfa["corners_by_own_possession"]["posiadanie_50_plus"]["rozne_za"] == [
        8, 6]
    assert alfa["games"][0]["crosses"] == [20, 10]
    assert alfa["games"][0]["corners_1h"] == [1, 0]
    assert alfa["games"][0]["xg"] == [1.25, 0.5]
    assert alfa["games"][1]["long_balls"] == [30, 40]  # attempted, Alfa away
    assert alfa["means"]["xg"]["za"] == round((1.25 + 0.5 + 1.25) / 3, 2)
    # 2 games at >= 50 %: a note, never a RYNEK WATCH
    assert "uwaga" in alfa["corners_by_own_possession"]["posiadanie_50_plus"]
    team_leg, both = style["matchup"]
    assert team_leg["leg"] == "Alfa - liczba rzutów rożnych: powyżej 3.5"
    assert team_leg["implied"] == 0.8
    (cell,) = team_leg["sides"]
    assert cell["team"] == "Alfa" and cell["own"] == "2/3"
    assert cell["opponent"] == "Beta" and cell["opponent_conceded"] == "1/2"
    assert cell["conceded_values"] == [2, 4]
    assert team_leg["market"] == "corners_for" and team_leg["subject"] == "alfa"
    assert (team_leg["line"], team_leg["direction"]) == (3.5, "OVER")
    assert "joint" not in team_leg and "price_gap" not in team_leg
    # a joint reads like a total on min(own, rival), as SETTLE grades it
    assert both["joint"] is True
    assert [c["team"] for c in both["sides"]] == ["Alfa", "Beta"]
    assert both["sides"][0]["values"] == [2, 3, 2]
    assert [c["games"] for c in both["sides"]] == ["3/3", "2/2"]
    # the HTML view's tag: every printed team-side leg, teams from 02_fixtures
    (run / "02_fixtures.json").write_text(json.dumps([{
        "sofascore_event_id": 500, "home_entity_id": 1, "away_entity_id": 2,
        "home_name": "Alfa", "away_name": "Beta",
        "kickoff_utc": "2026-10-20T12:00:00Z"}]))
    tags = dossier.matchups_for_legs(run, legs + [{
        **legs[0], "market": "player_shots_for"}], db_path=db)
    assert tags == {
        dossier.matchup_key(legs[0]): "zestawienie: Alfa 2/3, Beta oddaje 1/2",
        dossier.matchup_key(legs[1]): "zestawienie: noga łączna (min obu stron)"
        " · mecze Alfa 3/3 · mecze Beta 2/2",
    }
    assert dossier.matchups_for_legs(run, legs, db_path=tmp_path / "none.db") == {}
    # every leg together: Alfa's games 201 / 202 (203: 2 corners), Beta's
    # 206 (205: Beta conceded 2) - Alfa's side leg read as what Beta conceded
    joint = dossier.joint_history(run, legs + [{
        **legs[0], "market": "player_shots_for"}], db_path=db)
    assert (joint["k"], joint["n"], joint["legs_read"]) == (3, 5, 2)
    assert len(joint["legs_without_history"]) == 1
    assert "missing" in dossier.joint_history(run, legs, db_path=tmp_path / "x.db")
    # "każda z drużyn powyżej 2.5 - nie" = not both over: min under the line
    # (Alfa's mins 2, 3, 2; Beta's 2, 3) - never "both under"
    nie = {**legs[1], "line": 2.5, "direction": "UNDER"}
    rows = dossier.matchup_rows(
        [nie], {"home": [{"corners_for": [2, 5]}, {"corners_for": [3, 6]}],
                "away": [{"corners_for": [2, 2]}]},
        {"home": "Alfa", "away": "Beta"},
        {"competition": "L", "values": [{"corners_for": [1, 9]},
                                        {"corners_for": [4, 4]}]})
    ((row, _),) = rows
    assert [c["games"] for c in row["sides"]] == ["1/2", "1/1"]
    assert row["league"]["share"] == 0.5
    assert dossier._leg_hit(nie, {"corners_for": [2, 5]}, "home",
                            {"home": "Alfa", "away": "Beta"}) is True
    assert dossier._leg_hit(nie, {"corners_for": [3, 6]}, "home",
                            {"home": "Alfa", "away": "Beta"}) is False


def test_one_match_listed_under_two_ids_is_one_game(tmp_path: Path) -> None:
    """2026-10-29: Prat - Sant Rafel (Copa del Rey) sat twice in Prat's
    last_games (17136469 and 17336477, same sides, start and score); the
    form, the rebuilt table and the style rows read team_games."""
    db = tmp_path / "s.db"
    events = [ev(10, KICK - 3 * DAY, 1, 2, 5, 0),
              ev(11, KICK - 3 * DAY, 1, 2, 5, 0, periods=((3, 0), (2, 0))),
              ev(12, KICK - 10 * DAY, 2, 1, 1, 5)]
    make_db(db, events, ev(99, KICK, 1, 2, 0, 0, status="notstarted"))
    con = sqlite3.connect(db)
    assert [g["id"] for g in dossier.team_games(con, 1, KICK, 10)] == [10, 12]
