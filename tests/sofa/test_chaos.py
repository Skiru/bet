"""Chaos tests, on purpose (plan 2026-10-05 production grade, F6.1).

Every test drives the REAL SofascoreClient - its token bucket, breaker and
retry - through a fake transport (no network, no bridge) into the stage or
backfill that owns the request, and checks the contract in CLAUDE.md:

* a refusal (403) is a signal to slow down: never retried by the client, the
  breaker opens after SOFA_BREAKER_THRESHOLD, and once it is open the stage
  stops asking - the rest is UNVERIFIED / skipped / NOT_IDENTIFIED and the
  verdict says PARTIAL (or FAILED when nothing was done);
* the breaker's cycle: open -> (cooldown) half-open, one probe -> a failed
  probe reopens with a doubled cooldown, a good one closes it;
* the bridge disappearing mid-day (a transport error after N good requests)
  is retried once per request (a transport failure says nothing about the
  request), then counts as a failure like any other;
* every backfill resumes: interrupted mid-run, the next run asks only for
  what the first did not finish.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import bridge_transport
from bet.sofa.client import CircuitBreaker, SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.errors import CircuitOpenError, ProviderError, TransportError

API = "https://api.sofascore.com/api/v1/"


class Resp:
    def __init__(self, status: int, payload: Any = None) -> None:
        self.status_code = status
        self._payload = payload
        self.headers: dict[str, str] = {}

    @property
    def text(self) -> str:
        return json.dumps(self._payload)

    def json(self) -> Any:
        return self._payload


Router = Callable[[str], Any]


class ChaosTransport:
    """Answers from `router(path)` (a payload, or None for a 404) until
    `ok_calls` requests have been answered; after that every request gets
    `then`: "403" (a refusal) or "gone" (the bridge is not there)."""

    def __init__(self, router: Router, ok_calls: int | None = None,
                 then: str = "403") -> None:
        self.router, self.ok_calls, self.then = router, ok_calls, then
        self.calls: list[str] = []
        self.answered = 0

    def get(self, url: str, timeout: float = 10.0) -> Resp:
        path = url.removeprefix(API)
        self.calls.append(path)
        if self.ok_calls is not None and self.answered >= self.ok_calls:
            if self.then == "gone":
                raise TransportError("sofa bridge unreachable (test)")
            return Resp(403, {"error": {"code": 403}})
        self.answered += 1
        payload = self.router(path)
        return Resp(404, {}) if payload is None else Resp(200, payload)


def _config(tmp_path: Path, **kw: Any) -> SofaConfig:
    return SofaConfig(db_path=str(tmp_path / "sofa.db"),
                      runs_dir=str(tmp_path / "runs"), target_rps=1000,
                      max_concurrency=1, breaker_threshold=3, **kw)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """SofaConfig.from_env for a script's main(): a scratch DB and runs dir,
    one worker (deterministic order), no real sleeping."""
    monkeypatch.setenv("SOFA_DB_PATH", str(tmp_path / "sofa.db"))
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("SOFA_MAX_CONCURRENCY", "1")
    monkeypatch.setenv("SOFA_TARGET_RPS", "1000")
    monkeypatch.setenv("SOFA_BREAKER_THRESHOLD", "3")
    monkeypatch.delenv("SOFA_NOW", raising=False)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    (tmp_path / "runs").mkdir()
    return tmp_path


def _use(monkeypatch: pytest.MonkeyPatch, transport: ChaosTransport) -> None:
    """SofascoreClient(config) without a transport takes this one."""
    monkeypatch.setattr(bridge_transport, "make_transport", lambda: transport)


def _main(monkeypatch: pytest.MonkeyPatch, module: Any, argv: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", [module.__name__, *argv])
    code: int = module.main()
    return code


# --- the client and its breaker ---------------------------------------------------


def test_a_403_is_never_retried_and_the_breaker_stops_the_asking(tmp_path: Path):
    transport = ChaosTransport(lambda p: {}, ok_calls=0)
    client = SofascoreClient(_config(tmp_path), transport)
    for _ in range(3):
        with pytest.raises(ProviderError, match="HTTP 403"):
            client.event(1)
    assert len(transport.calls) == 3  # one request each, no retry
    for _ in range(5):
        with pytest.raises(CircuitOpenError):
            client.event(1)
    assert len(transport.calls) == 3  # an open breaker asks nobody
    rows = [json.loads(x) for x in
            (tmp_path / "runs" / "run.log.jsonl").read_text().splitlines()]
    assert [r["status"] for r in rows] == [403, 403, 403]
    assert rows[-1]["breaker_state"] == "OPEN"


def test_the_breaker_cycle_open_half_open_close(tmp_path: Path):
    clock = [0.0]
    transport = ChaosTransport(lambda p: {"ok": 1}, ok_calls=0)
    client = SofascoreClient(_config(tmp_path), transport)
    client.breaker = CircuitBreaker(3, cooldown_s=30, max_cooldown_s=300,
                                    clock=lambda: clock[0])
    for _ in range(3):
        with pytest.raises(ProviderError):
            client.event(1)
    assert client.breaker.is_open and client.breaker.tripped
    clock[0] = 29.9
    with pytest.raises(CircuitOpenError):
        client.event(1)
    assert len(transport.calls) == 3
    # half-open: exactly one probe, and a second caller is still refused
    clock[0] = 30.0
    assert client.breaker.allow() is True
    assert client.breaker.allow() is False
    client.breaker._probe_in_flight = False  # give the probe back to the client
    with pytest.raises(ProviderError):  # the probe is refused too
        client.event(1)
    assert len(transport.calls) == 4
    # reopened with the cooldown doubled
    clock[0] = 30.0 + 59.9
    with pytest.raises(CircuitOpenError):
        client.event(1)
    assert len(transport.calls) == 4
    clock[0] = 30.0 + 60.0
    transport.ok_calls = None  # Sofascore answers again
    assert client.event(1) == {"ok": 1}
    assert not client.breaker.is_open and client.breaker.failures == 0
    assert not client.breaker.tripped
    assert client.breaker._cooldown_s == 30  # and the cooldown is reset


def test_the_cooldown_doubles_up_to_its_cap(tmp_path: Path):
    clock = [0.0]
    breaker = CircuitBreaker(1, cooldown_s=30, max_cooldown_s=100,
                             clock=lambda: clock[0])
    breaker.record_failure()
    waits = []
    for _ in range(4):
        clock[0] += breaker._cooldown_s
        assert breaker.allow()
        breaker.record_failure()
        waits.append(breaker._cooldown_s)
    assert waits == [60, 100, 100, 100]


def test_the_bridge_gone_is_retried_once_per_request_then_opens(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    transport = ChaosTransport(lambda p: {"ok": 1}, ok_calls=2, then="gone")
    client = SofascoreClient(_config(tmp_path), transport)
    assert client.event(1) == {"ok": 1} and client.event(2) == {"ok": 1}
    for _ in range(3):
        with pytest.raises(ProviderError, match="Network error after retry"):
            client.event(3)
    assert len(transport.calls) == 2 + 3 * 2  # one retry each, no more
    with pytest.raises(CircuitOpenError):
        client.event(3)
    assert len(transport.calls) == 8


class _Urlopen:
    """bridge_transport.urlopen: the bridge server's answers, in order."""

    def __init__(self, answers: list[Any]) -> None:
        self.answers, self.calls = answers, 0

    def __call__(self, req: Any, timeout: float = 0.0) -> Any:
        self.calls += 1
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        body = json.dumps(answer).encode()

        class _R:
            def __enter__(self) -> Any:
                return self

            def __exit__(self, *a: Any) -> None:
                return None

            def read(self) -> bytes:
                return body

        return _R()


