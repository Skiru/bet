"""The suite must be able to collect itself.

Until 2026-09-07 ``pytest tests/`` ran **nothing at all**: 23 files failed at
import, pytest reported ``Interrupted: 23 errors during collection`` and every
one of the ~5,800 collectable tests was skipped along with them. A green run of
any single file hid it, which is how it survived -- the suite was not failing,
it was not starting.

Two causes, both now fixed and both guarded here separately, because they fail
in different ways and a single "collection works" assertion would not say which
came back:

* 15 files imported the quarantined S0-S10 stack (``bet.pipeline.orchestrator``,
  ``bet.pipeline.readiness_contracts``, ``scripts.pipeline_steps``,
  ``scripts.generate_v5_final_report``), which lives in ``legacy/`` and does not
  import. They were moved to ``legacy/tests/``, the established home for that
  stack, which ``testpaths = ["tests"]`` keeps out of collection.
* 8 files carried unresolved merge conflict markers. Three of them tested code
  that is still live in ``src/`` and were resolved and kept; five belong to the
  quarantined stack and moved with the others.

The first test here is the one that matters and is deliberately blunt: it runs
the real collector as a subprocess and requires exit 0. ``--collect-only``
imports every test module but executes no test body, so it costs no provider
requests and cannot trip the ``conftest.py`` quota guard.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

# ``<<<<<<< ``, ``=======``, ``>>>>>>> `` at the start of a line. Written as
# separate literals joined at runtime so this file cannot match its own source
# when the sweep below reads every test module -- which it does, including this
# one.
_MARKER_RE = re.compile(
    "^(?:" + "<" * 7 + " |" + "=" * 7 + "$|" + ">" * 7 + " )",
    re.MULTILINE,
)

# Modules that only exist under legacy/. A test under tests/ importing one of
# these cannot collect, which is exactly how 15 files went dead.
QUARANTINED = (
    "bet.pipeline.orchestrator",
    "bet.pipeline.readiness_contracts",
    "bet.pipeline.agent_work_orders",
    "bet.pipeline.agent_execution_prompts",
    "bet.pipeline.integration_artifacts",
    "bet.pipeline.market_probability_inputs",
    "scripts.pipeline_steps",
    "scripts.generate_v5_final_report",
    "scripts.certify_pipeline_final_closure",
)


def test_pytest_can_collect_the_whole_suite() -> None:
    """``pytest --collect-only tests/`` must exit 0.

    One assertion, and it is the whole defect. Anything that makes a test
    module unimportable -- a conflict marker, an import of the quarantined
    stack, a syntax error, a missing dependency -- stops the entire suite
    rather than the file, so this has to be checked at the level of the run and
    not per file.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", str(TESTS)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
    )
    if result.returncode != 0:
        errors = [
            line for line in result.stdout.splitlines() if line.startswith("ERROR")
        ]
        raise AssertionError(
            "pytest --collect-only tests/ exited "
            f"{result.returncode}; the suite runs no tests at all in this "
            "state. Files that failed to import:\n  "
            + "\n  ".join(errors or ["(none reported on stdout)"])
            + "\nA file that belongs to the quarantined S0-S10 stack goes to "
            "legacy/tests/; a file testing live src/ code gets fixed."
        )


def test_no_test_file_carries_a_conflict_marker() -> None:
    """Names the file and line, which exit 0 alone would not.

    Worth its own test because the failure above is a bare exit code: this one
    turns "collection is broken" into "this file, this line".
    """
    offenders: list[str] = []
    for path in sorted(TESTS.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _MARKER_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(ROOT)}:{line}")
    assert not offenders, (
        "unresolved merge conflict markers under tests/: "
        + ", ".join(offenders)
        + ". Resolve by looking at both sides -- for a security test, picking "
        "the wrong side is worse than a test that does not run."
    )


def test_no_test_file_imports_the_quarantined_stack() -> None:
    """The 15-file failure mode, caught by name instead of by exit code.

    A test that needs the S0-S10 stack belongs under ``legacy/tests/``. The one
    legitimate exception is a guarded lookup -- ``pytest.importorskip`` -- which
    is how ``test_t2_sharding_lifecycle.py`` keeps its four live sharding tests
    collectable while its orchestrator test stands down.

    **Module level only**, and the distinction is the whole reason this test is
    narrower than it first looks. An import at column 0 runs at collection and
    takes the entire suite down with it. The same import inside a test body
    runs only when that test runs, so it fails one test and collects fine --
    nine files under tests/ do exactly that today (``test_v8_plan_continuation``,
    ``test_superbet_manual_quote_contract`` and others). Those are real
    failures against the quarantined stack and they belong to the suite's
    failing-test baseline, not to this defect; flagging them here would make
    this guard fail for a reason it was not written to catch.
    """
    offenders: list[str] = []
    for path in sorted(TESTS.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.name == Path(__file__).name:
            continue
        # A module-level importorskip earlier in the file makes the import
        # below it safe: the module is skipped, not imported, and collection
        # survives. tests/tipsters/test_tipster_shadow_evidence_wrapper.py
        # keeps a quarantined wrapper's specification alive exactly this way.
        guard = text.find("pytest.importorskip(")
        for module in QUARANTINED:
            pattern = re.compile(
                rf"^(?:from\s+{re.escape(module)}[\s.]|import\s+{re.escape(module)}\b)",
                re.MULTILINE,
            )
            for match in pattern.finditer(text):
                if 0 <= guard < match.start():
                    continue
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(ROOT)}:{line} -> {module}")
    assert not offenders, (
        "tests/ imports modules that live only in legacy/, so the whole suite "
        "stops collecting: " + ", ".join(offenders) + ". Move the file to "
        "legacy/tests/, or reach the module through pytest.importorskip."
    )
