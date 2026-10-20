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


def _synthetic_history(n_maps: int = 120) -> list[eng.MapRow]:
    """Two teams of five, every map with rounds and full player rows."""
    import random

    rng = random.Random(5)
    out: list[eng.MapRow] = []
    for i in range(n_maps):
        hw = rng.random() < 0.55
        w, lost = 13, rng.randint(3, 11)
        hr, ar = (w, lost) if hw else (lost, w)
        players = []
        for team, base, rounds in ((A, 7, hr), (B, 70, ar)):
            for j in range(5):
                k = max(0, int(rounds * (0.9 + 0.1 * j) + rng.randint(-3, 3)))
                players.append((team, base + j, f"n{base + j}",
                                (("kills", k), ("deaths", rng.randint(8, 20)),
                                 ("assists", rng.randint(1, 8)),
                                 ("headshots", k // 2))))
        out.append(eng.MapRow(1000 + i, 1000 + i * 100, 1, A, B, hr, ar, hr > ar,
                              tuple(players), None, 3))
    return out


def test_model_probability_prices_headshots_from_the_exposure_only_when_on() -> None:
    from bet.sofa.cs2 import Cs2Line

    hist = _synthetic_history()
    ratings = eng.build_ratings(hist)
    hs = Cs2Line("e", "player_headshots", 1, "n9", 7.5, "OVER", 1.9)
    kills = Cs2Line("e", "player_kills", 1, "n9", 14.5, "OVER", 1.9)
    off, on = eng.build_exposure(hist), eng.build_exposure(hist, player_share=True)
    got = {name: eng.model_probability(line, A, B, "a", "b", 3, hist, ratings, True,
                                       exposure=book)
           for name, line, book in (("hs_off", hs, off), ("hs_on", hs, on),
                                    ("k_off", kills, off), ("k_on", kills, on))}
    assert all(v is not None for v in got.values())
    assert got["hs_off"].model != "round_exposure"  # type: ignore[union-attr]
    assert got["hs_on"].model == "round_exposure"  # type: ignore[union-attr]
    assert got["k_off"].model == got["k_on"].model == "round_exposure"  # type: ignore[union-attr]
    assert got["k_off"].p != got["k_on"].p  # type: ignore[union-attr]


def test_sport_confidence_builds_the_book_with_the_days_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.sofa import run_sport_confidence as rsc

    seen: list[bool] = []
    def fake(maps: list[eng.MapRow], share: bool = False) -> eng.ExposureBook:
        seen.append(share)
        return eng.ExposureBook()

    monkeypatch.setattr(rsc.cs2_engine, "build_exposure", fake)
    rsc.DbForecaster("unused.db", datetime(2026, 10, 20, 9, tzinfo=UTC),
                     "2026-10-20")._cs2_counts([])
    rsc.DbForecaster("unused.db", datetime(2026, 10, 21, 9, tzinfo=UTC),
                     "2026-10-21")._cs2_counts([])
    assert seen == [False, True]


def test_cs2_settle_builds_the_book_with_the_offered_days_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from contextlib import nullcontext
    from types import SimpleNamespace

    from scripts.sofa import settle_cs2 as sc

    seen: list[bool] = []
    monkeypatch.setattr(sc, "get_connection", lambda db: nullcontext(None))
    monkeypatch.setattr(sc, "load_history", lambda conn, before, eid: [])
    monkeypatch.setattr(sc, "build_ratings", lambda history, *a: {})
    monkeypatch.setattr(sc, "build_exposure",
                        lambda history, share=False: seen.append(share) or None)
    monkeypatch.setattr(sc, "model_probability", lambda *a, **k: SimpleNamespace(
        p=0.6, n=5, model="m"))
    fields = {k: None for k in sc.Cs2Line.__dataclass_fields__}
    for kick in (datetime(2026, 10, 20, 18, tzinfo=UTC),
                 datetime(2026, 10, 21, 18, tzinfo=UTC)):
        sc.attach_model([dict(fields)], SimpleNamespace(team1="a", team2="b"),
                        {"id": 1, "bestOf": 3}, {}, True, kick, "x.db")
    assert seen == [False, True]
