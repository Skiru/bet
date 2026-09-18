"""Tests for the defects the second live run exposed (FIRST_RUN_FINDINGS.md F13-F32).

Each test names the finding it pins and is written to fail against the code as
it stood on 010966d6 — for the reason the finding gives, not merely to exercise
the new path. Where a test is a guard rather than a proof, it says so.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _run_driver(source: str, tmp_path: Path, env_extra: dict[str, str]) -> Path:
    """Run a driver script as a subprocess with stdout redirected to a file.

    Redirection is the whole point: under a pipe or a file Python buffers
    stdout in blocks, which is how a stage's verdict spent three hours in a
    buffer while the run it condemned kept going (F18).
    """
    driver = tmp_path / "driver.py"
    driver.write_text(textwrap.dedent(source), encoding="utf-8")
    out = tmp_path / "stdout.txt"

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO)
    env.pop("PYTHONUNBUFFERED", None)  # the fix must not depend on the incantation
    env.update(env_extra)

    with open(out, "wb") as handle:
        proc = subprocess.Popen(
            [sys.executable, str(driver)],
            stdout=handle,
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=str(REPO),
        )
        try:
            deadline = time.time() + 30.0
            while time.time() < deadline:
                if out.read_text(encoding="utf-8", errors="replace").strip():
                    break
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
        finally:
            proc.kill()
            proc.wait(timeout=10)
    return out


# --------------------------------------------------------------------------
# F18 — a stage verdict you cannot see during the run is not a verdict
# --------------------------------------------------------------------------


def test_f18_stage_summary_reaches_a_redirected_file_before_the_process_ends(
    tmp_path: Path,
) -> None:
    """OFFER's FAILED summary must be readable while the process is still alive.

    Fails on the old code for the right reason: the summary was printed without
    ``flush``, so with stdout redirected the file stayed empty until exit — and
    the process here never gets to exit.
    """
    runs = tmp_path / "runs"
    (runs / "2026-01-01").mkdir(parents=True)
    (runs / "2026-01-01" / "02_fixtures.json").write_text("[]", encoding="utf-8")

    out = _run_driver(
        """
        import sys, time
        import scripts.sofa.run_offer as run_offer

        class Boom:
            def __init__(self, *a, **k): pass
            def fetch_offers(self, fixtures):
                raise RuntimeError("'NoneType' object is not iterable")

        run_offer.OfferFetcher = Boom
        run_offer.SuperbetClient = lambda **k: None
        sys.argv = ["run_offer", "--date", "2026-01-01"]
        run_offer.main()
        time.sleep(60)          # the run carries on, as it did on 2026-09-18
        """,
        tmp_path,
        {"SOFA_RUNS_DIR": str(runs)},
    )

    text = out.read_text(encoding="utf-8")
    assert "SOFA_SUMMARY" in text, "the stage verdict was still sitting in the buffer"
    payload = json.loads(text.split("SOFA_SUMMARY: ", 1)[1].splitlines()[0])
    assert payload["verdict"] == "FAILED"
    assert "NoneType" in payload["metrics"]["error"], (
        "the reason for the failure must travel with the verdict"
    )


def test_f18_pipeline_prints_a_verdict_for_every_stage_not_only_failures(
    tmp_path: Path,
) -> None:
    """A stage that succeeded must say so, on stderr, as it happens.

    Fails on the old code for the right reason: it printed a line only when a
    stage returned >= 2, so an OK stage passed in silence and the operator
    could not tell a finished stage from a hung one.
    """
    driver = tmp_path / "driver.py"
    driver.write_text(
        textwrap.dedent(
            """
            import json, sys, time, types
            import scripts.sofa.run_pipeline as rp

            ok = types.ModuleType("ok_stage")
            ok.main = lambda: 0
            sys.modules["ok_stage"] = ok

            hang = types.ModuleType("hang_stage")
            def _hang():
                time.sleep(60)
                return 0
            hang.main = _hang
            sys.modules["hang_stage"] = hang

            rp.STAGE_MODULES = {"OK": "ok_stage", "HANG": "hang_stage"}
            rp.DEFAULT_SEQUENCE = [("OK", "OK"), ("HANG", "HANG")]
            sys.argv = ["run_pipeline", "--date", "2026-01-01"]
            rp.main()
            """
        ),
        encoding="utf-8",
    )
    err = tmp_path / "stderr.txt"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO)
    env["SOFA_RUNS_DIR"] = str(tmp_path / "runs")

    with open(err, "wb") as handle:
        proc = subprocess.Popen(
            [sys.executable, str(driver)],
            stdout=subprocess.DEVNULL,
            stderr=handle,
            env=env,
            cwd=str(REPO),
        )
        try:
            deadline = time.time() + 30.0
            while time.time() < deadline:
                if "OK:" in err.read_text(encoding="utf-8", errors="replace"):
                    break
                time.sleep(0.05)
        finally:
            proc.kill()
            proc.wait(timeout=10)

    text = err.read_text(encoding="utf-8")
    assert "OK: OK (exit 0)" in text, (
        "a stage that succeeded passed in silence; only FAILED was ever printed"
    )
    assert "--- HANG ---" in text, "the next stage's marker must already be visible"


# --------------------------------------------------------------------------
# F13 — the run id must exist before the stages that log under it
# --------------------------------------------------------------------------


def test_f13_every_stage_sees_the_same_non_empty_run_id_and_it_differs_per_run(
    tmp_path: Path,
) -> None:
    """Stages log under the run id, so it has to exist before they run.

    Fails on the old code for the right reason: the id was minted *after* the
    stage loop, so every stage read "" from the environment, and ``setdefault``
    meant a second run inherited the first one's id instead of minting one.
    """
    driver = tmp_path / "driver.py"
    driver.write_text(
        textwrap.dedent(
            """
            import json, sys, types
            import scripts.sofa.run_pipeline as rp
            from bet.sofa.config import SofaConfig

            seen = []
            mod = types.ModuleType("probe_stage")
            mod.main = lambda: seen.append(SofaConfig.from_env().run_id) or 0
            sys.modules["probe_stage"] = mod

            rp.STAGE_MODULES = {"A": "probe_stage", "B": "probe_stage"}
            rp.DEFAULT_SEQUENCE = [("A", "A"), ("B", "B")]

            ids = []
            for _ in range(2):
                seen.clear()
                sys.argv = ["run_pipeline", "--date", "2026-01-01"]
                rp.main()
                ids.append(list(seen))
            print("PROBE: " + json.dumps(ids))
            """
        ),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO)
    env["SOFA_RUNS_DIR"] = str(tmp_path / "runs")
    # A stale id in the environment is exactly what setdefault used to honour.
    env["SOFA_RUN_ID"] = "stale-from-shell"

    proc = subprocess.run(
        [sys.executable, str(driver)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO),
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    line = next(ln for ln in proc.stdout.splitlines() if ln.startswith("PROBE: "))
    first, second = json.loads(line.removeprefix("PROBE: "))

    assert all(first), "a stage saw an empty run id"
    assert len(set(first)) == 1, "stages of one run must share an id"
    assert first[0] != "stale-from-shell", "an inherited id merges two runs in the log"
    assert set(first).isdisjoint(second), "a second run must mint a new id"


def test_f13_run_id_option_is_honoured_and_reaches_the_summary(tmp_path: Path) -> None:
    """Guard, not proof: --run-id did not exist before, so it cannot regress."""
    driver = tmp_path / "driver.py"
    driver.write_text(
        textwrap.dedent(
            """
            import sys, types
            import scripts.sofa.run_pipeline as rp
            from bet.sofa.config import SofaConfig

            mod = types.ModuleType("probe_stage")
            mod.main = lambda: print("STAGE_SAW: " + SofaConfig.from_env().run_id) or 0
            sys.modules["probe_stage"] = mod
            rp.STAGE_MODULES = {"A": "probe_stage"}
            rp.DEFAULT_SEQUENCE = [("A", "A")]
            sys.argv = ["run_pipeline", "--date", "2026-01-01", "--run-id", "chosen1"]
            rp.main()
            """
        ),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO)
    env["SOFA_RUNS_DIR"] = str(tmp_path / "runs")

    proc = subprocess.run(
        [sys.executable, str(driver)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO),
        timeout=60,
    )
    assert "STAGE_SAW: chosen1" in proc.stdout
    summary_line = next(
        ln for ln in proc.stdout.splitlines() if ln.startswith("SOFA_SUMMARY: ")
    )
    assert (
        json.loads(summary_line.removeprefix("SOFA_SUMMARY: "))["run_id"] == "chosen1"
    )


# --------------------------------------------------------------------------
# F22 / F20 — the stage belongs to the caller, not to the client method
# --------------------------------------------------------------------------


def test_f22_entity_events_is_logged_under_the_stage_that_called_it(
    tmp_path: Path,
) -> None:
    """SAMPLES calls entity_events too, and its cost must not read as RESOLVE.

    Fails on the old code for the right reason: ``entity_events`` passed the
    literal "RESOLVE" to ``_execute``, so 146 listing requests made by SAMPLES
    were filed under RESOLVE — 8.2% of that stage's cost, and the reason three
    claims in the audit were wrong.
    """
    from bet.sofa.client import SofascoreClient
    from bet.sofa.config import SofaConfig
    from bet.sofa.stage import stage
    from tests.sofa.test_client import MockResponse, MockTransport

    config = SofaConfig(runs_dir=str(tmp_path), target_rps=1000)
    transport = MockTransport()
    transport.responses = [MockResponse(200, {"events": []}) for _ in range(2)]
    client = SofascoreClient(config, transport)

    with stage("RESOLVE"):
        client.entity_events(1, "last", 0)
    with stage("SAMPLES"):
        client.entity_events(2, "last", 0)

    rows = [
        json.loads(ln)
        for ln in client.log_path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert [r["stage"] for r in rows] == ["RESOLVE", "SAMPLES"], (
        "the same method was called from two stages and must be logged as two"
    )


def test_f20_superbet_requests_are_logged_under_the_calling_stage(
    tmp_path: Path,
) -> None:
    """Every Superbet request said "BOARD", including OFFER's and SAMPLES'.

    Fails on the old code for the right reason: ``_get_json`` passed the literal
    "BOARD", so all 95 Superbet rows of the run read BOARD and the stages could
    only be told apart by the 30-minute gap between their timestamps.
    """
    import threading
    from typing import Any

    from bet.sofa.stage import stage
    from bet.sofa.superbet import SuperbetClient

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> Any:
            return {"data": []}

    class FakeSession:
        headers: dict[str, str] = {}

        def get(self, url: str, params: Any = None, timeout: float = 0.0) -> Any:
            return FakeResponse()

    client = SuperbetClient.__new__(SuperbetClient)
    client.base_url = "https://example.invalid"
    client.log_path = tmp_path / "run.log.jsonl"
    client.run_id = "t"
    client.session = FakeSession()  # type: ignore[assignment]
    client._log_lock = threading.Lock()

    # The real request path, from two different stages.
    with stage("OFFER"):
        client.event_odds(1)
    with stage("SAMPLES"):
        client.event_odds(2)

    rows = [
        json.loads(ln)
        for ln in client.log_path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert [r["stage"] for r in rows] == ["OFFER", "SAMPLES"], (
        "Superbet requests were all filed under BOARD regardless of caller"
    )


def test_f22_no_client_method_hardcodes_a_stage_literal() -> None:
    """Guard: the next method added must not reintroduce the defect.

    Fails on the old code for the right reason: six methods passed a literal.
    """
    import ast
    import inspect

    from bet.sofa import client as client_module

    tree = ast.parse(inspect.getsource(client_module))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "_execute"):
            continue
        for kw in node.keywords:
            if kw.arg == "stage" and isinstance(kw.value, ast.Constant):
                offenders.append(str(kw.value.value))
    assert not offenders, (
        f"client methods still name their own stage: {sorted(set(offenders))}"
    )


def test_f22_an_undeclared_caller_is_labelled_client_not_a_real_stage() -> None:
    """An unlabelled request must be visible, not misfiled under a real stage.

    Read in a fresh thread, because a thread starts with an empty context and
    so observes the declared default rather than whatever the last stage in
    this process happened to set.
    """
    import threading

    from bet.sofa.stage import current_stage

    seen: list[str] = []
    t = threading.Thread(target=lambda: seen.append(current_stage()))
    t.start()
    t.join()
    assert seen == ["CLIENT"]


# --------------------------------------------------------------------------
# F14 — the schema has to exist before anything reads it
# --------------------------------------------------------------------------


def test_f14_a_cache_on_a_fresh_database_can_read_and_write_every_table(
    tmp_path: Path,
) -> None:
    """The pipeline must start from nothing, on a database file that is not there.

    Fails on the old code for the right reason: nothing in production called
    migrate(), so the first statement raised ``no such table: sofa_entity``.
    The live database only worked because a table set had been created by hand
    once, which is why sofa_entity_miss — added later by F4 — was missing and
    killed RESOLVE on its first fixture.
    """
    from bet.sofa.cache import SofaCache
    from bet.sofa.config import SofaConfig
    from bet.sofa.db import get_connection
    from bet.sofa.settle import SettledRow, insert_settled_rows

    db = tmp_path / "does_not_exist_yet.db"
    assert not db.exists()
    cache = SofaCache(SofaConfig(db_path=str(db)))

    # sofa_entity
    assert cache.get_entity("football", "anything") is None
    cache.save_entity("football", "arsenal", 42, "Arsenal", "team", "ENG", "verified")
    assert (cache.get_entity("football", "arsenal") or {})["sofascore_id"] == 42

    # sofa_entity_miss — the table F4 added and the live database never got
    assert cache.get_entity_miss("football", "nosuchteam") is False
    cache.save_entity_miss("football", "nosuchteam")
    assert cache.get_entity_miss("football", "nosuchteam") is True

    # sofa_entity_events
    assert cache.get_entity_events(42, "last", 0) is None
    cache.save_entity_events(42, "last", 0, {"events": []})
    assert cache.get_entity_events(42, "last", 0) == {"events": []}

    # sofa_event_stats
    assert cache.get_event_stats(7) is None
    cache.save_event_stats(7, {"a": 1}, None, "finished")
    assert (cache.get_event_stats(7) or (None,))[0] == {"a": 1}

    # sofa_settled_row
    with get_connection(str(db)) as conn:
        rows = conn.execute("SELECT COUNT(*) AS n FROM sofa_settled_row").fetchone()
        assert rows["n"] == 0
        assert (
            insert_settled_rows(
                conn,
                [
                    SettledRow(
                        run_date="2026-01-01",
                        sofascore_event_id=7,
                        sport="football",
                        competition_id=1,
                        market="goals_total",
                        subject="",
                        line=2.5,
                        direction="OVER",
                        sample_size=10,
                        sample_mean=3.0,
                        sample_sd=1.1,
                        p_central=0.5,
                        p_bar=0.5,
                        market_p=0.5,
                        actual_value=3.0,
                        outcome="WIN",
                        settled_at="2026-01-02T00:00:00Z",
                    )
                ],
            )
            == 1
        )


def test_f14_every_table_migrate_declares_exists_after_the_cache_is_built(
    tmp_path: Path,
) -> None:
    """Guard: the next table added to migrate() must reach the live database.

    This is the check that would have caught F4's table going missing.
    """
    import re

    from bet.sofa.cache import SofaCache
    from bet.sofa.config import SofaConfig
    from bet.sofa.db import get_connection

    source = (REPO / "src" / "bet" / "sofa" / "db.py").read_text(encoding="utf-8")
    declared = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", source))
    assert declared, "migrate() declares no tables; the guard would pass vacuously"

    db = tmp_path / "fresh.db"
    SofaCache(SofaConfig(db_path=str(db)))
    with get_connection(str(db)) as conn:
        live = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert declared <= live, f"tables never created: {sorted(declared - live)}"


# --------------------------------------------------------------------------
# F15 — a stage that raises fails that stage, not the run
# --------------------------------------------------------------------------


def test_f15_a_raising_stage_does_not_stop_the_stages_after_it(
    tmp_path: Path,
) -> None:
    """One stage's exception must not take the rest of the sequence with it.

    Fails on the old code for the right reason: run_stage had no ``except
    Exception``, so a sqlite3.OperationalError in RESOLVE escaped main() and
    killed the whole pipeline — five stages never ran, and --stop-on-failure
    had not been asked for.
    """
    driver = tmp_path / "driver.py"
    driver.write_text(
        textwrap.dedent(
            """
            import json, sys, types
            import scripts.sofa.run_pipeline as rp

            ran = []
            boom = types.ModuleType("boom_stage")
            def _boom():
                ran.append("BOOM")
                raise RuntimeError("no such table: sofa_entity_miss")
            boom.main = _boom
            sys.modules["boom_stage"] = boom

            after = types.ModuleType("after_stage")
            def _after():
                ran.append("AFTER")
                return 0
            after.main = _after
            sys.modules["after_stage"] = after

            rp.STAGE_MODULES = {"BOOM": "boom_stage", "AFTER": "after_stage"}
            rp.DEFAULT_SEQUENCE = [("BOOM", "BOOM"), ("AFTER", "AFTER")]
            sys.argv = ["run_pipeline", "--date", "2026-01-01"]
            code = rp.main()
            print("PROBE: " + json.dumps({"ran": ran, "code": code}))
            """
        ),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO)
    env["SOFA_RUNS_DIR"] = str(tmp_path / "runs")

    proc = subprocess.run(
        [sys.executable, str(driver)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO),
        timeout=60,
    )
    assert proc.returncode == 0, (
        f"the exception escaped main() and killed the run:\n{proc.stderr}"
    )
    line = next(ln for ln in proc.stdout.splitlines() if ln.startswith("PROBE: "))
    probe = json.loads(line.removeprefix("PROBE: "))
    assert probe["ran"] == ["BOOM", "AFTER"], "the stage after the failure never ran"
    assert probe["code"] == 2, "the run's verdict must be FAILED"
    assert "STAGE_EXCEPTION" in proc.stderr, "the failure must name itself and the run"
    assert "run_id=" in proc.stderr


def test_f15_resolve_writes_its_artifact_even_when_the_stage_raises(
    tmp_path: Path,
) -> None:
    """F5 held only for CircuitOpenError, because the write sat after the loop.

    Fails on the old code for the right reason: 02_resolve/02_fixtures.json did
    not exist after the second run died, so the fixtures already resolved were
    lost along with the ones that never got a turn.
    """
    runs = tmp_path / "runs"
    (runs / "2026-01-01").mkdir(parents=True)
    board = [
        {
            "superbet_event_id": str(i),
            "sport": "football",
            "match_name": f"Team A{i} · Team B{i}",
            "side_a": f"Team A{i}",
            "side_b": f"Team B{i}",
            "kickoff_utc": "2026-01-01T18:00:00Z",
        }
        for i in (1, 2, 3)
    ]
    (runs / "2026-01-01" / "01_board.json").write_text(
        json.dumps(board), encoding="utf-8"
    )

    driver = tmp_path / "driver.py"
    driver.write_text(
        textwrap.dedent(
            """
            import sqlite3, sys
            import bet.sofa.resolve as R
            import scripts.sofa.run_resolve as run_resolve

            calls = {"n": 0}
            def fake_resolve(self, sport, side, kickoff, opponent, **kw):
                calls["n"] += 1
                if calls["n"] > 2:
                    # Not a ProviderError: the F14 failure was local, which is
                    # exactly why none of the three defences caught it.
                    raise sqlite3.OperationalError("no such table: sofa_entity_miss")
                return 10 + calls["n"], {"id": 100 + calls["n"]}, False

            def fake_quality(self, event, kickoff, opponent, **kw):
                return 100.0

            R.SofaResolver.resolve_entity = fake_resolve
            R.SofaResolver.match_quality = fake_quality
            from datetime import UTC, datetime
            from bet.sofa.contracts import Fixture

            def fake_parse(event, sport, ids, client, identity, **kw):
                return Fixture(
                    sofascore_event_id=event["id"],
                    superbet_event_ids=ids,
                    sport=sport,
                    kickoff_utc=datetime(2026, 1, 1, 18, 0, tzinfo=UTC),
                    home_name="a", away_name="b",
                    home_entity_id=1, away_entity_id=2,
                    competition_name="C", competition_id=1, season_id=1,
                    category_name="X", identity=identity,
                    round_number=None, round_name=None, cup_round_type=None,
                    previous_leg_event_id=None, venue_name=None, referee=None,
                    ground_type=None, default_period_count=None,
                )

            run_resolve.parse_fixture = fake_parse
            sys.argv = ["run_resolve", "--date", "2026-01-01"]
            run_resolve.main()
            """
        ),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO)
    env["SOFA_RUNS_DIR"] = str(runs)
    env["SOFA_DB_PATH"] = str(tmp_path / "t.db")

    proc = subprocess.run(
        [sys.executable, str(driver)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO),
        timeout=60,
    )
    assert proc.returncode != 0, "the driver is meant to die; that is the scenario"
    assert "OperationalError" in proc.stderr, proc.stderr[-3000:]

    artifact = runs / "2026-01-01" / "02_fixtures.json"
    assert artifact.exists(), "the stage died and left no artifact at all"
    resolved = json.loads(artifact.read_text(encoding="utf-8"))
    assert len(resolved) == 2, (
        "the fixtures that had already resolved must survive the failure"
    )


# --------------------------------------------------------------------------
# F32 — "odds": null is the normal shape, not an edge case
# --------------------------------------------------------------------------


def _fixture(sofascore_event_id: int, superbet_ids: list[str]):  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime

    from bet.sofa.contracts import Fixture

    return Fixture(
        sofascore_event_id=sofascore_event_id,
        superbet_event_ids=superbet_ids,
        sport="football",
        kickoff_utc=datetime(2026, 1, 1, 18, 0, tzinfo=UTC),
        home_name="Home",
        away_name="Away",
        home_entity_id=1,
        away_entity_id=2,
        competition_name="C",
        competition_id=1,
        season_id=1,
        category_name="X",
        identity="CONFIRMED",
        round_number=None,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type=None,
        default_period_count=None,
    )


def test_f32_a_match_that_is_no_longer_priced_does_not_take_the_board_with_it() -> None:
    """One finished match must cost one offer, not the whole day's coupon.

    Fails on the old code for the right reason: the gate asked whether the
    "odds" key existed, Superbet sends the key with a null value, and ``for
    item in None`` raised TypeError on the first fixture of the artifact —
    before reaching any match that still had a price.
    """
    from bet.sofa.offer import OfferFetcher

    class Client:
        def event_odds(self, event_id: str):  # type: ignore[no-untyped-def]
            if event_id == "dead":
                return {"odds": None}  # the dominant shape: 68 of 69 fixtures
            return {
                "odds": [
                    {
                        "marketName": "Liczba goli",
                        "specialBetValue": "2.5",
                        "name": "powyżej",
                        "price": 1.85,
                    },
                    {
                        "marketName": "Liczba goli",
                        "specialBetValue": "2.5",
                        "name": "poniżej",
                        "price": 1.95,
                    },
                ]
            }

    offers = OfferFetcher(Client()).fetch_offers(
        [_fixture(1, ["dead"]), _fixture(2, ["live"])]
    )

    assert len(offers) == 2
    assert offers[0].status == "NO_PRICE"
    assert offers[0].rungs == [], "an unpriced match is zero rungs, not an exception"
    assert offers[1].status == "PRICED"
    assert len(offers[1].rungs) == 1, "the rest of the board must still be priced"
    assert offers[1].rungs[0].over_odds == 1.85


def test_f32_the_gate_is_one_function_shared_by_offer_and_samples() -> None:
    """The defect was two copies of one intention, only one of them correct.

    Fails on the old code for the right reason: offer.py had its own inline
    gate, spelled differently from the correct one in samples.py.
    """
    from bet.sofa import offer, samples
    from bet.sofa.superbet import odds_items

    assert offer.odds_items is odds_items
    assert samples.odds_items is odds_items

    # And the function itself covers every shape Superbet actually sends.
    assert odds_items(None) == []
    assert odds_items({}) == []
    assert odds_items({"odds": None}) == []
    assert odds_items({"odds": []}) == []
    assert odds_items({"marketName": "x"}) == []  # key absent
    assert odds_items({"odds": [{"marketName": "x"}]}) == [{"marketName": "x"}]


# --------------------------------------------------------------------------
# F29 — one letter with no NFD decomposition killed eight mappings
# --------------------------------------------------------------------------

import pytest  # noqa: E402


@pytest.mark.parametrize(
    ("market_name", "expected"),
    [
        # The eight mappings that could not be reached at all.
        ("1.połowa - liczba goli", ("goals_1h_total", "")),
        ("2.połowa - liczba goli", ("goals_2h_total", "")),
        ("Liczba strzałów", ("shots_total", "")),
        ("Liczba celnych strzałów", ("shots_on_target_total", "")),
        ("Liczba podwójnych błędów", ("double_faults_total", "")),
        ("Liczba strzałów Wolfsburg", ("shots_for", "wolfsburg")),
        ("Liczba celnych strzałów - Wolfsburg", ("shots_on_target_for", "wolfsburg")),
        ("Djokovic liczba podwójnych błędów", ("double_faults_for", "djokovic")),
        # Per-team halves: the metrics existed in FOOTBALL_METRICS with no
        # pattern that could produce them.
        (
            "1.połowa - Hapoel Tel Aviv - liczba goli",
            ("goals_1h_for", "hapoel tel aviv"),
        ),
        ("2. połowa - Wolfsburg - liczba goli", ("goals_2h_for", "wolfsburg")),
        # Unchanged, so the half patterns cannot have stolen the whole-match one.
        ("Liczba goli", ("goals_total", "")),
        ("Hapoel Tel Aviv - liczba goli", ("goals_for", "hapoel tel aviv")),
    ],
)
def test_f29_market_names_with_l_stroke_classify(
    market_name: str, expected: tuple[str, str]
) -> None:
    """Fails on the old code for the right reason: eight of these returned None
    or, worse, routed a half-time line to the whole-match metric."""
    from bet.sofa.market_mapper import classify_market

    assert classify_market(market_name) == expected


def test_f29_fold_removes_the_letters_nfd_cannot_decompose() -> None:
    from bet.sofa.market_mapper import fold

    assert fold("połowa") == "polowa"
    assert fold("strzałów") == "strzalow"
    assert fold("błędów") == "bledow"
    assert fold("Đorđević") == "dordevic"
    assert fold("Ødegaard") == "odegaard"
    assert fold("Işık") == "isik"
    # The ones that already worked must keep working.
    assert fold("ŁKS Łomża") == "lks lomza"
    assert fold("Świt Skolwin") == "swit skolwin"


def test_f29_determine_side_refuses_a_subject_that_is_really_a_market_scope() -> None:
    """The threshold leaked on long team names; this is the last line of defence.

    Fails on the old code for the right reason: "1.połowa - Hapoel Tel Aviv"
    scored 73.2 against a threshold of 70 and was attributed to side_a, so a
    half-time line was priced off a whole-match sample. Whether a row leaked
    depended on how long the club's name was — 678 of 1160 combinations did.
    """
    sys.path.insert(0, str(REPO / "scripts"))
    from scripts.sofa.run_sheet import determine_side

    fixture = _fixture(1, ["x"])
    fixture.home_name = "Hapoel Tel Aviv"
    fixture.away_name = "Maccabi Haifa"

    assert determine_side("1.połowa - Hapoel Tel Aviv", fixture) is None
    assert determine_side("2. połowa - Hapoel Tel Aviv", fixture) is None
    assert (
        determine_side("1.połowa - ACS Academia de Fotbal Viitorul Cluj", fixture)
        is None
    )
    # A real team name still resolves, so the guard is not a blanket refusal.
    assert determine_side("Hapoel Tel Aviv", fixture) == "side_a"
    assert determine_side("Maccabi Haifa", fixture) == "side_b"


# --------------------------------------------------------------------------
# F25 — the men's fixture that matched a women's match, CONFIRMED
# --------------------------------------------------------------------------


def _gnistan_womens_event() -> dict:  # type: ignore[type-arg]
    """Sofascore 16681087, as the artifact recorded it: 09-19 15:00, sides reversed."""
    return {
        "id": 16681087,
        "startTimestamp": 1789830000,  # 2026-09-19T15:00:00Z
        "homeTeam": {"name": "HJK Helsinki"},
        "awayTeam": {"name": "IF Gnistan"},
        "tournament": {
            "name": "Kansallinen Liiga, Women, Championship group",
            "category": {"name": "Finland"},
            "uniqueTournament": {"name": "Kansallinen Liiga, Women"},
        },
    }


def _gnistan_mens_event() -> dict:  # type: ignore[type-arg]
    """The fixture Superbet actually listed: men's, same day, same orientation."""
    return {
        "id": 16681000,
        "startTimestamp": 1789740000,  # 2026-09-18T14:00:00Z
        "homeTeam": {"name": "IF Gnistan"},
        "awayTeam": {"name": "HJK Helsinki"},
        "tournament": {
            "name": "Veikkausliiga",
            "category": {"name": "Finland"},
            "uniqueTournament": {"name": "Veikkausliiga"},
        },
    }


