"""The measured sports' player-prop model (src/bet/sofa/player_model.py), its
pre-game forecast at SHADOW (run_shadow.forecast_players), its attachment at
SHADOW_SETTLE (settle_shadow.attach_player_model) and its measurement
(scripts/sofa/measure_player_props.py). Offline: a small SQLite file with the
four tables the model reads, and the settle / snapshot fakes of test_shadow.
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import player_model
from bet.sofa.player_model import (
    MODEL_KEYS,
    UNFITTED,
    Appearance,
    line_probability,
    load_appearances,
)
from bet.sofa.shadow import ShadowLine
from scripts.sofa import measure_player_props, run_shadow, settle_shadow
from tests.sofa.test_shadow import (
    HOCKEY_AET,
    T1,
    T2,
    FakeResolver,
    LineupsClient,
)

REPO = Path(__file__).resolve().parents[2]
DATE = "2026-09-28"
KICKOFF = datetime(2026, 9, 28, 16, tzinfo=UTC)
KO_TS = int(KICKOFF.timestamp())
HOME_ID, AWAY_ID = 10, 20
SOG = 230023  # hockey player_shots_on_goal
PLUS_MINUS = 232585
PTS = 233565  # basketball player_points
PTS_REB = 233572


# --- a fake database -----


def make_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE sofa_listing_event (entity_id INTEGER, kind TEXT,
            event_id INTEGER, start_ts INTEGER, fetched_at TEXT,
            PRIMARY KEY (entity_id, kind, event_id));
        CREATE TABLE sofa_event_stats (sofascore_event_id INTEGER PRIMARY KEY,
            fetched_at TEXT, statistics_json TEXT, incidents_json TEXT,
            status_type TEXT, lineups_json TEXT);
        CREATE TABLE sofa_listed_event (event_id INTEGER PRIMARY KEY, sport TEXT,
            start_ts INTEGER, fetched_at TEXT, event_json TEXT);
        CREATE TABLE sofa_entity (sport TEXT, query_key TEXT, sofascore_id INTEGER,
            sofascore_name TEXT, entity_type TEXT, country TEXT, status TEXT);
        """
    )
    return conn


def entry(
    team: int, pid: int, name: str, stats: dict[str, Any], pos: str = "C"
) -> dict[str, Any]:
    return {
        "player": {"id": pid, "name": name, "position": pos},
        "teamId": team,
        "position": pos,
        "statistics": stats,
    }


def add_game(
    conn: sqlite3.Connection,
    eid: int,
    ts: int,
    players: list[dict[str, Any]],
    home: int = HOME_ID,
    away: int = AWAY_ID,
    slug: str = "ice-hockey",
    names: tuple[str, str] = (T1, T2),
) -> None:
    lineups = {
        "home": {"players": [p for p in players if p["teamId"] == home]},
        "away": {"players": [p for p in players if p["teamId"] != home]},
    }
    for team in (home, away):
        conn.execute(
            "INSERT INTO sofa_listing_event VALUES (?, 'last', ?, ?, 'x')",
            (team, eid, ts),
        )
    conn.execute(
        "INSERT INTO sofa_event_stats VALUES (?, 'x', NULL, NULL, 'finished', ?)",
        (eid, json.dumps(lineups)),
    )
    event = {
        "id": eid,
        "startTimestamp": ts,
        "homeTeam": {"id": home, "name": names[0]},
        "awayTeam": {"id": away, "name": names[1]},
        "tournament": {"name": "Extraliga"},
    }
    conn.execute(
        "INSERT INTO sofa_listed_event VALUES (?, ?, ?, 'x', ?)",
        (eid, slug, ts, json.dumps(event)),
    )


def hockey_history(conn: sqlite3.Connection, games: int = 8) -> None:
    """Novak (home, C) shoots 2 / 4 alternately in 1,200 s; a team-mate and
    an opponent of the same position fill the pool."""
    for i in range(games):
        ts = KO_TS - (i + 1) * 2 * 86400
        add_game(
            conn,
            100 + i,
            ts,
            [
                entry(
                    HOME_ID,
                    1,
                    "Jan Novak",
                    {
                        "secondsPlayed": 1200,
                        "shots": 2 + 2 * (i % 2),
                        "plusMinus": (i % 3) - 1,
                    },
                ),
                entry(
                    HOME_ID,
                    2,
                    "Petr Svoboda",
                    {"secondsPlayed": 1100, "shots": 3, "plusMinus": 0},
                ),
                entry(
                    AWAY_ID,
                    3,
                    "Karel Dvorak",
                    {"secondsPlayed": 1000, "shots": 1, "plusMinus": 1},
                ),
            ],
        )


