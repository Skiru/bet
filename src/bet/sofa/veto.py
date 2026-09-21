"""Analyst vetoes — the one channel a human read has into the machine's output.

A veto is the only thing an analyst may put into the pipeline. It can remove a
row; it can never promote one. Matching is *most general wins*: a veto whose
`market`/`subject`/`line`/`direction` are `None` covers every row on that
fixture, which is the normal shape — a sample that does not describe the
fixture is broken at every rung, not at one of them.

The predicate is shared rather than reimplemented per caller. It was not, until
2026-09-21: `run_coupon` matched vetoes and `run_confidence` did not look for
the file at all, so an analyst's veto reached `06_coupon.json` — the VALUE
singles, which the runbook says are not the coupon — and never reached
`08_confidence.json`, which is what the PDF the operator stakes is built from.
The only structured output an analyst had could not touch the product.
"""

from pathlib import Path

from pydantic import RootModel

from bet.sofa.contracts import SheetRow, Veto


def veto_matches(
    veto: Veto,
    *,
    sofascore_event_id: int,
    market: str,
    subject: str,
    line: float,
    direction: str,
) -> bool:
    """Does this veto cover that (fixture, market, subject, line, direction)?

    Takes primitives rather than a `SheetRow` so the stages that carry rows as
    plain dicts — CONFIDENCE reads the sheet as JSON — use this predicate
    instead of writing a second one that drifts from it.
    """
    if veto.sofascore_event_id != sofascore_event_id:
        return False
    if veto.market is not None and veto.market != market:
        return False
    if veto.subject is not None and veto.subject != subject:
        return False
    if veto.line is not None and veto.line != line:
        return False
    if veto.direction is not None and veto.direction != direction:
        return False
    return True


def _row_matches(veto: Veto, row: SheetRow) -> bool:
    return veto_matches(
        veto,
        sofascore_event_id=row.sofascore_event_id,
        market=row.market,
        subject=row.subject,
        line=row.line,
        direction=row.direction,
    )


def match_vetoes(row: SheetRow, vetoes: list[Veto]) -> list[Veto]:
    return [veto for veto in vetoes if _row_matches(veto, row)]


def find_unmatched_vetoes(sheet_rows: list[SheetRow], vetoes: list[Veto]) -> list[Veto]:
    """Vetoes that hit nothing.

    T27: reported, never swallowed. A veto matching no row is either a typo or
    a row that vanished between the read and the rebuild, and both are things
    the operator has to hear about — a silent no-op reads exactly like a
    veto that was applied.
    """
    return [
        veto
        for veto in vetoes
        if not any(_row_matches(veto, row) for row in sheet_rows)
    ]


def load_vetoes(path: Path | str) -> list[Veto]:
    """Read a `vetoes.json`. Absent or empty is the normal, healthy case."""
    p = Path(path)
    if not p.exists():
        return []
    data = p.read_text(encoding="utf-8")
    if not data.strip():
        return []
    return RootModel[list[Veto]].model_validate_json(data).root
