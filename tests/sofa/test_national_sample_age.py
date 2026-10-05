"""A national-team fixture's sample is judged by count, not age, from
epochs.NATIONAL_SAMPLE_AGE_FROM_UTC (2026-10-05 night: SAMPLE_CROSSES_SEASON
refused 157 national-team legs on 10-05, all 8 Nations League fixtures)."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from bet.sofa.epochs import national_sample_by_count
from bet.sofa.resolve import national_teams
from tests.sofa.test_stats_only_confidence import (
    KO,
    T0,
    _conf,
    _day,
    _doc,
    _row,
    _run,
    _under,
    _z,
)


def _old_samples_and_flag(runs: Path, national: bool | None) -> None:
    run = runs / "2026-10-07"
    samples = json.loads((run / "03_samples.json").read_text())
    for doc in samples:
        for side in ("side_a", "side_b"):
            for i, o in enumerate(doc["metrics"]["goals_total"][side]):
                o["match_date_utc"] = _z(T0 - timedelta(days=3 + 40 * i))
    (run / "03_samples.json").write_text(json.dumps(samples))
    fixtures = json.loads((run / "02_fixtures.json").read_text())
    for f in fixtures:
        f["national_teams"] = national
    (run / "02_fixtures.json").write_text(json.dumps(fixtures))


def _build(tmp_path: Path, monkeypatch, national: bool | None) -> dict:
    p = 0.75
    odds = round(0.95 / _conf(p), 2)
    runs = _day(tmp_path, [_row(1, p, odds, 0.70)], {1: KO[1]},
                {1: (odds, _under(odds))})
    _old_samples_and_flag(runs, national)
    assert _run(runs, monkeypatch) == 0
    return _doc(runs)


def test_a_national_fixture_with_an_old_sample_prints_with_its_age(
        tmp_path, monkeypatch):
    doc = _build(tmp_path, monkeypatch, True)
    (single,) = doc["singles"]
    assert any(f.startswith("NATIONAL_SAMPLE_AGE(oldest ")
               for f in single["context_flags"])


def test_a_club_fixture_with_the_same_sample_is_still_refused(tmp_path, monkeypatch):
    assert _build(tmp_path, monkeypatch, False)["singles"] == []
    (tmp_path / "none").mkdir()
    assert _build(tmp_path / "none", monkeypatch, None)["singles"] == []


def test_the_rule_starts_on_2026_10_06():
    from datetime import UTC, datetime

    late, early = (datetime(2026, 10, 6, 1, tzinfo=UTC),
                   datetime(2026, 10, 5, 23, tzinfo=UTC))
    assert not national_sample_by_count("2026-10-05", late)
    assert not national_sample_by_count("2026-10-06", early)
    assert national_sample_by_count("2026-10-06", late)


def test_resolve_reads_both_sides_national_flags():
    assert national_teams({"homeTeam": {"national": True},
                           "awayTeam": {"national": True}}) is True
    assert national_teams({"homeTeam": {"national": True},
                           "awayTeam": {"national": False}}) is False
    assert national_teams({"homeTeam": {}, "awayTeam": {}}) is None
