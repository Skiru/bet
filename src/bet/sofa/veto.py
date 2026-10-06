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
from typing import Protocol

from pydantic import RootModel

from bet.sofa.contracts import LegRead, SheetRow, Veto


class _RowKey(Protocol):
    """What a veto and a read both carry: the row they cover."""

    @property
    def sofascore_event_id(self) -> int: ...
    @property
    def market(self) -> str | None: ...
    @property
    def subject(self) -> str | None: ...
    @property
    def line(self) -> float | None: ...
    @property
    def direction(self) -> str | None: ...


def veto_matches(
    veto: _RowKey,
    *,
    sofascore_event_id: int,
    market: str,
    subject: str,
    line: float | None,
    direction: str,
    period: int | None = None,
) -> bool:
    """Does this veto cover that (fixture, market, subject, line, direction)?

    `period` (a measured sport's leg, F7): a read naming a period covers only
    that period; a veto or read without one covers every period.

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
    want = getattr(veto, "period", None)
    if want is not None and period is not None and want != period:
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


def load_reads(path: Path | str) -> list[LegRead]:
    """Read a `reads.json` (contracts.LegRead). Absent or empty: no reads."""
    p = Path(path)
    if not p.exists():
        return []
    data = p.read_text(encoding="utf-8")
    if not data.strip():
        return []
    return RootModel[list[LegRead]].model_validate_json(data).root


def matching_reads(
    reads: list[LegRead],
    *,
    sofascore_event_id: int,
    market: str,
    subject: str,
    line: float | None,
    direction: str,
    period: int | None = None,
) -> list[LegRead]:
    """The reads that cover this row, with the veto's matching rule."""
    return [
        r
        for r in reads
        if veto_matches(
            r,
            sofascore_event_id=sofascore_event_id,
            market=market,
            subject=subject,
            line=line,
            direction=direction,
            period=period,
        )
    ]


def read_refusal(reads: list[LegRead]) -> str | None:
    """Why the reads covering a row refuse it, or None: NO_BET (a veto by
    another name) and WATCH both remove the leg from the coupon."""
    verdicts = {r.verdict for r in reads}
    if "NO_BET" in verdicts:
        return "READ_NO_BET"
    if "WATCH" in verdicts:
        return "WATCHED"
    return None
