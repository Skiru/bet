"""run_sheet.main's wiring of the 2026-10-08 switches (cards correlation,
count dispersion, per-market K, scoped tennis table): which flag reaches which
callee, the rule markers on the serialised rows, the guard call, and that a
configuration error is FAILED (rc 2), never PARTIAL (rc 1). Offline."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa.contracts import FixtureOffer
from scripts.sofa import run_sheet
from tests.sofa.test_count_dispersion import _sheet_row
from tests.sofa.test_football_rating import _samples as football_samples
from tests.sofa.test_player_markets import _fixture, dataclasses_replace_tennis
from tests.sofa.test_tennis_rating import _samples as tennis_samples

DAY = "2026-10-09"
FLAGS = ("cards", "dispersion", "k", "tennis")


class Harness:
    def __init__(self) -> None:
        self.process_calls: list[dict[str, Any]] = []
        self.side_corr_calls: list[dict[str, Any]] = []
        self.rating_calls: list[dict[str, Any]] = []
        self.table_loads = 0
        self.guard_dates: list[str] = []


def _run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, on: set[str],
    stats_only: bool = True, table: Any = "TABLE", guard: Exception | None = None,
    rating_error: Exception | None = None,
) -> tuple[int, Harness, list[dict[str, Any]]]:
    h = Harness()
    runs = tmp_path / "runs"
    day = runs / DAY
    day.mkdir(parents=True)
    football = _fixture()
    tennis = dataclasses_replace_tennis().model_copy(
        update={"sofascore_event_id": 2, "sport": "tennis"})
    (day / "02_fixtures.json").write_text(json.dumps(
        [football.model_dump(mode="json"), tennis.model_dump(mode="json")]))
    samples = [football_samples(),
               tennis_samples().model_copy(update={"sofascore_event_id": 2})]
    (day / "03_samples.json").write_text(
        json.dumps([s.model_dump(mode="json") for s in samples]))
    offers = [FixtureOffer(sofascore_event_id=i, status="PRICED",
                           unmapped_markets=[], rungs=[]) for i in (1, 2)]
    (day / "04_offer.json").write_text(
        json.dumps([o.model_dump(mode="json") for o in offers]))

    monkeypatch.setenv("SOFA_RUNS_DIR", str(runs))
    monkeypatch.setenv("SOFA_FOOTBALL_RATING", "0")
    monkeypatch.delenv("SOFA_NOW", raising=False)
    monkeypatch.setattr(run_sheet.sys, "argv", ["run_sheet", "--date", DAY])
    monkeypatch.setattr(run_sheet, "stats_only_epoch", lambda d: stats_only)
    monkeypatch.setattr(run_sheet, "tennis_rating_prices", lambda d: False)
    monkeypatch.setattr(run_sheet, "derived_marginal_centres_enabled", lambda d: False)
    for name, flag in (
        ("cards_correlation_enabled", "cards"),
        ("count_dispersion_enabled", "dispersion"),
        ("per_market_k_enabled", "k"),
        ("tennis_scoped_table_enabled", "tennis"),
    ):
        monkeypatch.setattr(
            epochs, name, lambda d, at=None, _f=flag: _f in on)
    def require(d: str, at: datetime | None = None) -> None:
        h.guard_dates.append(d)
        if guard is not None:
            raise guard

    monkeypatch.setattr(epochs, "require_k_with_dispersion", require)

    def side_corr(**kw: Any) -> dict[str, float | None]:
        h.side_corr_calls.append(kw)
        return {}

    def load_table() -> Any:
        h.table_loads += 1
        if isinstance(table, Exception):
            raise table
        return table

    def rating(config: Any, fixtures: Any, date: str, scoped: bool = False) -> None:
        h.rating_calls.append({"scoped": scoped})
        if rating_error is not None:
            raise rating_error

    def process(fixture: Any, *args: Any, **kw: Any) -> tuple[list[Any], list[Any]]:
        h.process_calls.append({"sport": fixture.sport, **kw})
        return [_sheet_row(sofascore_event_id=fixture.sofascore_event_id,
                           sport=fixture.sport)], []

    monkeypatch.setattr(run_sheet, "load_side_correlations", side_corr)
    monkeypatch.setattr(run_sheet, "load_dispersion_table", load_table)
    monkeypatch.setattr(run_sheet, "load_tennis_rating", rating)
    monkeypatch.setattr(run_sheet, "process_fixture", process)
    rc = run_sheet.main()
    sheet = day / "05_sheet.json"
    rows = json.loads(sheet.read_text()) if sheet.exists() else []
    return rc, h, rows


MARKERS = {
    "cards": "cards_rule", "dispersion": "dispersion_rule",
    "k": "k_rule", "tennis": "tennis_table_rule",
}


def test_every_flag_on_reaches_every_callee_and_stamps_every_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rc, h, rows = _run(tmp_path, monkeypatch, on=set(FLAGS))
    assert rc == 0
    assert h.guard_dates == [DAY]
    assert h.side_corr_calls == [{"cards_correlation": True}]
    assert h.rating_calls == [{"scoped": True}]
    assert h.table_loads == 1
    assert len(h.process_calls) == 2
    for call in h.process_calls:
        assert call["dispersion_table"] == "TABLE"
        assert call["per_market_k_on"] is True
        assert call["stats_only"] is True
    by_sport = {r["sport"]: r for r in rows}
    assert set(by_sport) == {"football", "tennis"}
    for sport, row in by_sport.items():
        assert row["cards_rule"] == epochs.CARDS_CORRELATION
        assert row["dispersion_rule"] == epochs.COUNT_DISPERSION
        assert row["k_rule"] == epochs.PER_MARKET_K
        if sport == "tennis":
            assert row["tennis_table_rule"] == epochs.TENNIS_SCOPED_TABLE
        else:
            assert "tennis_table_rule" not in row


@pytest.mark.parametrize("stats_only, on", [
    (True, set()),
    (False, set(FLAGS)),  # enabled by date, but not a stats-only build
])
def test_off_reaches_nothing_and_stamps_no_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stats_only: bool, on: set[str],
) -> None:
    rc, h, rows = _run(tmp_path, monkeypatch, on=on, stats_only=stats_only)
    assert rc == 0
    assert h.side_corr_calls == [{"cards_correlation": False}]
    assert h.rating_calls == [{"scoped": False}]
    assert h.table_loads == 0
    for call in h.process_calls:
        assert call["dispersion_table"] is None
        assert call["per_market_k_on"] is False
    assert len(rows) == 2
    for row in rows:
        assert not set(MARKERS.values()) & set(row)


@pytest.mark.parametrize("flag", FLAGS)
def test_one_flag_stamps_only_its_own_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flag: str,
) -> None:
    # K and dispersion are guarded as a pair in production; the guard is
    # patched out here so each marker is seen alone
    rc, _h, rows = _run(tmp_path, monkeypatch, on={flag})
    assert rc == 0
    for row in rows:
        present = {k for k in MARKERS.values() if k in row}
        if flag == "tennis" and row["sport"] != "tennis":
            assert present == set()
        else:
            assert present == {MARKERS[flag]}


def test_the_k_dispersion_guard_failing_is_failed_not_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    rc, h, rows = _run(
        tmp_path, monkeypatch, on={"dispersion"},
        guard=ValueError("COUNT_DISPERSION is on but PER_MARKET_K is not"))
    assert rc == 2
    assert h.process_calls == [] and rows == []  # nothing priced under a mix
    assert "configuration error" in capsys.readouterr().err


def test_a_malformed_dispersion_file_is_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    from bet.sofa import count_dispersion as cd

    bad = tmp_path / "bad.json"
    bad.write_text('{"markets": {"goals_for": {"family": "nb", "alpha": true}}}')
    with pytest.raises(ValueError) as caught:
        cd.load_table(bad)  # the real loader's error for a malformed file
    rc, _h, rows = _run(tmp_path, monkeypatch, on={"dispersion", "k"},
                        table=caught.value)
    assert rc == 2
    assert rows == []
    assert "configuration error" in capsys.readouterr().err


def test_a_missing_dispersion_file_is_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rc, _h, rows = _run(tmp_path, monkeypatch, on={"dispersion", "k"},
                        table=FileNotFoundError("sofa_count_dispersion.json"))
    assert rc == 2 and rows == []


def test_a_v5_rating_config_without_tier_start_is_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bet.sofa import tennis_rating as tr

    with pytest.raises(ValueError) as caught:
        tr.check_start([tr.TIER_START_FEATURE], None)  # the real V5 refusal
    rc, _h, rows = _run(tmp_path, monkeypatch, on=set(), rating_error=caught.value)
    assert rc == 2 and rows == []


def test_the_guard_and_main_see_the_same_day_in_the_stage_order() -> None:
    # sanity of the harness constants: the day is a stats-only day
    assert epochs.stats_only(DAY, datetime(2026, 10, 9, 12, tzinfo=UTC))
