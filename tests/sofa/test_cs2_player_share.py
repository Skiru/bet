"""CS2 player share (epochs.CS2_PLAYER_SHARE_FROM_UTC) and the impossible
headshot rows load_history drops (POMIAR_CS2_PLAYER_KILLS_2026-10-20, offline)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.sofa import cs2_engine as eng
from bet.sofa import epochs
from bet.sofa.cs2_store import save_series
from bet.sofa.db import migrate
from tests.sofa.test_cs2_engine import A, B, series


def test_player_share_switch_from_2026_10_21() -> None:
    at = datetime(2026, 10, 21, tzinfo=UTC)
    assert epochs.cs2_player_share("2026-10-21", at)
    assert not epochs.cs2_player_share("2026-10-20", at)
    assert not epochs.cs2_player_share(
        "2026-10-21", datetime(2026, 10, 20, 23, 59, tzinfo=UTC))


def test_families_add_headshots_only_with_the_switch() -> None:
    assert "player_headshots" not in eng.ExposureBook().families
    on = eng.ExposureBook(player_share=True).families
    assert "player_headshots" in on
    assert eng.EXPOSURE_FAMILIES <= on


def _side(team: int, pid: int, kills: int, team_kills: int) -> eng.MapRow:
    # one map, the player's team won 13-10; four teammates hold the rest
    rest = (team_kills - kills) // 4
    players = tuple(
        [(team, pid, "p", (("kills", kills),))]
        + [(team, 900 + i, f"t{i}", (("kills", rest),)) for i in range(4)]
    )
    return eng.MapRow(1, 0, 1, team, B, 13, 10, True, players, None, 3)


def test_share_window_and_shrinkage_follow_the_switch() -> None:
    old, new = eng.ExposureBook(), eng.ExposureBook(player_share=True)
    # 20 maps at a quarter of the team's kills, then 20 at a tenth
    maps = [_side(A, 7, 20, 80)] * 20 + [_side(A, 7, 8, 80)] * 20
    for m in maps:
        old.update(m)
        new.update(m)
    assert len(old.player_recent[7]) == eng.MAX_SAMPLE
    assert len(new.player_recent[7]) == eng.SHARE_WINDOW
    k_old, k_new = eng.K_SHARE, eng.K_SHARE_BY_STAT["kills"]
    want_old = (20 * 8 + k_old * eng.SHARE_PRIOR * 80) / (20 * 80 + k_old * 80)
    want_new = (20 * 20 + 20 * 8 + k_new * eng.SHARE_PRIOR * 80) / (
        40 * 80 + k_new * 80)
    assert old.share(7, "kills") == pytest.approx(want_old)
    assert new.share(7, "kills") == pytest.approx(want_new)


def test_build_exposure_carries_the_switch() -> None:
    assert eng.build_exposure([], player_share=True).player_share
    assert not eng.build_exposure([]).player_share


def test_load_history_drops_headshots_above_kills(tmp_path: Path) -> None:
    db = str(tmp_path / "t.db")
    migrate(db)
    conn = sqlite3.connect(db)
    event, games, lineups = series(
        1, 1000, A, B, [(13, 9)],
        {0: [("home", 7, "REZ", 20), ("home", 8, "fox", 15)]})
    save_series(conn, event, games, lineups, "2026-09-28T00:00:00Z", True)
    conn.execute("UPDATE cs2_player_map SET headshots = 2030 WHERE player_id = 7")
    conn.execute("UPDATE cs2_player_map SET headshots = 9 WHERE player_id = 8")
    (m,) = eng.load_history(conn, 5000, None)
    stats = {pid: dict(s) for _, pid, _, s in m.players}
    assert "headshots" not in stats[7] and stats[7]["kills"] == 20
    assert stats[8]["headshots"] == 9


def test_a_key_without_fit_rows_is_not_a_thin_bucket() -> None:
    from scripts.sofa.fit_sport_confidence import no_curve_reason

    assert no_curve_reason("player_kills|OVER", set()) == "NO_HISTORY_ROWS"
    assert no_curve_reason("map_winner|TEAM", {"map_winner|TEAM"}).startswith(
        "NO_FIT_BUCKET_WITH_N>=")