def _resolver():  # type: ignore[no-untyped-def]
    from bet.sofa.config import SofaConfig
    from bet.sofa.resolve import SofaResolver

    return SofaResolver(SofaConfig(), None, None)  # type: ignore[arg-type]


def test_f25_a_womens_match_does_not_match_a_mens_fixture(tmp_path: Path) -> None:
    """The exact case from the artifact must not resolve at all.

    Fails on the old code for the right reason: kickoff (23 h, inside ±24 h)
    and opponent ("hjk helsinki" exact, both clubs field both sides) were the
    only two conditions, and both passed — the row was written CONFIRMED.
    """
    from datetime import UTC, datetime

    kickoff = datetime(2026, 9, 18, 16, 0, tzinfo=UTC)  # Superbet's time
    quality = _resolver().match_quality(
        _gnistan_womens_event(),
        kickoff,
        "hjk helsinki",
        sport="football",
        superbet_side_a="IF Gnistan",
        superbet_side_b="HJK Helsinki",
    )
    assert quality is None, "a women's match was accepted for a men's fixture"


def test_f25_the_real_mens_fixture_still_resolves() -> None:
    """The gates must not be a blanket refusal — 285 men's fixtures agreed."""
    from datetime import UTC, datetime

    kickoff = datetime(2026, 9, 18, 16, 0, tzinfo=UTC)
    quality = _resolver().match_quality(
        _gnistan_mens_event(),
        kickoff,
        "hjk helsinki",
        sport="football",
        superbet_side_a="IF Gnistan",
        superbet_side_b="HJK Helsinki",
    )
    assert quality is not None and quality > 99.0


