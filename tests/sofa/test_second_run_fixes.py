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