def apps_of(conn: sqlite3.Connection, before: int = KO_TS - 60) -> list[Appearance]:
    return load_appearances(conn, "hockey", [HOME_ID, AWAY_ID], before, None)


def line(
    mid: int, subject: str, value: float, side: str, family: str = "x"
) -> ShadowLine:
    return ShadowLine("1", mid, family, 0, subject, value, side, 1.9)


# --- the sample -----


def test_the_sample_is_appearances_before_kickoff_for_the_players_own_team(
    tmp_path: Path,
) -> None:
    conn = make_db(tmp_path / "db.sqlite")
    hockey_history(conn, games=6)
    # A DNP (secondsPlayed 0), a game after the cut-off with a huge value, and
    # the graded game itself (excluded by id even though it is "before").
    add_game(
        conn,
        200,
        KO_TS - 86400,
        [entry(HOME_ID, 1, "Jan Novak", {"secondsPlayed": 0, "shots": 0})],
    )
    add_game(
        conn,
        201,
        KO_TS + 3600,
        [entry(HOME_ID, 1, "Jan Novak", {"secondsPlayed": 1200, "shots": 50})],
    )
    add_game(
        conn,
        700,
        KO_TS - 7200,
        [entry(HOME_ID, 1, "Jan Novak", {"secondsPlayed": 1200, "shots": 40})],
    )
    conn.commit()
    apps = load_appearances(conn, "hockey", [HOME_ID, AWAY_ID], KO_TS - 60, 700)
    mine = [a for a in apps if a.player_id == 1]
    assert len(mine) == 6
    assert all(a.ts < KO_TS - 60 and a.event_id not in (200, 201, 700) for a in mine)
    # Every appearance is attributed to the team that fielded it.
    assert {a.team_id for a in apps if a.player_id == 3} == {AWAY_ID}
    mp = line_probability(line(SOG, "Novak, Jan", 2.5, "OVER"), "hockey", apps)
    assert mp.p is not None and mp.n == 6 and mp.mean is not None
    assert 2.0 < mp.mean < 4.0  # never pulled towards the 50 or the 40


