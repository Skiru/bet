"""scripts/sofa/fit_double_chance_curve.py and fit_shot_detail.py - the
replays behind the new markets' curves price as SHEET does and read only the
past (offline, synthetic)."""

from __future__ import annotations

import pytest

from bet.sofa import football_rating as fr
from bet.sofa import football_result as res
from bet.sofa import shot_detail as sd
from scripts.sofa import fit_double_chance_curve as dc
from scripts.sofa import fit_shot_detail as fsd


def _m(eid: int, link: str, ts: int = 0, women: bool = False,
       x: int = 1, y: int = 0) -> dc.Match:
    return dc.Match(ts, eid, women, link, 1.6, 1.1, x, y)


def test_dc_prices_every_selection_as_sheet_and_leaves_unlinked_out() -> None:
    priced = dc.price([_m(1, fr.LINKED), _m(2, fr.UNLINKED)], 7.586)
    assert {p.match.event_id for p in priced} == {1}
    want = res.result_probs(1.6, 1.1, 7.586)
    got = {p.selection: p for p in priced}
    assert set(got) == {"1X", "X2", "12"}
    for sel, p in got.items():
        assert p.p == pytest.approx(want[sel], abs=1e-9)
    assert (got["1X"].y, got["X2"].y, got["12"].y) == (1, 0, 1)


def test_dc_run_gates_men_and_women_apart() -> None:
    day = 86400
    train = [dc.Priced(_m(i, fr.LINKED, ts=i), "1X", 0.72, int(i % 4 != 0))
             for i in range(2000)]
    hold = [dc.Priced(_m(10_000 + i, fr.LINKED, ts=10 * day + i), "1X", 0.72,
                      int(i % 4 != 0)) for i in range(400)]
    out = dc.run(train + hold, 10 * day, 20 * day, 30 * day)
    assert out["gate"][dc.KEY]["n"] == 400
    assert out["gate"][dc.WOMEN_KEY]["n"] == 0
    assert not out["gate"][dc.WOMEN_KEY]["pass"]
    assert out["counts"] == {"train": 2000, "holdout": 400, "final": 2400}


def test_shot_forecasts_read_only_earlier_starts() -> None:
    fitted = {"metrics": {m: {"k": 2, "pool": {"F": 1.0}, "pool_all": 0.5}
                          for m in sd.METRICS}}
    counts = {m: 0 for m in sd.METRICS}
    big = {m: 9 for m in sd.METRICS}
    rows = [(t, t, 7, "F", counts) for t in range(sd.MIN_STARTS)]
    rows.append((100, 100, 7, "F", big))
    fc = fsd.forecasts(rows, fitted, 0, 10**9)
    m = sd.METRICS[0]
    assert len(fc[m]) == len(fsd.LINES)  # only the sixth start is priced
    p, y, eid, *_ = fc[m][0]
    assert eid == 100 and y == 1
    assert p == pytest.approx(sd.forecast([0.0] * sd.MIN_STARTS, "F", m, 0.5,
                                          fitted))
