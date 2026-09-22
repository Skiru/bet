"""The deep audit must grade the bets the PDF actually staked.

`is_stakeable` lives in `bet.sofa.confidence` because the predicate had been
written out more than once and the copies disagreed. `run_confidence.py` and
`build_coupon_pdf.py` were consolidated onto it; `audit_day_deep.py` kept a
fourth, stale copy that tested `ev_if_product_priced` and so ignored the
measured 12% correlation haircut.

On 2026-09-21 that copy reported "1 slip, ROI -100.0%" for a builder the PDF
had correctly refused to stake: `ev_if_product_priced` was +0.043 while
`ev_after_haircut` was -0.0821. The day staked nothing, and the audit invented
a loss for it. A tool that grades a day must not disagree with the file that
is the coupon.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from bet.sofa.confidence import is_stakeable

AUDIT = Path(__file__).resolve().parents[2] / "scripts" / "sofa" / "audit_day_deep.py"


def test_audit_day_deep_imports_the_shared_predicate() -> None:
    tree = ast.parse(AUDIT.read_text())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "bet.sofa.confidence"
        for alias in node.names
    }
    assert "is_stakeable" in imported, (
        "audit_day_deep.py must import is_stakeable from bet.sofa.confidence "
        "rather than re-deriving which builders were staked"
    )


def test_audit_day_deep_does_not_test_product_ev_inline() -> None:
    """The specific shape of the 2026-09-21 defect, so it cannot come back."""
    source = AUDIT.read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        segment = ast.get_source_segment(source, node) or ""
        assert "ev_if_product_priced" not in segment, (
            "audit_day_deep.py compares ev_if_product_priced directly; that "
            "ignores the correlation haircut and grades bets the PDF never "
            f"staked. Use is_stakeable(). Offending expression: {segment!r}"
        )


@pytest.mark.parametrize(
    ("builder", "expected", "why"),
    [
        (
            {
                "best_for_fixture": True,
                "ev_if_product_priced": 0.043,
                "ev_after_haircut": -0.0821,
            },
            False,
            "the 2026-09-21 builder: positive on the product, negative after "
            "the haircut, and the PDF staked nothing",
        ),
        (
            {
                "best_for_fixture": True,
                "ev_if_product_priced": 0.30,
                "ev_after_haircut": 0.11,
            },
            True,
            "survives the haircut",
        ),
        (
            {
                "best_for_fixture": False,
                "ev_if_product_priced": 0.30,
                "ev_after_haircut": 0.11,
            },
            False,
            "not the best builder for its fixture",
        ),
    ],
)
def test_is_stakeable_prefers_the_haircut(
    builder: dict[str, object], expected: bool, why: str
) -> None:
    assert is_stakeable(builder) is expected, why


def test_audit_day_deep_guards_the_unsettled_day() -> None:
    """A day with no settled legs must report the absence, not crash.

    2026-09-22 shipped a PDF with zero picks and 2026-09-21 staked nothing
    either. On such a day the script raised TypeError formatting a None ROI,
    then ZeroDivisionError on `len(graded)`. Because it exits 1 for "findings
    found", the crash was indistinguishable from a real result.

    Sections 1-4 all divide by the settled population, so the guard has to sit
    at the definition of `graded` and return, not patch each division.
    """
    source = AUDIT.read_text()
    tree = ast.parse(source)

    main = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "main"
    )
    body = main.body
    graded_at = next(
        i for i, node in enumerate(body)
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "graded" for t in node.targets)
    )
    guard = next(
        (node for node in body[graded_at:graded_at + 4]
         if isinstance(node, ast.If)
         and isinstance(node.test, ast.UnaryOp)
         and isinstance(node.test.op, ast.Not)
         and getattr(node.test.operand, "id", None) == "graded"),
        None,
    )
    assert guard is not None, (
        "audit_day_deep.main() must guard `if not graded:` immediately after "
        "computing it; sections 1-4 divide by that population and a day that "
        "staked nothing is legitimate"
    )
    assert any(isinstance(n, ast.Return) for n in ast.walk(guard)), (
        "the empty-day guard must return, not fall through into the ROI "
        "arithmetic it is protecting"
    )


def test_audit_day_deep_runs_clean_on_the_unsettled_day() -> None:
    """End to end on real artifacts, when a zero-pick day is on disk."""
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[2]
    conf = repo / "runs" / "sofa" / "2026-09-22" / "08_confidence.json"
    if not conf.exists():
        pytest.skip("no 2026-09-22 run on disk")

    proc = subprocess.run(
        [sys.executable, str(AUDIT), "--date", "2026-09-22"],
        capture_output=True, text=True, cwd=str(repo),
        env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin"},
    )
    assert "Traceback" not in proc.stderr, proc.stderr[-1000:]
    assert proc.returncode == 0, f"exit {proc.returncode}: {proc.stderr[-600:]}"