def test_minutes_scale_the_per_second_rate(tmp_path: Path) -> None:
    conn = make_db(tmp_path / "db.sqlite")
    # 1 point per 120 s for everybody; Smith's last five games 1,800 s, the
    # ten before 600 s. Expected seconds are the half-life-weighted mean of
    # the sample (hl_minutes appearances), and the minutes mixture keeps it
    # as the mean.
    for i in range(15):
        secs = 1800 if i < 5 else 600
        add_game(
            conn,
            300 + i,
            KO_TS - (i + 1) * 86400,
            [
                entry(
                    HOME_ID,
                    1,
                    "Joe Smith",
                    {"secondsPlayed": secs, "points": secs // 120},
                    "G",
                ),
                entry(
                    HOME_ID, 2, "Al Jones", {"secondsPlayed": 1200, "points": 10}, "G"
                ),
            ],
            slug="basketball",
        )
    conn.commit()
    apps = load_appearances(conn, "basketball", [HOME_ID], KO_TS - 60, None)
    prm = player_model.sport_params("basketball")
    secs = [1800 if i < 5 else 600 for i in range(15)]
    w = [0.5 ** (i / prm.hl_minutes) for i in range(15)]
    expected_s = sum(a * b for a, b in zip(w, secs, strict=True)) / sum(w)
    mp = line_probability(line(PTS, "Smith, Joe", 14.5, "OVER"), "basketball", apps)
    assert mp.mean == pytest.approx(expected_s / 120.0)
    assert 600 / 120 < mp.mean < 1800 / 120  # more than the sample's mean of 7
    assert mp.p is not None and 0.0 < mp.p < 1.0
    assert mp.n == 15


def test_a_combined_line_models_the_sum_and_conditions_on_no_push(
    tmp_path: Path,
) -> None:
    conn = make_db(tmp_path / "db.sqlite")
    for i in range(10):
        add_game(
            conn,
            400 + i,
            KO_TS - (i + 1) * 86400,
            [
                entry(
                    HOME_ID,
                    1,
                    "Joe Smith",
                    {"secondsPlayed": 1500, "points": 10 + (i % 2) * 4, "rebounds": 5},
                    "F",
                )
            ],
            slug="basketball",
        )
    conn.commit()
    apps = load_appearances(conn, "basketball", [HOME_ID], KO_TS - 60, None)
    over = line_probability(
        line(PTS_REB, "Smith, Joe", 16.5, "OVER"), "basketball", apps
    )
    under = line_probability(
        line(PTS_REB, "Smith, Joe", 16.5, "UNDER"), "basketball", apps
    )
    assert over.mean == pytest.approx(17.0)  # the sum of sums, 15 / 19 alternating
    assert over.p is not None and under.p is not None
    assert over.p + under.p == pytest.approx(1.0)
    # An integer line: the push is VOID, so the two sides still sum to one.
    o17 = line_probability(
        line(PTS_REB, "Smith, Joe", 17.0, "OVER"), "basketball", apps
    )
    u17 = line_probability(
        line(PTS_REB, "Smith, Joe", 17.0, "UNDER"), "basketball", apps
    )
    assert o17.p is not None and u17.p is not None
    assert o17.p + u17.p == pytest.approx(1.0)


def test_plus_minus_is_a_signed_normal(tmp_path: Path) -> None:
    conn = make_db(tmp_path / "db.sqlite")
    hockey_history(conn, games=9)  # Novak -1, 0, 1, ... mean 0
    for i in range(9):
        add_game(
            conn,
            500 + i,
            KO_TS - (i + 30) * 86400,
            [
                entry(
                    HOME_ID,
                    7,
                    "Ivo Minus",
                    {"secondsPlayed": 1000, "plusMinus": -3 + (i % 2)},
                    "D",
                )
            ],
        )
    conn.commit()
    apps = apps_of(conn)
    at_zero = line_probability(
        line(PLUS_MINUS, "Novak, Jan", -0.5, "OVER"), "hockey", apps
    )
    above = line_probability(
        line(PLUS_MINUS, "Novak, Jan", 0.5, "OVER"), "hockey", apps
    )
    assert at_zero.p is not None and above.p is not None
    assert at_zero.p > 0.5 > above.p
    neg = line_probability(
        line(PLUS_MINUS, "Minus, Ivo", -0.5, "UNDER"), "hockey", apps
    )
    # Shrunk toward the pool by the fitted prior_games_signed pseudo-games
    # (no other defenceman: the pool's mean is 0).
    k = player_model.sport_params("hockey").prior_games_signed
    assert neg.mean == pytest.approx(-23 / (9 + k))  # -3, -2, ... over 9 games
    assert neg.p is not None and neg.p > 0.5 and neg.mean < 0


def test_too_few_appearances_or_an_unknown_name_give_no_p(tmp_path: Path) -> None:
    conn = make_db(tmp_path / "db.sqlite")
    hockey_history(conn, games=player_model.MIN_APPEARANCES - 1)
    conn.commit()
    apps = apps_of(conn)
    thin = line_probability(line(SOG, "Novak, Jan", 2.5, "OVER"), "hockey", apps)
    assert thin.p is None and thin.reason == "THIN_SAMPLE"
    assert thin.n == player_model.MIN_APPEARANCES - 1
    nobody = line_probability(line(SOG, "Nobody, Atall", 2.5, "OVER"), "hockey", apps)
    assert nobody.p is None and nobody.reason == "NOT_IN_HISTORY"
    assert "MIN_APPEARANCES" in UNFITTED


# --- SHADOW_SETTLE: attached, grades unchanged -----


def _settle_event() -> dict[str, Any]:
    return {
        "id": 700,
        "startTimestamp": KO_TS,
        "homeTeam": {"name": T1, "id": HOME_ID},
        "awayTeam": {"name": T2, "id": AWAY_ID},
        "tournament": {"name": "Extraliga"},
    }


GAME_LINEUPS = {
    "home": {
        "players": [
            entry(
                HOME_ID, 1, "Jan Novak", {"secondsPlayed": 1200, "goals": 4, "shots": 4}
            )
        ]
    },
    "away": {
        "players": [
            entry(
                AWAY_ID,
                3,
                "Karel Dvorak",
                {"secondsPlayed": 1000, "goals": 3, "shots": 1},
            )
        ]
    },
}


def _write_player_snapshot(runs: Path) -> None:
    lines = [
        ShadowLine("1", 623, "total", 0, "", 5.5, side, 1.9).as_dict()
        for side in ("OVER", "UNDER")
    ] + [
        ShadowLine(
            "1", SOG, "player_shots_on_goal", 0, "Novak, Jan", 2.5, side, odds
        ).as_dict()
        for side, odds in (("OVER", 1.8), ("UNDER", 2.0))
    ]
    day = runs / "shadow" / "hockey" / DATE
    day.mkdir(parents=True, exist_ok=True)
    (day / "snapshots.jsonl").write_text(
        json.dumps(
            {
                "fetched_at_utc": "2026-09-28T15:00:00Z",
                "superbet_event_id": "1",
                "match_name": f"{T1}·{T2}",
                "team1": T1,
                "team2": T2,
                "kickoff_utc": "2026-09-28T16:00:00Z",
                "tournament": "Extraliga",
                "lines": lines,
            }
        )
        + "\n"
    )


def _settle(runs: Path, db: str | None) -> dict[str, Any]:
    _write_player_snapshot(runs)
    client = LineupsClient({**_settle_event(), **HOCKEY_AET}, GAME_LINEUPS)
    settle_shadow.settle(
        DATE,
        FakeResolver(_settle_event()),  # type: ignore[arg-type]
        client,  # type: ignore[arg-type]
        None,
        str(runs),
        KICKOFF + timedelta(hours=6),
        ("hockey",),
        db_path=db,
    )
    path = runs / "shadow" / "hockey" / DATE / "settled.json"
    return dict(json.loads(path.read_text())["events"]["1"])


def _without_model(rec: dict[str, Any]) -> str:
    rec = {k: v for k, v in rec.items() if k != "player_model_error"}
    rec["graded"] = [
        {k: v for k, v in g.items() if k not in MODEL_KEYS} for g in rec["graded"]
    ]
    return json.dumps(rec, sort_keys=True)


@pytest.fixture
def db(tmp_path: Path) -> str:
    path = tmp_path / "db.sqlite"
    conn = make_db(path)
    hockey_history(conn)
    conn.commit()
    conn.close()
    return str(path)


def test_settle_attaches_the_model_and_leaves_every_grade_byte_identical(
    tmp_path: Path, db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare = _settle(tmp_path / "a", None)
    modelled = _settle(tmp_path / "b", db)
    assert _without_model(bare) == _without_model(modelled)
    player = [g for g in modelled["graded"] if g["family"] == "player_shots_on_goal"]
    assert len(player) == 2
    for g in player:
        assert g["model_source"] == "settle" and g["model"] == player_model.MODEL_NAME
        assert g["model_n"] == 8 and 0.0 < g["model_p"] < 1.0
        assert g["unfitted_constants"] == list(UNFITTED)
    assert sum(g["model_p"] for g in player) == pytest.approx(1.0, abs=2e-4)
    # Team lines carry nothing of the model.
    assert all("model_p" not in g for g in modelled["graded"] if g["family"] == "total")

    def boom(*_: Any, **__: Any) -> None:
        raise RuntimeError("model down")

    monkeypatch.setattr(player_model, "load_appearances", boom)
    failed = _settle(tmp_path / "c", db)
    assert failed["player_model_error"] == "RuntimeError: model down"
    assert _without_model(failed) == _without_model(bare)
    assert all("model_p" not in g for g in failed["graded"])


def test_settle_prefers_the_last_pregame_forecast_before_the_start(
    tmp_path: Path, db: str
) -> None:
    runs = tmp_path / "runs"
    day = runs / "shadow" / "hockey" / DATE
    day.mkdir(parents=True)
    base = {
        "superbet_event_id": "1",
        "market_id": SOG,
        "subject": "Novak, Jan",
        "line": 2.5,
        "side": "OVER",
        "model_n": 7,
        "model": player_model.MODEL_NAME,
        "unfitted_constants": ["X"],
    }
    rows = [
        {**base, "fetched_at_utc": "2026-09-28T14:00:00Z", "model_p": 0.55},
        {**base, "fetched_at_utc": "2026-09-28T15:00:00Z", "model_p": 0.61},
        # Newer, before the start, but an older model wrote it: never attached.
        {
            **base,
            "fetched_at_utc": "2026-09-28T15:10:00Z",
            "model_p": 0.42,
            "model": "player_rate_v1",
        },
        {**base, "fetched_at_utc": "2026-09-28T15:30:00Z", "model_p": None},
        {**base, "fetched_at_utc": "2026-09-28T16:30:00Z", "model_p": 0.99},  # in play
    ]
    (day / "player_model.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    rec = _settle(runs, db)
    over = next(g for g in rec["graded"] if g.get("subject") and g["side"] == "OVER")
    under = next(g for g in rec["graded"] if g.get("subject") and g["side"] == "UNDER")
    assert over["model_source"] == "pregame" and over["model_p"] == 0.61
    assert over["model_fetched_at_utc"] == "2026-09-28T15:00:00Z"
    # No forecast for the UNDER side: computed at settle.
    assert under["model_source"] == "settle"
    assert over["model"] == under["model"] == player_model.MODEL_NAME
    assert _without_model(rec) == _without_model(_settle(tmp_path / "bare", None))


# --- SHADOW: the pre-game forecast -----


class PlayerSuperbet:
    def events_by_date(self, start: datetime, end: datetime, offer_state: str) -> list:
        return [
            {
                "sportId": 3,
                "eventId": 1,
                "matchName": f"{T1}·{T2}",
                "utcDate": "2026-09-28T16:00:00Z",
                "tournamentId": 7,
            }
        ]

    def event_odds(self, event_id: str) -> dict[str, Any]:
        market = "Celne strzały zawodnika (z dogrywką)"

        def side(word: str, price: float) -> dict[str, Any]:
            return {
                "marketId": SOG,
                "marketName": market,
                "name": f"Novak, Jan - {word} 2.5",
                "info": "",
                "code": None,
                "specifiers": {"player": "Novak, Jan", "total": "2.5"},
                "status": "active",
                "price": price,
            }

        return {"odds": [side("powyżej", 1.8), side("poniżej", 2.0)]}

    def _get_json(self, path: str) -> dict[str, Any]:
        return {"data": {"tournaments": []}}


def _snapshot(runs: Path, db: str | None) -> dict[str, Any]:
    return run_shadow.snapshot(
        DATE,
        PlayerSuperbet(),  # type: ignore[arg-type]
        str(runs),
        at=datetime(2026, 9, 28, 14, tzinfo=UTC),
        db_path=db,
    )


def test_shadow_writes_an_idempotent_pregame_forecast(tmp_path: Path, db: str) -> None:
    conn = sqlite3.connect(db)
    # T1 through RESOLVE's entity cache, T2 through the listed games' names.
    conn.execute(
        "INSERT INTO sofa_entity VALUES "
        "('ice-hockey', ?, ?, ?, 'team', '', 'verified')",
        (player_model.normalize_name(T1), HOME_ID, T1),
    )
    conn.commit()
    conn.close()
    runs = tmp_path / "runs"
    result = _snapshot(runs, db)
    assert result["verdict"] == "OK"
    path = runs / "shadow" / "hockey" / DATE / "player_model.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    assert {r["side"] for r in rows} == {"OVER", "UNDER"}
    for r in rows:
        assert r["teams_resolved"] == 2 and r["model_n"] == 8
        assert r["fetched_at_utc"] == "2026-09-28T14:00:00Z"
        assert r["odds"] in (1.8, 2.0) and 0.0 < r["fair_p"] < 1.0
        assert r["model_p"] is not None and r["computed_at_utc"]
        assert r["unfitted_constants"] == list(UNFITTED) + ["TEAM_NAME_WINDOW_S"]
    assert result["player_model"] == {"hockey/2026-09-28": {"rows": 2, "with_p": 2}}
    # The same snapshot again (same fetched_at): nothing appended twice.
    _snapshot(runs, db)
    assert len(path.read_text().splitlines()) == 2


def test_a_failing_model_never_alters_the_snapshot(
    tmp_path: Path, db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = _snapshot(tmp_path / "plain", None)

    def boom(*_: Any, **__: Any) -> list[dict[str, Any]]:
        raise RuntimeError("model down")

    monkeypatch.setattr(player_model, "forecast_records", boom)
    broken = _snapshot(tmp_path / "broken", db)
    rel = Path("shadow") / "hockey" / DATE / "snapshots.jsonl"
    assert (tmp_path / "plain" / rel).read_bytes() == (
        tmp_path / "broken" / rel
    ).read_bytes()
    assert broken["verdict"] == plain["verdict"] == "OK"
    assert broken["metrics"] == plain["metrics"]
    assert (
        broken["player_model"]["hockey/2026-09-28"]["error"]
        == "RuntimeError: model down"
    )
    assert not (
        tmp_path / "broken" / "shadow" / "hockey" / DATE / "player_model.jsonl"
    ).exists()


def test_the_sport_coupons_never_read_the_player_model() -> None:
    for rel in (
        "src/bet/sofa/sport_coupon.py",
        "scripts/sofa/run_sport_coupon.py",
        "scripts/sofa/settle_sport_coupon.py",
    ):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "player_model" not in text, rel
    code = (
        "import sys; import scripts.sofa.run_sport_coupon; "
        "import scripts.sofa.settle_sport_coupon; "
        "sys.exit(1 if 'bet.sofa.player_model' in sys.modules else 0)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        env={"PYTHONPATH": f"{REPO / 'src'}:{REPO}", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr


# --- the measurement -----


def test_measure_player_props_on_a_fixture(tmp_path: Path, db: str) -> None:
    runs = tmp_path / "runs"
    day = runs / "shadow" / "hockey" / DATE
    day.mkdir(parents=True)
    graded = []
    for k, (side, outcome) in enumerate((("OVER", "WIN"), ("UNDER", "LOSS"))):
        graded.append(
            {
                "superbet_event_id": "1",
                "market_id": SOG,
                "family": "player_shots_on_goal",
                "period": 0,
                "subject": "Novak, Jan",
                "line": 2.5,
                "side": side,
                "odds": 1.9,
                "fair_p": 0.5,
                "outcome": outcome,
                "model_p": 0.6 - 0.2 * k,
                "model_source": "pregame",
            }
        )
    graded.append({**graded[0], "subject": "Nobody, Atall"})
    (day / "settled.json").write_text(
        json.dumps(
            {
                "events": {
                    "1": {
                        "state": "SETTLED",
                        "sofascore_event_id": 700,
                        "kickoff_utc": "2026-09-28T16:00:00Z",
                        "graded": graded,
                    }
                }
            }
        )
    )
    conn = sqlite3.connect(db)
    add_game(conn, 700, KO_TS, [])
    conn.commit()
    conn.close()
    out = tmp_path / "rows.jsonl"
    report = tmp_path / "report.json"
    code = measure_player_props.main(
        [
            "--runs-dir",
            str(runs),
            "--db",
            db,
            "--sport",
            "hockey",
            "--rows-out",
            str(out),
            "--json-out",
            str(report),
            "--bootstrap",
            "20",
        ]
    )
    assert code == 0
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    assert {r["source"] for r in rows} == {"recomputed", "pregame"}
    assert sum(r["source"] == "recomputed" for r in rows) == 2
    doc = json.loads(report.read_text())
    assert doc["skipped"] == {"hockey:recomputed:NOT_IN_HISTORY": 1}
    group = doc["groups"]["hockey|recomputed|player_shots_on_goal"]
    assert group["sides"] == 2 and group["lines"] == 1 and group["games"] == 1
    assert "brier_model" in group and group["split_half"]["odd"] is None
    assert doc["groups"]["hockey|pregame|ALL"]["sides"] == 3


def test_an_unimportable_model_costs_the_number_never_the_grade_or_snapshot(
    tmp_path: Path, db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model is imported lazily: a module that cannot even be imported
    must leave SHADOW's snapshot and SHADOW_SETTLE's grades as they are."""
    bare = _settle(tmp_path / "a", None)
    plain = _snapshot(tmp_path / "plain", None)
    monkeypatch.setitem(sys.modules, "bet.sofa.player_model", None)
    graded = _settle(tmp_path / "b", db)
    assert _without_model(graded) == _without_model(bare)
    assert "bet.sofa.player_model" in graded["player_model_error"]
    broken = _snapshot(tmp_path / "broken", db)
    rel = Path("shadow") / "hockey" / DATE / "snapshots.jsonl"
    assert (tmp_path / "plain" / rel).read_bytes() == (
        tmp_path / "broken" / rel
    ).read_bytes()
    assert broken["verdict"] == plain["verdict"] == "OK"
    assert "bet.sofa.player_model" in json.dumps(broken["player_model"])


# --- player_rate_v2: fitted constants, the replay, the calibration map -----


def test_v2_is_the_default_and_its_constants_load_with_provenance() -> None:
    assert player_model.MODEL_NAME == "player_rate_v2"
    params = player_model.load_params()
    assert set(params) == {"basketball", "hockey"}
    for prm in params.values():
        assert prm.pool in player_model.POOL_KINDS
        assert prm.max_sample >= player_model.MIN_APPEARANCES
        assert prm.hl_minutes > 0 and prm.k_phi > 0 and prm.prior_games > 0
        assert prm.sig_a >= 0 and prm.calibration_b is not None
    prov = player_model.params_provenance()
    assert prov["criterion"]
    splits = prov["fitted_from"]["splits"]
    for sport in ("basketball", "hockey"):
        assert splits[sport]["train"]["player_games"] > 0
        assert splits[sport]["test"]["player_games"] > 0
    doc = json.loads((REPO / "config" / player_model.PARAMS_FILE).read_text())
    for sport, entry in doc["sports"].items():
        assert entry["calibration_b"]["n"] > 0, sport
    # A fitted constant is no longer listed as unfitted; the chosen ones are.
    for name in ("N_MINUTES", "PRIOR_GAMES", "K_PHI", "MAX_SAMPLE"):
        assert name not in UNFITTED
    assert set(UNFITTED) == {
        "HISTORY_GAMES",
        "MIN_APPEARANCES",
        "MIN_SD_SIGNED",
        "CUTOFF_MARGIN_S",
    }


def test_a_file_without_provenance_or_for_another_model_is_refused() -> None:
    doc = json.loads((REPO / "config" / player_model.PARAMS_FILE).read_text())
    player_model.parse_params(doc)
    with pytest.raises(ValueError, match="fitted_from"):
        player_model.parse_params({**doc, "fitted_from": {}})
    with pytest.raises(ValueError, match="criterion"):
        player_model.parse_params({k: v for k, v in doc.items() if k != "criterion"})
    with pytest.raises(ValueError, match="player_rate_v1"):
        player_model.parse_params({**doc, "model": "player_rate_v1"})


def test_nb_pmf_is_joint_count_pmf() -> None:
    from bet.sofa.joint import count_pmf

    for mean, var in ((0.3, 0.3), (2.0, 5.0), (14.0, 30.0), (40.0, 41.0), (0.0, 1.0)):
        a = player_model.nb_pmf(mean, var, 80)
        b = count_pmf(mean, var, 80)
        assert max(abs(x - y) for x, y in zip(a, b, strict=True)) < 1e-12


def test_the_calibration_map_is_monotone_symmetric_and_count_families_only(
    tmp_path: Path,
) -> None:
    ps = [i / 100 for i in range(1, 100)]
    for b in (0.5, 0.9, 1.0, 1.3):
        mapped = [player_model.calibrate_side(p, b) for p in ps]
        assert all(x < y for x, y in zip(mapped, mapped[1:], strict=False))
        for p, m in zip(ps, mapped, strict=True):
            assert player_model.calibrate_side(1 - p, b) == pytest.approx(1 - m)
    assert player_model.calibrate_side(0.73, None) == 0.73
    assert player_model.calibrate_side(0.5, 0.7) == pytest.approx(0.5)
    conn = make_db(tmp_path / "db.sqlite")
    hockey_history(conn, games=9)
    conn.commit()
    apps = apps_of(conn)
    base = player_model.sport_params("hockey")
    off = dataclasses.replace(base, calibration_b=None)
    half = dataclasses.replace(base, calibration_b=0.5)
    sog = line(SOG, "Novak, Jan", 1.5, "OVER")
    p_off = line_probability(sog, "hockey", apps, off).p
    p_half = line_probability(sog, "hockey", apps, half).p
    assert p_off is not None and p_half is not None
    assert p_half == pytest.approx(player_model.calibrate_side(p_off, 0.5))
    assert abs(p_half - 0.5) < abs(p_off - 0.5)
    pm_line = line(PLUS_MINUS, "Novak, Jan", 0.5, "OVER")
    assert (
        line_probability(pm_line, "hockey", apps, off).p
        == line_probability(pm_line, "hockey", apps, half).p
    )


def test_volatile_minutes_widen_the_distribution(tmp_path: Path) -> None:
    """Same rate and mean minutes; the player whose minutes swing gets the
    less confident number at a line far from his mean (the v1 defect)."""
    conn = make_db(tmp_path / "db.sqlite")
    for i in range(12):
        swing = 2700 if i % 2 else 300
        add_game(
            conn,
            800 + i,
            KO_TS - (i + 1) * 86400,
            [
                entry(HOME_ID, 1, "Joe Steady", {"secondsPlayed": 1500, "points": 15}),
                entry(
                    HOME_ID,
                    2,
                    "Bob Swing",
                    {"secondsPlayed": swing, "points": swing // 100},
                ),
            ],
            slug="basketball",
        )
    conn.commit()
    apps = load_appearances(conn, "basketball", [HOME_ID], KO_TS - 60, None)
    steady = line_probability(
        line(PTS, "Steady, Joe", 24.5, "UNDER"), "basketball", apps
    )
    swing_ = line_probability(
        line(PTS, "Swing, Bob", 24.5, "UNDER"), "basketball", apps
    )
    assert steady.p is not None and swing_.p is not None
    assert swing_.p < steady.p


def test_the_replay_is_leak_free_and_reproduces_line_probability(
    tmp_path: Path,
) -> None:
    from scripts.sofa import fit_player_model as fpm

    conn = make_db(tmp_path / "db.sqlite")
    hockey_history(conn, games=8)
    target = 900
    add_game(
        conn,
        target,
        KO_TS,
        [
            entry(HOME_ID, 1, "Jan Novak", {"secondsPlayed": 1300, "shots": 9}),
            entry(HOME_ID, 2, "Petr Svoboda", {"secondsPlayed": 1100, "shots": 2}),
        ],
    )
    # Inside the margin before kickoff, and after it: neither may be read.
    add_game(
        conn,
        901,
        KO_TS - 30,
        [entry(HOME_ID, 1, "Jan Novak", {"secondsPlayed": 1200, "shots": 40})],
    )
    add_game(
        conn,
        902,
        KO_TS + 86400,
        [entry(HOME_ID, 1, "Jan Novak", {"secondsPlayed": 1200, "shots": 50})],
    )
    conn.commit()
    history = fpm.History.from_db(conn, "hockey")
    specs = fpm.family_specs("hockey")
    sog = [s.family for s in specs].index("player_shots_on_goal")
    recs = {r.pid: r for r in fpm.replay_game(history, target, specs)}
    novak = recs[1]
    cutoff = player_model.history_cutoff(KO_TS, KO_TS)
    assert novak.act_s == 1300 and novak.act[sog] == 9.0
    assert len(novak.own) == 8 and all(ts < cutoff for ts, _, _ in novak.own)
    assert all(v[sog] in (2.0, 4.0) for _, _, v in novak.own)
    # The in-memory history is load_appearances, row for row.
    mem = history.appearances_before([HOME_ID, AWAY_ID], cutoff, target)
    sql = load_appearances(conn, "hockey", [HOME_ID, AWAY_ID], cutoff, target)
    assert [(a.event_id, a.player_id, a.ts) for a in mem] == [
        (a.event_id, a.player_id, a.ts) for a in sql
    ]
    prm = player_model.sport_params("hockey")
    checked = 0
    for f, spec in enumerate(specs):
        got = fpm.record_distribution(novak, f, spec.family, prm)
        if got is None:
            continue
        mid = next(
            m
            for m, s in player_model.PLAYER_MARKETS["hockey"].items()
            if s.family == spec.family
        )
        ln = ShadowLine("1", mid, spec.family, 0, "Novak, Jan", 1.5, "OVER", 1.9)
        p = player_model.side_probability(ln, got[0])
        assert p is not None
        if spec.family not in player_model.SIGNED_FAMILIES:
            p = player_model.calibrate_side(p, prm.calibration_b)
        assert line_probability(ln, "hockey", sql, prm).p == pytest.approx(p, abs=1e-12)
        checked += 1
    assert checked == 2  # shots and plus-minus are in the fixture's boxes
    # A later game changing cannot move the record.
    later = {
        "home": {
            "players": [
                entry(HOME_ID, 1, "Jan Novak", {"secondsPlayed": 3000, "shots": 99})
            ]
        }
    }
    conn.execute(
        "UPDATE sofa_event_stats SET lineups_json = ? WHERE sofascore_event_id = 902",
        (json.dumps(later),),
    )
    conn.commit()
    again = fpm.replay_game(fpm.History.from_db(conn, "hockey"), target, specs)
    assert {r.pid: r for r in again}[1] == novak