def test_f25_a_womens_fixture_matches_a_womens_match() -> None:
    """Superbet's (K) marker and a Women competition agree: 4 such fixtures."""
    from datetime import UTC, datetime

    event = _gnistan_womens_event()
    event["homeTeam"], event["awayTeam"] = event["awayTeam"], event["homeTeam"]
    quality = _resolver().match_quality(
        event,
        datetime(2026, 9, 19, 15, 0, tzinfo=UTC),
        "hjk helsinki",
        sport="football",
        superbet_side_a="IF Gnistan (K)",
        superbet_side_b="HJK Helsinki (K)",
    )
    assert quality is not None


def test_f25_reversed_sides_are_refused_even_when_gender_agrees() -> None:
    """The orientation gate has value of its own: per-team markets are positional.

    Fails on the old code for the right reason: nothing checked orientation, so
    a reversed event was accepted and every `*_for` market on it would have
    been priced off the other team's sample.
    """
    from datetime import UTC, datetime

    event = _gnistan_mens_event()
    event["homeTeam"], event["awayTeam"] = event["awayTeam"], event["homeTeam"]
    quality = _resolver().match_quality(
        event,
        datetime(2026, 9, 18, 16, 0, tzinfo=UTC),
        "hjk helsinki",
        sport="football",
        superbet_side_a="IF Gnistan",
        superbet_side_b="HJK Helsinki",
    )
    assert quality is None


