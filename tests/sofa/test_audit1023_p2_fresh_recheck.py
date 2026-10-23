"""Coverage audit 2026-10-23 P2 (B2; epochs.IDENTITY_FRESH_RECHECK_ALL_FROM_UTC):
SPORT_IDENTITY re-asks a fresh team page on ANY refusal read from a cached
page close to the start (not only K5's NO_GAME_WITHIN_1H), and asks the
second team's page when the first finds nothing. Off: exactly the old asks.

10-23 Maybe - Eternal Premium (CS2, 10:30Z): Maybe's page (1244353) cached at
05:31Z held only the Sokerorg series at 13:00 - NO_MATCH_IN_LISTING, which
the K5 re-ask never fired on, and Eternal Premium's page was never asked."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import sport_identity as si
from tests.sofa.test_not_on_sofascore import StaleCache
from tests.sofa.test_sport_identity import KICK, FakeClient, _ev, _listed

NEAR = KICK - timedelta(hours=1)
ON = datetime(2026, 10, 6, 0, 0, tzinfo=UTC)


def _series(eid: int, home: tuple[int, str], away: tuple[int, str],
            start: datetime = KICK) -> dict[str, Any]:
    e = _listed(eid, home, away, start, slug="esports", category="Counter Strike")
    e["status"] = {"type": "notstarted"}
    return e


MAYBE, ETERNAL, SOKERORG = 1244353, 1300001, 1300002
OTHER_SERIES = _series(1, (MAYBE, "Maybe"), (SOKERORG, "Sokerorg"),
                       KICK + timedelta(minutes=50))
THE_SERIES = _series(2, (MAYBE, "Maybe"), (ETERNAL, "Eternal Premium"))
CS2_IDS = {"Maybe": MAYBE, "Eternal Premium": ETERNAL}


def _cs2(client: FakeClient, cache: StaleCache, switch: datetime | None,
         monkeypatch: pytest.MonkeyPatch, at: datetime = NEAR,
         ids: dict[str, int] | None = None) -> dict[str, Any]:
    monkeypatch.setattr(epochs, "IDENTITY_FRESH_RECHECK_ALL_FROM_UTC", switch)
    t = CS2_IDS if ids is None else ids
    (r,), _ = si.identify([_ev("9", "Maybe", "Eternal Premium", sport="cs2")],
                          client, cache, lambda s, n: t.get(n), at,
                          "2026-10-06", absence=True)
    return r


def test_off_a_cached_cs2_miss_is_never_asked_again(
        monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient({MAYBE: [OTHER_SERIES, THE_SERIES]})
    r = _cs2(client, StaleCache({MAYBE: [OTHER_SERIES]}), None, monkeypatch)
    assert r["status"] == si.NOT_IDENTIFIED
    assert r["reason"] == "NO_MATCH_IN_LISTING"
    assert client.calls == []  # neither a fresh page nor the second team


def test_on_a_cached_cs2_miss_near_the_start_is_asked_fresh(
        monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient({MAYBE: [OTHER_SERIES, THE_SERIES]})
    r = _cs2(client, StaleCache({MAYBE: [OTHER_SERIES]}), ON, monkeypatch)
    assert r["status"] == si.IDENTIFIED and r["sofascore_event_id"] == 2
    assert r["fresh_recheck"] is True and r["listing_from_cache"] is False
    assert client.calls == [MAYBE]


def test_on_far_from_the_start_the_cached_page_stands_and_costs_one_request(
        monkeypatch: pytest.MonkeyPatch) -> None:
    # 8 h before the start no fresh re-ask; the second team's page is asked
    # (not cached here) and holds the series.
    client = FakeClient({MAYBE: [OTHER_SERIES, THE_SERIES],
                         ETERNAL: [THE_SERIES]})
    r = _cs2(client, StaleCache({MAYBE: [OTHER_SERIES]}), ON, monkeypatch,
             at=KICK - timedelta(hours=8))
    assert r["status"] == si.IDENTIFIED
    assert r["identified_by_second_team"] is True
    assert r["second_team_id"] == ETERNAL and r["queried_team_id"] == MAYBE
    assert client.calls == [ETERNAL]


def test_on_the_second_teams_cached_page_is_asked_fresh_too(
        monkeypatch: pytest.MonkeyPatch) -> None:
    # Both pages cached without the series; the first's fresh page still
    # lacks it (Sofascore listed it on the opponent's page first).
    client = FakeClient({MAYBE: [OTHER_SERIES], ETERNAL: [THE_SERIES]})
    cache = StaleCache({MAYBE: [OTHER_SERIES], ETERNAL: []})
    r = _cs2(client, cache, ON, monkeypatch)
    assert r["status"] == si.IDENTIFIED and r["sofascore_event_id"] == 2
    assert r["second_fresh_recheck"] is True
    assert client.calls == [MAYBE, ETERNAL]


def test_on_nothing_anywhere_keeps_the_first_teams_refusal(
        monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient({MAYBE: [OTHER_SERIES], ETERNAL: []})
    r = _cs2(client, StaleCache({MAYBE: [OTHER_SERIES]}), ON, monkeypatch)
    assert r["status"] == si.NOT_IDENTIFIED
    assert r["reason"] == "NO_MATCH_IN_LISTING"
    assert r["second_team_reason"] == "NO_MATCH_IN_LISTING"
    assert client.calls == [MAYBE, ETERNAL]


def test_on_a_team_is_asked_fresh_once_per_run(
        monkeypatch: pytest.MonkeyPatch) -> None:
    # Two events of one team in a run: its page is re-asked once.
    monkeypatch.setattr(epochs, "IDENTITY_FRESH_RECHECK_ALL_FROM_UTC", ON)
    a = _ev("1", "Sparta Praha", "Kometa Brno")
    b = _ev("2", "Sparta Praha", "Zlin", KICK + timedelta(hours=4))
    client = FakeClient({10: []})
    recs, _ = si.identify([a, b], client, StaleCache({10: [], 20: [], 30: []}),
                          lambda s, n: {"Sparta Praha": 10, "Kometa Brno": 20,
                                        "Zlin": 30}.get(n),
                          KICK - timedelta(hours=1), "2026-10-06")
    assert [r["status"] for r in recs] == [si.NOT_IDENTIFIED] * 2
    # Sparta fresh once (first event), Kometa fresh for the first; the
    # second event is 5 h away - Zlin's cached page stands.
    assert client.calls == [10, 20]


def test_off_k5_still_fires_on_no_game_within_1h_only(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "IDENTITY_FRESH_RECHECK_ALL_FROM_UTC", None)
    game = _listed(9001, (10, "Sparta Praha"), (20, "Kometa Brno"))
    client = FakeClient({10: [game]})
    (r,), _ = si.identify([_ev("1", "Sparta Praha", "Kometa Brno")], client,
                          StaleCache({10: []}),
                          lambda s, n: {"Sparta Praha": 10,
                                        "Kometa Brno": 20}.get(n),
                          NEAR, "2026-10-06", absence=True)
    assert r["status"] == si.IDENTIFIED and r["fresh_recheck"] is True
    assert client.calls == [10]
    # ... and a hockey NO_MATCH_IN_LISTING from the cache is not re-asked.
    wrong = _listed(9002, (10, "Sparta Praha"), (99, "Plzen"))
    client = FakeClient({10: [game]})
    (r,), _ = si.identify([_ev("1", "Sparta Praha", "Kometa Brno")], client,
                          StaleCache({10: [wrong]}),
                          lambda s, n: {"Sparta Praha": 10}.get(n),
                          NEAR, "2026-10-06", absence=True)
    assert r["reason"] == "NO_MATCH_IN_LISTING" and client.calls == []


def test_the_switch_reads_the_day_and_the_build_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    at = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(epochs, "IDENTITY_FRESH_RECHECK_ALL_FROM_UTC", at)
    assert not epochs.identity_fresh_recheck_all("2026-10-23", at)
    assert not epochs.identity_fresh_recheck_all("2026-10-24",
                                                 at - timedelta(seconds=1))
    assert epochs.identity_fresh_recheck_all("2026-10-24", at)
