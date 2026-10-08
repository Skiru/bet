"""epochs.CARDS_CORRELATION: the cards joints' sides correlated at the measured
residual (+0.126) instead of independent. Off (None) = today's output, byte for
byte; the number lives behind the switch, not in the config file."""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bet.sofa import epochs
from bet.sofa import rebuild_plan as rp
from bet.sofa.contracts import SheetRow
from bet.sofa.derived import load_side_correlations
from scripts.sofa import calibrate_from_cache as cc
from scripts.sofa.calibrate_from_cache import Played, iter_rows
from scripts.sofa.run_sheet import sheet_row_json

CONFIG = Path(__file__).resolve().parents[2] / "config" / "sofa_side_correlations.json"
DAY = 86400
BASELINES = {
    "cards_points_for": {"global": {"mean": 2.0, "n": 5000}},
    "goals_for": {"global": {"mean": 1.3, "n": 5000}},
}


def test_the_switch_is_off_and_the_config_still_says_null() -> None:
    assert epochs.CARDS_CORRELATION_FROM_UTC is None
    assert not epochs.cards_correlation_enabled("2026-10-09")
    assert not epochs.cards_correlation_enabled(
        "2030-01-01", datetime(2030, 1, 1, tzinfo=UTC))
    assert json.loads(CONFIG.read_text())["cards_points"]["correlation"] is None


def test_loader_off_is_the_file_and_on_adds_only_cards() -> None:
    off = load_side_correlations()
    assert off == load_side_correlations(cards_correlation=False)
    assert off["cards_points"] is None
    on = load_side_correlations(cards_correlation=True)
    assert on["cards_points"] == pytest.approx(0.126)
    assert {k: v for k, v in on.items() if k != "cards_points"} == {
        k: v for k, v in off.items() if k != "cards_points"}


def test_loader_on_with_a_missing_file_still_reads_cards(tmp_path: Path) -> None:
    assert load_side_correlations(tmp_path / "none.json") == {}
    assert load_side_correlations(
        tmp_path / "none.json", cards_correlation=True) == {"cards_points": 0.126}


def test_switch_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "CARDS_CORRELATION_FROM_UTC",
                        datetime(2026, 10, 9, tzinfo=UTC))
    at = datetime(2026, 10, 9, 7, tzinfo=UTC)
    assert epochs.cards_correlation_enabled("2026-10-09", at)
    assert not epochs.cards_correlation_enabled("2026-10-08", at)
    assert not epochs.cards_correlation_enabled(
        "2026-10-09", datetime(2026, 10, 8, 23, tzinfo=UTC))


def test_rebuild_reruns_sheet_on_a_sheet_of_the_other_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = datetime(2026, 10, 9, 7, 0, tzinfo=UTC)
    limit = timedelta(minutes=45)
    assert epochs.sheet_cards_correlation([{"cards_rule": epochs.CARDS_CORRELATION}])
    assert not epochs.sheet_cards_correlation(
        [{"cards_rule": epochs.CARDS_CORRELATION}, {}])
    assert epochs.sheet_cards_correlation([])
    off = rp.build_plan(rp.DayState("2026-10-09", at, limit, sheet_cards=False))
    assert "SHEET" not in off.names()
    monkeypatch.setattr(epochs, "CARDS_CORRELATION_FROM_UTC",
                        datetime(2026, 10, 9, tzinfo=UTC))
    stale = rp.build_plan(rp.DayState("2026-10-09", at, limit, sheet_cards=False))
    step = next(s for s in stale.steps if s.name == "SHEET")
    assert "cards" in step.reason
    assert "SHEET" not in rp.build_plan(
        rp.DayState("2026-10-09", at, limit, sheet_cards=True)).names()
    assert "SHEET" not in rp.build_plan(
        rp.DayState("2026-10-08", at, limit, sheet_cards=False)).names()


def test_a_sheet_row_carries_the_rule_only_when_priced_under_it() -> None:
    assert "cards_rule" in SheetRow.model_fields

    class _R:
        def __init__(self, rule: str | None) -> None:
            self.rule = rule

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            return {"epoch": "x", "link_rule": None, "dispersion_rule": None,
                    "cards_rule": self.rule}

    assert "cards_rule" not in sheet_row_json(_R(None))  # type: ignore[arg-type]
    assert sheet_row_json(_R(epochs.CARDS_CORRELATION))[  # type: ignore[arg-type]
        "cards_rule"] == epochs.CARDS_CORRELATION


def _played() -> list[Played]:
    rng = random.Random(5)
    out = []
    for i in range(60):
        h, a = (1, 2) if i % 2 == 0 else (2, 1)
        out.append(Played(
            event_id=100 + i, timestamp=i * DAY, home_id=h, away_id=a,
            sport="football", competition_id=17,
            values={
                "cards_points": (float(rng.randint(0, 6)), float(rng.randint(0, 5))),
                "goals": (float(rng.randint(0, 4)), float(rng.randint(0, 3))),
            }))
    return out


def _joint(bases: frozenset[str]) -> list[tuple[object, ...]]:
    return [(r.event_id, r.market, r.line, r.p_central)
            for r in iter_rows(_played(), BASELINES, None, bases)
            if r.market.split("_")[0] in ("both", "most", "handicap")]


def test_replay_flag_moves_only_the_cards_joints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    both = frozenset({"cards_points", "goals"})
    assert cc.CARDS_CORRELATION is False
    off = _joint(both)
    monkeypatch.setattr(cc, "CARDS_CORRELATION", True)
    on = _joint(both)
    def part(rows: list[tuple[object, ...]], name: str) -> list[tuple[object, ...]]:
        return [r for r in rows if name in str(r[1])]

    assert part(off, "goals") and part(off, "cards")
    # a joint row that clears the resolution filter may differ in count, so
    # only the untouched family is compared row for row
    assert part(off, "goals") == part(on, "goals")
    assert part(off, "cards") != part(on, "cards")