def test_f25_the_match_window_is_per_sport_not_cut_globally() -> None:
    """Cutting ±24 h globally would close F25 and open a bigger hole (F26).

    Tennis ITF kickoffs disagree by a whole timezone, legally and in bulk, so
    the wide window has to stay there.
    """
    from datetime import UTC, datetime

    from bet.sofa.resolve import MATCH_WINDOW_S

    assert MATCH_WINDOW_S["football"] == 6 * 3600
    assert MATCH_WINDOW_S["tennis"] == 24 * 3600

    resolver = _resolver()
    # A nine-hour disagreement: routine for ITF, impossible for football.
    itf = {
        "id": 1,
        "startTimestamp": 1789725600,  # 2026-09-18T10:00:00Z
        "homeTeam": {"name": "Yidi Yang"},
        "awayTeam": {"name": "Sijia Wei"},
        "tournament": {"name": "ITF W35 Kyoto", "category": {"name": "Japan"}},
    }
    superbet_time = datetime(2026, 9, 18, 1, 4, tzinfo=UTC)
    assert (
        resolver.match_quality(itf, superbet_time, "sijia wei", sport="tennis")
        is not None
    )

    football = dict(itf)
    football["tournament"] = {"name": "Veikkausliiga", "category": {"name": "Finland"}}
    assert (
        resolver.match_quality(football, superbet_time, "sijia wei", sport="football")
        is None
    )


def test_f25_gender_is_read_from_the_competition_not_the_team_name() -> None:
    """Entity 296052 is called "IF Gnistan" and plays only women's football.

    This is the assumption F9 got wrong, and the reason a team-name suffix
    cannot be the fix.
    """
    from bet.sofa.resolve import sofascore_gender, superbet_gender

    assert sofascore_gender(_gnistan_womens_event()) == "W"
    assert sofascore_gender(_gnistan_mens_event()) == "M"
    # The team name carries nothing: same name, both genders.
    assert _gnistan_womens_event()["awayTeam"]["name"] == "IF Gnistan"
    assert _gnistan_mens_event()["homeTeam"]["name"] == "IF Gnistan"

    assert superbet_gender("Millonarios (K)") == "W"
    assert superbet_gender("Arsenal (W)") == "W"
    assert superbet_gender("Arsenal") == "M"


# --------------------------------------------------------------------------
# F16 — Superbet's (K) and Sofascore's (W) could never be equal
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "polish",
    ["Millonarios (K)", "LD Alajuelense (K)", "Azzurri United FC (K)", "Moravia (K)"],
)
def test_f16_polish_and_english_gender_markers_produce_one_key(polish: str) -> None:
    """Fails on the old code for the right reason: " (k)" became " w" without
    brackets while "(W)" kept them, so the keys could never be equal — 47 of
    the 54 marked names on the board went to sofa_entity_miss."""
    from bet.sofa.names import normalize_name

    english = polish.replace("(K)", "(W)")
    assert normalize_name(polish) == normalize_name(english)
    assert normalize_name(polish).endswith(" (w)")


@pytest.mark.parametrize(
    ("womens", "mens"),
    [
        ("Millonarios (K)", "Millonarios"),
        ("Arsenal (W)", "Arsenal"),
        ("Chelsea Women", "Chelsea"),
        ("HJK Helsinki Kobiety", "HJK Helsinki"),
    ],
)
def test_f16_a_womens_team_never_shares_a_key_with_the_mens_team(
    womens: str, mens: str
) -> None:
    """The marker stays in the key on purpose: two teams, one club name.

    This is what closes the residual risk F25 leaves — a men's and a women's
    side cannot share a cached entity even if their kickoffs agree.
    """
    from bet.sofa.names import normalize_name

    assert normalize_name(womens) != normalize_name(mens)


def test_f16_every_marker_spelling_collapses_to_the_same_form() -> None:
    from bet.sofa.names import is_womens_name, normalize_name

    forms = [
        "Arsenal (K)",
        "Arsenal (W)",
        "Arsenal (F)",
        "Arsenal Women",
        "Arsenal Kobiety",
    ]
    assert {normalize_name(f) for f in forms} == {"arsenal (w)"}
    assert all(is_womens_name(f) for f in forms)
    assert not is_womens_name("Arsenal")


def test_f16_the_marker_does_not_eat_a_club_whose_name_contains_the_word() -> None:
    """Anchored at the end because it is a suffix, not a word to hunt for."""
    from bet.sofa.names import normalize_name

    assert normalize_name("Women's United FC") == "women's united fc"
    # And the reserves marker still works next to it.
    assert normalize_name("Boca Juniors II") == "boca juniors (r)"


# --------------------------------------------------------------------------
# F28 — the shot identity omitted the woodwork, and rejected directionally
# --------------------------------------------------------------------------


def _shot_stats(
    total: tuple[float, float],
    on: tuple[float, float],
    off: tuple[float, float],
    blocked: tuple[float, float],
    woodwork: tuple[float, float],
):  # type: ignore[no-untyped-def]
    return {
        "ALL": {
            "totalShotsOnGoal": total,
            "shotsOnGoal": on,
            "shotsOffGoal": off,
            "blockedScoringAttempt": blocked,
            "hitWoodwork": woodwork,
        }
    }


def test_f28_a_woodwork_shot_does_not_block_the_match() -> None:
    """Real payload, event 13531730: away side 8 = 3 + 3 + 1, plus 1 off the post.

    Fails on the old code for the right reason: the sum omitted hitWoodwork, so
    a perfectly transcribed match was thrown out — and with it that match's
    corners, cards, fouls and offsides, since one failed shot count blocks
    every metric of the fixture.
    """
    from bet.sofa.metrics import check_identities

    stats = _shot_stats((8.0, 8.0), (5.0, 3.0), (1.0, 3.0), (2.0, 1.0), (0.0, 1.0))
    assert check_identities(stats, None, {}, "football") is None


def test_f28_a_real_transcription_error_is_still_blocked() -> None:
    """Real payload, event 14195525: home side 10 != 2 + 4 + 3, woodwork 0.

    This is the 1.4% the gate exists for, and it must keep firing.
    """
    from bet.sofa.contracts import GapReason
    from bet.sofa.metrics import check_identities

    stats = _shot_stats((10.0, 24.0), (2.0, 12.0), (4.0, 10.0), (3.0, 2.0), (0.0, 0.0))
    assert (
        check_identities(stats, None, {}, "football") == GapReason.INTERNAL_INCONSISTENT
    )


def test_f28_the_obvious_repair_would_have_been_wrong() -> None:
    """Sofascore is inconsistent about double-counting the woodwork.

    Adding hitWoodwork to the sum outright leaves matches with *negative*
    residuals blocked — there the post is already inside one of the three
    categories. Both conventions have to pass, which is why the rule is a
    bound and not an equality.
    """
    from bet.sofa.metrics import check_identities

    # Convention A: the woodwork shot is extra. base = 7, total = 8, wood = 1.
    assert (
        check_identities(
            _shot_stats((8.0, 8.0), (3.0, 3.0), (3.0, 3.0), (1.0, 1.0), (1.0, 1.0)),
            None,
            {},
            "football",
        )
        is None
    )
    # Convention B: it is already counted. base = 8, total = 8, wood = 1.
    # "base + hitWoodwork == total" would reject this one.
    assert (
        check_identities(
            _shot_stats((8.0, 8.0), (4.0, 4.0), (3.0, 3.0), (1.0, 1.0), (1.0, 1.0)),
            None,
            {},
            "football",
        )
        is None
    )


def test_f28_a_discrepancy_larger_than_the_woodwork_count_still_blocks() -> None:
    """The bound is the woodwork count, not a free pass."""
    from bet.sofa.contracts import GapReason
    from bet.sofa.metrics import check_identities

    # base = 5, total = 8, only 1 woodwork shot to explain a gap of 3.
    assert (
        check_identities(
            _shot_stats((8.0, 8.0), (2.0, 2.0), (2.0, 2.0), (1.0, 1.0), (1.0, 1.0)),
            None,
            {},
            "football",
        )
        == GapReason.INTERNAL_INCONSISTENT
    )


def test_f28_a_payload_without_the_woodwork_key_keeps_the_exact_identity() -> None:
    """Absent means zero tolerance, not unlimited tolerance."""
    from bet.sofa.contracts import GapReason
    from bet.sofa.metrics import check_identities

    stats = _shot_stats((8.0, 8.0), (3.0, 3.0), (3.0, 3.0), (1.0, 1.0), (0.0, 0.0))
    del stats["ALL"]["hitWoodwork"]
    assert (
        check_identities(stats, None, {}, "football") == GapReason.INTERNAL_INCONSISTENT
    )


# --------------------------------------------------------------------------
# F30 — the Poisson floor, and the normal CDF, on a variable with two values
# --------------------------------------------------------------------------


def test_f30_the_poisson_floor_does_not_apply_to_sets_total() -> None:
    """Fails on the old code for the right reason: predictive_sd returned 1.586
    for a sample whose real sd is 0.475, inflating it 3.34x."""
    import statistics

    from bet.sofa.engine import predictive_sd

    values = [2.0] * 626 + [3.0] * 252  # the finding's measured distribution
    mean = statistics.mean(values)
    variance = statistics.variance(values)

    floored = predictive_sd(variance, mean, 10, apply_poisson_floor=True)
    honest = predictive_sd(variance, mean, 10, apply_poisson_floor=False)
    assert floored > 1.5, "this is the old behaviour, kept reachable on purpose"
    assert honest < 0.5, f"sets_total sd must stay near the sample's own, got {honest}"
    assert floored / honest > 3.0


def test_f30_the_floor_still_applies_to_the_26_metrics_that_justify_it() -> None:
    """It never binds for them anyway — counts are overdispersed — but removing
    it wholesale would drop a real guard against an over-tight sample."""
    from bet.sofa.engine import uses_poisson_floor

    for market in (
        "goals_total",
        "corners_total",
        "cards_points_total",
        "fouls_total",
        "shots_total",
        "aces_total",
        "games_total",
        "offsides_total",
    ):
        assert uses_poisson_floor(market), market
    for market in ("sets_total", "tiebreaks_total", "xg_total", "xg_for"):
        assert not uses_poisson_floor(market), market


