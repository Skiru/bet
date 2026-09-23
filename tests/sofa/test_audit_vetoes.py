"""Grading the analysts' vetoes — and the three ways that grade lies.

A veto removes a row from the product; SETTLE still grades the row, so what
the veto removed has a result. The measurement has three traps, one test each:

  * a veto on a long price "loses more than the rest" by construction, because
    ROI falls with the length of the price — the baseline must be re-weighted
    to the group's own price bands;
  * a veto written after its fixture started may have seen the result;
  * one row matching a broad and a narrow veto is still one bet.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from bet.sofa.contracts import Veto
from scripts.sofa.audit_vetoes import (
    MIN_ODDS,
    Grade,
    attribute,
    grade_vetoes,
    price_band,
    render,
    veto_group,
)

KICKOFF = datetime(2026, 9, 22, 18, 0, tzinfo=UTC)
BEFORE = KICKOFF - timedelta(hours=3)


def _veto(**over: object) -> Veto:
    base: dict[str, object] = dict(
        sofascore_event_id=1, market=None, subject=None, line=None,
        direction=None, reason_class="OTHER", reason="r",
    )
    base.update(over)
    return Veto.model_validate(base)


def _row(eid: int = 1, odds: float | None = 1.8, outcome: str = "LOSS",
         **over: object) -> dict[str, object]:
    base: dict[str, object] = dict(
        sofascore_event_id=eid, market="corners_total", subject="", line=9.5,
        direction="OVER", offered_odds=odds, outcome=outcome, market_p=0.5,
    )
    base.update(over)
    return base


def test_a_context_tag_needs_the_context_class() -> None:
    """`context` says which kind of CONTEXT; on any other class it is a
    contradiction, and it fails loudly rather than landing in a group of its
    own that no one can interpret."""
    assert _veto(reason_class="CONTEXT", context="ROTATION").context == "ROTATION"
    with pytest.raises(ValidationError):
        _veto(reason_class="SAMPLE_UNINFORMATIVE", context="ROTATION")


def test_a_veto_file_from_before_the_tag_still_loads() -> None:
    """Every vetoes.json on disk predates `context`. `extra="forbid"` voids a
    whole file on one bad key, so the new field has to be optional."""
    v = _veto(reason_class="CONTEXT")
    assert v.context is None
    assert veto_group(v) == "CONTEXT"
    assert veto_group(_veto(reason_class="CONTEXT", context="DERBY")) == "CONTEXT/DERBY"


def test_a_row_under_two_vetoes_is_charged_once_to_the_narrow_one() -> None:
    broad = _veto(reason_class="SAMPLE_UNINFORMATIVE")
    narrow = _veto(reason_class="CONTEXT", context="ROTATION", market="corners_total")
    assert attribute(_row(), [broad, narrow]) is narrow
    audit = grade_vetoes([broad, narrow], [_row()],
                         kickoff_by_event={1: KICKOFF}, written_at=BEFORE)
    assert sum(g.rows for g in audit.groups.values()) == 1
    assert audit.groups["CONTEXT/ROTATION"].rows == 1


def test_a_veto_written_after_kickoff_is_not_graded() -> None:
    """It may have been written with the result in view; a leak absorbed into
    the grade makes the analysts look better than any honest read could."""
    audit = grade_vetoes([_veto()], [_row()], kickoff_by_event={1: KICKOFF},
                         written_at=KICKOFF + timedelta(minutes=1))
    assert audit.groups == {}
    assert audit.after_kickoff["OTHER"] == 1


def test_an_unknown_kickoff_counts_as_too_late() -> None:
    audit = grade_vetoes([_veto()], [_row()], kickoff_by_event={}, written_at=BEFORE)
    assert audit.groups == {}
    assert audit.after_kickoff["OTHER"] == 1


def test_rows_the_veto_could_not_have_changed_are_left_out() -> None:
    """CONFIDENCE refuses a price under MIN_ODDS before it reads the vetoes, and
    an unpriced or pushed row has no money in it."""
    rows = [_row(odds=MIN_ODDS - 0.01), _row(odds=None), _row(outcome="PUSH")]
    audit = grade_vetoes([_veto()], rows, kickoff_by_event={1: KICKOFF},
                         written_at=BEFORE)
    assert audit.groups == {}
    assert audit.baseline.rows == 0
    assert (audit.below_min_odds, audit.unpriced) == (1, 1)


def test_the_baseline_is_the_rest_of_the_board() -> None:
    rows = [_row(eid=1), _row(eid=2, outcome="WIN")]
    audit = grade_vetoes([_veto()], rows, kickoff_by_event={1: KICKOFF},
                         written_at=BEFORE)
    assert audit.groups["OTHER"].rows == 1
    assert audit.baseline.rows == 1
    assert audit.baseline.roi == pytest.approx(0.8)


def test_the_baseline_is_reweighted_to_the_groups_price_bands() -> None:
    """The rest of the board: short prices win, long prices lose. A group of
    long-price vetoes compared to the raw baseline looks like a triumph; at
    its own price mix it is exactly the board."""
    rest = Grade()
    for _ in range(9):
        rest.add(_row(odds=1.2, outcome="WIN"))
    rest.add(_row(odds=4.0, outcome="LOSS"))
    group = Grade()
    group.add(_row(odds=4.0, outcome="LOSS"))
    assert rest.roi is not None and rest.roi > 0
    assert rest.roi_at_mix(group.band_rows) == pytest.approx(-1.0)


def test_a_band_the_baseline_lacks_leaves_the_comparison_blank() -> None:
    rest = Grade()
    rest.add(_row(odds=1.2, outcome="WIN"))
    group = Grade()
    group.add(_row(odds=4.0, outcome="LOSS"))
    assert rest.roi_at_mix(group.band_rows) is None


def test_price_bands_split_where_the_measured_roi_breaks() -> None:
    assert [price_band(x) for x in (1.1, 1.49, 1.5, 1.99, 2.0, 2.99, 3.0, 8.0)] == [
        0, 0, 1, 1, 2, 2, 3, 3,
    ]


def test_an_unknown_write_time_is_said_not_tested() -> None:
    """With no write time nothing was excluded as late — silence would read
    as a passed check."""
    audit = grade_vetoes([_veto()], [_row()], kickoff_by_event={1: KICKOFF},
                         written_at=None)
    text = "\n".join(render(audit, heading="## x", written_at_known=False))
    assert "Czas zapisu wet nieznany" in text
    assert "nie został wykonany" in text
