"""K5 (identity plan): a NO_GAME_WITHIN_1H read from a cached team page is
asked again fresh near the start, and only a fresh page of a team resolved by
id with no game of it within 12 h is the proven absence NOT_ON_SOFASCORE
(epochs.NOT_ON_SOFASCORE_FROM_UTC)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from bet.sofa import epochs
from bet.sofa import sport_identity as si
from tests.sofa.test_sport_identity import KICK, FakeClient, _ev, _listed

NEAR = KICK - timedelta(hours=1)  # an hour before the start: inside the recheck


class StaleCache:
    """A cached page (whatever its age) - the fresh re-ask bypasses it."""

    def __init__(self, pages: dict[int, list[dict[str, Any]]]) -> None:
        self.pages = pages
        self.saved: list[int] = []

    def get_entity_events(
        self, team: int, kind: str, page: int
    ) -> dict[str, Any] | None:
        return {"events": self.pages[team]} if team in self.pages else None

    def save_entity_events(
        self, team: int, kind: str, page: int, events: dict[str, Any]
    ) -> None:
        self.saved.append(team)


TEAMS = {"Sparta Praha": 10, "Kometa Brno": 20}


def _run(
    client: FakeClient,
    cache: StaleCache,
    at: datetime = NEAR,
    absence: bool = True,
    teams: dict[str, int] | None = None,
    query: Any = None,
) -> dict[str, Any]:
    t = TEAMS if teams is None else teams
    (r,), _ = si.identify(
        [_ev("1", "Sparta Praha", "Kometa Brno")],
        client,
        cache,
        lambda s, n: t.get(n),
        at,
        "2026-10-06",
        query_teams=query,
        absence=absence,
    )
    return r


def test_a_stale_page_is_asked_again_and_finds_the_game() -> None:
    game = _listed(9001, (10, "Sparta Praha"), (20, "Kometa Brno"))
    cache = StaleCache({10: []})  # the cached page had no game
    off = _run(FakeClient({10: [game]}), cache, absence=False)
    assert off["reason"] == "NO_GAME_WITHIN_1H"
    client = FakeClient({10: [game]})
    on = _run(client, StaleCache({10: []}))
    assert on["status"] == si.IDENTIFIED and on["fresh_recheck"] is True
    assert client.calls == [10]


def test_far_from_the_start_the_cache_stands() -> None:
    client = FakeClient({10: []})
    r = _run(client, StaleCache({10: []}), at=KICK - timedelta(hours=8))
    assert r["reason"] == "NO_GAME_WITHIN_1H" and client.calls == []
    assert "absence_evidence" not in r  # a cached page proves nothing


def test_a_fresh_page_with_no_game_in_12h_is_the_proven_absence() -> None:
    week = _listed(1, (10, "Sparta Praha"), (30, "Other"), KICK + timedelta(days=3))
    r = _run(FakeClient({10: [week]}), StaleCache({10: []}))
    assert r["status"] == si.NOT_IDENTIFIED and r["reason"] == "NOT_ON_SOFASCORE"
    ev = r["absence_evidence"]
    assert (
        ev["team_id"] == 10 and ev["nearest_game_h"] == 72.0 and ev["window_h"] == 12.0
    )


def test_a_game_two_hours_away_is_a_moved_start_not_an_absence() -> None:
    # 10-14 Kavkasia - Lausanne: Sofascore had the game 2 h after Superbet
    moved = _listed(
        1, (10, "Sparta Praha"), (20, "Kometa Brno"), KICK + timedelta(hours=2)
    )
    r = _run(FakeClient({10: [moved]}), StaleCache({10: []}))
    assert r["reason"] == "NO_GAME_WITHIN_1H" and r["nearest_game_h"] == 2.0


def test_a_query_only_team_proves_nothing() -> None:
    r = _run(
        FakeClient({10: []}),
        StaleCache({}),
        teams={},
        query=lambda s, n: 10 if n == "Sparta Praha" else None,
    )
    assert r["reason"] == "NO_GAME_WITHIN_1H" and r.get("query_only") is True


def test_a_team_is_asked_fresh_once_a_run() -> None:
    client = FakeClient({10: []})
    cache = StaleCache({10: []})
    refreshed: set[int] = set()
    for sb in ("1", "2"):
        r = si.identify_event(
            _ev(sb, "Sparta Praha", "Kometa Brno"),
            client,
            cache,
            lambda s, n: TEAMS.get(n),
            NEAR,
            absence=True,
            refreshed=refreshed,
        )
        assert r["status"] == si.NOT_IDENTIFIED
    assert client.calls == [10] and refreshed == {10}


def test_the_switch_is_next_days_midnight() -> None:
    assert epochs.NOT_ON_SOFASCORE_FROM_UTC == datetime(2026, 10, 15, tzinfo=UTC)
    assert epochs.not_on_sofascore(
        "2026-10-15", datetime(2026, 10, 15, 0, 1, tzinfo=UTC)
    )
    assert not epochs.not_on_sofascore(
        "2026-10-14", datetime(2026, 10, 15, 1, tzinfo=UTC)
    )