def test_the_bridge_transport_maps_a_dead_bridge_and_a_refusal(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The real BrowserBridgeTransport under the client: a bridge that is not
    there (URLError) or a tab that never answered (HTTP 504 from the server)
    is a TransportError - retried once; a 403 Sofascore gave the tab is a
    status, never retried."""
    from io import BytesIO
    from urllib.error import HTTPError, URLError

    monkeypatch.setattr(time, "sleep", lambda s: None)
    gone = _Urlopen([URLError("connection refused")])
    monkeypatch.setattr(bridge_transport, "urlopen", gone)
    client = SofascoreClient(_config(tmp_path),
                             bridge_transport.BrowserBridgeTransport())
    with pytest.raises(ProviderError, match="Network error after retry"):
        client.event(1)
    assert gone.calls == 2
    timeout = _Urlopen([HTTPError("http://b/fetch", 504, "Gateway Timeout", {},  # type: ignore[arg-type]
                                  BytesIO(b'{"error": "no tab answered"}'))])
    monkeypatch.setattr(bridge_transport, "urlopen", timeout)
    with pytest.raises(ProviderError, match="bridge HTTP 504"):
        client.event(1)
    assert timeout.calls == 2
    refused = _Urlopen([{"status": 403, "body": "{}", "headers": {}}])
    monkeypatch.setattr(bridge_transport, "urlopen", refused)
    with pytest.raises(ProviderError, match="HTTP 403"):
        client.event(1)
    assert refused.calls == 1  # a refusal is not retried
    assert client.breaker.is_open  # three failures in a row
    with pytest.raises(CircuitOpenError):
        client.event(1)
    assert refused.calls == 1


# --- SPORT_IDENTITY ---------------------------------------------------------------


KICK = datetime(2026, 10, 6, 18, 0, tzinfo=UTC)


def _sport_listing(team: int) -> dict[str, Any]:
    return {"events": [{
        "id": 9000 + team, "startTimestamp": int(KICK.timestamp()),
        "status": {"type": "notstarted"},
        "tournament": {"id": 1, "name": "Extraliga",
                       "uniqueTournament": {"id": 55, "name": "Extraliga"},
                       "category": {"sport": {"slug": "ice-hockey"}}},
        "homeTeam": {"id": team, "name": f"Home {team}", "gender": "M"},
        "awayTeam": {"id": team + 100, "name": f"Away {team}", "gender": "M"}}]}


def _sport_router(path: str) -> Any:
    team = int(path.split("/")[1])
    return _sport_listing(team)


def _sport_board(tmp_path: Path, n: int) -> None:
    day = tmp_path / "runs" / "shadow" / "hockey" / "2026-10-06"
    day.mkdir(parents=True)
    rows = []
    for i in range(1, n + 1):
        rows.append(json.dumps({
            "fetched_at_utc": "2026-10-06T07:00:00Z", "superbet_event_id": str(i),
            "match_name": f"Home {i}·Away {i}", "team1": f"Home {i}",
            "team2": f"Away {i}",
            "kickoff_utc": (KICK + timedelta(minutes=i)).isoformat().replace(
                "+00:00", "Z"),
            "tournament": "Czechy - Extraliga",
            "lines": [{"superbet_event_id": str(i), "market_id": 630,
                       "family": "winner", "period": 0, "subject": "", "line": None,
                       "side": s, "odds": o} for s, o in (("T1", 1.8), ("T2", 2.0))]}))
    (day / "snapshots.jsonl").write_text("\n".join(rows) + "\n")


@pytest.mark.parametrize("then", ["403", "gone"])
def test_sport_identity_stops_at_the_first_refusal_and_resumes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, then: str):
    from bet.sofa import sport_identity as si
    from scripts.sofa import run_sport_identity as rsi

    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(rsi, "now", lambda: datetime(2026, 10, 6, 8, 0, tzinfo=UTC))
    monkeypatch.setattr(si.TeamResolver, "team_id",
                        lambda self, sport, name: int(name.split()[1])
                        if name.startswith("Home") else None)
    _sport_board(tmp_path, 4)
    conn = sqlite3.connect(":memory:")
    transport = ChaosTransport(_sport_router, ok_calls=2, then=then)
    client = SofascoreClient(_config(tmp_path), transport)
    doc, code = rsi.run("2026-10-06", ["hockey"], str(tmp_path / "runs"), client,
                        None, conn)
    assert code == 1  # PARTIAL
    status = {r["superbet_event_id"]: (r["status"], r.get("reason"))
              for r in doc["fixtures"]}
    assert status["1"][0] == status["2"][0] == si.IDENTIFIED
    assert status["3"] == status["4"] == (si.NOT_IDENTIFIED, "BRIDGE_ABORTED")
    # the refused request once (a transport failure: once more), then nothing
    assert len(transport.calls) == 3 + (then == "gone")
    assert doc["aborted"]
    # the bridge is back: only the two not yet identified are asked
    again = ChaosTransport(_sport_router)
    doc2, code2 = rsi.run("2026-10-06", ["hockey"], str(tmp_path / "runs"),
                          SofascoreClient(_config(tmp_path), again), None, conn)
    assert code2 == 0
    assert again.calls == ["team/3/events/next/0", "team/4/events/next/0"]


# --- FIXTURE_CHECK ----------------------------------------------------------------


def _fixture_day(tmp_path: Path, ids: list[int]) -> Path:
    run = tmp_path / "runs" / "2026-10-06"
    run.mkdir(parents=True)
    ko = "2026-10-06T18:00:00Z"
    (run / "02_fixtures.json").write_text(json.dumps(
        [{"sofascore_event_id": i, "kickoff_utc": ko} for i in ids]))
    # Superbet's clock moved 2 h: every match is a FIXTURE_CHECK target
    (run / "04_offer.json").write_text(json.dumps(
        [{"sofascore_event_id": i, "superbet_kickoff_seen_utc": "2026-10-06T20:00:00Z"}
         for i in ids]))
    return run


def _event_router(path: str) -> Any:
    eid = int(path.split("/")[1])
    return {"event": {"id": eid, "startTimestamp": int(KICK.timestamp()),
                      "status": {"type": "notstarted", "code": 0}}}


@pytest.mark.parametrize("then", ["403", "gone"])
def test_fixture_check_marks_the_rest_unverified_after_a_refusal(
        env: Path, monkeypatch: pytest.MonkeyPatch, then: str):
    from bet.sofa import fixture_status as fs
    from scripts.sofa import run_fixture_check

    monkeypatch.setattr(run_fixture_check, "frozen_clock_refusal", lambda d: None)
    run = _fixture_day(env, [11, 12, 13, 14])
    transport = ChaosTransport(_event_router, ok_calls=1, then=then)
    _use(monkeypatch, transport)
    code = _main(monkeypatch, run_fixture_check, ["--date", "2026-10-06"])
    assert code == 1  # PARTIAL
    events = json.loads((run / fs.FIXTURE_STATUS_FILE).read_text())["events"]
    assert events["11"]["status"] == "notstarted"
    assert {events[k]["status"] for k in ("12", "13", "14")} == {fs.UNVERIFIED}
    # one refused request (a transport failure: plus its one retry), then none
    assert transport.calls == ["event/11"] + ["event/12"] * (1 + (then == "gone"))


# --- RESOLVE ----------------------------------------------------------------------


def _resolve_payload(n: int) -> dict[str, Any]:
    return {
        "id": 5000 + n, "startTimestamp": int(KICK.timestamp()),
        "status": {"type": "notstarted"},
        "homeTeam": {"id": 100 + n, "name": f"Alpha{n}", "gender": "M"},
        "awayTeam": {"id": 200 + n, "name": f"Bravo{n}", "gender": "M"},
        "tournament": {"id": 1, "name": "Ekstraklasa",
                       "category": {"id": 47, "name": "Poland",
                                    "sport": {"slug": "football"}},
                       "uniqueTournament": {"id": 202, "name": "Ekstraklasa"}},
        "season": {"id": 1},
    }


def _resolve_router(path: str) -> Any:
    if path.startswith("search/all"):
        q = path.split("q=")[1].split("&")[0]
        n = int(q.removeprefix("alpha").removeprefix("bravo"))
        team = ({"id": 100 + n, "name": f"Alpha{n}"} if q.startswith("alpha")
                else {"id": 200 + n, "name": f"Bravo{n}"})
        return {"results": [{"type": "team", "entity": {
            **team, "sport": {"slug": "football"}, "gender": "M",
            "country": {"name": "Poland"}}}]}
    if path.startswith("team/"):
        _, tid, _, kind, page = path.split("/")
        n = int(tid) % 100
        if kind == "next" and page == "0":
            return {"events": [_resolve_payload(n)], "hasNextPage": False}
        return {"events": [], "hasNextPage": False}
    if path.startswith("event/"):
        return {"event": _resolve_payload(int(path.split("/")[1]) - 5000)}
    return None


def _resolve_board(env: Path, n: int) -> Path:
    day = env / "runs" / "2026-10-06"
    day.mkdir(parents=True, exist_ok=True)
    (day / "01_board.json").write_text(json.dumps([
        {"superbet_event_id": str(i), "sport": "football",
         "match_name": f"Alpha{i}·Bravo{i}", "side_a": f"Alpha{i}",
         "side_b": f"Bravo{i}", "kickoff_utc": "2026-10-06T18:00:00Z"}
        for i in range(1, n + 1)]))
    return day


def _summary(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    line = next(ln for ln in capsys.readouterr().out.splitlines()
                if ln.startswith("SOFA_SUMMARY: "))
    out: dict[str, Any] = json.loads(line.removeprefix("SOFA_SUMMARY: "))
    return out


def test_resolve_resolves_a_clean_board(env: Path, monkeypatch: pytest.MonkeyPatch,
                                        capsys: pytest.CaptureFixture[str]):
    """The fake Sofascore is good enough for RESOLVE to resolve every entry
    - so the chaos tests below test the failure, not the fake."""
    from scripts.sofa import run_resolve

    _resolve_board(env, 3)
    _use(monkeypatch, ChaosTransport(_resolve_router))
    assert _main(monkeypatch, run_resolve, ["--date", "2026-10-06"]) == 0
    assert _summary(capsys)["metrics"]["output_fixtures"] == 3


@pytest.mark.parametrize("then", ["403", "gone"])
def test_resolve_stops_when_the_breaker_opens_and_marks_the_slate(
        env: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str], then: str):
    from bet.sofa.artifact_guard import incomplete_reason
    from scripts.sofa import run_resolve

    day = _resolve_board(env, 6)
    clean = ChaosTransport(_resolve_router)
    _use(monkeypatch, clean)
    assert _main(monkeypatch, run_resolve, ["--date", "2026-10-06"]) == 0
    per_fixture = len(clean.calls) // 6
    capsys.readouterr()
    (day / "02_fixtures.json").unlink()
    # a fresh cache: every request goes out again
    Path(env / "sofa.db").unlink()

    transport = ChaosTransport(_resolve_router, ok_calls=2 * per_fixture, then=then)
    _use(monkeypatch, transport)
    code = _main(monkeypatch, run_resolve, ["--date", "2026-10-06"])
    summary = _summary(capsys)
    assert code == 1 and summary["verdict"] == "PARTIAL"
    assert summary["metrics"]["breaker_open"] is True
    assert summary["metrics"]["output_fixtures"] == 2
    assert incomplete_reason(day / "02_fixtures.json")  # never read as the slate
    refused = len(transport.calls) - 2 * per_fixture
    # threshold failures (a transport failure: each retried once), then quiet
    assert refused == 3 * (1 + (then == "gone"))
    assert not any(n > 1 for p, n in Counter(transport.calls).items()
                   if then == "403")  # a refused URL is never asked again


def test_resolve_with_five_workers_stops_within_the_requests_in_flight(
        env: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]):
    """ThreadPoolExecutor.map submits the whole board at once and the stage's
    `break` waits for it to drain: every queued entry must then meet the open
    breaker, not the provider."""
    from scripts.sofa import run_resolve

    monkeypatch.setenv("SOFA_MAX_CONCURRENCY", "5")
    _resolve_board(env, 40)
    transport = ChaosTransport(_resolve_router, ok_calls=0)
    _use(monkeypatch, transport)
    code = _main(monkeypatch, run_resolve, ["--date", "2026-10-06"])
    summary = _summary(capsys)
    assert code == 2 and summary["verdict"] == "FAILED"  # nothing resolved
    assert summary["metrics"]["breaker_open"] is True
    # the threshold, plus at most the other workers' requests already out
    assert 3 <= len(transport.calls) <= 3 + 4


# --- the backfills: interrupted, then resumed --------------------------------------


NOW = int(time.time())
DAY = 86400


def _db(env: Path) -> sqlite3.Connection:
    from bet.sofa.cache import SofaCache

    SofaCache(SofaConfig(db_path=str(env / "sofa.db"), runs_dir=str(env / "runs")))
    return sqlite3.connect(str(env / "sofa.db"))


def _football_event(eid: int, ts: int, home: int, away: int,
                    comp: int = 202) -> dict[str, Any]:
    return {"id": eid, "startTimestamp": ts, "status": {"type": "finished"},
            "tournament": {"category": {"sport": {"slug": "football"}},
                           "uniqueTournament": {"id": comp}},
            "homeTeam": {"id": home, "name": f"T{home}"},
            "awayTeam": {"id": away, "name": f"T{away}"},
            "homeScore": {"current": 1}, "awayScore": {"current": 0}}


def _save_page(conn: sqlite3.Connection, entity: int, page: int,
               events: list[dict[str, Any]], has_next: bool = True,
               fetched_at: str = "2026-09-01T00:00:00+00:00") -> None:
    conn.execute("INSERT OR REPLACE INTO sofa_entity_events "
                 "VALUES (?, 'last', ?, ?, ?)",
                 (entity, page, fetched_at,
                  json.dumps({"events": events, "hasNextPage": has_next})))
    conn.commit()


def test_backfill_listings_resumes_after_a_refusal(
        env: Path, monkeypatch: pytest.MonkeyPatch):
    from scripts.sofa import backfill_listings

    conn = _db(env)
    # two teams, each with one recent page cached; history goes back 10 pages
    for team in (1, 2):
        _save_page(conn, team, 0, [_football_event(team * 1000, NOW - DAY, team, 99)])

    def router(path: str) -> Any:
        _, tid, _, _, page = path.split("/")
        p = int(page)
        return {"events": [_football_event(int(tid) * 1000 + p, NOW - p * 60 * DAY,
                                           int(tid), 99)],
                "hasNextPage": p < 10}

    seed = env / "seed.json"
    argv = ["--days", "300", "--seed-file", str(seed), "--seed-before",
            "2026-12-31T00:00:00+00:00"]
    first = ChaosTransport(router, ok_calls=3)
    _use(monkeypatch, first)
    assert _main(monkeypatch, backfill_listings, argv) == 2  # FAILED: breaker
    done = first.calls[:3]
    assert len(first.calls) == 6  # three refused, then nothing
    second = ChaosTransport(router)
    _use(monkeypatch, second)
    assert _main(monkeypatch, backfill_listings, argv) == 0
    assert not set(done) & set(second.calls)  # nothing done is asked again
    assert set(second.calls) >= {"team/1/events/last/5", "team/2/events/last/1"}
    third = ChaosTransport(router)
    _use(monkeypatch, third)
    assert _main(monkeypatch, backfill_listings, argv) == 0
    assert third.calls == []  # both reach the window now


def _stats_router(path: str) -> Any:
    if path.endswith("/statistics"):
        return {"statistics": [{"period": "ALL", "groups": []}]}
    if path.endswith("/incidents"):
        return {"incidents": []}
    if path.endswith("/lineups"):
        return {"home": {"players": [{"player": {"id": 1}, "statistics": {
            "minutesPlayed": 90}}]}, "away": {"players": []}}
    return None


def _stats_cache(env: Path, n: int) -> None:
    conn = _db(env)
    _save_page(conn, 1, 0, [_football_event(7000 + i, NOW - (i + 3) * DAY, 1, 2)
                            for i in range(n)], has_next=False)
    day = env / "runs" / "2026-10-01"
    day.mkdir(parents=True, exist_ok=True)
    (day / "02_fixtures.json").write_text(json.dumps([
        {"sofascore_event_id": 1, "sport": "football", "competition_id": 202,
         "home_entity_id": 1, "away_entity_id": 2}]))


@pytest.mark.parametrize("then", ["403", "gone"])
def test_backfill_event_stats_resumes_where_it_stopped(
        env: Path, monkeypatch: pytest.MonkeyPatch, then: str):
    from scripts.sofa import backfill_event_stats

    _stats_cache(env, 5)
    first = ChaosTransport(_stats_router, ok_calls=4, then=then)  # 2 events x 2
    _use(monkeypatch, first)
    assert _main(monkeypatch, backfill_event_stats, ["--days", "60"]) == 2
    second = ChaosTransport(_stats_router)
    _use(monkeypatch, second)
    assert _main(monkeypatch, backfill_event_stats, ["--days", "60"]) == 0
    asked = {p.split("/")[1] for p in second.calls}
    # newest first: 7000 and 7001 were done; the rest, and only the rest, now
    assert asked == {"7002", "7003", "7004"}
    third = ChaosTransport(_stats_router)
    _use(monkeypatch, third)
    assert _main(monkeypatch, backfill_event_stats, ["--days", "60"]) == 0
    assert third.calls == []


def test_backfill_football_lineups_resumes_where_it_stopped(
        env: Path, monkeypatch: pytest.MonkeyPatch):
    from scripts.sofa import backfill_football_lineups

    _stats_cache(env, 4)
    day = env / "runs" / "2026-10-01"
    (day / "04_offer.json").write_text(json.dumps([
        {"sofascore_event_id": 1, "rungs": [{"market": "player_shots"}]}]))
    # event 7000: stats + incidents + lineups; 7001: stats + incidents, then
    # the lineups request is refused (the stats row is already written)
    first = ChaosTransport(_stats_router, ok_calls=5)
    _use(monkeypatch, first)
    assert _main(monkeypatch, backfill_football_lineups, ["--days", "60"]) == 2
    second = ChaosTransport(_stats_router)
    _use(monkeypatch, second)
    assert _main(monkeypatch, backfill_football_lineups, ["--days", "60"]) == 0
    assert "event/7000/lineups" not in second.calls
    assert "event/7001/statistics" not in second.calls  # its stats were kept
    assert "event/7001/lineups" in second.calls
    third = ChaosTransport(_stats_router)
    _use(monkeypatch, third)
    assert _main(monkeypatch, backfill_football_lineups, ["--days", "60"]) == 0
    assert third.calls == []


def test_backfill_cs2_resumes_after_the_bridge_went_away(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Through the real client: the series stored before the bridge went are
    not fetched again."""
    from scripts.sofa import backfill_cs2

    monkeypatch.setattr(time, "sleep", lambda s: None)
    at = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)

    def cs(eid: int, days_ago: float, home: int, away: int) -> dict[str, Any]:
        start = int((at - timedelta(days=days_ago)).timestamp())
        return {"id": eid, "startTimestamp": start,
                "homeTeam": {"id": home, "name": f"T{home}"},
                "awayTeam": {"id": away, "name": f"T{away}"},
                "homeScore": {"current": 1}, "awayScore": {"current": 0},
                "status": {"type": "finished", "description": "Ended"},
                "tournament": {"name": "CCT", "category": {"name": "Counter Strike"}}}

    def router(path: str) -> Any:
        if path.startswith("search/all"):
            q = path.split("q=")[1].split("&")[0]
            tid = {"T1": 1, "T2": 2}[q]
            return {"results": [{"type": "team", "entity": {
                "id": tid, "name": q, "sport": {"slug": "esports"}}}]}
        if path.startswith("team/"):
            page = int(path.split("/")[-1])
            return {"events": [cs(10 + i, i + 1, 1, 2) for i in range(4)]
                    if page == 0 else [], "hasNextPage": False}
        if path.endswith("/esports-games"):
            eid = int(path.split("/")[1])
            return {"games": [{"id": eid * 10, "startTimestamp": 1,
                               "status": {"type": "finished"},
                               "homeScore": {"display": 13},
                               "awayScore": {"display": 9},
                               "hasCompleteStatistics": True}]}
        if path.startswith("esports-game/"):
            gid = int(path.split("/")[1])
            rows = [{"player": {"id": gid + i, "name": f"p{i}"}, "kills": 15}
                    for i in range(5)]
            return {"homeTeamPlayers": rows, "awayTeamPlayers": rows}
        return None

    day = tmp_path / "runs" / "cs2" / "2026-09-27"
    day.mkdir(parents=True)
    (day / "snapshots.jsonl").write_text(
        json.dumps({"team1": "T1", "team2": "T2", "lines": []}) + "\n")
    cfg = _config(tmp_path)
    kw: dict[str, Any] = {"days": 180, "hops": 0, "max_minutes": 5,
                          "dry_run": False, "extra_team_ids": [], "at": at}
    probe = ChaosTransport(router)
    backfill_cs2.run(SofascoreClient(cfg, probe), cfg, **kw)
    per_series = sum(p.startswith(("event/", "esports-game/"))
                     for p in probe.calls) // 4
    discovery = len(probe.calls) - 4 * per_series
    Path(cfg.db_path).unlink()

    first = ChaosTransport(router, ok_calls=discovery + 2 * per_series, then="gone")
    result = backfill_cs2.run(SofascoreClient(cfg, first), cfg, **kw)
    assert result["verdict"] != "OK"
    stored = {r[0] for r in sqlite3.connect(cfg.db_path).execute(
        "SELECT sofascore_event_id FROM cs2_series")}
    assert len(stored) == 2
    second = ChaosTransport(router)
    backfill_cs2.run(SofascoreClient(cfg, second), cfg, **kw)
    fetched = {int(p.split("/")[1]) for p in second.calls
               if p.endswith("/esports-games")}
    assert fetched and not fetched & stored
