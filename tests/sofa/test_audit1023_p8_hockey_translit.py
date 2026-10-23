"""P8 hockey part (coverage audit 2026-10-23, section 3 B9): the pre-game
strict name rule (player_model.names_agree) folds transliterations -
umlauts written out, a Russian initial "Ye", "x" / "ks", a final "-iy" /
"-y" - behind epochs.name_rules_1023, by the game's day and the clock."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.sofa import epochs, player_model
from bet.sofa.player_model import names_agree, translit_token
from bet.sofa.shadow import ShadowLine
from tests.sofa.test_player_model import (
    HOME_ID,
    KO_TS,
    SOG,
    T1,
    T2,
    add_game,
    entry,
    make_db,
)


@pytest.mark.parametrize(
    ("subject", "candidate"),
    [
        ("Stuetzle, Tim", "Tim Stützle"),
        ("Chinakhov, Yegor", "Egor Chinakhov"),
        ("Romanov, Aleksei", "Alexei Romanov"),
        ("Orlov, Dmitriy", "Dmitry Orlov"),
    ],
)
def test_a_transliteration_agrees_only_under_the_rule(
    subject: str, candidate: str
) -> None:
    assert not names_agree(subject, candidate)
    assert names_agree(subject, candidate, translit=True)


@pytest.mark.parametrize(
    ("subject", "candidate"),
    [
        ("Williams, Jalen", "Jaylin Williams"),
        ("Chinakhov, Yegor", "Igor Chinakhov"),
        ("Stuetzle, Tim", "Tom Stützle"),
        ("Muller, Jan", "Jan Miller"),
        # Folded tokens are compared for equality only (basketball's stored
        # names, 2026-10-23): no prefix, no initial over a fold.
        ("Evans, Jeremy", "Jeremiah Evans"),
        ("Taylor, Trae", "Travis Taylor"),
        ("Harris, Chae", "Chaze Harris"),
        ("Romanov, Aleksandr", "Alexander Romanov"),
    ],
)
def test_the_fold_is_still_the_strict_rule(subject: str, candidate: str) -> None:
    assert not names_agree(subject, candidate, translit=True)


def test_the_fold_of_one_token() -> None:
    assert translit_token("stuetzle") == "stutzle"
    assert translit_token("yegor") == "egor"
    assert translit_token("alexander") == "aleksander"
    assert translit_token("dmitriy") == translit_token("dmitry") == "dmitri"
    assert translit_token("ye") == "ye"  # too short to be "Ye-" anything


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "db.sqlite"
    conn = make_db(db)
    for i in range(6):
        add_game(
            conn,
            100 + i,
            KO_TS - (i + 1) * 2 * 86400,
            [entry(HOME_ID, 5, "Tim Stützle", {"secondsPlayed": 1200, "shots": 3})],
        )
    conn.commit()
    conn.close()
    return db


def _forecast(db: Path) -> list[dict[str, object]]:
    rec = {
        "fetched_at_utc": "2026-09-28T14:00:00Z",
        "superbet_event_id": "1",
        "kickoff_utc": "2026-09-28T16:00:00Z",
        "team1": T1,
        "team2": T2,
        "lines": [
            ShadowLine(
                "1", SOG, "player_shots_on_goal", 0, "Stuetzle, Tim", 2.5, "OVER", 1.9
            ).as_dict()
        ],
    }
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return player_model.forecast_records(
            conn, "hockey", "ice-hockey", [rec], "x", set(), KO_TS
        )
    finally:
        conn.close()


def test_the_forecast_follows_the_days_name_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _db(tmp_path)
    monkeypatch.setattr(epochs, "NAME_RULES_1023_FROM_UTC", None)
    off = _forecast(db)
    assert [r["model_reason"] for r in off] == ["NAME_UNCERTAIN"]
    assert "name_rule" not in off[0]
    monkeypatch.setattr(
        epochs, "NAME_RULES_1023_FROM_UTC", datetime(2026, 9, 29, tzinfo=UTC)
    )
    assert _forecast(db) == off
    monkeypatch.setattr(
        epochs, "NAME_RULES_1023_FROM_UTC", datetime(2026, 9, 1, tzinfo=UTC)
    )
    on = _forecast(db)
    assert on[0]["model_p"] is not None and on[0]["model_player_id"] == 5
    assert on[0]["name_rule"] == player_model.NAME_RULE_TRANSLIT


def test_basketball_never_folds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "db.sqlite"
    conn = make_db(db)
    for i in range(6):
        add_game(
            conn,
            100 + i,
            KO_TS - (i + 1) * 2 * 86400,
            [entry(HOME_ID, 5, "Tim Stützle", {"secondsPlayed": 1200, "points": 3})],
            slug="basketball",
        )
    conn.commit()
    monkeypatch.setattr(
        epochs, "NAME_RULES_1023_FROM_UTC", datetime(2026, 9, 1, tzinfo=UTC)
    )
    rec = {
        "fetched_at_utc": "2026-09-28T14:00:00Z",
        "superbet_event_id": "1",
        "kickoff_utc": "2026-09-28T16:00:00Z",
        "team1": T1,
        "team2": T2,
        "lines": [
            ShadowLine(
                "1", 233565, "player_points", 0, "Stuetzle, Tim", 2.5, "OVER", 1.9
            ).as_dict()
        ],
    }
    rows = player_model.forecast_records(
        conn, "basketball", "basketball", [rec], "x", set(), KO_TS
    )
    conn.close()
    assert rows[0]["model_p"] is None and "name_rule" not in rows[0]