def test_f30_sets_total_is_priced_from_the_samples_own_frequency() -> None:
    """The remaining 4 pp are the normal CDF, not its width.

    Integrating a bell curve over a variable with two bars is wrong whatever
    sd you give it. Fails on the old code for the right reason: p_central for
    OVER 2.5 came out 0.4466 against an empirical truth of 0.2870, so the model
    accepted 2.46 where the honest bar is 3.83.
    """
    from bet.sofa.engine import p_empirical, uses_empirical_frequency

    assert uses_empirical_frequency("sets_total")
    assert not uses_empirical_frequency("goals_total")

    # 252 of 878 matches went to a third set.
    assert abs(p_empirical(252, 878) - 0.2870) < 0.001
    # Required odds at a 10% margin: 3.83, not 2.46.
    assert abs(1.10 / p_empirical(252, 878) - 3.83) < 0.01


def test_f30_the_empirical_estimator_is_clamped_like_the_cdf() -> None:
    """A unanimous sample of ten is not certainty."""
    from bet.sofa.engine import p_empirical

    assert p_empirical(10, 10) == 0.95
    assert p_empirical(0, 10) == 0.05
    assert p_empirical(3, 10) == 0.3


def test_f30_sheet_and_settle_share_one_estimator_policy() -> None:
    """A backtest measuring a different estimator than the one that ships
    measures nothing. Both read the policy from engine.py."""
    import inspect

    from bet.sofa import settle

    sys.path.insert(0, str(REPO / "scripts"))
    from scripts.sofa import run_sheet

    for module in (settle, run_sheet):
        source = inspect.getsource(module)
        assert "uses_poisson_floor" in source, module.__name__
        assert "uses_empirical_frequency" in source, module.__name__


# --------------------------------------------------------------------------
# F21 — the retry has been unreachable since the bridge became the transport
# --------------------------------------------------------------------------


def test_f21_a_transport_failure_is_retried_once(tmp_path: Path) -> None:
    """Fails on the old code for the right reason: the retry caught only
    curl_cffi's RequestsError, which the bridge never raises, so the bridge's
    failure fell to the catch-all and was re-raised on the first attempt.
    Measured in the log as 30.3 s between rows instead of ~61 s."""
    from bet.sofa.client import SofascoreClient
    from bet.sofa.config import SofaConfig
    from bet.sofa.errors import TransportError
    from tests.sofa.test_client import MockResponse

    class FlakyTransport:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, url: str, timeout: float = 10.0):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                raise TransportError("bridge HTTP 504: bridge timeout")
            return MockResponse(200, {"ok": 1})

    transport = FlakyTransport()
    client = SofascoreClient(
        SofaConfig(runs_dir=str(tmp_path), target_rps=1000), transport
    )
    import bet.sofa.client as client_module

    original_sleep = client_module.time.sleep
    client_module.time.sleep = lambda _s: None  # type: ignore[assignment]
    try:
        data = client.event_statistics(1)
    finally:
        client_module.time.sleep = original_sleep

    assert data == {"ok": 1}, "the retry must return the second attempt's data"
    assert transport.calls == 2, "exactly one retry, not zero and not a storm"


def test_f21_a_transport_failure_that_repeats_becomes_a_provider_error(
    tmp_path: Path,
) -> None:
    from bet.sofa.client import SofascoreClient
    from bet.sofa.config import SofaConfig
    from bet.sofa.errors import ProviderError, TransportError

    class DeadTransport:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, url: str, timeout: float = 10.0):  # type: ignore[no-untyped-def]
            self.calls += 1
            raise TransportError("bridge unreachable")

    transport = DeadTransport()
    client = SofascoreClient(
        SofaConfig(runs_dir=str(tmp_path), target_rps=1000), transport
    )
    import bet.sofa.client as client_module

    original_sleep = client_module.time.sleep
    client_module.time.sleep = lambda _s: None  # type: ignore[assignment]
    try:
        with pytest.raises(ProviderError):
            client.event_statistics(1)
    finally:
        client_module.time.sleep = original_sleep

    assert transport.calls == 2


def test_f21_a_semantic_provider_error_is_not_retried(tmp_path: Path) -> None:
    """403 is an answer, not a failed delivery. Asking again immediately is
    how a rate limit becomes a ban."""
    from bet.sofa.client import SofascoreClient
    from bet.sofa.config import SofaConfig
    from bet.sofa.errors import ProviderError
    from tests.sofa.test_client import MockResponse

    class ForbiddenTransport:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, url: str, timeout: float = 10.0):  # type: ignore[no-untyped-def]
            self.calls += 1
            return MockResponse(403, {})

    transport = ForbiddenTransport()
    client = SofascoreClient(
        SofaConfig(runs_dir=str(tmp_path), target_rps=1000), transport
    )
    with pytest.raises(ProviderError):
        client.event_statistics(1)
    assert transport.calls == 1, "a 403 must not be retried"


def test_f21_the_bridge_raises_transport_error_not_provider_error() -> None:
    """The bridge is the only working transport; if it raises the wrong class
    the retry goes dead again silently."""
    import inspect

    from bet.sofa import bridge_transport
    from bet.sofa.errors import SofaError, TransportError

    assert issubclass(TransportError, SofaError)
    source = inspect.getsource(bridge_transport.BrowserBridgeTransport.get)
    assert "TransportError" in source
    assert "raise ProviderError" not in source, (
        "a delivery failure raised as ProviderError is unreachable by the retry"
    )


def test_f21_the_real_bridge_transports_failure_is_retried_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The behavioural proof, with the actual transport the pipeline uses.

    Fails on the old code for the right reason, and not because a name is
    missing: the bridge raised ProviderError, ``_execute``'s retry branch only
    caught curl_cffi's RequestsError, so the failure went to the catch-all and
    the request was attempted exactly once. Here it must be attempted twice.
    """
    from urllib.error import URLError

    import bet.sofa.bridge_transport as bt
    import bet.sofa.client as client_module
    from bet.sofa.client import SofascoreClient
    from bet.sofa.config import SofaConfig
    from bet.sofa.errors import ProviderError

    attempts = {"n": 0}

    def dead_urlopen(*args: object, **kwargs: object) -> object:
        attempts["n"] += 1
        raise URLError("connection refused")

    monkeypatch.setattr(bt, "urlopen", dead_urlopen)
    monkeypatch.setattr(client_module.time, "sleep", lambda _s: None)

    client = SofascoreClient(
        SofaConfig(runs_dir=str(tmp_path), target_rps=1000),
        bt.BrowserBridgeTransport("http://127.0.0.1:1"),
    )
    with pytest.raises(ProviderError):
        client.event_statistics(1)

    assert attempts["n"] == 2, (
        f"the bridge's failure was attempted {attempts['n']} time(s); "
        "the retry has been dead since 2026-09-17"
    )


# --------------------------------------------------------------------------
# F17 — a 404 does not look like a cost in the log, so nobody counted it
# --------------------------------------------------------------------------


class _CountingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, int]] = []

    def entity_events(self, entity_id: int, kind: str, page: int):  # type: ignore[no-untyped-def]
        self.calls.append((entity_id, kind, page))
        return None  # 404


def test_f17_a_404_listing_is_not_rediscovered_within_the_ttl(tmp_path: Path) -> None:
    """Fails on the old code for the right reason: only non-empty responses were
    cached, so a 404 was paid for again every time — 242 of RESOLVE's ~870
    requests, 225 of them already known from the previous run."""
    from bet.sofa.cache import SofaCache
    from bet.sofa.config import SofaConfig
    from bet.sofa.resolve import SofaResolver

    config = SofaConfig(db_path=str(tmp_path / "t.db"))
    client = _CountingClient()
    resolver = SofaResolver(config, client, SofaCache(config))  # type: ignore[arg-type]

    resolver._fetch_events(42, "football")
    first = len(client.calls)
    assert first >= 1

    resolver._fetch_events(42, "football")
    assert len(client.calls) == first, (
        "the same absence was rediscovered; this is the 28% of the budget"
    )


def test_f17_the_negative_cache_expires_so_it_cannot_become_a_silent_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remembering a 404 forever trades waste for missing data, which is worse.

    A team with no upcoming match today has one next week.
    """
    from datetime import timedelta

    import bet.sofa.cache as cache_module
    from bet.sofa.cache import SofaCache
    from bet.sofa.config import SofaConfig
    from bet.sofa.resolve import SofaResolver
    from bet.sofa.timeutil import now as real_now

    config = SofaConfig(db_path=str(tmp_path / "t.db"), listing_miss_ttl_min=720)
    client = _CountingClient()
    resolver = SofaResolver(config, client, SofaCache(config))  # type: ignore[arg-type]

    resolver._fetch_events(42, "football")
    first = len(client.calls)
    resolver._fetch_events(42, "football")
    assert len(client.calls) == first

    base = real_now()
    monkeypatch.setattr(cache_module, "now", lambda: base + timedelta(minutes=721))
    resolver._fetch_events(42, "football")
    assert len(client.calls) > first, "after the TTL we must ask again"


def test_f17_tennis_never_asks_for_a_route_that_does_not_exist(tmp_path: Path) -> None:
    """team/{id}/events/next/ 404s for every tennis entity: 179 of 179.

    Fails on the old code for the right reason: _fetch_events iterated
    ("next", "last") regardless of sport, so every tennis entity bought one
    guaranteed failure — 179 requests, about 1.5 minutes at 2 req/s.
    """
    from bet.sofa.cache import SofaCache
    from bet.sofa.config import SofaConfig
    from bet.sofa.resolve import SofaResolver

    config = SofaConfig(db_path=str(tmp_path / "t.db"))
    client = _CountingClient()
    resolver = SofaResolver(config, client, SofaCache(config))  # type: ignore[arg-type]

    resolver._fetch_events(42, "tennis")
    assert client.calls, "tennis must still fetch something"
    assert all(kind == "last" for _, kind, _ in client.calls), (
        f"tennis asked for a route that does not exist: {client.calls}"
    )

    client.calls.clear()
    resolver._fetch_events(43, "football")
    assert any(kind == "next" for _, kind, _ in client.calls), (
        "football's next listing works (48 of 53 returned 200) and is kept"
    )


# --------------------------------------------------------------------------
# F26 — the coupon's time gate was fed by the wrong clock
# --------------------------------------------------------------------------


def _sheet_row(event_id: int, odds: float = 2.50):  # type: ignore[no-untyped-def]
    from bet.sofa.contracts import SheetRow

    return SheetRow(
        sofascore_event_id=event_id,
        sport="tennis",
        market="games_total",
        subject="",
        line=20.5,
        direction="OVER",
        sample_size=10,
        sample_mean=21.0,
        sample_sd=2.0,
        centre=21.0,
        p_central=0.60,
        market_p=0.50,
        ladder_centre=21.0,
        ladder_sigma=0.1,
        p_bar=0.58,
        bar_reason=None,
        required_odds=1.90,
        offered_odds=odds,
        edge=0.10,
        surplus=0.60,
        verdict="VALUE",
        notes=[],
    )


