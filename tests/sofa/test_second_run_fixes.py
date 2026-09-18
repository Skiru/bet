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
    assert json.loads(summary_line.removeprefix("SOFA_SUMMARY: "))["run_id"] == "chosen1"


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
