"""Chaos tests, part two (plan 2026-10-05 production grade, F6.1): the paths
test_chaos.py left NOT_TESTED - SAMPLES, SETTLE (and --refetch-stat-gaps,
resettle_sweep.py), OFFER through the real SuperbetClient, the SHADOW / CS2
snapshots, the daily loops (cs2_daily, shadow_daily, cs2_watchdog,
capture_closing --loop), the half-open probe during a long stage, and
backfill_event_stats for hockey / basketball / volleyball.

The same contract as test_chaos.py: a refusal is a signal to slow down (the
breaker opens, the stage stops asking), PARTIAL with the rest named, FAILED
when nothing was done, never a silent success; an unattended loop logs a
failing step and goes on, or stops loudly. No network, no sleeping: fake
transports / sessions and injected clocks.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tests.sofa import test_chaos as chaos
from tests.sofa.test_chaos import (
    DAY,
    NOW,
    ChaosTransport,
    _db,
    _main,
    _save_page,
    _summary,
    _use,
)

Router = Any
env = chaos.env  # the fixture: a scratch DB and runs dir, no real sleeping

# --- SAMPLES ----------------------------------------------------------------------

S_KICK = "2026-10-06T18:00:00Z"
S_KICK_TS = 1791309600  # 2026-10-06T18:00Z


def _s_fixture(n: int) -> dict[str, Any]:
    return {
        "sofascore_event_id": 5000 + n, "superbet_event_ids": [str(n)],
        "sport": "football", "kickoff_utc": S_KICK,
        "home_name": f"H{n}", "away_name": f"A{n}",
        "home_entity_id": 100 + n, "away_entity_id": 200 + n,
        "competition_name": "Liga", "competition_id": 202, "season_id": 1,
        "category_name": "Poland", "identity": "CONFIRMED", "round_number": 5,
        "round_name": None, "cup_round_type": None, "previous_leg_event_id": None,
        "venue_name": None, "referee": None, "ground_type": None,
        "default_period_count": 2}


def _s_offer(n: int) -> dict[str, Any]:
    return {"sofascore_event_id": 5000 + n, "status": "PRICED", "rungs": [
        {"market": "corners_total", "subject": "", "line": 9.5, "over_odds": 1.9,
         "under_odds": 1.9, "fetched_at_utc": "2026-10-06T07:00:00Z"}],
        "unmapped_markets": []}


def _s_listing(team: int) -> dict[str, Any]:
    events = []
    for i in range(12, 0, -1):  # ascending, as Sofascore pages are
        events.append({
            "id": team * 100 + i, "startTimestamp": S_KICK_TS - i * 7 * 86400,
            "status": {"type": "finished"},
            "tournament": {"id": 1, "name": "Liga",
                           "category": {"sport": {"slug": "football"}},
                           "uniqueTournament": {"id": 202}},
            "season": {"id": 1},
            "homeTeam": {"id": team, "name": f"T{team}"},
            "awayTeam": {"id": 9000 + i, "name": f"O{i}"},
            "homeScore": {"current": 1, "period1": 0, "period2": 1},
            "awayScore": {"current": 0, "period1": 0, "period2": 0}})
    return {"events": events, "hasNextPage": False}


def _s_stats() -> dict[str, Any]:
    item = {"name": "Corner kicks", "key": "cornerKicks", "home": "6", "away": "4",
            "homeValue": 6, "awayValue": 4, "statisticsType": "positive"}
    return {"statistics": [{"period": "ALL", "groups": [
        {"groupName": "Match overview", "statisticsItems": [item]}]}]}


def _s_router(path: str) -> Any:
    if path.startswith("team/"):
        return _s_listing(int(path.split("/")[1]))
    if path.endswith("/statistics"):
        return _s_stats()
    if path.endswith("/incidents"):
        return {"incidents": []}
    return None


def _s_day(env_: Path, n: int) -> Path:
    day = env_ / "runs" / "2026-10-06"
    day.mkdir(parents=True, exist_ok=True)
    (day / "02_fixtures.json").write_text(
        json.dumps([_s_fixture(i) for i in range(1, n + 1)]))
    (day / "04_offer.json").write_text(
        json.dumps([_s_offer(i) for i in range(1, n + 1)]))
    return day


S_PER_FIXTURE = 22  # two listings + ten matches' statistics per side


def _s_run(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
           transport: ChaosTransport) -> tuple[int, dict[str, Any]]:
    from scripts.sofa import run_samples

    _use(monkeypatch, transport)
    code = _main(monkeypatch, run_samples, ["--date", "2026-10-06"])
    return code, _summary(capsys)


def _s_state(day: Path) -> dict[int, str]:
    """fixture n -> READY, or the reason it was blocked."""
    return {s["sofascore_event_id"] - 5000: (
        s["gaps"][0]["reason"] if s["readiness"] == "BLOCKED" else s["readiness"])
        for s in json.loads((day / "03_samples.json").read_text())}


def test_samples_samples_a_clean_day(env: Path, monkeypatch: pytest.MonkeyPatch,
                                     capsys: pytest.CaptureFixture[str]):
    """The fake is good enough for SAMPLES to make every fixture READY - so
    the tests below test the failure, not the fake."""
    _s_day(env, 3)
    transport = ChaosTransport(_s_router)
    code, summary = _s_run(monkeypatch, capsys, transport)
    assert code == 0 and summary["metrics"]["readiness"] == {"READY": 3}
    assert summary["metrics"]["breaker_open"] is False
    assert len(transport.calls) == 3 * S_PER_FIXTURE


@pytest.mark.parametrize("then", ["403", "gone"])
def test_samples_blocks_the_rest_once_the_breaker_opens(
        env: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str], then: str):
    day = _s_day(env, 5)
    transport = ChaosTransport(_s_router, ok_calls=S_PER_FIXTURE, then=then)
    code, summary = _s_run(monkeypatch, capsys, transport)
    assert code == 1 and summary["verdict"] == "PARTIAL"
    assert summary["metrics"]["breaker_open"] is True
    assert summary["metrics"]["provider_fault_fixtures"] == 4
    state = _s_state(day)
    assert state[1] == "READY"
    assert {state[n] for n in (2, 3, 4)} == {"PROVIDER_ERROR"}
    assert state[5] == "CIRCUIT_OPEN"
    # three refused requests (a transport failure: each retried once), then quiet
    assert len(transport.calls) == S_PER_FIXTURE + 3 * (1 + (then == "gone"))


def test_samples_carried_over_on_a_refusal_is_partial_not_ok(
        env: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]):
    """The previous run's sample is kept (F41), but the day was not asked:
    the verdict must say so, never OK."""
    day = _s_day(env, 4)
    assert _s_run(monkeypatch, capsys, ChaosTransport(_s_router))[0] == 0
    (env / "sofa.db").unlink()  # a fresh cache: every request goes out again
    transport = ChaosTransport(_s_router, ok_calls=0)
    code, summary = _s_run(monkeypatch, capsys, transport)
    assert summary["metrics"]["carried_over_on_provider_fault"] == 4
    assert _s_state(day) == {n: "READY" for n in range(1, 5)}
    assert summary["metrics"]["breaker_open"] is True
    assert code == 1 and summary["verdict"] == "PARTIAL"
    assert len(transport.calls) == 3


def _tick_breaker(monkeypatch: pytest.MonkeyPatch, cooldown_s: float) -> list[float]:
    """Every breaker a client builds reads a clock that moves one second per
    look - a long stage without sleeping."""
    from bet.sofa import client as client_mod

    clock = [0.0]

    def tick() -> float:
        clock[0] += 1.0
        return clock[0]

    class Ticking(client_mod.CircuitBreaker):
        def __init__(self, threshold: int, **kw: Any) -> None:
            super().__init__(threshold, cooldown_s=cooldown_s,
                             max_cooldown_s=300, clock=tick)

    monkeypatch.setattr(client_mod, "CircuitBreaker", Ticking)
    return clock


def test_samples_half_open_probe_refused_during_a_long_stage(
        env: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]):
    """The breaker opens mid-SAMPLES; the stage goes on (each fixture meets the
    open breaker, nobody is asked) until the cooldown passes. Then exactly one
    probe goes out; refused, the breaker reopens with the cooldown doubled -
    never a burst into a 403."""
    _tick_breaker(monkeypatch, 10)
    day = _s_day(env, 40)
    transport = ChaosTransport(_s_router, ok_calls=S_PER_FIXTURE)
    code, summary = _s_run(monkeypatch, capsys, transport)
    assert code == 1 and summary["metrics"]["breaker_open"] is True
    rows = [json.loads(x) for x in
            (env / "runs" / "run.log.jsonl").read_text().splitlines()]
    refused = [i for i, r in enumerate(rows) if r["status"] == 403]
    assert len(refused) == len(transport.calls) - S_PER_FIXTURE
    # 3 to open it, then one lone probe per (doubling) cooldown
    assert 4 <= len(refused) <= 3 + 3
    assert all(b - a == 1 for a, b in zip(refused, refused[1:], strict=False))
    state = _s_state(day)
    assert state[1] == "READY"
    assert sum(v == "CIRCUIT_OPEN" for v in state.values()) >= 30


def test_samples_half_open_probe_answered_resumes_the_stage(
        env: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]):
    _tick_breaker(monkeypatch, 10)
    day = _s_day(env, 20)

    class Recovers(ChaosTransport):
        def get(self, url: str, timeout: float = 10.0) -> Any:
            if len(self.calls) == S_PER_FIXTURE + 3:
                self.ok_calls = None  # Sofascore answers the probe
            return super().get(url, timeout)

    transport = Recovers(_s_router, ok_calls=S_PER_FIXTURE)
    code, summary = _s_run(monkeypatch, capsys, transport)
    state = _s_state(day)
    assert code == 1 and summary["verdict"] == "PARTIAL"  # 2-4 were refused
    assert state[1] == "READY" and state[20] == "READY"
    opened = [n for n, v in state.items() if v != "READY"]
    assert opened and max(opened) < 20
    assert summary["metrics"]["breaker_open"] is False  # it closed again


# --- SETTLE -----------------------------------------------------------------------

SETTLE_DATE = "2026-10-04"


def _settle_row(eid: int, market: str = "goals_total") -> dict[str, Any]:
    return {
        "sofascore_event_id": eid, "sport": "football", "market": market,
        "subject": "", "line": 2.5, "direction": "OVER", "sample_size": 10,
        "sample_mean": 2.6, "sample_sd": 1.2, "p_central": 0.55, "p_bar": 0.55,
        "market_p": 0.5, "offered_odds": 1.9, "verdict": "VALUE"}


def _settle_event(eid: int) -> dict[str, Any]:
    return {"event": {
        "id": eid, "startTimestamp": 1791100800, "status": {"type": "finished",
                                                            "code": 100},
        "homeTeam": {"id": 1, "name": f"Home {eid}"},
        "awayTeam": {"id": 2, "name": f"Away {eid}"},
        "homeScore": {"current": 2, "period1": 1, "period2": 1},
        "awayScore": {"current": 1, "period1": 0, "period2": 1},
        "tournament": {"uniqueTournament": {"id": 17}}}}


def _settle_router(gaps: frozenset[int] = frozenset()) -> Any:
    def router(path: str) -> Any:
        parts = path.split("/")
        eid = int(parts[1])
        if len(parts) == 2:
            return _settle_event(eid)
        if parts[2] == "statistics":
            return None if eid in gaps else _s_stats()
        return {"incidents": []}
    return router


def _settle_day(env_: Path, n: int, market: str = "goals_total") -> Path:
    day = env_ / "runs" / SETTLE_DATE
    day.mkdir(parents=True, exist_ok=True)
    (day / "05_sheet.json").write_text(json.dumps(
        [_settle_row(i, market) for i in range(1, n + 1)]))
    (day / "02_fixtures.json").write_text(json.dumps([
        {"sofascore_event_id": i, "sport": "football", "home_name": f"Home {i}",
         "away_name": f"Away {i}"} for i in range(1, n + 1)]))
    return day


def _settle(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
            transport: ChaosTransport, *flags: str) -> tuple[int, dict[str, Any]]:
    from scripts.sofa import run_settle

    _use(monkeypatch, transport)
    code = _main(monkeypatch, run_settle, ["--date", SETTLE_DATE, *flags])
    return code, _summary(capsys)


def _settled_ids(day: Path) -> list[int]:
    return sorted(r["sofascore_event_id"] for r in
                  json.loads((day / "07_settled.json").read_text()))


def test_settle_grades_a_clean_day(env: Path, monkeypatch: pytest.MonkeyPatch,
                                   capsys: pytest.CaptureFixture[str]):
    day = _settle_day(env, 3)
    transport = ChaosTransport(_settle_router())
    code, summary = _settle(monkeypatch, capsys, transport)
    assert code == 0 and summary["metrics"]["rows_settled"] == 3
    assert _settled_ids(day) == [1, 2, 3]
    assert len(transport.calls) == 3 * 3  # event, statistics, incidents


@pytest.mark.parametrize("then", ["403", "gone"])
def test_settle_stops_at_the_open_breaker_and_resumes(
        env: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str], then: str):
    day = _settle_day(env, 6)
    transport = ChaosTransport(_settle_router(), ok_calls=2 * 3, then=then)
    code, summary = _settle(monkeypatch, capsys, transport)
    assert code == 1 and summary["verdict"] == "PARTIAL"
    assert summary["metrics"]["breaker_open"] is True
    assert _settled_ids(day) == [1, 2]
    skips = json.loads((day / "07_settle_skips.json").read_text())
    assert skips["breaker_open"] is True
    assert skips["skipped"] == {"PROVIDER_ERROR": 4}  # 3 refused + 1 never asked
    # three refused requests (a transport failure: each retried once), then quiet
    assert len(transport.calls) == 6 + 3 * (1 + (then == "gone"))
    # the bridge is back: only what was not graded is asked; nothing twice
    again = ChaosTransport(_settle_router())
    code, summary = _settle(monkeypatch, capsys, again)
    assert code == 0
    assert _settled_ids(day) == [1, 2, 3, 4, 5, 6]
    assert {int(p.split("/")[1]) for p in again.calls if p.count("/") == 1} == {
        1, 2, 3, 4, 5, 6}  # the event is re-read (cached stats are not)
    assert not any(p.endswith("/statistics") and int(p.split("/")[1]) in (1, 2)
                   for p in again.calls)


def test_settle_refused_on_its_last_events_still_says_the_breaker_opened(
        env: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]):
    """The three refusals that open the breaker are ProviderErrors, not
    CircuitOpenErrors: when they are the day's last events no later event
    meets the open breaker, and breaker_open read False - so
    resettle_sweep.py went on to the next day and into the next 403s."""
    day = _settle_day(env, 5)
    transport = ChaosTransport(_settle_router(), ok_calls=2 * 3)
    code, summary = _settle(monkeypatch, capsys, transport)
    assert code == 1 and summary["metrics"]["breaker_open"] is True
    assert json.loads((day / "07_settle_skips.json").read_text())["breaker_open"]


def test_settle_refetch_stat_gaps_refused_keeps_the_gaps_for_the_next_morning(
        env: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]):
    from scripts.sofa import run_settle

    day = _settle_day(env, 4, "corners_total")
    code, _ = _settle(monkeypatch, capsys,
                      ChaosTransport(_settle_router(frozenset({3, 4}))))
    assert code == 1 and _settled_ids(day) == [1, 2]
    skips_path = day / "07_settle_skips.json"
    assert run_settle.stat_gap_events(skips_path) == {3, 4}
    # the D-5 morning: Sofascore refuses the refetch from its first request
    transport = ChaosTransport(_settle_router(), ok_calls=0)
    code, summary = _settle(monkeypatch, capsys, transport, "--refetch-stat-gaps")
    assert code == 2 and summary["verdict"] == "FAILED"  # nothing graded
    assert summary["metrics"]["breaker_open"] is True
    assert len(transport.calls) == 3
    assert _settled_ids(day) == [1, 2]  # nothing on disk lost
    assert run_settle.stat_gap_events(skips_path) == {3, 4}  # asked again tomorrow
    # the statistics arrived: the next refetch grades them
    code, _ = _settle(monkeypatch, capsys, ChaosTransport(_settle_router()),
                      "--refetch-stat-gaps")
    assert code == 0 and _settled_ids(day) == [1, 2, 3, 4]
    assert run_settle.stat_gap_events(skips_path) == frozenset()


# --- resettle_sweep.py ------------------------------------------------------------


def _sweep(env_: Path, monkeypatch: pytest.MonkeyPatch,
           capsys: pytest.CaptureFixture[str], days: list[str],
           settle: dict[str, tuple[int, dict[str, Any]]],
           health: dict[str, Any] | None = None
           ) -> tuple[int, dict[str, Any], list[list[str]]]:
    from scripts.sofa import resettle_sweep as rs

    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> tuple[int, dict[str, Any]]:
        calls.append(cmd)
        if cmd[1].endswith("regrade_settled.py"):
            return 0, {}
        return settle[cmd[cmd.index("--date") + 1]]

    monkeypatch.setattr(rs, "plan", lambda *a: {d: 1 for d in days})
    monkeypatch.setattr(rs, "run", fake_run)
    monkeypatch.setattr(rs, "bridge_health", lambda: health)
    monkeypatch.setattr(sys, "argv", ["resettle_sweep", "--from", days[0],
                                      "--to", days[-1]])
    code = rs.main()
    return code, _summary(capsys), calls


def test_resettle_sweep_stops_at_the_day_whose_breaker_opened(
        env: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]):
    days = ["2026-09-28", "2026-09-29", "2026-09-30"]
    settle = {"2026-09-28": (1, {"metrics": {"breaker_open": False}}),
              "2026-09-29": (1, {"metrics": {"breaker_open": True}}),
              "2026-09-30": (0, {"metrics": {"breaker_open": False}})}
    code, summary, calls = _sweep(env, monkeypatch, capsys, days, settle,
                                  {"last_pull_age_s": 2})
    settled = [c[c.index("--date") + 1] for c in calls if "--date" in c]
    assert settled == days[:2]  # never on into the next refusals
    assert calls[-1][1].endswith("regrade_settled.py")  # local, still run
    assert code == 1 and summary["verdict"] == "PARTIAL"
    assert summary["metrics"]["breaker_open"] is True


def test_resettle_sweep_without_a_bridge_settles_nothing_and_says_so(
        env: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]):
    for health in (None, {"last_pull_age_s": None}, {"last_pull_age_s": 600}):
        code, summary, calls = _sweep(env, monkeypatch, capsys, ["2026-09-28"],
                                      {}, health)
        assert calls == []
        assert code == 1 and summary["verdict"] == "PARTIAL"
        assert summary["metrics"]["bridge"] is False


def test_resettle_sweep_a_crashed_day_is_named_and_the_rest_still_runs(
        env: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]):
    days = ["2026-09-28", "2026-09-29"]
    settle = {"2026-09-28": (2, {}),  # a traceback: no SOFA_SUMMARY at all
              "2026-09-29": (1, {"metrics": {"breaker_open": False}})}
    code, summary, calls = _sweep(env, monkeypatch, capsys, days, settle,
                                  {"last_pull_age_s": 2})
    assert summary["metrics"]["settle_exit"] == {"2026-09-28": 2, "2026-09-29": 1}
    assert code == 1 and summary["verdict"] == "PARTIAL"
    # every planned day crashed: FAILED
    settle["2026-09-29"] = (2, {})
    code, summary, _ = _sweep(env, monkeypatch, capsys, days, settle,
                              {"last_pull_age_s": 2})
    assert code == 2 and summary["verdict"] == "FAILED"


# --- Superbet: the client, OFFER ---------------------------------------------------


class SbResp:
    def __init__(self, status: int, payload: Any = None) -> None:
        self.status_code, self._payload = status, payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            from curl_cffi.requests.exceptions import HTTPError

            raise HTTPError(f"HTTP Error {self.status_code}", response=self)  # type: ignore[arg-type]

    def json(self) -> Any:
        return self._payload


class SuperbetChaos:
    """A curl_cffi Session for SuperbetClient: answers from `router(url)` (a
    payload, None for a 404) until `ok_calls` requests have been answered,
    then `then`: "403", "429", "500" or "timeout"."""

    def __init__(self, router: Router, ok_calls: int | None = None,
                 then: str = "403") -> None:
        self.router, self.ok_calls, self.then = router, ok_calls, then
        self.headers: dict[str, str] = {}
        self.calls: list[str] = []
        self.answered = 0

    def get(self, url: str, params: Any = None, timeout: float = 0.0) -> SbResp:
        self.calls.append(url)
        if self.ok_calls is not None and self.answered >= self.ok_calls:
            if self.then == "timeout":
                from curl_cffi.requests.exceptions import Timeout

                raise Timeout("Operation timed out after 25000 ms")
            return SbResp(int(self.then))
        self.answered += 1
        payload = self.router(url)
        return SbResp(404) if payload is None else SbResp(200, payload)


def _use_superbet(monkeypatch: pytest.MonkeyPatch, session: SuperbetChaos) -> None:
    from bet.sofa import superbet

    monkeypatch.setattr(superbet.requests, "Session", lambda **kw: session)


def _sb_event(url: str) -> Any:
    return {"data": [{"odds": [
        {"marketName": "Liczba goli", "name": side, "specialBetValue": "2.5",
         "price": price} for side, price in (("poniżej 2.5", 1.8),
                                             ("powyżej 2.5", 2.0))]}]}


def test_superbet_client_breaker_opens_on_refusals_not_on_a_404(
        env: Path, monkeypatch: pytest.MonkeyPatch):
    from bet.sofa.errors import CircuitOpenError
    from bet.sofa.superbet import SuperbetClient

    session = SuperbetChaos(lambda url: None)  # every event removed: 404
    _use_superbet(monkeypatch, session)
    client = SuperbetClient()
    for i in range(5):
        with pytest.raises(Exception, match="404"):
            client.event_odds(i)
    assert not client.breaker_tripped  # a 404 is an answer
    for then in ("403", "429", "500", "timeout"):
        session = SuperbetChaos(_sb_event, ok_calls=0, then=then)
        _use_superbet(monkeypatch, session)
        client = SuperbetClient()
        for i in range(3):
            with pytest.raises(Exception):  # noqa: B017 - whatever curl raised
                client.event_odds(i)
        with pytest.raises(CircuitOpenError):
            client.event_odds(99)
        assert len(session.calls) == 3, then  # one request each, no retry
        assert client.breaker_tripped
    rows = [json.loads(x) for x in
            (env / "runs" / "run.log.jsonl").read_text().splitlines()]
    assert rows[-1]["status"] is None and rows[-1]["breaker_state"] == "OPEN"


def _offer_day(env_: Path, n: int) -> Path:
    day = env_ / "runs" / "2026-10-06"
    day.mkdir(parents=True, exist_ok=True)
    (day / "02_fixtures.json").write_text(
        json.dumps([_s_fixture(i) for i in range(1, n + 1)]))
    return day


def _offer(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
           session: SuperbetChaos, *flags: str) -> tuple[int, dict[str, Any]]:
    from scripts.sofa import run_offer

    _use_superbet(monkeypatch, session)
    code = _main(monkeypatch, run_offer, ["--date", "2026-10-06", *flags])
    return code, _summary(capsys)


def _offer_ids(day: Path) -> dict[int, str]:
    return {o["sofascore_event_id"] - 5000: o["rungs"][0]["fetched_at_utc"]
            for o in json.loads((day / "04_offer.json").read_text())}


def test_offer_prices_a_clean_board(env: Path, monkeypatch: pytest.MonkeyPatch,
                                    capsys: pytest.CaptureFixture[str]):
    day = _offer_day(env, 4)
    code, summary = _offer(monkeypatch, capsys, SuperbetChaos(_sb_event))
    assert code == 0 and summary["metrics"]["breaker_open"] is False
    assert sorted(_offer_ids(day)) == [1, 2, 3, 4]


@pytest.mark.parametrize("then", ["403", "429", "timeout"])
def test_offer_stops_asking_superbet_once_its_breaker_opens(
        env: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str], then: str):
    """Before F6.1 OFFER caught each listing's error and asked the next: a
    Superbet refusing (or timing out at 25 s a request) was asked once per
    fixture on the board."""
    day = _offer_day(env, 10)
    session = SuperbetChaos(_sb_event, ok_calls=2, then=then)
    code, summary = _offer(monkeypatch, capsys, session)
    assert len(session.calls) == 2 + 3  # three refusals, then nobody asked
    assert code == 1 and summary["verdict"] == "PARTIAL"
    m = summary["metrics"]
    assert m["breaker_open"] is True and m["fetch_errors"] == 3
    assert m["not_reached_breaker_open"] == 5
    assert sorted(_offer_ids(day)) == [1, 2]


def test_offer_keeps_the_previous_price_of_a_fixture_it_could_not_ask(
        env: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]):
    """The second (full) OFFER of a day, refused half way: the fixtures it
    never asked keep the first OFFER's entry, at that entry's own age."""
    day = _offer_day(env, 8)
    assert _offer(monkeypatch, capsys, SuperbetChaos(_sb_event))[0] == 0
    first = _offer_ids(day)
    session = SuperbetChaos(_sb_event, ok_calls=2)
    code, summary = _offer(monkeypatch, capsys, session)
    assert code == 1 and summary["metrics"]["carried_forward_not_reached"] == 3
    now_ids = _offer_ids(day)
    # 1-2 re-priced, 3-5 refused (a failed listing: no entry, as before),
    # 6-8 never asked: the first OFFER's entries, unchanged
    assert sorted(now_ids) == [1, 2, 6, 7, 8]
    assert all(now_ids[n] == first[n] for n in (6, 7, 8))


def test_offer_refused_from_the_first_request_fails_and_keeps_the_file(
        env: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]):
    day = _offer_day(env, 6)
    assert _offer(monkeypatch, capsys, SuperbetChaos(_sb_event))[0] == 0
    session = SuperbetChaos(_sb_event, ok_calls=0)
    code, summary = _offer(monkeypatch, capsys, session)
    assert code == 2 and summary["verdict"] == "FAILED"
    assert len(session.calls) == 3
    assert sorted(_offer_ids(day)) == [4, 5, 6]  # never asked: kept
    # the filtered refresh of a rebuild keeps every entry it could not price
    session = SuperbetChaos(_sb_event, ok_calls=0)
    code, _ = _offer(monkeypatch, capsys, session, "--min-minutes-to-kickoff", "0")
    assert code == 2 and sorted(_offer_ids(day)) == [4, 5, 6]


def test_samples_superbet_fallback_asks_a_refusing_superbet_three_times(
        env: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]):
    """No offer artifact: SAMPLES asks Superbet which metrics are priced, per
    fixture. Refused, its breaker stops that, and every fixture is a named
    provider fault, never NO_PRICE."""
    from scripts.sofa import run_samples

    day = _s_day(env, 6)
    (day / "04_offer.json").unlink()
    monkeypatch.setattr(run_samples._THREAD_LOCAL, "superbet", None, raising=False)
    session = SuperbetChaos(_sb_event, ok_calls=0)
    _use_superbet(monkeypatch, session)
    transport = ChaosTransport(_s_router)
    code, summary = _s_run(monkeypatch, capsys, transport)
    assert len(session.calls) == 3
    assert transport.calls == []  # nothing priced is known: nothing sampled
    assert set(_s_state(day).values()) == {"PROVIDER_ERROR"}
    assert code == 2 and summary["verdict"] == "FAILED"


# --- SHADOW / CS2 snapshots ---------------------------------------------------------

SNAP_DATE = "2026-09-28"
SNAP_AT = datetime(2026, 9, 28, 14, tzinfo=UTC)


def _snap_router(sport_id: int, n: int, odds: list[dict[str, Any]]) -> Router:
    def router(url: str) -> Any:
        if "/events/by-date" in url:
            return {"data": [
                {"sportId": sport_id, "eventId": i, "matchName": f"H{i}·A{i}",
                 "utcDate": "2026-09-28T16:00:00Z", "tournamentId": 7}
                for i in range(1, n + 1)]}
        if url.endswith("/struct"):
            return {"data": {"tournaments": []}}
        return {"data": [{"odds": odds}]}
    return router


def _hockey_odds() -> list[dict[str, Any]]:
    return [{"marketId": 623, "marketName": "Liczba goli", "name": name,
             "info": "", "price": 1.9, "specifiers": {"total": "5.5"},
             "code": code, "status": "active", "tags": "v2"}
            for name, code in (("poniżej 5.5", "-"), ("powyżej 5.5", "+"))]


def _cs2_odds() -> list[dict[str, Any]]:
    return [{"marketName": "Liczba map", "name": name, "info": name,
             "price": 1.9, "specifiers": {"total": "2.5"}, "status": "active"}
            for name in ("poniżej 2.5", "powyżej 2.5")]


@pytest.mark.parametrize("ok_events, verdict", [(2, "PARTIAL"), (0, "FAILED")])
def test_shadow_snapshot_stops_at_superbets_breaker(
        env: Path, monkeypatch: pytest.MonkeyPatch, ok_events: int, verdict: str):
    """Before F6.1 each refused event was counted and the next one asked; a
    snapshot whose every event was refused said PARTIAL with nothing on disk."""
    from bet.sofa.superbet import SuperbetClient
    from scripts.sofa import run_shadow

    session = SuperbetChaos(_snap_router(3, 10, _hockey_odds()),
                            ok_calls=2 + ok_events)  # board + struct + events
    _use_superbet(monkeypatch, session)
    result = run_shadow.snapshot(SNAP_DATE, SuperbetClient(), str(env / "runs"),
                                 at=SNAP_AT)
    assert len(session.calls) == 2 + ok_events + 3  # then nobody asked
    assert result["verdict"] == verdict and result["breaker_open"] is True
    assert result["metrics"]["hockey"]["fetch_failed"] == 3
    assert result["metrics"]["hockey"]["events_with_lines"] == ok_events
    assert result["board_rows_not_reached"] == 10 - ok_events - 3


@pytest.mark.parametrize("ok_events, verdict", [(2, "PARTIAL"), (0, "FAILED")])
def test_cs2_snapshot_stops_at_superbets_breaker(
        env: Path, monkeypatch: pytest.MonkeyPatch, ok_events: int, verdict: str):
    from bet.sofa.superbet import SuperbetClient
    from scripts.sofa import run_cs2

    monkeypatch.setattr(run_cs2, "now", lambda: SNAP_AT)
    session = SuperbetChaos(_snap_router(55, 10, _cs2_odds()),
                            ok_calls=2 + ok_events)
    _use_superbet(monkeypatch, session)
    result = run_cs2.snapshot(SNAP_DATE, SuperbetClient(), str(env / "runs"))
    assert len(session.calls) == 2 + ok_events + 3
    assert result["verdict"] == verdict and result["breaker_open"] is True
    assert result["metrics"]["fetch_failed"] == 3
    assert result["metrics"]["events_with_lines"] == ok_events


def test_shadow_snapshot_clean_board_is_ok(env: Path, monkeypatch: pytest.MonkeyPatch):
    from bet.sofa.superbet import SuperbetClient
    from scripts.sofa import run_shadow

    session = SuperbetChaos(_snap_router(3, 4, _hockey_odds()))
    _use_superbet(monkeypatch, session)
    result = run_shadow.snapshot(SNAP_DATE, SuperbetClient(), str(env / "runs"),
                                 at=SNAP_AT)
    assert result["verdict"] == "OK" and result["breaker_open"] is False
    assert result["metrics"]["hockey"]["events_with_lines"] == 4


# --- the daily loops (cs2_daily / shadow_daily) ---------------------------------------


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.t = start

    def now(self) -> datetime:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += timedelta(seconds=seconds)


def _loop(runner: Any) -> int:
    from scripts.sofa import cs2_daily

    clock = _Clock(datetime(2026, 9, 29, 22, 0, tzinfo=UTC))
    code: int = cs2_daily.loop(
        ["snap"], [["scripts/sofa/settle.py"], ["scripts/sofa/record_results.py"]],
        ["audit"], 30, cs2_daily._at("2026-09-29", "23:30"),
        cs2_daily._at("2026-09-29", "05:00", day_offset=1),
        clock=clock.now, sleep=clock.sleep, runner=runner)
    return code


def test_daily_loop_a_step_that_raises_is_failed_and_the_loop_goes_on(
        capsys: pytest.CaptureFixture[str]):
    calls: list[str] = []

    def runner(cmd: list[str]) -> int:
        calls.append(cmd[0])
        if cmd == ["snap"] and calls.count("snap") == 1:
            raise OSError("Resource temporarily unavailable (fork)")
        if cmd == ["audit"]:
            raise RuntimeError("audit crashed")
        return 0

    assert _loop(runner) == 2  # the worst step, named
    assert calls.count("snap") == 3  # 22:00, 22:30, 23:00 - it went on
    assert "scripts/sofa/settle.py" in calls and calls[-1] == "audit"
    out = capsys.readouterr().out
    assert "STEP_FAILED snap: OSError" in out and "STEP_FAILED audit" in out


def test_daily_loop_a_step_killed_by_a_signal_is_failed_and_retried(
        capsys: pytest.CaptureFixture[str]):
    """subprocess.call returns -9 for a SIGKILLed step (OOM); max() read it as
    better than OK - a silent success, never retried."""
    calls: list[str] = []

    def runner(cmd: list[str]) -> int:
        calls.append(cmd[0])
        if cmd[0].endswith("settle.py") and calls.count(cmd[0]) == 1:
            return -9
        return 0

    assert _loop(runner) == 0  # the retry settled it
    assert calls.count("scripts/sofa/settle.py") == 2
    assert calls.count("scripts/sofa/record_results.py") == 2  # re-run after it
    assert "STEP_KILLED by signal 9" in capsys.readouterr().out

    def always_killed(cmd: list[str]) -> int:
        return -15 if cmd[0].endswith("settle.py") else 0

    assert _loop(always_killed) == 2


def test_daily_step_that_cannot_start_is_failed(monkeypatch: pytest.MonkeyPatch,
                                                capsys: pytest.CaptureFixture[str]):
    import subprocess

    from scripts.sofa import cs2_daily

    def no_fork(*a: Any, **kw: Any) -> int:
        raise OSError(35, "Resource temporarily unavailable")

    monkeypatch.setattr(subprocess, "call", no_fork)
    assert cs2_daily.step(["scripts/sofa/run_pipeline.py"]) == 2
    monkeypatch.setattr(subprocess, "call", lambda *a, **kw: -9)
    assert cs2_daily.step(["scripts/sofa/run_pipeline.py"]) == 2
    out = capsys.readouterr().out
    assert "STEP_NOT_STARTED" in out and "STEP_KILLED" in out


def _daily_main(module: Any, monkeypatch: pytest.MonkeyPatch, env_: Path,
                loop: Any) -> int:
    monkeypatch.setenv("SOFA_RUNS_DIR", str(env_ / "runs"))
    monkeypatch.setattr(module, "REPO", env_)
    monkeypatch.setattr(sys, "argv", [module.__name__, "--date", "2026-09-29"])
    if module.__name__.endswith("shadow_daily"):
        monkeypatch.setattr(module, "loop", loop)
    else:
        monkeypatch.setattr(module, "run", loop)
    code: int = module.main()
    return code


@pytest.mark.parametrize("name", ["cs2_daily", "shadow_daily"])
def test_daily_main_a_stale_pid_file_does_not_block_and_done_is_written(
        env: Path, monkeypatch: pytest.MonkeyPatch, name: str):
    import importlib
    import os

    module = importlib.import_module(f"scripts.sofa.{name}")
    sub = "cs2" if name == "cs2_daily" else "shadow"
    state = env / "runs" / sub
    state.mkdir(parents=True)
    pid = state / "daily_2026-09-29.pid"
    pid.write_text(str(os.getppid()))  # alive, but not a loop: a reused pid
    assert _daily_main(module, monkeypatch, env, lambda *a, **kw: 1) == 1
    assert json.loads((state / "daily_2026-09-29.done").read_text())["exit"] == 1
    assert not pid.exists()


@pytest.mark.parametrize("name", ["cs2_daily", "shadow_daily"])
def test_daily_main_a_loop_that_dies_is_loud_and_leaves_no_done(
        env: Path, monkeypatch: pytest.MonkeyPatch, name: str):
    """No .done, no pid file: the watchdog (cs2) sees a day that did not
    finish and is not running, and relaunches it."""
    import importlib

    module = importlib.import_module(f"scripts.sofa.{name}")
    sub = "cs2" if name == "cs2_daily" else "shadow"

    def dies(*a: Any, **kw: Any) -> int:
        raise MemoryError("loop died")

    with pytest.raises(MemoryError):
        _daily_main(module, monkeypatch, env, dies)
    state = env / "runs" / sub
    assert not (state / "daily_2026-09-29.done").exists()
    assert not (state / "daily_2026-09-29.pid").exists()


def test_watchdog_relaunches_a_day_whose_pid_file_is_stale(
        env: Path, monkeypatch: pytest.MonkeyPatch):
    """os.kill(pid, 0) alone read a reused pid as a live cs2_daily and the
    day was never relaunched."""
    import os

    from scripts.sofa import cs2_daily, cs2_watchdog

    monkeypatch.setattr(cs2_daily, "REPO", env)
    cs2_daily.state_dir().mkdir(parents=True)
    cs2_daily.pid_file("2026-09-29").write_text(str(os.getppid()))
    assert cs2_watchdog.pid_alive("2026-09-29") is False
    seen = cs2_watchdog.look(["2026-09-29"])
    actions = cs2_watchdog.decide(seen, datetime(2026, 9, 29, 12, tzinfo=UTC),
                                  {}, None)
    assert ("RELAUNCH", "2026-09-29") in actions
    cs2_daily.pid_file("2026-09-29").write_text("999999999")  # no such process
    assert cs2_watchdog.pid_alive("2026-09-29") is False


# --- capture_closing --loop -----------------------------------------------------------

CL_KO = datetime(2026, 10, 1, 18, 0, tzinfo=UTC)


def _closing_day(env_: Path, n: int) -> Path:
    day = env_ / "runs" / "2026-10-01"
    day.mkdir(parents=True, exist_ok=True)
    fixtures = [_s_fixture(i) | {"kickoff_utc": CL_KO.isoformat()}
                for i in range(1, n + 1)]
    (day / "02_fixtures.json").write_text(json.dumps(fixtures))
    legs = [{"sofascore_event_id": 5000 + i, "kickoff_utc": CL_KO.isoformat(),
             "market": "goals_total", "subject": "", "line": 2.5,
             "direction": "OVER", "offered_odds": 1.9} for i in range(1, n + 1)]
    (day / "08_confidence.json").write_text(
        json.dumps({"singles": legs, "pdf_max_singles": None}))
    return day


def test_capture_closing_a_refusing_superbet_is_an_error_not_a_pulled_market(
        env: Path, monkeypatch: pytest.MonkeyPatch):
    from bet.sofa.offer import OfferFetcher
    from bet.sofa.superbet import SuperbetClient
    from scripts.sofa import capture_closing as cc

    day = _closing_day(env, 6)
    session = SuperbetChaos(_sb_event, ok_calls=1)
    _use_superbet(monkeypatch, session)
    fetcher = OfferFetcher(SuperbetClient())
    assert cc.run_once(day, fetcher, CL_KO - timedelta(minutes=20)) == 6
    assert len(session.calls) == 1 + 3  # then the breaker: nobody asked
    recs = {r["sofascore_event_id"] - 5000: r for r in
            (json.loads(x) for x in (day / "closing.jsonl").read_text().splitlines())}
    assert recs[1]["odds_close"] == 2.0
    assert all(recs[n]["missing"] and "error" in recs[n] for n in range(2, 7))
    assert all("BREAKER_OPEN" in recs[n]["error"] for n in (5, 6))
    # the next pass, after the cooldown, asks again (one probe)
    fetcher.client.breaker._opened_at = -1e9
    session.ok_calls = None
    assert cc.run_once(day, fetcher, CL_KO - timedelta(minutes=10)) == 6
    assert len(session.calls) == 4 + 6


def test_capture_closing_loop_logs_failed_passes_and_exits_non_zero(
        env: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]):
    from scripts.sofa import capture_closing as cc

    day = _closing_day(env, 1)
    clock = _Clock(CL_KO - timedelta(minutes=40))
    passes = [0]

    def once(day_dir: Path, fetcher: Any) -> int:
        passes[0] += 1
        if passes[0] == 2:
            raise TimeoutError("superbet read timeout")
        return 1

    reads = [0]
    real = cc.printed_legs

    def legs(day_dir: Path) -> Any:
        reads[0] += 1
        if reads[0] == 3:
            raise ValueError("11_coupon.json: Expecting value")  # mid-rebuild
        return real(day_dir)

    monkeypatch.setattr(cc, "printed_legs", legs)
    code = cc.loop(day, None, clock=clock.now, sleep=clock.sleep, once=once)
    assert code == 1  # the loop ran to the end, and says a pass failed
    out = capsys.readouterr().out
    assert out.count("pass_failed") == 2
    assert passes[0] == 9  # every 5 min, T-40 .. T-0 (the last leg inside 3 min)

    def always(day_dir: Path, fetcher: Any) -> int:
        raise TimeoutError("down")

    clock = _Clock(CL_KO - timedelta(hours=3))
    assert cc.loop(day, None, clock=clock.now, sleep=clock.sleep,
                   once=always) == 2  # stops loudly after 12 in a row
    assert "loop_stopped" in capsys.readouterr().out
    clock = _Clock(CL_KO - timedelta(minutes=40))
    monkeypatch.setattr(cc, "printed_legs", real)
    assert cc.loop(day, None, clock=clock.now, sleep=clock.sleep,
                   once=lambda d, f: 1) == 0


# --- backfill_event_stats, the measured sports ------------------------------------


def _sport_event(eid: int, slug: str, days_ago: int) -> dict[str, Any]:
    return {"id": eid, "startTimestamp": NOW - days_ago * DAY,
            "status": {"type": "finished"},
            "tournament": {"name": "Liga", "category": {"sport": {"slug": slug}},
                           "uniqueTournament": {"id": 77, "name": "Liga"}},
            "homeTeam": {"id": 1, "name": "T1"}, "awayTeam": {"id": 2, "name": "T2"},
            "homeScore": {"current": 3}, "awayScore": {"current": 2}}


def _sport_stats_router(path: str) -> Any:
    if path.endswith("/statistics"):
        return {"statistics": [{"period": "ALL", "groups": []}]}
    if path.endswith("/lineups"):
        return {"home": {"players": []}, "away": {"players": []}}
    return None


@pytest.mark.parametrize("sport, slug", [("hockey", "ice-hockey"),
                                         ("basketball", "basketball"),
                                         ("volleyball", "volleyball")])
@pytest.mark.parametrize("then", ["403", "gone"])
def test_backfill_event_stats_measured_sport_resumes_route_by_route(
        env: Path, monkeypatch: pytest.MonkeyPatch, sport: str, slug: str,
        then: str):
    from scripts.sofa import backfill_event_stats

    conn = _db(env)
    # newest first: 9001 (4 days ago) .. 9005 (8 days ago)
    _save_page(conn, 1, 0, [_sport_event(9000 + i, slug, 3 + i) for i in range(1, 6)],
               has_next=False)
    argv = ["--sport", sport, "--days", "60", "--with-lineups"]
    # 9001 stats + lineups, 9002 stats; then refused: 9002 lineups, 9003 both
    first = ChaosTransport(_sport_stats_router, ok_calls=3, then=then)
    _use(monkeypatch, first)
    assert _main(monkeypatch, backfill_event_stats, argv) == 2  # FAILED: breaker
    assert len(first.calls) == 3 + 3 * (1 + (then == "gone"))
    second = ChaosTransport(_sport_stats_router)
    _use(monkeypatch, second)
    assert _main(monkeypatch, backfill_event_stats, argv) == 0
    assert "event/9001/statistics" not in second.calls
    assert "event/9001/lineups" not in second.calls
    assert "event/9002/statistics" not in second.calls  # kept though its
    assert "event/9002/lineups" in second.calls  # lineups were refused
    assert {"event/9005/statistics", "event/9005/lineups"} <= set(second.calls)
    third = ChaosTransport(_sport_stats_router)
    _use(monkeypatch, third)
    assert _main(monkeypatch, backfill_event_stats, argv) == 0
    assert third.calls == []