def test_f26_a_match_superbet_says_has_started_cannot_reach_the_coupon() -> None:
    """Fails on the old code for the right reason: the gate read Sofascore's
    kickoff, which for ITF runs 7-9 h late, so a finished match looked
    upcoming. Six fixtures on 2026-09-18 would have passed with the result
    already known; only the bookmaker delisting them prevented it, which does
    nothing for a match being played live and still priced."""
    from datetime import UTC, datetime, timedelta

    from bet.sofa.coupon import build_coupon

    fixture = _fixture(1, ["x"])
    fixture.sport = "tennis"
    # Yidi Yang vs Sijia Wei: really 02:30, Sofascore said 10:30.
    fixture.superbet_kickoff_utc = datetime(2026, 9, 18, 2, 30, tzinfo=UTC)
    fixture.kickoff_utc = datetime(2026, 9, 18, 10, 30, tzinfo=UTC)
    fixture.kickoff_disagreement_h = 8.0

    now = datetime(2026, 9, 18, 4, 0, tzinfo=UTC)
    result = build_coupon(
        [_sheet_row(1)],
        [fixture],
        [],
        [],
        now,
        now + timedelta(minutes=15),
        timedelta(minutes=45),
    )
    assert not result.coupon.singles, "a started match reached the coupon"
    reasons = [d.reason for d in result.dropped]
    assert "KICKOFF_TOO_SOON" in reasons
    detail = next(d.detail for d in result.dropped if d.reason == "KICKOFF_TOO_SOON")
    assert "disagree by 8.0 h" in (detail or ""), (
        "the disagreement must leave a trace, not vanish"
    )


def test_f26_a_fixture_both_sources_agree_is_upcoming_still_passes() -> None:
    from datetime import UTC, datetime, timedelta

    from bet.sofa.coupon import build_coupon

    fixture = _fixture(1, ["x"])
    fixture.superbet_kickoff_utc = datetime(2026, 9, 18, 18, 0, tzinfo=UTC)
    fixture.kickoff_utc = datetime(2026, 9, 18, 18, 0, tzinfo=UTC)
    fixture.kickoff_disagreement_h = 0.0

    now = datetime(2026, 9, 18, 10, 0, tzinfo=UTC)
    from bet.sofa.contracts import FixtureOffer, PricedRung

    offer = FixtureOffer(
        sofascore_event_id=1,
        status="PRICED",
        rungs=[
            PricedRung(
                market="games_total",
                subject="",
                line=20.5,
                over_odds=2.50,
                under_odds=1.55,
                fetched_at_utc=now,
            )
        ],
        unmapped_markets=[],
    )
    result = build_coupon(
        [_sheet_row(1)],
        [fixture],
        [offer],
        [],
        now,
        now + timedelta(minutes=15),
        timedelta(minutes=45),
    )
    assert len(result.coupon.singles) == 1, [
        (d.reason, d.detail) for d in result.dropped
    ]


def test_f26_the_disagreement_is_recorded_on_the_fixture() -> None:
    """A disagreement between sources must leave a trace, not disappear.

    Fails on the old code for the right reason: the field did not exist and a
    23-hour disagreement passed without a mark.
    """
    from datetime import UTC, datetime

    from bet.sofa.resolve import parse_fixture

    event = {
        "id": 1,
        "startTimestamp": int(datetime(2026, 9, 18, 10, 0, tzinfo=UTC).timestamp()),
        "homeTeam": {"name": "Yidi Yang", "id": 1},
        "awayTeam": {"name": "Sijia Wei", "id": 2},
        "tournament": {"name": "ITF W35 Kyoto", "category": {"name": "Japan"}},
        "season": {"id": 1},
    }

    class NoClient:
        def event(self, _id: int) -> None:
            return None

    fixture = parse_fixture(
        event,
        "tennis",
        ["1"],
        NoClient(),  # type: ignore[arg-type]
        superbet_kickoff_utc=datetime(2026, 9, 18, 1, 4, tzinfo=UTC),
    )
    assert fixture.kickoff_disagreement_h is not None
    assert abs(fixture.kickoff_disagreement_h - 8.93) < 0.05
    assert fixture.superbet_kickoff_utc == datetime(2026, 9, 18, 1, 4, tzinfo=UTC)


# --------------------------------------------------------------------------
# F27 — two listings of one match, and the price decided by arrival order
# --------------------------------------------------------------------------


def test_f27_a_price_collision_is_resolved_not_overwritten() -> None:
    """Fails on the old code for the right reason: the second listing's price
    was assigned over the first with no comparison and no trace, so which
    number reached the coupon depended on the order of superbet_event_ids."""
    from bet.sofa.offer import OfferFetcher

    prices = {"a": 1.80, "b": 1.95}

    class TwoListings:
        def event_odds(self, event_id: str):  # type: ignore[no-untyped-def]
            return {
                "odds": [
                    {
                        "marketName": "Liczba goli",
                        "specialBetValue": "2.5",
                        "name": "powyżej",
                        "price": prices[event_id],
                    },
                    {
                        "marketName": "Liczba goli",
                        "specialBetValue": "2.5",
                        "name": "poniżej",
                        "price": 2.00,
                    },
                ]
            }

    offers = OfferFetcher(TwoListings()).fetch_offers([_fixture(1, ["a", "b"])])
    rung = offers[0].rungs[0]

    assert rung.over_odds == 1.80, "the conservative quote, not the last one seen"
    assert offers[0].price_collisions, "the disagreement must be recorded"
    assert "1.8 vs 1.95" in offers[0].price_collisions[0]


def test_f27_the_outcome_does_not_depend_on_the_order_of_the_listings() -> None:
    """This is the actual defect: a coin flip on the only number that matters."""
    from bet.sofa.offer import OfferFetcher

    prices = {"a": 1.80, "b": 1.95}

    class TwoListings:
        def event_odds(self, event_id: str):  # type: ignore[no-untyped-def]
            return {
                "odds": [
                    {
                        "marketName": "Liczba goli",
                        "specialBetValue": "2.5",
                        "name": "powyżej",
                        "price": prices[event_id],
                    }
                ]
            }

    forward = OfferFetcher(TwoListings()).fetch_offers([_fixture(1, ["a", "b"])])
    backward = OfferFetcher(TwoListings()).fetch_offers([_fixture(1, ["b", "a"])])
    assert forward[0].rungs[0].over_odds == backward[0].rungs[0].over_odds == 1.80


def test_f27_the_union_of_two_listings_is_still_taken() -> None:
    """Merging by union is right and recovers a listing that is still live.

    Only the collision was the problem, so this must not regress: 20 fixtures
    carried two ids, and one pair was 0 priced markets against 8.
    """
    from bet.sofa.offer import OfferFetcher

    class Complementary:
        def event_odds(self, event_id: str):  # type: ignore[no-untyped-def]
            if event_id == "dead":
                return {"odds": None}
            return {
                "odds": [
                    {
                        "marketName": "Liczba goli",
                        "specialBetValue": "2.5",
                        "name": "powyżej",
                        "price": 1.85,
                    },
                    {
                        "marketName": "Liczba rzutów rożnych",
                        "specialBetValue": "9.5",
                        "name": "poniżej",
                        "price": 1.90,
                    },
                ]
            }

    offers = OfferFetcher(Complementary()).fetch_offers([_fixture(1, ["dead", "live"])])
    assert {r.market for r in offers[0].rungs} == {"goals_total", "corners_total"}
    assert not offers[0].price_collisions


# --------------------------------------------------------------------------
# F24 — the bridge threw away the headers that answer "are we being throttled"
# --------------------------------------------------------------------------


def test_f24_a_retry_after_header_reaches_the_log_row(tmp_path: Path) -> None:
    """Fails on the old code for the right reason: there was nowhere to put it.

    When latency jumped 13x the only source that could have answered directly
    was discarded, so the diagnosis went via ping and load average instead.
    """
    from bet.sofa.client import SofascoreClient
    from bet.sofa.config import SofaConfig
    from bet.sofa.stage import stage

    class HeaderResponse:
        status_code = 200
        headers = {
            "retry-after": "30",
            "x-ratelimit-remaining": "4",
            "server-timing": "cdn-cache; desc=HIT",
            "set-cookie": "should-not-be-logged",
        }

        def json(self) -> dict[str, int]:
            return {"ok": 1}

    class HeaderTransport:
        def get(self, url: str, timeout: float = 10.0) -> HeaderResponse:
            return HeaderResponse()

    client = SofascoreClient(
        SofaConfig(runs_dir=str(tmp_path), target_rps=1000), HeaderTransport()
    )
    with stage("SAMPLES"):
        client.event_statistics(1)

    row = json.loads(client.log_path.read_text(encoding="utf-8").splitlines()[0])
    assert row["headers"]["retry-after"] == "30"
    assert row["headers"]["x-ratelimit-remaining"] == "4"
    assert "set-cookie" not in row["headers"], "only the diagnostic ones"


def test_f24_a_429_carries_its_headers_too(tmp_path: Path) -> None:
    """The case the headers exist for."""
    from bet.sofa.client import SofascoreClient
    from bet.sofa.config import SofaConfig
    from bet.sofa.errors import ProviderError

    class Throttled:
        status_code = 429
        headers = {"retry-after": "120"}

        def json(self) -> dict[str, int]:
            return {}

    class T:
        def get(self, url: str, timeout: float = 10.0) -> Throttled:
            return Throttled()

    client = SofascoreClient(SofaConfig(runs_dir=str(tmp_path), target_rps=1000), T())
    with pytest.raises(ProviderError):
        client.event_statistics(1)

    row = json.loads(client.log_path.read_text(encoding="utf-8").splitlines()[0])
    assert row["status"] == 429
    assert row["headers"]["retry-after"] == "120"


def test_f24_a_response_without_diagnostic_headers_adds_no_noise(
    tmp_path: Path,
) -> None:
    """An empty headers dict in every row would be noise, not diagnostics."""
    from bet.sofa.client import SofascoreClient
    from bet.sofa.config import SofaConfig
    from tests.sofa.test_client import MockResponse, MockTransport

    transport = MockTransport()
    transport.responses = [MockResponse(200, {"ok": 1})]
    client = SofascoreClient(
        SofaConfig(runs_dir=str(tmp_path), target_rps=1000), transport
    )
    client.event_statistics(1)

    row = json.loads(client.log_path.read_text(encoding="utf-8").splitlines()[0])
    assert "headers" not in row


def test_f24_the_bridge_transport_carries_headers_from_the_browser() -> None:
    """The browser is the only place these headers exist; the bridge must pass
    them on rather than keeping status and body alone."""
    from bet.sofa.bridge_transport import BridgeResponse

    resp = BridgeResponse(200, "{}", {"retry-after": "5"})
    assert resp.headers == {"retry-after": "5"}


# --------------------------------------------------------------------------
# F19 — the pre-sample OFFER had no reader
# --------------------------------------------------------------------------


def test_f19_samples_reads_the_offer_artifact_instead_of_asking_superbet_again(
    tmp_path: Path,
) -> None:
    """Fails on the old code for the right reason: SAMPLES asked Superbet once
    per fixture even though 04_offer.json already held the answer — ~600
    requests a day to re-learn it, and the A4 docstring claimed otherwise."""
    from bet.sofa.contracts import FixtureOffer, PricedRung
    from bet.sofa.samples import process_fixture_samples
    from bet.sofa.timeutil import now as real_now

    class CountingSuperbet:
        def __init__(self) -> None:
            self.calls = 0

        def event_odds(self, event_id: str):  # type: ignore[no-untyped-def]
            self.calls += 1
            return {"odds": None}

    class NoSofascore:
        def entity_events(self, *a: object, **k: object) -> None:
            return None

        def event_statistics(self, *a: object, **k: object) -> None:
            return None

        def event_incidents(self, *a: object, **k: object) -> None:
            return None

    from bet.sofa.cache import SofaCache
    from bet.sofa.config import SofaConfig

    config = SofaConfig(db_path=str(tmp_path / "t.db"), runs_dir=str(tmp_path))
    superbet = CountingSuperbet()
    offer = FixtureOffer(
        sofascore_event_id=1,
        status="PRICED",
        rungs=[
            PricedRung(
                market="goals_total",
                subject="",
                line=2.5,
                over_odds=1.85,
                under_odds=1.95,
                fetched_at_utc=real_now(),
            )
        ],
        unmapped_markets=[],
    )

    process_fixture_samples(
        _fixture(1, ["a"]),
        NoSofascore(),  # type: ignore[arg-type]
        SofaCache(config),
        superbet,  # type: ignore[arg-type]
        config,
        offer=offer,
    )
    assert superbet.calls == 0, (
        f"SAMPLES asked Superbet {superbet.calls} time(s) for what the offer "
        "artifact already said"
    )


def test_f19_a_fixture_the_offer_does_not_cover_still_falls_back(
    tmp_path: Path,
) -> None:
    """A missing or partial offer must cost requests, not coverage."""
    from bet.sofa.cache import SofaCache
    from bet.sofa.config import SofaConfig
    from bet.sofa.samples import process_fixture_samples

    class CountingSuperbet:
        def __init__(self) -> None:
            self.calls = 0

        def event_odds(self, event_id: str):  # type: ignore[no-untyped-def]
            self.calls += 1
            return {"odds": None}

    class NoSofascore:
        def entity_events(self, *a: object, **k: object) -> None:
            return None

    config = SofaConfig(db_path=str(tmp_path / "t.db"), runs_dir=str(tmp_path))
    superbet = CountingSuperbet()
    process_fixture_samples(
        _fixture(1, ["a"]),
        NoSofascore(),  # type: ignore[arg-type]
        SofaCache(config),
        superbet,  # type: ignore[arg-type]
        config,
        offer=None,
    )
    assert superbet.calls == 1


def test_f19_metrics_come_from_the_offers_priced_rungs() -> None:
    from bet.sofa.contracts import FixtureOffer, PricedRung
    from bet.sofa.samples import metrics_from_offer
    from bet.sofa.timeutil import now as real_now

    offer = FixtureOffer(
        sofascore_event_id=1,
        status="PRICED",
        rungs=[
            PricedRung(
                market=m,
                subject="",
                line=2.5,
                over_odds=1.9,
                under_odds=1.9,
                fetched_at_utc=real_now(),
            )
            for m in ("goals_total", "corners_total", "goals_total")
        ],
        unmapped_markets=[],
    )
    assert metrics_from_offer(offer) == {"goals_total", "corners_total"}
    assert metrics_from_offer(None) == set()


# --------------------------------------------------------------------------
# F31 — a constant nobody reads, and an assert on the production path
# --------------------------------------------------------------------------


def test_f31_a_value_row_without_a_surplus_is_dropped_not_fatal() -> None:
    """Fails on the old code for the right reason: `assert row.surplus is not
    None` brought down the whole COUPON stage, and vanished entirely under -O,
    so the guard depended on how the process was started."""
    from datetime import UTC, datetime, timedelta

    from bet.sofa.contracts import FixtureOffer, PricedRung
    from bet.sofa.coupon import build_coupon

    row = _sheet_row(1)
    row.surplus = None

    now = datetime(2026, 9, 18, 10, 0, tzinfo=UTC)
    fixture = _fixture(1, ["x"])
    fixture.sport = "tennis"
    fixture.kickoff_utc = datetime(2026, 9, 18, 18, 0, tzinfo=UTC)
    offer = FixtureOffer(
        sofascore_event_id=1,
        status="PRICED",
        rungs=[
            PricedRung(
                market="games_total",
                subject="",
                line=20.5,
                over_odds=2.50,
                under_odds=1.55,
                fetched_at_utc=now,
            )
        ],
        unmapped_markets=[],
    )

    result = build_coupon(
        [row],
        [fixture],
        [offer],
        [],
        now,
        now + timedelta(minutes=15),
        timedelta(minutes=45),
    )
    assert not result.coupon.singles
    assert "NO_SURPLUS" in [d.reason for d in result.dropped], (
        "the row must be refused with a reason, like every other exclusion here"
    )


def test_f31_the_family_cap_constant_is_actually_read() -> None:
    """Fails on the old code for the right reason: the constant was defined and
    never referenced — "one" was hardcoded in `if family in families`, so
    changing it did nothing while looking as though it would."""
    import inspect

    from bet.sofa import coupon as coupon_module

    source = inspect.getsource(coupon_module)
    uses = source.count("MAX_PER_MECHANISM_FAMILY_PER_FIXTURE")
    assert uses >= 2, f"the constant is referenced {uses} time(s): definition only"


def test_f31_one_family_per_fixture_still_holds() -> None:
    """Behaviour is unchanged at the current value; only the wiring is real."""
    from datetime import UTC, datetime, timedelta

    from bet.sofa.contracts import FixtureOffer, PricedRung
    from bet.sofa.coupon import build_coupon

    now = datetime(2026, 9, 18, 10, 0, tzinfo=UTC)
    fixture = _fixture(1, ["x"])
    fixture.sport = "tennis"
    fixture.kickoff_utc = datetime(2026, 9, 18, 18, 0, tzinfo=UTC)

    rows = []
    rungs = []
    for i, line in enumerate((20.5, 21.5)):
        r = _sheet_row(1)
        r.line = line
        r.surplus = 0.60 - i * 0.1
        rows.append(r)
        rungs.append(
            PricedRung(
                market="games_total",
                subject="",
                line=line,
                over_odds=2.50,
                under_odds=1.55,
                fetched_at_utc=now,
            )
        )

    result = build_coupon(
        rows,
        [fixture],
        [
            FixtureOffer(
                sofascore_event_id=1,
                status="PRICED",
                rungs=rungs,
                unmapped_markets=[],
            )
        ],
        [],
        now,
        now + timedelta(minutes=15),
        timedelta(minutes=45),
    )
    assert len(result.coupon.singles) == 1
    assert "FAMILY_SLOT_TAKEN" in [d.reason for d in result.dropped]


# --------------------------------------------------------------------------
# AET/AP — operator decision: recover the goals, keep refusing the counts
# --------------------------------------------------------------------------


def _aet_event(code: int = 110):  # type: ignore[no-untyped-def]
    """A match level at 1-1 after 90 minutes, won 2-1 in extra time."""
    return {
        "id": 1,
        "status": {"type": "finished", "code": code},
        "homeScore": {"current": 2, "normaltime": 1},
        "awayScore": {"current": 1, "normaltime": 1},
    }


@pytest.mark.parametrize("code", [110, 120])
def test_aet_goals_come_from_normaltime_not_the_final_score(code: int) -> None:
    """Fails on the old code for the right reason: the match was excluded
    entirely, so it contributed nothing to any metric."""
    from bet.sofa.metrics import extract_metric

    event = _aet_event(code)
    assert extract_metric("goals_total", "football", {}, None, event, True) == 2.0, (
        "90 minutes is what Superbet's goal markets settle on, so 2 not 3"
    )
    assert extract_metric("goals_for", "football", {}, None, event, True) == 1.0


def test_aet_counting_metrics_are_still_refused() -> None:
    """A 120-minute match has a third more corners; admitting it would be the
    F28 error with the sign flipped."""
    from bet.sofa.contracts import GapReason
    from bet.sofa.metrics import extract_metric

    event = _aet_event()
    stats = {"ALL": {"cornerKicks": (7.0, 6.0), "fouls": (14.0, 12.0)}}
    for metric in ("corners_total", "corners_for", "fouls_total"):
        assert (
            extract_metric(metric, "football", stats, None, event, True)
            == GapReason.EVENT_NOT_FINISHED
        ), metric


def test_aet_without_normaltime_is_absent_not_wrong() -> None:
    """49 of the 824 cached AET matches have no normaltime; they must report
    absence rather than fall back to the 120-minute score."""
    from bet.sofa.contracts import GapReason
    from bet.sofa.metrics import extract_metric

    event = _aet_event()
    del event["homeScore"]["normaltime"]
    assert (
        extract_metric("goals_total", "football", {}, None, event, True)
        == GapReason.STAT_KEY_ABSENT
    )


def test_a_normal_match_is_untouched_by_the_extra_time_path() -> None:
    from bet.sofa.metrics import extract_metric

    normal = {
        "id": 2,
        "status": {"type": "finished", "code": 100},
        "homeScore": {"current": 3, "normaltime": 3},
        "awayScore": {"current": 1, "normaltime": 1},
    }
    assert extract_metric("goals_total", "football", {}, None, normal, True) == 4.0
    stats = {"ALL": {"cornerKicks": (7.0, 6.0)}}
    assert (
        extract_metric("corners_total", "football", stats, None, normal, True) == 13.0
    )


def test_a_retirement_or_walkover_is_still_excluded_entirely() -> None:
    """Widening the admission must not let the real exclusions back in."""
    from bet.sofa.settle import is_completed_event

    for code in (91, 92, 93, 98):
        assert not is_completed_event({"status": {"type": "finished", "code": code}})
    assert is_completed_event({"status": {"type": "finished", "code": 100}})
    assert is_completed_event({"status": {"type": "finished", "code": 110}})


# --------------------------------------------------------------------------
# F12 — operator decision: an exclusion list in BOARD, keyed on what Superbet
# actually sends (ids, never names)
# --------------------------------------------------------------------------


def _board_row(event_id: int, tournament_id: int, name: str = "A · B"):  # type: ignore[no-untyped-def]
    return {
        "eventId": event_id,
        "sportId": 5,
        "matchName": name,
        "utcDate": "2026-09-18T18:00:00Z",
        "tournamentId": tournament_id,
        "categoryId": 70,
    }


def test_f12_board_records_the_competition_ids_superbet_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Superbet sends no competition name at all, only ids. Without them the
    question "is this slate descending into competitions with no data" can only
    be answered by a live probe. Fails on the old code: the fields did not
    exist and the ids were discarded."""
    from bet.sofa import board as board_module

    class Client:
        def events_by_date(self, *a: object, **k: object) -> list[dict[str, object]]:
            return [_board_row(1, 91283)]

    monkeypatch.setattr(board_module, "load_excluded_tournament_ids", lambda: set())
    fixtures = board_module.fetch_board("2026-09-18", Client())  # type: ignore[arg-type]
    assert len(fixtures) == 1
    assert fixtures[0].tournament_id == 91283
    assert fixtures[0].category_id == 70


def test_f12_an_excluded_tournament_never_reaches_the_board(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bet.sofa import board as board_module

    class Client:
        def events_by_date(self, *a: object, **k: object) -> list[dict[str, object]]:
            return [_board_row(1, 91283), _board_row(2, 1656, "C · D")]

    monkeypatch.setattr(board_module, "load_excluded_tournament_ids", lambda: {91283})
    fixtures = board_module.fetch_board("2026-09-18", Client())  # type: ignore[arg-type]
    assert [f.superbet_event_id for f in fixtures] == ["2"]


def test_f12_the_shipped_exclusion_list_is_empty_and_that_is_deliberate() -> None:
    """The measurement did not support any exclusion, so none is shipped.

    Of 290 football fixtures on the 2026-09-18 board, 256 were in competitions
    with >=90% half coverage and none at 0%. The zero-coverage competitions the
    finding named appear in opponents' historical samples, not on the board.
    An exclusion nobody measured is a coverage cut wearing the costume of a
    saving — if this list ever grows, it grows with evidence behind it.
    """
    config = json.loads(
        (REPO / "config" / "sofa_board_exclusions.json").read_text(encoding="utf-8")
    )
    assert config["superbet_tournament_ids"] == []
    assert "_doc" in config, "the reason it is empty must travel with the file"


def test_f12_a_missing_or_broken_config_excludes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Degrading to "exclude nothing" is the safe direction: a config that
    cannot be read must not silently delete the slate."""
    from bet.sofa import board as board_module

    monkeypatch.chdir(tmp_path)
    assert board_module.load_excluded_tournament_ids() == set()

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "sofa_board_exclusions.json").write_text("{ broken")
    assert board_module.load_excluded_tournament_ids() == set()


# --------------------------------------------------------------------------
# cards — operator decision: build the market. There is no market to build.
# --------------------------------------------------------------------------


def test_cards_yellow_only_metrics_are_gone_because_nothing_prices_them() -> None:
    """Enumerated against the live board: every countable card market Superbet
    offers is "liczba kartek", settled in booking points with a red worth more
    than a yellow. There is no yellow-only market, so a yellowCards metric is
    coverage that cannot be bet."""
    from bet.sofa.metrics import FOOTBALL_METRICS

    assert "cards_total" not in FOOTBALL_METRICS
    assert "cards_for" not in FOOTBALL_METRICS
    assert FOOTBALL_METRICS["cards_points_total"]["is_total"] is True
    assert FOOTBALL_METRICS["cards_points_for"]["is_total"] is False


def test_cards_the_real_superbet_names_map_to_the_points_metrics() -> None:
    """The names below are verbatim from Brentford-Chelsea on 2026-09-18."""
    from bet.sofa.market_mapper import classify_market

    assert classify_market("Liczba kartek") == ("cards_points_total", "")
    assert classify_market("Brentford - liczba kartek") == (
        "cards_points_for",
        "brentford",
    )
    assert classify_market("Chelsea - liczba kartek") == ("cards_points_for", "chelsea")


@pytest.mark.parametrize(
    "market_name",
    [
        "1. połowa - liczba kartek",
        "2. połowa - liczba kartek",
        "1. połowa - Brentford liczba kartek",
        "2. połowa - Chelsea liczba kartek",
    ],
)
def test_a_half_time_scope_is_unmapped_not_a_phantom_per_team_row(
    market_name: str,
) -> None:
    """Fails on the old code for the right reason: the per-team pattern matched
    these with team="1. polowa", producing a row that prices a half-time line
    off a whole-match sample — F29's defect in a market family F29 did not
    reach. Verbatim names from the live board.

    None sends them to unmapped_markets, where a market we do not price is
    visible as exactly that.
    """
    from bet.sofa.market_mapper import classify_market

    assert classify_market(market_name) is None


# --------------------------------------------------------------------------
# has_xg / best_of — operator decision: drop the first, rename the second
# --------------------------------------------------------------------------


def test_has_xg_is_gone_from_the_fixture_contract() -> None:
    """It read hasXg off a match that had not been played, so it was False for
    the whole Bundesliga, and nothing consumed it. A field that lies and nobody
    reads is a trap for the next reader."""
    from bet.sofa.contracts import Fixture

    assert "has_xg" not in Fixture.model_fields


def test_the_xg_gate_still_asks_the_right_question_in_the_right_place() -> None:
    """Removing the field must not disturb the gate that actually works:
    metrics.py checks hasXg on each historical match separately."""
    from bet.sofa.contracts import GapReason
    from bet.sofa.metrics import extract_metric

    stats = {"ALL": {"expectedGoals": (1.4, 1.1)}}
    with_xg = {"id": 1, "status": {"type": "finished", "code": 100}, "hasXg": True}
    without = {"id": 2, "status": {"type": "finished", "code": 100}, "hasXg": False}

    assert extract_metric("xg_total", "football", stats, None, with_xg, True) == 2.5
    assert (
        extract_metric("xg_total", "football", stats, None, without, True)
        == GapReason.STAT_KEY_ABSENT
    ), "absent, never 0.0"


def test_best_of_is_renamed_to_what_it_actually_holds() -> None:
    """defaultPeriodCount. For football that is the number of halves, which is
    why `best_of: 2` appeared on all 290 football fixtures."""
    from bet.sofa.contracts import Fixture

    assert "best_of" not in Fixture.model_fields
    assert "default_period_count" in Fixture.model_fields


# --------------------------------------------------------------------------
# F33 — /event/{id} had no cache at all: 46% of a RESOLVE stage's requests
# --------------------------------------------------------------------------


class _CountingEventClient:
    def __init__(self, status_type: str = "finished") -> None:
        self.calls = 0
        self.status_type = status_type

    def event(self, event_id: int):  # type: ignore[no-untyped-def]
        self.calls += 1
        return {
            "event": {
                "id": event_id,
                "startTimestamp": 1789740000,
                "homeTeam": {"name": "Home", "id": 1},
                "awayTeam": {"name": "Away", "id": 2},
                "tournament": {"name": "T", "category": {"name": "C"}},
                "season": {"id": 1},
                "status": {"type": self.status_type, "code": 100},
                "roundInfo": {"round": 7},
            }
        }


def _parse_twice(tmp_path: Path, status_type: str, ttl_min: int = 60):  # type: ignore[no-untyped-def]
    from bet.sofa.cache import SofaCache
    from bet.sofa.config import SofaConfig
    from bet.sofa.resolve import parse_fixture

    config = SofaConfig(db_path=str(tmp_path / "t.db"), event_detail_ttl_min=ttl_min)
    cache = SofaCache(config)
    client = _CountingEventClient(status_type)
    event = {"id": 555, "startTimestamp": 1789740000}
    for _ in range(2):
        parse_fixture(event, "football", ["1"], client, cache=cache)  # type: ignore[arg-type]
    return client, cache, config


def test_f33_a_finished_matchs_detail_is_fetched_once(tmp_path: Path) -> None:
    """Fails on the old code for the right reason: there was no cache, so the
    payload was re-fetched on every run — 282 of 615 requests in the live run
    that raised this."""
    client, _, _ = _parse_twice(tmp_path, "finished")
    assert client.calls == 1, (
        f"fetched {client.calls} times; a finished match cannot change"
    )


def test_f33_an_unplayed_matchs_detail_expires(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The referee is announced late — filled for only 9% of fixtures — so an
    eternal cache would freeze an empty referee in place. That is the F17 trap:
    waste turned into a silent gap is the worse error."""
    from datetime import timedelta

    import bet.sofa.cache as cache_module
    from bet.sofa.resolve import parse_fixture
    from bet.sofa.timeutil import now as real_now

    client, cache, _ = _parse_twice(tmp_path, "notstarted", ttl_min=60)
    assert client.calls == 1, "within the TTL it must be reused"

    base = real_now()
    monkeypatch.setattr(cache_module, "now", lambda: base + timedelta(minutes=61))
    parse_fixture(
        {"id": 555, "startTimestamp": 1789740000},
        "football",
        ["1"],
        client,
        cache=cache,
    )  # type: ignore[arg-type]
    assert client.calls == 2, "after the TTL an unplayed match must be asked again"


def test_f33_a_finished_match_is_kept_past_the_ttl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Immutable payloads have no reason to expire, like sofa_event_stats."""
    from datetime import timedelta

    import bet.sofa.cache as cache_module
    from bet.sofa.resolve import parse_fixture
    from bet.sofa.timeutil import now as real_now

    client, cache, _ = _parse_twice(tmp_path, "finished", ttl_min=60)
    base = real_now()
    monkeypatch.setattr(cache_module, "now", lambda: base + timedelta(days=30))
    parse_fixture(
        {"id": 555, "startTimestamp": 1789740000},
        "football",
        ["1"],
        client,
        cache=cache,
    )  # type: ignore[arg-type]
    assert client.calls == 1


def test_f33_without_a_cache_the_behaviour_is_unchanged(tmp_path: Path) -> None:
    """Callers that pass no cache — the backfill — must be unaffected."""
    from bet.sofa.resolve import parse_fixture

    client = _CountingEventClient("finished")
    for _ in range(2):
        parse_fixture(
            {"id": 555, "startTimestamp": 1789740000}, "football", ["1"], client
        )  # type: ignore[arg-type]
    assert client.calls == 2
